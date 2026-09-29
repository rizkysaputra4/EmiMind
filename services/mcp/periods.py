"""Fiscal period and reporting end-date resolution for financial documents."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import BaseModel

PeriodSource = Literal["hint", "downloader_prefix", "filename_tokens", "cover_page"]


class ResolvedPeriod(BaseModel):
    """Result of fiscal period resolution."""

    fiscal_period: str
    period_end: date
    source: PeriodSource
    # True when the downloader prefix disagrees with an explicit period elsewhere in the
    # filename; the caller must confirm the period from the document itself.
    conflict: bool = False
    conflicting_period: str | None = None


def period_end_for(fiscal_period: str) -> date:
    """Computes the standard closing date for a given fiscal period (e.g. 2025Q2 -> 2025-06-30)."""
    m = re.match(r"^(\d{4})Q([1-4])$", fiscal_period.strip().upper())
    if not m:
        raise ValueError(f"Invalid fiscal period format: {fiscal_period!r}")
    year = int(m.group(1))
    return {
        1: date(year, 3, 31),
        2: date(year, 6, 30),
        3: date(year, 9, 30),
        4: date(year, 12, 31),
    }[int(m.group(2))]


def normalize_period(value: str) -> str:
    """Normalizes `YYYYQn`, `YYYYFY`, `YYYYH1`/`YYYYH2` (any case/spacing) to `YYYYQn`."""
    h = re.sub(r"[\s\-_]+", "", value.strip().upper())
    m = re.match(r"^(\d{4})(Q[1-4]|FY|H[12])$", h)
    if not m:
        raise ValueError(f"Invalid fiscal period hint: {value!r}")
    year, tok = m.group(1), m.group(2)
    quarter = {"FY": "Q4", "H1": "Q2", "H2": "Q4"}.get(tok, tok)
    return f"{year}{quarter}"


def _make(fp: str, source: PeriodSource) -> ResolvedPeriod:
    return ResolvedPeriod(fiscal_period=fp, period_end=period_end_for(fp), source=source)


# --------------------------------------------------------------------------- tokens

_MONTHS: dict[str, int] = {
    "januari": 1, "january": 1, "jan": 1,
    "februari": 2, "february": 2, "feb": 2, "pebruari": 2,
    "maret": 3, "march": 3, "mar": 3, "mrt": 3,
    "april": 4, "apr": 4,
    "mei": 5, "may": 5,
    "juni": 6, "june": 6, "jun": 6,
    "juli": 7, "july": 7, "jul": 7,
    "agustus": 8, "august": 8, "agu": 8, "agt": 8, "aug": 8, "ags": 8,
    "september": 9, "sept": 9, "sep": 9, "sepr": 9,
    "oktober": 10, "october": 10, "okt": 10, "oct": 10,
    "november": 11, "nopember": 11, "nov": 11, "nop": 11,
    "desember": 12, "december": 12, "des": 12, "dec": 12,
}  # fmt: skip
_QUARTER_END = {3: "Q1", 6: "Q2", 9: "Q3", 12: "Q4"}
_HALF_Q = {"1H": 2, "H1": 2, "2H": 4, "H2": 4, "FY": 4, "3M": 1, "6M": 2, "9M": 3, "12M": 4}
_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4}

_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))
_SEP = r"[\s\-_.,]*"
# Two-digit years are only accepted in this window, so day numbers 30/31 never become years.
_YY_MIN, _YY_MAX = 10, 29

_DATE_DMY = re.compile(
    rf"(?<![0-9])(\d{{1,2}}){_SEP}({_MONTH_RE})(?![a-z]){_SEP}('?\d{{4}}|'?\d{{2}})(?![0-9])",
    re.IGNORECASE,
)
_DATE_MDY = re.compile(
    rf"(?<![a-z])({_MONTH_RE})(?![a-z]){_SEP}(\d{{1,2}})[\s,\-_.]+(\d{{4}})(?![0-9])",
    re.IGNORECASE,
)
_DATE_ISO = re.compile(r"(?<![0-9])(20\d{2})[-_.]?(\d{2})[-_.]?(\d{2})(?![0-9])")
_DATE_NUM_DMY = re.compile(r"(?<![0-9])(\d{2})[-_./](\d{2})[-_./](20\d{2})(?![0-9])")
_MONTH_YEAR = re.compile(
    rf"(?<![a-z0-9])({_MONTH_RE})(?![a-z]){_SEP}('?\d{{4}}|'?\d{{2}})(?![0-9])",
    re.IGNORECASE,
)
# A day number right before "Maret 2022" makes it a (letter) date, not a month-year period.
_DAY_BEFORE = re.compile(r"(?<![0-9])\d{1,2}[\s\-_./]*$")
_NUM_MONTH_YEAR = re.compile(r"(?<![0-9])(03|06|09|12)[\s\-_./]+(20\d{2})(?![0-9])")

_QTOKEN = r"(?:q|tw|triwulan|trimester|kuartal|kwartal|quarter)"
_QNUM = r"([1-4]|iv|iii|ii|i)"
_QUARTER_TOKEN = re.compile(rf"(?<![a-z0-9]){_QTOKEN}{_SEP}{_QNUM}(?![a-z0-9])", re.IGNORECASE)
_QUARTER_ORDINAL = re.compile(
    r"(?<![a-z0-9])([1-4])(?:st|nd|rd|th)?[\s\-_.]*(?:quarter|qtr)(?![a-z])", re.IGNORECASE
)
_SEMESTER_TOKEN = re.compile(
    r"(?<![a-z0-9])(?:semester|sem|smt)[\s\-_.]*(1|2|ii|i)(?![a-z0-9])", re.I
)
_HALF_TOKEN = re.compile(r"(?<![a-z0-9])(1h|2h|h1|h2|3m|6m|9m|12m)(?![a-z0-9])", re.IGNORECASE)
_COMPOSITE = re.compile(
    r"(?<![a-z0-9])(1h|2h|h1|h2|fy|q[1-4]|tw[1-4]|3m|6m|9m|12m)'?(\d{2})(?![0-9])", re.IGNORECASE
)
_IDX_ROMAN = re.compile(r"(?<![0-9])(20\d{2})-(iv|iii|ii|i)(?![a-z])", re.IGNORECASE)
_ANNUAL_WORD = r"(?:tahunan|annual\s*report|annualreport|annual|lkt|fy|audited|audit|ar)"
_ANNUAL_BEFORE_YEAR = re.compile(
    rf"(?<![a-z]){_ANNUAL_WORD}{_SEP}(?:tahun{_SEP})?(20\d{{2}})(?![0-9])", re.IGNORECASE
)
_ANNUAL_AFTER_YEAR = re.compile(
    rf"(?<![0-9])(20\d{{2}}){_SEP}(?:tahunan|annual|audited|audit|fy)(?![a-z])", re.IGNORECASE
)
_YEAR = re.compile(r"(?<![0-9])(20\d{2})(?![0-9])")
_YEAR_MONTH = re.compile(r"(?<![0-9])(20\d{2})(0[1-9]|1[0-2])(?![0-9])")
_WEAK_ANNUAL = re.compile(
    r"(?<![a-z])(12m|audit|audited|tahunan|annual|aar|ar|lkt|fy|desember|december|des|dec)(?![a-z])",
    re.IGNORECASE,
)

# Strengths: DATE (full quarter-end date) > EXPLICIT (quarter/month token bound to a year).
_DATE, _EXPLICIT = 3, 2


@dataclass(frozen=True)
class _Candidate:
    fiscal_period: str
    strength: int
    pos: int


def _year4(raw: str) -> int | None:
    y = raw.lstrip("'")
    if len(y) == 4:
        return int(y) if 2000 <= int(y) <= 2099 else None
    yy = int(y)
    return 2000 + yy if _YY_MIN <= yy <= _YY_MAX else None


def _q_from_num(tok: str) -> int:
    t = tok.upper()
    return _ROMAN[t] if t in _ROMAN else int(t)


def _year_near(text: str, start: int, end: int) -> int | None:
    after = re.match(
        rf"{_SEP}(?:fy|tahun|th)?{_SEP}('?\d{{4}}|'?\d{{2}})(?![0-9])", text[end:], re.I
    )
    if after:
        y = _year4(after.group(1))
        if y:
            return y
    before = re.search(rf"(20\d{{2}})(?:{_SEP}fy)?{_SEP}$", text[max(0, start - 12) : start], re.I)
    return int(before.group(1)) if before else None


def _date_candidates(text: str) -> list[_Candidate]:
    out: list[_Candidate] = []

    def add(year: int | None, month: int, day: int, pos: int) -> None:
        if year and month in _QUARTER_END and day in (30, 31):
            out.append(_Candidate(f"{year}{_QUARTER_END[month]}", _DATE, pos))

    for m in _DATE_DMY.finditer(text):
        add(_year4(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1)), m.start())
    for m in _DATE_MDY.finditer(text):
        add(_year4(m.group(3)), _MONTHS[m.group(1).lower()], int(m.group(2)), m.start())
    for m in _DATE_ISO.finditer(text):
        add(int(m.group(1)), int(m.group(2)), int(m.group(3)), m.start())
    for m in _DATE_NUM_DMY.finditer(text):
        add(int(m.group(3)), int(m.group(2)), int(m.group(1)), m.start())
    return out


def _explicit_candidates(text: str) -> list[_Candidate]:
    out: list[_Candidate] = []

    def add(year: int | None, quarter: int, pos: int) -> None:
        if year and 1 <= quarter <= 4:
            out.append(_Candidate(f"{year}Q{quarter}", _EXPLICIT, pos))

    for m in _MONTH_YEAR.finditer(text):
        month = _MONTHS[m.group(1).lower()]
        if month in _QUARTER_END and not _DAY_BEFORE.search(text[: m.start()]):
            add(_year4(m.group(2)), month // 3, m.start())
    for m in _NUM_MONTH_YEAR.finditer(text):
        if not _DAY_BEFORE.search(text[: m.start()]):
            add(int(m.group(2)), int(m.group(1)) // 3, m.start())
    for m in _QUARTER_TOKEN.finditer(text):
        add(_year_near(text, m.start(), m.end()), _q_from_num(m.group(1)), m.start())
    for m in _QUARTER_ORDINAL.finditer(text):
        add(_year_near(text, m.start(), m.end()), int(m.group(1)), m.start())
    for m in _SEMESTER_TOKEN.finditer(text):
        add(_year_near(text, m.start(), m.end()), 2 * _q_from_num(m.group(1)), m.start())
    for m in _HALF_TOKEN.finditer(text):
        add(_year_near(text, m.start(), m.end()), _HALF_Q[m.group(1).upper()], m.start())
    for m in _COMPOSITE.finditer(text):
        tok = m.group(1).upper()
        add(_year4(m.group(2)), _HALF_Q.get(tok) or int(tok[-1]), m.start())
    for m in _IDX_ROMAN.finditer(text):
        add(int(m.group(1)), _ROMAN[m.group(2).upper()], m.start())
    for m in _ANNUAL_BEFORE_YEAR.finditer(text):
        add(int(m.group(1)), 4, m.start())
    for m in _ANNUAL_AFTER_YEAR.finditer(text):
        add(int(m.group(1)), 4, m.start())
    return out


def _weak_quarter(text: str) -> int | None:
    if re.search(
        rf"(?<![a-z0-9]){_QTOKEN}{_SEP}1(?![0-9])|(?<![a-z0-9])3m(?![a-z0-9])", text, re.I
    ):
        return 1
    if re.search(r"(?<![a-z])(maret|march|mar)(?![a-z])", text, re.I):
        return 1
    if re.search(
        rf"(?<![a-z0-9]){_QTOKEN}{_SEP}2(?![0-9])|(?<![a-z0-9])(6m|1h|h1)(?![a-z0-9])", text, re.I
    ):
        return 2
    if _SEMESTER_TOKEN.search(text) or re.search(r"(?<![a-z])(juni|june|jun)(?![a-z])", text, re.I):
        sem = _SEMESTER_TOKEN.search(text)
        return 2 * _q_from_num(sem.group(1)) if sem else 2
    if re.search(
        rf"(?<![a-z0-9]){_QTOKEN}{_SEP}3(?![0-9])|(?<![a-z0-9])9m(?![a-z0-9])", text, re.I
    ):
        return 3
    if re.search(r"(?<![a-z])(september|sept|sep)(?![a-z])", text, re.I):
        return 3
    if re.search(rf"(?<![a-z0-9]){_QTOKEN}{_SEP}4(?![0-9])", text, re.I) or _WEAK_ANNUAL.search(
        text
    ):
        return 4
    return None


def _free_candidates(text: str) -> list[_Candidate]:
    return sorted(_date_candidates(text) + _explicit_candidates(text), key=lambda c: c.pos)


def _resolve_from_filename_tokens(filename: str) -> ResolvedPeriod | None:
    stem = re.sub(r"\.pdf$", "", filename, flags=re.IGNORECASE)
    cands = _free_candidates(stem)
    if cands:
        best = max(cands, key=lambda c: (c.strength, -c.pos))
        return _make(best.fiscal_period, "filename_tokens")

    comp = _YEAR_MONTH.search(stem)
    year_m = _YEAR.search(stem)
    year = int(year_m.group(1)) if year_m else (int(comp.group(1)) if comp else None)
    if not year:
        return None
    quarter = _weak_quarter(stem)
    if quarter is None and comp and int(comp.group(2)) in _QUARTER_END:
        quarter = int(comp.group(2)) // 3
    if quarter is None:
        return None
    return _make(f"{year}Q{quarter}", "filename_tokens")


_PREFIX = re.compile(r"^[A-Za-z0-9]+_(\d{4})_(TW1|TW2|TW3|AUDIT|ANNUAL)_", re.IGNORECASE)
_PREFIX_Q = {"TW1": "Q1", "TW2": "Q2", "TW3": "Q3", "AUDIT": "Q4", "ANNUAL": "Q4"}


def _resolve_from_downloader_prefix(filename: str) -> ResolvedPeriod | None:
    m = _PREFIX.match(filename)
    if not m:
        return None
    fp = f"{int(m.group(1))}{_PREFIX_Q[m.group(2).upper()]}"
    res = _make(fp, "downloader_prefix")

    rest = re.sub(r"\.pdf$", "", filename[m.end() :], flags=re.IGNORECASE)
    explicit = _free_candidates(rest)
    if explicit and all(c.fiscal_period != fp for c in explicit):
        best = max(explicit, key=lambda c: (c.strength, -c.pos))
        res.conflict = True
        res.conflicting_period = best.fiscal_period
    return res


def resolve_fiscal_period(filename: str, hint: str | None = None) -> ResolvedPeriod | None:
    """Resolves fiscal period and period-end date from filename and optional hint."""
    if hint:
        return _make(normalize_period(hint), "hint")
    dl_res = _resolve_from_downloader_prefix(filename)
    if dl_res:
        return dl_res
    return _resolve_from_filename_tokens(filename)


# ------------------------------------------------------------------ cover-page text

_DURATION_Q = [
    (re.compile(r"tiga\s+bulan|three[\s-]+month|3\s+bulan", re.I), 1),
    (re.compile(r"enam\s+bulan|six[\s-]+month|6\s+bulan|semester\s+(pertama|i\b|1)", re.I), 2),
    (re.compile(r"sembilan\s+bulan|nine[\s-]+month|9\s+bulan", re.I), 3),
    (
        re.compile(
            r"tahun\s+yang\s+berakhir|for\s+the\s+years?\s+(then\s+)?ended|laporan\s+tahunan"
            r"|annual\s+report|tahun\s+buku",
            re.I,
        ),
        4,
    ),
]


def resolve_period_from_text(text: str) -> ResolvedPeriod | None:
    """Deterministically resolves the reporting period from cover-page text (no LLM).

    Picks the most frequent quarter-end date; a duration phrase ("enam bulan", "for the
    year ended") narrows the candidates to that quarter; ties go to the latest date.
    """
    if not text or not text.strip():
        return None
    dates = [c.fiscal_period for c in _date_candidates(text)]
    if not dates:
        return None
    counts = Counter(dates)
    wanted = {q for rx, q in _DURATION_Q if rx.search(text)}
    if len(wanted) == 1:
        (q,) = wanted
        narrowed = {fp: n for fp, n in counts.items() if fp.endswith(f"Q{q}")}
        if narrowed:
            counts = Counter(narrowed)
    best = max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]
    return _make(best, "cover_page")
