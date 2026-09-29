"""Number normalization and evidence grounding for EMIMIND MCP Server.

Grounding answers two questions for every submitted fact:
  * is the number on the cited page, at ONE scale (table unit, page header, document, contract)?
  * is it in the right row (label) and the right column (period)?
"""

from __future__ import annotations

import contextlib
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from rapidfuzz import fuzz

from services.mcp.types import ExtractedFactItem, PageEvidence, PageTable, PageTableCell

GroundingKind = Literal["cell", "text", "ocr_unverified"]

_ONE = Decimal(1)
_DASHES = "-–—−"

_NUM_RE = re.compile(
    r"(?<![\w.,])"
    r"(?P<open>\(\s*)?"
    r"(?P<sign>[-–—−](?=(?:rp|idr|usd|us\$|\$)?\.?\d))?"
    r"(?P<cur>(?:rp|idr|usd|us\$|\$)\.?\s*)?"
    r"(?P<num>\d[\d.,]*\d|\d)"
    r"(?P<close>\s*\))?"
    r"(?P<pct>\s*%)?"
    r"(?:\s*(?P<mult>triliun|trilyun|trillion|miliar|milyar|billion|juta|million|ribu|thousand)\b)?",
    re.IGNORECASE,
)
_DASH_TOKEN_RE = re.compile(r"(?<!\S)[-–—](?!\S)")
_NOTE_REF_RE = re.compile(r"^\d{1,2}(?:[.,]\d{1,2})*[a-z]?$", re.IGNORECASE)
_YEAR_RE = re.compile(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)")

_MULTIPLIERS: dict[str, Decimal] = {
    "triliun": Decimal(10) ** 12,
    "trilyun": Decimal(10) ** 12,
    "trillion": Decimal(10) ** 12,
    "miliar": Decimal(10) ** 9,
    "milyar": Decimal(10) ** 9,
    "billion": Decimal(10) ** 9,
    "juta": Decimal(10) ** 6,
    "million": Decimal(10) ** 6,
    "ribu": Decimal(10) ** 3,
    "thousand": Decimal(10) ** 3,
}

_UNIT_HINT_CODES: dict[str, Decimal] = {
    "IDR": _ONE,
    "IDR_FULL": _ONE,
    "IDR_K": Decimal(10) ** 3,
    "IDR_TH": Decimal(10) ** 3,
    "IDR_THOUSANDS": Decimal(10) ** 3,
    "IDR_MN": Decimal(10) ** 6,
    "IDR_MILLIONS": Decimal(10) ** 6,
    "IDR_BN": Decimal(10) ** 9,
    "IDR_BILLIONS": Decimal(10) ** 9,
    "USD": _ONE,
    "USD_K": Decimal(10) ** 3,
    "USD_MN": Decimal(10) ** 6,
    "USD_BN": Decimal(10) ** 9,
}

# Ordered: the earliest match on the page wins.
_PAGE_SCALE_PATTERNS: list[tuple[re.Pattern[str], Decimal]] = [
    (re.compile(r"\b(?:dalam|in)\s+(?:jutaan|juta|millions?)\b", re.I), Decimal(10) ** 6),
    (
        re.compile(r"\b(?:dalam|in)\s+(?:miliaran|miliar|milyaran|milyar|billions?)\b", re.I),
        Decimal(10) ** 9,
    ),
    (re.compile(r"\b(?:dalam|in)\s+(?:ribuan|ribu|thousands?)\b", re.I), Decimal(10) ** 3),
    (re.compile(r"\(\s*(?:rp|idr)\s*(?:juta|jutaan|million|mn)\s*\)", re.I), Decimal(10) ** 6),
    (re.compile(r"\(\s*(?:rp|idr)\s*(?:miliar|milyar|billion|bn)\s*\)", re.I), Decimal(10) ** 9),
    (re.compile(r"\b(?:dalam|in)\s+(?:rupiah\s+penuh|full\s+rupiah)\b", re.I), _ONE),
    (
        re.compile(
            r"\b(?:disajikan|dinyatakan|expressed|presented|stated)\s+(?:dalam|in)\s+"
            r"(?:rupiah|dolar|us\s+dollars?|dollars?)\b(?!\s+(?:juta|ribu|miliar))",
            re.I,
        ),
        _ONE,
    ),
]

