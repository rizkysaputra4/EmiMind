"""Deep Extraction Acceptance Gate (M9.6.2).

Evaluates committed extraction results, per document, against the M9 thresholds
(`docs/DEEP_EXTRACTION_REMEDIATION_PLAN.md` §Phase 6, `tasks/09-M9-deep-extraction.md`,
remediation spec in `docs/m9_workstreams/README.md` Workstream C). Every check is computed from
server-side evidence; nothing the extraction agent typed in is trusted.

| Check              | Source                                                  | Threshold                       |
|--------------------|---------------------------------------------------------|---------------------------------|
| Router recall      | `eval/reports/router_recall.json` (not in --aggregate)  | core >= .90, notes >= .80, precision >= .40 |
| KPI coverage       | contract mandatory KPIs vs committed facts; omissions   | extracted >= 80%, no CRITICAL gap, |
|                    | re-verified against every indexed page                  | 0 contradicted omissions        |
| Concept depth      | raw contract concepts committed, less verified omissions| >= 90% (annual filings)         |
| Segmented facts    | segment + source_page (annual filings)                  | >= 25                           |
| Grounding          | `financial_facts.grounding` (migration 026)             | 100% cell/text on pdf_text pages|
| Narratives         | verbatim on cited page, cross-ticker md5, boilerplate   | 100%, 0, 0, 0 in-doc duplicates |
| Provenance         | source_page in 1..page_count                            | 0 bad                           |
| Token efficiency   | ROUTED logs: chars/4 + 1,600 per page image             | <= max(15% of page_count x 2,000,|
|                    |                                                         |        50,000 tokens)           |
| Period correctness | fiscal_period, period_end, PyMuPDF page count of the PDF| exact; PDF must exist           |
| Embeddings         | `document_pages.embedding_model` (migration 025)        | every page 'BAAI/bge-m3'        |

A missing input (column, log, report, PDF, contract) is a FAIL, never a PASS.

Usage:
    uv run python eval/deep_extraction_gate.py --tickers BMRI,LSIP --out eval/reports/m9_gate.json
    uv run python eval/deep_extraction_gate.py --aggregate --since 2026-09-29T00:00:00+07:00
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
import pymupdf
import yaml  # type: ignore[import-untyped]

from services.mcp.narrative_checks import is_verbatim
from services.mcp.periods import period_end_for
from services.mcp.services.routing import get_extraction_contract
from services.shared.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_EMBEDDING_MODEL = "BAAI/bge-m3"
TOKENS_PER_PAGE_IMAGE = 1600
WHOLE_BOOK_TOKENS_PER_PAGE = 2000
TOKEN_BUDGET_RATIO = 0.15
# What a contract needs (3 statements + ~7-10 note modules, 20-30 pages) is fixed, not
# proportional to book length, so short filings get a floor. It binds below ~167 pages and still
# fails a whole-book read (a 70-page filing served in full is ~100k tokens).
TOKEN_BUDGET_FLOOR = 50_000
KPI_EXTRACTED_MIN = 0.80
SEGMENTED_MIN = 25
RECALL_CORE_MIN = 0.90
RECALL_NOTES_MIN = 0.80
PRECISION_MIN = 0.40
GROUNDED_VALUES = ("cell", "text")
DEFAULT_SECTOR_MIN = 40
# Concept depth is contract-relative (user decision 2026-10-14): the pre-remediation baseline is
# the old 31-concept template counted across ~25 stub docs, and FS_ANNUAL contracts ask for only
# 37-48 facts, so max(2 x baseline, sector min) is unreachable. That figure stays as info.
DEPTH_RATIO_MIN = 0.90

# (table, column, migration that adds it)
REQUIRED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("financial_facts", "grounding", "026_fact_identity_and_grounding.sql"),
    ("document_pages", "embedding_model", "025_document_pages_v2.sql"),
)

PASS, FAIL, NA = "PASS", "FAIL", "N/A"


@dataclass
class CheckResult:
    dimension: str
    ticker: str
    value: Any
    threshold: str
    status: str  # PASS | FAIL | N/A
    details: str = ""
    doc_id: str | None = None
    fiscal_period: str | None = None


# ----------------------------------------------------------------------------- loaders


def _sync_dsn() -> str:
    s = get_settings()
    return s.postgres_dsn_sync or s.postgres_dsn.replace("postgresql+asyncpg://", "postgresql://")


def load_sector_depth_minimums(
    path: Path | str = REPO_ROOT / "db/seeds/sector_depth_minimums.yaml",
) -> dict[str, int]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Sector depth minimums not found: {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "GENERIC" not in data:
        raise ValueError(f"{p} must be a mapping with a GENERIC key")
    return {str(k).upper(): int(v) for k, v in data.items()}


def load_boilerplate_phrases(
    path: Path | str = REPO_ROOT / "db/seeds/narrative_boilerplate.txt",
) -> list[str]:
    p = Path(path)
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()
    return [_norm(line) for line in lines if line.strip() and not line.startswith("#")]


def load_json(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


# ----------------------------------------------------------------------------- pure helpers


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^\w%]+", " ", text.lower()).split())


def is_annual(doc_type: str | None, fiscal_period: str | None) -> bool:
    """Annual filing = audited full-year statements, an annual report, or any Q4 filing.

    Q4 always counts: IDX issuers publish no separate Q4 interim, and a mislabelled doc_type
    must not turn the depth checks into N/A.
    """
    if doc_type in ("FS_ANNUAL", "ANNUAL_REPORT"):
        return True
    return bool(fiscal_period and fiscal_period.endswith("Q4"))


def depth_threshold(
    ticker: str,
    sector: str | None,
    sector_depths: dict[str, int],
    baseline: dict[str, Any],
) -> tuple[int, str]:
    """max(2 x the ticker's pre-remediation distinct concepts, the sector minimum)."""
    sector_key = (sector or "GENERIC").upper()
    sector_min = sector_depths.get(sector_key, sector_depths.get("GENERIC", DEFAULT_SECTOR_MIN))
    base = baseline.get(ticker) or {}
    base_concepts = int(base.get("distinct_concepts") or 0)
    threshold = max(2 * base_concepts, sector_min)
    basis = (
        f"max(2 x baseline {base_concepts}, {sector_key} min {sector_min})"
        if base
        else f"no baseline for {ticker}; {sector_key} min {sector_min}"
    )
    return threshold, basis


def contract_depth(
    contract_concepts: set[str],
    committed: set[str],
    omitted: set[str],
    contradicted: set[str],
) -> tuple[int, int]:
    """(committed extractable concepts, extractable concepts) for one filing.

    Extractable: the filing's raw contract concepts, less those recorded as omitted at commit
    whose omission the page search did not contradict (verified not disclosed). A contradicted
    omission stays extractable and counts as a miss.
    """
    not_disclosed = (omitted - contradicted - committed) & contract_concepts
    extractable = contract_concepts - not_disclosed
    return len(extractable & committed), len(extractable)


def token_budget(whole_book_est: int) -> int:
    """Token budget for one document: 15% of the whole-book estimate, never below the floor."""
    return max(int(whole_book_est * TOKEN_BUDGET_RATIO), TOKEN_BUDGET_FLOOR)


def tokens_from_routed_logs(rows: Sequence[dict[str, Any]]) -> tuple[int | None, str]:
    """Server-side token estimate from ROUTED log metadata; None when it cannot be computed."""
    if not rows:
        return None, "no ROUTED log rows (get_routed_pages never called for this document)"
    missing = [i for i, r in enumerate(rows) if not isinstance(r.get("chars"), int | float)]
    if missing:
        return None, f"{len(missing)}/{len(rows)} ROUTED rows lack 'chars' (pre-M9 remediation logs)"
    chars = sum(int(r["chars"]) for r in rows)
    images = sum(int(r.get("images") or 0) for r in rows)
    tokens = chars // 4 + TOKENS_PER_PAGE_IMAGE * images
    return tokens, f"{len(rows)} ROUTED calls, {chars} chars, {images} page images"


_BIG_NUMBER = re.compile(r"(?<![\w.,])\(?-?\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?\)?|(?<![\w.,])\d{4,}")
_YEAR_ONLY = re.compile(r"^(19|20)\d{2}$")


def omission_search_terms(names: Iterable[str]) -> list[tuple[str, bool]]:
    """(normalized term, is_acronym); words shorter than 6 chars are too ambiguous to search."""
    terms: list[tuple[str, bool]] = []
    for raw in names:
        for part in re.split(r"\s*/\s*", raw or ""):
            part = re.sub(r"\([^)]*\)", " ", part).strip()  # noqa: PLW2901
            if not part:
                continue
            words = part.split()
            if len(words) == 1 and words[0].isupper() and 2 < len(words[0]) <= 6:
                terms.append((words[0], True))
                continue
            norm = _norm(part)
            if len(norm) >= 6 and (norm, False) not in terms:
                terms.append((norm, False))
    return terms


def _term_regex(term: str, acronym: bool) -> re.Pattern[str]:
    if acronym:
        return re.compile(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])")
    words = [re.escape(w) for w in term.split()]
    return re.compile(r"(?<!\w)" + r"[\W_]+".join(words) + r"(?!\w)", re.IGNORECASE)


