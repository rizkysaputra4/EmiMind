"""Unit tests for provider-neutral LLM types and fake client execution."""

from __future__ import annotations

import pytest

from services.llm.fakes import FakeLLMClient
from services.llm.types import (
    Message,
    TextBlock,
    ToolCall,
    ToolDef,
    ToolResultBlock,
    Usage,
)


def test_llm_types_instantiation() -> None:
    text_block = TextBlock(text="Hello world", cache_hint=True)
    assert text_block.kind == "text"
    assert text_block.cache_hint is True

    tool_res = ToolResultBlock(tool_call_id="call_123", content="Result content")
    assert tool_res.kind == "tool_result"

    msg = Message(role="user", blocks=[text_block, tool_res])
    assert len(msg.blocks) == 2

    tool_def = ToolDef(
        name="test_tool",
        description="A test tool",
        parameters_schema={"type": "object", "properties": {"q": {"type": "string"}}},
    )
    assert tool_def.name == "test_tool"

    tool_call = ToolCall(id="tc_1", name="test_tool", arguments={"q": "query"})
    assert tool_call.arguments["q"] == "query"

    usage = Usage(input_tokens=100, output_tokens=50, cache_read_tokens=20)
    assert usage.input_tokens == 100
    assert usage.cache_read_tokens == 20


@pytest.mark.asyncio
async def test_fake_llm_client() -> None:
    client = FakeLLMClient()
    assert client.provider_id == "fake"
    assert client.capabilities.tool_use is True

    resp = await client.complete(
        system=[TextBlock(text="You are an assistant.")],
        messages=[
            Message(role="user", blocks=[TextBlock(text="What is BMRI net profit in 2024?")])
        ],
    )
    assert "BMRI" in resp.text
    assert "[BMRI-FS-2024Q4#" in resp.text
    assert resp.usage.input_tokens > 0
