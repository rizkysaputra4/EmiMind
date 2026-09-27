"""CLI script to backfill dense page embeddings for indexed documents."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text

from services.ingest.tasks.embed_pages import embed_pages_task
from services.ingest.tasks.index_pages import index_pages_task
from services.mcp.server import get_engine, inspect_document
from services.narrative.embedder import Embedder
from services.shared.config import get_settings
from services.shared.logging import get_logger

log = get_logger("scripts.backfill_page_embeddings")

LIGHTHOUSE_TICKERS = ["BMRI", "LSIP"]
LQ45_TICKERS = [
    "ACES", "ADMR", "ADRO", "AKRA", "AMMN", "AMRT", "ANTM", "ARTO", "ASII", "BBCA",
    "BBNI", "BBRI", "BBTN", "BFIN", "BMRI", "BRIS", "BRPT", "BUKA", "CPIN", "EMTK",
    "ESSA", "EXCL", "GGRM", "GOTO", "HRUM", "ICBP", "INCO", "INDF", "INKP", "INTP",
    "ITMG", "KLBF", "MAPI", "MBMA", "MDKA", "MEDC", "MIKA", "PGAS", "PGEO", "PTBA",
    "SMGR", "SRTG", "TLKM", "TOWR", "UNTR", "UNVR",
]


async def _ensure_indexed_document_for_ticker(engine: Any, ticker: str) -> str | None:
    """If no indexed document exists for ticker, look for report and index it."""
    reports_base = os.getenv("EMI_REPORTS_DIR", "../EmiMind-Extraction/incoming_reports")
    candidates = [
        Path(f"incoming_reports/{ticker}"),
        Path("incoming_reports"),
        Path(f"{reports_base}/{ticker}/processed"),
        Path(f"{reports_base}/{ticker}"),
    ]
    ticker_synonyms = {
        "BMRI": ["bmri", "mandiri"],
        "LSIP": ["lsip", "london sumatra"],
    }
    match_terms = ticker_synonyms.get(ticker.upper(), [ticker.lower()])

    for folder in candidates:
        if folder.is_dir():
            for p in sorted(folder.glob("*.pdf"), key=lambda f: f.stat().st_size):
                if p.stat().st_size < 50_000:
                    continue
                name_lower = p.name.lower()
                if any(term in name_lower for term in match_terms):
                    print(f"Auto-inspecting and indexing filing for {ticker}: {p.name}...")
                    insp_res = await inspect_document(str(p), ticker=ticker)
                    doc_id = insp_res.doc_id
                    if doc_id:
                        await index_pages_task({"db_pool": engine}, doc_id)
                        return doc_id
    return None


async def _process_backfill_docs(ctx: dict[str, Any], docs: list[dict[str, Any]], batch_size: int) -> None:
    """Processes document list through embedding task and logs summary."""
    print(f"Starting page embedding backfill for {len(docs)} document(s)...")

    total_pages_embedded = 0
    total_time_elapsed = 0.0

    for doc in docs:
        d_id = str(doc["id"])
        ticker = doc["ticker"]
        period = doc["fiscal_period"]
        pending = doc["null_page_count"]

        print(f"\nProcessing {ticker} ({period}) [doc_id={d_id}]: {pending} pages to embed...")
        result = await embed_pages_task(ctx, d_id, batch_size=batch_size)

        embedded = result.get("embedded_count", 0)
        elapsed = result.get("elapsed_s", 0.0)
        rate = result.get("pages_per_sec", 0.0)

        total_pages_embedded += embedded
        total_time_elapsed += elapsed

        print(f"Completed {ticker} ({period}): {embedded} pages embedded in {elapsed:.2f}s ({rate:.1f} pages/sec)")

    overall_rate = total_pages_embedded / total_time_elapsed if total_time_elapsed > 0 else 0.0
    print("\n=======================================================")
    print("Page Embedding Backfill Summary:")
    print(f"  Documents processed: {len(docs)}")
    print(f"  Total pages embedded: {total_pages_embedded}")
    print(f"  Total elapsed time: {total_time_elapsed:.2f}s")
    print(f"  Overall rate: {overall_rate:.1f} pages/sec")
    print("=======================================================")


def _resolve_target_tickers(args: argparse.Namespace) -> list[str]:
    """Determines target tickers from CLI arguments."""
    if args.tickers:
        return [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    if args.priority == "lighthouse":
        return LIGHTHOUSE_TICKERS
    if args.priority == "lq45":
        return LQ45_TICKERS
    return []


async def _handle_single_ticker_fallback(
    engine: Any,
    ticker: str,
    query: str,
    params: dict[str, Any],
) -> list[dict[str, Any]] | None:
    """Handles auto-indexing or verifying existing documents when no pending pages are found."""
    async with engine.connect() as conn:
        docs_info = (
            await conn.execute(
                text(
                    """
                    SELECT d.id, d.ticker, d.fiscal_period, d.doc_type,
                           count(p.id) AS page_count,
                           count(p.embedding) AS embedded_count
                    FROM documents d
                    LEFT JOIN document_pages p ON p.doc_id = d.id
                    WHERE d.ticker = :t
                    GROUP BY d.id, d.ticker, d.fiscal_period, d.doc_type
                    """
                ),
                {"t": ticker},
            )
        ).mappings().all()

    unindexed_docs = [d for d in docs_info if d["page_count"] == 0]
    if unindexed_docs:
        for ud in unindexed_docs:
            d_id = str(ud["id"])
            print(f"Document {ticker} [doc_id={d_id}] has 0 indexed pages. Attempting to index pages...")
            try:
                await index_pages_task({"db_pool": engine}, d_id)
            except Exception as exc:
                print(f"Warning: Failed to index pages for doc_id={d_id}: {exc}")

        async with engine.connect() as conn:
            res = await conn.execute(text(query), params)
            return [dict(r) for r in res.mappings().all()]

    if not docs_info:
        doc_id = await _ensure_indexed_document_for_ticker(engine, ticker)
        if doc_id:
            async with engine.connect() as conn:
                res = await conn.execute(
                    text(
                        """
                        SELECT d.id, d.ticker, d.fiscal_period, d.doc_type, count(p.id) AS null_page_count
                        FROM documents d
                        JOIN document_pages p ON p.doc_id = d.id
                        WHERE d.id = :id AND p.embedding IS NULL
                        GROUP BY d.id, d.ticker, d.fiscal_period, d.doc_type
                        """
                    ),
                    {"id": doc_id},
                )
                return [dict(r) for r in res.mappings().all()]

    return None


async def main_async() -> int:
    parser = argparse.ArgumentParser(description="Backfill dense page embeddings for document pages.")
    parser.add_argument("--tickers", type=str, default="", help="Comma-separated ticker symbols (e.g. BMRI,LSIP)")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of documents to backfill")
    parser.add_argument(
        "--priority",
        choices=["lighthouse", "lq45", "all"],
        default="all",
        help="Priority group to filter (lighthouse, lq45, all)",
    )
    parser.add_argument("--batch-size", type=int, default=32, help="Embedding batch size (default: 32)")

    args = parser.parse_args()
    target_tickers = _resolve_target_tickers(args)

    engine = get_engine()  # type: ignore[no-untyped-call]
    settings = get_settings()
    embedder = Embedder()
    ctx = {"db_pool": engine, "settings": settings, "embedder": embedder}

    query = """
        SELECT d.id, d.ticker, d.fiscal_period, d.doc_type, count(p.id) AS null_page_count
        FROM documents d
        JOIN document_pages p ON p.doc_id = d.id
        WHERE p.embedding IS NULL
    """
    params: dict[str, Any] = {}
    if target_tickers:
        query += " AND d.ticker = ANY(:tickers)"
        params["tickers"] = target_tickers
    query += " GROUP BY d.id, d.ticker, d.fiscal_period, d.doc_type ORDER BY d.ticker ASC"

    async with engine.connect() as conn:
        res = await conn.execute(text(query), params)
        raw_docs = [dict(r) for r in res.mappings().all()]

    if not raw_docs and len(target_tickers) == 1:
        ticker = target_tickers[0]
        fallback_docs = await _handle_single_ticker_fallback(engine, ticker, query, params)
        if fallback_docs is not None:
            raw_docs = fallback_docs
        else:
            print(f"All document pages for {ticker} are already embedded.")
            return 0

    if not raw_docs:
        print("No documents found requiring page embedding.")
        return 0

    if args.limit:
        raw_docs = raw_docs[: args.limit]

    await _process_backfill_docs(ctx, raw_docs, args.batch_size)
    return 0


def main() -> None:
    sys.exit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
