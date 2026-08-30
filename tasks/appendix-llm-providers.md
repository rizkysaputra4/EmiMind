# Appendix — LLM Provider Abstraction

> The blueprint names Claude Sonnet 4.6 / Haiku 4.5. In practice, the founder wants to swap providers over time — OpenAI (ChatGPT), Moonshot (Kimi), DeepSeek, and OpenAI-compatible endpoints (Together, Groq, Fireworks) all belong in the same slot. This appendix defines the abstraction so no calling code has to change when a provider changes.

Referenced by:
- `tasks/00-conventions.md` § 8 (LLM rules)
- `tasks/01-M1-skeleton.md` (env vars)
- `tasks/04-M4-retrieval-chat.md` § 1 (LLM client)
- `tasks/03-M3-derived-narrative.md` (translator + profile summary)
- `tasks/05-M5-kg-guidance.md` (guidance miner + causal linker)
- `tasks/06-M6-screener-technical.md` (NL → DSL parser)

---

## 1. Design goals

1. **Any calling module imports a `Protocol`, never a concrete provider SDK.** The provider SDK lives in exactly one place per provider.
2. **Two roles, not one:** `reasoner` (heavy, expensive, high-quality) and `utility` (cheap, fast — classifier, translator, summarizer, DSL parser).
3. **Each role is independently configurable** — you can run reasoner on Claude and utility on DeepSeek, or vice-versa, or both on the same provider.
4. **Providers advertise capabilities** — prompt caching, tool use, structured JSON output, vision. Calling code gracefully degrades when a feature is missing.
5. **Token accounting is normalized** across providers so cost and budget metrics are provider-agnostic.
6. **Adding a new provider is a single file** under `services/llm/providers/`, plus one line in the factory.

---

## 2. Roles and env config

Two role slots. Each is picked independently:

```dotenv
# Reasoner (chat generation, causal linker, profile summary) --------------------
EMI_LLM_REASONER_PROVIDER=anthropic           # anthropic | openai | openai_compat | google
EMI_LLM_REASONER_MODEL=claude-sonnet-4-6
EMI_LLM_REASONER_API_KEY=sk-ant-...
EMI_LLM_REASONER_BASE_URL=                    # only for openai_compat (Kimi, DeepSeek, Together, Groq...)
EMI_LLM_REASONER_MAX_OUTPUT_TOKENS=1024
EMI_LLM_REASONER_TIMEOUT_S=30

# Utility (classifier, translator, rolling summary, screener NL parser) --------
EMI_LLM_UTILITY_PROVIDER=anthropic
EMI_LLM_UTILITY_MODEL=claude-haiku-4-5-20251001
EMI_LLM_UTILITY_API_KEY=sk-ant-...
EMI_LLM_UTILITY_BASE_URL=
EMI_LLM_UTILITY_MAX_OUTPUT_TOKENS=512
EMI_LLM_UTILITY_TIMEOUT_S=15

# Judge (Suite C evaluator) — optional, defaults to reasoner ------------------
EMI_LLM_JUDGE_PROVIDER=
EMI_LLM_JUDGE_MODEL=
EMI_LLM_JUDGE_API_KEY=
EMI_LLM_JUDGE_BASE_URL=
```

**Example combinations:**

| Setup | Reasoner | Utility |
|---|---|---|
| Anthropic-only (blueprint default) | `anthropic` / `claude-sonnet-4-6` | `anthropic` / `claude-haiku-4-5-20251001` |
| OpenAI-only | `openai` / `gpt-5` | `openai` / `gpt-4o-mini` |
| Mixed: Claude reasoning, DeepSeek utility | `anthropic` / `claude-sonnet-4-6` | `openai_compat` / `deepseek-chat` @ `https://api.deepseek.com/v1` |
| Kimi + Moonshot | `openai_compat` / `moonshot-v1-128k` @ `https://api.moonshot.cn/v1` | same |
| Local Ollama | `openai_compat` / `llama3.1:70b` @ `http://localhost:11434/v1` | same |

Never hardcode a model name outside `services/shared/config.py`.

---

## 3. Provider-neutral interfaces

**File:** `services/llm/types.py`

```python
from typing import Literal, Any, Protocol
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
    provider_id: str  # 'anthropic' | 'openai' | ...
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
```

---

## 4. Provider implementations

**Directory:** `services/llm/providers/`

One file per provider. Each implements the `LLMClient` Protocol.

