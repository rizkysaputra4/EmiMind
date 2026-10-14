"""Router recall/precision eval against hand-labelled gold sets (M9.3.4).

Gold YAML format (one file per document):

    file: "BMRI_2025_AUDIT_RDF_LK PT Bank Mandiri-Desember 2025.pdf"
    sha256: "cdbe64..."            # preferred: matched against documents.doc_hash
    ticker: "BMRI"
    fiscal_period: "2025Q4"
    modules:
      BALANCE_SHEET: [22, 23]      # physical 1-based page indexes

Per module: recall = |gold & returned| / |gold|, precision = |gold & returned| / |returned|,
plus the number of pages returned. Capped recall = |gold & returned| / min(|gold|, budget),
where budget is the module's max_pages: what the router could reach within its page budget
when the gold note is longer. It is reported next to recall, never used for the thresholds. Thresholds: mean recall >= 0.90 (core statements) and
>= 0.80 (notes), mean precision >= 0.40. A gold document that is not indexed, or a module with
no route query, is a FAIL; `notes` in the report lists every real miss.

Usage:
    uv run python eval/router_recall.py --gold eval/router_gold/heldout/ \
        --out eval/reports/router_recall_heldout.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from services.mcp.contracts import get_route_query
from services.mcp.services.common import get_engine
from services.retrieval.page_router import route_pages

CORE_MODULES = {"BALANCE_SHEET", "INCOME_STATEMENT", "CASH_FLOW"}
RECALL_CORE_MIN = 0.90
RECALL_NOTES_MIN = 0.80
PRECISION_MIN = 0.40

_DOC_BY_HASH = """
SELECT d.id, d.ticker, d.fiscal_period, d.doc_hash,
       (SELECT count(*) FROM document_pages dp WHERE dp.doc_id = d.id) AS indexed_pages
FROM documents d WHERE d.doc_hash = :sha
ORDER BY d.ingested_at DESC LIMIT 1
"""
_DOC_BY_NAME = """
SELECT d.id, d.ticker, d.fiscal_period, d.doc_hash,
       (SELECT count(*) FROM document_pages dp WHERE dp.doc_id = d.id) AS indexed_pages
FROM documents d
WHERE (d.source_url ILIKE :f OR d.minio_key ILIKE :f)
  AND (CAST(:period AS text) IS NULL OR d.fiscal_period = :period)
ORDER BY d.ingested_at DESC LIMIT 1
"""
_DOC_BY_TICKER_PERIOD = """
SELECT d.id, d.ticker, d.fiscal_period, d.doc_hash,
       (SELECT count(*) FROM document_pages dp WHERE dp.doc_id = d.id) AS indexed_pages
