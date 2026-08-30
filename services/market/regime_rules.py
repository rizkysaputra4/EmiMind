"""Deterministic technical market regime classification engine."""

from __future__ import annotations

from typing import Any


def _determine_trend(sma20: float, sma50: float, sma200: float | None) -> str:
    if sma200 is not None:
        if sma20 > sma50 > sma200:
            return "bullish"
        if sma20 < sma50 < sma200:
            return "bearish"
        return "neutral"
    if sma20 > sma50:
        return "bullish"
    return "bearish" if sma20 < sma50 else "neutral"


def _determine_momentum(rsi14: float) -> str:
    if rsi14 >= 70.0:
        return "overbought"
    if rsi14 >= 55.0:
        return "bullish"
    if rsi14 <= 30.0:
        return "oversold"
    if rsi14 <= 45.0:
        return "bearish"
    return "neutral"


def classify_regime(ind: dict[str, Any]) -> dict[str, Any]:
    """Evaluates rule-based technical market regime from computed indicator vector."""
    c = ind.get("close")
    sma20 = ind.get("sma20")
    sma50 = ind.get("sma50")
    sma200 = ind.get("sma200")
    rsi14 = ind.get("rsi14") or 50.0
    bb_up = ind.get("bb_upper")
    bb_lo = ind.get("bb_lower")
    dist_high = ind.get("dist_52wk_high_pct") or 0.0

    if c is None or sma20 is None or sma50 is None:
        return {
            **ind,
            "trend": "insufficient_data",
            "momentum": "neutral",
            "volatility": "normal",
            "volume_regime": "average",
            "regime_label": "insufficient_data",
        }

    trend = _determine_trend(sma20, sma50, sma200)
    momentum = _determine_momentum(rsi14)

    bb_width_pct = ((bb_up - bb_lo) / sma20) if (bb_up and bb_lo and sma20 > 0) else 0.10
    volatility = (
        "expanding" if bb_width_pct > 0.15 else ("contracting" if bb_width_pct < 0.06 else "normal")
    )
    volume_regime = "average"

    # Evaluate rules in exact order
    if rsi14 < 25.0 and dist_high < -0.20:
        regime_label = "capitulation"
    elif sma200 and c > sma20 > sma50 > sma200 and 55.0 <= rsi14 <= 75.0:
        regime_label = "bullish_breakout"
    elif sma200 and sma20 > sma50 > sma200 and sma50 <= c <= sma20 and 40.0 <= rsi14 <= 55.0:
        regime_label = "bullish_pullback"
    elif sma200 and c < sma20 < sma50 < sma200:
        regime_label = "bearish_breakdown"
    elif sma200 and sma20 < sma50 < sma200 and c > sma20 and 40.0 <= rsi14 <= 55.0:
        regime_label = "bearish_bounce"
    elif bb_width_pct <= 0.05:
        regime_label = "low_volatility_squeeze"
    elif abs(sma20 - sma50) / sma50 <= 0.03:
        regime_label = "range_bound"
    else:
        regime_label = "neutral_consolidation"

    return {
        **ind,
        "trend": trend,
        "momentum": momentum,
        "volatility": volatility,
        "volume_regime": volume_regime,
        "regime_label": regime_label,
    }
