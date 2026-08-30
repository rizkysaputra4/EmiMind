# M6 — Screener + Technical + Coverage (Weeks 27–32)

**Goal:** natural-language screening works over `derived_metrics`. yfinance ingest populates `market_prices` daily; `technical_state` regime labels feed the `TECHNICAL` intent. Coverage expands from 10 to 50 tickers (LQ45).

**Prerequisite:** M5 exit gate green.

---

## 1. Screener DSL

### M6.1.1 — DSL schema
**File:** `services/screener/dsl.py`

Pydantic v2 model exactly matching BLUEPRINT §10.1:

```python
class Universe(BaseModel):
    index: Literal["IDX_ALL", "LQ45", "KOMPAS100"] | None = None
    sector: str | None = None
    sub_sector: str | None = None
    peer_group_id: str | None = None
    tickers: list[Ticker] | None = None


class Filter(BaseModel):
    metric: str  # metric_id from REGISTRY, or a concept_id (for raw fact filters)
    op: Literal[">", "<", ">=", "<=", "==", "!="]
    value: Decimal
    period_offset: int = 0  # 0 = as_of period; -1 = one quarter back


class Sort(BaseModel):
    metric: str
    dir: Literal["asc", "desc"] = "desc"


class ScreenerDSL(BaseModel):
    universe: Universe
    filters: list[Filter] = Field(min_length=1, max_length=20)
    as_of: FiscalPeriod
    sort: Sort | None = None
    limit: int = Field(default=25, ge=1, le=100)
```

Validation:
- Every `metric` referenced must exist in `REGISTRY` or in the seeded `concept_map`. Reject unknown metrics with a specific error.

### M6.1.2 — NL → DSL parser
**File:** `services/screener/parser.py`

`async parse_query(query: str) -> ScreenerDSL`.

`get_llm("utility")` with `force_tool="ScreenerDSL"` to emit the Pydantic model. System prompt includes the list of known metrics (compressed to 400 tokens via aliasing). `cache_hint=True` on the system block.

**Acceptance:**
- 10 hand-labeled NL queries in `tests/unit/test_screener_parser_fixtures.py` (via `FakeLLMClient`) each produce the expected DSL.

### M6.1.3 — SQL compiler
**File:** `services/screener/compiler.py`

`compile_to_sql(dsl: ScreenerDSL) -> tuple[str, dict[str, Any]]`.

Emits the templated query from BLUEPRINT §10.2, parameterized. Uses `INTERSECT` for AND-of-filters. Joins `issuer_profile` for sector filters, `peer_groups` for peer set filters.

**Every** filter is a bound parameter — no string interpolation of values.

### M6.1.4 — Executor
**File:** `services/screener/executor.py`

`async execute(dsl: ScreenerDSL) -> ScreenerResult`.

Returns:
```python
class ScreenerRow(BaseModel):
    ticker: Ticker
    metric_values: dict[str, Decimal]  # keyed by metric_id
    provenance: list[dict]  # {"metric": ..., "fact_ids": [...]}


class ScreenerResult(BaseModel):
    dsl: ScreenerDSL
    rows: list[ScreenerRow]
    total_matches: int  # before limit
```

**Statement timeout:** 3s.

### M6.1.5 — Screener API + tool
Rewrite the M1 stub at `services/api/routers/screener.py` to accept either `{query: str}` (parses via `parse_query`) or `{dsl: ScreenerDSL}`. Returns `ScreenerResult`.

Also wire the `run_screener` tool (M4.7.1) to `execute(...)`.

### M6.1.6 — Explanation renderer
When the LLM invokes `run_screener` in a chat turn, results come back rendered as:

```
| Ticker | ROE | PE | Reason |
|---|---|---|---|
| BMRI | 20.1% [BMRI-FS-2024Q4#p8] | 12.3 | Meets ROE>15%, PE<15 |
| BBRI | 18.8% [BBRI-FS-2024Q4#p9] | 11.2 | ... |
```

Provenance travels with each row so citations resolve.

**Acceptance:**
- End-to-end: `POST /api/v1/screener` with `{"query": "IDX banks with ROE>15%, DE<1, PE<15 as of 2024Q4"}` returns matching tickers.
- LLM-driven turn: "Find IDX banks with ROE>15%" invokes the tool, response cites source facts.
- The DB — not the LLM — decides pass/fail (unit-tested with an adversarial LLM that "wants" to include an off-list ticker).

---

## 2. yfinance ingest + market prices

### M2.1 — Market prices table
**File:** `db/schema/013_market.sql`
**Copy verbatim:** appendix-schemas.md § "013_market.sql"

Includes `market_prices` and `technical_state` + `technical_state_history` from BLUEPRINT §6.7.

### M6.2.2 — yfinance ingest
**File:** `services/market/yfinance_ingest.py`

`async ingest_prices(ticker: Ticker, since: date | None = None) -> IngestReport`.

