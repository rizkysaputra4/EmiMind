"""Peer group cross-sectional percentile ranking recipe."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from services.shared.types import FiscalPeriod, Ticker


async def compute_peer_percentiles(
    conn: AsyncConnection,
    ticker: Ticker,
    fiscal_period: FiscalPeriod,
) -> list[dict[str, Any]]:
    """Computes cross-sectional percentile ranks for all computed metrics across peer groups."""
    # 1. Fetch peer groups this ticker belongs to
    pg_res = await conn.execute(
        text("SELECT id, name, tickers FROM peer_groups WHERE :ticker = ANY(tickers)"),
        {"ticker": ticker},
    )
    peer_groups = pg_res.mappings().all()
    if not peer_groups:
        return []

    results: list[dict[str, Any]] = []

    for pg in peer_groups:
        pg_id = pg["id"]
        tickers: list[str] = pg["tickers"]
        if not tickers or ticker not in tickers:
            continue

        # 2. Fetch all derived_metrics for this peer group in this period (excluding peer_pct.*)
        m_res = await conn.execute(
            text(
                """
                SELECT ticker, metric_id, value_numeric
                FROM derived_metrics
                WHERE ticker = ANY(:tickers)
                  AND fiscal_period = :period
                  AND metric_id NOT LIKE 'peer_pct.%'
                  AND value_numeric IS NOT NULL;
                """
            ),
            {"tickers": tickers, "period": fiscal_period},
        )
        rows = m_res.mappings().all()

        # Group values by metric_id
        metrics_by_id: dict[str, dict[str, Decimal]] = {}
        for r in rows:
            m_id = r["metric_id"]
            t_name = r["ticker"]
            val = Decimal(str(r["value_numeric"]))
            if m_id not in metrics_by_id:
                metrics_by_id[m_id] = {}
            metrics_by_id[m_id][t_name] = val

        # 3. For each metric, compute percentile of this ticker
        for m_id, ticker_vals in metrics_by_id.items():
            if ticker not in ticker_vals:
                continue

            my_val = ticker_vals[ticker]
            all_vals = list(ticker_vals.values())
            n = len(all_vals)
            if n <= 1:
                pct = Decimal("50.0")
            else:
                less = sum(1 for v in all_vals if v < my_val)
                equal = sum(1 for v in all_vals if v == my_val)
                pct = Decimal(str(((less + 0.5 * equal) / n) * 100.0))

            results.append(
                {
                    "ticker": ticker,
                    "fiscal_period": fiscal_period,
                    "metric_id": f"peer_pct.{m_id}",
                    "value_numeric": round(pct, 2),
                    "unit": "PCT",
                    "inputs": {
                        "peer_group_id": pg_id,
                        "peer_count": n,
                        "peers": tickers,
                        "metric": m_id,
                        "value": float(my_val),
                    },
                    "peer_group_id": pg_id,
                    "recipe_version": "1.0",
                }
            )

    return results
