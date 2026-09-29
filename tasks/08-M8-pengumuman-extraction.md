# M8 — Pengumuman (Announcement) Extraction

**Goal:** ingest, classify, and extract structured facts from every PDF published on the IDX *Pengumuman* tab (`https://www.idx.co.id/id/perusahaan-tercatat/pengumuman/`) for every covered ticker. High-value doc classes get bespoke contracts; the long tail is covered by a generic disclosure contract as a safety net so nothing is unextractable.

**Design doc:** [`docs/PENGUMUMAN_EXTRACTION_DESIGN.md`](../docs/PENGUMUMAN_EXTRACTION_DESIGN.md) — read before starting any subtask.

**Definition of done for M8:** running the extraction agent on any announcement PDF (dividend, RUPS result, rights issue, material info, etc.) produces validated, committed facts in the DB with the correct `doc_type`, at least the safety-net fields populated, and — for the 8 high-value classes — the class-specific KPI set.

---

## Status legend
- `[ ]` not started
- `[/]` in progress
- `[x]` done

Each subtask has: **File(s)**, **Depends on**, **Acceptance**.

---

## Phase 1 — Foundation

Goal: PDFs are on disk and every announcement gets basic extraction. No bespoke contracts yet.

### M8.1.1 — Confirm pengumuman endpoint payload
- [ ] **File:** `docs/PENGUMUMAN_EXTRACTION_DESIGN.md` §2 (update with real payload once captured)
- **Depends on:** M8.1.2 (Cloudflare access)
- **What:** Capture a real `GetAnnouncement` JSON response for one ticker (e.g. NCKL, 90 days). Confirm field names, attachment shape, date format, pagination.
- **Acceptance:** Design doc §2 has a verified payload snippet checked in.

### M8.1.2 — Solve Cloudflare access with manual cf_clearance flow
- [x] **Files:**
  - `../EmiMind-Extraction/scripts/lib/idx_cf_solver.py` (new)
  - `../EmiMind-Extraction/scripts/download_idx_reports.py` (integrate)
- **Depends on:** none
- **What:** Implement the interactive Cloudflare-solve UX from design §3.
  1. On 403/503 from the announcement endpoint, print an instruction block with the URL to open in a browser.
  2. Optionally auto-open via `webbrowser.open()` (`--browser-open` flag).
  3. Prompt the user for the `cf_clearance` cookie value from DevTools.
  4. Persist to `~/.emimind/idx_cookies.json` with `{ value, captured_at, user_agent }`.
  5. On subsequent runs, load and reuse until it 403s again.
  6. Honour `IDX_CF_CLEARANCE` env var for non-interactive runs.
- **Acceptance:**
  - Fresh run with no cookie prompts once, downloads succeed after paste.
  - Second run within TTL uses stored cookie silently.
  - Third run after cookie expires re-prompts.
  - CI mode: `IDX_CF_CLEARANCE=bad` exits non-zero without stdin.

### M8.1.3 — Sample announcement corpus for taxonomy verification
- [ ] **File:** `docs/samples/pengumuman/{TICKER}/{doc_class_hint}_{date}.pdf` (add ~30 samples across 5–8 tickers)
- **Depends on:** M8.1.2
- **What:** Manually download ~30 announcement PDFs covering the classes listed in design §4 (5+ dividend, 3+ rights issue, 3+ RUPS, 3+ material info, plus the long tail). Store under `docs/samples/pengumuman/` (gitignored except for a manifest CSV) for use by contract builders and classifier rule tuning.
- **Acceptance:** Manifest `docs/samples/pengumuman/manifest.csv` lists every sample with `ticker,date,title,expected_doc_class,file`.

### M8.1.4 — Doc classifier v1 (regex-based)
- [x] **Files:**
  - `db/schema/019_announcement_taxonomy.sql` (new — expand doc_type domain, add tables per design §6)
  - `db/seeds/announcement_class_rules.csv` (new)
  - `scripts/seed_announcement_class_rules.py` (new)
  - `services/mcp/announcement_classifier.py` (new)
