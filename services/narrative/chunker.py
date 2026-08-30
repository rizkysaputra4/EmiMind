"""Semantic narrative text chunking and section classification."""

from __future__ import annotations

import re
from collections import Counter
from typing import Literal

import tiktoken

from services.shared.types import (
    DocType,
    FiscalPeriod,
    NarrativeChunkDraft,
    PageContent,
    Ticker,
)

ENCODING = tiktoken.get_encoding("cl100k_base")

# Running-header/footer detection parameters
HEADER_SCAN_LINES = 8  # lines from top of each page to consider as candidate header
FOOTER_SCAN_LINES = 4  # lines from bottom of each page to consider as candidate footer
REPEAT_THRESHOLD = 0.35  # a line is a running header if it appears on this fraction of pages

# Common prose connectors in Indonesian and English financial reporting
ID_PROSE_MARKERS = {
    "yang", "dan", "untuk", "pada", "dengan", "atas", "sebesar", "telah", "dapat",
    "merupakan", "sebagaimana", "dalam", "oleh", "karena", "adalah", "terhadap",
    "berdasarkan", "selama", "antara", "melalui", "secara", "sebagai", "sesuai",
    "tersebut", "mengalami", "meningkat", "menurun", "dicatat", "terdiri", "kebijakan",
}
EN_PROSE_MARKERS = {
    "the", "and", "for", "with", "that", "which", "from", "have", "has", "were",
    "was", "been", "are", "is", "will", "would", "shall", "under", "pursuant",
    "regarding", "including", "between", "during", "increased", "decreased", "consists",
}

# Generalized patterns for primary financial statement tables (Layer 2 numbers, not Layer 3 narrative)
PRIMARY_STMT_PATTERNS = [
    re.compile(r"laporan\s+posisi\s+keuangan|statement\s+of\s+financial\s+position|balance\s+sheet", re.I),
    re.compile(r"laporan\s+laba\s+rugi|statement\s+of\s+profit\s+or\s+loss|comprehensive\s+income", re.I),
    re.compile(r"laporan\s+arus\s+kas|statement\s+of\s+cash\s+flows", re.I),
    re.compile(r"laporan\s+perubahan\s+ekuitas|statement\s+of\s+changes\s+in\s+equity", re.I),
]

# Patterns for Table of Contents and pure cover/title pages
TOC_PATTERNS = [
    re.compile(r"^\s*(?:daftar\s+isi|table\s+of\s+contents)\s*$", re.I | re.M),
    re.compile(r"\.{4,}\s*\d{1,4}", re.M),  # Dot leaders like 'Laporan Posisi Keuangan ..... 1'
]

COVER_PATTERNS = [
    re.compile(r"laporan\s+keuangan\s+(?:konsolidasian|tahunan|interim|interim\s+yang\s+tidak\s+diaudit)", re.I),
    re.compile(r"unaudited\s+interim\s+consolidated\s+financial\s+statements", re.I),
    re.compile(r"annual\s+report\s+\d{4}|laporan\s+tahunan\s+\d{4}", re.I),
    re.compile(r"paparan\s+publik|public\s+expose\s+presentation", re.I),
    re.compile(r"surat\s+pernyataan\s+direksi|board\s+of\s+directors\s+statement", re.I),
]

SIGN_OFF_PATTERNS = [
    re.compile(r"^\s*(?:direksi|board\s+of\s+directors|dewan\s+komisaris|board\s+of\s+commissioners)\s*$", re.I | re.M),
    re.compile(r"^\s*(?:direktur\s+utama|president\s+director|direktur|director|komisaris\s+utama|president\s+commissioner)\s*$", re.I | re.M),
]


