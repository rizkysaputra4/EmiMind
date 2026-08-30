"""Factory and registry for instantiating provider-neutral LLM clients."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal

from services.llm.fakes import FakeLLMClient
from services.llm.providers.anthropic import AnthropicClient
from services.llm.providers.cli_agent import CLIAgentClient
from services.llm.providers.openai import OpenAIClient
from services.llm.providers.openai_compat import OpenAICompatClient
from services.llm.types import LLMClient
from services.shared.config import get_settings

_REGISTRY: dict[str, Any] = {
    "anthropic": AnthropicClient,
    "cli_agent": CLIAgentClient,
    "openai": OpenAIClient,
    "openai_compat": OpenAICompatClient,
    "fake": FakeLLMClient,
}


@lru_cache
def get_llm(role: Literal["reasoner", "utility", "judge"]) -> LLMClient:
    """Returns configured singleton LLMClient for the given role."""
    s = get_settings()
    cfg = s.llm_role(role)
    cls = _REGISTRY[cfg.provider]
    client: LLMClient = cls(
        model=cfg.model,
        api_key=cfg.api_key.get_secret_value(),
        base_url=cfg.base_url,
        max_output_tokens=cfg.max_output_tokens,
        timeout_s=cfg.timeout_s,
    )
    return client
