# Workstream A report: ingest, embeddings, OCR, table grids, page router

Status: **all 7 required items done and verified; all gates clean.** Nothing is committed. The previous agent's partial edits to `embedder.py`, `ocr.py`, `page_quality.py`, `tables.py`, `config.py` and `.env.example` were kept and finished. Everything else was written in this run. Live tracker: `wsA_progress.md`.

## Gates (run after the last edit)

| Gate | Result |
|---|---|
| `uv run ruff check services scripts tests` | All checks passed |
| `uv run mypy services` | Success: no issues in 126 source files |
| `uv run pytest -m "not integration" tests/unit -q -p no:cacheprovider` | **408 passed** (also 408 with `EMI_EMBEDDING_MODE=fake`) |
| `pytest -m integration` on `test_m9_index_pages.py`, `test_m9_embed_pages.py`, `test_m9_page_router.py` | 4 passed, 1 skipped (the scanned-OCR test skips because it checks `shutil.which("tesseract")` and tesseract is not on PATH; see "Left open") |

## Files changed, by task id

Mapping used: item 1 → M9.2.4, item 2 → M9.2.1/M9.2.4, item 3 → M9.3.2, item 4 → M9.2.2, item 5 → M9.2.2, item 6 → M9.2.3, item 7 → M9.3.1 + M9.3.2.

| Task | Files |
|---|---|
| **M9.2.4** Embedder never fakes (item 1) | `services/narrative/embedder.py`; `services/shared/config.py` (`embedding_device="auto"`, `embedding_mode` real/fake, `embedding_max_seq_length=1024`, `embedding_batch_size`, `embedding_fp16`); `.env.example`; NEW `tests/unit/test_embedder.py` |
| **M9.2.1 / M9.2.4** Migration 025, embed worker, backfill (item 2) | NEW `db/schema/025_document_pages_v2.sql`; `services/ingest/tasks/embed_pages.py`; `scripts/backfill_page_embeddings.py`; NEW `tests/unit/test_embed_pages.py`; NEW `tests/unit/_fake_async_db.py` (shared in-memory engine) |
| **M9.2.2** OCR fails loudly (item 4) | `services/extraction/ocr.py`; `services/extraction/page_quality.py`; `config.py` (`tesseract_cmd`, `tessdata_dir`, `ocr_min_chars=50`, `ocr_dpi`); `.env.example`; NEW `tests/unit/test_ocr.py`; `tests/unit/test_page_quality.py` |
| **M9.2.2** Indexer robustness (item 5) | `services/ingest/tasks/index_pages.py`; NEW `tests/unit/test_index_pages.py`; `tests/unit/test_page_quality.py` (page-label tests) |
| **M9.2.3** Honest table grids (item 6) | `services/extraction/tables.py`; `tests/unit/test_tables.py` |
| **M9.3.2** ANN without pgvector (item 3) and router (item 7) | `services/retrieval/page_router.py`; `config.py` (`router_ann_max_pages`); `tests/unit/test_page_router.py` |
| **M9.3.1** Module query table (item 7) | `db/seeds/page_router_queries.yaml` |

`config.py` and `.env.example` also hold the user's own earlier edits. Mine are additions only. `reports_dir` / `EMI_REPORTS_DIR` came from the diff I inherited; I did not add them.

## Evidence per item

### 1. The embedder never fakes (M9.2.4)
- `Embedder()` loads `BAAI/bge-m3` on `cuda` with fp16 and `max_seq_length=1024`. It returns hash vectors only when `mode="fake"` (`model_id="fake-hash-v1"`).
- A load, encode or dimension failure raises `EmbeddingUnavailableError`. `test_embedder.py` covers all three cases. `embed()` / `embed_sync()` keep the API that `embed_narrative` uses.
- Real vectors check: cos("Laporan posisi keuangan konsolidasian", "Consolidated statement of financial position") = **0.80**; against "Beban pokok penjualan" it is 0.44.
- Throughput: after model load, about **73 pages/s** on the RTX 4070 SUPER. The old md5 path did 1,400 pages/s.

### 2. Migration 025, embed worker, backfill (M9.2.1 / M9.2.4)
- Migration 025 adds `embedding_model text`, sets CHECK `text_source IN ('pdf_text','ocr','ocr_failed')`, and adds index `(doc_id, embedding_model)`.
- It was **applied twice** to the dev DB without error. Afterwards the constraint reads `CHECK (text_source = ANY (ARRAY['pdf_text','ocr','ocr_failed']))`. I also recorded it in `schema_migrations`.
- `embed_pages` is `WORKER_VERSION="2.0"`:
  - A page is stale when `embedding IS NULL OR embedding_model IS DISTINCT FROM <model>`, so the legacy md5 vectors (model NULL) get re-embedded.
  - Each batch is committed on its own. `UPDATE … WHERE id=:pid AND md5(page_text)=:text_md5` means a page re-indexed mid-run is never overwritten with a vector of its old text. It stays stale and the run ends `partial` / worker_runs `failed`.
  - An embedder error sets worker_runs to `failed` and re-raises.
