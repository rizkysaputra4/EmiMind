"""Provider-neutral LLM client interfaces, data types, and protocol definitions."""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel

Role = Literal["reasoner", "utility", "judge"]


class ToolDef(BaseModel):
    name: str
    description: str
    parameters_schema: dict[str, Any]  # JSONSchema draft-07 subset


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any]


class TextBlock(BaseModel):
    kind: Literal["text"] = "text"
    text: str
    cache_hint: bool = False  # provider treats this block as cacheable when supported


class ToolResultBlock(BaseModel):
    kind: Literal["tool_result"] = "tool_result"
    tool_call_id: str
    content: str
    name: str | None = None


class Message(BaseModel):
    role: Literal["user", "assistant"]
    blocks: list[TextBlock | ToolResultBlock]


class Usage(BaseModel):
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float | None = None


class LLMResponse(BaseModel):
    text: str
    stop_reason: Literal["end_turn", "tool_use", "max_tokens", "stop_sequence", "other"]
    tool_calls: list[ToolCall] = []
    usage: Usage
    raw: dict[str, Any] | None = None  # provider payload, debug-only


class Capabilities(BaseModel):
    prompt_caching: bool
    tool_use: bool
    structured_json: bool  # native JSON mode
    vision: bool
    max_context_tokens: int
    supports_system_message: bool


class LLMClient(Protocol):
    provider_id: str  # 'anthropic' | 'openai' | 'openai_compat' | 'fake'
    model: str
    capabilities: Capabilities

    async def complete(
        self,
        system: list[TextBlock],
        messages: list[Message],
        tools: list[ToolDef] | None = None,
        force_tool: str | None = None,  # provider-neutral 'tool_choice'
        max_output_tokens: int = 1024,
        temperature: float = 0.2,
        stop_sequences: list[str] | None = None,
    ) -> LLMResponse: ...
