"""Derived metric recipes for Insurance and Underwriting issuers."""

from __future__ import annotations

from decimal import Decimal

from services.derive.registry import RecipeContext, RecipeResult, recipe


@recipe(
    metric_id="insurance.rbc",
    sector="INSURANCE",
    depends_on=["idx:AvailableSolvencyCapital", "idx:MinimumRequiredCapital"],
)
async def compute_insurance_rbc(ctx: RecipeContext) -> RecipeResult | None:
    avail = await ctx.facts.get("idx:AvailableSolvencyCapital", ctx.fiscal_period)
    req = await ctx.facts.get("idx:MinimumRequiredCapital", ctx.fiscal_period)
    if avail is None or req is None or req.value_numeric <= 0:
        return None

    rbc = Decimal(str(avail.value_numeric)) / Decimal(str(req.value_numeric))
    return RecipeResult(
        value=rbc,
        unit="RATIO",
        inputs={"fact_ids": [avail.id, req.id]},
    )


@recipe(
    metric_id="insurance.loss_ratio",
    sector="INSURANCE",
    depends_on=["idx:NetClaimsIncurred", "idx:NetPremiumEarned"],
)
async def compute_insurance_loss_ratio(ctx: RecipeContext) -> RecipeResult | None:
    claims = await ctx.facts.get("idx:NetClaimsIncurred", ctx.fiscal_period)
    premium = await ctx.facts.get("idx:NetPremiumEarned", ctx.fiscal_period)
    if claims is None or premium is None or premium.value_numeric <= 0:
        return None

    loss_ratio = Decimal(str(claims.value_numeric)) / Decimal(str(premium.value_numeric))
    return RecipeResult(
        value=loss_ratio,
        unit="RATIO",
        inputs={"fact_ids": [claims.id, premium.id]},
    )


@recipe(
    metric_id="insurance.combined_ratio",
    sector="INSURANCE",
    depends_on=["idx:NetClaimsIncurred", "idx:OperatingExpenses", "idx:NetPremiumEarned"],
)
async def compute_insurance_combined_ratio(ctx: RecipeContext) -> RecipeResult | None:
    claims = await ctx.facts.get("idx:NetClaimsIncurred", ctx.fiscal_period)
    opex = await ctx.facts.get("idx:OperatingExpenses", ctx.fiscal_period)
    premium = await ctx.facts.get("idx:NetPremiumEarned", ctx.fiscal_period)
    if claims is None or opex is None or premium is None or premium.value_numeric <= 0:
        return None

    total_costs = Decimal(str(claims.value_numeric)) + Decimal(str(opex.value_numeric))
    combined = total_costs / Decimal(str(premium.value_numeric))
    return RecipeResult(
        value=combined,
        unit="RATIO",
        inputs={"fact_ids": [claims.id, opex.id, premium.id]},
    )
