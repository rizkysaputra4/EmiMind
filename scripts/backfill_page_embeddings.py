"""CLI: (re-)embed document pages whose vector is missing or from another model.

A page is stale when `embedding IS NULL` or `embedding_model` differs from the current
embedder's model id (NULL = legacy md5 hash vectors from M9). Documents are processed in
priority order: lighthouse (BMRI, LSIP) -> LQ45 members -> everything else.

    uv run python scripts/backfill_page_embeddings.py --priority all
    uv run python scripts/backfill_page_embeddings.py --tickers BMRI --limit 1
    uv run python scripts/backfill_page_embeddings.py --dry-run

It never inspects or indexes files; documents without `document_pages` rows are listed so
they can be indexed first (`index_pages_task`).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from sqlalchemy import text

from scripts.seed_idx_tickers import IDX_TICKERS
from services.ingest.tasks.embed_pages import embed_pages_task
from services.narrative.embedder import Embedder
from services.shared.config import get_settings
from services.shared.db import create_pool
from services.shared.logging import get_logger

log = get_logger("scripts.backfill_page_embeddings")

LIGHTHOUSE_TICKERS = ("BMRI", "LSIP")
LQ45_TICKERS = frozenset(t for t, *_rest, index in IDX_TICKERS if index == "LQ45")


def priority_rank(ticker: str) -> int:
    """0 = lighthouse, 1 = LQ45, 2 = rest."""
    t = ticker.upper()
    if t in LIGHTHOUSE_TICKERS:
        return 0
    if t in LQ45_TICKERS:
        return 1
    return 2


def order_documents(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Lighthouse -> LQ45 -> rest; within a group by ticker, newest period first."""
    by_period = sorted(docs, key=lambda d: str(d.get("fiscal_period") or ""), reverse=True)
    return sorted(by_period, key=lambda d: (priority_rank(str(d["ticker"])), str(d["ticker"])))


def select_by_priority(docs: list[dict[str, Any]], priority: str) -> list[dict[str, Any]]:
    if priority == "lighthouse":
        return [d for d in docs if priority_rank(str(d["ticker"])) == 0]
    if priority == "lq45":
        return [d for d in docs if priority_rank(str(d["ticker"])) <= 1]
    return docs


_STALE_DOCS_SQL = """
    SELECT d.id, d.ticker, d.fiscal_period, d.doc_type,
           count(p.id) AS page_count,
           count(p.id) FILTER (
               WHERE p.embedding IS NULL OR p.embedding_model IS DISTINCT FROM :model
           ) AS stale_count
    FROM documents d
    LEFT JOIN document_pages p ON p.doc_id = d.id
    {where}
    GROUP BY d.id, d.ticker, d.fiscal_period, d.doc_type
"""


async def _find_documents(
    engine: Any, model_id: str, tickers: list[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(documents with stale pages, documents with no indexed pages)."""
    params: dict[str, Any] = {"model": model_id}
    where = ""
    if tickers:
        where = "WHERE d.ticker = ANY(:tickers)"
        params["tickers"] = tickers
    async with engine.connect() as conn:
        res = await conn.execute(text(_STALE_DOCS_SQL.format(where=where)), params)
        rows = [dict(r) for r in res.mappings().all()]
    stale = [r for r in rows if r["page_count"] > 0 and r["stale_count"] > 0]
    unindexed = [r for r in rows if r["page_count"] == 0]
    return stale, unindexed


async def main_async(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tickers", default="", help="Comma-separated tickers (e.g. BMRI,LSIP)")
    parser.add_argument("--limit", type=int, default=None, help="Max documents to process")
    parser.add_argument(
        "--priority",
        choices=["lighthouse", "lq45", "all"],
        default="all",
        help="lighthouse = BMRI,LSIP; lq45 = lighthouse + LQ45; all = everything (in that order)",
    )
    parser.add_argument("--batch-size", type=int, default=None, help="Pages per batch/commit")
    parser.add_argument("--dry-run", action="store_true", help="List the work, embed nothing")
    args = parser.parse_args(argv)

    settings = get_settings()
    engine = create_pool(settings.postgres_dsn)
    embedder = Embedder()
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]

    stale, unindexed = await _find_documents(engine, embedder.model_id, tickers)
    docs = select_by_priority(order_documents(stale), args.priority)
    if args.limit:
        docs = docs[: args.limit]

    for u in unindexed:
        print(f"NOT INDEXED (run index_pages_task first): {u['ticker']} {u['fiscal_period']} "
              f"doc_id={u['id']}")
    if not docs:
        print(f"No documents with pages missing '{embedder.model_id}' vectors.")
        await engine.dispose()
        return 0

    total_pages = sum(int(d["stale_count"]) for d in docs)
    print(f"Model {embedder.model_id} on {embedder.device}: {len(docs)} document(s), "
          f"{total_pages} stale page(s).")
    if args.dry_run:
        for d in docs:
            print(f"  [{priority_rank(str(d['ticker']))}] {d['ticker']} {d['fiscal_period']} "
                  f"doc_id={d['id']} stale={d['stale_count']}/{d['page_count']}")
        await engine.dispose()
        return 0

    ctx = {"db_pool": engine, "settings": settings, "embedder": embedder}
    embedded = 0
    elapsed = 0.0
    failures = 0
    for d in docs:
        d_id = str(d["id"])
        print(f"\n{d['ticker']} {d['fiscal_period']} doc_id={d_id}: "
              f"{d['stale_count']}/{d['page_count']} pages to embed...")
        try:
            result = await embed_pages_task(ctx, d_id, batch_size=args.batch_size)
        except Exception as exc:
            failures += 1
            print(f"  FAILED: {type(exc).__name__}: {exc}")
            continue
        embedded += int(result.get("embedded_count", 0))
        elapsed += float(result.get("elapsed_s", 0.0))
        print(f"  {result['status']}: {result.get('embedded_count', 0)} pages in "
              f"{result.get('elapsed_s', 0.0):.2f}s ({result.get('pages_per_sec', 0.0):.1f} pages/sec)")

    rate = embedded / elapsed if elapsed > 0 else 0.0
    print("\n=======================================================")
    print(f"Documents: {len(docs)} (failed: {failures})")
    print(f"Pages embedded: {embedded} in {elapsed:.2f}s ({rate:.1f} pages/sec)")
    print("=======================================================")
    await engine.dispose()
    return 1 if failures else 0


def main() -> None:
    sys.exit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