def omission_contradictions(
    terms: Sequence[tuple[str, bool]], pages: dict[int, str]
) -> list[int]:
    """Pages where a metric label is followed on the same line by a financial-size number."""
    patterns = [_term_regex(t, a) for t, a in terms]
    hits: list[int] = []
    for page_index, page_text in sorted(pages.items()):
        found = False
        for line in (page_text or "").splitlines():
            for rx in patterns:
                match = rx.search(line)
                if not match:
                    continue
                nums = [
                    n for n in _BIG_NUMBER.findall(line[match.end() :])
                    if not _YEAR_ONLY.match(n.strip("()-"))
                ]  # fmt: skip
                if nums:
                    found = True
                    break
            if found:
                break
        if found:
            hits.append(page_index)
    return hits


def find_pdf(source_url: str | None, ticker: str, reports_dir: str) -> Path | None:
    if not source_url:
        return None
    name = Path(source_url).name
    base = Path(reports_dir)
    if not base.is_absolute():
        base = (REPO_ROOT / base).resolve()
    candidates = [
        Path(source_url),
        base / ticker / "processed" / name,
        base / ticker / name,
        base / "processed" / name,
        REPO_ROOT / "incoming_reports" / "processed" / name,
        REPO_ROOT / "incoming_reports" / name,
    ]
    for cand in candidates:
        if cand.is_file():
            return cand
    return None