### 4.1 Anthropic — `services/llm/providers/anthropic.py`
- Uses `anthropic` SDK.
- Maps `cache_hint=True` blocks to `{"type":"text","text":..., "cache_control":{"type":"ephemeral"}}`.
- Maps `force_tool="name"` to `tool_choice={"type":"tool","name":"..."}`.
- Capabilities: caching ✅, tool_use ✅, structured_json ✅ (via tool_use), vision ✅.

### 4.2 OpenAI — `services/llm/providers/openai.py`
- Uses `openai` SDK.
- Merges system blocks into the leading `role="system"` message. `cache_hint` is a no-op (OpenAI caches implicitly on identical prefixes).
- Maps tools → `tools=[{"type":"function","function":{"name":..., "description":..., "parameters":...}}]`.
- Maps `force_tool` → `tool_choice={"type":"function","function":{"name":...}}`.
- Response `tool_calls` are demarshaled to `ToolCall`.
- Capabilities: caching ✅ (implicit), tool_use ✅, structured_json ✅ (json mode + tool use), vision ✅.

### 4.3 OpenAI-compatible — `services/llm/providers/openai_compat.py`
- Same SDK (`openai.OpenAI(base_url=..., api_key=...)`), but hits DeepSeek, Moonshot (Kimi), Together, Fireworks, Groq, or a local Ollama with the OpenAI-compat endpoint.
- Capabilities are **capability-flagged per model** via a small table:

```python
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
    # fallback default assumes tool_use + system message only
}
```

When a requested capability is unavailable (e.g. `deepseek-reasoner` + tool use), the client raises `LLMCapabilityError` with a clear message pointing at env config.

### 4.4 Google — `services/llm/providers/google.py` (optional M7+)
- Uses `google-genai` SDK.
- Left as a stub in M4; wire fully when the founder needs it.

---

## 5. Factory + registry

**File:** `services/llm/factory.py`

```python
from functools import lru_cache
from services.shared.config import get_settings
from services.llm.providers.anthropic import AnthropicClient
from services.llm.providers.openai import OpenAIClient
from services.llm.providers.openai_compat import OpenAICompatClient
# from services.llm.providers.google import GoogleClient   # M7+

_REGISTRY = {
    "anthropic": AnthropicClient,
    "openai": OpenAIClient,
    "openai_compat": OpenAICompatClient,
    # "google":      GoogleClient,
}


@lru_cache
def get_llm(role: Literal["reasoner", "utility", "judge"]) -> LLMClient:
    s = get_settings()
    cfg = s.llm_role(role)  # returns a RoleConfig with provider/model/api_key/base_url
    cls = _REGISTRY[cfg.provider]
    return cls(
        model=cfg.model,
        api_key=cfg.api_key.get_secret_value(),
        base_url=cfg.base_url,
        max_output_tokens=cfg.max_output_tokens,
        timeout_s=cfg.timeout_s,
    )
```

**Rule:** every caller does `client = get_llm("reasoner")` or `get_llm("utility")`. **Nothing else knows a provider exists.**

---

## 6. Settings model

**File:** `services/shared/config.py` (add to the existing `Settings`)

```python
class RoleConfig(BaseModel):
    provider: Literal["anthropic", "openai", "openai_compat", "google"]
    model: str
    api_key: SecretStr
    base_url: str | None = None
    max_output_tokens: int = 1024
    timeout_s: int = 30


class Settings(BaseSettings):
    # ... other fields ...

    llm_reasoner_provider: str = "anthropic"
    llm_reasoner_model: str = "claude-sonnet-4-6"
    llm_reasoner_api_key: SecretStr
    llm_reasoner_base_url: str | None = None
    llm_reasoner_max_output_tokens: int = 1024
    llm_reasoner_timeout_s: int = 30

    llm_utility_provider: str = "anthropic"
    llm_utility_model: str = "claude-haiku-4-5-20251001"
    llm_utility_api_key: SecretStr
    llm_utility_base_url: str | None = None
    llm_utility_max_output_tokens: int = 512
    llm_utility_timeout_s: int = 15

    llm_judge_provider: str | None = None
    llm_judge_model: str | None = None
    llm_judge_api_key: SecretStr | None = None
    llm_judge_base_url: str | None = None

    def llm_role(self, role: Literal["reasoner", "utility", "judge"]) -> RoleConfig:
        if role == "judge" and not self.llm_judge_provider:
            return self.llm_role("reasoner")
        p = getattr(self, f"llm_{role}_provider")
        return RoleConfig(
            provider=p,
            model=getattr(self, f"llm_{role}_model"),
            api_key=getattr(self, f"llm_{role}_api_key"),
            base_url=getattr(self, f"llm_{role}_base_url"),
            max_output_tokens=getattr(self, f"llm_{role}_max_output_tokens", 1024),
            timeout_s=getattr(self, f"llm_{role}_timeout_s", 30),
        )
```

