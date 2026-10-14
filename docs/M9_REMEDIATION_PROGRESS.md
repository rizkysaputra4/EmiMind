# M9 Remediation — Progress Log

Tracks the work to fix the findings in [`docs/M9_REVIEW.md`](M9_REVIEW.md) (score 42/100 on 2026-09-28) and bring each M9 task close to 100.

> **Resuming? Read "State at shutdown" and "Next steps" at the bottom first**, then [`docs/m9_workstreams/README.md`](m9_workstreams/README.md) (full workstream specs + what each paused agent had already changed).
>
> **If workstream agents were interrupted:** each keeps a live tracker at `docs/m9_workstreams/ws{A,B,C}_progress.md`. Relaunch each agent with its spec section plus the instruction: "read your tracker first, continue from *Next action*, don't redo items marked done".

## LIVE STATUS — read this first on resume (updated after every sub-step)

- **RESUME HERE (saved 2026-10-14).** Router notes-recall rework (workstream R) is done and COMMITTED. Tracker: `docs/m9_workstreams/wsR_progress.md`.
  - Fresh dev split dev2 (seed 20261013): SIMP, BUMI, CTRA, INDF, TLKM, BRIS. Indexed and blind-labelled (`eval/router_gold/dev2/`). MinIO was restarted with user OK.
  - dev2 notes recall 0.467 → 0.776 (capped higher within page budgets).
  - Held-out random: 0.599 → 0.739; on the wave-1 subset (TAPG+PTBA) 0.686 → 0.838.
  - Older held-out set: 0.807 → 0.835.
  - LSIP 2025Q4 REVENUE_BREAKDOWN regression (1.0 → 0) fixed 2026-10-14. Cause: seed p101 sat on the page after the note start p100; its coverage counted p100, but the budget ran out before the backward step. Fix: such a seed holds its start page up front (`select_pages` leads). Diagnosed on LSIP, which was already a tuning ticker, so the random held-out set is untouched (re-run unchanged).
  - User decisions 2026-10-13: DEBT_BY_LENDER budget 6 → 10; MDA stays at 10; the eval reports capped recall next to raw recall.
  - **Depth threshold check (2026-10-14): 62 is unreachable on a statutory FS.**
    - The baseline of 31 is the old pipeline's fixed template. Every non-bank ticker has exactly 31. It is a union across about 25 one-page stub docs per ticker, not a per-filing count. No per-filing data was kept, and the DB has been reset.
    - FS_ANNUAL contracts ask for 37–48 required facts: NISP 48, TAPG 39, PTBA 40, BSDE 37, UNVR 41, ISAT 37. A perfect extraction is below 62, and also below the CPO 50 / BANK 60 sector minimums.
    - The ontology has 273 definitions. Only 49 are statement line items (BS 23, IS 19, CF 7) and 32 apply to ALL sectors; 180 are operational KPIs, mostly sourced from investor presentations and annual reports.
    - TAPG committed 28 distinct concepts.
    - **User decision 2026-10-14: contract-relative depth.** Pass when at least 90% of the filing's extractable contract concepts are committed. Extractable = EXTRACTED_RAW contract concepts, less omissions recorded at commit that the page search does not contradict. The old max(2 × baseline, sector min) stays in the report as info only (`eval/deep_extraction_gate.py` `contract_depth`).
    - TAPG under the new check: 24/29 (82.8%), FAIL. Misses: BankLoans, FfbProduction, D&A. Router notes for TAPG are now 0.76 (were 0.57).
  - **Validator fixes `857118e` (2026-10-14), from the PTBA runbook friction.**
    - Fixed: hierarchy labels with section headers (concept label and text grounding), and bilingual or multi-column wrapped labels joined column by column (text lines and table rows).
    - Verified on real PTBA p15, p119 and p120: LongTermBorrowings 1,277,425 and BRI 1,950,000 now pass.
    - S&M already passed on HEAD; no change.
    - Not fixed:
      - 4 module targets missing from the ontology (warning only; adding them changes contracts).
      - AGENTS.md gaps: retry_attempt on micro-submits, MDA narrative on a statutory FS, no page-fetch tool, ~20 KB micro-submit responses.
  - **Next:** Wave 1b (PTBA resume + TAPG gap fill) OPENED in `m9_comms/ORDERS.md` on 2026-10-14. It needs an `emimind` MCP restart first; a second restart after `857118e`. After that, grade wave 1b with the gate, then open wave 2 (NISP, BSDE, ISAT) and wave 3 (UNVR). The gold labeller still has to do UNVR and ISAT.
