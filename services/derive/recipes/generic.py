"""Generic sector-agnostic financial ratio and growth rate recipes."""

from __future__ import annotations

from decimal import Decimal

from services.derive.registry import RecipeContext, RecipeResult, recipe


def offset_fiscal_period(fp: str, quarters: int) -> str:
    """Calculates previous or subsequent fiscal period by quarter offset."""
    year = int(fp[:4])
    q_str = fp[4:]
    if q_str.startswith("Q"):
        q = int(q_str[1])
    elif q_str == "FY":
        q = 4
    elif q_str == "H1":
        q = 2
    else:
        q = 4

    total_q = year * 4 + (q - 1) + quarters
    new_year = total_q // 4
    new_q = (total_q % 4) + 1
    return f"{new_year}Q{new_q}"


CONCEPT_ALIASES = {
    "revenue": "ifrs:Revenue",
    "net_profit": "ifrs:ProfitLoss",
    "operating_profit": "ifrs:OperatingProfit",
    "gross_profit": "ifrs:GrossProfit",
    "assets": "ifrs:Assets",
    "equity": "ifrs:Equity",
    "eps": "ifrs:BasicEarningsLossPerShare",
    "cfo": "ifrs:CashFlowsFromUsedInOperatingActivities",
    "loans": "idx:LoansAndAdvances",
    "deposits": "idx:CustomerDeposits",
    "net_interest_income": "idx:NetInterestIncome",
}


# Register YoY, QoQ, and 3Y CAGR recipes for all standard concept aliases
for alias, concept_id in CONCEPT_ALIASES.items():

    def _make_yoy_recipe(c_id: str, a_name: str) -> None:
        @recipe(
            metric_id=f"yoy.{a_name}",
            version="1.0",
            sector=None,
            depends_on=[c_id],
        )
        async def yoy_fn(ctx: RecipeContext) -> RecipeResult | None:
            t0 = await ctx.facts.get(c_id)
            prev_period = offset_fiscal_period(str(ctx.fiscal_period), -4)
            t_prev = await ctx.facts.get(c_id, period=prev_period)

            if not t0 or not t_prev or t_prev.value_numeric == 0:
                return None

            val = (t0.value_numeric - t_prev.value_numeric) / abs(t_prev.value_numeric)
            comparability = (
                t0.accounting_std != t_prev.accounting_std
                if t0.accounting_std and t_prev.accounting_std
                else False
            )
            return RecipeResult(
                value=round(val, 6),
                unit="RATIO",
                inputs={
                    "fact_ids": [t0.id, t_prev.id],
                    "formula": f"({t0.value_numeric} - {t_prev.value_numeric}) / abs({t_prev.value_numeric})",
                    "comparability_flag": comparability,
                },
            )

    def _make_qoq_recipe(c_id: str, a_name: str) -> None:
        @recipe(
            metric_id=f"qoq.{a_name}",
            version="1.0",
            sector=None,
            depends_on=[c_id],
        )
        async def qoq_fn(ctx: RecipeContext) -> RecipeResult | None:
            t0 = await ctx.facts.get(c_id)
            prev_period = offset_fiscal_period(str(ctx.fiscal_period), -1)
            t_prev = await ctx.facts.get(c_id, period=prev_period)

            if not t0 or not t_prev or t_prev.value_numeric == 0:
                return None

            val = (t0.value_numeric - t_prev.value_numeric) / abs(t_prev.value_numeric)
            comparability = (
                t0.accounting_std != t_prev.accounting_std
                if t0.accounting_std and t_prev.accounting_std
                else False
            )
            return RecipeResult(
                value=round(val, 6),
                unit="RATIO",
                inputs={
                    "fact_ids": [t0.id, t_prev.id],
                    "formula": f"({t0.value_numeric} - {t_prev.value_numeric}) / abs({t_prev.value_numeric})",
                    "comparability_flag": comparability,
                },
            )

    def _make_cagr_recipe(c_id: str, a_name: str) -> None:
        @recipe(
            metric_id=f"cagr_3y.{a_name}",
            version="1.0",
            sector=None,
            depends_on=[c_id],
        )
        async def cagr_fn(ctx: RecipeContext) -> RecipeResult | None:
            t0 = await ctx.facts.get(c_id)
            prev_period = offset_fiscal_period(str(ctx.fiscal_period), -12)
            t_prev = await ctx.facts.get(c_id, period=prev_period)

            if not t0 or not t_prev or t_prev.value_numeric <= 0 or t0.value_numeric <= 0:
                return None

            ratio = float(t0.value_numeric / t_prev.value_numeric)
            cagr = Decimal(str(ratio ** (1.0 / 3.0) - 1.0))
            return RecipeResult(
                value=round(cagr, 6),
                unit="RATIO",
                inputs={
                    "fact_ids": [t0.id, t_prev.id],
                    "formula": f"({t0.value_numeric} / {t_prev.value_numeric}) ** (1/3) - 1",
                    "comparability_flag": False,
                },
            )

    _make_yoy_recipe(concept_id, alias)
    _make_qoq_recipe(concept_id, alias)
    _make_cagr_recipe(concept_id, alias)


