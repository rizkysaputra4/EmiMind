"""Worker task for refreshing L6 Issuer Profile cards."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import text

from services.derive.valuation import calculate_valuation
from services.narrative.embedder import Embedder
from services.shared.logging import get_logger

log = get_logger(__name__)

WORKER_VERSION = "1.0"


HEADLINE_CONCEPTS = (
    # Income Statement
    "ifrs:Revenue",
    "ifrs:CostOfSales",
    "ifrs:GrossProfit",
    "ifrs:OperatingProfit",
    "ifrs:ProfitBeforeTax",
    "ifrs:ProfitLoss",
    "ifrs:ProfitLossAttributableToOwnersOfParent",
    "ifrs:FinanceCosts",
    "ifrs:DepreciationAndAmortisationExpense",
    # Balance Sheet
    "ifrs:CashAndCashEquivalents",
    "ifrs:TradeAndOtherReceivables",
    "ifrs:Inventories",
    "ifrs:CurrentAssets",
    "ifrs:NonCurrentAssets",
    "ifrs:Assets",
    "ifrs:TradeAndOtherPayables",
    "ifrs:ShortTermBorrowings",
    "ifrs:CurrentLiabilities",
    "ifrs:LongTermBorrowings",
    "ifrs:NonCurrentLiabilities",
    "ifrs:Liabilities",
    "ifrs:EquityAttributableToOwnersOfParent",
    "ifrs:Equity",
    # Cash Flow Statement
    "ifrs:CashFlowsFromUsedInOperatingActivities",
    "ifrs:CashFlowsFromUsedInInvestingActivities",
    "ifrs:CashFlowsFromUsedInFinancingActivities",
    "ifrs:PaymentsToAcquirePropertyPlantAndEquipment",
    # Per Share & Market
    "ifrs:BasicEarningsLossPerShare",
    "idx:SharesOutstanding",
    "idx:MarketCap",
    "idx:FreeFloat",
    "idx:DividendPerShare",
)


def _fmt_amount(value: float | None, unit: str | None) -> str:
    """Formats a monetary or ratio value compactly."""
    if value is None:
        return "N/A"
    v = float(value)
    if unit:
        u_upper = unit.upper()
        if u_upper == "RATIO":
            return f"{v * 100:.2f}%"
        if u_upper == "PCT":
            return f"{v:.2f}%"
        if u_upper == "DAYS":
            return f"{v:.1f} Days"
        return f"{v:,.2f} {unit}".rstrip()
    return f"{v:,.2f}"


def _synthesize_profile_summary(
    ticker: str,
    name: str,
    sector: str,
    sub_sector: str | None,
    metrics: list[dict[str, Any]],
    headline_facts: list[dict[str, Any]],
    last_period: str,
    technical_state: dict[str, Any] | None = None,
    valuation: dict[str, Any] | None = None,
) -> str:
    """Generates structured institutional Key Stats profile anchored in extracted facts and derived metrics."""
    sector_line = f"**Sector:** {sector}"
    if sub_sector:
        sector_line += f" / {sub_sector}"
    sector_line += f" | **Latest Reported Period:** {last_period}"

    lines = [
        f"### {name} ({ticker}) — Institutional Key Stats Profile",
        sector_line,
        "",
    ]

    facts_dict = {f["concept_id"]: f for f in headline_facts}
    metrics_dict = {m["metric_id"]: m for m in metrics}

    def _render_sec(title: str, items: list[tuple[str, str, dict[str, Any] | None]]) -> None:
        valid_items = [(label, fmt_type, obj) for label, fmt_type, obj in items if obj is not None]
        if not valid_items:
            return
        lines.append(f"#### {title}")
        for label, fmt_type, obj in valid_items:
            val = obj.get("value_numeric")
            unit = obj.get("unit")
            val_str = _fmt_amount(val, unit)
            lines.append(f" * {label}: {val_str}")
        lines.append("")

    # 1. Market Overview
    live_mcap = valuation.get("market_cap") if valuation else None
    live_shares = valuation.get("shares_outstanding") if valuation else None
    _render_sec("Market Overview", [
        (
            "Market Cap" + (" (Live)" if live_mcap else ""),
            "CURR",
            {"value_numeric": live_mcap, "unit": "IDR"} if live_mcap else (facts_dict.get("idx:MarketCap") or metrics_dict.get("market_cap")),
        ),
        (
            "Current Share Outstanding",
            "NUM",
            {"value_numeric": live_shares, "unit": "SHARES"} if live_shares else facts_dict.get("idx:SharesOutstanding"),
        ),
        ("Free Float", "PCT", facts_dict.get("idx:FreeFloat")),
    ])

    # 2. Valuation (On-the-fly with live market price)
    val_title = "Valuation"
    if valuation and valuation.get("price"):
        p_val = valuation["price"]
        p_dt = valuation.get("price_date") or "Latest"
        val_title = f"Valuation (Calculated on-the-fly with live price: IDR {p_val:,.0f} as of {p_dt})"

    val_items = []
    if valuation and valuation.get("price"):
        if valuation.get("pe"):
            val_items.append(("Current PE Ratio (TTM)", "RATIO", {"value_numeric": valuation["pe"], "unit": "x"}))
        if valuation.get("pbv"):
            val_items.append(("Current Price to Book Value (PBV)", "RATIO", {"value_numeric": valuation["pbv"], "unit": "x"}))
        if valuation.get("ps"):
            val_items.append(("Current Price to Sales (TTM)", "RATIO", {"value_numeric": valuation["ps"], "unit": "x"}))
        if valuation.get("pcf"):
            val_items.append(("Current Price to Cashflow (TTM)", "RATIO", {"value_numeric": valuation["pcf"], "unit": "x"}))
        if valuation.get("pfcf"):
            val_items.append(("Current Price to Free Cashflow (TTM)", "RATIO", {"value_numeric": valuation["pfcf"], "unit": "x"}))
        if valuation.get("ev_ebitda"):
            val_items.append(("EV to EBITDA (TTM)", "RATIO", {"value_numeric": valuation["ev_ebitda"], "unit": "x"}))
        if valuation.get("dividend_yield"):
            val_items.append(("Dividend Yield", "PCT", {"value_numeric": valuation["dividend_yield"], "unit": "PCT"}))
    else:
        val_items = [
            ("Current PE Ratio (TTM)", "RATIO", metrics_dict.get("pe.ttm") or metrics_dict.get("pe")),
            ("Current Price to Book Value (PBV)", "RATIO", metrics_dict.get("pbv")),
            ("Current Price to Sales (TTM)", "RATIO", metrics_dict.get("ps.ttm") or metrics_dict.get("ps")),
            ("Current Price to Cashflow (TTM)", "RATIO", metrics_dict.get("pcf.ttm")),
            ("Current Price to Free Cashflow (TTM)", "RATIO", metrics_dict.get("pfcf.ttm")),
            ("EV to EBITDA (TTM)", "RATIO", metrics_dict.get("ev_ebitda.ttm") or metrics_dict.get("ev_ebitda")),
        ]

    _render_sec(val_title, val_items)

    # 3. Per Share
    _render_sec("Per Share", [
        ("Current EPS (TTM)", "CURR", facts_dict.get("ifrs:BasicEarningsLossPerShare") or metrics_dict.get("eps.ttm")),
        ("Revenue Per Share", "CURR", metrics_dict.get("revenue_per_share")),
        ("Cash Per Share", "CURR", metrics_dict.get("cash_per_share")),
        ("Current Book Value Per Share (BVPS)", "CURR", metrics_dict.get("bvps")),
        ("Free Cashflow Per Share", "CURR", metrics_dict.get("fcf_per_share")),
    ])

    # 4. Solvency
    _render_sec("Solvency", [
        ("Current Ratio", "RATIO", metrics_dict.get("current_ratio")),
        ("Quick Ratio", "RATIO", metrics_dict.get("quick_ratio")),
        ("Debt to Equity Ratio", "RATIO", metrics_dict.get("debt_equity")),
        ("Interest Coverage Ratio", "RATIO", metrics_dict.get("interest_coverage")),
    ])

    # 5. Profitability
    _render_sec("Profitability", [
        ("Return on Assets (ROA)", "RATIO", metrics_dict.get("roa")),
        ("Return on Equity (ROE)", "RATIO", metrics_dict.get("roe")),
        ("Gross Profit Margin", "RATIO", metrics_dict.get("margin.gross")),
        ("Operating Profit Margin", "RATIO", metrics_dict.get("margin.operating")),
        ("Net Profit Margin", "RATIO", metrics_dict.get("margin.net")),
        ("EBITDA Margin", "RATIO", metrics_dict.get("margin.ebitda")),
    ])

    # 6. Management Effectiveness
    _render_sec("Management Effectiveness", [
        ("Return on Capital Employed (ROCE)", "RATIO", metrics_dict.get("roce")),
        ("Days Sales Outstanding (DSO)", "DAYS", metrics_dict.get("dso")),
        ("Days Inventory (DIO)", "DAYS", metrics_dict.get("dio")),
        ("Days Payables Outstanding (DPO)", "DAYS", metrics_dict.get("dpo")),
    ])

    # 7. Dividend
    _render_sec("Dividend", [
        ("Dividend Per Share", "CURR", facts_dict.get("idx:DividendPerShare")),
        ("Payout Ratio", "RATIO", metrics_dict.get("payout_ratio")),
    ])

    # 8. Income Statement
    _render_sec("Income Statement", [
        ("Revenue", "CURR", facts_dict.get("ifrs:Revenue")),
        ("Gross Profit", "CURR", facts_dict.get("ifrs:GrossProfit")),
        ("Operating Profit", "CURR", facts_dict.get("ifrs:OperatingProfit")),
        ("EBITDA", "CURR", metrics_dict.get("ebitda")),
        ("Net Income", "CURR", facts_dict.get("ifrs:ProfitLoss")),
    ])

    # 9. Balance Sheet
    _render_sec("Balance Sheet", [
        ("Cash & Cash Equivalents", "CURR", facts_dict.get("ifrs:CashAndCashEquivalents")),
        ("Total Current Assets", "CURR", facts_dict.get("ifrs:CurrentAssets")),
        ("Total Assets", "CURR", facts_dict.get("ifrs:Assets")),
        ("Total Current Liabilities", "CURR", facts_dict.get("ifrs:CurrentLiabilities")),
        ("Total Liabilities", "CURR", facts_dict.get("ifrs:Liabilities")),
        ("Short-term Debt", "CURR", facts_dict.get("ifrs:ShortTermBorrowings")),
        ("Long-term Debt", "CURR", facts_dict.get("ifrs:LongTermBorrowings")),
        ("Total Debt", "CURR", metrics_dict.get("total_debt")),
        ("Net Debt", "CURR", metrics_dict.get("net_debt")),
        ("Common Equity", "CURR", facts_dict.get("ifrs:EquityAttributableToOwnersOfParent")),
        ("Total Equity", "CURR", facts_dict.get("ifrs:Equity")),
    ])

    # 10. Cash Flow Statement
    _render_sec("Cash Flow Statement", [
        ("Cash From Operations (CFO)", "CURR", facts_dict.get("ifrs:CashFlowsFromUsedInOperatingActivities")),
        ("Cash From Investing (CFI)", "CURR", facts_dict.get("ifrs:CashFlowsFromUsedInInvestingActivities")),
        ("Cash From Financing (CFF)", "CURR", facts_dict.get("ifrs:CashFlowsFromUsedInFinancingActivities")),
        ("Capital Expenditure (Capex)", "CURR", facts_dict.get("ifrs:PaymentsToAcquirePropertyPlantAndEquipment")),
        ("Free Cash Flow (FCF)", "CURR", metrics_dict.get("fcf")),
    ])

    # 11. Growth
    _render_sec("Growth (YoY / QoQ)", [
        ("Revenue (YoY Growth)", "RATIO", metrics_dict.get("yoy.revenue")),
        ("Operating Profit (YoY Growth)", "RATIO", metrics_dict.get("yoy.operating_profit")),
        ("Net Income (YoY Growth)", "RATIO", metrics_dict.get("yoy.net_profit")),
        ("Gross Profit (YoY Growth)", "RATIO", metrics_dict.get("yoy.gross_profit")),
        ("EPS (YoY Growth)", "RATIO", metrics_dict.get("yoy.eps")),
        ("Revenue (QoQ Growth)", "RATIO", metrics_dict.get("qoq.revenue")),
        ("Net Income (QoQ Growth)", "RATIO", metrics_dict.get("qoq.net_profit")),
    ])

    # 12. Price Performance & Technical State
    if technical_state:
        lines.append("#### Price Performance & Technical State")
        regime = technical_state.get("regime_label", "neutral")
        trend = technical_state.get("trend", "neutral")
        rsi = technical_state.get("rsi14")
        rsi_str = f" (RSI {rsi:.1f})" if rsi is not None else ""
        lines.append(f" * Market Regime: `{regime}` | Trend: `{trend}`{rsi_str}")
        if technical_state.get("dist_52wk_high_pct") is not None:
            lines.append(f" * 52-Week High Distance: {technical_state['dist_52wk_high_pct'] * 100:+.2f}%")
        if technical_state.get("dist_52wk_low_pct") is not None:
            lines.append(f" * 52-Week Low Distance: {technical_state['dist_52wk_low_pct'] * 100:+.2f}%")
        lines.append("")

    if len(lines) <= 3:
        lines.append("_No extracted headline financials or derived metrics are available yet for this issuer._")

    return "\n".join(lines).rstrip()


async def refresh_profile_task(ctx: dict[str, Any], doc_id: str) -> dict[str, Any]:
    """Builds and refreshes L6 issuer_profile summary card and embedding."""
    engine = ctx.get("db_pool") or ctx.get("db_engine")
    if engine is None:
        raise RuntimeError("Worker context missing database pool.")

    embedder = ctx.get("embedder") or Embedder()

    async with engine.connect() as conn:
        res = await conn.execute(
            text("SELECT id, ticker, fiscal_period, doc_hash FROM documents WHERE id = :id"),
            {"id": doc_id},
        )
        doc = res.mappings().first()
        if not doc:
            raise ValueError(f"Document {doc_id} not found in database.")

        ticker = doc["ticker"]
        fiscal_period = doc["fiscal_period"]
        doc_hash = doc["doc_hash"]

        # 1. Fetch top derived metrics for this ticker
        m_res = await conn.execute(
            text(
                """
                SELECT metric_id, fiscal_period, value_numeric, unit
                FROM derived_metrics
                WHERE ticker = :ticker
                ORDER BY fiscal_period DESC, metric_id ASC
                LIMIT 25;
                """
            ),
            {"ticker": ticker},
        )
        metrics = [dict(r) for r in m_res.mappings()]

        # 1b. Fetch headline P&L / balance-sheet facts from financial_facts.
        # Take the most recent value per concept_id, prefer this period.
        facts_res = await conn.execute(
            text(
                """
                SELECT DISTINCT ON (concept_id)
                    concept_id, fiscal_period, value_numeric, unit, source_page
                FROM financial_facts
                WHERE ticker = :ticker AND concept_id = ANY(:concepts)
                ORDER BY concept_id,
                         (fiscal_period = :period) DESC,
                         fiscal_period DESC;
                """
            ),
            {
                "ticker": ticker,
                "concepts": list(HEADLINE_CONCEPTS),
                "period": fiscal_period,
            },
        )
        headline_facts_rows = [dict(r) for r in facts_res.mappings()]
        # Preserve HEADLINE_CONCEPTS ordering rather than alphabetical from DISTINCT ON.
        by_concept = {r["concept_id"]: r for r in headline_facts_rows}
        headline_facts = [by_concept[c] for c in HEADLINE_CONCEPTS if c in by_concept]

        # Compute hash of metrics + headline facts to detect changes.
        state_repr = json.dumps(
            {
                "metrics": [
                    {"m": m["metric_id"], "p": m["fiscal_period"], "v": str(m["value_numeric"])}
                    for m in metrics
                ],
                "facts": [
                    {"c": f["concept_id"], "p": f["fiscal_period"], "v": str(f["value_numeric"])}
                    for f in headline_facts
                ],
            },
            sort_keys=True,
        )
        metrics_hash = hashlib.sha256(state_repr.encode("utf-8")).hexdigest()

        # Check existing profile
        p_res = await conn.execute(
            text("SELECT top_metrics_hash FROM issuer_profile WHERE ticker = :ticker"),
            {"ticker": ticker},
        )
        existing_profile = p_res.mappings().first()
        if existing_profile and existing_profile["top_metrics_hash"] == metrics_hash:
            log.info("Issuer profile already up to date", ticker=ticker)
            return {"status": "unchanged", "ticker": ticker}

        # 2. Fetch sector info
        sec_res = await conn.execute(
            text(
                "SELECT name, sector, sub_sector FROM peer_groups "
                "WHERE :ticker = ANY(tickers) LIMIT 1"
            ),
            {"ticker": ticker},
        )
        sec_row = sec_res.mappings().first()
        company_name = (sec_row["name"] if sec_row and sec_row.get("name") else f"PT {ticker} Tbk")
        sector_name = sec_row["sector"] if sec_row and sec_row.get("sector") else "Unclassified"
        sub_sector_name = sec_row["sub_sector"] if sec_row else None

        # 2b. Fetch technical state and live valuation info
        tech_res = await conn.execute(
            text("SELECT * FROM technical_state WHERE ticker = :ticker LIMIT 1"),
            {"ticker": ticker},
        )
        tech_row = tech_res.mappings().first()
        technical_state = dict(tech_row) if tech_row else None

        # Calculate on-the-fly live valuation with latest market price
        live_val = await calculate_valuation(conn, ticker, fiscal_period=fiscal_period, is_live=True)

        # 3. Synthesize summary
        summary_en = _synthesize_profile_summary(
            ticker=ticker,
            name=company_name,
            sector=sector_name,
            sub_sector=sub_sector_name,
            metrics=metrics,
            headline_facts=headline_facts,
            last_period=fiscal_period,
            technical_state=technical_state,
            valuation=live_val,
        )

        # 4. Generate profile embedding
        embs = await embedder.embed([summary_en])
        profile_emb = embs[0] if embs else None

        # 5. Check if vector extension is enabled
        has_vector_res = await conn.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        )
        has_vector = has_vector_res.first() is not None

        # 6. Upsert issuer_profile
        kpis = [m["metric_id"] for m in metrics[:10]]
        upsert_sql = """
        INSERT INTO issuer_profile (
            ticker, name, sector, sub_sector, profile_summary_en,
            last_facts_period, last_refreshed_at, refresh_recipe_ver, top_metrics_hash, key_kpis
        ) VALUES (
            :ticker, :name, :sector, :sub_sector, :summary,
            :period, now(), :ver, :hash, :kpis
        )
        ON CONFLICT (ticker) DO UPDATE SET
            name = EXCLUDED.name,
            sector = EXCLUDED.sector,
            sub_sector = EXCLUDED.sub_sector,
            profile_summary_en = EXCLUDED.profile_summary_en,
            last_facts_period = EXCLUDED.last_facts_period,
            last_refreshed_at = now(),
            refresh_recipe_ver = EXCLUDED.refresh_recipe_ver,
            top_metrics_hash = EXCLUDED.top_metrics_hash,
            key_kpis = EXCLUDED.key_kpis;
        """
        await conn.execute(
            text(upsert_sql),
            {
                "ticker": ticker,
                "name": company_name,
                "sector": sector_name,
                "sub_sector": sub_sector_name,
                "summary": summary_en,
                "period": fiscal_period,
                "ver": WORKER_VERSION,
                "hash": metrics_hash,
                "kpis": kpis,
            },
        )

        if has_vector and profile_emb:
            vec_str = f"[{','.join(str(x) for x in profile_emb)}]"
            await conn.execute(
                text(
                    """
                    UPDATE issuer_profile
                    SET profile_embedding = CAST(:emb AS halfvec(1024))
                    WHERE ticker = :ticker;
                    """
                ),
                {"emb": vec_str, "ticker": ticker},
            )

        # 7. Record worker_runs
        await conn.execute(
            text(
                """
                INSERT INTO worker_runs (doc_hash, worker_name, worker_version, status, finished_at)
                VALUES (:hash, 'refresh_profile', :ver, 'ok', now())
                ON CONFLICT (doc_hash, worker_name, worker_version)
                DO UPDATE SET status = 'ok', finished_at = now();
                """
            ),
            {"hash": doc_hash, "ver": WORKER_VERSION},
        )
        await conn.commit()

    log.info("Issuer profile refreshed successfully", ticker=ticker)
    return {"status": "ok", "ticker": ticker}