_MONTHS: dict[str, int] = {
    "januari": 1, "january": 1, "jan": 1,
    "februari": 2, "february": 2, "feb": 2,
    "maret": 3, "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "mei": 5, "may": 5,
    "juni": 6, "june": 6, "jun": 6,
    "juli": 7, "july": 7, "jul": 7,
    "agustus": 8, "august": 8, "aug": 8, "agu": 8,
    "september": 9, "sep": 9, "sept": 9,
    "oktober": 10, "october": 10, "oct": 10, "okt": 10,
    "november": 11, "nov": 11,
    "desember": 12, "december": 12, "dec": 12, "des": 12,
}  # fmt: skip
_DATE_RE = re.compile(
    r"(?:(?P<d1>\d{1,2})\s+(?P<m1>[a-z]{3,9})\.?\s+(?P<y1>(?:19|20)\d{2}))"
    r"|(?:(?P<m2>[a-z]{3,9})\.?\s+(?P<d2>\d{1,2}),?\s+(?P<y2>(?:19|20)\d{2}))",
    re.IGNORECASE,
)

LABEL_MATCH_THRESHOLD = 80.0
_LABEL_STOPWORDS = frozenset(
    {"total", "jumlah", "catatan", "note", "notes", "dan", "and", "the", "of", "yang", "atas"}
)
_PERCENT_UNITS = frozenset({"PERCENT", "PERCENTAGE", "PCT", "%", "RATIO", "X", "TIMES"})
_MONETARY_PREFIXES = ("IDR", "USD", "EUR", "SGD", "JPY", "CNY", "RP")


@dataclass(frozen=True)
class NumberToken:
    """A numeric token found in page or cell text."""

    raw: str
    values: tuple[Decimal, ...]
    precisions: tuple[Decimal, ...]
    is_dash: bool = False
    is_year: bool = False
    is_percent: bool = False
    is_note_ref: bool = False
    has_grouping: bool = False
    multiplier: Decimal | None = None

    @property
    def is_amount(self) -> bool:
        """True for tokens that look like reported amounts (not years or note references)."""
        if self.is_year or self.is_note_ref:
            return False
        return self.is_dash or self.has_grouping or self.is_percent or self.multiplier is not None


@dataclass
class GroundingOutcome:
    """Result of grounding one fact against its cited page."""

    ok: bool
    kind: GroundingKind | None = None
    issues: list[tuple[str, str, str]] = field(default_factory=list)  # (severity, category, msg)
    confidence: float | None = None
    bbox: list[float] | None = None
    scale: Decimal = _ONE
    scale_source: str = "default"

    def add(self, severity: str, category: str, message: str) -> None:
        self.issues.append((severity, category, message))


def _parse_number_string(s: str) -> tuple[list[tuple[Decimal, Decimal]], bool]:
    """Returns ([(candidate, precision)], has_grouping) for a bare digit/separator string."""
    cands: list[tuple[Decimal, Decimal]] = []
    grouping = False

    def _add(txt: str, precision: Decimal) -> None:
        with contextlib.suppress(InvalidOperation, ValueError):
            d = Decimal(txt)
            if all(d != c for c, _p in cands):
                cands.append((d, precision))

    if "." in s and "," in s:
        grouping = True
        dec_sep = "," if s.rfind(",") > s.rfind(".") else "."
        int_part, frac = s.rsplit(dec_sep, 1)
        _add(re.sub(r"[.,]", "", int_part) + "." + frac, Decimal(10) ** -len(frac))
    elif s.count(".") > 1 or s.count(",") > 1:
        grouping = True
        _add(re.sub(r"[.,]", "", s), _ONE)
    elif "." in s or "," in s:
        sep = "." if "." in s else ","
        int_part, frac = s.split(sep)
        if len(frac) == 3 and 1 <= len(int_part) <= 3:
            grouping = True
            _add(int_part + frac, _ONE)
        _add(int_part + "." + frac, Decimal(10) ** -len(frac))
    else:
        _add(s, _ONE)
    return cands, grouping


def tokenize_numbers(text: str) -> list[NumberToken]:
    """Extracts numeric tokens (amounts, percents, dashes, years, note refs) from text."""
    tokens: list[NumberToken] = []
    for m in _NUM_RE.finditer(text):
        num = m.group("num")
        cands, grouping = _parse_number_string(num)
        if not cands:
            continue
        paren = bool(m.group("open")) and bool(m.group("close"))
        neg = paren or bool(m.group("sign"))
        values = tuple(-c if neg else c for c, _p in cands)
        mult_word = (m.group("mult") or "").lower()
        is_year = (
            len(num) == 4
            and num.isdigit()
            and 1900 <= int(num) <= 2100
            and not paren
            and not m.group("cur")
            and not mult_word
        )
        is_note = (
            bool(
                _NOTE_REF_RE.match(num) and not paren and not m.group("cur") and not m.group("pct")
            )
            and not mult_word
        )
        tokens.append(
            NumberToken(
                raw=m.group(0).strip(),
                values=values,
                precisions=tuple(p for _c, p in cands),
                is_year=is_year,
                is_percent=bool(m.group("pct")),
                is_note_ref=is_note,
                has_grouping=grouping or paren or bool(m.group("cur")),
                multiplier=_MULTIPLIERS.get(mult_word) if mult_word else None,
            )
        )
    for _m in _DASH_TOKEN_RE.finditer(text):
        tokens.append(NumberToken(raw="-", values=(Decimal(0),), precisions=(_ONE,), is_dash=True))
    return tokens


