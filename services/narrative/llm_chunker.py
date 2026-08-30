"""LLM-powered semantic narrative extraction and chunking engine."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Literal

from services.llm.factory import get_llm
from services.llm.types import Message, TextBlock
from services.narrative.chunker import (
    chunk_pages as heuristic_chunk_pages,
    is_cover_or_title_page,
    is_digit_heavy,
    is_table_of_contents_page,
)
from services.shared.logging import get_logger
from services.shared.types import (
    DocType,
    FiscalPeriod,
    NarrativeChunkDraft,
    PageContent,
    Ticker,
)

log = get_logger("narrative.llm_chunker")

NARRATIVE_EXTRACTION_PROMPT = """You are an institutional financial disclosure parser for Indonesian Stock Exchange (IDX) filings.
Extract genuine narrative disclosure statements from this page text into a structured JSON array.

CRITICAL RULES:
1. IGNORE all table headers, continuation tags like "(lanjutan)/(continued)", page numbers, and currency disclaimers (e.g. "(Disajikan dalam Jutaan Rupiah)").
2. IGNORE isolated columns of accounting line-item names (these belong in the numerical fact tables, not narrative text).
3. IGNORE standalone director/auditor signature blocks and boilerplate formality text.
4. EXTRACT ONLY substantive narrative disclosures (e.g., general company information, accounting policies, business operations, debt terms, litigations, tax issues, commitments, risk factors, management discussion, guidance targets).
5. If this page is a pure numbers table, cover page, or contains NO valuable narrative disclosure, return an empty array `[]`.

DOCUMENT METADATA:
Ticker: {ticker}
Document Type: {doc_type}
Fiscal Period: {fiscal_period}
Page Number: {page_num}

PAGE TEXT:
\"\"\"
{page_text}
\"\"\"

OUTPUT FORMAT:
Return ONLY a valid JSON array of objects with the following keys (no markdown code fences, no extra text):
[
  {{
    "section": "FOOTNOTE" | "MDA" | "RISK" | "GUIDANCE" | "MGMT_STMT" | "OTHER",
    "topic": "Short descriptive topic (e.g. Accounting Policies, Credit Facilities, Litigation)",
    "text_original": "Clean, verbatim narrative sentence or paragraph without any header debris",
    "claim_type": "EXPLANATION" | "GUIDANCE" | "FORWARD_LOOKING" | "RISK" | "NEUTRAL",
    "mentioned_concepts": ["concept_key1", "concept_key2"]
  }}
]
"""


def _clean_json_response(raw_text: str) -> list[dict[str, Any]]:
    """Strips markdown fences and parses JSON array safely."""
    text = raw_text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    # Find array brackets
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]

    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "chunks" in data and isinstance(data["chunks"], list):
            return data["chunks"]
    except Exception as e:
        log.warning("Failed to parse LLM JSON narrative response", error=str(e), preview=text[:150])
    return []


async def _extract_page_narrative(
    page: PageContent,
    ticker: Ticker,
    doc_type: DocType,
    fiscal_period: FiscalPeriod,
    semaphore: asyncio.Semaphore,
) -> list[NarrativeChunkDraft]:
    """Extracts narrative chunks from a single page using LLM."""
    clean_text = (page.text or "").strip()
    if len(clean_text) < 60:
        return []

    # Skip obvious non-narrative pages before calling LLM to save latency & tokens
    if is_table_of_contents_page(clean_text):
        return []
    if is_cover_or_title_page(clean_text, page.page_num):
        return []
    if is_digit_heavy(clean_text, threshold=0.75):
        return []

    # Cap prompt text to 3,500 chars to avoid excessive token usage
    sample_text = clean_text[:3500]

    prompt = NARRATIVE_EXTRACTION_PROMPT.format(
        ticker=ticker,
        doc_type=doc_type,
        fiscal_period=fiscal_period,
        page_num=page.page_num,
        page_text=sample_text,
    )

    async with semaphore:
        try:
            llm = get_llm("utility")
            resp = await llm.complete(
                system=[
                    TextBlock(
                        text="You are an expert institutional financial NLP extractor. Return pure JSON only."
                    )
                ],
                messages=[Message(role="user", blocks=[TextBlock(text=prompt)])],
            )
            raw_chunks = _clean_json_response(resp.text)
        except Exception as e:
            log.warning(
                "LLM narrative extraction failed on page; falling back to heuristics",
                page=page.page_num,
                error=str(e),
            )
            return heuristic_chunk_pages([page], ticker, doc_type, fiscal_period)

    chunks: list[NarrativeChunkDraft] = []
    valid_sections = {"FOOTNOTE", "MDA", "RISK", "GUIDANCE", "MGMT_STMT", "OTHER"}
    valid_claim_types = {"EXPLANATION", "GUIDANCE", "FORWARD_LOOKING", "RISK", "NEUTRAL"}

    for item in raw_chunks:
        if not isinstance(item, dict):
            continue
        text_orig = (item.get("text_original") or "").strip()
        if not text_orig or len(text_orig) < 25:
            continue

        sec = item.get("section", "OTHER").upper()
        if sec not in valid_sections:
            sec = "OTHER"

        claim = item.get("claim_type", "EXPLANATION").upper()
        if claim not in valid_claim_types:
            claim = "EXPLANATION"

        concepts = item.get("mentioned_concepts")
        if not isinstance(concepts, list):
            concepts = []

        chunks.append(
            NarrativeChunkDraft(
                source_page=page.page_num,
                section=sec,  # type: ignore[arg-type]
                language=page.language,
                text_original=text_orig,
                speaker=item.get("speaker"),
                claim_type=claim,  # type: ignore[arg-type]
                mentioned_concepts=[str(c) for c in concepts if c],
                mentioned_periods=[fiscal_period],
            )
        )

    return chunks


async def extract_narrative_chunks_llm(
    pages: list[PageContent],
    ticker: Ticker,
    doc_type: DocType,
    fiscal_period: FiscalPeriod,
    max_concurrency: int = 4,
) -> list[NarrativeChunkDraft]:
    """Extracts high-quality semantic narrative chunks across all document pages using LLM."""
    if not pages:
        return []

    log.info(
        "Starting LLM narrative extraction",
        ticker=ticker,
        doc_type=doc_type,
        fiscal_period=fiscal_period,
        total_pages=len(pages),
    )

    semaphore = asyncio.Semaphore(max_concurrency)
    tasks = [
        _extract_page_narrative(page, ticker, doc_type, fiscal_period, semaphore)
        for page in pages
    ]

    results = await asyncio.gather(*tasks, return_exceptions=False)
    all_chunks: list[NarrativeChunkDraft] = []
    for page_chunks in results:
        all_chunks.extend(page_chunks)

    log.info(
        "LLM narrative extraction completed",
        ticker=ticker,
        total_chunks=len(all_chunks),
        pages_with_chunks=len({c.source_page for c in all_chunks}),
    )

    return all_chunks
