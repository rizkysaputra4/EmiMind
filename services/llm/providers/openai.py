"""OpenAI provider implementation of LLMClient protocol."""

from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI

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


class OpenAIClient(LLMClient):
    """Client for OpenAI models (GPT-4o, GPT-4o-mini, etc.)."""

    provider_id = "openai"

    def __init__(
        self,
        model: str = "gpt-4o",
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
            prompt_caching=True,  # Implicit caching
            tool_use=True,
            structured_json=True,
            vision=True,
            max_context_tokens=128_000,
            supports_system_message=True,
        )

        self._client = AsyncOpenAI(
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
        if force_tool and not self.capabilities.tool_use:
            raise LLMCapabilityError(f"Model '{self.model}' does not support tool use.")

        # 1. Format messages with system message prepended
        formatted_messages: list[dict[str, Any]] = []

        if system:
            system_text = "\n\n".join(b.text for b in system)
            formatted_messages.append({"role": "system", "content": system_text})

        for m in messages:
            content_str = ""
            is_tool_role = False

            for b in m.blocks:
                if isinstance(b, TextBlock):
                    content_str += b.text
                elif isinstance(b, ToolResultBlock):
                    is_tool_role = True
                    tool_name = b.name or "function"
                    # Gemini and OpenAI require the previous assistant message to include matching tool_calls
                    if formatted_messages and formatted_messages[-1].get("role") == "assistant":
                        prev_msg = formatted_messages[-1]
                        if "tool_calls" not in prev_msg:
                            prev_msg["tool_calls"] = []
                        prev_msg["tool_calls"].append(
                            {
                                "id": b.tool_call_id,
                                "type": "function",
                                "function": {
                                    "name": tool_name,
                                    "arguments": "{}",
                                },
                            }
                        )
                    tool_msg: dict[str, Any] = {
                        "role": "tool",
                        "tool_call_id": b.tool_call_id,
                        "name": tool_name,
                        "content": b.content,
                    }
                    formatted_messages.append(tool_msg)

            if not is_tool_role:
                formatted_messages.append({"role": m.role, "content": content_str})

        # 2. Format tool definitions
        formatted_tools: list[dict[str, Any]] | None = None
        if tools:
            formatted_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters_schema,
                    },
                }
                for t in tools
            ]

        tool_choice: Any = None
        if force_tool:
            tool_choice = {"type": "function", "function": {"name": force_tool}}

        log = get_logger("llm.openai")
        log.info(
            "Executing LLM prompt",
            provider=self.provider_id,
            model=self.model,
            messages=formatted_messages,
            tools=[t.name for t in tools] if tools else None,
            force_tool=force_tool,
        )

        # 3. Call OpenAI API
        try:
            kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": formatted_messages,
                "max_tokens": max_output_tokens or self.default_max_output_tokens,
                "temperature": temperature,
            }
            if formatted_tools:
                kwargs["tools"] = formatted_tools
            if tool_choice:
                kwargs["tool_choice"] = tool_choice
            if stop_sequences:
                kwargs["stop"] = stop_sequences

            resp = await self._client.chat.completions.create(**kwargs)
            choice = resp.choices[0]
            msg = choice.message

            tool_calls: list[ToolCall] = []
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments)
                    except Exception:
                        args = {}
                    tool_calls.append(
                        ToolCall(
                            id=tc.id,
                            name=tc.function.name,
                            arguments=args,
                        )
                    )

            # Usage mapping
            in_tok = resp.usage.prompt_tokens if resp.usage else 0
            out_tok = resp.usage.completion_tokens if resp.usage else 0
            cached_tok = 0
            if resp.usage and hasattr(resp.usage, "prompt_tokens_details"):
                cached_tok = getattr(resp.usage.prompt_tokens_details, "cached_tokens", 0) or 0

            usage = Usage(
                input_tokens=in_tok,
                output_tokens=out_tok,
                cache_read_tokens=cached_tok,
            )
            usage.cost_usd = calculate_cost_usd(self.provider_id, self.model, usage)

            stop_reason = "end_turn"
            if choice.finish_reason == "tool_calls":
                stop_reason = "tool_use"
            elif choice.finish_reason == "length":
                stop_reason = "max_tokens"

            log.info(
                "Received LLM response",
                provider=self.provider_id,
                model=self.model,
                response=msg.content or "",
                tool_calls=[tc.name for tc in tool_calls] if tool_calls else None,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
            )

            return LLMResponse(
                text=msg.content or "",
                stop_reason=stop_reason,
                tool_calls=tool_calls,
                usage=usage,
                raw={"id": resp.id, "model": resp.model},
            )

        except Exception as e:
            raise LLMProviderError(f"OpenAI complete failed: {e}") from e