- **Previous resume point (saved 2026-10-12 ~01:00).** Step 7 is paused; PTBA and wave 2 are ON HOLD in `EmiMind-Extraction/m9_comms/ORDERS.md`.
  - **Done this session:**
    - Created the comms channel `m9_comms/`: Lead writes ORDERS, Tester writes STATUS and issues.
    - Graded wave 1.
    - Deleted the wrong TAPG fact 1214 (`idx:FfbProduction`).
    - Committed fixes `5708b4a`: mining route queries, contract filtered by sub-sector, PPE/capex label false positives. 446 unit tests pass; ruff and mypy are clean. Integration tests were NOT run (they need MinIO).
  - **Current numbers:**
    - TAPG gate re-run on 10-12: 5 PASS / 5 FAIL. Coverage 72.7%, depth 28 vs 62, segmented 17 vs 25, tokens 56,330 vs 50,000, router notes 0.57.
    - Held-out random notes recall for TAPG+PTBA is 0.686 (target 0.80).
  - **Provisional M9 score: about 60/100.** This is a Lead estimate, not a formal re-score; the official score is still 42.
  - **Open:**
    - Four `get_routed_pages` calls on PTBA happened 10-12 00:32–00:41 (mining modules and COGS; they show the MCP server runs the fixed code). The source is unknown, and nothing was written to STATUS or the trackers. Ask the user whether it was them or the Tester.
    - PTBA's `issuer_profile.name` is "Large Coal Miners", which looks like a peer-group name.
  - **Next steps:**
    1. Router notes-recall rework (weak: MDA, REVENUE_BREAKDOWN, DEBT_BY_LENDER, BIOLOGICAL_ASSETS_DETAIL) on a FRESH dev split, never on the random held-out six.
    2. Check whether concept-depth threshold 62 (max(2 × baseline, CPO min 50)) is realistic for a statutory FS.
    3. Re-run TAPG + PTBA via the Tester, then waves 2 (NISP, BSDE, ISAT) and 3 (UNVR). The gold labeller still has to do UNVR and ISAT.
    4. Gate, review tools, then the formal re-score of `M9_REVIEW.md`.
- **2026-10-11, wave 1 graded** (test agent; channel `EmiMind-Extraction/m9_comms/`).
  - **TAPG:** committed; gate 5 PASS / 5 FAIL (`eval/reports/m9_gate_wave1.json`). The wrong `idx:FfbProduction` was deleted.
  - **PTBA:** blocked by issue 001, now fixed in `5708b4a`.
  - **Router:** held-out random notes recall was 0.568, now 0.686 after the fixes. Still below 0.80: MDA, REVENUE_BREAKDOWN, DEBT_BY_LENDER, BIOLOGICAL_ASSETS_DETAIL. The router rework is the next step.
