# M9 — Deep Extraction Remediation

**Goal:** move from shallow headline extraction (~30 top-level concepts per ticker, fabricated segments, boilerplate narratives, wrong periods) to grounded, note-level extraction. Every number is traceable to a parsed table cell or page text on a physical PDF page.

**Design doc:** [`docs/DEEP_EXTRACTION_REMEDIATION_PLAN.md`](../docs/DEEP_EXTRACTION_REMEDIATION_PLAN.md). Read it before starting any task. If this file and the design doc disagree, **the design doc wins**: stop and flag the conflict.

**Conventions:** [`tasks/00-conventions.md`](00-conventions.md) applies to everything here. In particular:
- migrations are forward-only
- unit tests use no DB and no network
- integration tests are marked `@pytest.mark.integration`
- workers are idempotent via `worker_runs`
- ingestion makes no LLM calls
- facts with confidence below 0.7 are quarantined

**Definition of done for M9:** `uv run python eval/deep_extraction_gate.py --tickers BMRI,LSIP` exits `0`. That script checks every threshold in design doc §Phase 6.

---

## How to work this file (for the AI builder)

1. **Work tasks in order.** Only tasks marked `Parallel-safe with:` may be interleaved.
2. **A task is done only when every command under "Done when" passes, run by you, in this repo.** "It compiles" or "the code looks right" is not done. Paste the command output summary into the commit message body.
3. **Global gates for every task** (in addition to its own checks):
   ```bash
   uv run ruff check .
   uv run mypy services eval
   uv run pytest -m "not integration" tests/
   ```
   None of these may regress. Integration tests need the local stack: run `make up && make migrate && make seed` first, then `uv run pytest -m integration tests/integration/<file>`.
4. **Commit per task:** `M9.x.y: <what>`, with the attribution lines from your session instructions.
5. **Test fixtures.** Unit tests must not depend on real IDX PDFs. Build synthetic PDFs with PyMuPDF in `tests/fixtures/m9/build_fixtures.py` (task M9.0.2). Real filings are used only by integration and eval tasks, located via env var `EMI_REPORTS_DIR` (default `../EmiMind-Extraction/incoming_reports`). Never commit real filings.
6. **If blocked** (missing table, ambiguous design, a test you cannot make pass honestly), stop and ask. Do not weaken an assertion to make it pass.

### Status legend
- `[ ]` not started · `[/]` in progress · `[x]` done

Each task has: **Files**, **Depends on**, **What**, **Target**, **Done when**.

---

## Phase 0 — Baseline & fixtures

### M9.0.1 — Snapshot pre-remediation metrics
- [x] **Files:** `scripts/m9_baseline_snapshot.py` (new), `eval/reports/m9_baseline.json` (generated, committed)
- **Depends on:** none. **Must run before M9.1.6 (reset).** After the reset this data is gone.
- **What:** Query the current DB and write a JSON with, per ticker in `issuer_profile` that has facts:
  - `distinct_concepts`: `count(DISTINCT concept_id)` from `financial_facts`
  - `segmented_facts`: count of facts where `segment IS NOT NULL`
  - `narrative_total`, `narrative_distinct_text`: count vs `count(DISTINCT md5(text_original))` from `narrative_chunks`
  - `documents`, `docs_with_page_count_1`, `docs_with_period_end_2024_12_31`

  Also write global totals.
- **Target:** a frozen baseline that M9.6's "≥ 2× baseline concepts" check can compare against.
- **Done when:**
  - `uv run python scripts/m9_baseline_snapshot.py --out eval/reports/m9_baseline.json` exits 0.
  - The JSON contains keys `BMRI` and `LSIP`, each with all six fields as integers.
  - `global.documents` equals `SELECT count(*) FROM documents`, checked with `psql` or a one-line Python query.

### M9.0.2 — Synthetic PDF fixture builder
- [x] **Files:** `tests/fixtures/m9/build_fixtures.py` (new), `tests/fixtures/m9/*.pdf` (generated at test time into `tmp_path`, not committed), `tests/unit/test_m9_fixtures.py` (new)
- **Depends on:** none. **Parallel-safe with:** M9.0.1, M9.1.*
- **What:** Pytest fixtures (session-scoped) that generate, with PyMuPDF:
  1. `fs_small.pdf`, 8 pages:
     - p1 cover: "PT Contoh Tbk — Laporan Keuangan 31 Desember 2025"
     - p2 balance sheet: a **ruled** table with header "(Dalam jutaan Rupiah)", columns `Catatan | 31 Des 2025 | 31 Des 2024`, rows Jumlah aset / Jumlah liabilitas / Jumlah ekuitas where A = L + E holds for both years
     - p3 income statement
     - p4 cash flow
     - p5 note "12. KREDIT YANG DIBERIKAN": collectibility × segment matrix table
     - p6 the same note continued, header "12. KREDIT YANG DIBERIKAN (lanjutan)", with the total row
     - p7 MD&A narrative text with issuer-specific numbers
     - p8 a **borderless** (whitespace-aligned) cash-per-bank table
  2. `scanned.pdf`, 2 pages: each page is only an embedded raster image of rendered text (no text layer).
  3. `bilingual.pdf`, 1 page: two columns, Indonesian left and English right, of the same balance-sheet heading and rows.

  Also add a fixture exposing the **ground-truth values** (dict of concept → value per year, plus the page index of each module) so later tests assert against it.