FROM documents d WHERE d.ticker = :ticker AND d.fiscal_period = :period
ORDER BY d.ingested_at DESC LIMIT 1
"""


def load_gold_datasets(gold: Path) -> list[tuple[str, dict[str, Any]]]:
    files = [gold] if gold.is_file() else sorted([*gold.glob("*.yaml"), *gold.glob("*.yml")])
    loaded: list[tuple[str, dict[str, Any]]] = []
    for gf in files:
        data = yaml.safe_load(gf.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            loaded.append((gf.name, data))
    return loaded


def gold_pages(raw: Any) -> list[int]:
    values = raw if isinstance(raw, list) else [raw]
    return sorted({int(v) for v in values if v is not None})


def score_module(gold: list[int], returned: list[int], budget: int | None = None) -> dict[str, Any]:
    g, r = set(gold), set(returned)
    hits = sorted(g & r)
    reachable = min(len(g), budget) if budget else len(g)
    return {
        "gold_pages": sorted(g),
        "returned_pages": sorted(r),
        "hits": hits,
        "missed": sorted(g - r),
        "pages_returned": len(r),
        "recall": len(hits) / len(g) if g else 0.0,
        "capped_recall": len(hits) / reachable if reachable else 0.0,
        "precision": len(hits) / len(r) if r else 0.0,
    }


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def summarize(results: list[dict[str, Any]], failures: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregates module scores; thresholds_met is False on any failure or missing input."""
    core = [r for r in results if r["type"] == "core"]
    notes = [r for r in results if r["type"] == "notes"]
    core_recall = _mean([r["recall"] for r in core])
    notes_recall = _mean([r["recall"] for r in notes])
    notes_capped = _mean([r.get("capped_recall", r["recall"]) for r in notes])
    precision = _mean([r["precision"] for r in results])
    pages_per_module = _mean([float(r["pages_returned"]) for r in results])
    reasons: list[str] = []
    if failures:
        reasons.append(f"{len(failures)} gold document/module(s) could not be evaluated")
    if not results:
        reasons.append("no module evaluated")
    if core and (core_recall or 0.0) < RECALL_CORE_MIN:
        reasons.append(f"core recall {core_recall:.3f} < {RECALL_CORE_MIN}")
    if notes and (notes_recall or 0.0) < RECALL_NOTES_MIN:
        reasons.append(f"notes recall {notes_recall:.3f} < {RECALL_NOTES_MIN}")
    if results and (precision or 0.0) < PRECISION_MIN:
        reasons.append(f"precision {precision:.3f} < {PRECISION_MIN}")

    per_ticker: dict[str, dict[str, Any]] = {}
    for tkr in sorted({r["ticker"] for r in results}):
        rs = [r for r in results if r["ticker"] == tkr]
        per_ticker[tkr] = {
            "core_mean_recall": _mean([r["recall"] for r in rs if r["type"] == "core"]),
            "notes_mean_recall": _mean([r["recall"] for r in rs if r["type"] == "notes"]),
            "mean_precision": _mean([r["precision"] for r in rs]),
            "mean_pages_per_module": _mean([float(r["pages_returned"]) for r in rs]),
            "modules": len(rs),
        }

    def rnd(x: float | None) -> float | None:
        return None if x is None else round(x, 4)

    return {
        "core_mean_recall": rnd(core_recall),
        "notes_mean_recall": rnd(notes_recall),
        "notes_mean_capped_recall": rnd(notes_capped),
        "mean_precision": rnd(precision),
        "mean_pages_per_module": rnd(pages_per_module),
        "total_evaluated_modules": len(results),
        "core_module_count": len(core),
        "notes_module_count": len(notes),
        "failures": len(failures),
        "thresholds": {
            "core_recall": RECALL_CORE_MIN,
            "notes_recall": RECALL_NOTES_MIN,
            "precision": PRECISION_MIN,
        },
        "thresholds_met": not reasons,
        "fail_reasons": reasons,
        "per_ticker": per_ticker,
    }


def miss_notes(results: list[dict[str, Any]], failures: list[dict[str, Any]]) -> list[str]:
    notes = [f"FAIL {f['gold_file']}: {f['reason']}" for f in failures]
    for r in results:
        if r["missed"]:
            notes.append(
                f"{r['ticker']} {r['module']}: missed gold pages {r['missed']} "
                f"(returned {r['returned_pages']})"
            )
        min_recall = RECALL_CORE_MIN if r["type"] == "core" else RECALL_NOTES_MIN
        if r["recall"] < min_recall or r["precision"] < PRECISION_MIN:
            notes.append(
                f"{r['ticker']} {r['module']}: recall {r['recall']:.2f}, precision "
                f"{r['precision']:.2f} ({r['pages_returned']} pages for {len(r['gold_pages'])} gold)"
            )
    return notes


async def resolve_document(conn: AsyncConnection, gold: dict[str, Any]) -> dict[str, Any] | None:
    """sha256 first (exact), then file name, then ticker + fiscal period."""
    sha = gold.get("sha256")
    period = gold.get("fiscal_period")
    if sha:
        row = (await conn.execute(text(_DOC_BY_HASH), {"sha": sha})).mappings().first()
        if row:
            return dict(row)
    if gold.get("file"):
        params = {"f": f"%{Path(str(gold['file'])).name}%", "period": period}
        row = (await conn.execute(text(_DOC_BY_NAME), params)).mappings().first()
        if row:
            return dict(row)
    if not sha and gold.get("ticker") and period:
        params = {"ticker": gold["ticker"], "period": period}
        row = (await conn.execute(text(_DOC_BY_TICKER_PERIOD), params)).mappings().first()
        if row:
            return dict(row)
    return None


