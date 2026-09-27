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

When extracting from financial statement PDFs in `incoming_reports/`:

### Core Rules
1. **NEVER read the entire 150+ page PDF from start to end.**
2. `source_page` must **always** be the **1-based physical PDF page index** (`page_index`), **never** the printed folio label.
3. Numeric values must come from table cell parser (`tables[].cells`), citing `cell_ref: {"table_index": T, "row": R, "col": C}` and bounding box `bbox`. Use page images only for visual confirmation.
4. Scale detection: Check table `unit_hint` (e.g. "dalam jutaan rupiah" vs "dalam ribuan rupiah") and expand values to full integer IDR in the JSON payload.
5. Provide token/page usage telemetry in `usage: {"input_tokens": N, "output_tokens": N, "pages_read": N}`.

### 7-Step Extraction Loop

1. **Inspect Document (`inspect_document`):**
   - Call `inspect_document(file_path, ticker, fiscal_period)`.
   - If status is `ALREADY_PROCESSED`, terminate immediately with 0 tokens spent.
   - If status is `NEEDS_METADATA`, resolve `fiscal_period` (e.g. `"2025Q4"`) and re-call `inspect_document`.
   - Note the returned `doc_id`.

2. **Retrieve Extraction Contract (`get_extraction_contract`):**
   - Call `get_extraction_contract(doc_id)`.
   - Inspect the returned `sector`, `required_facts`, `granular_note_modules`, and `scaling_rules`.

3. **Retrieve Targeted Spans per Module (`get_routed_pages`):**
   - For core statements: `get_routed_pages(doc_id, "BALANCE_SHEET")`, `get_routed_pages(doc_id, "INCOME_STATEMENT")`, `get_routed_pages(doc_id, "CASH_FLOW")`.
   - For sector note modules: call `get_routed_pages(doc_id, module.name)` for each applicable module in `contract.granular_note_modules` (e.g. `BANK_LOANS_NPL`, `DEPOSITS_FUNDING`, `PLANTATION_AREA`, `REVENUE_BREAKDOWN`, `MDA`).

4. **Parse Grid Cells & Ground Facts:**
   - Extract facts from `tables[].cells`:
     - Match cell numeric values multiplied by scale.
     - Attach `cell_ref={"table_index": table.table_index, "row": cell.row, "col": cell.col}` and `bbox=cell.bbox`.
     - Assign `statement`: `"BS"` for Balance Sheet, `"IS"` for Income Statement, `"CF"` for Cash Flow, `"NOTE"` for disclosure notes.
   - For breakdown items (segments, bank placements, loan matrices): provide `segment` dict (e.g. `{"segment": "Kredit Modal Kerja", "type": "loan_facility"}`) and cite the specific physical note `source_page`.

5. **Mandatory Operational KPIs & Omission Handling:**
   - Extract required metrics specified in the contract.
   - If a mandatory metric is genuinely absent from this PDF, explicitly declare it in `omitted_kpis`:
     ```json
     {
       "metric_id": "idx:CostOfCredit",
       "reason": "NOT_DISCLOSED_IN_REPORT",
       "explanation": "No cost of credit disclosure provided in annual audited notes",
       "search_pages_checked": [12, 13, 14]
     }
     ```

6. **Submit Draft Validation (`submit_draft_extraction`):**
   - Submit per-module or consolidated micro-payloads to `submit_draft_extraction`.
   - Include `usage: {"input_tokens": ..., "output_tokens": ..., "pages_read": ...}`.
   - If validation status is `INVALID`, inspect `report.issues`:
     - Examine ONLY the `target_pages` indicated in the feedback issues.
     - Correct column offsets, scale errors, or sum discrepancies.
     - Retry (up to 3 attempts).

7. **Commit Verified Extraction (`commit_verified_report`):**
   - When report status is `VALID`, call `commit_verified_report(payload_json, usage=...)`.
   - Confirm returned status is `COMMITTED`.
