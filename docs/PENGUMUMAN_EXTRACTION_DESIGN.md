# Pengumuman (IDX Announcement) Extraction — Design

> Companion architecture doc for [`tasks/08-M8-pengumuman-extraction.md`](../tasks/08-M8-pengumuman-extraction.md).
> Scope: extend EmiMind to ingest, classify, and extract structured facts from **any PDF** published on the IDX *Pengumuman* tab (`https://www.idx.co.id/id/perusahaan-tercatat/pengumuman/`).

---

## 1. Why this matters

Today EmiMind covers financial statements (`FS_QUARTERLY`, `FS_ANNUAL`) and annual reports (`AR`) — a rich but narrow slice of what actually moves prices. Corporate announcements (dividend, rights issue, RUPS results, material information, insider transactions, board changes, bond issuance, etc.) carry the events that break trends and reset consensus. Without them, the graph is missing its causal spine.

Goal: **no IDX PDF for a covered ticker is un-extractable**. High-value classes get bespoke structured contracts; everything else gets a generic disclosure contract as a safety net.

---

## 2. IDX pengumuman endpoint

**Base:** `https://www.idx.co.id/primary/ListedCompany/GetAnnouncement`

**Params (empirical, subject to change):**

| Param | Example | Notes |
|---|---|---|
| `indexFrom` | `1` | 1-based pagination cursor |
| `pageSize` | `20` | Cap ~100 |
| `dateFrom` | `2025-01-01` | ISO date, inclusive |
| `dateTo` | `2025-12-31` | ISO date, inclusive |
| `kodeEmiten` | `NCKL` | Optional — omit for all issuers |
| `keyword` | `dividen` | Optional title/subject filter |
| `SortColumn` | `TanggalPengumuman` | Rarely needed |
| `SortOrder` | `desc` | |

