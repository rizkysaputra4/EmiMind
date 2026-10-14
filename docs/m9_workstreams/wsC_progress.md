# Workstream C — live progress tracker

> Resume protocol: if you are a fresh agent picking this up, read this file FIRST, then `git diff` the files listed under "Files touched". Continue from "Next action". Do NOT redo items marked `done` (re-run their verification only if a later change could have broken them).
> Update this file after every completed sub-step (before starting the next one), not only at the end.

Spec: `docs/m9_workstreams/README.md` → Workstream C. Final report: `wsC_report.md`.
Scratch (session 1041b615): `C:\Users\rizky\AppData\Local\Temp\claude\C--Users-rizky-Documents-Code-EmiMind\1041b615-b76d-4f47-a638-0f02443221c7\scratchpad\wsC\` (= `$SP` below).

## Items

| # | Item | Status | Evidence / notes |
|---|---|---|---|
| 0 | Fix current breakage (test_auth DB-guard failure) | done | `tests/unit/test_auth.py` → mocked conn (2 tests); real-DB version moved to `tests/integration/test_auth_db.py` (passes on emimind_test, deletes its user). |
| 1 | Resolver fixes + corpus probe before/after | done | Code from previous agent verified. Probe (`eval/review_tools/workstream_probes/wsC_probe.py $SP`) over all 94,562 names: 0 errors, 0 None; 535 prefix/name conflicts now flagged `conflict=True` (review: 815 silently won by prefix). 55 tests in `test_periods.py` pass (added Triwulan III, Kuartal II, TW-II, ISO dash/dot dates, roman-in-letter-number, Q1 31 Maret 2026 → 2026Q1). |
| 2 | Inspection | done | Added: domain-first (`is_announcement`: sidecar kind / `announcements/` dir → no FS triage, doc_type GENERIC_DISCLOSURE default), `infer_doc_type` prefix-domain first + `period_from_prefix` (period overridden by cover/agent → doc_type follows period), newspaper/e-paper/press-release + "BOD statement" rules. Real-path probe on 117 COPIES (`$SP/inspect_probe.py`, fake engine, no DB): 61 AUTHORIZED / 56 SKIPPED_ADMINISTRATIVE; 44 conflict files: 26 resolved from cover page, 18 administrative; 0 NEEDS_METADATA in sample. `tests/unit/test_inspection_triage.py` 50 pass. |
| 3 | Gate | done | `eval/deep_extraction_gate.py` rewritten; `tests/unit/test_deep_extraction_gate.py` 40 pass (29 parametrized "each check can fail" cases + missing inputs). Real run vs dev DB: FAIL exit 1 with grounding "column missing (026)" etc. |
| 4 | Recall eval | done | `eval/router_recall.py` rewritten (precision, pages/module, sha256→name→ticker lookup, failures list, notes). Real held-out run → `$SP/recall_heldout.json`: core .833, notes .670, precision .627, AALI missing → FAIL, exit 1. Tests `tests/unit/test_router_recall_eval.py` (5). |
| 5 | Batch script | done | `scripts/m9_batch.py prepare|report`; tiers from `scripts.seed_idx_tickers.IDX_TICKERS` membership; stages copies in `EmiMind-Extraction/m9_stage/<T>/`; manifest `eval/reports/m9_batch_manifest.json`. `select_filing` probe picks BMRI LK 537p, LSIP bilingual 122p etc. NOT run end-to-end (would register docs in dev DB). |
| 6 | Test hygiene | done | Guard in `tests/unit/conftest.py` + `test_db_guard.py`. `emimind_test` created by integration conftest; 026 applied there. Run 1: 4 failed/19 passed (failures A/B-owned); emimind changes during run all from wsA scratch paths, 0 test-marker rows. |
| 7 | Runbook | done | AGENTS.md rewritten (backup `$SP\AGENTS.md.orig`); `docs/runbook.md` §6 rewritten. |
| 8 | Gates + report | done | ruff/mypy clean for C files; unit 308 pass / 19 fail (all A/B files). Integration run 2: emimind 31 tables identical before/after (5,718 rows), emimind_test left empty; 3 failures A/B-owned. Report: `wsC_report.md`. |

ROUTED logging: `services/mcp/services/routing.py` now logs `chars`, `text_chars`, `table_chars`, `images` (also on empty result). Test `tests/unit/test_routed_logging.py`.
Sector minimums: `db/seeds/sector_depth_minimums.yaml` BANK 60, CPO/PLANTATION 50, all others 40.

## Current step
All items done; report written (`docs/m9_workstreams/wsC_report.md`).

## Next action
None for C. Lead: apply the server.py `doc_type=None` fix (see gotchas), run `m9_batch.py prepare` after A/B land, regenerate gate/recall reports.

## Files touched
All hunks below are Workstream C's. No user pre-existing hunks were found in these files (`wsC_inspection_orig.py` == HEAD inspection.py; periods/metadata_extractor/test_periods/integration conftest diffs are all remediation work). routing.py was clean at HEAD before C edited it.
- `services/mcp/periods.py` — resolver rewrite (prev agent): candidates by strength, conflict flag, `normalize_period`, `resolve_period_from_text`.
- `services/mcp/services/inspection.py` — deterministic triage, cover-page resolution, no LLM, page-count ERROR, sidecar date dropped, doc_type inference, announcement domain, enqueue_fn injectable.
- `services/extraction/metadata_extractor.py` — one hunk: `propose_metadata_from_text` (regex only).
- `services/mcp/services/routing.py` — ROUTED metadata chars/images; page list built before logging; empty-result log.
- `eval/deep_extraction_gate.py`, `eval/router_recall.py`, `scripts/m9_batch.py` — rewritten.
- `db/seeds/sector_depth_minimums.yaml` — rewritten.
- `tests/unit/conftest.py`, `tests/unit/test_db_guard.py` (new, prev agent); `tests/unit/test_auth.py` (mocked); `tests/unit/test_periods.py`; `tests/unit/test_deep_extraction_gate.py` (rewritten); new `tests/unit/test_inspection_triage.py`, `tests/unit/test_router_recall_eval.py`, `tests/unit/test_routed_logging.py`.
- `tests/integration/conftest.py` (emimind_test isolation, prev agent); new `tests/integration/test_auth_db.py`.
- `docs/runbook.md` §6; `C:\Users\rizky\Documents\Code\EmiMind-Extraction\AGENTS.md` (outside git).
- `docs/m9_workstreams/wsC_progress.md`, `wsC_report.md`.

## DB changes / doc_ids created or deleted
- emimind: C created/deleted NO documents (inspection verification used a fake engine on copies; gate/recall runs are read-only).
- emimind_test: created by `tests/integration/conftest.py` (all `db/schema/*.sql` incl. 025, 026 applied, tracked in `schema_migrations`; seeds run once). Session teardown deletes docs/log/worker_runs it created.
- AGENTS.md backup: `$SP\AGENTS.md.orig`.
- Pre-existing pollution found (not C's, not deleted): `users` analyst@fund.co.id, pilot_user@fund.co.id in emimind (2026-08-27, old test_auth).

## Decisions & gotchas
- `services/mcp/server.py` MCP tool `inspect_document` still has `doc_type: str = "FS_QUARTERLY"` → inference never runs via MCP. server.py is not C-owned: lead must change the default to `None`.
- Gate: Q4 filings always count as annual (old docs are mislabelled FS_QUARTERLY). Mandatory KPIs = contract rules required & EXTRACTED_RAW & CRITICAL/HIGH. Omissions re-verified by the gate itself (label/synonym + financial-size number on one line), independent of B.
- Gate imports B's `services.mcp.narrative_checks.is_verbatim`.
- Router recall mean precision (not per module) is compared to 0.40.
- Other agents write to emimind concurrently (wsA indexed AALI/JKON/BMRI-letter copies at 00:20); attribute row-count changes by source_url before blaming the integration suite.
- Probe copies for inspection live in `$SP/inspect_copies/` (never inspect inside incoming_reports: it archives).
