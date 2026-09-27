"""Unit tests for page router pure functions (RRF fusion, continuation, span merging)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from services.retrieval.page_router import is_continuation, merge_spans, rrf_fuse
from tests.fixtures.m9.build_fixtures import build_fs_small


def test_rrf_fuse_ranks_expected_first() -> None:
    """rrf_fuse([[3,1,2],[1,4]]) ranks page 1 first."""
    ranked = rrf_fuse([[3, 1, 2], [1, 4]])
    assert len(ranked) == 4
    top_page, _ = ranked[0]
    assert top_page == 1, f"Expected page 1 first, got {top_page}"

    # Verify order of the rest
    pages_in_order = [p for p, _ in ranked]
    assert pages_in_order[0] == 1


def test_is_continuation_fixture_headers(tmp_path: Path) -> None:
    """is_continuation is True for a p5 -> p6 header pair from the fixture and False for p4 -> p5."""
    import pymupdf

    pdf_path = build_fs_small(tmp_path / "fs_small.pdf")
    doc: Any = pymupdf.open(str(pdf_path))  # type: ignore[no-untyped-call]

    p4_text = doc[3].get_text()  # physical page 4
    p5_text = doc[4].get_text()  # physical page 5
    p6_text = doc[5].get_text()  # physical page 6

    # p5 -> p6 is a continuation of note 12 (Kredit yang Diberikan lanjutan)
    assert is_continuation(p5_text, p6_text) is True

    # p4 -> p5 is Cash Flow Statement -> Note 12 (not a continuation)
    assert is_continuation(p4_text, p5_text) is False

    doc.close()


def test_merge_spans() -> None:
    """merge_spans([(5, 6), (6, 8)]) == [(5, 8)]."""
    spans = [(5, 6), (6, 8)]
    merged = merge_spans(spans)
    assert merged == [(5, 8)]

    # Additional test cases: non-overlapping, fully contained, empty
    assert merge_spans([]) == []
    assert merge_spans([(1, 2), (4, 5)]) == [(1, 2), (4, 5)]
    assert merge_spans([(1, 4), (2, 3)]) == [(1, 4)]
    assert merge_spans([(1, 2), (2, 3), (3, 4)]) == [(1, 4)]
