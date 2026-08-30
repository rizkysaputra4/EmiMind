# 00 — Conventions & Architecture Rules

> **Read this before writing any code.** Every task in every milestone assumes these rules.

The blueprint's north star is:
> **Database calculates reality → Memory stores context → Retrieval selects evidence → LLM reasons over evidence → User gets a challengeable, cited answer.**

These conventions exist to protect that north star as the codebase grows. Follow them literally. Do not "improve" them mid-task; if you think a rule is wrong, stop and raise it, do not silently deviate.

---

## 1. Repository layout (top level)

```
EmiMind/
├── BLUEPRINT.md              # design source of truth (do not edit during implementation)
├── TASKS.md                  # task index
├── README.md                 # dev quickstart (see M1)
├── .env.example              # every configurable value, with comments
├── .gitignore
├── docker-compose.yml        # postgres + minio + redis for local dev
├── pyproject.toml            # single Python project, uv-managed
├── ruff.toml
├── mypy.ini                  # or pyrightconfig.json
├── Makefile                  # dev shortcuts: make up, make migrate, make test
│
├── tasks/                    # this folder — implementation task lists
│
├── db/
│   ├── schema/               # numbered SQL migrations, forward-only
│   └── seeds/                # concept_map CSVs, peer_groups CSVs
│
├── services/                 # Python monorepo (single venv, shared code)
│   ├── shared/               # config, db pool, minio, redis, logging, types
│   ├── api/                  # FastAPI
│   ├── ingest/               # arq workers + orchestration
│   ├── extraction/           # pure functions used by ingest (pdf, tables, xbrl, ocr)
│   ├── derive/               # metric recipe registry
│   ├── narrative/            # chunking, embedding, translation, reranking
│   ├── retrieval/            # classifier, planner, budgeter, prompt assembler
│   ├── kg/                   # guidance_miner, actual_matcher, causal_linker
│   ├── market/               # yfinance_ingest, technical_engine, regime_rules
│   ├── screener/             # dsl, compiler, executor, parser (NL→DSL)
│   └── llm/                  # provider-neutral LLM abstraction, provider adapters, system prompt, tools
│
├── eval/                     # golden sets + suite runners
├── scripts/                  # one-off backfill / seed scripts
├── tests/                    # pytest unit + integration tests
└── web/                      # Next.js chat UI + evidence panel
```

