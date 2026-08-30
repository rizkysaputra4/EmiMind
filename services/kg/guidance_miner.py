"""Two-tier management guidance extraction engine (Regex + LLM fallback)."""

from __future__ import annotations

import re
from decimal import Decimal

from services.kg.types import GuidancePayload
from services.llm.factory import get_llm
from services.llm.types import Message, TextBlock, ToolDef
from services.shared.logging import get_logger
from services.shared.types import FiscalPeriod

log = get_logger("kg.guidance_miner")

# Precompiled regex patterns for common financial guidance targets in English & Indonesian
PATTERNS = [
    # Loan growth range: "loan growth of 10-12% for 2025"
    (
        re.compile(
            r"(?:loan\s+growth|pertumbuhan\s+kredit|kredit).*?"
            r"(\d+(?:\.\d+)?)\s*(?:-|\u2013|to|sampai)\s*(\d+(?:\.\d+)?)\s*%.*?"
            r"(?:(?:for|in|pada|tahun)\s*(20\d{2}(?:[qh][1-4]|fy)?))?",
            re.IGNORECASE,
        ),
        "idx:LoansAndAdvances",
        "RATIO",
        "range",
        True,  # is_pct
    ),
    # NIM range/target: "NIM 5.0 - 5.3%" or "NIM target of 5.2%"
    (
        re.compile(
            r"NIM.*?(?:target|of|sebesar|di\s*kisaran)?\s*"
            r"(\d+(?:\.\d+)?)\s*(?:-|\u2013|to|sampai)\s*(\d+(?:\.\d+)?)\s*%.*?"
            r"(?:(?:for|in|pada|tahun)\s*(20\d{2}(?:[qh][1-4]|fy)?))?",
            re.IGNORECASE,
        ),
        "bank.nim",
        "RATIO",
        "range",
        True,
    ),
    (
        re.compile(
            r"NIM.*?(?:target|of|sebesar|mencapai)\s*(\d+(?:\.\d+)?)\s*%.*?"
            r"(?:(?:for|in|pada|tahun)\s*(20\d{2}(?:[qh][1-4]|fy)?))?",
            re.IGNORECASE,
        ),
        "bank.nim",
        "RATIO",
        "exact",
        True,
    ),
    # NPL ceiling: "NPL below 2%" or "NPL di bawah 2.0%" or "NPL < 2.0%"
    (
        re.compile(
            r"NPL.*?(?:below|under|di\s*bawah|<|maksimal|maximum)\s*(\d+(?:\.\d+)?)\s*%.*?"
            r"(?:(?:for|in|pada|tahun)\s*(20\d{2}(?:[qh][1-4]|fy)?))?",
            re.IGNORECASE,
        ),
        "bank.npl",
        "RATIO",
        "at_most",
        True,
    ),
    # Cost of Credit (CoC): "Cost of Credit 1.0 - 1.2%" or "CoC 1.0 - 1.2%"
    (
        re.compile(
            r"(?:Cost\s+of\s+Credit|CoC).*?(\d+(?:\.\d+)?)\s*(?:-|\u2013|to|sampai)\s*"
            r"(\d+(?:\.\d+)?)\s*%.*?(?:(?:for|in|pada|tahun)\s*(20\d{2}(?:[qh][1-4]|fy)?))?",
            re.IGNORECASE,
        ),
        "bank.coc",
        "RATIO",
        "range",
        True,
    ),
    # CASA floor: "CASA ratio above 70%" or "CASA di atas 70%"
    (
        re.compile(
            r"CASA.*?(?:above|over|di\s*atas|>|minimal|at\s*least)\s*(\d+(?:\.\d+)?)\s*%.*?"
            r"(?:(?:for|in|pada|tahun)\s*(20\d{2}(?:[qh][1-4]|fy)?))?",
            re.IGNORECASE,
        ),
        "bank.casa",
        "RATIO",
        "at_least",
        True,
    ),
    # Coal production: "production volume 60 - 65 million tons"
    (
        re.compile(
            r"(?:production|produksi).*?(\d+(?:\.\d+)?)\s*(?:-|\u2013|to|sampai)\s*"
            r"(\d+(?:\.\d+)?)\s*(?:million\s*tons|juta\s*ton|mt).*?"
            r"(?:(?:for|in|pada|tahun)\s*(20\d{2}(?:[qh][1-4]|fy)?))?",
            re.IGNORECASE,
        ),
        "mining.production",
        "TONS",
        "range",
        False,
    ),
]

GUIDANCE_TOOL = ToolDef(
    name="GuidanceExtraction",
    description="Extracts management forward-looking guidance targets from disclosures.",
    parameters_schema={
        "type": "object",
        "properties": {
            "targets": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "metric": {
                            "type": "string",
                            "description": "Canonical metric ID (e.g. bank.nim, LoansAndAdvances)",
                        },
                        "low": {"type": "number", "description": "Lower bound (decimal)"},
                        "high": {"type": "number", "description": "Upper bound (decimal)"},
                        "period_target": {"type": "string", "description": "Target fiscal period"},
                        "qualifier": {
                            "type": "string",
                            "enum": ["at_least", "at_most", "exact", "range", "direction"],
                        },
                        "direction": {"type": "string", "enum": ["up", "down", "flat"]},
                        "unit": {"type": "string", "description": "Unit e.g. RATIO or IDR or TONS"},
                        "verbatim": {"type": "string", "description": "Verbatim sentence"},
                    },
                    "required": ["metric", "period_target", "verbatim"],
                },
            }
        },
        "required": ["targets"],
    },
)