def pymupdf_page_count(path: Path) -> int | None:
    try:
        with pymupdf.open(str(path)) as pdf:  # type: ignore[no-untyped-call]
            return int(pdf.page_count)
    except Exception:
        return None


# ----------------------------------------------------------------------------- collection


def missing_columns(conn: psycopg.Connection[Any]) -> list[str]:
    out: list[str] = []
    with conn.cursor() as cur:
        for table, column, migration in REQUIRED_COLUMNS:
            cur.execute(
                "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
                (table, column),
            )
            if cur.fetchone() is None:
                out.append(f"{table}.{column} (migration {migration} not applied)")
    return out


async def _fetch_contract(doc_id: str) -> Any:
    return await get_extraction_contract(doc_id)


def _scalar(cur: psycopg.Cursor[Any], sql: str, params: Sequence[Any]) -> int:
    cur.execute(sql, params)
    row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


_SQL_WINDOW_DOCS = """
SELECT DISTINCT ON (d.id) d.id, d.ticker, d.fiscal_period, d.period_end, d.page_count,
       d.source_url, d.doc_type, ip.sector
FROM documents d
JOIN document_processing_log l ON l.doc_id = d.id AND l.action = 'COMMITTED'
LEFT JOIN issuer_profile ip ON ip.ticker = d.ticker
WHERE (%(since)s::timestamptz IS NULL OR l.created_at >= %(since)s::timestamptz)
  AND (%(tickers)s::text[] IS NULL OR d.ticker = ANY(%(tickers)s::text[]))
ORDER BY d.id
"""
_SQL_TICKER_PERIOD_DOC = """
SELECT d.id, d.ticker, d.fiscal_period, d.period_end, d.page_count,
       d.source_url, d.doc_type, ip.sector
FROM documents d
LEFT JOIN issuer_profile ip ON ip.ticker = d.ticker
WHERE d.ticker = %s AND d.fiscal_period = %s
ORDER BY EXISTS (SELECT 1 FROM document_processing_log l
                 WHERE l.doc_id = d.id AND l.action = 'COMMITTED') DESC,
         d.ingested_at DESC
LIMIT 1
"""


def select_documents(
    conn: psycopg.Connection[Any],
    tickers: list[str] | None,
    period: str | None,
    since: datetime | None,
    aggregate: bool,
) -> list[dict[str, Any]]:
    """Target documents. Aggregate: every document COMMITTED inside the window."""
    with conn.cursor() as cur:
        if aggregate:
            cur.execute(_SQL_WINDOW_DOCS, {"since": since, "tickers": tickers})
            rows = cur.fetchall()
        else:
            rows = []
            for t in tickers or []:
                cur.execute(_SQL_TICKER_PERIOD_DOC, (t, period))
                row = cur.fetchone()
                rows.append(row if row else (None, t, period, None, None, None, None, None))
    keys = ["doc_id", "ticker", "fiscal_period", "period_end", "page_count", "source_url",
            "doc_type", "sector"]  # fmt: skip
    return [dict(zip(keys, r, strict=True)) for r in rows]


