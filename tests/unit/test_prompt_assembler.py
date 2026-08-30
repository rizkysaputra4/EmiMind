"""Unit tests for prompt assembler and sticky header formatting."""

from __future__ import annotations

import pytest

from services.llm.types import TextBlock
from services.retrieval.budgeter import BudgetedBundle
from services.retrieval.prompt_assembler import (
    assemble_prompt,
    format_sticky_header,
)
from services.retrieval.session_store import StickyState
from services.shared.types import FiscalPeriod, Ticker


def test_format_sticky_header() -> None:
    sticky = StickyState(
        focus_ticker=Ticker("BMRI"),
        focus_periods=[FiscalPeriod("2024Q4")],
        peer_set=[Ticker("BBCA"), Ticker("BBRI")],
        active_metrics=["bank.nim"],
    )
    header = format_sticky_header(sticky)
    assert "focus=BMRI" in header
    assert "periods=2024Q4" in header
    assert "peers=BBCA,BBRI" in header
    assert "active_metrics=bank.nim" in header


@pytest.mark.asyncio
async def test_assemble_prompt_structure() -> None:
    bundle = BudgetedBundle(
        facts_md="| idx:NetInterestIncome | 72.30T | IDR | 2024Q4 | [BMRI-FS-2024Q4#p1] |",
        derived_md="| bank.nim | 0.0520 | RATIO | 2024Q4 | [BMRI-DERIVED-2024Q4] |",
        narrative_md='**[1] MDA Excerpt** [BMRI-FS-2024Q4#p1]\n> "Loan growth was robust."',
        total_tokens=150,
    )
    sticky = StickyState(focus_ticker=Ticker("BMRI"))

    prompt = await assemble_prompt(
        bundle=bundle,
        sticky=sticky,
        user_query="Why did NIM expand?",
        rolling_summary="Previous turns discussed loan growth.",
    )

    assert len(prompt.system) == 1
    assert prompt.system[0].cache_hint is True
    assert len(prompt.messages) == 1

    block = prompt.messages[0].blocks[0]
    assert isinstance(block, TextBlock)
    user_text = block.text
    assert '<evidence type="facts">' in user_text
    assert '<evidence type="derived">' in user_text
    assert '<evidence type="narrative">' in user_text
    assert '<evidence type="summary">' in user_text
    assert "[CONTEXT: focus=BMRI" in user_text
    assert "User Question: Why did NIM expand?" in user_text
