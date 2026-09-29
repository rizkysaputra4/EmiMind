# Workstream D report: page-router note-module tuning

Tracker: `wsD_progress.md`. Nothing is committed; the lead commits.

## Gates (run after the last edit)
- `uv run ruff check services scripts tests`: all checks passed.
- `uv run mypy services`: no issues (126 files).
- `uv run pytest -m "not integration" tests/unit -q -p no:cacheprovider`: 423 passed.

## Held-out hygiene
- I did not read, open or grep `eval/router_gold/heldout/**`, `eval/router_gold/BMRI_2025Q4.yaml`, `eval/router_gold/LSIP_2025Q4.yaml` or `eval/reports/router_recall_heldout.json`.
- I did not route, inspect or read pages of BMRI 2025Q4, LSIP 2025Q4 or AALI 2021Q1. My SQL and dump helpers refuse those doc_ids.
- The only thing that touched AALI generally was `backfill_page_embeddings.py --tickers AALI,BBNI`. Its dry run listed only the two new docs as stale, so the held-out AALI doc was not re-embedded.

## Dev set: `eval/router_gold/dev/` (5 documents, 47 module labels)

| File | doc_id | Pages | How it got here |
|---|---|---|---|
| `BMRI_2026Q2.yaml` | `6f214b27-e326-4be7-8f21-4e89509eb957` | 603 | existing; lead re-indexed it (index_pages 2.0 ok, 01:14Z; 708 tables; 603/603 embedded) |
| `BBNI_2021Q3.yaml` | `a6f1e36d-804e-446b-a09e-f577d2b09621` | 295 | new: copied to `m9_stage\BBNI\`, inspected, `index_pages_task`, backfilled bge-m3 |
| `LSIP_2025Q3.yaml` | `0d5a1599-cb28-4f0b-9212-c6d447728f25` | 113 | existing; labels copied from README Workstream A item 7 |
| `SSMS_2025Q3.yaml` | `4518d03f-12c9-4e62-8904-4b2b3645985b` | 137 | new, same way (`m9_stage\SSMS\`). `issuer_profile.sector` is `Unclassified`, so it routes on `ALL`, which is what CPO uses anyway: the YAML has no CPO keys. |
| `AALI_2020Q3.yaml` | `c4480fad-e7cf-497c-9640-32af1546c4d0` | 69 | new, same way (`m9_stage\AALI\`) |

**Why SSMS as well as AALI.** AALI's financial statements disclose no planted hectares, so AALI alone cannot test PLANTATION_AREA properly. I checked AALI 2021 FY too, and it has none either. SSMS 2025Q3 has hectares in four places:
- the general-information note
- the plasma note
- the bearer-plants note
- a dedicated plantation-area note

**How labels were found.** I dumped every page's text and its numbered note headings (the `note_headings` helper) from `document_pages` via SQL, then read the pages. No label comes from router output. Each YAML carries a comment on every module; the main ones:

- **BMRI 2026Q2**
  - Core statements: BS 6-13, IS 14-16, CF 21-24.
  - Note 41 interest income (428-429) and note 43 fees (430) → REVENUE_BREAKDOWN.
  - Note 42 interest expense (429-430) → COGS_COMPONENTS.
  - DEBT_BY_LENDER:
    - note 30 *Efek-efek yang diterbitkan* summary (288)
    - note 36 *Pinjaman yang diterima* summary (330-331)
    - direct off-shore lender list (332-333)
    - Note 36 runs 72 pages, so I did not label the rest.
  - Collectibility and NPL are **not** in the loans note: note 12m (p239) points to note 65k *Informasi tambahan*.
    - Kol 1-5 by type (573) and by sector (576) for 30 Jun 2026.
    - NPL summary (581) and NPL ratio (582). These four pages are BANK_LOAN_QUALITY_NPL.
    - BANK_LOANS_NPL adds note 12c stage movement (229) and 12g CKPN movement (235-237).
  - Only the current-period page is gold where each period has its own page.
  - BANK_LOANS_BY_SEGMENT:
    - note 57 segment table, 30 Jun 2026 (471)
    - note 62A credit risk: loans by Korporasi/Komersial/Retail/Syariah (496)
    - concentration by segment row, geographic (498) and industry (502)
- **BBNI 2021Q3**
  - Core statements: BS 4-8, IS 9-11, CF 14-15. Pp284-295 are parent-only schedules and not gold.
  - Note 39/40 (196) → REVENUE_BREAKDOWN and COGS_COMPONENTS.
  - DEBT_BY_LENDER: note 29 securities issued (168-169), note 30 borrowings summary (170) and bilateral lenders a)-g) (171-173).
  - BANK_LOAN_QUALITY_NPL: note 12 *Pinjaman yang diberikan* e. Kol table (126), f. NPL + ratio (127).
  - BANK_LOANS_NPL adds:
    - h. restructured (128)
    - j. stage/CKPN (129-131)
    - note 60 *Analisis kualitas kredit* loan tables by internal rating (269) and days past due (275)
  - BANK_LOANS_BY_SEGMENT: BBNI has no loans-by-business-segment table, so I labelled 12a by type (124) and the note 47 segment table (220).
- **SSMS 2025Q3**
  - Core statements: BS 4-6, IS 7-8, CF 10-11.
  - Cash note 58-59; biological assets 63.
  - PLANTATION_AREA:
    - note 1e subsidiaries table with mature/immature hectares (19)
    - note 15 plasma hectares (76-78)
    - note 36 *Area perkebunan* (134)
  - Note 27 (113) → REVENUE_BREAKDOWN and CUSTOMER_CONCENTRATION ("melebihi 10%").
  - Note 28 (114) → COGS.
  - Note 21 *Utang bank* per-creditor tables (93-95) → DEBT_BY_LENDER.
- **AALI 2020Q3**
  - Core statements: BS 3-4, IS 5, CF 7.
  - Cash 27; biological assets 40.
  - PLANTATION_AREA: no hectares in this filing, so I labelled note 11 *Tanaman produktif* mature (35) and immature (36).
  - Note 28 (62) → revenue, and customers > 10% (CUSTOMER_CONCENTRATION).
  - Note 29 (63) → COGS.
  - Note 19 *Pinjaman bank* per-lender tables (51-52) → DEBT_BY_LENDER.
- **Skipped for banks**
  - CUSTOMER_CONCENTRATION: no such disclosure (the BANK route is interest income).
  - BANK_PROFITABILITY_KPIS: no route query.
  - MDA: not in the financial statements.

## Dev metrics: baseline (router at HEAD) vs final

| | Baseline | Final |
|---|---|---|
| Core mean recall | 0.867 (BMRI BS and IS: 0.00) | **1.000** |
| Notes mean recall | 0.676 | **0.888** |
| Mean precision | 0.620 | **0.752** |
| Mean pages per module | 3.55 | 3.68 |
| Weak bank modules (LQ, NPL, SEGMENT, bank DEBT; 8 rows) | 0.163 | 0.578 |
| Weak plantation modules (PLANTATION_AREA, CUSTOMER_CONCENTRATION; 6 rows) | 0.445 | 0.967 |
| LSIP 2025Q3 (must stay ≥ 0.963 / 0.852) | 0.963 / 0.852 | **1.000 / 0.870** |

Per document (core recall / notes recall / precision):

| Doc | Baseline | Final |
|---|---|---|
| AALI | 1.00 / 0.71 / 0.68 | 1.00 / 1.00 / 0.83 |
| BBNI | 1.00 / 0.44 / 0.44 | 1.00 / 0.82 / 0.56 |
| BMRI | 0.33 / 0.44 / 0.39 | 1.00 / 0.62 / 0.69 |
| LSIP | 1.00 / 0.94 / 0.85 | 1.00 / 1.00 / 0.87 |
| SSMS | 1.00 / 0.81 / 0.72 | 1.00 / 0.97 / 0.80 |

No module lost recall against the baseline. Per module (R = recall, P = precision, number of pages returned in brackets):

| Doc | Module | Gold | Baseline R / P | Final R / P | Final returned |
|---|---|---|---|---|---|
| AALI | PLANTATION_AREA | 35, 36 | 0.00 / 0.00 (1) | 1.00 / 0.50 (4) | 35, 36, 41, 42 |
| AALI | CUSTOMER_CONCENTRATION | 62 | 0.00 / 0.00 (2) | 1.00 / 1.00 (1) | 62 |
| AALI | DEBT_BY_LENDER | 51, 52 | 1.00 / 0.33 (6) | 1.00 / 0.33 (6) | 51-56 |
| AALI | other 7 modules | | 1.00 | 1.00 (unchanged) | |
| BBNI | REVENUE_BREAKDOWN | 196 | 1.00 / 0.17 (6) | 1.00 / 0.17 (6) | 140, 196, 219-222 |
| BBNI | COGS_COMPONENTS | 196 | 1.00 / 0.17 (6) | 1.00 / 0.17 (6) | 139-141, 162-163, 196 |
| BBNI | DEBT_BY_LENDER | 168-173 | 0.67 / 0.67 (6) | 0.67 / 0.67 (6) | 170-174, 257 |
| BBNI | BANK_LOAN_QUALITY_NPL | 126, 127 | 0.00 / 0.00 (6) | 1.00 / 0.33 (6) | 124-127, 132, 208 |
| BBNI | BANK_LOANS_NPL | 126-131, 269, 275 | 0.00 / 0.00 (12) | 0.75 / 0.50 (12) | 125-132, 256-259 |
| BBNI | BANK_LOANS_BY_SEGMENT | 124, 220 | 0.00 / 0.00 (6) | 0.50 / 0.17 (6) | 128, 132, 219-222 |
| BBNI | BS / IS / CF | | 1.00 | 1.00 | |
| BMRI | BALANCE_SHEET | 6-13 | 0.00 / 0.00 (8) | 1.00 / 1.00 (8) | 6-13 |
| BMRI | INCOME_STATEMENT | 14-16 | 0.00 / 0.00 (6) | 1.00 / 1.00 (3) | 14-16 |
| BMRI | CASH_FLOW, REVENUE, COGS | | 1.00 | 1.00 | |
| BMRI | DEBT_BY_LENDER | 288, 330-333 | 0.00 / 0.00 (6) | 0.20 / 0.17 (6) | 288, 292, 358, 364-366 |
| BMRI | BANK_LOAN_QUALITY_NPL | 573, 576, 581, 582 | 0.00 / 0.00 (6) | 0.75 / 0.50 (6) | 549, 573, 581-584 |
| BMRI | BANK_LOANS_NPL | 229, 235-237, 573, 576, 581, 582 | 0.38 / 0.30 (10) | 0.50 / 0.33 (12) | 230-239, 549, 573 |
| BMRI | BANK_LOANS_BY_SEGMENT | 471, 496, 498, 502 | 0.25 / 0.17 (6) | 0.25 / 0.17 (6) | 470-475 |
| LSIP | PLANTATION_AREA | 62, 73, 74 | 0.67 / 0.33 (6) | 1.00 / 0.50 (6) | 61, 62, 71-74 |
| LSIP | other 8 modules | | 1.00 | 1.00 (unchanged) | |
| SSMS | PLANTATION_AREA | 19, 76-78, 134 | 0.00 / 0.00 (1) | 0.80 / 0.67 (6) | 65, 76-79, 134 |
| SSMS | DEBT_BY_LENDER | 93-95 | 0.67 / 0.33 (6) | 1.00 / 0.50 (6) | 93-97, 104 |
| SSMS | other 8 modules | | 1.00 | 1.00 (unchanged) | |

## What I changed and why

**`services/retrieval/page_router.py`** (no page numbers, no ticker rules, anchors still a third RRF list, embedder failure still raises `EmbeddingUnavailableError`):

1. **Statement queries drop notes pages.** `excluded_pages(core_query=True)` now drops pages with a notes header plus a numbered note heading.
   - Before this, BMRI's policy note (p77, "informasi kebijakan akuntansi material", which describes each statement) outranked the balance sheet.
   - Statement mode then walked back over pp70-77. BS and IS both scored 0.00.
2. **Policy exclusion also catches "ESTIMASI DAN PERTIMBANGAN" / "estimates and judgements".** This is BMRI note 3 and AALI note 38. The regex only knew the "pertimbangan, estimasi" word order.
3. **Sub-heading anchors, a new tier inside the anchor list.** The order is now:
   1. pages where a matching numbered note heading starts
   2. pages where a matching **labelled sub-heading** starts (`k. Kredit yang diberikan…`, `(iii) …`, `4. Ikhtisar kredit yang diberikan…`)
   3. `(lanjutan)` pages
   - Sub-heading pages also count as heading starts, so they do not step back a page.
   - This finds a section that lives inside another note, such as BMRI's collectibility and NPL tables in note 65k.
   - Not counted as sub-headings:
     - continued sub-headings
     - table rows (a number of 5+ characters)
     - lines where the phrase is not near the start (45 characters)
     - enumerations, meaning a comma in the matched span. This drops fair-value lists like "1. Kas dan setara kas, piutang…".
4. **`select_pages`: seeds first, then the budget.**
   - A candidate seed is skipped if an earlier seed's continuation walk would reach it (same note, not a second location). Before, it was skipped only if already chosen.
   - Every seed holds its own page. Seeds then grow in fused order into the budget that is left.
   - Before, a long first note (a lender list, a 10-page loans note) could eat the whole budget and starve a second location. SSMS DEBT went from 0.67 to 1.00 and BMRI loan quality improved.
   - I tried a pure round-robin allocation and rejected it: notes 0.853, because weak second seeds took pages from the right note.
5. **Note-start seed.** When no seed is, or reaches, a page where a matching heading starts, the best-fused heading-start page becomes one extra seed. A note's first page carries its summary table, and the RRF rarely ranks it because only the anchor leg sees it. This fixed BMRI DEBT p288. It never applies in statement mode.

**`db/seeds/page_router_queries.yaml`** (no budget changed; the three justified overrides are untouched):
- **Bank DEBT_BY_LENDER / DEBT_FACILITIES**
  - New anchors: `EFEK(-EFEK| UTANG)? YANG DITERBITKAN`, `SECURITIES ISSUED`.
  - New terms: `efek-efek yang diterbitkan`, `pemberi pinjaman`, `pinjaman bilateral`, `debt securities issued`, `lender`, `bilateral loans`.
- **DEBT_BY_LENDER ALL**: `PINJAMAN BANK` / `BANK LOANS?` anchors, and "pemberi pinjaman" / "lenders" terms. AALI titles the note "Pinjaman bank".
- **BANK_LOANS_NPL / BANK_LOAN_QUALITY_NPL / BANK_LOANS_BY_SEGMENT**
  - `PINJAMAN YANG DIBERIKAN` anchor: BBNI does not say "kredit".
  - NPL gets `KUALITAS KREDIT` / `CREDIT QUALITY`; segment gets `INFORMASI SEGMEN` / `SEGMENT INFORMATION`.
  - Collectibility-grade terms (*dalam perhatian khusus*, *kurang lancar*, *special mention*, *collectability*, *kredit bermasalah*).
  - The single generic words `lancar` / `current` / `loss` are dropped: they matched every page with current assets or profit or loss.
- **PLANTATION_AREA**
  - Anchors now target area headings: `TANAMAN PRODUKTIF`, `BEARER PLANTS`, `AREA PERKEBUNAN`, `PLANTATION AREA`, `LUAS AREAL?`, `PLASMA`.
  - `ASET BIOLOGIS` is no longer an anchor here. That note is BIOLOGICAL_ASSETS_DETAIL, and it was winning every PLANTATION_AREA route.
  - Terms: plasma and plantation-area terms.
- **CUSTOMER_CONCENTRATION**
  - Revenue-note heading anchors (`PENDAPATAN (BERSIH|NETO|USAHA)`, `PENJUALAN (BERSIH|NETO)`, `NET (REVENUE|SALES)`, `REVENUE FROM CONTRACTS`).
  - Terms that match the actual wording: "pelanggan yang melebihi 10%", "melebihi 10% dari pendapatan", "exceeding 10% of revenue". The old "transaksi penjualan melebihi 10%" required words AALI does not use.

**`tests/unit/test_page_router.py`** (17 tests, all synthetic pages):
- Updated the budget test to the new seed-first semantics.
- New tests:
  - a long first note does not starve a second seed, and a candidate inside a seed's reach is not a seed
  - the note-start extra seed, including "not in statement mode"
  - policy and estimates exclusion, and the notes-page exclusion for statement queries
  - `sub_heading_starts` accept and reject cases, and the three-tier anchor order

**Rejected experiments** (all measured on dev):
- `SEED_SCORE_RATIO` 0.6: notes recall stayed 0.888, precision fell from 0.75 to 0.56, pages per module rose from 3.7 to 4.9.
- The sub-heading tier placed after `(lanjutan)` pages: notes 0.876, because the BMRI loan-quality pages dropped.

## Remaining misses (honest)

- **BMRI DEBT_BY_LENDER 0.20.**
  - Notes 30 and 36 run 96 pages of lender tables. The router returns lender tables (bond series p292, bilateral loans pp364-366) and the note 30 start (p288).
  - It does not return the note 36 summary (330-331): the note-start rule adds only one start seed.
  - The returned pages are arguably usable answers, but they are not my gold.
- **BMRI BANK_LOANS_BY_SEGMENT 0.25.** The segment note (470-475) takes the budget. The risk-note segment tables (496/498/502) score about 0.6 of the best page and do not pass the seed ratio.
- **BMRI BANK_LOANS_NPL 0.50.**
  - The loans note (230-239) takes 10 of the 12 pages.
  - Note 65k gets one page (573). p549 is a fair-value narrative whose sub-heading "(iii) Kredit yang diberikan…" matches the anchor.
  - The Kol-by-sector page (576) and the NPL pages (581-582) are missed.
- **BMRI BANK_LOAN_QUALITY_NPL 0.75.** The Kol-by-sector page (576) is missed; p549 is noise.
  - **Comparative pages.** BMRI prints one page per period (Jun 2026 / Dec 2025 / Dec 2024). The router cannot prefer the current-period page, because it does not know the fiscal period.
- **BBNI BANK_LOANS_BY_SEGMENT 0.50.** It misses p124 (loans by type), which is a generous label anyway.
- **BBNI BANK_LOANS_NPL 0.75.** It misses note 60 pp269/275: fused score 0.68 of the best, below the ratio. Pp256-259 (fair-value note, sub-heading "Pinjaman yang diberikan") are noise.
- **BBNI DEBT_BY_LENDER 0.67.** It misses the securities-issued pages 168-169. The borrowings note wins; 169's fused score is below the ratio and it is not a heading start.
- **SSMS PLANTATION_AREA 0.80.** It misses p19, the hectare table inside note 1 *Umum*. It is rank 4 in FTS and rank 10 in ANN, but there is no heading to anchor it and it is below the seed ratio.
- **Precision drags, recall fine.**
  - BBNI REVENUE_BREAKDOWN and COGS_COMPONENTS: 0.17. Segment-table and prepaid-expense pages pass the ratio as second seeds.
  - AALI DEBT_BY_LENDER: 0.33. The pinjaman-bank note continues for 6 pages and all of it is returned.
- **Known risk from sub-heading anchors (non-dev sanity check on JKON 2021Q3 `fff5e74b…`).**
  - Core is unchanged: BS 3-5, IS 6, CF 8.
  - CASH_BANKS now returns [81-83, 32] instead of [32]. The "a) Kas dan Setara Kas" sub-heading in JKON's credit-quality section outranks note 4, because it is also FTS rank 1.
  - Recall is kept and precision drops. The same mechanism is what finds loan tables in bank risk and additional-information notes, so I kept it.
- **Expect the held-out to be lower than dev.**
  - The dev bank numbers (notes 0.62-0.82 on the two banks) are the weak spot.
  - The BMRI and AALI changes should carry over to the held-out BMRI 2025Q4 and AALI 2021Q1 filings, since they come from the same issuers. That is unmeasured.
- **Scratch tools** (session scratchpad `wsD\`, not in the repo):
  - `legs.py <doc> <MODULE> <SECTOR>` prints the FTS, ANN and anchor ranks, the fused scores and the chosen units.
  - `cmp.py a.json b.json` diffs two eval reports.
  - `sql.py`, `dump.py`.
  - Eval JSONs: `baseline.json` and `final.json`.
