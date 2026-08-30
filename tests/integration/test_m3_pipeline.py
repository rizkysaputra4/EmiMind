"""Integration tests for Milestone 3 (Derived Metrics, Embedding, Narrative Retrieval, Issuer Profile)."""

from __future__ import annotations

import io
import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from services.ingest.tasks.ingest_document import ingest_document
from services.retrieval.narrative_retriever import (
    NarrativeFilters,
    retrieve_narrative,
)
from services.shared.config import get_settings
from services.shared.db import create_pool
from services.shared.types import FiscalPeriod, Ticker

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


class InMemoryMinioResponse:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.stream = io.BytesIO(data)

    def read(self) -> bytes:
        return self.data

    def close(self) -> None:
        pass

    def release_conn(self) -> None:
        pass


class InMemoryMinioClient:
    def __init__(self) -> None:
        self.storage: dict[str, bytes] = {}

    def put_object(
        self,
        bucket: str,
        object_name: str,
        data: io.BytesIO | bytes,
        length: int = -1,
        content_type: str = "application/octet-stream",
    ) -> None:
        if isinstance(data, io.BytesIO):
            self.storage[object_name] = data.getvalue()
        else:
            self.storage[object_name] = data

    def get_object(self, bucket: str, object_name: str) -> InMemoryMinioResponse:
        if object_name not in self.storage:
            raise FileNotFoundError(f"Object {object_name} not found in memory bucket {bucket}")
        return InMemoryMinioResponse(self.storage[object_name])


@pytest.mark.integration
async def test_full_m3_pipeline_and_retrieval() -> None:
    settings = get_settings()
    pool = create_pool(settings.postgres_dsn)
    minio_client = InMemoryMinioClient()

    pdf_path = FIXTURES_DIR / "sample_bmri.pdf"
    xbrl_path = FIXTURES_DIR / "sample_bmri.xbrl.xml"

    pdf_bytes = pdf_path.read_bytes()
    xbrl_bytes = xbrl_path.read_bytes()

    test_uid = uuid.uuid4().hex[:12]
    doc_id = str(uuid.uuid4())
    doc_hash = f"bmri_m3_test_{test_uid}"
    minio_key = f"raw/BMRI/2024Q4/{doc_hash}.pdf"
    xbrl_key = f"{minio_key}.xbrl.xml"

    # 1. Upload fixtures
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

    # 2. Insert document record
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

    # 3. Execute complete 8-step pipeline
    ctx: dict[str, Any] = {
        "db_pool": pool,
        "minio_client": minio_client,
    }

    result = await ingest_document(ctx, doc_id)
    assert result["status"] == "completed"

    async with pool.connect() as conn:
        # 4. Verify derived_metrics
        dm_res = await conn.execute(
            text(
                "SELECT metric_id, value_numeric, unit FROM derived_metrics WHERE ticker = 'BMRI' AND fiscal_period = '2024Q4'"
            ),
        )
        derived_rows = dm_res.mappings().all()
        assert len(derived_rows) >= 5

        metric_ids = [r["metric_id"] for r in derived_rows]
        assert any("bank.nim" in m or "bank.ldr" in m or "peer_pct." in m for m in metric_ids)

        # 5. Verify narrative_chunks translation and embedding
        nc_res = await conn.execute(
            text("SELECT count(*), count(text_en) FROM narrative_chunks WHERE source_doc_id = :id"),
            {"id": doc_id},
        )
        nc_counts = nc_res.fetchone()
        assert nc_counts is not None
        total_chunks, en_chunks = nc_counts
        assert total_chunks >= 1
        assert en_chunks == total_chunks

        # 6. Verify issuer_profile
        ip_res = await conn.execute(
            text(
                "SELECT ticker, name, profile_summary_en, last_facts_period FROM issuer_profile WHERE ticker = 'BMRI'"
            ),
        )
        profile = ip_res.mappings().first()
        assert profile is not None
        assert profile["last_facts_period"] == "2024Q4"
        assert len(profile["profile_summary_en"]) > 50

        # 7. Verify hybrid retrieval
        filters = NarrativeFilters(
            tickers=[Ticker("BMRI")],
            periods=[FiscalPeriod("2024Q4")],
        )
        hits = await retrieve_narrative(
            conn=conn,
            query="pertumbuhan kredit dan likuiditas",
            filters=filters,
            top_k=5,
        )
        assert len(hits) >= 1
        assert hits[0].ticker == "BMRI"
        assert "[BMRI-FS-2024Q4#" in hits[0].citation

    await pool.dispose()
