# Workstream B report: validator, grounding, commit path, narratives

**Status:** all 11 required items and the coordinator's item 14 are done. Gates are clean for B's files. Nothing is committed.
Live tracker: `docs/m9_workstreams/wsB_progress.md`.

## 1. Files changed, by task id

| Task | Required item(s) | Files |
|---|---|---|
| **M9.4.2** Grounding rules | 1 (no evidence, no validation), 2 (one scale), 3 (row/column/label) | `services/mcp/grounding.py` (rewrite: `fact_scale`, `ground_cell`, `ground_text`, `ground_fact`, column-period and row-label checks, block-subtotal rule, `USD_BN`); `services/mcp/validator.py` (grounding wiring, `DOCUMENT_NOT_INDEXED`); `services/mcp/contracts.py` (`_STANDARD_SCALING_RULES` only); `tests/unit/test_grounding.py`; `tests/unit/test_mcp_validator.py` |
| **M9.1.4** Commit path / period types | 3 (concept↔label), 4 (period types) | `services/mcp/fact_semantics.py` (new: `check_concept_label`, `resolve_period_type`, supplemental synonyms, `BUILTIN_CONCEPTS`); `services/mcp/types.py` (`VALID_PERIOD_TYPES`, `ConceptDefinition`); validator |
| **M9.1.3** Fact identity (migration) | 4, 5 | `db/schema/026_fact_identity_and_grounding.sql` (new); ON CONFLICT targets in `services/mcp/services/extraction.py`, `services/ingest/tasks/normalize_facts.py`, `services/ingest/tasks/xbrl_sidecar.py`; `tests/integration/test_m9_fact_uniqueness.py` |
| **M9.4.3** Commit uses grounding | 1, 5 (conf=min, real bbox, `grounding` column), 11 (guidance) | `services/mcp/services/extraction.py` (rewrite: `_load_page_evidence`, `_load_concept_defs`, `commit_params_for`, guidance → `kg_nodes` GUIDANCE); `services/mcp/types.py` (`CommitReport.warnings`); `tests/unit/test_mcp_server.py` |
| **M9.4.4** Anti-synthetic | 7 | validator; `tests/fixtures/m9/aali_synthetic_payload.json` (explicit `period_type`); tests |
| **M9.4.5** Sums and tie-outs | 5 (`DUPLICATE_FACT`), 8 | validator; `db/seeds/tie_out_rules.yaml` |
| Sector KPI gate / omissions (M9.4.2 or M9.6.2 scope) | 6 | validator (`OMISSION_CONTRADICTED`, page range); `fact_semantics.find_metric_mentions` (unit-aware); service loads every page's text when omissions are declared |
| **M9.4.6** Narrative quality | 9 | `services/mcp/narrative_checks.py` (new: `is_verbatim`, `boilerplate_match`, `issuer_anchor`, `narrative_md5`); validator; extraction.py (auto-chunk fallback deleted, dedupe `ON CONFLICT (source_doc_id, text_hash)`, cross-issuer lookup by hash); `db/seeds/narrative_boilerplate.txt`; migration 026 (§3) |
| **M9.0.2 / §3.9** Tests off the production DB | 10 | `tests/unit/test_mcp_server.py` (in-file `FakeDB`; the 4 real-DB tests are mocked now); `tests/unit/_mcp_contract_fixtures.py` (`render_evidence`, `printed_value`, `PAGE_HEADER`; ratio units on `NPLCoverageRatio`) |
| **M9.5.1** Runbook smoke test (coordinator item 14b) | — | `tests/integration/test_m9_agent_runbook_smoke.py` (payload only) |
| Review tools | verification | `eval/review_tools/adversarial.py` (rewritten); new `eval/review_tools/workstream_probes/wsB_{harness,run_genuine,fp_probe,prior_probe}.py` |

Two unrelated drive-by fixes in `extraction.py`, both in commit honesty:
- The commit no longer archives *any* `incoming_reports/*{ticker}*.pdf` when the document's own file is missing. That fallback could archive another period's pending filing.
- Evidence-load failures roll the connection back and are reported, never swallowed.

## 2. Exact hunks in `types.py` / `contracts.py`

**`services/mcp/types.py`: ours (stage these)**
- `VALID_PERIOD_TYPES: frozenset[str]` (new constant after `class CellRef`).
- `ExtractedFactItem.period_type`: comment only (the field is unchanged).
- `CommitReport.warnings: list[str]` (new field).
- `class ConceptDefinition(BaseModel)` (new, after `CommitReport`).
- `PageEvidence.text_source`: comment only (`'ocr_failed'` added).

