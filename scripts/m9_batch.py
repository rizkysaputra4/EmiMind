"""Prioritized Batch Rollout Script (M9.6.3).

Executes batch deep extraction over in-scope tickers in priority order (LQ45 -> all).
Evaluates the gate in --aggregate mode after each batch of 20 documents, automatically
pausing if any quality threshold regresses.

Usage:
    uv run python scripts/m9_batch.py --priority lq45 --limit 20
    uv run python scripts/m9_batch.py --priority all --limit 50 --batch-size 20
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
from sqlalchemy import text

from eval.deep_extraction_gate import (
    _dsn,
    collect_metrics_for_ticker,
    evaluate_gate,
    load_baseline,
    load_boilerplate_phrases,
    load_sector_depth_minimums,
    print_results_table,
)
from services.ingest.tasks.embed_pages import embed_pages_task
from services.ingest.tasks.index_pages import index_pages_task
from services.mcp.server import get_engine, inspect_document
from services.shared.logging import get_logger

log = get_logger("scripts.m9_batch")

LQ45_TICKERS = [
    "ACES", "ADMR", "ADRO", "AKRA", "AMMN", "AMRT", "ANTM", "ARTO", "ASII", "BBCA",
    "BBNI", "BBRI", "BBTN", "BFIN", "BMRI", "BRIS", "BRPT", "BUKA", "CPIN", "EMTK",
    "ESSA", "EXCL", "GGRM", "GOTO", "HRUM", "ICBP", "INCO", "INDF", "INKP", "INTP",
    "ITMG", "KLBF", "MAPI", "MBMA", "MDKA", "MEDC", "MIKA", "PGAS", "PGEO", "PTBA",
    "SMGR", "SRTG", "TLKM", "TOWR", "UNTR", "UNVR",
]


async def get_target_tickers(priority: str, engine: Any) -> list[str]:
    """Retrieve ordered target tickers based on priority."""
    if priority == "lq45":
        return list(LQ45_TICKERS)

    # For 'all', get all tickers in issuer_profile, placing LQ45 first
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT ticker FROM issuer_profile ORDER BY ticker;"))
        all_tickers = [row[0] for row in res.fetchall()]

    lq45_set = set(LQ45_TICKERS)
    lq45_ordered = [t for t in LQ45_TICKERS if t in set(all_tickers)]
    others_ordered = [t for t in all_tickers if t not in lq45_set]
    return lq45_ordered + others_ordered


def find_annual_filing_for_ticker(ticker: str, target_year: str = "2025") -> Path | None:
    """Scans incoming folders for the best matching annual report or financial statement PDF."""
    reports_base = os.getenv("EMI_REPORTS_DIR", "../EmiMind-Extraction/incoming_reports")
    t_lower = ticker.lower()
    candidate_folders = [
        Path(f"incoming_reports/{ticker}"),
        Path(f"{reports_base}/{ticker}/processed"),
        Path(f"{reports_base}/{ticker}"),
        Path("incoming_reports/processed"),
        Path("incoming_reports"),
    ]

    for folder in candidate_folders:
        if not folder.is_dir():
            continue
        pdf_candidates = list(folder.glob("*.pdf"))
        matching_pdfs = [
            p for p in pdf_candidates
            if (t_lower in p.name.lower() or t_lower in [part.lower() for part in p.parts])
        ]
        sorted_pdfs = sorted(
            matching_pdfs,
            key=lambda p: (
                target_year in p.name,
                "AUDIT" in p.name.upper() or "TAHUNAN" in p.name.upper(),
                "ANNUAL" in p.name.upper(),
                p.stat().st_size,
            ),
            reverse=True,
        )
        for p in sorted_pdfs:
            if p.stat().st_size > 50_000 and target_year in p.name:
                return p

    return None


async def is_already_committed(engine: Any, ticker: str, fiscal_period: str = "2025Q4") -> bool:
    """Checks if a document for this ticker and period has already reached COMMITTED status."""
    async with engine.connect() as conn:
        res = await conn.execute(
            text(
                """
                SELECT count(*)
                FROM documents d
                JOIN document_processing_log l ON l.doc_id = d.id
                WHERE d.ticker = :ticker AND d.fiscal_period = :period AND l.action = 'COMMITTED';
                """
            ),
            {"ticker": ticker, "period": fiscal_period},
        )
        count = res.scalar() or 0
        return count > 0


async def process_document_pipeline(
    engine: Any,
    ticker: str,
    pdf_path: Path,
    period: str = "2025Q4",
) -> dict[str, Any]:
    """Runs inspect -> index -> embed pipeline for a filing."""
    log.info("Processing document pipeline", ticker=ticker, path=str(pdf_path))

    # 1. Inspect
    inspect_res = await inspect_document(str(pdf_path), ticker=ticker)
    doc_id = inspect_res.doc_id
    if not doc_id:
        return {"status": "SKIPPED", "ticker": ticker, "reason": inspect_res.message}

    # 2. Index pages if not already indexed
    async with engine.connect() as conn:
        res = await conn.execute(
            text("SELECT count(*) FROM document_pages WHERE doc_id = :doc_id"),
            {"doc_id": doc_id},
        )
        indexed_pages = res.scalar() or 0

    if indexed_pages == 0:
        log.info("Indexing pages", ticker=ticker, doc_id=doc_id)
        await index_pages_task({"db_pool": engine}, doc_id)

    # 3. Embed pages if embeddings missing
    async with engine.connect() as conn:
        res = await conn.execute(
            text("SELECT count(*) FROM document_pages WHERE doc_id = :doc_id AND embedding IS NULL"),
            {"doc_id": doc_id},
        )
        unembedded_pages = res.scalar() or 0

    if unembedded_pages > 0:
        log.info("Embedding pages", ticker=ticker, doc_id=doc_id, count=unembedded_pages)
        await embed_pages_task({"db_pool": engine, "batch_size": 32}, doc_id)

    return {
        "status": "READY_OR_COMMITTED",
        "ticker": ticker,
        "doc_id": doc_id,
        "inspect_status": inspect_res.status,
    }


def run_aggregate_gate(
    tickers: list[str],
    period: str = "2025Q4",
    sector_depths: dict[str, int] | None = None,
    baseline_data: dict[str, Any] | None = None,
    boilerplate_phrases: list[str] | None = None,
) -> tuple[bool, dict[str, Any]]:
    """Runs acceptance gate in aggregate mode over processed tickers."""
    metrics_list: list[dict[str, Any]] = []
    with psycopg.connect(_dsn()) as conn:
        for ticker in tickers:
            m = collect_metrics_for_ticker(
                conn=conn,
                ticker=ticker,
                period=period,
                sector_depths=sector_depths,
                baseline_data=baseline_data,
                boilerplate_phrases=boilerplate_phrases,
                router_recall_data={},
            )
            metrics_list.append(m)

    all_passed, results, summary = evaluate_gate(metrics_list, is_aggregate=True)
    print_results_table(results, summary)
    return all_passed, {
        "summary": summary,
        "results": [r.__dict__ for r in results],
        "metrics": metrics_list,
    }


async def run_batch_rollout(  # noqa: PLR0915
    priority: str = "lq45",
    limit: int | None = None,
    batch_size: int = 20,
    resumable: bool = True,
    period: str = "2025Q4",
) -> None:
    """Executes prioritized batch extraction and checks the gate periodically."""
    engine = get_engine()
    batch_start = datetime.now(UTC)
    date_str = batch_start.strftime("%Y%m%d_%H%M%S")
    report_path = Path(f"eval/reports/m9_batch_{date_str}.json")

    sector_depths = load_sector_depth_minimums()
    baseline_data = load_baseline()
    boilerplate_phrases = load_boilerplate_phrases()

    target_tickers = await get_target_tickers(priority, engine)
    log.info(
        "Starting batch extraction run",
        priority=priority,
        tickers_count=len(target_tickers),
        limit=limit,
        batch_size=batch_size,
    )

    processed_tickers: list[str] = []
    skipped_tickers: list[str] = []
    errors: list[dict[str, Any]] = []

    for _idx, ticker in enumerate(target_tickers):
        if limit and len(processed_tickers) >= limit:
            log.info("Reached processing limit", limit=limit)
            break

        if resumable and await is_already_committed(engine, ticker, period):
            log.info("Ticker already committed, skipping (resumable)", ticker=ticker)
            skipped_tickers.append(ticker)
            processed_tickers.append(ticker)
            continue

        pdf_path = find_annual_filing_for_ticker(ticker)
        if not pdf_path:
            log.warning("No annual report PDF found for ticker", ticker=ticker)
            errors.append({"ticker": ticker, "error": "No matching PDF found"})
            continue

        try:
            res = await process_document_pipeline(engine, ticker, pdf_path, period=period)
            processed_tickers.append(ticker)
            log.info("Completed document pipeline", ticker=ticker, result=res)
        except Exception as exc:
            log.error("Pipeline failed for ticker", ticker=ticker, error=str(exc))
            errors.append({"ticker": ticker, "error": str(exc)})

        # Checkpoint evaluation after every batch_size tickers
        if len(processed_tickers) > 0 and len(processed_tickers) % batch_size == 0:
            log.info("Running aggregate gate checkpoint", processed_count=len(processed_tickers))
            batch_slice = processed_tickers[-batch_size:]
            all_passed, gate_out = run_aggregate_gate(
                batch_slice,
                period=period,
                sector_depths=sector_depths,
                baseline_data=baseline_data,
                boilerplate_phrases=boilerplate_phrases,
            )
            if not all_passed:
                log.error("Gate threshold failed during checkpoint! Pausing batch.", failed_slice=batch_slice)
                # Write intermediate failure report
                report_path.parent.mkdir(parents=True, exist_ok=True)
                with open(report_path, "w", encoding="utf-8") as f:  # noqa: ASYNC230
                    json.dump(
                        {
                            "status": "FAILED_AT_CHECKPOINT",
                            "checkpoint_at": len(processed_tickers),
                            "batch_start": batch_start.isoformat(),
                            "gate_evaluation": gate_out,
                            "errors": errors,
                        },
                        f,
                        indent=2,
                        default=str,
                    )
                sys.exit(1)

    # Final aggregate gate evaluation on all committed tickers in this run
    committed_in_run = [t for t in processed_tickers if t not in [e["ticker"] for e in errors]]
    final_gate_out: dict[str, Any] = {}
    all_passed = True
    if committed_in_run:
        all_passed, final_gate_out = run_aggregate_gate(
            committed_in_run,
            period=period,
            sector_depths=sector_depths,
            baseline_data=baseline_data,
            boilerplate_phrases=boilerplate_phrases,
        )

    # Write final report
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_data = {
        "status": "COMPLETED" if all_passed else "FAILED",
        "batch_start": batch_start.isoformat(),
        "batch_end": datetime.now(UTC).isoformat(),
        "priority": priority,
        "processed_count": len(processed_tickers),
        "processed_tickers": processed_tickers,
        "skipped_tickers": skipped_tickers,
        "errors": errors,
        "gate_evaluation": final_gate_out,
    }
    with open(report_path, "w", encoding="utf-8") as f:  # noqa: ASYNC230
        json.dump(report_data, f, indent=2, default=str)
    log.info("Batch run report saved", report_path=str(report_path))

    if not all_passed:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prioritized batch rollout for deep extraction.")
    parser.add_argument("--priority", choices=["lq45", "all"], default="lq45", help="Target ticker priority")
    parser.add_argument("--limit", type=int, default=None, help="Max documents to process")
    parser.add_argument("--batch-size", type=int, default=20, help="Checkpoint batch size")
    parser.add_argument("--period", type=str, default="2025Q4", help="Fiscal period (default: 2025Q4)")
    parser.add_argument("--no-resumable", action="store_true", help="Disable skipping already committed docs")

    args = parser.parse_args()

    asyncio.run(
        run_batch_rollout(
            priority=args.priority,
            limit=args.limit,
            batch_size=args.batch_size,
            resumable=not args.no_resumable,
            period=args.period,
        )
    )


if __name__ == "__main__":
    main()
