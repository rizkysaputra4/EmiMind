"""CLI script to backfill market daily prices and compute technical indicators."""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import text

from services.ingest.tasks.nightly_market import nightly_market_task
from services.ingest.tasks.nightly_technical import nightly_technical_task
from services.shared.config import get_settings
from services.shared.db import create_pool


async def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill daily market prices and compute technical state.")
    parser.add_argument("--tickers", type=str, default="", help="Comma-separated list of tickers (e.g. BMRI,BBRI)")
    args = parser.parse_args()

    settings = get_settings()
    pool = create_pool(settings.postgres_dsn)
    ctx = {"db_pool": pool}

    tickers_list = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    if not tickers_list:
        async with pool.connect() as conn:
            res = await conn.execute(text("SELECT ticker FROM issuer_profile ORDER BY ticker ASC;"))
            tickers_list = [r[0] for r in res.fetchall()]

    print(f"Backfilling market prices for {len(tickers_list)} tickers...")
    market_rep = await nightly_market_task(ctx, tickers_list)
    print(f"Market Ingest: {market_rep}")

    print(f"Computing technical indicator state for {len(tickers_list)} tickers...")
    tech_rep = await nightly_technical_task(ctx, tickers_list)
    print(f"Technical Compute: {tech_rep}")

    await pool.dispose()
    print("Market backfill and technical computation complete.")


if __name__ == "__main__":
    asyncio.run(main())
