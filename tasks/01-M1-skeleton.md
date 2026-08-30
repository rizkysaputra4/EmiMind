# M1 — Skeleton (Weeks 1–4)

**Goal:** every dev-loop primitive works. `docker-compose up` gives you Postgres, MinIO, Redis. A user can upload a PDF via the API; a row appears in `documents` with `status='raw'`; the blob lands in MinIO. FastAPI + Next.js chat UI both boot. Concept map is seeded for banks + coal miners (10 tickers).

**Definition of done for M1:** every `Acceptance` block in this file passes end-to-end from a fresh `git clone`.

---

## 1. Project bootstrap

### M1.1.1 — Create Python project skeleton
**File:** `pyproject.toml`
**Depends on:** none

Create a `pyproject.toml` using `uv` (`hatchling` build backend). Set:
- `name = "emimind"`
- `version = "0.1.0"`
- `requires-python = ">=3.11,<3.13"`
- Dependencies (production):
  - `fastapi>=0.115`
  - `uvicorn[standard]>=0.30`
  - `pydantic>=2.7`
  - `pydantic-settings>=2.3`
  - `asyncpg>=0.29`
  - `sqlalchemy[asyncio]>=2.0`
  - `structlog>=24.1`
  - `python-multipart>=0.0.9`
  - `minio>=7.2`
  - `redis>=5.0`
  - `arq>=0.26`
  - `httpx>=0.27`
  - LLM SDKs — install the ones you'll use; the abstraction (see `appendix-llm-providers.md`) keeps each SDK confined to one file:
    - `anthropic>=0.39` (Anthropic Claude)
    - `openai>=1.40` (OpenAI + OpenAI-compatible: Kimi/Moonshot, DeepSeek, Together, Groq, local Ollama)
    - `google-genai>=0.3` — optional, add when needed
- Dependencies (dev, `[tool.uv.dev-dependencies]`):
  - `ruff>=0.5`
  - `mypy>=1.10`
  - `pytest>=8.2`
  - `pytest-asyncio>=0.23`
  - `pytest-cov>=5.0`

**Acceptance:**
- `[RUN]` `uv sync` completes without error.
- `[VERIFY]` `.venv/` created; `uv run python -c "import fastapi; import anthropic; import arq; import minio; import structlog"` prints nothing (i.e. no error).

### M1.1.2 — Ruff & mypy config
**Files:** `ruff.toml`, `mypy.ini`
**Depends on:** M1.1.1

`ruff.toml`:
```toml
line-length = 100
target-version = "py311"

[lint]
select = ["E","F","I","N","B","UP","PL","RUF","T20","ASYNC","S"]
ignore = ["PLR0913","PLR2004"]

[lint.per-file-ignores]
"tests/**" = ["S101","PLR2004"]
"scripts/**" = ["T201"]
```

`mypy.ini`:
```ini
[mypy]
python_version = 3.11
strict = True
warn_unused_ignores = True
warn_redundant_casts = True
disallow_untyped_decorators = False
plugins = pydantic.mypy

[mypy-camelot.*]
ignore_missing_imports = True
[mypy-yfinance.*]
ignore_missing_imports = True
[mypy-pdfplumber.*]
ignore_missing_imports = True
```

**Acceptance:**
- `[RUN]` `uv run ruff check .` prints "All checks passed!" (empty project).
- `[RUN]` `uv run mypy services eval` prints "Success" (empty target — will be non-empty by M1.4).

### M1.1.3 — Create service package tree
**Files:** create empty `__init__.py` in every folder below.
**Depends on:** M1.1.1

Create the exact folder tree from `tasks/00-conventions.md § 1`:

```
services/__init__.py
services/shared/__init__.py
services/api/__init__.py
services/api/routers/__init__.py
services/ingest/__init__.py
services/ingest/tasks/__init__.py
services/extraction/__init__.py
services/derive/__init__.py
services/derive/recipes/__init__.py
services/narrative/__init__.py
services/retrieval/__init__.py
services/kg/__init__.py
services/market/__init__.py
services/screener/__init__.py
services/llm/__init__.py
eval/__init__.py
scripts/__init__.py
tests/__init__.py
tests/unit/__init__.py
tests/integration/__init__.py
db/schema/.gitkeep
db/seeds/.gitkeep
```

**Acceptance:**
- `[RUN]` `python -c "import services.shared, services.api, services.ingest, services.derive"` from repo root succeeds.

