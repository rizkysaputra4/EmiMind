# EmiMind — Implementation Task Index

> Executable task list derived from `BLUEPRINT.md`.
> Read this file first, then work milestones in order.

---

## How to use this file

1. **Read `tasks/00-conventions.md` before writing any code.** It defines the folder layout, naming rules, dependency direction, and non-negotiable architectural constraints. Every task in every milestone assumes these rules are followed.
2. **Work milestones in order (M1 → M7).** Each milestone builds on the previous one. Do not skip ahead.
3. **Inside a milestone, work tasks in order** unless a task explicitly says `Parallel-safe with: <task-ids>`.
4. **Every task has an `Acceptance` section.** A task is only complete when every acceptance bullet is satisfied. Do not mark a task done because "the code compiles" — run the acceptance checks.
5. **If a task references a schema, copy it verbatim from `tasks/appendix-schemas.md`.** Do not paraphrase SQL — column names, indexes, and constraint names are load-bearing.
6. **If you are blocked, stop and ask.** Do not invent columns, invent env vars, or invent library APIs. Blueprint.md is the source of truth for design; if it doesn't cover something, ask before improvising.

---

## Milestone Files

| # | File | Weeks | Deliverable |
|---|---|---|---|
| — | [`tasks/00-conventions.md`](tasks/00-conventions.md) | Read first | Architecture rules, folder layout, naming, dependency direction |
| M1 | [`tasks/01-M1-skeleton.md`](tasks/01-M1-skeleton.md) | 1–4 | Postgres + MinIO + Redis + FastAPI + Next.js up; upload endpoint stores PDF and creates `documents` row |
| M2 | [`tasks/02-M2-ingestion.md`](tasks/02-M2-ingestion.md) | 5–10 | pdfplumber/Camelot/Tesseract cascade + XBRL sidecar parser; `financial_facts` populated; concept map seeded for banks + coal miners |
| M3 | [`tasks/03-M3-derived-narrative.md`](tasks/03-M3-derived-narrative.md) | 11–14 | Recipe registry writes `derived_metrics`; BGE-M3 embedder writes `narrative_chunks`; hybrid ANN+FTS+rerank retrieval |
| M4 | [`tasks/04-M4-retrieval-chat.md`](tasks/04-M4-retrieval-chat.md) | 15–20 | Classifier + planner + budgeter + prompt assembler + Sonnet 4.6 chat turn; citation UI; Eval Suites A/B/C in CI |
| M5 | [`tasks/05-M5-kg-guidance.md`](tasks/05-M5-kg-guidance.md) | 21–26 | KG nodes/edges; guidance miner; actual matcher; causal linker; rolling conversation summary; sticky slots |
| M6 | [`tasks/06-M6-screener-technical.md`](tasks/06-M6-screener-technical.md) | 27–32 | Screener DSL + SQL compiler + executor; yfinance ingest; `technical_state` with regime labels; 50-ticker coverage |
| M7 | [`tasks/07-M7-polish.md`](tasks/07-M7-polish.md) | 33–36 | Eval regressions fixed; onboarding; session persistence; coverage to LQ45 + KOMPAS100 |

## Appendices

| File | Purpose |
|---|---|
| [`tasks/appendix-schemas.md`](tasks/appendix-schemas.md) | All Postgres schemas, ready to copy verbatim into `db/schema/*.sql` |
| [`tasks/appendix-eval-framework.md`](tasks/appendix-eval-framework.md) | Details of Suites A/B/C referenced by M2, M3, M4 |
| [`tasks/appendix-llm-providers.md`](tasks/appendix-llm-providers.md) | Provider-neutral LLM abstraction — pick Anthropic Claude, OpenAI, Kimi, DeepSeek, or any OpenAI-compat endpoint per role via env; referenced by M3, M4, M5, M6 |

---

## Global Definition-of-Done for every task

Regardless of which milestone a task is from, a task is not "done" until:

- [ ] Code lives at the path specified in the task; if the task said `services/derive/recipes/bank.py`, it is at that path, not elsewhere.
- [ ] Every function has type hints. Every module-level function that crosses a module boundary returns a Pydantic model, not a dict.
- [ ] `ruff check .` and `ruff format --check .` pass (Python).
- [ ] `pnpm lint` and `pnpm typecheck` pass (Next.js).
- [ ] Any new schema is in `db/schema/NNN_*.sql` where `NNN` is the next monotonic number; existing files are never renumbered.
- [ ] Any new env var is added to `.env.example` with a comment; secrets are never committed.
- [ ] If the task adds a new dependency, it is added to `pyproject.toml` (Python) or `web/package.json` (frontend), not installed ad-hoc.
- [ ] The acceptance checks in the task's own `Acceptance` section all pass.

---

## Notation used across milestone files

- `[FILE]` = create this file
- `[EDIT]` = modify an existing file (task will say which lines / functions)
- `[RUN]` = shell command that must succeed
- `[VERIFY]` = an assertion the executor must confirm before moving on
- `[BLOCKED]` = do not attempt; wait for the previous task noted
- `# ==> ...` inside code blocks = executor guidance, not real code

Task IDs have the form `M<milestone>.<section>.<index>`, e.g. `M2.4.3` = M2 § 4, task 3. Section numbers correspond to headings in the milestone file.