@recipe(
    metric_id="margin.gross",
    version="1.0",
    sector=None,
    depends_on=["ifrs:Revenue", "ifrs:CostOfSales"],
)
async def recipe_gross_margin(ctx: RecipeContext) -> RecipeResult | None:
    rev = await ctx.facts.get("ifrs:Revenue")
    cos = await ctx.facts.get("ifrs:CostOfSales")
    if not rev or not cos or rev.value_numeric == 0:
        return None

    # Note: Cost of sales is typically positive or negative depending on statement presentation
    val = (rev.value_numeric - abs(cos.value_numeric)) / rev.value_numeric
    return RecipeResult(
        value=round(val, 6),
        unit="RATIO",
        inputs={
            "fact_ids": [rev.id, cos.id],
            "formula": f"({rev.value_numeric} - {abs(cos.value_numeric)}) / {rev.value_numeric}",
            "comparability_flag": False,
        },
    )


@recipe(
    metric_id="margin.operating",
    version="1.0",
    sector=None,
    depends_on=["ifrs:Revenue", "ifrs:OperatingProfit"],
)
async def recipe_operating_margin(ctx: RecipeContext) -> RecipeResult | None:
    rev = await ctx.facts.get("ifrs:Revenue")
    op = await ctx.facts.get("ifrs:OperatingProfit")
    if not rev or not op or rev.value_numeric == 0:
        return None

    val = op.value_numeric / rev.value_numeric
    return RecipeResult(
        value=round(val, 6),
        unit="RATIO",
        inputs={
            "fact_ids": [rev.id, op.id],
            "formula": f"{op.value_numeric} / {rev.value_numeric}",
            "comparability_flag": False,
        },
    )


@recipe(
    metric_id="margin.net",
    version="1.0",
    sector=None,
    depends_on=["ifrs:Revenue", "ifrs:ProfitLoss"],
)
async def recipe_net_margin(ctx: RecipeContext) -> RecipeResult | None:
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


@recipe(
    metric_id="debt_equity",
    version="1.0",
    sector=None,
    depends_on=["ifrs:Liabilities", "ifrs:Equity"],
)
async def recipe_debt_equity(ctx: RecipeContext) -> RecipeResult | None:
    liab = await ctx.facts.get("ifrs:Liabilities")
    eq = await ctx.facts.get("ifrs:Equity")
    if not liab or not eq or eq.value_numeric == 0:
        return None

    val = liab.value_numeric / eq.value_numeric
    return RecipeResult(
        value=round(val, 6),
        unit="RATIO",
        inputs={
            "fact_ids": [liab.id, eq.id],
            "formula": f"{liab.value_numeric} / {eq.value_numeric}",
            "comparability_flag": False,
        },
    )


@recipe(
    metric_id="current_ratio",
    version="1.0",
    sector=None,
    depends_on=["ifrs:CurrentAssets", "ifrs:CurrentLiabilities"],
)
async def recipe_current_ratio(ctx: RecipeContext) -> RecipeResult | None:
    ca = await ctx.facts.get("ifrs:CurrentAssets")
    cl = await ctx.facts.get("ifrs:CurrentLiabilities")
    if not ca or not cl or cl.value_numeric == 0:
        return None

    val = ca.value_numeric / cl.value_numeric
    return RecipeResult(
        value=round(val, 6),
        unit="RATIO",
        inputs={
            "fact_ids": [ca.id, cl.id],
            "formula": f"{ca.value_numeric} / {cl.value_numeric}",
            "comparability_flag": False,
        },
    )


