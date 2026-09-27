"""Natural Language to ScreenerDSL structured parser using LLM and heuristic fallback."""

from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any

from services.derive.registry import REGISTRY
from services.llm.factory import get_llm
from services.llm.types import Message, TextBlock, ToolDef
from services.screener.dsl import Filter, ScreenerDSL, Sort, Universe
from services.shared.logging import get_logger
from services.shared.types import FiscalPeriod, Ticker

log = get_logger("screener.parser")

SCREENER_TOOL = ToolDef(
    name="ScreenerDSL",
    description="Translates a natural language stock screening query into ScreenerDSL payload.",
    parameters_schema={
        "type": "object",
        "properties": {
            "universe": {
                "type": "object",
                "properties": {
                    "index": {"type": "string", "enum": ["IDX_ALL", "LQ45", "KOMPAS100"]},
                    "sector": {"type": "string", "description": "Sector e.g. BANK, MINING"},
                    "sub_sector": {"type": "string"},
                    "peer_group_id": {"type": "string"},
                    "tickers": {"type": "array", "items": {"type": "string"}},
                },
            },
            "filters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "metric": {"type": "string", "description": "Metric ID e.g. bank.nim, roe"},
                        "op": {"type": "string", "enum": [">", "<", ">=", "<=", "==", "!="]},
                        "value": {"type": "number", "description": "Threshold decimal"},
                        "period_offset": {"type": "integer", "default": 0},
                    },
                    "required": ["metric", "op", "value"],
                },
            },
            "as_of": {"type": "string", "description": "Target fiscal period e.g. 2024Q4"},
            "sort": {
                "type": "object",
                "properties": {
                    "metric": {"type": "string"},
                    "dir": {"type": "string", "enum": ["asc", "desc"]},
                },
                "required": ["metric"],
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25},
        },
        "required": ["filters", "as_of"],
    },
)


def _detect_universe_and_period(query: str, default_period: str) -> tuple[Universe, FiscalPeriod]:
    """Infers sector universe and reporting period from query string."""
    q_lower = query.lower()
    sector = None
    if "bank" in q_lower or "perbankan" in q_lower:
        sector = "BANK"
    elif "min" in q_lower or "tambang" in q_lower or "coal" in q_lower:
        sector = "MINING"
    elif "telco" in q_lower or "telekomunikasi" in q_lower:
        sector = "TELCO"

    universe = Universe(index="IDX_ALL", sector=sector)

    p_match = re.search(r"20\d\d[qQ][1-4]|20\d\d[fF][yY]|20\d\d", query)
    if p_match:
        raw_p = p_match.group(0).upper()
        as_of = FiscalPeriod(f"{raw_p}FY" if len(raw_p) == 4 else raw_p)
    else:
        as_of = FiscalPeriod(default_period)

    return universe, as_of


def _heuristic_parse_query(query: str, default_period: str) -> ScreenerDSL:
    """Deterministic regex parser fallback for common stock screening query patterns."""
    q_lower = query.lower()
    universe, as_of = _detect_universe_and_period(query, default_period)
    filters: list[Filter] = []

    patterns = [
        (r"roe\s*(>|>=|<|<=|==)\s*(\d+(?:\.\d+)?)\s*%?", "roe", True),
        (r"nim\s*(>|>=|<|<=|==)\s*(\d+(?:\.\d+)?)\s*%?", "bank.nim", True),
        (r"npl\s*(>|>=|<|<=|==)\s*(\d+(?:\.\d+)?)\s*%?", "bank.npl", True),
        (r"(?:net\s*margin|npm)\s*(>|>=|<|<=|==)\s*(\d+(?:\.\d+)?)\s*%?", "margin.net", True),
        (
            r"(?:debt\s*to\s*equity|der|debt_equity|de)\s*(>|>=|<|<=|==)\s*(\d+(?:\.\d+)?)",
            "debt_equity",
            False,
        ),
        (
            r"(?:yoy\s*revenue|pertumbuhan\s*pendapatan)\s*(>|>=|<|<=|==)\s*(\d+(?:\.\d+)?)\s*%?",
            "yoy.idx:TotalRevenue",
            True,
        ),
    ]

    for pat, metric, is_pct in patterns:
        m = re.search(pat, q_lower)
        if m:
            op_raw = m.group(1)
            op = op_raw if op_raw in (">", "<", ">=", "<=", "==", "!=") else ">"
            val = float(m.group(2))
            val_dec = Decimal(str(val / 100.0 if (is_pct and val > 1.0) else val))
            filters.append(Filter(metric=metric, op=op, value=val_dec))

    sort = Sort(metric=filters[0].metric, dir="desc") if filters else None
    if not filters:
        filters.append(Filter(metric="roe", op=">", value=Decimal("0.10")))
        sort = Sort(metric="roe", dir="desc")

    return ScreenerDSL(universe=universe, filters=filters, as_of=as_of, sort=sort, limit=25)


