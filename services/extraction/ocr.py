"""Pure OCR extraction utilities (Tesseract via pytesseract). Fails loudly, never returns ''."""

from __future__ import annotations

import functools
import io
from pathlib import Path

import pymupdf
import pytesseract
from PIL import Image

from services.shared.config import get_settings
from services.shared.errors import ExtractionError

DEFAULT_OCR_LANG = "ind+eng"
_OCR_TIMEOUT_S = 180


class OcrUnavailableError(ExtractionError):
    """Raised when Tesseract cannot run (binary missing, language data missing, crash, timeout)."""


def _tess_config(tessdata_dir: str | None) -> str:
    if not tessdata_dir:
        return ""
    # pytesseract shlex-splits config (posix on some calls, non-posix on Windows for others), so
    # neither quotes nor backslashes survive both; an unquoted forward-slash path does.
    posix_dir = Path(tessdata_dir).as_posix()
    if " " in posix_dir:
        raise OcrUnavailableError(
            f"EMI_TESSDATA_DIR must not contain spaces (got {tessdata_dir!r})."
        )
    return f"--tessdata-dir {posix_dir}"


@functools.lru_cache(maxsize=8)
def check_tesseract(tesseract_cmd: str, tessdata_dir: str | None, lang: str) -> str:
    """Verifies the binary runs and every requested language is installed; returns the version."""
    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    try:
        version = str(pytesseract.get_tesseract_version())
        available = set(pytesseract.get_languages(config=_tess_config(tessdata_dir)))
    except (pytesseract.TesseractNotFoundError, OSError, RuntimeError) as exc:
        raise OcrUnavailableError(
            f"Tesseract not runnable at '{tesseract_cmd}': {exc}. Set EMI_TESSERACT_CMD."
        ) from exc
    except pytesseract.TesseractError as exc:
        raise OcrUnavailableError(f"Tesseract failed listing languages: {exc}") from exc

    missing = [code for code in lang.split("+") if code and code not in available]
    if missing:
        raise OcrUnavailableError(
            f"Tesseract language data missing: {missing} (tessdata_dir={tessdata_dir!r}, "
            f"available={sorted(available)}). Set EMI_TESSDATA_DIR."
        )
    return version


def ocr_image(
    image: Image.Image,
    lang: str = DEFAULT_OCR_LANG,
    *,
    tesseract_cmd: str | None = None,
    tessdata_dir: str | None = None,
) -> str:
    """Runs Tesseract on a PIL image; raises OcrUnavailableError on any Tesseract failure."""
    settings = get_settings()
    cmd = tesseract_cmd or settings.tesseract_cmd
    tdir = tessdata_dir if tessdata_dir is not None else settings.tessdata_dir
    check_tesseract(cmd, tdir, lang)
    pytesseract.pytesseract.tesseract_cmd = cmd
    try:
        text = pytesseract.image_to_string(
            image, lang=lang, config=_tess_config(tdir), timeout=_OCR_TIMEOUT_S
        )
    except (pytesseract.TesseractError, pytesseract.TesseractNotFoundError, OSError) as exc:
        raise OcrUnavailableError(f"Tesseract OCR failed: {exc}") from exc
    except RuntimeError as exc:  # pytesseract raises RuntimeError on timeout
        raise OcrUnavailableError(f"Tesseract OCR timed out after {_OCR_TIMEOUT_S}s") from exc
    return str(text).strip()


def ocr_page(
    page: pymupdf.Page,
    lang: str = DEFAULT_OCR_LANG,
    *,
    dpi: int | None = None,
    tesseract_cmd: str | None = None,
    tessdata_dir: str | None = None,
) -> str:
    """Renders an already-open PyMuPDF page and OCRs it."""
    pix = page.get_pixmap(dpi=dpi or get_settings().ocr_dpi)
    image = Image.open(io.BytesIO(pix.tobytes("png")))
    return ocr_image(image, lang, tesseract_cmd=tesseract_cmd, tessdata_dir=tessdata_dir)


def ocr_pdf_page(pdf_bytes: bytes, page_num: int, lang: str = DEFAULT_OCR_LANG) -> str:
    """Convenience wrapper: opens the PDF and OCRs one 1-based page."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        if page_num < 1 or page_num > len(doc):
            raise ValueError(f"Page number {page_num} is out of bounds (1..{len(doc)})")
        return ocr_page(doc[page_num - 1], lang)
    finally:
        doc.close()
