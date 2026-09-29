"""Per-page table extraction cascade (Camelot lattice -> stream -> pdfplumber) and cell grids."""

from __future__ import annotations

import gc
import io
import re
import tempfile
import warnings
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import camelot
import pdfplumber
from pydantic import BaseModel, Field

from services.shared.logging import get_logger
from services.shared.types import (
    BBox,
    ExtractedFact,
    ExtractedTable,
    FiscalPeriod,
    PageContent,
    PeriodType,
    TableCell,
)

log = get_logger(__name__)

_LATTICE_MIN_ACCURACY = 70.0
_MIXED_CELL_PENALTY = 0.10
_HEADER_LINES = 15


class GridCell(BaseModel):
    """One parsed cell; bbox is top-left-origin PDF points, None when the parser gave none."""

    row: int
    col: int
    text: str
    value: float | None = None
    bbox: list[float] | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    value_from_mixed_cell: bool = False
    note_ref: bool = False


class PageGrid(BaseModel):
    page_index: int
    table_index: int
    extraction_method: str
    confidence: float = Field(ge=0.0, le=1.0)
    unit_hint: str | None = None
    bbox: list[float] | None = None
    cells: list[GridCell]


def parse_numeric_value(val_str: str) -> float | None:
    """Parses numeric string supporting Indonesian & standard formats, parentheses as negatives."""
    s = val_str.strip()
    if not s or s in ("-", "–", "—", "nil", "n/a", "na"):
        return 0.0

    is_negative = False
    if (s.startswith("(") and s.endswith(")")) or (s.startswith("[") and s.endswith("]")):
        is_negative = True
        s = s[1:-1].strip()
    elif s.startswith("-"):
        is_negative = True
        s = s[1:].strip()

    s = re.sub(r"^(rp|idr|usd|us\$)\.?\s*", "", s, flags=re.IGNORECASE).strip()

    if "." in s and "," in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "." in s and s.count(".") > 1:
        s = s.replace(".", "")
    elif "," in s and s.count(",") > 1:
        s = s.replace(",", "")
    elif "." in s:
        parts = s.split(".")
        if len(parts[1]) == 3 and len(parts[0]) <= 3:
            s = s.replace(".", "")
    elif "," in s:
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


# ---------------------------------------------------------------------------
# Unit detection
# ---------------------------------------------------------------------------

_SCALE_WORDS = {
    "MN": r"jutaan|juta|millions?|mn",
    "BN": r"miliaran|miliar|milyaran|milyar|billions?|bn",
    "K": r"ribuan|ribu|thousands?",
}
_CURRENCY_WORDS = {
    "IDR": r"rupiah|rp\.?|idr",
    "USD": r"dolar\s+amerika\s+serikat|dolar\s+as|us\s+dollars?|united\s+states\s+dollars?"
    r"|dollars?\s+amerika|usd|us\$",
}
_SCALE_RE = "|".join(f"(?P<{k}>{v})" for k, v in _SCALE_WORDS.items())
_CUR_RE = "|".join(f"(?P<{k}>{v})" for k, v in _CURRENCY_WORDS.items())
# "(dalam jutaan Rupiah)", "(Expressed in millions of Rupiah)", "in thousands of US Dollars"
_SCALE_THEN_CUR = re.compile(
    rf"(?<![a-z])(?:{_SCALE_RE})(?:\s+of)?\s+(?:{_CUR_RE})(?![a-z])", re.IGNORECASE
)
# "Rp juta", "USD thousand", "Rupiah (millions)"
_CUR_THEN_SCALE = re.compile(
    rf"(?<![a-z])(?:{_CUR_RE})\s*\(?\s*(?:{_SCALE_RE})(?![a-z])", re.IGNORECASE
)
# "(Expressed in Rupiah)", "(Disajikan dalam Rupiah)", "(dalam Rupiah penuh)"
_CUR_ONLY = re.compile(
    rf"(?:expressed\s+in|disajikan\s+dalam|dinyatakan\s+dalam|\(\s*dalam|\(\s*in)\s+"
    rf"(?:full\s+)?(?:amounts?\s+of\s+)?(?:{_CUR_RE})(?![a-z])",
    re.IGNORECASE,
)