**Response shape (expected, based on the FS endpoint's shape):** `{ ResultCount, Results: [ { KodeEmiten, JudulPengumuman, TanggalPengumuman, Attachments: [ { File_Name, File_Path, File_Size, File_Type } ] } ] }`. Must be confirmed with a real payload once Cloudflare access is solved (see §3).

**File URL:** `https://www.idx.co.id` + `File_Path` (same convention as FS).

---

## 3. Cloudflare block — manual-solve UX flow

The `GetAnnouncement` endpoint is protected harder than `GetFinancialReport`:

- Vanilla `httpx` / `requests` → 403 (JA3 fingerprint).
- `curl_cffi` with `impersonate='chrome131'` (works for FS) → **still 403** JS challenge or 503 Varnish.
- Full browser (Playwright) works but is heavy infra.

**Chosen approach: assisted manual solve.** When the downloader hits Cloudflare, it prints an instruction block that the user can act on, then waits.

### 3.1 UX flow

```
$ uv run --project ../EmiMind python scripts/download_idx_reports.py --tickers NCKL --mode announcements
Querying MCP server for already-processed documents...
Warming up IDX session...

======================================================================
  IDX Cloudflare challenge detected on /primary/ListedCompany/GetAnnouncement
  A human "I'm not a robot" check is required.

  1. Open this URL in your browser (Chrome/Edge/Firefox — logged-in session OK):
     https://www.idx.co.id/id/perusahaan-tercatat/pengumuman/

  2. Solve the Cloudflare challenge if it appears.

  3. Open DevTools → Application/Storage → Cookies → https://www.idx.co.id
     Copy the value of the `cf_clearance` cookie.

  4. Paste it below (or press Ctrl+C to abort):

  cf_clearance> _
======================================================================
```

The user pastes the cookie; the script stores it in `~/.emimind/idx_cookies.json` with a timestamp and continues. On next run the cookie is reused until it expires (typically 30 min – 24 h), at which point the script re-prompts.

### 3.2 Non-interactive fallback

For CI / cron: honour `IDX_CF_CLEARANCE` env var. If set, skip the prompt and try the cookie directly; on failure log & exit non-zero rather than blocking on stdin.

### 3.3 Optional: `--browser-open` flag

Convenience: when set, the script opens the URL via `webbrowser.open()` so the user doesn't have to copy-paste it.

### 3.4 Escalation path

If manual solve becomes annoying at scale, later swap the CF handling for:
- **Playwright** headless with saved profile — solve once, reuse profile.
- **FlareSolverr** Docker sidecar — proxies through a real browser.

Deferred until it's actually painful; the manual flow is fine for weekly runs.

---

## 4. Document taxonomy

IDX pengumuman is heterogeneous. Below is the working taxonomy (to be verified against real samples during task 2).

### 4.1 High-value classes (bespoke contracts)

| doc_type | Description | Key extractable fields |
|---|---|---|
| `DIVIDEND` | Cash / stock dividend announcement | DPS, total amount, cum/ex/recording/payment dates, dividend type |
| `RIGHTS_ISSUE` | HMETD (rights issue) | Ratio, exercise price, HMETD trading period, use of proceeds, dilution |
| `RUPS_RESULT` | Annual/EGM meeting results | Agenda outcomes, dividend approved, board changes, capital changes |
| `MATERIAL_INFO` | KTI / material information disclosure | Event type, financial impact, effective date, counterparty |
| `BOND_ISSUE` | MTN / bond / sukuk issuance | Principal, coupon, tenor, use of proceeds, rating |
| `AFFILIATED_TX` | Transaksi afiliasi / material tx | Value, counterparty, related party test, independent appraisal |
| `PRIVATE_PLACEMENT` | PMTHMETD (non-rights capital raise) | Shares, price, subscribers, dilution |
| `TENDER_OFFER` | Tender offer / mandatory tender | Price, ratio, acceptance window |

### 4.2 Lower-value classes (generic contract initially)

`INSIDER_TX`, `BOARD_CHANGE` (direksi/komisaris), `SUSPEND_NOTICE`, `UNSUSPEND_NOTICE`, `PUBLIC_EXPOSE`, `ARTIKEL_MEDIA`, `SHARE_BUYBACK`, `ARTICLES_AMENDMENT`, `NAME_CHANGE`, `LISTING_ACTION`, others.

Each may earn a bespoke contract later based on actual downstream demand.

### 4.3 Safety net: `GENERIC_DISCLOSURE`

Every announcement gets *at least* the generic contract, so nothing is unextractable:

- `doc_date`
- `effective_date`
- `parties[]` (issuer, counterparty, third parties)
- `monetary_amounts[]` (currency, amount, context)
- `key_dates[]` (label, date)
- `narrative_summary` (LLM one-paragraph summary)
- `event_type_hint` (best-guess classifier tag)

---

## 5. Doc classification

Two stages:

1. **Deterministic first pass** — regex on `JudulPengumuman` (announcement title) and filename. Fast, cheap, works for the ~70% of announcements with standardised titles. Rules table lives in a new seed `db/seeds/announcement_class_rules.csv` (`pattern`, `doc_type`, `priority`).
2. **LLM fallback** — when regex is inconclusive, call the extraction agent with a lightweight "classify this PDF" prompt that returns one of the enum values. Cached per `doc_hash`.

The classifier writes `documents.doc_type` at ingest time. Downstream `get_extraction_contract(doc_id)` uses `doc_type` to route to the right contract.

---

## 6. Database schema changes

New migration `db/schema/02X_announcement_doc_types.sql`:

```sql
-- Expand doc_type domain
ALTER TABLE documents
    DROP CONSTRAINT IF EXISTS documents_doc_type_check;

-- If doc_type is text (not enum), add a CHECK; if enum, ALTER TYPE ... ADD VALUE.
-- Confirmed shape after inspecting existing schema.

-- Announcement metadata table (only for announcement docs)
CREATE TABLE IF NOT EXISTS announcement_metadata (
    doc_id UUID PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    announcement_title TEXT NOT NULL,
    announcement_date DATE NOT NULL,
    doc_class TEXT NOT NULL,
    classifier_source TEXT NOT NULL CHECK (classifier_source IN ('regex', 'llm', 'manual')),
    classifier_confidence NUMERIC(3, 2)
);

-- Classification rule seed loaded by scripts/seed_announcement_class_rules.py
CREATE TABLE IF NOT EXISTS announcement_class_rules (
    id SERIAL PRIMARY KEY,
    pattern TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    priority INT NOT NULL DEFAULT 100,
    active BOOLEAN NOT NULL DEFAULT TRUE
);
```

Extraction contract routing: `sector_metric_contracts` becomes keyed on `(sector, doc_type)` instead of just `sector`. Migration adds the column with default `FS_QUARTERLY` so existing contracts are unaffected.

---

## 7. Extraction contract design per class

Each bespoke contract lives in `db/seeds/announcement_contracts/{DOC_TYPE}.yaml`:

```yaml
# db/seeds/announcement_contracts/DIVIDEND.yaml
doc_type: DIVIDEND
sector: UNIVERSAL         # applies to all sectors unless overridden
required_facts:
  - concept_id: dividend_per_share
    importance: CRITICAL
    synonyms_id: ["dividen per saham", "DPS"]
    synonyms_en: ["dividend per share", "DPS"]
    expected_type: currency_per_share
  - concept_id: total_dividend_amount
    importance: HIGH
    synonyms_id: ["jumlah dividen"]
    synonyms_en: ["total dividend"]
    expected_type: currency
  - concept_id: dividend_cum_date
    importance: CRITICAL
    synonyms_id: ["cum dividen", "cum date"]
    expected_type: date
  # ...ex, recording, payment
narrative_sections:
  - id: dividend_rationale
    prompt: "Summarise the dividend approval context and payout ratio if stated."
```

Same YAML shape for `RIGHTS_ISSUE`, `RUPS_RESULT`, etc. A one-time seed script loads them into `sector_metric_contracts`.

`GENERIC_DISCLOSURE` uses a fixed contract compiled into `services/mcp/contracts.py` — no seed needed.

---

## 8. Extraction agent runbook changes

Add to `../EmiMind-Extraction/AGENTS.md`:

1. When `inspect_document` returns `AUTHORIZED` with `doc_type` starting with an announcement class (not `FS_*` / `AR`), the extraction workflow is **schema-driven, not exhaustive**: only the fields in `required_facts[]` are needed; page-navigation heuristics differ from FS.
2. If `doc_type == GENERIC_DISCLOSURE`, extract the safety-net fields and produce a strong `narrative_summary` — do not fabricate KPIs that aren't in the contract.
3. Announcements are usually 1–10 pages; scanning the full PDF is acceptable and expected.

---

## 9. Ingest / downloader integration

- Downloader adds `--mode {financial,announcements,all}` (default `all`).
- Announcement output path: `incoming_reports/{TICKER}/announcements/{YYYY-MM-DD}_{DOC_CLASS_HINT}_{safe_title}.pdf`.
- Announcement metadata (title, date, hint) preserved in a per-file sidecar `.meta.json` for the extraction agent to consume:

```json
{
  "announcement_title": "Pemberitahuan Pembayaran Dividen Tunai",
  "announcement_date": "2025-05-15",
  "doc_class_hint": "DIVIDEND",
  "idx_file_id": "...",
  "source_url": "https://www.idx.co.id/Portals/0/..."
}
```

- The MCP server's `inspect_document` reads the sidecar if present to seed `doc_type` and metadata.
- `list_processed_documents` already returns per-ticker file basenames — no change needed for dedupe.

---

## 10. Open questions

1. **Sector-specific announcement contracts?** e.g. does a Bank RUPS need different fields than a Mining RUPS? Assume no for v1; revisit if data shows otherwise.
2. **Backfill horizon.** How far back do we go? Default proposal: **2020 onwards** matching FS default. May balloon storage — ~500 announcements/year × 900 issuers × 5 years ≈ 2.25 M PDFs total in the worst case. In practice most issuers publish 20–80/year → 100 k–350 k. Storage plan: MinIO tier for cold announcements, hot in DB metadata only.
3. **Real-time vs batch.** v1 = batch weekly. Realtime (webhook/RSS) is a later concern.
4. **Language.** Announcements are almost entirely Bahasa Indonesia. Translation for narrative summaries: yes for `MATERIAL_INFO` and `RIGHTS_ISSUE`, defer for others.
