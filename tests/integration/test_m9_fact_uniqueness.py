"""Integration test for full-segment financial fact uniqueness constraint."""

from __future__ import annotations

import json
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from services.mcp.server import get_engine


@pytest.mark.integration
@pytest.mark.asyncio
async def test_m9_fact_segment_uniqueness() -> None:
    engine = get_engine()
    doc_id = str(uuid.uuid4())
    ticker = "TEST_UNQ"
    period = "2025Q4"
    cid = "idx:LoansAndAdvances"

    async with engine.connect() as conn:
        # Clean up any leftover test data
        await conn.execute(text("DELETE FROM financial_facts WHERE ticker = :t"), {"t": ticker})
        await conn.execute(text("DELETE FROM documents WHERE id = :d"), {"d": doc_id})

        # Insert dummy document for FK
        await conn.execute(
            text(
                """
                INSERT INTO documents (id, ticker, doc_type, period_end, fiscal_period, language, source_url, minio_key, doc_hash, page_count, status)
                VALUES (:id, :ticker, 'FS_ANNUAL', '2025-12-31', :period, 'id', 'test://url', 'test/key', :hash, 1, 'raw');
                """
            ),
            {"id": doc_id, "ticker": ticker, "period": period, "hash": f"hash_{doc_id}"},
        )

        insert_sql = """
        INSERT INTO financial_facts (
            source_doc_id, ticker, period_end, fiscal_period, statement, concept_id, concept_local,
            value_numeric, unit, segment, period_type, accounting_std, source_page, extraction_conf, extraction_method
        ) VALUES (
            :doc_id, :ticker, '2025-12-31', :period, 'NOTE', :concept_id, 'Kredit',
            :val, 'IDR', CAST(:seg AS jsonb), 'instant', 'IFRS', 5, 0.95, 'llm_extract'
        )
        ON CONFLICT (ticker, fiscal_period, concept_id, (coalesce(segment, '{}'::jsonb)))
        WHERE is_restated = false
        DO UPDATE SET
            value_numeric = EXCLUDED.value_numeric,
            extraction_conf = EXCLUDED.extraction_conf;
        """

        seg1 = {"collectibility": "Lancar", "segment": "Korporasi"}
        seg2 = {"collectibility": "Lancar", "segment": "UMKM"}

        # 1. Insert first fact
        await conn.execute(
            text(insert_sql),
            {
                "doc_id": doc_id,
                "ticker": ticker,
                "period": period,
                "concept_id": cid,
                "val": float(Decimal("100.0")),
                "seg": json.dumps(seg1),
            },
        )

        # 2. Insert second fact
        await conn.execute(
            text(insert_sql),
            {
                "doc_id": doc_id,
                "ticker": ticker,
                "period": period,
                "concept_id": cid,
                "val": float(Decimal("50.0")),
                "seg": json.dumps(seg2),
            },
        )

        # Assert 2 rows exist
        cnt_res = await conn.execute(
            text("SELECT count(*) FROM financial_facts WHERE ticker = :t AND fiscal_period = :p"),
            {"t": ticker, "p": period},
        )
        assert cnt_res.scalar() == 2

        # 3. Re-insert first fact with new value (upsert)
        await conn.execute(
            text(insert_sql),
            {
                "doc_id": doc_id,
                "ticker": ticker,
                "period": period,
                "concept_id": cid,
                "val": float(Decimal("150.0")),
                "seg": json.dumps(seg1),
            },
        )

        # Assert still 2 rows, and value updated
        cnt_res2 = await conn.execute(
            text("SELECT count(*) FROM financial_facts WHERE ticker = :t AND fiscal_period = :p"),
            {"t": ticker, "p": period},
        )
        assert cnt_res2.scalar() == 2

        val_res = await conn.execute(
            text(
                """
                SELECT value_numeric FROM financial_facts
                WHERE ticker = :t AND fiscal_period = :p AND segment = CAST(:seg AS jsonb)
                """
            ),
            {"t": ticker, "p": period, "seg": json.dumps(seg1)},
        )
        assert val_res.scalar() == Decimal("150.0000")

        # Cleanup
        await conn.execute(text("DELETE FROM financial_facts WHERE ticker = :t"), {"t": ticker})
        await conn.execute(text("DELETE FROM documents WHERE id = :d"), {"d": doc_id})
        await conn.commit()
