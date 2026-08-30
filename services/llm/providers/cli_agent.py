"""CLI-agent provider — shells out to a locally installed AI CLI.

Supports any CLI agent that accepts a prompt on the command line and prints its
answer on stdout: Claude Code CLI (`claude -p`), Gemini CLI (`gemini -p`), OpenAI
Codex CLI (`codex exec`), Charmbracelet Crush (`crush -p`), Sourcegraph Amp
(`amp -p`), Qwen Code CLI (`qwen -p`), etc.

Selection via env:
    EMI_LLM_<ROLE>_PROVIDER=cli_agent
    EMI_LLM_<ROLE>_MODEL=<adapter-key>          # 'claude' | 'gemini' | 'codex' | ...
    EMI_LLM_<ROLE>_BASE_URL=<binary-path>       # optional; overrides the default binary lookup

Design contract:
    - The CLI handles its own authentication (`claude login`, `gemini auth`, ...);
      this provider never touches API keys.
    - Prompts are passed as argv (never through a shell), so shell metacharacters
      inside the prompt are inert.
    - Structured tool use is unsupported — CLI agents don't expose a tool-call
      wire format. Callers that set `force_tool` get an `LLMCapabilityError`.

Extending: register a new adapter with `register_adapter(...)` before the factory
constructs the client (typical spot: `services/llm/__init__.py`, or a test).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

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

log = get_logger("llm.cli_agent")

ArgvBuilder = Callable[[str, str, list[str]], list[str]]
StdoutParser = Callable[[str, str], tuple[str, Usage, dict[str, Any] | None]]


@dataclass(frozen=True)
class CLIAdapter:
    """Per-CLI-agent binding: how to build argv, how to parse stdout, what it supports."""

    key: str
    default_binary: str
    build_argv: ArgvBuilder
    parse_stdout: StdoutParser
    capabilities: Capabilities


# --------------------------------------------------------------------------- #
# Adapters
# --------------------------------------------------------------------------- #


def _claude_argv(prompt: str, model: str, extra: list[str]) -> list[str]:
    argv = ["-p", prompt, "--output-format", "json"]
    if model and model not in ("claude", "default"):
        argv += ["--model", model]
    return argv + extra


def _claude_parse(stdout: str, stderr: str) -> tuple[str, Usage, dict[str, Any] | None]:
    """Parse `claude -p --output-format json` output.

    The last non-empty line is a JSON object with `result` and `usage`; earlier
    lines may be progress noise depending on version. Defends against both shapes.
    """
    payload = _last_json_object(stdout)
    if payload is None:
        return stdout.strip(), Usage(input_tokens=0, output_tokens=0), None

    text = payload.get("result") or payload.get("output") or ""
    if isinstance(text, list):
        text = "".join(b.get("text", "") for b in text if b.get("type") == "text")

    u = payload.get("usage") or {}
    usage = Usage(
        input_tokens=int(u.get("input_tokens", 0)),
        output_tokens=int(u.get("output_tokens", 0)),
        cache_read_tokens=int(u.get("cache_read_input_tokens", 0)),
        cache_write_tokens=int(u.get("cache_creation_input_tokens", 0)),
        cost_usd=payload.get("total_cost_usd"),
    )
    return str(text).strip(), usage, payload


def _gemini_argv(prompt: str, model: str, extra: list[str]) -> list[str]:
    argv = ["-p", prompt]
    if model and model not in ("gemini", "default"):
        argv += ["--model", model]
    return argv + extra


def _gemini_parse(stdout: str, stderr: str) -> tuple[str, Usage, dict[str, Any] | None]:
    """Gemini CLI emits plain text by default; autodetect JSON shape when present."""
    payload = _last_json_object(stdout)
    if payload is not None:
        text = payload.get("response") or payload.get("result") or ""
        return str(text).strip() or stdout.strip(), Usage(input_tokens=0, output_tokens=0), payload
    return stdout.strip(), Usage(input_tokens=0, output_tokens=0), None


def _codex_argv(prompt: str, model: str, extra: list[str]) -> list[str]:
    """OpenAI Codex CLI uses `codex exec <prompt>` for non-interactive runs."""
    argv = ["exec", prompt]
    if model and model not in ("codex", "default"):
        argv += ["--model", model]
    return argv + extra


def _generic_parse(stdout: str, stderr: str) -> tuple[str, Usage, dict[str, Any] | None]:
    return stdout.strip(), Usage(input_tokens=0, output_tokens=0), None


def _crush_argv(prompt: str, model: str, extra: list[str]) -> list[str]:
    argv = ["-p", prompt]
    if model and model not in ("crush", "default"):
        argv += ["-m", model]
    return argv + extra


def _amp_argv(prompt: str, model: str, extra: list[str]) -> list[str]:
    return ["-p", prompt, *extra]


def _qwen_argv(prompt: str, model: str, extra: list[str]) -> list[str]:
    argv = ["-p", prompt]
    if model and model not in ("qwen", "default"):
        argv += ["--model", model]
    return argv + extra


ADAPTERS: dict[str, CLIAdapter] = {
    "claude": CLIAdapter(
        key="claude",
        default_binary="claude",
        build_argv=_claude_argv,
        parse_stdout=_claude_parse,
        capabilities=Capabilities(
            prompt_caching=True,
            tool_use=False,
            structured_json=True,
            vision=True,
            max_context_tokens=200_000,
            supports_system_message=True,
        ),
    ),
    "gemini": CLIAdapter(
        key="gemini",
        default_binary="gemini",
        build_argv=_gemini_argv,
        parse_stdout=_gemini_parse,
        capabilities=Capabilities(
            prompt_caching=True,
            tool_use=False,
            structured_json=False,
            vision=True,
            max_context_tokens=1_000_000,
            supports_system_message=True,
        ),
    ),
    "codex": CLIAdapter(
        key="codex",
        default_binary="codex",
        build_argv=_codex_argv,
        parse_stdout=_generic_parse,
        capabilities=Capabilities(
            prompt_caching=False,
            tool_use=False,
            structured_json=False,
            vision=False,
            max_context_tokens=128_000,
            supports_system_message=True,
        ),
    ),
    "crush": CLIAdapter(
        key="crush",
        default_binary="crush",
        build_argv=_crush_argv,
        parse_stdout=_generic_parse,
        capabilities=Capabilities(
            prompt_caching=False,
            tool_use=False,
            structured_json=False,
            vision=False,
            max_context_tokens=128_000,
            supports_system_message=True,
        ),
    ),
    "amp": CLIAdapter(
        key="amp",
        default_binary="amp",
        build_argv=_amp_argv,
        parse_stdout=_generic_parse,
        capabilities=Capabilities(
            prompt_caching=False,
            tool_use=False,
            structured_json=False,
            vision=False,
            max_context_tokens=128_000,
            supports_system_message=True,
        ),
    ),
    "qwen": CLIAdapter(
        key="qwen",
        default_binary="qwen",
        build_argv=_qwen_argv,
        parse_stdout=_generic_parse,
        capabilities=Capabilities(
            prompt_caching=False,
            tool_use=False,
            structured_json=False,
            vision=False,
            max_context_tokens=128_000,
            supports_system_message=True,
        ),
    ),
}


def register_adapter(adapter: CLIAdapter) -> None:
    """Register a new CLI adapter (tests, plugins, user extensions)."""
    ADAPTERS[adapter.key] = adapter


def available_adapters() -> list[str]:
    return sorted(ADAPTERS)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _last_json_object(stdout: str) -> dict[str, Any] | None:
    """Return the last standalone JSON object printed on stdout, or None."""
    stripped = stdout.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            parsed = json.loads(stripped)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass
    for raw_line in reversed(stdout.splitlines()):
        line = raw_line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue
    return None


def _flatten_prompt(system: list[TextBlock], messages: list[Message]) -> str:
    """CLI agents take a single string; flatten our block model deterministically."""
    parts: list[str] = []
    system_text = "\n\n".join(b.text for b in system if isinstance(b, TextBlock) and b.text)
    if system_text:
        parts.append(f"[SYSTEM]\n{system_text}")
    for msg in messages:
        chunks: list[str] = []
        for block in msg.blocks:
            if isinstance(block, TextBlock):
                if block.text:
                    chunks.append(block.text)
            elif isinstance(block, ToolResultBlock):
                chunks.append(f"[tool_result:{block.tool_call_id}]\n{block.content}")
        if chunks:
            parts.append(f"[{msg.role.upper()}]\n" + "\n".join(chunks))
    return "\n\n".join(parts).strip()


def _resolve_launch(binary: str) -> list[str]:
    """Resolve a binary to a launch argv prefix, handling Windows shim types."""
    resolved = shutil.which(binary)
    if resolved is None:
        raise LLMProviderError(
            f"CLI binary '{binary}' not found on PATH. "
            "Install the corresponding agent or set EMI_LLM_<ROLE>_BASE_URL "
            "to an absolute path."
        )
    if sys.platform == "win32":
        lower = resolved.lower()
        if lower.endswith((".cmd", ".bat")):
            # If it's a batch shim, check if it points to a direct .exe inside node_modules
            parent_dir = os.path.dirname(resolved)
            try:
                with open(resolved, encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                match = re.search(r'"(%~?dp0%?\\[^"]+\.exe)"', content, re.IGNORECASE)
                if match:
                    raw_rel = match.group(1).replace("%dp0%\\", "").replace("%~dp0", "").strip("\\")
                    abs_target = os.path.normpath(os.path.join(parent_dir, raw_rel))
                    if os.path.exists(abs_target):
                        return [abs_target]
            except Exception as e:
                log.debug("Failed to inspect batch shim target", path=resolved, error=str(e))
            return ["cmd.exe", "/c", resolved]
        if lower.endswith(".ps1"):
            return ["powershell.exe", "-NoProfile", "-File", resolved]
    return [resolved]


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #


def _resolve_adapter_and_model(model_spec: str) -> tuple[CLIAdapter, str]:
    """Resolves an adapter and specific sub-model from a model spec string.

    Supports:
      - Plain adapter key: 'claude', 'gemini', 'codex', 'crush', 'amp', 'qwen'
      - Namespaced spec: 'claude:opus', 'claude:claude-3-5-haiku', 'gemini:gemini-2.0-flash'
      - Direct model names: 'opus', 'sonnet', 'haiku', 'claude-3-7-sonnet-20250219', 'gemini-1.5-pro', etc.
    """
    if ":" in model_spec:
        adapter_key, sub_model = model_spec.split(":", 1)
        adapter = ADAPTERS.get(adapter_key)
        if adapter:
            return adapter, sub_model

    if model_spec in ADAPTERS:
        return ADAPTERS[model_spec], model_spec

    lower = model_spec.lower()
    if lower in ("opus", "sonnet", "haiku") or lower.startswith("claude"):
        return ADAPTERS["claude"], model_spec
    if lower.startswith("gemini"):
        return ADAPTERS["gemini"], model_spec
    if lower.startswith(("gpt", "o1", "o3", "codex")):
        return ADAPTERS["codex"], model_spec
    if lower.startswith("qwen"):
        return ADAPTERS["qwen"], model_spec
    if lower.startswith("crush"):
        return ADAPTERS["crush"], model_spec

    raise LLMProviderError(
        f"Unknown CLI adapter or model '{model_spec}'. Available adapters: {available_adapters()}. "
        "You can specify e.g. 'opus', 'claude', 'claude:opus', 'claude-3-5-haiku', 'gemini', etc."
    )


class CLIAgentClient(LLMClient):
    """LLMClient backed by a locally installed AI CLI agent."""

    provider_id = "cli_agent"

    def __init__(
        self,
        model: str = "claude",
        api_key: str = "",
        base_url: str | None = None,
        max_output_tokens: int = 1024,
        timeout_s: int = 120,
    ) -> None:
        adapter, sub_model = _resolve_adapter_and_model(model)

        self.model = sub_model
        self._adapter = adapter
        self._binary_launch = _resolve_launch(base_url or adapter.default_binary)
        self._extra_args = shlex.split(os.environ.get("EMI_LLM_CLI_EXTRA_ARGS", ""))
        self.default_max_output_tokens = max_output_tokens
        self.timeout_s = timeout_s
        self.capabilities = adapter.capabilities

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
            raise LLMCapabilityError(
                f"CLI adapter '{self._adapter.key}' does not support forced tool use. "
                "Use an HTTP provider (anthropic / openai / openai_compat) for structured outputs."
            )

        prompt = _flatten_prompt(system, messages)
        argv = [
            *self._binary_launch,
            *self._adapter.build_argv(prompt, self.model, self._extra_args),
        ]

        log = get_logger("llm.cli_agent")
        log.info(
            "Executing LLM prompt",
            provider=self.provider_id,
            adapter=self._adapter.key,
            model=self.model,
            prompt=prompt,
        )

        started = time.monotonic()
        try:
            res = await asyncio.to_thread(
                subprocess.run,
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.timeout_s,
                env=os.environ.copy(),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise LLMProviderError(
                f"{self._adapter.key} CLI timed out after {self.timeout_s}s"
            ) from exc
        except FileNotFoundError as exc:
            raise LLMProviderError(f"Cannot launch CLI agent {argv[0]!r}: {exc}") from exc
        except OSError as exc:
            raise LLMProviderError(f"OS error launching CLI agent: {exc}") from exc

        elapsed_ms = int((time.monotonic() - started) * 1000)
        stdout = res.stdout.decode("utf-8", errors="replace")
        stderr = res.stderr.decode("utf-8", errors="replace")

        if res.returncode != 0:
            raise LLMProviderError(
                f"{self._adapter.key} CLI exited {res.returncode} after {elapsed_ms}ms. "
                f"stderr[:2000]={stderr[:2000]!r}"
            )

        text, usage, provider_raw = self._adapter.parse_stdout(stdout, stderr)
        tool_calls: list[ToolCall] = []  # CLI agents don't emit structured tool calls

        if usage.cost_usd is None:
            usage.cost_usd = calculate_cost_usd(self.provider_id, self.model, usage)

        log.info(
            "Received LLM response",
            provider=self.provider_id,
            model=self.model,
            elapsed_ms=elapsed_ms,
            response=text,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )

        return LLMResponse(
            text=text,
            stop_reason="end_turn",
            tool_calls=tool_calls,
            usage=usage,
            raw={
                "adapter": self._adapter.key,
                "argv": argv,
                "elapsed_ms": elapsed_ms,
                "provider_raw": provider_raw,
            },
        )
