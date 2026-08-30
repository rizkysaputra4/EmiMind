"""Unit tests for mining (coal) sector KPI recipes."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from services.derive.recipes.mining import (
    recipe_mining_asp,
    recipe_mining_cash_cost,
    recipe_mining_ni_margin,
    recipe_mining_strip_ratio,
)
from services.derive.registry import FactValue, RecipeContext
from services.shared.types import FiscalPeriod, Ticker


@pytest.mark.asyncio
async def test_mining_recipes() -> None:
    facts = AsyncMock()
    facts.get.side_effect = lambda c, period=None: {
        "idx:CashCostPerTon": FactValue(
            id=1,
            concept_id="idx:CashCostPerTon",
            value_numeric=Decimal("42.50"),
            unit="USD/ton",
            period_type="duration_ytd",
            accounting_std="IFRS",
            period_end="2024-12-31",
        ),
        "idx:StripRatio": FactValue(
            id=2,
            concept_id="idx:StripRatio",
            value_numeric=Decimal("4.80"),
            unit="bcm/ton",
            period_type="duration_ytd",
            accounting_std="IFRS",
            period_end="2024-12-31",
        ),
        "idx:AverageSellingPrice": FactValue(
            id=3,
            concept_id="idx:AverageSellingPrice",
            value_numeric=Decimal("88.20"),
            unit="USD/ton",
            period_type="duration_ytd",
            accounting_std="IFRS",
            period_end="2024-12-31",
        ),
        "ifrs:Revenue": FactValue(
            id=4,
            concept_id="ifrs:Revenue",
            value_numeric=Decimal("5000000"),
            unit="USD",
            period_type="duration_ytd",
            accounting_std="IFRS",
            period_end="2024-12-31",
        ),
        "ifrs:ProfitLoss": FactValue(
            id=5,
            concept_id="ifrs:ProfitLoss",
            value_numeric=Decimal("1250000"),
            unit="USD",
            period_type="duration_ytd",
            accounting_std="IFRS",
            period_end="2024-12-31",
        ),
    }.get(c)

    ctx = RecipeContext(
        ticker=Ticker("ADRO"),
        fiscal_period=FiscalPeriod("2024Q4"),
        facts=facts,
        peers=AsyncMock(),
    )

    cost = await recipe_mining_cash_cost(ctx)
    assert cost is not None
    assert cost.value == Decimal("42.500000")
    assert cost.unit == "USD/ton"

    sr = await recipe_mining_strip_ratio(ctx)
    assert sr is not None
    assert sr.value == Decimal("4.800000")

    asp = await recipe_mining_asp(ctx)
    assert asp is not None
    assert asp.value == Decimal("88.200000")

    margin = await recipe_mining_ni_margin(ctx)
    assert margin is not None
    # 1250000 / 5000000 = 0.25 (25%)
    assert margin.value == Decimal("0.250000")
