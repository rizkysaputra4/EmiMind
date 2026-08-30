"""Banking sector KPI recipes (NIM, NPL, CASA, LDR, CoC, BOPO, CIR)."""

from __future__ import annotations

from decimal import Decimal

from services.derive.recipes.generic import offset_fiscal_period
from services.derive.registry import RecipeContext, RecipeResult, recipe


@recipe(
    metric_id="bank.nim",
    version="1.0",
    sector="BANK",
    depends_on=["idx:NetInterestIncome", "idx:LoansAndAdvances"],
)
async def recipe_bank_nim(ctx: RecipeContext) -> RecipeResult | None:
    """Net Interest Margin = Net Interest Income / Average Earning Assets (Loans)."""
    nii = await ctx.facts.get("idx:NetInterestIncome")
    loans_t = await ctx.facts.get("idx:LoansAndAdvances")
    prev_period = offset_fiscal_period(str(ctx.fiscal_period), -1)
    loans_prev = await ctx.facts.get("idx:LoansAndAdvances", period=prev_period)

    if not nii or not loans_t:
        return None

    avg_earning_assets = (
        (loans_t.value_numeric + loans_prev.value_numeric) / Decimal("2")
        if loans_prev
        else loans_t.value_numeric
    )
    if avg_earning_assets == 0:
        return None

    val = nii.value_numeric / avg_earning_assets
    return RecipeResult(
        value=round(val, 6),
        unit="RATIO",
        inputs={
            "fact_ids": [nii.id, loans_t.id] + ([loans_prev.id] if loans_prev else []),
            "formula": f"{nii.value_numeric} / {avg_earning_assets}",
            "comparability_flag": False,
        },
    )


@recipe(
    metric_id="bank.npl",
    version="1.0",
    sector="BANK",
    depends_on=["idx:NonPerformingLoans", "idx:LoansAndAdvances"],
)
async def recipe_bank_npl(ctx: RecipeContext) -> RecipeResult | None:
    """Non-Performing Loans Ratio = NPL / Total Loans."""
    npl = await ctx.facts.get("idx:NonPerformingLoans")
    loans = await ctx.facts.get("idx:LoansAndAdvances")
    if not npl or not loans or loans.value_numeric == 0:
        return None

    val = npl.value_numeric / loans.value_numeric
    return RecipeResult(
        value=round(val, 6),
        unit="RATIO",
        inputs={
            "fact_ids": [npl.id, loans.id],
            "formula": f"{npl.value_numeric} / {loans.value_numeric}",
            "comparability_flag": False,
        },
    )


@recipe(
    metric_id="bank.casa",
    version="1.0",
    sector="BANK",
    depends_on=["idx:DemandDeposits", "idx:SavingsDeposits", "idx:CustomerDeposits"],
)
async def recipe_bank_casa(ctx: RecipeContext) -> RecipeResult | None:
    """CASA Ratio = (Demand Deposits + Savings Deposits) / Total Deposits."""
    demand = await ctx.facts.get("idx:DemandDeposits")
    savings = await ctx.facts.get("idx:SavingsDeposits")
    total_dep = await ctx.facts.get("idx:CustomerDeposits")

    if not total_dep or total_dep.value_numeric == 0:
        return None

    casa_sum = Decimal("0")
    fact_ids = [total_dep.id]
    if demand:
        casa_sum += demand.value_numeric
        fact_ids.append(demand.id)
    if savings:
        casa_sum += savings.value_numeric
        fact_ids.append(savings.id)

    if not demand and not savings:
        return None

    val = casa_sum / total_dep.value_numeric
    return RecipeResult(
        value=round(val, 6),
        unit="RATIO",
        inputs={
            "fact_ids": fact_ids,
            "formula": f"{casa_sum} / {total_dep.value_numeric}",
            "comparability_flag": False,
        },
    )