- `yfinance.download(f"{ticker}.JK", period="max" if since is None else "1y", progress=False, threads=False)`.
- Upsert into `market_prices` on `(ticker, dt)`.
- Handle API failures: retry x3 with backoff; on giving up, log with `stale_as_of` set on `technical_state`.

CLI: `python scripts/backfill_market_prices.py --tickers=BMRI,BBRI,...`.

### M6.2.3 — Nightly cron
**File:** `services/ingest/tasks/nightly_market.py`

arq scheduled job (`cron("0 20 * * MON-FRI")` — IDX closes at ~16 WIB; run 20 WIB). Ingests all covered tickers (from `issuer_profile`).

**Acceptance:**
- Backfill of 10 tickers from 2020-01-01 populates `market_prices` with ≥ 5 × 250 rows per ticker.
- Nightly job idempotent.

---

## 3. Technical engine

### M6.3.1 — Indicator computation
**File:** `services/market/technical_engine.py`

Function: `async compute_indicators(ticker: Ticker, as_of: date) -> TechnicalStateRow`.

Uses `pandas-ta` on the last 252 trading days:
- `sma20/50/200`, `rsi14`, `macd + signal`, `bb_upper/lower`, `atr14`, `vol_avg20`, 52-week distance.

### M6.3.2 — Regime rules
**File:** `services/market/regime_rules.py`

Deterministic rules from BLUEPRINT §11.2 → `regime_label`. Also emits `trend`, `momentum`, `volatility`, `volume_regime`.

Every rule is a pure function of the indicator vector. Order matters — evaluate in the table's order; first match wins.

Unit tests for each label using synthetic OHLCV.

### M6.3.3 — Nightly compute
**File:** `services/ingest/tasks/nightly_technical.py`

arq scheduled job right after `nightly_market`. For each ticker: compute → upsert `technical_state`, insert current snapshot into `technical_state_history`.

**Acceptance:**
- After nightly runs, `SELECT regime_label, count(*) FROM technical_state GROUP BY 1` shows a plausible distribution across the 7 labels.

### M6.3.4 — `TECHNICAL` intent
Wire into planner: L7Step returns the `technical_state` row (never raw OHLCV).

Renderer emits the compact block from BLUEPRINT §11.3.

**Acceptance:**
- End-to-end: "Is BMRI breaking out?" returns the regime block + a citation-free technical summary (no PDF citations expected here).

---

## 4. Coverage expansion (10 → 50 tickers)

### M6.4.1 — Ticker roster
**File:** `db/seeds/tickers_lq45.csv`

Header: `ticker,name,sector,sub_sector,index_membership`.

Populate with LQ45 constituents (as of the milestone start). Founder is responsible for this data.

### M6.4.2 — Bulk ingest tool
**File:** `scripts/bulk_ingest.py`

CLI that reads a manifest CSV (`ticker,doc_type,fiscal_period,pdf_path,xbrl_path?`), uploads each via the API, and reports success/failure.

Founder uses this to onboard 40 more tickers across ≥ 5 quarters each.

### M6.4.3 — Concept map coverage expansion
Curate additional concept_map rows for the new sectors reached by LQ45: CPO, TELCO, INSURANCE, CONSUMER_GOODS. Aim for 1500 additional rows.

### M6.4.4 — Sector recipes (best-effort)
**Files:** `services/derive/recipes/cpo.py`, `recipes/telco.py`, `recipes/insurance.py` from BLUEPRINT §6.3 table.

At minimum: `cpo_price_realized`, `yield_per_ha`, `arpu`, `subs`, `rbc`, `combined_ratio`.

---

## 5. Screener quality gate

### M6.5.1 — Eval Suite A extension
Add 100 more Q/A pairs covering LQ45 tickers; target ≥ 99% pass.

### M6.5.2 — Screener smoke suite
**File:** `eval/suite_screener.py`

30 NL screener queries with expected `min_tickers_returned` and `must_include`/`must_exclude` sets. Passes when the SQL returns a superset of `must_include` and doesn't include `must_exclude`.

Warning-only in CI (screeners are subjective); gate on 90%.

---

## M6 exit gate

- [ ] Screener works via `POST /api/v1/screener` and as an LLM-called tool.
- [ ] All screener decisions come from Postgres (adversarial LLM test passes).
- [ ] `market_prices` populated for all 50 tickers back to 2020-01-01.
- [ ] Nightly cron runs cleanly for 3 consecutive nights.
- [ ] `TECHNICAL` intent works end-to-end.
- [ ] Coverage at 50 tickers; ingestion succeeds for at least 4 quarters per ticker.
- [ ] Eval Suite A ≥ 99% (on the 200+ Q/A corpus), Suite B == 100%, Suite C ≥ 4.0, Suite Screener ≥ 90%.
- [ ] Cost per turn (measured over a 100-turn sample) matches BLUEPRINT §14.1 within ±30%.
- [ ] `make lint`, `make typecheck`, `make test` green.
