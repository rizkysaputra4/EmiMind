# Workstream C report: periods, inspection, gate, recall eval, batch, test hygiene, runbook

Date: 2026-09-29. Nothing is committed. Scratch evidence: `C:\Users\rizky\AppData\Local\Temp\claude\C--Users-rizky-Documents-Code-EmiMind\1041b615-b76d-4f47-a638-0f02443221c7\scratchpad\wsC\` (`$SP`). Live tracker: `docs/m9_workstreams/wsC_progress.md`.

## 1. Files changed, by task id

| Task | Files |
|---|---|
| **M9.1.1** resolver | `services/mcp/periods.py`, `tests/unit/test_periods.py` |
| **M9.1.2** inspection | `services/mcp/services/inspection.py`, `services/extraction/metadata_extractor.py` (one hunk: `propose_metadata_from_text`), new `tests/unit/test_inspection_triage.py` |
| **M9.3.4** recall eval | `eval/router_recall.py`, new `tests/unit/test_router_recall_eval.py` |
| **M9.5.1** runbook | `C:\Users\rizky\Documents\Code\EmiMind-Extraction\AGENTS.md` (outside git; original at `$SP\AGENTS.md.orig`), `docs/runbook.md` §6 |
| **M9.5.2** token logging (server side) | `services/mcp/services/routing.py` (ROUTED metadata only), new `tests/unit/test_routed_logging.py` |
| **M9.6.2** gate | `eval/deep_extraction_gate.py`, `db/seeds/sector_depth_minimums.yaml`, `tests/unit/test_deep_extraction_gate.py` |
| **M9.6.3** batch | `scripts/m9_batch.py` |
| **M9.0.2 / §3.9** test hygiene | new `tests/unit/conftest.py`, new `tests/unit/test_db_guard.py`, `tests/unit/test_auth.py` (now mocked), new `tests/integration/test_auth_db.py`, `tests/integration/conftest.py` |
| tracking | `docs/m9_workstreams/wsC_progress.md`, this report |

## 2. Hunks in shared files

No hunks from the user's own earlier edits were found in any file C touched. `eval/review_tools/workstream_probes/wsC_inspection_orig.py` is byte-identical to `HEAD:services/mcp/services/inspection.py`. The `periods.py`, `metadata_extractor.py`, `test_periods.py` and `tests/integration/conftest.py` diffs are all this remediation, and `routing.py` was clean at HEAD. **So every hunk in every file listed above is Workstream C's**, and each file can be staged whole.

Dependency to watch: `tests/integration/conftest.py` `SEED_MODULES` runs `scripts.seed_announcement_class_rules`, `scripts.seed_announcement_contracts` and `scripts.seed_extraction_narratives`. Those are the **user's untracked** scripts. If they are not committed with or before the conftest, integration seeding breaks.

## 3. What was done

**Resolver (M9.1.1).** The previous agent's rewrite was verified, and more test cases were added:
- `Q1 31 Maret 2026` now resolves to 2026Q1 (it used to give 2031).
- Roman numerals count only next to TW/Triwulan/Kuartal/Semester/Q, or in `YYYY-III`, and never inside letter numbers (`Surat 045/CORSEC/III/2025` → None).
- Newly recognised: Triwulan II/III, Kuartal 1/II, Semester I/2, ISO/dot/compact dates (`2024-06-30`, `30.06.2024`, `20240630`), `LKT 2023`, `H1`.
- When the prefix disagrees with the name, the result has `conflict=True` and `conflicting_period` set.

**Inspection (M9.1.2).**
- `doc_type` defaults to `None` and is inferred. The domain is checked first: the announcement domain comes from the sidecar `kind`, or from an `announcements/` folder. Then the prefix domain token: `ANNUAL_AAR`/Annual Report title → ANNUAL_REPORT, `AUDIT_RDF` → FS_ANNUAL, `TW1-3_RDF` → FS_QUARTERLY. When the cover page or the agent overrides the prefix period, `doc_type` follows the real period (Q4 → FS_ANNUAL).
- `SKIPPED_ADMINISTRATIVE` is deterministic: filename rules, plus short documents (≤ 3 pages) with no statement keywords.
  - Rules: checklist/cheklist, pengantar, pernyataan direksi / surat pernyataan / director or BOD statement / SPD, ESG/sustainability, public expose/PUBEX, penjelasan, perubahan > 20 % / perubahan aset-liabilitas.
  - Added: newspaper items (iklan, koran, e-paper, Investor Daily, Kontan, press/news release).
  - The letter rules only fire at ≤ 10 pages, so a letter bundled with a full statement is kept.
- A conflict is resolved from the text of the first three pages (regex), or else returns `NEEDS_METADATA` naming both periods. The LLM fallback is gone.
- An unreadable PDF → `ERROR` and is not registered; the page count is never defaulted to 1.
- The sidecar `announcement_date` is never used as a period hint.
- `2025H1` → Q2; an invalid hint → `NEEDS_METADATA` instead of a crash.
- The page count and period source are logged in `INSPECTED_AUTHORIZED` metadata.
- `enqueue_fn` is injectable, for tests.

**Gate (M9.6.2).** Checks run per document. All inputs are server-side, and any missing input is a FAIL.
- **Router recall and precision**: core ≥ .90, notes ≥ .80, precision ≥ .40, from the recall report. Skipped in `--aggregate`.
- **KPI coverage**: the contract's mandatory KPIs (required, EXTRACTED_RAW, CRITICAL or HIGH).
  - At least 80 % must be *extracted*, with no uncovered CRITICAL KPI.
  - Each omission is re-verified by the gate itself: it searches every indexed page for the label or a synonym followed by a financial-size number.
  - A contract failure, or 0 mandatory KPIs, is a FAIL.
- **Depth**: max(2 × the ticker's full baseline, sector minimum). BMRI → 90. It applies to annual filings, and any Q4 filing counts as annual, so a mislabelled doc can't dodge it. Quarterly filings get `N/A`.
- **Segmented facts**: ≥ 25 per annual filing.
- **Grounding**: from `financial_facts.grounding` (cell/text = 100 % on `pdf_text` pages). A missing column → FAIL "migration 026".
- **Narratives**: 100 % verbatim on the cited page (uses B's `narrative_checks.is_verbatim`), 0 cross-ticker md5 duplicates, 0 boilerplate, 0 in-document duplicates, and at least one narrative when the contract requires them.
- **Provenance.**
- **Tokens**: computed from ROUTED logs as chars/4 + 1,600 × images, against page_count × 2,000, must be ≤ 15 %. No ROUTED rows, or rows without `chars`, → FAIL.
- **Period**: fiscal_period, period_end = `period_end_for(fp)`, and the PyMuPDF page count of the PDF on disk. A missing PDF → FAIL.
- **Embeddings**: every page has `embedding_model='BAAI/bge-m3'` and indexed pages = page_count. A missing column → FAIL "migration 025".
- `--since` is implemented. `--aggregate` evaluates every document COMMITTED in the window, and an empty window → FAIL.

**ROUTED logging (M9.5.2).** `get_routed_pages` now logs `chars`, `text_chars`, `table_chars` (the JSON of the served tables) and `images` (pages served with an image URL). It logs empty results too.

**Recall eval (M9.3.4).**
- Adds per-module precision and pages returned, plus mean pages per module and per-ticker summaries.
- Documents are looked up by sha256 (= `documents.doc_hash`) first, then by file name, then by ticker + period.
- A gold document that is missing or not indexed, a sha256 mismatch, or a module with no route query → recorded in `failures`, and the eval FAILs.
- `notes` lists every missed page, every module below threshold, and every failure.
- The report is written outside the async code, and the exit code is 0 only when thresholds are met.

**Batch (M9.6.3).**
- `prepare` orders tickers lighthouse → LQ45/IDX30 → KOMPAS100 → the rest. Membership comes from `scripts.seed_idx_tickers.IDX_TICKERS`, so there is no hardcoded list.
- It picks one real statement per ticker and period, never an administrative file (the same classifier as inspection), and prefers the issuer's own release over the IDX `FinancialStatement-*` rendering.
- It copies the file to `EmiMind-Extraction/m9_stage/<T>/`, then runs inspect → `index_pages_task` → `embed_pages_task`, resumable through a manifest plus DB checks.
- `report` gives per-document status plus the aggregate gate over the batch window → `eval/reports/m9_batch_<date>.json`, exiting 1 on FAIL.

**Test hygiene.** The unit guard blocks every asyncpg and psycopg connect path. `test_auth` is mocked, and the real-DB version was moved to integration. The integration conftest creates `emimind_test`, applies every `db/schema/*.sql` through `schema_migrations`, seeds it once, refuses to run against `emimind`, and deletes the documents, log and worker_runs it created at teardown.

**Runbook (M9.5.1).** AGENTS.md was rewritten around the 9-step loop:
1. inspect, with a status table covering NEEDS_METADATA and SKIPPED_ADMINISTRATIVE
2. contract
3. routed pages per module
4. cells with `cell_ref` + `bbox`, plus the concept traps from review §3.3
5. explicit `statement` and `period_type`
6. verbatim narratives
7. omissions only when truly absent (OMISSION_CONTRADICTED)
8. micro-payloads, then a consolidated submit
9. commit

It also states that `source_page` is the physical page index, that usage is optional (tokens are measured server-side), and that an announcement's period is the quarter containing its announcement date. `docs/runbook.md` §6 mirrors it and adds the batch, gate and recall commands.

## 4. Verification evidence

**Corpus period probe.** All 94,562 file names under `EmiMind-Extraction/incoming_reports/**`, run with `wsC_probe.py`:
- 94,555 resolved via the prefix and 7 via tokens; 0 None, 0 errors.
- Conflicts **before** (the review): 815 prefix/name disagreements, silently won by the prefix.
- **After**: 535 are flagged `conflict=True` (273 differ in year, 262 in quarter only) and sent to cover-page resolution. The remainder parse disagrees with the prefix on 671 names; the other 136 come from weak tokens only and are not flagged.
- The conflict list is in `eval/review_tools/workstream_probes/wsC_conflicts.json`.

**Filename-only classification over the corpus** (`$SP/cls_probe.py`):

| Result | Files |
|---|---:|
| kept | 68,598 |
| checklist | 6,481 |
| directors_statement | 6,131 |
| cover_letter | 5,175 |
| explanation_letter | 3,870 |
| esg_sustainability | 2,473 |
| change_over_20_percent | 1,347 |
| newspaper_publication | 451 |
| public_expose | 36 |

Inferred `doc_type` of the kept files: FS_QUARTERLY 39,293, ANNUAL_REPORT 16,279, FS_ANNUAL 13,026.

**Inspection on real filings** (`$SP/inspect_probe.py`): the real `inspect_document` code path, run on 120 **copies** in `$SP/inspect_copies/` with a fake engine, so no DB.
- Results: 51 AUTHORIZED, 67 SKIPPED_ADMINISTRATIVE, 2 NEEDS_METADATA.
- Of 43 conflict files: 17 resolved from the cover page, 24 administrative, 2 NEEDS_METADATA.

Examples:

| File | Result |
|---|---|
| `LSIP_2025_TW3…bilingual_30_Sep_2025` | AUTHORIZED 2025Q3 FS_QUARTERLY, 113 p |
| `BMRI_2025_AUDIT…LK PT Bank Mandiri-Desember 2025` | AUTHORIZED 2025Q4 FS_ANNUAL, 537 p |
| `AALI_2021_TW1…LK TW I 2021` | 2021Q1, 71 p |
| `BMRI_2024_TW2…Surat Pengantar Corsec` (the scanned letter the review saw AUTHORIZED) | SKIPPED_ADMINISTRATIVE cover_letter |
| `BMRI…Checklist OJK Desember 2025` (83 p) | SKIPPED checklist |
| `LSIP…ESG2025` | SKIPPED esg |
| `FOOD_2023_TW1_RDF_LK PT SFI TW 3_2022` | cover says 2022Q3 → AUTHORIZED 2022Q3 FS_QUARTERLY (prefix 2023Q1 overridden) |
| `RIGS_2024_AUDIT…30 Juni 2025` | 2025Q2 FS_QUARTERLY |
| `CANI_2020_TW2…31 Dec 2020` | 2020Q4 FS_ANNUAL |
| `INDO_2020_TW1…31 Desember 2019` | NEEDS_METADATA (cover not resolvable) |

Workstream A's live inspect at 00:20 also logged `SKIPPED_ADMINISTRATIVE` for the BMRI cover letter in `emimind` (log id 245).

**Unit tests for C files**, all passing:

| File | Tests |
|---|---:|
| `test_periods.py` | 55 |
| `test_inspection_triage.py` | 50 |
| `test_deep_extraction_gate.py` | 40 |
| `test_router_recall_eval.py` | 5 |
| `test_routed_logging.py` | 2 |
| `test_auth.py` | 2 |
| `test_db_guard.py` | 2 |

**Every gate check can fail** (`test_each_check_can_fail`, 29 cases, each asserting that exactly one dimension FAILs):
- **Router recall:** core, notes and precision below threshold; recall report missing.
- **KPI coverage:** under 80 % extracted; a CRITICAL KPI uncovered; an omission contradicted; contract error; zero mandatory KPIs.
- **Depth and segmented facts:** below threshold.
- **Grounding:** under 100 %; column missing; no facts.
- **Narratives:** not verbatim; cross-ticker duplicate; boilerplate; in-document duplicate; required but none.
- **Provenance.**
- **Tokens:** over budget; missing.
- **Period:** wrong period; wrong period_end; PDF missing; page-count mismatch.
- **Embeddings:** incomplete; pages not indexed; column missing.

Other tests cover document lookup, an empty window, aggregate mode skipping recall but not tokens, `report()` exit code 1 with FAIL in the output and JSON, and `main()` wiring for `--since`/`--aggregate`.

**Gate on real data** (read-only, `--tickers BMRI,LSIP`) exits 1 in both runs.

First run (`$SP/gate_real.json`), before 026 was applied to `emimind`. It FAILs:
- grounding: "financial_facts.grounding column missing (migration 026)"
- tokens: no ROUTED rows
- embeddings: 0/537 and 0/122 bge-m3
- KPI: 0 % extracted
- narratives: 6 required sections, 0 committed
- recall: no precision in the stale `router_recall.json`

Second run (`$SP/gate_real2.json`), after B applied 026 to `emimind` mid-session: grounding now evaluates and FAILs on "0 facts on text pages". Depth (≥ 90 for BMRI, ≥ 68 for LSIP) and segmented facts FAIL too, because Q4 counts as annual even though these docs are labelled FS_QUARTERLY.

Totals: 4 PASS, 16 FAIL, 0 N/A. Period and provenance PASS.

**Recall eval on the held-out gold** (read-only, report in `$SP/recall_heldout.json`) exits 1:
- core recall .833, notes recall .670, mean precision .627, 3.7 pages per module
- AALI_2021Q1 → FAIL "gold document not in documents"
- misses listed, e.g. BMRI BANK_LOAN_QUALITY_NPL missed 507/512/513

The ANN leg returned 0 because the docs have no bge-m3 vectors yet.

**Integration DB isolation.**
- `emimind_test` was created and has all migrations applied (023–026 included, in `schema_migrations`) plus seeds (234 issuer_profile rows).
- Run 2 (00:29:27–00:32:08): `emimind` snapshot of all 31 tables, both row counts and max timestamps, was identical before and after: 5,718 → 5,718 rows, **0 tables changed**. `emimind_test` was left with 0 documents, 0 processing_log rows, 0 facts and 0 pages.
- Run 1 showed changes in `emimind`, but all of them were Workstream A's copies (source_url under `scratchpad\wsA\`: AALI, JKON, BMRI letter). There were 0 rows with integration-test tickers or pytest paths.
- Integration results: 20 passed, 3 failed, 1 skipped. None of the failures is C-owned:
  - `test_m9_agent_runbook_smoke`: INVALID under B's stricter validator
  - `test_m9_fact_uniqueness`: its old ON CONFLICT no longer matches 026's identity index (B)
  - `test_page_router_bilingual_english_query`: A

**Gates.**
- `ruff check services eval scripts tests`: clean for every C file. Remaining: `eval/review_tools/**` (probe scripts) and `services/ingest/tasks/embed_pages.py` (A: S608 ×2 + 1).
- `mypy services eval`: clean for C files. Remaining: `eval/review_tools/**`, `services/ingest/tasks/index_pages.py` (A), `services/mcp/narrative_checks.py` (B), and the pre-existing `services/derive/valuation.py:94`.
- `pytest -m "not integration" tests/unit`: 308 passed, 19 failed, all in A/B files:
  - `test_mcp_server.py` (B: DB-guard hits and new strictness)
  - `test_mcp_validator.py` ×5
  - `test_grounding.py` ×1
  - `test_mcp_contracts.py::test_page_router_queries_yaml_schema` (A YAML)
  - `test_page_quality.py` ×2
  - `test_tables.py` ×1

**Proposal.** Exclude throwaway probes from lint and type checks by adding `"eval/review_tools"` to the `exclude` list in `ruff.toml` (ruff reads `ruff.toml`, not pyproject), and `exclude = ["eval/review_tools/"]` under `[tool.mypy]` in `pyproject.toml`. They are evidence scripts, not product code.

## 5. doc_ids created or deleted

None. C created no documents in `emimind` and deleted none. Inspection was verified with a fake engine on copies, and the gate and recall runs are read-only. The integration suite's documents in `emimind_test` were deleted by the session teardown.

Pre-existing pollution I found and left alone: `users` rows `analyst@fund.co.id` and `pilot_user@fund.co.id` in `emimind`, dated 2026-08-27, written by the old `test_auth`. Suggest deleting them.

## 6. Cross-workstream needs

1. **Lead / `services/mcp/server.py` (not C-owned)**: the MCP tool `inspect_document` still declares `doc_type: str = "FS_QUARTERLY"` and passes it through, so **doc_type inference never runs through MCP**. Change it to `doc_type: str | None = None`, and update the docstring to mention NEEDS_METADATA and SKIPPED_ADMINISTRATIVE.
2. **B**:
   - The gate needs `financial_facts.grounding` (026 is now applied in both `emimind_test` and `emimind`) and imports `narrative_checks.is_verbatim(chunk, page_text) -> (bool, float)`. Keep that signature.
   - `tests/integration/test_m9_fact_uniqueness.py` needs its ON CONFLICT updated for 026.
   - The runbook smoke test now fails validation.
3. **A**: the gate requires `embedding_model='BAAI/bge-m3'` on every page and indexed pages = page_count. 025 is applied in `emimind`, but the four existing docs have 0 bge-m3 pages.
4. **Lead**: `eval/reports/m9_gate.json` and `eval/reports/router_recall.json` are stale artifacts from the previous builder: the old passing gate, and no precision. Regenerate them after re-index and re-extraction.
   - `m9_gate.json`: `uv run python eval/deep_extraction_gate.py --tickers BMRI,LSIP --out eval/reports/m9_gate.json`
   - recall: `uv run python eval/router_recall.py --gold eval/router_gold/heldout/ --out eval/reports/router_recall_heldout.json`
   - The gate reads `eval/reports/router_recall.json` by default; pass `--router-recall eval/reports/router_recall_heldout.json` to use the held-out report.

## 7. Incomplete, stated honestly

- `scripts/m9_batch.py prepare/report` has **not been run end to end**. It would register and index documents in the dev DB, and A's indexer and embedder are still in flux. Only `select_filing`/`order_tickers` were exercised on the real corpus, and the gate/report path was exercised with synthetic metrics.
- The gate has never passed on real data. By design that requires 026, bge-m3 re-embedding and a real agent extraction.
- The M9.5.1 "done when" (a fresh agent run following only AGENTS.md on the `fs_small` fixture) was not performed. The integration smoke test for it currently fails in B's validator.
- A resolver with the review's "815" definition was not re-run. The review's probe script isn't in the repo, so the 535 figure uses the current `conflict` definition (prefix vs strong filename evidence).
- In the inspection probe, 2 conflict files with scanned or unhelpful covers end in NEEDS_METADATA. That is the intended behaviour, but the agent then has to read the cover.