DISCLAIMER_PATTERNS = [
    re.compile(r"the\s+original\s+.*financial\s+statements\s+included\s+herein\s+are\s+in\s+the\s+indonesian\s+language.*", re.I),
    re.compile(r"laporan\s+keuangan\s+konsolidasian\s+terlampir\s+disusun\s+dalam\s+bahasa\s+indonesia.*", re.I),
    re.compile(r"lihat\s+catatan\s+atas\s+laporan\s+keuangan.*merupakan\s+bagian\s+integral.*", re.I),
    re.compile(r"see\s+notes\s+to\s+.*financial\s+statements.*integral\s+part.*", re.I),
]


def _normalize_line(s: str) -> str:
    """Normalize a line for repetition comparison (collapse whitespace, drop pure page numbers)."""
    t = re.sub(r"\s+", " ", s).strip()
    return t


def detect_repeating_lines(pages: list[PageContent]) -> set[str]:
    """Finds normalized lines that recur across many pages (running headers / footers).

    Only scans the top HEADER_SCAN_LINES and bottom FOOTER_SCAN_LINES of each page,
    then flags any line appearing on at least REPEAT_THRESHOLD of pages.
    """
    if len(pages) < 3:
        return set()

    counter: Counter[str] = Counter()
    for page in pages:
        if not page.text:
            continue
        lines = [ln for ln in page.text.splitlines() if ln.strip()]
        if not lines:
            continue
        head = lines[:HEADER_SCAN_LINES]
        tail = lines[-FOOTER_SCAN_LINES:] if len(lines) > HEADER_SCAN_LINES else []
        seen_on_page: set[str] = set()
        for ln in head + tail:
            norm = _normalize_line(ln)
            if len(norm) < 3:
                continue
            # Skip lines that look like standalone page numbers (they aren't real headers).
            if re.fullmatch(r"\d{1,4}", norm) or re.fullmatch(r"[-–]?\s*\d{1,4}\s*[-–]?", norm):
                continue
            seen_on_page.add(norm)
        for norm in seen_on_page:
            counter[norm] += 1

    threshold = max(2, int(len(pages) * REPEAT_THRESHOLD))
    return {line for line, count in counter.items() if count >= threshold}


def strip_repeating_lines(text: str, repeating: set[str]) -> str:
    """Removes lines whose normalized form matches the repeating-line set, disclaimers, or page numbers."""
    if not text:
        return text
    kept: list[str] = []
    for ln in text.splitlines():
        norm = _normalize_line(ln)
        if norm in repeating:
            continue
        # Strip standalone page numbers like 'Halaman - 1/120 - Page' or '1'
        if re.fullmatch(r"(?:halaman|page)?\s*[-–/]?\s*\d{1,4}(?:\s*/\s*\d{1,4})?\s*[-–]?(?:\s*(?:halaman|page))?", norm, re.I):
            continue
        # Strip boilerplate disclaimers
        if any(pat.search(norm) for pat in DISCLAIMER_PATTERNS):
            continue
        kept.append(ln)

    cleaned = "\n".join(kept)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def is_table_of_contents_page(text: str) -> bool:
    """Detects Table of Contents / Daftar Isi pages."""
    for pat in TOC_PATTERNS:
        if pat.search(text):
            return True
    return False


def is_cover_or_title_page(text: str, page_num: int) -> bool:
    """Detects standalone cover sheets or title announcement pages on initial pages."""
    if page_num > 3:
        return False
    clean = text.strip()
    # Check if page matches cover pattern and has no long explanatory narrative
    for pat in COVER_PATTERNS:
        if pat.search(clean):
            # If the page does not contain substantial footnote / MD&A sections
            if not re.search(
                r"catatan\s+atas\s+laporan\s+keuangan|notes\s+to\s+.*financial|tinjauan\s+operasional|management\s+discussion|diskusi\s+dan\s+analisis\s+manajemen|md&a|tinjauan\s+kinerja|kinerja\s+perseroan|faktor\s+risiko|risk\s+factor",
                clean,
                re.I,
            ):
                return True
    return False


