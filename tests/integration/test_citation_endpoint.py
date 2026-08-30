"""Integration tests for citation resolution, PDF thumbnail rendering, and report endpoints."""

from __future__ import annotations

from urllib.parse import quote

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_citation_endpoints_live(async_client: AsyncClient) -> None:
    # 1. Resolve detail with URL-encoded tag
    encoded_tag = quote("[BMRI-FS-2024Q4#p1]")
    res = await async_client.get(f"/api/v1/citation/{encoded_tag}")
    assert res.status_code == 200
    data = res.json()
    assert data["ticker"] == "BMRI"
    assert data["fiscal_period"] == "2024Q4"
    assert data["page"] == 1
    assert data["document"] is not None

    # 2. Report citation
    report_res = await async_client.post(
        "/api/v1/citation/report",
        json={
            "citation": "[BMRI-FS-2024Q4#p1]",
            "feedback": "Value matches, test report verification.",
        },
    )
    assert report_res.status_code == 200
    assert report_res.json()["status"] == "recorded"

    # 3. Malformed citation returns 400
    bad_res = await async_client.get("/api/v1/citation/invalid_citation_format")
    assert bad_res.status_code == 400
