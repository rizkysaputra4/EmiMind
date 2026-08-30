"""Technical analysis indicators calculator over historical daily market prices."""

from __future__ import annotations

import math
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from services.shared.logging import get_logger
from services.shared.types import Ticker

log = get_logger("market.technical_engine")


def _calc_sma(prices: list[float], window: int) -> float | None:
    if len(prices) < window:
        return None
    return sum(prices[-window:]) / float(window)


def _calc_rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None

    gains: list[float] = []
    losses: list[float] = []

    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        if diff > 0:
            gains.append(diff)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(diff))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _calc_ema(prices: list[float], window: int) -> list[float]:
    if not prices:
        return []
    k = 2.0 / (window + 1)
    ema = [prices[0]]
    for p in prices[1:]:
        ema.append(p * k + ema[-1] * (1.0 - k))
    return ema


def _calc_macd(closes: list[float]) -> tuple[float | None, float | None]:
    if len(closes) < 35:
        return None, None
    ema12 = _calc_ema(closes, 12)
    ema26 = _calc_ema(closes, 26)
    macd_line = [e12 - e26 for e12, e26 in zip(ema12, ema26, strict=False)]
    signal_line = _calc_ema(macd_line, 9)
    return round(macd_line[-1], 2), round(signal_line[-1], 2)


def _calc_bollinger(
    closes: list[float], window: int = 20, num_std: float = 2.0
) -> tuple[float | None, float | None]:
    if len(closes) < window:
        return None, None
    subset = closes[-window:]
    mean = sum(subset) / window
    variance = sum((x - mean) ** 2 for x in subset) / window
    std = math.sqrt(variance)
    return round(mean + num_std * std, 2), round(mean - num_std * std, 2)


def _calc_atr(bars: list[dict[str, Any]], period: int = 14) -> float | None:
    if len(bars) < period + 1:
        return None

    tr_list: list[float] = []
    for i in range(1, len(bars)):
        high_val = float(bars[i]["h"])
        low_val = float(bars[i]["l"])
        prev_c = float(bars[i - 1]["c"])
        tr = max(high_val - low_val, abs(high_val - prev_c), abs(low_val - prev_c))
        tr_list.append(tr)

    return sum(tr_list[-period:]) / float(period)


async def compute_indicators(
    conn: AsyncConnection,
    ticker: Ticker,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Computes technical indicator state for a ticker as of a given date (default today)."""
    target_dt = as_of or date.today()
    ticker_str = str(ticker).upper()

    res = await conn.execute(
        text(
            """
            SELECT dt, o, h, l, c, v
            FROM market_prices
            WHERE ticker = :ticker AND dt <= :dt
            ORDER BY dt ASC;
            """
        ),
        {"ticker": ticker_str, "dt": target_dt},
    )
    bars = [dict(r) for r in res.mappings()]

    if not bars:
        log.warning(
            "No price bars found to compute indicators",
            ticker=ticker_str,
            as_of=str(target_dt),
        )
        return {
            "ticker": ticker_str,
            "as_of": target_dt,
            "close": None,
            "sma20": None,
            "sma50": None,
            "sma200": None,
            "rsi14": None,
            "macd": None,
            "macd_signal": None,
            "bb_upper": None,
            "bb_lower": None,
            "atr14": None,
            "vol_avg20": None,
            "dist_52wk_high_pct": None,
            "dist_52wk_low_pct": None,
        }

    closes = [float(b["c"]) for b in bars]
    volumes = [int(b["v"]) for b in bars]
    last_close = closes[-1]
    actual_as_of = bars[-1]["dt"]

    lookback_52w = bars[-252:]
    high_52w = max(float(b["h"]) for b in lookback_52w)
    low_52w = min(float(b["l"]) for b in lookback_52w)

    dist_high_pct = (last_close - high_52w) / high_52w if high_52w > 0 else 0.0
    dist_low_pct = (last_close - low_52w) / low_52w if low_52w > 0 else 0.0

    sma20 = _calc_sma(closes, 20)
    sma50 = _calc_sma(closes, 50)
    sma200 = _calc_sma(closes, 200)
    rsi14 = _calc_rsi(closes, 14)
    macd, macd_sig = _calc_macd(closes)
    bb_up, bb_lo = _calc_bollinger(closes, 20, 2.0)
    atr14 = _calc_atr(bars, 14)
    vol_avg20 = _calc_sma([float(v) for v in volumes], 20)

    return {
        "ticker": ticker_str,
        "as_of": actual_as_of,
        "close": last_close,
        "sma20": round(sma20, 2) if sma20 is not None else None,
        "sma50": round(sma50, 2) if sma50 is not None else None,
        "sma200": round(sma200, 2) if sma200 is not None else None,
        "rsi14": round(rsi14, 2) if rsi14 is not None else None,
        "macd": macd,
        "macd_signal": macd_sig,
        "bb_upper": bb_up,
        "bb_lower": bb_lo,
        "atr14": round(atr14, 2) if atr14 is not None else None,
        "vol_avg20": int(vol_avg20) if vol_avg20 is not None else None,
        "dist_52wk_high_pct": round(dist_high_pct, 4),
        "dist_52wk_low_pct": round(dist_low_pct, 4),
    }
