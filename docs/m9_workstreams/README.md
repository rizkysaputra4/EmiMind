# M9 remediation workstreams: specs for relaunching

These are the instructions given to the three parallel fix agents on 2026-09-28. All three were **stopped mid-task** when the PC was shut down, and none wrote its final report. To resume, give a fresh agent the section for its workstream plus the "Resume notes" at the end of this file.

**Per-workstream live trackers (added 2026-09-29):** `wsA_progress.md`, `wsB_progress.md` and `wsC_progress.md` in this folder. Each agent updates its tracker after every completed sub-step: item status, current step, next action, files touched, DB changes/doc_ids, decisions. **When relaunching an interrupted agent, point it at its tracker first.** It should continue from "Next action" and must not redo items marked `done`. The "Resume notes" at the bottom only describe the first interruption (2026-09-28); the trackers take precedence.

Common rules for all workstreams:
- Keep your `ws<X>_progress.md` tracker current (see above).
- Read first: `docs/M9_REVIEW.md` (findings), `docs/M9_REMEDIATION_PROGRESS.md` (state), `tasks/00-conventions.md`, `tasks/09-M9-deep-extraction.md`, `docs/DEEP_EXTRACTION_REMEDIATION_PLAN.md`.
- Edit only files in your ownership list; note cross-workstream needs in your report.
- Verify on real filings under `C:\Users\rizky\Documents\Code\EmiMind-Extraction\incoming_reports\<TICKER>\processed\`. To index one, `inspect_document()` a COPY placed outside `incoming_reports` (otherwise it gets archived), then run `index_pages_task({}, doc_id)`.
- Unit tests must never touch Postgres (a guard in `tests/unit/conftest.py`, workstream C, enforces this).
- Do not commit; the lead reviews and commits per task (`M9.x.y: …`).
- Write a report `docs/m9_workstreams/ws<X>_report.md`: files changed grouped by task id, verification evidence, doc_ids created, cross-workstream needs.

Environment (done): torch 2.14 cu126 + sentence-transformers 6.1 (uv default group `ml`); bge-m3 in the HF cache; CUDA works (RTX 4070 SUPER). Tesseract 5.4 is at `C:\Program Files\Tesseract-OCR\tesseract.exe` (not on PATH), with eng+ind+osd tessdata in `C:\Users\rizky\AppData\Local\tessdata`. pgvector is NOT installed (`document_pages.embedding` is `float8[]`). DB: `postgresql://emimind:emimind@localhost:5432/emimind`.

---

## Workstream A: ingest, embeddings, OCR, table grids, page router

**Files owned:**
- `services/narrative/embedder.py`
- `services/extraction/ocr.py`
- `services/extraction/page_quality.py`
- `services/extraction/tables.py`
- `services/ingest/tasks/index_pages.py`
- `services/ingest/tasks/embed_pages.py`
- `scripts/backfill_page_embeddings.py`
- `services/retrieval/page_router.py`
- `db/seeds/page_router_queries.yaml`
- `services/shared/config.py` (add settings only)
- `.env.example` (add keys only)
- new `db/schema/025_document_pages_v2.sql`
- unit tests for these modules

**Required:**
1. **Embedder never fakes.** Use bge-m3 via sentence-transformers. The device comes from a setting defaulting to "auto" (cuda if available). Hash vectors only when `EMI_EMBEDDING_MODE=fake` (tests); otherwise raise on failure. Set a sensible `max_seq_length`. Keep the API compatible with `embed_narrative`.
2. **Migration 025.**
   - Add `document_pages.embedding_model text`.
   - Allow `text_source='ocr_failed'` (CHECK constraint).
   - Must be idempotent.
   - `embed_pages`/backfill write `embedding_model`; `WORKER_VERSION` becomes "2.0"; re-embed rows where the model is NULL or different; the UPDATE must not clobber rows.
   - Priority order: lighthouse (BMRI, LSIP) → LQ45 → rest.
3. **ANN without pgvector.**
   - Fix the `:q_vec::vector` bind bug (SQLAlchemy reads it as `q_ve`).
   - When pgvector is absent, compute cosine similarity in numpy over the document's page vectors.
   - The query vector must come from the real Embedder.
   - Verify that an English-only query finds bilingual/Indonesian pages.
4. **OCR fails loudly.**
   - Settings `EMI_TESSERACT_CMD` and `EMI_TESSDATA_DIR`, with defaults as above.
   - Raise `OcrUnavailableError`; never return "".
   - `needs_ocr` `min_chars=50`.
   - In the indexer, an OCR error or < 50 characters → `text_source='ocr_failed'`.
   - Verify on `BMRI/processed/BMRI_2024_TW2_RDF_Surat Pengantar Corsec - BEI Juni 2024.pdf` (scanned).
