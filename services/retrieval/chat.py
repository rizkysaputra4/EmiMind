"""Full end-to-end chat orchestration pipeline for conversational financial research."""

from __future__ import annotations

import re
import time
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from services.llm.factory import get_llm
from services.llm.tools import TOOL_DEFS, TOOL_HANDLERS
from services.llm.types import Message, TextBlock, ToolResultBlock
from services.retrieval.budgeter import budget
from services.retrieval.classifier import classify
from services.retrieval.executor import execute_plan
from services.retrieval.planner import plan_retrieval
from services.retrieval.prompt_assembler import assemble_prompt
from services.retrieval.session_store import (
    append_turn,
    get_or_create_session,
    update_sticky_state,
)
from services.retrieval.summarizer import refresh_rolling_summary
from services.retrieval.turn_router import classify_turn_kind
from services.shared.logging import get_logger
from services.shared.types import (
    BBox,
    ChatCitation,
    ChatResponse,
    Ticker,
)

log = get_logger("retrieval.chat")

CITATION_REGEX = re.compile(
    r"\[([A-Z0-9]{2,10})-([A-Z0-9_]+)-([A-Z0-9_]+)(?:#p(\d+))?\]"
)


async def resolve_citations(
    conn: AsyncConnection,
    text_content: str,
) -> list[ChatCitation]:
    """Extracts citation tags from assistant text and resolves them to database entities."""
    citations: list[ChatCitation] = []
    seen_tags: set[str] = set()

    for match in CITATION_REGEX.finditer(text_content):
        tag = match.group(0)
        if tag in seen_tags:
            continue
        seen_tags.add(tag)

        ticker = match.group(1)
        doc_type_hint = match.group(2)
        fiscal_period = match.group(3)
        page_str = match.group(4)
        page_num = int(page_str) if page_str else 1

        # Look up document id in database
        d_res = await conn.execute(
            text(
                "SELECT id, minio_key FROM documents "
                "WHERE ticker = :ticker AND fiscal_period = :period LIMIT 1"
            ),
            {"ticker": ticker, "period": fiscal_period},
        )
        doc = d_res.mappings().first()
        doc_id = str(doc["id"]) if doc else "unknown"

        # Find matching fact or narrative bbox if page is specified
        fact_id: int | None = None
        chunk_id: str | None = None
        source_bbox: BBox | None = None
        snippet: str | None = None

        if doc_type_hint in ("FS", "PUBEX", "AR"):
            f_res = await conn.execute(
                text(
                    "SELECT id, source_bbox, concept_local, value_numeric, unit "
                    "FROM financial_facts "
                    "WHERE ticker = :ticker AND fiscal_period = :period AND source_page = :page LIMIT 1"
                ),
                {"ticker": ticker, "period": fiscal_period, "page": page_num},
            )
            f_row = f_res.mappings().first()
            if f_row:
                try:
                    fact_id = int(f_row["id"])
                except (ValueError, TypeError):
                    fact_id = None
                raw_bbox = f_row["source_bbox"]
                if isinstance(raw_bbox, (list, tuple)) and len(raw_bbox) == 4:
                    source_bbox = BBox(*raw_bbox)
                snippet = f"{f_row['concept_local']}: {f_row['value_numeric']} {f_row['unit']}"
            else:
                # Fallback to narrative chunk
                nc_res = await conn.execute(
                    text(
                        "SELECT id, text_original, text_en FROM narrative_chunks "
                        "WHERE ticker = :ticker AND fiscal_period = :period AND source_page = :page LIMIT 1"
                    ),
                    {"ticker": ticker, "period": fiscal_period, "page": page_num},
                )
                nc_row = nc_res.mappings().first()
                if nc_row:
                    chunk_id = str(nc_row["id"])
                    snippet = (nc_row["text_en"] or nc_row["text_original"])[:120]

        citations.append(
            ChatCitation(
                fact_id=fact_id,
                chunk_id=chunk_id,
                document_id=doc_id,
                ticker=ticker,
                fiscal_period=fiscal_period,
                page=page_num,
                bbox=source_bbox,
                snippet=snippet,
                citation_tag=tag,
            )
        )

    return citations