def is_primary_tabular_statement(text: str) -> bool:
    """Detects primary financial statements (Balance Sheet, Income Statement, Cash Flows, Equity Changes).

    These tabular sheets contain numerical line items that belong in Layer 2 (financial_facts),
    not Layer 3 narrative chunks.
    """
    for pat in PRIMARY_STMT_PATTERNS:
        if pat.search(text[:350]):
            # If it is not part of Catatan atas Laporan Keuangan (CALK / Footnotes) or MD&A
            if not re.search(
                r"catatan\s+atas\s+laporan\s+keuangan|notes\s+to\s+.*financial|tinjauan\s+operasional|management\s+discussion|laporan\s+direksi",
                text[:500],
                re.I,
            ):
                return True
    return False


def is_sign_off_block(text: str) -> bool:
    """Detects standalone signature blocks (e.g. Direksi / Board of Directors signing rows)."""
    clean = text.strip()
    if len(clean) > 300:
        return False
    sign_count = sum(1 for pat in SIGN_OFF_PATTERNS if pat.search(clean))
    return sign_count >= 1 and not re.search(r"yang|adalah|telah|merupakan|pada|untuk|that|with|were", clean, re.I)


def is_valid_narrative_prose(text: str) -> bool:
    """Verifies that a paragraph contains genuine natural language sentence structure.

    Rejects isolated lists of account titles or uppercase banners lacking sentence prose.
    """
    clean = text.strip()
    words = re.findall(r"\b[a-zA-Z]{2,}\b", clean.lower())
    if len(words) < 8:
        return False

    # Check prose connector presence
    prose_count = sum(1 for w in words if w in ID_PROSE_MARKERS or w in EN_PROSE_MARKERS)
    prose_ratio = prose_count / len(words)

    # Check for all-caps banner titles
    split_words = clean.split()
    caps_words = sum(1 for w in split_words if w.isupper() and len(w) > 1)
    caps_ratio = caps_words / max(len(split_words), 1)

    if caps_ratio > 0.70 and not clean.endswith("."):
        return False

    # Punctuation check (sentences should have standard punctuation or connectors)
    has_punctuation = any(c in clean for c in ".,;:-()")

    return (prose_ratio >= 0.05 and has_punctuation) or len(words) >= 25


SECTION_RULES: list[
    tuple[re.Pattern[str], Literal["MDA", "RISK", "GUIDANCE", "MGMT_STMT", "FOOTNOTE", "OTHER"]]
] = [
    (
        re.compile(
            r"management\s+discussion|diskusi\s+dan\s+analisis\s+manajemen|md&a|tinjauan\s+keuangan|tinjauan\s+operasional",
            re.I,
        ),
        "MDA",
    ),
    (
        re.compile(r"risk\s+factor|faktor\s+risiko|manajemen\s+risiko|profil\s+risiko", re.I),
        "RISK",
    ),
    (
        re.compile(
            r"guidance|panduan|target\s+\d{4}|prospek|outlook|tinjauan\s+masa\s+depan", re.I
        ),
        "GUIDANCE",
    ),
    (
        re.compile(
            r"laporan\s+direksi|laporan\s+dewan\s+komisaris|board\s+of\s+directors|sambutan\s+direktur",
            re.I,
        ),
        "MGMT_STMT",
    ),
    (
        re.compile(r"notes\s+to\s+.*financial|catatan\s+atas\s+laporan\s+keuangan|calck|kebijakan\s+akuntansi", re.I),
        "FOOTNOTE",
    ),
]


def classify_section(
    text: str, heading_path: str = ""
) -> Literal["MDA", "RISK", "GUIDANCE", "MGMT_STMT", "FOOTNOTE", "OTHER"]:
    """Classifies chunk section using rule-based heading and keyword detection."""
    combined = f"{heading_path} {text[:300]}".lower()
    for pattern, section in SECTION_RULES:
        if pattern.search(combined):
            return section
    return "OTHER"


