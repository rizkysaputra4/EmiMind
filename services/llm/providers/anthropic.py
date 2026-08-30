"""Anthropic provider implementation of LLMClient protocol."""

from __future__ import annotations

import asyncio
from typing import Any

from anthropic import AsyncAnthropic, RateLimitError

from services.llm.errors import LLMCapabilityError, LLMProviderError
from services.llm.pricing import calculate_cost_usd
from services.llm.types import (
    Capabilities,
    LLMClient,
    LLMResponse,
    Message,
    TextBlock,
    ToolCall,
    ToolDef,
    ToolResultBlock,
    Usage,
)
from services.shared.logging import get_logger


class AnthropicClient(LLMClient):
    """Client for Anthropic Claude models."""

    provider_id = "anthropic"

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        api_key: str = "",
        base_url: str | None = None,
        max_output_tokens: int = 1024,
        timeout_s: int = 30,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.default_max_output_tokens = max_output_tokens
        self.timeout_s = timeout_s

        self.capabilities = Capabilities(
            prompt_caching=True,
            tool_use=True,
            structured_json=True,
            vision=True,
            max_context_tokens=200_000,
            supports_system_message=True,
        )

        self._client = AsyncAnthropic(
            api_key=api_key or "mock-key",
            base_url=base_url,
            timeout=float(timeout_s),
        )

    async def complete(
        self,
        system: list[TextBlock],
        messages: list[Message],
        tools: list[ToolDef] | None = None,
        force_tool: str | None = None,
        max_output_tokens: int = 1024,
        temperature: float = 0.2,
        stop_sequences: list[str] | None = None,
    ) -> LLMResponse:
        # Check tool use capability
        if force_tool and not self.capabilities.tool_use:
            raise LLMCapabilityError(f"Model '{self.model}' does not support tool use.")

        # 1. Format system message blocks with ephemeral cache control
        formatted_system: list[dict[str, Any]] = []
        for block in system:
            b_dict: dict[str, Any] = {"type": "text", "text": block.text}
            if block.cache_hint and self.capabilities.prompt_caching:
                b_dict["cache_control"] = {"type": "ephemeral"}
            formatted_system.append(b_dict)

        # 2. Format user/assistant message turns
        formatted_messages: list[dict[str, Any]] = []
        for m in messages:
            content_blocks: list[dict[str, Any]] = []
            for b in m.blocks:
                if isinstance(b, TextBlock):
                    c_dict: dict[str, Any] = {"type": "text", "text": b.text}
                    if b.cache_hint and self.capabilities.prompt_caching:
                        c_dict["cache_control"] = {"type": "ephemeral"}
                    content_blocks.append(c_dict)
                elif isinstance(b, ToolResultBlock):
                    content_blocks.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": b.tool_call_id,
                            "content": b.content,
                        }
                    )
            formatted_messages.append({"role": m.role, "content": content_blocks})

        # 3. Format tool definitions
        formatted_tools: list[dict[str, Any]] | None = None
        if tools:
            formatted_tools = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.parameters_schema,
                }
                for t in tools
            ]

        tool_choice: dict[str, Any] | None = None
        if force_tool:
            tool_choice = {"type": "tool", "name": force_tool}

        log = get_logger("llm.anthropic")
        log.info(
            "Executing LLM prompt",
            provider=self.provider_id,
            model=self.model,
            system=formatted_system,
            messages=formatted_messages,
            tools=[t.name for t in tools] if tools else None,
            force_tool=force_tool,
        )

        # 4. Invoke API with exponential backoff on 429
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                kwargs: dict[str, Any] = {
                    "model": self.model,
                    "system": formatted_system,
                    "messages": formatted_messages,
                    "max_tokens": max_output_tokens or self.default_max_output_tokens,
                }
                if formatted_tools:
                    kwargs["tools"] = formatted_tools
                if tool_choice:
                    kwargs["tool_choice"] = tool_choice
                if stop_sequences:
                    kwargs["stop_sequences"] = stop_sequences

                resp = await self._client.messages.create(**kwargs)

                # 5. Extract text and tool calls
                text_content = ""
                tool_calls: list[ToolCall] = []

                for block in resp.content:
                    if block.type == "text":
                        text_content += block.text
                    elif block.type == "tool_use":
                        tool_calls.append(
                            ToolCall(
                                id=block.id,
                                name=block.name,
                                arguments=block.input if isinstance(block.input, dict) else {},
                            )
                        )

                # Stop reason mapping
                stop_reason = "end_turn"
                if resp.stop_reason == "tool_use":
                    stop_reason = "tool_use"
                elif resp.stop_reason == "max_tokens":
                    stop_reason = "max_tokens"
                elif resp.stop_reason == "stop_sequence":
                    stop_reason = "stop_sequence"

                # Usage mapping
                usage = Usage(
                    input_tokens=resp.usage.input_tokens,
                    output_tokens=resp.usage.output_tokens,
                    cache_read_tokens=getattr(resp.usage, "cache_read_input_tokens", 0) or 0,
                    cache_write_tokens=getattr(resp.usage, "cache_creation_input_tokens", 0) or 0,
                )
                usage.cost_usd = calculate_cost_usd(self.provider_id, self.model, usage)

                log.info(
                    "Received LLM response",
                    provider=self.provider_id,
                    model=self.model,
                    response=text_content,
                    tool_calls=[tc.name for tc in tool_calls] if tool_calls else None,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                )

                return LLMResponse(
                    text=text_content,
                    stop_reason=stop_reason,
                    tool_calls=tool_calls,
                    usage=usage,
                    raw={"id": resp.id, "model": resp.model},
                )

            except RateLimitError as e:
                last_err = e
                await asyncio.sleep(2**attempt)
            except Exception as e:
                raise LLMProviderError(f"Anthropic complete failed: {e}") from e

        raise LLMProviderError(f"Anthropic rate limit retries exhausted: {last_err}")
