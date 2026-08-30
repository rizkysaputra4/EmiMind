"""Derived metric recipes for Palm Oil / CPO plantation issuers (e.g. AALI, LSIP, SIMP)."""

from __future__ import annotations

from decimal import Decimal

from services.derive.registry import RecipeContext, RecipeResult, recipe


@recipe(
    metric_id="cpo.price_realized",
    sector="CPO",
    depends_on=["idx:CPORevenue", "idx:CPOSalesVolume"],
)
async def compute_cpo_price_realized(ctx: RecipeContext) -> RecipeResult | None:
    rev = await ctx.facts.get("idx:CPORevenue", ctx.fiscal_period)
    vol = await ctx.facts.get("idx:CPOSalesVolume", ctx.fiscal_period)
    if rev is None or vol is None or vol.value_numeric <= 0:
        return None

    price = Decimal(str(rev.value_numeric)) / Decimal(str(vol.value_numeric))
    return RecipeResult(
        value=price,
        unit="IDR/TON",
        inputs={"fact_ids": [rev.id, vol.id]},
    )


@recipe(
    metric_id="cpo.ffb_yield",
    sector="CPO",
    depends_on=["idx:FFBProduction", "idx:MatureAreaHa"],
)
async def compute_cpo_ffb_yield(ctx: RecipeContext) -> RecipeResult | None:
    prod = await ctx.facts.get("idx:FFBProduction", ctx.fiscal_period)
    area = await ctx.facts.get("idx:MatureAreaHa", ctx.fiscal_period)
    if prod is None or area is None or area.value_numeric <= 0:
        return None

    ffb_yield = Decimal(str(prod.value_numeric)) / Decimal(str(area.value_numeric))
    return RecipeResult(
        value=ffb_yield,
        unit="TONS/HA",
        inputs={"fact_ids": [prod.id, area.id]},
    )


@recipe(
    metric_id="cpo.cash_cost",
    sector="CPO",
    depends_on=["idx:CostOfGoodsSold", "idx:CPOProductionVolume"],
)
async def compute_cpo_cash_cost(ctx: RecipeContext) -> RecipeResult | None:
    cogs = await ctx.facts.get("idx:CostOfGoodsSold", ctx.fiscal_period)
    prod = await ctx.facts.get("idx:CPOProductionVolume", ctx.fiscal_period)
    if cogs is None or prod is None or prod.value_numeric <= 0:
        return None

    cash_cost = Decimal(str(cogs.value_numeric)) / Decimal(str(prod.value_numeric))
    return RecipeResult(
        value=cash_cost,
        unit="IDR/TON",
        inputs={"fact_ids": [cogs.id, prod.id]},
    )


@recipe(
    metric_id="cpo.oer",
    sector="CPO",
    depends_on=["idx:CPOProductionVolume", "idx:FFBProcessedVolume"],
)
async def compute_cpo_oer(ctx: RecipeContext) -> RecipeResult | None:
    cpo = await ctx.facts.get("idx:CPOProductionVolume", ctx.fiscal_period)
    ffb = await ctx.facts.get("idx:FFBProcessedVolume", ctx.fiscal_period)
    if cpo is None or ffb is None or ffb.value_numeric <= 0:
        return None

    oer = Decimal(str(cpo.value_numeric)) / Decimal(str(ffb.value_numeric))
    return RecipeResult(
        value=oer,
        unit="RATIO",
        inputs={"fact_ids": [cpo.id, ffb.id]},
    )
