"""Integration test for inspect_document real metadata registration."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text

from services.mcp.server import get_engine, inspect_document
from services.mcp.types import InspectionStatus
from tests.fixtures.m9.build_fixtures import build_fs_small


@pytest.mark.integration
@pytest.mark.asyncio
async def test_m9_inspect_real_metadata(tmp_path: Path) -> None:
    engine = get_engine()

    # 1. Seed test issuer profile
    async with engine.connect() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO issuer_profile (ticker, name, sector, sub_sector)
                VALUES ('XXXX', 'PT XXXX Tbk', 'BANK', 'BANK')
                ON CONFLICT (ticker) DO UPDATE SET sector = 'BANK';
                """
            )
        )
        await conn.commit()

    # 2. Build synthetic fixture
    pdf_path = tmp_path / "XXXX_2025_TW2_RDF_fs_small.pdf"
    build_fs_small(pdf_path)

    # 3. Call inspect_document
    res = await inspect_document(str(pdf_path), ticker="XXXX")
    assert res.status == InspectionStatus.AUTHORIZED
    assert res.fiscal_period == "2025Q2"
    assert res.doc_id is not None

    # 4. Verify DB row
    async with engine.connect() as conn:
        doc_res = await conn.execute(
            text("SELECT period_end, page_count, fiscal_period FROM documents WHERE id = :doc_id"),
            {"doc_id": res.doc_id},
        )
        row = doc_res.mappings().first()
        assert row is not None
        assert row["period_end"] == date(2025, 6, 30)
        assert row["page_count"] == 8
        assert row["fiscal_period"] == "2025Q2"
