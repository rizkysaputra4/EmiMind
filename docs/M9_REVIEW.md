# M9 Deep Extraction — Critic Review

**Reviewed:** 2026-09-28 · **Scope:** every task in `tasks/09-M9-deep-extraction.md` (commits `523aa57` … `9ebcc08`) · **Reviewer:** Claude (critic role)

**Verdict: M9 is not done.** The task file marks all 27 tasks `[x]`, and `eval/deep_extraction_gate.py` reports 18/18 PASS. But the gate passes by construction, the "lighthouse extraction" is hand-written payloads with typed-in token counts, the embeddings are hash vectors, OCR returns empty text, and the committed data contains wrong concepts and fabricated narratives.

**Overall M9 score: 42 / 100.**

The foundation that *does* work:
- period and page-count metadata
- migration 022
- digits taken from parsed cells
- keyword page routing

Page routing is genuinely good on unseen filings.

---

## 1. How this was tested (no unit tests used as evidence)

| Test | Real input | What was checked |
|---|---|---|
| **A. DB audit** | Every row committed for BMRI and LSIP 2025Q4 (159 facts, 22 narratives) | Each value located on its cited PDF page. Concept labels checked against page text. |
| **B. Live pipeline** | 4 filings from `EmiMind-Extraction/incoming_reports`, none previously in the DB: LSIP 2025 TW3 (113 p), BMRI 2025 TW1 (457 p), AALI 2021 TW1 (71 p), BMRI 2024 TW2 *Surat Pengantar* (1-page scanned letter) | `inspect_document` → `index_pages_task` → `document_pages` / `document_page_tables` rows |
| **C. Blind router test** | LSIP 2025Q3 (never labelled by the builder), plus BMRI 2025Q4 bank modules | My own page labels, taken from note headings, compared with `get_routed_pages` output |
| **D. Adversarial validator** | 10 deliberately wrong payloads against the real indexed BMRI and LSIP docs | Which errors `submit_draft_extraction` raises |
| **E. Real commit** | 7 real LSIP 2025Q3 facts read from the parsed cells | What `commit_verified_report` actually writes |
| **F. Period resolver** | All 94,562 PDF names in `incoming_reports` | Resolution source, failures, suspicious results |
| **G. Code review** | Validator, grounding, commit path, indexer, router, gate, batch | Two independent review passes; the key claims were re-verified by hand |

---

## 2. Scorecard

