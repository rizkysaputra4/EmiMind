"""Unit tests for technical analysis indicator calculations."""

from __future__ import annotations

from services.market.technical_engine import (
    _calc_bollinger,
    _calc_macd,
    _calc_rsi,
    _calc_sma,
)


def test_calc_sma() -> None:
    prices = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert _calc_sma(prices, 3) == 40.0
    assert _calc_sma(prices, 10) is None


def test_calc_rsi() -> None:
    # Strictly increasing prices -> RSI = 100
    closes = [float(i) for i in range(1, 20)]
    rsi = _calc_rsi(closes, 14)
    assert rsi is not None
    assert rsi == 100.0


def test_calc_bollinger() -> None:
    closes = [100.0] * 20
    bb_up, bb_lo = _calc_bollinger(closes, 20, 2.0)
    assert bb_up == 100.0
    assert bb_lo == 100.0


def test_calc_macd() -> None:
    closes = [float(i) for i in range(1, 40)]
    macd, sig = _calc_macd(closes)
    assert macd is not None
    assert sig is not None
