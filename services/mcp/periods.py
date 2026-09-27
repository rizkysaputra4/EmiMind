"""Fiscal period and reporting end-date resolution for financial documents."""

from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel


class ResolvedPeriod(BaseModel):
    """Result of fiscal period resolution."""

    fiscal_period: str
    period_end: date
    source: Literal["hint", "downloader_prefix", "filename_tokens"]


def period_end_for(fiscal_period: str) -> date:
    """Computes the standard closing date for a given fiscal period (e.g. 2025Q2 -> 2025-06-30)."""
    m = re.match(r"^(\d{4})Q([1-4])$", fiscal_period.strip().upper())
    if not m:
        raise ValueError(f"Invalid fiscal period format: {fiscal_period!r}")

    year = int(m.group(1))
    quarter = int(m.group(2))

    if quarter == 1:
        return date(year, 3, 31)
    if quarter == 2:
        return date(year, 6, 30)
    if quarter == 3:
        return date(year, 9, 30)
    return date(year, 12, 31)


def _resolve_from_hint(hint: str) -> ResolvedPeriod:
    h = hint.strip().upper()
    if re.match(r"^\d{4}FY$", h):
        h = f"{h[:4]}Q4"
    if not re.match(r"^\d{4}Q[1-4]$", h):
        raise ValueError(f"Invalid fiscal period hint: {hint!r}")
    return ResolvedPeriod(
        fiscal_period=h,
        period_end=period_end_for(h),
        source="hint",
    )


def _resolve_from_downloader_prefix(filename: str) -> ResolvedPeriod | None:
    m = re.match(
        r"^[A-Za-z0-9]+_(\d{4})_(TW1|TW2|TW3|AUDIT|ANNUAL)_",
        filename,
        re.IGNORECASE,
    )
    if not m:
        return None

    year = int(m.group(1))
    token = m.group(2).upper()
    q_map = {
        "TW1": "Q1",
        "TW2": "Q2",
        "TW3": "Q3",
        "AUDIT": "Q4",
        "ANNUAL": "Q4",
    }
    fp = f"{year}{q_map[token]}"
    return ResolvedPeriod(
        fiscal_period=fp,
        period_end=period_end_for(fp),
        source="downloader_prefix",
    )


def _extract_roman_numeral(filename: str) -> str | None:
    if re.search(r"[-_]IV[-_]", filename, re.IGNORECASE):
        return "Q4"
    if re.search(r"[-_]III[-_]", filename, re.IGNORECASE):
        return "Q3"
    if re.search(r"[-_]II[-_]", filename, re.IGNORECASE):
        return "Q2"
    if re.search(r"[-_]I[-_]", filename, re.IGNORECASE):
        return "Q1"
    return None


def _extract_composite_code(norm: str) -> tuple[int | None, str | None]:
    m = re.search(
        r"\b(1H|2H|H1|H2|Q[1-4]|FY|TW[1-4])\s*(\d{2})\b",
        norm,
        re.IGNORECASE,
    )
    if not m:
        return None, None

    tok = m.group(1).upper()
    yy = int(m.group(2))
    year = 2000 + yy

    if tok in ("1H", "H1"):
        q = "Q2"
    elif tok in ("2H", "H2", "FY"):
        q = "Q4"
    elif tok.startswith("Q"):
        q = tok
    elif tok.startswith("TW"):
        q = f"Q{tok[2:]}"
    else:
        q = None

    return year, q


def _extract_free_quarter(norm: str, roman_q: str | None) -> str | None:
    if roman_q:
        return roman_q
    if re.search(r"\bQ1\b|\bTW\s*1\b|\b3M\b|\b(maret|mar)\b", norm, re.IGNORECASE):
        return "Q1"
    if re.search(
        r"\bQ2\b|\bTW\s*2\b|\b(6M|1H|H1|semester\s*1|sem\s*1|juni|jun|june)\b",
        norm,
        re.IGNORECASE,
    ):
        return "Q2"
    if re.search(r"\bQ3\b|\bTW\s*3\b|\b(9M|september|sep|sept)\b", norm, re.IGNORECASE):
        return "Q3"
    if re.search(
        r"\bQ4\b|\bTW\s*4\b|\b(12M|audit|tahunan|annual|aar|\bar\b|fy|desember|december|des|dec)\b",
        norm,
        re.IGNORECASE,
    ):
        return "Q4"
    return None


def _resolve_from_filename_tokens(filename: str) -> ResolvedPeriod | None:
    roman_q = _extract_roman_numeral(filename)
    norm = re.sub(r"[_\-\.]+", " ", filename)

    year, q = _extract_composite_code(norm)

    if not year:
        m_yr = re.search(r"\b(20\d{2})\b", norm)
        if not m_yr:
            m_yr = re.search(r"\b(20\d{2})\d{2}\b", norm)
        if m_yr:
            year = int(m_yr.group(1))

    if not year:
        return None

    if not q:
        q = _extract_free_quarter(norm, roman_q)

    if not q:
        return None

    fp = f"{year}{q}"
    return ResolvedPeriod(
        fiscal_period=fp,
        period_end=period_end_for(fp),
        source="filename_tokens",
    )


def resolve_fiscal_period(filename: str, hint: str | None = None) -> ResolvedPeriod | None:
    """Resolves fiscal period and period-end date from filename and optional hint."""
    if hint:
        return _resolve_from_hint(hint)

    dl_res = _resolve_from_downloader_prefix(filename)
    if dl_res:
        return dl_res

    return _resolve_from_filename_tokens(filename)