def collect_metrics(  # noqa: PLR0912
    conn: psycopg.Connection[Any],
    doc: dict[str, Any],
    *,
    sector_depths: dict[str, int],
    baseline: dict[str, Any],
    boilerplate: list[str],
    router_recall: dict[str, Any],
    missing_cols: list[str],
    reports_dir: str,
    contract_fetcher: Any = None,
) -> dict[str, Any]:
    """All raw measurements for one document (no pass/fail decisions here)."""
    ticker = str(doc["ticker"])
    m: dict[str, Any] = {"ticker": ticker, "fiscal_period": doc.get("fiscal_period")}
    if not doc.get("doc_id"):
        m["error"] = f"No document found for {ticker} {doc.get('fiscal_period')}"
        return m
    doc_id = str(doc["doc_id"])
    page_count = int(doc["page_count"] or 0)
    m.update(
        doc_id=doc_id,
        doc_type=doc.get("doc_type"),
        sector=doc.get("sector") or "GENERIC",
        period_end=str(doc["period_end"]) if doc.get("period_end") else None,
        page_count=page_count,
        missing_columns=missing_cols,
        annual=is_annual(doc.get("doc_type"), doc.get("fiscal_period")),
    )

    with conn.cursor() as cur:
        # -- facts / depth / segments / provenance
        cur.execute(
            "SELECT DISTINCT concept_id FROM financial_facts WHERE source_doc_id = %s", (doc_id,)
        )
        concepts = {str(r[0]) for r in cur.fetchall()}
        m["fact_count"] = _scalar(
            cur, "SELECT count(*) FROM financial_facts WHERE source_doc_id = %s", (doc_id,)
        )
        m["distinct_concepts_count"] = len(concepts)
        m["depth_threshold"], m["depth_basis"] = depth_threshold(
            ticker, m["sector"], sector_depths, baseline
        )
        m["segmented_facts_count"] = _scalar(
            cur,
            "SELECT count(*) FROM financial_facts WHERE source_doc_id = %s "
            "AND segment IS NOT NULL AND segment <> 'null'::jsonb AND source_page IS NOT NULL",
            (doc_id,),
        )
        m["bad_provenance_count"] = _scalar(
            cur,
            "SELECT count(*) FROM financial_facts WHERE source_doc_id = %s "
            "AND (source_page IS NULL OR source_page < 1 OR source_page > %s)",
            (doc_id, page_count),
        )

        # -- grounding (financial_facts.grounding, migration 026)
        if any(c.startswith("financial_facts.grounding") for c in missing_cols):
            m["grounding_error"] = "financial_facts.grounding column missing (migration 026)"
        else:
            cur.execute(
                "SELECT COALESCE(dp.text_source, 'missing_page') AS ts, ff.grounding, count(*) "
                "FROM financial_facts ff LEFT JOIN document_pages dp "
                "  ON dp.doc_id = ff.source_doc_id AND dp.page_index = ff.source_page "
                "WHERE ff.source_doc_id = %s GROUP BY 1, 2",
                (doc_id,),
            )
            breakdown = [(str(r[0]), r[1], int(r[2])) for r in cur.fetchall()]
            on_text = [b for b in breakdown if b[0] == "pdf_text"]
            m["grounding_breakdown"] = [list(b) for b in breakdown]
            m["facts_on_text_pages"] = sum(b[2] for b in on_text)
            m["grounded_on_text_pages"] = sum(b[2] for b in on_text if b[1] in GROUNDED_VALUES)
            m["grounded_total"] = sum(b[2] for b in breakdown if b[1] in GROUNDED_VALUES)

        # -- embeddings (document_pages.embedding_model, migration 025)
        m["indexed_pages"] = _scalar(
            cur, "SELECT count(*) FROM document_pages WHERE doc_id = %s", (doc_id,)
        )
        if any(c.startswith("document_pages.embedding_model") for c in missing_cols):
            m["embedding_error"] = "document_pages.embedding_model column missing (migration 025)"
        else:
            m["pages_with_expected_embedding"] = _scalar(
                cur,
                "SELECT count(*) FROM document_pages WHERE doc_id = %s "
                "AND embedding IS NOT NULL AND embedding_model = %s",
                (doc_id, EXPECTED_EMBEDDING_MODEL),
            )

        # -- tokens from ROUTED logs
        cur.execute(
            "SELECT metadata FROM document_processing_log WHERE doc_id = %s AND action = 'ROUTED'",
            (doc_id,),
        )
        routed = [r[0] if isinstance(r[0], dict) else {} for r in cur.fetchall()]
        tokens, token_detail = tokens_from_routed_logs(routed)
        m["routed_tokens"] = tokens
        m["token_detail"] = token_detail
        m["whole_book_est"] = page_count * WHOLE_BOOK_TOKENS_PER_PAGE

        # -- narratives
        cur.execute(
            "SELECT nc.text_original, nc.source_page, dp.page_text FROM narrative_chunks nc "
            "LEFT JOIN document_pages dp ON dp.doc_id = nc.source_doc_id "
            "  AND dp.page_index = nc.source_page WHERE nc.source_doc_id = %s",
            (doc_id,),
        )
        narr = cur.fetchall()
        m["narrative_count"] = len(narr)
        not_verbatim: list[int | None] = []
        bp_hits = 0
        seen: set[str] = set()
        in_doc_dups = 0
        for text_original, source_page, page_text in narr:
            ok, _score = is_verbatim(str(text_original or ""), str(page_text or ""))
            if not ok:
                not_verbatim.append(source_page)
            norm = _norm(str(text_original or ""))
            if any(bp and bp in norm for bp in boilerplate):
                bp_hits += 1
            if norm in seen:
                in_doc_dups += 1
            seen.add(norm)
        m["narratives_not_verbatim"] = len(not_verbatim)
        m["narratives_not_verbatim_pages"] = not_verbatim[:20]
        m["boilerplate_hits"] = bp_hits
        m["in_doc_duplicates"] = in_doc_dups
        m["cross_ticker_duplicates"] = _scalar(
            cur,
            "SELECT count(*) FROM narrative_chunks a JOIN narrative_chunks b "
            "ON md5(a.text_original) = md5(b.text_original) AND a.ticker <> b.ticker "
            "WHERE a.source_doc_id = %s",
            (doc_id,),
        )

        # -- omissions recorded at commit
        cur.execute(
            "SELECT suggested_canonical FROM concept_review "
            "WHERE doc_id = %s AND local_label LIKE 'OMITTED: %%'",
            (doc_id,),
        )
        omitted = {str(r[0]) for r in cur.fetchall()}

        cur.execute("SELECT page_index, page_text FROM document_pages WHERE doc_id = %s", (doc_id,))
        pages = {int(r[0]): str(r[1] or "") for r in cur.fetchall()}

    # -- KPI coverage against the live contract
    fetch = contract_fetcher or (lambda d: asyncio.run(_fetch_contract(d)))
    try:
        contract = fetch(doc_id)
    except Exception as exc:
        m["contract_error"] = f"{type(exc).__name__}: {exc}"
        contract = None
    if contract is not None:
        raw_rules = [r for r in contract.required_facts if r.extraction_mode == "EXTRACTED_RAW"]
        rules = [
            r for r in raw_rules if r.required and r.importance.upper() in ("CRITICAL", "HIGH")
        ]
        mandatory = {r.concept_id for r in rules}
        critical = {r.concept_id for r in rules if r.importance.upper() == "CRITICAL"}
        extracted = mandatory & concepts
        not_extracted = mandatory - extracted
        # omissions are re-verified for every raw contract concept: KPI coverage reads the
        # mandatory ones, concept depth all of them
        contradicted_any: dict[str, list[int]] = {}
        for r in raw_rules:
            if r.concept_id not in concepts and r.concept_id in omitted:
                terms = omission_search_terms([r.label, *r.synonyms_id, *r.synonyms_en])
                hit_pages = omission_contradictions(terms, pages)
                if hit_pages:
                    contradicted_any[r.concept_id] = hit_pages[:10]
        contradicted = {k: v for k, v in contradicted_any.items() if k in not_extracted}
        hit, extractable = contract_depth(
            {r.concept_id for r in raw_rules}, concepts, omitted, set(contradicted_any)
        )
        m.update(
            depth_extractable_count=extractable,
            depth_hit_count=hit,
            depth_ratio=(hit / extractable) if extractable else 0.0,
        )
        m.update(
            mandatory_kpis_count=len(mandatory),
            extracted_kpis_count=len(extracted),
            kpi_extracted_ratio=(len(extracted) / len(mandatory)) if mandatory else 0.0,
            omitted_kpis=sorted(not_extracted & omitted),
            uncovered_kpis=sorted(not_extracted - omitted),
            uncovered_critical=sorted((not_extracted - omitted) & critical),
            contradicted_omissions=contradicted,
            required_narratives_count=len(contract.required_narratives),
        )

    # -- period correctness against the PDF on disk
    pdf = find_pdf(doc.get("source_url"), ticker, reports_dir)
    m["pdf_path"] = str(pdf) if pdf else None
    m["actual_page_count"] = pymupdf_page_count(pdf) if pdf else None
    fp = str(doc.get("fiscal_period") or "")
    try:
        m["expected_period_end"] = str(period_end_for(fp))
    except ValueError:
        m["expected_period_end"] = None

    # -- router recall (from the recall report)
    mods = [x for x in router_recall.get("modules", []) if x.get("ticker") == ticker]
    doc_mods = [x for x in mods if x.get("doc_id") == doc_id] or mods

    def _mean(values: list[float]) -> float | None:
        return sum(values) / len(values) if values else None

    m["router_modules"] = len(doc_mods)
    m["mean_core_recall"] = _mean([float(x["recall"]) for x in doc_mods if x.get("type") == "core"])
    m["mean_notes_recall"] = _mean(
        [float(x["recall"]) for x in doc_mods if x.get("type") == "notes"]
    )
    m["mean_precision"] = _mean(
        [float(x["precision"]) for x in doc_mods if x.get("precision") is not None]
    )
    return m


