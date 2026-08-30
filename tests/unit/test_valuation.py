"""Unit tests for dynamic live valuation engine and tool grounding."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.derive.valuation import calculate_valuation
from services.llm.tools import handle_compute_metric


@pytest.mark.asyncio
async def test_calculate_live_valuation_mock() -> None:
    conn = AsyncMock()

    # Mock DB query results:
    # 1. doc_res
    # 2. price_res
    # 3. facts_res
    # 4. derived_res
    def _execute_side_effect(sql_stmt, params=None):
        sql_str = str(sql_stmt)
        mock_res = MagicMock()
        mappings_mock = MagicMock()
        mock_res.mappings.return_value = mappings_mock

        if "FROM documents" in sql_str:
            mappings_mock.first.return_value = {
                "fiscal_period": "2024Q4",
                "period_end": "2024-12-31",
                "ingested_at": "2025-01-15",
            }
            mappings_mock.all.return_value = []
        elif "FROM market_prices" in sql_str:
            mappings_mock.first.return_value = {
                "c": Decimal("7000.00"),
                "dt": "2026-08-29",
            }
            mappings_mock.all.return_value = []
        elif "FROM financial_facts" in sql_str:
            facts_list = [
                {"concept_id": "idx:SharesOutstanding", "value_numeric": Decimal("93333333000")},
                {"concept_id": "ifrs:BasicEarningsLossPerShare", "value_numeric": Decimal("590.00")},
                {"concept_id": "ifrs:Equity", "value_numeric": Decimal("284000000000000")},
                {"concept_id": "ifrs:Revenue", "value_numeric": Decimal("110500000000000")},
                {"concept_id": "idx:DividendPerShare", "value_numeric": Decimal("350.00")},
            ]
            mappings_mock.first.return_value = facts_list[0]
            mappings_mock.all.return_value = facts_list
        elif "FROM derived_metrics" in sql_str:
            derived_list = [
                {"metric_id": "bvps", "value_numeric": Decimal("3042.85")},
                {"metric_id": "ebitda", "value_numeric": Decimal("75000000000000")},
                {"metric_id": "net_debt", "value_numeric": Decimal("0.00")},
            ]
            mappings_mock.first.return_value = derived_list[0]
            mappings_mock.all.return_value = derived_list
        elif "FROM technical_state" in sql_str:
            mappings_mock.first.return_value = {"as_of": "2026-08-29"}
            mappings_mock.all.return_value = []
        else:
            mappings_mock.first.return_value = None
            mappings_mock.all.return_value = []

        return mock_res

    conn.execute.side_effect = _execute_side_effect

    val = await calculate_valuation(conn, "BMRI", is_live=True)

    assert val["is_live"] is True
    assert val["price"] == 7000.00
    assert val["price_date"] == "2026-08-29"
    # P/E = 7000 / 590 = 11.86
    assert val["pe"] == 11.86
    # PBV = 7000 / 3042.85 = 2.30
    assert val["pbv"] == 2.30
    # Dividend Yield = (350 / 7000) * 100 = 5.0%
    assert val["dividend_yield"] == 5.0
    # Market Cap = 7000 * 93333333000
    assert val["market_cap"] == 7000.0 * 93333333000


@pytest.mark.asyncio
async def test_tool_handle_live_compute_metric() -> None:
    conn = AsyncMock()

    def _execute_side_effect(sql_stmt, params=None):
        sql_str = str(sql_stmt)
        mock_res = MagicMock()
        mappings_mock = MagicMock()
        mock_res.mappings.return_value = mappings_mock

        if "FROM documents" in sql_str:
            mappings_mock.first.return_value = {
                "fiscal_period": "2024Q4",
                "period_end": "2024-12-31",
                "ingested_at": "2025-01-15",
            }
            mappings_mock.all.return_value = []
        elif "FROM market_prices" in sql_str:
            mappings_mock.first.return_value = {
                "c": Decimal("7000.00"),
                "dt": "2026-08-29",
            }
            mappings_mock.all.return_value = []
        elif "FROM financial_facts" in sql_str:
            facts_list = [
                {"concept_id": "idx:SharesOutstanding", "value_numeric": Decimal("93333333000")},
                {"concept_id": "ifrs:BasicEarningsLossPerShare", "value_numeric": Decimal("590.00")},
                {"concept_id": "ifrs:Equity", "value_numeric": Decimal("284000000000000")},
            ]
            mappings_mock.first.return_value = facts_list[0]
            mappings_mock.all.return_value = facts_list
        elif "FROM derived_metrics" in sql_str:
            derived_list = [
                {"metric_id": "bvps", "value_numeric": Decimal("3042.85")},
            ]
            mappings_mock.first.return_value = derived_list[0]
            mappings_mock.all.return_value = derived_list
        else:
            mappings_mock.first.return_value = None
            mappings_mock.all.return_value = []

        return mock_res

    conn.execute.side_effect = _execute_side_effect

    res = await handle_compute_metric(conn, {"ticker": "BMRI", "metric_id": "pbv", "period": "CURRENT"})
    assert "CURRENT, live on-the-fly with price IDR 7,000 as of 2026-08-29" in res
    assert "2.30" in res
    assert "[BMRI-LIVE-VALUATION-2026-08-29]" in res