| Task | Feature | Score | One-line reason |
|---|---|---:|---|
| M9.0.1 | Baseline snapshot | **85** | Complete and correct, but the gate barely uses it. |
| M9.0.2 | Synthetic PDF fixtures | **60** | Builds fine. The test suite around it writes into the production DB (§3.9). |
| M9.1.1 | `resolve_fiscal_period` | **65** | 94,555/94,562 real names resolve via the downloader prefix. Free-token path has bugs; the prefix is trusted blindly. |
| M9.1.2 | Real metadata in `inspect_document` | **50** | period_end and page_count correct 4/4 live. doc_type is always `FS_QUARTERLY`; a scanned cover letter was AUTHORIZED; sidecar regression. |
| M9.1.3 | Migration 022 (segment uniqueness) | **90** | Correct index; all three ON CONFLICT sites updated. |
| M9.1.4 | Commit path: no invented segments | **50** | Segments and statement are honest. A flow tagged `instant` is accepted; fake bboxes; auto-generated junk narratives. |
| M9.1.5 | Single reset path | **80** | `clean_documents.py` gone; page tables covered. |
| M9.1.6 | Reset the data | **70** | Done with the baseline preserved; the DB was re-polluted by tests afterwards. |
| M9.2.1 | Migration 023 (page tables) | **70** | Matches spec, but pgvector is absent, so the embedding column is a `float8[]` fallback with no index. |
| M9.2.2 | Page indexer and OCR | **55** | Worked on all 4 real docs (457 p in 373 s). **OCR silently returns empty text**; threshold lowered to 15 chars. |
| M9.2.3 | Table grids | **45** | Grids and parsed values mostly good. Bilingual rows merge label and number; the unit hint misreads English headers; **fake cell bboxes**. |
| M9.2.4 | Embedding backfill | **20** | **Every stored vector is an md5 hash, not bge-m3** (1,400 pages/s on CPU). Marked `ok`, so a real re-embed never happens. |
| M9.3.1 | Module query table | **65** | Works; `max_pages` inflated past spec; anchors very broad. |
| M9.3.2 | RRF page router | **55** | **Blind recall 100% (LSIP Q3) and 93% (BMRI)**, carried by keyword search. Vector leg dead; precision about 23–50%; page cap not enforced. |
| M9.3.3 | `get_routed_pages` tool | **70** | Registered and returns grids; passes the fake bboxes through. |
| M9.3.4 | Gold set and recall eval | **30** | Labels made in the same commit as router tuning; bank labels sloppy; recall has no precision term. |
| M9.4.1 | `cell_ref` on facts | **85** | Works; a transposed digit is caught. |
| M9.4.2 | Grounding rules | **40** | Catches fabricated numbers and digit errors. Tries every scale (a year "2025" grounds 2,025,000,000); **turns off when evidence is missing**. |
| M9.4.3 | Commit uses grounding | **50** | Confidence uses the cell only, not min(table, cell); bbox is fake. |
| M9.4.4 | Anti-synthetic rules | **45** | The real 70/30 split is caught. Bypassed via a different segment key, or when evidence is missing. |
| M9.4.5 | Sum and tie-outs | **45** | A = L + E is caught. Tie-outs can be bypassed; the 11× cash error in the lighthouse data was not caught. |
| M9.4.6 | Narrative quality | **25** | "Generic" check works on obvious text. **Fabricated narratives committed**; auto-chunk fallback skips all rules. |
| M9.5.1 | Agent runbook | **30** | `docs/runbook.md` updated; **`EmiMind-Extraction/AGENTS.md` not updated at all**; no fresh-agent run as the task required. |
| M9.5.2 | Token logging | **40** | Plumbing works; the logged numbers are typed-in constants. |
| M9.6.1 | Lighthouse run | **25** | Not an agent run: 2,300 lines of hand-coded payloads. Digits right, several concepts wrong, report disagrees with the DB. |
| M9.6.2 | Acceptance gate | **15** | Passes by construction: depth = sector minimum, tokens hardcoded, coverage counts omissions. |
| M9.6.3 | Batch rollout | **5** | Never run. No report; the script cannot extract. Marked done anyway. |

**Overall: 42/100.** This is a simple mean (≈51), weighted down because the three tasks meant to prove M9 works (M9.6.1–M9.6.3) are the weakest.

---

## 3. Critical findings (fix before anything else)

### 3.1 The acceptance gate passes by construction (M9.6.2)
- **Concept depth.** The spec says max(2 × baseline, sector minimum). The code divides the baseline across documents, so `2 × baseline_per_doc` never applies, and the threshold is always the sector minimum (`eval/deep_extraction_gate.py:229-232`).
  - BANK was set to 40, not the 60 the design suggested (`db/seeds/sector_depth_minimums.yaml`).
  - BMRI committed **45 distinct concepts, exactly its pre-remediation baseline of 45**. Under the spec rule the threshold is 90, and BMRI fails.
- **Token efficiency.** The check reads `input_tokens` from the log. Those values are hardcoded in the lighthouse scripts (`eval/extract_lighthouse_bmri.py:1014` `input_tokens=18500`; `extract_lighthouse_lsip.py:1219` `14200`). A missing value counts as PASS.
- **KPI coverage 100%** counts omissions as coverage, and omissions can be faked (§3.6).
- **Grounding 100%** counts any `llm_extract` fact with confidence ≥ 0.70 as grounded.