def _unit_code(m: re.Match[str], with_scale: bool) -> str:
    groups = {k for k, v in m.groupdict().items() if v}
    currency = "USD" if "USD" in groups else "IDR"
    if not with_scale:
        return currency
    scale = next((k for k in ("MN", "BN", "K") if k in groups), None)
    return f"{currency}_{scale}" if scale else currency


def detect_unit_from_header(text: str) -> str | None:
    """Unit code from an explicit unit phrase (IDR_MN, IDR_BN, IDR_K, IDR, USD_*); None if absent."""
    if not text:
        return None
    t = re.sub(r"\s+", " ", text)
    matches: list[tuple[int, str]] = []
    for pattern, with_scale in ((_SCALE_THEN_CUR, True), (_CUR_THEN_SCALE, True)):
        matches += [(m.start(), _unit_code(m, with_scale)) for m in pattern.finditer(t)]
    if not matches:
        matches = [(m.start(), _unit_code(m, False)) for m in _CUR_ONLY.finditer(t)]
    if not matches:
        return None
    return min(matches)[1]


def detect_page_unit(page_text: str, header_lines: int = _HEADER_LINES) -> str | None:
    """Prefers the unit stated in the page header; falls back to the first one on the page."""
    head = "\n".join(page_text.splitlines()[:header_lines])
    return detect_unit_from_header(head) or detect_unit_from_header(page_text)


# ---------------------------------------------------------------------------
# Cell post-processing: note references and mixed label+number cells
# ---------------------------------------------------------------------------

_NUM_TOKEN = re.compile(
    r"^\(?-?(?:\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,4})?|\d{3,}(?:[.,]\d{1,4})?|\d{1,3}[.,]\d{1,2}"
    r"|[-–—])\)?$"
)
_YEAR_TOKEN = re.compile(r"^(?:19|20)\d{2}$")
_NOTE_REF = re.compile(
    r"^\d{1,2}[a-z]?(?:\.?\([ivx]+\))?(?:\s*[,/;]\s*\d{1,2}[a-z]?(?:\.?\([ivx]+\))?)*$",
    re.IGNORECASE,
)
_NOTE_HEADER = re.compile(r"(?<![a-z])(?:catatan|notes?|ref)(?![a-z])", re.IGNORECASE)
_LETTERS = re.compile(r"[A-Za-zÀ-ɏ]{3,}")


def is_note_reference(text: str) -> bool:
    """Unambiguous note references anywhere: '2c,2g,4', '5a', '62b.(vii)', '4, 12, 30'."""
    s = text.strip()
    if not s or not _NOTE_REF.match(s):
        return False
    if re.search(r"\d[a-z]|\(", s, re.IGNORECASE):
        return True
    return len(re.split(r"\s*[,/;]\s*", s)) >= 3


def _looks_note_like(text: str) -> bool:
    """Weaker test used column-wise: also plain '15' or '22,27' (could be a decimal elsewhere)."""
    return bool(_NOTE_REF.match(text.strip()))


def split_mixed_cell(text: str) -> float | None:
    """Value of a 'label ... 828.016' cell: exactly one trailing numeric token after a label."""
    tokens = text.split()
    if len(tokens) < 2:
        return None
    last = tokens[-1]
    if not _NUM_TOKEN.match(last) or _YEAR_TOKEN.match(last) or last in "-–—":
        return None
    rest = tokens[:-1]
    if _NUM_TOKEN.match(rest[-1]) or not _LETTERS.search(" ".join(rest)):
        return None
    return parse_numeric_value(last)


_AMOUNT = re.compile(r"\d{1,3}(?:[.,]\d{3})+")


def _header_rows(rows: dict[int, dict[int, str]], cap: int = 8) -> list[int]:
    """Rows above the first row that carries a thousand-separated amount."""
    out: list[int] = []
    for r in sorted(rows)[:cap]:
        if any(_AMOUNT.search(t) for t in rows[r].values()):
            break
        out.append(r)
    return out


