# Gemini Task — Wire the `cli_agent` LLM Provider

> A new LLM provider file has been added at `services/llm/providers/cli_agent.py` that shells out to locally installed AI CLIs (Claude Code CLI, Gemini CLI, OpenAI Codex CLI, Charmbracelet Crush, Sourcegraph Amp, Qwen Code CLI). This document is the complete instruction set for wiring it into the existing plumbing.

**Paste everything in the fenced block below into Gemini.**

---

```
Wire a new "cli_agent" LLM provider into EmiMind. The provider file is already
written at `services/llm/providers/cli_agent.py` — DO NOT rewrite it. Only wire
it into the existing plumbing, add its price rows, add its test, and update
`.env.example`. Do not touch any file under `tasks/` or the appendices.

Context you need to read first:
  - services/llm/providers/cli_agent.py   (the new provider — read to understand its shape)
  - services/llm/types.py                 (LLMClient protocol)
  - services/llm/factory.py               (where to register the class)
  - services/llm/pricing.py               (add zero-cost rows for CLI adapters)
  - services/shared/config.py             (extend the provider Literal on RoleConfig + Settings)
  - services/llm/providers/openai_compat.py  (mirror its registration style)

# ============================================================================
# TASK 1 — Extend the provider Literal
# ============================================================================
File: services/shared/config.py

Everywhere the type Literal["anthropic","openai","openai_compat","google","fake"]
appears (RoleConfig.provider, Settings.llm_reasoner_provider,
Settings.llm_utility_provider, and the local `p` variable if annotated),
add "cli_agent" as an additional option. Do not remove existing options.

# ============================================================================
# TASK 2 — Register the client in the factory
# ============================================================================
File: services/llm/factory.py

Add:
    from services.llm.providers.cli_agent import CLIAgentClient
into the imports, and:
    "cli_agent": CLIAgentClient,
into the _REGISTRY dict. Keep alphabetical-ish order consistent with the
existing style.

# ============================================================================
# TASK 3 — Add price rows so cost accounting doesn't return None
# ============================================================================
File: services/llm/pricing.py

CLI agents don't expose per-token pricing (the CLI handles billing on its own
account), but we still want the cost_usd field populated with 0.0 rather than
None so metrics dashboards don't drop the rows. Add these entries to
PRICE_PER_MTOK:

    ("cli_agent", "claude"): PriceRow(input_per_mtok=0.0, output_per_mtok=0.0),
    ("cli_agent", "gemini"): PriceRow(input_per_mtok=0.0, output_per_mtok=0.0),
    ("cli_agent", "codex"):  PriceRow(input_per_mtok=0.0, output_per_mtok=0.0),
    ("cli_agent", "crush"):  PriceRow(input_per_mtok=0.0, output_per_mtok=0.0),
    ("cli_agent", "amp"):    PriceRow(input_per_mtok=0.0, output_per_mtok=0.0),
    ("cli_agent", "qwen"):   PriceRow(input_per_mtok=0.0, output_per_mtok=0.0),

# ============================================================================
# TASK 4 — Have the client call cost accounting
# ============================================================================
File: services/llm/providers/cli_agent.py

The provider I wrote does NOT populate usage.cost_usd from the pricing table
(it only picks up the total_cost_usd claude prints in its JSON). Add ONE line
at the end of CLIAgentClient.complete, immediately before the `return
LLMResponse(...)` call:

    if usage.cost_usd is None:
        usage.cost_usd = calculate_cost_usd(self.provider_id, self.model, usage)

And add the import at the top of the file:

    from services.llm.pricing import calculate_cost_usd

# ============================================================================
# TASK 5 — Extend `.env.example`
# ============================================================================
File: .env.example

In the LLM section, immediately after the existing OpenAI-compat examples,
append a new commented block:

    # ---- CLI agent (local AI CLIs — Claude Code, Gemini CLI, Codex, ...) ----
    # Uses a locally installed CLI binary (the CLI handles its own auth).
    # MODEL selects the adapter: claude | gemini | codex | crush | amp | qwen
    # BASE_URL is optional — set to the absolute path if the binary isn't on PATH.
    #
    # EMI_LLM_REASONER_PROVIDER=cli_agent
    # EMI_LLM_REASONER_MODEL=claude
    # EMI_LLM_REASONER_API_KEY=cli   # any non-empty string; unused, CLI has its own auth
    # EMI_LLM_REASONER_BASE_URL=
    # EMI_LLM_REASONER_TIMEOUT_S=120

Also, in services/shared/config.py's `llm_role` method, note that a non-empty
api_key is required to avoid the "fake" fallback path. Confirm that setting
EMI_LLM_REASONER_API_KEY=cli (or any non-mock string) routes to cli_agent
correctly — no code change needed there, just verify with a manual print.

# ============================================================================
# TASK 6 — Add a unit test
# ============================================================================
File: tests/unit/test_cli_agent.py  (new)

Write a test that:
  1. Registers a fake adapter whose default_binary is sys.executable and whose
     build_argv returns ["-c", <inline script>] that prints a claude-shaped
     JSON blob ({"result": "...", "usage": {"input_tokens": 5, "output_tokens": 3}}).
  2. Instantiates CLIAgentClient(model="fake_cli_test").
  3. Awaits .complete(...) with a trivial system+user message.
  4. Asserts response.text is the echoed prompt fragment.
  5. Asserts response.usage.input_tokens == 5 and output_tokens == 3.
  6. Asserts response.raw["adapter"] == "fake_cli_test".
  7. Second test case: assert that force_tool="anything" raises
     LLMCapabilityError.
  8. Third test case (skip on non-Windows): a fake adapter that resolves a .cmd
     shim path routes through cmd.exe /c — this only needs a structural check
     on _resolve_launch, not a full run.

Mark the tests `@pytest.mark.asyncio` where needed. Use `sys.executable` so the
test is cross-platform and does not require any CLI to be installed.

# ============================================================================
# TASK 7 — Verification (run and report)
# ============================================================================
Run and paste output:

  uv run ruff check services/llm services/shared tests/unit/test_cli_agent.py
  uv run mypy services/llm services/shared
  uv run pytest tests/unit/test_cli_agent.py -v
  uv run pytest tests/unit/test_pricing.py tests/unit/test_llm_types.py -v
  uv run python -c "from services.llm.factory import _REGISTRY; print(sorted(_REGISTRY))"

Expected results:
  - ruff: clean
  - mypy: clean
  - test_cli_agent.py: all pass
  - existing tests: still pass, no regressions
  - _REGISTRY print includes 'cli_agent'

# ============================================================================
# HARD CONSTRAINTS
# ============================================================================
  1. Do NOT modify files under tasks/ or the appendix-*.md files.
  2. Do NOT modify BLUEPRINT.md, TASKS.md, TASK_TRACKER.md, or README.md.
  3. Do NOT rewrite services/llm/providers/cli_agent.py — only make the
     one-line addition described in TASK 4.
  4. Do NOT rename anything. The provider key is "cli_agent" everywhere.
  5. If any verification step fails, stop and report the failure verbatim
     instead of "fixing" the test to make it pass.
```