def normalize_candidates(text: str) -> list[Decimal]:
    """Extracts and normalizes numeric values from financial text (years excluded)."""
    results: list[Decimal] = []
    for tok in tokenize_numbers(text):
        if tok.is_year or tok.is_dash:
            continue
        for v in tok.values:
            if v not in results:
                results.append(v)
    return results


def is_percent_unit(unit: str | None) -> bool:
    """True when a fact unit is a percentage or ratio (scale 1, fraction/percent tolerant)."""
    return (unit or "").strip().upper() in _PERCENT_UNITS


def is_monetary_unit(unit: str | None) -> bool:
    """True when the page/table monetary scale applies to the fact's unit."""
    u = (unit or "IDR").strip().upper()
    return u.startswith(_MONETARY_PREFIXES)


def resolve_scale(
    unit_hint: str | None,
    scaling_rules: dict[str, Any] | None = None,
) -> Decimal:
    """Returns the multiplier for a table unit_hint code, else the contract scaling rule, else 1."""
    hint_scale = scale_from_unit_hint(unit_hint)
    if hint_scale is not None:
        return hint_scale
    contract_scale = scale_from_rules(scaling_rules)
    return contract_scale if contract_scale is not None else _ONE


def scale_from_unit_hint(unit_hint: str | None) -> Decimal | None:
    """Maps a table unit_hint (IDR_MN, IDR_BN, IDR_K, IDR, or legacy phrases) to a multiplier."""
    if not unit_hint:
        return None
    code = unit_hint.strip().upper()
    if code in _UNIT_HINT_CODES:
        return _UNIT_HINT_CODES[code]
    return detect_page_scale(f"dalam {unit_hint}") or (
        _ONE if code.startswith(("IDR", "RUPIAH")) else None
    )


def scale_from_rules(scaling_rules: dict[str, Any] | None) -> Decimal | None:
    """Reads the numeric multiplier of a contract scaling rule."""
    if not scaling_rules:
        return None
    for key in ("multiplier", "scale"):
        if key in scaling_rules:
            with contextlib.suppress(InvalidOperation, ValueError, TypeError):
                return Decimal(str(scaling_rules[key]))
    return None


def detect_page_scale(text: str) -> Decimal | None:
    """Scale declared in page text ('dalam jutaan Rupiah' → 1e6); the earliest declaration wins."""
    best: tuple[int, Decimal] | None = None
    for pat, scale in _PAGE_SCALE_PATTERNS:
        m = pat.search(text)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), scale)
    return best[1] if best else None


def dominant_scale(pages: dict[int, PageEvidence]) -> Decimal | None:
    """Most common declared page scale across the document (fallback for pages without one)."""
    counts: Counter[Decimal] = Counter()
    for ev in pages.values():
        s = detect_page_scale(ev.page_text[:1500])
        if s is not None:
            counts[s] += 1
    return counts.most_common(1)[0][0] if counts else None


def fact_scale(
    fact: ExtractedFactItem,
    page_ev: PageEvidence | None,
    *,
    doc_scale: Decimal | None,
    contract_scale: Decimal | None,
) -> tuple[Decimal, str]:
    """ONE scale per fact: table unit_hint → page header → document → contract rule."""
    if is_percent_unit(fact.unit) or not is_monetary_unit(fact.unit):
        return _ONE, "unit"
    if page_ev is not None:
        if fact.cell_ref is not None:
            tbl = next(
                (t for t in page_ev.tables if t.table_index == fact.cell_ref.table_index), None
            )
            if tbl is not None:
                s = scale_from_unit_hint(tbl.unit_hint)
                if s is not None:
                    return s, f"table unit_hint {tbl.unit_hint}"
        else:
            hints = Counter(
                s for s in (scale_from_unit_hint(t.unit_hint) for t in page_ev.tables) if s
            )
            if hints:
                return hints.most_common(1)[0][0], "page table unit_hint"
        s = detect_page_scale(page_ev.page_text)
        if s is not None:
            return s, "page header"
    if doc_scale is not None:
        return doc_scale, "document header"
    if contract_scale is not None:
        return contract_scale, "contract scaling rule"
    return _ONE, "default"


def token_matches(
    tok: NumberToken, value: Decimal, scale: Decimal, *, percent: bool = False
) -> bool:
    """Does a token ground `value` at `scale` (±1 unit of scale; sign-insensitive)?"""
    target = abs(value)
    if tok.is_dash:
        return value == 0
    if tok.is_year:
        return False
    for cand, precision in zip(tok.values, tok.precisions, strict=True):
        c = abs(cand)
        if tok.multiplier is not None:
            if abs(c * tok.multiplier - target) <= precision * tok.multiplier / 2:
                return True
            continue
        if percent:
            if abs(c - target) <= Decimal("1e-9") or abs(c - target * 100) <= Decimal("1e-6"):
                return True
            continue
        if abs(c * scale - target) <= scale:
            return True
    return False


