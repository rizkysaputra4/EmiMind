"""Actual matcher comparing management guidance against realized financial disclosures."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from services.kg.types import MatchReport
from services.shared.db import ACTIVE_FACTS_PREDICATE
from services.shared.logging import get_logger
from services.shared.types import FiscalPeriod, Ticker

log = get_logger("kg.actual_matcher")


async def _lookup_actual_value(
    conn: AsyncConnection,
    ticker: str,
    period_str: str,
    metric: str,
    default_unit: str,
) -> tuple[float | None, str, dict[str, Any]]:
    """Looks up realized actual value from derived_metrics or financial_facts."""
    # 1. Try derived_metrics
    dm_res = await conn.execute(
        text(
            """
            SELECT id, value_numeric, unit
            FROM derived_metrics
            WHERE ticker = :ticker AND fiscal_period = :period AND metric_id = :metric
            LIMIT 1;
            """
        ),
        {"ticker": ticker, "period": period_str, "metric": metric},
    )
    dm_row = dm_res.mappings().first()
    if dm_row and dm_row["value_numeric"] is not None:
        return (
            float(dm_row["value_numeric"]),
            dm_row["unit"] or default_unit,
            {"derived_metric_id": dm_row["id"], "period": period_str},
        )

    # 2. Try financial_facts
    ff_sql = f"""
    SELECT id, value_numeric, unit, source_doc_id, source_page
    FROM financial_facts
    WHERE {ACTIVE_FACTS_PREDICATE}
      AND ticker = :ticker AND fiscal_period = :period AND concept_id = :concept
    ORDER BY created_at DESC
    LIMIT 1;
    """  # noqa: S608
    ff_res = await conn.execute(
        text(ff_sql),
        {"ticker": ticker, "period": period_str, "concept": metric},
    )
    ff_row = ff_res.mappings().first()
    if ff_row and ff_row["value_numeric"] is not None:
        return (
            float(ff_row["value_numeric"]),
            ff_row["unit"] or default_unit,
            {
                "fact_id": ff_row["id"],
                "doc_id": str(ff_row["source_doc_id"]) if ff_row["source_doc_id"] else None,
                "page": ff_row["source_page"],
            },
        )

    return None, default_unit, {}


def _evaluate_bounds_and_delta(
    actual_val: float,
    qualifier: str,
    low: float | None,
    high: float | None,
) -> tuple[bool, float]:
    """Calculates hit_bounds boolean and numeric delta from guidance target."""
    if qualifier == "range" and low is not None and high is not None:
        mid = (low + high) / 2.0
        return low <= actual_val <= high, round(actual_val - mid, 6)
    if qualifier == "exact" and low is not None:
        return abs(actual_val - low) < 0.005, round(actual_val - low, 6)
    if qualifier == "at_least" and low is not None:
        return actual_val >= low, round(actual_val - low, 6)
    if qualifier == "at_most" and high is not None:
        return actual_val <= high, round(actual_val - high, 6)
    return True, 0.0


async def _upsert_actual_node(
    conn: AsyncConnection,
    *,
    ticker: str,
    period_str: str,
    metric: str,
    actual_val: float,
    unit: str,
    source_ref: dict[str, Any],
) -> int:
    """Finds existing or creates new ACTUAL node in kg_nodes."""
    exist_act_res = await conn.execute(
        text(
            """
            SELECT id FROM kg_nodes
            WHERE node_type = 'ACTUAL'
              AND ticker = :ticker
              AND fiscal_period = :period
              AND payload->>'metric' = :metric
            LIMIT 1;
            """
        ),
        {"ticker": ticker, "period": period_str, "metric": metric},
    )
    act_row = exist_act_res.first()
    if act_row:
        return int(act_row[0])

    act_payload = {"metric": metric, "value": actual_val, "unit": unit, "period": period_str}
    act_res = await conn.execute(
        text(
            """
            INSERT INTO kg_nodes (
                node_type, ticker, fiscal_period, payload, source_ref, created_at
            )
            VALUES (
                'ACTUAL', :ticker, :period,
                CAST(:payload AS jsonb), CAST(:source_ref AS jsonb), now()
            )
            RETURNING id;
            """
        ),
        {
            "ticker": ticker,
            "period": period_str,
            "payload": json.dumps(act_payload),
            "source_ref": json.dumps(source_ref),
        },
    )
    return int(act_res.scalar_one())


async def match_actuals_for(
    conn: AsyncConnection,
    ticker: Ticker,
    new_period: FiscalPeriod,
) -> MatchReport:
    """Finds outstanding GUIDANCE nodes for target period and creates REALIZED_AS edges."""
    report = MatchReport(ticker=ticker, period=new_period)
    period_str = str(new_period)
    year_prefix = period_str[:4]

    g_res = await conn.execute(
        text(
            """
            SELECT id, ticker, fiscal_period, payload, source_ref
            FROM kg_nodes
            WHERE node_type = 'GUIDANCE'
              AND ticker = :ticker
              AND (payload->>'period_target' = :period OR payload->>'period_target' = :fy_target);
            """
        ),
        {
            "ticker": str(ticker),
            "period": period_str,
            "fy_target": f"{year_prefix}FY",
        },
    )
    guidance_nodes = g_res.mappings().all()
    if not guidance_nodes:
        return report

    for g_node in guidance_nodes:
        g_id = g_node["id"]
        g_payload = g_node["payload"]
        metric = g_payload.get("metric", "")
        low = float(g_payload["low"]) if g_payload.get("low") is not None else None
        high = float(g_payload["high"]) if g_payload.get("high") is not None else None
        qualifier = g_payload.get("qualifier", "range")

        actual_val, unit, source_ref = await _lookup_actual_value(
            conn=conn,
            ticker=str(ticker),
            period_str=period_str,
            metric=metric,
            default_unit=g_payload.get("unit", "RATIO"),
        )
        if actual_val is None:
            continue

        act_node_id = await _upsert_actual_node(
            conn=conn,
            ticker=str(ticker),
            period_str=period_str,
            metric=metric,
            actual_val=actual_val,
            unit=unit,
            source_ref=source_ref,
        )

        hit_bounds, delta = _evaluate_bounds_and_delta(actual_val, qualifier, low, high)
        edge_payload = {
            "delta": delta,
            "hit_bounds": hit_bounds,
            "status": "MET" if hit_bounds else "MISSED",
            "qualifier": qualifier,
            "target_range": [low, high],
            "actual_value": actual_val,
        }

        edge_exist = await conn.execute(
            text(
                """
                SELECT id FROM kg_edges
                WHERE src_id = :src AND dst_id = :dst AND edge_type = 'REALIZED_AS'
                LIMIT 1;
                """
            ),
            {"src": g_id, "dst": act_node_id},
        )
        if not edge_exist.first():
            edge_ins = await conn.execute(
                text(
                    """
                    INSERT INTO kg_edges (
                        src_id, dst_id, edge_type, confidence, payload, created_at
                    )
                    VALUES (:src, :dst, 'REALIZED_AS', 1.0, CAST(:payload AS jsonb), now())
                    RETURNING id;
                    """
                ),
                {"src": g_id, "dst": act_node_id, "payload": json.dumps(edge_payload)},
            )
            report.edges_created.append(edge_ins.scalar_one())
            report.matched_count += 1

            if not hit_bounds:
                contra_payload = {"reason": "Missed guidance bounds", "delta": delta}
                contra_ins = await conn.execute(
                    text(
                        """
                        INSERT INTO kg_edges (
                            src_id, dst_id, edge_type, confidence, payload, created_at
                        )
                        VALUES (:src, :dst, 'CONTRADICTS', 1.0, CAST(:payload AS jsonb), now())
                        RETURNING id;
                        """
                    ),
                    {"src": g_id, "dst": act_node_id, "payload": json.dumps(contra_payload)},
                )
                report.edges_created.append(contra_ins.scalar_one())

    return report
