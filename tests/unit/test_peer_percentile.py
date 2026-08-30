"""Unit tests for cross-sectional peer percentile computation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.derive.recipes.peer_percentile import compute_peer_percentiles
from services.shared.types import FiscalPeriod, Ticker


@pytest.mark.asyncio
async def test_compute_peer_percentiles() -> None:
    conn = AsyncMock()

    # Mock peer groups query
    pg_row = {
        "id": "bank_kbmi4",
        "name": "KBMI 4 Banks",
        "tickers": ["BMRI", "BBRI", "BBNI", "BBCA"],
    }
    pg_res = MagicMock()
    pg_res.mappings.return_value.all.return_value = [pg_row]

    # Mock derived metrics query for peers
    m_rows = [
        {"ticker": "BMRI", "metric_id": "bank.nim", "value_numeric": 0.052},
        {"ticker": "BBRI", "metric_id": "bank.nim", "value_numeric": 0.068},
        {"ticker": "BBNI", "metric_id": "bank.nim", "value_numeric": 0.045},
        {"ticker": "BBCA", "metric_id": "bank.nim", "value_numeric": 0.055},
    ]
    m_res = MagicMock()
    m_res.mappings.return_value.all.return_value = m_rows

    conn.execute.side_effect = [pg_res, m_res]

    results = await compute_peer_percentiles(
        conn=conn,
        ticker=Ticker("BMRI"),
        fiscal_period=FiscalPeriod("2024Q4"),
    )

    assert len(results) == 1
    res = results[0]
    assert res["metric_id"] == "peer_pct.bank.nim"
    assert res["unit"] == "PCT"
    # Values: BBNI (0.045) < BMRI (0.052) < BBCA (0.055) < BBRI (0.068)
    # BMRI has 1 below it, out of 4: (1 + 0.5 * 1) / 4 * 100 = 37.5%
    assert res["value_numeric"] == 37.5