async def run_turn(
    conn: AsyncConnection,
    session_id: UUID | None,
    message: str,
    user_id: str | None = None,
    focus_ticker: str | None = None,
) -> ChatResponse:
    """Executes a single conversational turn through the full retrieval and LLM reasoning pipeline."""
    start_time = time.time()

    # 1. Retrieve or create session
    session = await get_or_create_session(conn, session_id=session_id, user_id=user_id)
    sticky = session.sticky_state

    # 2. Classify user query
    cls = await classify(message, session_state=sticky)
    if focus_ticker:
        cls.tickers = [Ticker(focus_ticker)]

    # 3. Classify turn transition kind and update sticky slots
    turn_kind = classify_turn_kind(sticky, cls)
    if turn_kind == "pivot":
        sticky.focus_ticker = cls.tickers[0] if cls.tickers else None
        if len(cls.tickers) > 1:
            sticky.peer_set = cls.tickers[1:]
        if cls.periods:
            sticky.focus_periods = cls.periods
    elif turn_kind == "drill":
        if not sticky.focus_ticker and cls.tickers:
            sticky.focus_ticker = cls.tickers[0]
        if cls.periods:
            sticky.focus_periods = cls.periods
        if cls.concepts:
            sticky.active_metrics = list(set(sticky.active_metrics + cls.concepts))
    elif turn_kind == "topic_change":
        sticky.focus_ticker = cls.tickers[0] if cls.tickers else None
        sticky.focus_periods = cls.periods
        sticky.peer_set = []
        sticky.active_metrics = []

    log.info(
        "Chat turn classified",
        intent=cls.intent.value,
        tickers=cls.tickers,
        periods=cls.periods,
        concepts=cls.concepts,
        turn_kind=turn_kind,
    )

    # 4. Plan retrieval steps
    plan = plan_retrieval(cls, sticky, original_query=message)

    # 5. Execute retrieval plan
    bundle = await execute_plan(conn, plan)
    log.info(
        "Retrieved evidence bundle",
        facts_count=len(bundle.facts),
        narrative_chunks_count=len(bundle.narrative),
        guidance_triples_count=len(bundle.guidance_triples),
    )

    # 6. Budget evidence tokens
    budgeted = await budget(bundle)

    # 7. Assemble provider-neutral prompt
    prompt = await assemble_prompt(
        bundle=budgeted,
        sticky=sticky,
        user_query=message,
        rolling_summary=session.rolling_summary,
    )
    log.info(
        "Prompt assembled for Reasoner LLM",
        system_blocks_count=len(prompt.system),
        message_turns_count=len(prompt.messages),
    )

    # 8. Record user turn in DB
    await append_turn(
        conn=conn,
        session_id=session.id,
        role="user",
        content=message,
    )

    # 9. Call Reasoner LLM with tools
    client = get_llm("reasoner")
    resp = await client.complete(
        system=prompt.system,
        messages=prompt.messages,
        tools=TOOL_DEFS,
        max_output_tokens=1024,
        temperature=0.2,
    )

    # 10. Handle Tool Use (max 1 round)
    if resp.stop_reason == "tool_use" and resp.tool_calls:
        tool_call = resp.tool_calls[0]
        handler = TOOL_HANDLERS.get(tool_call.name)
        tool_output = "Tool execution error"
        if handler:
            tool_output = await handler(conn, tool_call.arguments)

        # Append tool result turn and complete
        extended_messages = [
            *prompt.messages,
            Message(
                role="assistant",
                blocks=[TextBlock(text=resp.text or f"Executing tool: {tool_call.name}")],
            ),
            Message(
                role="user",
                blocks=[
                    ToolResultBlock(
                        tool_call_id=tool_call.id,
                        name=tool_call.name,
                        content=tool_output,
                    )
                ],
            ),
        ]
        resp = await client.complete(
            system=prompt.system,
            messages=extended_messages,
            tools=None,
            max_output_tokens=1024,
            temperature=0.2,
        )

    # 11. Resolve citations
    answer_text = resp.text
    citations = await resolve_citations(conn, answer_text)

    # 12. Build manifest and record assistant turn
    latency_ms = int((time.time() - start_time) * 1000)
    manifest = {
        "fact_ids": [f["id"] for f in bundle.facts if f.get("id")],
        "chunk_ids": [h.chunk_id for h in bundle.narrative],
        "turn_kind": turn_kind,
        "intent": cls.intent.value,
    }
    usage_dict = {
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
        "cost_usd": resp.usage.cost_usd,
    }

    await append_turn(
        conn=conn,
        session_id=session.id,
        role="assistant",
        content=answer_text,
        retrieval_manifest=manifest,
        token_usage=usage_dict,
        latency_ms=latency_ms,
    )

    # 13. Update session sticky state & check rolling summary
    await update_sticky_state(conn, session.id, sticky)
    await conn.commit()

    # Periodic rolling summary trigger (every 4 turns)
    turn_count_res = await conn.execute(
        text("SELECT count(*) FROM conversation_turns WHERE session_id = :sid"),
        {"sid": str(session.id)},
    )
    t_count = turn_count_res.scalar() or 0
    if t_count > 0 and t_count % 4 == 0:
        await refresh_rolling_summary(conn, session.id)
        await conn.commit()

    return ChatResponse(
        session_id=str(session.id),
        answer=answer_text,
        citations=citations,
        latency_ms=latency_ms,
        token_usage=usage_dict,
    )