**`services/mcp/types.py`: NOT ours (pre-existing)**
- Blank line added after the `DocumentSkipResult` docstring.
- Trailing blank line removed at the end of the file.

**`services/mcp/contracts.py`: ours (stage these)**
- The comment block above `_STANDARD_SCALING_RULES` and its body: new keys `payload_unit` and `scale_precedence`, and rewritten `instructions`. There is still no `multiplier`, by design: a page that declares no unit is read at face value.

**`services/mcp/contracts.py`: NOT ours (pre-existing formatting)**
- The `yaml_path` wrap and `open(...)` in `load_page_router_queries`.
- The `target_concepts=[...]` wrap in `_load_granular_modules`.
- The `_load_narrative_rules` signature wrap.
- `ANNOUNCEMENT_DOC_TYPES` reformatted to one item per line.

## 3. Behaviour now (what an agent sees)

- **Evidence is mandatory.** No `document_pages`, or evidence fails to load → ERROR `DOCUMENT_NOT_INDEXED`. This is the same in submit and commit, because both go through `_prepare_validation` → `_load_page_evidence`. No path skips grounding.
- **One scale per fact**, in this order: the cited table's `unit_hint`, then the page header, then the document's dominant header, then the contract `multiplier`, then 1. Tolerance is ±1 printed unit.
  - Years never match an amount.
  - PERCENT/RATIO facts are never scaled: 0.1936 and 19.36 both ground "19,36%".
  - "Rp4,2 triliun" and "miliar" are parsed; en-dash negatives are handled; a "-" grounds only 0.
- **Right column and right row:**
  - `GROUNDING_COLUMN_PERIOD`: the cell's column header date, or the page's year order for text lines.
  - `ROW_LABEL_MISMATCH` for cells; `GROUNDING_TEXT_LABEL_DISTANCE` for text (±3 lines).
  - Unlabeled block subtotals are accepted: an amounts-only line closing a labelled header block, e.g. LSIP owners' equity.
  - `source_label_original` is now required (SCHEMA ERROR).
- **Concepts:**
  - `CONCEPT_LABEL_MISMATCH` uses `metric_definitions` names and synonyms plus `SUPPLEMENTAL_SYNONYMS`.
  - Segmented facts may be labelled by their segment member ("Pihak ketiga").
  - Concepts not in the ontology get a WARNING `CONCEPT_NOT_IN_ONTOLOGY`.
- **Period types:**
  - An invalid value is a SCHEMA ERROR (`duration_q` is no longer coerced).
  - `PERIOD_TYPE_MISMATCH` fires for a FLOW concept submitted as `instant`, a STOCK concept submitted as a duration, BS facts that are not `instant`, IS/CF facts submitted as `instant`, and unknown flow-like names submitted as `instant`.
  - An unknown concept on a NOTE/EQ fact with no `period_type` is an ERROR.
- **Identity:**
  - `DUPLICATE_FACT` for the same (concept, period_type, segment) twice in one payload.
  - DB identity is `ux_financial_facts_identity_v2` (ticker, fiscal_period, concept_id, period_type, segment).
- **Commit:**
  - Every fact is re-grounded with the same `ground_fact` the validator uses.
  - Cell → `table_parser`, conf = min(table, cell), the real cell bbox (synthetic → agent bbox → NULL), `grounding='cell'`.
  - Text → `llm_extract` 0.75, `'text'`.
  - OCR → 0.65, `needs_review`, `'text'` or `'ocr_unverified'`.
  - An `ocr_failed` page is an ERROR `GROUNDING_OCR_FAILED`.
  - `guidance_committed` counts the GUIDANCE `kg_nodes` actually inserted; previously guidance was never stored.
- **Omissions:**
  - Claimed pages must fall within 1..page_count (PROVENANCE).
  - Then every indexed page is searched for the metric's names and synonyms followed by a number of the right kind: monetary metrics need a non-percent amount, ratio metrics need a percent. A hit → `OMISSION_CONTRADICTED`, listing pages and lines.
- **Anti-synthetic:**
  - Placeholders are checked in every segment string value.
  - A placeholder is exempt only when the fact is grounded and the placeholder is its printed row label.
  - A round split (multiples of 5% ±0.5 pp) needs **every** child grounded.
- **Sums and tie-outs:**
  - `SUM_MISMATCH` is grouped by (concept, period_type, segment key set + type).
  - Tie-outs ignore the `statement` label.
  - YAML: dropped CashInBanks↔C&CE and the same-concept rules (now covered by DUPLICATE_FACT); added C&CE ↔ `idx:CashAtEndOfPeriod`.
  - The syirkah plug applies to BANK only.
