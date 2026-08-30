"""Tool schemas and handlers for LLM tool use execution during chat reasoning."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from services.derive.valuation import calculate_valuation
from services.llm.types import ToolDef
from services.market.renderers import render_technical_state
from services.screener.executor import execute_screener
from services.screener.parser import parse_query
from services.screener.renderers import render_screener_results_table


# --- Argument Models ---
class ExpandEvidenceArgs(BaseModel):
    chunk_id: int | None = Field(default=None, description="Narrative chunk ID to expand")
    node_id: int | None = Field(default=None, description="Knowledge graph node ID to expand")


class RunScreenerArgs(BaseModel):
    query: str = Field(default="", description="Natural language stock screening query")
    dsl_json: dict[str, Any] | None = Field(default=None, description="Screener query DSL payload")
    as_of: str | None = Field(default="2024Q4", description="Reporting period")


class ComputeMetricArgs(BaseModel):
    ticker: str = Field(description="Ticker symbol, e.g. BMRI")
    metric_id: str = Field(description="Metric identifier, e.g. bank.nim")
    period: str = Field(description="Fiscal period, e.g. 2024Q4")


class FetchPriceActionArgs(BaseModel):
    ticker: str = Field(description="Ticker symbol, e.g. BMRI")
    window: str = Field(default="1y", description="Lookback window")


class ListPeriodsArgs(BaseModel):
    ticker: str = Field(description="Ticker symbol, e.g. BMRI")


# --- Tool Definitions ---
TOOL_DEFS: list[ToolDef] = [
    ToolDef(
        name="expand_evidence",
        description="Expands evidence context for a specific narrative chunk ID or knowledge graph node ID.",
        parameters_schema={
            "type": "object",
            "properties": {
                "chunk_id": {"type": "integer", "description": "ID of narrative chunk to expand"},
                "node_id": {"type": "integer", "description": "ID of KG node to expand"},
            },
        },
    ),
    ToolDef(
        name="run_screener",
        description="Screens the Indonesian equity universe for companies meeting fundamental and financial criteria.",
        parameters_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language screening criteria"},
                "as_of": {"type": "string", "description": "Target fiscal period, e.g. 2024Q4"},
            },
            "required": ["query"],
        },
    ),
    ToolDef(
        name="compute_metric",
        description="Fetches or calculates a verified financial metric from derived metrics with audit citations.",
        parameters_schema={
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Ticker symbol"},
                "metric_id": {
                    "type": "string",
                    "description": "Metric ID, e.g. bank.nim, yoy.revenue",
                },
                "period": {"type": "string", "description": "Fiscal period, e.g. 2024Q4"},
            },
            "required": ["ticker", "metric_id", "period"],
        },
    ),
    ToolDef(
        name="fetch_price_action",
        description="Fetches technical market regime and recent price performance for a company.",
        parameters_schema={
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Ticker symbol"},
                "window": {"type": "string", "description": "Lookback window, e.g. 1y"},
            },
            "required": ["ticker"],
        },
    ),
    ToolDef(
        name="list_periods",
        description="Lists all available fiscal reporting periods for a given ticker in the database.",
        parameters_schema={
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Ticker symbol (e.g. BMRI)"},
            },
            "required": ["ticker"],
        },
    ),
]


# --- Handlers ---
async def handle_expand_evidence(conn: AsyncConnection, args_dict: dict[str, Any]) -> str:
    args = ExpandEvidenceArgs.model_validate(args_dict)
    if args.chunk_id is not None:
        res = await conn.execute(
            text(
                "SELECT ticker, fiscal_period, section, source_page, text_original, text_en "
                "FROM narrative_chunks WHERE id = :id"
            ),
            {"id": args.chunk_id},
        )
        row = res.mappings().first()
        if row:
            return (
                f"**Expanded Evidence for Chunk #{args.chunk_id}** "
                f"[{row['ticker']}-FS-{row['fiscal_period']}#p{row['source_page']}]\n"
                f"Section: {row['section']}\n"
                f"Original: {row['text_original']}\n"
                f"English: {row['text_en'] or row['text_original']}"
            )

    return "No valid chunk_id or node_id specified."


async def handle_run_screener(conn: AsyncConnection, args_dict: dict[str, Any]) -> str:
    args = RunScreenerArgs.model_validate(args_dict)
    dsl = await parse_query(args.query, default_period=args.as_of or "2024Q4")
    result = await execute_screener(conn, dsl)
    return render_screener_results_table(result)


async def handle_compute_metric(conn: AsyncConnection, args_dict: dict[str, Any]) -> str:
    args = ComputeMetricArgs.model_validate(args_dict)
    ticker = args.ticker.upper()
    metric_id = args.metric_id
    period = args.period.upper()

    # 1. Valuation metrics handling (Live on-the-fly vs Historical release snapshot)
    val_map = {
        "pe": "pe",
        "pe.ttm": "pe",
        "pe_ratio": "pe",
        "per": "pe",
        "pbv": "pbv",
        "pbv_ratio": "pbv",
        "price_to_book": "pbv",
        "ps": "ps",
        "ps.ttm": "ps",
        "price_to_sales": "ps",
        "pcf": "pcf",
        "pcf.ttm": "pcf",
        "price_to_cashflow": "pcf",
        "pfcf": "pfcf",
        "pfcf.ttm": "pfcf",
        "price_to_fcf": "pfcf",
        "ev_ebitda": "ev_ebitda",
        "ev/ebitda": "ev_ebitda",
        "market_cap": "market_cap",
        "dividend_yield": "dividend_yield",
    }

    if metric_id.lower() in val_map:
        val_key = val_map[metric_id.lower()]
        is_live = period in ("CURRENT", "LIVE", "LATEST")

        # If not explicitly marked LIVE, check if requested period is the latest available period
        if not is_live:
            latest_res = await conn.execute(
                text(
                    "SELECT fiscal_period FROM documents WHERE ticker = :ticker ORDER BY period_end DESC, fiscal_period DESC LIMIT 1"
                ),
                {"ticker": ticker},
            )
            latest_row = latest_res.mappings().first()
            if latest_row and latest_row["fiscal_period"] == period:
                is_live = True

        val_res = await calculate_valuation(conn, ticker, fiscal_period=period, is_live=is_live)
        if val_res and val_res.get(val_key) is not None:
            val = val_res[val_key]
            p_val = val_res.get("price")
            p_dt = val_res.get("price_date")
            if is_live and p_val is not None:
                citation = f"[{ticker}-LIVE-VALUATION-{p_dt or 'TODAY'}]"
                return (
                    f"{ticker} {metric_id} (CURRENT, live on-the-fly with price IDR {p_val:,.0f} as of {p_dt}): "
                    f"{val:,.2f} {citation}"
                )
            else:
                citation = f"[{ticker}-VALUATION-{period}]"
                return f"{ticker} {metric_id} ({period}, filing release snapshot price IDR {p_val or 0:,.0f}): {val:,.2f} {citation}"

    # 2. Check derived_metrics
    res = await conn.execute(
        text(
            "SELECT value_numeric, unit FROM derived_metrics "
            "WHERE ticker = :ticker AND metric_id = :metric AND fiscal_period = :period LIMIT 1"
        ),
        {"ticker": ticker, "metric": metric_id, "period": period},
    )
    row = res.mappings().first()
    if row:
        val = float(row["value_numeric"])
        unit = row["unit"] or ""
        citation = f"[{ticker}-DERIVED-{period}]"
        return f"{ticker} {metric_id} ({period}): {val:,.4f} {unit} {citation}"

    # 3. Check financial_facts (handling concept aliases)
    concept_candidates = [metric_id]
    alias_map = {
        "net_profit": "ifrs:ProfitLoss",
        "revenue": "ifrs:Revenue",
        "gross_profit": "ifrs:GrossProfit",
        "operating_profit": "ifrs:OperatingProfit",
        "ebit": "ifrs:OperatingProfit",
        "assets": "ifrs:Assets",
        "liabilities": "ifrs:Liabilities",
        "equity": "ifrs:Equity",
        "cash": "ifrs:CashAndCashEquivalents",
        "eps": "ifrs:BasicEarningsLossPerShare",
        "cfo": "ifrs:CashFlowsFromUsedInOperatingActivities",
        "capex": "ifrs:PaymentsToAcquirePropertyPlantAndEquipment",
    }
    if metric_id.lower() in alias_map:
        concept_candidates.append(alias_map[metric_id.lower()])

    fact_res = await conn.execute(
        text(
            """
            SELECT value_numeric, unit, source_page, concept_id
            FROM financial_facts
            WHERE ticker = :ticker AND (concept_id = ANY(:concepts) OR concept_local ILIKE :metric)
                  AND fiscal_period = :period
            ORDER BY extraction_conf DESC
            LIMIT 1
            """
        ),
        {"ticker": ticker, "concepts": concept_candidates, "metric": metric_id, "period": period},
    )
    fact_row = fact_res.mappings().first()
    if fact_row:
        f_val = float(fact_row["value_numeric"])
        f_unit = fact_row["unit"] or "IDR"
        page = fact_row["source_page"] or 1
        citation = f"[{ticker}-FS-{period}#p{page}]"
        return f"{ticker} {metric_id} ({period}): {f_val:,.2f} {f_unit} {citation}"

    return f"Metric {metric_id} not available for {ticker} {period}."


async def handle_fetch_price_action(conn: AsyncConnection, args_dict: dict[str, Any]) -> str:
    args = FetchPriceActionArgs.model_validate(args_dict)
    res = await conn.execute(
        text("SELECT * FROM technical_state WHERE ticker = :ticker LIMIT 1"),
        {"ticker": args.ticker.upper()},
    )
    row = res.mappings().first()
    if row:
        return render_technical_state(dict(row))
    return f"Technical regime state not computed yet for {args.ticker.upper()}."


async def handle_list_periods(conn: AsyncConnection, args_dict: dict[str, Any]) -> str:
    args = ListPeriodsArgs.model_validate(args_dict)
    res = await conn.execute(
        text(
            "SELECT DISTINCT fiscal_period FROM documents "
            "WHERE ticker = :ticker ORDER BY fiscal_period DESC"
        ),
        {"ticker": args.ticker.upper()},
    )
    periods = [r[0] for r in res.fetchall() if r[0]]
    if periods:
        return f"Available reporting periods for {args.ticker.upper()}: {', '.join(periods)}"
    return f"No filings found for ticker {args.ticker.upper()}."


ToolHandler = Callable[[AsyncConnection, dict[str, Any]], Coroutine[Any, Any, str]]

TOOL_HANDLERS: dict[str, ToolHandler] = {
    "expand_evidence": handle_expand_evidence,
    "run_screener": handle_run_screener,
    "compute_metric": handle_compute_metric,
    "fetch_price_action": handle_fetch_price_action,
    "list_periods": handle_list_periods,
}