async def evaluate_router(gold_dir: Path, top_k: int = 3) -> dict[str, Any]:
    """Routes every gold module and returns the full report payload."""
    gold_sets = load_gold_datasets(gold_dir)
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    if not gold_sets:
        failures.append({"gold_file": str(gold_dir), "reason": "no gold YAML files found"})

    engine = get_engine()
    try:
        async with engine.connect() as conn:
            for file_name, gold in gold_sets:
                doc = await resolve_document(conn, gold)
                if not doc or int(doc.get("indexed_pages") or 0) == 0:
                    why = (
                        "not in documents" if not doc else f"doc {doc['id']} has no document_pages"
                    )
                    failures.append(
                        {"gold_file": file_name, "file": gold.get("file"),
                         "sha256": gold.get("sha256"), "reason": f"gold document {why}"}
                    )  # fmt: skip
                    continue
                if gold.get("sha256") and doc.get("doc_hash") != gold["sha256"]:
                    failures.append(
                        {"gold_file": file_name, "reason": "matched by name but sha256 differs"}
                    )
                    continue
                doc_id, ticker = str(doc["id"]), str(doc["ticker"])
                prof = (
                    (
                        await conn.execute(
                            text("SELECT sector FROM issuer_profile WHERE ticker = :t"),
                            {"t": ticker},
                        )
                    )
                    .mappings()
                    .first()
                )
                sector = str(prof["sector"]) if prof and prof.get("sector") else "GENERIC"

                for mod_name, raw_pages in (gold.get("modules") or {}).items():
                    module = str(mod_name).upper()
                    pages = gold_pages(raw_pages)
                    if not pages:
                        continue
                    route_q = get_route_query(module, sector)
                    if not route_q:
                        failures.append(
                            {"gold_file": file_name, "module": module,
                             "reason": f"no route query for module {module} (sector {sector})"}
                        )  # fmt: skip
                        continue
                    spans = await route_pages(conn, doc_id, route_q, top_k=top_k)
                    returned = sorted({p for s in spans for p in s.pages})
                    results.append(
                        {"gold_file": file_name, "ticker": ticker, "doc_id": doc_id,
                         "module": module, "type": "core" if module in CORE_MODULES else "notes",
                         **score_module(pages, returned, route_q.max_pages)}
                    )  # fmt: skip
    finally:
        await engine.dispose()

    summary = summarize(results, failures)
    return {
        "summary": summary,
        "modules": results,
        "failures": failures,
        "notes": miss_notes(results, failures),
    }


def print_table(
    results: list[dict[str, Any]], failures: list[dict[str, Any]], summary: dict[str, Any]
) -> None:
    def short(pages: list[int]) -> str:
        s = str(pages)
        return s if len(s) <= 22 else f"{pages[:3]}..+{len(pages) - 3}"

    print("\n" + "=" * 112)
    print(f"{'Module':<24} {'Ticker':<6} {'Type':<5} {'Gold':<24} {'Returned':<24} "
          f"{'Recall':>7} {'Prec':>6} {'Pages':>5}")  # fmt: skip
    print("-" * 112)
    for r in results:
        print(
            f"{r['module']:<24} {r['ticker']:<6} {r['type']:<5} {short(r['gold_pages']):<24} "
            f"{short(r['returned_pages']):<24} {r['recall']:>7.2f} {r['precision']:>6.2f} "
            f"{r['pages_returned']:>5}"
        )
    for f in failures:
        print(f"FAIL {f['gold_file']} {f.get('module', '')}: {f['reason']}")
    print("=" * 112)

    def pct(x: float | None) -> str:
        return "n/a" if x is None else f"{x * 100:.1f}%"

    print(f"Core mean recall:   {pct(summary['core_mean_recall'])} (>= {RECALL_CORE_MIN:.0%})")
    print(f"Notes mean recall:  {pct(summary['notes_mean_recall'])} (>= {RECALL_NOTES_MIN:.0%})")
    capped = pct(summary.get("notes_mean_capped_recall"))
    print(f"Notes capped recall: {capped} (within each module's page budget; informational)")
    print(f"Mean precision:     {pct(summary['mean_precision'])} (>= {PRECISION_MIN:.0%})")
    print(f"Mean pages/module:  {summary['mean_pages_per_module']}")
    print(f"Thresholds met:     {summary['thresholds_met']} {summary['fail_reasons'] or ''}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate page router recall/precision.")
    parser.add_argument("--gold", type=Path, default=Path("eval/router_gold/heldout"))
    parser.add_argument("--out", type=Path, default=Path("eval/reports/router_recall.json"))
    parser.add_argument("--top-k", type=int, default=3, help="Top seeds to expand")
    args = parser.parse_args(argv)
    payload = asyncio.run(evaluate_router(args.gold, top_k=args.top_k))
    print_table(payload["modules"], payload["failures"], payload["summary"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Report written to {args.out}")
    return 0 if payload["summary"]["thresholds_met"] else 1


if __name__ == "__main__":
    sys.exit(main())