def _resolve_target_period(period_str: str | None, source_period: str) -> FiscalPeriod:
    """Infers target fiscal period string into canonical FiscalPeriod."""
    if not period_str:
        if "Q" in source_period:
            year = int(source_period[:4])
            return FiscalPeriod(f"{year + 1}FY")
        return FiscalPeriod("2025FY")

    p = period_str.upper()
    if re.match(r"^20\d\d$", p):
        return FiscalPeriod(f"{p}FY")
    return FiscalPeriod(p)


def mine_guidance_regex(text: str, source_period: str) -> list[GuidancePayload]:
    """Runs high-precision deterministic regular expression extractors on chunk text."""
    results: list[GuidancePayload] = []
    # Split on sentence boundaries, newlines, or semicolons without splitting decimal points
    sentences = re.split(r"\n+|;\s*|(?<=[a-zA-Z\)])\.\s+", text)

    for raw_sentence in sentences:
        sentence = raw_sentence.strip()
        if not sentence:
            continue

        for regex, metric, unit, qualifier, is_pct in PATTERNS:
            match = regex.search(sentence)
            if not match:
                continue

            groups = match.groups()
            if qualifier == "range":
                v1 = float(groups[0]) / 100.0 if is_pct else float(groups[0]) * 1_000_000.0
                v2 = float(groups[1]) / 100.0 if is_pct else float(groups[1]) * 1_000_000.0
                period_match = groups[2] if len(groups) > 2 else None
                p_target = _resolve_target_period(period_match, source_period)

                results.append(
                    GuidancePayload(
                        metric=metric,
                        low=Decimal(str(round(v1, 6))),
                        high=Decimal(str(round(v2, 6))),
                        period_target=p_target,
                        qualifier="range",
                        unit=unit,
                        verbatim=sentence,
                    )
                )
            elif qualifier == "exact":
                v1 = float(groups[0]) / 100.0 if is_pct else float(groups[0])
                period_match = groups[1] if len(groups) > 1 else None
                p_target = _resolve_target_period(period_match, source_period)

                results.append(
                    GuidancePayload(
                        metric=metric,
                        low=Decimal(str(round(v1, 6))),
                        high=Decimal(str(round(v1, 6))),
                        period_target=p_target,
                        qualifier="exact",
                        unit=unit,
                        verbatim=sentence,
                    )
                )
            elif qualifier == "at_most":
                v1 = float(groups[0]) / 100.0 if is_pct else float(groups[0])
                period_match = groups[1] if len(groups) > 1 else None
                p_target = _resolve_target_period(period_match, source_period)

                results.append(
                    GuidancePayload(
                        metric=metric,
                        low=None,
                        high=Decimal(str(round(v1, 6))),
                        period_target=p_target,
                        qualifier="at_most",
                        unit=unit,
                        verbatim=sentence,
                    )
                )
            elif qualifier == "at_least":
                v1 = float(groups[0]) / 100.0 if is_pct else float(groups[0])
                period_match = groups[1] if len(groups) > 1 else None
                p_target = _resolve_target_period(period_match, source_period)

                results.append(
                    GuidancePayload(
                        metric=metric,
                        low=Decimal(str(round(v1, 6))),
                        high=None,
                        period_target=p_target,
                        qualifier="at_least",
                        unit=unit,
                        verbatim=sentence,
                    )
                )

    return results


async def mine_guidance_llm(text: str, source_period: str) -> list[GuidancePayload]:
    """Fallback structured LLM guidance extractor for unstructured disclosure sentences."""
    client = get_llm("reasoner")
    results: list[GuidancePayload] = []

    prompt_text = (
        f"Extract any forward-looking guidance targets from this disclosure:\n\n"
        f'"{text}"\n\nSource Reporting Period: {source_period}'
    )

    try:
        resp = await client.complete(
            system=[TextBlock(text="Extract numerical guidance targets into structured format.")],
            messages=[Message(role="user", blocks=[TextBlock(text=prompt_text)])],
            tools=[GUIDANCE_TOOL],
            force_tool="GuidanceExtraction",
        )

        for tc in resp.tool_calls:
            if tc.name == "GuidanceExtraction":
                targets = tc.arguments.get("targets", [])
                for t in targets:
                    try:
                        p_target = FiscalPeriod(t["period_target"])
                    except Exception:
                        p_target = _resolve_target_period(None, source_period)

                    results.append(
                        GuidancePayload(
                            metric=t["metric"],
                            low=Decimal(str(t["low"])) if t.get("low") is not None else None,
                            high=Decimal(str(t["high"])) if t.get("high") is not None else None,
                            period_target=p_target,
                            qualifier=t.get("qualifier", "range"),
                            direction=t.get("direction"),
                            unit=t.get("unit", "RATIO"),
                            verbatim=t.get("verbatim", text[:120]),
                        )
                    )
    except Exception as e:
        log.warning("LLM guidance mining failed, returning regex results", error=str(e))

    return results


async def mine_guidance(text: str, source_period: str) -> list[GuidancePayload]:
    """Unified two-tier guidance extractor."""
    regex_results = mine_guidance_regex(text, source_period)
    if regex_results:
        return regex_results

    if any(k in text.lower() for k in ["guidance", "target", "proyeksi", "expect", "panduan"]):
        return await mine_guidance_llm(text, source_period)

    return []
