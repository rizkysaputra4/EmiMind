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
