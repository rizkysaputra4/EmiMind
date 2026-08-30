"""Industry-tailored extraction contract generation for EMIMIND MCP Server."""

from __future__ import annotations

from services.mcp.types import ExtractionContract, ExtractionFactRule

BASE_GENERIC_FACTS: list[ExtractionFactRule] = [
    # Balance Sheet
    ExtractionFactRule(
        concept_id="ifrs:Assets",
        label="Total Aset / Total Assets",
        statement_type="BALANCE_SHEET",
        required=True,
    ),
    ExtractionFactRule(
        concept_id="ifrs:CurrentAssets",
        label="Total Aset Lancar / Current Assets",
        statement_type="BALANCE_SHEET",
        required=True,
    ),
    ExtractionFactRule(
        concept_id="ifrs:NonCurrentAssets",
        label="Total Aset Tidak Lancar / Non-Current Assets",
        statement_type="BALANCE_SHEET",
        required=True,
    ),
    ExtractionFactRule(
        concept_id="ifrs:CashAndCashEquivalents",
        label="Kas dan Setara Kas / Cash and Cash Equivalents",
        statement_type="BALANCE_SHEET",
        required=True,
    ),
    ExtractionFactRule(
        concept_id="ifrs:TradeAndOtherReceivables",
        label="Piutang Usaha / Trade Receivables",
        statement_type="BALANCE_SHEET",
        required=False,
    ),
    ExtractionFactRule(
        concept_id="ifrs:Inventories",
        label="Persediaan / Inventories",
        statement_type="BALANCE_SHEET",
        required=False,
    ),
    ExtractionFactRule(
        concept_id="ifrs:Liabilities",
        label="Total Liabilitas / Total Liabilities",
        statement_type="BALANCE_SHEET",
        required=True,
    ),
    ExtractionFactRule(
        concept_id="ifrs:CurrentLiabilities",
        label="Total Liabilitas Jangka Pendek / Current Liabilities",
        statement_type="BALANCE_SHEET",
        required=True,
    ),
    ExtractionFactRule(
        concept_id="ifrs:NonCurrentLiabilities",
        label="Total Liabilitas Jangka Panjang / Non-Current Liabilities",
        statement_type="BALANCE_SHEET",
        required=True,
    ),
    ExtractionFactRule(
        concept_id="ifrs:ShortTermBorrowings",
        label="Pinjaman Jangka Pendek / Utang Bank JK Pendek",
        statement_type="BALANCE_SHEET",
        required=False,
    ),
    ExtractionFactRule(
        concept_id="ifrs:LongTermBorrowings",
        label="Pinjaman Jangka Panjang / Utang Bank JK Panjang",
        statement_type="BALANCE_SHEET",
        required=False,
    ),
    ExtractionFactRule(
        concept_id="ifrs:Equity",
        label="Total Ekuitas / Total Equity",
        statement_type="BALANCE_SHEET",
        required=True,
    ),
    ExtractionFactRule(
        concept_id="ifrs:EquityAttributableToOwnersOfParent",
        label="Ekuitas yang Dapat Diatribusikan ke Pemilik Entitas Induk",
        statement_type="BALANCE_SHEET",
        required=False,
    ),
    # Income Statement
    ExtractionFactRule(
        concept_id="ifrs:Revenue",
        label="Pendapatan Usaha / Revenue / Sales",
        statement_type="INCOME_STATEMENT",
        required=True,
    ),
    ExtractionFactRule(
        concept_id="ifrs:CostOfSales",
        label="Beban Pokok Penjualan / Cost of Goods Sold",
        statement_type="INCOME_STATEMENT",
        required=False,
    ),
    ExtractionFactRule(
        concept_id="ifrs:GrossProfit",
        label="Laba Kotor / Gross Profit",
        statement_type="INCOME_STATEMENT",
        required=False,
    ),
    ExtractionFactRule(
        concept_id="ifrs:OperatingProfit",
        label="Laba Usaha / Operating Profit / EBIT",
        statement_type="INCOME_STATEMENT",
        required=True,
    ),
    ExtractionFactRule(
        concept_id="ifrs:FinanceCosts",
        label="Beban Keuangan / Beban Bunga / Finance Costs",
        statement_type="INCOME_STATEMENT",
        required=False,
    ),
    ExtractionFactRule(
        concept_id="ifrs:ProfitBeforeTax",
        label="Laba Sebelum Pajak Penghasilan / Profit Before Tax",
        statement_type="INCOME_STATEMENT",
        required=False,
    ),
    ExtractionFactRule(
        concept_id="ifrs:ProfitLoss",
        label="Laba Bersih Tahun/Periode Berjalan / Net Profit",
        statement_type="INCOME_STATEMENT",
        required=True,
    ),
    ExtractionFactRule(
        concept_id="ifrs:ProfitLossAttributableToOwnersOfParent",
        label="Laba Bersih yang Dapat Diatribusikan ke Entitas Induk",
        statement_type="INCOME_STATEMENT",
        required=False,
    ),
    ExtractionFactRule(
        concept_id="ifrs:DepreciationAndAmortisationExpense",
        label="Beban Penyusutan dan Amortisasi / D&A Expense",
        statement_type="INCOME_STATEMENT",
        required=False,
    ),
    # Cash Flow
    ExtractionFactRule(
        concept_id="ifrs:CashFlowsFromUsedInOperatingActivities",
        label="Arus Kas Bersih dari Aktivitas Operasi (CFO)",
        statement_type="CASH_FLOW",
        required=True,
    ),
    ExtractionFactRule(
        concept_id="ifrs:CashFlowsFromUsedInInvestingActivities",
        label="Arus Kas Bersih dari Aktivitas Investasi (CFI)",
        statement_type="CASH_FLOW",
        required=False,
    ),
    ExtractionFactRule(
        concept_id="ifrs:CashFlowsFromUsedInFinancingActivities",
        label="Arus Kas Bersih dari Aktivitas Pendanaan (CFF)",
        statement_type="CASH_FLOW",
        required=False,
    ),
    ExtractionFactRule(
        concept_id="ifrs:PaymentsToAcquirePropertyPlantAndEquipment",
        label="Perolehan/Pembelian Aset Tetap (Capex)",
        statement_type="CASH_FLOW",
        required=False,
    ),
    # Per Share & Disclosures
    ExtractionFactRule(
        concept_id="ifrs:BasicEarningsLossPerShare",
        label="Laba per Saham Dasar (EPS)",
        statement_type="PER_SHARE",
        required=False,
    ),
    ExtractionFactRule(
        concept_id="idx:SharesOutstanding",
        label="Jumlah Saham Beredar / Shares Outstanding",
        statement_type="PER_SHARE",
        required=False,
    ),
    ExtractionFactRule(
        concept_id="idx:DividendPerShare",
        label="Dividen per Saham / Dividend Per Share",
        statement_type="PER_SHARE",
        required=False,
    ),
]