# ---------------------------------------------------------------------------
# Label matching
# ---------------------------------------------------------------------------

# Common English words of bilingual IDX statements; stripped from row text when the fact
# label is Indonesian (and kept alone when it is English) so interleaved halves compare cleanly.
_EN_WORDS = frozenset(
    """
    and of the at in on to for from with by as or its their other others net gross
    cash equivalents bank banks balances assets asset liabilities liability equity current
    non noncurrent revenue revenues sales income expense expenses cost costs goods sold
    profit loss losses gain gains period year years end beginning ended month months nine six
    three twelve operating operations activities activity investing financing provided used
    trade receivables receivable payables payable related party parties third share shares
    capital paid additional retained earnings appropriated unappropriated reserve general
    interest finance tax taxes before after attributable owners parent controlling interests
    comprehensive fair value biological deferred charges advances suppliers prepaid inventories
    fixed right use lease leases investment investments associates associate employee
    employees benefits benefit short long term accrued contract contracts customers customer
    distribution selling administrative dividends dividend payments payment received receipts
    proceeds additions disposals increase decrease effects exchange rate changes loans loan
    deposits deposit borrowings allowance impairment plasma claims refund assessments appeal
    held sale unless otherwise stated expressed millions rupiah amount full maturities
    """.split()
)


def normalize_label(text: str) -> str:
    """Lowercases, strips numbers/punctuation and generic words for label comparison."""
    t = text.lower().replace("\n", " ")
    t = re.sub(r"[^a-z\u00c0-\u024f ]+", " ", t)
    words = [w for w in t.split() if w not in _LABEL_STOPWORDS and len(w) > 1]
    return " ".join(words)


def _squash(text: str) -> str:
    return re.sub(r"[^a-z]", "", text.lower())


def _english_share(text: str) -> float:
    words = re.findall(r"[a-z]+", text.lower())
    return sum(w in _EN_WORDS for w in words) / len(words) if words else 0.0


def _language_variants(candidate: str, fact_is_english: bool) -> list[str]:
    words = re.findall(r"[A-Za-z\u00c0-\u024f]+", candidate)
    if fact_is_english:
        only_en = " ".join(w for w in words if w.lower() in _EN_WORDS or w.lower() == "total")
        return [candidate, only_en] if only_en else [candidate]
    no_en = " ".join(w for w in words if w.lower() not in _EN_WORDS)
    return [candidate, no_en] if no_en else [candidate]


def label_score(fact_label: str, candidate: str) -> float:
    """Similarity of a fact label and a row label (0..100), order-insensitive, penalizing extras."""
    a = normalize_label(fact_label)
    if not a:
        # A label made only of generic words ("Total", "Jumlah") matches only itself.
        # The row must itself be generic-only, so "Total" never matches "Total Aset".
        raw = _squash(fact_label)
        words = {_squash(w) for w in re.findall(r"[A-Za-z]+", candidate)}
        return 100.0 if raw and raw in words and not normalize_label(candidate) else 0.0
    best = 0.0
    for variant in _language_variants(candidate, _english_share(fact_label) >= 0.6):
        b = normalize_label(variant)
        if not b:
            continue
        if a == b or _squash(a) == _squash(b):
            return 100.0
        best = max(
            best, float(fuzz.token_sort_ratio(a, b)), float(fuzz.ratio(_squash(a), _squash(b)))
        )
    return best


def best_label_score(fact_label: str, candidates: list[str]) -> float:
    """Best label_score over candidate row texts."""
    return max((label_score(fact_label, c) for c in candidates), default=0.0)


def _text_chunks(line: str) -> list[str]:
    """Letter-bearing text segments of a line, split around numeric tokens."""
    parts = re.split(r"\(?\s*[-\u2013\u2212]?\s*\d[\d.,]*\s*\)?%?", line)
    return [p.strip(" -/:") for p in parts if len(re.findall(r"[A-Za-z]", p)) >= 3]


# ---------------------------------------------------------------------------
# Column (period) checks
# ---------------------------------------------------------------------------


