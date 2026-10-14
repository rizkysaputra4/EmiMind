"""Concept <-> label sanity and period-type resolution for submitted facts.

Pure functions; the concept vocabulary comes from `metric_definitions` rows passed in by the caller.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from services.mcp.grounding import sorted_tokens
from services.mcp.types import VALID_PERIOD_TYPES, ConceptDefinition, ExtractedFactItem

# Concepts the validator itself relies on (tie-outs) that may be missing from metric_definitions.
BUILTIN_CONCEPTS: dict[str, ConceptDefinition] = {
    "idx:CashAtEndOfPeriod": ConceptDefinition(
        metric_id="idx:CashAtEndOfPeriod",
        name_id="Kas dan Setara Kas Akhir Tahun / Kas dan Setara Kas Akhir Periode",
        name_en="Cash and Cash Equivalents at End of Year / Cash and Cash Equivalents at End of Period",
        synonyms_id=[
            "Kas dan Setara Kas pada Akhir Tahun",
            "Kas dan Setara Kas pada Akhir Periode",
        ],
        synonyms_en=["Cash and Cash Equivalents at the End of the Year"],
        flow_stock_type="STOCK_POINT_IN_TIME",
        unit="IDR",
        value_type="MONETARY",
        statement_type="CASH_FLOW",
    ),
}

# Common IDX statement captions missing from metric_definitions synonyms (reported upstream).
SUPPLEMENTAL_SYNONYMS: dict[str, list[str]] = {
    "ifrs:CashFlowsFromUsedInOperatingActivities": [
        "Kas Neto yang Diperoleh dari Aktivitas Operasi",
        "Kas Neto yang Digunakan untuk Aktivitas Operasi",
        "Arus Kas Neto dari Aktivitas Operasi",
        "Net Cash Provided by Operating Activities",
        "Net Cash Used in Operating Activities",
    ],
    "ifrs:GrossProfit": ["Laba Bruto"],
    "ifrs:Revenue": ["Pendapatan", "Pendapatan Neto", "Pendapatan Bersih", "Revenues"],
    "ifrs:ProfitBeforeTax": [
        "Laba Sebelum Beban Pajak Penghasilan",
        "Profit Before Income Tax Expense",
    ],
    "idx:Capex": [
        "Penambahan Aset Tetap",
        "Additions to Fixed Assets",
        "Perolehan Aset Tetap",
        "Pembelian Aset Tetap",
        "Acquisitions of Fixed Assets",
        # Bearer plants are property, plant and equipment (PSAK 16), so their purchase is capex.
        "Perolehan Aset Tetap dan Tanaman Produktif",
        "Acquisitions of Fixed Assets and Bearer Plants",
    ],
    "idx:SellingAndMarketingExpense": [
        "Beban Penjualan dan Distribusi",
        "Selling and Distribution Expenses",
    ],
    "ifrs:ProfitLossAttributableToOwnersOfParent": [
        "Laba yang Dapat Diatribusikan kepada Pemilik Entitas Induk",
        "Laba Periode Berjalan yang Dapat Diatribusikan kepada Pemilik Entitas Induk",
        "Laba Tahun Berjalan yang Dapat Diatribusikan kepada Pemilik Entitas Induk",
    ],
}

# Words treated as equal when comparing a label with concept names.
_EQUIVALENT_WORDS: list[frozenset[str]] = [
    frozenset({"bruto", "kotor", "gross"}),
    frozenset({"neto", "bersih", "net"}),
    frozenset({"marjin", "margin"}),
]
# Net-words may be absent from a label ("Laba tahun berjalan" is net profit).
_OPTIONAL = frozenset({"bersih", "neto", "net"})
# ...except where the gross line is a different figure: "Pendapatan bunga" is gross interest
# income, not net interest income.
_NET_WORD_REQUIRED = frozenset({"idx:NetInterestIncome"})

_STOPWORDS = frozenset(
    """
    yang dan atas dari ke kepada pada di dalam untuk dengan oleh sebagai per atau serta
    telah akan masih the of and to for from in at on a an by with as or its
    total jumlah catatan note notes
    """.split()
)
# Extra label words that never change what a line denotes.
_NEUTRAL = frozenset(
    """
    tahun year years periode period berjalan current akhir end konsolidasian consolidated
    interim bersih neto net kategori category rp idr juta jutaan million millions rugi loss
    tbk pt entitas anak subsidiaries this ini tersebut sebelumnya
    """.split()
)
_SEGMENT_ROW_WORDS = frozenset({"segmen", "segment", "segments", "dilaporkan", "reportable"})
# "Aset tetap - setelah dikurangi akumulasi penyusutan" is the carrying amount the balance sheet
# reports, not a different line, so the net-of-depreciation phrase is dropped before matching.
_NET_OF_DEPRECIATION_RE = re.compile(
    r"(setelah dikurangi akumulasi (penyusutan|amortisasi)( dan [a-z ]*?penurunan nilai)?"
    r"|net of accumulated (depreciation|amortization|amortisation)( and [a-z ]*?impairment)?)",
    re.IGNORECASE,
)
# A hierarchy label '<header> - <row>' (the form the validator asks for on sub-rows) whose
# header is a balance-sheet section says only which term the row sits in: 'Liabilitas jangka
# panjang setelah bagian lancar - Pinjaman bank' is the long-term bank loan line. The header
# keeps its term words; 'net of current portion' only restates that the section is non-current.
_SECTION_HEADER_RES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"setelah (dikurangi )?bagian (yang (akan )?jatuh tempo dalam (waktu )?satu tahun"
            r"|lancar|jangka pendek)|net of current (portion|maturities)",
            re.IGNORECASE,
        ),
        " ",
    ),
    (
        re.compile(r"\b(liabilitas|liabilities|aset|assets)\s+(jangka panjang|jangka pendek)\b", re.I),
        r"\2",
    ),
    (re.compile(r"\b(long-term|non-current|short-term)\s+(liabilities|assets)\b", re.I), r"\1"),
]
# The long-term portion of a loan is the long-term borrowing itself ('Pinjaman bank - Bagian
# jangka panjang'). Only this phrase: a current portion stays a different figure.
_LONG_TERM_PORTION_RE = re.compile(
    r"\bbagian jangka panjang\b|\b(non-current|long-term) portion\b", re.IGNORECASE
)


def _reduce_label(label: str) -> str:
    """Drop phrases that never change what a line denotes (see the patterns above)."""
    text = _NET_OF_DEPRECIATION_RE.sub(" ", label)
    if " - " in text:
        header, row = text.rsplit(" - ", 1)
        for pattern, repl in _SECTION_HEADER_RES:
            header = pattern.sub(repl, header)
        text = f"{header} - {row}"
    return _LONG_TERM_PORTION_RE.sub(lambda m: "long-term" if m.group(1) else "jangka panjang", text)


_FLOW_NAME_RE = re.compile(
    r"(expense|expenses|cost|costs|component|revenue|revenues|income|production|sales|"
    r"beban|biaya|pendapatan|penjualan|produksi|penghasilan)",
    re.IGNORECASE,
)
_STOCK_NAME_RE = re.compile(
    r"(payable|receivable|accrued|prepaid|deferred|liabilit|asset|provision|balance|unearned|"
    r"reserve|utang|piutang|dibayar di muka|masih harus|tangguhan|cadangan|saldo)",
    re.IGNORECASE,
)


def _tokens(text: str) -> list[str]:
    t = re.sub(r"[^a-z0-9À-ɏ]+", " ", text.lower())
    return [w for w in t.split() if w not in _STOPWORDS]


def name_variants(cdef: ConceptDefinition) -> list[str]:
    """All names of a concept: '/'-split variants, parenthetical abbreviations, synonyms."""
    raw = [
        cdef.name_id,
        cdef.name_en,
        *cdef.synonyms_id,
        *cdef.synonyms_en,
        *SUPPLEMENTAL_SYNONYMS.get(cdef.metric_id, []),
    ]
    out: list[str] = []
    for name in raw:
        if not name:
            continue
        parts = [p.strip() for p in re.split(r"\s+/\s+", name) if p.strip()]
        expanded: list[str] = []
        for k, raw_part in enumerate(parts):
            # "Beban Pokok Pendapatan / Penjualan" means "... / Beban Pokok Penjualan".
            part = raw_part
            if k > 0:
                prev = re.sub(r"\([^)]*\)", " ", parts[0]).split()
                cur = re.sub(r"\([^)]*\)", " ", raw_part).split()
                if 0 < len(cur) < len(prev):
                    part = " ".join(prev[: len(prev) - len(cur)] + cur)
            expanded.append(part)
        for part in expanded:
            parens = [
                p
                for p in re.findall(r"\(([^)]*)\)", part)
                if re.search(r"[A-Z]{2,}", p) and "/" not in p and " per " not in f" {p.lower()} "
            ]
            base = re.sub(r"\([^)]*\)", " ", part).strip()
            for raw_v in [base, *parens]:
                v = " ".join(raw_v.replace("%", " ").split())
                toks = _tokens(v)
                if not toks or all(t in _NEUTRAL or t.isdigit() for t in toks):
                    continue
                if v not in out:
                    out.append(v)
    return out


def _tok_eq(a: str, b: str) -> bool:
    if a == b:
        return True
    if any(a in eq and b in eq for eq in _EQUIVALENT_WORDS):
        return True
    if len(a) >= 5 and len(b) >= 5 and (a.startswith(b) or b.startswith(a)):
        return True
    return len(a) >= 6 and len(b) >= 6 and fuzz.ratio(a, b) >= 88


def _covers(
    label_toks: list[str], variant_toks: list[str], optional: frozenset[str] = _OPTIONAL
) -> bool:
    required = [v for v in variant_toks if v not in optional] or variant_toks
    return bool(required) and all(any(_tok_eq(v, lt) for lt in label_toks) for v in required)


@dataclass(frozen=True)
class ConceptLabelVerdict:
    ok: bool
    reason: str = ""


def check_concept_label(
    label: str, cdef: ConceptDefinition, segment_words: list[str] | None = None
) -> ConceptLabelVerdict:
    """Does `label` plausibly denote the concept? All tokens of one name variant must be in the
    label, and every other label word must belong to the concept's vocabulary, the segment,
    or a small neutral list (year/period/net/consolidated...)."""
    label_toks = _tokens(_reduce_label(label))
    if not label_toks:
        return ConceptLabelVerdict(False, "empty label")
    variants = name_variants(cdef)
    variant_toks = [_tokens(v) for v in variants]
    optional = frozenset() if cdef.metric_id in _NET_WORD_REQUIRED else _OPTIONAL
    covering = [vt for vt in variant_toks if _covers(label_toks, vt, optional)]
    if not covering:
        return ConceptLabelVerdict(
            False,
            f"no name of the concept is contained in the label (expected one of: "
            f"{'; '.join(variants[:8])})",
        )
    vocab = {t for vt in variant_toks for t in vt}
    seg_toks = {t for w in (segment_words or []) for t in _tokens(w)}
    if segment_words:
        # a segmented fact's row in the segment note: 'Aset segmen dilaporkan' / 'Reportable
        # segment assets' is the segment's own figure of the concept
        seg_toks |= _SEGMENT_ROW_WORDS
    extras = [
        t
        for t in label_toks
        if not t.isdigit()
        and len(t) > 1
        and t not in _NEUTRAL
        and not any(_tok_eq(t, v) for v in vocab)
        and not any(_tok_eq(t, s) for s in seg_toks)
    ]
    if extras:
        return ConceptLabelVerdict(
            False,
            f"the label adds qualifiers {extras} that the concept's names do not contain "
            f"(names: {'; '.join(variants[:8])}); a qualified line is usually a different concept",
        )
    return ConceptLabelVerdict(True)


def segment_strings(segment: dict[str, object] | None) -> list[str]:
    """All string values of a segment dict (any key, nested lists included)."""
    out: list[str] = []
    if not segment:
        return out
    for v in segment.values():
        if isinstance(v, str) and v.strip():
            out.append(v.strip())
        elif isinstance(v, list):
            out += [x.strip() for x in v if isinstance(x, str) and x.strip()]
    return out


def name_denotes_flow(concept_id: str, label: str | None) -> bool:
    """Heuristic for concepts outside the ontology: expense/revenue/income/production names."""
    local = concept_id.split(":", 1)[-1]
    words = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", local)
    text = f"{words} {label or ''}"
    return bool(_FLOW_NAME_RE.search(words)) and not _STOCK_NAME_RE.search(text)


@dataclass(frozen=True)
class PeriodTypeVerdict:
    resolved: str | None
    category: str | None = None  # SCHEMA | PERIOD_TYPE_MISMATCH
    message: str = ""


def resolve_period_type(
    fact: ExtractedFactItem, cdef: ConceptDefinition | None
) -> PeriodTypeVerdict:
    """The period_type to store, or the reason it is invalid. Never coerces a submitted value."""
    pt = fact.period_type
    stmt = fact.statement or "NOTE"
    flow_stock = ((cdef.flow_stock_type if cdef else None) or "").upper()
    is_stock = flow_stock.startswith("STOCK")
    is_flow = flow_stock.startswith("FLOW")
    cid = fact.concept_id

    if pt is not None and pt not in VALID_PERIOD_TYPES:
        return PeriodTypeVerdict(
            None,
            "SCHEMA",
            f"Fact '{cid}' has invalid period_type '{pt}'. Expected one of: "
            f"{sorted(VALID_PERIOD_TYPES)} (use duration_ytd for full-year/YTD, duration_qtd for "
            f"the quarter alone).",
        )
    if pt is None:
        if is_stock or stmt == "BS":
            return PeriodTypeVerdict("instant")
        if is_flow or stmt in ("IS", "CF"):
            return PeriodTypeVerdict("duration_ytd")
        if cdef is not None:
            return PeriodTypeVerdict("instant")
        return PeriodTypeVerdict(
            None,
            "SCHEMA",
            f"Fact '{cid}' (statement {stmt}) is not in metric_definitions, so period_type must be "
            f"given explicitly ('instant' for balances, 'duration_ytd'/'duration_qtd' for flows).",
        )

    if is_flow and pt == "instant":
        return PeriodTypeVerdict(
            None,
            "PERIOD_TYPE_MISMATCH",
            f"Fact '{cid}' is a FLOW concept in metric_definitions but was submitted as 'instant'; "
            f"use 'duration_ytd' (or 'duration_qtd' for a quarter-only column).",
        )
    if is_stock and pt != "instant":
        return PeriodTypeVerdict(
            None,
            "PERIOD_TYPE_MISMATCH",
            f"Fact '{cid}' is a STOCK (point-in-time) concept but was submitted as '{pt}'; use 'instant'.",
        )
    if stmt == "BS" and pt != "instant":
        return PeriodTypeVerdict(
            None,
            "PERIOD_TYPE_MISMATCH",
            f"Balance-sheet fact '{cid}' must be 'instant', got '{pt}'.",
        )
    if stmt in ("IS", "CF") and pt == "instant" and not is_stock:
        return PeriodTypeVerdict(
            None,
            "PERIOD_TYPE_MISMATCH",
            f"{stmt} fact '{cid}' cannot be 'instant' (income-statement and cash-flow lines are "
            f"flows); use 'duration_ytd' or 'duration_qtd'.",
        )
    if cdef is None and pt == "instant" and name_denotes_flow(cid, fact.source_label_original):
        return PeriodTypeVerdict(
            None,
            "PERIOD_TYPE_MISMATCH",
            f"Fact '{cid}' ('{fact.source_label_original}') names an expense/revenue/income/"
            f"production flow but was submitted as 'instant'; use 'duration_ytd' or 'duration_qtd'.",
        )
    return PeriodTypeVerdict(pt)


def metric_search_terms(
    cdef: ConceptDefinition | None, extra_names: list[str]
) -> list[tuple[str, bool]]:
    """(term, is_acronym) phrases whose presence next to a number contradicts an omission."""
    names = list(extra_names)
    if cdef is not None:
        names += name_variants(cdef)
    terms: list[tuple[str, bool]] = []
    for n in names:
        for raw_part in re.split(r"\s+/\s+", n):
            part = re.sub(r"\([^)]*\)", " ", raw_part).strip()
            raw_words = part.split()
            if not raw_words:
                continue
            if len(raw_words) == 1:
                w = raw_words[0].strip(".,:;")
                if w.isupper() and 3 <= len(w) <= 6:
                    terms.append((w, True))
                    continue
                if len(w) < 6:
                    continue
            norm = " ".join(re.sub(r"[^a-z0-9À-ɏ]+", " ", part.lower()).split())
            if len(norm) >= 6 and (norm, False) not in terms:
                terms.append((norm, False))
    return terms


def label_is_segment_member(label: str, segment_words: list[str]) -> bool:
    """True when a segmented fact's label only names its segment member (e.g. 'Pihak ketiga')."""
    label_toks = [t for t in _tokens(label) if not t.isdigit() and len(t) > 1 and t not in _NEUTRAL]
    seg_toks = {t for w in segment_words for t in _tokens(w)}
    return (
        bool(label_toks)
        and bool(seg_toks)
        and all(any(_tok_eq(t, s) for s in seg_toks) for t in label_toks)
    )


