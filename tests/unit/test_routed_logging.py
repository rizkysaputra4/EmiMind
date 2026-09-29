"""The ROUTED log row records what was served, so the gate can compute tokens server-side."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from eval.deep_extraction_gate import tokens_from_routed_logs
from services.mcp.services.routing import get_routed_pages
from services.retrieval.page_router import RoutedSpan


class _Result:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self._data = data

    def mappings(self) -> _Result:
        return self

    def first(self) -> dict[str, Any] | None:
        return self._data[0] if self._data else None

    def all(self) -> list[dict[str, Any]]:
        return self._data


def _engine(pages: list[dict[str, Any]], tables: list[dict[str, Any]]) -> MagicMock:
    async def execute(sql: Any, params: dict[str, Any] | None = None) -> _Result:
        s = str(sql)
        if "FROM documents WHERE id" in s:
            return _Result([{"id": "d1", "ticker": "LSIP", "fiscal_period": "2025Q3",
                             "doc_type": "FS_QUARTERLY", "minio_key": "raw/x/LSIP.pdf",
                             "doc_hash": "h"}])  # fmt: skip
        if "FROM issuer_profile" in s:
            return _Result([{"sector": "CPO"}])
        if "FROM document_pages" in s:
            return _Result(pages)
        if "FROM document_page_tables" in s:
            return _Result(tables)
        return _Result([])

    conn = AsyncMock()
    conn.execute.side_effect = execute

    class _Ctx:
        async def __aenter__(self) -> AsyncMock:
            return conn

        async def __aexit__(self, *args: Any) -> None:
            return None

    engine = MagicMock()
    engine.connect.return_value = _Ctx()
    return engine


async def test_routed_log_records_served_chars_and_images() -> None:
    pages = [
        {"page_index": 4, "page_label": "1", "text_source": "pdf_text",
         "page_text": "a" * 4000, "image_key": "thumbnails/d1/4.webp"},
        {"page_index": 5, "page_label": "2", "text_source": "pdf_text",
         "page_text": "b" * 2000, "image_key": None},
    ]  # fmt: skip
    tables = [{"page_index": 4, "table_index": 0, "extraction_method": "camelot_lattice",
               "confidence": 0.9, "unit_hint": "IDR_MN",
               "cells": [{"row": 0, "col": 0, "text": "Kas", "value": None, "bbox": None}]}]  # fmt: skip
    log_fn = AsyncMock()
    minio = MagicMock()
    minio.presigned_get_object.return_value = "https://minio/4.webp"
    router = AsyncMock(return_value=[RoutedSpan(start_page=4, end_page=5, score=0.1, seed_page=4,
                                                pages=[4, 5])])  # fmt: skip

    res = await get_routed_pages(
        "d1", "BALANCE_SHEET", engine=_engine(pages, tables), router_fn=router,
        minio_getter=lambda _s: minio, log_event_fn=log_fn, include_images=True,
    )  # fmt: skip

    assert res.total_pages_returned == 2
    assert res.pages[0].image_url == "https://minio/4.webp"
    meta = log_fn.await_args.kwargs["metadata"]
    assert log_fn.await_args.kwargs["action"] == "ROUTED"
    assert meta["pages"] == [4, 5]
    assert meta["text_chars"] == 6000
    assert meta["table_chars"] == len(res.pages[0].tables[0].model_dump_json())
    assert meta["chars"] == meta["text_chars"] + meta["table_chars"]
    assert meta["images"] == 1
    tokens, _ = tokens_from_routed_logs([meta])
    assert tokens == meta["chars"] // 4 + 1600


async def test_empty_routing_is_logged_with_zero_chars() -> None:
    log_fn = AsyncMock()
    res = await get_routed_pages(
        "d1", "BALANCE_SHEET", engine=_engine([], []), router_fn=AsyncMock(return_value=[]),
        minio_getter=lambda _s: MagicMock(), log_event_fn=log_fn,
    )  # fmt: skip
    assert res.total_pages_returned == 0
    meta = log_fn.await_args.kwargs["metadata"]
    assert meta["chars"] == 0 and meta["images"] == 0


async def test_default_serves_text_grids_without_images() -> None:
    pages = [{"page_index": 4, "page_label": "1", "text_source": "pdf_text",
              "page_text": "Kas 5 1.000", "image_key": "thumbnails/d1/4.webp"}]  # fmt: skip
    tables = [{"page_index": 4, "table_index": 0, "extraction_method": "camelot_stream",
               "confidence": 0.85, "unit_hint": "IDR_MN",
               "cells": [{"row": 0, "col": 0, "text": "Kas", "value": None, "bbox": [1, 2, 3, 4]},
                         {"row": 0, "col": 2, "text": "1.000", "value": 1000.0,
                          "bbox": [5, 6, 7, 8], "confidence": 0.85},
                         {"row": 1, "col": 1, "text": "5", "value": None}]}]  # fmt: skip
    log_fn = AsyncMock()
    minio = MagicMock()
    router = AsyncMock(return_value=[RoutedSpan(start_page=4, end_page=4, score=0.1, seed_page=4,
                                                pages=[4])])  # fmt: skip

    res = await get_routed_pages(
        "d1", "BALANCE_SHEET", engine=_engine(pages, tables), router_fn=router,
        minio_getter=lambda _s: minio, log_event_fn=log_fn,
    )  # fmt: skip

    page = res.pages[0]
    assert page.image_url is None
    minio.presigned_get_object.assert_not_called()
    tbl = page.tables[0]
    assert tbl.rows == [["Kas", "", "1.000"], ["", "5", ""]]
    assert (tbl.table_index, tbl.unit_hint, tbl.confidence) == (0, "IDR_MN", 0.85)
    dumped = tbl.model_dump_json()
    assert "bbox" not in dumped and "value" not in dumped
    assert log_fn.await_args.kwargs["metadata"]["images"] == 0


async def test_excluded_pages_are_listed_but_not_served() -> None:
    pages = [{"page_index": 4, "page_label": "1", "text_source": "pdf_text",
              "page_text": "Kas 1.000", "image_key": "thumbnails/d1/4.webp"},
             {"page_index": 5, "page_label": "2", "text_source": "pdf_text",
              "page_text": "Piutang 2.000", "image_key": "thumbnails/d1/5.webp"}]  # fmt: skip
    tables = [{"page_index": 4, "table_index": 0, "extraction_method": "camelot_stream",
               "confidence": 0.9, "unit_hint": None,
               "cells": [{"row": 0, "col": 0, "text": "Kas"}]}]  # fmt: skip
    log_fn = AsyncMock()
    minio = MagicMock()
    minio.presigned_get_object.return_value = "https://minio/x.webp"
    router = AsyncMock(return_value=[RoutedSpan(start_page=4, end_page=5, score=0.1, seed_page=4,
                                                pages=[4, 5])])  # fmt: skip

    res = await get_routed_pages(
        "d1", "BALANCE_SHEET", engine=_engine(pages, tables), router_fn=router,
        minio_getter=lambda _s: minio, log_event_fn=log_fn, include_images=True,
        exclude_pages=[4],
    )  # fmt: skip

    p4, p5 = res.pages
    assert (p4.page_index, p4.page_label, p4.already_served) == (4, "1", True)
    assert p4.page_text == "" and p4.tables == [] and p4.image_url is None
    assert (p5.already_served, p5.page_text) == (False, "Piutang 2.000")
    meta = log_fn.await_args.kwargs["metadata"]
    assert meta["pages"] == [4, 5] and meta["excluded_pages"] == [4]
    assert meta["chars"] == len("Piutang 2.000") and meta["images"] == 1
