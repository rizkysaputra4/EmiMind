"""Prompt assembler constructing provider-neutral AssembledPrompt from budgeted evidence."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from services.llm.types import Message, TextBlock
from services.retrieval.budgeter import BudgetedBundle
from services.retrieval.session_store import StickyState

SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent.parent / "llm" / "system_prompt.md"


class AssembledPrompt(BaseModel):
    """Structured prompt blocks ready for LLM consumption."""

    system: list[TextBlock] = Field(default_factory=list)
    messages: list[Message] = Field(default_factory=list)


def format_sticky_header(sticky: StickyState) -> str:
    """Formats sticky context header string per BLUEPRINT §13.3."""
    focus = sticky.focus_ticker or "None"
    periods = ",".join(sticky.focus_periods) if sticky.focus_periods else "None"
    peers = ",".join(sticky.peer_set) if sticky.peer_set else "None"
    metrics = ",".join(sticky.active_metrics) if sticky.active_metrics else "None"

    return (
        f"[CONTEXT: focus={focus} | periods={periods} | peers={peers} | active_metrics={metrics}]"
    )


async def assemble_prompt(
    bundle: BudgetedBundle,
    sticky: StickyState,
    user_query: str,
    rolling_summary: str = "",
) -> AssembledPrompt:
    """Assembles provider-neutral system blocks and user messages with structured evidence."""
    # 1. Load system prompt
    system_text = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
    system_blocks = [TextBlock(text=system_text, cache_hint=True)]

    # 2. Build user turn content
    blocks: list[str] = []

    # Frame block (L6)
    if bundle.frame_md:
        blocks.append(f'<evidence type="frame">\n{bundle.frame_md}\n</evidence>')

    # Rolling summary
    if rolling_summary:
        blocks.append(
            f'<evidence type="summary">\n### Prior Conversation Context\n'
            f"{rolling_summary}\n</evidence>"
        )

    # Evidence blocks
    if bundle.guidance_md:
        blocks.append(
            f'<evidence type="guidance">\n### Management Guidance vs Realized Actuals Matrix\n'
            f"{bundle.guidance_md}\n</evidence>"
        )

    if bundle.facts_md:
        blocks.append(f'<evidence type="facts">\n{bundle.facts_md}\n</evidence>')

    if bundle.derived_md:
        blocks.append(f'<evidence type="derived">\n{bundle.derived_md}\n</evidence>')

    if bundle.narrative_md:
        blocks.append(f'<evidence type="narrative">\n{bundle.narrative_md}\n</evidence>')

    if bundle.kg_md:
        blocks.append(
            f'<evidence type="relationships">\n### Causal Factor Attribution Graph (Layer 5)\n'
            f"{bundle.kg_md}\n</evidence>"
        )

    if bundle.market_md:
        blocks.append(
            f'<evidence type="technical">\n### Market Technical Analysis & Regime State (Layer 7)\n'
            f"{bundle.market_md}\n</evidence>"
        )

    # Sticky header + user query
    sticky_header = format_sticky_header(sticky)
    blocks.append(f"{sticky_header}\n\nUser Question: {user_query}")

    user_turn_text = "\n\n".join(blocks)

    messages = [
        Message(
            role="user",
            blocks=[TextBlock(text=user_turn_text)],
        )
    ]

    return AssembledPrompt(system=system_blocks, messages=messages)