@recipe(
    metric_id="roe",
    version="1.0",
    sector=None,
    depends_on=["ifrs:ProfitLoss", "ifrs:Equity"],
)
async def recipe_roe(ctx: RecipeContext) -> RecipeResult | None:
    ni = await ctx.facts.get("ifrs:ProfitLoss")
    eq_t = await ctx.facts.get("ifrs:Equity")
    prev_period = offset_fiscal_period(str(ctx.fiscal_period), -1)
    eq_prev = await ctx.facts.get("ifrs:Equity", period=prev_period)

    if not ni or not eq_t:
        return None

    avg_equity = (
        (eq_t.value_numeric + eq_prev.value_numeric) / Decimal("2")
        if eq_prev
        else eq_t.value_numeric
    )
    if avg_equity == 0:
        return None

    val = ni.value_numeric / avg_equity
    return RecipeResult(
        value=round(val, 6),
        unit="RATIO",
        inputs={
            "fact_ids": [ni.id, eq_t.id] + ([eq_prev.id] if eq_prev else []),
            "formula": f"{ni.value_numeric} / {avg_equity}",
            "comparability_flag": False,
        },
    )


@recipe(
    metric_id="roa",
    version="1.0",
    sector=None,
    depends_on=["ifrs:ProfitLoss", "ifrs:Assets"],
)
async def recipe_roa(ctx: RecipeContext) -> RecipeResult | None:
    ni = await ctx.facts.get("ifrs:ProfitLoss")
    ast_t = await ctx.facts.get("ifrs:Assets")
    prev_period = offset_fiscal_period(str(ctx.fiscal_period), -1)
    ast_prev = await ctx.facts.get("ifrs:Assets", period=prev_period)

    if not ni or not ast_t:
        return None

    avg_assets = (
        (ast_t.value_numeric + ast_prev.value_numeric) / Decimal("2")
        if ast_prev
        else ast_t.value_numeric
    )
    if avg_assets == 0:
        return None

    val = ni.value_numeric / avg_assets
    return RecipeResult(
        value=round(val, 6),
        unit="RATIO",
        inputs={
            "fact_ids": [ni.id, ast_t.id] + ([ast_prev.id] if ast_prev else []),
            "formula": f"{ni.value_numeric} / {avg_assets}",
            "comparability_flag": False,
        },
    )


@recipe(
    metric_id="quick_ratio",
    version="1.0",
    sector=None,
    depends_on=["ifrs:CashAndCashEquivalents", "ifrs:TradeAndOtherReceivables", "ifrs:CurrentLiabilities"],
)
async def recipe_quick_ratio(ctx: RecipeContext) -> RecipeResult | None:
    cash = await ctx.facts.get("ifrs:CashAndCashEquivalents")
    rec = await ctx.facts.get("ifrs:TradeAndOtherReceivables")
    cl = await ctx.facts.get("ifrs:CurrentLiabilities")
    if not cl or cl.value_numeric == 0:
        return None

    quick_assets = (cash.value_numeric if cash else Decimal("0")) + (rec.value_numeric if rec else Decimal("0"))
    if quick_assets == 0:
        return None

    val = quick_assets / cl.value_numeric
    fact_ids = [cl.id]
    if cash:
        fact_ids.append(cash.id)
    if rec:
        fact_ids.append(rec.id)

    return RecipeResult(
        value=round(val, 6),
        unit="RATIO",
        inputs={
            "fact_ids": fact_ids,
            "formula": f"({quick_assets}) / {cl.value_numeric}",
            "comparability_flag": False,
        },
    )


@recipe(
    metric_id="total_debt",
    version="1.0",
    sector=None,
    depends_on=["ifrs:ShortTermBorrowings", "ifrs:LongTermBorrowings", "ifrs:Liabilities"],
)
async def recipe_total_debt(ctx: RecipeContext) -> RecipeResult | None:
    st_debt = await ctx.facts.get("ifrs:ShortTermBorrowings")
    lt_debt = await ctx.facts.get("ifrs:LongTermBorrowings")
    bank_loans = await ctx.facts.get("idx:BankLoans")

    tot = Decimal("0")
    fact_ids = []
    if st_debt:
        tot += st_debt.value_numeric
        fact_ids.append(st_debt.id)
    if lt_debt:
        tot += lt_debt.value_numeric
        fact_ids.append(lt_debt.id)
    if bank_loans and not (st_debt or lt_debt):
        tot += bank_loans.value_numeric
        fact_ids.append(bank_loans.id)

    if tot == 0:
        # Fallback to total liabilities if debt breakdown is not itemized
        liab = await ctx.facts.get("ifrs:Liabilities")
        if liab:
            tot = liab.value_numeric
            fact_ids.append(liab.id)

    if tot == 0:
        return None

    return RecipeResult(
        value=round(tot, 4),
        unit="IDR",
        inputs={"fact_ids": fact_ids, "formula": "ShortTermDebt + LongTermDebt"},
    )