**Rules:**
- **Do not create top-level folders not on this list.** Utility scripts go in `scripts/`, tests in `tests/`, ad-hoc notebooks nowhere (they don't belong in the repo).
- **Every folder under `services/` has an `__init__.py`.** No implicit namespace packages.
- **Never move a file after M1 without updating `TASKS.md`.** Task IDs reference paths.

---

## 2. Dependency direction (the single most important rule)

```
                  ┌───────────────┐
                  │  services/api │  (FastAPI routers — thin, no logic)
                  └───────┬───────┘
                          ▼
      ┌────────┬──────────┴──────────┬───────────┬──────────┬──────────┐
      │ ingest │ retrieval           │  screener │  derive  │   kg     │
      │  (arq) │  (chat plan/exec)   │  (SQL)    │ (recipes)│ (miners) │
      └────┬───┴──────────┬──────────┴─────┬─────┴────┬─────┴────┬─────┘
           ▼              ▼                ▼          ▼          ▼
      extraction     narrative           llm        (shared: config, db, minio, redis, types, logging)
           │              │                │          ▲
           └──────────────┴────────────────┴──────────┘
```

- `services/api` may import from **any** service module.
- Service modules (`ingest`, `retrieval`, `screener`, `derive`, `kg`) may import from `extraction`, `narrative`, `llm`, and `shared` — but **never from each other**, and **never from `api`**.
- `extraction`, `narrative`, `llm` may only import from `shared`.
- `shared` imports nothing from the rest of the project.

**If you find yourself wanting to reverse an arrow, extract the shared thing into `services/shared/` first.** No exceptions. Any deviation must be raised and approved.

---

## 3. Coding standards (Python)

**Version:** Python 3.11+. Use `from __future__ import annotations` at the top of every module.

**Formatter/linter:** `ruff` (config in `ruff.toml`). Line length 100. Enable rules: `E, F, I, N, B, UP, PL, RUF, T20` (T20 = no `print` in library code).

**Type checker:** `mypy --strict` or `pyright` in strict mode on `services/` and `eval/`.

**Async everywhere on the hot path.** FastAPI, DB, HTTP, LLM calls, arq tasks — all `async def`. The one exception is CPU-bound extraction code (pdfplumber, Camelot, Tesseract, BGE-M3 inference) — run it in a thread pool via `asyncio.to_thread` or `anyio.to_thread.run_sync`.

**Pydantic v2 at every module boundary.** Public functions in a module accept and return Pydantic models or scalars, never plain `dict`. Internal helpers may use dicts.

**Exceptions.** Raise domain-specific exceptions from `services/shared/errors.py`:
- `ExtractionError`, `NormalizationError`, `RetrievalError`, `LLMError`, `BudgetExceededError`, `ProvenanceError`.
- Never `except Exception:` silently. Log the exception with structured fields and re-raise, or convert to a domain exception at the module boundary.

**Logging.** `structlog` configured in `services/shared/logging.py`. Every log line carries `service`, `worker` or `route`, `doc_id` / `session_id` / `ticker` when applicable. Never `print`.

**No globals.** Config, DB pool, MinIO client, Redis client, LLM client are all constructed once in `services/shared/*` and passed via FastAPI dependency injection or arq context — never imported as a global singleton.

**Docstrings.** One-line summary only, unless the function is genuinely non-obvious. Long docstrings rot. If the function is complex enough to need one, first ask whether it should be split.

**Comments.** Default: no comments. Only add a comment when the WHY is non-obvious (a workaround for a bug, a subtle invariant). Do not narrate the WHAT — names carry that.

**File length.** Aim for <300 lines per module. If it grows past 400, split.

---

## 4. Coding standards (TypeScript / Next.js)

**Version:** Node 20 LTS, Next.js 14+ App Router, TypeScript 5+ strict mode.

**UI kit:** shadcn/ui + Tailwind. No other component library.

**State:** TanStack Query for server state; React state for local UI. **No Redux, no Zustand** unless a task explicitly says so.

**API calls go through `web/lib/api.ts`.** Never `fetch()` directly from a component.

**PDF rendering:** `react-pdf` with `pdfjs-dist`. See M4 for exact version.

**No `any`.** Every response type is defined in `web/lib/types.ts`, generated from the FastAPI OpenAPI schema (see M1 for the tooling).

**Component files** are `PascalCase.tsx`; hooks are `useSomething.ts`; utility modules are `kebab-case.ts`.

---

## 5. Configuration

All configuration lives in `services/shared/config.py` using `pydantic-settings`. Read from environment variables. Values documented in `.env.example`.

**Namespacing:** every env var is prefixed with `EMI_`. Examples:
- `EMI_POSTGRES_DSN`
- `EMI_MINIO_ENDPOINT`
- `EMI_MINIO_ACCESS_KEY`
- `EMI_MINIO_SECRET_KEY`
- `EMI_REDIS_URL`
- `EMI_ANTHROPIC_API_KEY`
- `EMI_EMBEDDING_MODEL_PATH`
- `EMI_LOG_LEVEL`

**Rules:**
- Never read `os.environ` outside `services/shared/config.py`.
- Never hardcode a URL, port, table name, or bucket name in application code.
- Every env var referenced in code must exist in `.env.example`.

---

## 6. Database rules

**Migrations are forward-only.** File naming: `db/schema/NNN_short_name.sql`, `NNN` monotonically increasing, zero-padded to 3 digits. Never edit a merged migration; write a new one.

**Every table has:**
- A primary key (`bigserial` for hot tables, `uuid` for `documents` and session tables).
- A `created_at timestamptz DEFAULT now()` column unless it's genuinely stateless.

**Every fact-carrying row has provenance columns:** `source_doc_id`, `source_page`, `source_bbox` (or a `source_ref jsonb` that contains those). No provenance = the row cannot be shown to the LLM.

**All queries are parameterized.** No `f"SELECT ... {ticker}"` — ever. Use asyncpg / SQLAlchemy Core parameter binding. This is a security requirement.

**All DB access from application code goes through helpers in `services/shared/db.py`.** Routers/services do not open pools, do not manage transactions. Transactions are opened via `async with db.tx() as conn:`.

**Indexes named explicitly** where they're non-trivial: `CREATE INDEX ix_financial_facts_ticker_period ON ...`. Postgres auto-names are fine for GIN/HNSW indexes with one column.

**Long-running or LLM-adjacent queries have a `statement_timeout`** set at the connection scope, e.g. 5s for retrieval, 30s for backfill scripts.

---

## 7. Ingestion / worker rules

**Every worker is idempotent.** The uniqueness key for "already done" is `(doc_hash, worker_name, worker_version)`. Record it in `worker_runs`:

```sql
CREATE TABLE worker_runs (
  doc_hash        text NOT NULL,
  worker_name     text NOT NULL,
  worker_version  text NOT NULL,
  status          text NOT NULL,      -- 'ok' | 'failed'
  error           text,
  started_at      timestamptz DEFAULT now(),
  finished_at     timestamptz,
  PRIMARY KEY (doc_hash, worker_name, worker_version)
);
```

A worker's first action is `SELECT ... FROM worker_runs WHERE ...` — if `ok`, skip. If `failed` and retry budget exhausted, skip and page a human.

**Every worker declares a version constant:** `WORKER_VERSION = "1.0"`. Bumping it forces a re-run on next enqueue.

**No LLM calls in the hot path of ingestion parsing.** LLM is only allowed in: causal linker, translator, profile summary refresh. Extraction/normalization are deterministic.

**Rows written with `extraction_conf < 0.7` are flagged** `needs_review = true` at the caller side, and excluded from LLM retrieval until reviewed. See M2.

---

## 8. LLM rules

**Provider-neutral by design.** The blueprint names Claude, but the codebase must let the founder swap providers (OpenAI/ChatGPT, Kimi, DeepSeek, local Ollama, Google) without touching any calling code. Details in [`tasks/appendix-llm-providers.md`](appendix-llm-providers.md).

- **Only `services/llm/providers/<name>.py` may import a provider SDK.** Every other module imports `services.llm.factory.get_llm(role)` and calls the provider-neutral `LLMClient` Protocol from `services/llm/types.py`.
- **Two role slots** — `reasoner` (chat generation, causal linker, profile summary) and `utility` (classifier, translator, summarizer, DSL parser). A third optional `judge` slot for Suite C; falls back to `reasoner` if unset. Each role's provider + model + API key are independently configurable via `EMI_LLM_<ROLE>_*` env vars.
- **Prompt caching is a hint, not a hard requirement.** Callers set `TextBlock.cache_hint=True` on cacheable content (system prompt, tool defs, L6 frame). Providers that support explicit caching (Anthropic) honor it; providers with implicit caching (OpenAI) ignore it; providers without caching skip it. Budget and cost math still work.
- **Every LLM call has a hard timeout** (30s default for `reasoner`, 15s for `utility`, 60s for batched causal linker; all configurable per role).
- **Every LLM call is logged** with `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `provider_id`, `model`, `cost_usd`, and a stable `call_id`.
- **Never hardcode a model string** anywhere outside `services/shared/config.py` and `services/llm/pricing.py`.
- **Structured outputs use the tool-use pattern** (`ToolDef` + `force_tool="name"`), not free-form JSON in text. Validate the returned `ToolCall.arguments` with a Pydantic model at the caller. When a chosen provider doesn't support tool use (rare), the client raises `LLMCapabilityError` — do not silently fall back to text parsing except in `utility` calls that can tolerate it.
- **Grep hygiene:** `grep -rn "from anthropic\|from openai\|import openai\|from google\.genai" services/ eval/` must only match files under `services/llm/providers/`. This is a CI grep guard.

---

## 9. Testing rules

**Three test tiers under `tests/`:**
- `tests/unit/` — pure logic, no network, no DB. Fast (<1s each).
- `tests/integration/` — hits local Postgres + MinIO + Redis (via `docker-compose`). Marked `@pytest.mark.integration`.
- `tests/eval/` — invokes the eval framework in a smoke mode; not the golden set.

**Every recipe in `services/derive/recipes/` has at least one unit test** verifying a hand-computed value.

**Every SQL migration is applied in `conftest.py` via `db/schema/*.sql` in order** before integration tests run.

**Never mock the LLM SDK at the integration layer.** Use a real tiny prompt via the utility role if you must; better: build a `services/llm/fakes.py` `FakeLLMClient` that returns canned Pydantic tool-call responses, and inject it via the factory when `EMI_LLM_MODE=fake`.

---

## 10. Git & PR discipline

- One milestone task per commit when possible. Commit messages: `Mx.y.z: <what>`.
- Never commit `.env`, `data/`, `.venv/`, `node_modules/`, MinIO blobs.
- Do not check in generated OpenAPI clients or generated migrations.
- Do not merge with failing `ruff`, `mypy`, `pytest`, or `pnpm typecheck`.

---

## 11. Documentation rules

- **`README.md`** is the developer quickstart: how to run `docker-compose up`, how to run migrations, how to start the API, how to start the worker, how to start the web app. Updated in M1.5.
- **`BLUEPRINT.md`** is the design source. Update it only if the design changes; do not sync it with implementation churn.
- **Per-module `README.md`** is optional but encouraged for tricky modules (`retrieval`, `kg`, `derive`), covering the "why" — never repeat what code already says.
- No other markdown files unless a task explicitly asks for one.

---

## 12. Non-negotiable financial guarantees (from BLUEPRINT §2.2)

These are enforced by tests and by the system prompt. Any code that violates them is a bug:

1. The LLM is never the source of truth for any number.
2. Every claim in a chat answer resolves to `document_id + page + bbox`.
3. Every user turn stays under the ~7200-token retrieval+prompt budget.
4. Every LLM-cited number is reproducible by a deterministic SQL query.
5. Any extracted fact with `extraction_conf < 0.7` is quarantined until a human reviews it.

If a task appears to violate one of these, stop and raise it.