def _extract_json_payload(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    try:
        data = json.loads(stripped)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", stripped, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return None


async def parse_query(query: str, default_period: str = '2024Q4') -> ScreenerDSL:
    """Parses natural language screener query into valid ScreenerDSL."""
    client = get_llm("utility")
    known_metrics = list(REGISTRY.keys())[:30]
    metrics_str = ", ".join(known_metrics)

    prompt = (
        f"Parse stock screening query into a valid ScreenerDSL tool call:\n"
        f'Query: "{query}"\n'
        f"Default Period: {default_period}\n"
        f"Known Metrics: {metrics_str}"
    )

    try:
        args = None
        if client.capabilities.tool_use:
            resp = await client.complete(
                system=[
                    TextBlock(
                        text=(
                            "Expert equity research screener parser converting "
                            "queries to ScreenerDSL"
                        ),
                        cache_hint=True,
                    )
                ],
                messages=[Message(role="user", blocks=[TextBlock(text=prompt)])],
                tools=[SCREENER_TOOL],
                force_tool="ScreenerDSL",
            )
            for tc in resp.tool_calls:
                if tc.name == "ScreenerDSL":
                    args = tc.arguments
                    break
        else:
            json_system = (
                "Expert equity research screener parser converting queries to ScreenerDSL.\n"
                "Respond with ONLY a JSON object matching this schema:\n"
                '{"universe": {"index": "IDX_ALL", "sector": "..."}, '
                '"filters": [{"metric": "roe", "op": ">", "value": 0.15}], '
                '"as_of": \'2024Q4\', "sort": {"metric": "roe", "dir": "desc"}, "limit": 25}\n'
                "Do not include any commentary or markdown outside the JSON."
            )
            resp = await client.complete(
                system=[TextBlock(text=json_system, cache_hint=True)],
                messages=[Message(role="user", blocks=[TextBlock(text=prompt)])],
            )
            args = _extract_json_payload(resp.text)

        if args:
            univ_dict = args.get("universe", {})
            raw_tickers = univ_dict.get("tickers")
            tickers = [Ticker(t) for t in raw_tickers] if raw_tickers else None
            universe = Universe(
                index=univ_dict.get("index"),
                sector=univ_dict.get("sector"),
                sub_sector=univ_dict.get("sub_sector"),
                peer_group_id=univ_dict.get("peer_group_id"),
                tickers=tickers,
            )

            parsed_filters: list[Filter] = []
            for f in args.get("filters", []):
                parsed_filters.append(
                    Filter(
                        metric=f["metric"],
                        op=f["op"],
                        value=Decimal(str(f["value"])),
                        period_offset=f.get("period_offset", 0),
                    )
                )

            sort_dict = args.get("sort")
            sort_obj = (
                Sort(metric=sort_dict["metric"], dir=sort_dict.get("dir", "desc"))
                if sort_dict
                else None
            )
            as_of_val = args.get("as_of") or default_period
            return ScreenerDSL(
                universe=universe,
                filters=parsed_filters,
                as_of=FiscalPeriod(as_of_val),
                sort=sort_obj,
                limit=args.get("limit", 25),
            )
    except Exception as e:
        log.warning("LLM screener parsing failed, falling back to heuristics", error=str(e))

    return _heuristic_parse_query(query, default_period)
