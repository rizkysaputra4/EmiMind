"""LLM-assisted metadata proposal for uploaded PDFs (regex-first, LLM fallback)."""

from __future__ import annotations

import io
import json
import re
from typing import Any

import pdfplumber

from services.extraction.pdf import detect_language
from services.llm.factory import get_llm
from services.llm.types import Message, TextBlock, ToolDef
from services.shared.logging import get_logger
from services.shared.types import DocType, ProposedMetadata

log = get_logger("extraction.metadata_extractor")

MAX_PAGES_FOR_METADATA = 2
MAX_SNIPPET_CHARS = 240

_TICKER_KEYWORDS = (
    "kode emiten",
    "kode saham",
    "ticker",
    "stock code",
    "trading code",
    "idx",
    "bei",
)

_TICKER_NEAR_KEYWORD = re.compile(
    r"(?:kode\s+emiten|kode\s+saham|ticker|stock\s+code|trading\s+code|idx|bei)"
    r"\s*[:\-]?\s*([A-Z]{4})\b",
    re.IGNORECASE,
)
_TICKER_STANDALONE = re.compile(r"\b([A-Z]{4})\b")

_MONTH_TO_QUARTER = {
    "march": "Q1",
    "maret": "Q1",
    "june": "Q2",
    "juni": "Q2",
    "september": "Q3",
    "december": "Q4",
    "desember": "Q4",
}

_PERIOD_DATE = re.compile(
    r"(?:31|30)\s+(march|maret|june|juni|september|december|desember)\s+(\d{4})",
    re.IGNORECASE,
)
_PERIOD_LITERAL = re.compile(r"\b(19|20)(\d{2})\s*(Q[1-4]|FY|H[12])\b", re.IGNORECASE)

_DOCTYPE_RULES: list[tuple[DocType, tuple[str, ...]]] = [
    ("PUBEX", ("public expose", "paparan publik", "public exposé")),
    ("ANNUAL_REPORT", ("annual report", "laporan tahunan")),
    (
        "FS_ANNUAL",
        (
            "audited consolidated financial statements",
            "laporan keuangan konsolidasian auditan",
            "consolidated financial statements as of december 31",
            "consolidated financial statements as of 31 december",
            "laporan keuangan konsolidasian tanggal 31 desember",
            "for the year then ended",
            "for the year ended 31 december",
            "for the year ended december 31",
            "untuk tahun yang berakhir 31 desember",
            "untuk tahun yang berakhir pada tanggal 31 desember",
        ),
    ),
    (
        "FS_QUARTERLY",
        (
            "interim financial statements",
            "laporan keuangan interim",
            "laporan keuangan triwulan",
            "for the three-month period",
            "for the nine-month period",
            "for the six-month period",
            "consolidated financial statements as of march 31",
            "consolidated financial statements as of june 30",
            "consolidated financial statements as of september 30",
            "laporan keuangan konsolidasian tanggal 31 maret",
            "laporan keuangan konsolidasian tanggal 30 juni",
            "laporan keuangan konsolidasian tanggal 30 september",
        ),
    ),
]


def _extract_first_pages_text(pdf_bytes: bytes, max_pages: int = MAX_PAGES_FOR_METADATA) -> str:
    """Extracts text from the first N PDF pages only — keeps LLM cost tiny."""
    chunks: list[str] = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages[:max_pages]:
                text = page.extract_text() or ""
                if text.strip():
                    chunks.append(text)
    except Exception as e:
        log.warning("Failed to extract first pages for metadata", error=str(e))
    return "\n".join(chunks)


def _extract_ticker_regex(text: str) -> tuple[str | None, str | None]:
    """Returns (ticker, snippet) — prefers matches next to explicit keywords."""
    match = _TICKER_NEAR_KEYWORD.search(text)
    if match:
        ticker = match.group(1).upper()
        return ticker, _snippet_around(text, match.start(), match.end())

    lowered = text.lower()
    for kw in _TICKER_KEYWORDS:
        idx = lowered.find(kw)
        if idx == -1:
            continue
        window = text[idx : idx + 120]
        m = _TICKER_STANDALONE.search(window)
        if m:
            return m.group(1).upper(), window.strip()

    return None, None


