"""Unit tests for guidance actuals matcher."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.kg.actual_matcher import match_actuals_for
from services.shared.types import FiscalPeriod, Ticker


@pytest.mark.asyncio
async def test_match_actuals_within_range() -> None:
    conn = AsyncMock()

    # Guidance nodes mock
    g_res = MagicMock()
    g_res.mappings.return_value.all.return_value = [
        {
            "id": 101,
            "ticker": "BMRI",
            "fiscal_period": "2024FY",
            "payload": {
                "metric": "bank.nim",
                "low": 0.050,
                "high": 0.054,
                "period_target": "2025FY",
                "qualifier": "range",
                "unit": "RATIO",
            },
            "source_ref": {"page": 14},
        }
    ]

    # Derived actual mock (actual NIM = 5.20%)
    dm_res = MagicMock()
    dm_res.mappings.return_value.first.return_value = {
        "id": 501,
        "value_numeric": 0.052,
        "unit": "RATIO",
    }

    # Existing actual node check
    act_exist_res = MagicMock()
    act_exist_res.first.return_value = (201,)

    # Existing edge check
    edge_exist_res = MagicMock()
    edge_exist_res.first.return_value = None

    # Insert edge mock
    edge_ins_res = MagicMock()
    edge_ins_res.scalar_one.return_value = 301

    conn.execute.side_effect = [
        g_res,
        dm_res,
        act_exist_res,
        edge_exist_res,
        edge_ins_res,
    ]

    report = await match_actuals_for(conn, Ticker("BMRI"), FiscalPeriod("2025FY"))
    assert report.matched_count == 1
    assert report.edges_created == [301]
