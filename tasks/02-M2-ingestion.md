# M2 — Ingestion (Weeks 5–10)

**Goal:** the ingestion chain populates `financial_facts` and `narrative_chunks` (structure only for L4 — embeddings land in M3). XBRL sidecars take the fast path. Concept mapping fuzzy-matches to canonical IDs; unmatched labels go to a review queue. Eval Suite A hits ≥ 95% on 10-ticker corpus (banks + coal miners).

**Prerequisite:** M1 exit gate green.

---

## 1. External extraction tooling

### M2.1.1 — Add extraction dependencies
**File:** `pyproject.toml` (edit)

Add to production dependencies:
- `pdfplumber>=0.11`
- `camelot-py[base]>=0.11`
- `pytesseract>=0.3`
- `Pillow>=10`
- `pymupdf>=1.24`  # fitz, for page image rendering
- `arelle-release>=2.28`  # XBRL parser
- `fasttext-langdetect>=1.0.5` (or `pycld3` if fasttext binaries are painful on Windows)
- `python-slugify>=8.0`
- `rapidfuzz>=3.9`
- `polars>=1.0`  # for tables.parquet handling

**System requirements** (documented in README):
- `tesseract` binary with `ind` and `eng` language packs installed on host.
- `ghostscript` (Camelot dependency for lattice mode).

**Acceptance:**
- `[RUN]` `uv sync` succeeds.
- `[RUN]` `uv run python -c "import pdfplumber, camelot, pytesseract, fitz; from arelle import Cntlr"` succeeds.
- `[RUN]` `tesseract --list-langs` shows `ind` and `eng`.

### M2.1.2 — Extraction module skeleton
**Files:**
- `services/extraction/pdf.py`
- `services/extraction/tables.py`
- `services/extraction/ocr.py`
- `services/extraction/xbrl.py`
- `services/extraction/concepts.py`

All modules are **pure functions**: they take bytes / paths / models in, return Pydantic models out. No DB access, no MinIO access, no async. The `ingest` layer wraps them in workers that do IO.

Add to `services/shared/types.py`:
```python
class PageContent(BaseModel):
    page_num: int
    text: str
    language: Language
    has_text_layer: bool
    bbox_by_char: list[tuple[str, BBox]] | None = (
        None  # optional, populated when we need char-level
    )


class TableCell(BaseModel):
    row: int
    col: int
    text: str
    bbox: BBox
    confidence: float = Field(ge=0.0, le=1.0)


class ExtractedTable(BaseModel):
    page_num: int
    cells: list[TableCell]
    extraction_method: Literal["camelot_lattice", "camelot_stream", "ocr", "llm"]
    confidence: float


class ExtractedFact(BaseModel):
    concept_local: str
    value_numeric: Decimal
    unit: str
    period_type: Literal["instant", "duration_qtd", "duration_ytd"]
    segment: dict[str, str] | None = None
    source_page: int
    source_bbox: BBox
    confidence: float
    method: ExtractionMethod
```

**Acceptance:** modules importable, empty function stubs.

---

## 2. `parse_layout` worker

### M2.2.1 — PDF parsing
**File:** `services/extraction/pdf.py`

Function: `parse_pdf(pdf_bytes: bytes) -> list[PageContent]`.
- Uses `pdfplumber` to extract text + language detection per page.
- Language detection: `fasttext-langdetect` per-page on first 500 chars; if unsure, mark `mixed`.
- If page has <100 chars of text, mark `has_text_layer=False` (OCR pass will handle it in the tables worker).
- Emits one `PageContent` per page.

### M2.2.2 — Worker task
**File:** `services/ingest/tasks/parse_layout.py`

`WORKER_VERSION = "1.0"`.

Behavior:
1. Check `worker_runs` for `(doc_hash, "parse_layout", WORKER_VERSION)`. If `ok`, return early.
2. Read PDF from MinIO via `documents.minio_key`.
3. Call `parse_pdf(...)`.
4. Write pages as JSONL to MinIO at `{minio_key}.pages.jsonl`.
5. Update `documents.status = 'parsed'`, `documents.page_count = len(pages)`.
6. Write `worker_runs` `ok` row.
7. Return `{"pages": len(pages)}`.

