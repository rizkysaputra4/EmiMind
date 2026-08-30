"""Unit tests for tool definitions, validation schemas, and tool execution handlers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.llm.tools import (
    TOOL_DEFS,
    handle_compute_metric,
    handle_expand_evidence,
    handle_list_periods,
)


def test_tool_defs_registry() -> None:
    tool_names = [t.name for t in TOOL_DEFS]
    assert "expand_evidence" in tool_names
    assert "compute_metric" in tool_names
    assert "list_periods" in tool_names
    assert "run_screener" in tool_names
    assert "fetch_price_action" in tool_names


@pytest.mark.asyncio
async def test_handle_list_periods() -> None:
    conn = AsyncMock()
    res = MagicMock()
    res.fetchall.return_value = [("2024Q4",), ("2024Q3",), ("2023FY",)]
    conn.execute.return_value = res

    output = await handle_list_periods(conn, {"ticker": "BMRI"})
    assert "BMRI: 2024Q4, 2024Q3, 2023FY" in output


@pytest.mark.asyncio
async def test_handle_compute_metric() -> None:
    conn = AsyncMock()
    res = MagicMock()
    res.mappings.return_value.first.return_value = {
        "value_numeric": 0.052,
        "unit": "RATIO",
    }
    conn.execute.return_value = res

    output = await handle_compute_metric(
        conn, {"ticker": "BMRI", "metric_id": "bank.nim", "period": "2024Q4"}
    )
    assert "BMRI bank.nim (2024Q4): 0.0520 RATIO [BMRI-DERIVED-2024Q4]" in output


@pytest.mark.asyncio
async def test_handle_expand_evidence() -> None:
    conn = AsyncMock()
    res = MagicMock()
    res.mappings.return_value.first.return_value = {
        "ticker": "BMRI",
        "fiscal_period": "2024Q4",
        "section": "MDA",
        "source_page": 2,
        "text_original": "Pertumbuhan kredit mencapai 16.3% YoY.",
        "text_en": "Loan growth reached 16.3% YoY.",
    }
    conn.execute.return_value = res

    output = await handle_expand_evidence(conn, {"chunk_id": 5})
    assert "**Expanded Evidence for Chunk #5** [BMRI-FS-2024Q4#p2]" in output
    assert "Loan growth reached 16.3% YoY." in output