SECTOR_EXTENSIONS: dict[str, list[ExtractionFactRule]] = {
    "BANK": [
        ExtractionFactRule(
            concept_id="idx:LoansAndAdvances",
            label="Kredit yang Diberikan / Loans & Advances",
            statement_type="BALANCE_SHEET",
            required=True,
        ),
        ExtractionFactRule(
            concept_id="idx:CustomerDeposits",
            label="Dana Pihak Ketiga / Customer Deposits (Giro, Tabungan, Deposito)",
            statement_type="BALANCE_SHEET",
            required=True,
        ),
        ExtractionFactRule(
            concept_id="idx:DemandDeposits",
            label="Giro / Demand Deposits (CASA)",
            statement_type="BALANCE_SHEET",
            required=False,
        ),
        ExtractionFactRule(
            concept_id="idx:SavingsDeposits",
            label="Tabungan / Savings Deposits (CASA)",
            statement_type="BALANCE_SHEET",
            required=False,
        ),
        ExtractionFactRule(
            concept_id="idx:TimeDeposits",
            label="Deposito Berjangka / Time Deposits",
            statement_type="BALANCE_SHEET",
            required=False,
        ),
        ExtractionFactRule(
            concept_id="idx:NetInterestIncome",
            label="Pendapatan Bunga Bersih / Net Interest Income (NII)",
            statement_type="INCOME_STATEMENT",
            required=True,
        ),
        ExtractionFactRule(
            concept_id="idx:NonPerformingLoansGross",
            label="Kredit Bermasalah (NPL Gross)",
            statement_type="NOTES",
            required=False,
        ),
    ],
    "MINING": [
        ExtractionFactRule(
            concept_id="idx:CoalProductionVolume",
            label="Volume Produksi Batubara/Nikel (Production Volume)",
            statement_type="NOTES",
            required=False,
        ),
        ExtractionFactRule(
            concept_id="idx:CoalSalesVolume",
            label="Volume Penjualan (Sales Volume)",
            statement_type="NOTES",
            required=False,
        ),
        ExtractionFactRule(
            concept_id="idx:AverageSellingPrice",
            label="Harga Jual Rata-rata / Average Selling Price (ASP)",
            statement_type="NOTES",
            required=False,
        ),
        ExtractionFactRule(
            concept_id="idx:CashCost",
            label="Biaya Kas per Ton / Cash Cost",
            statement_type="NOTES",
            required=False,
        ),
        ExtractionFactRule(
            concept_id="idx:StripRatio",
            label="Nisbah Kupas / Strip Ratio",
            statement_type="NOTES",
            required=False,
        ),
        ExtractionFactRule(
            concept_id="idx:MiningRoyalties",
            label="Royalti dan Iuran Pertambangan",
            statement_type="INCOME_STATEMENT",
            required=False,
        ),
    ],
    "CPO": [
        ExtractionFactRule(
            concept_id="idx:FfbProduction",
            label="Produksi Tandan Buah Segar (FFB Production)",
            statement_type="NOTES",
            required=False,
        ),
        ExtractionFactRule(
            concept_id="idx:CpoProduction",
            label="Produksi CPO (Crude Palm Oil Production)",
            statement_type="NOTES",
            required=False,
        ),
        ExtractionFactRule(
            concept_id="idx:OilExtractionRate",
            label="Tingkat Ekstraksi Minyak / Oil Extraction Rate (OER)",
            statement_type="NOTES",
            required=False,
        ),
    ],
    "TELCO": [
        ExtractionFactRule(
            concept_id="idx:DataRevenue",
            label="Pendapatan Data dan Digital / Data Revenue",
            statement_type="INCOME_STATEMENT",
            required=False,
        ),
        ExtractionFactRule(
            concept_id="idx:SubscriberCount",
            label="Jumlah Pelanggan / Subscriber Base",
            statement_type="NOTES",
            required=False,
        ),
        ExtractionFactRule(
            concept_id="idx:ArpuBlended",
            label="Average Revenue Per User (ARPU)",
            statement_type="NOTES",
            required=False,
        ),
    ],
}


