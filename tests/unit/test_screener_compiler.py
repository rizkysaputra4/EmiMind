"""Unit tests for Screener SQL compiler."""

from __future__ import annotations

from decimal import Decimal

from services.screener.compiler import compile_to_sql
from services.screener.dsl import Filter, ScreenerDSL, Sort, Universe
from services.shared.types import FiscalPeriod


def test_compile_to_sql_structure() -> None:
    dsl = ScreenerDSL(
        universe=Universe(sector="BANK"),
        filters=[
            Filter(metric="roe", op=">", value=Decimal("0.15")),
            Filter(metric="bank.nim", op=">=", value=Decimal("0.05")),
        ],
        as_of=FiscalPeriod("2024Q4"),
        sort=Sort(metric="roe", dir="desc"),
        limit=20,
    )

    sql, params = compile_to_sql(dsl)

    assert "WITH candidates AS" in sql
    assert "INTERSECT" in sql
    assert "JOIN derived_metrics d" in sql
    assert "WHERE (CAST(:sector AS text) IS NULL OR ip.sector = :sector" in sql
    assert "LIMIT :limit" in sql

    assert params["as_of"] == "2024Q4"
    assert params["limit"] == 20
    assert params["sector"] == "BANK"
    assert params["metric_0"] == "roe"
    assert params["val_0"] == 0.15
    assert params["metric_1"] == "bank.nim"
    assert params["val_1"] == 0.05