- **Target:** deterministic fixtures that every M9 unit test can reuse.
- **Done when:**
  - `uv run pytest tests/unit/test_m9_fixtures.py -q` passes, asserting:
    - `fs_small.pdf` has 8 pages
    - `page.get_text()` of p2 contains `Jumlah aset`
    - every page of `scanned.pdf` returns fewer than 50 non-whitespace chars from `get_text()`
    - the ground-truth dict satisfies A = L + E

---

## Phase 1 — Period, metadata, commit-path fixes, reset

### M9.1.1 — `resolve_fiscal_period` pure function
- [x] **Files:** `services/mcp/periods.py` (new), `tests/unit/test_periods.py` (new)
- **Depends on:** none
- **What:** `resolve_fiscal_period(filename: str, hint: str | None = None) -> ResolvedPeriod | None`, where `ResolvedPeriod` is a Pydantic model with `fiscal_period` (e.g. `2025Q2`), `period_end: date` and `source: Literal['hint','downloader_prefix','filename_tokens']`.
  - **Precedence:**
    1. an explicit `hint` (validated against grammar `^\d{4}Q[1-4]$`; `YYYYFY` accepted and normalized to `YYYYQ4`)
    2. the downloader prefix `^{TICKER}_{YYYY}_{TOKEN}_`, where TOKEN ∈ `TW1|TW2|TW3|AUDIT|ANNUAL`
    3. free filename tokens, using the mapping table in design doc §1.2
  - **Full-year filings map to `YYYYQ4`.** Returns `None` when year or period cannot be determined. Never defaults.
  - Also expose `period_end_for(fiscal_period) -> date`.
- **Target:** single source of truth for period parsing, reused by `inspect_document` and `commit_verified_report`.
- **Done when:** `uv run pytest tests/unit/test_periods.py -q` passes with a table-driven test of at least these cases (filename → expected):

  | Filename | Expected |
  |---|---|
  | `BMRI_2020_TW1_RDF_FinancialStatement-2020-I-BMRI.pdf` | `2020Q1`, 2020-03-31 |
  | `BMRI_2021_TW2_RDF_PT Bank Mandiri Tbk_Ind_30 Juni_2021.pdf` | `2021Q2` |
  | `BMRI_2025_TW3_RDF_LKFS Bank Mandiri 30 Sept 2025 FINAL.pdf` | `2025Q3`, 2025-09-30 |
  | `BMRI_2024_AUDIT_RDF_FinancialStatement-2024-Tahunan-BMRI.pdf` | `2024Q4`, 2024-12-31 |
  | `LSIP_2025_ANNUAL_AAR_AnnualReport2025-LSIP-att1.pdf` | `2025Q4` |
  | `202603_ULTJ_Group_Q1_FR.pdf` | `2026Q1` |
  | `LSIP_bilingual_30_Jun_2026_Released.pdf` | `2026Q2` |
  | `Financial Statements 1H26.pdf` | `2026Q2` |
  | `Laporan Keuangan TBP 30 Juni 2026.pdf` | `2026Q2` |
  | `LSIP_bilingual_31 des_2025_released.pdf` | `2025Q4` |
  | `FinancialStatement-2022-III-XXXX.pdf` | `2022Q3` |
  | `Annual Report 2025.pdf` | `2025Q4` |
  | `random_scan.pdf` | `None` |
  | hint `2023FY` + any filename | `2023Q4`, source `hint` |
  | hint `2023Q5` | raises `ValueError` |

  Also: `grep -n "2024Q4\|2024-12-31" services/mcp/periods.py` returns nothing.

### M9.1.2 — Real metadata in `inspect_document`
- [x] **Files:** `services/mcp/server.py` (`inspect_document`), `services/mcp/types.py` (add `InspectionStatus.NEEDS_METADATA`), `tests/unit/test_mcp_server.py`
- **Depends on:** M9.1.1, M9.0.2
- **What:**
  - Replace the `fp_clean` expression at `server.py:294` with `resolve_fiscal_period(p.name, fiscal_period)`.
  - If that returns `None`, try `services/extraction/metadata_extractor.propose_metadata` (period only). If still unresolved, return `status=NEEDS_METADATA` with a message telling the agent to pass `fiscal_period`, and log `action='NEEDS_METADATA'` to `document_processing_log`. Do **not** register the document.
  - In the `INSERT INTO documents`, replace the literals `'2024-12-31'` and `1` with the bound params `:period_end` (from the resolver) and `:page_count` (`pymupdf.open(p).page_count`).
