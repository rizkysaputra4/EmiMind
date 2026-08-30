# Evaluation Suite Triage & Regression Guide

## Triage Procedure for Evaluation Failures

When a test in Eval Suite A, B, C, or Screener fails:

### 1. Suite A (Fact Recall) Failure
- **Symptom:** Fact not found in `financial_facts` or confidence `< 0.70`.
- **Action:**
  1. Check `unmapped_labels` for the concept.
  2. If missing, add to `db/seeds/concept_map_seed.csv` and re-run seed.
  3. Verify table extraction coordinates in `services/extraction/table_extractor.py`.

### 2. Suite B (Citation Precision) Failure
- **Symptom:** Citation fails to resolve to exact filing document or page in PostgreSQL.
- **Action:**
  1. Inspect citation format against regex `^\[([A-Z]{4})-(FS|DERIVED|PUBEX|AR)-(\d{4}(?:Q[1-4]|FY|H[12]))(?:#p(\d+))?\]$`.
  2. Ensure prompt assembler does not hallucinate fictional page numbers.

### 3. Suite C (Complex Reasoning) Failure
- **Symptom:** Average reasoning score `< 4.0` or missing evidence citations.
- **Action:**
  1. Inspect retrieval manifest to confirm necessary facts/chunks were budgeted.
  2. Increase category token budget in `services/retrieval/budgeter.py` if evidence was truncated.

### 4. Suite Screener Failure
- **Symptom:** SQL compiler misses expected tickers or excludes required sector.
- **Action:**
  1. Inspect generated SQL with `compile_to_sql()`.
  2. Ensure all referenced metrics exist in `REGISTRY`.