- **Current step: 7, test extraction on RANDOM held-out tickers.** User instruction 2026-09-29: for rescoring and testing, use random tickers other than BMRI and LSIP, which were used in tuning and dev.
  - Also excluded because they were already used: BBNI, SSMS, AALI, JKON.
  - Draw: one ticker per classified sector, `random.Random(20260929)` shuffle, first pick of each. BANK NISP, CPO TAPG, MINING PTBA, PROPERTY BSDE, CONSUMER UNVR, TELCO ISAT, all FY2025 audited FS (`FS_ANNUAL`).
  - Prepared with `scripts/m9_batch.py prepare --tickers NISP,TAPG,PTBA,BSDE,UNVR,ISAT --period 2025Q4`; manifest `eval/reports/m9_batch_manifest.json`.
  - Extraction agents follow only AGENTS.md, which forbids touching the EmiMind repo. So trackers and payloads live in the extraction workspace: `EmiMind-Extraction/m9_stage/<T>/wsE_<T>_progress.md` and `wsE_<T>_payload.json`.
  - Prepare: all six ready (every page indexed and embedded, 0 ocr_failed). doc_ids:
    - NISP `f67d9be5…` (197 pages)
    - TAPG `257139d8…` (131)
    - PTBA `69967908…` (168)
    - BSDE `e963c620…` (223)
    - UNVR `070f0223…` (97)
    - ISAT `d7433034…` (152)
  - TAPG first failed on a NUL char in a Camelot cell; fixed in `b36cbe7`.
  - **Interrupted 2026-09-30:** the machine ran critically low on memory. Claude Code killed MinIO, and all 7 agents were stopped.
    - Nothing committed (0 facts).
    - Extraction trackers are at: TAPG and PTBA ~9 modules done; ISAT core done; NISP, BSDE and UNVR balance sheet done. Payload files exist for all six.
    - Gold: NISP, TAPG, PTBA and BSDE are done; UNVR and ISAT are still todo.
    - Relaunch fewer agents at a time (2–3), and restart MinIO only when the user says so.
  - **Launched 2026-09-29 ~21:40:** 6 extraction agents plus the blind gold labeller (tracker `docs/m9_workstreams/wsG_progress.md`). If interrupted, relaunch each with its tracker ("read your tracker first, continue from Next action").
  - After they finish:
    - `uv run python eval/router_recall.py --gold eval/router_gold/heldout_random/ --out eval/reports/router_recall_random.json`
    - `eval/deep_extraction_gate.py --tickers NISP,TAPG,PTBA,BSDE,UNVR,ISAT --router-recall eval/reports/router_recall_random.json`
    - Review tools: verify_facts, narr_check, real_commit.
    - Then re-score `docs/M9_REVIEW.md`.
  - Router recall for the rescore: new held-out gold in `eval/router_gold/heldout_random/`, labelled from note headings by an agent that never sees router output.
  - MCP server reconnected and verified on the new code (`exclude_pages` returns `already_served` stubs). This session's cached tool schema doesn't show `exclude_pages`, but the server accepts it.
  - BMRI/LSIP 2025Q4 extraction is no longer part of the test set.
- **Step 6b DONE** (`f80a02d`, 2026-09-29):
  - Tables are served as `rows[r][c]` text grids.
  - Images are sent only with `include_images=true`.
  - New `exclude_pages` param: pages the agent already holds come back as `already_served` stubs.
  - YAML route queries added for `BANK_PROFITABILITY_KPIS` (checked on dev docs BMRI 2026Q2 pp569–571 and BBNI pp258–259, both capital-management notes) and `CPO_UPSTREAM_KPIS` (max_pages 3; FS rarely disclose these, so omission is the norm).
  - AGENTS.md steps 3/4 and the payload example updated (no `bbox`; Indonesian number format; pass `exclude_pages`). `docs/runbook.md` updated.
  - Gates: ruff, mypy, 425 unit and 24 integration tests pass (integration needs MinIO: `minio.exe server ./minio-data --address :9000`).
  - **Gate simulation** (`<scratchpad 0dc1495e…>/gate_sim.py`, full contract with exclude_pages; tokens from the ROUTED log, limit 15%):
    - Pass: BMRI 2025Q4 8.1%, BMRI 2026Q2 8.7%, SSMS 11.5%, BBNI 12.9%, LSIP 2025Q4 13.0%, LSIP 2025Q3 14.6%.
    - Failed at 15%: JKON 19.2% (32,974 tokens), AALI 2020Q3 23.0% (31,724), AALI 2021Q1 28.8% (40,899). On a ~70-page quarterly the 20–29 relevant pages are a third of the book.
    - **User decision 2026-09-29: budget = max(15%, 50,000 tokens), committed `d1e803c`.** All three now pass. AALI 2021Q1 routes 29 pages, which is high for 71 pages: check its routing in step 8.
