"""Multi-pass table extraction cascade and financial fact conversion."""

from __future__ import annotations

import io
import re
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import camelot
import pdfplumber

from services.shared.types import (
    BBox,
    ExtractedFact,
    ExtractedTable,
    FiscalPeriod,
    PageContent,
    PeriodType,
    TableCell,
)


def parse_numeric_value(val_str: str) -> float | None:
    """Parses numeric string supporting Indonesian & standard formats, parentheses as negatives."""
    s = val_str.strip()
    if not s or s in ("-", "\u2013", "\u2014", "nil", "n/a", "na"):
        return 0.0

    is_negative = False
    if (s.startswith("(") and s.endswith(")")) or (s.startswith("[") and s.endswith("]")):
        is_negative = True
        s = s[1:-1].strip()
    elif s.startswith("-"):
        is_negative = True
        s = s[1:].strip()

    # Remove currency prefixes
    s = re.sub(r"^(rp|idr|usd|us\$)\.?\s*", "", s, flags=re.IGNORECASE).strip()

    # Determine thousand vs decimal separator
    # Case 1: Indonesian format e.g. 1.234.567,89
    if "." in s and "," in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "." in s and s.count(".") > 1:
        # e.g. 1.234.567
        s = s.replace(".", "")
    elif "," in s and s.count(",") > 1:
        # e.g. 1,234,567
        s = s.replace(",", "")
    elif "." in s:
        # Single dot: e.g. 45.200 (thousands) vs 12.34 (decimals)
        parts = s.split(".")
        if len(parts[1]) == 3 and len(parts[0]) <= 3:
            s = s.replace(".", "")
    elif "," in s:
        # Single comma: could be 1,234 (thousands) or 1,23 (decimals)
        parts = s.split(",")
        if len(parts[1]) == 3 and len(parts[0]) <= 3:
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")

    try:
        val = float(Decimal(s))
        return -val if is_negative else val
    except (InvalidOperation, ValueError):
        return None


def detect_unit_from_header(text: str) -> str:
    """Infers reporting unit from header text (e.g. dalam jutaan Rupiah -> IDR_MN)."""
    t = text.lower()
    if (
        "jutaan rupiah" in t
        or "million idr" in t
        or "in million rupiah" in t
        or "dalam jutaan" in t
    ):
        return "IDR_MN"
    if (
        "miliaran rupiah" in t
        or "billion idr" in t
        or "in billion rupiah" in t
        or "dalam miliaran" in t
    ):
        return "IDR_BN"
    if (
        "ribuan rupiah" in t
        or "thousand idr" in t
        or "in thousand rupiah" in t
        or "dalam ribuan" in t
    ):
        return "IDR_TH"
    if "usd" in t or "dolar as" in t:
        if "thousand" in t or "ribuan" in t:
            return "USD_TH"
        if "million" in t or "jutaan" in t:
            return "USD_MN"
        return "USD"
    return "IDR"


def extract_tables(pdf_bytes: bytes, pages: list[PageContent]) -> list[ExtractedTable]:
    """Extracts tables across all pages using Camelot (lattice -> stream) and pdfplumber fallback."""
    extracted: list[ExtractedTable] = []

    # Write bytes to temporary file for Camelot
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = Path(tmp.name)

    try:
        for page in pages:
            page_num = page.page_num
            if not page.has_text_layer:
                continue

            page_tables: list[ExtractedTable] = []

            # 1. Try Camelot lattice
            try:
                tables = camelot.read_pdf(  # type: ignore[attr-defined]
                    str(tmp_path),
                    pages=str(page_num),
                    flavor="lattice",
                    suppress_stdout=True,
                )
                if tables and len(tables) > 0:
                    for t in tables:
                        if getattr(t, "accuracy", 0.0) >= 70.0:
                            cells = _camelot_table_to_cells(t)
                            if cells:
                                page_tables.append(
                                    ExtractedTable(
                                        page_num=page_num,
                                        cells=cells,
                                        extraction_method="camelot_lattice",
                                        confidence=0.95,
                                    )
                                )
            except Exception:
                pass

            # 2. Try Camelot stream if lattice found no tables
            if not page_tables:
                try:
                    tables = camelot.read_pdf(  # type: ignore[attr-defined]
                        str(tmp_path),
                        pages=str(page_num),
                        flavor="stream",
                        suppress_stdout=True,
                    )
                    if tables and len(tables) > 0:
                        for t in tables:
                            cells = _camelot_table_to_cells(t)
                            if cells and len(cells) >= 4:
                                page_tables.append(
                                    ExtractedTable(
                                        page_num=page_num,
                                        cells=cells,
                                        extraction_method="camelot_stream",
                                        confidence=0.85,
                                    )
                                )
                except Exception:
                    pass

            extracted.extend(page_tables)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass

    # 3. Fallback to pdfplumber table extraction if no tables extracted via Camelot
    if not extracted:
        extracted = _extract_tables_pdfplumber(pdf_bytes, pages)

    return extracted


def _camelot_table_to_cells(t: Any) -> list[TableCell]:
    """Converts a Camelot Table object into normalized TableCell models."""
    cells: list[TableCell] = []
    df = t.df
    for r_idx, row in df.iterrows():
        for c_idx, val in enumerate(row):
            text = str(val).strip()
            if text:
                # Default approximate bounding box
                cells.append(
                    TableCell(
                        row=int(r_idx),
                        col=int(c_idx),
                        text=text,
                        bbox=BBox(0.0, float(r_idx * 15), 500.0, float((r_idx + 1) * 15)),
                        confidence=0.90,
                    )
                )
    return cells