- **Depends on:** M8.1.3
- **What:**
  - Migration: add `announcement_metadata` and `announcement_class_rules` tables; expand `doc_type` domain with values from design §4.
  - Seed rules table from CSV. Rules are ordered by `priority`; first match wins. Each row: `(pattern, doc_type, priority)`.
  - Classifier: given `(title, filename)` returns `(doc_type, source='regex', confidence)`. If no rule matches, returns `(GENERIC_DISCLOSURE, source='fallback', 0.0)`.
- **Acceptance:**
  - `pytest tests/unit/test_announcement_classifier.py` passes for all sample PDFs' titles from M8.1.3 (≥90% match the expected class).
  - `make migrate && make seed` runs the new migration + seed clean on an empty DB.

### M8.1.5 — Generic disclosure contract (safety net)
- [x] **Files:**
  - `services/mcp/contracts.py` (add `GENERIC_DISCLOSURE_CONTRACT`)
  - `services/mcp/validator.py` (loosen strict CRITICAL-miss enforcement when `doc_type == GENERIC_DISCLOSURE`)
  - `tests/unit/test_generic_disclosure_contract.py` (new)
- **Depends on:** M8.1.4
- **What:** Implement the safety-net contract from design §4.3. Fields: `doc_date`, `effective_date`, `parties[]`, `monetary_amounts[]`, `key_dates[]`, `narrative_summary`, `event_type_hint`. Validator accepts payloads that fill the shape without requiring all fields (all HIGH, none CRITICAL).
- **Acceptance:** `submit_draft_extraction` accepts a minimal generic payload with only `doc_date` + `narrative_summary` filled.

### M8.1.6 — Extend downloader for announcements
- [x] **File:** `../EmiMind-Extraction/scripts/download_idx_reports.py`
- **Depends on:** M8.1.1, M8.1.2, M8.1.4
- **What:**
  - Add `--mode {financial,announcements,all}` (default `all`).
  - Announcement fetching uses the CF-solved session.
  - Output path: `incoming_reports/{TICKER}/announcements/{YYYY-MM-DD}_{DOC_CLASS_HINT}_{safe_title}.pdf`.
  - Alongside each PDF write a sidecar `.meta.json` (design §9).
  - MCP dedupe: `list_processed_documents` already returns basenames — no change.
- **Acceptance:**
  - `--mode announcements --tickers NCKL --dry-run` enumerates ≥50 attachments for the last 2 years.
  - Real run downloads without duplicates on second execution.

### M8.1.7 — Ingest sidecar-aware inspect_document
- [x] **File:** `services/mcp/server.py::inspect_document`
- **Depends on:** M8.1.6
- **What:** When a PDF has a matching `.meta.json` sidecar in the same folder, read it and use `doc_class_hint` as the initial `doc_type`. Persist `announcement_metadata` row when doc_type is an announcement class.
- **Acceptance:** Ingesting a downloader-produced announcement writes a `documents` row with correct `doc_type` and a matching `announcement_metadata` row.

### M8.1.8 — Extraction agent runbook updates (Phase 1)
- [x] **File:** `../EmiMind-Extraction/AGENTS.md`
- **Depends on:** M8.1.5, M8.1.7
- **What:** Add the section from design §8: agent behaviour for announcement `doc_type`s, especially the GENERIC_DISCLOSURE contract fallback.
- **Acceptance:** A fresh agent run on a `GENERIC_DISCLOSURE` PDF from the sample corpus produces a validated payload with `narrative_summary` and at least `doc_date`.

**Phase 1 exit criteria:** end-to-end run — `download_idx_reports.py --mode announcements --tickers NCKL` → extraction agent processes each PDF → all rows land in `documents` + `announcement_metadata` + `narrative_chunks` with correct doc_type. Bespoke KPIs not required yet.

---

## Phase 2 — High-value bespoke contracts

