"""Submit deliberately wrong (and deliberately right) payloads against real indexed documents.

Uses submit_draft_extraction only (no commit, and a no-op processing-log writer, so nothing is
written to the DB). Each case names the ERROR categories that must appear ("caught"), or, for the
control cases, the per-fact categories that must NOT appear ("pass").

Doc ids (workstream B, re-indexed 2026-09-29 with the workstream-A indexer):
    BMRI 2025Q4  9a0154b0-9d27-42d4-b45a-f2ee9e75a187  (LK PT Bank Mandiri-Desember 2025.pdf)
    LSIP 2025Q4  9cbf5811-986f-4c8f-882f-6c0cf67a504a  (LSIP_bilingual_31 des_2025_released.pdf)
    LSIP 2025Q3  0d5a1599-cb28-4f0b-9212-c6d447728f25  (LSIP_bilingual_30_Sep_2025_Released.pdf)

Run: uv run python eval/review_tools/adversarial.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from typing import Any

from services.mcp.services.common import get_engine
from services.mcp.services.extraction import submit_draft_extraction

BMRI = "9a0154b0-9d27-42d4-b45a-f2ee9e75a187"
LSIP = "9cbf5811-986f-4c8f-882f-6c0cf67a504a"
LSIP_Q3 = "0d5a1599-cb28-4f0b-9212-c6d447728f25"
M = 1_000_000

# Categories that describe a single fact (used to judge the control cases).
FACT_CATEGORIES = {
    "SCHEMA",
    "PROVENANCE",
    "GROUNDING_CELL",
    "GROUNDING_TEXT",
    "GROUNDING_TEXT_LABEL_DISTANCE",
    "GROUNDING_COLUMN_PERIOD",
    "ROW_LABEL_MISMATCH",
    "CONCEPT_LABEL_MISMATCH",
    "PERIOD_TYPE_MISMATCH",
    "DUPLICATE_FACT",
}


def fact(
    cid: str,
    val: int,
    page: int,
    *,
    st: str = "BS",
    cell: tuple[int, int, int] | None = None,
    label: str | None = None,
    seg: dict[str, Any] | None = None,
    pt: str | None = None,
) -> dict[str, Any]:
    f: dict[str, Any] = {
        "concept_id": cid,
        "value_numeric": str(val),
        "statement": st,
        "source_page": page,
        "source_label_original": label or cid,
    }
    if cell:
        f["cell_ref"] = {"table_index": cell[0], "row": cell[1], "col": cell[2]}
    if seg:
        f["segment"] = seg
    if pt:
        f["period_type"] = pt
    return f


def payload(
    doc: str,
    ticker: str,
    facts: list[dict[str, Any]],
    *,
    narratives: list[dict[str, Any]] | None = None,
    omitted: list[dict[str, Any]] | None = None,
    fiscal_period: str = "2025Q4",
) -> dict[str, Any]:
    return {
        "doc_id": doc,
        "ticker": ticker,
        "fiscal_period": fiscal_period,
        "facts": facts,
        "narratives": narratives or [],
        "omitted_kpis": omitted or [],
    }


# name -> (payload, expected ERROR categories (any of), "caught" | "pass")
CASES: dict[str, tuple[dict[str, Any], set[str], str]] = {
    # --- the 10 review cases (docs/M9_REVIEW.md §5.D) ---
    "01_cell_transposed_digit": (
        payload(
            BMRI,
            "BMRI",
            [fact("idx:CashOnHand", 33_857_202 * M, 22, cell=(0, 3, 2), label="Kas", pt="instant")],
        ),
        {"GROUNDING_CELL"},
        "caught",
    ),
    "02_cell_prior_year_column": (
        payload(
            BMRI,
            "BMRI",
            [fact("idx:CashOnHand", 31_665_082 * M, 22, cell=(0, 3, 3), label="Kas", pt="instant")],
        ),
        {"GROUNDING_COLUMN_PERIOD"},
        "caught",
    ),
    "03_text_fabricated_number": (
        payload(BMRI, "BMRI", [fact("ifrs:Assets", 2_999_111_222 * M, 24, label="TOTAL ASET")]),
        {"GROUNDING_TEXT"},
        "caught",
    ),
    "04_text_wrong_row_same_page": (
        payload(
            LSIP,
            "LSIP",
            [
                fact(
                    "ifrs:EquityAttributableToOwnersOfParent",
                    13_996_113 * M,
                    15,
                    label="Ekuitas pemilik",
                )
            ],
        ),
        {"CONCEPT_LABEL_MISMATCH", "GROUNDING_TEXT_LABEL_DISTANCE"},
        "caught",
    ),
    "05_provenance_out_of_range": (
        payload(
            LSIP, "LSIP", [fact("ifrs:Revenue", 5_511_706 * M, 999, st="IS", label="Pendapatan")]
        ),
        {"PROVENANCE"},
        "caught",
    ),
    "06_synthetic_70_30_split": (
        payload(
            LSIP,
            "LSIP",
            [
                fact(
                    "ifrs:Revenue",
                    5_511_706 * M,
                    16,
                    st="IS",
                    label="Pendapatan dari kontrak dengan pelanggan",
                ),
                fact(
                    "ifrs:Revenue",
                    round(5_511_706 * 0.7) * M,
                    100,
                    st="NOTE",
                    label="Primary Operations",
                    seg={"segment": "Primary Operations", "type": "product"},
                ),
                fact(
                    "ifrs:Revenue",
                    round(5_511_706 * 0.3) * M,
                    100,
                    st="NOTE",
                    label="Other Operations",
                    seg={"segment": "Other Operations", "type": "product"},
                ),
            ],
        ),
        {"SYNTHETIC_LABEL", "SYNTHETIC_SPLIT"},
        "caught",
    ),
    "07_balance_prior_year_assets": (
        payload(
            BMRI,
            "BMRI",
            [
                fact("ifrs:Assets", 2_427_223_262 * M, 24, label="TOTAL ASET"),
                fact("ifrs:Liabilities", 2_212_925_204 * M, 27, label="TOTAL LIABILITAS"),
                fact(
                    "idx:TemporarySyirkahFunds",
                    289_620_824 * M,
                    28,
                    label="TOTAL DANA SYIRKAH TEMPORER",
                    pt="instant",
                ),
                fact("ifrs:Equity", 327_401_998 * M, 29, label="TOTAL EKUITAS"),
            ],
        ),
        {"BALANCE_SHEET_UNBALANCED", "GROUNDING_COLUMN_PERIOD"},
        "caught",
    ),
    "08_generic_narrative": (
        payload(
            LSIP,
            "LSIP",
            [
                fact(
                    "ifrs:Revenue",
                    5_511_706 * M,
                    16,
                    st="IS",
                    label="Pendapatan dari kontrak dengan pelanggan",
                )
            ],
            narratives=[
                {
                    "section": "MDA",
                    "text_original": "Perusahaan terus berkomitmen untuk meningkatkan kinerja dan memberikan nilai tambah bagi pemegang saham.",
                    "source_page": 16,
                }
            ],
        ),
        {"NARRATIVE_GENERIC", "NARRATIVE_NOT_VERBATIM"},
        "caught",
    ),
    "09_flow_as_instant": (
        payload(
            LSIP,
            "LSIP",
            [
                fact(
                    "idx:CostOfGoodsSoldComponent",
                    604_326 * M,
                    101,
                    st="NOTE",
                    label="Biaya panen",
                    seg={"segment": "Biaya Panen", "type": "cogs_component"},
                    pt="instant",
                )
            ],
        ),
        {"PERIOD_TYPE_MISMATCH"},
        "caught",
    ),
    "10_substring_number": (
        payload(
            LSIP,
            "LSIP",
            [fact("ifrs:FinanceCosts", 5_511 * M, 16, st="IS", label="Beban keuangan")],
        ),
        {"GROUNDING_TEXT"},
        "caught",
    ),
    # --- concept mistakes from the lighthouse data (review §3.3): must FAIL ---
    "C1_kas_as_cash_equivalents": (
        payload(
            BMRI,
            "BMRI",
            [fact("ifrs:CashAndCashEquivalents", 33_857_220 * M, 22, cell=(0, 3, 2), label="Kas")],
        ),
        {"CONCEPT_LABEL_MISMATCH"},
        "caught",
    ),
    "C2_restructured_npl_as_npl_gross": (
        payload(
            BMRI,
            "BMRI",
            [
                fact(
                    "idx:NonPerformingLoansGross",
                    9_259_663 * M,
                    510,
                    st="NOTE",
                    label="Total kredit yang telah direstrukturisasi dalam kategori NPL",
                )
            ],
        ),
        {"CONCEPT_LABEL_MISMATCH"},
        "caught",
    ),
    "C3_deposits_from_banks_as_bank_loans": (
        payload(
            BMRI,
            "BMRI",
            [fact("idx:BankLoans", 20_755_543 * M, 25, label="Total simpanan dari bank lain")],
        ),
        {"CONCEPT_LABEL_MISMATCH"},
        "caught",
    ),
    "C4_accrued_interest_as_receivables": (
        payload(
            BMRI,
            "BMRI",
            [
                fact(
                    "ifrs:TradeAndOtherReceivables",
                    7_218_467 * M,
                    226,
                    st="NOTE",
                    label="Bunga yang masih akan diterima",
                )
            ],
        ),
        {"CONCEPT_LABEL_MISMATCH"},
        "caught",
    ),
    "C5_total_equity_as_owners_equity": (
        payload(
            LSIP,
            "LSIP",
            [
                fact(
                    "ifrs:EquityAttributableToOwnersOfParent",
                    13_996_113 * M,
                    15,
                    label="Total Ekuitas",
                )
            ],
        ),
        {"CONCEPT_LABEL_MISMATCH"},
        "caught",
    ),
    "C6_lease_liability_as_short_term_borrowings": (
        payload(
            LSIP,
            "LSIP",
            [
                fact(
                    "ifrs:ShortTermBorrowings",
                    329 * M,
                    15,
                    label="Bagian lancar atas liabilitas sewa",
                )
            ],
        ),
        {"CONCEPT_LABEL_MISMATCH"},
        "caught",
    ),
    # --- correct concept mappings on real pages: must PASS (no per-fact ERROR) ---
    "P1_cash_equivalents_end_of_year": (
        payload(
            BMRI,
            "BMRI",
            [
                fact(
                    "ifrs:CashAndCashEquivalents",
                    379_877_189 * M,
                    38,
                    st="CF",
                    label="Kas dan setara kas akhir tahun",
                )
            ],
        ),
        FACT_CATEGORIES,
        "pass",
    ),
    "P2_total_assets": (
        payload(BMRI, "BMRI", [fact("ifrs:Assets", 2_829_948_026 * M, 24, label="Total Aset")]),
        FACT_CATEGORIES,
        "pass",
    ),
    "P3_owners_equity_subtotal": (
        payload(
            LSIP,
            "LSIP",
            [
                fact(
                    "ifrs:EquityAttributableToOwnersOfParent",
                    13_999_946 * M,
                    15,
                    label="Ekuitas yang dapat diatribusikan kepada pemilik entitas induk",
                )
            ],
        ),
        FACT_CATEGORIES,
        "pass",
    ),
    "P4_profit_for_the_year": (
        payload(
            LSIP,
            "LSIP",
            [fact("ifrs:ProfitLoss", 1_886_355 * M, 16, st="IS", label="Laba tahun berjalan")],
        ),
        FACT_CATEGORIES,
        "pass",
    ),
    "P5_cost_of_sales": (
        payload(
            LSIP,
            "LSIP",
            [fact("ifrs:CostOfSales", 3_250_368 * M, 16, st="IS", label="Beban pokok penjualan")],
        ),
        FACT_CATEGORIES,
        "pass",
    ),
    # --- narratives on real pages ---
    "N1_fabricated_narrative_on_is_page": (
        payload(
            LSIP,
            "LSIP",
            [
                fact(
                    "ifrs:Revenue",
                    5_511_706 * M,
                    16,
                    st="IS",
                    label="Pendapatan dari kontrak dengan pelanggan",
                )
            ],
            narratives=[
                {
                    "section": "MDA",
                    "text_original": "Penjualan Perseroan meningkat 20,8% menjadi Rp5,5 triliun didorong oleh kenaikan volume penjualan dan harga jual.",
                    "source_page": 16,
                }
            ],
        ),
        {"NARRATIVE_NOT_VERBATIM"},
        "caught",
    ),
    "N2_genuine_bilingual_quote": (
        payload(
            LSIP,
            "LSIP",
            [
                fact(
                    "ifrs:Revenue",
                    5_511_706 * M,
                    16,
                    st="IS",
                    label="Pendapatan dari kontrak dengan pelanggan",
                )
            ],
            narratives=[
                {
                    "section": "FOOTNOTE",
                    "text_original": (
                        "Tujuan utama pengelolaan modal Grup adalah untuk memastikan pemeliharaan rasio "
                        "modal yang sehat untuk mendukung usaha dan memaksimalkan imbalan bagi pemegang saham."
                    ),
                    "text_en": "The primary objective of the Group's capital management is to ensure that it maintains healthy capital ratios.",
                    "source_page": 100,
                }
            ],
        ),
        {"NARRATIVE_NOT_VERBATIM", "NARRATIVE_BOILERPLATE", "PROVENANCE"},
        "pass",
    ),
    # --- omissions and evidence ---
    "O1_lsip_q3_cce_omission": (
        payload(
            LSIP_Q3,
            "LSIP",
            [fact("ifrs:Assets", 14_784_538 * M, 4, label="Total Aset")],
            omitted=[
                {
                    "metric_id": "ifrs:CashAndCashEquivalents",
                    "reason": "NOT_DISCLOSED_IN_REPORT",
                    "explanation": "Cash and cash equivalents are not disclosed in this interim report.",
                    "search_pages_checked": list(range(1, 114)),
                }
            ],
            fiscal_period="2025Q3",
        ),
        {"OMISSION_CONTRADICTED"},
        "caught",
    ),
    "O2_omission_pages_out_of_range": (
        payload(
            LSIP_Q3,
            "LSIP",
            [fact("ifrs:Assets", 14_784_538 * M, 4, label="Total Aset")],
            omitted=[
                {
                    "metric_id": "idx:OilExtractionRate",
                    "reason": "NOT_DISCLOSED_IN_REPORT",
                    "explanation": "The interim financial statements do not report the oil extraction rate.",
                    "search_pages_checked": list(range(1, 400)),
                }
            ],
            fiscal_period="2025Q3",
        ),
        {"PROVENANCE"},
        "caught",
    ),
    "E1_document_not_indexed": (
        payload(
            str(uuid.uuid4()), "LSIP", [fact("ifrs:Assets", 14_784_538 * M, 4, label="Total Aset")]
        ),
        {"DOCUMENT_NOT_INDEXED"},
        "caught",
    ),
    "E2_duplicate_identity": (
        payload(
            LSIP,
            "LSIP",
            [
                fact("ifrs:ProfitLoss", 1_886_355 * M, 16, st="IS", label="Laba tahun berjalan"),
                fact("ifrs:ProfitLoss", 1_886_355 * M, 16, st="IS", label="Laba tahun berjalan"),
            ],
        ),
        {"DUPLICATE_FACT"},
        "caught",
    ),
}


async def _noop_log(*_args: Any, **_kwargs: Any) -> None:
    return None


async def main() -> int:
    eng = get_engine()
    failures = 0
    try:
        for name, (p, expected, mode) in CASES.items():
            rep = await submit_draft_extraction(json.dumps(p), engine=eng, log_event_fn=_noop_log)
            errors = sorted(
                {
                    i.category
                    for i in rep.issues
                    if getattr(i.severity, "value", i.severity) == "ERROR"
                }
            )
            if mode == "caught":
                ok = bool(expected & set(errors))
            else:
                ok = not (expected & set(errors))
            failures += not ok
            relevant = [c for c in errors if not c.startswith("MISSING")]
            print(
                f"{'OK  ' if ok else 'FAIL'} {name:<42} {mode:<6} status={rep.status:<8} errors={relevant}"
            )
    finally:
        await eng.dispose()
    print(f"\n{len(CASES) - failures}/{len(CASES)} cases behave as expected")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