@dataclass(frozen=True)
class MetricMention:
    """A line on an indexed page where a metric's name is followed by a reported number."""

    page: int
    term: str
    line: str


def _term_regex(term: str, is_acronym: bool) -> re.Pattern[str]:
    if is_acronym:
        return re.compile(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])")
    words = [re.escape(w) for w in term.split()]
    return re.compile(r"(?<![a-z0-9])" + r"[^a-z0-9]+".join(words) + r"(?![a-z0-9])", re.IGNORECASE)


def _has_amount(text: str, want_percent: bool | None = None) -> bool:
    for t in sorted_tokens(text):
        if not t.is_amount or t.is_dash:
            continue
        if want_percent is None or t.is_percent == want_percent:
            return True
    return False


def find_metric_mentions(
    terms: list[tuple[str, bool]],
    pages: dict[int, str],
    *,
    max_hits: int = 5,
    want_percent: bool | None = None,
) -> list[MetricMention]:
    """Lines where a metric name is followed by an amount (same line, or a numbers-only next line).

    Used to contradict omissions: a metric declared 'not disclosed' whose caption appears next to
    a number somewhere in the indexed document was not actually absent. `want_percent` makes the
    number match the metric's kind: a monetary metric is not contradicted by a ratio printed next
    to its caption ("rasio NPL gross 2,5%"), nor a ratio metric by an amount.
    """
    patterns = [(term, _term_regex(term, acr)) for term, acr in terms]
    hits: list[MetricMention] = []
    for page in sorted(pages):
        lines = pages[page].splitlines()
        for i, line in enumerate(lines):
            for term, pat in patterns:
                m = pat.search(line)
                if m is None:
                    continue
                after = line[m.end() :]
                nxt = lines[i + 1] if i + 1 < len(lines) else ""
                nxt_numbers_only = not re.search(r"[A-Za-z]{3,}", nxt)
                if _has_amount(after, want_percent) or (
                    nxt_numbers_only and _has_amount(nxt, want_percent)
                ):
                    hits.append(MetricMention(page=page, term=term, line=line.strip()[:160]))
                    break
            if len(hits) >= max_hits:
                return hits
    return hits