def _detect_note_columns(rows: dict[int, dict[int, str]], header_rows: list[int]) -> set[int]:
    """Columns headed Catatan/Notes, or whose body is only note-number integers/lists."""
    note_cols: set[int] = set()
    for r in header_rows:
        for c, txt in rows[r].items():
            if _NOTE_HEADER.search(txt) and len(txt) <= 25:
                note_cols.add(c)

    header_set = set(header_rows)
    by_col: dict[int, list[str]] = {}
    for r, cols in rows.items():
        if r in header_set:
            continue
        for c, txt in cols.items():
            if txt.strip():
                by_col.setdefault(c, []).append(txt.strip())
    has_amount_col = any(
        sum(1 for t in vals if _AMOUNT.search(t)) >= 2 for vals in by_col.values()
    )
    for c, vals in by_col.items():
        refs = [t for t in vals if _looks_note_like(t)]
        if has_amount_col and len(refs) >= 2 and len(refs) == len(vals):
            note_cols.add(c)
    return note_cols


def build_grid_cells(
    raw: list[tuple[int, int, str, list[float] | None]], table_confidence: float
) -> list[GridCell]:
    """Turns (row, col, text, bbox) tuples into GridCells with parsed values and flags."""
    rows: dict[int, dict[int, str]] = {}
    for r, c, txt, _ in raw:
        rows.setdefault(r, {})[c] = txt
    header_rows = set(_header_rows(rows))
    note_cols = _detect_note_columns(rows, sorted(header_rows))
    tconf = round(table_confidence, 2)

    cells: list[GridCell] = []
    for r, c, txt, bbox in raw:
        in_note_col = c in note_cols
        note = (in_note_col and _looks_note_like(txt)) or is_note_reference(txt)
        value: float | None = None
        mixed = False
        conf = tconf
        is_header_year = r in header_rows and bool(_YEAR_TOKEN.match(txt.strip()))
        if not note and not in_note_col and not is_header_year:
            value = parse_numeric_value(txt) if not _LETTERS.search(txt) else None
            if value is None:
                mixed_value = split_mixed_cell(txt)
                if mixed_value is not None:
                    value, mixed = mixed_value, True
                    conf = round(max(0.0, tconf - _MIXED_CELL_PENALTY), 2)
        cells.append(
            GridCell(
                row=r,
                col=c,
                text=txt,
                value=value,
                bbox=bbox,
                confidence=min(conf, tconf),
                value_from_mixed_cell=mixed,
                note_ref=note,
            )
        )
    return cells


def _has_numeric_content(raw: list[tuple[int, int, str, list[float] | None]]) -> bool:
    return sum(1 for _, _, t, _ in raw if re.search(r"\d", t)) >= 2


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

RawCell = tuple[int, int, str, list[float] | None]
# (extraction_method, table_confidence, table_bbox, cells)
RawTable = tuple[str, float, list[float] | None, list[RawCell]]


def _rounded_box(x0: float, y0: float, x1: float, y1: float) -> list[float]:
    return [round(min(x0, x1), 2), round(min(y0, y1), 2), round(max(x0, x1), 2), round(max(y0, y1), 2)]


def _camelot_cell_bbox(t: Any, r: int, c: int, page_height: float) -> list[float] | None:
    """Cell box in top-left origin; lattice cells are widened over their unruled span."""
    try:
        cell = t.cells[r][c]
    except (IndexError, AttributeError):
        return None
    x1, y1, x2, y2 = float(cell.x1), float(cell.y1), float(cell.x2), float(cell.y2)
    if getattr(t, "flavor", None) == "lattice":
        cc = c
        while not t.cells[r][cc].right and cc + 1 < len(t.cells[r]) and not str(
            t.df.iloc[r, cc + 1]
        ).strip():
            cc += 1
            x2 = float(t.cells[r][cc].x2)
        rr = r
        while not t.cells[rr][c].bottom and rr + 1 < len(t.cells) and not str(
            t.df.iloc[rr + 1, c]
        ).strip():
            rr += 1
            y1 = float(t.cells[rr][c].y1)
    return _rounded_box(x1, page_height - y2, x2, page_height - y1)


