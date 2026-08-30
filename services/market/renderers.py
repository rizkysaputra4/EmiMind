"""Technical state renderer for LLM prompts and chat responses."""

from __future__ import annotations

from typing import Any


def render_technical_state(state: dict[str, Any]) -> str:
    """Renders compact technical regime summary string per BLUEPRINT §11.3."""
    ticker = state.get("ticker", "UNKNOWN")
    as_of = state.get("as_of", "")
    regime = state.get("regime_label", "neutral_consolidation")
    trend = state.get("trend", "neutral")
    momentum = state.get("momentum", "neutral")
    rsi = state.get("rsi14")
    rsi_str = f" (RSI {rsi:.1f})" if rsi is not None else ""
    vol_avg = state.get("vol_avg20")
    vol_str = f" (20d avg: {vol_avg:,.0f})" if vol_avg is not None else ""
    dist_high = state.get("dist_52wk_high_pct")
    dist_high_str = f"{dist_high * 100:+.1f}%" if dist_high is not None else "N/A"
    dist_low = state.get("dist_52wk_low_pct")
    dist_low_str = f"{dist_low * 100:+.1f}%" if dist_low is not None else "N/A"

    lines = [
        f"**{ticker} Technical State (as of {as_of}):**",
        f"- **Regime:** `{regime}`",
        f"- **Trend:** `{trend}`",
        f"- **Momentum:** `{momentum}`{rsi_str}",
        f"- **Volume:** `{state.get('volume_regime', 'average')}`{vol_str}",
        f"- **52-Week Range Distance:** High {dist_high_str} | Low {dist_low_str}",
    ]

    return "\n".join(lines)
