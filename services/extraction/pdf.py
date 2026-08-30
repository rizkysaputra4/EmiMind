"""Pure PDF layout and text parsing functions."""

from __future__ import annotations

import io
import re

import pdfplumber

from services.shared.types import BBox, Language, PageContent

ID_MARKERS = {
    "pada",
    "dan",
    "laba",
    "aset",
    "beban",
    "catatan",
    "untuk",
    "tahun",
    "posisi",
    "keuangan",
    "arus",
    "kas",
    "liabilitas",
    "ekuitas",
    "pendapatan",
    "desember",
    "september",
    "juni",
    "maret",
    "entitas",
    "induk",
    "konsolidasian",
}
EN_MARKERS = {
    "the",
    "and",
    "profit",
    "loss",
    "assets",
    "expense",
    "notes",
    "for",
    "year",
    "ended",
    "financial",
    "statements",
    "cash",
    "flows",
    "liabilities",
    "equity",
    "revenue",
    "december",
    "september",
    "june",
    "march",
    "parent",
    "entity",
    "consolidated",
}


def detect_language(text: str) -> Language:
    """Detects primary language (id, en, mixed) using domain keyword frequency."""
    if not text or len(text.strip()) < 20:
        return "mixed"

    words = set(re.findall(r"\b[a-zA-Z]{2,}\b", text.lower()[:1500]))
    if not words:
        return "mixed"

    id_count = len(words & ID_MARKERS)
    en_count = len(words & EN_MARKERS)

    if id_count > en_count and id_count >= 2:
        return "id"
    if en_count > id_count and en_count >= 2:
        return "en"
    if id_count > 0 and en_count > 0:
        return "mixed"
    return "id"  # Default for IDX filings if ambiguous


def parse_pdf(pdf_bytes: bytes) -> list[PageContent]:
    """Parses PDF bytes into structured PageContent models per page."""
    pages: list[PageContent] = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for idx, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            clean_text = text.strip()

            has_text_layer = len(clean_text) >= 100
            language: Language = detect_language(clean_text)

            # Optional char-level bounding boxes if text layer is present
            bbox_by_char: list[tuple[str, BBox]] = []
            if has_text_layer and page.chars:
                # Sample or aggregate words to avoid excessive memory
                for char in page.chars[:1000]:
                    c_text = char.get("text", "")
                    x0 = float(char.get("x0", 0.0))
                    y0 = float(char.get("top", 0.0))
                    x1 = float(char.get("x1", x0))
                    y1 = float(char.get("bottom", y0))
                    if x0 <= x1 and y0 <= y1:
                        bbox_by_char.append((c_text, BBox(x0, y0, x1, y1)))

            pages.append(
                PageContent(
                    page_num=idx,
                    text=text,
                    language=language,
                    has_text_layer=has_text_layer,
                    bbox_by_char=bbox_by_char if bbox_by_char else None,
                )
            )

    return pages