def sorted_dates(text: str) -> list[tuple[int | None, int | None, int]]:
    """(day, month, year) triples in textual order; bare years give (None, None, year)."""
    items: list[tuple[int, tuple[int | None, int | None, int]]] = []
    spans: list[tuple[int, int]] = []
    for m in _DATE_RE.finditer(text):
        mon = _MONTHS.get((m.group("m1") or m.group("m2") or "").lower())
        if mon is None:
            continue
        day = int(m.group("d1") or m.group("d2"))
        items.append((m.start(), (day, mon, int(m.group("y1") or m.group("y2")))))
        spans.append(m.span())
    for m in _YEAR_RE.finditer(text):
        if not any(s <= m.start() < e for s, e in spans):
            items.append((m.start(), (None, None, int(m.group(1)))))
    return [d for _p, d in sorted(items, key=lambda x: x[0])]


def period_matches_header(header: str, period_end: date) -> bool | None:
    """True/False when the header names a period; None when it names none."""
    dates = sorted_dates(header)
    if not dates:
        return None
    return any(
        yr == period_end.year and (mon is None or mon == period_end.month) for _d, mon, yr in dates
    )


def page_header_years(page_text: str, period_end: date, max_lines: int = 25) -> list[int]:
    """Column year order at the top of a page: first line naming >=2 plausible, distinct years."""
    lo, hi = period_end.year - 2, period_end.year
    for line in page_text.splitlines()[:max_lines]:
        dedup: list[int] = []
        for _d, _m, y in sorted_dates(line):
            if not dedup or dedup[-1] != y:
                dedup.append(y)
        if len(set(dedup)) >= 2 and all(lo <= y <= hi for y in dedup) and hi in dedup:
            return dedup
    return []


def _is_amount_cell(c: PageTableCell) -> bool:
    if c.value is None:
        return c.text.strip() in ("-", "\u2013", "\u2014")
    t = c.text.strip()
    return bool(re.search(r"\d[.,]\d{3}", t) or "(" in t or abs(c.value) >= 1000)


def _amount_columns(table: PageTable) -> list[int]:
    counts: Counter[int] = Counter(
        c.col for c in table.cells if _is_amount_cell(c) and c.value is not None
    )
    return sorted(col for col, n in counts.items() if n >= 2)


def column_header_text(table: PageTable, row: int, col: int) -> str:
    """Nearest cell text above (row, col) in the same column that names a period."""
    above = sorted((c for c in table.cells if c.col == col and c.row < row), key=lambda c: -c.row)
    for c in above:
        if sorted_dates(c.text):
            return c.text
    return ""


def check_cell_period(
    table: PageTable, cell: PageTableCell, page_text: str, period_end: date
) -> str | None:
    """Error message when the cited column's header names a different period, else None."""
    header = column_header_text(table, cell.row, cell.col)
    if header:
        if period_matches_header(header, period_end) is False:
            return (
                f"column header '{header.strip()}' does not match the payload period "
                f"ending {period_end.isoformat()}"
            )
        return None
    years = page_header_years(page_text, period_end)
    amount_cols = _amount_columns(table)
    if years and cell.col in amount_cols and len(amount_cols) == len(years):
        yr = years[amount_cols.index(cell.col)]
        if yr != period_end.year:
            return (
                f"column {cell.col} is the {yr} column per the page header "
                f"(columns ordered {years}); the payload period ends {period_end.isoformat()}"
            )
    return None


# ---------------------------------------------------------------------------
# Row labels
# ---------------------------------------------------------------------------


def _clean_label_text(text: str) -> str:
    return " ".join(_text_chunks(text))


def _row_label_texts(table: PageTable, row: int, exclude_col: int | None = None) -> list[str]:
    out: list[str] = []
    for c in sorted((c for c in table.cells if c.row == row), key=lambda c: c.col):
        if c.col == exclude_col and c.value is not None:
            continue
        t = _clean_label_text(c.text)
        if t:
            out.append(t)
    return out


def _row_has_amounts(table: PageTable, row: int) -> bool:
    return any(_is_amount_cell(c) for c in table.cells if c.row == row)


def _combine(own: list[str], wrapped: list[str], header: list[str]) -> list[str]:
    cands = list(own)
    for k in range(len(wrapped)):
        joined = " ".join(wrapped[k:])
        cands += [f"{joined} {o}" for o in own]
    cands += [f"{h} {o}" for h in header for o in own]
    return cands


def row_label_candidates(table: PageTable, row: int, col: int) -> list[str]:
    """Row label, plus wrapped-label and section-header combinations from the rows above."""
    own = _row_label_texts(table, row, exclude_col=col)
    rows = sorted({c.row for c in table.cells})
    above = [r for r in rows if r < row][::-1]
    wrapped: list[str] = []
    for r in above:
        if _row_has_amounts(table, r) or len(wrapped) >= 3:
            break
        labels = _row_label_texts(table, r)
        if not labels:
            break
        wrapped.insert(0, " ".join(labels))
    header: list[str] = []
    for r in above[:8]:
        if not _row_has_amounts(table, r):
            labels = _row_label_texts(table, r)
            if labels:
                header = [" ".join(labels)]
                break
    return _combine(own, wrapped, header)