- **Target:** zero documents registered with a guessed period or fake page count.
- **Done when:**
  - `grep -nE "'2024-12-31'|\"2024Q4\"" services/mcp/server.py` returns nothing.
  - New unit tests (DB layer mocked the way existing `test_mcp_server.py` tests do) pass:
    - `fs_small.pdf` renamed `XXXX_2025_TW2_RDF_x.pdf` → insert params have `period_end=date(2025,6,30)`, `page_count=8`
    - `random_scan.pdf` with no hint and the metadata extractor mocked to return nothing → status `NEEDS_METADATA`, no INSERT executed
  - Integration (`tests/integration/test_m9_inspect.py`, marked): after inspecting the renamed fixture, `SELECT period_end, page_count, fiscal_period FROM documents WHERE id = :doc_id` returns `(2025-06-30, 8, '2025Q2')`.

### M9.1.3 — Migration 022: full-segment fact uniqueness
- [x] **Files:** `db/schema/022_fact_segment_uniqueness.sql` (new); `services/mcp/server.py`, `services/ingest/tasks/normalize_facts.py`, `services/ingest/tasks/xbrl_sidecar.py` (update their `ON CONFLICT` targets); `tests/integration/test_m9_fact_uniqueness.py` (new)
- **Depends on:** none. **Parallel-safe with:** M9.1.1, M9.1.2
- **What:**
  - Drop `ux_financial_facts_ticker_period_concept_seg`.
  - Create `ux_financial_facts_identity ON financial_facts (ticker, fiscal_period, concept_id, (coalesce(segment, '{}'::jsonb))) WHERE is_restated = false`.
  - Update **all three** `ON CONFLICT` clauses to the new expression.
- **Target:** multi-dimensional segments no longer overwrite each other.
- **Done when:**
  - `make migrate` applies cleanly on a fresh DB and on the current DB.
  - `grep -rn "segment->>'segment'" services/ --include=*.py` returns nothing.
  - The integration test inserts two facts with the same concept and segments `{"collectibility":"Lancar","segment":"Korporasi"}` and `{"collectibility":"Lancar","segment":"UMKM"}` → 2 rows. Re-inserting the first with a new value → still 2 rows, value updated.

### M9.1.4 — Commit path: no invented segments, explicit statement/period type, honest provenance
- [x] **Files:** `services/mcp/types.py` (`ExtractedFactItem`: add `statement: Literal['BS','IS','CF','EQ','NOTE']`, keep `bbox`), `services/mcp/server.py` (`commit_verified_report`), `services/mcp/validator.py` (reject a missing or invalid `statement`), `tests/unit/test_mcp_server.py`, `tests/unit/test_mcp_validator.py`
- **Depends on:** M9.1.1, M9.1.3
- **What:**
  1. **Delete** the label-keyword segment inference block (the `generic_labels` and `seg_type` heuristics). `segment` is stored exactly as submitted, or `NULL`.
  2. **Delete** the substring statement-type guessing. Use `f.statement`.
  3. `period_type`: look up `metric_definitions.flow_stock_type` for `concept_id` (`STOCK_*` → `instant`, `FLOW_*` → `duration_ytd`); otherwise use the submitted value. Map `duration_q` → `duration_qtd`. Anything not in the DB CHECK set → validator ERROR.
  4. `period_end` = `period_end_for(fiscal_period)`. An unparseable period raises, and the commit is rejected (no `2024` fallback).
  5. Persist `source_bbox` from `f.bbox`. Set `extraction_method='llm_extract'`, `extraction_conf=0.75`. (M9.4.3 upgrades grounded facts to `table_parser`.)
- **Target:** the server never fabricates or reclassifies agent data.
- **Done when:**
  - `grep -nE "generic_labels|seg_type|\"Cash\", \"Loans\"|else 2024" services/mcp/server.py` returns nothing.
  - Unit tests pass:
    - a fact with no segment and label `Beban pupuk` → INSERT param `seg` is `None`
    - a fact `ifrs:CashFlowsFromOperatingActivities` with `statement='CF'` → `statement='CF'` and `period_type='duration_ytd'`
    - a payload missing `statement` → validator report `INVALID`, category `SCHEMA`
    - `fiscal_period='XXXX'` → commit returns an error and executes no INSERT
    - a submitted `bbox` is present in the INSERT params as JSON
  - Existing tests in `tests/unit/test_mcp_*.py` still pass (update fixtures in `_mcp_contract_fixtures.py` to include `statement`).

### M9.1.5 — Single reset path
- [x] **Files:** `scripts/clean_documents.py` (delete), `scripts/reset_extraction_data.py` (add `document_pages`, `document_page_tables` to `EXTRACTION_TABLES` once M9.2.1 lands; guard with `IF EXISTS`), `README.md`/`docs/runbook.md` (any reference to `clean_documents.py`)
- **Depends on:** none
- **What:** Remove the second reset script so there is exactly one documented reset.
- **Done when:**
  - `test ! -e scripts/clean_documents.py` succeeds.
  - `grep -rn "clean_documents" --include=*.md --include=*.py . | grep -v "^./.venv"` returns nothing, except this task file and the design doc's historical note.
  - `uv run python scripts/reset_extraction_data.py --help` exits 0.