Register in `services/ingest/worker.py`.

**Acceptance:**
- Integration test: upload a real PDF (add a small fixture PDF to `tests/fixtures/sample_bmri.pdf`), enqueue `parse_layout`, assert `pages.jsonl` object exists in MinIO with N rows matching page count.
- Idempotency test: run twice, second run is a no-op (log shows "already ok").

---

## 3. `extract_tables` worker

### M2.3.1 — Table extraction cascade
**File:** `services/extraction/tables.py`

Function: `extract_tables(pdf_bytes: bytes, pages: list[PageContent]) -> list[ExtractedTable]`.

Implement the cascade from BLUEPRINT §7.2:
1. For each page **without** a text layer: OCR image via `pytesseract` (`lang="ind+eng"`), retry table detection on OCR output. Confidence 0.7.
2. For each page **with** a text layer: try `camelot.read_pdf(..., flavor='lattice')`. If ≥1 table and `report.accuracy > 80`, emit with confidence 0.95.
3. Else try `camelot.read_pdf(..., flavor='stream')`. If ≥1 table, emit with confidence 0.85.
4. Else return empty for that page. (LLM extraction is a future stretch; do not implement in M2.)

Bbox for each cell comes from Camelot's cell metadata.

### M2.3.2 — OCR module
**File:** `services/extraction/ocr.py`

Function: `ocr_page(pdf_bytes: bytes, page_num: int) -> str`. Renders page via `pymupdf`, calls `pytesseract.image_to_string(..., lang="ind+eng")`.

### M2.3.3 — Worker task
**File:** `services/ingest/tasks/extract_tables.py`

`WORKER_VERSION = "1.0"`.
Behavior:
1. Idempotency check.
2. Read PDF and `pages.jsonl` from MinIO.
3. Call `extract_tables(...)`.
4. Serialize to Parquet via `polars` and upload as `{minio_key}.tables.parquet`.
5. `worker_runs` ok.
6. Return `{"tables": len(tables)}`.

**Acceptance:**
- Integration test with fixture PDF that contains ≥1 known table produces the parquet file.
- Rows with `extraction_method='camelot_lattice'` outnumber `camelot_stream` on a real IDX filing (sanity check).

---

## 4. `xbrl_sidecar` worker (fast path)

### M4.1 rationale — this is the single biggest ingestion accelerator (BLUEPRINT §7.3). Prioritize it.

### M2.4.1 — Taxonomy alias table
**File:** `db/schema/005_xbrl_taxonomy.sql`
**Copy verbatim:** appendix-schemas.md § "005_xbrl_taxonomy.sql"

Includes `xbrl_alias(taxonomy_concept text PRIMARY KEY, canonical_concept_id text NOT NULL, description text)`.

**Acceptance:** migration applies; loader seed script (M2.4.2) can insert.

### M2.4.2 — Seed the IDX XBRL taxonomy
**File:** `db/seeds/xbrl_alias_seed.csv`

Founder-curated mapping of IDX XBRL concept URIs → canonical `concept_id`. Minimum for M2: the 30 most common concepts across bank + mining filings.

Loader: `scripts/seed_xbrl_alias.py` (mirror `seed_concept_map.py` structure). Upsert on `taxonomy_concept`.

**Acceptance:**
- `make seed` also runs this loader (edit `Makefile` to run both seeders).
- `SELECT count(*) FROM xbrl_alias` ≥ 30.

### M2.4.3 — XBRL parser
**File:** `services/extraction/xbrl.py`

Function: `parse_xbrl(xbrl_bytes: bytes) -> list[ExtractedFact]`.
- Use `arelle` to load the instance document.
- For each fact: extract taxonomy concept URI, value, unit, `contextRef` (period + segment), period type.
- Emit `ExtractedFact` with `confidence=1.0`, `method="xbrl"`.
- Bbox is not applicable for XBRL — set to `(0,0,0,0)` sentinel; store `source_page = 0`.