### M1.1.4 — Create `.env.example`
**File:** `.env.example`
**Depends on:** M1.1.3

```dotenv
# ============================================================================
# EmiMind local development environment
# Copy this to .env and fill secrets. Never commit .env.
# ============================================================================

# Postgres --------------------------------------------------------------------
EMI_POSTGRES_DSN=postgresql+asyncpg://emimind:emimind@localhost:5432/emimind
EMI_POSTGRES_DSN_SYNC=postgresql://emimind:emimind@localhost:5432/emimind

# MinIO -----------------------------------------------------------------------
EMI_MINIO_ENDPOINT=localhost:9000
EMI_MINIO_ACCESS_KEY=minioadmin
EMI_MINIO_SECRET_KEY=minioadmin
EMI_MINIO_SECURE=false
EMI_MINIO_BUCKET_RAW=emimind-raw

# Redis (queue) ---------------------------------------------------------------
EMI_REDIS_URL=redis://localhost:6379/0

# LLM — provider-neutral (see tasks/appendix-llm-providers.md) ---------------
# Two role slots. Each can pick any provider independently.
#   provider ∈ { anthropic | openai | openai_compat | google }
#   For openai_compat, set BASE_URL to the endpoint (Kimi/Moonshot, DeepSeek,
#   Together, Groq, Ollama, etc.).
EMI_LLM_REASONER_PROVIDER=anthropic
EMI_LLM_REASONER_MODEL=claude-sonnet-4-6
EMI_LLM_REASONER_API_KEY=sk-ant-...
EMI_LLM_REASONER_BASE_URL=
EMI_LLM_REASONER_MAX_OUTPUT_TOKENS=1024
EMI_LLM_REASONER_TIMEOUT_S=30

EMI_LLM_UTILITY_PROVIDER=anthropic
EMI_LLM_UTILITY_MODEL=claude-haiku-4-5-20251001
EMI_LLM_UTILITY_API_KEY=sk-ant-...
EMI_LLM_UTILITY_BASE_URL=
EMI_LLM_UTILITY_MAX_OUTPUT_TOKENS=512
EMI_LLM_UTILITY_TIMEOUT_S=15

# Optional judge slot (Suite C). If unset, falls back to the reasoner.
EMI_LLM_JUDGE_PROVIDER=
EMI_LLM_JUDGE_MODEL=
EMI_LLM_JUDGE_API_KEY=
EMI_LLM_JUDGE_BASE_URL=

# ---- Example alternative setups (uncomment to use) --------------------------
# Kimi (Moonshot) for both roles:
# EMI_LLM_REASONER_PROVIDER=openai_compat
# EMI_LLM_REASONER_MODEL=moonshot-v1-128k
# EMI_LLM_REASONER_BASE_URL=https://api.moonshot.cn/v1
# EMI_LLM_REASONER_API_KEY=sk-...
#
# DeepSeek reasoner + OpenAI utility:
# EMI_LLM_REASONER_PROVIDER=openai_compat
# EMI_LLM_REASONER_MODEL=deepseek-chat
# EMI_LLM_REASONER_BASE_URL=https://api.deepseek.com/v1
# EMI_LLM_REASONER_API_KEY=sk-...
# EMI_LLM_UTILITY_PROVIDER=openai
# EMI_LLM_UTILITY_MODEL=gpt-4o-mini
# EMI_LLM_UTILITY_API_KEY=sk-...

# Embedding model (populated in M3) ------------------------------------------
EMI_EMBEDDING_MODEL=BAAI/bge-m3
EMI_EMBEDDING_DEVICE=cpu
EMI_RERANKER_MODEL=BAAI/bge-reranker-v2-m3

# Logging ---------------------------------------------------------------------
EMI_LOG_LEVEL=INFO
EMI_LOG_FORMAT=console   # console | json

# Chat token budget -----------------------------------------------------------
EMI_CHAT_TOKEN_BUDGET=7200
```

**Acceptance:**
- File exists, contains every key above.

### M1.1.5 — Create `.gitignore`
**File:** `.gitignore`
**Depends on:** none

```gitignore
.venv/
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
.env
.env.local
node_modules/
web/.next/
web/out/
web/.turbo/
data/
minio-data/
postgres-data/
*.log
.DS_Store
.idea/
.vscode/
```

**Acceptance:** file exists.

---

