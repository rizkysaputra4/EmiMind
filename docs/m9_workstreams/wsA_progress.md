# Workstream A — live progress tracker

> Resume protocol: if you are a fresh agent picking this up, read this file FIRST, then `git diff` the files listed under "Files touched". Continue from "Next action". Do NOT redo items marked `done` (re-run their verification only if a later change could have broken them).
> Update this file after every completed sub-step (before starting the next one), not only at the end.

Spec: `docs/m9_workstreams/README.md` → Workstream A. Final report: `wsA_report.md`.
Scratch (probe scripts + PDF copies): `C:\Users\rizky\AppData\Local\Temp\claude\C--Users-rizky-Documents-Code-EmiMind\1041b615-b76d-4f47-a638-0f02443221c7\scratchpad\` (`wsA\` = PDF copies; `router_dev.py` = dev-set eval; `index_docs.py`, `embed_doc.py`, `q.py` = SQL helper).

## Items

| # | Item | Status | Evidence / notes |
|---|---|---|---|
| 0 | Fix current breakage | done | config.py lambdas→callables + import blank line; ocr.py/tables.py unused ignores removed; tables.py `RawTable` alias fixes return type; index_pages rewritten. Tests not yet updated (item 8). |
| 1 | Embedder never fakes | done | Previous agent's embedder.py kept. Verified: `BAAI/bge-m3 cuda fp16 max_seq 1024`; cos(ID BS title, EN BS title)=0.80 vs 0.44 unrelated. Embedding 113 pages: 73 pages/s on GPU (batches 2+), vs 1,400 p/s hash before. |
| 2 | Migration 025 + embed_pages/backfill | done | 025 applied twice to dev DB (idempotent), registered in schema_migrations. embed_pages WORKER_VERSION 2.0, writes embedding_model, md5(page_text) guard in UPDATE, failed worker_runs on error; 2nd run = already_ok. Backfill rewritten (priority lighthouse→LQ45 from `scripts/seed_idx_tickers.IDX_TICKERS`→rest, `--dry-run`, no auto-inspect). Backfill CLI not yet run (dry-run pending). |
| 3 | ANN without pgvector | done | `CAST(:q_vec AS halfvec(1024))` for pgvector; numpy `cosine_top` otherwise; only pages with `embedding_model = embedder.model_id`. Cross-lingual on Indonesian-only JKON 2021Q3 (FTS returns 0 for EN terms): EN-only ANN top-1 = BS p3, Cash note p32, CF p8 (all correct). |
| 4 | OCR fails loudly | done | Scanned BMRI 2024Q2 cover letter: text_source=ocr, 1,409 chars (was 0). With bogus `EMI_TESSERACT_CMD`: text_source=ocr_failed, warning logged, run ok. |
| 5 | Indexer robustness | done | AALI 2021Q1: 68/71 labelled (before 6/71, all 6 false: 781, 2021, 63, 11, 304, 310); labels = "Lampiran 5/27" schedule ids, 0 anomalies; LSIP 110/113, BMRI 2025Q4 PDF 533/537 (i..xvii then 1..). Stale table probe row deleted on force re-index (153→152). Missing-PDF probe → worker_runs failed + error, probe rows deleted. |
| 6 | Table grids honest | done | LSIP TW3 pp4–6: 6 tables, 0 synthetic/None/out-of-page bboxes, numeric text found inside its bbox 105/105, note refs ('5','27','21,27','22,27') value=None, 47 mixed cells valued at conf 0.75 (table 0.85). BMRI 2025 LK pp22–24: 6 tables, 109/109 inside bbox, '2c,2g,62b.(vii)' etc → None. OLD code on LSIP pp4–6: 354/354 synthetic bboxes, note refs '5'/'27' parsed as numbers. Units: JKON 146 tables IDR_K, AALI 152 IDR_MN. Script: scratch `grids.py`, `bboxcheck.py`, `old_grid.py`. |
| 7 | Router | done | Dev set LSIP 2025Q3: mean recall 0.963 / precision 0.852 (micro 0.944 / 0.739, 23 pages). Before: recall 1.00 / precision 0.20 (93 pages). FTS-only mode gives same numbers. Only miss: PLANTATION_AREA p62. |
| 8 | Gates clean + report | done | ruff clean; mypy services clean; unit 408 passed; integration m9 index/embed/router 4 passed 1 skipped; backfill --dry-run: 6 docs / 1,335 stale pages; report written. |

## Current step
DONE. All items verified, gates clean, report written (`wsA_report.md`).

## Next action
None for WS A. Lead: see "Cross-workstream needs" in `wsA_report.md` (fake-embedding autouse in tests/unit/conftest.py; re-index wsB docs with force=True; run backfill --priority all; held-out recall).

## Files touched
- `services/narrative/embedder.py` — (prev agent) bge-m3, device auto, fake only in mode=fake, EmbeddingUnavailableError, model cache, `model_id`.
- `services/extraction/ocr.py` — (prev agent) OcrUnavailableError, settings tesseract_cmd/tessdata_dir, `ocr_page(page: pymupdf.Page)`, `ocr_pdf_page(bytes, n)`; I removed 2 unused ignores.
- `services/extraction/page_quality.py` — min_chars 50, `non_whitespace_len`; restored `"\ufffd"` escape.
- `services/extraction/tables.py` — (prev agent) cascade, real bboxes, units, note refs, mixed cells; I added `RawCell`/`RawTable` aliases, removed unused ignore.
- `services/shared/config.py` — (prev agent) embedding_*/tesseract/ocr/router settings; I fixed ruff (callables for default_factory, blank line). `reports_dir` may be user's own edit — leave.
- `.env.example` — (prev agent) keys added; nothing more needed.
- `db/schema/025_document_pages_v2.sql` — NEW: embedding_model col, text_source CHECK + ocr_failed, index (doc_id, embedding_model).
- `services/ingest/tasks/index_pages.py` — REWRITTEN: v2.0, OCR on open page, ocr_failed, 25-page commits, running/failed/ok worker_runs, stale page/table deletion, embedding reset when page_text changes, `force=` kwarg, new `detect_page_label`.
- `services/ingest/tasks/embed_pages.py` — REWRITTEN: v2.0, stale = NULL or other model, md5 guard, failed worker_runs, duck-typed embedder ok.
- `scripts/backfill_page_embeddings.py` — REWRITTEN (see item 2).
- `services/retrieval/page_router.py` — REWRITTEN: 3-leg RRF, note-heading parser, budget-limited greedy selection, SEED_SCORE_RATIO 0.7, statement mode (1 seed, walk back/forward on same title), touching-span merge, FTS = OR of plainto_tsquery.
- `db/seeds/page_router_queries.yaml` — every entry has explicit `max_pages: 6` (B's test_mcp_contracts requires the key) except justified 8 (BANK BS), 10 (MDA), 12 (BANK_LOANS_NPL); added PSAK 72 revenue terms.
- tests: `test_tables.py`, `test_page_quality.py`, `test_page_router.py` (updated); NEW `test_embedder.py`, `test_ocr.py`, `test_index_pages.py`, `test_embed_pages.py`, `_fake_async_db.py`.
- router: `select_pages(exclude=...)` so statement walk-back never enters TOC/excluded pages; `is_core_statement_query` also checks terms (fixed integration bilingual test).
- `embed_pages.py`: SQL now literal constants (ruff S608).
- `index_pages.py`: 4 `type: ignore[no-untyped-call]` for pymupdf.

## DB changes / doc_ids created
- Migration 025 applied (twice) + row in `schema_migrations`.
- Embedded (bge-m3) existing wsB doc `0d5a1599-cb28-4f0b-9212-c6d447728f25` (LSIP 2025Q3, 113 pages) — needed for router dev eval.
- Created via `inspect_document` + `index_pages_task` v2: `68083f0c-6659-4842-8a24-8c590f1bdcde` AALI 2021Q1 (71 p, 152 tables), `fff5e74b-8a19-480c-ab8d-41370541a30f` JKON 2021Q3 (86 p, 147 tables, embedded bge-m3; Indonesian-only, for cross-lingual check).
- Created by direct INSERT (inspection now SKIPS cover letters): `cdd61743-c12e-4e22-abea-57532a1a48bd` BMRI 2024Q2 cover letter, doc_type GENERIC_DISCLOSURE (1 OCR page).
- Probe doc `00000000-0000-4000-8000-00000000a0a0` (WSA_TEST) created and deleted, with its worker_runs row.

## Decisions & gotchas
- **USD_K not USD_TH**: tables.py emits `{IDR,USD}_{K,MN,BN}`; `services/mcp/grounding.py` (WS B) maps USD_K/USD_MN (no USD_TH, no USD_BN) → update test to USD_K; tell B to add USD_BN.
- inspect_document dedupes by doc_hash, so copies of wsB's docs map to the same doc_id; don't delete wsB docs (B may be using them).
- Page labels: spec rule (bare digits/roman fully inside top/bottom 8%) + explicit markers ("Lampiran 5/27", "Halaman 3", "Page 3 of 9") inside 12% — AALI's only printed page ids are "Lampiran x/y" at 8.5–11% of height. Years 1900–2100 rejected; roman validated.
- Router: note headings with "(lanjutan)" on the next wrapped line; upper-case ratio computed after stripping the marker (otherwise "(lanjutan)" hides the heading). Title-case headings accepted when short & digit-free (JKON style).
- Router: phrase FTS fails on bilingual two-column pages (interleaved lines) → per-term AND (plainto) ORed.
- Heredoc python edits with `\\n` inside triple-quoted strings produced literal newlines once; use the Edit tool for regex/escape-heavy code.
- WS B added USD_BN to grounding (coordinator, after my note). WS C done; gate expects embedding_model='BAAI/bge-m3' on all pages.
- Never tune on `eval/router_gold/heldout/` (BMRI_2025Q4, LSIP_2025Q4, AALI_2021Q1). JKON/AALI routing outputs were only sanity-checked, not tuned.