def _extract_period_regex(text: str) -> tuple[str | None, str | None]:
    """Returns (fiscal_period, snippet). Prefers explicit literals, then dates."""
    lit = _PERIOD_LITERAL.search(text)
    if lit:
        year = lit.group(1) + lit.group(2)
        suffix = lit.group(3).upper()
        return f"{year}{suffix}", _snippet_around(text, lit.start(), lit.end())

    date_match = _PERIOD_DATE.search(text)
    if date_match:
        month = date_match.group(1).lower()
        year = date_match.group(2)
        quarter = _MONTH_TO_QUARTER.get(month)
        if quarter:
            return f"{year}{quarter}", _snippet_around(text, date_match.start(), date_match.end())

    return None, None


def _extract_doctype_regex(text: str) -> tuple[DocType | None, str | None]:
    """Returns (doc_type, snippet) via keyword scoring."""
    lowered = text.lower()
    for doc_type, keywords in _DOCTYPE_RULES:
        for kw in keywords:
            idx = lowered.find(kw)
            if idx != -1:
                return doc_type, _snippet_around(text, idx, idx + len(kw))
    return None, None


def _snippet_around(text: str, start: int, end: int, radius: int = 80) -> str:
    lo = max(0, start - radius)
    hi = min(len(text), end + radius)
    return text[lo:hi].strip()[:MAX_SNIPPET_CHARS]


_METADATA_TOOL = ToolDef(
    name="ProposeDocumentMetadata",
    description=(
        "Propose the IDX ticker (4 uppercase letters), fiscal period (YYYY + Q1|Q2|Q3|Q4|H1|H2|FY), "
        "and document type for an Indonesian public issuer PDF based on the provided cover-page text."
    ),
    parameters_schema={
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "IDX ticker, exactly 4 uppercase letters. Null if unknown.",
            },
            "fiscal_period": {
                "type": "string",
                "description": "Fiscal period, e.g. '2024Q4', '2023FY'. Null if unknown.",
            },
            "doc_type": {
                "type": "string",
                "enum": ["PUBEX", "FS_QUARTERLY", "FS_ANNUAL", "ANNUAL_REPORT"],
                "description": "Document type. Null if unknown.",
            },
            "confidence": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "number"},
                    "fiscal_period": {"type": "number"},
                    "doc_type": {"type": "number"},
                },
                "description": "Per-field confidence in [0, 1].",
            },
            "evidence_snippet": {
                "type": "string",
                "description": "Short quoted phrase from the text that supports the extraction.",
            },
        },
        "required": ["confidence"],
    },
)

_SYSTEM_PROMPT = (
    "You are a metadata extractor for Indonesian Stock Exchange (IDX) corporate filings. "
    "Given the first two pages of a PDF (cover, TOC, or opening statement), identify the ticker, "
    "fiscal period, and document type. Only fill fields you can support with the text — otherwise "
    "leave them null and mark low confidence. Always call the ProposeDocumentMetadata tool."
)


_JSON_FALLBACK_SUFFIX = (
    "\n\nYou MUST respond with ONLY a valid JSON object matching this schema — no prose, "
    'no code fences: {"ticker": "<TICKER or null>", "fiscal_period": "<YYYYQ#|FY|H# or null>", '
    '"doc_type": "<PUBEX|FS_QUARTERLY|FS_ANNUAL|ANNUAL_REPORT or null>", '
    '"confidence": {"ticker": <0..1>, "fiscal_period": <0..1>, "doc_type": <0..1>}, '
    '"evidence_snippet": "<short quoted phrase>"}. '
    "Use JSON null (not the string 'null') for unknown fields."
)


def _extract_json_payload(text: str) -> dict[str, Any] | None:
    """Best-effort JSON extraction from prose responses (mirrors classifier.py)."""
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


async def _llm_fallback(
    text: str,
    missing: list[str],
) -> dict[str, Any] | None:
    """Calls the utility LLM to fill in fields the regex tier missed.

    Uses tool-use when the provider supports it; otherwise falls back to a
    strict-JSON prompt (so CLI-agent providers still contribute).
    """
    if not text.strip():
        return None
    try:
        client = get_llm("utility")
        user_prompt = (
            f"Fields still needed: {', '.join(missing)}\n\n"
            f"PDF opening text:\n---\n{text[:6000]}\n---"
        )
        if client.capabilities.tool_use:
            resp = await client.complete(
                system=[TextBlock(text=_SYSTEM_PROMPT, cache_hint=True)],
                messages=[Message(role="user", blocks=[TextBlock(text=user_prompt)])],
                tools=[_METADATA_TOOL],
                force_tool="ProposeDocumentMetadata",
                max_output_tokens=400,
                temperature=0.0,
            )
            if resp.tool_calls:
                return resp.tool_calls[0].arguments
            # Some providers echo tool params as JSON in text — try parsing.
            payload = _extract_json_payload(resp.text)
            if payload:
                return payload
        else:
            resp = await client.complete(
                system=[TextBlock(text=_SYSTEM_PROMPT + _JSON_FALLBACK_SUFFIX, cache_hint=True)],
                messages=[Message(role="user", blocks=[TextBlock(text=user_prompt)])],
                max_output_tokens=400,
                temperature=0.0,
            )
            payload = _extract_json_payload(resp.text)
            if payload:
                return payload
    except Exception as e:
        log.warning("LLM metadata fallback failed", error=str(e))
    return None