### M2.4.4 — Worker task
**File:** `services/ingest/tasks/xbrl_sidecar.py`

`WORKER_VERSION = "1.0"`.

Behavior:
1. Idempotency check.
2. Check MinIO for `{minio_key}.xbrl.xml`. If absent, return `{"xbrl_present": False}` and do nothing else (this is the "no fast path" path — subsequent workers handle normal extraction).
3. If present: `parse_xbrl(...)`, then translate to `financial_facts` rows via `xbrl_alias` join.
4. Insert with `ON CONFLICT (unique key from BLUEPRINT §6.2) DO UPDATE SET ... WHERE source_conf < 1.0` — XBRL wins.
5. Return `{"xbrl_present": True, "facts": N}`.

**Acceptance:**
- Integration test with a real IDX XBRL fixture inserts N facts.
- If PDF parser previously inserted a conflicting row, running XBRL supersedes it (unit test on the merge logic).

---

## 5. `normalize_facts` worker (PDF → facts)

### M2.5.1 — Concept mapper
**File:** `services/extraction/concepts.py`

Function: `map_local_to_canonical(local_label: str, sector: str) -> tuple[str, float]` — returns `(canonical_concept_id, confidence)`.

Algorithm:
1. Normalize label: strip, lowercase, remove punctuation, collapse whitespace.
2. Exact match against `concept_map WHERE sector=... OR sector IS NULL`. If found, `confidence=1.0`.
3. Else `pg_trgm` similarity: `SELECT canonical_concept_id, similarity(local_label, :label) AS s FROM concept_map WHERE sector=... AND s > 0.6 ORDER BY s DESC LIMIT 1`. If found, return `(row.canonical, min(row.s, 0.8))`.
4. Else raise `ConceptMappingError` — caller writes the row with `concept_id = 'UNMAPPED:' || local_label` and `needs_review=true`.

**Never** call the LLM here in M2. Fuzzy match + review queue only.

### M2.5.2 — Review queue table
**File:** `db/schema/006_review_queue.sql`
**Copy verbatim:** appendix-schemas.md § "006_review_queue.sql"

Includes `concept_review(id, ticker, doc_id, local_label, suggested_canonical, similarity_score, status, resolved_at, resolved_by, canonical_final)`.

### M2.5.3 — Table row → fact normalizer
**File:** `services/extraction/tables.py` (add function)

Function: `tables_to_facts(tables: list[ExtractedTable], sector: str, ticker: str, fiscal_period: FiscalPeriod, doc_id: UUID) -> list[ExtractedFact]`.

Heuristics:
- Assume financial tables have a leftmost column of labels and one or more numeric columns (periods).
- Detect the header row via presence of period-like strings (`2024`, `Q4`, `TW IV`, `Desember`).
- For each labeled row, associate the value in the target period column.
- Unit inference: watch for headers like `(dalam jutaan Rupiah)` → `unit='IDR_MN'`.
- Signs: parentheses → negative.

Every emitted `ExtractedFact` has `source_page` and `source_bbox` from the leftmost-label cell (per BLUEPRINT §12.1 — citations point at the label).

### M2.5.4 — Worker task
**File:** `services/ingest/tasks/normalize_facts.py`

`WORKER_VERSION = "1.0"`.

Behavior:
1. Idempotency check.
2. Read `tables.parquet` from MinIO; deserialize to `list[ExtractedTable]`.
3. Look up sector for ticker via `issuer_profile` (or fall back to `concept_map` distinct sectors).
4. Call `tables_to_facts(...)`.
5. For each fact: `map_local_to_canonical(...)`. On mapping failure, insert into `concept_review` and write the fact with `concept_id = 'UNMAPPED:' + local_label` and `needs_review=true`.
6. Insert into `financial_facts`. On conflict with existing row: **only overwrite if new confidence > existing confidence** — XBRL rows win over PDF rows.
7. Update `documents.status = 'facts_extracted'` (only if we got at least 1 fact).
8. Enqueue downstream `chunk_narrative` and `derive_metrics`.

