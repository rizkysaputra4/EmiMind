"""Unit tests for deterministic inspection triage (M9.1.2 remediation). No database.

Filenames are real names from `EmiMind-Extraction/incoming_reports/**`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pymupdf
import pytest

from services.mcp.services.inspection import (
    PdfFacts,
    _period_from_cover,
    classify_administrative,
    infer_doc_type,
    inspect_document,
    is_announcement,
    read_pdf_facts,
)
from services.mcp.types import InspectionStatus

FS_COVER = "LAPORAN POSISI KEUANGAN KONSOLIDASIAN 31 DESEMBER 2025"
LETTER_TEXT = "Perihal: Penyampaian Laporan Keuangan. Dengan hormat, bersama ini kami sampaikan"


@pytest.mark.parametrize(
    ("name", "reason"),
    [
        ("BMRI_2025_AUDIT_RDF_Checklist OJK Desember 2025-compressed_rotated.pdf", "checklist"),
        ("MIRA_2025_AUDIT_RDF_CHECKLIST PENGUNGKAPAN LKMIRA Des 25.pdf", "checklist"),
        ("BUVA_2021_TW1_RDF_Cheklist OJK.pdf", "checklist"),
        ("LSIP_2025_AUDIT_RDF_ESG2025-LSIP.pdf", "esg_sustainability"),
        ("ASMI_2024_ANNUAL_AAR_Sustainability Report 2024.pdf", "esg_sustainability"),
        ("PTDU_2024_AUDIT_RDF_PUBLIC EXPOSE 2025.pdf", "public_expose"),
        ("BABP_2021_AUDIT_RDF_Materi Pubex BABP 2022.pdf", "public_expose"),
        ("BMRI_2024_TW2_RDF_Surat Pengantar Corsec - BEI Juni 2024.pdf", "cover_letter"),
        ("LSIP_2025_AUDIT_RDF_LSIP_Pengantar LK FY2025.pdf", "cover_letter"),
        ("LSIP_2025_AUDIT_RDF_Surat Pernyataan Direksi LSIP 31 Desember 2025.pdf", "directors_statement"),
        ("SOHO_2023_TW2_RDF_SOHO Director Statement June23.pdf", "directors_statement"),
        ("CMPP_2024_TW2_RDF_20240730 - FS Q2 BOD Statement.pdf", "directors_statement"),
        ("KETR_2024_TW2_RDF_Penjelasan Perubahan Liabilitas Q2 2024.pdf", "explanation_letter"),
        ("LSIP_2025_AUDIT_RDF_LSIP Perubahan Lebih Dari 20 Persen FY2025.pdf", "change_over_20_percent"),
        ("IKAI_2021_TW1_RDF_Perubahan Aset dan Liabilitas IKAI Mar 21.pdf", "change_over_20_percent"),
        ("BOLT_2020_TW2_RDF_Bukti Iklan Investor Daily 23 Juli 2020.pdf", "newspaper_publication"),
        ("BTPS_2022_TW3_RDF_LK Bisnis Indonesia.pdf", "newspaper_publication"),
    ],
)
def test_administrative_filenames_are_skipped(name: str, reason: str) -> None:
    assert classify_administrative(name, None) == f"filename:{reason}"
    # a one-page letter with its real page count is skipped too
    assert classify_administrative(name, PdfFacts(page_count=1, cover_text=LETTER_TEXT)) is not None


@pytest.mark.parametrize(
    "name",
    [
        "BMRI_2025_AUDIT_RDF_LK PT Bank Mandiri-Desember 2025.pdf",
        "LSIP_2025_AUDIT_RDF_LSIP_bilingual_31 des_2025_released.pdf",
        "LSIP_2025_TW3_RDF_FinancialStatement-2025-III-LSIP.pdf",
        "AALI_2021_TW1_RDF_AALI LK TW I 2021.pdf",
        "BBCA_2025_AUDIT_RDF_Audited Report BCA 31 Des 2025 (Ind).pdf",
        "SINI_2021_AUDIT_RDF_AnnualReport2021-SINI-att1.pdf",
        "LPPS_2025_TW3_RDF_Laporan Posisi Keuangan Konsolidasian.pdf",
    ],
)
def test_statement_filenames_are_kept(name: str) -> None:
    assert classify_administrative(name, None) is None
    assert classify_administrative(name, PdfFacts(page_count=120, cover_text=FS_COVER)) is None


def test_letter_bundled_with_full_statement_is_kept() -> None:
    name = "XXXX_2025_AUDIT_RDF_Surat Pengantar dan Laporan Keuangan 2025.pdf"
    assert classify_administrative(name, PdfFacts(page_count=95, cover_text=FS_COVER)) is None
    assert classify_administrative(name, PdfFacts(page_count=2, cover_text=LETTER_TEXT))


def test_short_document_without_statement_keywords_is_skipped() -> None:
    name = "BDMN_2024_TW1_RDF_S.045.CORSEC.04.2024.pdf"
    assert classify_administrative(name, None) is None
    short_letter = PdfFacts(page_count=1, cover_text=LETTER_TEXT)
    assert classify_administrative(name, short_letter) == (
        "content:short_document_without_financial_statement"
    )
    short_fs = PdfFacts(page_count=3, cover_text="Laporan posisi keuangan ... Laba rugi")
    assert classify_administrative(name, short_fs) is None
    assert classify_administrative(name, PdfFacts(page_count=4, cover_text=LETTER_TEXT)) is None


@pytest.mark.parametrize(
    ("name", "period", "expected"),
    [
        ("BMRI_2025_AUDIT_RDF_LK PT Bank Mandiri-Desember 2025.pdf", "2025Q4", "FS_ANNUAL"),
        ("LSIP_2025_TW3_RDF_LSIP_bilingual_30_Sep_2025_Released.pdf", "2025Q3", "FS_QUARTERLY"),
        ("AALI_2021_TW1_RDF_AALI LK TW I 2021.pdf", "2021Q1", "FS_QUARTERLY"),
        ("MTWI_2022_ANNUAL_AAR_AnnualReport2022-MTWI-att1.pdf", "2022Q4", "ANNUAL_REPORT"),
        ("SINI_2021_AUDIT_RDF_AnnualReport2021-SINI-att1.pdf", "2021Q4", "ANNUAL_REPORT"),
        ("Annual Report 2025.pdf", "2025Q4", "ANNUAL_REPORT"),
        ("Laporan Keuangan TBP 30 Juni 2026.pdf", "2026Q2", "FS_QUARTERLY"),
        ("LSIP_bilingual_31 des_2025_released.pdf", "2025Q4", "FS_ANNUAL"),
    ],
)
def test_infer_doc_type(name: str, period: str, expected: str) -> None:
    assert infer_doc_type(name, period, None) == expected


def test_infer_doc_type_prefix_beats_content_guess() -> None:
    name = "LSIP_2025_TW3_RDF_LSIP_bilingual_30_Sep_2025_Released.pdf"
    assert infer_doc_type(name, "2025Q3", "ANNUAL_REPORT") == "FS_QUARTERLY"
    assert infer_doc_type("scan.pdf", "2025Q2", "FS_ANNUAL") == "FS_ANNUAL"


def test_is_announcement_domain() -> None:
    assert is_announcement(Path("incoming_reports/BMRI/announcements/x.pdf"), None)
    assert is_announcement(Path("x.pdf"), {"kind": "announcement"})
    assert not is_announcement(Path("incoming_reports/BMRI/processed/x.pdf"), {"kind": "fs"})


def test_period_from_cover_page() -> None:
    res = _period_from_cover(
        "PT SALIM IVOMAS\nLAPORAN KEUANGAN KONSOLIDASIAN INTERIM\n30 SEPTEMBER 2025\n"
        "DAN UNTUK PERIODE SEMBILAN BULAN YANG BERAKHIR PADA TANGGAL TERSEBUT"
    )
    assert res is not None and res.fiscal_period == "2025Q3" and res.source == "cover_page"
    assert _period_from_cover("") is None
    assert _period_from_cover("Surat pengantar tanpa periode") is None


# ------------------------------------------------------------------ inspect_document flow


def _pdf(path: Path, pages: list[str]) -> Path:
    doc = pymupdf.open()
    for body in pages:
        page = doc.new_page()
        page.insert_text((50, 72), body)
    doc.save(str(path))
    doc.close()
    return path


class _Result:
    def __init__(self, row: dict[str, Any] | None = None, scalar: int = 0) -> None:
        self._row = row
        self._scalar = scalar

    def mappings(self) -> _Result:
        return self

    def first(self) -> dict[str, Any] | None:
        return self._row

    def scalar(self) -> int:
        return self._scalar


class _FakeConn:
    def __init__(self, sector: str | None = "CPO") -> None:
        self.sector = sector
        self.sql: list[str] = []
        self.commit = AsyncMock()

    async def execute(self, stmt: Any, params: dict[str, Any] | None = None) -> _Result:
        sql = str(stmt)
        self.sql.append(sql)
        if "FROM issuer_profile" in sql:
            return _Result({"name": "PT Test Tbk", "sector": self.sector, "sub_sector": None})
        return _Result(None)


class _FakeEngine:
    def __init__(self, conn: _FakeConn) -> None:
        self.conn = conn

    def connect(self) -> Any:
        conn = self.conn

        class _Ctx:
            async def __aenter__(self) -> _FakeConn:
                return conn

            async def __aexit__(self, *args: Any) -> None:
                return None

        return _Ctx()


async def _inspect(path: Path, **kwargs: Any) -> tuple[Any, _FakeConn, AsyncMock, AsyncMock]:
    conn = _FakeConn()
    log_fn = AsyncMock()
    enqueue = AsyncMock()
    res = await inspect_document(
        str(path), engine=_FakeEngine(conn), log_event_fn=log_fn, enqueue_fn=enqueue, **kwargs  # type: ignore[arg-type]
    )
    return res, conn, log_fn, enqueue


def _actions(log_fn: AsyncMock) -> list[str]:
    return [c.kwargs["action"] for c in log_fn.await_args_list]


def _inserted(conn: _FakeConn) -> bool:
    return any("INSERT INTO documents" in s for s in conn.sql)


async def test_checklist_is_skipped_administrative_without_registration(tmp_path: Path) -> None:
    f = _pdf(tmp_path / "BMRI_2025_AUDIT_RDF_Checklist OJK Desember 2025.pdf", [FS_COVER] * 5)
    res, conn, log_fn, enqueue = await _inspect(f)
    assert res.status == InspectionStatus.SKIPPED_ADMINISTRATIVE
    assert _actions(log_fn) == ["SKIPPED_ADMINISTRATIVE"]
    assert not _inserted(conn)
    enqueue.assert_not_awaited()


async def test_scanned_style_cover_letter_is_skipped(tmp_path: Path) -> None:
    f = _pdf(tmp_path / "BMRI_2024_TW2_RDF_Surat Pengantar Corsec - BEI Juni 2024.pdf", [""])
    res, conn, _log, _enq = await _inspect(f)
    assert res.status == InspectionStatus.SKIPPED_ADMINISTRATIVE
    assert not _inserted(conn)


async def test_prefix_conflict_resolved_from_cover_page(tmp_path: Path) -> None:
    f = _pdf(
        tmp_path / "FOOD_2023_TW1_RDF_LK PT SFI TW 3_2022.pdf",
        ["LAPORAN KEUANGAN INTERIM\nLAPORAN POSISI KEUANGAN 30 SEPTEMBER 2022\n"
         "UNTUK PERIODE SEMBILAN BULAN YANG BERAKHIR 30 SEPTEMBER 2022"] + ["notes"] * 10,
    )  # fmt: skip
    res, conn, log_fn, enqueue = await _inspect(f, ticker="FOOD")
    assert res.status == InspectionStatus.AUTHORIZED
    assert res.fiscal_period == "2022Q3"
    assert res.doc_type == "FS_QUARTERLY"
    assert _inserted(conn)
    authorized = [c for c in log_fn.await_args_list if c.kwargs["action"] == "INSPECTED_AUTHORIZED"]
    meta = authorized[0].kwargs["metadata"]
    assert meta["filename_period"] == "2023Q1"
    assert meta["conflicting_period"] == "2022Q3"
    assert meta["cover_period"] == "2022Q3"
    assert meta["period_source"] == "cover_page"
    assert meta["page_count"] == 11
    enqueue.assert_awaited_once()


async def test_prefix_conflict_without_cover_evidence_needs_metadata(tmp_path: Path) -> None:
    f = _pdf(tmp_path / "RIGS_2023_TW2_RDF_RIGS - Laporan Keuangan 31 Desember 2023.pdf",
             ["Laporan posisi keuangan tanpa tanggal"] * 8)  # fmt: skip
    res, conn, log_fn, _enq = await _inspect(f, ticker="RIGS")
    assert res.status == InspectionStatus.NEEDS_METADATA
    assert "2023Q2" in res.message and "2023Q4" in res.message
    assert _actions(log_fn) == ["NEEDS_METADATA"]
    assert not _inserted(conn)
    # the agent confirms the period from the cover page and re-calls with it
    res2, conn2, _log2, _enq2 = await _inspect(f, ticker="RIGS", fiscal_period="2023Q4")
    assert res2.status == InspectionStatus.AUTHORIZED
    assert res2.fiscal_period == "2023Q4"
    assert _inserted(conn2)


async def test_unreadable_pdf_is_error_never_page_count_one(tmp_path: Path) -> None:
    f = tmp_path / "LSIP_2025_TW3_RDF_LSIP_bilingual_30_Sep_2025_Released.pdf"
    f.write_bytes(b"%PDF-1.4 not really a pdf")
    assert read_pdf_facts(f) is None
    res, conn, log_fn, _enq = await _inspect(f, ticker="LSIP")
    assert res.status == InspectionStatus.ERROR
    assert _actions(log_fn) == ["ERROR"]
    assert not _inserted(conn)


async def test_half_year_hint_maps_to_q2(tmp_path: Path) -> None:
    f = _pdf(tmp_path / "Financial Statements 1H26.pdf", [FS_COVER] * 6)
    res, _conn, _log, _enq = await _inspect(f, ticker="LSIP", fiscal_period="2026H1")
    assert res.status == InspectionStatus.AUTHORIZED
    assert res.fiscal_period == "2026Q2"


async def test_invalid_hint_needs_metadata_instead_of_crashing(tmp_path: Path) -> None:
    f = _pdf(tmp_path / "scan.pdf", [FS_COVER] * 6)
    res, _conn, _log, _enq = await _inspect(f, ticker="LSIP", fiscal_period="2025-05-15")
    assert res.status == InspectionStatus.NEEDS_METADATA


def _announcement_pdf(tmp_path: Path) -> Path:
    ann_dir = tmp_path / "BMRI" / "announcements"
    ann_dir.mkdir(parents=True)
    f = _pdf(ann_dir / "pengumuman_dividen.pdf", ["Pengumuman pembagian dividen tunai"])
    meta = {"kind": "announcement", "ticker": "BMRI", "doc_class_hint": "DIVIDEND",
            "announcement_date": "2025-05-15T10:00:00"}  # fmt: skip
    Path(str(f) + ".meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return f


async def test_announcement_sidecar_date_is_not_a_period(tmp_path: Path) -> None:
    f = _announcement_pdf(tmp_path)
    res, _conn, log_fn, _enq = await _inspect(f)
    # short, keyword-free, but in the announcement domain: not skipped as administrative
    assert res.status == InspectionStatus.NEEDS_METADATA
    assert _actions(log_fn) == ["NEEDS_METADATA"]
    res2, conn2, _log2, _enq2 = await _inspect(f, fiscal_period="2025Q2")
    assert res2.status == InspectionStatus.AUTHORIZED
    assert res2.doc_type == "DIVIDEND"
    assert _inserted(conn2)


def test_inspect_module_has_no_llm_fallback() -> None:
    import services.mcp.services.inspection as mod

    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "propose_metadata(" not in src  # the async LLM-capable extractor is never called
    assert "propose_metadata_from_text" in src  # regex-only entry point


@pytest.mark.parametrize(
    "name",
    [
        "PNBS_2022_AUDIT_RDF_e-paper LK PaninSyariah Des_2021 Audited.pdf",
        "DMAS_2020_AUDIT_RDF_DMAS News Release 31 Mar 2021.pdf",
        "KEHA_2021_AUDIT_RDF_KEHA-Scan Koran-Dec2021.pdf",
    ],
)
def test_press_and_newspaper_items_are_skipped(name: str) -> None:
    assert classify_administrative(name, None) == "filename:newspaper_publication"


def test_doc_type_follows_the_period_when_the_prefix_was_overridden() -> None:
    name = "RIGS_2024_AUDIT_RDF_RIGS - VIII.G.07 RIG Tenders 30 Juni 2025.pdf"
    assert infer_doc_type(name, "2024Q4", None) == "FS_ANNUAL"
    assert infer_doc_type(name, "2025Q2", None, period_from_prefix=False) == "FS_QUARTERLY"
    name = "CANI_2020_TW2_RDF_CANI_LK TW-II  31 Dec 2020 (in house).pdf"
    assert infer_doc_type(name, "2020Q4", None, period_from_prefix=False) == "FS_ANNUAL"
