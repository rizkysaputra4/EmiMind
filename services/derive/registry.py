"""Derived metrics recipe registry and execution context."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from services.shared.db import active_facts_query
from services.shared.types import FiscalPeriod, Ticker


class FactValue(BaseModel):
    id: int
    concept_id: str
    value_numeric: Decimal
    unit: str | None
    period_type: str
    accounting_std: str | None
    period_end: Any


class FactsAccessor:
    """Provides async query helpers for financial facts with confidence gating."""

    def __init__(self, conn: AsyncConnection, ticker: Ticker, fiscal_period: FiscalPeriod) -> None:
        self.conn = conn
        self.ticker = ticker
        self.fiscal_period = fiscal_period
        self._cache: dict[tuple[str, str], FactValue | None] = {}

    async def get(self, concept_id: str, period: str | None = None) -> FactValue | None:
        """Retrieves active fact value by concept_id and fiscal_period."""
        target_period = period or self.fiscal_period
        cache_key = (concept_id, target_period)
        if cache_key in self._cache:
            return self._cache[cache_key]

        sql, params = active_facts_query(
            ticker=self.ticker,
            fiscal_period=target_period,
            concept_id=concept_id,
        )
        res = await self.conn.execute(text(sql), params)
        row = res.mappings().first()
        if not row or row["value_numeric"] is None:
            self._cache[cache_key] = None
            return None

        val = FactValue(
            id=row["id"],
            concept_id=row["concept_id"],
            value_numeric=Decimal(str(row["value_numeric"])),
            unit=row["unit"],
            period_type=row["period_type"],
            accounting_std=row["accounting_std"],
            period_end=row["period_end"],
        )
        self._cache[cache_key] = val
        return val


class PeersAccessor:
    """Provides access to peer group memberships and peer metrics."""

    def __init__(self, conn: AsyncConnection, ticker: Ticker) -> None:
        self.conn = conn
        self.ticker = ticker

    async def get_peer_groups(self) -> list[dict[str, Any]]:
        """Retrieves peer groups containing this ticker."""
        res = await self.conn.execute(
            text(
                "SELECT id, name, tickers, sector, sub_sector FROM peer_groups WHERE :ticker = ANY(tickers)"
            ),
            {"ticker": self.ticker},
        )
        return [dict(r) for r in res.mappings()]


class RecipeContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    ticker: Ticker
    fiscal_period: FiscalPeriod
    facts: Any  # FactsAccessor
    peers: Any  # PeersAccessor


class RecipeResult(BaseModel):
    value: Decimal | None
    unit: str
    inputs: dict[str, Any]  # {"fact_ids": [...], "formula": "...", "comparability_flag": bool}


Recipe = Callable[[RecipeContext], Awaitable[RecipeResult | None]]


@dataclass
class RecipeSpec:
    metric_id: str
    version: str
    sector: str | None  # None = generic
    depends_on: list[str]  # concept_ids or other metric_ids
    fn: Recipe


REGISTRY: dict[str, RecipeSpec] = {}


def recipe(
    metric_id: str,
    version: str = "1.0",
    sector: str | None = None,
    depends_on: list[str] | None = None,
) -> Callable[[Recipe], Recipe]:
    """Decorator registering a metric calculation recipe."""

    def deco(fn: Recipe) -> Recipe:
        REGISTRY[metric_id] = RecipeSpec(metric_id, version, sector, depends_on or [], fn)
        return fn

    return deco