- Live run: LSIP 2025Q3 embedded 113 pages. A second run returned `already_ok`, 0 embed calls. JKON (86 pages) behaved the same.
- Backfill order is lighthouse (BMRI, LSIP), then LQ45, then the rest.
  - LQ45 membership is derived from `scripts/seed_idx_tickers.IDX_TICKERS`, not a hardcoded list.
  - Adds `--dry-run`.
  - The old auto-inspect fallback is gone: it could archive files out of `incoming_reports`.
- `--dry-run` output now:
  ```
  Model BAAI/bge-m3 on cuda: 6 document(s), 1335 stale page(s).
    [0] BMRI 2026Q2 6f214b27… stale=603/603   (legacy md5 vectors, model NULL)
    [0] BMRI 2025Q4 9a0154b0… stale=537/537
    [0] BMRI 2024Q2 cdd61743… stale=1/1
    [0] LSIP 2025Q4 9cbf5811… stale=122/122
    [0] LSIP 2025Q3 0d5a1599… stale=1/113     (one page re-indexed since my embed → correctly reset)
    [2] AALI 2021Q1 68083f0c… stale=71/71
  ```
  I did not run the full re-embed; that is the lead's job. On this GPU it would take about 20 s plus model load.

### 3. ANN without pgvector (M9.3.2)
- **Bind bug fixed.** With pgvector the query uses `ORDER BY embedding <=> CAST(:q_vec AS halfvec(1024))` (no `::vector`). A unit test asserts the SQL and the bind.
- **Fallback without pgvector.** numpy cosine (`cosine_top`) over the document's vectors, filtered to `embedding_model = embedder.model_id`. A bge-m3 query is never compared with md5 vectors. The fallback is capped by `EMI_ROUTER_ANN_MAX_PAGES=2000`.
- The query vector comes from `Embedder()`. If the embedder raises, the ANN leg is dropped with a logged error and routing continues on FTS + anchors. That is a deliberate choice.
- **Cross-lingual check.** Doc: JKON 2021Q3 (`fff5e74b…`), which is **Indonesian-only**: whole-doc hits for "the/and/of/statement/assets/cash" = 24. I sent English-only queries. The FTS leg returned **0 pages** for each. The ANN leg's top-1:

  | English query | ANN top-1 | Actual page |
  |---|---|---|
  | "statement of financial position; total assets; …" | p3 | p3 "LAPORAN POSISI KEUANGAN KONSOLIDASIAN" |
  | "cash and cash equivalents; cash in banks; time deposits" | p32 | p32 "4. Kas dan Setara Kas" |
  | "statement of cash flows; …" | p8 | p8 "LAPORAN ARUS KAS" |

### 4. OCR fails loudly (M9.2.2)
- Settings `EMI_TESSERACT_CMD` (default `C:\Program Files\Tesseract-OCR\tesseract.exe` if present) and `EMI_TESSDATA_DIR` (default `%LOCALAPPDATA%\tessdata`).
- A missing binary, missing language data, a Tesseract error or a timeout raises `OcrUnavailableError`. OCR never returns `""`.
- `needs_ocr` now uses `min_chars=50`.
- In the indexer, an OCR error or fewer than 50 characters sets `text_source='ocr_failed'`, logged as a warning with the page list.
- Scanned `BMRI_2024_TW2_RDF_Surat Pengantar Corsec - BEI Juni 2024.pdf`, doc `cdd61743…`:
  - Before: `ocr` with **0 chars**.
  - Now: `text_source='ocr'`, **1,409 chars** ("Nomor : CRL.CSC/CMA.143…/2024 … PT Bursa Efek Indonesia …").
  - Re-indexed with `EMI_TESSERACT_CMD=C:/nonexistent/tesseract.exe`: `text_source='ocr_failed'`, warning "Tesseract not runnable …". I then re-indexed normally, so it is back to `ocr`.

### 5. Indexer robustness (M9.2.2)
`index_pages` is now `WORKER_VERSION="2.0"`, with an optional `force=` kwarg.
- **Commits** every 25 pages, and table grids in 25-page batches.
- **worker_runs** goes `running`, then `ok` or `failed` with the error.
  - Probe: a doc pointing at a missing PDF gave `failed`, "FileNotFoundError: Could not load PDF bytes …". I deleted the probe rows afterwards.
- **Stale rows** are deleted: `document_page_tables` for the doc, and pages beyond the page count.
  - Probe: I inserted a bogus table row into AALI, then force re-indexed. Row count went 153 → 152 and the bogus row was gone.
