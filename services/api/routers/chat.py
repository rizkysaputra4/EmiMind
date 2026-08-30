"""Chat API router for conversational equity research."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncConnection

from services.api.deps import get_db
from services.retrieval.chat import run_turn
from services.shared.types import ChatRequest, ChatResponse

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat_turn(
    payload: ChatRequest,
    conn: AsyncConnection = Depends(get_db),
) -> ChatResponse:
    """Executes a conversational research turn with citations and evidence grounding."""
    session_uuid = UUID(payload.session_id) if payload.session_id else None
    return await run_turn(
        conn=conn,
        session_id=session_uuid,
        message=payload.message,
        focus_ticker=payload.focus_ticker,
    )
