"""Integration tests for FastAPI endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_healthz(async_client: AsyncClient) -> None:
    response = await async_client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


@pytest.mark.asyncio
async def test_chat_turn(async_client: AsyncClient) -> None:
    response = await async_client.post(
        "/api/v1/chat",
        json={"message": "Why did BMRI profit increase?", "focus_ticker": "BMRI"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert len(data["answer"]) > 0
    assert isinstance(data["citations"], list)


@pytest.mark.asyncio
async def test_screener_stub(async_client: AsyncClient) -> None:
    response = await async_client.post(
        "/api/v1/screener",
        json={"query": "NIM > 5%"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "dsl" in data
    assert "rows" in data
    assert "table_md" in data


@pytest.mark.asyncio
async def test_upload_invalid_filetype(async_client: AsyncClient) -> None:
    files = {"file": ("test.txt", b"not a pdf content", "text/plain")}
    data = {
        "ticker": "BMRI",
        "doc_type": "FS_QUARTERLY",
        "fiscal_period": "2024Q4",
        "language": "id",
    }
    response = await async_client.post("/api/v1/upload", data=data, files=files)
    assert response.status_code == 415


@pytest.mark.asyncio
async def test_upload_invalid_ticker(async_client: AsyncClient) -> None:
    files = {"file": ("test.pdf", b"%PDF-1.4 dummy", "application/pdf")}
    data = {
        "ticker": "invalid_ticker",
        "doc_type": "FS_QUARTERLY",
        "fiscal_period": "2024Q4",
        "language": "id",
    }
    response = await async_client.post("/api/v1/upload", data=data, files=files)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_upload_success(async_client: AsyncClient) -> None:
    files = {"file": ("sample.pdf", b"%PDF-1.4 dummy valid content", "application/pdf")}
    data = {
        "ticker": "BMRI",
        "doc_type": "FS_QUARTERLY",
        "fiscal_period": "2024Q4",
        "language": "id",
    }
    response = await async_client.post("/api/v1/upload", data=data, files=files)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "raw"
    assert res_data["deduplicated"] is False
    assert "document_id" in res_data
