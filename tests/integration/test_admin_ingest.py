"""Integration tests for admin ingest monitoring dashboard."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.integration
async def test_admin_ingest_dashboard(async_client: AsyncClient) -> None:
    res = await async_client.get("/api/v1/admin/ingest")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "documents" in data
    assert "total_financial_facts" in data
    assert "total_narrative_chunks" in data
    assert "unmapped_labels_queue" in data