### M9.1.6 — Reset the data
- [ ] **Files:** none (operation)
- **Depends on:** M9.0.1 (baseline saved), M9.1.2, M9.1.3, M9.1.4 merged
- **What:** `uv run python scripts/reset_extraction_data.py --yes`.
- **Done when:**
  - `SELECT count(*) FROM financial_facts` = 0 and `SELECT count(*) FROM documents` = 0.
  - `SELECT count(*) FROM metric_definitions` > 0 and `SELECT count(*) FROM issuer_profile` > 0 (config preserved).
  - `eval/reports/m9_baseline.json` still exists and is committed.

**Phase 1 exit:** inspecting any real filing under `EMI_REPORTS_DIR/BMRI/processed/` registers a correct `fiscal_period`, `period_end` and `page_count`. Spot-check 5 files across TW1/TW2/TW3/AUDIT/ANNUAL with a SQL query.

---

## Phase 2 — Page index

### M9.2.1 — Migration 023: `document_pages` + `document_page_tables`
- [ ] **Files:** `db/schema/023_document_pages.sql` (new, verbatim from design doc §Phase 2, guarded on the `vector` extension exactly like `007`/`009`)
- **Depends on:** M9.1.3
- **Done when:**
  - `make migrate` succeeds on a fresh DB and is re-runnable (idempotent `IF NOT EXISTS`).
  - `\d document_pages` shows `tsv` generated with `to_tsvector('simple', ...)`, `UNIQUE (doc_id, page_index)`, the GIN index and the HNSW index.
  - `\d document_page_tables` shows `UNIQUE (doc_id, page_index, table_index)`.
  - Deleting a `documents` row cascades to both tables (integration test `tests/integration/test_m9_pages_schema.py`).

### M9.2.2 — Page indexer: text, OCR fallback, images
- [ ] **Files:** `services/ingest/tasks/index_pages.py` (new, `WORKER_VERSION = "1.0"`), `services/extraction/page_quality.py` (new: `needs_ocr(text) -> bool`), `tests/unit/test_page_quality.py`, `tests/integration/test_m9_index_pages.py`
- **Depends on:** M9.2.1, M9.0.2
- **What:** `index_pages_task(ctx, doc_id)`:
  1. Check `worker_runs` for `(doc_hash, 'index_pages', WORKER_VERSION)`; skip if `ok`.
  2. Load the PDF from MinIO, then `parse_pdf` for per-page text and language.
  3. Per page, if `needs_ocr(text)` (fewer than 50 non-whitespace chars, or more than 30% non-printable/replacement glyphs), use `ocr_page(pdf_bytes, n, 'ind+eng')` and set `text_source='ocr'`.
  4. Render 150 DPI WebP and upload to `thumbnails/{doc_id}/page_{page_index}.webp`.
  5. Detect the printed page label (a standalone number or roman numeral in the top/bottom 8% of the page) and store it in `page_label` (nullable).
  6. Upsert rows into `document_pages` with `page_index` 1-based and `embedding` NULL.

  Register the task in the worker, and have `inspect_document` enqueue it for `AUTHORIZED` documents.
- **Target:** every authorized document has one `document_pages` row per physical page, including scanned pages.
- **Done when:**
  - Unit: `needs_ocr('')` is True; `needs_ocr('Jumlah aset 1.234.567')` is False; the `scanned.pdf` fixture page text gives True.
  - Integration, on `fs_small.pdf`:
    - `SELECT count(*) FROM document_pages WHERE doc_id=:id` = 8
    - `min(page_index)=1`, `max(page_index)=8`
    - every `image_key` exists in MinIO
  - Integration, on `scanned.pdf` (skip if `tesseract` is not on PATH, with a printed reason):
    - both rows have `text_source='ocr'`
    - `length(page_text) > 50`
  - Running the task twice creates no duplicate rows and records one `worker_runs` row with status `ok`.

### M9.2.3 — Table grids at index time
- [ ] **Files:** `services/ingest/tasks/index_pages.py` (extend) or `services/ingest/tasks/index_page_tables.py` (new), `services/extraction/tables.py` (add a helper returning per-table `unit_hint` and parsed cell `value`s), `tests/unit/test_tables.py` (extend), `tests/integration/test_m9_index_pages.py` (extend)
- **Depends on:** M9.2.2
- **What:**
  - For each `pdf_text` page, run the existing `extract_tables` cascade.
  - Store each table in `document_page_tables` with `cells` = `[{row, col, text, value: parse_numeric_value(text) or null, bbox, confidence}]` and `unit_hint = detect_unit_from_header(<page header text>)`.
  - OCR pages get no grid.
- **Target:** digits come from the parser, not the model.
- **Done when:**
  - Unit (runs `extract_tables` directly on the fixture, no DB), `fs_small.pdf` p2:
    - at least one table
    - a cell with text containing `Jumlah aset` exists, and the numeric cell in the same row, current-year column, has `value` equal to the ground-truth total assets (in millions)
    - `unit_hint` indicates millions
  - Unit: p8 (borderless) yields a table via `camelot_stream` or `pdfplumber` with every bank row's `value` matching ground truth.
  - Unit: the `parse_numeric_value` cases `"(12.345)" → -12345`, `"1.234.567,89" → 1234567.89` and `"-" → 0.0` pass (existing behaviour, keep it covered).
  - Integration: `SELECT count(*) FROM document_page_tables WHERE doc_id=:id AND page_index=2` ≥ 1, and `cells` is a JSON array whose elements all have the keys `row, col, text, value, bbox`.

