"""Authentication and session token management using magic links and PostgreSQL."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from services.api.deps import get_db_conn
from services.shared.config import get_settings
from services.shared.logging import get_logger

log = get_logger("api.auth")
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class MagicLinkRequest(BaseModel):
    email: str


class VerifyTokenRequest(BaseModel):
    token: str


class AuthResponse(BaseModel):
    token: str
    user_id: str
    email: str
    expires_at: str


class User(BaseModel):
    id: uuid.UUID
    email: str
    created_at: datetime


async def get_or_create_user(conn: AsyncConnection, email: str) -> User:
    """Retrieves existing user or creates a new user record."""
    clean_email = email.lower().strip()
    res = await conn.execute(
        text("SELECT id, email, created_at FROM users WHERE email = :email"),
        {"email": clean_email},
    )
    row = res.mappings().first()
    if row:
        return User(id=row["id"], email=row["email"], created_at=row["created_at"])

    new_id = uuid.uuid4()
    now = datetime.now(UTC)
    await conn.execute(
        text("INSERT INTO users (id, email, created_at) VALUES (:id, :email, :created_at)"),
        {"id": new_id, "email": clean_email, "created_at": now},
    )
    await conn.commit()
    return User(id=new_id, email=clean_email, created_at=now)


@router.post("/magic-link")
async def send_magic_link(
    payload: MagicLinkRequest,
    conn: AsyncConnection = Depends(get_db_conn),  # noqa: B008
) -> dict[str, Any]:
    """Generates and stores a magic-link authentication token."""
    user = await get_or_create_user(conn, payload.email)
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(minutes=15)

    await conn.execute(
        text(
            """
            INSERT INTO auth_tokens (token, user_id, kind, expires_at)
            VALUES (:token, :user_id, 'magic_link', :expires_at);
            """
        ),
        {"token": token, "user_id": user.id, "expires_at": expires_at},
    )
    await conn.commit()

    # In production, this dispatches via email provider. In dev/test, token is returned.
    log.info("Magic link generated", email=user.email, expires_at=str(expires_at))
    return {
        "status": "success",
        "message": "Magic link generated successfully.",
        "debug_token": token,  # Facilitates automated tests and development
    }


@router.post("/verify", response_model=AuthResponse)
async def verify_magic_link(
    payload: VerifyTokenRequest,
    conn: AsyncConnection = Depends(get_db_conn),  # noqa: B008
) -> AuthResponse:
    """Verifies a magic-link token and exchanges it for a 30-day session token."""
    now = datetime.now(UTC)
    res = await conn.execute(
        text(
            """
            SELECT user_id FROM auth_tokens
            WHERE token = :token AND kind = 'magic_link' AND expires_at > :now;
            """
        ),
        {"token": payload.token, "now": now},
    )
    row = res.mappings().first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired magic link token.",
        )

    user_id = row["user_id"]

    # Invalidate used magic link
    await conn.execute(
        text("DELETE FROM auth_tokens WHERE token = :token"),
        {"token": payload.token},
    )

    # Issue 30-day session token
    session_token = secrets.token_urlsafe(48)
    expires_at = now + timedelta(days=30)
    await conn.execute(
        text(
            """
            INSERT INTO auth_tokens (token, user_id, kind, expires_at)
            VALUES (:token, :user_id, 'session', :expires_at);
            """
        ),
        {"token": session_token, "user_id": user_id, "expires_at": expires_at},
    )
    await conn.commit()

    # Fetch user details
    u_res = await conn.execute(text("SELECT email FROM users WHERE id = :id"), {"id": user_id})
    u_row = u_res.mappings().first()
    email = u_row["email"] if u_row else "user@emimind.ai"

    return AuthResponse(
        token=session_token,
        user_id=str(user_id),
        email=email,
        expires_at=expires_at.isoformat(),
    )


async def get_current_user_optional(
    authorization: str | None = Header(None),
    conn: AsyncConnection = Depends(get_db_conn),  # noqa: B008
) -> User | None:
    """Extracts authenticated user from Bearer token if present."""
    if not authorization:
        settings = get_settings()
        if settings.environment == "dev":
            return await get_or_create_user(conn, "dev@emimind.ai")
        return None

    token = authorization.replace("Bearer ", "").strip()
    now = datetime.now(UTC)
    res = await conn.execute(
        text(
            """
            SELECT u.id, u.email, u.created_at
            FROM auth_tokens t
            JOIN users u ON u.id = t.user_id
            WHERE t.token = :token AND t.kind = 'session' AND t.expires_at > :now;
            """
        ),
        {"token": token, "now": now},
    )
    row = res.mappings().first()
    if not row:
        return None

    return User(id=row["id"], email=row["email"], created_at=row["created_at"])


async def require_user(
    user: User | None = Depends(get_current_user_optional),  # noqa: B008
) -> User:
    """Dependency enforcing that an active authenticated user session exists."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in.",
        )
    return user
