# EmiMind — Operational Runbook & Incident Playbook

This runbook documents production operations, triage procedures, API key management, and extension guides for EmiMind.

---

## 1. Promoting Unmapped Concepts to `concept_map`

When extraction logs report false negatives or new Indonesian accounting labels:

1. **Inspect Review Queue:**
   ```sql
   SELECT label_raw, ticker, count(*) AS occurrences
   FROM unmapped_labels
   GROUP BY label_raw, ticker
   ORDER BY occurrences DESC
   LIMIT 20;
   ```
2. **Add Canonical Mapping to Seed:**
   Edit `db/seeds/concept_map_seed.csv`:
   ```csv
   label_raw,concept_id,category,statement
   "Beban Bunga dan Syariah",idx:InterestExpense,EXPENSE,INCOME_STATEMENT
   ```
3. **Re-seed Database:**
   ```bash
   uv run python scripts/seed_concept_map.py
   ```
4. **Trigger Re-extraction:**
   Re-run `normalize_facts_task` for affected filings.

---

## 2. Re-ingesting Filings on Recipe Version Bumps

When a formula in `services/derive/recipes/` changes (e.g. updating `bank.nim` calculation):

1. Update the `version` attribute in `@recipe`:
   ```python
   @recipe(metric_id="bank.nim", version="1.1", sector="BANK")
   ```
2. Recompute metrics for covered documents:
   ```bash
   uv run python -c "
   import asyncio
   from services.ingest.tasks.derive_metrics import derive_metrics_task
   from services.shared.db import create_pool
   # Runs idempotent derive recalculation
   "
   ```

---

## 3. Handling Market Price Outages & Stale Technical State

If Yahoo Finance (`.JK` symbols) rate limits or experiences downtime:

1. The ingestion engine automatically falls back to deterministic synthetic price models for local test environments without crashing.
2. For production data refresh, check the `stale_as_of` column in `technical_state`:
   ```sql
   SELECT ticker, as_of, stale_as_of FROM technical_state WHERE as_of < CURRENT_DATE - INTERVAL '2 days';
   ```
3. Trigger manual backfill for specific tickers:
   ```bash
   uv run python scripts/backfill_market_prices.py --tickers=BMRI,BBRI,BBCA
   ```

---

## 4. Rotating LLM Provider API Keys & Role Fallbacks

EmiMind assigns roles dynamically via `services/shared/config.py`:
- `reasoner`: DeepSeek-R1 / Claude 3.5 Sonnet / GPT-4o
- `utility`: DeepSeek-V3 / Claude 3.5 Haiku / GPT-4o-mini
- `judge`: Claude 3.5 Sonnet / GPT-4o

### To rotate a key or swap a provider:
1. Update `.env`:
   ```env
   EMI_ROLE_REASONER=deepseek/deepseek-reasoner
   DEEPSEEK_API_KEY=sk-new-key-here
   ```
2. Restart the API and Worker containers:
   ```bash
   docker compose restart api worker
   ```
3. Run the validation smoke test:
   ```bash
   uv run python -m eval.runner --suite=all
   ```

---

## 5. Adding a New Sector End-to-End

To add a new sector (e.g., `PROPERTY` or `HEALTHCARE`):

1. **Add Canonical Financial Concepts:**
   Add local Indonesian labels to `db/seeds/concept_map_seed.csv`.
2. **Implement Sector Derived Metric Recipes:**
   Create `services/derive/recipes/<sector>.py` using `@recipe(metric_id="...", sector="...")`.
   Register in `services/derive/recipes/__init__.py`.
3. **Add Peer Groups:**
   Add sector peer cohorts in `db/seeds/peer_groups_seed.csv` and run `uv run python scripts/seed_peer_groups.py`.
4. **Add Unit & Integration Tests:**
   Add unit test in `tests/unit/test_sector_recipes.py`.
5. **Verify Suite:**
   Run `uv run pytest -v` and `uv run python -m eval.runner --suite=all`.

---

## 6. Agent Targeted Deep Extraction Protocol

The agent-facing runbook is `../EmiMind-Extraction/AGENTS.md` (read by Claude Code / Codex / Gemini in that workspace). This section is the operator's summary of the same loop; if the two ever disagree, fix both.

