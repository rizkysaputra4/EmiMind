"""Page quality heuristics for determining OCR requirement."""

from __future__ import annotations

import re


def needs_ocr(text: str, min_chars: int = 15, max_bad_glyph_ratio: float = 0.30) -> bool:
    """Returns True if the extracted text layer is empty, near-empty, or corrupted with glyph garbage.

    Args:
        text: Extracted plain text for the page.
        min_chars: Minimum non-whitespace characters required for a valid text layer.
        max_bad_glyph_ratio: Maximum allowable ratio of replacement/unprintable glyphs.
    """
    if not text:
        return True

    non_ws = re.sub(r"\s+", "", text)
    if len(non_ws) < min_chars:
        return True

    bad_glyphs = sum(1 for c in non_ws if c == "\ufffd" or not c.isprintable())
    if len(non_ws) > 0 and (bad_glyphs / len(non_ws)) > max_bad_glyph_ratio:
        return True

    return False