# ----------------------------------------------------------------------------- evaluation


def _check(  # noqa: PLR0917
    results: list[CheckResult],
    m: dict[str, Any],
    dimension: str,
    ok: bool | None,
    value: Any,
    threshold: str,
    details: str = "",
) -> None:
    status = NA if ok is None else (PASS if ok else FAIL)
    results.append(
        CheckResult(
            dimension=dimension,
            ticker=str(m.get("ticker", "UNKNOWN")),
            value=value,
            threshold=threshold,
            status=status,
            details=details,
            doc_id=m.get("doc_id"),
            fiscal_period=m.get("fiscal_period"),
        )
    )


def evaluate_document(  # noqa: PLR0912
    m: dict[str, Any], *, is_aggregate: bool = False, expected_period: str | None = None
) -> list[CheckResult]:
    results: list[CheckResult] = []
    if "error" in m:
        _check(results, m, "Document lookup", False, m["error"], "document exists", m["error"])
        return results

    # 1. Router recall (skipped in aggregate mode: batch filings have no gold labels)
    if not is_aggregate:
        core, notes, prec = m.get("mean_core_recall"), m.get("mean_notes_recall"), m.get(
            "mean_precision"
        )
        ok = (
            core is not None and core >= RECALL_CORE_MIN
            and notes is not None and notes >= RECALL_NOTES_MIN
            and prec is not None and prec >= PRECISION_MIN
        )  # fmt: skip

        def fmt(x: float | None) -> str:
            return "missing" if x is None else f"{x:.2f}"

        _check(
            results, m, "Router recall", ok,
            f"core={fmt(core)} notes={fmt(notes)} prec={fmt(prec)}",
            f"core>={RECALL_CORE_MIN} notes>={RECALL_NOTES_MIN} prec>={PRECISION_MIN}",
            f"{m.get('router_modules', 0)} gold modules in router_recall.json",
        )  # fmt: skip

    # 2. KPI coverage
    if m.get("contract_error") or "mandatory_kpis_count" not in m:
        err = m.get("contract_error") or "contract not evaluated"
        _check(results, m, "KPI coverage", False, "contract error", "contract loads", err)
    else:
        n = int(m["mandatory_kpis_count"])
        ratio = float(m.get("kpi_extracted_ratio", 0.0))
        contradicted = m.get("contradicted_omissions") or {}
        uncovered_crit = m.get("uncovered_critical") or []
        ok = n > 0 and ratio >= KPI_EXTRACTED_MIN and not contradicted and not uncovered_crit
        details = (
            f"extracted {m.get('extracted_kpis_count')}/{n}; omitted {len(m.get('omitted_kpis', []))};"
            f" uncovered {m.get('uncovered_kpis', [])}; CRITICAL uncovered {uncovered_crit};"
            f" contradicted omissions {contradicted}"
        )
        if n == 0:
            details = "contract has no mandatory EXTRACTED_RAW KPIs"
        _check(
            results, m, "KPI coverage", ok, f"{ratio:.1%} extracted",
            f">= {KPI_EXTRACTED_MIN:.0%} extracted, 0 CRITICAL gaps, 0 contradicted omissions",
            details,
        )  # fmt: skip

    # 3. Concept depth and 4. segmented facts: per annual filing
    annual = bool(m.get("annual"))
    if not annual:
        _check(results, m, "Concept depth", None, str(m.get("distinct_concepts_count", 0)),
               f">= {DEPTH_RATIO_MIN:.0%} of extractable", "not an annual filing")  # fmt: skip
    elif m.get("contract_error") or "depth_extractable_count" not in m:
        err = m.get("contract_error") or "contract not evaluated"
        _check(results, m, "Concept depth", False, "contract error", "contract loads", err)
    else:
        hit, extractable = int(m["depth_hit_count"]), int(m["depth_extractable_count"])
        ratio = float(m.get("depth_ratio", 0.0))
        _check(
            results, m, "Concept depth", extractable > 0 and ratio >= DEPTH_RATIO_MIN,
            f"{hit}/{extractable} ({ratio:.1%})",
            f">= {DEPTH_RATIO_MIN:.0%} of extractable contract concepts",
            f"extractable = raw contract concepts less verified omissions; "
            f"{m.get('distinct_concepts_count', 0)} distinct concepts committed; "
            f"info only: {m.get('depth_basis')} = {m.get('depth_threshold')}",
        )  # fmt: skip
    seg = int(m.get("segmented_facts_count", 0))
    _check(
        results, m, "Segmented facts", (seg >= SEGMENTED_MIN) if annual else None, str(seg),
        f">= {SEGMENTED_MIN}", "segment + source_page" if annual else "not an annual filing",
    )  # fmt: skip

    # 5. Grounding share from financial_facts.grounding
    if m.get("grounding_error"):
        _check(results, m, "Grounding", False, "column missing", "100%", m["grounding_error"])
    else:
        total = int(m.get("facts_on_text_pages", 0))
        grounded = int(m.get("grounded_on_text_pages", 0))
        facts = int(m.get("fact_count", 0))
        ok = facts > 0 and total > 0 and grounded == total
        _check(
            results, m, "Grounding", ok,
            f"{grounded}/{total}" if total else "0 facts on text pages",
            "100% cell/text on pdf_text pages", f"breakdown {m.get('grounding_breakdown')}",
        )  # fmt: skip

    # 6. Narratives
    n_narr = int(m.get("narrative_count", 0))
    bad_verb = int(m.get("narratives_not_verbatim", 0))
    dups = int(m.get("cross_ticker_duplicates", 0))
    bps = int(m.get("boilerplate_hits", 0))
    in_doc = int(m.get("in_doc_duplicates", 0))
    required_n = int(m.get("required_narratives_count", 0))
    ok = bad_verb == 0 and dups == 0 and bps == 0 and in_doc == 0 and not (
        required_n > 0 and n_narr == 0
    )
    _check(
        results, m, "Narratives", ok,
        f"{n_narr - bad_verb}/{n_narr} verbatim",
        "100% verbatim, 0 dup, 0 boilerplate",
        f"not verbatim pages {m.get('narratives_not_verbatim_pages', [])}; cross-ticker dups {dups};"
        f" boilerplate {bps}; in-doc dups {in_doc}; required sections {required_n}",
    )  # fmt: skip

    # 7. Provenance
    bad = int(m.get("bad_provenance_count", 0))
    _check(results, m, "Provenance", bad == 0, str(bad), "0", "source_page outside 1..page_count")

    # 8. Token efficiency (server-side, ROUTED logs)
    tokens = m.get("routed_tokens")
    est = int(m.get("whole_book_est", 0))
    if tokens is None or est <= 0:
        _check(
            results, m, "Token efficiency", False, "missing",
            f"<= max({TOKEN_BUDGET_RATIO:.0%}, {TOKEN_BUDGET_FLOOR:,} tokens)",
            str(m.get("token_detail")),
        )  # fmt: skip
    else:
        budget = token_budget(est)
        _check(
            results, m, "Token efficiency", int(tokens) <= budget,
            f"{int(tokens):,} tokens ({int(tokens) / est:.1%})",
            f"<= {budget:,} (max({TOKEN_BUDGET_RATIO:.0%} of {est:,}, {TOKEN_BUDGET_FLOOR:,}))",
            str(m.get("token_detail")),
        )  # fmt: skip

    # 9. Period correctness (PDF must exist)
    fp = m.get("fiscal_period")
    pc, apc = int(m.get("page_count") or 0), m.get("actual_page_count")
    problems: list[str] = []
    if expected_period and fp != expected_period:
        problems.append(f"fiscal_period {fp} != {expected_period}")
    if not m.get("expected_period_end") or m.get("period_end") != m.get("expected_period_end"):
        problems.append(f"period_end {m.get('period_end')} != {m.get('expected_period_end')}")
    if not m.get("pdf_path"):
        problems.append("PDF not found on disk")
    elif apc is None:
        problems.append("PDF unreadable")
    elif int(apc) != pc or pc <= 0:
        problems.append(f"page_count {pc} != PyMuPDF {apc}")
    _check(
        results, m, "Period correctness", not problems,
        f"{fp} / {m.get('period_end')} / {pc}p", "exact match", "; ".join(problems) or "ok",
    )  # fmt: skip

    # 10. Embeddings
    if m.get("embedding_error"):
        _check(results, m, "Embeddings", False, "column missing", "all pages", m["embedding_error"])
    else:
        idx = int(m.get("indexed_pages", 0))
        good = int(m.get("pages_with_expected_embedding", 0))
        ok = idx > 0 and idx == pc and good == idx
        why = []
        if idx != pc:
            why.append(f"{idx} indexed pages != page_count {pc}")
        if good != idx:
            why.append(f"{idx - good} pages without a {EXPECTED_EMBEDDING_MODEL} embedding")
        _check(
            results, m, "Embeddings", ok, f"{good}/{idx} pages ({pc} in PDF)",
            f"every page {EXPECTED_EMBEDDING_MODEL}", "; ".join(why) or "ok",
        )  # fmt: skip
    return results


