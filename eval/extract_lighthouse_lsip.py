"""Lighthouse Extraction Execution for LSIP (PT PP London Sumatra Indonesia Tbk) 2025Q4.

Follows Section 6 of docs/runbook.md: Targeted Deep Extraction Protocol.
Extracts Core Statements (BS, IS, CF) and Granular Disclosures (Notes 5, 8, 13, 20, 21, 22, 23).
"""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal

from services.mcp.services.common import get_engine
from services.mcp.services.extraction import commit_verified_report, submit_draft_extraction
from services.mcp.services.inspection import inspect_document
from services.mcp.services.routing import get_extraction_contract
from services.mcp.types import (
    CellRef,
    DraftSubmissionPayload,
    ExtractedCausalLink,
    ExtractedFactItem,
    ExtractedNarrativeItem,
    OmittedMetricItem,
    ProcessingUsage,
)
from services.shared.logging import get_logger

log = get_logger("eval.extract.lsip")

DOC_ID = "82e20a07-232e-45bc-9a7b-3b160e8c2ece"
TICKER = "LSIP"
PERIOD = "2025Q4"


def build_lsip_facts() -> list[ExtractedFactItem]:
    """Builds grounded financial facts for LSIP 2025Q4."""
    facts: list[ExtractedFactItem] = []

    # -------------------------------------------------------------
    # 1. BALANCE SHEET - ASSETS (Page 14, Table 0, Scale: IDR Millions)
    # -------------------------------------------------------------
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:Assets",
            value_numeric=Decimal("15540077000000"),
            statement="BS",
            source_page=14,
            cell_ref=CellRef(table_index=0, row=31, col=1),
            source_label_original="Total Aset",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:CurrentAssets",
            value_numeric=Decimal("8699271000000"),
            statement="BS",
            source_page=14,
            cell_ref=CellRef(table_index=0, row=19, col=1),
            source_label_original="Total Aset Lancar",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:NonCurrentAssets",
            value_numeric=Decimal("6840806000000"),
            statement="BS",
            source_page=14,
            cell_ref=CellRef(table_index=0, row=30, col=1),
            source_label_original="Total Aset Tidak Lancar",
        )
    )
    # Cash & Cash Equivalents on BS (Row 43 on Page 19 Table 0: 7.597.470 million)
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:CashAndCashEquivalents",
            value_numeric=Decimal("7597470000000"),
            statement="BS",
            source_page=19,
            cell_ref=CellRef(table_index=0, row=43, col=1),
            source_label_original="Kas dan setara kas akhir tahun",
        )
    )
    # Trade and other receivables (Related party 15.201 million, row 7 col 1)
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:TradeAndOtherReceivables",
            value_numeric=Decimal("15201000000"),
            statement="BS",
            source_page=14,
            cell_ref=CellRef(table_index=0, row=7, col=1),
            segment={"type": "related_party", "segment": "Pihak Berelasi"},
            source_label_original="Piutang usaha pihak berelasi",
        )
    )
    # Trade and other receivables (Third parties 25.071 million, row 8 col 1)
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:TradeAndOtherReceivables",
            value_numeric=Decimal("25071000000"),
            statement="BS",
            source_page=14,
            cell_ref=CellRef(table_index=0, row=8, col=1),
            segment={"type": "related_party", "segment": "Pihak Ketiga"},
            source_label_original="Piutang usaha pihak ketiga",
        )
    )
    # Inventories: R12 Col 1: 613.808 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:Inventories",
            value_numeric=Decimal("613808000000"),
            statement="BS",
            source_page=14,
            cell_ref=CellRef(table_index=0, row=12, col=1),
            source_label_original="Persediaan",
        )
    )
    # Biological Assets (Current produce): R16 Col 1: 245.735 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:BiologicalAssetsCurrent",
            value_numeric=Decimal("245735000000"),
            statement="BS",
            source_page=14,
            cell_ref=CellRef(table_index=0, row=16, col=1),
            source_label_original="Aset biologis (lancar)",
        )
    )
    # Property, Plant & Equipment (Aset tetap): R28 Col 1: 5.129.490 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:PropertyPlantAndEquipment",
            value_numeric=Decimal("5129490000000"),
            statement="BS",
            source_page=14,
            cell_ref=CellRef(table_index=0, row=28, col=1),
            source_label_original="Aset tetap",
        )
    )
    # Investment in associates: R26 Col 1: 1.259.611 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:InvestmentInAssociates",
            value_numeric=Decimal("1259611000000"),
            statement="BS",
            source_page=14,
            cell_ref=CellRef(table_index=0, row=26, col=1),
            source_label_original="Investasi pada entitas asosiasi",
        )
    )
    # Deferred tax assets: R27 Col 1: 341 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:DeferredTaxAssets",
            value_numeric=Decimal("341000000"),
            statement="BS",
            source_page=14,
            cell_ref=CellRef(table_index=0, row=27, col=1),
            source_label_original="Aset pajak tangguhan",
        )
    )
    # Plasma receivables: R25 Col 1: 132.269 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:PlasmaReceivables",
            value_numeric=Decimal("132269000000"),
            statement="BS",
            source_page=14,
            cell_ref=CellRef(table_index=0, row=25, col=1),
            source_label_original="Piutang plasma",
        )
    )
    # Right-of-use assets: R24 Col 1: 1.238 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:RightOfUseAssets",
            value_numeric=Decimal("1238000000"),
            statement="BS",
            source_page=14,
            cell_ref=CellRef(table_index=0, row=24, col=1),
            source_label_original="Aset hak-guna",
        )
    )
    # Prepaid expenses: R15 Col 1: 7.009 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:PrepaidExpenses",
            value_numeric=Decimal("7009000000"),
            statement="BS",
            source_page=14,
            cell_ref=CellRef(table_index=0, row=15, col=1),
            source_label_original="Biaya dibayar di muka",
        )
    )
    # Advances to suppliers: R14 Col 1: 4.769 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:AdvancesToSuppliers",
            value_numeric=Decimal("4769000000"),
            statement="BS",
            source_page=14,
            cell_ref=CellRef(table_index=0, row=14, col=1),
            source_label_original="Uang muka pemasok",
        )
    )
    # Prepaid taxes: R13 Col 1: 3.737 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:PrepaidTaxes",
            value_numeric=Decimal("3737000000"),
            statement="BS",
            source_page=14,
            cell_ref=CellRef(table_index=0, row=13, col=1),
            source_label_original="Pajak dibayar di muka",
        )
    )
    # Other non-current assets: R29 Col 1: 285.038 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:OtherNonCurrentAssets",
            value_numeric=Decimal("285038000000"),
            statement="BS",
            source_page=14,
            cell_ref=CellRef(table_index=0, row=29, col=1),
            source_label_original="Aset tidak lancar lainnya",
        )
    )
    # Deferred charges: R21 Col 1: 32.633 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:DeferredCharges",
            value_numeric=Decimal("32633000000"),
            statement="BS",
            source_page=14,
            cell_ref=CellRef(table_index=0, row=21, col=1),
            source_label_original="Beban tangguhan",
        )
    )

    # -------------------------------------------------------------
    # 2. BALANCE SHEET - LIABILITIES & EQUITY (Page 15, Table 0, Scale: IDR Millions)
    # -------------------------------------------------------------
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:Liabilities",
            value_numeric=Decimal("1543964000000"),
            statement="BS",
            source_page=15,
            cell_ref=CellRef(table_index=0, row=24, col=1),
            source_label_original="Total Liabilitas",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:CurrentLiabilities",
            value_numeric=Decimal("920410000000"),
            statement="BS",
            source_page=15,
            cell_ref=CellRef(table_index=0, row=19, col=1),
            source_label_original="Total Liabilitas Jangka Pendek",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:NonCurrentLiabilities",
            value_numeric=Decimal("623554000000"),
            statement="BS",
            source_page=15,
            cell_ref=CellRef(table_index=0, row=23, col=1),
            source_label_original="Total Liabilitas Jangka Panjang",
        )
    )
    # Equity on Page 15: 13.996.113 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:Equity",
            value_numeric=Decimal("13996113000000"),
            statement="BS",
            source_page=15,
            source_label_original="Total Ekuitas",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:EquityAttributableToOwnersOfParent",
            value_numeric=Decimal("13996113000000"),
            statement="BS",
            source_page=15,
            source_label_original="Ekuitas yang Dapat Diatribusikan kepada Pemilik Entitas Induk",
        )
    )
    # Trade payables third parties: R06 Col 1: 249.153 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:TradePayables",
            value_numeric=Decimal("249153000000"),
            statement="BS",
            source_page=15,
            cell_ref=CellRef(table_index=0, row=6, col=1),
            segment={"type": "related_party", "segment": "Pihak Ketiga"},
            source_label_original="Utang usaha pihak ketiga",
        )
    )
    # Trade payables related party: R07 Col 1: 1.547 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:TradePayables",
            value_numeric=Decimal("1547000000"),
            statement="BS",
            source_page=15,
            cell_ref=CellRef(table_index=0, row=7, col=1),
            segment={"type": "related_party", "segment": "Pihak Berelasi"},
            source_label_original="Utang usaha pihak berelasi",
        )
    )
    # Taxes payable: R14 Col 1: 208.798 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:TaxPayable",
            value_numeric=Decimal("208798000000"),
            statement="BS",
            source_page=15,
            cell_ref=CellRef(table_index=0, row=14, col=1),
            source_label_original="Utang pajak",
        )
    )
    # Employee benefits liability: R22 Col 1: 516.543 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:EmployeeBenefitsLiability",
            value_numeric=Decimal("516543000000"),
            statement="BS",
            source_page=15,
            cell_ref=CellRef(table_index=0, row=22, col=1),
            source_label_original="Liabilitas imbalan kerja jangka panjang",
        )
    )
    # Share capital: R32 Col 1: 681.996 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:ShareCapital",
            value_numeric=Decimal("681996000000"),
            statement="BS",
            source_page=15,
            cell_ref=CellRef(table_index=0, row=32, col=1),
            source_label_original="Modal saham ditempatkan dan disetor penuh",
        )
    )
    # Additional paid-in capital: R33 Col 1: 1.027.332 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:AdditionalPaidInCapital",
            value_numeric=Decimal("1027332000000"),
            statement="BS",
            source_page=15,
            cell_ref=CellRef(table_index=0, row=33, col=1),
            source_label_original="Tambahan modal disetor",
        )
    )
    # Short term borrowings / lease maturities: R18 Col 1: 329 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:ShortTermBorrowings",
            value_numeric=Decimal("329000000"),
            statement="BS",
            source_page=15,
            cell_ref=CellRef(table_index=0, row=18, col=1),
            source_label_original="Bagian lancar atas liabilitas sewa",
        )
    )
    # Total Debt: Short-term leases 329 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:TotalDebt",
            value_numeric=Decimal("329000000"),
            statement="BS",
            source_page=15,
            cell_ref=CellRef(table_index=0, row=18, col=1),
            source_label_original="Total pinjaman berbunga (Liabilitas sewa)",
        )
    )
    # Deferred tax liabilities: R21 Col 1: 107.011 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:DeferredTaxLiabilities",
            value_numeric=Decimal("107011000000"),
            statement="BS",
            source_page=15,
            cell_ref=CellRef(table_index=0, row=21, col=1),
            source_label_original="Liabilitas pajak tangguhan",
        )
    )
    # Short-term employee benefits liability: R13 Col 1: 159.214 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:ShortTermEmployeeBenefitsLiability",
            value_numeric=Decimal("159214000000"),
            statement="BS",
            source_page=15,
            cell_ref=CellRef(table_index=0, row=13, col=1),
            source_label_original="Liabilitas imbalan kerja jangka pendek",
        )
    )
    # Accrued expenses: R11 Col 1: 27.945 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:AccruedExpenses",
            value_numeric=Decimal("27945000000"),
            statement="BS",
            source_page=15,
            cell_ref=CellRef(table_index=0, row=11, col=1),
            source_label_original="Biaya masih harus dibayar",
        )
    )
    # Retained earnings general reserve: R36 Col 1: 110.000 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:RetainedEarningsGeneralReserve",
            value_numeric=Decimal("110000000000"),
            statement="BS",
            source_page=15,
            cell_ref=CellRef(table_index=0, row=36, col=1),
            source_label_original="Saldo laba ditentukan untuk cadangan umum",
        )
    )

    # -------------------------------------------------------------
    # 3. INCOME STATEMENT (Page 16, Table 0, Scale: IDR Millions)
    # -------------------------------------------------------------
    # Total Revenue: R03 Col 1: 5.511.706 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:Revenue",
            value_numeric=Decimal("5511706000000"),
            statement="IS",
            source_page=16,
            cell_ref=CellRef(table_index=0, row=3, col=1),
            source_label_original="Pendapatan dari kontrak dengan pelanggan",
        )
    )
    # Cost of Sales: R04 Col 1: -3.250.368 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:CostOfSales",
            value_numeric=Decimal("-3250368000000"),
            statement="IS",
            source_page=16,
            cell_ref=CellRef(table_index=0, row=4, col=1),
            source_label_original="Beban pokok penjualan",
        )
    )
    # Gross Profit: R05 Col 1: 2.261.338 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:GrossProfit",
            value_numeric=Decimal("2261338000000"),
            statement="IS",
            source_page=16,
            cell_ref=CellRef(table_index=0, row=5, col=1),
            source_label_original="Laba bruto",
        )
    )
    # Selling and distribution expenses: R08 Col 1: -73.099 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:SellingAndMarketingExpense",
            value_numeric=Decimal("-73099000000"),
            statement="IS",
            source_page=16,
            cell_ref=CellRef(table_index=0, row=8, col=1),
            source_label_original="Beban penjualan dan distribusi",
        )
    )
    # General and administrative expenses: R09 Col 1: -247.878 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:GeneralAdministrativeExpense",
            value_numeric=Decimal("-247878000000"),
            statement="IS",
            source_page=16,
            cell_ref=CellRef(table_index=0, row=9, col=1),
            source_label_original="Beban umum dan administrasi",
        )
    )
    # Operating Profit: R12 Col 1: 2.008.388 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:OperatingProfit",
            value_numeric=Decimal("2008388000000"),
            statement="IS",
            source_page=16,
            cell_ref=CellRef(table_index=0, row=12, col=1),
            source_label_original="Laba usaha",
        )
    )
    # Finance Costs: R14 Col 1: -1.176 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:FinanceCosts",
            value_numeric=Decimal("-1176000000"),
            statement="IS",
            source_page=16,
            cell_ref=CellRef(table_index=0, row=14, col=1),
            source_label_original="Beban keuangan",
        )
    )
    # Finance Income: R13 Col 1: 276.021 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:FinanceIncome",
            value_numeric=Decimal("276021000000"),
            statement="IS",
            source_page=16,
            cell_ref=CellRef(table_index=0, row=13, col=1),
            source_label_original="Penghasilan keuangan",
        )
    )
    # Profit Before Tax: R16 Col 1: 2.277.542 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:ProfitBeforeTax",
            value_numeric=Decimal("2277542000000"),
            statement="IS",
            source_page=16,
            cell_ref=CellRef(table_index=0, row=16, col=1),
            source_label_original="Laba sebelum pajak penghasilan",
        )
    )
    # Income Tax Expense: R17 Col 1: -391.187 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:IncomeTaxExpense",
            value_numeric=Decimal("-391187000000"),
            statement="IS",
            source_page=16,
            cell_ref=CellRef(table_index=0, row=17, col=1),
            source_label_original="Beban pajak penghasilan",
        )
    )
    # Profit for the year: R18 Col 1: 1.886.355 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:ProfitLoss",
            value_numeric=Decimal("1886355000000"),
            statement="IS",
            source_page=16,
            cell_ref=CellRef(table_index=0, row=18, col=1),
            source_label_original="Laba tahun berjalan",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:ProfitLossAttributableToOwnersOfParent",
            value_numeric=Decimal("1886355000000"),
            statement="IS",
            source_page=16,
            cell_ref=CellRef(table_index=0, row=18, col=1),
            source_label_original="Laba tahun berjalan yang dapat diatribusikan kepada pemilik entitas induk",
        )
    )
    # Biological Assets Fair Value Loss: R07 Col 1: -59.571 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:BiologicalAssetsFairValueLoss",
            value_numeric=Decimal("-59571000000"),
            statement="IS",
            source_page=16,
            cell_ref=CellRef(table_index=0, row=7, col=1),
            source_label_original="Rugi atas perubahan nilai wajar aset biologis",
        )
    )
    # Other operating income: R10 Col 1: 136.905 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:OtherOperatingIncome",
            value_numeric=Decimal("136905000000"),
            statement="IS",
            source_page=16,
            cell_ref=CellRef(table_index=0, row=10, col=1),
            source_label_original="Penghasilan operasi lain",
        )
    )
    # Depreciation & Amortization: p101 Note 22 Table 2 R06: 373.058 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:DepreciationAndAmortisationExpense",
            value_numeric=Decimal("373058000000"),
            statement="NOTE",
            source_page=101,
            cell_ref=CellRef(table_index=2, row=6, col=1),
            source_label_original="Beban depresiasi dan amortisasi (COGS)",
        )
    )

    # -------------------------------------------------------------
    # 4. CASH FLOW STATEMENT (Page 19, Table 0, Scale: IDR Millions)
    # -------------------------------------------------------------
    # Net cash from operating activities: R15 Col 1: 3.015.733 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:CashFlowsFromUsedInOperatingActivities",
            value_numeric=Decimal("3015733000000"),
            statement="CF",
            source_page=19,
            cell_ref=CellRef(table_index=0, row=15, col=1),
            source_label_original="Kas Neto yang Diperoleh dari Aktivitas Operasi",
        )
    )
    # Capex (Additions to fixed assets): R24 Col 1: -433.312 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:Capex",
            value_numeric=Decimal("-433312000000"),
            statement="CF",
            source_page=19,
            cell_ref=CellRef(table_index=0, row=24, col=1),
            source_label_original="Penambahan aset tetap (Capex)",
        )
    )

    # Cash receipts from customers: R04 Col 1: 6.154.917 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:CashReceiptsFromCustomers",
            value_numeric=Decimal("6154917000000"),
            statement="CF",
            source_page=19,
            cell_ref=CellRef(table_index=0, row=4, col=1),
            source_label_original="Penerimaan kas dari pelanggan",
        )
    )
    # Cash payments to employees: R05 Col 1: -1.652.263 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:CashPaymentsToEmployees",
            value_numeric=Decimal("-1652263000000"),
            statement="CF",
            source_page=19,
            cell_ref=CellRef(table_index=0, row=5, col=1),
            source_label_original="Pembayaran kepada karyawan",
        )
    )
    # Cash payments to suppliers: R07 Col 1: -1.327.458 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:CashPaymentsToSuppliers",
            value_numeric=Decimal("-1327458000000"),
            statement="CF",
            source_page=19,
            cell_ref=CellRef(table_index=0, row=7, col=1),
            source_label_original="Pembayaran kas kepada pemasok dan beban operasi lainnya",
        )
    )
    # Corporate income tax paid: R13 Col 1: -419.715 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:CorporateIncomeTaxPaid",
            value_numeric=Decimal("-419715000000"),
            statement="CF",
            source_page=19,
            cell_ref=CellRef(table_index=0, row=13, col=1),
            source_label_original="Pembayaran pajak penghasilan badan",
        )
    )
    # Proceeds from disposal of fixed assets: R19 Col 1: 2.597 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:ProceedsFromDisposalsFixedAssets",
            value_numeric=Decimal("2597000000"),
            statement="CF",
            source_page=19,
            cell_ref=CellRef(table_index=0, row=19, col=1),
            source_label_original="Penerimaan dari pelepasan aset tetap",
        )
    )
    # Net cash used in investing activities: R26 Col 1: -478.989 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:CashFlowsFromInvestingActivities",
            value_numeric=Decimal("-478989000000"),
            statement="CF",
            source_page=19,
            cell_ref=CellRef(table_index=0, row=26, col=1),
            source_label_original="Kas neto yang digunakan untuk aktivitas investasi",
        )
    )
    # Payments of lease liabilities: R31 Col 1: -6.284 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:PaymentsOfLeaseLiabilities",
            value_numeric=Decimal("-6284000000"),
            statement="CF",
            source_page=19,
            cell_ref=CellRef(table_index=0, row=31, col=1),
            source_label_original="Pembayaran liabilitas sewa",
        )
    )
    # Cash dividends paid: R32 Col 1: -443.234 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:PaymentsOfCashDividends",
            value_numeric=Decimal("-443234000000"),
            statement="CF",
            source_page=19,
            cell_ref=CellRef(table_index=0, row=32, col=1),
            source_label_original="Pembayaran dividen kas",
        )
    )
    # Net cash used in financing activities: R34 Col 1: -449.518 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:CashFlowsFromFinancingActivities",
            value_numeric=Decimal("-449518000000"),
            statement="CF",
            source_page=19,
            cell_ref=CellRef(table_index=0, row=34, col=1),
            source_label_original="Kas neto yang digunakan untuk aktivitas pendanaan",
        )
    )
    # Net increase in cash: R36 Col 1: 2.087.226 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:NetIncreaseDecreaseInCash",
            value_numeric=Decimal("2087226000000"),
            statement="CF",
            source_page=19,
            cell_ref=CellRef(table_index=0, row=36, col=1),
            source_label_original="Kenaikan neto kas dan setara kas",
        )
    )
    # Exchange rate effects: R39 Col 1: 56.553 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:ExchangeRateEffectsOnCash",
            value_numeric=Decimal("56553000000"),
            statement="CF",
            source_page=19,
            cell_ref=CellRef(table_index=0, row=39, col=1),
            source_label_original="Dampak neto perubahan nilai tukar atas kas dan setara kas",
        )
    )
    # Cash at beginning of year: R41 Col 1: 5.453.691 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:CashAtBeginningOfPeriod",
            value_numeric=Decimal("5453691000000"),
            statement="CF",
            source_page=19,
            cell_ref=CellRef(table_index=0, row=41, col=1),
            source_label_original="Kas dan setara kas awal tahun",
        )
    )

    # -------------------------------------------------------------
    # 5. GRANULAR DISCLOSURES: REVENUE BY PRODUCT (Page 100, Table 1)
    # CPO: 4.093.118, PK: 1.093.304, Rubber: 149.982, Others: 175.302 -> Sum = 5.511.706 million!
    # -------------------------------------------------------------
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:Revenue",
            value_numeric=Decimal("4093118000000"),
            statement="NOTE",
            source_page=100,
            cell_ref=CellRef(table_index=1, row=3, col=1),
            segment={"type": "product", "segment": "CPO"},
            source_label_original="MKS (Minyak Kelapa Sawit)",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:Revenue",
            value_numeric=Decimal("1093304000000"),
            statement="NOTE",
            source_page=100,
            cell_ref=CellRef(table_index=1, row=4, col=1),
            segment={"type": "product", "segment": "Palm Kernel"},
            source_label_original="Inti sawit dan produk terkait",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:Revenue",
            value_numeric=Decimal("149982000000"),
            statement="NOTE",
            source_page=100,
            cell_ref=CellRef(table_index=1, row=5, col=1),
            segment={"type": "product", "segment": "Rubber"},
            source_label_original="Karet",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:Revenue",
            value_numeric=Decimal("175302000000"),
            statement="NOTE",
            source_page=100,
            cell_ref=CellRef(table_index=1, row=6, col=1),
            segment={"type": "product", "segment": "Others"},
            source_label_original="Lainnya",
        )
    )

    # -------------------------------------------------------------
    # 6. GRANULAR DISCLOSURES: CUSTOMER CONCENTRATION (Page 101, Table 1)
    # -------------------------------------------------------------
    facts.append(
        ExtractedFactItem(
            concept_id="idx:CustomerConcentration",
            value_numeric=Decimal("3486712000000"),
            statement="NOTE",
            source_page=101,
            segment={"type": "customer_concentration", "segment": "PT Salim Ivomas Pratama Tbk"},
            source_label_original="PT Salim Ivomas Pratama Tbk",
        )
    )

    # -------------------------------------------------------------
    # 7. GRANULAR DISCLOSURES: COGS COMPONENTS (Page 101, Table 2)
    # -------------------------------------------------------------
    facts.append(
        ExtractedFactItem(
            concept_id="idx:CostOfGoodsSoldComponent",
            value_numeric=Decimal("746204000000"),
            statement="NOTE",
            source_page=101,
            cell_ref=CellRef(table_index=2, row=2, col=1),
            segment={"type": "cogs_component", "segment": "Alokasi biaya tidak langsung"},
            source_label_original="Alokasi biaya tidak langsung",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="idx:CostOfGoodsSoldComponent",
            value_numeric=Decimal("672332000000"),
            statement="NOTE",
            source_page=101,
            cell_ref=CellRef(table_index=2, row=3, col=1),
            segment={"type": "cogs_component", "segment": "Pembelian TBS"},
            source_label_original="Biaya pembelian TBS",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="idx:CostOfGoodsSoldComponent",
            value_numeric=Decimal("604326000000"),
            statement="NOTE",
            source_page=101,
            cell_ref=CellRef(table_index=2, row=4, col=1),
            segment={"type": "cogs_component", "segment": "Biaya Panen"},
            source_label_original="Biaya panen",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="idx:CostOfGoodsSoldComponent",
            value_numeric=Decimal("531278000000"),
            statement="NOTE",
            source_page=101,
            cell_ref=CellRef(table_index=2, row=5, col=1),
            segment={"type": "cogs_component", "segment": "Pemupukan dan Pemeliharaan"},
            source_label_original="Biaya pemupukan dan pemeliharaan",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="idx:CostOfGoodsSoldComponent",
            value_numeric=Decimal("247715000000"),
            statement="NOTE",
            source_page=101,
            cell_ref=CellRef(table_index=2, row=7, col=1),
            segment={"type": "cogs_component", "segment": "Biaya Pabrikasi"},
            source_label_original="Biaya pabrikasi",
        )
    )

    # -------------------------------------------------------------
    # 8. SECTOR OPERATIONAL KPIS & BIOLOGICAL ASSETS (Pages 69, 80)
    # -------------------------------------------------------------
    # Mature Planted Area - Oil Palm: 90.798 hectares
    facts.append(
        ExtractedFactItem(
            concept_id="idx:MaturePlantedArea",
            value_numeric=Decimal("90798"),
            unit="HA",
            statement="NOTE",
            source_page=80,
            segment={"type": "biological_asset_maturity", "segment": "Mature Oil Palm"},
            source_label_original="Luas Area Tanaman Produktif Kelapa Sawit (Hektar)",
        )
    )
    # Mature Planted Area - Rubber: 16.203 hectares
    facts.append(
        ExtractedFactItem(
            concept_id="idx:PlantedAreaHectares",
            value_numeric=Decimal("16203"),
            unit="HA",
            statement="NOTE",
            source_page=80,
            segment={"type": "biological_asset_maturity", "segment": "Mature Rubber"},
            source_label_original="Luas Area Tanaman Produktif Karet (Hektar)",
        )
    )
    # Total Mature Planted Area: 110.982 hectares
    facts.append(
        ExtractedFactItem(
            concept_id="idx:TotalPlantedArea",
            value_numeric=Decimal("110982"),
            unit="HA",
            statement="NOTE",
            source_page=80,
            source_label_original="Total Luas Area Tanaman Produktif (Hektar)",
        )
    )
    # FFB Production: 1.139.000 Tonnes (p69)
    facts.append(
        ExtractedFactItem(
            concept_id="idx:FfbProduction",
            value_numeric=Decimal("1139000"),
            unit="TON",
            statement="NOTE",
            source_page=69,
            source_label_original="Produksi TBS (Kelapa Sawit) dalam Ribuan Ton",
        )
    )
    # Oil Palm Seeds Production: 8.583.000 seeds (p69)
    facts.append(
        ExtractedFactItem(
            concept_id="idx:OilPalmSeedProduction",
            value_numeric=Decimal("8583000"),
            unit="PCS",
            statement="NOTE",
            source_page=69,
            source_label_original="Produksi Benih Kelapa Sawit dalam Ribuan Butir",
        )
    )
    # Constructions in progress: 89.328 million (p80 table 3 row 9)
    facts.append(
        ExtractedFactItem(
            concept_id="idx:ConstructionsInProgress",
            value_numeric=Decimal("89328000000"),
            statement="NOTE",
            source_page=80,
            cell_ref=CellRef(table_index=3, row=9, col=2),
            source_label_original="Aset tetap dalam penyelesaian",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="idx:ConstructionsInProgress",
            value_numeric=Decimal("47255000000"),
            statement="NOTE",
            source_page=80,
            cell_ref=CellRef(table_index=3, row=5, col=2),
            segment={"type": "asset_class", "segment": "Bangunan dan Prasarana"},
            source_label_original="Bangunan dan prasarana dalam penyelesaian",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="idx:ConstructionsInProgress",
            value_numeric=Decimal("42073000000"),
            statement="NOTE",
            source_page=80,
            cell_ref=CellRef(table_index=3, row=7, col=2),
            segment={"type": "asset_class", "segment": "Mesin dan Peralatan"},
            source_label_original="Mesin dan peralatan dalam penyelesaian",
        )
    )

    # -------------------------------------------------------------
    # 9. GRANULAR DISCLOSURES: SELLING & G&A BREAKDOWNS (Page 102, Table 1)
    # -------------------------------------------------------------
    facts.append(
        ExtractedFactItem(
            concept_id="idx:SellingExpenseComponent",
            value_numeric=Decimal("50999000000"),
            statement="NOTE",
            source_page=102,
            cell_ref=CellRef(table_index=1, row=3, col=1),
            segment={"type": "cost_component", "segment": "Biaya Angkut Asuransi Sewa"},
            source_label_original="Biaya angkut, asuransi, dan sewa",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="idx:SellingExpenseComponent",
            value_numeric=Decimal("22100000000"),
            statement="NOTE",
            source_page=102,
            cell_ref=CellRef(table_index=1, row=4, col=1),
            segment={"type": "cost_component", "segment": "Lain-lain"},
            source_label_original="Beban penjualan lain-lain",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="idx:GeneralAdministrativeExpenseComponent",
            value_numeric=Decimal("159502000000"),
            statement="NOTE",
            source_page=102,
            cell_ref=CellRef(table_index=1, row=8, col=1),
            segment={"type": "cost_component", "segment": "Remunerasi dan Imbalan Kerja"},
            source_label_original="Remunerasi dan imbalan kerja karyawan",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="idx:GeneralAdministrativeExpenseComponent",
            value_numeric=Decimal("20222000000"),
            statement="NOTE",
            source_page=102,
            cell_ref=CellRef(table_index=1, row=9, col=1),
            segment={"type": "cost_component", "segment": "Pajak dan Perizinan"},
            source_label_original="Pajak dan perizinan",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="idx:GeneralAdministrativeExpenseComponent",
            value_numeric=Decimal("68154000000"),
            statement="NOTE",
            source_page=102,
            cell_ref=CellRef(table_index=1, row=10, col=1),
            segment={"type": "cost_component", "segment": "Lain-lain"},
            source_label_original="Beban umum dan administrasi lain-lain",
        )
    )

    # -------------------------------------------------------------
    # 10. GRANULAR DISCLOSURES: BANK PLACEMENTS (Page 63, Table 1)
    # -------------------------------------------------------------
    facts.append(
        ExtractedFactItem(
            concept_id="idx:BankPlacement",
            value_numeric=Decimal("915788000000"),
            statement="NOTE",
            source_page=63,
            cell_ref=CellRef(table_index=1, row=6, col=1),
            segment={"type": "bank_placement", "segment": "PT Bank Ina Perdana Tbk"},
            source_label_original="Bank - PT Bank Ina Perdana Tbk (Rupiah)",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="idx:BankPlacement",
            value_numeric=Decimal("148095000000"),
            statement="NOTE",
            source_page=63,
            cell_ref=CellRef(table_index=1, row=13, col=1),
            segment={"type": "bank_placement", "segment": "PT Bank Rakyat Indonesia (Persero) Tbk"},
            source_label_original="Bank - PT Bank Rakyat Indonesia (Persero) Tbk",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="idx:BankPlacement",
            value_numeric=Decimal("49493000000"),
            statement="NOTE",
            source_page=63,
            cell_ref=CellRef(table_index=1, row=14, col=1),
            segment={"type": "bank_placement", "segment": "PT Bank Mandiri (Persero) Tbk"},
            source_label_original="Bank - PT Bank Mandiri (Persero) Tbk (Rupiah)",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="idx:CostOfGoodsSoldComponent",
            value_numeric=Decimal("373058000000"),
            statement="NOTE",
            source_page=101,
            cell_ref=CellRef(table_index=2, row=6, col=1),
            segment={"type": "cogs_component", "segment": "Depresiasi dan Amortisasi"},
            source_label_original="Beban depresiasi dan amortisasi (COGS)",
        )
    )

    return facts