def _extract_tables_pdfplumber(pdf_bytes: bytes, pages: list[PageContent]) -> list[ExtractedTable]:
    """Fallback extraction using pdfplumber."""
    extracted: list[ExtractedTable] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pages:
            if page.page_num > len(pdf.pages):
                continue
            plumber_page = pdf.pages[page.page_num - 1]
            tables = plumber_page.extract_tables() or []
            for t in tables:
                cells: list[TableCell] = []
                for r_idx, row in enumerate(t):
                    for c_idx, val in enumerate(row):
                        if val and str(val).strip():
                            text = str(val).strip()
                            cells.append(
                                TableCell(
                                    row=r_idx,
                                    col=c_idx,
                                    text=text,
                                    bbox=BBox(
                                        0.0, float(r_idx * 15), 500.0, float((r_idx + 1) * 15)
                                    ),
                                    confidence=0.80,
                                )
                            )
                if cells:
                    extracted.append(
                        ExtractedTable(
                            page_num=page.page_num,
                            cells=cells,
                            extraction_method="camelot_stream",
                            confidence=0.80,
                        )
                    )
    return extracted


def tables_to_facts(
    tables: list[ExtractedTable],
    sector: str | None,
    ticker: str,
    fiscal_period: FiscalPeriod,
    doc_id: str,
) -> list[ExtractedFact]:
    """Normalizes extracted tables into raw ExtractedFact items."""
    facts: list[ExtractedFact] = []

    for table in tables:
        # Organize cells by row
        rows_by_idx: dict[int, dict[int, TableCell]] = {}
        for c in table.cells:
            rows_by_idx.setdefault(c.row, {})[c.col] = c

        if not rows_by_idx:
            continue

        unit = "IDR"
        note_cols: set[int] = set()

        # Check first 3 rows for unit declaration and note column headers
        for r_i in range(min(3, len(rows_by_idx))):
            row_cols = rows_by_idx.get(r_i, {})
            row_text = " ".join(c.text for c in row_cols.values())
            detected_unit = detect_unit_from_header(row_text)
            if detected_unit != "IDR":
                unit = detected_unit

            for col_i, cell in row_cols.items():
                c_text = cell.text.strip().lower()
                if re.search(r"\b(?:catatan|note|notes|calck|ref)\b", c_text):
                    note_cols.add(col_i)

        # Process each data row
        for _r_i, row_cols in sorted(rows_by_idx.items()):
            # Leftmost column contains the concept label
            label_cell = row_cols.get(0)
            if not label_cell:
                continue

            raw_label = label_cell.text.strip()

            # Skip Table of Contents dot leaders like "Konsolidasian Interim  ................... 6"
            if re.search(r"\.{3,}\s*\d+", raw_label) or re.search(r"^\s*(?:daftar\s+isi|table\s+of\s+contents)\b", raw_label, re.I):
                continue

            # Clean trailing dots/dashes from label
            clean_label = re.sub(r"[\.\-_]{3,}.*$", "", raw_label).strip()
            # Clean bilingual separator e.g. "Kas dan setara kas / Cash and cash equivalents" -> "Kas dan setara kas"
            clean_label = re.sub(r"\s*/\s*[A-Za-z\s]+$", "", clean_label).strip() or clean_label

            # Skip short or header-only lines
            if len(clean_label) < 3 or clean_label.isdigit():
                continue

            # Look for values in subsequent columns, skipping known note columns
            candidate_vals: list[tuple[int, float, TableCell]] = []
            for col_i in sorted(row_cols.keys()):
                if col_i == 0 or col_i in note_cols:
                    continue

                val_cell = row_cols[col_i]
                parsed_num = parse_numeric_value(val_cell.text)
                if parsed_num is not None:
                    candidate_vals.append((col_i, parsed_num, val_cell))

            if not candidate_vals:
                continue

            # If the first candidate column looks like an isolated note number (e.g. 1-99)
            # while the next column has a substantial financial number, skip the note number
            chosen_col, chosen_val, chosen_cell = candidate_vals[0]
            if len(candidate_vals) > 1:
                first_text = candidate_vals[0][2].text.strip()
                # Check if first col is a small unformatted integer (e.g. "4", "5", "23") note reference
                if (
                    re.fullmatch(r"\d{1,2}[a-z]?", first_text)
                    and abs(candidate_vals[0][1]) < 200
                    and abs(candidate_vals[1][1]) >= 100
                ):
                    chosen_col, chosen_val, chosen_cell = candidate_vals[1]

            # Determine period type (BS is instant, others duration_ytd)
            period_type: PeriodType = "duration_ytd"
            if any(
                w in clean_label.lower()
                for w in ("aset", "asset", "liabilitas", "liability", "ekuitas", "equity", "simpanan", "kas", "piutang")
            ):
                period_type = "instant"

            facts.append(
                ExtractedFact(
                    concept_local=clean_label,
                    value_numeric=chosen_val,
                    unit=unit,
                    period_type=period_type,
                    source_page=table.page_num,
                    source_bbox=label_cell.bbox,
                    confidence=min(table.confidence, chosen_cell.confidence),
                    method="table_parser",
                )
            )

    return facts