**Acceptance:**
- Integration test using the fixture BMRI 2024Q4 quarterly PDF inserts ≥ 30 rows into `financial_facts` with mapped `concept_id`.
- Unmapped labels create `concept_review` rows.
- Confidence gate: rows with `extraction_conf < 0.7` have `needs_review = true`.

---

## 6. `chunk_narrative` worker (structure only in M2)

Full embedding lands in M3. In M2 we split, classify sections, populate `narrative_chunks` with `embedding IS NULL`.

### M2.6.1 — Narrative chunks table
**File:** `db/schema/007_narrative_chunks.sql`
**Copy verbatim:** appendix-schemas.md § "007_narrative_chunks.sql"

### M2.6.2 — Chunker
**File:** `services/narrative/chunker.py`

Function: `chunk_pages(pages: list[PageContent], ticker: Ticker, doc_type: DocType, fiscal_period: FiscalPeriod) -> list[NarrativeChunkDraft]`.

Rules from BLUEPRINT §6.4:
- Semantic paragraphs, 200–400 tokens (count via `tiktoken` on `cl100k_base` as an approximation).
- No overlap.
- Detect heading hierarchy via font-size heuristics from `pdfplumber` (bold + larger = heading). Prepend heading path.
- Never emit chunks whose text is >70% digits (tables — they belong in L2, not L4).

`NarrativeChunkDraft` (add to `types.py`):
```python
class NarrativeChunkDraft(BaseModel):
    source_page: int
    section: Literal["MDA", "RISK", "GUIDANCE", "MGMT_STMT", "FOOTNOTE", "OTHER"]
    language: Language
    text_original: str
    text_en: str | None = None  # None until M3 translator runs
    speaker: str | None = None
    claim_type: Literal["GUIDANCE", "EXPLANATION", "FORWARD_LOOKING", "RISK", "NEUTRAL"] | None
    mentioned_concepts: list[str] = []
    mentioned_periods: list[str] = []
```

### M2.6.3 — Section classifier (rule-based)
**File:** `services/narrative/chunker.py` (add function)

Regex-based classifier for the section field:
- Chunk heading path contains `Management Discussion` / `Diskusi dan Analisis Manajemen` → `MDA`.
- Contains `Risk Factor` / `Faktor Risiko` → `RISK`.
- Contains `Guidance` / `Panduan` / `Target` / `Prospek` → `GUIDANCE`.
- Contains `Notes to Financial Statement` / `Catatan atas Laporan Keuangan` → `FOOTNOTE`.
- Else `OTHER`.

Do **not** LLM-classify in M2. Rule-based only.

### M2.6.4 — Worker task
**File:** `services/ingest/tasks/chunk_narrative.py`

`WORKER_VERSION = "1.0"`.

Behavior:
1. Idempotency check.
2. Read `pages.jsonl`.
3. Call `chunk_pages(...)`.
4. Insert into `narrative_chunks` with `embedding=NULL` and `tsv = to_tsvector('simple', text_original)`.
5. Return `{"chunks": N}`.

**Acceptance:**
- Fixture PDF produces ≥ 20 `narrative_chunks` rows.
- `SELECT count(*) FROM narrative_chunks WHERE section='MDA'` > 0 for a real fixture.

---

## 7. Ingestion chain orchestration

### M2.7.1 — Pipeline task
**File:** `services/ingest/tasks/ingest_document.py` (rewrite the M1 stub)

Sequential chain (using arq `enqueue_job` at end of each task, or a wrapper `ingest_document` that awaits each sub-task in order):

```
xbrl_sidecar (parallel-safe with parse_layout)
    ↓
parse_layout
    ↓
extract_tables
    ↓
normalize_facts
    ↓
chunk_narrative
    ↓
derive_metrics       (implemented in M3)
    ↓
build_kg             (implemented in M5)
    ↓
refresh_profile      (implemented in M3)
```

