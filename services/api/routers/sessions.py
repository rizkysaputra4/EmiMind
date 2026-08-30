"""Sessions management and conversation turn history API router."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from services.api.auth import User, require_user
from services.api.deps import get_db_conn
from services.shared.logging import get_logger

log = get_logger("api.sessions")
router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


class SessionSummary(BaseModel):
    id: str
    title: str
    last_activity_at: str
    created_at: str
    turn_count: int
    last_message_preview: str = ""
    sticky_state: dict[str, Any] = Field(default_factory=dict)


class SessionTurn(BaseModel):
    id: int
    role: str
    content: str
    retrieval_manifest: dict[str, Any] | None = None
    token_usage: dict[str, Any] | None = None
    latency_ms: int | None = None
    ts: str


class RenameSessionRequest(BaseModel):
    title: str


@router.get("", response_model=list[SessionSummary])
async def list_sessions(
    user: User = Depends(require_user),
    conn: AsyncConnection = Depends(get_db_conn),
) -> list[SessionSummary]:
    """Lists all conversation sessions for the authenticated user, ordered by recent activity."""
    res = await conn.execute(
        text(
            """
            SELECT s.id, s.title, s.sticky_state, s.created_at, s.last_activity_at,
                   count(t.id) AS turn_count,
                   (
                     SELECT content FROM conversation_turns
                     WHERE session_id = s.id ORDER BY id DESC LIMIT 1
                   ) AS last_content
            FROM chat_sessions s
            LEFT JOIN conversation_turns t ON t.session_id = s.id
            WHERE s.user_id = :user_id OR s.user_id = 'default'
            GROUP BY s.id
            ORDER BY s.last_activity_at DESC;
            """
        ),
        {"user_id": str(user.id)},
    )
    rows = res.mappings().all()

    sessions: list[SessionSummary] = []
    for r in rows:
        last_c = r["last_content"] or ""
        preview = (last_c[:90] + "...") if len(last_c) > 90 else last_c
        sessions.append(
            SessionSummary(
                id=str(r["id"]),
                title=r["title"] or "Untitled Research Session",
                last_activity_at=r["last_activity_at"].isoformat() if r["last_activity_at"] else "",
                created_at=r["created_at"].isoformat() if r["created_at"] else "",
                turn_count=int(r["turn_count"] or 0),
                last_message_preview=preview,
                sticky_state=r["sticky_state"] or {},
            )
        )

    return sessions


@router.get("/{session_id}/turns", response_model=list[SessionTurn])
async def get_session_turns(
    session_id: uuid.UUID,
    user: User = Depends(require_user),
    conn: AsyncConnection = Depends(get_db_conn),
) -> list[SessionTurn]:
    """Retrieves full chronological turn history and manifests for a given session."""
    res = await conn.execute(
        text(
            """
            SELECT id, role, content, retrieval_manifest, token_usage, latency_ms, ts
            FROM conversation_turns
            WHERE session_id = :session_id
            ORDER BY id ASC;
            """
        ),
        {"session_id": session_id},
    )
    rows = res.mappings().all()

    turns: list[SessionTurn] = []
    for r in rows:
        turns.append(
            SessionTurn(
                id=r["id"],
                role=r["role"],
                content=r["content"],
                retrieval_manifest=r["retrieval_manifest"],
                token_usage=r["token_usage"],
                latency_ms=r["latency_ms"],
                ts=r["ts"].isoformat() if r["ts"] else "",
            )
        )

    return turns


@router.post("/{session_id}/rename")
async def rename_session(
    session_id: uuid.UUID,
    payload: RenameSessionRequest,
    user: User = Depends(require_user),
    conn: AsyncConnection = Depends(get_db_conn),
) -> dict[str, str]:
    """Renames a session title."""
    clean_title = payload.title.strip()
    if not clean_title:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Title cannot be empty."
        )

    await conn.execute(
        text("UPDATE chat_sessions SET title = :title WHERE id = :id"),
        {"id": session_id, "title": clean_title},
    )
    await conn.commit()
    return {"status": "success", "title": clean_title}


@router.delete("/{session_id}")
async def delete_session(
    session_id: uuid.UUID,
    user: User = Depends(require_user),
    conn: AsyncConnection = Depends(get_db_conn),
) -> dict[str, str]:
    """Deletes a session and its associated conversation turns."""
    await conn.execute(
        text("DELETE FROM conversation_turns WHERE session_id = :id"), {"id": session_id}
    )
    await conn.execute(text("DELETE FROM chat_sessions WHERE id = :id"), {"id": session_id})
    await conn.commit()
    return {"status": "success", "message": "Session deleted."}