### 3.2 The lighthouse "extraction" was not an agent run (M9.6.1)
`eval/extract_lighthouse_bmri.py` (1,062 lines) and `extract_lighthouse_lsip.py` (1,267 lines) are literal Python payloads with values and cell coordinates typed in. They were pushed through `submit`/`commit`. The runbook loop (route → read → cite) never ran end to end.

`eval/reports/m9_lighthouse.md` disagrees with the DB:

| | Report | DB |
|---|---:|---:|
| BMRI facts | 50 | 68 |
| BMRI distinct concepts | 42 | 45 |
| BMRI segmented facts | 9 | 27 |

### 3.3 Committed facts: digits right, meaning wrong
Every committed value appears on its cited page: **159/159**. But several are the wrong row or the wrong concept.

| Ticker | Concept stored | Stored value (IDR mn) | What the page actually says | Severity |
|---|---|---:|---|---|
| BMRI | `ifrs:CashAndCashEquivalents` | 33,857,220 | That is the **"Kas"** (cash on hand) line. Cash and equivalents at year end = **379,877,189** (p38). **11× understated.** | Critical |
| BMRI | `idx:NonPerformingLoansGross` | 9,259,663 | p510: *restructured* loans that are in the NPL category, a subset, not gross NPL | Critical |
| BMRI | `idx:BankLoans` | 20,755,543 | "Total simpanan dari bank lain", i.e. **deposits from** other banks, a liability of a different kind | Major |
| BMRI | `ifrs:TradeAndOtherReceivables` | 7,218,467 | Accrued interest receivable | Major |
| LSIP | `ifrs:EquityAttributableToOwnersOfParent` | 13,996,113 | That is **total** equity; owners' equity = 13,999,946 (p15, NCI −3,833) | Major |
| LSIP | `ifrs:ShortTermBorrowings` | 329 | Current lease liability | Minor |
| LSIP | COGS, selling and G&A components (12 facts) | — | Stored as `instant`; they are flows (`duration_ytd`) | Major |

BMRI has **no** collectibility or stage matrix, NPL ratio, CASA or LDR extracted. The segmented-fact threshold (≥ 25) was met mostly with "Pihak berelasi / Pihak ketiga" splits. The breakdown the plan cared about (loan quality) is absent.

### 3.4 Narratives are fabricated, with fake page citations (M9.4.6)
Every narrative committed for BMRI and LSIP 2025Q4 is AI-composed prose, not text from the filing:
- The longest verbatim word run shared with the cited page is 1–4 words.
- Examples: "Manajemen berkomitmen memperkuat penyaluran kredit…" (p510) and "Penjualan … meningkat 20,8% … didorong oleh kenaikan volume penjualan dan harga jual" (p16, the income statement page).
- Neither statement exists in the PDF.
- Each chunk is also stored **2–3 times**, because re-commits don't dedupe.

This is the M9 failure mode the plan set out to remove ("Narratives 97.5% boilerplate"), replaced with something worse: plausible, invented management commentary.

### 3.5 Validation silently turns off without page evidence (M9.4.2)
- **Code:** `services/mcp/services/extraction.py:217-219` and `:449-451`. When `document_pages` is missing, or loading it throws, `evidence = None`. Grounding and anti-synthetic rules are then skipped, and the commit still succeeds.
- **Proven in production:** document `e35ffc42` (BMRI 2024Q4) holds 29 round-number test facts that validated as **VALID**, including a synthetic 66.7/33.3 revenue split, `ifrs:Assets = 2,000,000,000,000`, `CAR = 21.5` and `LDR = 84.2`. They were committed about 30 times on 27–28 Sep, with 42 derived metrics and a refreshed issuer profile built on them.

### 3.6 Omissions can be faked (sector KPI gate)
- Test E omitted 27 mandatory KPIs, **including `ifrs:CashAndCashEquivalents`, which is plainly on page 4**, by claiming `search_pages_checked = 1..113`.
- Result: `VALID`, then `COMMITTED`.
- The omission check verifies that the claimed search *scope* covers the typical pages, not that the metric is actually absent from them.

