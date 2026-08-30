# M3 — Derived Metrics + Narrative Memory (Weeks 11–14)

**Goal:** L3 (`derived_metrics`) is fully populated by a recipe registry; L4 (`narrative_chunks`) is embedded via BGE-M3 and searchable via hybrid ANN+FTS+rerank. L6 (`issuer_profile`) frame cards are generated per ticker.

**Prerequisite:** M2 exit gate green.

---

## 1. Derived metrics table + recipe registry

### M3.1.1 — Derived metrics schema
**File:** `db/schema/008_derived_metrics.sql`
**Copy verbatim:** appendix-schemas.md § "008_derived_metrics.sql"

Includes `derived_metrics` from BLUEPRINT §6.3 + `peer_groups`.

**Acceptance:** migration applies.

### M3.1.2 — Peer groups seed
**File:** `db/seeds/peer_groups_seed.csv`

Rows for MVP scope. Minimum:
- `bank_kbmi4`, name "KBMI 4 Banks", tickers `{BMRI,BBRI,BBNI,BBCA}`, sector `BANK`.
- `coal_large`, name "Large Coal Miners", tickers `{ADRO,PTBA,ITMG,HRUM,INDY,BUMI}`, sector `MINING`, sub_sector `COAL`.

Loader: `scripts/seed_peer_groups.py`.

**Acceptance:** `SELECT count(*) FROM peer_groups` = 2.

### M3.1.3 — Recipe registry
**File:** `services/derive/registry.py`

Define:
```python
class RecipeContext(BaseModel):
    ticker: Ticker
    fiscal_period: FiscalPeriod
    facts: FactsAccessor  # thin async wrapper around active_facts_query
    peers: PeersAccessor


class RecipeResult(BaseModel):
    value: Decimal | None
    unit: str
    inputs: dict[str, Any]  # {"fact_ids":[...], "formula":"(a-b)/b", "comparability_flag": bool}


Recipe = Callable[[RecipeContext], Awaitable[RecipeResult | None]]


@dataclass
class RecipeSpec:
    metric_id: str
    version: str
    sector: str | None  # None = generic
    depends_on: list[str]  # concept_ids or other metric_ids
    fn: Recipe


REGISTRY: dict[str, RecipeSpec] = {}


def recipe(
    metric_id: str, version: str, sector: str | None = None, depends_on: list[str] | None = None
):
    def deco(fn: Recipe) -> Recipe:
        REGISTRY[metric_id] = RecipeSpec(metric_id, version, sector, depends_on or [], fn)
        return fn

    return deco
```

**Discovery:** `services/derive/recipes/__init__.py` imports every module in `recipes/` so decorators fire at import time.

**Acceptance:** `from services.derive.registry import REGISTRY; print(len(REGISTRY))` prints ≥ 10 after M3.1.4/M3.1.5.

### M3.1.4 — Generic recipes
**File:** `services/derive/recipes/generic.py`

Implement (all sector-agnostic):
- `yoy.<concept_alias>` — YoY % change, needs `t` and `t-4Q`.
- `qoq.<concept_alias>` — QoQ.
- `cagr_3y.<concept_alias>` — 3-year CAGR (needs 13 quarters back).
- `margin.gross` — `(Revenue - CostOfSales) / Revenue`.
- `margin.operating` — `OperatingProfit / Revenue`.
- `margin.net` — `ProfitLoss / Revenue`.
- `debt_equity` — `Liabilities / Equity`.
- `current_ratio` — `CurrentAssets / CurrentLiabilities`.
- `roe` — `ProfitLoss / avg(Equity[t], Equity[t-1])`.
- `roa` — `ProfitLoss / avg(Assets[t], Assets[t-1])`.

Every recipe:
- Returns `None` if any input is missing (do not fabricate).
- Sets `inputs.comparability_flag = True` when spanning PSAK 71 boundary (period_end crosses 2020-01-01) or when the accounting standard on the input rows differs.

**Concept aliases** live in a module-level dict, e.g. `CONCEPT_ALIASES = {"revenue": "ifrs:Revenue", "net_profit": "ifrs:ProfitLoss", ...}`. The recipe registers as `yoy.revenue`, `yoy.net_profit`, etc.

### M3.1.5 — Bank recipes
**File:** `services/derive/recipes/bank.py`

Sector `BANK`. Implement per BLUEPRINT §6.3:
- `bank.nim` — Net Interest Income / average earning assets.
- `bank.npl` — Non-Performing Loans / Total Loans.
- `bank.casa` — (Demand + Savings) / Total Deposits.
- `bank.ldr` — Loans / Deposits.
- `bank.coc` — Impairment Charges / average Loans (Cost of Credit).
- `bank.bopo` — Operating Expenses / Operating Income.
- `bank.cir` — Cost-to-Income Ratio.

### M3.1.6 — Mining (coal) recipes
**File:** `services/derive/recipes/mining.py`