def evaluate_gate(
    metrics_list: list[dict[str, Any]],
    is_aggregate: bool = False,
    expected_period: str | None = None,
) -> tuple[bool, list[CheckResult], dict[str, Any]]:
    """Pure evaluation of collected metrics. Returns (all_passed, results, summary)."""
    results: list[CheckResult] = []
    per_doc: list[dict[str, Any]] = []
    for m in metrics_list:
        doc_results = evaluate_document(
            m, is_aggregate=is_aggregate, expected_period=None if is_aggregate else expected_period
        )
        results.extend(doc_results)
        per_doc.append(
            {
                "ticker": m.get("ticker"),
                "doc_id": m.get("doc_id"),
                "fiscal_period": m.get("fiscal_period"),
                "passed": all(r.status != FAIL for r in doc_results),
                "failed_checks": [r.dimension for r in doc_results if r.status == FAIL],
            }
        )
    all_passed = bool(metrics_list) and all(r.status != FAIL for r in results)
    summary = {
        "timestamp": datetime.now(UTC).isoformat(),
        "all_passed": all_passed,
        "is_aggregate": is_aggregate,
        "documents": len(metrics_list),
        "documents_passed": sum(1 for d in per_doc if d["passed"]),
        "per_document": per_doc,
        "total_checks": len(results),
        "passed_checks": sum(1 for r in results if r.status == PASS),
        "failed_checks": sum(1 for r in results if r.status == FAIL),
        "na_checks": sum(1 for r in results if r.status == NA),
    }
    if not metrics_list:
        summary["error"] = "no documents to evaluate"
    return all_passed, results, summary


