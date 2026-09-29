"""In-memory ExtractionContract fixtures for MCP validator/server unit tests.

Unit tests should not depend on a live Postgres. These fixtures mirror the
minimum shape of what `build_extraction_contract` returns from the DB so that
`validate_draft_submission` can be exercised in isolation.
"""

from __future__ import annotations

from decimal import Decimal

from services.mcp.contracts import get_route_query
from services.mcp.grounding import is_monetary_unit, is_percent_unit
from services.mcp.types import (
    ExtractedFactItem,
    ExtractionContract,
    ExtractionFactRule,
    GranularNoteModule,
    PageEvidence,
)

MN = Decimal(1_000_000)
PAGE_HEADER = "PT TEST Tbk\nLAPORAN KEUANGAN\n(Disajikan dalam jutaan Rupiah, kecuali dinyatakan lain)\n"


def fmt_id(v: Decimal) -> str:
    """Indonesian number formatting: 100000 -> '100.000', 5.25 -> '5,25'."""
    if v == v.to_integral_value():
        return f"{int(v):,}".replace(",", ".")
    whole, frac = f"{v:f}".split(".")
    return f"{int(whole):,}".replace(",", ".") + "," + frac


def printed_value(f: ExtractedFactItem) -> str:
    """How the fact's number is printed on a 'jutaan Rupiah' page."""
    if is_percent_unit(f.unit):
        return fmt_id(f.value_numeric) + "%"
    if is_monetary_unit(f.unit):
        return fmt_id(f.value_numeric / MN)
    return fmt_id(f.value_numeric)


def render_page_text(facts: list[ExtractedFactItem], page: int, extra: str = "") -> str:
    lines = [
        f"{f.source_label_original} {printed_value(f)}"
        for f in facts
        if f.source_page == page and f.cell_ref is None
    ]
    return PAGE_HEADER + "\n".join([*lines, *([extra] if extra else [])])


def render_evidence(
    facts: list[ExtractedFactItem], extra: dict[int, str] | None = None
) -> dict[int, PageEvidence]:
    """Page evidence with one "<label> <value in millions>" line per fact on its cited page."""
    pages = {f.source_page for f in facts if f.source_page is not None and f.source_page > 0}
    pages |= set(extra or {})
    return {
        p: PageEvidence(
            page_index=p, text_source="pdf_text", page_text=render_page_text(facts, p, (extra or {}).get(p, ""))
        )
        for p in sorted(pages)
    }

_CORE_RULES: list[ExtractionFactRule] = [
    ExtractionFactRule(concept_id="ifrs:Assets", label="Total Assets", statement_type="BALANCE_SHEET", required=True, importance="CRITICAL"),
    ExtractionFactRule(concept_id="ifrs:CurrentAssets", label="Current Assets", statement_type="BALANCE_SHEET", required=True, importance="CRITICAL"),
    ExtractionFactRule(concept_id="ifrs:NonCurrentAssets", label="Non-Current Assets", statement_type="BALANCE_SHEET", required=True, importance="CRITICAL"),
    ExtractionFactRule(concept_id="ifrs:CashAndCashEquivalents", label="Cash", statement_type="BALANCE_SHEET", required=True, importance="HIGH"),
    ExtractionFactRule(concept_id="ifrs:Liabilities", label="Total Liabilities", statement_type="BALANCE_SHEET", required=True, importance="CRITICAL"),
    ExtractionFactRule(concept_id="ifrs:CurrentLiabilities", label="Current Liabilities", statement_type="BALANCE_SHEET", required=True, importance="CRITICAL"),
    ExtractionFactRule(concept_id="ifrs:NonCurrentLiabilities", label="Non-Current Liabilities", statement_type="BALANCE_SHEET", required=True, importance="CRITICAL"),
    ExtractionFactRule(concept_id="ifrs:Equity", label="Total Equity", statement_type="BALANCE_SHEET", required=True, importance="CRITICAL"),
    ExtractionFactRule(concept_id="ifrs:Revenue", label="Revenue", statement_type="INCOME_STATEMENT", required=True, importance="CRITICAL"),
    ExtractionFactRule(concept_id="ifrs:OperatingProfit", label="Operating Profit", statement_type="INCOME_STATEMENT", required=True, importance="CRITICAL"),
    ExtractionFactRule(concept_id="ifrs:ProfitLoss", label="Net Profit", statement_type="INCOME_STATEMENT", required=True, importance="CRITICAL"),
    ExtractionFactRule(concept_id="ifrs:CashFlowsFromUsedInOperatingActivities", label="CFO", statement_type="CASH_FLOW", required=True, importance="CRITICAL"),
    ExtractionFactRule(concept_id="ifrs:CostOfSales", label="COGS", statement_type="INCOME_STATEMENT", required=False, importance="HIGH"),
    ExtractionFactRule(concept_id="ifrs:GrossProfit", label="Gross Profit", statement_type="INCOME_STATEMENT", required=False, importance="HIGH"),
]

