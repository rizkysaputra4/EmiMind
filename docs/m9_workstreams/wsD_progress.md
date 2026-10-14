# Workstream D (router note-module tuning): live progress tracker

> **Resume protocol.** If you are a fresh agent picking this up:
> 1. Read this file first.
> 2. `git diff` the files listed under "Files touched".
> 3. Continue from "Next action". Do not redo items marked `done`; re-run their check only if a later change could have broken them.
>
> Update this file after every completed sub-step, before starting the next one, not only at the end.

Spec: the prompt that launched this workstream is copied into "Spec" below. Final report: `wsD_report.md`.

## Spec (copied from the launch prompt)
- **Goal:** raise note-module recall of `services/retrieval/page_router.py` to ≥ 0.80, while keeping:
  - core-statement recall at ≥ 0.90
  - mean precision at ≥ 0.40
  - the default budget of 6 pages per module
- **Weak modules:** bank notes (BANK_LOAN_QUALITY_NPL, BANK_LOANS_BY_SEGMENT, BANK_LOANS_NPL, DEBT_BY_LENDER) and plantation notes (PLANTATION_AREA, CUSTOMER_CONCENTRATION).
- **Tune ONLY on dev documents.**
  - Never read `eval/router_gold/heldout/**`, `eval/router_gold/BMRI_2025Q4.yaml`, `eval/router_gold/LSIP_2025Q4.yaml` or `eval/reports/router_recall_heldout.json`.
  - Never route or inspect the held-out documents (BMRI 2025Q4 `9a0154b0…`, LSIP 2025Q4 `9cbf5811…`, AALI 2021Q1 `68083f0c…`).
- **Files owned:**
  - `services/retrieval/page_router.py`
  - `db/seeds/page_router_queries.yaml`
  - `tests/unit/test_page_router.py`
  - new `eval/router_gold/dev/*.yaml`
  - new `docs/m9_workstreams/wsD_*.md`

## Items

| # | Item | Status (todo / in progress / done / blocked) | Evidence / notes |
|---|---|---|---|
| 1 | Dev gold labels written from note headings (BMRI 2026Q2, LSIP 2025Q3, one more plantation filing, one more bank filing) | done | 5 yaml in eval/router_gold/dev (BMRI_2026Q2, BBNI_2021Q3, LSIP_2025Q3, SSMS_2025Q3, AALI_2020Q3); per-label reasons in yaml comments |
| 2 | Baseline dev recall/precision measured | done | scratch wsD/baseline.json: core 0.867 (BMRI BS->p70-77, IS->p72-77 miss), notes 0.676, prec 0.620, pages 3.55. LSIP unchanged 0.963/0.852 on its 9 modules. Zero-recall: AALI PLANTATION_AREA, AALI CUSTOMER_CONC, BBNI LOAN_QUALITY/LOANS_NPL/BY_SEGMENT, BMRI DEBT_BY_LENDER/LOAN_QUALITY, SSMS PLANTATION_AREA |
| 3 | Bank note modules tuned | done | step A done (wsD/stepA.json): core 1.00, notes 0.852, prec 0.740, pages 3.57. Remaining bank misses: BMRI DEBT 0, BMRI LOAN_QUALITY 0.25, BMRI LOANS_NPL 0.38, BMRI BY_SEGMENT 0.25, BBNI BY_SEGMENT 0.5, BBNI DEBT 0.67 |
| 4 | Plantation note modules tuned | done | step A: AALI PA 1.0, AALI CC 1.0, LSIP PA 1.0 (was .67), SSMS PA 0.8 (miss p19). LSIP all 9 modules recall 1.0, prec .87 |
| 5 | No regressions: core recall, precision, all dev docs, unit tests | done | stepB3 vs baseline: no module lost recall; LSIP 1.00/.87 (>= .963/.852); ruff ok, mypy ok, 423 unit pass. JKON sanity: core ok, CASH_BANKS precision drop (see gotchas) |
| 6 | Gates clean + `wsD_report.md` | done | ruff ok, mypy ok (126 files), 423 unit pass after last edit. Final dev (wsD/final.json): core 1.000, notes 0.888, prec 0.752, pages 3.68; thresholds met |