## 2. Docker Compose for local dev

### M1.2.1 — `docker-compose.yml`
**File:** `docker-compose.yml`
**Depends on:** M1.1.4

Postgres 16 with `pgvector` extension, MinIO, Redis 7. Named volumes. Health checks. No app services yet — the app runs on the host in M1.

```yaml
version: "3.9"

services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: emimind
      POSTGRES_PASSWORD: emimind
      POSTGRES_DB: emimind
    ports:
      - "5432:5432"
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "emimind"]
      interval: 3s
      timeout: 3s
      retries: 30

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - minio-data:/data
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 3s
      timeout: 3s
      retries: 30

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 3s
      timeout: 3s
      retries: 30

volumes:
  postgres-data:
  minio-data:
```

**Acceptance:**
- `[RUN]` `docker compose up -d` starts all three; all reach healthy state.
- `[RUN]` `docker compose ps` shows all three as healthy within 60s.
- `[VERIFY]` `psql "postgresql://emimind:emimind@localhost:5432/emimind" -c "SELECT 1"` returns 1.
- `[VERIFY]` MinIO console at http://localhost:9001 loads.

### M1.2.2 — Makefile
**File:** `Makefile`
**Depends on:** M1.2.1

```makefile
.PHONY: up down migrate seed api worker web lint typecheck test fmt

up:
	docker compose up -d

down:
	docker compose down

migrate:
	uv run python scripts/apply_migrations.py

seed:
	uv run python scripts/seed_concept_map.py

api:
	uv run uvicorn services.api.main:app --reload --host 0.0.0.0 --port 8000

worker:
	uv run arq services.ingest.worker.WorkerSettings

web:
	cd web && pnpm dev

lint:
	uv run ruff check .
	cd web && pnpm lint

typecheck:
	uv run mypy services eval
	cd web && pnpm typecheck

fmt:
	uv run ruff format .
	cd web && pnpm format

test:
	uv run pytest -m "not integration" tests/
```

**Acceptance:** file exists; `make lint` works after M1.4.

---

## 3. Database schemas (skeleton)

Every SQL block below is **copy verbatim from `tasks/appendix-schemas.md`**. Do not paraphrase.

### M1.3.1 — Extensions migration
**File:** `db/schema/000_extensions.sql`
**Depends on:** M1.2.1
**Copy verbatim:** appendix-schemas.md § "000_extensions.sql"

**Acceptance:**
- `[RUN]` `psql $EMI_POSTGRES_DSN_SYNC -f db/schema/000_extensions.sql` succeeds.
- `[VERIFY]` `SELECT extname FROM pg_extension WHERE extname IN ('vector','pg_trgm','uuid-ossp');` returns 3 rows.

### M1.3.2 — Documents table
**File:** `db/schema/001_documents.sql`
**Copy verbatim:** appendix-schemas.md § "001_documents.sql"

**Acceptance:**
- Migration applies clean; `\d documents` in `psql` shows all columns from BLUEPRINT §6.1.

### M1.3.3 — Financial facts
**File:** `db/schema/002_financial_facts.sql`
**Copy verbatim:** appendix-schemas.md § "002_financial_facts.sql"

Includes `financial_facts` table + `needs_review` flag column + all indexes from BLUEPRINT §6.2.

**Acceptance:**
- Migration applies clean.
- `\d financial_facts` shows the unique index on `(ticker, fiscal_period, concept_id, segment_key)` scoped to `is_restated = false`.

### M1.3.4 — Concept map
**File:** `db/schema/003_concept_map.sql`
**Copy verbatim:** appendix-schemas.md § "003_concept_map.sql"

**Acceptance:** migration applies clean.

### M1.3.5 — Worker runs
**File:** `db/schema/004_worker_runs.sql`
**Copy verbatim:** appendix-schemas.md § "004_worker_runs.sql"

**Acceptance:** migration applies clean.

### M1.3.6 — Migration runner
**File:** `scripts/apply_migrations.py`
**Depends on:** M1.3.1..M1.3.5

Behavior:
- Reads `EMI_POSTGRES_DSN_SYNC` from env.
- Lists `db/schema/*.sql`, sorts by filename.
- Creates a `schema_migrations` table if absent: `(filename text PRIMARY KEY, applied_at timestamptz DEFAULT now())`.
- For each unapplied file, applies inside a transaction, then inserts the filename row.
- Exits nonzero on error.

