"""Pure OCR extraction utilities."""

from __future__ import annotations

import io

import pymupdf
import pytesseract
from PIL import Image


def ocr_page(pdf_bytes: bytes, page_num: int, lang: str = "ind+eng") -> str:
    """Renders a PDF page to image and runs OCR text extraction."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    if page_num < 1 or page_num > len(doc):
        doc.close()
        raise ValueError(f"Page number {page_num} is out of bounds (1..{len(doc)})")

    page = doc[page_num - 1]
    pix = page.get_pixmap(dpi=200)
    img_bytes = pix.tobytes("png")
    doc.close()

    image = Image.open(io.BytesIO(img_bytes))
    try:
        text = pytesseract.image_to_string(image, lang=lang)
        return str(text).strip()
    except Exception:
        # Graceful fallback if tesseract host binary is not configured
        return ""
