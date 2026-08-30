"""Integration tests for POST /api/v1/screener and LLM tool execution."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text

from services.screener.dsl import Filter, ScreenerDSL, Sort, Universe
from services.screener.executor import execute_screener
from services.shared.config import get_settings
from services.shared.db import create_pool
from services.shared.types import FiscalPeriod, Ticker


@pytest.mark.integration
async def test_screener_execution_with_seed_data() -> None:
    settings = get_settings()
    pool = create_pool(settings.postgres_dsn)

    async with pool.connect() as conn:
        # Seed test derived metrics and issuer profiles
        await conn.execute(
            text(
                """
                INSERT INTO issuer_profile (ticker, name, sector, last_refreshed_at)
                VALUES ('BMRI', 'Bank Mandiri', 'BANK', now()),
                       ('BBRI', 'Bank Rakyat Indonesia', 'BANK', now())
                ON CONFLICT (ticker) DO UPDATE SET sector = EXCLUDED.sector;
                """
            )
        )
        await conn.execute(
            text(
                """
                INSERT INTO derived_metrics (
                    ticker, fiscal_period, metric_id, value_numeric, unit, inputs, recipe_version, computed_at
                )
                VALUES
                    ('BMRI', '2024Q4', 'roe', 0.201, 'RATIO', '{"fact_ids": [1]}', '1.0', now()),
                    ('BMRI', '2024Q4', 'bank.nim', 0.052, 'RATIO', '{"fact_ids": [2]}', '1.0', now()),
                    ('BBRI', '2024Q4', 'roe', 0.188, 'RATIO', '{"fact_ids": [3]}', '1.0', now()),
                    ('BBRI', '2024Q4', 'bank.nim', 0.068, 'RATIO', '{"fact_ids": [4]}', '1.0', now())
                ON CONFLICT (ticker, fiscal_period, metric_id, coalesce(peer_group_id, ''))
                DO UPDATE SET value_numeric = EXCLUDED.value_numeric;
                """
            )
        )
        await conn.commit()

        dsl = ScreenerDSL(
            universe=Universe(sector="BANK"),
            filters=[
                Filter(metric="roe", op=">", value=Decimal("0.15")),
                Filter(metric="bank.nim", op=">", value=Decimal("0.05")),
            ],
            as_of=FiscalPeriod("2024Q4"),
            sort=Sort(metric="roe", dir="desc"),
            limit=10,
        )

        res = await execute_screener(conn, dsl)
        assert res.total_matches >= 2
        tickers = [r.ticker for r in res.rows]
        assert Ticker("BMRI") in tickers
        assert Ticker("BBRI") in tickers

    await pool.dispose()