### M9.2.4 — Embedding backfill worker
- [ ] **Files:** `services/ingest/tasks/embed_pages.py` (new, `WORKER_VERSION="1.0"`), `scripts/backfill_page_embeddings.py` (new: `--tickers`, `--limit`, `--priority lighthouse,lq45,all`), `tests/integration/test_m9_embed_pages.py`
- **Depends on:** M9.2.2
- **What:**
  - Batch (default 32 pages) through `services.narrative.embedder.Embedder`, writing `embedding` only where it is NULL.
  - Resumable: a crash mid-run loses at most one batch.
  - Log pages/sec to stdout.
  - The device comes from `EMI_EMBEDDING_DEVICE`, not code.
- **Target:** embeddings backfill in the background without blocking FTS routing.
- **Done when:**
  - Integration, with the embedder in its deterministic-hash test mode if one exists (`_deterministic_hash_embedding`), otherwise the real model:
    - after the run, `SELECT count(*) FROM document_pages WHERE doc_id=:id AND embedding IS NULL` = 0
    - a second run makes 0 embed calls (assert via a counter or mock)
  - `uv run python scripts/backfill_page_embeddings.py --tickers BMRI --limit 1` completes on a real indexed document and prints a pages/sec figure.

**Phase 2 exit:** index the two lighthouse documents (M9.6.1 lists them). Every page has text, both have table grids on their statement pages, and embeddings are complete.

---

## Phase 3 — Router

### M9.3.1 — Module query table in the contract
- [ ] **Files:** `db/seeds/page_router_queries.yaml` (new), `services/mcp/contracts.py` (load it; attach `route_query` per module), `services/mcp/types.py` (`GranularNoteModule.route_query: RouteQuery | None`, plus core modules `BALANCE_SHEET`, `INCOME_STATEMENT`, `CASH_FLOW`, `MDA`), `tests/unit/test_mcp_contracts.py`
- **Depends on:** none. **Parallel-safe with:** Phase 2
- **What:**
  - YAML keyed by module name, then sector (`ALL` default, overridable per sector). Fields: `terms_id`, `terms_en`, `max_pages` (default 6), `anchor_patterns` (optional note-heading regexes such as `KREDIT YANG DIBERIKAN`, used only as an FTS boost, never as the sole mechanism).
  - Seed it with the 9 modules from design doc §Phase 3.
- **Done when:**
  - Unit: `build_extraction_contract` for a BANK issuer includes the `BANK_LOANS_NPL` module with non-empty `terms_id` and `terms_en`.
  - Unit: for a PLANTATION issuer it includes `PLANTATION_AREA`.
  - Unit: every module in the YAML has both term lists non-empty (schema test).

### M9.3.2 — `page_router.py` with RRF
- [ ] **Files:** `services/retrieval/page_router.py` (new), `tests/unit/test_page_router.py` (new, pure RRF/expansion logic), `tests/integration/test_m9_page_router.py`
- **Depends on:** M9.2.2, M9.2.3, M9.3.1
- **What:** `route_pages(conn, doc_id, route_query, top_k) -> list[RoutedSpan]`:
  - FTS leg: `ts_rank_cd(tsv, websearch_to_tsquery('simple', ...))` over the ID+EN terms, top 40.
  - ANN leg: `embedding <=> :q_vec`, top 40, skipped when the doc has NULL embeddings.
  - Fuse with **RRF** `Σ 1/(60+rank)`.
  - Expand each of the top-k seeds by ±1 page, then continue forward while `is_continuation(prev, next)` holds: the next page's header has `(lanjutan)`/`(continued)` or the same note number, and it has no new note heading. Cap at `max_pages`.
  - Merge overlapping spans.
  - Set `statement_timeout` to 5s.

  Pure functions (`rrf_fuse`, `is_continuation`, `merge_spans`) live in the module and are unit-tested without a DB.
- **Target:** a small, correct page span per module.
- **Done when:**
  - Unit: `rrf_fuse([[3,1,2],[1,4]])` ranks page 1 first.
  - Unit: `is_continuation` is True for a p5 → p6 header pair from the fixture and False for p4 → p5.
  - Unit: `merge_spans([(5,6),(6,8)]) == [(5,8)]`.
  - Integration on `fs_small.pdf`:
    - the `BANK_LOANS_NPL` query returns a span covering **both p5 and p6**
    - `BALANCE_SHEET` returns a span containing p2
    - `CASH_BANKS` returns p8
  - Integration: with all embeddings set to NULL, the same three assertions still pass (FTS-only mode).
  - Integration, on `bilingual.pdf`: an English-only query finds p1.

