"""M9 batch rollout helper (M9.6.3): prepare filings for agent extraction, then report.

Extraction itself is done by the agent following `EmiMind-Extraction/AGENTS.md`; this script
does the deterministic parts around it.

    prepare  pick one real financial-statement filing per ticker for --period (never ESG,
             checklists, cover letters or other administrative files), copy it to a staging
             folder outside incoming_reports (inspection archives files found there), then
             inspect -> index pages -> embed pages. Resumable: every step is idempotent and the
             manifest records progress after each filing.
    report   per-document status (inspection, pages indexed/embedded, committed facts) plus the
             acceptance gate in --aggregate mode over the batch window, written to
             eval/reports/m9_batch_<date>.json. Exit code 1 when the gate fails.

Ticker priority comes from data, not a hardcoded list: lighthouse (BMRI, LSIP) -> LQ45/IDX30 ->
KOMPAS100 (index membership in scripts/seed_idx_tickers.IDX_TICKERS) -> every other ticker in
issuer_profile.

Usage:
    uv run python scripts/m9_batch.py prepare --priority lq45 --limit 20 --period 2025Q4
    uv run python scripts/m9_batch.py prepare --tickers BMRI,LSIP
    uv run python scripts/m9_batch.py report
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from eval.deep_extraction_gate import report as gate_report
from eval.deep_extraction_gate import run_gate
from scripts.seed_idx_tickers import IDX_TICKERS
from services.ingest.tasks.embed_pages import embed_pages_task
from services.ingest.tasks.index_pages import index_pages_task
from services.mcp.periods import resolve_fiscal_period
from services.mcp.services.common import get_engine
from services.mcp.services.inspection import (
    classify_administrative,
    infer_doc_type,
    inspect_document,
    read_pdf_facts,
)
from services.mcp.types import InspectionStatus
from services.shared.config import get_settings
from services.shared.logging import get_logger

log = get_logger("scripts.m9_batch")

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORTS_OUT = REPO_ROOT / "eval" / "reports"
MANIFEST = REPORTS_OUT / "m9_batch_manifest.json"
LIGHTHOUSE = ("BMRI", "LSIP")
TIERS = ("lighthouse", "lq45", "kompas100", "all")
EXPECTED_MODEL = "BAAI/bge-m3"
# IDX-generated renderings (FinancialStatement-2025-Tahunan-XXXX.pdf) rank below the issuer's
# own released statements, which carry the full notes.
_IDX_RENDER = re.compile(r"^financialstatement-\d{4}-", re.I)
_PREFIX = re.compile(r"^[A-Za-z0-9]+_\d{4}_(TW1|TW2|TW3|AUDIT|ANNUAL)_[A-Za-z0-9]+_", re.I)


# ----------------------------------------------------------------------------- selection


def tier_of(ticker: str, membership: dict[str, str]) -> int:
    if ticker in LIGHTHOUSE:
        return 0
    idx = membership.get(ticker, "")
    if idx in ("LQ45", "IDX30"):
        return 1
    if idx == "KOMPAS100":
        return 2
    return 3


def order_tickers(universe: list[str], priority: str) -> list[str]:
    """Orders tickers by tier and keeps the tiers up to and including `priority`."""
    membership = {t: idx for t, _name, _sector, _sub, idx in IDX_TICKERS}
    max_tier = TIERS.index(priority)
    ranked = sorted(set(universe) | set(LIGHTHOUSE), key=lambda t: (tier_of(t, membership), t))
    return [t for t in ranked if tier_of(t, membership) <= max_tier]


@dataclass(frozen=True)
class Candidate:
    path: Path
    page_count: int
    doc_type: str


def select_filing(ticker_dir: Path, period: str, kind: str = "fs") -> Candidate | None:
    """Best real statement filing for `period`; administrative/ESG/cover-letter files never."""
    files = sorted({*ticker_dir.glob("*.pdf"), *(ticker_dir / "processed").glob("*.pdf")})
    ranked: list[tuple[tuple[int, int], Candidate]] = []
    for f in files:
        res = resolve_fiscal_period(f.name)
        if res is None or res.conflict or res.fiscal_period != period:
            continue
        if classify_administrative(f.name, None):
            continue
        doc_type = infer_doc_type(f.name, period, None)
        wanted = ("ANNUAL_REPORT",) if kind == "ar" else ("FS_ANNUAL", "FS_QUARTERLY")
        if doc_type not in wanted:
            continue
        facts = read_pdf_facts(f)
        if facts is None or classify_administrative(f.name, facts):
            continue
        title = _PREFIX.sub("", f.name)
        own_release = 0 if _IDX_RENDER.match(title) else 1
        ranked.append(((own_release, facts.page_count), Candidate(f, facts.page_count, doc_type)))
    if not ranked:
        return None
    return max(ranked, key=lambda x: x[0])[1]


# ----------------------------------------------------------------------------- manifest


def load_manifest(path: Path = MANIFEST) -> dict[str, Any]:
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    return {"entries": {}}


def save_manifest(manifest: dict[str, Any], path: Path = MANIFEST) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")


# ----------------------------------------------------------------------------- DB status


async def page_status(engine: AsyncEngine, doc_id: str) -> dict[str, Any]:
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    """
                    SELECT d.page_count, d.fiscal_period, d.doc_type, d.ticker,
                      (SELECT count(*) FROM document_pages p WHERE p.doc_id = d.id) AS indexed,
                      (SELECT count(*) FROM document_pages p WHERE p.doc_id = d.id
                         AND p.embedding IS NOT NULL AND p.embedding_model = :model) AS embedded,
                      (SELECT count(*) FROM document_pages p WHERE p.doc_id = d.id
                         AND p.text_source = 'ocr_failed') AS ocr_failed,
                      (SELECT count(*) FROM financial_facts f WHERE f.source_doc_id = d.id) AS facts,
                      EXISTS (SELECT 1 FROM document_processing_log l WHERE l.doc_id = d.id
                         AND l.action = 'COMMITTED') AS committed
                    FROM documents d WHERE d.id = :id
                    """
                ),
                {"id": doc_id, "model": EXPECTED_MODEL},
            )
        ).mappings().first()
    return dict(row) if row else {"missing": True}


# ----------------------------------------------------------------------------- prepare


async def prepare_one(
    engine: AsyncEngine, ticker: str, cand: Candidate, stage_dir: Path
) -> dict[str, Any]:
    staged = stage_copy(cand.path, stage_dir, ticker)
    entry: dict[str, Any] = {
        "ticker": ticker,
        "source": str(cand.path),
        "staged": str(staged),
        "page_count": cand.page_count,
        "doc_type": cand.doc_type,
    }
    insp = await inspect_document(str(staged), ticker=ticker)
    entry.update(inspect_status=insp.status.value, doc_id=insp.doc_id, message=insp.message)
    if insp.status != InspectionStatus.AUTHORIZED or not insp.doc_id:
        entry["status"] = f"not_prepared:{insp.status.value}"
        return entry
    entry["fiscal_period"] = insp.fiscal_period
    ctx: dict[str, Any] = {"db_pool": engine}
    await index_pages_task(ctx, insp.doc_id)
    await embed_pages_task(ctx, insp.doc_id)
    st = await page_status(engine, insp.doc_id)
    entry["pages"] = st
    complete = st.get("indexed") == st.get("page_count") == st.get("embedded")
    entry["status"] = "ready" if complete else "incomplete"
    return entry


def resolve_dirs(stage_arg: str | None) -> tuple[Path, Path]:
    """(reports_dir, stage_dir); staging defaults to a sibling of incoming_reports."""
    reports_dir = Path(get_settings().reports_dir)
    if not reports_dir.is_absolute():
        reports_dir = (REPO_ROOT / reports_dir).resolve()
    stage_dir = Path(stage_arg).resolve() if stage_arg else reports_dir.parent / "m9_stage"
    return reports_dir, stage_dir


def stage_copy(src: Path, stage_dir: Path, ticker: str) -> Path:
    staged = stage_dir / ticker / src.name
    staged.parent.mkdir(parents=True, exist_ok=True)
    if not staged.exists():
        shutil.copy2(src, staged)
    return staged


async def prepare(args: argparse.Namespace) -> int:
    reports_dir, stage_dir = resolve_dirs(args.stage_dir)
    engine = get_engine()
    manifest = load_manifest()
    manifest.setdefault("batch_start", datetime.now(UTC).isoformat())
    manifest["period"] = args.period
    entries: dict[str, Any] = manifest.setdefault("entries", {})
    try:
        if args.tickers:
            tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
        else:
            async with engine.connect() as conn:
                res = await conn.execute(text("SELECT ticker FROM issuer_profile"))
                universe = [str(r[0]) for r in res.fetchall()]
            tickers = order_tickers(universe, args.priority)
        done = 0
        for ticker in tickers:
            if args.limit and done >= args.limit:
                break
            key = f"{ticker}:{args.period}"
            prev = entries.get(key)
            if prev and prev.get("status") == "ready" and prev.get("doc_id"):
                st = await page_status(engine, prev["doc_id"])
                if st.get("indexed") == st.get("page_count") == st.get("embedded"):
                    log.info("Already prepared, skipping", ticker=ticker, doc_id=prev["doc_id"])
                    done += 1
                    continue
            cand = select_filing(reports_dir / ticker, args.period, args.kind)
            if cand is None:
                entries[key] = {"ticker": ticker, "status": "no_filing_found"}
                save_manifest(manifest)
                continue
            log.info("Preparing filing", ticker=ticker, file=cand.path.name, pages=cand.page_count)
            try:
                entries[key] = await prepare_one(engine, ticker, cand, stage_dir)
            except Exception as exc:
                log.error("Prepare failed", ticker=ticker, error=str(exc))
                entries[key] = {"ticker": ticker, "source": str(cand.path), "status": "error",
                                "error": f"{type(exc).__name__}: {exc}"}  # fmt: skip
            save_manifest(manifest)
            done += 1
    finally:
        await engine.dispose()
    ready = sum(1 for e in entries.values() if e.get("status") == "ready")
    print(f"Prepared {ready} filing(s) ready for extraction; manifest: {MANIFEST}")
    for e in entries.values():
        print(f"  {e.get('ticker'):<6} {e.get('status'):<32} {Path(str(e.get('staged', ''))).name}")
    return 0


# ----------------------------------------------------------------------------- report


async def _doc_statuses(entries: dict[str, Any]) -> list[dict[str, Any]]:
    engine = get_engine()
    try:
        out = []
        for key, e in sorted(entries.items()):
            row = {"key": key, **{k: e.get(k) for k in ("ticker", "status", "doc_id", "staged")}}
            if e.get("doc_id"):
                row["db"] = await page_status(engine, e["doc_id"])
            out.append(row)
        return out
    finally:
        await engine.dispose()


def report(args: argparse.Namespace) -> int:
    manifest = load_manifest()
    entries: dict[str, Any] = manifest.get("entries", {})
    since_raw = args.since or manifest.get("batch_start")
    since = datetime.fromisoformat(since_raw) if since_raw else None
    if since and since.tzinfo is None:
        since = since.replace(tzinfo=UTC)
    docs = asyncio.run(_doc_statuses(entries))
    tickers = sorted({str(e["ticker"]) for e in entries.values() if e.get("ticker")}) or None
    metrics, info = run_gate(tickers=tickers, period=None, aggregate=True, since=since)
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    out = Path(args.out) if args.out else REPORTS_OUT / f"m9_batch_{stamp}.json"
    code = gate_report(
        metrics,
        is_aggregate=True,
        expected_period=None,
        out=out,
        extra={
            **info,
            "batch_start": manifest.get("batch_start"),
            "period": manifest.get("period"),
            "documents_prepared": sum(1 for d in docs if d.get("status") == "ready"),
            "documents_committed": sum(1 for d in docs if (d.get("db") or {}).get("committed")),
            "per_document_status": docs,
        },
    )
    print(f"Batch report: {out}")
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M9 batch: prepare filings, then report.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare", help="inspect -> index -> embed, resumable")
    p.add_argument("--priority", choices=TIERS, default="lq45")
    p.add_argument("--tickers", default=None, help="Explicit comma-separated tickers")
    p.add_argument("--limit", type=int, default=None, help="Max filings to prepare")
    p.add_argument("--period", default="2025Q4")
    p.add_argument("--kind", choices=["fs", "ar"], default="fs", help="statements or annual report")
    p.add_argument("--stage-dir", default=None, help="Copy target (default: ../m9_stage)")
    r = sub.add_parser("report", help="per-doc status + aggregate gate -> JSON")
    r.add_argument("--since", default=None, help="Window start (default: manifest batch_start)")
    r.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        return asyncio.run(prepare(args))
    return report(args)


if __name__ == "__main__":
    sys.exit(main())
