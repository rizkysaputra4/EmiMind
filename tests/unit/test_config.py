"""Unit tests for Settings model loading and environment resolution."""

from __future__ import annotations

import pytest

from services.shared.config import Settings


def test_settings_custom_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMI_POSTGRES_DSN", "postgresql+asyncpg://user:pw@testdb:5432/test_db")
    monkeypatch.setenv("EMI_MINIO_ENDPOINT", "minio.test:9000")
    monkeypatch.setenv("EMI_CHAT_TOKEN_BUDGET", "8000")

    settings = Settings()
    assert settings.postgres_dsn == "postgresql+asyncpg://user:pw@testdb:5432/test_db"
    assert settings.minio_endpoint == "minio.test:9000"
    assert settings.chat_token_budget == 8000