@recipe(
    metric_id="net_debt",
    version="1.0",
    sector=None,
    depends_on=["ifrs:CashAndCashEquivalents", "ifrs:ShortTermBorrowings", "ifrs:LongTermBorrowings", "ifrs:Liabilities"],
)
async def recipe_net_debt(ctx: RecipeContext) -> RecipeResult | None:
    cash = await ctx.facts.get("ifrs:CashAndCashEquivalents")
    st_debt = await ctx.facts.get("ifrs:ShortTermBorrowings")
    lt_debt = await ctx.facts.get("ifrs:LongTermBorrowings")
    bank_loans = await ctx.facts.get("idx:BankLoans")
    liab = await ctx.facts.get("ifrs:Liabilities")

    tot_debt = Decimal("0")
    fact_ids = []
    if st_debt:
        tot_debt += st_debt.value_numeric
        fact_ids.append(st_debt.id)
    if lt_debt:
        tot_debt += lt_debt.value_numeric
        fact_ids.append(lt_debt.id)
    if bank_loans and not (st_debt or lt_debt):
        tot_debt += bank_loans.value_numeric
        fact_ids.append(bank_loans.id)
    if tot_debt == 0 and liab:
        tot_debt = liab.value_numeric
        fact_ids.append(liab.id)

    cash_val = cash.value_numeric if cash else Decimal("0")
    if cash:
        fact_ids.append(cash.id)

    val = tot_debt - cash_val
    return RecipeResult(
        value=round(val, 4),
        unit="IDR",
        inputs={"fact_ids": fact_ids, "formula": f"{tot_debt} - {cash_val}"},
    )


@recipe(
    metric_id="interest_coverage",
    version="1.0",
    sector=None,
    depends_on=["ifrs:OperatingProfit", "ifrs:FinanceCosts"],
)
async def recipe_interest_coverage(ctx: RecipeContext) -> RecipeResult | None:
    op = await ctx.facts.get("ifrs:OperatingProfit")
    fc = await ctx.facts.get("ifrs:FinanceCosts")
    if not op or not fc or fc.value_numeric == 0:
        return None

    val = op.value_numeric / abs(fc.value_numeric)
    return RecipeResult(
        value=round(val, 4),
        unit="RATIO",
        inputs={
            "fact_ids": [op.id, fc.id],
            "formula": f"{op.value_numeric} / abs({fc.value_numeric})",
        },
    )


@recipe(
    metric_id="ebitda",
    version="1.0",
    sector=None,
    depends_on=["ifrs:OperatingProfit", "ifrs:DepreciationAndAmortisationExpense"],
)
async def recipe_ebitda(ctx: RecipeContext) -> RecipeResult | None:
    op = await ctx.facts.get("ifrs:OperatingProfit")
    da = await ctx.facts.get("ifrs:DepreciationAndAmortisationExpense")
    if not op:
        return None

    ebitda_val = op.value_numeric + (abs(da.value_numeric) if da else Decimal("0"))
    fact_ids = [op.id] + ([da.id] if da else [])

    return RecipeResult(
        value=round(ebitda_val, 4),
        unit="IDR",
        inputs={"fact_ids": fact_ids, "formula": "OperatingProfit + Depreciation"},
    )


@recipe(
    metric_id="fcf",
    version="1.0",
    sector=None,
    depends_on=["ifrs:CashFlowsFromUsedInOperatingActivities", "ifrs:PaymentsToAcquirePropertyPlantAndEquipment"],
)
async def recipe_fcf(ctx: RecipeContext) -> RecipeResult | None:
    cfo = await ctx.facts.get("ifrs:CashFlowsFromUsedInOperatingActivities")
    capex = await ctx.facts.get("ifrs:PaymentsToAcquirePropertyPlantAndEquipment")
    if not cfo:
        return None

    capex_val = abs(capex.value_numeric) if capex else Decimal("0")
    fcf_val = cfo.value_numeric - capex_val
    fact_ids = [cfo.id] + ([capex.id] if capex else [])

    return RecipeResult(
        value=round(fcf_val, 4),
        unit="IDR",
        inputs={"fact_ids": fact_ids, "formula": f"{cfo.value_numeric} - {capex_val}"},
    )


