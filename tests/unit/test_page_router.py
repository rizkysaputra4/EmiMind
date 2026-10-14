"""Unit tests for the page router: pure helpers plus route_pages over an in-memory DB."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from services.mcp.types import RouteQuery
from services.narrative.embedder import Embedder, EmbeddingUnavailableError
from services.retrieval import page_router as pr
from services.retrieval.page_router import (
    anchor_ranking,
    compile_anchor,
    cosine_top,
    excluded_pages,
    forward_walk,
    is_continuation,
    merge_spans,
    note_headings,
    pattern_starts,
    rrf_fuse,
    select_pages,
    statement_title,
    sub_heading_starts,
)
from tests.fixtures.m9.build_fixtures import build_fs_small
from tests.unit._fake_async_db import FakeConn

HDR = "PT CONTOH Tbk\nDAN ENTITAS ANAKNYA\n"
NOTES_HDR = HDR + "CATATAN ATAS LAPORAN KEUANGAN KONSOLIDASIAN (lanjutan)\n(Disajikan dalam jutaan Rupiah)\n"


def _doc() -> dict[int, str]:
    """A 10-page synthetic filing: BS pp2-3, IS p4, notes 5 (p5-6), 6 (p7), 7 (p8-9), 8 (p10)."""
    return {
        1: "DAFTAR ISI\nLaporan posisi keuangan 2\nCatatan 5",
        2: HDR + "LAPORAN POSISI KEUANGAN KONSOLIDASIAN\nKas dan setara kas 5 1.000\nJumlah aset 9.000",
        3: HDR + "LAPORAN POSISI KEUANGAN KONSOLIDASIAN\nLiabilitas\nJumlah ekuitas 4.000",
        4: HDR + "LAPORAN LABA RUGI KONSOLIDASIAN\nPendapatan 7.000\nBeban pokok penjualan 3.000",
        5: NOTES_HDR + "4. PERSEDIAAN (lanjutan)\nBahan baku 10\n5. KAS DAN SETARA KAS\nKas 100\nBank 900",
        6: NOTES_HDR + "5. KAS DAN SETARA KAS (lanjutan)\nDeposito berjangka 300\nJumlah kas dan setara kas 1.000",
        7: NOTES_HDR + "6. PIUTANG USAHA\nPihak ketiga 50\nkas dan setara kas tidak dijaminkan",
        8: NOTES_HDR + "7. PENDAPATAN DARI KONTRAK DENGAN\nPELANGGAN\nPenjualan minyak sawit 7.000",
        9: NOTES_HDR + "7. PENDAPATAN DARI KONTRAK DENGAN\nPELANGGAN (lanjutan)\nPelanggan melebihi 10% 4.000",
        10: NOTES_HDR + "8. BEBAN POKOK PENJUALAN\nBahan baku 1.000",
    }


def test_rrf_fuse_ranks_expected_first() -> None:
    ranked = rrf_fuse([[3, 1, 2], [1, 4]])
    assert len(ranked) == 4 and ranked[0][0] == 1
    # duplicates within one list count once
    assert rrf_fuse([[5, 5, 5]]) == [(5, 1.0 / 61)]


def test_merge_spans_merges_touching_spans() -> None:
    assert merge_spans([(5, 6), (6, 8)]) == [(5, 8)]
    assert merge_spans([(5, 6), (7, 8)]) == [(5, 8)]
    assert merge_spans([]) == []
    assert merge_spans([(1, 2), (4, 5)]) == [(1, 2), (4, 5)]
    assert merge_spans([(1, 4), (2, 3)]) == [(1, 4)]
    assert merge_spans([(3, 4), (1, 2)]) == [(1, 4)]


def test_note_headings_detect_wrapped_continuation() -> None:
    doc = _doc()
    assert [(n, c) for n, _h, c in note_headings(doc[5])] == [("4", True), ("5", False)]
    assert [(n, c) for n, _h, c in note_headings(doc[9])] == [("7", True)]
    # title-case headings (JKON style) are headings; numbered sentences are not
    assert note_headings("4. Kas dan Setara Kas\n2021 2020")[0][0] == "4"
    assert note_headings("1. Perusahaan telah menerima pembayaran sebesar Rp 100 juta.") == []


def test_is_continuation() -> None:
    doc = _doc()
    assert is_continuation(doc[5], doc[6]) is True  # note 5 continues
    assert is_continuation(doc[6], doc[7]) is False  # note 6 starts
    assert is_continuation(doc[8], doc[9]) is True  # note 7 (lanjutan on the wrapped line)
    assert is_continuation(doc[2], doc[3]) is True  # same statement title repeated
    assert is_continuation(doc[3], doc[4]) is False  # a different statement
    assert statement_title(doc[5]) is None  # notes pages are not statements


def test_is_continuation_fixture_headers(tmp_path: Path) -> None:
    import pymupdf

    pdf_path = build_fs_small(tmp_path / "fs_small.pdf")
    doc: Any = pymupdf.open(str(pdf_path))
    try:
        p4, p5, p6 = (doc[i].get_text() for i in (3, 4, 5))
        assert is_continuation(p5, p6) is True  # note 12 (lanjutan)
        assert is_continuation(p4, p5) is False  # cash flow statement -> note 12
    finally:
        doc.close()


def test_exclusions_and_anchor_ranking() -> None:
    doc = _doc()
    core_ex = excluded_pages(doc, core_query=True)
    assert 1 in core_ex  # table of contents
    # statement queries skip notes pages (notes header + a note heading), not statements
    assert {5, 6, 7, 8, 9, 10} <= core_ex and not {2, 3, 4} & core_ex
    note_ex = excluded_pages(doc, core_query=False)
    assert {1, 2, 3, 4} <= note_ex and 5 not in note_ex
    ranked, starts = anchor_ranking(doc, ["PENDAPATAN DARI KONTRAK"], note_ex)
    assert ranked == [8, 9] and starts == {8}
    ranked, starts = anchor_ranking(doc, ["KAS DAN SETARA KAS"], note_ex)
    assert ranked == [5, 6] and starts == {5}
    ranked, _ = anchor_ranking(doc, ["LAPORAN POSISI KEUANGAN"], excluded_pages(doc, True))
    assert ranked == [2, 3]


def test_select_pages_respects_total_budget_and_seed_ratio() -> None:
    doc = _doc()
    fused = [(6, 0.05), (9, 0.049), (7, 0.048), (10, 0.047)]
    # 9 is inside note 7 but outside seed 6's reach, 7 starts note 6: three seeds, and with a
    # budget of 3 each keeps its own page instead of seed 6 taking all of it
    units = select_pages(fused, doc, budget=3, top_k=3, seed_ratio=0.7, heading_starts={5})
    assert [ps for _s, ps, _sc in units] == [[6], [9], [7]]
    # one page more: seed 6 continues note 5 -> takes its start page first
    units = select_pages(fused, doc, budget=4, top_k=3, seed_ratio=0.7, heading_starts={5})
    assert [ps for _s, ps, _sc in units] == [[5, 6], [9], [7]]
    # a weak second seed is not added
    units = select_pages([(6, 0.05), (10, 0.02)], doc, budget=6, seed_ratio=0.7)
    assert [ps for _s, ps, _sc in units] == [[5, 6]]


def _long_note_doc() -> dict[int, str]:
    """Note 9 runs pp1-8 (a long lender list); note 10 starts on p9."""
    doc = {1: NOTES_HDR + "9. PINJAMAN YANG DITERIMA\nRingkasan per jenis 1.000"}
    for i in range(2, 9):
        doc[i] = NOTES_HDR + f"9. PINJAMAN YANG DITERIMA (lanjutan)\nPemberi pinjaman {i}"
    doc[9] = NOTES_HDR + "10. EFEK-EFEK YANG DITERBITKAN\nObligasi 500"
    return doc


def test_select_pages_long_first_note_does_not_starve_a_second_location() -> None:
    doc = _long_note_doc()
    units = select_pages([(3, 0.05), (9, 0.045)], doc, budget=4, heading_starts={1, 9})
    # seed 3 grows over its note, but seed 9 keeps its page
    assert [ps for _s, ps, _sc in units] == [[2, 3, 4], [9]]
    # a candidate inside the first seed's continuation reach is the same note, not a seed
    units = select_pages([(3, 0.05), (5, 0.049), (9, 0.045)], doc, budget=4, heading_starts={1, 9})
    assert [s for s, _ps, _sc in units] == [3, 9]


def test_select_pages_seed_after_a_note_start_holds_the_start_page() -> None:
    doc = _long_note_doc()
    doc[10] = NOTES_HDR + "10. EFEK-EFEK YANG DITERBITKAN (lanjutan)\nObligasi seri B"
    # seed 10 continues note 10, which starts on p9; seed 3 would take the rest of the
    # budget before seed 10's backward step, so p9 is held up front
    units = select_pages([(3, 0.05), (10, 0.045)], doc, budget=4, heading_starts={1, 9})
    assert [ps for _s, ps, _sc in units] == [[2, 3], [9, 10]]
    # no room for the start page: the seed keeps only its own page
    units = select_pages([(3, 0.05), (10, 0.045)], doc, budget=2, heading_starts={1, 9})
    assert [ps for _s, ps, _sc in units] == [[3], [10]]


def test_select_pages_adds_the_note_start_when_every_seed_is_mid_note() -> None:
    doc = _long_note_doc()
    # seed 6 is deep inside note 9 (reach 5..8); the note starts on p1, which only the
    # anchor leg ranks
    fused = [(6, 0.05), (1, 0.016)]
    units = select_pages(fused, doc, budget=4, heading_starts={1})
    assert [s for s, _ps, _sc in units] == [6, 1]
    assert sorted(p for _s, ps, _sc in units for p in ps) == [1, 5, 6, 7]
    # no extra seed when a seed already reaches a heading start
    units = select_pages([(2, 0.05), (1, 0.016)], doc, budget=4, heading_starts={1})
    assert [s for s, _ps, _sc in units] == [2]
    # never in statement mode
    units = select_pages(fused, doc, budget=4, top_k=1, heading_starts={1}, statement_mode=True)
    assert [s for s, _ps, _sc in units] == [6]


def test_policy_notes_that_describe_statements_are_excluded() -> None:
    policy = NOTES_HDR + "2. INFORMASI KEBIJAKAN AKUNTANSI MATERIAL (lanjutan)\nLaporan posisi keuangan"
    estimates = NOTES_HDR + "3. PENGGUNAAN ESTIMASI DAN PERTIMBANGAN\nAKUNTANSI YANG PENTING"
    estimates_en = NOTES_HDR + "38. CRITICAL ACCOUNTING ESTIMATES AND\nJUDGEMENTS"
    doc = {1: policy, 2: estimates, 3: estimates_en, 4: HDR + "LAPORAN POSISI KEUANGAN\nJumlah aset 1"}
    assert excluded_pages(doc, core_query=False) == {1, 2, 3, 4}
    assert excluded_pages(doc, core_query=True) == {1, 2, 3}


def test_sub_heading_anchors_rank_after_note_starts_and_before_continuations() -> None:
    comp = [re.compile("KREDIT YANG DIBERIKAN", re.I)]
    assert sub_heading_starts("Intro\nk. Kredit yang Diberikan dan Piutang/ k. Loans", comp)
    assert sub_heading_starts("(iii) Kredit yang diberikan dan piutang/\nx", comp)
    assert sub_heading_starts("4. Ikhtisar kredit yang diberikan dan\npiutang bermasalah", comp)
    # continued sub-heading, enumeration, table row, phrase far from the start: no
    assert not sub_heading_starts("k. Kredit yang Diberikan dan Piutang/\nPembiayaan (lanjutan)", comp)
    assert not sub_heading_starts("1. Kas, piutang dan kredit yang diberikan", comp)
    assert not sub_heading_starts("a. Kredit yang diberikan 1.234.567 1.000.000", comp)
    assert not sub_heading_starts("a. Rincian saldo menurut mata uang dan jangka waktu kredit yang diberikan", comp)

    doc = {
        1: NOTES_HDR + "12. KREDIT YANG DIBERIKAN\na. Berdasarkan jenis",
        2: NOTES_HDR + "12. KREDIT YANG DIBERIKAN (lanjutan)\nb. Berdasarkan sektor",
        3: NOTES_HDR + "40. INFORMASI TAMBAHAN\nk. Kredit yang Diberikan dan Piutang\nKol 1 Lancar",
        4: NOTES_HDR + "40. INFORMASI TAMBAHAN (lanjutan)\nk. Kredit yang Diberikan (lanjutan)",
    }
    ranked, starts = anchor_ranking(doc, ["KREDIT YANG DIBERIKAN"], set())
    # p4: the note heading line plus its next line matches -> a continuation page
    assert ranked == [1, 3, 2, 4] and starts == {1, 3}


def test_select_pages_statement_mode_walks_back_to_statement_start() -> None:
    doc = _doc()
    units = select_pages(
        [(3, 0.05), (4, 0.049)], doc, budget=6, top_k=1, statement_mode=True, exclude={1}
    )
    assert [ps for _s, ps, _sc in units] == [[2, 3]]


def test_compile_anchor_matches_headings_with_squashed_spaces() -> None:
    assert compile_anchor("UTANG BANK").search("15. UTANGBANK 15. BANK LOANS")
    assert compile_anchor("UTANG BANK").search("15. Utang  Bank")
    assert compile_anchor("SUKUK .{0,25}DITERBITKAN").search("28. SUKUKMUDHARABAHDITERBITKAN")
    assert not compile_anchor("UTANG BANK").search("15. UTANG USAHA")


def test_note_headings_join_only_upper_case_wraps() -> None:
    wrap = NOTES_HDR + "33. TUJUAN DAN KEBIJAKAN MANAJEMEN\nRISIKO KEUANGAN\nRisiko pasar"
    assert note_headings(wrap)[0][1].endswith("RISIKO KEUANGAN")
    # the first body line under a heading is not part of the heading text
    body = NOTES_HDR + "42. PERISTIWA SETELAH TANGGAL NERACA\nUtang bank jangka pendek"
    assert "Utang" not in note_headings(body)[0][1]
    # '-Lanjutan' / '-Continued' after the scale line marks a continued page
    cont = HDR + "CATATAN ATAS LAPORAN KEUANGAN\nkecuali dinyatakan lain)-Lanjutan\nTeks"
    assert is_continuation(NOTES_HDR + "1. UMUM\nTeks", cont)


def test_body_line_anchor_ranks_with_sub_headings_not_note_starts() -> None:
    doc = {
        1: NOTES_HDR + "8. ASET BIOLOGIS\nAset biologis terdiri atas",
        2: NOTES_HDR + "13. ASET TETAP\nTanaman Produktif/ Alat Berat",
        3: NOTES_HDR + "42. PERISTIWA SETELAH TANGGAL NERACA\nUtang bank jangka pendek",
    }
    ranked, starts = anchor_ranking(doc, ["ASET BIOLOGIS", "TANAMAN PRODUKTIF"], set())
    assert ranked == [1, 2] and starts == {1, 2}
    ranked, starts = anchor_ranking(doc, ["UTANG BANK"], set())
    assert ranked == [3] and starts == {3}
    # strong (the heading matches) vs weak (only the first body line does)
    assert pattern_starts(doc, ["ASET BIOLOGIS", "TANAMAN PRODUKTIF"], set()) == [
        {1: True},
        {2: False},
    ]


def test_forward_walk_stops_where_another_note_starts() -> None:
    doc = {
        1: NOTES_HDR + "33. MANAJEMEN RISIKO KEUANGAN\nRisiko kredit",
        2: NOTES_HDR + "33. MANAJEMEN RISIKO KEUANGAN (lanjutan)\nRisiko likuiditas\n"
        "34. PENGUKURAN NILAI WAJAR\nInstrumen keuangan",
        3: NOTES_HDR + "34. PENGUKURAN NILAI WAJAR (lanjutan)\nHierarki",
        4: NOTES_HDR + "34. PENGUKURAN NILAI WAJAR (lanjutan)\nLevel 3",
    }
    # p2 holds the tail of note 33, so it belongs; p3 continues note 34, so it doesn't
    assert list(forward_walk(1, doc, set())) == [2]
    # a seed inside note 34 walks on through note 34
    assert list(forward_walk(2, doc, set())) == [3, 4]


def test_policy_note_pages_without_a_heading_are_excluded() -> None:
    doc = {
        1: NOTES_HDR + "2. IKHTISAR KEBIJAKAN AKUNTANSI MATERIAL\na. Dasar penyusunan",
        2: NOTES_HDR + "t. Pengakuan Pendapatan\nPendapatan dari kontrak dengan pelanggan",
        3: NOTES_HDR + "u. Beban\nBeban diakui",
        4: NOTES_HDR + "4. KAS DAN SETARA KAS\nKas 100",
        5: NOTES_HDR + "Bank 900",
    }
    # pp2-3 continue the policy note; p5 continues note 4
    assert excluded_pages(doc, core_query=False) == {1, 2, 3}


def _multi_note_doc() -> dict[int, str]:
    """Note 1 General p1-2, note 30 risk management p5-7, note 40 subsequent events p9."""
    doc = {i: NOTES_HDR + "Teks" for i in range(1, 11)}
    doc[1] = NOTES_HDR + "1. UMUM\nPendirian perusahaan"
    doc[2] = NOTES_HDR + "1. UMUM (lanjutan)\nEntitas anak\n2. KEBIJAKAN AKUNTANSI\nDasar"
    doc[3] = NOTES_HDR + "2. KEBIJAKAN AKUNTANSI (lanjutan)\nDasar"
    doc[5] = NOTES_HDR + "30. MANAJEMEN RISIKO KEUANGAN\nRisiko kredit"
    doc[6] = NOTES_HDR + "30. MANAJEMEN RISIKO KEUANGAN (lanjutan)\nRisiko likuiditas"
    doc[7] = NOTES_HDR + "30. MANAJEMEN RISIKO KEUANGAN (lanjutan)\nRisiko pasar"
    doc[8] = NOTES_HDR + "31. PENGELOLAAN MODAL\nRasio utang"
    doc[9] = NOTES_HDR + "40. PERISTIWA SETELAH PERIODE PELAPORAN\nPinjaman baru"
    return doc


def test_select_pages_seeds_every_note_of_a_multi_note_module() -> None:
    doc = _multi_note_doc()
    patterns = [r"^\s*1\.\s+UMUM", "MANAJEMEN RISIKO", "PERISTIWA SETELAH"]
    concepts = pattern_starts(doc, patterns, set())
    # the risk note dominates the fused ranking; notes 1 and 40 sit far below the seed ratio
    fused = [(6, 0.05), (5, 0.049), (7, 0.048), (1, 0.016), (9, 0.015)]
    units = select_pages(fused, doc, budget=6, concept_starts=concepts, support={9})
    assert [s for s, _ps, _sc in units] == [6, 1, 9]
    assert sorted(p for _s, ps, _sc in units for p in ps) == [1, 2, 5, 6, 7, 9]
    # without concept starts only the risk note is routed
    units = select_pages(fused, doc, budget=6)
    assert [s for s, _ps, _sc in units] == [6]
    # a note matched only by its first body line needs FTS/ANN support
    units = select_pages(fused, doc, budget=6, concept_starts=[{9: False}], support=set())
    assert [s for s, _ps, _sc in units] == [6]


def test_cosine_top() -> None:
    vecs = {1: [1.0, 0.0], 2: [0.0, 1.0], 3: [0.7, 0.7], 4: [0.0, 0.0]}
    assert cosine_top([1.0, 0.1], vecs, limit=3) == [1, 3, 2]
    assert cosine_top([1.0, 0.0], {}) == []


def _router_handler(doc: dict[int, str], has_pgvector: bool, model: str) -> Any:
    def handle(sql: str, p: dict[str, Any]) -> Any:  # noqa: PLR0911 - one branch per query
        if sql.startswith("SET LOCAL statement_timeout"):
            return None
        if sql.startswith("SELECT page_index, page_text FROM document_pages"):
            return [{"page_index": i, "page_text": t} for i, t in sorted(doc.items())]
        if sql.startswith("WITH q AS"):
            return [{"page_index": 6, "rank": 0.3}, {"page_index": 5, "rank": 0.2},
                    {"page_index": 7, "rank": 0.1}, {"page_index": 2, "rank": 0.05}]
        if sql.startswith("SELECT count(*) FROM document_pages"):
            assert p["model"] == model
            return [{"count": len(doc)}]
        if "FROM pg_extension" in sql:
            return [{"x": 1}] if has_pgvector else []
        if sql.startswith("SELECT page_index FROM document_pages") and "halfvec" in sql:
            return [{"page_index": 6}, {"page_index": 5}]
        if sql.startswith("SELECT page_index, embedding FROM document_pages"):
            assert "embedding_model = :model" in sql
            return [{"page_index": i, "embedding": [1.0, 0.0] if i in (5, 6) else [0.0, 1.0]}
                    for i in doc]
        raise AssertionError(f"unexpected SQL: {sql}")

    return handle


class _QueryEmbedder(Embedder):
    def __init__(self) -> None:
        super().__init__(mode="fake")
        self.queries: list[str] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.queries.extend(texts)
        return [[1.0, 0.0] for _ in texts]


CASH_QUERY = RouteQuery(
    terms_id=["kas dan setara kas", "deposito berjangka"],
    terms_en=["cash and cash equivalents"],
    max_pages=3,
    anchor_patterns=["KAS DAN SETARA KAS"],
)


@pytest.mark.asyncio
async def test_route_pages_numpy_ann_and_budget() -> None:
    emb = _QueryEmbedder()
    conn = FakeConn(_router_handler(_doc(), has_pgvector=False, model=emb.model_id))
    spans = await pr.route_pages(conn, "d1", CASH_QUERY, top_k=3, embedder=emb)  # type: ignore[arg-type]
    pages = [p for s in spans for p in s.pages]
    assert pages[:2] == [5, 6] and len(pages) <= CASH_QUERY.max_pages
    assert conn.calls[0][0] == "SET LOCAL statement_timeout = '5000ms'"
    assert emb.queries and "cash and cash equivalents" in emb.queries[0]
    assert not any("::vector" in s for s, _p in conn.calls)


@pytest.mark.asyncio
async def test_route_pages_pgvector_bind_is_a_cast() -> None:
    emb = _QueryEmbedder()
    conn = FakeConn(_router_handler(_doc(), has_pgvector=True, model=emb.model_id))
    await pr.route_pages(conn, "d1", CASH_QUERY, embedder=emb)  # type: ignore[arg-type]
    ann_sql = [(s, p) for s, p in conn.calls if "halfvec" in s]
    assert ann_sql and "CAST(:q_vec AS halfvec(1024))" in ann_sql[0][0]
    assert ann_sql[0][1]["q_vec"].startswith("[1.0,")


@pytest.mark.asyncio
async def test_route_pages_fts_only_mode_skips_embedder() -> None:
    emb = _QueryEmbedder()
    conn = FakeConn(_router_handler(_doc(), has_pgvector=False, model=emb.model_id))
    spans = await pr.route_pages(conn, "d1", CASH_QUERY, embedder=emb, use_ann=False)  # type: ignore[arg-type]
    assert [p for s in spans for p in s.pages][:2] == [5, 6]
    assert emb.queries == []


class _BrokenEmbedder(_QueryEmbedder):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingUnavailableError("CUDA out of memory")


@pytest.mark.asyncio
async def test_route_pages_raises_when_query_embedding_fails() -> None:
    emb = _BrokenEmbedder()
    conn = FakeConn(_router_handler(_doc(), has_pgvector=False, model=emb.model_id))
    with pytest.raises(EmbeddingUnavailableError, match="CUDA out of memory"):
        await pr.route_pages(conn, "d1", CASH_QUERY, embedder=emb)  # type: ignore[arg-type]