- **The PDF is opened once.** OCR renders the already-open `pymupdf.Page`.
- **A changed `page_text` nulls `embedding` / `embedding_model`** so the page is re-embedded. Unchanged text keeps its vector.
- **`detect_page_label`** now accepts two forms:
  - Short standalone blocks only (≤ 32 chars): bare digits (not years 1900–2100) or a *valid* roman numeral `^[ivxlcdm]{1,6}$`, fully inside the top/bottom 8%.
  - Explicit markers ("Lampiran 5/27 Schedule", "Halaman 3", "Page 3 of 9") fully inside 12%.

  | Doc | Labelled before | Labelled now | Notes |
  |---|---|---|---|
  | AALI 2021 TW1 | 6/71, all false ("781", "2021", "63", "11", "304", "310") | **68/71** | 0 anomalies against a consistent offset. Labels are the printed "Lampiran 1/1 … 5/64" schedule ids. |
  | LSIP 2025Q3 | 110/113 | 110/113 | |
  | BMRI 2025 LK | not reported | 533/537 | i…xvii, then 1… |

- Live: AALI took 71 pages in 47 s (70 pdf_text, 1 ocr with 2,598 chars, 152 tables). JKON took 86 pages in 51 s (147 tables).

### 6. Honest table grids (M9.2.3)
Checked by calling `extract_page_grids` directly on the PDFs, no DB.

| Check | LSIP 2025 TW3 pp4–6 | BMRI 2025 LK pp22–24 |
|---|---|---|
| Tables | 6 | 6 |
| Synthetic / None / out-of-page bboxes | 0 / 0 / 0 | 0 / 0 / 0 |
| Numeric cells whose text PyMuPDF finds inside their bbox (top-left origin) | **105/105** | **109/109** |
| Cells with confidence > table confidence | 0 | 0 |
| Unit | IDR_MN | IDR_MN |

- **Note-reference cells get value null.** LSIP: `'5'`, `'27'`, `'21,27'`, `'22,27'`. BMRI: `'2c,2g,62b.(vii)'`, `'2c,2f,2g,2h,5,65d'`.
- **Mixed label+number cells.** LSIP has 47 such cells (e.g. `'Pihak berelasi … 1.993.586'`). They are valued from the trailing token with `value_from_mixed_cell=true` and confidence 0.75, against 0.85 for the table.
- **Before**, the HEAD `tables.py` on LSIP pp4–6 gave **354/354 synthetic bboxes**, and note refs `'5'`/`'27'` parsed as numbers.
- The per-page cascade is lattice → stream → pdfplumber. Every table in these filings came out `camelot_stream`; they are borderless.
- `detect_unit_from_header` spec cases pass:
  - millions/jutaan → IDR_MN; miliar/billions → IDR_BN; ribuan/thousands → IDR_K; "(Expressed in Rupiah)" → IDR; unknown → None.
  - No substring false hits: "otherwise", "column", "corporate".
  - Live: JKON gets 146 tables IDR_K; AALI gets 152 IDR_MN.
- **Decision: `USD_K`, not `USD_TH`.** Thousands are `*_K` for every currency, matching `grounding.py`'s `IDR_K` / `USD_K`. I updated the test. B has since added `USD_BN`.

### 7. Router (M9.3.1 / M9.3.2)
- **Three ranked lists fused with RRF (k=60):**
  - FTS: an OR of `plainto_tsquery(term)`. Phrase matching fails on bilingual two-column text layers, where the ID and EN lines interleave.
  - ANN.
  - Anchors: pages whose note heading or statement title matches, heading starts first, then "(lanjutan)" pages.
- **`max_pages` is a total budget per module.**
  - Seeds are taken in fused order and each extends over its real continuation pages.
  - Extra seeds need ≥ 0.7 × the best fused score, which in practice means as many legs as the best page.
  - Statement modules take one seed and walk to the statement's first and last page.
  - Note seeds step back one page only across a real continuation.