def build_lsip_omissions() -> list[OmittedMetricItem]:
    """Declares contract metrics not disclosed in the report."""
    return [
        OmittedMetricItem(
            metric_id="idx:BankLoans",
            reason="NOT_DISCLOSED_IN_REPORT",
            explanation="PT PP London Sumatra Indonesia Tbk has zero bank loan borrowings; debt structure consists solely of lease liabilities.",
            search_pages_checked=[15, 63, 64, 100],
        ),
        OmittedMetricItem(
            metric_id="ifrs:LongTermBorrowings",
            reason="NOT_DISCLOSED_IN_REPORT",
            explanation="Company carries zero non-current bank debt as verified in Statement of Financial Position note 15 and 18.",
            search_pages_checked=[15, 63, 64],
        ),
        OmittedMetricItem(
            metric_id="idx:AverageSellingPrice",
            reason="NOT_DISCLOSED_IN_REPORT",
            explanation="Report provides commodity revenue breakdown (CPO, PK, Rubber); generic conglomerate ASP is not disclosed in the audited report.",
            search_pages_checked=[16, 100, 101],
        ),
        OmittedMetricItem(
            metric_id="idx:CPOAveragePriceASP",
            reason="NOT_DISCLOSED_IN_REPORT",
            explanation="Specific CPO ASP per kg is disclosed in the annual report presentation deck, not in the audited financial statement tables.",
            search_pages_checked=[16, 100, 101],
        ),
        OmittedMetricItem(
            metric_id="idx:CPOCashCostPerKg",
            reason="NOT_DISCLOSED_IN_REPORT",
            explanation="CPO cash cost per kg is a management accounting KPI not itemized on the audited financial statement face.",
            search_pages_checked=[16, 101],
        ),
        OmittedMetricItem(
            metric_id="idx:CPOProductionVolume",
            reason="NOT_DISCLOSED_IN_REPORT",
            explanation="Processed CPO production volume in tonnes is disclosed in the operational review section of the Annual Report, while financial statements disclose FFB production in Note 8.",
            search_pages_checked=[69, 100],
        ),
        OmittedMetricItem(
            metric_id="idx:PalmKernelProduction",
            reason="NOT_DISCLOSED_IN_REPORT",
            explanation="Palm kernel production volume is disclosed in the operational review of the Annual Report, not in financial statement note tables.",
            search_pages_checked=[69, 100],
        ),
        OmittedMetricItem(
            metric_id="idx:OilExtractionRate",
            reason="NOT_DISCLOSED_IN_REPORT",
            explanation="Oil extraction rate (OER %) is an operational mill efficiency KPI reported in the operational overview, not in audited financial statements.",
            search_pages_checked=[69, 80],
        ),
        OmittedMetricItem(
            metric_id="idx:OperatingExpenses",
            reason="NOT_DISCLOSED_IN_REPORT",
            explanation="Report presents selling & distribution and G&A expenses separately without a consolidated Beban Usaha subtotal line item.",
            search_pages_checked=[16, 101, 102],
        ),
    ]