- **Step 6b history (the finding, the measurement and the plan it was built from):**
  - **Problem 1: responses too large.** 11–40k chars per page, mostly table-cell JSON (per-cell bbox/value/confidence). BMRI BANK_LOANS_BY_SEGMENT was 238k chars in one call, over the tool-result limit.
  - **Problem 2: the token gate can't pass.** A full contract run was 54% (LSIP) / 32% (BMRI) of `page_count × 2000` against a 15% limit.
  - **Measured fix** (`scratchpad/size_grid.py`): tables as row-text grids `rows: [[cell text…]]`, no per-cell bbox/value/confidence; the server resolves the value and bbox from `cell_ref` at validation/commit; page images only with `include_images=true`. Result: LSIP 14.1%, BMRI 8.3%, largest call 73k chars.
  - **Plan:**
    - (a) `services/mcp/types.py`: RoutedPage/RoutedTable lean models.
    - (b) `services/mcp/services/routing.py` builds them; ROUTED log chars computed from the served JSON.
    - (c) `server.py`: `include_images: bool = False`.
    - (d) Check the validator/commit don't require an agent bbox/value beyond `value_numeric`.
    - (e) Tests.
    - (f) AGENTS.md steps 3/4 + `docs/runbook.md`.
    - (g) YAML route queries for `BANK_PROFITABILITY_KPIS` and `CPO_UPSTREAM_KPIS`, which currently raise "Unknown module". Validate on dev docs only.
  - **Also:** the MCP server in the session is STILL old code (process started 23:56 on 09-28; returned 14 pages where the current code gives 6). The user must reconnect `/mcp` after these changes land.
