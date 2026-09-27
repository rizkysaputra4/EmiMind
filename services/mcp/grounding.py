"""Number normalization and evidence grounding validation for EMIMIND MCP Server."""

from __future__ import annotations

import contextlib
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from services.mcp.types import ExtractedFactItem, PageEvidence, PageTableCell


def _parse_token_candidates(token: str) -> list[Decimal]:
    """Parse a single numeric match token into potential Decimal candidates."""
    s = token.strip()
    is_neg = False
    if s.startswith("(") and s.endswith(")"):
        is_neg = True
        s = s[1:-1].strip()
    elif s.startswith("-") or s.startswith("\u2212"):
        is_neg = True
        s = s[1:].strip()

    s = re.sub(r"^(rp|idr|usd|us\$|\$)\.?\s*", "", s, flags=re.IGNORECASE).strip()
    if not s or not any(ch.isdigit() for ch in s):
        return []

    cands: list[Decimal] = []
    if "." in s and "," in s:
        clean = (
            s.replace(".", "").replace(",", ".")
            if s.rfind(",") > s.rfind(".")
            else s.replace(",", "")
        )
        with contextlib.suppress(InvalidOperation, ValueError):
            d = Decimal(clean)
            cands.append(-d if is_neg else d)
            if clean.endswith(".00") or clean.endswith(".0"):
                cands.append(Decimal(int(-d if is_neg else d)))
    elif ("." in s and s.count(".") > 1) or ("," in s and s.count(",") > 1):
        clean = s.replace(".", "") if "." in s else s.replace(",", "")
        with contextlib.suppress(InvalidOperation, ValueError):
            d = Decimal(clean)
            cands.append(-d if is_neg else d)
    elif "." in s or "," in s:
        sep = "." if "." in s else ","
        parts = s.split(sep)
        clean_dec = s.replace(",", ".")
        with contextlib.suppress(InvalidOperation, ValueError):
            d_dec = Decimal(clean_dec)
            cands.append(-d_dec if is_neg else d_dec)
            if sep == "," and (parts[1] in ("00", "0")):
                cands.append(Decimal(int(-d_dec if is_neg else d_dec)))
        if len(parts[1]) == 3 and len(parts[0]) <= 3:
            with contextlib.suppress(InvalidOperation, ValueError):
                d_th = Decimal(s.replace(sep, ""))
                cands.append(-d_th if is_neg else d_th)
    else:
        with contextlib.suppress(InvalidOperation, ValueError):
            d = Decimal(s)
            cands.append(-d if is_neg else d)

    return cands


def normalize_candidates(text: str) -> list[Decimal]:
    """Extracts and normalizes numeric values from financial text."""
    pattern = re.compile(
        r"\(?\s*[-\u2013\u2212]?\s*(?:Rp|IDR|USD|US\$|\$)?\s*\d[\d.,]*\s*\)?",
        re.IGNORECASE,
    )
    results: list[Decimal] = []
    for m in pattern.findall(text):
        for c in _parse_token_candidates(m):
            if c not in results:
                results.append(c)
    return results


def resolve_scale(
    unit_hint: str | None,
    scaling_rules: dict[str, Any] | None = None,
) -> Decimal:
    """Infers integer multiplier scale from unit_hint or scaling_rules."""
    if unit_hint:
        t = unit_hint.lower()
        if any(k in t for k in ("bn", "miliar", "billion", "10^9")):
            return Decimal("1000000000")
        if any(k in t for k in ("mn", "jutaan", "juta", "million", "10^6")):
            return Decimal("1000000")
        if any(k in t for k in ("th", "ribuan", "ribu", "thousand", "10^3")):
            return Decimal("1000")
        if any(k in t for k in ("idr", "full", "satuan")):
            return Decimal("1")

    if scaling_rules:
        for key in ("multiplier", "scale"):
            if key in scaling_rules:
                with contextlib.suppress(InvalidOperation, ValueError):
                    return Decimal(str(scaling_rules[key]))

    return Decimal("1")