Use `psycopg` (add to `pyproject.toml` deps: `psycopg[binary]>=3.1`). Sync driver for migrations only.

**Acceptance:**
- `[RUN]` `make migrate` on a fresh DB applies files 000..004 in order.
- `[RUN]` running again is a no-op (prints "0 migrations applied").
- `[VERIFY]` `SELECT count(*) FROM schema_migrations` returns 5.

---

## 4. Shared infrastructure (`services/shared`)

### M1.4.1 — Config
**File:** `services/shared/config.py`

`pydantic-settings`-based `Settings` model reading every `EMI_*` env var. Cached singleton via `@lru_cache` factory `get_settings() -> Settings`. Fields typed (`AnyUrl`, `SecretStr` for API keys). No default DSN — must come from env.

**Acceptance:**
- `[RUN]` `uv run python -c "from services.shared.config import get_settings; print(get_settings().postgres_dsn)"` prints the value after `source .env` (or with `.env` in cwd).

### M1.4.2 — Logging
**File:** `services/shared/logging.py`

`structlog` configured for console (dev) or JSON (prod) based on `EMI_LOG_FORMAT`. Exposes `configure_logging()` (call once at app start) and `get_logger(name) -> structlog.BoundLogger`.

**Acceptance:**
- `[RUN]` `uv run python -c "from services.shared.logging import configure_logging,get_logger; configure_logging(); get_logger('t').info('hi', x=1)"` prints a structured log line.

### M1.4.3 — DB pool
**File:** `services/shared/db.py`

- `create_pool() -> AsyncEngine` (SQLAlchemy async engine, `asyncpg` driver, pool_size=10).
- FastAPI dependency `get_conn() -> AsyncIterator[AsyncConnection]`.
- Async context manager `tx(conn) -> AsyncIterator` wrapping `begin_nested()` for savepoints.
- Sets `statement_timeout` to 5000ms on each session.
- All queries done with `sqlalchemy.text(...)` + parameter binding.

**Acceptance:**
- Unit test `tests/unit/test_shared_db.py` verifies `create_pool()` doesn't try to connect eagerly. Actual connection is tested in integration.

### M1.4.4 — MinIO client
**File:** `services/shared/minio_client.py`

- `get_minio() -> Minio` factory reading settings.
- `ensure_bucket(name)` creates bucket if absent.
- `raw_key(ticker, doc_type, fiscal_period, doc_hash, ext) -> str` returns the canonical MinIO key per BLUEPRINT §6.1.
- `put_pdf(key, data, size)` and `get_pdf(key) -> bytes` helpers.

**Acceptance:**
- Integration test `tests/integration/test_minio.py` puts and reads a small file, deletes it.

### M1.4.5 — Redis + arq client
**File:** `services/shared/redis_client.py`

- `get_redis_pool()` returns an `arq.connections.ArqRedis` pool.
- `enqueue_job(name, *args, **kwargs)` thin wrapper for tests/scripts.

**Acceptance:** unit test constructs the pool with a fake settings object.

### M1.4.6 — Types
**File:** `services/shared/types.py`

Central Pydantic models used across module boundaries. Start with:
- `FiscalPeriod` — validated string, regex `^(19|20)\d{2}(Q[1-4]|FY|H[12])$`.
- `Ticker` — validated string, uppercase, `^[A-Z]{4}$` (IDX tickers are 4 letters).
- `DocType` — `Literal["PUBEX","FS_QUARTERLY","FS_ANNUAL","ANNUAL_REPORT"]`.
- `Language` — `Literal["id","en","mixed"]`.
- `Statement` — `Literal["IS","BS","CF","EQ","NOTE"]`.
- `ExtractionMethod` — `Literal["xbrl","table_parser","llm_extract","manual"]`.
- `BBox` — `tuple[float,float,float,float]` newtype with validation `x0<=x1 and y0<=y1`.

**Acceptance:**
- Unit tests validate each type rejects malformed input (e.g. `Ticker("bmri")` fails, `Ticker("BMRI")` passes).

### M1.4.7 — Errors
**File:** `services/shared/errors.py`

Define exception hierarchy:
```python
class EmiError(Exception): ...


class ExtractionError(EmiError): ...


class NormalizationError(EmiError): ...


class RetrievalError(EmiError): ...


class LLMError(EmiError): ...


class BudgetExceededError(EmiError): ...


class ProvenanceError(EmiError): ...


class ConceptMappingError(NormalizationError): ...
```

