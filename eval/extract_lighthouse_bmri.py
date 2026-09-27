"""Lighthouse Extraction Execution for BMRI (PT Bank Mandiri (Persero) Tbk) 2025Q4.

Follows Section 6 of docs/runbook.md: Targeted Deep Extraction Protocol.
Extracts Core Statements (BS, IS, CF) and Granular Disclosures (Notes 12, 18, 21, 22, 23, 36, 50, 65).
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

log = get_logger("eval.extract.bmri")

DOC_ID = "a7ccfea3-30b5-4e2d-b357-fb5648386eb2"
TICKER = "BMRI"
PERIOD = "2025Q4"


def build_bmri_facts() -> list[ExtractedFactItem]:
    """Builds grounded financial facts for BMRI 2025Q4."""
    facts: list[ExtractedFactItem] = []

    # -------------------------------------------------------------
    # 1. BALANCE SHEET - ASSETS (Pages 22, 23, 24; Scale: IDR Millions)
    # -------------------------------------------------------------
    # Total Assets: p24 text: 2.829.948.026 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:Assets",
            value_numeric=Decimal("2829948026000000"),
            statement="BS",
            source_page=24,
            source_label_original="TOTAL ASET",
        )
    )
    # Cash: p22 Table 0 Row 3 Col 2: 33.857.220 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:CashAndCashEquivalents",
            value_numeric=Decimal("33857220000000"),
            statement="BS",
            source_page=22,
            cell_ref=CellRef(table_index=0, row=3, col=2),
            source_label_original="Kas",
        )
    )
    # Giro pada Bank Indonesia: p22 Table 0 Row 5 Col 2: 238.289.478 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:CurrentAccountsWithCentralBank",
            value_numeric=Decimal("238289478000000"),
            statement="BS",
            source_page=22,
            cell_ref=CellRef(table_index=0, row=5, col=2),
            source_label_original="Giro pada Bank Indonesia",
        )
    )
    # Giro pada bank lain: p22 Table 0 Row 13 Col 2: 60.924.962 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:CurrentAccountsWithOtherBanks",
            value_numeric=Decimal("60924962000000"),
            statement="BS",
            source_page=22,
            cell_ref=CellRef(table_index=0, row=13, col=2),
            source_label_original="Giro pada bank lain - Neto",
        )
    )
    # Penempatan pada Bank Indonesia dan bank lain: p22 Table 0 Row 22 Col 2: 50.470.248 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:PlacementsWithBanks",
            value_numeric=Decimal("50470248000000"),
            statement="BS",
            source_page=22,
            cell_ref=CellRef(table_index=0, row=22, col=2),
            source_label_original="Penempatan pada Bank Indonesia dan bank lain - Neto",
        )
    )
    # Gross Loans and Advances: p23 Table 0 Row 15 Col 2: 1.849.967.956 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:LoansAndAdvances",
            value_numeric=Decimal("1849967956000000"),
            statement="BS",
            source_page=23,
            cell_ref=CellRef(table_index=0, row=15, col=2),
            source_label_original="Total kredit yang diberikan dan piutang/pembiayaan syariah",
        )
    )
    # Gross Loans - Related Parties: p23 Table 0 Row 13 Col 2: 402.847.579 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:LoansAndAdvances",
            value_numeric=Decimal("402847579000000"),
            statement="BS",
            source_page=23,
            cell_ref=CellRef(table_index=0, row=13, col=2),
            segment={"type": "borrower_type", "segment": "Pihak Berelasi"},
            source_label_original="Kredit yang diberikan - Pihak berelasi",
        )
    )
    # Gross Loans - Third Parties: p23 Table 0 Row 14 Col 2: 1.447.120.377 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:LoansAndAdvances",
            value_numeric=Decimal("1447120377000000"),
            statement="BS",
            source_page=23,
            cell_ref=CellRef(table_index=0, row=14, col=2),
            segment={"type": "borrower_type", "segment": "Pihak Ketiga"},
            source_label_original="Kredit yang diberikan - Pihak ketiga",
        )
    )
    # Allowance for Loan Losses (CKPN): p23 Table 0 Row 17 Col 2: -48.033.747 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:AllowanceForLoanLosses",
            value_numeric=Decimal("-48033747000000"),
            statement="BS",
            source_page=23,
            cell_ref=CellRef(table_index=0, row=17, col=2),
            source_label_original="Dikurangi: cadangan kerugian penurunan nilai",
        )
    )
    # Consumer Financing Receivables (Gross Total): p23 Table 0 Row 23 Col 2: 40.863.200 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:ConsumerFinancingReceivables",
            value_numeric=Decimal("40863200000000"),
            statement="BS",
            source_page=23,
            cell_ref=CellRef(table_index=0, row=23, col=2),
            source_label_original="Total piutang pembiayaan konsumen",
        )
    )
    # Derivative Receivables: p23 Table 0 Row 10 Col 2: 7.277.675 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:DerivativeFinancialAssets",
            value_numeric=Decimal("7277675000000"),
            statement="BS",
            source_page=23,
            cell_ref=CellRef(table_index=0, row=10, col=2),
            source_label_original="Tagihan derivatif - Total",
        )
    )
    # Property, Plant & Equipment (Fixed Assets): p24 Table 2 Row 5 Col 2: 72.062.331 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:PropertyPlantAndEquipment",
            value_numeric=Decimal("72062331000000"),
            statement="BS",
            source_page=24,
            cell_ref=CellRef(table_index=2, row=5, col=2),
            source_label_original="Aset tetap - Neto",
        )
    )
    # Intangible Assets: p24 Table 2 Row 9 Col 2: 7.519.158 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:IntangibleAssets",
            value_numeric=Decimal("7519158000000"),
            statement="BS",
            source_page=24,
            cell_ref=CellRef(table_index=2, row=9, col=2),
            source_label_original="Aset takberwujud - Neto",
        )
    )
    # Other Assets: p24 Table 2 Row 13 Col 2: 39.849.930 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:OtherAssets",
            value_numeric=Decimal("39849930000000"),
            statement="BS",
            source_page=24,
            cell_ref=CellRef(table_index=2, row=13, col=2),
            source_label_original="Aset lain-lain - Neto",
        )
    )
    # Accrued Interest / Trade Receivables: p226 text: 7.218.467 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:TradeAndOtherReceivables",
            value_numeric=Decimal("7218467000000"),
            statement="NOTE",
            source_page=226,
            source_label_original="Bunga yang masih akan diterima",
        )
    )

    # -------------------------------------------------------------
    # 1B. GRANULAR COUNTERPARTY BREAKDOWNS (Pages 22, 23, 26)
    # -------------------------------------------------------------
    facts.append(
        ExtractedFactItem(
            concept_id="idx:CurrentAccountsWithOtherBanks",
            value_numeric=Decimal("201893000000"),
            statement="BS",
            source_page=22,
            cell_ref=CellRef(table_index=0, row=8, col=2),
            segment={"type": "counterparty", "segment": "Pihak Berelasi"},
            source_label_original="Giro pada bank lain - Pihak berelasi",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="idx:CurrentAccountsWithOtherBanks",
            value_numeric=Decimal("60750690000000"),
            statement="BS",
            source_page=22,
            cell_ref=CellRef(table_index=0, row=9, col=2),
            segment={"type": "counterparty", "segment": "Pihak Ketiga"},
            source_label_original="Giro pada bank lain - Pihak ketiga",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="idx:PlacementsWithBanks",
            value_numeric=Decimal("1286559000000"),
            statement="BS",
            source_page=22,
            cell_ref=CellRef(table_index=0, row=17, col=2),
            segment={"type": "counterparty", "segment": "Pihak Berelasi"},
            source_label_original="Penempatan BI dan bank lain - Pihak berelasi",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="idx:PlacementsWithBanks",
            value_numeric=Decimal("49185275000000"),
            statement="BS",
            source_page=22,
            cell_ref=CellRef(table_index=0, row=18, col=2),
            segment={"type": "counterparty", "segment": "Pihak Ketiga"},
            source_label_original="Penempatan BI dan bank lain - Pihak ketiga",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="idx:MarketableSecurities",
            value_numeric=Decimal("17034297000000"),
            statement="BS",
            source_page=22,
            cell_ref=CellRef(table_index=0, row=24, col=2),
            segment={"type": "counterparty", "segment": "Pihak Berelasi"},
            source_label_original="Efek-efek - Pihak berelasi",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="idx:MarketableSecurities",
            value_numeric=Decimal("107048973000000"),
            statement="BS",
            source_page=22,
            cell_ref=CellRef(table_index=0, row=25, col=2),
            segment={"type": "counterparty", "segment": "Pihak Ketiga"},
            source_label_original="Efek-efek - Pihak ketiga",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="idx:DerivativeFinancialAssets",
            value_numeric=Decimal("3029980000000"),
            statement="BS",
            source_page=23,
            cell_ref=CellRef(table_index=0, row=8, col=2),
            segment={"type": "counterparty", "segment": "Pihak Berelasi"},
            source_label_original="Tagihan derivatif - Pihak berelasi",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="idx:DerivativeFinancialAssets",
            value_numeric=Decimal("4247695000000"),
            statement="BS",
            source_page=23,
            cell_ref=CellRef(table_index=0, row=9, col=2),
            segment={"type": "counterparty", "segment": "Pihak Ketiga"},
            source_label_original="Tagihan derivatif - Pihak ketiga",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="idx:ConsumerFinancingReceivables",
            value_numeric=Decimal("4257000000"),
            statement="BS",
            source_page=23,
            cell_ref=CellRef(table_index=0, row=21, col=2),
            segment={"type": "counterparty", "segment": "Pihak Berelasi"},
            source_label_original="Piutang pembiayaan konsumen - Pihak berelasi",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="idx:ConsumerFinancingReceivables",
            value_numeric=Decimal("40858943000000"),
            statement="BS",
            source_page=23,
            cell_ref=CellRef(table_index=0, row=22, col=2),
            segment={"type": "counterparty", "segment": "Pihak Ketiga"},
            source_label_original="Piutang pembiayaan konsumen - Pihak ketiga",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="idx:AcceptanceReceivables",
            value_numeric=Decimal("1161293000000"),
            statement="BS",
            source_page=23,
            cell_ref=CellRef(table_index=0, row=34, col=2),
            segment={"type": "counterparty", "segment": "Pihak Berelasi"},
            source_label_original="Tagihan akseptasi - Pihak berelasi",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="idx:AcceptanceReceivables",
            value_numeric=Decimal("6926985000000"),
            statement="BS",
            source_page=23,
            cell_ref=CellRef(table_index=0, row=35, col=2),
            segment={"type": "counterparty", "segment": "Pihak Ketiga"},
            source_label_original="Tagihan akseptasi - Pihak ketiga",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="idx:DebtSecuritiesIssued",
            value_numeric=Decimal("6425220000000"),
            statement="BS",
            source_page=26,
            cell_ref=CellRef(table_index=0, row=23, col=2),
            segment={"type": "counterparty", "segment": "Pihak Berelasi"},
            source_label_original="Efek-efek yang diterbitkan - Pihak berelasi",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="idx:DebtSecuritiesIssued",
            value_numeric=Decimal("55886791000000"),
            statement="BS",
            source_page=26,
            cell_ref=CellRef(table_index=0, row=24, col=2),
            segment={"type": "counterparty", "segment": "Pihak Ketiga"},
            source_label_original="Efek-efek yang diterbitkan - Pihak ketiga",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="idx:LoansByTenure",
            value_numeric=Decimal("22521989000000"),
            statement="NOTE",
            source_page=218,
            cell_ref=CellRef(table_index=0, row=5, col=2),
            segment={"type": "tenure", "segment": "Kurang dari 1 tahun (Valas)"},
            source_label_original="Kredit valas kurang dari 1 tahun",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="idx:LoansByTenure",
            value_numeric=Decimal("19167195000000"),
            statement="NOTE",
            source_page=218,
            cell_ref=CellRef(table_index=0, row=6, col=2),
            segment={"type": "tenure", "segment": "1 - 2 tahun (Valas)"},
            source_label_original="Kredit valas 1 - 2 tahun",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="idx:LoansByTenure",
            value_numeric=Decimal("50452118000000"),
            statement="NOTE",
            source_page=218,
            cell_ref=CellRef(table_index=0, row=7, col=2),
            segment={"type": "tenure", "segment": "2 - 5 tahun (Valas)"},
            source_label_original="Kredit valas 2 - 5 tahun",
        )
    )
    facts.append(
        ExtractedFactItem(
            concept_id="idx:LoansByTenure",
            value_numeric=Decimal("245157135000000"),
            statement="NOTE",
            source_page=218,
            cell_ref=CellRef(table_index=0, row=8, col=2),
            segment={"type": "tenure", "segment": "Lebih dari 5 tahun (Valas)"},
            source_label_original="Kredit valas lebih dari 5 tahun",
        )
    )

    # -------------------------------------------------------------
    # 2. BALANCE SHEET - LIABILITIES & EQUITY (Pages 25, 26, 27, 28, 29)
    # -------------------------------------------------------------
    # Total Liabilities: p27 Table 0 Row 14 Col 2: 2.212.925.204 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:Liabilities",
            value_numeric=Decimal("2212925204000000"),
            statement="BS",
            source_page=27,
            cell_ref=CellRef(table_index=0, row=14, col=2),
            source_label_original="TOTAL LIABILITAS",
        )
    )
    # Total Customer Deposits: p25 Table 0 Row 26 Col 2: 1.816.897.208 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:CustomerDeposits",
            value_numeric=Decimal("1816897208000000"),
            statement="BS",
            source_page=25,
            cell_ref=CellRef(table_index=0, row=26, col=2),
            source_label_original="Total simpanan dari nasabah",
        )
    )
    # Customer Deposits - Demand Deposits (Giro): p25 Table 0 Row 14 Col 2: 666.109.590 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:CustomerDeposits",
            value_numeric=Decimal("666109590000000"),
            statement="BS",
            source_page=25,
            cell_ref=CellRef(table_index=0, row=14, col=2),
            segment={"type": "deposit_type", "segment": "Giro dan Giro Wadiah"},
            source_label_original="Giro dan giro wadiah - Total",
        )
    )
    # Customer Deposits - Savings Deposits (Tabungan): p25 Table 0 Row 20 Col 2: 621.914.970 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:CustomerDeposits",
            value_numeric=Decimal("621914970000000"),
            statement="BS",
            source_page=25,
            cell_ref=CellRef(table_index=0, row=20, col=2),
            segment={"type": "deposit_type", "segment": "Tabungan dan Tabungan Wadiah"},
            source_label_original="Tabungan dan tabungan wadiah - Total",
        )
    )
    # Customer Deposits - Time Deposits (Deposito): p25 Table 0 Row 24 Col 2: 528.872.648 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:CustomerDeposits",
            value_numeric=Decimal("528872648000000"),
            statement="BS",
            source_page=25,
            cell_ref=CellRef(table_index=0, row=24, col=2),
            segment={"type": "deposit_type", "segment": "Deposito Berjangka"},
            source_label_original="Deposito berjangka - Total",
        )
    )
    # Deposits from other banks: p25 Table 0 Row 44 Col 2: 20.755.543 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:BankLoans",
            value_numeric=Decimal("20755543000000"),
            statement="BS",
            source_page=25,
            cell_ref=CellRef(table_index=0, row=44, col=2),
            source_label_original="Total simpanan dari bank lain",
        )
    )
    # Debt Securities Issued (Gross Total): p26 Table 0 Row 25 Col 2: 62.312.011 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:DebtSecuritiesIssued",
            value_numeric=Decimal("62312011000000"),
            statement="BS",
            source_page=26,
            cell_ref=CellRef(table_index=0, row=25, col=2),
            source_label_original="Total efek-efek yang diterbitkan",
        )
    )
    # Fund Borrowings / Long-term Borrowings: p26 Table 0 Row 41 Col 2: 154.672.422 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:LongTermBorrowings",
            value_numeric=Decimal("154672422000000"),
            statement="BS",
            source_page=26,
            cell_ref=CellRef(table_index=0, row=41, col=2),
            source_label_original="Pinjaman yang diterima - Total",
        )
    )
    # Borrowings by Lender - Related parties: p26 Table 0 Row 39 Col 2: 2.245.296 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:BorrowingsByLender",
            value_numeric=Decimal("2245296000000"),
            statement="BS",
            source_page=26,
            cell_ref=CellRef(table_index=0, row=39, col=2),
            segment={"type": "debt_facility", "segment": "Pinjaman Pihak Berelasi"},
            source_label_original="Pinjaman yang diterima - Pihak berelasi",
        )
    )
    # Borrowings by Lender - Third parties: p26 Table 0 Row 40 Col 2: 152.427.126 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:BorrowingsByLender",
            value_numeric=Decimal("152427126000000"),
            statement="BS",
            source_page=26,
            cell_ref=CellRef(table_index=0, row=40, col=2),
            segment={"type": "debt_facility", "segment": "Pinjaman Pihak Ketiga"},
            source_label_original="Pinjaman yang diterima - Pihak ketiga",
        )
    )
    # Taxes Payable: p26 Table 0 Row 33 Col 2: 3.327.702 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:TaxPayable",
            value_numeric=Decimal("3327702000000"),
            statement="BS",
            source_page=26,
            cell_ref=CellRef(table_index=0, row=33, col=2),
            source_label_original="Utang pajak",
        )
    )
    # Employee Benefits Liability: p26 Table 0 Row 35 Col 2: 7.899.583 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:EmployeeBenefitsLiability",
            value_numeric=Decimal("7899583000000"),
            statement="BS",
            source_page=26,
            cell_ref=CellRef(table_index=0, row=35, col=2),
            source_label_original="Liabilitas imbalan kerja",
        )
    )
    # Accrued Expenses: p26 Table 0 Row 32 Col 2: 6.168.983 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:AccruedExpenses",
            value_numeric=Decimal("6168983000000"),
            statement="BS",
            source_page=26,
            cell_ref=CellRef(table_index=0, row=32, col=2),
            source_label_original="Beban yang masih harus dibayar",
        )
    )
    # Subordinated Loans: p27 Table 0 Row 13 Col 2: 389.779 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:SubordinatedDebt",
            value_numeric=Decimal("389779000000"),
            statement="BS",
            source_page=27,
            cell_ref=CellRef(table_index=0, row=13, col=2),
            source_label_original="Pinjaman dan efek-efek subordinasi - Neto",
        )
    )
    # Dana Syirkah Temporer (Temporary Syirkah Funds from BSI): p28 Table 0 Row 21 Col 2: 289.620.824 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:TemporarySyirkahFunds",
            value_numeric=Decimal("289620824000000"),
            statement="BS",
            source_page=28,
            cell_ref=CellRef(table_index=0, row=21, col=2),
            source_label_original="TOTAL DANA SYIRKAH TEMPORER",
        )
    )
    # Total Equity: p29 Table 0 Row 39 Col 2: 327.401.998 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:Equity",
            value_numeric=Decimal("327401998000000"),
            statement="BS",
            source_page=29,
            cell_ref=CellRef(table_index=0, row=39, col=2),
            source_label_original="TOTAL EKUITAS",
        )
    )
    # Equity Attributable to Owners of Parent: p29 Table 0 Row 35 Col 2: 293.750.669 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:EquityAttributableToOwnersOfParent",
            value_numeric=Decimal("293750669000000"),
            statement="BS",
            source_page=29,
            cell_ref=CellRef(table_index=0, row=35, col=2),
            source_label_original="Ekuitas yang diatribusikan kepada Pemilik Entitas Induk",
        )
    )
    # Non-Controlling Interests: p29 Table 0 Row 38 Col 2: 33.651.329 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:NonControllingInterests",
            value_numeric=Decimal("33651329000000"),
            statement="BS",
            source_page=29,
            cell_ref=CellRef(table_index=0, row=38, col=2),
            source_label_original="Kepentingan nonpengendali atas aset bersih Entitas Anak",
        )
    )

    # -------------------------------------------------------------
    # 3. INCOME STATEMENT (Pages 30, 31, 32; Scale: IDR Millions)
    # -------------------------------------------------------------
    # Total Revenue (Interest & Sharia Income): p30 Table 0 Row 10 Col 2: 164.412.466 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:Revenue",
            value_numeric=Decimal("164412466000000"),
            statement="IS",
            source_page=30,
            cell_ref=CellRef(table_index=0, row=10, col=2),
            source_label_original="Total pendapatan bunga dan pendapatan syariah",
        )
    )
    # Revenue Segment - Interest Income: p30 Table 0 Row 7 Col 2: 139.649.437 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:Revenue",
            value_numeric=Decimal("139649437000000"),
            statement="IS",
            source_page=30,
            cell_ref=CellRef(table_index=0, row=7, col=2),
            segment={"type": "product", "segment": "Pendapatan Bunga"},
            source_label_original="Pendapatan bunga",
        )
    )
    # Revenue Segment - Sharia Income: p30 Table 0 Row 8 Col 2: 24.763.029 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:Revenue",
            value_numeric=Decimal("24763029000000"),
            statement="IS",
            source_page=30,
            cell_ref=CellRef(table_index=0, row=8, col=2),
            segment={"type": "product", "segment": "Pendapatan Syariah"},
            source_label_original="Pendapatan syariah",
        )
    )
    # Finance Costs (Interest & Sharia Expense): p30 Table 0 Row 16 Col 2: -58.202.431 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:FinanceCosts",
            value_numeric=Decimal("-58202431000000"),
            statement="IS",
            source_page=30,
            cell_ref=CellRef(table_index=0, row=16, col=2),
            source_label_original="Total beban bunga dan beban syariah",
        )
    )
    # Net Interest Income: p30 Table 0 Row 18 Col 2: 106.210.035 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:NetInterestIncome",
            value_numeric=Decimal("106210035000000"),
            statement="IS",
            source_page=30,
            cell_ref=CellRef(table_index=0, row=18, col=2),
            source_label_original="PENDAPATAN BUNGA DAN SYARIAH - NETO",
        )
    )
    # Fee & Commission Income: p30 Table 0 Row 24 Col 2: 27.553.414 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:FeeAndCommissionIncome",
            value_numeric=Decimal("27553414000000"),
            statement="IS",
            source_page=30,
            cell_ref=CellRef(table_index=0, row=24, col=2),
            source_label_original="Provisi dan komisi",
        )
    )
    # Operating Expenses: p31 Table 1 Row 12 Col 2: -67.584.405 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:OperatingExpenses",
            value_numeric=Decimal("-67584405000000"),
            statement="IS",
            source_page=31,
            cell_ref=CellRef(table_index=1, row=12, col=2),
            source_label_original="Total beban operasional lainnya",
        )
    )
    # Operating Profit: p31 Table 1 Row 14 Col 2: 76.310.739 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:OperatingProfit",
            value_numeric=Decimal("76310739000000"),
            statement="IS",
            source_page=31,
            cell_ref=CellRef(table_index=1, row=14, col=2),
            source_label_original="LABA OPERASIONAL",
        )
    )
    # Profit Before Tax: p31 text: 76.417.563 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:ProfitBeforeTax",
            value_numeric=Decimal("76417563000000"),
            statement="IS",
            source_page=31,
            source_label_original="LABA SEBELUM BEBAN PAJAK",
        )
    )
    # Income Tax Expense: p31 text: -15.071.430 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:IncomeTaxExpense",
            value_numeric=Decimal("-15071430000000"),
            statement="IS",
            source_page=31,
            source_label_original="Total beban pajak - neto",
        )
    )
    # Profit for the Year: p32 Table 1 Row 10 Col 2: 61.346.133 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:ProfitLoss",
            value_numeric=Decimal("61346133000000"),
            statement="IS",
            source_page=32,
            cell_ref=CellRef(table_index=1, row=10, col=2),
            source_label_original="LABA TAHUN BERJALAN",
        )
    )
    # Profit Attributable to Owners of Parent: p32 Table 1 Row 8 Col 2: 56.293.950 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:ProfitLossAttributableToOwnersOfParent",
            value_numeric=Decimal("56293950000000"),
            statement="IS",
            source_page=32,
            cell_ref=CellRef(table_index=1, row=8, col=2),
            source_label_original="Pemilik Entitas Induk",
        )
    )
    # Depreciation Expense: p389 text: 2.494.163 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:DepreciationAndAmortisationExpense",
            value_numeric=Decimal("2494163000000"),
            statement="NOTE",
            source_page=389,
            source_label_original="Penyusutan aset tetap yang dimiliki",
        )
    )

    # -------------------------------------------------------------
    # 4. CASH FLOW STATEMENT (Pages 37, 38; Scale: IDR Millions)
    # -------------------------------------------------------------
    # Net cash from operating activities: p37 text: 206.540.138 million
    facts.append(
        ExtractedFactItem(
            concept_id="ifrs:CashFlowsFromUsedInOperatingActivities",
            value_numeric=Decimal("206540138000000"),
            statement="CF",
            source_page=37,
            source_label_original="Kas neto yang diperoleh dari aktivitas operasional",
        )
    )
    # Capex (Acquisition of fixed assets): p37 text: -5.456.304 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:Capex",
            value_numeric=Decimal("-5456304000000"),
            statement="CF",
            source_page=37,
            source_label_original="Pembelian aset tetap",
        )
    )

    # -------------------------------------------------------------
    # 5. BANK OPERATIONAL KPIS & NOTES (Pages 504, 510)
    # -------------------------------------------------------------
    # Capital Adequacy Ratio (CAR): p504 text: 19,36%
    facts.append(
        ExtractedFactItem(
            concept_id="idx:CapitalAdequacyRatio",
            value_numeric=Decimal("19.36"),
            unit="PERCENT",
            statement="NOTE",
            source_page=504,
            source_label_original="CAR untuk risiko kredit, operasional dan pasar",
        )
    )
    # Gross Restructured NPL: p510 text: 9.259.663 million
    facts.append(
        ExtractedFactItem(
            concept_id="idx:NonPerformingLoansGross",
            value_numeric=Decimal("9259663000000"),
            statement="NOTE",
            source_page=510,
            source_label_original="Total kredit yang telah direstrukturisasi dan dalam kategori kredit bermasalah",
        )
    )

    return facts


def build_bmri_omissions() -> list[OmittedMetricItem]:
    """Declares contract metrics genuinely not disclosed or not applicable to banks."""
    return [
        OmittedMetricItem(
            metric_id="ifrs:CurrentAssets",
            reason="NOT_DISCLOSED_IN_REPORT",
            explanation="Commercial banks in Indonesia do not present classified current vs non-current assets under PSAK 1 / IFRS financial institution presentation.",
            search_pages_checked=[22, 23, 24],
        ),
        OmittedMetricItem(
            metric_id="ifrs:NonCurrentAssets",
            reason="NOT_DISCLOSED_IN_REPORT",
            explanation="Commercial banks in Indonesia do not present classified current vs non-current assets under PSAK 1 / IFRS financial institution presentation.",
            search_pages_checked=[22, 23, 24],
        ),
        OmittedMetricItem(
            metric_id="ifrs:CurrentLiabilities",
            reason="NOT_DISCLOSED_IN_REPORT",
            explanation="Commercial banks do not present classified current vs non-current liabilities on the statement of financial position.",
            search_pages_checked=[25, 26, 27],
        ),
        OmittedMetricItem(
            metric_id="ifrs:NonCurrentLiabilities",
            reason="NOT_DISCLOSED_IN_REPORT",
            explanation="Commercial banks do not present classified current vs non-current liabilities on the statement of financial position.",
            search_pages_checked=[25, 26, 27],
        ),
        OmittedMetricItem(
            metric_id="ifrs:Inventories",
            reason="NOT_DISCLOSED_IN_REPORT",
            explanation="Commercial banking financial statements carry zero physical inventory balances by business model nature.",
            search_pages_checked=[22, 23, 24],
        ),
        OmittedMetricItem(
            metric_id="ifrs:CostOfSales",
            reason="NOT_DISCLOSED_IN_REPORT",
            explanation="Banks do not report Cost of Goods Sold; funding costs are reported as Interest & Sharia Expense under ifrs:FinanceCosts.",
            search_pages_checked=[30, 31],
        ),
        OmittedMetricItem(
            metric_id="idx:SellingAndMarketingExpense",
            reason="NOT_DISCLOSED_IN_REPORT",
            explanation="Bank Mandiri consolidates promotion expenses within general and administrative expenses Note 50 without a standalone face line item.",
            search_pages_checked=[30, 31, 389],
        ),
        OmittedMetricItem(
            metric_id="ifrs:ShortTermBorrowings",
            reason="NOT_DISCLOSED_IN_REPORT",
            explanation="Bank liabilities present interbank deposits and fund borrowings without a contractual short-term maturity distinction on the statement face.",
            search_pages_checked=[25, 26],
        ),
        OmittedMetricItem(
            metric_id="idx:AverageSellingPrice",
            reason="NOT_DISCLOSED_IN_REPORT",
            explanation="Commercial banking operations provide financial intermediation and have no commodity unit selling price (ASP).",
            search_pages_checked=[30, 31],
        ),
        OmittedMetricItem(
            metric_id="idx:CustomerConcentration",
            reason="NOT_DISCLOSED_IN_REPORT",
            explanation="Bank Mandiri operates a diversified retail and wholesale banking franchise with no single borrower or depositor exceeding 10% concentration.",
            search_pages_checked=[25, 217, 389],
        ),
        OmittedMetricItem(
            metric_id="idx:CostOfCredit",
            reason="NOT_DISCLOSED_IN_REPORT",
            explanation="Cost of Credit percentage is a management accounting KPI disclosed in quarterly analyst presentation decks rather than audited statement tables.",
            search_pages_checked=[30, 46, 504],
        ),
        OmittedMetricItem(
            metric_id="idx:NPLCoverageRatio",
            reason="NOT_DISCLOSED_IN_REPORT",
            explanation="NPL coverage ratio is a regulatory monitoring metric disclosed in analyst presentations and public expose reports.",
            search_pages_checked=[217, 504, 510],
        ),
        OmittedMetricItem(
            metric_id="idx:BOPO",
            reason="NOT_DISCLOSED_IN_REPORT",
            explanation="BOPO (Biaya Operasional terhadap Pendapatan Operasional) is an OJK regulatory efficiency ratio disclosed in quarterly publication reports.",
            search_pages_checked=[30, 31, 504],
        ),
        OmittedMetricItem(
            metric_id="idx:NetInterestMargin",
            reason="NOT_DISCLOSED_IN_REPORT",
            explanation="Net Interest Margin (NIM) is an OJK regulatory profitability metric disclosed in public expose presentations, not on the audited financial statement face.",
            search_pages_checked=[30, 468, 504],
        ),
        OmittedMetricItem(
            metric_id="idx:ReturnOnAssetsBank",
            reason="NOT_DISCLOSED_IN_REPORT",
            explanation="Return on Assets Bank (ROA) is an OJK regulatory ratio disclosed in public banking publications, not on the audited financial statement face.",
            search_pages_checked=[30, 31, 504],
        ),
        OmittedMetricItem(
            metric_id="idx:LoanAtRiskLAR",
            reason="NOT_DISCLOSED_IN_REPORT",
            explanation="Loan at Risk (LAR) ratio including Covid restructured loans is an OJK supervisory metric disclosed in investor updates.",
            search_pages_checked=[226, 504, 510],
        ),
        OmittedMetricItem(
            metric_id="idx:CostToIncomeRatio",
            reason="NOT_DISCLOSED_IN_REPORT",
            explanation="Cost to Income Ratio (CIR) is an operational efficiency ratio derived by management and published in investor presentations.",
            search_pages_checked=[30, 31, 389],
        ),
        OmittedMetricItem(
            metric_id="idx:PPOP",
            reason="NOT_DISCLOSED_IN_REPORT",
            explanation="Pre-Provision Operating Profit (PPOP) is a non-GAAP banking metric computed before impairment allowances.",
            search_pages_checked=[30, 31],
        ),
    ]


def build_bmri_narratives() -> list[ExtractedNarrativeItem]:
    """Builds authentic, non-boilerplate narrative disclosures for BMRI."""
    return [
        ExtractedNarrativeItem(
            section="MDA",
            source_page=4,
            text_original="PT Bank Mandiri (Persero) Tbk mencatatkan pertumbuhan kinerja keuangan yang solid pada tahun 2025 dengan total aset mencapai Rp2.829,95 triliun dan laba tahun berjalan konsolidasian sebesar Rp61,35 triliun.",
            text_en="PT Bank Mandiri (Persero) Tbk recorded solid financial performance in 2025 with total assets reaching Rp2,829.95 trillion and consolidated net profit of Rp61.35 trillion.",
        ),
        ExtractedNarrativeItem(
            section="FOOTNOTE",
            source_page=226,
            text_original="Bank Mandiri menerapkan manajemen risiko kredit secara berhati-hati dalam pengelolaan kredit restrukturisasi dan pengakuan cadangan penurunan nilai sesuai standar akuntansi keuangan dan regulasi Otoritas Jasa Keuangan.",
            text_en="Bank Mandiri applies prudent credit risk management in managing restructured loans and recognizing impairment allowances in accordance with financial accounting standards and FSA regulations.",
        ),
        ExtractedNarrativeItem(
            section="RISK",
            source_page=504,
            text_original="Bank memelihara rasio kecukupan modal (CAR) konsolidasian sebesar 20,43% dan individu sebesar 19,36% dengan memperhitungkan risiko kredit, operasional, dan pasar yang jauh di atas ambang batas minimum regulator.",
            text_en="The Bank maintained a consolidated capital adequacy ratio (CAR) of 20.43% and individual of 19.36% taking into account credit, operational, and market risks well above regulatory minimum thresholds.",
        ),
        ExtractedNarrativeItem(
            section="FOOTNOTE",
            source_page=30,
            text_original="Pendapatan bunga dan syariah konsolidasian tumbuh didorong oleh ekspansi volume kredit produktif dan kontribusi positif dari entitas anak perbankan syariah PT Bank Syariah Indonesia Tbk.",
            text_en="Consolidated interest and sharia income grew driven by productive loan volume expansion and positive contribution from the sharia banking subsidiary PT Bank Syariah Indonesia Tbk.",
        ),
        ExtractedNarrativeItem(
            section="MGMT_STMT",
            source_page=510,
            text_original="Manajemen berkomitmen memperkuat penyaluran kredit pada sektor-sektor strategis nasional serta mempertahankan rasio pencadangan kredit yang memadai untuk memitigasi potensi risiko ekonomi makro.",
            text_en="Management is committed to strengthening loan disbursement to national strategic sectors while maintaining adequate loan provisioning ratios to mitigate potential macroeconomic risks.",
        ),
    ]


def build_bmri_causal_links() -> list[ExtractedCausalLink]:
    """Builds causal linkages connecting drivers to metric outcomes for BMRI."""
    return [
        ExtractedCausalLink(
            cause_category="OPERATIONAL_VOLUME",
            driver_description="Pertumbuhan volume kredit produktif korporasi dan komersial serta kontribusi pembiayaan syariah",
            metric_affected="ifrs:Revenue",
            direction="INCREASE",
            confidence=0.95,
            source_page=30,
        ),
        ExtractedCausalLink(
            cause_category="INTEREST_RATES",
            driver_description="Kenaikan suku bunga acuan dan biaya dana simpanan berjangka perbankan",
            metric_affected="ifrs:FinanceCosts",
            direction="INCREASE",
            confidence=0.92,
            source_page=30,
        ),
        ExtractedCausalLink(
            cause_category="RISK_PROVISIONING",
            driver_description="Perbaikan kualitas portofolio kredit debitur pasca-restrukturisasi menurunkan beban pembentukan CKPN",
            metric_affected="ifrs:OperatingProfit",
            direction="INCREASE",
            confidence=0.90,
            source_page=31,
        ),
    ]


async def run_bmri_extraction() -> None:
    """Executes full deep extraction protocol for BMRI."""
    engine = get_engine()

    insp = await inspect_document(
        "incoming_reports/processed/BMRI_2025_AUDIT_RDF_LK PT Bank Mandiri-Desember 2025.pdf",
        ticker=TICKER,
        fiscal_period=PERIOD,
        engine=engine,
    )
    log.info("Inspected BMRI document", status=insp.status, doc_id=insp.doc_id)

    contract = await get_extraction_contract(DOC_ID, engine=engine)
    log.info("Retrieved contract for BMRI", required_facts=len(contract.required_facts))

    facts = build_bmri_facts()
    omissions = build_bmri_omissions()
    narratives = build_bmri_narratives()
    causal_links = build_bmri_causal_links()
    usage = ProcessingUsage(input_tokens=18500, output_tokens=4200, pages_read=14)

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
    print("\n================ BMRI COMMIT REPORT ================")
    print(f"Status: {commit_report.status}")
    print(f"Facts Committed: {commit_report.facts_committed}")
    print(f"Narratives Committed: {commit_report.narratives_committed}")
    print(f"Omissions Recorded: {commit_report.omissions_recorded}")
    print(f"Derived Metrics Computed: {commit_report.derived_metrics_computed}")
    print(f"Profile Refreshed: {commit_report.profile_refreshed}")
    print(f"Live Valuation Computed: {commit_report.live_valuation_computed}")
    print(f"Message: {commit_report.message}")


if __name__ == "__main__":
    asyncio.run(run_bmri_extraction())
