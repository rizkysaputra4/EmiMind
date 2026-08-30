"""Unit tests for newly added sector recipes (CPO, Telco, Insurance)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from services.derive.recipes.cpo import compute_cpo_price_realized
from services.derive.recipes.insurance import compute_insurance_rbc
from services.derive.recipes.telco import compute_telco_ebitda_margin
from services.derive.registry import FactsAccessor, FactValue, PeersAccessor, RecipeContext
from services.shared.types import FiscalPeriod, Ticker


@pytest.mark.asyncio
async def test_cpo_recipe_price_realized() -> None:
    facts = AsyncMock(spec=FactsAccessor)
    facts.get.side_effect = lambda cid, p: {
        "idx:CPORevenue": FactValue(
            id=1,
            concept_id="idx:CPORevenue",
            value_numeric=Decimal("12000000000000"),
            unit="IDR",
            period_type="duration",
            accounting_std="IFRS",
            period_end=None,
        ),
        "idx:CPOSalesVolume": FactValue(
            id=2,
            concept_id="idx:CPOSalesVolume",
            value_numeric=Decimal("1000000"),
            unit="TONS",
            period_type="duration",
            accounting_std="IFRS",
            period_end=None,
        ),
    }.get(cid)

    ctx = RecipeContext(
        ticker=Ticker("AALI"),
        fiscal_period=FiscalPeriod("2024Q4"),
        facts=facts,
        peers=AsyncMock(spec=PeersAccessor),
    )

    res = await compute_cpo_price_realized(ctx)
    assert res is not None
    assert res.value == Decimal("12000000")
    assert res.unit == "IDR/TON"


@pytest.mark.asyncio
async def test_telco_recipe_ebitda_margin() -> None:
    facts = AsyncMock(spec=FactsAccessor)
    facts.get.side_effect = lambda cid, p: {
        "idx:EBITDA": FactValue(
            id=1,
            concept_id="idx:EBITDA",
            value_numeric=Decimal("75000000000000"),
            unit="IDR",
            period_type="duration",
            accounting_std="IFRS",
            period_end=None,
        ),
        "idx:TotalRevenue": FactValue(
            id=2,
            concept_id="idx:TotalRevenue",
            value_numeric=Decimal("150000000000000"),
            unit="IDR",
            period_type="duration",
            accounting_std="IFRS",
            period_end=None,
        ),
    }.get(cid)

    ctx = RecipeContext(
        ticker=Ticker("TLKM"),
        fiscal_period=FiscalPeriod("2024Q4"),
        facts=facts,
        peers=AsyncMock(spec=PeersAccessor),
    )

    res = await compute_telco_ebitda_margin(ctx)
    assert res is not None
    assert res.value == Decimal("0.5")


@pytest.mark.asyncio
async def test_insurance_recipe_rbc() -> None:
    facts = AsyncMock(spec=FactsAccessor)
    facts.get.side_effect = lambda cid, p: {
        "idx:AvailableSolvencyCapital": FactValue(
            id=1,
            concept_id="idx:AvailableSolvencyCapital",
            value_numeric=Decimal("3500000000000"),
            unit="IDR",
            period_type="instant",
            accounting_std="IFRS",
            period_end=None,
        ),
        "idx:MinimumRequiredCapital": FactValue(
            id=2,
            concept_id="idx:MinimumRequiredCapital",
            value_numeric=Decimal("1000000000000"),
            unit="IDR",
            period_type="instant",
            accounting_std="IFRS",
            period_end=None,
        ),
    }.get(cid)

    ctx = RecipeContext(
        ticker=Ticker("LIFE"),
        fiscal_period=FiscalPeriod("2024Q4"),
        facts=facts,
        peers=AsyncMock(spec=PeersAccessor),
    )

    res = await compute_insurance_rbc(ctx)
    assert res is not None
    assert res.value == Decimal("3.5")
