"""Dynamic live on-the-fly valuation and historical snapshot calculation engine."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from services.shared.logging import get_logger

log = get_logger(__name__)


async def get_market_price(
    conn: AsyncConnection,
    ticker: str,
    as_of: date | None = None,
) -> tuple[float | None, date | None]:
    """Retrieves the market closing price for a ticker as of a specific date or the latest available."""
    ticker_clean = ticker.upper()

    if as_of:
        res = await conn.execute(
            text(
                """
                SELECT c, dt FROM market_prices
                WHERE ticker = :ticker AND dt <= :as_of
                ORDER BY dt DESC
                LIMIT 1
                """
            ),
            {"ticker": ticker_clean, "as_of": as_of},
        )
    else:
        res = await conn.execute(
            text(
                """
                SELECT c, dt FROM market_prices
                WHERE ticker = :ticker
                ORDER BY dt DESC
                LIMIT 1
                """
            ),
            {"ticker": ticker_clean},
        )

    row = res.mappings().first()
    if row and row["c"] is not None:
        return float(row["c"]), row["dt"]

    # Fallback to technical_state if market_prices row is missing
    ts_res = await conn.execute(
        text("SELECT as_of FROM technical_state WHERE ticker = :ticker LIMIT 1"),
        {"ticker": ticker_clean},
    )
    ts_row = ts_res.mappings().first()
    if ts_row:
        return None, ts_row["as_of"]

    return None, None


async def calculate_valuation(
    conn: AsyncConnection,
    ticker: str,
    fiscal_period: str | None = None,
    is_live: bool = True,
) -> dict[str, Any] | None:
    """Calculates live on-the-fly valuation or historical release-date valuation snapshot.

    - If is_live is True: Uses the latest live market price against the latest reported fundamentals.
    - If is_live is False: Uses the market price on the filing release date of the specified fiscal_period.
    """
    ticker_clean = ticker.upper()

    # 1. Determine target period and price date
    if not fiscal_period:
        # Find latest period with documents or facts
        p_res = await conn.execute(
            text(
                """
                SELECT fiscal_period, period_end, ingested_at FROM documents
                WHERE ticker = :ticker
                ORDER BY period_end DESC, fiscal_period DESC
                LIMIT 1
                """
            ),
            {"ticker": ticker_clean},
        )
        doc_row = p_res.mappings().first()
        if not doc_row or not doc_row.get("fiscal_period"):
            return None
        target_period = str(doc_row["fiscal_period"])
        filing_dt = doc_row["period_end"]
    else:
        target_period = fiscal_period.upper()
        p_res = await conn.execute(
            text(
                """
                SELECT period_end, ingested_at FROM documents
                WHERE ticker = :ticker AND fiscal_period = :period
                LIMIT 1
                """
            ),
            {"ticker": ticker_clean, "period": target_period},
        )
        doc_row = p_res.mappings().first()
        filing_dt = doc_row["period_end"] if doc_row else None

    # 2. Fetch appropriate market price
    if is_live:
        price, price_dt = await get_market_price(conn, ticker_clean, as_of=None)
    else:
        price, price_dt = await get_market_price(conn, ticker_clean, as_of=filing_dt)

    # 3. Fetch fundamentals for target period
    facts_res = await conn.execute(
        text(
            """
            SELECT concept_id, value_numeric
            FROM financial_facts
            WHERE ticker = :ticker AND fiscal_period = :period
            """
        ),
        {"ticker": ticker_clean, "period": target_period},
    )
    facts = {r["concept_id"]: float(r["value_numeric"]) for r in facts_res.mappings().all() if r.get("value_numeric") is not None}

    # Fetch derived fundamentals for target period
    derived_res = await conn.execute(
        text(
            """
            SELECT metric_id, value_numeric
            FROM derived_metrics
            WHERE ticker = :ticker AND fiscal_period = :period
            """
        ),
        {"ticker": ticker_clean, "period": target_period},
    )
    derived = {r["metric_id"]: float(r["value_numeric"]) for r in derived_res.mappings().all() if r.get("value_numeric") is not None}

    # Extract core inputs
    shares = facts.get("idx:SharesOutstanding")
    equity = facts.get("ifrs:Equity") or facts.get("ifrs:EquityAttributableToOwnersOfParent")
    revenue = facts.get("ifrs:Revenue")
    net_income = facts.get("ifrs:ProfitLoss") or facts.get("ifrs:ProfitLossAttributableToOwnersOfParent")
    eps = facts.get("ifrs:BasicEarningsLossPerShare")
    cfo = facts.get("ifrs:CashFlowsFromUsedInOperatingActivities")
    fcf = derived.get("fcf")
    ebitda = derived.get("ebitda")
    net_debt = derived.get("net_debt") or 0.0
    dps = facts.get("idx:DividendPerShare")

    # If shares outstanding is not in facts, try to infer from MarketCap if present
    if not shares and facts.get("idx:MarketCap") and price:
        shares = facts["idx:MarketCap"] / price

    # Fallback for per-share items if EPS/BVPS not explicitly reported
    if not eps and net_income and shares and shares > 0:
        eps = net_income / shares

    bvps = derived.get("bvps")
    if not bvps and equity and shares and shares > 0:
        bvps = equity / shares

    rev_per_share = revenue / shares if (revenue and shares and shares > 0) else None
    cfo_per_share = cfo / shares if (cfo and shares and shares > 0) else None
    fcf_per_share = fcf / shares if (fcf and shares and shares > 0) else None

    # Compute valuation metrics
    valuation: dict[str, Any] = {
        "ticker": ticker_clean,
        "fiscal_period": target_period,
        "is_live": is_live,
        "price": price,
        "price_date": str(price_dt) if price_dt else None,
        "shares_outstanding": shares,
        "eps": eps,
        "bvps": bvps,
        "revenue_per_share": rev_per_share,
        "cashflow_per_share": cfo_per_share,
        "fcf_per_share": fcf_per_share,
        "market_cap": None,
        "pe": None,
        "pbv": None,
        "ps": None,
        "pcf": None,
        "pfcf": None,
        "ev_ebitda": None,
        "dividend_yield": None,
    }

    if price is not None and price > 0:
        if shares and shares > 0:
            valuation["market_cap"] = price * shares

        if eps and eps > 0:
            valuation["pe"] = round(price / eps, 2)

        if bvps and bvps > 0:
            valuation["pbv"] = round(price / bvps, 2)

        if rev_per_share and rev_per_share > 0:
            valuation["ps"] = round(price / rev_per_share, 2)

        if cfo_per_share and cfo_per_share > 0:
            valuation["pcf"] = round(price / cfo_per_share, 2)

        if fcf_per_share and fcf_per_share > 0:
            valuation["pfcf"] = round(price / fcf_per_share, 2)

        if valuation["market_cap"] and ebitda and ebitda > 0:
            ev = valuation["market_cap"] + net_debt
            valuation["ev_ebitda"] = round(ev / ebitda, 2)

        if dps and dps > 0:
            valuation["dividend_yield"] = round((dps / price) * 100.0, 2)

    return valuation
