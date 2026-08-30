"""Unit tests for LLM-powered narrative chunk extraction."""

import pytest
from services.narrative.llm_chunker import _clean_json_response, extract_narrative_chunks_llm
from services.shared.types import PageContent


def test_clean_json_response() -> None:
    # Test raw json
    raw = '[{"section": "FOOTNOTE", "text_original": "Grup bergerak dalam bidang nikel."}]'
    assert len(_clean_json_response(raw)) == 1

    # Test with markdown code blocks
    markdown_wrapped = '```json\n[{"section": "MDA", "text_original": "Pendapatan naik 20%."}]\n```'
    parsed = _clean_json_response(markdown_wrapped)
    assert len(parsed) == 1
    assert parsed[0]["section"] == "MDA"

    # Test with surrounding conversational noise
    noisy = 'Here are the extracted chunks:\n[{"section": "RISK", "text_original": "Risiko fluktuasi harga komoditas."}]\nHope this helps!'
    parsed_noisy = _clean_json_response(noisy)
    assert len(parsed_noisy) == 1
    assert parsed_noisy[0]["section"] == "RISK"


@pytest.mark.asyncio
async def test_extract_narrative_chunks_llm_empty_pages() -> None:
    chunks = await extract_narrative_chunks_llm([], "NCKL", "FS_QUARTERLY", "2026Q2")
    assert chunks == []


@pytest.mark.asyncio
async def test_extract_narrative_chunks_llm_skips_cover() -> None:
    cover_page = PageContent(
        page_num=1,
        text="PT Trimegah Bangun Persada Tbk.\nLaporan keuangan konsolidasian interim yang tidak diaudit",
        language="id",
        has_text_layer=True,
    )
    chunks = await extract_narrative_chunks_llm([cover_page], "NCKL", "FS_QUARTERLY", "2026Q2")
    # Cover page is skipped prior to LLM call
    assert chunks == []