Goal: 8 announcement classes with rich structured extraction. Iterative — one class at a time, each validated against sample PDFs.

Contract seed convention: `db/seeds/announcement_contracts/{DOC_TYPE}.yaml` (design §7).

### M8.2.1 — DIVIDEND contract
- [x] **Files:** `db/seeds/announcement_contracts/DIVIDEND.yaml`, `scripts/seed_announcement_contracts.py` (loader), `tests/unit/test_contract_dividend.py`
- **Depends on:** M8.1 phase complete
- **Fields:** `dividend_per_share`, `total_dividend_amount`, `dividend_type` (cash/stock), `cum_date`, `ex_date`, `recording_date`, `payment_date`, `payout_ratio` (optional).
- **Acceptance:** ≥5 sample dividend PDFs extract all CRITICAL fields correctly.

### M8.2.2 — RIGHTS_ISSUE contract
- [x] **Files:** as above with `RIGHTS_ISSUE.yaml`
- **Fields:** `hmetd_ratio`, `exercise_price`, `total_shares_issued`, `total_proceeds`, `hmetd_trading_start`, `hmetd_trading_end`, `use_of_proceeds` (narrative), `dilution_pct`.
- **Acceptance:** ≥3 sample rights-issue PDFs extract all CRITICAL fields.

### M8.2.3 — RUPS_RESULT contract
- [x] **Files:** `RUPS_RESULT.yaml`
- **Fields:** `meeting_date`, `meeting_type` (AGM/EGM), `agenda_outcomes[]` (label, approved bool, vote_for/against), `dividend_approved` (link to DIVIDEND if applicable), `board_changes[]`, `capital_changes` (narrative).
- **Acceptance:** ≥3 sample RUPS PDFs.

### M8.2.4 — MATERIAL_INFO contract
- [x] **Files:** `MATERIAL_INFO.yaml`
- **Fields:** `event_type` (from a controlled vocab: acquisition, disposal, lawsuit, contract_win, force_majeure, etc.), `event_date`, `financial_impact_amount`, `financial_impact_currency`, `counterparty`, `effective_date`, `narrative_summary`.
- **Acceptance:** ≥5 sample material-info PDFs.

### M8.2.5 — BOND_ISSUE contract
- [x] **Files:** `BOND_ISSUE.yaml`
- **Fields:** `instrument_type` (bond/sukuk/MTN), `principal_amount`, `currency`, `coupon_rate`, `coupon_frequency`, `tenor_years`, `issue_date`, `maturity_date`, `use_of_proceeds`, `credit_rating`, `rating_agency`, `underwriters[]`.
- **Acceptance:** ≥3 sample bond/MTN PDFs.

### M8.2.6 — AFFILIATED_TX contract
- [x] **Files:** `AFFILIATED_TX.yaml`
- **Fields:** `transaction_value`, `counterparty`, `relationship` (parent/subsidiary/common_control), `is_material_tx` (bool per POJK threshold), `independent_appraiser`, `fairness_opinion` (narrative), `effective_date`.
- **Acceptance:** ≥3 sample PDFs.

### M8.2.7 — PRIVATE_PLACEMENT contract
- [x] **Files:** `PRIVATE_PLACEMENT.yaml`
- **Fields:** `shares_issued`, `issue_price`, `total_proceeds`, `subscribers[]` (name, shares, %), `dilution_pct`, `use_of_proceeds`, `effective_date`.
- **Acceptance:** ≥3 sample PDFs.

### M8.2.8 — TENDER_OFFER contract
- [x] **Files:** `TENDER_OFFER.yaml`
- **Fields:** `offer_price`, `total_shares_target`, `offer_type` (voluntary/mandatory), `acceptance_start`, `acceptance_end`, `settlement_date`, `offeror`.
- **Acceptance:** ≥3 sample PDFs.

**Phase 2 exit criteria:** each of the 8 contracts has ≥3 successfully extracted sample PDFs committed to the DB with all CRITICAL fields populated.

