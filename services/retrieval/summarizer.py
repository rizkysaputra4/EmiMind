"""Rolling conversation summarizer compressing older conversation turns."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from services.llm.factory import get_llm
from services.llm.types import Message, TextBlock
from services.retrieval.session_store import update_rolling_summary
from services.shared.logging import get_logger

log = get_logger("retrieval.summarizer")

SUMMARY_PROMPT = """You are a concise financial conversation summarizer.
Summarize the key facts, decisions, tickers, metrics, and conclusions discussed in the following conversation turns into ≤ 300 words.
Preserve all ticker names, numerical conclusions, and open questions. Omit pleasantries."""


async def refresh_rolling_summary(
    conn: AsyncConnection,
    session_id: UUID,
) -> str:
    """Compresses older turns (> 4 turns ago) into a concise rolling summary string."""
    res = await conn.execute(
        text(
            """
            SELECT role, content
            FROM conversation_turns
            WHERE session_id = :sid
            ORDER BY ts ASC;
            """
        ),
        {"sid": str(session_id)},
    )
    all_turns = list(res.mappings().all())

    # Only summarize if more than 4 turns exist
    if len(all_turns) <= 4:
        return ""

    older_turns = all_turns[:-4]
    turns_text = "\n\n".join(f"{t['role'].upper()}: {t['content']}" for t in older_turns)

    client = get_llm("utility")
    try:
        resp = await client.complete(
            system=[TextBlock(text=SUMMARY_PROMPT, cache_hint=True)],
            messages=[Message(role="user", blocks=[TextBlock(text=turns_text)])],
            max_output_tokens=350,
            temperature=0.0,
        )
        summary = resp.text.strip()
        await update_rolling_summary(conn, session_id, summary)
        log.info("Refreshed rolling summary", session_id=str(session_id), length=len(summary))
        return summary
    except Exception as e:
        log.warning("Rolling summary generation failed", error=str(e))
        return ""
