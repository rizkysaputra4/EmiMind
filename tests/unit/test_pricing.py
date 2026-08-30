"""Unit tests for token pricing calculation."""

from __future__ import annotations

from services.llm.pricing import calculate_cost_usd
from services.llm.types import Usage


def test_pricing_calculation() -> None:
    # 100k input, 20k output for Claude Sonnet 4.6
    # input: 100,000 * 3.0 / 1M = 0.30
    # output: 20,000 * 15.0 / 1M = 0.30
    # total = 0.60
    usage = Usage(input_tokens=100_000, output_tokens=20_000)
    cost = calculate_cost_usd("anthropic", "claude-sonnet-4-6", usage)
    assert cost == 0.60

    # DeepSeek chat
    # 1M input * 0.14 = 0.14
    # 500k output * 0.28 = 0.14
    # total = 0.28
    usage_ds = Usage(input_tokens=1_000_000, output_tokens=500_000)
    cost_ds = calculate_cost_usd("openai_compat", "deepseek-chat", usage_ds)
    assert cost_ds == 0.28

    # Unknown model -> returns None
    assert calculate_cost_usd("unknown", "unknown-model", usage) is None