# ---------------------------------------------------------------------------
# Cell and text grounding
# ---------------------------------------------------------------------------


def is_synthetic_bbox(bbox: list[float] | None) -> bool:
    """Legacy parsers synthesized [0, 15r, 500, 15(r+1)] boxes; [0,0,0,0] is a placeholder."""
    if not bbox or len(bbox) != 4:
        return True
    x0, y0, x1, y1 = bbox
    if x0 == 0 and y0 == 0 and x1 == 0 and y1 == 0:
        return True
    return bool(x0 == 0.0 and x1 == 500.0 and abs((y1 - y0) - 15.0) < 1e-6 and y0 % 15 == 0)


def check_cell_grounding(
    fact: ExtractedFactItem,
    page_evidence: PageEvidence,
    default_scale: Decimal | None = None,
    *,
    period_end: date | None = None,
) -> tuple[bool, str | None, float | None, list[float] | None]:
    """Back-compatible wrapper: (is_grounded, error, confidence, bbox) for the value only.

    The scale is the fact's single scale (table unit_hint first); `default_scale` is only the
    contract fallback."""
    scale, src = fact_scale(fact, page_evidence, doc_scale=None, contract_scale=default_scale)
    out = ground_cell(
        fact, page_evidence, scale=scale, period_end=period_end, check_label=False, scale_source=src
    )
    err = next((m for _s, _c, m in out.issues), None)
    return out.ok, err, out.confidence, out.bbox


def ground_cell(
    fact: ExtractedFactItem,
    page_ev: PageEvidence,
    *,
    scale: Decimal,
    period_end: date | None,
    check_label: bool = True,
    scale_source: str = "",
) -> GroundingOutcome:
    """Cell grounding: value at the cited cell, column period, and row label."""
    out = GroundingOutcome(ok=False, scale=scale, scale_source=scale_source)
    ref = fact.cell_ref
    if ref is None:
        out.add("ERROR", "GROUNDING_CELL", "Fact has no cell_ref")
        return out
    table = next((t for t in page_ev.tables if t.table_index == ref.table_index), None)
    if table is None:
        out.add(
            "ERROR",
            "GROUNDING_CELL",
            f"Table index {ref.table_index} not found on page {fact.source_page}.",
        )
        return out
    cell = next((c for c in table.cells if c.row == ref.row and c.col == ref.col), None)
    if cell is None:
        out.add(
            "ERROR",
            "GROUNDING_CELL",
            f"Cell (row={ref.row}, col={ref.col}) not found in table {ref.table_index} on page {fact.source_page}.",
        )
        return out

    percent = is_percent_unit(fact.unit)
    text = cell.text.strip()
    if text and all(ch in _DASHES for ch in text):
        matched = fact.value_numeric == 0
        shown = "-"
    elif cell.value is not None:
        tok = NumberToken(raw=text, values=(Decimal(str(cell.value)),), precisions=(_ONE,))
        matched = token_matches(tok, fact.value_numeric, scale, percent=percent)
        shown = str(cell.value)
    else:
        toks = [t for t in tokenize_numbers(text) if not t.is_year and not t.is_note_ref]
        matched = any(token_matches(t, fact.value_numeric, scale, percent=percent) for t in toks)
        shown = repr(text)
    if not matched:
        out.add(
            "ERROR",
            "GROUNDING_CELL",
            f"Fact '{fact.concept_id}' value {fact.value_numeric} does not match cell "
            f"({ref.table_index}, {ref.row}, {ref.col}) value {shown} at scale {scale:,} "
            f"({scale_source or 'scale'}; tolerance ±{scale:,}) on page {fact.source_page}.",
        )
        return out

    if period_end is not None:
        period_err = check_cell_period(table, cell, page_ev.page_text, period_end)
        if period_err:
            out.add(
                "ERROR",
                "GROUNDING_COLUMN_PERIOD",
                f"Fact '{fact.concept_id}' cites cell ({ref.table_index}, {ref.row}, {ref.col}) on page "
                f"{fact.source_page} but {period_err}. Check you used the current-period column.",
            )
    if check_label:
        label = (fact.source_label_original or "").strip()
        cands = row_label_candidates(table, ref.row, ref.col)
        own_text = _clean_label_text(cell.text)
        if own_text:
            cands.append(own_text)
        score = best_label_score(label, cands)
        if score < LABEL_MATCH_THRESHOLD:
            shown_row = (
                " | ".join(_row_label_texts(table, ref.row, exclude_col=ref.col)) or "(no label)"
            )
            out.add(
                "ERROR",
                "ROW_LABEL_MISMATCH",
                f"Fact '{fact.concept_id}' label '{label}' does not match the row label of cell "
                f"({ref.table_index}, {ref.row}, {ref.col}) on page {fact.source_page}: '{shown_row}'. "
                f"Use the row's own label (prefix the section header for sub-rows, e.g. "
                f"'<header> - <row>').",
            )
    out.ok = not any(sev == "ERROR" for sev, _c, _m in out.issues)
    out.kind = "cell" if out.ok else None
    cell_conf = cell.confidence if cell.confidence is not None else table.confidence
    out.confidence = min(float(table.confidence), float(cell_conf))
    out.bbox = None if is_synthetic_bbox(cell.bbox) else cell.bbox
    return out


