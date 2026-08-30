"""Unit tests for banking sector KPI recipes (NIM, NPL, CASA, LDR, CoC, BOPO, CIR)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from services.derive.recipes.bank import (
    recipe_bank_bopo,
    recipe_bank_casa,
    recipe_bank_cir,
    recipe_bank_coc,
    recipe_bank_ldr,
    recipe_bank_nim,
    recipe_bank_npl,
)
from services.derive.registry import FactValue, RecipeContext
from services.shared.types import FiscalPeriod, Ticker


@pytest.mark.asyncio
async def test_recipe_bank_nim_and_ldr() -> None:
    facts = AsyncMock()
    facts.get.side_effect = lambda c, period=None: {
        "idx:NetInterestIncome": FactValue(
            id=1,
            concept_id="idx:NetInterestIncome",
            value_numeric=Decimal("72000"),
            unit="IDR",
            period_type="duration_ytd",
            accounting_std="PSAK 71",
            period_end="2024-12-31",
        ),
        "idx:LoansAndAdvances": FactValue(
            id=2,
            concept_id="idx:LoansAndAdvances",
            value_numeric=Decimal("1500000"),
            unit="IDR",
            period_type="instant",
            accounting_std="PSAK 71",
            period_end="2024-12-31",
        ),
        "idx:CustomerDeposits": FactValue(
            id=3,
            concept_id="idx:CustomerDeposits",
            value_numeric=Decimal("1600000"),
            unit="IDR",
            period_type="instant",
            accounting_std="PSAK 71",
            period_end="2024-12-31",
        ),
    }.get(c)

    ctx = RecipeContext(
        ticker=Ticker("BMRI"),
        fiscal_period=FiscalPeriod("2024Q4"),
        facts=facts,
        peers=AsyncMock(),
    )

    nim = await recipe_bank_nim(ctx)
    assert nim is not None
    # 72000 / 1500000 = 0.048
    assert nim.value == Decimal("0.048000")

    ldr = await recipe_bank_ldr(ctx)
    assert ldr is not None
    # 1500000 / 1600000 = 0.9375
    assert ldr.value == Decimal("0.937500")


@pytest.mark.asyncio
async def test_recipe_bank_npl_and_casa() -> None:
    facts = AsyncMock()
    facts.get.side_effect = lambda c, period=None: {
        "idx:NonPerformingLoans": FactValue(
            id=1,
            concept_id="idx:NonPerformingLoans",
            value_numeric=Decimal("15000"),
            unit="IDR",
            period_type="instant",
            accounting_std="PSAK 71",
            period_end="2024-12-31",
        ),
        "idx:LoansAndAdvances": FactValue(
            id=2,
            concept_id="idx:LoansAndAdvances",
            value_numeric=Decimal("1500000"),
            unit="IDR",
            period_type="instant",
            accounting_std="PSAK 71",
            period_end="2024-12-31",
        ),
        "idx:DemandDeposits": FactValue(
            id=3,
            concept_id="idx:DemandDeposits",
            value_numeric=Decimal("500000"),
            unit="IDR",
            period_type="instant",
            accounting_std="PSAK 71",
            period_end="2024-12-31",
        ),
        "idx:SavingsDeposits": FactValue(
            id=4,
            concept_id="idx:SavingsDeposits",
            value_numeric=Decimal("700000"),
            unit="IDR",
            period_type="instant",
            accounting_std="PSAK 71",
            period_end="2024-12-31",
        ),
        "idx:CustomerDeposits": FactValue(
            id=5,
            concept_id="idx:CustomerDeposits",
            value_numeric=Decimal("1600000"),
            unit="IDR",
            period_type="instant",
            accounting_std="PSAK 71",
            period_end="2024-12-31",
        ),
    }.get(c)

    ctx = RecipeContext(
        ticker=Ticker("BMRI"),
        fiscal_period=FiscalPeriod("2024Q4"),
        facts=facts,
        peers=AsyncMock(),
    )

    npl = await recipe_bank_npl(ctx)
    assert npl is not None
    # 15000 / 1500000 = 0.01 (1.0% NPL)
    assert npl.value == Decimal("0.010000")

    casa = await recipe_bank_casa(ctx)
    assert casa is not None
    # (500000 + 700000) / 1600000 = 1200000 / 1600000 = 0.75 (75% CASA)
    assert casa.value == Decimal("0.750000")


@pytest.mark.asyncio
async def test_recipe_bank_bopo_and_cir_and_coc() -> None:
    facts = AsyncMock()
    facts.get.side_effect = lambda c, period=None: {
        "idx:OperatingExpenses": FactValue(
            id=1,
            concept_id="idx:OperatingExpenses",
            value_numeric=Decimal("-40000"),
            unit="IDR",
            period_type="duration_ytd",
            accounting_std="PSAK 71",
            period_end="2024-12-31",
        ),
        "idx:InterestIncome": FactValue(
            id=2,
            concept_id="idx:InterestIncome",
            value_numeric=Decimal("100000"),
            unit="IDR",
            period_type="duration_ytd",
            accounting_std="PSAK 71",
            period_end="2024-12-31",
        ),
        "idx:NetInterestIncome": FactValue(
            id=3,
            concept_id="idx:NetInterestIncome",
            value_numeric=Decimal("70000"),
            unit="IDR",
            period_type="duration_ytd",
            accounting_std="PSAK 71",
            period_end="2024-12-31",
        ),
        "idx:FeeAndCommissionIncome": FactValue(
            id=4,
            concept_id="idx:FeeAndCommissionIncome",
            value_numeric=Decimal("10000"),
            unit="IDR",
            period_type="duration_ytd",
            accounting_std="PSAK 71",
            period_end="2024-12-31",
        ),
        "idx:ImpairmentLossesOnFinancialAssets": FactValue(
            id=5,
            concept_id="idx:ImpairmentLossesOnFinancialAssets",
            value_numeric=Decimal("-15000"),
            unit="IDR",
            period_type="duration_ytd",
            accounting_std="PSAK 71",
            period_end="2024-12-31",
        ),
        "idx:LoansAndAdvances": FactValue(
            id=6,
            concept_id="idx:LoansAndAdvances",
            value_numeric=Decimal("1500000"),
            unit="IDR",
            period_type="instant",
            accounting_std="PSAK 71",
            period_end="2024-12-31",
        ),
    }.get(c)

    ctx = RecipeContext(
        ticker=Ticker("BMRI"),
        fiscal_period=FiscalPeriod("2024Q4"),
        facts=facts,
        peers=AsyncMock(),
    )

    bopo = await recipe_bank_bopo(ctx)
    assert bopo is not None
    # 40000 / (100000 + 10000) = 40000 / 110000 = 0.363636
    assert bopo.value == Decimal("0.363636")

    cir = await recipe_bank_cir(ctx)
    assert cir is not None
    # 40000 / (70000 + 10000) = 40000 / 80000 = 0.50
    assert cir.value == Decimal("0.500000")

    coc = await recipe_bank_coc(ctx)
    assert coc is not None
    # 15000 / 1500000 = 0.010000
    assert coc.value == Decimal("0.010000")