@recipe(
    metric_id="roce",
    version="1.0",
    sector=None,
    depends_on=["ifrs:OperatingProfit", "ifrs:Assets", "ifrs:CurrentLiabilities"],
)
async def recipe_roce(ctx: RecipeContext) -> RecipeResult | None:
    op = await ctx.facts.get("ifrs:OperatingProfit")
    ast = await ctx.facts.get("ifrs:Assets")
    cl = await ctx.facts.get("ifrs:CurrentLiabilities")
    if not op or not ast:
        return None

    capital_employed = ast.value_numeric - (cl.value_numeric if cl else Decimal("0"))
    if capital_employed <= 0:
        return None

    val = op.value_numeric / capital_employed
    fact_ids = [op.id, ast.id] + ([cl.id] if cl else [])
    return RecipeResult(
        value=round(val, 6),
        unit="RATIO",
        inputs={"fact_ids": fact_ids, "formula": f"{op.value_numeric} / {capital_employed}"},
    )


@recipe(
    metric_id="dso",
    version="1.0",
    sector=None,
    depends_on=["ifrs:TradeAndOtherReceivables", "ifrs:Revenue"],
)
async def recipe_dso(ctx: RecipeContext) -> RecipeResult | None:
    rec = await ctx.facts.get("ifrs:TradeAndOtherReceivables")
    rev = await ctx.facts.get("ifrs:Revenue")
    if not rec or not rev or rev.value_numeric == 0:
        return None

    days = (rec.value_numeric / rev.value_numeric) * Decimal("90")
    return RecipeResult(
        value=round(days, 2),
        unit="DAYS",
        inputs={"fact_ids": [rec.id, rev.id], "formula": f"({rec.value_numeric} / {rev.value_numeric}) * 90"},
    )


@recipe(
    metric_id="dio",
    version="1.0",
    sector=None,
    depends_on=["ifrs:Inventories", "ifrs:CostOfSales"],
)
async def recipe_dio(ctx: RecipeContext) -> RecipeResult | None:
    inv = await ctx.facts.get("ifrs:Inventories")
    cos = await ctx.facts.get("ifrs:CostOfSales")
    if not inv or not cos or cos.value_numeric == 0:
        return None

    days = (inv.value_numeric / abs(cos.value_numeric)) * Decimal("90")
    return RecipeResult(
        value=round(days, 2),
        unit="DAYS",
        inputs={"fact_ids": [inv.id, cos.id], "formula": f"({inv.value_numeric} / {abs(cos.value_numeric)}) * 90"},
    )


@recipe(
    metric_id="dpo",
    version="1.0",
    sector=None,
    depends_on=["ifrs:TradeAndOtherPayables", "ifrs:CostOfSales"],
)
async def recipe_dpo(ctx: RecipeContext) -> RecipeResult | None:
    pay = await ctx.facts.get("ifrs:TradeAndOtherPayables")
    cos = await ctx.facts.get("ifrs:CostOfSales")
    if not pay or not cos or cos.value_numeric == 0:
        return None

    days = (pay.value_numeric / abs(cos.value_numeric)) * Decimal("90")
    return RecipeResult(
        value=round(days, 2),
        unit="DAYS",
        inputs={"fact_ids": [pay.id, cos.id], "formula": f"({pay.value_numeric} / {abs(cos.value_numeric)}) * 90"},
    )


@recipe(
    metric_id="bvps",
    version="1.0",
    sector=None,
    depends_on=["ifrs:Equity", "idx:SharesOutstanding"],
)
async def recipe_bvps(ctx: RecipeContext) -> RecipeResult | None:
    eq = await ctx.facts.get("ifrs:Equity")
    shares = await ctx.facts.get("idx:SharesOutstanding")
    if not eq or not shares or shares.value_numeric == 0:
        return None

    val = eq.value_numeric / shares.value_numeric
    return RecipeResult(
        value=round(val, 2),
        unit="IDR",
        inputs={"fact_ids": [eq.id, shares.id], "formula": f"{eq.value_numeric} / {shares.value_numeric}"},
    )

