from __future__ import annotations

import json
import re
from typing import Any

from services.llm.factory import get_llm
from services.llm.types import Message, TextBlock, ToolDef
from services.retrieval.session_store import StickyState
from services.shared.logging import get_logger
from services.shared.types import Intent, QueryClassification

log = get_logger("retrieval.classifier")

CLASSIFIER_TOOL = ToolDef(
    name="QueryClassification",
    description="Extracts structured intent and parameter slots from a financial research query.",
    parameters_schema={
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "enum": [i.value for i in Intent],
                "description": "Primary intention of the query.",
            },
            "tickers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Stock ticker symbols mentioned or inferred (e.g. ['BMRI']).",
            },
            "periods": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Fiscal periods mentioned or inferred (e.g. ['2024Q4']).",
            },
            "concepts": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Financial concepts/metrics mentioned (e.g. ['revenue', 'net_profit', 'nim']).",
            },
            "is_drill": {
                "type": "boolean",
                "description": "True if the query is a follow-up drill down on previous analysis.",
            },
            "references_prior_claim": {
                "type": "boolean",
                "description": "True if query references a specific assertion made in previous turns.",
            },
        },
        "required": [
            "intent",
            "tickers",
            "periods",
            "concepts",
            "is_drill",
            "references_prior_claim",
        ],
    },
)

SYSTEM_PROMPT = """You are an expert financial query parser for the Indonesian Stock Exchange (IDX).
Given a user query and the current conversation context (sticky focus ticker and periods), classify the intent and extract all relevant tickers (4 uppercase letters), fiscal periods (e.g. 2024Q4, 2023FY), and financial concepts.

Intent taxonomy:
- FACT_LOOKUP: Direct lookup of specific financial numbers or balance sheet items.
- EXPLANATION: Asking why a metric moved, what caused a result, or driver analysis.
- TREND: Multi-period historical trajectory, growth rate, or CAGR questions.
- COMPARE_PEERS: Comparative questions across two or more tickers or peer groups.
- SCREEN: Filtering or screening for companies matching specific criteria.
- GUIDANCE_CHECK: Questions regarding management guidance, targets, or forecasts.
- TECHNICAL: Questions regarding market regime, price momentum, or volume.
- META: Non-financial greetings, help requests, or out-of-domain questions.

Always output structured results via the QueryClassification tool."""


def _extract_json_payload(text: str) -> dict[str, Any] | None:
    """Extracts first valid JSON object from model response text."""
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


async def classify(
    query: str,
    session_state: StickyState | None = None,
) -> QueryClassification:
    """Classifies user query intent and extracts financial parameters using utility LLM."""
    client = get_llm("utility")

    context_str = "No prior session context."
    if session_state and session_state.focus_ticker:
        context_str = (
            f"Active Focus Ticker: {session_state.focus_ticker}\n"
            f"Active Focus Periods: {session_state.focus_periods}\n"
            f"Active Peer Set: {session_state.peer_set}\n"
            f"Active Metrics: {session_state.active_metrics}"
        )

    user_prompt = f'Context:\n{context_str}\n\nUser Query: "{query}"'

    try:
        if client.capabilities.tool_use:
            resp = await client.complete(
                system=[TextBlock(text=SYSTEM_PROMPT, cache_hint=True)],
                messages=[Message(role="user", blocks=[TextBlock(text=user_prompt)])],
                tools=[CLASSIFIER_TOOL],
                force_tool="QueryClassification",
                max_output_tokens=512,
                temperature=0.0,
            )

            if resp.tool_calls:
                call = resp.tool_calls[0]
                args: dict[str, Any] = call.arguments
                return QueryClassification.model_validate(args)
        else:
            # Fallback for CLI agents or providers without native tool_use capability
            json_system = (
                SYSTEM_PROMPT
                + "\n\nYou MUST respond with ONLY a valid JSON object matching this schema:\n"
                + '{"intent": "<INTENT>", "tickers": ["<TICKER>"], "periods": ["<PERIOD>"], "concepts": ["<CONCEPT>"], "is_drill": false, "references_prior_claim": false}\n'
                + "Do not include any commentary or text outside the JSON object."
            )
            resp = await client.complete(
                system=[TextBlock(text=json_system, cache_hint=True)],
                messages=[Message(role="user", blocks=[TextBlock(text=user_prompt)])],
                max_output_tokens=512,
                temperature=0.0,
            )
            payload = _extract_json_payload(resp.text)
            if payload:
                return QueryClassification.model_validate(payload)

    except Exception as e:
        log.warning(
            "Classifier LLM call failed, falling back to heuristic classification", error=str(e)
        )

    # Fallback heuristic classification
    ticker = session_state.focus_ticker if session_state and session_state.focus_ticker else "BMRI"
    return QueryClassification(
        intent=Intent.FACT_LOOKUP,
        tickers=[ticker],
        periods=session_state.focus_periods
        if session_state and session_state.focus_periods
        else ['2024Q4'],
        concepts=["net_profit"],
        is_drill=False,
        references_prior_claim=False,
    )