Sector `MINING`:
- `mining.cash_cost` — CashCost concept (already a fact — pass through with unit conversion if needed).
- `mining.strip_ratio` — StripRatio pass-through.
- `mining.asp` — AverageSellingPrice pass-through.
- `mining.ni_margin` — ProfitLoss / Revenue (mining-flavored margin).

### M3.1.7 — Peer percentile recipe
**File:** `services/derive/recipes/peer_percentile.py`

Special-shape recipe. Rather than one `metric_id` per concept, it emits `peer_pct.<metric_id>` for every base metric within a peer group.

Logic:
- For each peer group `pg`, for each ticker `t ∈ pg.tickers`, for each already-computed metric `m ∈ REGISTRY`:
  - Query all peers' `value_numeric` for `m` at `fiscal_period`.
  - Compute percentile of `t`'s value within the peer set.
  - Write row with `metric_id = f"peer_pct.{m}"`, `peer_group_id = pg.id`, `value_numeric = percentile`, `unit = "PCT"`.

Runs after all deterministic recipes for a period.

### M3.1.8 — Compute engine
**File:** `services/derive/engine.py`

Function: `async def compute_for_document(doc_id: UUID) -> ComputeReport`.

Logic:
1. Load the document's ticker + fiscal_period + sector.
2. Determine the set of "affected" metrics: recipes whose `depends_on` includes any `concept_id` that appears in this doc's `financial_facts`. (Cheap: query distinct concept_ids for the doc; intersect with each recipe's depends_on.) Also include recipes for the ticker's sector.
3. Sort affected recipes topologically (`depends_on` may reference other metrics).
4. For each recipe: build `RecipeContext`, await it, upsert `derived_metrics` on the unique key `(ticker, fiscal_period, metric_id, coalesce(peer_group_id,''))`.
5. After deterministic recipes, run `peer_percentile` for each peer group the ticker belongs to.
6. Emit `ComputeReport{computed: int, skipped_missing_inputs: int, errors: list[str]}`.

### M3.1.9 — Worker task
**File:** `services/ingest/tasks/derive_metrics.py`

Wraps `compute_for_document`. Idempotent (`WORKER_VERSION` bumped on any recipe change — enforce via `WORKER_VERSION = "1.0"` and a comment "bump when any recipe version changes").

**Acceptance:**
- Integration test: after M2's fixture ingestion, running the worker produces ≥ 20 rows in `derived_metrics` for the fixture ticker/period.
- `SELECT metric_id FROM derived_metrics WHERE ticker='BMRI'` includes `bank.nim`, `bank.npl`, `margin.net`, `yoy.revenue`, `peer_pct.bank.roe`, etc.
- Unit test for each generic + bank + mining recipe with hand-computed golden values.

---

## 2. Embedding + narrative memory

### M3.2.1 — Embedder module
**File:** `services/narrative/embedder.py`

Wraps BGE-M3. Options:
- `sentence-transformers`-based (simpler): `SentenceTransformer('BAAI/bge-m3', device=EMI_EMBEDDING_DEVICE)`.
- If GPU-less latency matters, use `FlagEmbedding` and quantize.

Public API:
- `class Embedder`: `__init__(model_name, device)`, `async embed(texts: list[str]) -> list[list[float]]`.
- Dimensions: 1024 for BGE-M3 full; per BLUEPRINT we store as `halfvec(768)` — **note the mismatch**. Blueprint says 768; BGE-M3 native is 1024. Reconcile: use BGE-M3 dense output truncated to 768 dims (its dense layer supports Matryoshka), OR change `halfvec(768)` to `halfvec(1024)`.

**Decision:** default to `halfvec(1024)`. Update the schema (M2.6.1) accordingly before running M3 migrations; if the DB is already populated, ship a migration that alters the column.

**Sub-task M3.2.1a — Fix vector dim**
- **File:** `db/schema/009_narrative_embedding_dim.sql`
- Alters `narrative_chunks.embedding` to `halfvec(1024)`. If existing rows have `NULL`, this is safe.

### M3.2.2 — Translator
**File:** `services/narrative/translator.py`

For chunks with `language='id'` or `'mixed'`, translate to English via `get_llm("utility")` (default Haiku 4.5; swappable per `appendix-llm-providers.md`). Batches of ~20 chunks per call. Sets `cache_hint=True` on the system message. Populates `text_en`.

**API:** `async translate(texts: list[str]) -> list[str]`.

### M3.2.3 — Embedder worker step
**File:** `services/ingest/tasks/embed_narrative.py`

New worker. `WORKER_VERSION = "1.0"`.

Behavior:
1. Find chunks for the document with `embedding IS NULL`.
2. If `text_en IS NULL` and `language != 'en'`, translate.
3. Embed using `text_en if present else text_original`.
4. Update `embedding` column.

Insert into the pipeline right after `chunk_narrative`.

**Acceptance:**
- Integration test: after ingestion, `SELECT count(*) FROM narrative_chunks WHERE embedding IS NULL` = 0.

