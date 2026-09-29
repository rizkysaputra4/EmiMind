"""Page quality heuristics for determining OCR requirement."""

from __future__ import annotations

import re

OCR_MIN_CHARS = 50


def non_whitespace_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def needs_ocr(
    text: str, min_chars: int = OCR_MIN_CHARS, max_bad_glyph_ratio: float = 0.30
) -> bool:
    """True if the text layer is empty, near-empty (< min_chars non-whitespace) or glyph garbage."""
    if not text:
        return True

    non_ws = re.sub(r"\s+", "", text)
    if len(non_ws) < min_chars:
        return True

    bad_glyphs = sum(1 for c in non_ws if c == "\ufffd" or not c.isprintable())
    return bad_glyphs / len(non_ws) > max_bad_glyph_ratio