### M9.3.3 — `get_routed_pages` MCP tool
- [ ] **Files:** `services/mcp/server.py` (new tool), `services/mcp/types.py` (`RoutedPages`, `RoutedPage`, `PageTable`), `tests/unit/test_mcp_server.py`
- **Depends on:** M9.3.2
- **What:**
  - Signature: `get_routed_pages(doc_id: str, module: str, top_k: int = 3) -> RoutedPages`.
  - Each `RoutedPage` has: `page_index`, `page_label`, `text_source`, `score`, `page_text`, `image_url` (presigned MinIO URL) and `tables: list[PageTable]` (from `document_page_tables`, including `table_index`, `unit_hint`, `cells`).
  - Unknown module → a clear error listing the valid modules.
  - Log the call to `document_processing_log` with `action='ROUTED'` and `metadata={module, pages}`.
- **Done when:**
  - Unit tests with a mocked router/DB pass:
    - response schema is complete
    - an unknown module returns an error containing a valid module name
    - `tables[0].cells[0]` has `value` and `bbox`
  - Manual smoke test via the MCP client on the indexed BMRI lighthouse doc: `get_routed_pages(<doc_id>, "BALANCE_SHEET")` returns pages whose `page_text` contains `Jumlah aset` or `Total assets`. Record the page numbers in the commit message.

### M9.3.4 — Router gold set + recall eval
- [ ] **Files:** `eval/router_gold/BMRI_2025Q4.yaml`, `eval/router_gold/LSIP_2025Q4.yaml` (new), `eval/router_recall.py` (new), `eval/reports/router_recall.json` (generated)
- **Depends on:** M9.3.2, lighthouse docs indexed (Phase 2 exit)
- **What:**
  - Hand-label, by opening the PDFs, the correct physical page span per module: the 9 modules for each ticker where applicable, about 50 labels total. Format: `{file: <basename>, modules: {BALANCE_SHEET: [6,7], BANK_LOANS_NPL: [228,229,230], ...}}`. Labelling is the builder's job: open the PDF and verify each page. Do not derive labels from the router's own output.
  - `router_recall.py` runs `route_pages` per module and computes **recall@k** = |gold ∩ returned| / |gold| per module, plus the mean. It writes the JSON report.
- **Target:** ≥ 90% mean recall on core statements and ≥ 80% on notes (design doc §Phase 6).
- **Done when:**
  - Both YAMLs exist, with at least 20 labelled modules combined.
  - `uv run python eval/router_recall.py --gold eval/router_gold/ --out eval/reports/router_recall.json` exits 0 only if the thresholds are met, and prints a per-module table.
  - If the thresholds are not met, fix the queries or expansion and re-run. Record the misses and their causes in the report's `notes`.

---

## Phase 4 — Grounded extraction & validator

### M9.4.1 — `cell_ref` on facts
- [ ] **Files:** `services/mcp/types.py` (`ExtractedFactItem.cell_ref: CellRef | None` with `table_index`, `row`, `col`), `tests/unit/test_types.py`
- **Depends on:** M9.3.3
- **Done when:** a payload with `cell_ref` round-trips through `DraftSubmissionPayload.model_validate`, and one without it still validates (it is optional).

### M9.4.2 — Validator evidence input + grounding rules
- [ ] **Files:**
  - `services/mcp/validator.py`: new param `evidence: dict[int, PageEvidence] | None`. `PageEvidence` = `{text_source, page_text, tables}`. The validator stays pure, with no DB access.
  - `services/mcp/grounding.py` (new): number normalization and matching.
  - `services/mcp/server.py`: `submit_draft_extraction` loads evidence for every cited `source_page` and passes it in.
  - `tests/unit/test_mcp_validator.py`, `tests/unit/test_grounding.py`
- **Depends on:** M9.4.1
- **What** (design doc §Phase 5, rules 3–4):
  - **Provenance:** `1 ≤ source_page ≤ page_count`, and the page exists in evidence. Otherwise ERROR `PROVENANCE`.
  - **Cell-grounded:** the cell at `cell_ref` exists, and `cell.value × scale == value_numeric` within ±1 unit of scale. Otherwise ERROR `GROUNDING_CELL`.
  - **Text-grounded:** without `cell_ref` on a `pdf_text` page, the unscaled number must match in `page_text` after normalization (`.`/`,` separators, parentheses negatives, trailing `,00`). Otherwise ERROR `GROUNDING_TEXT`, with `target_pages=[source_page]`.
  - **OCR page:** no grid match required. A miss gives WARNING `GROUNDING_OCR` and marks the fact `needs_review`.
  - Scale comes from the table's `unit_hint`, falling back to the contract's `scaling_rules`.
- **Done when:** `uv run pytest tests/unit/test_grounding.py tests/unit/test_mcp_validator.py -q` passes, with cases:
  - `normalize_candidates("1.234.567")` contains 1234567; `"(12.345)"` gives -12345; `"1,234,567"` gives 1234567
  - a correct cell_ref plus millions scale → no issues
  - a cell_ref with one digit transposed → `GROUNDING_CELL` ERROR
  - a text fact whose number is absent from the page → `GROUNDING_TEXT` ERROR
  - the same fact on an OCR page → `GROUNDING_OCR` WARNING and report status `VALID`
  - `source_page = page_count + 1` → `PROVENANCE` ERROR

