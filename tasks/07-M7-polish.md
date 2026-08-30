# M7 — Polish + First Pilots (Weeks 33–36)

**Goal:** ship a product a human is willing to pay for. Fix top-20 eval regressions. Polish onboarding, session persistence, and the evidence panel. Coverage reaches LQ45 + KOMPAS100 (~100 tickers).

**Prerequisite:** M6 exit gate green.

---

## 1. Onboarding & auth (minimum viable)

### M7.1.1 — Auth layer
**File:** `services/api/auth.py`

Choice for MVP: magic-link email via a small SendGrid/Postmark integration. Sessions stored in Postgres. No SSO, no OAuth.

`users(id uuid PK, email text unique, created_at)` + `sessions(token text PK, user_id, expires_at)`.

Middleware: `require_user()` dependency for chat/upload/screener endpoints; healthz stays public.

### M7.1.2 — Login page
**File:** `web/app/login/page.tsx`

Email input → magic link email → confirmation page → sets cookie → redirects to `/`.

### M7.1.3 — Rate limits
**File:** `services/api/rate_limit.py`

Redis-backed sliding-window limiter:
- Free tier: 20 turns/day, 5 tickers of history depth (BLUEPRINT §20).
- Upload: 20 docs/day.
- Screener: 30/day.

Bypass in `EMI_ENV=dev`.

**Acceptance:**
- End-to-end signup + login flow works.
- Rate limits enforce; hitting the cap returns 429 with a helpful message.

---

## 2. Session persistence & history

### M7.2.1 — Session list
**File:** `services/api/routers/sessions.py`

`GET /api/v1/sessions` — list the user's sessions with last message preview and updated_at.
`GET /api/v1/sessions/{id}/turns` — full turn history.
`POST /api/v1/sessions/{id}/rename` — set a friendly title (LLM-suggested from turn 1 concept).

### M7.2.2 — Sidebar in web
**File:** `web/components/SessionSidebar.tsx`

Left rail with sessions grouped by day; click loads the session's turns into `ChatWindow`.

**Acceptance:**
- Logging in restores previous sessions and lets the user resume any.

---

## 3. Evidence panel polish

### M7.3.1 — Multi-citation view
When an answer has many citations, group by document; a document card expands to show all cited pages.

### M7.3.2 — "Trace the reasoning"
On any answer, a button opens a debug drawer that shows the full `retrieval_manifest`: which facts / chunks / KG triples were used, budget consumption per bucket, and which fell to sidecar (available for `expand_evidence`).

### M7.3.3 — Report incorrect extraction
Wire the `POST /api/v1/citation/report` endpoint from M4.9.1 to insert into a `citation_reports` table. Weekly cron emits a CSV to the founder.

### M7.3.4 — Copy answer with citations
"Copy" button on assistant bubble copies markdown including citations. Useful for the target user (retail investor drafting Stockbit / Telegram posts).

---

## 4. Coverage to LQ45 + KOMPAS100

### M7.4.1 — Roster expansion
Add KOMPAS100 constituents to `db/seeds/tickers_kompas100.csv`.

Bulk-ingest 4+ quarters per ticker for the additional ~55 tickers.

### M7.4.2 — Concept map expansion
Reach ≥ 3000 concept_map rows covering the KOMPAS100 sector mix (PROPERTY, CONSTRUCTION, HEALTHCARE, TOBACCO, RETAIL).

### M7.4.3 — Peer group expansion
Add hand-curated peer groups for major sub-sectors: `banking_bumn`, `banking_private`, `cpo_large`, `telco_big3`, `consumer_staples`, `property_developer`.

---

## 5. Fix top-20 eval regressions

### M7.5.1 — Regression triage
**File:** `eval/reports/triage.md`

Runner enhancement: on each failure, capture the exact prompt, the exact model output, and the retrieval manifest. Store under `eval/reports/failures/<suite>/<id>.json`.