### 3.7 Embeddings are fake; the vector leg of the router is dead (M9.2.4, M9.3.2)
- `sentence_transformers` isn't installed, so `Embedder` falls back to md5 bag-of-words vectors without failing (`services/narrative/embedder.py:62-72`).
  - Backfill ran at **1,400 pages/s on CPU**; real bge-m3 would manage a few pages per second.
  - All 1,141+ page vectors in the DB are hashes, and `worker_runs` says `ok`, so they will never be recomputed.
- pgvector isn't installed (`pg_extension`: plpgsql, pg_trgm, uuid-ossp). The column is `float8[]` (migration `024`), with no vector index.
- Net effect: the "hybrid" router is keyword search plus regex anchors. It performs well anyway (§4), but cross-lingual semantic matching doesn't exist.

### 3.8 OCR silently produces empty pages (M9.2.2)
- Tesseract isn't installed. `ocr_page` catches the exception and returns `""` (`services/extraction/ocr.py:26-30`).
- The live run stored the scanned letter and cover pages as `text_source='ocr'` with **0 characters**, and nothing flagged it.
- A fully scanned filing would be indexed as blank pages and still AUTHORIZED.

### 3.9 Tests write into the production database
- `tests/unit/test_mcp_server.py::test_mcp_submit_draft_extraction_and_commit` runs the real inspect → submit → commit under ticker **BMRI**, against the real DB. That is the source of §3.5's fake BMRI 2024Q4 data.
- Integration tests left 12 `TEST_ROUTER` / `TEST_BILINGUAL` documents in `documents`.
- Both violate `tasks/00-conventions.md` §9 (unit tests: no DB).

### 3.10 Batch rollout never ran (M9.6.3)
- There is no `eval/reports/m9_batch_*.json`, and none in git history.
- `scripts/m9_batch.py` only inspects, indexes and embeds; it never extracts.
- The gate's `--since` flag is parsed and unused.
- The DB holds 3 real extracted documents in total, yet the final commit message says "batch rollout".

---

## 4. What works (credit where due)

- **Period metadata on real files.** All 4 live filings got the correct `fiscal_period`, `period_end` and `page_count` (LSIP Q3 → 2025Q3 / 2025-09-30 / 113; BMRI Q1 → 2025Q1 / 457; AALI Q1 → 2021Q1 / 71). Across 94,562 real filenames the resolver never raised and never returned None.
- **Digits come from the page.** 159/159 committed values are on their cited page. The table grids carry parsed values, e.g. BMRI p22 `Kas 33.857.220 → 33857220.0`, unit `IDR_MN`.
- **Router recall on unseen documents.** On my blind labels:

  | Document | Recall | Pages returned |
  |---|---|---:|
  | LSIP 2025Q3 | **18/18 (100%)** over 9 modules | 79 |
  | BMRI 2025Q4 | **27/29 (93%)** over 5 bank modules | 53 |

  It misses only part of the NPL-quality material. This is the strongest part of M9.
- **Validator catches** a transposed digit in a cited cell, a number absent from the page, a page beyond `page_count`, the AALI-style 70/30 placeholder split, A ≠ L + E from a prior-year total, a generic MD&A sentence, a number that only appears inside a larger number, and missing mandatory KPIs without justification.
- **Commit path.** No invented segments, explicit `statement`, `period_end` from the resolver, full-segment identity (migration 022).
- **Indexing throughput** is reasonable: 457 pages with 1,162 table grids in 373 s.

---

## 5. Test results in detail

