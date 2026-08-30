"""Unit tests for recursive CTE graph traversal and query helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.kg.traversal import find_guidance_actual_triples, traverse


@pytest.mark.asyncio
async def test_kg_traversal_mock() -> None:
    conn = AsyncMock()
    mock_res = MagicMock()
    mock_res.mappings.return_value.all.return_value = [
        {
            "edge_id": 1,
            "src_id": 10,
            "dst_id": 20,
            "edge_type": "CAUSED_BY",
            "confidence": 0.75,
            "edge_payload": {"driver": "Wholesale loan growth"},
            "depth": 1,
            "sn_id": 10,
            "src_type": "CLAIM",
            "src_ticker": "BMRI",
            "src_period": "2024Q4",
            "src_payload": {"metric": "idx:LoansAndAdvances"},
            "src_ref": {"page": 2},
            "dn_id": 20,
            "dst_type": "METRIC",
            "dst_ticker": "BMRI",
            "dst_period": "2024Q4",
            "dst_payload": {"name": "Wholesale loan growth"},
            "dst_ref": {"page": 2},
        }
    ]
    conn.execute.return_value = mock_res

    triples = await traverse(conn, root_id=10, edge_types=["CAUSED_BY"])
    assert len(triples) == 1
    assert triples[0].edge["edge_type"] == "CAUSED_BY"
    assert triples[0].depth == 1
    assert triples[0].src_node["ticker"] == "BMRI"


@pytest.mark.asyncio
async def test_find_guidance_actual_triples_mock() -> None:
    conn = AsyncMock()
    mock_res = MagicMock()
    mock_res.mappings.return_value.all.return_value = [
        {
            "edge_id": 2,
            "src_id": 101,
            "dst_id": 201,
            "edge_type": "REALIZED_AS",
            "confidence": 1.0,
            "edge_payload": {"delta": 0.002, "hit_bounds": True, "status": "MET"},
            "depth": 1,
            "sn_id": 101,
            "src_type": "GUIDANCE",
            "src_ticker": "BMRI",
            "src_period": "2024FY",
            "src_payload": {
                "metric": "bank.nim",
                "low": 0.05,
                "high": 0.053,
                "period_target": "2025FY",
            },
            "src_ref": {"page": 14},
            "dn_id": 201,
            "dst_type": "ACTUAL",
            "dst_ticker": "BMRI",
            "dst_period": "2025FY",
            "dst_payload": {"metric": "bank.nim", "value": 0.052},
            "dst_ref": {"page": 6},
        }
    ]
    conn.execute.return_value = mock_res

    triples = await find_guidance_actual_triples(conn, ticker="BMRI")
    assert len(triples) == 1
    assert triples[0].edge["edge_type"] == "REALIZED_AS"
    assert triples[0].src_node["node_type"] == "GUIDANCE"