**Acceptance:** file exists, imports clean.

---

## 5. FastAPI skeleton + upload endpoint

### M1.5.1 — FastAPI app
**File:** `services/api/main.py`

- Creates `FastAPI(title="EmiMind API", version="0.1.0")`.
- Startup event: `configure_logging()`, initialize DB engine, MinIO bucket, Redis pool. Store on `app.state`.
- Shutdown: dispose engine, close redis.
- Health endpoint `GET /healthz` returns `{"ok": true}`.
- Mounts routers from `services.api.routers.upload`, `services.api.routers.chat`, `services.api.routers.screener` (chat/screener stubs in M1, real in M4/M6).
- CORS: allow `http://localhost:3000`.

**Acceptance:**
- `[RUN]` `make api` starts uvicorn.
- `[VERIFY]` `curl http://localhost:8000/healthz` returns `{"ok":true}`.
- `[VERIFY]` `curl http://localhost:8000/openapi.json | jq .info.title` returns `"EmiMind API"`.

### M1.5.2 — Dependency helpers
**File:** `services/api/deps.py`

FastAPI dependency functions:
- `get_db_conn() -> AsyncIterator[AsyncConnection]`
- `get_minio_client() -> Minio`
- `get_redis() -> ArqRedis`
- `get_settings_dep() -> Settings`

Each pulls from `request.app.state` — never from a global.

**Acceptance:** file exists, imports clean.

### M1.5.3 — Upload router
**File:** `services/api/routers/upload.py`

`POST /api/v1/upload` — multipart form:
- `ticker: str` (form field, must match `Ticker` type)
- `doc_type: DocType`
- `fiscal_period: FiscalPeriod`
- `language: Language`
- `file: UploadFile` (PDF)
- (optional) `xbrl_file: UploadFile | None` (for the XBRL sidecar path)

Behavior:
1. Read the PDF into memory (cap at 50MB; reject with 413 if larger).
2. Compute `doc_hash = sha256(pdf_bytes).hexdigest()`.
3. Query `documents` for existing hash. If exists, return `{"document_id": existing.id, "status": existing.status, "deduplicated": true}` with HTTP 200.
4. Compute `minio_key = raw_key(...)`.
5. `put_pdf(minio_key, pdf_bytes, len(pdf_bytes))`.
6. If `xbrl_file`, upload as `{basename}.xbrl.xml`.
7. `INSERT INTO documents (...) VALUES (...)` with `status='raw'`; return `{"document_id": ..., "status": "raw", "deduplicated": false}`.
8. Enqueue arq job `ingest_document(document_id)`.

Return type: Pydantic `UploadResponse` model.

**Never** read `request.headers['content-type']` for the PDF — trust `UploadFile.content_type` and verify it's `application/pdf`.

**Acceptance:**
- `[RUN]` end-to-end curl:
  ```bash
  curl -X POST http://localhost:8000/api/v1/upload \
    -F ticker=BMRI -F doc_type=FS_QUARTERLY -F fiscal_period=2024Q4 \
    -F language=id -F file=@sample.pdf
  ```
  returns `{"document_id":"...","status":"raw","deduplicated":false}`.
- `[VERIFY]` `psql -c "SELECT ticker, status FROM documents"` shows the row.
- `[VERIFY]` `mc ls local/emimind-raw/BMRI/FS_QUARTERLY/2024Q4/` shows the file.
- `[VERIFY]` re-uploading the same PDF returns `deduplicated: true` and does not create a second row.
- Unit test rejects a non-PDF upload with 415.

### M1.5.4 — Chat router stub
**File:** `services/api/routers/chat.py`

`POST /api/v1/chat` — accepts a body `{session_id?: uuid, message: str, focus_ticker?: str}` and returns a stub:
```json
{"session_id": "...", "answer": "Chat not implemented until M4.", "citations": []}
```

Purpose: gives the frontend a stable contract to develop against.

**Acceptance:** endpoint returns a valid JSON response.

### M1.5.5 — Screener router stub
**File:** `services/api/routers/screener.py`

`POST /api/v1/screener` — returns `{"results": [], "message": "Screener not implemented until M6."}`.

**Acceptance:** endpoint returns valid JSON.

---

## 6. arq worker skeleton

### M1.6.1 — Worker settings
**File:** `services/ingest/worker.py`