5. **Indexer robustness.**
   - Batch commits (e.g. every 25 pages).
   - Write a `worker_runs` 'failed' row on exception.
   - Delete stale `document_page_tables` rows on re-index.
   - Don't re-open the PDF for every page during OCR.
   - Tighten `detect_page_label`: a short standalone block, digits or roman `^[ivxlcdm]{1,6}$`, fully inside the top/bottom 8%.
   - Verify on AALI 2021 TW1: 6/71 labelled before; must improve with no false labels.
6. **Table grids honest.**
   - Real cell bboxes from Camelot/pdfplumber, converted to top-left origin. Never synthesize `BBox(0, r*15, 500, …)`; use null if unknown.
   - Per-page cascade: lattice → stream → pdfplumber.
   - Cell confidence ≤ table confidence.
   - `detect_unit_from_header`:
     - "(Expressed in millions of Rupiah)" / "jutaan" → IDR_MN
     - "miliar" / "billions" → IDR_BN
     - "ribuan" / "thousands" → IDR_K
     - "(Expressed in Rupiah)" → IDR
     - unknown → None
     - no substring bugs ("th" in "otherwise")
   - Note-reference columns ("22,27", "2c,2g,4", header Catatan/Notes) get value null.
   - A mixed label+number cell gets value from its single trailing numeric token, plus `value_from_mixed_cell: true`.
   - Verify on LSIP 2025 TW3 pp4–6 and BMRI 2025 pp22–24.
7. **Router.**
   - `max_pages` is a per-module TOTAL budget (default 6; justified overrides in YAML).
   - Anchors are a third ranked list in the RRF, not prepended.
   - `merge_spans` merges touching spans.
   - Remove dead code; keep `SET LOCAL statement_timeout`.
   - Dev labels for tuning, LSIP 2025Q3 (TW3 file): BALANCE_SHEET {4,5}, INCOME_STATEMENT {6,7}, CASH_FLOW {9}, CASH_BANKS {54,55}, BIOLOGICAL_ASSETS_DETAIL {59,60}, PLANTATION_AREA {62,73,74}, REVENUE_BREAKDOWN {93,94}, CUSTOMER_CONCENTRATION {94,95}, COGS_BREAKDOWN {94,95}.
   - Target: recall ≥ 0.9 and precision ≥ 0.5. No hardcoded pages; the held-out gold set is in `eval/router_gold/heldout/`, and don't tune on it.

---

## Workstream B: validator, grounding, commit path, narratives

**Files owned:**
- `services/mcp/validator.py`
- `services/mcp/grounding.py`
- `services/mcp/services/extraction.py`
- `services/mcp/types.py`
- `services/mcp/contracts.py`
- new helper modules (`services/mcp/fact_semantics.py` and `services/mcp/narrative_checks.py` were started)
- `db/seeds/tie_out_rules.yaml`
- `db/seeds/narrative_boilerplate.txt`
- the ON CONFLICT targets in `services/ingest/tasks/normalize_facts.py` and `xbrl_sidecar.py`
- new `db/schema/026_fact_identity_and_grounding.sql`
- tests: `test_mcp_validator.py`, `test_grounding.py`, `test_mcp_server.py`, `test_mcp_contracts.py`, `_mcp_contract_fixtures.py`, `test_types.py`, `tests/fixtures/m9/*`

**Required:**
1. **No evidence, no validation.** No `document_pages`, or evidence loading fails → INVALID `DOCUMENT_NOT_INDEXED`, in both submit and commit. Remove every path that skips grounding.
2. **Strict text grounding, one scale.**
   - Order: table `unit_hint` → page header unit → contract scaling rule (fix `_STANDARD_SCALING_RULES`).
   - Tolerance ±1 unit.
   - PERCENT/RATIO: scale 1, accept 0.1936 ↔ "19,36%".
   - Parse "Rp4,2 triliun" / "miliar"; handle en-dash negatives; a "-" cell grounds only 0.
3. **Right row, right column.**
   - Cell column header year/date must match the period, else `GROUNDING_COLUMN_PERIOD`.
   - Row label must fuzzy-match `source_label_original`, else `ROW_LABEL_MISMATCH`.
   - Text facts: the number must be within ±3 lines of the label, else `GROUNDING_TEXT_LABEL_DISTANCE`.
   - Concept ↔ label check against `metric_definitions` synonyms (`CONCEPT_LABEL_MISMATCH`). These must **FAIL**:
     - "Kas" → C&CE
     - "Total kredit yang telah direstrukturisasi dalam kategori NPL" → NPL gross
     - "Total simpanan dari bank lain" → idx:BankLoans
     - "Bunga yang masih akan diterima" → TradeAndOtherReceivables
     - "Total Ekuitas" → EquityAttributableToOwnersOfParent
     - "Bagian lancar atas liabilitas sewa" → ShortTermBorrowings
   - These must **PASS**:
     - "Kas dan setara kas akhir tahun" → C&CE
     - "Total Aset" → Assets
     - "Ekuitas yang dapat diatribusikan kepada pemilik entitas induk" → EquityAttributable…
     - "Laba tahun berjalan" → ProfitLoss
     - "Beban pokok penjualan" → CostOfSales
   - Concepts not in the ontology → WARNING.
