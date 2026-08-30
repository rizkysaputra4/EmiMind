"""Unit tests for the CLI agent LLM provider and adapter registry."""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from services.llm.errors import LLMCapabilityError
from services.llm.providers.cli_agent import (
    CLIAdapter,
    CLIAgentClient,
    _claude_parse,
    _resolve_launch,
    register_adapter,
)
from services.llm.types import Capabilities, Message, TextBlock


def _fake_cli_argv(prompt: str, model: str, extra: list[str]) -> list[str]:
    # Runs python -c "import json; print(json.dumps({'result': 'echo: ' + ...}))"
    code = (
        "import json, sys; "
        "print(json.dumps({'result': 'hello from fake cli', 'usage': {'input_tokens': 5, 'output_tokens': 3}}))"
    )
    return ["-c", code]


@pytest.fixture(autouse=True)
def register_fake_cli_adapter() -> None:
    adapter = CLIAdapter(
        key="fake_cli_test",
        default_binary=sys.executable,
        build_argv=_fake_cli_argv,
        parse_stdout=_claude_parse,
        capabilities=Capabilities(
            prompt_caching=False,
            tool_use=False,
            structured_json=True,
            vision=False,
            max_context_tokens=10000,
            supports_system_message=True,
        ),
    )
    register_adapter(adapter)


@pytest.mark.asyncio
async def test_cli_agent_complete_success() -> None:
    client = CLIAgentClient(model="fake_cli_test")

    response = await client.complete(
        system=[TextBlock(text="You are a helpful assistant.")],
        messages=[Message(role="user", blocks=[TextBlock(text="Say hello")])],
    )

    assert response.text == "hello from fake cli"
    assert response.usage.input_tokens == 5
    assert response.usage.output_tokens == 3
    assert response.raw["adapter"] == "fake_cli_test"
    assert response.stop_reason == "end_turn"


@pytest.mark.asyncio
async def test_cli_agent_force_tool_unsupported() -> None:
    client = CLIAgentClient(model="fake_cli_test")

    with pytest.raises(LLMCapabilityError) as exc_info:
        await client.complete(
            system=[],
            messages=[Message(role="user", blocks=[TextBlock(text="test")])],
            force_tool="some_tool",
        )

    assert "does not support forced tool use" in str(exc_info.value)


def test_resolve_launch_windows_cmd() -> None:
    if sys.platform != "win32":
        pytest.skip("Windows-specific shim resolution test")

    with patch("shutil.which", return_value=r"C:\Users\test\AppData\Roaming\npm\claude.cmd"):
        launch = _resolve_launch("claude")
        assert launch == ["cmd.exe", "/c", r"C:\Users\test\AppData\Roaming\npm\claude.cmd"]


def test_gemini_adapter_resolution() -> None:
    from services.llm.providers.cli_agent import (
        _gemini_argv,
        _gemini_parse,
        _resolve_adapter_and_model,
    )

    adapter, model = _resolve_adapter_and_model("gemini")
    assert adapter.key == "gemini"
    assert model == "gemini"

    adapter2, model2 = _resolve_adapter_and_model("gemini-2.0-flash")
    assert adapter2.key == "gemini"
    assert model2 == "gemini-2.0-flash"

    argv = _gemini_argv("hello world", "gemini-2.0-flash", [])
    assert argv == ["-p", "hello world", "--model", "gemini-2.0-flash"]

    text, usage, payload = _gemini_parse('{"response": "Hello from Gemini"}', "")
    assert text == "Hello from Gemini"