Define `arq.WorkerSettings`:
- `functions = [ingest_document]` (a stub for now — real chain in M2)
- `redis_settings` from config
- `job_timeout = 600` seconds
- `max_jobs = 4`
- `on_startup` / `on_shutdown` initialize DB pool, MinIO, logger; store on `ctx`.

### M1.6.2 — Stub `ingest_document` task
**File:** `services/ingest/tasks/ingest_document.py`

```python
async def ingest_document(ctx: dict, document_id: str) -> dict:
    log = ctx["log"].bind(worker="ingest_document", document_id=document_id)
    log.info("received (stub)")
    return {"document_id": document_id, "status": "raw", "note": "stub — real chain lands in M2"}
```

Registered in `worker.py`.

**Acceptance:**
- `[RUN]` `make worker` in one terminal, `make api` in another.
- After running M1.5.3 acceptance curl, the worker terminal logs "received (stub)".

---

## 7. Concept map seed (banks + coal miners, 10 tickers)

### M1.7.1 — Seed CSV
**File:** `db/seeds/concept_map_seed.csv`

Header: `local_label,sector,psak_version,canonical_concept_id,confidence`.

Minimum coverage — the founder curates these; the executor just types them in:

- 10 tickers to prioritize: banks `BMRI, BBRI, BBNI, BBCA` + coal miners `ADRO, PTBA, ITMG, HRUM, INDY, BUMI`.
- For **banks**, at minimum these local_label → canonical_concept_id mappings, `sector=BANK`, `psak_version=PSAK_71`, `confidence=1.0`:
  - `Pendapatan Bunga` → `ifrs:InterestIncome`
  - `Beban Bunga` → `ifrs:InterestExpense`
  - `Pendapatan Bunga Bersih` → `idx:NetInterestIncome`
  - `Pendapatan Operasional Lainnya` → `idx:OtherOperatingIncome`
  - `Beban Operasional` → `idx:OperatingExpenses`
  - `Laba Sebelum Pajak` → `ifrs:ProfitBeforeTax`
  - `Laba Bersih` → `ifrs:ProfitLoss`
  - `Total Aset` → `ifrs:Assets`
  - `Total Liabilitas` → `ifrs:Liabilities`
  - `Ekuitas` → `ifrs:Equity`
  - `Kredit yang Diberikan` → `idx:LoansAndReceivables`
  - `Simpanan Nasabah` → `idx:CustomerDeposits`
  - `Giro` → `idx:DemandDeposits`
  - `Tabungan` → `idx:SavingsDeposits`
  - `Deposito` → `idx:TimeDeposits`
  - `Kredit Bermasalah` → `idx:NonPerformingLoans`
  - `Cadangan Kerugian Penurunan Nilai` → `idx:AllowanceForImpairment`
  - Plus English variants (`Interest Income`, `Net Interest Income`, etc.).
- For **mining (coal)**, `sector=MINING`, `psak_version=PSAK_72`:
  - `Penjualan Bersih` → `ifrs:Revenue`
  - `Beban Pokok Penjualan` → `ifrs:CostOfSales`
  - `Laba Kotor` → `ifrs:GrossProfit`
  - `Laba Usaha` → `ifrs:OperatingProfit`
  - `Volume Produksi Batubara` → `idx:CoalProductionVolume`
  - `Volume Penjualan Batubara` → `idx:CoalSalesVolume`
  - `Harga Jual Rata-rata` → `idx:AverageSellingPrice`
  - `Cash Cost` → `idx:CashCost`
  - `Strip Ratio` → `idx:StripRatio`
  - Plus English variants.

Aim for ~80 rows across the two sectors. This is intentionally boring hand-curation and is the highest-leverage work of M1.

**Acceptance:** CSV exists with ≥ 80 rows.

### M1.7.2 — Seed loader
**File:** `scripts/seed_concept_map.py`

Reads `db/seeds/concept_map_seed.csv`; upserts rows into `concept_map` via `ON CONFLICT (local_label, sector) DO UPDATE`. Prints inserted / updated counts.

**Acceptance:**
- `[RUN]` `make seed` reports N rows loaded.
- `[VERIFY]` `SELECT count(*) FROM concept_map` = row count in the CSV.
- `[RUN]` running `make seed` twice is idempotent.

---

## 8. Next.js chat UI skeleton

### M1.8.1 — Scaffold Next.js app
**Directory:** `web/`
**Depends on:** none