Founder triages the top 20 by frequency:
- If extraction quality: fix concept_map or add a new recipe.
- If retrieval: fix planner rule or renderer.
- If reasoning: adjust system prompt or add few-shot in the assembler for that intent.

Every fix has a test added to `tests/regression/` referencing the eval id.

**Acceptance:**
- Eval Suite A ≥ 99.5%; B == 100%; C ≥ 4.2.

---

## 6. Observability

### M6.1 — Metrics
**File:** `services/shared/metrics.py`

Prometheus counters + histograms via `prometheus_client`:
- `emi_turn_latency_seconds{intent,phase}` (phase = classify, plan, retrieve, budget, assemble, complete)
- `emi_prompt_tokens{intent,bucket}`
- `emi_llm_cost_usd{model}`
- `emi_ingest_worker_seconds{worker,status}`
- `emi_citation_reports_total`

`GET /metrics` on the API (protected by a basic-auth token).

### M7.6.2 — Structured log sink
Deploy behind a small log aggregator (Grafana Loki, or just journald + friendly querying). Every log line already carries the fields from `services/shared/logging.py`; ensure `session_id`, `document_id`, and `ticker` propagate through arq contexts.

### M7.6.3 — Weekly ingest dashboard
A hand-built page at `/admin/ingest` showing:
- Docs by status (raw/parsed/facts_extracted/failed).
- Review queue depth.
- Worker success rates last 7 days.

Founder-facing only; behind an admin flag.

---

## 7. Pre-pilot checklist (BLUEPRINT §3.5)

Before onboarding a paying user:

- [ ] Data licensing conversation with legal counsel: IDX filing redistribution + derived-data rights.
- [ ] Replace yfinance with a licensed OHLCV vendor (RTI, IDNFinancials, or equivalent). Adapter lives in `services/market/` behind the same `ingest_prices` interface.
- [ ] Disclaimer footer per OJK guidance rendered on every assistant answer ("not investment advice").
- [ ] Privacy policy + UU PDP compliance for user-uploaded documents.
- [ ] Data retention policy in the ToS.

---

## 8. Documentation & handoff

### M7.8.1 — Update `BLUEPRINT.md`
Where implementation diverged from the design (e.g. vector dim change in M3.2.1a), update the blueprint. Blueprint is the source of truth for what the system IS, not what it WAS.

### M7.8.2 — Per-module READMEs
For the trickiest modules — `retrieval/`, `derive/`, `kg/`, `screener/` — write a short README covering:
- What lives here and what doesn't.
- Which upstream modules feed it.
- Which downstream modules consume it.
- How to add a new recipe / intent / edge type.

### M7.8.3 — Runbook
**File:** `docs/runbook.md`

Covers:
- How to promote a `concept_review` row after a false-negative in retrieval.
- How to re-ingest a filing when a recipe version bumps.
- How to handle a yfinance outage (stale technical_state).
- How to rotate an LLM provider API key (per role, per provider — Anthropic, OpenAI, Kimi, DeepSeek).
- How to switch a role from one provider to another safely (env swap → restart → Suite A + B smoke).
- How to add a new sector (recipe + concept_map + peer group).

---

## M7 exit gate (MVP shippable)

- [ ] LQ45 + KOMPAS100 tickers ingested; 4+ quarters each.
- [ ] Eval Suite A ≥ 99.5%, B == 100%, C ≥ 4.2, Screener ≥ 90%.
- [ ] Auth + rate limits + session persistence work.
- [ ] Evidence panel polished; trace-the-reasoning drawer available.
- [ ] Cost per turn matches blueprint; monthly infra cost ≤ blueprint estimate.
- [ ] Metrics dashboard exposes turn latency, tokens, and worker health.
- [ ] BLUEPRINT and per-module READMEs updated.
- [ ] Pilot legal checklist reviewed with counsel.
- [ ] The founder can hand this repo to a junior engineer, point them at `README.md` and `TASKS.md`, and the engineer can add a new sector end-to-end (recipe + concepts + peer group + test) within one week.