def print_results_table(results: list[CheckResult], summary: dict[str, Any]) -> None:
    width = 128
    print("\n" + "=" * width)
    verdict = "ALL CHECKS PASSED" if summary["all_passed"] else "GATE FAILED"
    print(f" DEEP EXTRACTION ACCEPTANCE GATE - {verdict}")
    print("=" * width)
    print(f"| {'Dimension':<20} | {'Ticker':<6} | {'Period':<6} | {'Value':<30} | "
          f"{'Threshold':<40} | {'Status':<6} |")  # fmt: skip
    print("|" + "-" * (width - 2) + "|")
    for r in results:
        print(
            f"| {r.dimension:<20} | {r.ticker:<6} | {r.fiscal_period or ''!s:<6} | "
            f"{str(r.value)[:30]:<30} | {str(r.threshold)[:40]:<40} | {r.status:<6} |"
        )
        if r.status == FAIL and r.details:
            print(f"|   -> {r.details[: width - 10]}")
    print("|" + "-" * (width - 2) + "|")
    if summary.get("error"):
        print(f"ERROR: {summary['error']}")
    print(
        f"Summary: {summary['passed_checks']} PASS, {summary['failed_checks']} FAIL, "
        f"{summary['na_checks']} N/A over {summary['documents']} document(s); "
        f"{summary['documents_passed']} document(s) fully passing. "
        f"Overall: {'PASS (exit 0)' if summary['all_passed'] else 'FAIL (exit 1)'}\n"
    )


