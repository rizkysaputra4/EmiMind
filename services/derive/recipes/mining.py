"""Mining (Coal) sector KPI recipes (Cash Cost, Strip Ratio, ASP, Net Margin)."""

from __future__ import annotations

from services.derive.registry import RecipeContext, RecipeResult, recipe


@recipe(
    metric_id="mining.cash_cost",
    version="1.0",
    sector="MINING",
    depends_on=["idx:CashCostPerTon"],
)
async def recipe_mining_cash_cost(ctx: RecipeContext) -> RecipeResult | None:
    """Cash Cost per Ton pass-through."""
    cost = await ctx.facts.get("idx:CashCostPerTon")
    if not cost:
        return None

    return RecipeResult(
        value=round(cost.value_numeric, 6),
        unit=cost.unit or "USD/ton",
        inputs={
            "fact_ids": [cost.id],
            "formula": "pass_through(idx:CashCostPerTon)",
            "comparability_flag": False,
        },
    )


@recipe(
    metric_id="mining.strip_ratio",
    version="1.0",
    sector="MINING",
    depends_on=["idx:StripRatio"],
)
async def recipe_mining_strip_ratio(ctx: RecipeContext) -> RecipeResult | None:
    """Strip Ratio (Overburden bcm / Coal ton) pass-through."""
    sr = await ctx.facts.get("idx:StripRatio")
    if not sr:
        return None

    return RecipeResult(
        value=round(sr.value_numeric, 6),
        unit="bcm/ton",
        inputs={
            "fact_ids": [sr.id],
            "formula": "pass_through(idx:StripRatio)",
            "comparability_flag": False,
        },
    )


@recipe(
    metric_id="mining.asp",
    version="1.0",
    sector="MINING",
    depends_on=["idx:AverageSellingPrice"],
)
async def recipe_mining_asp(ctx: RecipeContext) -> RecipeResult | None:
    """Average Selling Price per ton pass-through."""
    asp = await ctx.facts.get("idx:AverageSellingPrice")
    if not asp:
        return None

    return RecipeResult(
        value=round(asp.value_numeric, 6),
        unit=asp.unit or "USD/ton",
        inputs={
            "fact_ids": [asp.id],
            "formula": "pass_through(idx:AverageSellingPrice)",
            "comparability_flag": False,
        },
    )


@recipe(
    metric_id="mining.ni_margin",
    version="1.0",
    sector="MINING",
    depends_on=["ifrs:Revenue", "ifrs:ProfitLoss"],
)
async def recipe_mining_ni_margin(ctx: RecipeContext) -> RecipeResult | None:
    """Mining Net Profit Margin = ProfitLoss / Revenue."""
    rev = await ctx.facts.get("ifrs:Revenue")
    ni = await ctx.facts.get("ifrs:ProfitLoss")
    if not rev or not ni or rev.value_numeric == 0:
        return None

    val = ni.value_numeric / rev.value_numeric
    return RecipeResult(
        value=round(val, 6),
        unit="RATIO",
        inputs={
            "fact_ids": [rev.id, ni.id],
            "formula": f"{ni.value_numeric} / {rev.value_numeric}",
            "comparability_flag": False,
        },
    )
