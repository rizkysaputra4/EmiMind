"""Unit tests for index_pages_task with an in-memory DB and MinIO (no Postgres)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from services.extraction.ocr import OcrUnavailableError
from services.ingest.tasks import index_pages as ip
from tests.fixtures.m9.build_fixtures import build_fs_small, build_scanned
from tests.unit._fake_async_db import FakeConn, FakeEngine


class FakeMinio:
    def __init__(self) -> None:
        self.puts: list[str] = []

    def bucket_exists(self, _bucket: str) -> bool:
        return True

    def get_object(self, _bucket: str, key: str) -> Any:
        raise FileNotFoundError(f"NoSuchKey {key}")

    def put_object(self, _bucket: str, key: str, _data: Any, length: int, content_type: str) -> None:
        self.puts.append(key)


def _settings() -> SimpleNamespace:
    return SimpleNamespace(minio_bucket_raw="raw", postgres_dsn="unused", ocr_min_chars=50)


def _handler(source_url: str, prior_status: str | None = None) -> Any:
    def handle(sql: str, _p: dict[str, Any]) -> Any:
        if sql.startswith("SELECT id, doc_hash, minio_key, source_url FROM documents"):
            return [{"id": "d1", "doc_hash": "h1", "minio_key": "raw/x.pdf", "source_url": source_url}]
        if sql.startswith("SELECT status FROM worker_runs"):
            return [{"status": prior_status}] if prior_status else []
        return None

    return handle


def _statuses(conn: FakeConn) -> list[str]:
    return [p["status"] for _s, p in conn.sql_matching("INSERT INTO worker_runs")]


@pytest.mark.asyncio
async def test_index_pages_happy_path_batches_and_replaces_tables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = build_fs_small(tmp_path / "fs_small.pdf")
    monkeypatch.setattr(ip, "PAGE_COMMIT_BATCH", 3)
    conn = FakeConn(_handler(str(pdf)))
    minio = FakeMinio()

    result = await ip.index_pages_task(
        {"db_pool": FakeEngine(conn), "minio_client": minio, "settings": _settings()}, "d1"
    )

    assert result["status"] == "ok" and result["pages"] == 8
    upserts = conn.sql_matching("INSERT INTO document_pages")
    assert [p["page_index"] for _s, p in upserts] == list(range(1, 9))
    assert {p["text_source"] for _s, p in upserts} == {"pdf_text"}
    # re-index resets vectors only when the text changed
    assert "THEN NULL ELSE document_pages.embedding END" in upserts[0][0]
    # stale rows: pages beyond page_count and every old table grid of the doc
    delete_tables = [i for i, (s, _p) in enumerate(conn.calls) if s.startswith("DELETE FROM document_page_tables")]
    first_grid = next(i for i, (s, _p) in enumerate(conn.calls) if "INSERT INTO document_page_tables" in s)
    assert delete_tables and delete_tables[0] < first_grid
    assert conn.sql_matching("DELETE FROM document_pages WHERE doc_id = :id AND page_index > :n")
    assert result["tables"] == len(conn.sql_matching("INSERT INTO document_page_tables")) > 0
    # 8 pages at 3 per batch -> commits at pages 3 and 6, plus the later phases
    assert conn.commits >= 4
    assert _statuses(conn) == ["running", "ok"]
    assert sum(k.startswith("thumbnails/d1/") for k in minio.puts) == 8


@pytest.mark.asyncio
async def test_index_pages_skips_when_already_ok(tmp_path: Path) -> None:
    conn = FakeConn(_handler(str(tmp_path / "missing.pdf"), prior_status="ok"))
    out = await ip.index_pages_task(
        {"db_pool": FakeEngine(conn), "minio_client": FakeMinio(), "settings": _settings()}, "d1"
    )
    assert out == {"status": "already_ok"}
    assert not conn.sql_matching("INSERT INTO worker_runs")


@pytest.mark.asyncio
async def test_index_pages_failure_records_failed_run(tmp_path: Path) -> None:
    conn = FakeConn(_handler(str(tmp_path / "missing.pdf")))
    with pytest.raises(FileNotFoundError):
        await ip.index_pages_task(
            {"db_pool": FakeEngine(conn), "minio_client": FakeMinio(), "settings": _settings()}, "d1"
        )
    runs = conn.sql_matching("INSERT INTO worker_runs")
    assert [p["status"] for _s, p in runs] == ["running", "failed"]
    assert "FileNotFoundError" in runs[-1][1]["error"]
    assert conn.rollbacks == 1


@pytest.mark.asyncio
async def test_scanned_pages_ocr_failure_marks_ocr_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = build_scanned(tmp_path / "scanned.pdf")

    def _no_tesseract(_page: Any, *_a: Any, **_k: Any) -> str:
        raise OcrUnavailableError("Tesseract not runnable")

    monkeypatch.setattr(ip, "ocr_page", _no_tesseract)
    conn = FakeConn(_handler(str(pdf)))
    result = await ip.index_pages_task(
        {"db_pool": FakeEngine(conn), "minio_client": FakeMinio(), "settings": _settings()}, "d1"
    )
    sources = [p["text_source"] for _s, p in conn.sql_matching("INSERT INTO document_pages")]
    assert sources == ["ocr_failed", "ocr_failed"]
    assert result["ocr_failed_pages"] == [1, 2]
    assert not conn.sql_matching("INSERT INTO document_page_tables")  # OCR pages get no grid


def test_page_text_with_ocr_short_output_is_ocr_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ip, "ocr_page", lambda _page: "12")
    text, source, err = ip._page_text_with_ocr(None, "", 50)  # type: ignore[arg-type]
    assert source == "ocr_failed" and text == "12" and err and "(< 50)" in err

    monkeypatch.setattr(ip, "ocr_page", lambda _page: "Laporan posisi keuangan " * 5)
    text, source, err = ip._page_text_with_ocr(None, "", 50)  # type: ignore[arg-type]
    assert source == "ocr" and err is None and text.startswith("Laporan")


def test_nul_characters_are_stripped_before_storage() -> None:
    # Postgres TEXT/JSONB reject U+0000; TAPG FY2025 had one in a Camelot cell
    nul = chr(0)
    assert ip._strip_nul(f"Kas{nul} 1.000") == "Kas 1.000"
    cells = [{"row": 0, "col": 0, "text": f"a{nul}b", "value": None}, {"row": 0, "col": 1}]
    cleaned = ip._clean_cells(cells)
    assert cleaned == [{"row": 0, "col": 0, "text": "ab", "value": None}, {"row": 0, "col": 1}]
    assert chr(92) + "u0000" not in json.dumps(cleaned)
