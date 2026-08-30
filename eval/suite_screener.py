"""Eval Suite Screener: Multi-criteria natural language stock screener benchmark."""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, Field

from services.screener.executor import execute_screener
from services.screener.parser import parse_query
from services.shared.config import get_settings
from services.shared.db import create_pool
from services.shared.logging import get_logger

log = get_logger("eval.suite_screener")

# 10 curated test queries for the screener benchmark
SCREENER_TEST_CASES = [
    {
        "id": "SCR-001",
        "query": "Find IDX banks with ROE > 15% as of 2024Q4",
        "expected_sector": "BANK",
        "expected_metric": "roe",
        "must_include": ["BMRI", "BBCA", "BBRI"],
    },
    {
        "id": "SCR-002",
        "query": "Bank stocks with NIM > 5% and NPL < 2.5% in 2024Q4",
        "expected_sector": "BANK",
        "expected_metric": "bank.nim",
        "must_include": ["BMRI", "BBRI"],
    },
    {
        "id": "SCR-003",
        "query": "Companies with Net Margin > 15% in 2024Q4",
        "expected_metric": "margin.net",
        "must_include": ["BMRI", "BBCA", "ITMG"],
    },
    {
        "id": "SCR-004",
        "query": "Mining companies with Net Margin > 10% in 2024Q4",
        "expected_sector": "MINING",
        "expected_metric": "margin.net",
        "must_include": ["ADRO", "ITMG"],
    },
    {
        "id": "SCR-005",
        "query": "Top banks by ROE as of 2024Q4",
        "expected_sector": "BANK",
        "expected_metric": "roe",
        "must_include": ["BMRI", "BBCA"],
    },
    {
        "id": "SCR-006",
        "query": "Stocks with Debt to Equity < 1.0 as of 2024Q4",
        "expected_metric": "debt_equity",
        "must_include": ["ITMG", "PTBA"],
    },
    {
        "id": "SCR-007",
        "query": "Banks with CASA ratio above 65% in 2024Q4",
        "expected_sector": "BANK",
        "expected_metric": "bank.casa",
        "must_include": ["BMRI", "BBCA"],
    },
    {
        "id": "SCR-008",
        "query": "IDX banks with ROE > 10% and Debt to Equity < 5.0 in 2024Q4",
        "expected_sector": "BANK",
        "expected_metric": "roe",
        "must_include": ["BMRI", "BBRI", "BBCA"],
    },
    {
        "id": "SCR-009",
        "query": "Mining sector with production revenue growth in 2024Q4",
        "expected_sector": "MINING",
        "expected_metric": "margin.net",
        "must_include": ["ADRO"],
    },
    {
        "id": "SCR-010",
        "query": "High profitability banks with ROE > 18% as of 2024Q4",
        "expected_sector": "BANK",
        "expected_metric": "roe",
        "must_include": ["BMRI", "BBCA"],
    },
]


class ScreenerEvalReport(BaseModel):
    """Evaluation summary for screener suite."""

    total_queries: int
    passed_queries: int
    pass_rate: float
    results: list[dict[str, Any]] = Field(default_factory=list)


async def run_suite_screener() -> ScreenerEvalReport:
    """Executes the screener evaluation suite."""
    settings = get_settings()
    pool = create_pool(settings.postgres_dsn)

    passed = 0
    results: list[dict[str, Any]] = []

    async with pool.connect() as conn:
        for tc in SCREENER_TEST_CASES:
            tc_id = str(tc["id"])
            query = str(tc["query"])

            dsl = await parse_query(query, default_period="2024Q4")
            res = await execute_screener(conn, dsl)

            # Check that DSL parsed successfully with valid filters
            has_filters = len(dsl.filters) >= 1
            valid_universe = tc.get("expected_sector") is None or dsl.universe.sector == tc["expected_sector"]

            is_pass = has_filters and valid_universe
            if is_pass:
                passed += 1

            results.append(
                {
                    "id": tc_id,
                    "query": query,
                    "filters_count": len(dsl.filters),
                    "sector": dsl.universe.sector,
                    "matches_found": res.total_matches,
                    "status": "PASS" if is_pass else "FAIL",
                }
            )

    await pool.dispose()
    pass_rate = (passed / float(len(SCREENER_TEST_CASES))) * 100.0 if SCREENER_TEST_CASES else 0.0

    return ScreenerEvalReport(
        total_queries=len(SCREENER_TEST_CASES),
        passed_queries=passed,
        pass_rate=pass_rate,
        results=results,
    )


if __name__ == "__main__":
    rep = asyncio.run(run_suite_screener())
    print(f"Suite Screener: {rep.passed_queries}/{rep.total_queries} passed ({rep.pass_rate:.1f}%)")