In M2, stop at `chunk_narrative` and log `pipeline_completed_m2`. Downstream workers are noops until their milestone.

**Failure semantics:** if any step raises, log with structured context, mark `worker_runs.status='failed'`, and update `documents.status='failed'`. The pipeline is not retried automatically — the review UI (or a CLI) triggers re-enqueue.

**Acceptance:**
- End-to-end: uploading `sample_bmri.pdf` walks through XBRL(if present) + parse + tables + normalize + chunk, and finishes with `documents.status='facts_extracted'`.
- Killing worker mid-flight and restarting resumes from the last completed step (worker_runs idempotency).

---

## 8. Confidence gate & review UI

### M2.8.1 — Review CLI
**File:** `scripts/review_queue.py`

Argparse commands:
- `list --status=open` — prints unresolved rows.
- `resolve --id=<n> --canonical=<concept_id>` — updates `concept_review`, then re-runs normalize on the affected doc.
- `reject --id=<n>` — marks resolved with `canonical_final=NULL` (row stays quarantined).

This is a founder-facing tool. A proper web UI is deferred to M7.

**Acceptance:**
- `[RUN]` after ingesting a fixture with intentionally unmapped labels, `python scripts/review_queue.py list --status=open` shows those labels.
- Resolving one removes it from `list`.

### M2.8.2 — Retrieval gate
**File:** `services/shared/db.py` (add helper)

Function: `active_facts_query(...)` that always includes `WHERE needs_review = false AND (extraction_conf >= 0.7 OR extraction_method = 'xbrl')`.

Every downstream module MUST use this helper — no ad-hoc `SELECT * FROM financial_facts` queries.

**Acceptance:**
- Grep of the codebase (documented in this task): only `financial_facts` selects go through the helper.
- Unit test verifies the WHERE clause is applied.

---

## 9. Eval Suite A (bootstrap)

### M2.9.1 — Golden set format
**File:** `eval/golden/suite_a_fact_recall.jsonl`

Format (one JSON per line):
```json
{"id":"A-001","ticker":"BMRI","fiscal_period":"2024Q4","question":"What was BMRI's Net Interest Income in 2024Q4?","expected_value":"IDR 24.5 tn","expected_concept_id":"idx:NetInterestIncome","expected_source_doc_hint":"BMRI-FS-2024Q4"}
```

Curate ≥ 50 Q/A pairs across the 10 M1 tickers (banks + coal miners). Each pair references a fact that will exist in `financial_facts` after ingestion.

### M2.9.2 — Suite A runner
**File:** `eval/suite_a.py`

Behavior:
- For each row, query `financial_facts` for the expected concept + period.
- Assert value present, unit correct, `source_doc_id` matches the hint pattern.
- Emit `pass_rate`, `failed_ids`, and per-fail reason.

Wire into `eval/runner.py` with `python -m eval.runner --suite=a`.

**Acceptance:**
- `[RUN]` after ingesting a corpus that satisfies the golden set, `python -m eval.runner --suite=a` prints `pass_rate >= 0.95`.

---

## M2 exit gate

Before starting M3:

- [ ] Uploading any of the 10 covered tickers' quarterly PDFs completes the full chain to `status='facts_extracted'`.
- [ ] XBRL sidecar fast path works: uploading a PDF + XBRL pair produces facts with `extraction_method='xbrl'` and `conf=1.0`, superseding PDF-extracted duplicates.
- [ ] Concept mapper resolves ≥ 90% of tables without hitting the review queue (measured on 10 sample filings).
- [ ] Review CLI lets the founder resolve unmapped labels; resolving re-normalizes.
- [ ] `narrative_chunks` populated (embedding still NULL — M3).
- [ ] `active_facts_query` is the only path to `financial_facts` from services.
- [ ] Eval Suite A passes ≥ 95% on the 10-ticker corpus.
- [ ] All ingestion workers idempotent (verified by re-running a doc: no duplicate rows).
- [ ] `make lint`, `make typecheck`, `make test` green.