def propose_metadata_from_text(text: str) -> ProposedMetadata:
    """Deterministic regex-only proposal from cover-page text; never calls an LLM.

    `fiscal_period` keeps the extractor's raw form (`2025Q2`, `2025FY`, `2025H1`); the
    caller normalizes it.
    """
    ticker, ticker_snip = _extract_ticker_regex(text)
    period, period_snip = _extract_period_regex(text)
    doc_type, doctype_snip = _extract_doctype_regex(text)
    confidence = {
        field: 1.0
        for field, value in (("ticker", ticker), ("fiscal_period", period), ("doc_type", doc_type))
        if value
    }
    snippets = [s for s in (ticker_snip, period_snip, doctype_snip) if s]
    return ProposedMetadata(
        ticker=ticker,
        fiscal_period=period,
        doc_type=doc_type,
        language=detect_language(text) if text.strip() else "id",
        confidence=confidence,
        evidence_snippet=" • ".join(snippets)[:MAX_SNIPPET_CHARS] or None,
        source="regex" if confidence else "none",
    )


async def propose_metadata(pdf_bytes: bytes) -> ProposedMetadata:
    """Proposes ticker/fiscal_period/doc_type/language from a PDF's opening pages.

    Regex tier is deterministic and free; LLM tier only runs for missing fields.
    """
    text = _extract_first_pages_text(pdf_bytes)
    language = detect_language(text) if text else "id"

    ticker, ticker_snip = _extract_ticker_regex(text)
    period, period_snip = _extract_period_regex(text)
    doc_type, doctype_snip = _extract_doctype_regex(text)

    confidence: dict[str, float] = {}
    snippets: list[str] = []

    if ticker:
        confidence["ticker"] = 1.0
        if ticker_snip:
            snippets.append(ticker_snip)
    if period:
        confidence["fiscal_period"] = 1.0
        if period_snip:
            snippets.append(period_snip)
    if doc_type:
        confidence["doc_type"] = 1.0
        if doctype_snip:
            snippets.append(doctype_snip)

    missing = [
        field
        for field, value in (
            ("ticker", ticker),
            ("fiscal_period", period),
            ("doc_type", doc_type),
        )
        if value is None
    ]

    source = "regex" if not missing else ("mixed" if confidence else "llm")

    if missing:
        llm_args = await _llm_fallback(text, missing)
        if llm_args:
            llm_conf = llm_args.get("confidence") or {}
            if ticker is None:
                cand = llm_args.get("ticker")
                if isinstance(cand, str) and re.fullmatch(r"[A-Za-z]{4}", cand):
                    ticker = cand.upper()
                    confidence["ticker"] = float(llm_conf.get("ticker", 0.6))
            if period is None:
                cand = llm_args.get("fiscal_period")
                if isinstance(cand, str) and re.fullmatch(
                    r"(19|20)\d{2}(Q[1-4]|FY|H[12])", cand.upper()
                ):
                    period = cand.upper()
                    confidence["fiscal_period"] = float(llm_conf.get("fiscal_period", 0.6))
            if doc_type is None:
                cand = llm_args.get("doc_type")
                if cand in ("PUBEX", "FS_QUARTERLY", "FS_ANNUAL", "ANNUAL_REPORT"):
                    doc_type = cand
                    confidence["doc_type"] = float(llm_conf.get("doc_type", 0.6))
            llm_snip = llm_args.get("evidence_snippet")
            if isinstance(llm_snip, str) and llm_snip.strip():
                snippets.append(llm_snip.strip()[:MAX_SNIPPET_CHARS])

    if source != "regex" and confidence and any(v < 1.0 for v in confidence.values()):
        source = "mixed"
    if not confidence:
        source = "none"

    evidence_snippet = " • ".join(s for s in snippets if s)[:MAX_SNIPPET_CHARS] or None

    return ProposedMetadata(
        ticker=ticker,
        fiscal_period=period,
        doc_type=doc_type,
        language=language,
        confidence=confidence,
        evidence_snippet=evidence_snippet,
        source=source,
    )