### Core rules
1. Never read a whole 150+ page PDF: work from `get_routed_pages` output. Tokens are measured server-side from the pages and characters it serves (`document_processing_log` `ROUTED` rows: `chars/4 + 1,600 per page image`), budget ≤ max(15 % of `page_count × 2,000`, 50,000 tokens); the floor covers short filings.
2. `source_page` is always the **1-based physical PDF page index** (`page_index`), never the printed folio (`page_label`). Same for `search_pages_checked`.
3. Digits come from the table grids `tables[].rows[r][c]` (printed cell text): cite `cell_ref {table_index,row,col}` and scale by the table `unit_hint`. The server resolves the cell's parsed value and bbox from `cell_ref`, so the agent sends no `bbox`. Page images are served only with `include_images=true`, and are for layout only.
4. Every fact carries an explicit `statement` (`BS`/`IS`/`CF`/`EQ`/`NOTE`) and `period_type` (`instant` / `duration_ytd` / `duration_qtd`); IS and CF facts are never `instant`.
5. Narratives are verbatim quotes of the cited page; omissions only when the metric is truly absent (the server searches every indexed page and rejects contradicted omissions).

### The loop
1. **`inspect_document`** — `AUTHORIZED` → continue; `ALREADY_PROCESSED` / `OUT_OF_SCOPE` / `ERROR` → stop; `SKIPPED_ADMINISTRATIVE` (checklists, cover letters, directors' statements, ESG, PUBEX, *Penjelasan*, *Perubahan > 20 %*, newspaper publications, ≤ 3-page docs without statements) → nothing registered, move on; `NEEDS_METADATA` (period unresolved or filename prefix ≠ title and the cover page does not settle it) → read the cover page and re-call with `fiscal_period="YYYYQn"`. Inspection is deterministic (no LLM); `doc_type` is inferred from the downloader prefix (`AUDIT_RDF` → `FS_ANNUAL`, `TW1-3_RDF` → `FS_QUARTERLY`, `ANNUAL_AAR` → `ANNUAL_REPORT`) unless passed explicitly.
2. **`get_extraction_contract(doc_id)`** — mandatory KPIs, modules, narratives, scaling rules.
3. **`get_routed_pages(doc_id, module, exclude_pages=[…])`** for each core and granular module. `exclude_pages` lists the pages already received from earlier modules; they come back as `already_served` stubs without text or tables, so each page is served (and budgeted) once per run.
4. **Read digits from `tables[].rows`** and cite `cell_ref`: right row label, current-period column, right concept (e.g. *Kas* ≠ cash and cash equivalents).
5. **Set `statement` and `period_type`** on every fact.
6. **Verbatim narratives** (`text_original` copied from `source_page`; `text_en` may translate).
7. **Omissions only when truly absent**, with the pages actually read.
8. **Micro-payloads to `submit_draft_extraction`** per module; fix every error except missing-KPI errors for modules not yet sent; then submit the full consolidated payload until `VALID` (≤ 3 attempts, then `ingest_review_queue`).
9. **`commit_verified_report`** with the validated payload; expect `COMMITTED`.

### Preparing a batch and checking it
```bash
# pick real statements (never ESG / checklists / cover letters), copy to ../EmiMind-Extraction/m9_stage,
# inspect -> index pages -> embed pages (bge-m3). Resumable.
uv run python scripts/m9_batch.py prepare --priority lq45 --limit 20 --period 2025Q4
# ... the agent extracts each staged file per AGENTS.md ...
# per-document status + acceptance gate over the batch window -> eval/reports/m9_batch_<date>.json
uv run python scripts/m9_batch.py report
# gate for specific filings, or any window
uv run python eval/deep_extraction_gate.py --tickers BMRI,LSIP --out eval/reports/m9_gate.json
uv run python eval/deep_extraction_gate.py --aggregate --since 2026-09-29T00:00:00+07:00
# router recall + precision on the held-out gold set
uv run python eval/router_recall.py --gold eval/router_gold/heldout/ --out eval/reports/router_recall_heldout.json
```
The gate fails (exit 1) when any input is missing: migration 025/026 columns, `ROUTED` logs with `chars`, the PDF on disk, the contract, or the router recall report.
