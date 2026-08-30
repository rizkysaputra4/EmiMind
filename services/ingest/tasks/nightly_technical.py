"""Nightly scheduled arq worker task: computes technical regime states for covered tickers."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from sqlalchemy import text

from services.market.regime_rules import classify_regime
from services.market.technical_engine import compute_indicators
from services.shared.db import create_pool
from services.shared.logging import get_logger
from services.shared.types import Ticker

log = get_logger("ingest.nightly_technical")
WORKER_VERSION = "1.0"


async def nightly_technical_task(
    ctx: dict[str, Any], tickers_list: list[str] | None = None
) -> dict[str, Any]:
    """Scheduled nightly task computing and persisting technical states and snapshots."""
    pool = ctx.get("db_pool") or create_pool()
    computed_count = 0

    async with pool.connect() as conn:
        if not tickers_list:
            res = await conn.execute(text("SELECT ticker FROM issuer_profile ORDER BY ticker ASC;"))
            tickers_list = [r[0] for r in res.fetchall()]

        if not tickers_list:
            tickers_list = [
                "BMRI",
                "BBRI",
                "BBCA",
                "BBNI",
                "ADRO",
                "PTBA",
                "ITMG",
                "TLKM",
                "ASII",
                "ICBP",
            ]

        for t_str in tickers_list:
            ticker = Ticker(t_str)
            raw_ind = await compute_indicators(conn, ticker)
            classified = classify_regime(raw_ind)

            as_of_val = classified.get("as_of") or date.today()

            # Upsert into technical_state
            await conn.execute(
                text(
                    """
                    INSERT INTO technical_state (
                        ticker, as_of, sma20, sma50, sma200, rsi14, macd, macd_signal,
                        bb_upper, bb_lower, atr14, vol_avg20, dist_52wk_high_pct, dist_52wk_low_pct,
                        trend, momentum, volatility, volume_regime, regime_label
                    )
                    VALUES (
                        :ticker, :as_of, :sma20, :sma50, :sma200, :rsi14, :macd, :macd_signal,
                        :bb_upper, :bb_lower, :atr14, :vol_avg20, :dist_52wk_high_pct, :dist_52wk_low_pct,
                        :trend, :momentum, :volatility, :volume_regime, :regime_label
                    )
                    ON CONFLICT (ticker) DO UPDATE SET
                        as_of = EXCLUDED.as_of,
                        sma20 = EXCLUDED.sma20,
                        sma50 = EXCLUDED.sma50,
                        sma200 = EXCLUDED.sma200,
                        rsi14 = EXCLUDED.rsi14,
                        macd = EXCLUDED.macd,
                        macd_signal = EXCLUDED.macd_signal,
                        bb_upper = EXCLUDED.bb_upper,
                        bb_lower = EXCLUDED.bb_lower,
                        atr14 = EXCLUDED.atr14,
                        vol_avg20 = EXCLUDED.vol_avg20,
                        dist_52wk_high_pct = EXCLUDED.dist_52wk_high_pct,
                        dist_52wk_low_pct = EXCLUDED.dist_52wk_low_pct,
                        trend = EXCLUDED.trend,
                        momentum = EXCLUDED.momentum,
                        volatility = EXCLUDED.volatility,
                        volume_regime = EXCLUDED.volume_regime,
                        regime_label = EXCLUDED.regime_label;
                    """
                ),
                {
                    "ticker": t_str,
                    "as_of": as_of_val,
                    "sma20": classified.get("sma20"),
                    "sma50": classified.get("sma50"),
                    "sma200": classified.get("sma200"),
                    "rsi14": classified.get("rsi14"),
                    "macd": classified.get("macd"),
                    "macd_signal": classified.get("macd_signal"),
                    "bb_upper": classified.get("bb_upper"),
                    "bb_lower": classified.get("bb_lower"),
                    "atr14": classified.get("atr14"),
                    "vol_avg20": classified.get("vol_avg20"),
                    "dist_52wk_high_pct": classified.get("dist_52wk_high_pct"),
                    "dist_52wk_low_pct": classified.get("dist_52wk_low_pct"),
                    "trend": classified.get("trend"),
                    "momentum": classified.get("momentum"),
                    "volatility": classified.get("volatility"),
                    "volume_regime": classified.get("volume_regime"),
                    "regime_label": classified.get("regime_label"),
                },
            )

            # Insert history snapshot
            # Convert date objects in snapshot for json serialization
            serializable_snap = {
                k: (str(v) if isinstance(v, date) else v) for k, v in classified.items()
            }
            await conn.execute(
                text(
                    """
                    INSERT INTO technical_state_history (ticker, as_of, snapshot)
                    VALUES (:ticker, :as_of, CAST(:snapshot AS jsonb))
                    ON CONFLICT (ticker, as_of) DO UPDATE SET snapshot = EXCLUDED.snapshot;
                    """
                ),
                {
                    "ticker": t_str,
                    "as_of": as_of_val,
                    "snapshot": json.dumps(serializable_snap),
                },
            )
            computed_count += 1

        await conn.commit()

    log.info(
        "Nightly technical analysis finished", tickers=len(tickers_list), computed=computed_count
    )
    return {
        "status": "success",
        "tickers_count": len(tickers_list),
        "computed": computed_count,
    }