- `merge_spans` now merges touching spans. The dead code is gone (the `_get_model()` probe and the unreachable plainto fallback). `SET LOCAL statement_timeout='5000ms'` stays.
- **YAML:** default 6 is explicit on every entry, because B's `test_mcp_contracts` requires the key. Only three overrides remain, each with a comment: BANK balance sheet 8, MDA 10, BANK_LOANS_NPL 12. I also added the PSAK 72 revenue-note terms.
- **Dev-set result, LSIP 2025Q3 (`0d5a1599…`, dev labels from the spec only).** I did not run anything on `eval/router_gold/heldout/`.

  | Module | Recall | Precision | Returned |
  |---|---|---|---|
  | BALANCE_SHEET | 1.00 | 1.00 | 4, 5 |
  | INCOME_STATEMENT | 1.00 | 1.00 | 6, 7 |
  | CASH_FLOW | 1.00 | 1.00 | 9 |
  | CASH_BANKS | 1.00 | 1.00 | 54, 55 |
  | BIOLOGICAL_ASSETS_DETAIL | 1.00 | 1.00 | 59, 60 |
  | PLANTATION_AREA | 0.67 | 0.33 | 59, 60, 72–75 (misses p62, the plasma note) |
  | REVENUE_BREAKDOWN | 1.00 | 0.67 | 93–95 |
  | CUSTOMER_CONCENTRATION | 1.00 | 0.67 | 93–95 |
  | COGS_BREAKDOWN | 1.00 | 1.00 | 94, 95 |
  | **Mean** | **0.963** | **0.852** | 23 pages (micro 0.944 / 0.739) |

  - Before (old router, same harness): recall 1.00, precision **0.20**, 93 pages.
  - FTS-only mode (`use_ann=False`) gives the same numbers on this bilingual filing. ANN matters on monolingual filings (item 3).
  - Targets were recall ≥ 0.9 and precision ≥ 0.5: both met. No page numbers are hardcoded.
- Sanity check without tuning, on JKON: BS → pp3–5, IS → p6, CF → p8, CASH_BANKS → p32. All correct.

## doc_ids created or touched

| doc_id | What | How |
|---|---|---|
| `68083f0c-6659-4842-8a24-8c590f1bdcde` | AALI 2021Q1 (71 p, 152 tables), v2 index | `inspect_document` on a scratch copy + `index_pages_task` |
| `fff5e74b-8a19-480c-ab8d-41370541a30f` | JKON 2021Q3 (86 p, 147 tables, **bge-m3 embedded**), Indonesian-only, used for the cross-lingual check | same |
| `cdd61743-c12e-4e22-abea-57532a1a48bd` | BMRI 2024Q2 cover letter (1 OCR page), `doc_type='GENERIC_DISCLOSURE'` | direct INSERT, because inspection now correctly SKIPS cover letters |
| `0d5a1599-cb28-4f0b-9212-c6d447728f25` (existing, from wsB) | LSIP 2025Q3, bge-m3 embedded for the router dev eval | `embed_pages_task` |
| `00000000-0000-4000-8000-00000000a0a0` | failure probe | created and deleted, including its worker_runs row |

MinIO received thumbnails for the three new docs. The scratch PDF copies are in `…\scratchpad\wsA\`. The integration tests ran against `emimind_test` via C's conftest.

## Cross-workstream needs
- **C / lead: set fake embeddings in unit tests.** `tests/unit/conftest.py` should force fake mode. `tests/unit/test_hybrid_retriever.py::test_retrieve_narrative_mock` builds a default `Embedder()`. It now loads real bge-m3 on GPU (still passes, but slow and GPU-dependent), because the old silent hash fallback is gone. Suggested autouse fixture:
  ```python
  monkeypatch.setenv("EMI_EMBEDDING_MODE", "fake"); get_settings.cache_clear()
  ```
  With `EMI_EMBEDDING_MODE=fake` the model is never loaded and 408 tests pass.
- **Integration OCR test skips wrongly.** `tests/integration/test_m9_index_pages.py` skips its OCR test on `shutil.which("tesseract")`. It should use `get_settings().tesseract_cmd` instead, since Tesseract is not on PATH here but is configured.
- **Lead: re-embed.** `uv run python scripts/backfill_page_embeddings.py --priority all` (1,335 stale pages now), after re-indexing the wsB docs with index_pages v2. C's gate requires `embedding_model='BAAI/bge-m3'` on every page.
- **B (FYI):** `document_page_tables.cells[].bbox` is now a real top-left-origin box or `null`. Flags `note_ref` / `value_from_mixed_cell` appear only when true, and cell confidence ≤ table confidence.
- **Router consumers (`routing.py`, `router_recall.py`):** `route_pages(..., use_ann=True)` is a new keyword. Spans are sorted by score, and pages within a span are contiguous.

## Left open
- **Held-out router recall/precision not measured.** That is the lead's step 5, run on re-indexed and re-embedded docs. PLANTATION_AREA p62 is the one dev miss. I did not tune for it: the fix would be LSIP-specific.
- **Old wsB-indexed docs not re-indexed.** BMRI 2025Q4 / LSIP 2025Q4 / LSIP 2025Q3 were indexed with the old `tables.py` (fake bboxes). I left them alone because B was using them. The lead should re-index them with `force=True`, or delete and re-inspect them.
- **The router's ANN leg falls back to FTS + anchors on embedder failure**, with a logged error, rather than failing the tool call. Say if you want it to raise instead.
