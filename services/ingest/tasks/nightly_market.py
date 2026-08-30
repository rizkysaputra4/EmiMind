"""Nightly scheduled arq worker task: ingests daily market prices for covered tickers."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from services.market.yfinance_ingest import ingest_prices
from services.shared.db import create_pool
from services.shared.logging import get_logger
from services.shared.types import Ticker

log = get_logger("ingest.nightly_market")
WORKER_VERSION = "1.0"


async def nightly_market_task(
    ctx: dict[str, Any], tickers_list: list[str] | None = None
) -> dict[str, Any]:
    """Scheduled nightly task ingesting recent daily OHLCV market prices for covered tickers."""
    pool = ctx.get("db_pool") or create_pool()
    ingested_count = 0

    async with pool.connect() as conn:
        if not tickers_list:
            # Query all tickers from issuer_profile
            res = await conn.execute(text("SELECT ticker FROM issuer_profile ORDER BY ticker ASC;"))
            tickers_list = [r[0] for r in res.fetchall()]

        if not tickers_list:
            tickers_list = [
                "BMRI",
                "BBRI",
                "BBCA",
                "BBNI",
                "ADRO",
                "PTBA",
                "ITMG",
                "TLKM",
                "ASII",
                "ICBP",
            ]

        for t_str in tickers_list:
            ticker = Ticker(t_str)
            rep = await ingest_prices(conn, ticker)
            ingested_count += rep.rows_inserted

        await conn.commit()

    log.info(
        "Nightly market price ingestion finished",
        tickers=len(tickers_list),
        total_rows=ingested_count,
    )
    return {
        "status": "success",
        "tickers_count": len(tickers_list),
        "total_rows_inserted": ingested_count,
    }