- **Narratives:**
  - The auto-chunk fallback is gone.
  - `NARRATIVE_NOT_VERBATIM` fires when the normalized partial_ratio is < 90, or when the chunk has a number not on the page, or when more than max(1, 5%) of its words are not on the page. I added the last two after measuring that an edited figure scored 96 and a swapped company name 94.
  - Boilerplate is matched by containment after normalization.
  - The MD&A anchor must appear on the page.
  - Dedupe uses a unique index on (source_doc_id, text_hash); the cross-issuer lookup is by hash (no `LIMIT 5000`).
  - `is_verbatim(chunk, page_text) -> (bool, float)` keeps its signature (C's gate imports it).

## 4. Verification evidence

Environment: `emimind` dev DB, migration 026 applied, docs re-indexed with workstream A's current indexer. Submissions go through `submit_draft_extraction` with a no-op processing-log writer, so they wrote nothing.

**Adversarial suite:** `uv run python eval/review_tools/adversarial.py` → **27/27 cases behave as expected**.

| Case group | Result |
|---|---|
| 10 review cases | all caught. 01 `GROUNDING_CELL`; 02 `GROUNDING_COLUMN_PERIOD`; 03 `GROUNDING_TEXT`; 04 `CONCEPT_LABEL_MISMATCH` + `GROUNDING_TEXT_LABEL_DISTANCE`; 05 `PROVENANCE`; 06 `SYNTHETIC_LABEL` + `SYNTHETIC_SPLIT`; 07 `BALANCE_SHEET_UNBALANCED` + `GROUNDING_COLUMN_PERIOD`; 08 `NARRATIVE_GENERIC` + `NARRATIVE_NOT_VERBATIM`; 09 `PERIOD_TYPE_MISMATCH`; 10 `GROUNDING_TEXT` |
| 6 concept mistakes (on the real BMRI/LSIP pages) | all FAIL with `CONCEPT_LABEL_MISMATCH` |
| 5 correct mappings | all PASS with no per-fact error, e.g. BMRI p38 C&CE 379,877,189 and the LSIP p15 owners'-equity subtotal 13,999,946 |
| LSIP 2025Q3 C&CE omission | `OMISSION_CONTRADICTED` (p9 "Kas dan Setara Kas Akhir Periode 6.901.140") |
| Other | omission pages out of range → PROVENANCE; unknown doc → `DOCUMENT_NOT_INDEXED`; duplicate → `DUPLICATE_FACT`; fabricated MD&A on the IS page → NOT_VERBATIM; a genuine bilingual-interleaved quote (LSIP p100) → PASS |

**Concept-label probes:**
- `eval/review_tools/workstream_probes/wsB_cl.py`: 0 mismatches.
- An extra 43 common IDX captions: 0 mismatches, after adding supplemental synonyms (Revenue "Pendapatan", PBT "Laba sebelum beban pajak penghasilan", Capex "Penambahan aset tetap", Selling "Beban penjualan dan distribusi") and making "rugi" neutral.

**Genuine payload:** `uv run python eval/review_tools/workstream_probes/wsB_run_genuine.py` → **VALID** (0 errors, 2 warnings: D&A not extracted, no revenue breakdown).
- 23 genuine LSIP 2025Q3 facts: 14 cell-cited and 9 text-cited, across BS p4–5, IS p6–7 and CF p9. They include receivables segments and C&CE from CF p9, since the BS has no C&CE total.
- 10 honest omissions (CPO operational KPIs, bank loans, borrowings, opex).

**False-positive rate on genuine facts:** `wsB_fp_probe.py` generates every current-period row of the primary statements as a fact.

| Filing | Text-cited rows | Cell-cited rows | Errors |
|---|---:|---:|---:|
| LSIP 2025Q3 | 85 | 89 | 0 |
| LSIP 2025Q4 | 85 | 118 | 0 |
| BMRI 2025Q4 | 232 | 202 | 0 |
| **Total** | | **811** | **0 (0.0%)** |

- Before the fix, the only false positives were bare "Total" labels (2 rows); a generic-only label now matches only a generic-only row.
- Mirror probe `wsB_prior_probe.py` (the same rows from the prior-year column): **759/759 caught** as `GROUNDING_COLUMN_PERIOD`.
- Caveat: these probes take labels from the row itself and choose the current column with the same header logic the validator uses. They measure grounding mechanics, not agent label choice. The hand-built payload and the concept probes cover the label side.

**Omission false positives:**
- LSIP 2025Q3: 12 omissions declared, 2 contradicted. Both were real disclosures: D&A on p94 and receivables on p4/p111. The other 10 honest omissions pass.
- Found and fixed: a ratio next to a caption ("rasio NPL gross 2,5%", fixture p7) used to contradict the omission of the monetary NPL amount.

**Gates:**

| Gate | Result |
|---|---|
| `uv run ruff check services scripts tests` | All checks passed |
| `uv run mypy services` | Success, 126 files |
| `uv run pytest -m "not integration" tests/unit -q -p no:cacheprovider` | 408 passed, plus 1 test added afterwards (test_mcp_validator: 53 passed) |
| `uv run pytest tests/integration -q -p no:cacheprovider` (`emimind_test`) | 21 passed, 1 skipped, 2 failed |

- The two integration failures are `test_m9_inspect.py::test_m9_inspect_real_metadata` and `test_m9_page_router.py::test_page_router_bilingual_english_query`. Both pass when run alone, so they depend on test order or shared state. They are C/A files, not B.
- `test_m9_fact_uniqueness.py` and `test_m9_agent_runbook_smoke.py` pass.
- `emimind` row counts are identical before and after the integration run: documents 7, facts 0, narratives 0, processing_log 222.

## 5. Doc ids and DB changes

- **Migration 026:** applied to `emimind` twice with psql (idempotent). The pre-check found 0 facts and 0 narratives, so there were no uniqueness violations.
- **Re-indexed with A's indexer** (same ids, no new documents):

| doc_id | Filing | Pages | Tables |
|---|---|---:|---:|
| `0d5a1599-cb28-4f0b-9212-c6d447728f25` | LSIP 2025Q3 | 113 | 188 |
| `9cbf5811-986f-4c8f-882f-6c0cf67a504a` | LSIP 2025Q4 | 122 | 159 |
| `9a0154b0-9d27-42d4-b45a-f2ee9e75a187` | BMRI 2025Q4 | 537 | 956 |

  Their source copies are still in the old scratchpad (`...\b86736b6-...\scratchpad\wsB_docs\`) and are referenced by `documents.source_url`. They should be moved to a stable location before that folder is cleaned.
- **Facts / narratives:** none written to `emimind`; no processing-log rows from my harness.
- **MinIO:** started (`minio server minio-data`, :9000) because the indexer needs it. It is still running.

## 6. Cross-workstream needs

- **C (AGENTS.md / runbook), agent contract changes:**
  - `source_label_original` is required and must be the printed row label; prefix the section header for sub-rows ("Kas dan setara kas - Pihak ketiga").
  - `period_type` is required for concepts not in the ontology on NOTE/EQ facts.
  - Narratives must be exact quotes of the cited page; put any translation in `text_en`.
  - Omissions are checked against every page.
  - C&CE may be cited from the CF ending-cash line.
- **Ontology seeds** (`scripts/seed_metric_ontology.py`, not B):
  - Move `fact_semantics.SUPPLEMENTAL_SYNONYMS` into `metric_definitions`.
  - Add the missing concepts: `idx:NetInterestIncome`, `ifrs:IncomeTaxExpense`, `ifrs:BiologicalAssets`, `ifrs:FinanceIncome`, `idx:LoansGross`, `idx:CashAtEndOfPeriod`.
- **Readers of `financial_facts`** (derive, refresh_profile, api): the identity now includes `period_type`, so a concept can have both `duration_qtd` and `duration_ytd` rows. Queries should filter on `period_type`.
- **Gate (C):** `financial_facts.grounding` now exists (migration 026); `'cell'` or `'text'` counts as grounded.
- **A:** B relies on real cell bboxes, `value=null` for note refs and `unit_hint` codes `{IDR,USD}_{K,MN,BN}`. All are present and used; `USD_BN` was added.
- **Integration flakiness** (A/C): the two order-dependent failures listed in §4.

## 7. Not done / honest caveats

- The verbatim check is fuzzy (threshold 90 plus the number and word rules). A quote of a few words is accepted if it appears on the page. It does not judge whether the chunk is meaningful narrative.
- The omission search is caption-based. A metric printed under a caption not in its names or synonyms will not contradict an omission. Conversely, a caption followed by an unrelated number of the right kind can contradict one; in the LSIP Q3 sample both hits were genuine.
- The block-subtotal rule accepts the first unlabeled amounts-only line within 15 rows after a labelled header that has member rows. That is a deliberate, narrow relaxation of ±3 lines.
- The genuine payload was built by hand from the parsed grids (by me), not by a fresh agent run. The lighthouse re-extraction (M9.6.1) is still to do.
- `tests/unit/_fake_async_db.py` belongs to A and was not used or edited.
