"""Narrative quality rules: verbatim quotes, boilerplate containment, issuer anchors."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path

from rapidfuzz import fuzz

from services.mcp.grounding import tokenize_numbers

VERBATIM_THRESHOLD = 90.0
_GENERIC_CAPITALIZED = frozenset(
    """
    perusahaan perseroan grup group company direksi dewan komisaris manajemen management
    kami we our the pada dalam dengan untuk tahun year namun selain hal oleh sebagai secara
    bank entitas indonesia rupiah catatan note laporan keuangan financial statements
    """.split()
)


def normalize_narrative_text(text: str) -> str:
    """Lowercase, whitespace-collapsed, digits kept (the dedupe/duplicate hash basis)."""
    return re.sub(r"\s+", " ", text.lower()).strip()


def narrative_md5(text: str) -> str:
    """MD5 of normalize_narrative_text(text)."""
    norm = normalize_narrative_text(text)
    return hashlib.md5(norm.encode("utf-8"), usedforsecurity=False).hexdigest()


def normalize_for_match(text: str) -> str:
    """Normalization for verbatim/boilerplate matching: hyphenation, quotes, punctuation, case."""
    t = unicodedata.normalize("NFKC", text)
    t = t.replace("�", " ")
    t = re.sub(r"(\w)[-­]\s*\n\s*(\w)", r"\1\2", t)  # line-break hyphenation
    t = t.lower()
    t = re.sub(r"[‘’“”\"'`]", "", t)
    t = re.sub(r"[^\w%]+", " ", t)
    return " ".join(t.split())


_BOILERPLATE: tuple[set[str], list[str]] | None = None


def load_boilerplate() -> tuple[set[str], list[str]]:
    """(md5 hashes, normalized sentences) from db/seeds/narrative_boilerplate.txt."""
    global _BOILERPLATE
    if _BOILERPLATE is None:
        hashes: set[str] = set()
        sentences: list[str] = []
        path = Path(__file__).resolve().parents[2] / "db" / "seeds" / "narrative_boilerplate.txt"
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                line_s = line.strip()
                if not line_s or line_s.startswith("#"):
                    continue
                if re.fullmatch(r"[0-9a-fA-F]{32}", line_s):
                    hashes.add(line_s.lower())
                else:
                    hashes.add(narrative_md5(line_s))
                    norm = normalize_for_match(line_s)
                    if norm:
                        sentences.append(norm)
        _BOILERPLATE = (hashes, sentences)
    return _BOILERPLATE


def boilerplate_match(text: str) -> str | None:
    """The boilerplate sentence a chunk contains (or is a fragment of), else None."""
    hashes, sentences = load_boilerplate()
    if narrative_md5(text) in hashes:
        return text
    norm = normalize_for_match(text)
    if not norm:
        return None
    for sent in sentences:
        if sent in norm:
            return sent
        if len(norm) >= 30 and norm in sent:
            return sent
        if len(norm) >= 30 and abs(len(norm) - len(sent)) <= 0.2 * len(sent):
            if fuzz.ratio(norm, sent) >= 92:
                return sent
    return None


def _contained_score(needle: str, hay: str) -> float:
    """How well `needle` occurs inside `hay` (0..100).

    rapidfuzz.partial_ratio aligns the SHORTER string inside the longer one, so a haystack
    shorter than the needle would let a short page fragment "contain" a long invented chunk.
    """
    if len(hay) < len(needle):
        return float(fuzz.ratio(needle, hay))
    return float(fuzz.partial_ratio(needle, hay))


def _foreign_content(chunk: str, page_text: str, c: str, p: str) -> bool:
    """True when the chunk carries numbers or words the page does not have.

    A fuzzy score alone lets an edited quote through (a changed figure or a swapped company
    name still scores > 90), so every number must be on the page and at most max(1, 5%) of the
    chunk's words may be missing from it."""
    page_numbers = {re.sub(r"\D", "", t.raw) for t in tokenize_numbers(page_text)}
    for tok in tokenize_numbers(chunk):
        digits = re.sub(r"\D", "", tok.raw)
        if not tok.is_dash and digits and digits not in page_numbers:
            return True
    page_words = set(p.split())
    words = [w for w in c.split() if len(w) >= 3 and not w.isdigit()]
    missing = [w for w in words if w not in page_words]
    return len(missing) > max(1, int(0.05 * len(words)))


def is_verbatim(chunk: str, page_text: str) -> tuple[bool, float]:
    """Is `chunk` a verbatim span of the page after normalization (bilingual interleave tolerant)?

    Returns (ok, score 0..100). Stable signature: the acceptance gate imports it."""
    c = normalize_for_match(chunk)
    p = normalize_for_match(page_text)
    if not c or not p:
        return False, 0.0
    if c in p:
        return True, 100.0
    score = _contained_score(c, p)
    # Bilingual pages interleave the ID and EN columns line by line; keep only the page words
    # that occur in the chunk and compare the resulting sequence.
    vocab = set(c.split())
    filtered = " ".join(w for w in p.split() if w in vocab)
    if len(c.split()) >= 6 and filtered:
        score = max(score, _contained_score(c, filtered))
    if score >= VERBATIM_THRESHOLD and not _foreign_content(chunk, page_text, c, p):
        return True, score
    return False, min(score, VERBATIM_THRESHOLD - 1) if score >= VERBATIM_THRESHOLD else score


def issuer_anchor(chunk: str, page_text: str, segment_names: list[str]) -> str | None:
    """A concrete anchor shared by chunk and page: a non-year number, a segment, or a name."""
    page_norm = normalize_for_match(page_text)
    page_numbers = {re.sub(r"\D", "", t.raw) for t in tokenize_numbers(page_text)}
    for tok in tokenize_numbers(chunk):
        if tok.is_year or tok.is_dash or tok.is_note_ref:
            continue
        raw_digits = re.sub(r"\D", "", tok.raw)
        if raw_digits and raw_digits in page_numbers:
            return tok.raw
    chunk_norm = normalize_for_match(chunk)
    for seg in segment_names:
        s = normalize_for_match(seg)
        if len(s) >= 3 and s in chunk_norm and s in page_norm:
            return seg
    words = re.findall(r"[A-Za-z][\w&.-]*", chunk)
    for k, w in enumerate(words):
        prev = words[k - 1] if k > 0 else ""
        sentence_start = k == 0 or bool(re.search(r"[.!?]\s*$", prev))
        is_acronym = bool(re.fullmatch(r"[A-Z][A-Z0-9&]{1,}", w))
        is_proper = w[0].isupper() and not sentence_start
        if not (is_acronym or is_proper):
            continue
        if w.lower() in _GENERIC_CAPITALIZED or len(w) < 3:
            continue
        if normalize_for_match(w) in page_norm.split():
            return str(w)
    return None