4. **Period types.**
   - Invalid value → ERROR (no coercion).
   - FLOW concept as `instant` → `PERIOD_TYPE_MISMATCH`; IS/CF facts can't be `instant`.
   - Unknown-concept NOTE facts must state `period_type` explicitly; flow-like names as `instant` → ERROR.
   - Migration 026 puts `period_type` in the fact identity index; update ALL ON CONFLICT clauses.
5. **Commit honesty.**
   - conf = min(table, cell).
   - Store the real cell bbox (or the agent's, or NULL).
   - Migration 026 adds `financial_facts.grounding` ('cell' | 'text' | 'ocr_unverified'), filled at commit.
   - `DUPLICATE_FACT` for the same identity twice in one payload.
6. **Omissions verified.** Search ALL indexed pages for the metric's labels/synonyms followed by a number → `OMISSION_CONTRADICTED`. Claimed pages must be within 1..page_count. Omitting C&CE for LSIP 2025Q3 must now be rejected.
7. **Anti-synthetic.** Labels from all segment string values; the exemption only if EVERY child is grounded; round tolerance 0.5 pp; the "Lainnya" only-child rule checks the row label near the number.
8. **Sums and tie-outs.**
   - Group children by the set of segment keys; tie-outs regardless of the `statement` label.
   - Fix the YAML: drop CashInBanks ↔ C&CE.
   - Add BS C&CE ↔ CF ending cash.
   - Syirkah plug only for BANK.
9. **Narratives are quotes.**
   - Delete the commit auto-chunk fallback.
   - `NARRATIVE_NOT_VERBATIM`: normalized partial_ratio ≥ 90 against the cited page; `text_en` may translate.
   - Boilerplate by containment after normalizing punctuation.
   - GENERIC anchors must appear on the page.
   - Dedupe (source_doc_id, md5(normalized)) with a unique index in 026.
   - Cross-issuer lookup by hash, not LIMIT 5000.
10. **Tests off the production DB.** Convert `test_mcp_server.py::test_mcp_submit_draft_extraction_and_commit` (and any real-engine unit tests) to mocks.
11. `guidance_committed` must reflect reality.

**Verification:** all 10 adversarial cases in `eval/review_tools/adversarial.py` caught (re-index copies; the old doc_ids are gone), plus the 6 concept mistakes and the omission contradiction. A realistic payload of ≥ 10 genuine LSIP 2025Q3 facts must be VALID.

---

## Workstream C: periods, inspection, gate, recall eval, batch script, test hygiene, runbook

**Files owned:**
- `services/mcp/periods.py`
- `services/mcp/services/inspection.py`
- `services/extraction/metadata_extractor.py` (a deterministic no-LLM entry point only)
- `services/mcp/services/routing.py` (ROUTED logging only)
- `eval/deep_extraction_gate.py`
- `eval/router_recall.py`
- `scripts/m9_batch.py`
- `db/seeds/sector_depth_minimums.yaml`
- `tests/unit/conftest.py`
- `tests/integration/conftest.py` + integration test setup/teardown
- `tests/unit/test_periods.py`, `tests/unit/test_deep_extraction_gate.py`
- `C:\Users\rizky\Documents\Code\EmiMind-Extraction\AGENTS.md` (not a git repo)
- `docs/runbook.md`

**Required:**
1. **Resolver.**
   - Fix `Q1 31 Maret 2026` → 2031 (composite code bug).
   - Roman numerals only near TW/Triwulan/Kuartal/Semester/Q or `FinancialStatement-YYYY-III`; not inside letter reference numbers.
   - Add Triwulan II, Semester I, Kuartal 1, ISO dates, 20240630, LKT 2023.
   - Prefix-vs-name disagreement → `conflict=True`.
   - Re-run the corpus probe (review found 815 conflicts).
2. **Inspection.**
   - `doc_type` default None and inferred: AUDIT+RDF → FS_ANNUAL, TW1–3+RDF → FS_QUARTERLY, ANNUAL/AAR → ANNUAL_REPORT. Check the domain first.
   - Administrative files → SKIPPED_ADMINISTRATIVE: Checklist/Cheklist, Surat Pengantar/Pengantar LK, Pernyataan Direksi, Surat Pernyataan, ESG/Sustainability, Public Expose/PUBEX, Penjelasan, "Perubahan Lebih Dari 20 Persen".
   - Short docs (≤ 3 pages) without statement keywords → SKIPPED_ADMINISTRATIVE.
   - Resolve conflicts from the cover page (regex, no LLM), else NEEDS_METADATA.
   - Remove the LLM fallback.
   - Page-count failure → ERROR/NEEDS_METADATA, never 1.
   - The sidecar `announcement_date` must not be used as a period hint (it crashes).
   - `2025H1` → Q2.
3. **Gate.**
   - Depth = max(2 × ticker baseline from `m9_baseline.json`, sector minimum). BANK 60, PLANTATION/CPO 50, GENERIC 40 (others ≥ 40). Per annual filing.
   - Tokens computed server-side from ROUTED logs: `routing.py` logs served pages and characters; tokens = chars/4 + 1,600 per page image, against page_count × 2,000. Missing → FAIL.
   - Grounding share from the `financial_facts.grounding` column (B, migration 026); missing column → FAIL.
   - KPI coverage: extracted ≥ 80% of mandatory, omissions validated; contract failure → FAIL.
   - Narratives verbatim on their cited page (100%).
   - All pages have `embedding_model='BAAI/bge-m3'` (A, migration 025).
   - PDF missing → FAIL.
   - `--since` implemented; `--aggregate` evaluates the window.
   - A unit test proves each check can fail.
4. **Recall eval.**
   - Add precision + mean pages per module.
   - Thresholds: recall ≥ 0.90 core / 0.80 notes, precision ≥ 0.40.
   - Missing doc/module → FAIL; `notes` lists the real misses.
   - Support gold files keyed by file name + sha256 (`eval/router_gold/heldout/` already uses this format).
5. **Batch script.** `prepare` (inspect → index → embed, resumable, skip administrative files) and `report` (per-doc status + gate aggregate → `eval/reports/m9_batch_<date>.json`). No hardcoded LQ45 list; never pick ESG files or cover letters.
6. **Test hygiene.**
   - `tests/unit/conftest.py` autouse guard: any DB connection raises.
   - Integration tests use the `emimind_test` DB (create it, apply `db/schema/*.sql`) and clean up.
   - Prove it: running the integration suite leaves 0 new rows in `emimind`.
7. **Runbook.** Rewrite the extraction workflow section of `EmiMind-Extraction/AGENTS.md`, keeping `docs/runbook.md` consistent:
   1. inspect (handle NEEDS_METADATA / SKIPPED_ADMINISTRATIVE)
   2. `get_extraction_contract`
   3. `get_routed_pages` per module
   4. digits from `tables[].cells` with `cell_ref` + bbox
   5. explicit `statement` and `period_type`
   6. verbatim narratives
   7. omissions only when truly absent
   8. micro-payloads to submit
   9. commit

   `source_page` = physical page index.

---

## Resume notes (state at shutdown, 2026-09-28 ~09:00)

Every change below is **uncommitted, partial and unverified**. The agents were killed mid-edit, so some files may not import. Run `uv run ruff check`, `uv run mypy services eval` and the unit tests first.

| WS | Files already modified or created | Not started, by file inspection |
|---|---|---|
| A | `services/narrative/embedder.py`, `services/extraction/ocr.py`, `services/extraction/page_quality.py`, `services/extraction/tables.py`, `services/shared/config.py`, `.env.example` (was about to edit this when stopped) | migration 025, `index_pages.py`, `embed_pages.py`, `backfill_page_embeddings.py`, `page_router.py`, `page_router_queries.yaml`, unit tests |
| B | `services/mcp/grounding.py` (large rewrite), new `services/mcp/fact_semantics.py`, new `services/mcp/narrative_checks.py` (was writing this when stopped), possibly `services/mcp/types.py` / `contracts.py` (these two ALSO carry the user's own pre-existing uncommitted edits, so separate hunks carefully before committing) | `validator.py` wiring, `services/extraction.py` commit changes, migration 026, tie-out YAML, unit tests |
| C | `services/mcp/periods.py`, `services/mcp/services/inspection.py`, `services/extraction/metadata_extractor.py`, `tests/unit/test_periods.py`, new `tests/unit/conftest.py` (DB guard), new `tests/unit/test_db_guard.py`, `tests/integration/conftest.py` | gate, `router_recall.py`, `m9_batch.py`, `routing.py` logging, `sector_depth_minimums.yaml`, AGENTS.md, runbook |

Workstream probe scripts (copied from the session scratchpad) are in `eval/review_tools/workstream_probes/`. `wsC_conflicts.json` holds the corpus prefix/name conflicts C found.