### M9.4.3 — Commit uses grounding result
- [ ] **Files:** `services/mcp/server.py` (`commit_verified_report`), `tests/unit/test_mcp_server.py`
- **Depends on:** M9.4.2, M9.1.4
- **What:**
  - Re-run validation with evidence at commit time; never trust the draft blindly.
  - Cell-grounded facts get `extraction_method='table_parser'` and `extraction_conf=min(table.confidence, cell.confidence)`, and `source_bbox` is set from the cell bbox.
  - Text-grounded facts get `llm_extract` and 0.75.
  - OCR facts get `llm_extract`, 0.65 and `needs_review=true`.
- **Done when:** unit tests assert the INSERT params for each of the three cases, and assert that a payload which fails grounding at commit time is rejected with no INSERT.

### M9.4.4 — Anti-synthetic rules
- [ ] **Files:** `services/mcp/validator.py`, `tests/unit/test_mcp_validator.py`, `tests/fixtures/m9/aali_synthetic_payload.json` (new regression fixture)
- **Depends on:** M9.4.2
- **What** (design doc §Phase 5, rule 5):
  - ERROR `SYNTHETIC_LABEL` for placeholder segment labels (`Primary Operations`, `Other Operations`, `Operasi Utama`, `Operasi Lainnya`, or `Lainnya`/`Others` as the only child) unless the label is found verbatim in the cited page text.
  - ERROR `SYNTHETIC_SPLIT` when all children of a parent are exact round fractions (ratio × 100 is an integer multiple of 5) **and** none is cell- or text-grounded.
  - ERROR `SEGMENT_PROVENANCE` for a segmented fact without its own `source_page`.
- **Done when:**
  - The AALI-style fixture (parent revenue 1000, children 700 "Primary Operations" / 300 "Other Operations", not present in the page text) produces `SYNTHETIC_LABEL` and `SYNTHETIC_SPLIT` errors and status `INVALID`.
  - A genuine grounded split whose values happen to be 50/50 but appear in the page text passes.

### M9.4.5 — Sum and cross-statement tie-outs
- [ ] **Files:** `services/mcp/validator.py`, `db/seeds/tie_out_rules.yaml` (new: pairs like `idx:LoansGross` note total ↔ BS line, cash per bank ↔ `ifrs:CashAndCashEquivalents`), `tests/unit/test_mcp_validator.py`
- **Depends on:** M9.4.2
- **What:**
  - Children with the same parent concept and segment dimension must sum to the parent within tolerance (max(1 unit of scale, 0.1%)).
  - Tie-out pairs from YAML: when both sides are present, they must match within tolerance, otherwise ERROR `TIE_OUT` with a hint: "check you used the current-period column".
- **Done when:** unit tests pass for:
  - loan matrix children summing to the total
  - children off by 5% → `SUM_MISMATCH`
  - a note total equal to the prior-year BS value → `TIE_OUT` ERROR mentioning the column hint

