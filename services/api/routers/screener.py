"""Screener API router compiling natural language and DSL queries to database results."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncConnection

from services.api.deps import get_db_conn
from services.screener.dsl import ScreenerDSL
from services.screener.executor import execute_screener
from services.screener.parser import parse_query
from services.screener.renderers import render_screener_results_table

router = APIRouter(prefix="/api/v1", tags=["screener"])


class ScreenerAPIRequest(BaseModel):
    """API request accepting either a natural language string or a structured ScreenerDSL."""

    query: str | None = None
    dsl: ScreenerDSL | None = None
    default_period: str = "2024Q4"


class ScreenerAPIResponse(BaseModel):
    """API response containing parsed DSL, matched rows, and rendered markdown table."""

    dsl: ScreenerDSL
    total_matches: int
    rows: list[dict[str, Any]]
    table_md: str


@router.post("/screener", response_model=ScreenerAPIResponse)
async def screen_tickers(
    payload: ScreenerAPIRequest,
    conn: AsyncConnection = Depends(get_db_conn),
) -> ScreenerAPIResponse:
    """Screens universe of companies based on natural language or structured DSL criteria."""
    if payload.dsl is not None:
        dsl = payload.dsl
    elif payload.query:
        dsl = await parse_query(payload.query, default_period=payload.default_period)
    else:
        raise HTTPException(status_code=400, detail="Either 'query' or 'dsl' must be provided.")

    result = await execute_screener(conn, dsl)
    table_md = render_screener_results_table(result)

    serialized_rows: list[dict[str, Any]] = []
    for r in result.rows:
        serialized_rows.append(
            {
                "ticker": str(r.ticker),
                "metric_values": {k: float(v) for k, v in r.metric_values.items()},
                "provenance": r.provenance,
            }
        )

    return ScreenerAPIResponse(
        dsl=result.dsl,
        total_matches=result.total_matches,
        rows=serialized_rows,
        table_md=table_md,
    )