## Current step
DONE. Report written: docs/m9_workstreams/wsD_report.md.

## Next action
None for WS-D. Lead: re-run held-out eval; commit page_router.py, page_router_queries.yaml, test_page_router.py, eval/router_gold/dev/, wsD_*.md.

## Files touched
- db/seeds/page_router_queries.yaml: step A synonyms/anchors (bank DEBT x2, BANK_LOANS_NPL, BANK_LOAN_QUALITY_NPL, BANK_LOANS_BY_SEGMENT, PLANTATION_AREA, CUSTOMER_CONCENTRATION, DEBT_BY_LENDER ALL); applied by scratch wsD/yaml_stepA.py (already applied, do not rerun)
- services/retrieval/page_router.py: B3 in select_pages: if no seed is/reaches a heading start, best-fused heading start becomes an extra seed. yaml: BANK_LOANS_NPL anchors + KUALITAS KREDIT/CREDIT QUALITY. Eval wsD/stepB3.json: notes 0.888, prec 0.752, pages 3.68, no regressions.
- services/retrieval/page_router.py: B2 select_pages = seeds first (skip candidates inside an earlier seed's continuation reach, `_reach()`), each seed holds its page, then greedy growth in seed order into remaining budget. (Pure round-robin tried: worse, 0.853.) Eval wsD/stepB2r.json: core 1.0, notes 0.8818, prec 0.748, pages 3.68, no regressions vs B1b. Unit test test_select_pages_respects_total_budget_and_seed_ratio now fails (expects old greedy) -> must update.
- services/retrieval/page_router.py: B1 sub-heading anchors: _SUB_HEADING/_SUB_MATCH_CHARS/_TABLE_NUMBER, sub_heading_starts(), anchor_ranking returns starts+subs+conts (subs also in heading_starts); comma in matched span rejects enumerations. Eval wsD/stepB1b.json: notes 0.8635, prec 0.741, pages 3.68 (no regressions vs A).
- services/retrieval/page_router.py: _POLICY_HEADING + 'estimasi dan pertimbangan'/'estimates and judgements'; excluded_pages drops notes pages (notes header + note heading) for core queries
- tests/unit/test_page_router.py: updated select_pages budget test to new semantics; new tests: long first note doesn't starve 2nd seed + reach-skip, note-start extra seed, policy/estimates exclusion + core notes exclusion, sub-heading anchors (sub_heading_starts + anchor tiers). (File was not ruff-formatted before; left as is, ruff check passes.)
- eval/router_gold/dev/{SSMS_2025Q3,AALI_2020Q3,LSIP_2025Q3,BBNI_2021Q3,BMRI_2026Q2}.yaml: new dev gold

- docs/m9_workstreams/wsD_report.md: final report

## DB changes / doc_ids created
- AALI 2020Q3 `c4480fad-e7cf-497c-9640-32af1546c4d0` (69 p, 142 tables), copy in m9_stage/AALI; indexed + bge-m3 embedded
- BBNI 2021Q3 `a6f1e36d-804e-446b-a09e-f577d2b09621` (295 p, 686 tables), copy in m9_stage/BBNI; indexed + bge-m3 embedded
- SSMS 2025Q3 `4518d03f-12c9-4e62-8904-4b2b3645985b` (137 p, 220 tables), copy in m9_stage/SSMS; indexed + embedded. Added because AALI FS disclose no planted hectares; SSMS has hectares in note 1 (p19), plasma, bearer plants, customers >10%. issuer_profile sector = 'Unclassified' (router falls back to ALL, same as CPO since YAML has no CPO keys)
- Existing: BMRI 2026Q2 `6f214b27-e326-4be7-8f21-4e89509eb957`, LSIP 2025Q3 `0d5a1599-cb28-4f0b-9212-c6d447728f25`

## Decisions & gotchas
- Scratch dumps: `wsD/<doc>.txt` (page text) and `<doc>.heads.txt` (note headings) for aali20q3, bbni21q3, bmri26q2, lsip25q3, ssms25q3; made by `wsD/dump.py <doc_id> <out>`.
- Label conventions (follow LSIP README labels): BIOLOGICAL_ASSETS_DETAIL = aset biologis note; PLANTATION_AREA = pages with planted/plasma hectares (AALI has none -> bearer-plants mature/immature pages); DEBT_BY_LENDER = per-creditor balance tables only, not facility narratives (bank: + efek-efek yang diterbitkan by type). Bank modules labelled: BS, IS, CF, REVENUE_BREAKDOWN (interest income note), COGS_COMPONENTS (interest expense note), DEBT_BY_LENDER, BANK_LOAN_QUALITY_NPL (Kol table + NPL), BANK_LOANS_NPL (+ restructured, CKPN/stage, risk-note stage tables), BANK_LOANS_BY_SEGMENT. Skipped for banks: CUSTOMER_CONCENTRATION (no disclosure), BANK_PROFITABILITY_KPIS (no route query), MDA (not in FS).
- BMRI 2026Q2 index_pages v2 finished ok 01:14Z (708 tables); embeddings intact (603/603).
- BMRI 2026Q2: collectibility/NPL live in note 65k INFORMASI TAMBAHAN (pp573-582), not the loans note; loans by segment in note 57 (p471) + note 62A risk (496/498/502).
- Diagnosis (legs.py `<doc> <MODULE> <SECTOR>`): P6 BMRI BS/IS hijacked by policy note p77 (core queries don't exclude notes pages; statement_mode walks back 70-77). P7 _POLICY_HEADING misses 'ESTIMASI DAN PERTIMBANGAN'/'estimates and judgements' (BMRI p175-176 note 3). P4 anchors miss 'PINJAMAN YANG DIBERIKAN' (BBNI), 'EFEK-EFEK YANG DITERBITKAN', 'TANAMAN PRODUKTIF', 'AREA PERKEBUNAN', 'PENDAPATAN BERSIH'. P5 generic FTS words ('current','loss','lancar'). P2 SEED_SCORE_RATIO 0.7 blocks 2nd locations (3-leg best vs 2-leg page). P3 first seed's continuation eats whole budget. P1 long-note conts get anchor credit, mid-note pages beat note start (BMRI DEBT 358 vs 330).
- Eval: `uv run python eval/router_recall.py --gold eval/router_gold/dev/ --out wsD/<x>.json`; compare `wsD/cmp.py a.json b.json`.
- REJECTED: sub-heading tier after conts (wsD/stepB4_subslast.json): notes 0.888->0.876 (BMRI LQ/NPL worse). Kept starts+subs+conts.
- KNOWN RISK: JKON 2021Q3 (non-dev sanity) CASH_BANKS now [81-83 + 32] (was [32]): 'a) Kas dan Setara Kas' sub-heading in credit-quality section outranks note 4 (FTS rank 1). Recall kept, precision drops. Core JKON unchanged (BS 3-5, IS 6, CF 8).
- REJECTED: SEED_SCORE_RATIO 0.6 (wsD/stepB3_r06.json): notes recall unchanged 0.8818, precision 0.748->0.560, pages 3.68->4.89. Ratio stays 0.7 (reverted).
- SQL helper: scratchpad `wsD/sql.py "<SQL>"` (refuses held-out ids).
- BANK contract modules (sector_metric_contracts): ALL: COGS_COMPONENTS, CUSTOMER_CONCENTRATION, DEBT_BY_LENDER, REVENUE_BREAKDOWN; BANK: BANK_LOAN_QUALITY_NPL, BANK_LOANS_BY_SEGMENT, BANK_PROFITABILITY_KPIS (no route query); + core BS/IS/CF/MDA. CPO: BIOLOGICAL_ASSETS_DETAIL, CPO_UPSTREAM_KPIS (no route query), PLANTATION_AREA default.
- BANK_LOAN_QUALITY_NPL has its own YAML entry (ALL only), not the BANK_LOANS_NPL alias.
