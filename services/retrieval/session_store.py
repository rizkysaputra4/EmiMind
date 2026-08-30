"""Chat session state management and conversation turns persistence."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from services.shared.types import FiscalPeriod, Ticker


class StickyState(BaseModel):
    """Sticky context parameters retained across conversational turns."""

    focus_ticker: Ticker | None = None
    focus_periods: list[FiscalPeriod] = Field(default_factory=list)
    peer_set: list[Ticker] = Field(default_factory=list)
    active_metrics: list[str] = Field(default_factory=list)
    last_claim_node_id: int | None = None


class ChatSession(BaseModel):
    """Chat session database entity."""

    id: UUID
    user_id: str | None = None
    title: str | None = None
    sticky_state: StickyState = Field(default_factory=StickyState)
    rolling_summary: str = ""
    created_at: datetime
    last_activity_at: datetime


class ConversationTurn(BaseModel):
    """Single conversational turn entity."""

    id: int
    session_id: UUID
    role: Literal["user", "assistant", "tool"]
    content: str
    retrieval_manifest: dict[str, Any] | None = None
    token_usage: dict[str, Any] | None = None
    latency_ms: int | None = None
    ts: datetime


async def get_or_create_session(
    conn: AsyncConnection,
    session_id: UUID | None = None,
    user_id: str | None = None,
) -> ChatSession:
    """Retrieves an existing session or initializes a new one in PostgreSQL."""
    if session_id is not None:
        res = await conn.execute(
            text(
                "SELECT id, user_id, title, sticky_state, rolling_summary, created_at, last_activity_at "
                "FROM chat_sessions WHERE id = :id"
            ),
            {"id": str(session_id)},
        )
        row = res.mappings().first()
        if row:
            raw_sticky = row["sticky_state"]
            sticky_obj = (
                StickyState.model_validate(raw_sticky)
                if isinstance(raw_sticky, dict)
                else StickyState()
            )
            return ChatSession(
                id=row["id"],
                user_id=row["user_id"],
                title=row["title"],
                sticky_state=sticky_obj,
                rolling_summary=row["rolling_summary"] or "",
                created_at=row["created_at"],
                last_activity_at=row["last_activity_at"],
            )

    new_id = session_id or uuid4()
    now = datetime.utcnow()
    await conn.execute(
        text(
            """
            INSERT INTO chat_sessions (id, user_id, sticky_state, rolling_summary, created_at, last_activity_at)
            VALUES (:id, :user_id, '{}', '', :now, :now)
            ON CONFLICT (id) DO NOTHING;
            """
        ),
        {"id": str(new_id), "user_id": user_id, "now": now},
    )

    return ChatSession(
        id=new_id,
        user_id=user_id,
        sticky_state=StickyState(),
        rolling_summary="",
        created_at=now,
        last_activity_at=now,
    )


async def append_turn(
    conn: AsyncConnection,
    session_id: UUID,
    role: Literal["user", "assistant", "tool"],
    content: str,
    retrieval_manifest: dict[str, Any] | None = None,
    token_usage: dict[str, Any] | None = None,
    latency_ms: int | None = None,
) -> ConversationTurn:
    """Appends a conversation turn to PostgreSQL and updates session last_activity_at."""
    res = await conn.execute(
        text(
            """
            INSERT INTO conversation_turns (
                session_id, role, content, retrieval_manifest, token_usage, latency_ms, ts
            ) VALUES (
                :sid, :role, :content, CAST(:manifest AS jsonb), CAST(:usage AS jsonb), :latency, now()
            )
            RETURNING id, session_id, role, content, retrieval_manifest, token_usage, latency_ms, ts;
            """
        ),
        {
            "sid": str(session_id),
            "role": role,
            "content": content,
            "manifest": json.dumps(retrieval_manifest) if retrieval_manifest else None,
            "usage": json.dumps(token_usage) if token_usage else None,
            "latency": latency_ms,
        },
    )
    row = res.mappings().one()

    await conn.execute(
        text("UPDATE chat_sessions SET last_activity_at = now() WHERE id = :id"),
        {"id": str(session_id)},
    )

    return ConversationTurn(
        id=row["id"],
        session_id=row["session_id"],
        role=row["role"],
        content=row["content"],
        retrieval_manifest=row["retrieval_manifest"],
        token_usage=row["token_usage"],
        latency_ms=row["latency_ms"],
        ts=row["ts"],
    )


async def update_sticky_state(
    conn: AsyncConnection,
    session_id: UUID,
    state: StickyState,
) -> None:
    """Updates the sticky state JSONB column for a session."""
    await conn.execute(
        text(
            """
            UPDATE chat_sessions
            SET sticky_state = CAST(:state AS jsonb), last_activity_at = now()
            WHERE id = :id;
            """
        ),
        {"id": str(session_id), "state": state.model_dump_json()},
    )


async def update_rolling_summary(
    conn: AsyncConnection,
    session_id: UUID,
    summary: str,
) -> None:
    """Updates the rolling summary text for a session."""
    await conn.execute(
        text(
            "UPDATE chat_sessions SET rolling_summary = :summary, last_activity_at = now() WHERE id = :id"
        ),
        {"id": str(session_id), "summary": summary},
    )


async def recent_turns(
    conn: AsyncConnection,
    session_id: UUID,
    n: int = 6,
) -> list[ConversationTurn]:
    """Retrieves the last n conversational turns for a session in chronological order."""
    res = await conn.execute(
        text(
            """
            SELECT id, session_id, role, content, retrieval_manifest, token_usage, latency_ms, ts
            FROM conversation_turns
            WHERE session_id = :sid
            ORDER BY ts DESC
            LIMIT :n;
            """
        ),
        {"sid": str(session_id), "n": n},
    )
    rows = list(res.mappings().all())
    rows.reverse()
    return [
        ConversationTurn(
            id=r["id"],
            session_id=r["session_id"],
            role=r["role"],
            content=r["content"],
            retrieval_manifest=r["retrieval_manifest"],
            token_usage=r["token_usage"],
            latency_ms=r["latency_ms"],
            ts=r["ts"],
        )
        for r in rows
    ]