def build_extraction_contract(
    doc_id: str,
    ticker: str,
    company_name: str,
    sector: str,
    fiscal_period: str,
    period_type: str = "duration_ytd",
) -> ExtractionContract:
    """Builds a dynamic extraction contract customized for the company's sector and reporting period."""
    sector_upper = (sector or "GENERIC").upper()

    # Combine generic rules with sector-specific additions
    required_facts: list[ExtractionFactRule] = list(BASE_GENERIC_FACTS)

    for sec_key, extra_rules in SECTOR_EXTENSIONS.items():
        if sec_key in sector_upper:
            required_facts.extend(extra_rules)

    sector_guidelines = [
        f"Target Issuer: {company_name} ({ticker}) — Sector: {sector_upper}.",
        "Scaling: Inspect the top of each financial statement table for the phrase: 'Disajikan dalam jutaan rupiah' (multiply by 1,000,000) or 'Disajikan dalam ribuan rupiah' (multiply by 1,000). Always output full unscaled IDR amount in output JSON.",
        "Precision: Capture exact monetary numbers. Do not round numbers.",
        "Sign conventions: Cost of Sales, Expenses, and negative Cash Flows should be positive numbers in the payload; the system applies statement logic.",
        "Provenances: Include exact source_page (1-indexed) and source_label_original for every extracted item.",
    ]

    do_not_extract = [
        "Do NOT extract financial ratios (ROE, ROA, DER, PE, PBV, Margins, NIM). EMIMIND calculates them deterministically.",
        "Do NOT extract prior year comparative columns unless specifically asked.",
        "Do NOT extract decorative or non-financial pages (cover, directors signature page).",
    ]

    scaling_rules = {
        "unit": "IDR",
        "instructions": "All extracted monetary amounts must be converted to full IDR integer/decimal value before submission.",
    }

    return ExtractionContract(
        doc_id=doc_id,
        ticker=ticker.upper(),
        company_name=company_name,
        sector=sector_upper,
        fiscal_period=fiscal_period.upper(),
        period_type=period_type,
        scaling_rules=scaling_rules,
        required_facts=required_facts,
        sector_specific_guidelines=sector_guidelines,
        do_not_extract=do_not_extract,
    )