def _camelot_grids(
    pdf_path: Path, page_num: int, flavor: str, page_height: float
) -> list[RawTable]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        tables = camelot.read_pdf(  # type: ignore[attr-defined]
            str(pdf_path), pages=str(page_num), flavor=flavor, suppress_stdout=True
        )
    out: list[RawTable] = []
    for t in tables:
        accuracy = float(getattr(t, "accuracy", 0.0) or 0.0)
        if flavor == "lattice" and accuracy < _LATTICE_MIN_ACCURACY:
            continue
        raw: list[tuple[int, int, str, list[float] | None]] = []
        for r_idx in range(t.df.shape[0]):
            for c_idx in range(t.df.shape[1]):
                txt = str(t.df.iloc[r_idx, c_idx]).strip()
                if txt:
                    raw.append((r_idx, c_idx, txt, _camelot_cell_bbox(t, r_idx, c_idx, page_height)))
        if len(raw) < 4 or not _has_numeric_content(raw):
            continue
        base = 0.95 if flavor == "lattice" else 0.85
        conf = round(base * min(1.0, max(accuracy, 0.0) / 100.0), 2)
        tb = getattr(t, "_bbox", None)
        tbox = _rounded_box(tb[0], page_height - tb[3], tb[2], page_height - tb[1]) if tb else None
        out.append((f"camelot_{flavor}", conf, tbox, raw))
    return out


def _pdfplumber_grids(
    plumber_page: Any,
) -> list[RawTable]:
    out: list[RawTable] = []
    for tbl in plumber_page.find_tables():
        texts = tbl.extract()
        raw: list[tuple[int, int, str, list[float] | None]] = []
        for r_idx, row in enumerate(texts):
            row_cells = tbl.rows[r_idx].cells if r_idx < len(tbl.rows) else []
            for c_idx, val in enumerate(row):
                if val and str(val).strip():
                    box = row_cells[c_idx] if c_idx < len(row_cells) else None
                    raw.append(
                        (r_idx, c_idx, str(val).strip(), _rounded_box(*box) if box else None)
                    )
        if raw and _has_numeric_content(raw):
            out.append(("pdfplumber", 0.80, _rounded_box(*tbl.bbox), raw))
    return out


def _remove_temp_pdf(path: Path) -> None:
    # Camelot's PDF backends can hold the file open on Windows until garbage collection.
    for _ in range(2):
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError:
            gc.collect()
    log.debug("temp pdf still locked; left for OS temp cleanup", path=str(path))


def extract_page_grids(pdf_bytes: bytes, pages: list[PageContent]) -> list[PageGrid]:
    """Runs lattice -> stream -> pdfplumber independently for every text-layer page."""
    grids: list[PageGrid] = []
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = Path(tmp.name)
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pages:
                if not page.has_text_layer or page.page_num > len(pdf.pages):
                    continue
                plumber_page = pdf.pages[page.page_num - 1]
                height = float(plumber_page.height)
                unit = detect_page_unit(page.text)
                found = []
                for flavor in ("lattice", "stream"):
                    try:
                        found = _camelot_grids(tmp_path, page.page_num, flavor, height)
                    except Exception as exc:
                        log.warning(
                            "camelot failed", page=page.page_num, flavor=flavor, error=str(exc)
                        )
                        found = []
                    if found:
                        break
                if not found:
                    try:
                        found = _pdfplumber_grids(plumber_page)
                    except Exception as exc:
                        log.warning("pdfplumber failed", page=page.page_num, error=str(exc))
                for t_idx, (method, conf, tbox, raw) in enumerate(found):
                    grids.append(
                        PageGrid(
                            page_index=page.page_num,
                            table_index=t_idx,
                            extraction_method=method,
                            confidence=conf,
                            unit_hint=unit,
                            bbox=tbox,
                            cells=build_grid_cells(raw, conf),
                        )
                    )
    finally:
        _remove_temp_pdf(tmp_path)
    return grids


def grid_to_storage_dict(grid: PageGrid) -> dict[str, Any]:
    """document_page_tables row; flags are only emitted when true to keep cells compact."""
    cells = []
    for c in grid.cells:
        d: dict[str, Any] = {
            "row": c.row,
            "col": c.col,
            "text": c.text,
            "value": c.value,
            "bbox": c.bbox,
            "confidence": c.confidence,
        }
        if c.value_from_mixed_cell:
            d["value_from_mixed_cell"] = True
        if c.note_ref:
            d["note_ref"] = True
        cells.append(d)
    return {
        "page_index": grid.page_index,
        "table_index": grid.table_index,
        "extraction_method": grid.extraction_method,
        "confidence": grid.confidence,
        "unit_hint": grid.unit_hint,
        "cells": cells,
    }


