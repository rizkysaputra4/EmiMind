# Workstream B — live progress tracker

> Resume protocol: if you are a fresh agent picking this up, read this file FIRST, then `git diff` the files listed under "Files touched". Continue from "Next action". Do NOT redo items marked `done` (re-run their verification only if a later change could have broken them).
> Update this file after every completed sub-step (before starting the next one), not only at the end.

Spec: `docs/m9_workstreams/README.md` → Workstream B. Final report: `wsB_report.md`.
Scratch (harness/probes, not in repo): `C:\Users\rizky\AppData\Local\Temp\claude\C--Users-rizky-Documents-Code-EmiMind\1041b615-b76d-4f47-a638-0f02443221c7\scratchpad\wsB\` (`harness.py`, `run_genuine.py`, `fp_probe.py`, `prior_probe.py`, `cells.py`, `reindex.py`).

## Items

| # | Item | Status | Evidence / notes |
|---|---|---|---|
| 0 | Fix current breakage | done (code); tests in progress | ruff PLW2901 fixed (renamed loop vars), mypy `narrative_checks.py:140` → `str(w)`. `narrative_checks.py` was complete. |
| 1 | No evidence, no validation | done (code) | validator: `evidence is None` → ERROR `DOCUMENT_NOT_INDEXED`; service `_load_page_evidence` returns None on no pages / load error (+rollback), never skips. Same path for submit and commit. |
| 2 | Strict grounding, one scale | done (code) | `grounding.fact_scale` order unit_hint → page header → doc header → contract `multiplier`; `ground_fact()` single entry used by validate AND commit. `_STANDARD_SCALING_RULES` rewritten (no multiplier, precedence documented). |
| 3 | Right row / column / concept | done (code) | GROUNDING_COLUMN_PERIOD, ROW_LABEL_MISMATCH, GROUNDING_TEXT_LABEL_DISTANCE (+ block-subtotal rule for unlabeled subtotal lines), CONCEPT_LABEL_MISMATCH via `fact_semantics.check_concept_label` (probe `eval/review_tools/workstream_probes/wsB_cl.py`: 6 fail / 5 pass, 0 mismatches). Unknown concept → WARNING `CONCEPT_NOT_IN_ONTOLOGY`. `source_label_original` now required (SCHEMA ERROR). |
| 4 | Period types | done | `fact_semantics.resolve_period_type` (no coercion). Migration 026 applied (identity incl. period_type); ON CONFLICT updated in extraction.py, normalize_facts.py, xbrl_sidecar.py. |
| 5 | Commit honesty | done (code) | `commit_params_for()`: conf=min(table,cell), real bbox (synthetic → agent bbox → NULL), `grounding` column filled; DUPLICATE_FACT in validator. |
| 6 | Omissions verified | done (code) | `fact_semantics.find_metric_mentions` over ALL page texts (service loads them when omissions exist) → `OMISSION_CONTRADICTED`; claimed pages out of range → PROVENANCE. |
| 7 | Anti-synthetic | done (code) | all segment string values; exemption only if EVERY child grounded; ±0.5 pp; placeholder exemption needs grounded fact whose label contains the placeholder. |
| 8 | Sums & tie-outs | done (code) | SUM grouped by (concept, period_type, segment-key set + type); tie-outs ignore `statement`; YAML: dropped CashInBanks↔C&CE and same-concept rules, added C&CE↔`idx:CashAtEndOfPeriod`; syirkah plug BANK only. |
| 9 | Narratives are quotes | done (code) | auto-chunk fallback deleted; NARRATIVE_NOT_VERBATIM (≥90), boilerplate containment, GENERIC anchor must be on page; `narrative_chunks.text_hash` generated col + unique (source_doc_id,text_hash); cross-issuer lookup by hash. |
| 10 | Tests off production DB | done | `test_mcp_server.py` rewritten around an in-file `FakeDB` (SQL-substring router, records inserts); 26 pass, 0 real DB. `test_mcp_validator.py` rewritten (52 pass) with evidence from `_mcp_contract_fixtures.render_evidence`; `test_grounding.py` +8 tests (15 pass). `tests/unit/_fake_async_db.py` is A's — not used/edited. |
| 11 | guidance_committed real | done (code) | guidance inserted as `kg_nodes` GUIDANCE; count = rows inserted. |
| 12 | Verification | done (re-run after later code changes) | `uv run python eval/review_tools/adversarial.py` → 25/25 (10 review cases, 6 concept mistakes FAIL, 5 controls PASS, LSIP Q3 C&CE omission OMISSION_CONTRADICTED, omission pages out of range, not-indexed, duplicate). Genuine LSIP Q3 (scratch `run_genuine.py`): 23 facts + 10 omissions VALID. FP probe (`fp_probe.py`) 0/377 genuine rows; prior-year probe 351/351 caught. Concept captions probe (`cl_extra.py`) 0/43 mismatches after adding synonyms. |
| 13 | Gates + report | done | ruff services scripts tests: clean. mypy services: clean (126 files). unit: 408 passed (+1 later = test_mcp_validator 53). adversarial 27/27. BMRI FP probe 0/434, prior-year 408/408. is_verbatim tightened (numbers + ≤max(1,5%) missing words) after finding edited figures scored 96. Probes copied to `eval/review_tools/workstream_probes/wsB_{harness,run_genuine,fp_probe,prior_probe}.py`. |
| 14 | Coordinator adds (A/C flags) | done | (a) `test_m9_fact_uniqueness.py`: ON CONFLICT → 026 identity, period_type param, + step asserting instant vs duration_ytd are 2 rows — passes on emimind_test. (b) runbook smoke failure was B's stricter rules vs a lax payload: labels weren't the printed ones, unknown NOTE concept without period_type, MD&A quote not verbatim; ALSO a real FP: 'rasio NPL gross 2,5%' contradicted the monetary NPL omission → omission search now unit-aware (`find_metric_mentions(want_percent=)`, `validator._metric_is_ratio`, ontology unit wins). Payload fixed; passes. Full integration: 21 pass, 1 skip, 2 fail only in full run (test_m9_inspect_real_metadata, test_m9_page_router bilingual) — both pass in isolation, order-dependent, not B. emimind row counts identical before/after. (c) is_verbatim signature kept. (d) USD_BN added. |

## Current step
Done. Report: `docs/m9_workstreams/wsB_report.md`.

## Next action
None for B. Lead: review diffs, stage only B hunks of types.py/contracts.py (see Files touched), commit per task.

## Files touched
- `services/mcp/grounding.py` — (prev agent) big rewrite; (me) `ground_fact`, `is_synthetic_bbox` (renamed from `_is_synthetic_bbox`), block-subtotal rule, generic "Total" label match, LF endings.
- `services/mcp/fact_semantics.py` — (prev agent) new; (me) lint fixes, `marjin/margin`, supplemental synonyms (Capex, selling&distribution), `label_is_segment_member`, `find_metric_mentions`.
- `services/mcp/narrative_checks.py` — (prev agent) new; (me) mypy fix only.
- `services/mcp/validator.py` — rewritten (me).
- `services/mcp/services/extraction.py` — rewritten (me).
- `services/mcp/contracts.py` — OURS: only `_STANDARD_SCALING_RULES` (+ comment above it). All other hunks in the diff (formatting of `load_page_router_queries`, `target_concepts` list, `_load_narrative_rules` signature, `ANNOUNCEMENT_DOC_TYPES` one-per-line) are pre-existing, NOT ours.
- `services/mcp/types.py` — OURS: `VALID_PERIOD_TYPES`, `ExtractedFactItem.period_type` comment, `CommitReport.warnings`, `ConceptDefinition`, `PageEvidence.text_source` comment (`ocr_failed`). NOT ours: blank line in `DocumentSkipResult` docstring, trailing-newline removal at EOF.
- `services/ingest/tasks/normalize_facts.py`, `xbrl_sidecar.py` — ON CONFLICT target only (+ period_type).
- `db/schema/026_fact_identity_and_grounding.sql` — new.
- `db/seeds/tie_out_rules.yaml`, `db/seeds/narrative_boilerplate.txt` — edited.
- `tests/unit/test_mcp_server.py`, `test_mcp_validator.py`, `test_grounding.py`, `_mcp_contract_fixtures.py` (+`render_evidence`, `printed_value`, `PAGE_HEADER`), `tests/fixtures/m9/aali_synthetic_payload.json` (explicit period_type).
- `services/mcp/narrative_checks.py` — `_contained_score`: partial_ratio only when page ≥ chunk (short page used to 'contain' a long invented chunk). `is_verbatim` signature unchanged (C's gate imports it).
- `tests/integration/test_m9_fact_uniqueness.py`, `tests/integration/test_m9_agent_runbook_smoke.py` (payload labels/period_type/verbatim quote) — assigned to B by coordinator.
- `eval/review_tools/adversarial.py` — rewritten (new doc_ids, 25 cases, exit code 1 on any failure). Lead asked for it; not in the original ownership list.
- `grounding.check_cell_grounding` wrapper now uses `fact_scale` (was ignoring table unit_hint — real bug, found by test_check_cell_grounding_pass). test_grounding.py passes unchanged.

## DB changes / doc_ids used or created
- Migration 026 applied to `emimind` twice (idempotent, OK). Pre-check: 0 facts, 0 narratives → no violations.
- Re-indexed with A's current indexer (same doc_ids, no new docs): `0d5a1599-cb28-4f0b-9212-c6d447728f25` LSIP 2025Q3 (113 p, 188 tables), `9cbf5811-986f-4c8f-882f-6c0cf67a504a` LSIP 2025Q4 (122 p, 159 tables), `9a0154b0-9d27-42d4-b45a-f2ee9e75a187` BMRI 2025Q4 (537 p, 956 tables). Source copies still in old scratch `...\b86736b6-...\scratchpad\wsB_docs\`.
- Started MinIO (`minio server minio-data` on :9000, background) — indexer needs it.
- No facts/narratives written. Harness uses `log_event_fn=noop` → no processing-log rows.

## Decisions & gotchas
- `tests/integration/test_m9_fact_uniqueness.py:48` still uses the OLD ON CONFLICT target → will fail once 026 is in `emimind_test`. Not in B's ownership → cross-workstream need.
- Consumers reading `financial_facts` may now see both duration_qtd and duration_ytd rows per concept (identity includes period_type).
- LSIP Q3 BS has no C&CE total (only Pihak berelasi/ketiga) → C&CE is cited from CF p9 "Kas dan Setara Kas Akhir Periode".
- Owners' equity subtotal (LSIP p5 line 50) has no label → handled by block-subtotal rule in `ground_text`.
- Validator `concept_defs=None` skips concept checks (unit tests); service always passes a dict.
- Supplemental synonyms (fact_semantics.SUPPLEMENTAL_SYNONYMS) added for real captions the ontology lacks: Capex ("Penambahan aset tetap"), Selling ("Beban penjualan dan distribusi"), Revenue ("Pendapatan", "Pendapatan neto"), PBT ("Laba sebelum beban pajak penghasilan"); 'rugi'/'loss' neutral. Should be upstreamed into metric_definitions seeds (not B's file).
- idx:NetInterestIncome is NOT in metric_definitions (bank KPI) → WARNING CONCEPT_NOT_IN_ONTOLOGY.