- **Then step 7:** lighthouse re-extraction (BMRI 2025Q4 + LSIP 2025Q4) by fresh extraction subagents that follow ONLY `EmiMind-Extraction/AGENTS.md` through the `emimind` MCP tools. Trackers: `docs/m9_workstreams/wsE_BMRI_progress.md` and `wsE_LSIP_progress.md`. **Blocker:** the user must reconnect the `emimind` MCP server (`/mcp`) so it runs the new code.
- **Step 5 DONE** (`6724faf`, workstream D): held-out core 1.00, notes **0.807**, precision 0.765; thresholds met. Still weak: BMRI loans-by-segment 0.00, debt-by-lender 0.00, loan-quality 0.33, NPL 0.70. The extraction agent must use the AGENTS.md fallback (ToC / notes index) for those modules. Dev docs added by D: BBNI 2021Q3 `a6f1e36d…`, SSMS 2025Q3 `4518d03f…`, AALI 2020Q3 `c4480fad…`.
- Step 4 is done; its history follows. Step 4 was: re-index + re-embed (background job: `scratchpad/step4_reindex.py`, then `scripts/backfill_page_embeddings.py --priority all`). Logs: `<session scratchpad>/step4_reindex.log`, `step4_backfill.log`. Session scratchpad = `C:\Users\rizky\AppData\Local\Temp\claude\C--Users-rizky-Documents-Code-EmiMind\1041b615-b76d-4f47-a638-0f02443221c7\scratchpad\`.
- **Done in step 4:** PDFs copied to `EmiMind-Extraction/m9_stage/<T>/` (sha256 verified) and `source_url` updated; BMRI/LSIP 2025Q4 doc_type → FS_ANNUAL; probe doc `cdd61743…` and test users deleted; AGENTS.md got the validator error-code table; `idx:NetInterestIncome` added to the ontology + reseeded (`4f97dfb`). Re-index finished for all 6 docs (exit 0): LSIP Q3 188 tables, LSIP Q4 159, BMRI 2025Q4 956, AALI 152, JKON 147, **BMRI 2026Q2 only 7 tables / 603 pages**. Camelot raises "Text extraction is not allowed" (PDF permission flag) and the pdfplumber fallback produced almost nothing → fixed in `492cc60` (tables work on a decrypted copy of owner-password PDFs). Backfill done: all 1,532 pages of the 6 docs have bge-m3 vectors.
- **Step 4 DONE:** BMRI 2026Q2 re-indexed with the encrypted-PDF fix: 1,042 tables (camelot_stream 1,040 on 579 pages, lattice 2), was 7. All 6 docs have every page embedded with bge-m3 (1,532 pages).
- **Step 5 (held-out recall), first run 2026-09-29, report `eval/reports/router_recall_heldout.json`:** core 1.00, notes **0.694 (< 0.80, FAIL)**, precision 0.682, 3.2 pages/module.
  - Misses: BMRI BANK_LOAN_QUALITY_NPL 0, BANK_LOANS_BY_SEGMENT 0, DEBT_BY_LENDER 0, BANK_LOANS_NPL 0.5; AALI PLANTATION_AREA 0, CUSTOMER_CONCENTRATION 0.
- **Workstream D launched (subagent):** router note-module tuning on a DEV set only (BMRI 2026Q2, LSIP 2025Q3, plus one more plantation and one more bank filing it labels itself). Tracker `docs/m9_workstreams/wsD_progress.md`, report `wsD_report.md`. If it's interrupted, relaunch it with its tracker. When it's done, the lead reviews, commits and re-runs the held-out eval.
- **Step 6 (partial):** `eval/review_tools/adversarial.py` gives **27/27** on the re-indexed docs (2026-09-29). `verify_facts.py`, `narr_check.py` and `real_commit.py` need committed facts, so they run after step 7.
- **Before step 7:** the `emimind` MCP server that the extraction agent talks to must be RESTARTED so it loads the new code. It was started before the remediation commits; in Claude Code use `/mcp` → reconnect, or restart the client.
- **Checks still to do for step 4:** every doc has a `worker_runs` index_pages v2.0 ok row after 2026-09-29 00:45 UTC; `SELECT doc_id, count(*) FILTER (WHERE embedding_model='BAAI/bge-m3'), count(*) FROM document_pages GROUP BY 1` is full; BMRI 2026Q2 tables (Camelot failed with "Text extraction is not allowed" → check the pdfplumber fallback produced grids). If the job died, re-run `step4_reindex.py` (it skips docs already done), then the backfill (it skips pages already embedded).
- **Resume rule:** every subagent gets its own `docs/m9_workstreams/<name>_progress.md` tracker (template: `wsA_progress.md`) and must update it after every sub-step; relaunch interrupted agents with "read your tracker first, continue from Next action".

**Scope agreed with the user (2026-09-28):**
- Install the real embedding stack: CUDA torch + sentence-transformers + BAAI/bge-m3.
- Install Tesseract OCR via winget.
- Batch scope: re-extract BMRI + LSIP (lighthouse) with a real agent run, plus about 6 more filings. The full LQ45 batch happens later, once every score is maxed.
- Commit per task (`M9.x.y: …`), staging only this work's changes.

---

## Status

| # | Workstream | Status | Notes |
|---|---|---|---|
| 0 | Environment: torch CUDA + sentence-transformers | done | torch 2.14.0+cu126, CUDA OK (RTX 4070 SUPER), sentence-transformers 6.1.0 via `pyproject.toml` groups `ml` + `extraction` (both default; the first `uv sync` had removed playwright). bge-m3 is in the HF cache. |
| 0 | Environment: Tesseract | done | 5.4.0 at `C:\Program Files\Tesseract-OCR\tesseract.exe` (not on PATH); eng+ind+osd tessdata in `C:\Users\rizky\AppData\Local\tessdata` |
| 1 | DB cleanup | done | documents 20 → 1, facts 195 → 0, narratives 157 → 0, derived 160 → 0 |
| 2 | Fixes A: ingest / embeddings / OCR / tables / router | done, committed | `f05c7c5` (M9.2.x), `ced25f2` (M9.3.1/3.2); report `wsA_report.md` |
| 3 | Fixes B: validator / grounding / commit path / narratives | done, committed | `e20996d`; migration 026 applied to emimind; report `wsB_report.md` |
| 4 | Fixes C: periods / inspection / gate / recall eval / batch / test hygiene / AGENTS.md | done, committed | `c520bad` `9bee83e` `26101ce` `26b103c` `32d4a92` `4e41997`; AGENTS.md is outside git; report `wsC_report.md` |
| 5 | Re-index + re-embed with real bge-m3 | **next** | migration 025 applied; LSIP 2025Q3 + JKON embedded; the rest pending |
| 6 | Independent router gold set + recall with precision | gold done; eval pending | `eval/router_gold/heldout/{BMRI_2025Q4,LSIP_2025Q4,AALI_2021Q1}.yaml`, labelled by the reviewer from note headings (never from router output). The router agent only saw an LSIP 2025Q3 dev set. BMRI loan quality / NPL is in Note 65 (pp507–513), not Note 12. |
| 7 | Lighthouse re-extraction (real agent run) | not started | needs A + B + C |
| 8 | Small batch (~6 filings) | not started | |
| 9 | Gate run + re-score in `M9_REVIEW.md` | not started | |

## Log

- **2026-09-29:** Committed 16 commits `00740cc`..`f59b4fc`: the user's own pending work (M8 announcement taxonomy, ticker seeding, ops scripts, sector docs) plus the M9 remediation, one commit per task group.
  - Left uncommitted, on the user's instruction: trackers, `incoming_reports/**`, the admr/payload test-data deletions, `scratch/`, `idxurl.txt`, `.claude/settings.local.json`, `wsC_conflicts.json`.
  - The router now raises when the query embedding fails; the user chose this over an FTS fallback.
  - Clean worktree of HEAD: ruff and mypy clean, 410 unit and 24 integration tests pass.

- **2026-09-28:** Added the `ml` dependency group (torch from the `pytorch-cu126` index, sentence-transformers). It, and later `extraction`, are default groups so `uv run` always has them.
- **2026-09-28:** Tesseract installed via winget; `ind.traineddata` (tessdata_best) placed with eng/osd in `%LOCALAPPDATA%\tessdata`.
- **2026-09-28:** DB cleanup (`eval/review_tools/cleanup.py`). Deleted:
  - the fake BMRI 2024Q4 unit-test document and its derived metrics
  - 12 TEST_ROUTER/TEST_BILINGUAL documents
  - 4 review-test documents
  - the old BMRI and LSIP 2025Q4 lighthouse documents (wrong concepts, fabricated narratives)
  - their derived metrics, kg nodes and worker_runs
- **2026-09-28:** Three parallel fix workstreams launched with disjoint file ownership. A: ingest/router, migration 025. B: validator/commit, migration 026. C: periods/inspection/gate/tests/AGENTS.md.
- **2026-09-28:** Held-out router gold set written (row 6).
- **2026-09-28:** bge-m3 download verified on CUDA. cosine("Laporan posisi keuangan konsolidasian", "Consolidated statement of financial position") = 0.80, vs 0.44 against "Beban pokok penjualan".
- **2026-09-28/29 (resume):** Gates on the partial tree:
  - ruff: 66 errors (60 in `eval/review_tools/`; 6 in `fact_semantics.py` + `config.py`).
  - mypy: 79 errors (9 in `services/`: `index_pages.py` `ocr_page` call, `tables.py`, `ocr.py`, `narrative_checks.py`, and a pre-existing one in `derive/valuation.py:94`).
  - Unit tests: 10 failed / 224 passed. 5 are DB-guard hits (`test_auth`, 3 in `test_mcp_server`), 5 are strictness/semantics changes.
  - Fresh agents A, B and C relaunched with the same ownership, continuing from their partial diffs.
- **2026-09-29:** Workstream C finished; report is `docs/m9_workstreams/wsC_report.md`.
  - Lead fixed the `services/mcp/server.py` `inspect_document(doc_type=None)` default, so doc_type inference now runs through MCP.
  - C's cross-workstream items went to B: the fact-uniqueness integration test's ON CONFLICT, the runbook smoke test, keeping `is_verbatim` stable, and USD_BN.
  - Still open for the lead:
    - Commit C's integration conftest together with or after the user's untracked `seed_announcement_*` / `seed_extraction_narratives` scripts, which it depends on.
    - Exclude `eval/review_tools` from ruff (`ruff.toml`) and mypy.
    - Delete the stale test users `analyst@` / `pilot_user@fund.co.id` from `emimind`.
    - Regenerate `eval/reports/m9_gate.json` and `router_recall.json`.
    - Run `m9_batch.py prepare` end to end once A and B land.
  - Baseline held-out recall (pre-A-final): core 0.833, notes 0.670, precision 0.627; AALI 2021Q1 not yet in documents.
- **2026-09-29:** A and B were cut off by the API session limit (A was on unit tests, B was rewriting `test_mcp_server.py`). Both were resumed from their transcripts and trackers.
  - Lead excluded `eval/review_tools/` from ruff (`ruff.toml`) and from mypy. The mypy exclusion went in `mypy.ini`, which takes precedence over `pyproject.toml`.
  - Lead fixed the `derive/valuation.py` return type (`dict | None`).
- **2026-09-29:** Workstream A finished; report is `docs/m9_workstreams/wsA_report.md`. Gates: ruff and mypy clean, 408 unit tests pass.
  - Router dev set (LSIP 2025Q3): recall 0.963, precision 0.852. Before: 1.00 / 0.20.
  - Table bboxes are real: 105/105 and 109/109 numeric cells inside their bbox (was 354/354 synthetic).
  - AALI page labels: 68/71 (was 6/71, all wrong).
  - Lead applied A's cross-workstream fixes:
    - `tests/unit/conftest.py`: autouse `EMI_EMBEDDING_MODE=fake`, so unit tests never load bge-m3.
    - `test_m9_index_pages`: the OCR skip now uses `settings.tesseract_cmd`; the scanned test runs and passes.
  - Open decision: when the embedder fails, the router currently degrades to FTS + anchors and logs an error, instead of raising.
  - Lead TODO: force re-index the wsB docs (old fake bboxes), `backfill_page_embeddings.py --priority all`, then the held-out recall eval.
- **2026-09-28 ~09:00:** User shut the PC down. All three agents stopped mid-edit. Specs and partial-state notes saved to `docs/m9_workstreams/README.md`; review tools copied from the session scratchpad to `eval/review_tools/`.

## State at shutdown (2026-09-28 ~09:00). HISTORICAL: superseded by the 2026-09-29 log entries and the next steps below

- **Git:** nothing from this remediation is committed. Uncommitted work in the tree:
  - `pyproject.toml` / `uv.lock`: `ml` + `extraction` default groups, torch cu126 index.
  - `docs/M9_REVIEW.md`, this file, `docs/m9_workstreams/README.md`.
  - `eval/router_gold/heldout/*.yaml` and `eval/review_tools/**`.
  - The three workstreams' partial code edits, listed per workstream in `docs/m9_workstreams/README.md` → Resume notes.
- **Careful when committing:** several files also carry the user's own pre-existing uncommitted edits (`services/mcp/contracts.py`, `services/mcp/types.py`, `scripts/seed_*`, `README.md`, `TASKS.md`, start/stop scripts, `uv.lock`, …). Stage this work's hunks only.
- **Subagents:** all three stopped mid-edit, no reports written, and they can't be resumed after a reboot. Relaunch fresh agents from the specs in `docs/m9_workstreams/README.md`.
- **Database (`emimind`)**, 4 documents:
  - `6f214b27-e326-4be7-8f21-4e89509eb957` BMRI 2026Q2: pre-existing, untouched, status raw. Its 603 page vectors are OLD md5-hash vectors and must be re-embedded.
  - Three docs indexed by workstream B from copies in the old session scratchpad (`...\scratchpad\wsB_docs\`, may not survive). They have pages + tables but no embeddings and no facts:
    - `9a0154b0-9d27-42d4-b45a-f2ee9e75a187` BMRI 2025Q4
    - `9cbf5811-986f-4c8f-882f-6c0cf67a504a` LSIP 2025Q4
    - `0d5a1599-cb28-4f0b-9212-c6d447728f25` LSIP 2025Q3
  - Those three were indexed with the OLD `tables.py` (fake bboxes). Delete them and re-inspect from stable copies after A's indexer fixes land.
  - Migrations 025/026 don't exist yet.
- **Old session scratchpad:** `C:\Users\rizky\AppData\Local\Temp\claude\C--Users-rizky-Documents-Code-EmiMind\b86736b6-60ea-495b-a79f-3de91bda3071\scratchpad\`. Everything reusable is copied to `eval/review_tools/`.
- **Untracked `scratch/` folder:** left by the previous builder AI (pre-review check scripts). Not part of this work.

## Next steps (resume here)

Steps 1–3 are **done** (2026-09-29): gates checked, A/B/C finished, 16 commits `00740cc`..`f59b4fc`.

4. **Re-index and re-embedding.** Migrations 025 and 026 are already applied to `emimind`.
   - Copy the source PDFs of the three wsB docs to a stable folder. Their `source_url` points into the old session scratchpad (`...\b86736b6-...\scratchpad\wsB_docs\`).
   - Force re-index the wsB docs (`index_pages_task(..., force=True)`) with the final indexer.
   - Then run `uv run python scripts/backfill_page_embeddings.py --priority all`. The dry-run showed 6 docs and 1,335 stale pages; BMRI 2026Q2 is included.
   - Before starting, check that MinIO is running.
   - Also: delete the stale test users `analyst@` / `pilot_user@fund.co.id` from `emimind`.
   - Also: sync `EmiMind-Extraction/AGENTS.md` with B's new rules: `source_label_original` = the printed row label; explicit `period_type` for non-ontology NOTE facts; narratives quoted verbatim with any translation only in `text_en`; omissions are checked against every page; `get_routed_pages` errors if embeddings are unavailable.
   - Also: move `fact_semantics.SUPPLEMENTAL_SYNONYMS` into the ontology seeds, and add the missing `idx:NetInterestIncome` / `idx:LoansGross`.
5. **Held-out recall.** `uv run python eval/router_recall.py --gold eval/router_gold/heldout/ --out eval/reports/router_recall_heldout.json`. Targets: recall ≥ 0.90 core / 0.80 notes, precision ≥ 0.40. Quick alternative: `eval/review_tools/router_blind.py <doc_id> '<json gold>'`.
6. **Re-verify with the review tools** in `eval/review_tools/`: `adversarial.py` (update doc_ids), `verify_facts.py`, `narr_check.py`, `real_commit.py`.
7. **Lighthouse re-extraction.** Re-extract BMRI + LSIP 2025Q4 as a real agent run through the tools: correct concepts (review §3.3), BMRI Note 65 loan quality (pp507–513), verbatim narratives, no fake omissions. Then a small batch of about 6 filings across sectors.
8. **Gate and re-score.** Run `eval/deep_extraction_gate.py --tickers BMRI,LSIP` and re-score every task in `docs/M9_REVIEW.md` with fresh evidence.