@dataclass
class _Line:
    text: str
    tokens: list[NumberToken]
    chunks: list[str]

    @property
    def amounts(self) -> list[NumberToken]:
        return [t for t in self.tokens if t.is_amount]


def _parse_lines(page_text: str) -> list[_Line]:
    lines = []
    for raw in page_text.splitlines():
        toks = sorted_tokens(raw)
        lines.append(_Line(text=raw, tokens=toks, chunks=_text_chunks(raw)))
    return lines


def sorted_tokens(line: str) -> list[NumberToken]:
    """Tokens in textual order (dash tokens included at their position)."""
    items: list[tuple[int, NumberToken]] = []
    for m in _NUM_RE.finditer(line):
        toks = tokenize_numbers(m.group(0))
        if toks:
            items.append((m.start(), toks[0]))
    for m in _DASH_TOKEN_RE.finditer(line):
        items.append(
            (
                m.start(),
                NumberToken(raw="-", values=(Decimal(0),), precisions=(_ONE,), is_dash=True),
            )
        )
    return [t for _p, t in sorted(items, key=lambda x: x[0])]


def _line_label_candidates(lines: list[_Line], i: int) -> list[str]:
    own = lines[i].chunks
    wrapped: list[str] = []
    for j in range(i - 1, max(-1, i - 4), -1):
        if not lines[j].chunks or lines[j].amounts:
            break
        wrapped.insert(0, " ".join(lines[j].chunks))
    header: list[str] = []
    for j in range(i - 1, max(-1, i - 8), -1):
        if lines[j].chunks and not lines[j].amounts:
            header = [" ".join(lines[j].chunks)]
            break
    cands = _combine(own, wrapped, header)
    if own and not lines[i].amounts and i + 1 < len(lines):
        cands += [f"{' '.join(own)} {n}" for n in lines[i + 1].chunks]
    return cands


_SUBTOTAL_MAX_ROWS = 15


def _block_subtotal_line(lines: list[_Line], header: int) -> int | None:
    """The unlabeled subtotal line closing the block that starts at `header`, if any.

    Member rows below the header must each carry a label and an amount (or be label-only
    continuation lines); the first amounts-only line with no label is the block's subtotal.
    """
    saw_member = False
    for j in range(header + 1, min(len(lines), header + 1 + _SUBTOTAL_MAX_ROWS)):
        ln = lines[j]
        if ln.amounts and not ln.chunks:
            return j if saw_member else None
        if ln.amounts:
            saw_member = True
    return None


