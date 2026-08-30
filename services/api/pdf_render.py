"""PDF page image rendering with bounding box highlighting via PyMuPDF."""

from __future__ import annotations

from typing import TYPE_CHECKING

import fitz  # type: ignore[import-untyped]

if TYPE_CHECKING:
    from services.shared.types import BBox


def render_page_png(
    pdf_bytes: bytes,
    page_num: int = 1,
    bbox: BBox | None = None,
    dpi: int = 150,
) -> bytes:
    """Renders a PDF page to PNG bytes and draws a highlighted bounding box if provided."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    # Page index is 0-based in PyMuPDF
    p_idx = max(0, min(page_num - 1, len(doc) - 1))
    page = doc[p_idx]

    # Draw highlighted bounding box if coordinates are valid
    if bbox:
        rect = fitz.Rect(bbox.x0, bbox.y0, bbox.x1, bbox.y1)
        # Red rectangle overlay with slight fill
        page.draw_rect(
            rect,
            color=(0.85, 0.15, 0.15),
            fill=(1.0, 0.8, 0.8),
            fill_opacity=0.25,
            width=2.0,
        )

    pix = page.get_pixmap(dpi=dpi)
    png_bytes = pix.tobytes("png")
    doc.close()
    return bytes(png_bytes)
