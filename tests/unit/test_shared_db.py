"""Unit tests for database engine factory and transaction manager."""

from __future__ import annotations

from services.shared.db import create_pool


def test_create_pool_lazy_init() -> None:
    # Engine creation should succeed without connecting eagerly
    engine = create_pool("postgresql+asyncpg://dummy:dummy@localhost:5432/dummy")
    assert engine is not None
    assert engine.url.render_as_string(hide_password=False) == (
        "postgresql+asyncpg://dummy:dummy@localhost:5432/dummy"
    )
