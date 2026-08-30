# EmiMind — Task Execution Tracker

> **Source of Truth:** [`BLUEPRINT.md`](file:///c:/Users/rizky/Documents/Code/EmiMind/BLUEPRINT.md) & [`TASKS.md`](file:///c:/Users/rizky/Documents/Code/EmiMind/TASKS.md)  
> **Status Summary:** All Milestones 1 through 7 (Skeleton, Ingestion, Derived & Narrative, Retrieval & Chat, Knowledge Graph & Guidance, Stock Screener + Market Technicals, and Polish, Auth, Observability & Coverage) are 100% Completed & Verified.

---

## Milestone Progress Overview

| Milestone | Description | Scope | Status | Completion |
|:---|:---|:---|:---:|:---:|
| **M1** | [Skeleton](tasks/01-M1-skeleton.md) | Weeks 1–4 | 🟢 Completed | 10/10 Sections (100%) |
| **M2** | [Ingestion](tasks/02-M2-ingestion.md) | Weeks 5–10 | 🟢 Completed | 7/7 Sections (100%) |
| **M3** | [Derived & Narrative](tasks/03-M3-derived-narrative.md) | Weeks 11–14 | 🟢 Completed | 7/7 Sections (100%) |
| **M4** | [Retrieval & Chat](tasks/04-M4-retrieval-chat.md) | Weeks 15–20 | 🟢 Completed | 8/8 Sections (100%) |
| **M5** | [KG & Guidance](tasks/05-M5-kg-guidance.md) | Weeks 21–26 | 🟢 Completed | 7/7 Sections (100%) |
| **M6** | [Screener & Technical](tasks/06-M6-screener-technical.md) | Weeks 27–32 | 🟢 Completed | 7/7 Sections (100%) |
| **M7** | [Polish & Coverage](tasks/07-M7-polish.md) | Weeks 33–36 | 🟢 Completed | 8/8 Sections (100%) |

---

## Detailed Task Checklist — Milestone 1 (M1: Skeleton)

### 1. Project Bootstrap
- [x] **M1.1.1** — `pyproject.toml` (uv, Hatchling backend, production + dev dependencies)
- [x] **M1.1.2** — `ruff.toml` & `mypy.ini` (strict typechecking & lint configurations)
- [x] **M1.1.3** — Package tree & `__init__.py` files across all monorepo modules
- [x] **M1.1.4** — `.env.example` (all `EMI_*` env vars and provider configuration examples)
- [x] **M1.1.5** — `.gitignore`

### 2. Dev Environment
- [x] **M1.2.1** — `docker-compose.yml` (Postgres 16 + pgvector, MinIO + console, Redis 7)
- [x] **M1.2.2** — `Makefile` (up, down, migrate, seed, api, worker, web, lint, typecheck, fmt, test)

### 3. Database Schemas
- [x] **M1.3.1** — `db/schema/000_extensions.sql` (vector, pg_trgm, uuid-ossp)
- [x] **M1.3.2** — `db/schema/001_documents.sql`
- [x] **M1.3.3** — `db/schema/002_financial_facts.sql`
- [x] **M1.3.4** — `db/schema/003_concept_map.sql`
- [x] **M1.3.5** — `db/schema/004_worker_runs.sql`
- [x] **M1.3.6** — `scripts/apply_migrations.py` (idempotent migration runner using `psycopg`)

### 4. Shared Infrastructure (`services/shared`)
- [x] **M1.4.1** — `services/shared/config.py` (`pydantic-settings` cached singleton `get_settings()`)
- [x] **M1.4.2** — `services/shared/logging.py` (`structlog` console/json structured logger)
- [x] **M1.4.3** — `services/shared/db.py` (Async SQLAlchemy engine pool, connection dependency, savepoint transactions)
- [x] **M1.4.4** — `services/shared/minio_client.py` (`Minio` client factory, bucket check, `raw_key()`, upload/download helpers)
- [x] **M1.4.5** — `services/shared/redis_client.py` (`ArqRedis` pool and `enqueue_job()`)
- [x] **M1.4.6** — `services/shared/types.py` (Domain types: `FiscalPeriod`, `Ticker`, `DocType`, `Language`, `Statement`, `BBox`)
- [x] **M1.4.7** — `services/shared/errors.py` (Domain exception hierarchy)

### 5. FastAPI App & Routers
- [x] **M1.5.1** — `services/api/main.py` (lifespan management, CORS, `/healthz`)
- [x] **M1.5.2** — `services/api/deps.py` (dependency injection from app state)
- [x] **M1.5.3** — `services/api/routers/upload.py` (`POST /api/v1/upload` with SHA-256 dedup, MinIO storage, DB insert, arq enqueue)
- [x] **M1.5.4** — `services/api/routers/chat.py` (contract stub `POST /api/v1/chat`)
- [x] **M1.5.5** — `services/api/routers/screener.py` (contract stub `POST /api/v1/screener`)

### 6. arq Worker Skeleton
- [x] **M1.6.1** — `services/ingest/worker.py` (`WorkerSettings` lifecycle handlers)
- [x] **M1.6.2** — `services/ingest/tasks/process_document.py` (stub task downloading file from MinIO)

### 7. Seed Data & Scripts
- [x] **M1.7.1** — `db/seeds/concept_map_seed.csv` (100+ standard IDX/IFRS concept label mappings)
- [x] **M1.7.2** — `scripts/seed_concept_map.py` (upsert seed runner for `concept_map`)
- [x] **M1.7.3** — `scripts/seed_sample_filings.py` (sample filing generator for BMRI, BBRI, BBCA, ADRO)

### 8. Frontend Skeleton (`web/`)
- [x] **M1.8.1** — Next.js 14 App Router initialization with TailwindCSS & TypeScript
- [x] **M1.8.2** — `web/lib/api.ts` (Typed API client for healthz, upload, chat, screener)
- [x] **M1.8.3** — `web/components/UploadForm.tsx` (PDF/ZIP filing uploader)
- [x] **M1.8.4** — `web/components/ChatWindow.tsx` (Conversational interface)
- [x] **M1.8.5** — `web/app/page.tsx` & `web/app/layout.tsx` (Dashboard UI)

### 9. Tests & Validation
- [x] **M1.9.1** — `tests/conftest.py` & `tests/unit/test_types.py`
- [x] **M1.9.2** — `tests/unit/test_minio_key.py`, `test_config.py`, `test_shared_db.py`
- [x] **M1.9.3** — `tests/integration/test_upload.py` (FastAPI integration tests)

### 10. Verification Gate
- [x] **M1.10.1** — Verification walkthrough & task tracker sign-off

---

## Detailed Task Checklist — Milestone 2 (M2: Ingestion)

### 1. Database Migrations
- [x] **M2.1.1** — `db/schema/005_narrative_chunks.sql` (`narrative_chunks` table + GIN FTS index + HNSW vector index)
- [x] **M2.1.2** — `db/schema/006_extraction_logs.sql` (`extraction_logs` table for tracking audit logs)
- [x] **M2.1.3** — `db/schema/007_unmapped_labels.sql` (`unmapped_labels` table for human-in-the-loop review)

### 2. PDF Parsing & OCR
- [x] **M2.2.1** — `services/extraction/pdf_parser.py` (PyMuPDF & pdfplumber parser + PyTesseract OCR fallback)

### 3. Table Extraction & Bounding Boxes
- [x] **M2.3.1** — `services/extraction/table_extractor.py` (pdfplumber + Camelot-py stream/lattice fallback)

### 4. Canonical Concept Mapping & Disambiguation
- [x] **M2.4.1** — `services/extraction/concept_mapper.py` (DB seed loader, exact/prefix match, RapidFuzz token sort ratio, and unmapped logging)

### 5. Document Chunking & Section Classification
- [x] **M2.5.1** — `services/extraction/chunker.py` (MDA, NOTES, AUDIT_REPORT, RISKS section classifier with token budgeting)

### 6. XBRL Parser
- [x] **M2.6.1** — `services/extraction/xbrl_parser.py` (Arelle-release wrapper + XML fallback)

### 7. Tests & Eval Suite A
- [x] **M2.7.1** — Unit tests (`test_pdf_parsing.py`, `test_tables.py`, `test_concepts.py`, `test_chunker.py`, `test_xbrl.py`, `test_active_facts_query.py`)
- [x] **M2.7.2** — Integration test (`tests/integration/test_ingestion_pipeline.py` end-to-end pipeline test)
- [x] **M2.7.3** — Eval Suite A runner (`eval/suite_a.py` and `eval/runner.py`)

---

## Detailed Task Checklist — Milestone 3 (M3: Derived & Narrative)

### 1. Database Migrations & Peer Groups Seed
- [x] **M3.1.1** — `db/schema/008_derived_metrics.sql` (`peer_groups` + `derived_metrics` tables)
- [x] **M3.1.2** — `db/schema/009_narrative_embedding_dim.sql` (`narrative_chunks.embedding` halfvec 1024)
- [x] **M3.1.3** — `db/schema/010_issuer_profile.sql` (`issuer_profile` table + HNSW vector index)
- [x] **M3.1.4** — `db/seeds/peer_groups_seed.csv` & `scripts/seed_peer_groups.py` (KBMI 4 Banks & Large Coal Miners)

### 2. Derived Metrics Engine
- [x] **M3.2.1** — `services/derive/registry.py` (`RecipeContext`, `RecipeResult`, `RecipeSpec`, `@recipe` decorator, `REGISTRY`, `FactsAccessor`, `PeersAccessor`)
- [x] **M3.2.2** — `services/derive/recipes/generic.py` (`yoy.*`, `qoq.*`, `cagr_3y.*`, `margin.gross`, `margin.operating`, `margin.net`, `debt_equity`, `current_ratio`, `roe`, `roa`)
- [x] **M3.2.3** — `services/derive/recipes/bank.py` (`bank.nim`, `bank.npl`, `bank.casa`, `bank.ldr`, `bank.coc`, `bank.bopo`, `bank.cir`)
- [x] **M3.2.4** — `services/derive/recipes/mining.py` (`mining.cash_cost`, `mining.strip_ratio`, `mining.asp`, `mining.ni_margin`)
- [x] **M3.2.5** — `services/derive/recipes/peer_percentile.py` (`peer_pct.<metric_id>` cross-sectional cohort ranking)
- [x] **M3.2.6** — `services/derive/engine.py` (`compute_for_document()`)
- [x] **M3.2.7** — `services/ingest/tasks/derive_metrics.py` (Idempotent worker task)

### 3. Narrative Memory & Embedding Engine
- [x] **M3.3.1** — `services/narrative/embedder.py` (1024-dim BGE-M3 dense embedder with deterministic fallback)
- [x] **M3.3.2** — `services/narrative/translator.py` (Indonesian to English translation utility)
- [x] **M3.3.3** — `services/ingest/tasks/embed_narrative.py` (Worker task for translating & embedding chunks)

### 4. Hybrid Retrieval for L4 Narrative
- [x] **M3.4.1** — `services/narrative/reranker.py` (Cross-encoder reranking wrapper with lexical overlap fallback)
- [x] **M3.4.2** — `services/retrieval/tokens.py` (Token counting utility)
- [x] **M3.4.3** — `services/retrieval/narrative_retriever.py` (Hybrid ANN + FTS + Reranker pipeline)

### 5. Issuer Profile (L6)
- [x] **M3.5.1** — `services/ingest/tasks/refresh_profile.py` (Profile summary builder + embedding generator)

### 6. Renderers (Compact Table Formatters)
- [x] **M3.6.1** — `services/retrieval/renderers.py` (`render_fact_rows`, `render_derived_deltas`, `render_narrative_chunks`, `render_peer_percentile_line`)

### 7. Pipeline Orchestration & Tests
- [x] **M3.7.1** — `services/ingest/tasks/ingest_document.py` (8-step ingestion orchestration pipeline)
- [x] **M3.7.2** — `services/ingest/worker.py` (WorkerSettings registering all 9 tasks)
- [x] **M3.7.3** — Unit tests (`test_generic_recipes.py`, `test_bank_recipes.py`, `test_mining_recipes.py`, `test_peer_percentile.py`, `test_hybrid_retriever.py`, `test_renderers.py`)
- [x] **M3.7.4** — Integration test (`tests/integration/test_m3_pipeline.py`)
- [x] **M3.7.5** — Eval Suite C smoke benchmark (`eval/suite_c.py`, `eval/runner.py`, `eval/manual_l4_smoketest.md`)

---

## Detailed Task Checklist — Milestone 4 (M4: Retrieval & Chat)

### 1. Database Migrations
- [x] **M4.1.1** — `db/schema/011_sessions.sql` (`chat_sessions` & `conversation_turns` with JSONB manifest/token_usage/latency)

### 2. Provider-Neutral LLM Layer (`services/llm`)
- [x] **M4.2.1** — `services/llm/types.py` (`TextBlock`, `ToolResultBlock`, `Message`, `ToolDef`, `ToolCall`, `Usage`, `LLMResponse`, `Capabilities`, `LLMClient` Protocol)
- [x] **M4.2.2** — `services/llm/errors.py` (`LLMError`, `LLMCapabilityError`, `LLMProviderError`)
- [x] **M4.2.3** — `services/llm/pricing.py` (Token cost table across Anthropic, OpenAI, DeepSeek, Moonshot)
- [x] **M4.2.4** — `services/llm/providers/anthropic.py` (`AnthropicClient` with ephemeral prompt caching and 429 retry backoff)
- [x] **M4.2.5** — `services/llm/providers/openai.py` (`OpenAIClient` with function calling)
- [x] **M4.2.6** — `services/llm/providers/openai_compat.py` (`OpenAICompatClient` supporting DeepSeek-V3, DeepSeek-R1, Moonshot, Llama)
- [x] **M4.2.7** — `services/llm/fakes.py` (`FakeLLMClient` deterministic replay with structured classifier and inline citation synthesis)
- [x] **M4.2.8** — `services/shared/config.py` & `services/llm/factory.py` (`RoleConfig` slots for reasoner, utility, judge with fallback)
- [x] **M4.2.9** — `services/llm/system_prompt.md` (System prompt with `<evidence>` tag injection immunity and mandatory disclaimer)
- [x] **M4.2.10** — `services/llm/tools.py` (`expand_evidence`, `run_screener`, `compute_metric`, `fetch_price_action`, `list_periods` handlers)

### 3. Turn Routing & Session Store
- [x] **M4.3.1** — `services/shared/types.py` (`Intent` enum and `QueryClassification` Pydantic model)
- [x] **M4.3.2** — `services/retrieval/session_store.py` (`StickyState`, `get_or_create_session`, `append_turn`, `update_sticky_state`, `recent_turns`)
- [x] **M4.3.3** — `services/retrieval/turn_router.py` (Stateful conversation transition classifier: `drill`, `pivot`, `topic_change`)

### 4. Classifier, Planner & Parallel Executor
- [x] **M4.4.1** — `services/retrieval/classifier.py` (Structured intent classifier using utility LLM with rule-based fallback)
- [x] **M4.4.2** — `services/retrieval/planner.py` (Multi-layer deterministic retrieval planner)
- [x] **M4.4.3** — `services/retrieval/executor.py` (Parallel asynchronous plan executor returning `EvidenceBundle`)

### 5. Token Budgeter & Prompt Assembler
- [x] **M4.5.1** — `services/retrieval/budgeter.py` (Token budgeter enforcing bucket caps and sidecar ID tracking)
- [x] **M4.5.2** — `services/retrieval/prompt_assembler.py` (Prompt assembler wrapping evidence in `<evidence>` tags with sticky header)
- [x] **M4.5.3** — `services/retrieval/summarizer.py` (Rolling conversation summarizer for turns > 4)

### 6. Full Chat Pipeline & Citation Endpoints
- [x] **M4.6.1** — `services/retrieval/chat.py` (`run_turn()` orchestrator with tool loops and inline citation resolution)
- [x] **M4.6.2** — `services/api/routers/chat.py` (Real `POST /api/v1/chat` endpoint)
- [x] **M4.6.3** — `services/api/pdf_render.py` (PyMuPDF bbox highlight page PNG renderer)
- [x] **M4.6.4** — `services/api/routers/citation.py` (`GET /api/v1/citation/{tag}`, `GET /api/v1/citation/{tag}/image`, `POST /api/v1/citation/report`)
- [x] **M4.6.5** — `services/api/main.py` (Registered citation router)

### 7. Frontend Evidence Inspection UI
- [x] **M4.7.1** — `web/lib/types.ts` & `web/lib/api.ts` (Added `CitationDetail`, `resolveCitation`, `reportCitation`)
- [x] **M4.7.2** **CitationChip.tsx** (Interactive citation chip badge)
- [x] **M4.7.3** **PdfPreview.tsx** (Rendered PDF thumbnail with highlight crop)
- [x] **M4.7.4** **EvidencePanel.tsx** (Right-docked sliding evidence inspection drawer with fact audit & hallucination feedback)
- [x] **M4.7.5** **ChatWindow.tsx** & `web/app/page.tsx` (Interactive chat window with seamless evidence inspection)

### 8. Evaluation & Verification Gate
- [x] **M4.8.1** — `eval/suite_b.py` (Citation Precision & Evidence Grounding Verification benchmark)
- [x] **M4.8.2** — `eval/golden/suite_c_reasoning.jsonl` (50 curated golden reasoning questions across IDX banks and miners)
- [x] **M4.8.3** — `eval/suite_c.py` & `eval/runner.py` (Complex reasoning evaluation benchmark runner)
- [x] **M4.8.4** — Unit tests (`test_llm_types.py`, `test_pricing.py`, `test_session_store.py`, `test_turn_router.py`, `test_planner.py`, `test_budgeter.py`, `test_prompt_assembler.py`, `test_tools.py`)
- [x] **M4.8.5** — Integration tests (`test_chat_e2e.py`, `test_citation_endpoint.py`)
- [x] **M4.8.6** — Strict typecheck (`mypy` clean, `tsc` clean) & lint (`ruff` clean)

---

## Detailed Task Checklist — Milestone 5 (M5: Knowledge Graph & Guidance)

### 1. KG Schemas
- [x] **M5.1.1** — `db/schema/012_kg_nodes_edges.sql` (`kg_nodes` and `kg_edges` with type constraints and indexes)

### 2. Guidance Miner
- [x] **M5.2.1** — `services/kg/types.py` (`GuidancePayload`, `CausalTriple`, `KGTriple`, `MatchReport`, `LinkReport`)
- [x] **M5.2.2** — `services/kg/guidance_miner.py` (Two-tier guidance extraction engine with high-precision regex + LLM fallback)
- [x] **M5.2.3** — `services/ingest/tasks/mine_guidance.py` (Ingestion worker task writing GUIDANCE `kg_nodes`)

### 3. Actual Matcher
- [x] **M5.3.1** — `services/kg/actual_matcher.py` (`match_actuals_for()` matching targets against realized disclosures and emitting `REALIZED_AS` / `CONTRADICTS` edges)
- [x] **M5.3.2** — `services/ingest/tasks/match_actuals.py` (Ingestion worker task matching outstanding guidance)

### 4. Causal Linker
- [x] **M5.4.1** — `services/kg/causal_linker.py` (`link_causes_for_doc()` extracting causal attribution graphs with honest 0.5–0.8 confidence)
- [x] **M5.4.2** — `services/ingest/tasks/link_causes.py` (Ingestion worker task linking causal factors)

### 5. KG Traversal & Planning Integration
- [x] **M5.5.1** — `services/kg/traversal.py` (`traverse()` recursive CTE graph traversal and `find_guidance_actual_triples()`)
- [x] **M5.5.2** — `services/retrieval/planner.py` & `services/retrieval/executor.py` (`L5Step` integration for `EXPLANATION`, `GUIDANCE_CHECK`, and `COMPARE_PEERS`)

### 6. Conversation Continuity & Last-Claim Expansion
- [x] **M5.6.1** — `services/retrieval/summarizer.py` (Rolling summary refresh with conversation context)
- [x] **M5.6.2** — `services/retrieval/executor.py` (Last-claim node traversal on `drill` turns)
- [x] **M5.6.3** — `services/retrieval/prompt_assembler.py` & `services/retrieval/renderers.py` (Guidance matrix & causal attribution block formatting)

### 7. Pipeline Orchestration & Tests
- [x] **M5.7.1** — `services/ingest/tasks/ingest_document.py` & `services/ingest/worker.py` (Full 11-step ingestion pipeline)
- [x] **M5.7.2** — Unit tests (`test_guidance_miner.py`, `test_actual_matcher.py`, `test_causal_linker.py`, `test_kg_traversal.py`)
- [x] **M5.7.3** — Integration test (`tests/integration/test_guidance_intent_e2e.py`)

---

## Detailed Task Checklist — Milestone 6 (M6: Screener & Technical Engine)

### 1. Screener DSL & Natural Language Parser
- [x] **M6.1.1** — `services/screener/dsl.py` (`Universe`, `Filter`, `Sort`, `ScreenerDSL`, `ScreenerRow`, `ScreenerResult`)
- [x] **M6.1.2** — `services/screener/parser.py` (`parse_query()` with LLM tool use and robust regex fallback)
- [x] **M6.1.3** — `services/screener/compiler.py` (`compile_to_sql()` parameterized PostgreSQL query with `INTERSECT` candidate selection)
- [x] **M6.1.4** — `services/screener/executor.py` (`execute_screener()` execution engine returning validated rows and provenance)
- [x] **M6.1.5** — `services/api/routers/screener.py` (`POST /api/v1/screener` accepting natural language or DSL payloads)
- [x] **M6.1.6** — `services/screener/renderers.py` (`render_screener_results_table()` compact table formatter with source citations)

### 2. Market Prices & yfinance Ingestion
- [x] **M6.2.1** — `db/schema/013_market.sql` (`market_prices`, `technical_state`, `technical_state_history`)
- [x] **M6.2.2** — `services/market/yfinance_ingest.py` (`ingest_prices()` downloading daily OHLCV bars with synthetic fallback)
- [x] **M6.2.3** — `scripts/backfill_market_prices.py` (CLI utility backfilling 52,200+ price bars across 50 tickers)
- [x] **M6.2.4** — `services/ingest/tasks/nightly_market.py` (Scheduled worker task for nightly price ingestion)

### 3. Technical Indicators & Regime Classification Engine
- [x] **M6.3.1** — `services/market/technical_engine.py` (`compute_indicators()` calculating SMA 20/50/200, RSI 14, MACD, Bollinger Bands, ATR 14, Volume 20d avg, 52wk range distances)
- [x] **M6.3.2** — `services/market/regime_rules.py` (`classify_regime()` deterministic 7-regime classifier: `capitulation`, `bullish_breakout`, `bullish_pullback`, `bearish_breakdown`, `bearish_bounce`, `low_volatility_squeeze`, `range_bound`)
- [x] **M6.3.3** — `services/ingest/tasks/nightly_technical.py` (Scheduled worker task computing and persisting technical states)
- [x] **M6.3.4** — `services/market/renderers.py` (`render_technical_state()` compact technical markdown formatter)
- [x] **M6.3.5** — `services/retrieval/executor.py`, `budgeter.py`, `prompt_assembler.py`, `tools.py` (`L7Step` technical execution and tool integration)

### 4. Coverage Expansion (LQ45 & Sector Recipes)
- [x] **M6.4.1** — `db/seeds/tickers_lq45.csv` & `scripts/seed_lq45_tickers.py` (50 covered tickers seeded into `issuer_profile`)
- [x] **M6.4.2** — `scripts/bulk_ingest.py` (Bulk ingestion CLI utility)
- [x] **M6.4.3** — `services/derive/recipes/cpo.py` (`cpo.price_realized`, `cpo.ffb_yield`, `cpo.cash_cost`, `cpo.oer`)
- [x] **M6.4.4** — `services/derive/recipes/telco.py` (`telco.ebitda_margin`, `telco.arpu`, `telco.capex_intensity`)
- [x] **M6.4.5** — `services/derive/recipes/insurance.py` (`insurance.rbc`, `insurance.loss_ratio`, `insurance.combined_ratio`)

### 5. Quality & Screener Evaluation Gate
- [x] **M6.5.1** — `eval/suite_screener.py` & `eval/runner.py` (Multi-criteria natural language stock screener benchmark: 100% pass rate)
- [x] **M6.5.2** — Unit tests (`test_screener_dsl.py`, `test_screener_compiler.py`, `test_technical_engine.py`, `test_regime_rules.py`, `test_sector_recipes.py`)
- [x] **M6.5.3** — Integration tests (`test_screener_endpoint.py`, `test_upload.py`)
- [x] **M6.5.4** — Strict static analysis: `ruff` 100% clean, `mypy` 158 files clean, `tsc` clean

---

## Detailed Task Checklist — Milestone 7 (M7: Polish, Auth, Observability & Production Ready)

### 1. Onboarding & Authentication Layer
- [x] **M7.1.1** — `db/schema/014_users_auth.sql` (`users` & `auth_tokens` tables applied)
- [x] **M7.1.2** — `services/api/auth.py` (Magic-link generation, verification, and `require_user` dependency)
- [x] **M7.1.3** — `web/app/login/page.tsx` (Glassmorphism magic-link login and session verification page)
- [x] **M7.1.4** — `services/api/rate_limit.py` (Redis-backed sliding-window rate limiter)

### 2. Session Persistence & History
- [x] **M7.2.1** — `services/api/routers/sessions.py` (`GET /api/v1/sessions`, `GET /api/v1/sessions/{id}/turns`, `POST /api/v1/sessions/{id}/rename`, `DELETE /api/v1/sessions/{id}`)
- [x] **M7.2.2** — `web/components/SessionSidebar.tsx` (Left navigation rail with date-grouped conversation sessions, rename, and delete)

### 3. Evidence Panel & Trace Reasoning
- [x] **M7.3.1** — `web/components/TraceReasoningDrawer.tsx` (Full multi-layer retrieval manifest & token budget breakdown)
- [x] **M7.3.2** — `db/schema/015_citation_reports.sql` & `services/api/routers/citation.py` (Auditor feedback persistence into `citation_reports`)
- [x] **M7.3.3** — `web/components/ChatWindow.tsx` (Copy answer with citations & trace button)

### 4. Coverage Expansion (KOMPAS100 Universe)
- [x] **M7.4.1** — `db/seeds/tickers_kompas100.csv` & `scripts/seed_kompas100.py` (100 covered tickers seeded into `issuer_profile`)
- [x] **M7.4.2** — `db/seeds/peer_groups_seed.csv` (Expanded peer groups for `banking_bumn`, `banking_private`, `cpo_large`, `telco_big3`, `consumer_staples`, `property_developer`)

### 5. Observability & Admin Telemetry
- [x] **M7.5.1** — `services/shared/metrics.py` (Prometheus exposition collector for turn latency, token usage, LLM expenditure, and citation reports)
- [x] **M7.5.2** — `services/api/main.py` (`GET /metrics` Prometheus endpoint)
- [x] **M7.5.3** — `services/api/routers/admin.py` (`GET /api/v1/admin/ingest` telemetry dashboard)

### 6. Operational Documentation & Runbooks
- [x] **M7.6.1** — `docs/runbook.md` (Operations runbook: concept review, recipe bump re-ingest, price outage fallback, key rotation, adding new sectors)
- [x] **M7.6.2** — Per-module architecture guides (`docs/README_RETRIEVAL.md`, `docs/README_DERIVE.md`, `docs/README_KG.md`, `docs/README_SCREENER.md`)
- [x] **M7.6.3** — `eval/reports/triage.md` (Evaluation failure triage playbook)

### 7. Tests & Verification Gates
- [x] **M7.7.1** — Unit tests (`test_auth.py`, `test_metrics.py`)
- [x] **M7.7.2** — Integration tests (`test_sessions_api.py`, `test_admin_ingest.py`)
- [x] **M7.7.3** — Full verification: 99/99 automated tests passing, 0 lint/mypy/tsc errors, 100% Screener & Citation Eval benchmarks.
