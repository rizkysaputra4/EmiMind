"""Derived metrics computation engine."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

# Ensure all recipes are loaded into REGISTRY
import services.derive.recipes  # noqa: F401
from services.derive.recipes.peer_percentile import compute_peer_percentiles
from services.derive.registry import (
    REGISTRY,
    FactsAccessor,
    PeersAccessor,
    RecipeContext,
)
from services.shared.logging import get_logger
from services.shared.types import FiscalPeriod, Ticker

log = get_logger(__name__)


@dataclass
class ComputeReport:
    computed: int = 0
    skipped_missing_inputs: int = 0
    errors: list[str] = field(default_factory=list)


async def compute_for_document(doc_id: str, engine: AsyncEngine) -> ComputeReport:
    """Computes all applicable derived metrics and peer percentiles for an ingested document."""
    report = ComputeReport()

    async with engine.connect() as conn:
        # 1. Fetch document ticker & fiscal_period
        doc_res = await conn.execute(
            text("SELECT id, ticker, fiscal_period FROM documents WHERE id = :id"),
            {"id": doc_id},
        )
        doc = doc_res.mappings().first()
        if not doc:
            raise ValueError(f"Document {doc_id} not found in database.")

        try:
            ticker = Ticker(doc["ticker"])
            fiscal_period = FiscalPeriod(doc["fiscal_period"])
        except ValidationError as e:
            report.errors.append(f"Invalid ticker or fiscal_period: {e}")
            return report

        # 2. Determine ticker sector
        sector_res = await conn.execute(
            text(
                "SELECT sector FROM peer_groups WHERE :ticker = ANY(tickers) AND sector IS NOT NULL LIMIT 1"
            ),
            {"ticker": ticker},
        )
        sector_row = sector_res.mappings().first()
        sector = sector_row["sector"] if sector_row else None

        facts_accessor = FactsAccessor(conn, ticker, fiscal_period)
        peers_accessor = PeersAccessor(conn, ticker)
        ctx = RecipeContext(
            ticker=ticker,
            fiscal_period=fiscal_period,
            facts=facts_accessor,
            peers=peers_accessor,
        )

        upsert_sql = """
        INSERT INTO derived_metrics (
            ticker, fiscal_period, metric_id, value_numeric, unit, inputs, peer_group_id, recipe_version
        ) VALUES (
            :ticker, :fiscal_period, :metric_id, :value_numeric, :unit, CAST(:inputs AS jsonb), :peer_group_id, :ver
        )
        ON CONFLICT (ticker, fiscal_period, metric_id, coalesce(peer_group_id,''))
        DO UPDATE SET
            value_numeric = EXCLUDED.value_numeric,
            unit = EXCLUDED.unit,
            inputs = EXCLUDED.inputs,
            computed_at = now(),
            recipe_version = EXCLUDED.recipe_version;
        """

        # 3. Execute all matching recipes in REGISTRY
        for m_id, spec in REGISTRY.items():
            # Check sector compatibility
            if spec.sector and sector and spec.sector != sector:
                continue

            try:
                res = await spec.fn(ctx)
                if res is None or res.value is None:
                    report.skipped_missing_inputs += 1
                    continue

                inputs_json = json.dumps(res.inputs)
                await conn.execute(
                    text(upsert_sql),
                    {
                        "ticker": ticker,
                        "fiscal_period": fiscal_period,
                        "metric_id": m_id,
                        "value_numeric": float(res.value),
                        "unit": res.unit,
                        "inputs": inputs_json,
                        "peer_group_id": None,
                        "ver": spec.version,
                    },
                )
                report.computed += 1

            except Exception as e:
                err_msg = f"Error computing metric '{m_id}': {e}"
                log.warning(err_msg, ticker=ticker, period=fiscal_period)
                report.errors.append(err_msg)

        # 4. Compute and upsert peer percentiles
        try:
            peer_results = await compute_peer_percentiles(conn, ticker, fiscal_period)
            for pr in peer_results:
                await conn.execute(
                    text(upsert_sql),
                    {
                        "ticker": pr["ticker"],
                        "fiscal_period": pr["fiscal_period"],
                        "metric_id": pr["metric_id"],
                        "value_numeric": float(pr["value_numeric"]),
                        "unit": pr["unit"],
                        "inputs": json.dumps(pr["inputs"]),
                        "peer_group_id": pr["peer_group_id"],
                        "ver": pr["recipe_version"],
                    },
                )
                report.computed += 1
        except Exception as e:
            err_msg = f"Error computing peer percentiles: {e}"
            log.warning(err_msg, ticker=ticker, period=fiscal_period)
            report.errors.append(err_msg)

        await conn.commit()

    log.info(
        "Derived metrics computed",
        doc_id=doc_id,
        ticker=ticker,
        period=fiscal_period,
        computed=report.computed,
        skipped=report.skipped_missing_inputs,
    )
    return report
