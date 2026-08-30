"""Unit tests for Screener DSL schema and models."""

from __future__ import annotations

from decimal import Decimal

from services.screener.dsl import Filter, ScreenerDSL, Sort, Universe
from services.shared.types import FiscalPeriod


def test_screener_dsl_instantiation() -> None:
    dsl = ScreenerDSL(
        universe=Universe(index="IDX_ALL", sector="BANK"),
        filters=[
            Filter(metric="roe", op=">", value=Decimal("0.15")),
            Filter(metric="bank.nim", op=">=", value=Decimal("0.05")),
        ],
        as_of=FiscalPeriod("2024Q4"),
        sort=Sort(metric="roe", dir="desc"),
        limit=10,
    )

    assert dsl.universe.sector == "BANK"
    assert len(dsl.filters) == 2
    assert dsl.as_of == FiscalPeriod("2024Q4")
    assert dsl.sort is not None
    assert dsl.sort.metric == "roe"
    assert dsl.limit == 10


def test_screener_dsl_defaults() -> None:
    dsl = ScreenerDSL()
    assert dsl.limit == 25
    assert dsl.filters == []
