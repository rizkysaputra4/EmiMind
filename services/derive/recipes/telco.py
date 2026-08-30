"""Derived metric recipes for Telecommunications issuers (e.g. TLKM, ISAT, EXCL)."""

from __future__ import annotations

from decimal import Decimal

from services.derive.registry import RecipeContext, RecipeResult, recipe


@recipe(
    metric_id="telco.ebitda_margin",
    sector="TELCO",
    depends_on=["idx:EBITDA", "idx:TotalRevenue"],
)
async def compute_telco_ebitda_margin(ctx: RecipeContext) -> RecipeResult | None:
    ebitda = await ctx.facts.get("idx:EBITDA", ctx.fiscal_period)
    rev = await ctx.facts.get("idx:TotalRevenue", ctx.fiscal_period)
    if ebitda is None or rev is None or rev.value_numeric <= 0:
        return None

    margin = Decimal(str(ebitda.value_numeric)) / Decimal(str(rev.value_numeric))
    return RecipeResult(
        value=margin,
        unit="RATIO",
        inputs={"fact_ids": [ebitda.id, rev.id]},
    )


@recipe(
    metric_id="telco.arpu",
    sector="TELCO",
    depends_on=["idx:MobileServiceRevenue", "idx:SubscriberCount"],
)
async def compute_telco_arpu(ctx: RecipeContext) -> RecipeResult | None:
    rev = await ctx.facts.get("idx:MobileServiceRevenue", ctx.fiscal_period)
    subs = await ctx.facts.get("idx:SubscriberCount", ctx.fiscal_period)
    if rev is None or subs is None or subs.value_numeric <= 0:
        return None

    # Quarterly revenue / 3 months / subscribers
    arpu = (Decimal(str(rev.value_numeric)) / Decimal("3")) / Decimal(str(subs.value_numeric))
    return RecipeResult(
        value=arpu,
        unit="IDR/SUB/MONTH",
        inputs={"fact_ids": [rev.id, subs.id]},
    )


@recipe(
    metric_id="telco.capex_intensity",
    sector="TELCO",
    depends_on=["idx:CapitalExpenditures", "idx:TotalRevenue"],
)
async def compute_telco_capex_intensity(ctx: RecipeContext) -> RecipeResult | None:
    capex = await ctx.facts.get("idx:CapitalExpenditures", ctx.fiscal_period)
    rev = await ctx.facts.get("idx:TotalRevenue", ctx.fiscal_period)
    if capex is None or rev is None or rev.value_numeric <= 0:
        return None

    intensity = abs(Decimal(str(capex.value_numeric))) / Decimal(str(rev.value_numeric))
    return RecipeResult(
        value=intensity,
        unit="RATIO",
        inputs={"fact_ids": [capex.id, rev.id]},
    )
