"""Evaluation script: computes router recall@k against hand-labelled gold sets."""

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
from services.mcp.server import get_engine
from services.retrieval.page_router import route_pages

CORE_MODULES = {"BALANCE_SHEET", "INCOME_STATEMENT", "CASH_FLOW"}


async def _resolve_document(
    conn: AsyncConnection,
    file_target: str | None,
    ticker_hint: str | None,
    period_hint: str | None,
) -> dict[str, Any] | None:
    """Finds the most relevant indexed document matching the target criteria."""
    if file_target:
        fname = f"%{Path(file_target).name}%"
        if period_hint:
            res = await conn.execute(
                text(
                    """
                    SELECT d.id, d.ticker, d.fiscal_period
                    FROM documents d
                    JOIN document_pages dp ON d.id = dp.doc_id
                    WHERE (d.source_url ILIKE :f OR d.minio_key ILIKE :f)
                      AND d.fiscal_period = :period
                    GROUP BY d.id, d.ticker, d.fiscal_period, d.ingested_at
                    ORDER BY d.ingested_at DESC LIMIT 1
                    """
                ),
                {"f": fname, "period": period_hint},
            )
        else:
            res = await conn.execute(
                text(
                    """
                    SELECT d.id, d.ticker, d.fiscal_period
                    FROM documents d
                    JOIN document_pages dp ON d.id = dp.doc_id
                    WHERE (d.source_url ILIKE :f OR d.minio_key ILIKE :f)
                    GROUP BY d.id, d.ticker, d.fiscal_period, d.ingested_at
                    ORDER BY d.ingested_at DESC LIMIT 1
                    """
                ),
                {"f": fname},
            )
        row = res.mappings().first()
        if row:
            return dict(row)

    if ticker_hint and period_hint:
        res = await conn.execute(
            text(
                """
                SELECT d.id, d.ticker, d.fiscal_period
                FROM documents d
                JOIN document_pages dp ON d.id = dp.doc_id
                WHERE d.ticker = :ticker AND d.fiscal_period = :period
                GROUP BY d.id, d.ticker, d.fiscal_period, d.ingested_at
                ORDER BY d.ingested_at DESC LIMIT 1
                """
            ),
            {"ticker": ticker_hint, "period": period_hint},
        )
        row = res.mappings().first()
        if row:
            return dict(row)

    if ticker_hint:
        res = await conn.execute(
            text(
                """
                SELECT d.id, d.ticker, d.fiscal_period
                FROM documents d
                JOIN document_pages dp ON d.id = dp.doc_id
                WHERE d.ticker = :ticker
                GROUP BY d.id, d.ticker, d.fiscal_period, d.ingested_at
                ORDER BY d.ingested_at DESC LIMIT 1
                """
            ),
            {"ticker": ticker_hint},
        )
        row = res.mappings().first()
        if row:
            return dict(row)

    return None


def load_gold_datasets(gold_dir: Path) -> list[tuple[str, dict[str, Any]]]:
    """Loads gold dataset YAML files synchronously."""
    gold_files: list[Path] = []
    if gold_dir.is_file():
        gold_files = [gold_dir]
    elif gold_dir.is_dir():
        gold_files = sorted(gold_dir.glob("*.yaml")) + sorted(gold_dir.glob("*.yml"))

    loaded: list[tuple[str, dict[str, Any]]] = []
    for gf in gold_files:
        with open(gf, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict):
            loaded.append((gf.name, data))
    return loaded