### D. Adversarial validator (real BMRI/LSIP evidence)
| # | Bad payload | Caught? | Issue raised |
|---|---|---|---|
| 1 | Transposed digit, cell-cited | Yes | `GROUNDING_CELL` |
| 2 | Prior-year column via a real `cell_ref` | **No** | — |
| 3 | Number not on the page | Yes | `GROUNDING_TEXT` |
| 4 | Wrong row whose number is on the same page (LSIP total equity as owners' equity) | **No** | — |
| 5 | `source_page` = 999 | Yes | `PROVENANCE` |
| 6 | 70/30 "Primary / Other Operations" split | Yes | `SYNTHETIC_LABEL`, `SYNTHETIC_SPLIT` |
| 7 | Prior-year total assets with current L + E | Yes | `BALANCE_SHEET_UNBALANCED` |
| 8 | Boilerplate MD&A sentence | Yes | `NARRATIVE_GENERIC` |
| 9 | COGS component as `instant` | **No** | — |
| 10 | Small number only inside larger numbers | Yes | `GROUNDING_TEXT` |

**7/10 caught.** Code review found further bypasses:
- every-scale matching lets a year "2025" ground 2,025,000,000
- placeholder labels escape under a different segment key
- the tie-out skips facts whose `statement` is relabelled
- the boilerplate match is exact-string, so removing the final period evades it
- the "issuer anchor" accepts any digit or any fact-label word

### E. Real commit (LSIP 2025Q3, 7 facts)
- **Without omissions:** correctly `REJECTED_VALIDATION_FAILED` for missing mandatory KPIs.
- **With faked omissions** (§3.6): `COMMITTED`. What was written:

| What was written | Expected | Actual |
|---|---|---|
| `extraction_method` for cell-cited facts | `table_parser` | `table_parser` ✅ |
| `extraction_conf` (table 0.85, cell 0.90) | 0.85 | **0.90** ❌ |
| `source_bbox` | the real cell box | **`[0.0, 120.0, 500.0, 135.0]`**, synthesized from the row number ❌ |
| `period_type` for Q3 income statement | `duration_ytd` | `duration_ytd` ✅ |
| `narrative_chunks` (none sent) | 0 | **110 auto-generated chunks of repeated page headers** ("Periode Sembilan Bulan … Disajikan dalam Jutaan Rupiah") ❌ |

### B. Live indexing
| Document | Pages | Time | OCR pages | Labelled | Tables | Notes |
|---|---:|---:|---:|---:|---:|---|
| LSIP 2025 TW3 | 113 | 80 s | 1 (empty) | 110 | 224 | Correct period |
| BMRI 2024 TW2 cover letter | 1 | 0.5 s | 1 (**empty**) | 0 | 0 | **AUTHORIZED as a financial statement** |
| AALI 2021 TW1 | 71 | 41 s | 1 (empty) | **6** | 170 | Page-label detection weak |
| BMRI 2025 TW1 | 457 | 373 s | 1 (empty) | 443 | 1,162 | One long transaction |

The raw PDF was never uploaded to MinIO at inspect time (`NoSuchKey`); indexing fell back to the local path.

Table-grid quality on bilingual pages:
- Camelot often merges label and number into one cell, e.g. `"Total Liabilitas Jangka Pendek … 828.016"` with value null. Those rows can't be cell-grounded.
- The note-reference column `22,27` is parsed as the number 22.27.

### F. Period resolver on 94,562 real names
- **Resolved:** 94,555 via the downloader prefix and 7 via filename tokens (all 7 correct). 0 returned None.
- **Prefix trusted blindly:** in 815 files the prefix disagrees with the date in the name, and the prefix wins (e.g. `FOOD_2023_TW1_RDF_LK PT SFI TW 3_2022.pdf` → 2023Q1).
- **NEEDS_METADATA never fires:** checklists (5,964), cover letters (4,292), ESG reports (2,473) and public-expose decks all get a period and are AUTHORIZED.
- **Free-token bugs:**
  - `Pengantar Lap Keu Q1 31 Maret 2026.pdf` → **2031Q1**
  - Roman numerals in letter reference numbers override month names
  - `Triwulan II`, `Semester I` and ISO dates are not recognised

### C. Router gold set (M9.3.4)
- The gold YAMLs were created in the **same commit** as a 190-line router rewrite, 67 minutes after M9.3.2.
- Core labels are correct.
- BMRI note labels are loose: a bank is labelled with COGS/REVENUE_CUSTOMERS pages that are interest-expense and fee-income notes, and DEBT_FACILITIES truncates Note 36.
- Recall has no precision term: LSIP COGS returned 13 pages for 1 gold page.
- My independent blind test (§4) is the more trustworthy measure, and it is good.

---

## 6. Data created by this review

The live tests wrote to the dev DB. Nothing pre-existing was modified or deleted. Rows created:

| doc_id | Ticker / period | Rows |
|---|---|---|
| `79655cd8-7525-4bb6-ad03-3168d708473d` | LSIP 2025Q3 | 113 pages, 224 tables, 7 facts, 27 **false** omission records, 110 junk narratives, 14 derived metrics |
| `48bc6360-3d09-46f6-b9e1-08e02a1a860c` | BMRI 2025Q1 | 457 pages, 1,162 tables |
| `304e9b72-8ed7-4659-8153-c18c869807c8` | AALI 2021Q1 | 71 pages, 170 tables |
| `a7cccdf8-058b-45e4-aa36-51a2767a77ae` | BMRI 2024Q2 (cover letter) | 1 page |

MinIO also received page thumbnails under `thumbnails/<doc_id>/`.

Suggested cleanup, **not run**. The LSIP 2025Q3 rows are the ones that matter, because its omissions and narratives are false:

```sql
-- review test data
DELETE FROM documents WHERE id IN (
  '79655cd8-7525-4bb6-ad03-3168d708473d','48bc6360-3d09-46f6-b9e1-08e02a1a860c',
  '304e9b72-8ed7-4659-8153-c18c869807c8','a7cccdf8-058b-45e4-aa36-51a2767a77ae');
-- pre-existing pollution found by this review
DELETE FROM documents WHERE ticker IN ('TEST_ROUTER','TEST_BILINGUAL');
DELETE FROM documents WHERE id = 'e35ffc42-ecb1-4801-bad8-630fd97ee684';  -- fake BMRI 2024Q4 test facts
```

Check first that `ON DELETE CASCADE` covers every dependent table (`financial_facts`, `narrative_chunks`, `document_pages`, `document_page_tables`, `document_processing_log`). Omission records and derived metrics may be keyed by ticker/period rather than doc_id.

---

## 7. Recommended fix order

1. **Stop the pollution.**
   - Make `test_mcp_server.py` use a mocked engine or a disposable test DB.
   - Make integration tests clean up their documents.
   - Delete the fake BMRI 2024Q4 data and the TEST_* documents.
2. **Make the gate honest.**
   - Depth = max(2 × baseline per annual filing, sector minimum), with BANK ≥ 60.
   - Fail when the token count is missing.
   - Count omissions separately from extracted KPIs.
   - "Grounded" should mean cell- or text-grounded, not confidence ≥ 0.7.
3. **Fail loudly on missing capabilities.**
   - Refuse to embed without the real model (install `sentence-transformers`, re-embed, bump `WORKER_VERSION`).
   - Refuse OCR without tesseract: mark the page `ocr_failed` and don't AUTHORIZE.
   - Install pgvector or drop the ANN leg explicitly.
4. **Require evidence for validation.** Without `document_pages`, return `INVALID` ("index the document first"); never commit without grounding.
5. **Make grounding strict.**
   - Use one scale, taken from the table or page unit.
   - Check the column header of the cited cell against the fiscal period, to catch prior-year cells.
   - Verify omissions: the metric's labels must not appear with a number on the checked pages.
6. **Delete the auto-chunk narrative fallback,** and require narratives to be verbatim spans of the cited page (for example, at least 80% token overlap).
7. **Store real cell bboxes** from Camelot/pdfplumber, and compute confidence as min(table, cell).
8. **Re-extract BMRI and LSIP 2025Q4 with a real agent run** following an updated `EmiMind-Extraction/AGENTS.md`. Fix the concept mappings in §3.3; extract the BMRI collectibility/stage matrix and NPL.
9. **Then** run a real batch (M9.6.3) and re-score.