---

## 3. Hybrid retrieval for L4

### M3.3.1 — Reranker module
**File:** `services/narrative/reranker.py`

Wraps `bge-reranker-v2-m3` via `FlagEmbedding`. Public API:
- `async rerank(query: str, candidates: list[str]) -> list[float]` — returns scores aligned with input order.

### M3.3.2 — L4 hybrid retriever
**File:** `services/retrieval/narrative_retriever.py`

Function: `async retrieve_narrative(query: str, filters: NarrativeFilters, top_k: int = 6) -> list[NarrativeHit]`.

`NarrativeFilters`:
```python
class NarrativeFilters(BaseModel):
    tickers: list[Ticker]
    periods: list[FiscalPeriod] | None = None  # None = last 8 quarters
    sections: list[str] | None = None  # e.g. ["MDA","GUIDANCE"]
```

`NarrativeHit`: chunk row + `rerank_score`.

Algorithm (BLUEPRINT §8.5):
1. SQL prefilter: rows matching filters, ordered by recency, top 200.
2. On the prefilter set, run in parallel:
   - **ANN top-40:** `ORDER BY embedding <=> :query_vec LIMIT 40`.
   - **FTS top-40:** `WHERE tsv @@ websearch_to_tsquery(:query) ORDER BY ts_rank_cd(tsv, ...) LIMIT 40`.
3. Union, dedupe by chunk_id → up to 80 candidates.
4. Rerank via BGE reranker on `text_en` (or `text_original` if English).
5. Return top 6 by rerank score.

**Statement timeout** on the ANN query: 500ms (with HNSW should be tens of ms; this catches pathologies).

**Acceptance:**
- Unit test: mock DB rows, verify union-and-rerank flow.
- Integration test: after M2/M3 ingestion of the BMRI fixture, `retrieve_narrative("net interest margin drivers", filters=[BMRI])` returns 6 hits, at least 3 from `section='MDA'`.

---

## 4. Issuer profile (L6)

### M3.4.1 — Issuer profile schema
**File:** `db/schema/010_issuer_profile.sql`
**Copy verbatim:** appendix-schemas.md § "010_issuer_profile.sql"

### M3.4.2 — Profile builder
**File:** `services/ingest/tasks/refresh_profile.py`

`WORKER_VERSION = "1.0"`.

Behavior:
1. Compute a hash of the top-20 metrics for the ticker (canonical list per sector). If unchanged from last refresh, skip.
2. Assemble a prompt for `get_llm("reasoner")`:
   - Ticker, name, sector.
   - Last 8 quarters of core metrics as markdown table.
   - Last 10 material events (from `recent_events` — MVP: empty; M5 will populate).
3. Request `profile_summary_en` of 400–800 tokens.
4. Embed the summary via BGE-M3.
5. Upsert `issuer_profile`.

**Acceptance:**
- After ingestion, `SELECT profile_summary_en FROM issuer_profile WHERE ticker='BMRI'` returns non-empty text mentioning the latest period.
- Re-running with no new data is a no-op (`refresh_recipe_ver` unchanged, hash unchanged).

---

## 5. Renderers (compact table formatters)

### M3.5.1 — Table renderers
**File:** `services/retrieval/renderers.py`

Pure functions taking DB rows and emitting compact markdown per BLUEPRINT §8.4. Every renderer includes citations.

Functions:
- `render_fact_rows(rows) -> str` — one markdown table.
- `render_derived_deltas(rows) -> str` — YoY / QoQ compact.
- `render_narrative_chunks(hits, budget_tokens) -> str` — trimmed to fit token budget.
- `render_peer_percentile_line(ticker, metric, value, peer_group) -> str` — the one-line percentile summary.

Each renderer uses `services/retrieval/tokens.py:count_tokens()` to size-check and trim.

**Never** emit numbers without an inline citation `[TICKER-DOCTYPE-PERIOD#pPAGE]`.

**Acceptance:**
- Unit tests verify each renderer produces a citation for every numeric row and stays under the requested token cap.

---

## M3 exit gate

- [ ] Recipe registry has ≥ 20 recipes (generic + bank + mining + peer percentile).
- [ ] After ingesting a filing, `derived_metrics` gains rows for the affected metrics, including `peer_pct.*` rows.
- [ ] `narrative_chunks.embedding` populated for all M2-covered docs (no NULLs).
- [ ] Hybrid retriever returns high-quality hits on 5 hand-tested queries (founder-judged pass/fail; log to `eval/manual_l4_smoketest.md`).
- [ ] Issuer profile summaries generated for the 10 covered tickers.
- [ ] Renderers emit citations for every number; token budget enforced.
- [ ] Suite A still ≥ 95%; a new **Suite C smoke** (5 hand-graded questions) shows the retrieved chunks are relevant to the query.
- [ ] `make lint`, `make typecheck`, `make test` green.
