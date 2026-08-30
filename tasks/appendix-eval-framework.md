# Appendix — Evaluation Framework

Cross-cutting reference for Eval Suites A, B, C, and Screener. Milestones M2, M3, M4, M6 grow the golden sets and tighten thresholds.

**Non-negotiable:** the eval harness ships **before** the chat UI (BLUEPRINT §15). If tests do not run in CI on every PR touching `services/**`, we are shipping blind.

---

## 1. Directory layout

```
eval/
├── __init__.py
├── runner.py                                 # `python -m eval.runner --suite=<name>`
├── suite_a.py                                # fact recall
├── suite_b.py                                # provenance validity
├── suite_c.py                                # reasoning quality (LLM judge)
├── suite_screener.py                         # M6
├── golden/
│   ├── suite_a_fact_recall.jsonl
│   ├── suite_b_provenance.jsonl              # generated from suite_a runs
│   ├── suite_c_reasoning.jsonl
│   └── suite_screener.jsonl
└── reports/
    ├── <YYYYMMDD_HHMM>.json                  # per-run summary
    └── failures/<suite>/<id>.json            # captured failures for triage
```

---

## 2. Golden-set formats

### Suite A — fact recall

```json
{
  "id": "A-001",
  "ticker": "BMRI",
  "fiscal_period": "2024Q4",
  "question": "What was BMRI's Net Interest Income in 2024Q4?",
  "expected_value": "24.5",
  "expected_unit": "IDR_TN",
  "expected_concept_id": "idx:NetInterestIncome",
  "expected_source_doc_hint": "BMRI-FS-2024Q4"
}
```

### Suite B — provenance validity

Generated automatically from every A/C run:
- for each cited `[TICKER-DOCTYPE-PERIOD#pPAGE]` in an assistant answer, verify
  1. The `documents` row exists.
  2. The associated `financial_facts` or `narrative_chunks` row exists.
  3. The number stated near the citation matches the fact's `value_numeric` (within a 0.5% tolerance for rounding).
  4. `source_page` is non-null and `source_bbox` is non-null (or `extraction_method='xbrl'`).

No hand-curated golden file; the suite is a set of assertions.

### Suite C — reasoning quality

```json
{
  "id": "C-001",
  "ticker": "BMRI",
  "session_seed": [
    "Why did BMRI's net profit rise despite the revenue decline this quarter?"
  ],
  "reference_answer": "Net profit rose because credit costs fell sharply YoY, driven by ... Revenue decline was ... The chain is consistent with prior guidance ...",
  "must_mention": ["credit cost", "provision", "coverage ratio"],
  "must_not_mention": ["estimated", "approximately"]
}
```

`get_llm("judge")`-as-judge (falls back to `get_llm("reasoner")` if the judge role is unset) scores 0–5 on a strict rubric:
1. **Answer directness** — did it lead with the answer?
2. **Evidence usage** — are all claims backed by cited facts / chunks?
3. **Correctness** — do the cited numbers match the reference?
4. **Calibration** — does it flag comparability, uncertainty, or missing data honestly?
5. **Style** — punchy, no hedged filler, no repetition of the question.

Weighted mean; suite gate is warning-only (BLUEPRINT §15.1).

### Suite Screener (M6)

```json
{
  "id": "S-001",
  "query": "IDX banks with ROE>15%, DE<1, PE<15 as of 2024Q4",
  "as_of": "2024Q4",
  "must_include": ["BMRI","BBCA"],
  "must_not_include": ["GOTO"],
  "min_results": 3,
  "max_results": 20
}
```

---

## 3. Runner behavior

`python -m eval.runner --suite=<a|b|c|screener|all> [--tickers=...] [--limit=N] [--fail-fast]`:

1. Loads config; asserts DB is reachable and MinIO bucket exists.
2. Uses `services.llm.fakes.FakeLLMClient` **only** if `EMI_LLM_MODE=fake`; otherwise real providers.
3. For each row in the suite:
    - Runs the full `chat.run_turn` pipeline (Suite A/C) or the appropriate direct query (Suite B/Screener).
    - Captures prompt tokens, cost, latency, retrieval manifest.
    - Runs assertions.
    - On failure, dumps `{prompt, answer, manifest, expected, actual, reason}` to `reports/failures/<suite>/<id>.json`.
4. Emits a JSON summary to `reports/<ts>.json`:

```json
{
  "suite": "a",
  "n": 300,
  "passed": 297,
  "pass_rate": 0.99,
  "failed_ids": ["A-042","A-113","A-289"],
  "avg_latency_ms": 3120,
  "total_cost_usd": 4.87
}
```

5. Exits 0 on pass, 1 on gate failure.

---

## 4. CI wiring

`.github/workflows/eval.yml`:

```yaml
name: eval
on:
  pull_request:
    paths:
      - "services/**"
      - "eval/**"
      - "db/schema/**"
      - "services/derive/recipes/**"

jobs:
  eval-a-b:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env: { POSTGRES_USER: emimind, POSTGRES_PASSWORD: emimind, POSTGRES_DB: emimind }
        ports: [5432:5432]
      redis: { image: redis:7-alpine, ports: [6379:6379] }
      minio: { image: minio/minio, ports: [9000:9000] }
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
      - run: make migrate seed
      - run: uv run python scripts/restore_eval_fixtures.py
      - name: Suite A
        run: uv run python -m eval.runner --suite=a --gate=0.99
      - name: Suite B
        run: uv run python -m eval.runner --suite=b --gate=1.00
```

`scripts/restore_eval_fixtures.py` writes a pre-ingested fixture dump into the DB + MinIO so CI doesn't re-run the full ingestion pipeline. Fixture dump is checked in under `eval/fixtures/`.

---

## 5. Gate thresholds by milestone

| Milestone | Suite A | Suite B | Suite C | Screener |
|---|---|---|---|---|
| M2 exit | ≥ 95% | not yet | not yet | — |
| M3 exit | ≥ 95% | not yet | smoke (5 qs, founder judge) | — |
| M4 exit | ≥ 99% | 100% | ≥ 4.0 (warn) | — |
| M5 exit | ≥ 99% | 100% | ≥ 4.1 (warn) | — |
| M6 exit | ≥ 99% | 100% | ≥ 4.0 | ≥ 90% (warn) |
| M7 exit | ≥ 99.5% | 100% | ≥ 4.2 | ≥ 90% |

Gates evolve; do not regress on a milestone that already passed a higher bar.

---

## 6. Regression capture

Every failure automatically writes `reports/failures/<suite>/<id>.json`. When the founder fixes a bug, they:

1. Add a regression test at `tests/regression/test_<suite>_<id>.py` that re-asserts the specific failure mode.
2. Update the golden row if the failure was due to a bad expectation (rare — treat as a red flag).
3. Never delete a failure record; keep the history under `reports/failures/`.
