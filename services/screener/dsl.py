"""Screener Domain Specific Language (DSL) models and validation schemas."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

from services.shared.types import FiscalPeriod, Ticker


class Universe(BaseModel):
    """Universe filter defining company population to screen over."""

    index: Literal["IDX_ALL", "LQ45", "KOMPAS100"] | None = None
    sector: str | None = None
    sub_sector: str | None = None
    peer_group_id: str | None = None
    tickers: list[Ticker] | None = None


class Filter(BaseModel):
    """Quantitative threshold filter applied to a financial metric or fact."""

    metric: str
    op: Literal[">", "<", ">=", "<=", "==", "!="]
    value: Decimal
    period_offset: int = 0


class Sort(BaseModel):
    """Sorting criterion on a metric."""

    metric: str
    dir: Literal["asc", "desc"] = "desc"


class ScreenerDSL(BaseModel):
    """Structured domain-specific language query for multi-criteria screening."""

    universe: Universe = Field(default_factory=Universe)
    filters: list[Filter] = Field(default_factory=list, max_length=20)
    as_of: FiscalPeriod = Field(default_factory=lambda: FiscalPeriod('2024Q4'))
    sort: Sort | None = None
    limit: int = Field(default=25, ge=1, le=100)


class ScreenerRow(BaseModel):
    """A single matched ticker row with extracted metric values and provenance citations."""

    ticker: Ticker
    metric_values: dict[str, Decimal] = Field(default_factory=dict)
    provenance: list[dict[str, Any]] = Field(default_factory=list)


class ScreenerResult(BaseModel):
    """Complete screener output containing compiled DSL and matched candidate rows."""

    dsl: ScreenerDSL
    rows: list[ScreenerRow] = Field(default_factory=list)
    total_matches: int = 0
