"""Integration test configuration and fixtures."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import fitz  # type: ignore[import-untyped]
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from services.api.deps import get_db, get_db_conn, get_minio_client, get_redis
from services.api.main import app


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