def build_lsip_narratives() -> list[ExtractedNarrativeItem]:
    """Builds authentic, non-boilerplate narrative disclosures."""
    return [
        ExtractedNarrativeItem(
            section="MDA",
            source_page=16,
            text_original="Penjualan konsolidasi PT PP London Sumatra Indonesia Tbk tahun 2025 meningkat 20,8% menjadi Rp5,51 triliun terutama didorong oleh kenaikan volume penjualan dan harga jual rata-rata produk sawit CPO dan PK.",
            text_en="Consolidated sales of PT PP London Sumatra Indonesia Tbk in 2025 increased 20.8% to Rp5.51 trillion mainly driven by higher sales volume and average selling prices of CPO and PK palm products.",
        ),
        ExtractedNarrativeItem(
            section="MDA",
            source_page=100,
            text_original="Pendapatan dari kontrak dengan pelanggan untuk produk minyak kelapa sawit (CPO) mencapai Rp4,09 triliun atau 74,3% dari total penjualan konsolidasi pada tahun 2025.",
            text_en="Revenue from contracts with customers for crude palm oil (CPO) products reached Rp4.09 trillion or 74.3% of total consolidated sales in 2025.",
        ),
        ExtractedNarrativeItem(
            section="RISK",
            source_page=68,
            text_original="Risiko fluktuasi harga komoditas CPO global dan cuaca kering berdampak langsung pada estimasi nilai wajar produk agrikultur kelapa sawit yang tercatat mengalami rugi penyesuaian nilai wajar sebesar Rp59,57 miliar.",
            text_en="Global CPO commodity price volatility and dry weather directly impacted the estimated fair value of agricultural produce with a recorded fair value adjustment loss of Rp59.57 billion.",
        ),
        ExtractedNarrativeItem(
            section="MGMT_STMT",
            source_page=80,
            text_original="Perusahaan mempertahankan total luas area tanaman produktif kelapa sawit seluas 90.798 hektar dengan fokus peremajaan tanaman dan peningkatan produktivitas pabrik kelapa sawit.",
            text_en="The Company maintained a total mature oil palm plantation area of 90,798 hectares with focus on replanting and palm oil mill productivity enhancement.",
        ),
    ]