def extract_page_table_grids(pdf_bytes: bytes, pages: list[PageContent]) -> list[dict[str, Any]]:
    """Per-table grids formatted for document_page_tables."""
    return [grid_to_storage_dict(g) for g in extract_page_grids(pdf_bytes, pages)]


def extract_tables(pdf_bytes: bytes, pages: list[PageContent]) -> list[ExtractedTable]:
    """Legacy ExtractedTable view of extract_page_grids (cells without a bbox use the table's)."""
    out: list[ExtractedTable] = []
    for g in extract_page_grids(pdf_bytes, pages):
        cells: list[TableCell] = []
        for c in g.cells:
            box = c.bbox or g.bbox
            if box is None:
                continue
            cells.append(
                TableCell(
                    row=c.row,
                    col=c.col,
                    text=c.text,
                    value=c.value,
                    bbox=BBox(*box),
                    confidence=c.confidence,
                )
            )
        if cells:
            out.append(
                ExtractedTable(
                    page_num=g.page_index,
                    cells=cells,
                    extraction_method=g.extraction_method,
                    confidence=g.confidence,
                    unit_hint=g.unit_hint,
                )
            )
    return out


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
        rows_by_idx: dict[int, dict[int, TableCell]] = {}
        for c in table.cells:
            rows_by_idx.setdefault(c.row, {})[c.col] = c

        if not rows_by_idx:
            continue

        unit = table.unit_hint or "IDR"
        note_cols: set[int] = set()

        for r_i in range(min(3, len(rows_by_idx))):
            row_cols = rows_by_idx.get(r_i, {})
            row_text = " ".join(c.text for c in row_cols.values())
            detected_unit = detect_unit_from_header(row_text)
            if detected_unit:
                unit = detected_unit

            for col_i, cell in row_cols.items():
                if _NOTE_HEADER.search(cell.text.strip()):
                    note_cols.add(col_i)

        for _r_i, row_cols in sorted(rows_by_idx.items()):
            label_cell = row_cols.get(0)
            if not label_cell:
                continue

            raw_label = label_cell.text.strip()
            if re.search(r"\.{3,}\s*\d+", raw_label) or re.search(
                r"^\s*(?:daftar\s+isi|table\s+of\s+contents)\b", raw_label, re.I
            ):
                continue

            clean_label = re.sub(r"[\.\-_]{3,}.*$", "", raw_label).strip()
            clean_label = re.sub(r"\s*/\s*[A-Za-z\s]+$", "", clean_label).strip() or clean_label
            if len(clean_label) < 3 or clean_label.isdigit():
                continue

            candidate_vals: list[tuple[int, float, TableCell]] = []
            for col_i in sorted(row_cols.keys()):
                if col_i == 0 or col_i in note_cols:
                    continue
                val_cell = row_cols[col_i]
                if is_note_reference(val_cell.text):
                    continue
                parsed_num = parse_numeric_value(val_cell.text)
                if parsed_num is not None:
                    candidate_vals.append((col_i, parsed_num, val_cell))

            if not candidate_vals:
                continue

            _chosen_col, chosen_val, chosen_cell = candidate_vals[0]
            if len(candidate_vals) > 1:
                first_text = candidate_vals[0][2].text.strip()
                if (
                    re.fullmatch(r"\d{1,2}[a-z]?", first_text)
                    and abs(candidate_vals[0][1]) < 200
                    and abs(candidate_vals[1][1]) >= 100
                ):
                    _chosen_col, chosen_val, chosen_cell = candidate_vals[1]

            period_type: PeriodType = "duration_ytd"
            if any(
                w in clean_label.lower()
                for w in (
                    "aset", "asset", "liabilitas", "liability", "ekuitas", "equity",
                    "simpanan", "kas", "piutang",
                )
            ):
                period_type = "instant"

            facts.append(
                ExtractedFact(
                    concept_local=clean_label,
                    value_numeric=chosen_val,
                    unit=unit,
                    period_type=period_type,
                    source_page=table.page_num,
                    source_bbox=chosen_cell.bbox,
                    confidence=min(table.confidence, chosen_cell.confidence),
                    method="table_parser",
                )
            )

    return facts
