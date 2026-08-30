"""Unit tests for deterministic technical regime classification rules."""

from __future__ import annotations

from services.market.regime_rules import classify_regime


def test_bullish_breakout_regime() -> None:
    ind = {
        "ticker": "BMRI",
        "close": 7000.0,
        "sma20": 6800.0,
        "sma50": 6500.0,
        "sma200": 6000.0,
        "rsi14": 62.0,
        "bb_upper": 7100.0,
        "bb_lower": 6500.0,
        "dist_52wk_high_pct": -0.02,
    }
    res = classify_regime(ind)
    assert res["regime_label"] == "bullish_breakout"
    assert res["trend"] == "bullish"
    assert res["momentum"] == "bullish"


def test_capitulation_regime() -> None:
    ind = {
        "ticker": "UNVR",
        "close": 2000.0,
        "sma20": 2400.0,
        "sma50": 2800.0,
        "sma200": 3500.0,
        "rsi14": 18.0,
        "bb_upper": 2700.0,
        "bb_lower": 1900.0,
        "dist_52wk_high_pct": -0.45,
    }
    res = classify_regime(ind)
    assert res["regime_label"] == "capitulation"
    assert res["trend"] == "bearish"
    assert res["momentum"] == "oversold"


def test_range_bound_regime() -> None:
    ind = {
        "ticker": "TLKM",
        "close": 3000.0,
        "sma20": 3020.0,
        "sma50": 3000.0,
        "sma200": 3400.0,
        "rsi14": 49.0,
        "bb_upper": 3150.0,
        "bb_lower": 2900.0,
        "dist_52wk_high_pct": -0.15,
    }
    res = classify_regime(ind)
    assert res["regime_label"] == "range_bound"
    assert res["momentum"] == "neutral"
