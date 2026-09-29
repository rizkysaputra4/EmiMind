"""Integration test configuration and fixtures.

Integration tests run against an isolated database (``emimind_test`` by default), never the
dev database. The database is created on first use, every ``db/schema/*.sql`` migration is
applied in order (tracked in ``schema_migrations``), the config/ontology seed scripts are run
once, and documents created during the session are deleted at teardown.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import fitz  # type: ignore[import-untyped]
import psycopg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from services.api.deps import get_db, get_db_conn, get_minio_client, get_redis
from services.api.main import app
from services.shared.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / "db" / "schema"
TEST_DB_NAME = os.environ.get("EMI_TEST_DB_NAME", "emimind_test")
DEV_DB_NAMES = {"emimind"}
SEED_MODULES = [
    "scripts.seed_concept_map",
    "scripts.seed_xbrl_alias",
    "scripts.seed_metric_ontology",
    "scripts.seed_extraction_narratives",
    "scripts.seed_idx_tickers",
    "scripts.seed_peer_groups",
    "scripts.seed_announcement_class_rules",
    "scripts.seed_announcement_contracts",
]


def _swap_db(dsn: str, db_name: str) -> str:
    base, _, _old = dsn.rpartition("/")
    return f"{base}/{db_name}"


def _sync(dsn: str) -> str:
    return dsn.replace("postgresql+asyncpg://", "postgresql://")


def _ensure_test_database(sync_dsn: str) -> bool:
    """Creates the test database if missing; returns True when it was just created."""
    with psycopg.connect(_swap_db(sync_dsn, "postgres"), autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB_NAME,)
        ).fetchone()
        if exists:
            return False
        conn.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
        return True


def _apply_migrations(test_sync_dsn: str) -> list[str]:
    applied_now: list[str] = []
    with psycopg.connect(test_sync_dsn) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "filename text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        conn.commit()
        applied = {r[0] for r in conn.execute("SELECT filename FROM schema_migrations")}
        for sql_file in sorted(SCHEMA_DIR.glob("*.sql")):
            if sql_file.name in applied:
                continue
            with conn.transaction():
                conn.execute(sql_file.read_text(encoding="utf-8"))  # type: ignore[call-overload]
                conn.execute(
                    "INSERT INTO schema_migrations (filename) VALUES (%s)", (sql_file.name,)
                )
            applied_now.append(sql_file.name)
    return applied_now


def _seed_config(test_dsn: str, test_sync_dsn: str) -> None:
    with psycopg.connect(test_sync_dsn) as conn:
        row = conn.execute("SELECT count(*) FROM issuer_profile").fetchone()
        if row and int(row[0]) > 0:
            return
    env = {**os.environ, "EMI_POSTGRES_DSN": test_dsn, "EMI_POSTGRES_DSN_SYNC": test_sync_dsn}
    for module in SEED_MODULES:
        proc = subprocess.run(  # noqa: S603
            [sys.executable, "-m", module],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"Seeding test DB with {module} failed: {proc.stderr[-2000:]}")


@pytest.fixture(scope="session", autouse=True)
def isolated_test_database() -> Iterator[str]:
    """Points every integration test at ``emimind_test`` and cleans up created documents."""
    base = get_settings()
    test_dsn = _swap_db(base.postgres_dsn, TEST_DB_NAME)
    test_sync_dsn = _sync(test_dsn)
    if TEST_DB_NAME in DEV_DB_NAMES:
        raise RuntimeError(f"Refusing to run integration tests against dev DB {TEST_DB_NAME!r}")
    _ensure_test_database(_sync(base.postgres_dsn))
    _apply_migrations(test_sync_dsn)
    _seed_config(test_dsn, test_sync_dsn)

    saved = {k: os.environ.get(k) for k in ("EMI_POSTGRES_DSN", "EMI_POSTGRES_DSN_SYNC")}
    os.environ["EMI_POSTGRES_DSN"] = test_dsn
    os.environ["EMI_POSTGRES_DSN_SYNC"] = test_sync_dsn
    get_settings.cache_clear()
    active = get_settings().postgres_dsn.rpartition("/")[2]
    if active != TEST_DB_NAME:
        raise RuntimeError(f"Integration settings still point at {active!r}, not {TEST_DB_NAME!r}")

    started = datetime.now(UTC)
    with psycopg.connect(test_sync_dsn) as conn:
        before = {str(r[0]) for r in conn.execute("SELECT id FROM documents")}
    try:
        yield test_dsn
    finally:
        with psycopg.connect(test_sync_dsn) as conn:
            created = [
                str(r[0])
                for r in conn.execute("SELECT id FROM documents")
                if str(r[0]) not in before
            ]
            if created:
                conn.execute("DELETE FROM documents WHERE id = ANY(%s::uuid[])", (created,))
            conn.execute("DELETE FROM document_processing_log WHERE created_at >= %s", (started,))
            conn.execute("DELETE FROM worker_runs WHERE started_at >= %s", (started,))
            conn.commit()
        for key, val in saved.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
        get_settings.cache_clear()


def _create_minimal_pdf_bytes() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (50, 72),
        "PT BANK MANDIRI (PERSERO) TBK\nLAPORAN POSISI KEUANGAN\nNet Interest Income: 72,300",
    )
    b = doc.tobytes()
    doc.close()
    return bytes(b)


@pytest_asyncio.fixture
async def async_client() -> AsyncIterator[AsyncClient]:
    """Async HTTP client with mocked external services for API route testing."""
    mock_engine = MagicMock()
    mock_minio = MagicMock()
    mock_redis = AsyncMock()

    pdf_bytes = _create_minimal_pdf_bytes()
    mock_response = MagicMock()
    mock_response.read.return_value = pdf_bytes
    mock_minio.get_object.return_value = mock_response

    app.state.db_engine = mock_engine
    app.state.minio_client = mock_minio
    app.state.redis_pool = mock_redis

    mock_db_conn = AsyncMock()

    async def mock_execute(stmt: Any, params: dict[str, Any] | None = None) -> MagicMock:
        cursor = MagicMock()
        stmt_str = str(stmt)

        cursor.scalar.return_value = 1
        cursor.fetchall.return_value = [("2024Q4",)]
        cursor.mappings.return_value.all.return_value = []

        if "WHERE doc_hash =" in stmt_str or "WHERE doc_hash=" in stmt_str:
            cursor.mappings.return_value.first.return_value = None
        elif "financial_facts" in stmt_str:
            cursor.mappings.return_value.first.return_value = {
                "id": 1,
                "ticker": "BMRI",
                "fiscal_period": "2024Q4",
                "concept_id": "idx:NetInterestIncome",
                "concept_local": "Pendapatan Bunga Bersih",
                "value_numeric": 72300000000000.0,
                "unit": "IDR",
                "source_page": 1,
                "source_bbox": [50.0, 100.0, 400.0, 120.0],
                "confidence": 0.95,
                "method": "table_parser",
            }
        else:
            cursor.mappings.return_value.first.return_value = {
                "id": "00000000-0000-0000-0000-000000000001",
                "user_id": None,
                "title": None,
                "sticky_state": {},
                "rolling_summary": "",
                "created_at": "2026-08-27 10:00:00",
                "last_activity_at": "2026-08-27 10:00:00",
                "ticker": "BMRI",
                "doc_type": "FS_QUARTERLY",
                "fiscal_period": "2024Q4",
                "period_end": "2024-12-31",
                "minio_key": "raw/BMRI/2024Q4/test.pdf",
                "doc_hash": "testhash",
                "status": "raw",
                "concept_id": "idx:NetInterestIncome",
                "concept_local": "Pendapatan Bunga Bersih",
                "value_numeric": 72300000000000.0,
                "unit": "IDR",
                "source_page": 1,
                "source_bbox": [50.0, 100.0, 400.0, 120.0],
                "confidence": 0.95,
                "method": "table_parser",
                "section": "MDA",
                "text_original": "Test narrative",
                "text_en": "Test narrative EN",
            }

        cursor.mappings.return_value.one.return_value = {
            "id": 1,
            "session_id": "00000000-0000-0000-0000-000000000001",
            "role": "user",
            "content": "test",
            "retrieval_manifest": None,
            "token_usage": None,
            "latency_ms": 10,
            "ts": "2026-08-27 10:00:00",
            "status": "raw",
        }
        return cursor

    mock_db_conn.execute.side_effect = mock_execute

    async def override_get_db_conn() -> AsyncIterator[AsyncMock]:
        yield mock_db_conn

    def override_get_minio() -> MagicMock:
        return mock_minio

    def override_get_redis() -> AsyncMock:
        return mock_redis

    app.dependency_overrides[get_db_conn] = override_get_db_conn
    app.dependency_overrides[get_db] = override_get_db_conn
    app.dependency_overrides[get_minio_client] = override_get_minio
    app.dependency_overrides[get_redis] = override_get_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    app.dependency_overrides.clear()