### M9.4.6 — Narrative quality rules
- [ ] **Files:** `services/mcp/validator.py`, `db/seeds/narrative_boilerplate.txt` (new: normalized hashes or strings, seeded from the 28,679-duplicate sentence captured in M9.0.1 if available), `services/mcp/server.py` (load cross-issuer hashes of committed chunks for the evidence), `tests/unit/test_mcp_validator.py`
- **Depends on:** M9.4.2
- **What** (design doc §Phase 5, rule 7):
  - ERROR `NARRATIVE_BOILERPLATE` when a normalized md5 (lowercased, whitespace-collapsed, digits kept) is in the boilerplate list.
  - ERROR `NARRATIVE_DUPLICATE` when it matches a committed chunk of a **different** ticker.
  - ERROR `NARRATIVE_GENERIC` when an `MDA` chunk has no issuer anchor (no number, no named segment or product from the payload's facts, no period reference).
  - The same ticker's repeat across periods is allowed.
- **Done when:** unit tests cover:
  - the boilerplate sentence → ERROR
  - another ticker's committed text → ERROR
  - the same ticker's prior-period text → no error
  - "Pendapatan naik 12% menjadi Rp4,2 triliun didorong volume CPO" → no error

---

## Phase 5 — Agent workflow & observability

### M9.5.1 — Agent runbook update
- [ ] **Files:** `../EmiMind-Extraction/AGENTS.md`, `docs/runbook.md`
- **Depends on:** M9.3.3, M9.4.2
- **What:** Document the loop from design doc §Phase 4:
  1. `inspect_document`
  2. `get_extraction_contract`
  3. `get_routed_pages` per module
  4. read digits from `tables[].cells`, cite `cell_ref` + `bbox`, and use the image only for layout
  5. set `statement`
  6. per-module micro-payloads to `submit_draft_extraction`, fixing and retrying on `target_pages`
  7. `commit_verified_report`

  State that `source_page` = the physical PDF page (`page_index`), never the printed label. Handle `NEEDS_METADATA`.
- **Done when:** a fresh agent session following only the runbook, run on the `fs_small.pdf` fixture copied into the incoming folder as `XXXX_2025_AUDIT_RDF_fs_small.pdf` (with XXXX seeded in `issuer_profile` as BANK for the test), commits facts:
  - `SELECT count(*) FROM financial_facts WHERE ticker='XXXX' AND extraction_method='table_parser'` ≥ 10
  - `... AND segment ? 'collectibility'` ≥ 4

  Clean up with the reset afterwards.

### M9.5.2 — Token and cost logging
- [ ] **Files:** `services/mcp/server.py` (`submit_draft_extraction` and `commit_verified_report` accept optional `usage: {input_tokens, output_tokens, pages_read}` and log it to `document_processing_log.metadata`), `../EmiMind-Extraction/AGENTS.md` (the agent reports its usage)
- **Depends on:** M9.5.1
- **Done when:**
  - Unit: submitting with `usage` writes a log row whose metadata has all three keys.
  - `SELECT metadata->>'input_tokens' FROM document_processing_log WHERE doc_id=:id AND action='COMMITTED'` is non-null after the M9.5.1 smoke run.

---

## Phase 6 — Lighthouse & gate

### M9.6.1 — Lighthouse extraction run
- [ ] **Files:** none (operation); results in `eval/reports/m9_lighthouse.md`
- **Depends on:** Phases 1–5
- **Documents** (from `EMI_REPORTS_DIR`):
  - `BMRI/processed/BMRI_2025_AUDIT_RDF_LK PT Bank Mandiri-Desember 2025.pdf`
  - `LSIP/processed/LSIP_2025_AUDIT_RDF_LSIP_bilingual_31 des_2025_released.pdf`
- **What:** Copy them into the incoming folder, run index + embed, then run the agent per the runbook. Record per module: pages routed, facts committed, validation retries, tokens.
- **Done when:** both documents reach `COMMITTED` in `document_processing_log`, and `eval/reports/m9_lighthouse.md` has the per-module table filled for both.

### M9.6.2 — Acceptance gate script
- [ ] **Files:** `eval/deep_extraction_gate.py` (new), `eval/reports/m9_gate.json` (generated), `db/seeds/sector_depth_minimums.yaml` (new: e.g. `BANK: 60`, `PLANTATION: 50`, `GENERIC: 40` distinct concepts per annual filing)
- **Depends on:** M9.6.1, M9.3.4, M9.0.1
- **What:** compute and check each threshold from design doc §Phase 6. Exit non-zero if any fails, and print a table of dimension / value / threshold / PASS|FAIL.

  | Check | Query / source | Threshold |
  |---|---|---|
  | Router recall | `eval/reports/router_recall.json` | core ≥ 0.90, notes ≥ 0.80 |
  | Sector KPI coverage | contract mandatory KPIs vs committed facts ∪ `omitted_kpis` | 100% |
  | Concept depth | `count(DISTINCT concept_id)` per ticker-period | ≥ max(2 × baseline from `m9_baseline.json`, sector minimum) |
  | Segmented facts | facts with `segment IS NOT NULL AND source_page IS NOT NULL` | ≥ 25 per annual filing |
  | Grounding | `extraction_method='table_parser'` or text-grounded, among facts on `pdf_text` pages | 100% |
  | Narrative genuineness | cross-ticker duplicate md5 of `text_original`; boilerplate hits | 0 and 0 |
  | Provenance | facts with NULL `source_page`, or `source_page > documents.page_count` | 0 |
  | Token efficiency | `input_tokens` from the log vs `page_count × 2000` (whole-book estimate) | ≤ 15% |
  | Period correctness | lighthouse docs `fiscal_period='2025Q4'`, `period_end='2025-12-31'`, `page_count` = PyMuPDF count | 100% |
- **Done when:**
  - `uv run python eval/deep_extraction_gate.py --tickers BMRI,LSIP --out eval/reports/m9_gate.json` **exits 0**.
  - The JSON is committed.
  - Unit test `tests/unit/test_deep_extraction_gate.py` feeds a synthetic metrics dict with one failing check and asserts exit code 1 and FAIL in the output. This proves the gate can fail.

### M9.6.3 — Prioritized batch rollout
- [ ] **Files:** `scripts/m9_batch.py` (new: `--priority lq45|all`, `--limit`, resumable), `eval/reports/m9_batch_<date>.json`
- **Depends on:** M9.6.2 passing
- **What:** Index, embed and run extraction over in-scope tickers in priority order. After each batch of 20 documents, run the gate in `--aggregate` mode, which applies the same checks except router recall. Stop the batch automatically if any check regresses below threshold.
- **Done when:** the first LQ45 batch of at least 20 documents completes, and `deep_extraction_gate.py --aggregate --since <batch_start>` exits 0.

---

## M9 exit criteria

- [ ] `uv run python eval/deep_extraction_gate.py --tickers BMRI,LSIP` exits 0
- [ ] `uv run pytest -m "not integration" tests/` green; M9 integration tests green against the local stack
- [ ] `uv run ruff check .` and `uv run mypy services eval` clean
- [ ] `grep -rnE "'2024-12-31'|\"2024Q4\"|segment->>'segment'|generic_labels" services/ --include=*.py` returns nothing
- [ ] `eval/reports/{m9_baseline,router_recall,m9_gate}.json` committed