def is_digit_heavy(text: str, threshold: float = 0.60) -> bool:
    """Returns True if chunk is predominantly digits/table rows."""
    non_space = [c for c in text if not c.isspace()]
    if not non_space:
        return True
    digits = [c for c in non_space if c.isdigit()]
    return (len(digits) / len(non_space)) >= threshold


def chunk_pages(
    pages: list[PageContent],
    ticker: Ticker,
    doc_type: DocType,
    fiscal_period: FiscalPeriod,
) -> list[NarrativeChunkDraft]:
    """Splits document pages into 200-400 token semantic narrative chunks.

    Applies generalized filtering to skip cover pages, tables of contents,
    primary tabular financial statements, and signature boilerplate across all report types.
    """
    chunks: list[NarrativeChunkDraft] = []

    # Pre-pass: identify running headers/footers dynamically across pages
    repeating_lines = detect_repeating_lines(pages)

    # Track active section across pages (e.g. once in CALK, continue as FOOTNOTE)
    active_section: Literal["MDA", "RISK", "GUIDANCE", "MGMT_STMT", "FOOTNOTE", "OTHER"] = "OTHER"

    for page in pages:
        if not page.text or not page.has_text_layer:
            continue

        page_text = strip_repeating_lines(page.text, repeating_lines)
        if not page_text:
            continue

        # 1. Skip Table of Contents pages
        if is_table_of_contents_page(page_text):
            continue

        # 2. Skip Cover / Announcement Title sheets
        if is_cover_or_title_page(page_text, page.page_num):
            continue

        # 3. Skip Primary Tabular Financial Statements (Neraca, Laba Rugi, Arus Kas)
        if is_primary_tabular_statement(page_text):
            continue

        # Update active section if new section heading detected
        page_header_sample = page_text[:400]
        detected_sec = classify_section(page_header_sample)
        if detected_sec != "OTHER":
            active_section = detected_sec

        # Split page into raw paragraphs
        raw_paragraphs = [p.strip() for p in re.split(r"\n{2,}", page_text) if p.strip()]
        current_buffer: list[str] = []
        current_tokens = 0
        current_heading = ""

        for para in raw_paragraphs:
            # Skip digit heavy blocks (tables belong in Layer 2)
            if is_digit_heavy(para):
                continue

            # Skip standalone signature blocks
            if is_sign_off_block(para):
                continue

            # Detect short uppercase / bold lines as headings
            if len(para) < 80 and (para.isupper() or para.endswith(":")):
                current_heading = para
                sec = classify_section(para)
                if sec != "OTHER":
                    active_section = sec
                continue

            # Validate that paragraph contains genuine narrative prose
            if not is_valid_narrative_prose(para) and not current_buffer:
                continue

            token_count = len(ENCODING.encode(para))

            if current_tokens + token_count > 400 and current_buffer:
                # Flush buffer
                chunk_text = " ".join(current_buffer)
                section = classify_section(chunk_text, current_heading)
                if section == "OTHER" and active_section != "OTHER":
                    section = active_section

                chunks.append(
                    NarrativeChunkDraft(
                        source_page=page.page_num,
                        section=section,
                        language=page.language,
                        text_original=chunk_text,
                        mentioned_periods=[fiscal_period],
                    )
                )
                current_buffer = [para]
                current_tokens = token_count
            else:
                current_buffer.append(para)
                current_tokens += token_count

        # Flush remaining buffer for the page
        if current_buffer:
            chunk_text = " ".join(current_buffer)
            if len(ENCODING.encode(chunk_text)) >= 25 and not is_digit_heavy(chunk_text):
                section = classify_section(chunk_text, current_heading)
                if section == "OTHER" and active_section != "OTHER":
                    section = active_section

                chunks.append(
                    NarrativeChunkDraft(
                        source_page=page.page_num,
                        section=section,
                        language=page.language,
                        text_original=chunk_text,
                        mentioned_periods=[fiscal_period],
                    )
                )

    return chunks

