p = r'C:\Users\rizky\Documents\Code\EmiMind\services\mcp\grounding.py'
s = open(p, encoding='utf-8').read()
start = s.index('# ---------------------------------------------------------------------------\n# Label matching')
end = s.index('# ---------------------------------------------------------------------------\n# Cell and text grounding')
new = r'''# ---------------------------------------------------------------------------
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
        return 0.0
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


'''
s = s[:start] + new + s[end:]

start = s.index('def _line_label_candidates(')
end = s.index('def ground_text(')
s = s[:start] + r'''def _line_label_candidates(lines: list[_Line], i: int) -> list[str]:
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


''' + s[end:]

a = s.index('    accepted: tuple[int, int] | None = None')
b = s.index('    if accepted is None:')
s = s[:a] + '''    accepted: tuple[int, int] | None = None
    for li in label_lines:
        for vi, ordinal in value_hits:
            if vi == li or (
                abs(vi - li) <= window and not lines[vi].chunks and not lines[li].amounts
            ):
                accepted = (vi, ordinal)
                break
        if accepted:
            break
''' + s[b:]
s = s.replace('years = page_header_years(page_ev.page_text)\n', 'years = page_header_years(page_ev.page_text, period_end)\n')
open(p, 'w', encoding='utf-8').write(s)
print("ok")