def _find_target_cell(
    page_evidence: PageEvidence,
    table_index: int,
    row: int,
    col: int,
) -> tuple[PageTableCell | None, str | None, Decimal]:
    """Locates target cell in page evidence tables, returning (cell, error, scale)."""
    target_table = next(
        (tbl for tbl in page_evidence.tables if tbl.table_index == table_index),
        None,
    )
    if target_table is None:
        return None, f"Table index {table_index} not found", Decimal("1")

    target_cell = next(
        (c for c in target_table.cells if c.row == row and c.col == col),
        None,
    )
    if target_cell is None:
        return None, f"Cell (row={row}, col={col}) not found in table {table_index}", Decimal("1")

    scale = resolve_scale(target_table.unit_hint)
    return target_cell, None, scale


def check_cell_grounding(
    fact: ExtractedFactItem,
    page_evidence: PageEvidence,
    default_scale: Decimal | None = None,
) -> tuple[bool, str | None, float | None, list[float] | None]:
    """Validates cell-level grounding for a fact.

    Returns:
        (is_grounded, error_message, confidence, bbox)
    """
    if not fact.cell_ref:
        return False, "Fact has no cell_ref", None, None

    cell_ref = fact.cell_ref
    target_cell, err, scale = _find_target_cell(
        page_evidence, cell_ref.table_index, cell_ref.row, cell_ref.col
    )
    if target_cell is None:
        return False, f"{err} on page {fact.source_page}", None, None

    if scale == 1 and default_scale is not None and default_scale > 1:
        scale = default_scale

    if target_cell.value is not None:
        cell_val = Decimal(str(target_cell.value))
    else:
        candidates = normalize_candidates(target_cell.text)
        if not candidates:
            return (
                False,
                f"Cell ({cell_ref.row}, {cell_ref.col}) has non-numeric text '{target_cell.text}'",
                None,
                target_cell.bbox,
            )
        cell_val = candidates[0]

    scaled_cell_val = cell_val * scale
    tolerance = scale if scale > 0 else Decimal("1")

    if abs(scaled_cell_val - fact.value_numeric) <= tolerance:
        conf = target_cell.confidence if target_cell.confidence is not None else 1.0
        return True, None, conf, target_cell.bbox

    return (
        False,
        (
            f"Fact '{fact.concept_id}' value {fact.value_numeric} does not match cell "
            f"({cell_ref.table_index}, {cell_ref.row}, {cell_ref.col}) value {target_cell.value} "
            f"(scaled: {scaled_cell_val:,.0f} ± {tolerance:,.0f}) on page {fact.source_page}."
        ),
        None,
        target_cell.bbox,
    )


def check_text_grounding(
    fact: ExtractedFactItem,
    page_evidence: PageEvidence,
    default_scale: Decimal | None = None,
) -> tuple[bool, str | None]:
    """Validates text-level grounding for a fact on a pdf_text or ocr page."""
    candidates = normalize_candidates(page_evidence.page_text)
    if not candidates:
        return (
            False,
            f"Fact '{fact.concept_id}' value {fact.value_numeric} not found on page "
            f"{fact.source_page} (page text contains no numbers).",
        )

    scales: list[Decimal] = [Decimal("1")]
    if default_scale is not None and default_scale not in scales:
        scales.append(default_scale)
    for tbl in page_evidence.tables:
        s = resolve_scale(tbl.unit_hint)
        if s not in scales:
            scales.append(s)

    text_scale = resolve_scale(page_evidence.page_text)
    if text_scale not in scales:
        scales.append(text_scale)

    for std_scale in (Decimal("1000000"), Decimal("1000"), Decimal("1000000000")):
        if std_scale not in scales:
            scales.append(std_scale)

    for s in scales:
        unscaled = fact.value_numeric / s
        tol = min(Decimal("1"), abs(unscaled) * Decimal("0.01")) if unscaled != 0 else Decimal("0")
        for cand in candidates:
            if abs(cand - unscaled) <= tol:
                return True, None
            if abs(unscaled) > 0 and abs(cand - unscaled) / abs(unscaled) < Decimal("0.0001"):
                return True, None

    return (
        False,
        f"Fact '{fact.concept_id}' value {fact.value_numeric} not found in text on page "
        f"{fact.source_page}.",
    )