**Retire** the previous `EMI_ANTHROPIC_API_KEY`, `EMI_MODEL_REASONER`, `EMI_MODEL_UTILITY`. Migrate `.env` accordingly (see the updated `.env.example` in `tasks/01-M1-skeleton.md`).

---

## 7. Provider-neutral behavior for cross-cutting features

### Prompt caching
- Callers set `TextBlock.cache_hint=True` on the system prompt block, the tool schema block, and the L6 frame block.
- Providers that support explicit caching (Anthropic) use it. Providers that cache implicitly (OpenAI) ignore the hint. Providers with no caching skip it — cost model still works, just less efficient.

### Tool use (structured outputs)
- Callers always define tools via `ToolDef` with JSONSchema.
- To force structured output (classifier, guidance miner, screener parser), call `complete(..., force_tool="<name>")`.
- The provider is responsible for shaping the request; the response comes back as `ToolCall.arguments` (already validated by the caller via a Pydantic model).
- If a provider doesn't support tool use, the client raises `LLMCapabilityError`. The caller may either fall back to a "return JSON only" prompt (utility calls only) or refuse.

### Token accounting
- Every provider maps its usage payload into the shared `Usage` model.
- `cost_usd` is populated by a small pricing table `services/llm/pricing.py` (per-provider, per-model, updated as needed). Missing entries → `None`; metrics simply skip cost aggregation.

### Fake client
- `services/llm/fakes.py` — `FakeLLMClient` implements `LLMClient` and replays canned responses keyed on `hash(system + messages + tools)`. Used by all unit tests and the offline eval mode.

---

## 8. Calling-site rules

Anywhere that used to say "call Anthropic":

```python
# BEFORE (anti-pattern):
resp = await anthropic_client.messages.create(model="claude-sonnet-4-6", ...)

# AFTER:
from services.llm.factory import get_llm
client = get_llm("reasoner")
resp = await client.complete(
    system=[TextBlock(text=SYSTEM_PROMPT, cache_hint=True)],
    messages=[Message(role="user", blocks=[TextBlock(text=user_msg)])],
    tools=TOOL_DEFS,
    max_output_tokens=1024,
)
```

Modules using this pattern:
- `services/retrieval/chat.py` → `get_llm("reasoner")`
- `services/retrieval/classifier.py` → `get_llm("utility")`
- `services/retrieval/summarizer.py` → `get_llm("utility")`
- `services/narrative/translator.py` → `get_llm("utility")`
- `services/kg/guidance_miner.py` (LLM fallback) → `get_llm("reasoner")`
- `services/kg/causal_linker.py` → `get_llm("reasoner")`
- `services/ingest/tasks/refresh_profile.py` → `get_llm("reasoner")`
- `services/screener/parser.py` → `get_llm("utility")`
- `eval/suite_c.py` (judge) → `get_llm("judge")`

**Grep hygiene:** `grep -rn "from anthropic" services/ eval/` should return matches only in `services/llm/providers/anthropic.py`. Same for `from openai`, `from google.genai`, etc.

---

## 9. Testing across providers

Add `tests/integration/test_llm_provider_matrix.py` gated behind env flags:

- For each of `EMI_TEST_PROVIDERS` (comma-separated), instantiate the client, run a tiny "return the string OK via a tool call named `echo`" prompt, assert normalized `LLMResponse` shape.
- Marked `@pytest.mark.provider`; not run in default CI. Ship a nightly job or a founder-manual run.

This guards against regressions when a provider bumps their SDK or changes a shape.

---

## 10. Documentation notes

- Update `README.md` "Environment" section to list the new `EMI_LLM_*` variables and show two example setups (Anthropic + Anthropic, Claude + DeepSeek).
- Add a short "Switching providers" runbook in `docs/runbook.md` (M7) covering: swap env → restart services → run Suite A + B to catch quality regressions.