async def evaluate_router(gold_dir: Path, out_path: Path, top_k: int = 3) -> bool:
    """Run route_pages per module across all gold YAMLs and evaluate recall."""
    gold_datasets = load_gold_datasets(gold_dir)
    if not gold_datasets:
        print(f"No gold YAML files found in {gold_dir}")
        return False

    engine = get_engine()
    results: list[dict[str, Any]] = []

    async with engine.connect() as conn:
        for file_name, gold_data in gold_datasets:
            file_target = gold_data.get("file")
            ticker_hint = gold_data.get("ticker")
            period_hint = gold_data.get("fiscal_period")
            modules_gold = gold_data.get("modules", {})

            doc = await _resolve_document(conn, file_target, ticker_hint, period_hint)
            if not doc:
                print(f"Warning: Document for gold set {file_name} not found in DB.")
                continue

            doc_id = str(doc["id"])
            ticker = doc["ticker"]

            prof_res = await conn.execute(
                text("SELECT sector FROM issuer_profile WHERE ticker = :ticker"),
                {"ticker": ticker},
            )
            prof_row = prof_res.mappings().first()
            sector = prof_row["sector"] if prof_row and prof_row.get("sector") else "GENERIC"

            for mod_name, gold_pages_raw in modules_gold.items():
                gold_pages = sorted(
                    set(gold_pages_raw if isinstance(gold_pages_raw, list) else [gold_pages_raw])
                )
                if not gold_pages:
                    continue

                route_q = get_route_query(mod_name.upper(), sector)
                if not route_q:
                    print(f"Warning: No RouteQuery found for module {mod_name} (sector {sector})")
                    continue

                spans = await route_pages(conn, doc_id, route_q, top_k=top_k)
                returned_pages = sorted({p for s in spans for p in s.pages})

                hits = sorted(set(gold_pages) & set(returned_pages))
                recall = len(hits) / len(gold_pages) if gold_pages else 1.0

                mod_type = "core" if mod_name.upper() in CORE_MODULES else "notes"
                results.append(
                    {
                        "gold_file": file_name,
                        "ticker": ticker,
                        "doc_id": doc_id,
                        "module": mod_name.upper(),
                        "type": mod_type,
                        "gold_pages": gold_pages,
                        "returned_pages": returned_pages,
                        "hits": hits,
                        "recall": recall,
                    }
                )

    if not results:
        print("No module results could be evaluated.")
        return False

    core_results = [r for r in results if r["type"] == "core"]
    notes_results = [r for r in results if r["type"] == "notes"]

    core_mean = sum(r["recall"] for r in core_results) / len(core_results) if core_results else 0.0
    notes_mean = (
        sum(r["recall"] for r in notes_results) / len(notes_results) if notes_results else 0.0
    )
    overall_mean = sum(r["recall"] for r in results) / len(results)

    thresholds_met = (core_mean >= 0.90) and (notes_mean >= 0.80)

    # Print table
    print("\n" + "=" * 90)
    print(
        f"{'Module':<20} {'Ticker':<8} {'Type':<6} {'Gold Pages':<18} "
        f"{'Returned':<18} {'Hits':<8} {'Recall':<8}"
    )
    print("-" * 90)
    for r in results:
        gold_str = (
            str(r["gold_pages"])
            if len(str(r["gold_pages"])) <= 17
            else f"{r['gold_pages'][:3]}...+{len(r['gold_pages'])-3}"
        )
        ret_str = (
            str(r["returned_pages"])
            if len(str(r["returned_pages"])) <= 17
            else f"{r['returned_pages'][:3]}...+{len(r['returned_pages'])-3}"
        )
        hits_str = f"{len(r['hits'])}/{len(r['gold_pages'])}"
        recall_pct = f"{r['recall']*100:.1f}%"
        print(
            f"{r['module']:<20} {r['ticker']:<8} {r['type']:<6} {gold_str:<18} "
            f"{ret_str:<18} {hits_str:<8} {recall_pct:<8}"
        )
    print("=" * 90)
    print(
        f"Core Mean Recall:    {core_mean*100:.1f}% (target: >= 90.0%) -> "
        f"{'PASS' if core_mean >= 0.90 else 'FAIL'}"
    )
    print(
        f"Notes Mean Recall:   {notes_mean*100:.1f}% (target: >= 80.0%) -> "
        f"{'PASS' if notes_mean >= 0.80 else 'FAIL'}"
    )
    print(f"Overall Mean Recall: {overall_mean*100:.1f}%")
    print(f"Thresholds Met:      {thresholds_met}")
    print("=" * 90 + "\n")

    report_payload = {
        "summary": {
            "core_mean_recall": round(core_mean, 4),
            "notes_mean_recall": round(notes_mean, 4),
            "overall_mean_recall": round(overall_mean, 4),
            "total_evaluated_modules": len(results),
            "core_module_count": len(core_results),
            "notes_module_count": len(notes_results),
            "thresholds_met": thresholds_met,
        },
        "modules": results,
        "notes": "Generated by eval/router_recall.py",
    }

    _save_report(out_path, report_payload)
    print(f"Report written to {out_path}")

    return thresholds_met


def _save_report(out_path: Path, payload: dict[str, Any]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate page router recall against gold sets.")
    parser.add_argument(
        "--gold",
        type=Path,
        default=Path("eval/router_gold"),
        help="Path to gold YAML file or directory",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("eval/reports/router_recall.json"),
        help="Output JSON path",
    )
    parser.add_argument("--top-k", type=int, default=3, help="Top seeds to expand")
    args = parser.parse_args()

    success = asyncio.run(evaluate_router(args.gold, args.out, top_k=args.top_k))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