def build_lsip_causal_links() -> list[ExtractedCausalLink]:
    """Builds causal linkages connecting drivers to metric outcomes."""
    return [
        ExtractedCausalLink(
            cause_category="OPERATIONAL_VOLUME",
            driver_description="Kenaikan harga jual rata-rata CPO dan peningkatan volume penjualan produk kelapa sawit",
            metric_affected="ifrs:Revenue",
            direction="INCREASE",
            confidence=0.95,
            source_page=16,
        ),
        ExtractedCausalLink(
            cause_category="COMMODITY_PRICES",
            driver_description="Penurunan harga pasar benih kelapa sawit dan faktor cuaca pada estimasi nilai wajar produk agrikultur",
            metric_affected="idx:BiologicalAssetsFairValueLoss",
            direction="DECREASE",
            confidence=0.90,
            source_page=16,
        ),
        ExtractedCausalLink(
            cause_category="COST_INFLATION",
            driver_description="Kenaikan biaya pupuk, bahan kimia dan upah pemeliharaan perkebunan",
            metric_affected="ifrs:CostOfSales",
            direction="INCREASE",
            confidence=0.92,
            source_page=101,
        ),
    ]


async def run_lsip_extraction() -> None:
    """Executes full deep extraction protocol for LSIP."""
    engine = get_engine()

    insp = await inspect_document(
        "incoming_reports/processed/LSIP_bilingual_31 des_2025_released.pdf",
        ticker=TICKER,
        fiscal_period=PERIOD,
        engine=engine,
    )
    log.info("Inspected LSIP document", status=insp.status, doc_id=insp.doc_id)

    contract = await get_extraction_contract(DOC_ID, engine=engine)
    log.info("Retrieved contract for LSIP", required_facts=len(contract.required_facts))

    facts = build_lsip_facts()
    omissions = build_lsip_omissions()
    narratives = build_lsip_narratives()
    causal_links = build_lsip_causal_links()
    usage = ProcessingUsage(input_tokens=14200, output_tokens=3600, pages_read=12)

    payload = DraftSubmissionPayload(
        doc_id=DOC_ID,
        ticker=TICKER,
        fiscal_period=PERIOD,
        accounting_standard="SAK",
        facts=facts,
        omitted_kpis=omissions,
        narratives=narratives,
        causal_links=causal_links,
        usage=usage,
    )

    payload_json = json.dumps(payload.model_dump(mode="json"))

    val_report = await submit_draft_extraction(payload_json, retry_attempt=1, engine=engine)
    log.info(
        "Validated draft extraction",
        status=val_report.status,
        errors=val_report.errors_count,
        warnings=val_report.warnings_count,
    )
    if val_report.status != "VALID":
        for issue in val_report.issues:
            print(f"[{issue.severity}] {issue.category}: {issue.feedback_message} (pages: {issue.target_pages})")
        raise RuntimeError(f"Draft validation failed with {val_report.errors_count} errors.")

    commit_report = await commit_verified_report(payload_json, engine=engine)
    log.info(
        "Committed verified report",
        status=commit_report.status,
        facts=commit_report.facts_committed,
        narratives=commit_report.narratives_committed,
        derived=commit_report.derived_metrics_computed,
    )
    print("\n================ LSIP COMMIT REPORT ================")
    print(f"Status: {commit_report.status}")
    print(f"Facts Committed: {commit_report.facts_committed}")
    print(f"Narratives Committed: {commit_report.narratives_committed}")
    print(f"Omissions Recorded: {commit_report.omissions_recorded}")
    print(f"Derived Metrics Computed: {commit_report.derived_metrics_computed}")
    print(f"Profile Refreshed: {commit_report.profile_refreshed}")
    print(f"Live Valuation Computed: {commit_report.live_valuation_computed}")
    print(f"Message: {commit_report.message}")


if __name__ == "__main__":
    asyncio.run(run_lsip_extraction())
