"""Unit tests for OCR: it raises OcrUnavailableError instead of returning empty text."""

from __future__ import annotations

import shutil
from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from services.extraction import ocr
from services.extraction.ocr import OcrUnavailableError, check_tesseract, ocr_image, ocr_page
from services.shared.config import get_settings


@pytest.fixture(autouse=True)
def _clear_tesseract_cache() -> None:
    check_tesseract.cache_clear()


def test_missing_binary_raises() -> None:
    img = Image.new("RGB", (200, 60), "white")
    with pytest.raises(OcrUnavailableError, match="not runnable"):
        ocr_image(img, tesseract_cmd="C:/definitely/not/tesseract.exe", tessdata_dir=None)


def test_missing_language_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr.pytesseract, "get_tesseract_version", lambda: "5.4.0")
    monkeypatch.setattr(ocr.pytesseract, "get_languages", lambda config="": ["eng", "osd"])
    with pytest.raises(OcrUnavailableError, match=r"language data missing: \['ind'\]"):
        check_tesseract("tesseract", None, "ind+eng")


def test_tesseract_runtime_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr, "check_tesseract", lambda *a, **k: "5.4.0")

    def _boom(*_a: object, **_k: object) -> str:
        raise ocr.pytesseract.TesseractError(1, "segfault")

    monkeypatch.setattr(ocr.pytesseract, "image_to_string", _boom)
    with pytest.raises(OcrUnavailableError, match="OCR failed"):
        ocr_image(Image.new("RGB", (10, 10)), tesseract_cmd="tesseract", tessdata_dir=None)


def test_tessdata_dir_with_spaces_rejected() -> None:
    with pytest.raises(OcrUnavailableError, match="must not contain spaces"):
        ocr._tess_config("C:/Program Files/tessdata")


def _tesseract_available() -> bool:
    cmd = get_settings().tesseract_cmd
    return Path(cmd).is_file() or shutil.which(cmd) is not None


@pytest.mark.skipif(not _tesseract_available(), reason="tesseract binary not installed")
def test_ocr_page_reads_rendered_text() -> None:
    doc = pymupdf.open()
    try:
        page = doc.new_page(width=700, height=100)
        page.insert_text((20, 60), "LAPORAN POSISI KEUANGAN KONSOLIDASIAN 2025", fontsize=18)
        text = ocr_page(page, dpi=200)
    finally:
        doc.close()
    assert "POSISI" in text.upper()
