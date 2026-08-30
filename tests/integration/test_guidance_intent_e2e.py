"""Integration tests for GUIDANCE_CHECK intent, KG traversal, and guidance matrix rendering."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from services.retrieval.chat import run_turn
from services.shared.config import get_settings
from services.shared.db import create_pool


@pytest.mark.integration
async def test_guidance_check_turn_e2e() -> None:
    settings = get_settings()
    pool = create_pool(settings.postgres_dsn)

    async with pool.connect() as conn:
        # Seed test GUIDANCE node and ACTUAL node + REALIZED_AS edge
        g_res = await conn.execute(
            text(
                """
                INSERT INTO kg_nodes (node_type, ticker, fiscal_period, payload, source_ref, created_at)
                VALUES ('GUIDANCE', 'BMRI', '2024FY', CAST(:payload AS jsonb), CAST(:sref AS jsonb), now())
                RETURNING id;
                """
            ),
            {
                "payload": json.dumps(
                    {
                        "metric": "bank.nim",
                        "low": 0.050,
                        "high": 0.053,
                        "period_target": "2025FY",
                        "qualifier": "range",
                        "unit": "RATIO",
                        "verbatim": "NIM target 5.0 - 5.3% for 2025.",
                    }
                ),
                "sref": json.dumps({"page": 14, "doc_id": "test_doc"}),
            },
        )
        g_id = g_res.scalar_one()

        a_res = await conn.execute(
            text(
                """
                INSERT INTO kg_nodes (node_type, ticker, fiscal_period, payload, source_ref, created_at)
                VALUES ('ACTUAL', 'BMRI', '2025FY', CAST(:payload AS jsonb), CAST(:sref AS jsonb), now())
                RETURNING id;
                """
            ),
            {
                "payload": json.dumps({"metric": "bank.nim", "value": 0.052, "unit": "RATIO"}),
                "sref": json.dumps({"page": 6, "doc_id": "test_doc"}),
            },
        )
        a_id = a_res.scalar_one()

        await conn.execute(
            text(
                """
                INSERT INTO kg_edges (src_id, dst_id, edge_type, confidence, payload, created_at)
                VALUES (:src, :dst, 'REALIZED_AS', 1.0, CAST(:payload AS jsonb), now());
                """
            ),
            {
                "src": g_id,
                "dst": a_id,
                "payload": json.dumps(
                    {
                        "delta": 0.0005,
                        "hit_bounds": True,
                        "status": "MET",
                    }
                ),
            },
        )
        await conn.commit()

        # Run GUIDANCE_CHECK turn
        resp = await run_turn(
            conn=conn,
            session_id=None,
            message="Did BMRI meet their loan growth and NIM guidance targets for 2025?",
            focus_ticker="BMRI",
        )

        assert resp.session_id is not None
        assert len(resp.answer) > 0
        assert len(resp.citations) >= 1

    await pool.dispose()