```bash
pnpm create next-app@latest web --typescript --app --tailwind --eslint --src-dir=false --import-alias "@/*"
cd web && pnpm add lucide-react @tanstack/react-query zod
pnpm dlx shadcn-ui@latest init
pnpm dlx shadcn-ui@latest add button input textarea card scroll-area separator toast
```

**Acceptance:**
- `[RUN]` `cd web && pnpm dev` boots on port 3000.
- `[VERIFY]` http://localhost:3000 loads without errors.

### M1.8.2 — API client
**File:** `web/lib/api.ts`

Typed helpers:
- `uploadDocument(payload: UploadRequest): Promise<UploadResponse>` (multipart)
- `sendChatMessage(payload: ChatRequest): Promise<ChatResponse>`

Types live in `web/lib/types.ts`. Read `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`).

**Acceptance:** typechecks; each function returns a typed promise.

### M1.8.3 — Chat window skeleton
**File:** `web/components/ChatWindow.tsx`

- Message list (empty initially), input at the bottom.
- Submit calls `sendChatMessage` and appends both user and assistant messages.
- Placeholder "Upload a document first" hint when list is empty.

**Acceptance:**
- On the home page, the chat window renders; typing a message and pressing Enter shows both messages (backed by the M1.5.4 stub answer).

### M1.8.4 — Home page
**File:** `web/app/page.tsx`

Two-pane layout: left = upload form, right = `<ChatWindow />`.

**Acceptance:** page loads at `/`; layout is functional (styling can be minimal).

---

## 9. Tests & CI-lite

### M1.9.1 — Unit tests
**Files:**
- `tests/unit/test_types.py` — validates `Ticker`, `FiscalPeriod`, `BBox`.
- `tests/unit/test_config.py` — loads settings from a monkeypatched env.
- `tests/unit/test_minio_key.py` — verifies `raw_key(...)` produces the expected string.

**Acceptance:** `[RUN]` `uv run pytest tests/unit -q` passes.

### M1.9.2 — Integration tests
**Files:**
- `tests/integration/conftest.py` — spins up a fixture that applies all migrations to a fresh DB (or a `schema` created per test session).
- `tests/integration/test_upload.py` — hits `POST /api/v1/upload` with a tiny PDF (embed base64 in the test), asserts row and MinIO object.

**Acceptance:** `[RUN]` `uv run pytest -m integration tests/integration -q` passes with `docker compose up` running.

---

## 10. README

### M1.10.1 — Developer quickstart
**File:** `README.md`

Cover:
- What EmiMind is (1 paragraph, from BLUEPRINT §1).
- Prerequisites: Python 3.11+, `uv`, Docker, Node 20, `pnpm`, `mc` (optional).
- Setup steps:
  1. `cp .env.example .env` and fill `EMI_ANTHROPIC_API_KEY`.
  2. `docker compose up -d`
  3. `uv sync`
  4. `make migrate`
  5. `make seed`
  6. In terminal A: `make api`
  7. In terminal B: `make worker`
  8. In terminal C: `cd web && pnpm install && pnpm dev`
- How to run tests, lint, typecheck.
- Link to `BLUEPRINT.md` and `TASKS.md`.

**Acceptance:** a fresh checkout can be brought up by following the README in <10 minutes.

---

## M1 exit gate

Before starting M2, every item below must be true:

- [ ] `docker compose up -d` starts Postgres, MinIO, Redis; all healthy.
- [ ] `make migrate` on a fresh DB applies migrations 000..004; idempotent.
- [ ] `make seed` loads ≥ 80 concept_map rows; idempotent.
- [ ] `make api` boots FastAPI on :8000; `/healthz` returns ok.
- [ ] `make worker` boots arq; consumes stub `ingest_document` jobs.
- [ ] `cd web && pnpm dev` boots Next.js on :3000; upload form + chat pane render.
- [ ] Uploading a sample PDF via the UI (or curl) creates a `documents` row with `status='raw'`, uploads the blob to MinIO, and enqueues the stub worker.
- [ ] `make lint` and `make typecheck` pass.
- [ ] `make test` (unit) passes.
- [ ] The founder has hand-curated at least 40 gold Q/A rows for eval Suite A in `eval/golden/suite_a_fact_recall.jsonl` (rows can reference facts that will only exist once M2 populates them — that's fine, they're future-verifiable).
