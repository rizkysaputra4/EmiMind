"""Unit tests for generic financial ratio recipes and fiscal period offset logic."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from services.derive.recipes.generic import (
    offset_fiscal_period,
    recipe_current_ratio,
    recipe_debt_equity,
    recipe_gross_margin,
    recipe_net_margin,
    recipe_operating_margin,
    recipe_roa,
    recipe_roe,
)
from services.derive.registry import FactValue, RecipeContext
from services.shared.types import FiscalPeriod, Ticker


def test_offset_fiscal_period() -> None:
    assert offset_fiscal_period("2024Q4", -4) == "2023Q4"
    assert offset_fiscal_period("2024Q1", -1) == "2023Q4"
    assert offset_fiscal_period("2024Q4", -1) == "2024Q3"
    assert offset_fiscal_period("2024Q1", -12) == "2021Q1"
    assert offset_fiscal_period("2024FY", -4) == "2023Q4"


@pytest.mark.asyncio
async def test_recipe_gross_margin() -> None:
    facts = AsyncMock()
    facts.get.side_effect = lambda c, period=None: {
        "ifrs:Revenue": FactValue(
            id=1,
            concept_id="ifrs:Revenue",
            value_numeric=Decimal("100000"),
            unit="IDR",
            period_type="duration_ytd",
            accounting_std="IFRS",
            period_end="2024-12-31",
        ),
        "ifrs:CostOfSales": FactValue(
            id=2,
            concept_id="ifrs:CostOfSales",
            value_numeric=Decimal("60000"),
            unit="IDR",
            period_type="duration_ytd",
            accounting_std="IFRS",
            period_end="2024-12-31",
        ),
    }.get(c)

    ctx = RecipeContext(
        ticker=Ticker("BMRI"),
        fiscal_period=FiscalPeriod("2024Q4"),
        facts=facts,
        peers=AsyncMock(),
    )

    res = await recipe_gross_margin(ctx)
    assert res is not None
    assert res.value == Decimal("0.400000")
    assert res.unit == "RATIO"


@pytest.mark.asyncio
async def test_recipe_operating_and_net_margin() -> None:
    facts = AsyncMock()
    facts.get.side_effect = lambda c, period=None: {
        "ifrs:Revenue": FactValue(
            id=1,
            concept_id="ifrs:Revenue",
            value_numeric=Decimal("100000"),
            unit="IDR",
            period_type="duration_ytd",
            accounting_std="IFRS",
            period_end="2024-12-31",
        ),
        "ifrs:OperatingProfit": FactValue(
            id=2,
            concept_id="ifrs:OperatingProfit",
            value_numeric=Decimal("30000"),
            unit="IDR",
            period_type="duration_ytd",
            accounting_std="IFRS",
            period_end="2024-12-31",
        ),
        "ifrs:ProfitLoss": FactValue(
            id=3,
            concept_id="ifrs:ProfitLoss",
            value_numeric=Decimal("20000"),
            unit="IDR",
            period_type="duration_ytd",
            accounting_std="IFRS",
            period_end="2024-12-31",
        ),
    }.get(c)

    ctx = RecipeContext(
        ticker=Ticker("BMRI"),
        fiscal_period=FiscalPeriod("2024Q4"),
        facts=facts,
        peers=AsyncMock(),
    )

    op_res = await recipe_operating_margin(ctx)
    assert op_res is not None
    assert op_res.value == Decimal("0.300000")

    net_res = await recipe_net_margin(ctx)
    assert net_res is not None
    assert net_res.value == Decimal("0.200000")


@pytest.mark.asyncio
async def test_recipe_debt_equity_and_current_ratio() -> None:
    facts = AsyncMock()
    facts.get.side_effect = lambda c, period=None: {
        "ifrs:Liabilities": FactValue(
            id=1,
            concept_id="ifrs:Liabilities",
            value_numeric=Decimal("800000"),
            unit="IDR",
            period_type="instant",
            accounting_std="IFRS",
            period_end="2024-12-31",
        ),
        "ifrs:Equity": FactValue(
            id=2,
            concept_id="ifrs:Equity",
            value_numeric=Decimal("200000"),
            unit="IDR",
            period_type="instant",
            accounting_std="IFRS",
            period_end="2024-12-31",
        ),
        "ifrs:CurrentAssets": FactValue(
            id=3,
            concept_id="ifrs:CurrentAssets",
            value_numeric=Decimal("300000"),
            unit="IDR",
            period_type="instant",
            accounting_std="IFRS",
            period_end="2024-12-31",
        ),
        "ifrs:CurrentLiabilities": FactValue(
            id=4,
            concept_id="ifrs:CurrentLiabilities",
            value_numeric=Decimal("150000"),
            unit="IDR",
            period_type="instant",
            accounting_std="IFRS",
            period_end="2024-12-31",
        ),
    }.get(c)

    ctx = RecipeContext(
        ticker=Ticker("BMRI"),
        fiscal_period=FiscalPeriod("2024Q4"),
        facts=facts,
        peers=AsyncMock(),
    )

    de_res = await recipe_debt_equity(ctx)
    assert de_res is not None
    assert de_res.value == Decimal("4.000000")

    cr_res = await recipe_current_ratio(ctx)
    assert cr_res is not None
    assert cr_res.value == Decimal("2.000000")


@pytest.mark.asyncio
async def test_recipe_roe_and_roa() -> None:
    def _mock_get(c: str, period: str | None = None) -> FactValue | None:
        if c == "ifrs:ProfitLoss":
            return FactValue(
                id=1,
                concept_id="ifrs:ProfitLoss",
                value_numeric=Decimal("50000"),
                unit="IDR",
                period_type="duration_ytd",
                accounting_std="IFRS",
                period_end="2024-12-31",
            )
        elif c == "ifrs:Equity":
            if period == "2024Q3":
                return FactValue(
                    id=2,
                    concept_id="ifrs:Equity",
                    value_numeric=Decimal("240000"),
                    unit="IDR",
                    period_type="instant",
                    accounting_std="IFRS",
                    period_end="2024-09-30",
                )
            return FactValue(
                id=3,
                concept_id="ifrs:Equity",
                value_numeric=Decimal("260000"),
                unit="IDR",
                period_type="instant",
                accounting_std="IFRS",
                period_end="2024-12-31",
            )
        elif c == "ifrs:Assets":
            return FactValue(
                id=4,
                concept_id="ifrs:Assets",
                value_numeric=Decimal("1000000"),
                unit="IDR",
                period_type="instant",
                accounting_std="IFRS",
                period_end="2024-12-31",
            )
        return None

    facts = AsyncMock()
    facts.get.side_effect = _mock_get

    ctx = RecipeContext(
        ticker=Ticker("BMRI"),
        fiscal_period=FiscalPeriod("2024Q4"),
        facts=facts,
        peers=AsyncMock(),
    )

    roe_res = await recipe_roe(ctx)
    assert roe_res is not None
    # 50000 / avg(260000, 240000) = 50000 / 250000 = 0.20
    assert roe_res.value == Decimal("0.200000")

    roa_res = await recipe_roa(ctx)
    assert roa_res is not None
    # 50000 / 1000000 = 0.05
    assert roa_res.value == Decimal("0.050000")


@pytest.mark.asyncio
async def test_key_stats_recipes() -> None:
    from services.derive.recipes.generic import (
        recipe_bvps,
        recipe_dio,
        recipe_dpo,
        recipe_dso,
        recipe_ebitda,
        recipe_fcf,
        recipe_quick_ratio,
        recipe_roce,
    )

    facts = AsyncMock()
    facts.get.side_effect = lambda c, period=None: {
        "ifrs:CashAndCashEquivalents": FactValue(id=1, concept_id="ifrs:CashAndCashEquivalents", value_numeric=Decimal("50000"), unit="IDR", period_type="instant", accounting_std="IFRS", period_end="2024-12-31"),
        "ifrs:TradeAndOtherReceivables": FactValue(id=2, concept_id="ifrs:TradeAndOtherReceivables", value_numeric=Decimal("30000"), unit="IDR", period_type="instant", accounting_std="IFRS", period_end="2024-12-31"),
        "ifrs:CurrentLiabilities": FactValue(id=3, concept_id="ifrs:CurrentLiabilities", value_numeric=Decimal("100000"), unit="IDR", period_type="instant", accounting_std="IFRS", period_end="2024-12-31"),
        "ifrs:OperatingProfit": FactValue(id=4, concept_id="ifrs:OperatingProfit", value_numeric=Decimal("40000"), unit="IDR", period_type="duration_ytd", accounting_std="IFRS", period_end="2024-12-31"),
        "ifrs:DepreciationAndAmortisationExpense": FactValue(id=5, concept_id="ifrs:DepreciationAndAmortisationExpense", value_numeric=Decimal("10000"), unit="IDR", period_type="duration_ytd", accounting_std="IFRS", period_end="2024-12-31"),
        "ifrs:CashFlowsFromUsedInOperatingActivities": FactValue(id=6, concept_id="ifrs:CashFlowsFromUsedInOperatingActivities", value_numeric=Decimal("45000"), unit="IDR", period_type="duration_ytd", accounting_std="IFRS", period_end="2024-12-31"),
        "ifrs:PaymentsToAcquirePropertyPlantAndEquipment": FactValue(id=7, concept_id="ifrs:PaymentsToAcquirePropertyPlantAndEquipment", value_numeric=Decimal("15000"), unit="IDR", period_type="duration_ytd", accounting_std="IFRS", period_end="2024-12-31"),
        "ifrs:Assets": FactValue(id=8, concept_id="ifrs:Assets", value_numeric=Decimal("500000"), unit="IDR", period_type="instant", accounting_std="IFRS", period_end="2024-12-31"),
        "ifrs:Revenue": FactValue(id=9, concept_id="ifrs:Revenue", value_numeric=Decimal("120000"), unit="IDR", period_type="duration_ytd", accounting_std="IFRS", period_end="2024-12-31"),
        "ifrs:Inventories": FactValue(id=10, concept_id="ifrs:Inventories", value_numeric=Decimal("20000"), unit="IDR", period_type="instant", accounting_std="IFRS", period_end="2024-12-31"),
        "ifrs:CostOfSales": FactValue(id=11, concept_id="ifrs:CostOfSales", value_numeric=Decimal("80000"), unit="IDR", period_type="duration_ytd", accounting_std="IFRS", period_end="2024-12-31"),
        "ifrs:TradeAndOtherPayables": FactValue(id=12, concept_id="ifrs:TradeAndOtherPayables", value_numeric=Decimal("25000"), unit="IDR", period_type="instant", accounting_std="IFRS", period_end="2024-12-31"),
        "ifrs:Equity": FactValue(id=13, concept_id="ifrs:Equity", value_numeric=Decimal("300000"), unit="IDR", period_type="instant", accounting_std="IFRS", period_end="2024-12-31"),
        "idx:SharesOutstanding": FactValue(id=14, concept_id="idx:SharesOutstanding", value_numeric=Decimal("1000000"), unit="SHARES", period_type="instant", accounting_std="IFRS", period_end="2024-12-31"),
    }.get(c)

    ctx = RecipeContext(
        ticker=Ticker("NCKL"),
        fiscal_period=FiscalPeriod("2024Q4"),
        facts=facts,
        peers=AsyncMock(),
    )

    qr = await recipe_quick_ratio(ctx)
    assert qr is not None and qr.value == Decimal("0.800000")  # (50k + 30k) / 100k

    eb = await recipe_ebitda(ctx)
    assert eb is not None and eb.value == Decimal("50000.0000")  # 40k + 10k

    fcf = await recipe_fcf(ctx)
    assert fcf is not None and fcf.value == Decimal("30000.0000")  # 45k - 15k

    roce = await recipe_roce(ctx)
    assert roce is not None and roce.value == Decimal("0.100000")  # 40k / (500k - 100k)

    dso = await recipe_dso(ctx)
    assert dso is not None and dso.value == Decimal("22.50")  # (30k / 120k) * 90

    dio = await recipe_dio(ctx)
    assert dio is not None and dio.value == Decimal("22.50")  # (20k / 80k) * 90

    dpo = await recipe_dpo(ctx)
    assert dpo is not None and dpo.value == Decimal("28.12") or dpo.value == Decimal("28.13")  # (25k / 80k) * 90

    bvps = await recipe_bvps(ctx)
    assert bvps is not None and bvps.value == Decimal("0.30")  # 300k / 1M