def ground_text(
    fact: ExtractedFactItem,
    page_ev: PageEvidence,
    *,
    scale: Decimal,
    period_end: date | None,
    window: int = 3,
    scale_source: str = "",
) -> GroundingOutcome:
    """Strict text grounding: the number at ONE scale, within ±window lines of its label."""
    out = GroundingOutcome(ok=False, scale=scale, scale_source=scale_source)
    percent = is_percent_unit(fact.unit)
    lines = _parse_lines(page_ev.page_text)
    value_hits: list[tuple[int, int]] = []  # (line, amount ordinal)
    for i, ln in enumerate(lines):
        amounts = ln.amounts
        for tok in ln.tokens:
            if tok.is_year or (tok.is_note_ref and scale > 1):
                continue
            if token_matches(tok, fact.value_numeric, scale, percent=percent):
                ordinal = next((k for k, a in enumerate(amounts) if a is tok), -1)
                value_hits.append((i, ordinal))
    if not value_hits:
        out.add(
            "ERROR",
            "GROUNDING_TEXT",
            f"Fact '{fact.concept_id}' value {fact.value_numeric} not found in text on page "
            f"{fact.source_page} at scale {scale:,} ({scale_source or 'scale'}).",
        )
        return out

    label = (fact.source_label_original or "").strip()
    label_lines = [
        i
        for i in range(len(lines))
        if lines[i].chunks
        and best_label_score(label, _line_label_candidates(lines, i)) >= LABEL_MATCH_THRESHOLD
    ]
    accepted: tuple[int, int] | None = None
    for li in label_lines:
        for vi, ordinal in value_hits:
            if vi == li or (
                abs(vi - li) <= window and not lines[vi].chunks and not lines[li].amounts
            ):
                accepted = (vi, ordinal)
                break
        if accepted:
            break
    if accepted is None:
        # Block subtotal: a section header with no amount ("Ekuitas yang Dapat Diatribusikan
        # kepada Pemilik Entitas Induk") whose total is the first unlabeled amounts-only line
        # below its member rows.
        for li in label_lines:
            if lines[li].amounts:
                continue
            sub = _block_subtotal_line(lines, li)
            hit = next(((vi, o) for vi, o in value_hits if vi == sub), None)
            if hit is not None:
                accepted = hit
                break
    if accepted is None:
        where = sorted({vi + 1 for vi, _o in value_hits})[:6]
        if label_lines:
            msg = (
                f"Fact '{fact.concept_id}' value {fact.value_numeric} appears on page {fact.source_page} "
                f"(lines {where}) but not within ±{window} lines of the label '{label}' "
                f"(label lines {[x + 1 for x in label_lines[:6]]}). Cite the row that carries this label."
            )
        else:
            msg = (
                f"Fact '{fact.concept_id}' label '{label}' was not found on page {fact.source_page}; "
                f"the value appears on lines {where}. Use the label exactly as printed next to the number."
            )
        out.add("ERROR", "GROUNDING_TEXT_LABEL_DISTANCE", msg)
        return out

    vi, ordinal = accepted
    if period_end is not None and ordinal >= 0:
        years = page_header_years(page_ev.page_text, period_end)
        n_amounts = len(lines[vi].amounts)
        if years and n_amounts == len(years) and years[ordinal] != period_end.year:
            out.add(
                "ERROR",
                "GROUNDING_COLUMN_PERIOD",
                f"Fact '{fact.concept_id}' value {fact.value_numeric} is in the {years[ordinal]} column of "
                f"page {fact.source_page} (columns ordered {years}); the payload period ends "
                f"{period_end.isoformat()}. Check you used the current-period column.",
            )
            return out
    out.ok = True
    out.kind = "text"
    return out


def check_text_grounding(
    fact: ExtractedFactItem,
    page_evidence: PageEvidence,
    default_scale: Decimal | None = None,
) -> tuple[bool, str | None]:
    """Back-compatible wrapper: value-only text grounding at the page's single scale."""
    scale, src = fact_scale(fact, page_evidence, doc_scale=None, contract_scale=default_scale)
    percent = is_percent_unit(fact.unit)
    for tok in tokenize_numbers(page_evidence.page_text):
        if not (tok.is_note_ref and scale > 1) and token_matches(
            tok, fact.value_numeric, scale, percent=percent
        ):
            return True, None
    return (
        False,
        f"Fact '{fact.concept_id}' value {fact.value_numeric} not found in text on page "
        f"{fact.source_page} at scale {scale:,} ({src}).",
    )


def ground_fact(
    fact: ExtractedFactItem,
    page_ev: PageEvidence,
    *,
    period_end: date | None,
    doc_scale: Decimal | None = None,
    contract_scale: Decimal | None = None,
) -> GroundingOutcome:
    """Grounds one fact on its cited page: the single entry point used by validate AND commit.

    * ``ocr_failed`` page → ERROR ``GROUNDING_OCR_FAILED`` (no text to verify against).
    * ``cell_ref`` → value at the cited cell (one scale), column period, row label.
    * ``pdf_text`` page → the number at one scale within ±3 lines of its label, right column.
    * ``ocr`` page → the same text check; a miss is a WARNING ``GROUNDING_OCR`` and the fact is
      kept as ``ocr_unverified`` (needs review), because OCR digits are unreliable.
    """
    scale, src = fact_scale(fact, page_ev, doc_scale=doc_scale, contract_scale=contract_scale)
    if page_ev.text_source == "ocr_failed":
        out = GroundingOutcome(ok=False, scale=scale, scale_source=src)
        out.add(
            "ERROR",
            "GROUNDING_OCR_FAILED",
            f"Fact '{fact.concept_id}' cites page {fact.source_page}, which has no usable text "
            f"(OCR failed at index time), so the value cannot be verified. Cite a page with a text "
            f"layer, or have the page re-OCRed and re-indexed.",
        )
        return out
    if fact.cell_ref is not None:
        return ground_cell(fact, page_ev, scale=scale, period_end=period_end, scale_source=src)
    out = ground_text(fact, page_ev, scale=scale, period_end=period_end, scale_source=src)
    if page_ev.text_source == "ocr" and not out.ok:
        reasons = "; ".join(m for _s, _c, m in out.issues)
        out = GroundingOutcome(ok=True, kind="ocr_unverified", scale=scale, scale_source=src)
        out.add(
            "WARNING",
            "GROUNDING_OCR",
            f"Fact '{fact.concept_id}' on OCR page {fact.source_page} could not be confirmed in the "
            f"OCR text; stored as ocr_unverified and flagged for review ({reasons}).",
        )
    return out
