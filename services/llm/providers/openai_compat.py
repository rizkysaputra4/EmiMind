"""OpenAI-compatible provider implementation (DeepSeek, Moonshot/Kimi, Together, Groq, Ollama)."""

from __future__ import annotations

from services.llm.providers.openai import OpenAIClient
from services.llm.types import Capabilities

OPENAI_COMPAT_CAPABILITIES: dict[str, Capabilities] = {
    "deepseek-chat": Capabilities(
        prompt_caching=True,
        tool_use=True,
        structured_json=True,
        vision=False,
        max_context_tokens=128_000,
        supports_system_message=True,
    ),
    "deepseek-reasoner": Capabilities(
        prompt_caching=True,
        tool_use=False,
        structured_json=False,
        vision=False,
        max_context_tokens=64_000,
        supports_system_message=True,
    ),
    "moonshot-v1-128k": Capabilities(
        prompt_caching=False,
        tool_use=True,
        structured_json=True,
        vision=False,
        max_context_tokens=128_000,
        supports_system_message=True,
    ),
    "llama3.1:70b": Capabilities(
        prompt_caching=False,
        tool_use=True,
        structured_json=True,
        vision=False,
        max_context_tokens=128_000,
        supports_system_message=True,
    ),
    "gemini-3.6-flash": Capabilities(
        prompt_caching=True,
        tool_use=True,
        structured_json=True,
        vision=True,
        max_context_tokens=1_000_000,
        supports_system_message=True,
    ),
    "gemini-3.7-flash": Capabilities(
        prompt_caching=True,
        tool_use=True,
        structured_json=True,
        vision=True,
        max_context_tokens=1_000_000,
        supports_system_message=True,
    ),
    "gemini-2.5-flash": Capabilities(
        prompt_caching=True,
        tool_use=True,
        structured_json=True,
        vision=True,
        max_context_tokens=1_000_000,
        supports_system_message=True,
    ),
    "gemini-2.0-flash": Capabilities(
        prompt_caching=True,
        tool_use=True,
        structured_json=True,
        vision=True,
        max_context_tokens=1_000_000,
        supports_system_message=True,
    ),
    "gemini-2.5-pro": Capabilities(
        prompt_caching=True,
        tool_use=True,
        structured_json=True,
        vision=True,
        max_context_tokens=2_000_000,
        supports_system_message=True,
    ),
    "gemini-1.5-flash": Capabilities(
        prompt_caching=True,
        tool_use=True,
        structured_json=True,
        vision=True,
        max_context_tokens=1_000_000,
        supports_system_message=True,
    ),
    "gemini-1.5-pro": Capabilities(
        prompt_caching=True,
        tool_use=True,
        structured_json=True,
        vision=True,
        max_context_tokens=2_000_000,
        supports_system_message=True,
    ),
}

DEFAULT_COMPAT_CAPABILITIES = Capabilities(
    prompt_caching=False,
    tool_use=True,
    structured_json=True,
    vision=False,
    max_context_tokens=128_000,
    supports_system_message=True,
)


class OpenAICompatClient(OpenAIClient):
    """Client for any OpenAI-compatible API endpoint."""

    provider_id = "openai_compat"

    def __init__(
        self,
        model: str = "deepseek-chat",
        api_key: str = "",
        base_url: str | None = None,
        max_output_tokens: int = 1024,
        timeout_s: int = 30,
    ) -> None:
        super().__init__(
            model=model,
            api_key=api_key,
            base_url=base_url or "https://api.deepseek.com/v1",
            max_output_tokens=max_output_tokens,
            timeout_s=timeout_s,
        )
        self.capabilities = OPENAI_COMPAT_CAPABILITIES.get(model, DEFAULT_COMPAT_CAPABILITIES)
