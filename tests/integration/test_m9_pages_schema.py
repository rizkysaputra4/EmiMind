"""Integration test for document_pages and document_page_tables schema (Migration 023)."""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from services.mcp.server import get_engine


@pytest.mark.integration
@pytest.mark.asyncio
async def test_m9_pages_schema_and_cascade() -> None:
    engine = get_engine()
    doc_id = str(uuid.uuid4())
    ticker = "TEST_PAGES"
    period = "2025Q4"

    async with engine.connect() as conn:
        # Clean up any leftover test data
        await conn.execute(text("DELETE FROM documents WHERE id = :d"), {"d": doc_id})

        # 1. Insert parent document
        await conn.execute(
            text(
                """
                INSERT INTO documents (
                    id, ticker, doc_type, period_end, fiscal_period, language,
                    source_url, minio_key, doc_hash, page_count, status
                ) VALUES (
                    :id, :ticker, 'FS_ANNUAL', '2025-12-31', :period, 'id',
                    'test://pages_schema', 'test/pages_key', :hash, 2, 'raw'
                );
                """
            ),
            {"id": doc_id, "ticker": ticker, "period": period, "hash": f"hash_{doc_id}"},
        )

        # 2. Insert into document_pages
        await conn.execute(
            text(
                """
                INSERT INTO document_pages (
                    doc_id, page_index, page_label, page_text, text_source, language, image_key
                ) VALUES (
                    :doc_id, 1, '1', 'Laporan Posisi Keuangan Konsolidasian Aset Lancar', 'pdf_text', 'id', 'thumbnails/p1.webp'
                );
                """
            ),
            {"doc_id": doc_id},
        )

        # Check that tsv was generated
        tsv_res = await conn.execute(
            text("SELECT tsv IS NOT NULL FROM document_pages WHERE doc_id = :doc_id AND page_index = 1"),
            {"doc_id": doc_id},
        )
        assert tsv_res.scalar() is True

        # 3. Insert into document_page_tables
        cells_data = [
            {"row": 0, "col": 0, "text": "Jumlah Aset", "value": 1000000.0, "bbox": [10.0, 20.0, 100.0, 40.0], "confidence": 0.95}
        ]
        await conn.execute(
            text(
                """
                INSERT INTO document_page_tables (
                    doc_id, page_index, table_index, extraction_method, confidence, unit_hint, cells
                ) VALUES (
                    :doc_id, 1, 0, 'camelot_lattice', 0.95, 'IDR_MILLIONS', CAST(:cells AS jsonb)
                );
                """
            ),
            {"doc_id": doc_id, "cells": json.dumps(cells_data)},
        )

        # 4. Verify uniqueness on document_pages (doc_id, page_index)
        with pytest.raises(IntegrityError):
            async with conn.begin_nested():
                await conn.execute(
                    text(
                        """
                        INSERT INTO document_pages (
                            doc_id, page_index, page_label, page_text, text_source
                        ) VALUES (
                            :doc_id, 1, 'duplicate', 'Text', 'pdf_text'
                        );
                        """
                    ),
                    {"doc_id": doc_id},
                )

        # 5. Verify uniqueness on document_page_tables (doc_id, page_index, table_index)
        with pytest.raises(IntegrityError):
            async with conn.begin_nested():
                await conn.execute(
                    text(
                        """
                        INSERT INTO document_page_tables (
                            doc_id, page_index, table_index, extraction_method, confidence, cells
                        ) VALUES (
                            :doc_id, 1, 0, 'camelot_lattice', 0.90, '[]'::jsonb
                        );
                        """
                    ),
                    {"doc_id": doc_id},
                )

        # 6. Verify Cascade Delete: deleting documents row cascades to both tables
        await conn.execute(text("DELETE FROM documents WHERE id = :doc_id"), {"doc_id": doc_id})

        pages_count = await conn.execute(
            text("SELECT count(*) FROM document_pages WHERE doc_id = :doc_id"),
            {"doc_id": doc_id},
        )
        assert pages_count.scalar() == 0

        tables_count = await conn.execute(
            text("SELECT count(*) FROM document_page_tables WHERE doc_id = :doc_id"),
            {"doc_id": doc_id},
        )
        assert tables_count.scalar() == 0

        await conn.commit()
