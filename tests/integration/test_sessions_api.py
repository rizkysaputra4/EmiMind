"""Integration tests for sessions persistence and turn history endpoints."""

from __future__ import annotations

import httpx
import pytest

from services.api.main import app
from services.shared.config import get_settings
from services.shared.db import create_pool


@pytest.mark.integration
async def test_sessions_crud_flow() -> None:
    settings = get_settings()
    pool = create_pool(settings.postgres_dsn)
    app.state.db_engine = pool

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Request magic link
        ml_res = await client.post(
            "/api/v1/auth/magic-link",
            json={"email": "pilot_user@fund.co.id"},
        )
        assert ml_res.status_code == 200
        debug_token = ml_res.json().get("debug_token")
        assert debug_token is not None

        # 2. Verify magic link
        v_res = await client.post(
            "/api/v1/auth/verify",
            json={"token": debug_token},
        )
        assert v_res.status_code == 200
        auth_data = v_res.json()
        session_token = auth_data["token"]

        headers = {"Authorization": f"Bearer {session_token}"}

        # 3. List sessions
        s_res = await client.get("/api/v1/sessions", headers=headers)
        assert s_res.status_code == 200
        sessions = s_res.json()
        assert isinstance(sessions, list)

    await pool.dispose()