_BANK_RULES: list[ExtractionFactRule] = [
    ExtractionFactRule(concept_id="idx:LoansAndAdvances", label="Loans and Advances", statement_type="BALANCE_SHEET", required=True, importance="CRITICAL",
                       synonyms_id=["Kredit yang Diberikan", "Kredit Bank"], search_hints=["Catatan Kredit yang Diberikan"]),
    ExtractionFactRule(concept_id="idx:CustomerDeposits", label="Customer Deposits", statement_type="BALANCE_SHEET", required=True, importance="CRITICAL",
                       synonyms_id=["Dana Pihak Ketiga", "DPK"], search_hints=["Catatan Simpanan Nasabah"]),
    ExtractionFactRule(concept_id="idx:CASA", label="CASA", statement_type="BALANCE_SHEET", required=True, importance="HIGH"),
    ExtractionFactRule(concept_id="idx:NetInterestIncome", label="Net Interest Income", statement_type="INCOME_STATEMENT", required=True, importance="CRITICAL"),
    ExtractionFactRule(concept_id="idx:NetInterestMargin", label="Net Interest Margin", statement_type="OPERATIONAL_KPI", required=True, importance="CRITICAL"),
    ExtractionFactRule(concept_id="idx:NonPerformingLoansGross", label="NPL Gross", statement_type="OPERATIONAL_KPI", required=True, importance="CRITICAL"),
    ExtractionFactRule(concept_id="idx:CapitalAdequacyRatio", label="CAR", statement_type="OPERATIONAL_KPI", required=True, importance="CRITICAL"),
    ExtractionFactRule(concept_id="idx:BOPO", label="BOPO", statement_type="OPERATIONAL_KPI", required=True, importance="CRITICAL"),
    ExtractionFactRule(concept_id="idx:CostOfCredit", label="Cost of Credit", statement_type="OPERATIONAL_KPI", required=True, importance="HIGH"),
    ExtractionFactRule(concept_id="idx:LoanToDepositRatio", label="LDR", statement_type="OPERATIONAL_KPI", required=True, importance="HIGH"),
    ExtractionFactRule(
        concept_id="idx:NPLCoverageRatio", label="NPL Coverage Ratio", statement_type="OPERATIONAL_KPI",
        required=True, importance="HIGH", unit="PERCENT", value_type="PERCENTAGE",
        search_hints=["Catatan Cadangan Kerugian Penurunan Nilai (CKPN)"],
        synonyms_id=["Rasio Cakupan NPL", "Cakupan CKPN"],
    ),
]

_CPO_RULES: list[ExtractionFactRule] = [
    ExtractionFactRule(concept_id="idx:MaturePlantedArea", label="Mature Planted Area (Ha)", statement_type="OPERATIONAL_KPI",
                       required=True, importance="CRITICAL", unit="HECTARES"),
    ExtractionFactRule(concept_id="idx:FfbProduction", label="FFB Production (Ton)", statement_type="OPERATIONAL_KPI",
                       required=True, importance="CRITICAL", unit="TONNES"),
    ExtractionFactRule(concept_id="idx:CPOProductionVolume", label="CPO Production Volume (Ton)", statement_type="OPERATIONAL_KPI",
                       required=True, importance="CRITICAL", unit="TONNES",
                       synonyms_en=["CPO Production"], synonyms_id=["Produksi CPO"]),
    ExtractionFactRule(concept_id="idx:OilExtractionRate", label="OER (%)", statement_type="OPERATIONAL_KPI",
                       required=True, importance="CRITICAL", unit="PERCENT"),
    ExtractionFactRule(concept_id="idx:CPOAveragePriceASP", label="CPO ASP", statement_type="OPERATIONAL_KPI",
                       required=True, importance="CRITICAL", unit="IDR_PER_KG"),
    ExtractionFactRule(concept_id="idx:CPOCashCostPerKg", label="CPO Cash Cost", statement_type="OPERATIONAL_KPI",
                       required=True, importance="CRITICAL", unit="IDR_PER_KG"),
]

