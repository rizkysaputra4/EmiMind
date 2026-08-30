"""Screener query execution engine over PostgreSQL derived metrics and issuer profiles."""

from __future__ import annotations

import json
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from services.screener.compiler import compile_to_sql
from services.screener.dsl import ScreenerDSL, ScreenerResult, ScreenerRow
from services.shared.logging import get_logger
from services.shared.types import Ticker

log = get_logger("screener.executor")


async def execute_screener(
    conn: AsyncConnection,
    dsl: ScreenerDSL,
) -> ScreenerResult:
    """Compiles and executes ScreenerDSL over database returning validated rows and provenance."""
    sql, params = compile_to_sql(dsl)
    log.info("Executing screener query", limit=dsl.limit, filters_count=len(dsl.filters))

    res = await conn.execute(text(sql), params)
    rows = res.mappings().all()

    result_rows: list[ScreenerRow] = []
    for r in rows:
        ticker = Ticker(r["ticker"])
        raw_vals = r["metric_values"]
        m_vals = raw_vals if isinstance(raw_vals, dict) else json.loads(raw_vals or "{}")

        metric_values: dict[str, Decimal] = {}
        for k, v in m_vals.items():
            if v is not None:
                metric_values[k] = Decimal(str(v))

        raw_prov = r["provenance"]
        provenance = raw_prov if isinstance(raw_prov, list) else json.loads(raw_prov or "[]")

        result_rows.append(
            ScreenerRow(
                ticker=ticker,
                metric_values=metric_values,
                provenance=provenance,
            )
        )

    return ScreenerResult(
        dsl=dsl,
        rows=result_rows,
        total_matches=len(result_rows),
    )
