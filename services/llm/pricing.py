"""Model pricing table and token cost calculation utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.llm.types import Usage


@dataclass(frozen=True)
class PriceRow:
    input_per_mtok: float
    output_per_mtok: float
    cache_read_per_mtok: float = 0.0
    cache_write_per_mtok: float = 0.0


# Pricing table in USD per 1M tokens
PRICE_PER_MTOK: dict[tuple[str, str], PriceRow] = {
    # Anthropic
    ("anthropic", "claude-sonnet-4-6"): PriceRow(
        input_per_mtok=3.00,
        output_per_mtok=15.00,
        cache_read_per_mtok=0.30,
        cache_write_per_mtok=3.75,
    ),
    ("anthropic", "claude-haiku-4-5-20251001"): PriceRow(
        input_per_mtok=1.00,
        output_per_mtok=5.00,
        cache_read_per_mtok=0.10,
        cache_write_per_mtok=1.25,
    ),
    # OpenAI
    ("openai", "gpt-4o"): PriceRow(
        input_per_mtok=2.50,
        output_per_mtok=10.00,
        cache_read_per_mtok=1.25,
    ),
    ("openai", "gpt-4o-mini"): PriceRow(
        input_per_mtok=0.15,
        output_per_mtok=0.60,
        cache_read_per_mtok=0.075,
    ),
    # DeepSeek (via openai_compat)
    ("openai_compat", "deepseek-chat"): PriceRow(
        input_per_mtok=0.14,
        output_per_mtok=0.28,
        cache_read_per_mtok=0.014,
    ),
    ("openai_compat", "deepseek-reasoner"): PriceRow(
        input_per_mtok=0.55,
        output_per_mtok=2.19,
        cache_read_per_mtok=0.14,
    ),
    # Moonshot / Kimi
    ("openai_compat", "moonshot-v1-128k"): PriceRow(
        input_per_mtok=0.85,
        output_per_mtok=0.85,
    ),
    # Google Gemini (via openai_compat)
    ("openai_compat", "gemini-3.6-flash"): PriceRow(
        input_per_mtok=0.10,
        output_per_mtok=0.40,
        cache_read_per_mtok=0.025,
    ),
    ("openai_compat", "gemini-3.7-flash"): PriceRow(
        input_per_mtok=0.10,
        output_per_mtok=0.40,
        cache_read_per_mtok=0.025,
    ),
    ("openai_compat", "gemini-2.5-flash"): PriceRow(
        input_per_mtok=0.10,
        output_per_mtok=0.40,
        cache_read_per_mtok=0.025,
    ),
    ("openai_compat", "gemini-2.0-flash"): PriceRow(
        input_per_mtok=0.10,
        output_per_mtok=0.40,
        cache_read_per_mtok=0.025,
    ),
    ("openai_compat", "gemini-2.5-pro"): PriceRow(
        input_per_mtok=1.25,
        output_per_mtok=5.00,
        cache_read_per_mtok=0.3125,
    ),
    ("openai_compat", "gemini-1.5-flash"): PriceRow(
        input_per_mtok=0.075,
        output_per_mtok=0.30,
        cache_read_per_mtok=0.01875,
    ),
    ("openai_compat", "gemini-1.5-pro"): PriceRow(
        input_per_mtok=1.25,
        output_per_mtok=5.00,
        cache_read_per_mtok=0.3125,
    ),
    # CLI Agent
    ("cli_agent", "claude"): PriceRow(input_per_mtok=0.0, output_per_mtok=0.0),
    ("cli_agent", "gemini"): PriceRow(input_per_mtok=0.0, output_per_mtok=0.0),
    ("cli_agent", "codex"): PriceRow(input_per_mtok=0.0, output_per_mtok=0.0),
    ("cli_agent", "crush"): PriceRow(input_per_mtok=0.0, output_per_mtok=0.0),
    ("cli_agent", "amp"): PriceRow(input_per_mtok=0.0, output_per_mtok=0.0),
    ("cli_agent", "qwen"): PriceRow(input_per_mtok=0.0, output_per_mtok=0.0),
}


def calculate_cost_usd(provider: str, model: str, usage: Usage) -> float | None:
    """Calculates approximate USD cost for token usage."""
    price = PRICE_PER_MTOK.get((provider, model))
    if not price:
        return None

    cost = (
        (usage.input_tokens / 1_000_000) * price.input_per_mtok
        + (usage.output_tokens / 1_000_000) * price.output_per_mtok
        + (usage.cache_read_tokens / 1_000_000) * price.cache_read_per_mtok
        + (usage.cache_write_tokens / 1_000_000) * price.cache_write_per_mtok
    )
    return round(cost, 6)