_MINING_RULES: list[ExtractionFactRule] = [
    ExtractionFactRule(concept_id="idx:CoalProductionVolume", label="Coal Production (MT)", statement_type="OPERATIONAL_KPI",
                       required=True, importance="CRITICAL"),
    ExtractionFactRule(concept_id="idx:AverageSellingPrice", label="ASP", statement_type="OPERATIONAL_KPI",
                       required=False, importance="HIGH"),
]

_SECTOR_RULES = {
    "BANK": _BANK_RULES,
    "CPO": _CPO_RULES,
    "MINING": _MINING_RULES,
}


def make_test_contract(sector: str, doc_id: str = "test_doc", ticker: str = "TEST", fiscal_period: str = "2024Q4") -> ExtractionContract:
    sector_upper = (sector or "GENERIC").upper()
    rules = list(_CORE_RULES) + list(_SECTOR_RULES.get(sector_upper, []))

    granular = [
        GranularNoteModule(
            name="REVENUE_BREAKDOWN",
            description="Rincian pendapatan per lini produk",
            typical_note_title="Catatan Pendapatan / Segmen",
            target_concepts=["ifrs:Revenue"],
            expected_segment_fields=["segment", "type", "pct_total"],
            guideline="Extract each product line with segment metadata.",
            route_query=get_route_query("REVENUE_BREAKDOWN", sector_upper),
        ),
    ]
    if sector_upper == "BANK":
        granular.append(
            GranularNoteModule(
                name="BANK_LOANS_NPL",
                description="Kolektibilitas kredit dan pencadangan kerugian (NPL, CKPN).",
                typical_note_title="Catatan Kualitas Aset Produktif / Kolektibilitas Kredit",
                target_concepts=["idx:LoansAndAdvances", "idx:NonPerformingLoansGross"],
                expected_segment_fields=["segment", "type", "kol_rating", "npl_status"],
                guideline="Extract loan quality and NPL per collectibility category.",
                route_query=get_route_query("BANK_LOANS_NPL", sector_upper),
            )
        )
    elif sector_upper in ("CPO", "PLANTATION"):
        granular.append(
            GranularNoteModule(
                name="PLANTATION_AREA",
                description="Profil kebun kelapa sawit: luas areal tertanam.",
                typical_note_title="Catatan Tanaman Produktif / Aset Biologis / Perkebunan",
                target_concepts=["ifrs:BiologicalAssets", "idx:MaturePlantedArea"],
                expected_segment_fields=["segment", "type", "planted_area_ha"],
                guideline="Extract planted hectares breakdown.",
                route_query=get_route_query("PLANTATION_AREA", sector_upper),
            )
        )

    core_modules = {}
    for mod in ["BALANCE_SHEET", "INCOME_STATEMENT", "CASH_FLOW", "MDA"]:
        rq = get_route_query(mod, sector_upper)
        if rq:
            core_modules[mod] = rq

    return ExtractionContract(
        doc_id=doc_id,
        ticker=ticker.upper(),
        company_name=f"PT {ticker.upper()} Tbk",
        sector=sector_upper,
        fiscal_period=fiscal_period.upper(),
        period_type="duration_ytd",
        scaling_rules={"unit": "IDR"},
        required_facts=rules,
        required_narratives=[],
        granular_note_modules=granular,
        core_modules=core_modules,
        sector_specific_guidelines=[],
        do_not_extract=[],
    )