---

## Phase 3 — Long tail

Goal: keep converting long-tail classes from `GENERIC_DISCLOSURE` fallback to bespoke as demand emerges.

### M8.3.1 — Prioritisation loop
- [ ] **File:** `services/api/routes/announcements_coverage.py` (new)
- **What:** Small API endpoint that returns count of `GENERIC_DISCLOSURE` docs grouped by `event_type_hint` and by `announcement_class_rules` matches without a bespoke contract. Feeds the prioritisation decision for which class to bespoke next.

### M8.3.2 — Ongoing contract additions (open-ended)
- [ ] **Classes candidate list:** `INSIDER_TX`, `BOARD_CHANGE`, `SHARE_BUYBACK`, `SUSPEND_NOTICE`, `UNSUSPEND_NOTICE`, `PUBLIC_EXPOSE`, `ARTICLES_AMENDMENT`, `NAME_CHANGE`, `LISTING_ACTION`.
- **What:** Each ships a YAML contract + tests + updated classifier rules. Same template as Phase 2.
- **Acceptance (per class):** ≥3 sample PDFs extract all CRITICAL fields.

### M8.3.3 — Classifier v2 (LLM fallback)
- [ ] **File:** `services/mcp/announcement_classifier.py`
- **What:** When regex classifier confidence is 0 (fallback), invoke a lightweight LLM classification call, cached by `doc_hash`. Confidence threshold controls whether it overrides `GENERIC_DISCLOSURE`.
- **Acceptance:** ≥80% classification accuracy on a held-out sample set of 50 announcements previously bucketed to `GENERIC_DISCLOSURE`.

---

## Cross-cutting

### C1 — Storage strategy for announcement PDFs
- [ ] **File:** `services/shared/minio.py` (extend paths)
- **What:** Decide MinIO layout for announcements: `raw/announcements/{TICKER}/{YYYY}/{doc_hash}.pdf`. Keep announcements separate from FS PDFs.

### C2 — Retrieval integration
- [ ] **Files:** `services/retrieval/planner.py`, `services/retrieval/prompt_assembler.py`
- **What:** Extend retrieval to consider announcement facts (`DIVIDEND`, `RIGHTS_ISSUE`, `MATERIAL_INFO`) as first-class evidence when answering questions about corporate events. Cited in answers with the announcement date.

### C3 — Knowledge graph edges for announcements
- [ ] **File:** `services/kg/edges.py`
- **What:** New edge types: `DECLARED_DIVIDEND`, `RAISED_CAPITAL_VIA`, `MERGED_WITH`, `ACQUIRED`, `AFFILIATED_WITH`. Link the announcement doc to the graph.

### C4 — Update memory / operator docs
- [ ] **File:** `memory/idx_downloader_script.md` (in ~/.claude/... memory)
- **What:** Document the new `--mode announcements`, the `~/.emimind/idx_cookies.json` file, and the manual CF-solve flow so it's discoverable.

---

## Rollout order (recommended)

1. M8.1.1 → M8.1.2 → M8.1.3 (Cloudflare + samples first — nothing works without these).
2. M8.1.4 → M8.1.5 → M8.1.6 → M8.1.7 → M8.1.8 (foundation shipped; every announcement gets *something* extracted).
3. Pick 1 high-value class from Phase 2 based on user need; ship end-to-end. Then next.
4. Cross-cutting C1–C4 in parallel once Phase 1 is live.
5. Phase 3 opens up: prioritisation loop drives which long-tail class ships next.

---

## Non-goals for M8

- Realtime/webhook ingestion (M8 is batch-only).
- Sector-specific *announcement* contracts (design §10 open question). Revisit if data shows systematic per-sector differences.
- Full corpus backfill to 2015 or earlier. Default: 2020 onwards, matching FS default.
- Multi-language contracts. Announcements are Bahasa Indonesia; English translations only for narrative summaries where useful.
