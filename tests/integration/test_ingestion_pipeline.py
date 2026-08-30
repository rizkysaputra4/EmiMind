"""Integration tests for the complete Milestone 2 document ingestion pipeline."""

from __future__ import annotations

import io
import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from services.ingest.tasks.ingest_document import ingest_document
from services.shared.config import get_settings
from services.shared.db import active_facts_query, create_pool

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


class InMemoryMinioResponse:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def read(self) -> bytes:
        return self.data

    def close(self) -> None:
        pass

    def release_conn(self) -> None:
        pass


class InMemoryMinioClient:
    def __init__(self) -> None:
        self.storage: dict[str, bytes] = {}

    def bucket_exists(self, bucket_name: str) -> bool:
        return True

    def make_bucket(self, bucket_name: str) -> None:
        pass

    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data: io.BytesIO | Any,
        length: int,
        content_type: str = "application/octet-stream",
    ) -> None:
        self.storage[object_name] = data.read()

    def get_object(self, bucket_name: str, object_name: str) -> InMemoryMinioResponse:
        if object_name not in self.storage:
            raise KeyError(f"Object {object_name} not found in MinIO bucket {bucket_name}")
        return InMemoryMinioResponse(self.storage[object_name])


@pytest.mark.integration
async def test_full_ingestion_pipeline_with_xbrl_and_pdf() -> None:
    settings = get_settings()
    pool = create_pool(settings.postgres_dsn)
    minio_client = InMemoryMinioClient()

    pdf_path = FIXTURES_DIR / "sample_bmri.pdf"
    xbrl_path = FIXTURES_DIR / "sample_bmri.xbrl.xml"

    pdf_bytes = pdf_path.read_bytes()
    xbrl_bytes = xbrl_path.read_bytes()

    test_uid = uuid.uuid4().hex[:12]
    doc_id = str(uuid.uuid4())
    doc_hash = f"bmri_test_hash_{test_uid}"
    minio_key = f"raw/BMRI/2024Q4/{doc_hash}.pdf"
    xbrl_key = f"{minio_key}.xbrl.xml"

    # 1. Upload fixtures to MinIO
    minio_client.put_object(
        settings.minio_bucket_raw,
        minio_key,
        io.BytesIO(pdf_bytes),
        length=len(pdf_bytes),
        content_type="application/pdf",
    )
    minio_client.put_object(
        settings.minio_bucket_raw,
        xbrl_key,
        io.BytesIO(xbrl_bytes),
        length=len(xbrl_bytes),
        content_type="application/xml",
    )

    # 2. Insert document record in PostgreSQL
    async with pool.connect() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO documents (id, ticker, doc_type, period_end, fiscal_period, language, minio_key, doc_hash, status)
                VALUES (:id, 'BMRI', 'FS_QUARTERLY', '2024-12-31', '2024Q4', 'id', :key, :hash, 'raw')
                ON CONFLICT (doc_hash) DO UPDATE SET status = 'raw';
                """
            ),
            {"id": doc_id, "key": minio_key, "hash": doc_hash},
        )
        await conn.commit()

    # 3. Execute ingestion pipeline
    ctx = {
        "db_pool": pool,
        "minio_client": minio_client,
    }

    result = await ingest_document(ctx, doc_id)
    assert result["status"] == "completed"

    # 4. Verify facts in PostgreSQL using active_facts_query
    sql, params = active_facts_query(ticker="BMRI", fiscal_period="2024Q4")
    async with pool.connect() as conn:
        res = await conn.execute(text(sql), params)
        facts = res.mappings().all()

        assert len(facts) >= 5
        concept_ids = [f["concept_id"] for f in facts]
        assert any("Assets" in c or "Interest" in c or "Profit" in c for c in concept_ids)

        # 5. Verify narrative chunks in PostgreSQL
        c_res = await conn.execute(
            text("SELECT count(*) FROM narrative_chunks WHERE source_doc_id = :id;"),
            {"id": doc_id},
        )
        chunks_count = c_res.fetchone()[0]  # type: ignore[index]
        assert chunks_count >= 1

        # 6. Verify worker_runs recorded ok for all tasks
        wr_res = await conn.execute(
            text("SELECT worker_name, status FROM worker_runs WHERE doc_hash = :hash;"),
            {"hash": doc_hash},
        )
        runs = {r["worker_name"]: r["status"] for r in wr_res.mappings()}
        assert runs.get("parse_layout") == "ok"
        assert runs.get("extract_tables") == "ok"
        assert runs.get("normalize_facts") == "ok"
        assert runs.get("chunk_narrative") == "ok"

    await pool.dispose()
