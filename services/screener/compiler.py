"""Screener DSL compiler translating multi-criteria filters to parameterized SQL."""

from __future__ import annotations

from typing import Any

from services.derive.recipes.generic import offset_fiscal_period
from services.screener.dsl import ScreenerDSL


def compile_to_sql(dsl: ScreenerDSL) -> tuple[str, dict[str, Any]]:
    """Compiles ScreenerDSL into parameterized PostgreSQL query with INTERSECT filtering."""
    params: dict[str, Any] = {
        "as_of": str(dsl.as_of),
        "limit": dsl.limit,
        "sector": dsl.universe.sector,
        "universe_tickers": [str(t) for t in dsl.universe.tickers] if dsl.universe.tickers else [],
        "tickers_len": len(dsl.universe.tickers) if dsl.universe.tickers else 0,
    }

    intersect_queries: list[str] = []

    for idx, f in enumerate(dsl.filters):
        period_target = (
            str(offset_fiscal_period(dsl.as_of, f.period_offset))
            if f.period_offset != 0
            else str(dsl.as_of)
        )
        p_metric = f"metric_{idx}"
        p_val = f"val_{idx}"
        p_period = f"period_{idx}"

        params[p_metric] = f.metric
        params[p_val] = float(f.value)
        params[p_period] = period_target

        op_sql = f.op if f.op != "==" else "="

        subquery = f"""
        SELECT ticker FROM derived_metrics
        WHERE fiscal_period = :{p_period}
          AND metric_id = :{p_metric}
          AND value_numeric {op_sql} :{p_val}
        """  # noqa: S608
        intersect_queries.append(subquery.strip())

    if not intersect_queries:
        candidates_cte = "SELECT DISTINCT ticker FROM derived_metrics WHERE fiscal_period = :as_of"
    else:
        candidates_cte = "\nINTERSECT\n".join(intersect_queries)

    # Sort clause
    sort_clause = "c.ticker ASC"
    if dsl.sort:
        params["sort_metric"] = dsl.sort.metric
        dir_sql = "DESC" if dsl.sort.dir == "desc" else "ASC"
        sort_clause = (
            f"max(CASE WHEN d.metric_id = :sort_metric THEN d.value_numeric END) "
            f"{dir_sql} NULLS LAST"
        )

    sql = f"""
    WITH candidates AS (
      {candidates_cte}
    )
    SELECT c.ticker,
           jsonb_object_agg(d.metric_id, d.value_numeric) AS metric_values,
           jsonb_agg(
             jsonb_build_object(
               'metric', d.metric_id,
               'value', d.value_numeric,
               'unit', d.unit,
               'fact_ids', d.inputs->'fact_ids'
             )
           ) AS provenance
    FROM candidates c
    JOIN derived_metrics d ON d.ticker = c.ticker AND d.fiscal_period = :as_of
    LEFT JOIN issuer_profile ip ON ip.ticker = c.ticker
    WHERE (CAST(:sector AS text) IS NULL OR ip.sector = :sector OR ip.sub_sector = :sector)
      AND (:tickers_len = 0 OR c.ticker = ANY(CAST(:universe_tickers AS text[])))
    GROUP BY c.ticker
    ORDER BY {sort_clause}
    LIMIT :limit;
    """  # noqa: S608

    return sql.strip(), params