def report(
    metrics_list: list[dict[str, Any]],
    *,
    is_aggregate: bool,
    expected_period: str | None,
    out: Path | None = None,
    extra: dict[str, Any] | None = None,
) -> int:
    """Evaluates, prints, optionally writes JSON, and returns the process exit code."""
    all_passed, results, summary = evaluate_gate(metrics_list, is_aggregate, expected_period)
    if extra:
        summary.update(extra)
    print_results_table(results, summary)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "summary": summary,
            "results": [asdict(r) for r in results],
            "metrics": metrics_list,
        }
        out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        print(f"Wrote gate report to {out}")
    return 0 if all_passed else 1


def run_gate(
    *,
    tickers: list[str] | None,
    period: str | None,
    aggregate: bool,
    since: datetime | None,
    sector_depth_path: Path | str = REPO_ROOT / "db/seeds/sector_depth_minimums.yaml",
    baseline_path: Path | str = REPO_ROOT / "eval/reports/m9_baseline.json",
    router_recall_path: Path | str = REPO_ROOT / "eval/reports/router_recall.json",
    boilerplate_path: Path | str = REPO_ROOT / "db/seeds/narrative_boilerplate.txt",
    dsn: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Collects metrics for the requested documents. Returns (metrics_list, run_info)."""
    sector_depths = load_sector_depth_minimums(sector_depth_path)
    baseline = load_json(baseline_path)
    router_recall = load_json(router_recall_path)
    boilerplate = load_boilerplate_phrases(boilerplate_path)
    reports_dir = get_settings().reports_dir
    metrics: list[dict[str, Any]] = []
    with psycopg.connect(dsn or _sync_dsn()) as conn:
        cols = missing_columns(conn)
        docs = select_documents(conn, tickers, period, since, aggregate)
        for doc in docs:
            metrics.append(
                collect_metrics(
                    conn, doc, sector_depths=sector_depths, baseline=baseline,
                    boilerplate=boilerplate, router_recall=router_recall, missing_cols=cols,
                    reports_dir=reports_dir,
                )
            )  # fmt: skip
    info = {
        "missing_columns": cols,
        "since": since.isoformat() if since else None,
        "tickers": tickers,
        "period": None if aggregate else period,
        "router_recall_report": str(router_recall_path) if router_recall else None,
    }
    return metrics, info


def _parse_since(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    if isinstance(dt, datetime) and dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate deep extraction acceptance criteria.")
    parser.add_argument("--tickers", default=None, help="Comma-separated tickers")
    parser.add_argument("--period", default="2025Q4", help="Fiscal period (non-aggregate mode)")
    parser.add_argument("--out", default=None, help="Output JSON path")
    parser.add_argument(
        "--aggregate", action="store_true",
        help="Evaluate every document COMMITTED in the --since window (skips router recall)",
    )  # fmt: skip
    parser.add_argument("--since", default=None, help="ISO timestamp: window start (aggregate)")
    parser.add_argument("--sector-depth", default=str(REPO_ROOT / "db/seeds/sector_depth_minimums.yaml"))
    parser.add_argument("--baseline", default=str(REPO_ROOT / "eval/reports/m9_baseline.json"))
    parser.add_argument("--router-recall", default=str(REPO_ROOT / "eval/reports/router_recall.json"))
    parser.add_argument("--boilerplate", default=str(REPO_ROOT / "db/seeds/narrative_boilerplate.txt"))
    args = parser.parse_args(argv)

    tickers = [t.strip().upper() for t in (args.tickers or "").split(",") if t.strip()] or None
    if not args.aggregate and not tickers:
        tickers = ["BMRI", "LSIP"]
    if args.since and not args.aggregate:
        parser.error("--since is only meaningful with --aggregate")
    since = _parse_since(args.since)
    metrics, info = run_gate(
        tickers=tickers, period=args.period, aggregate=args.aggregate, since=since,
        sector_depth_path=args.sector_depth, baseline_path=args.baseline,
        router_recall_path=args.router_recall, boilerplate_path=args.boilerplate,
    )  # fmt: skip
    return report(
        metrics,
        is_aggregate=args.aggregate,
        expected_period=None if args.aggregate else args.period,
        out=Path(args.out) if args.out else None,
        extra=info,
    )


if __name__ == "__main__":
    sys.exit(main())