@recipe(
    metric_id="bank.ldr",
    version="1.0",
    sector="BANK",
    depends_on=["idx:LoansAndAdvances", "idx:CustomerDeposits"],
)
async def recipe_bank_ldr(ctx: RecipeContext) -> RecipeResult | None:
    """Loan to Deposit Ratio = Total Loans / Total Customer Deposits."""
    loans = await ctx.facts.get("idx:LoansAndAdvances")
    deposits = await ctx.facts.get("idx:CustomerDeposits")
    if not loans or not deposits or deposits.value_numeric == 0:
        return None

    val = loans.value_numeric / deposits.value_numeric
    return RecipeResult(
        value=round(val, 6),
        unit="RATIO",
        inputs={
            "fact_ids": [loans.id, deposits.id],
            "formula": f"{loans.value_numeric} / {deposits.value_numeric}",
            "comparability_flag": False,
        },
    )


@recipe(
    metric_id="bank.coc",
    version="1.0",
    sector="BANK",
    depends_on=["idx:ImpairmentLossesOnFinancialAssets", "idx:LoansAndAdvances"],
)
async def recipe_bank_coc(ctx: RecipeContext) -> RecipeResult | None:
    """Cost of Credit = Impairment Losses / Average Total Loans."""
    imp = await ctx.facts.get("idx:ImpairmentLossesOnFinancialAssets")
    loans_t = await ctx.facts.get("idx:LoansAndAdvances")
    prev_period = offset_fiscal_period(str(ctx.fiscal_period), -1)
    loans_prev = await ctx.facts.get("idx:LoansAndAdvances", period=prev_period)

    if not imp or not loans_t:
        return None

    avg_loans = (
        (loans_t.value_numeric + loans_prev.value_numeric) / Decimal("2")
        if loans_prev
        else loans_t.value_numeric
    )
    if avg_loans == 0:
        return None

    val = abs(imp.value_numeric) / avg_loans
    return RecipeResult(
        value=round(val, 6),
        unit="RATIO",
        inputs={
            "fact_ids": [imp.id, loans_t.id] + ([loans_prev.id] if loans_prev else []),
            "formula": f"{abs(imp.value_numeric)} / {avg_loans}",
            "comparability_flag": False,
        },
    )


@recipe(
    metric_id="bank.bopo",
    version="1.0",
    sector="BANK",
    depends_on=["idx:OperatingExpenses", "idx:InterestIncome"],
)
async def recipe_bank_bopo(ctx: RecipeContext) -> RecipeResult | None:
    """BOPO = Operating Expenses / Operating Income (Interest + Non-Interest)."""
    opex = await ctx.facts.get("idx:OperatingExpenses")
    ii = await ctx.facts.get("idx:InterestIncome")
    nii_fee = await ctx.facts.get("idx:FeeAndCommissionIncome")

    if not opex or not ii:
        return None

    op_income = ii.value_numeric + (nii_fee.value_numeric if nii_fee else Decimal("0"))
    if op_income == 0:
        return None

    val = abs(opex.value_numeric) / op_income
    fact_ids = [opex.id, ii.id] + ([nii_fee.id] if nii_fee else [])
    return RecipeResult(
        value=round(val, 6),
        unit="RATIO",
        inputs={
            "fact_ids": fact_ids,
            "formula": f"{abs(opex.value_numeric)} / {op_income}",
            "comparability_flag": False,
        },
    )


@recipe(
    metric_id="bank.cir",
    version="1.0",
    sector="BANK",
    depends_on=["idx:OperatingExpenses", "idx:NetInterestIncome"],
)
async def recipe_bank_cir(ctx: RecipeContext) -> RecipeResult | None:
    """Cost to Income Ratio = Operating Expenses / (Net Interest Income + Fee Income)."""
    opex = await ctx.facts.get("idx:OperatingExpenses")
    nii = await ctx.facts.get("idx:NetInterestIncome")
    fee = await ctx.facts.get("idx:FeeAndCommissionIncome")

    if not opex or not nii:
        return None

    total_income = nii.value_numeric + (fee.value_numeric if fee else Decimal("0"))
    if total_income == 0:
        return None

    val = abs(opex.value_numeric) / total_income
    fact_ids = [opex.id, nii.id] + ([fee.id] if fee else [])
    return RecipeResult(
        value=round(val, 6),
        unit="RATIO",
        inputs={
            "fact_ids": fact_ids,
            "formula": f"{abs(opex.value_numeric)} / {total_income}",
            "comparability_flag": False,
        },
    )
