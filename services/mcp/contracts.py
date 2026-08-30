"""Industry-tailored extraction contract generation for EMIMIND MCP Server."""

from __future__ import annotations

from services.mcp.types import (
    ExtractionContract,
    ExtractionFactRule,
    ExtractionNarrativeRule,
    GranularNoteModule,
)

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


BASE_REQUIRED_NARRATIVES: list[ExtractionNarrativeRule] = [
    ExtractionNarrativeRule(
        topic="General Corporate Overview",
        target_note_description="Catatan 1 (Informasi Umum Perusahaan / General Information)",
        expected_section="MDA",
        guideline="Extract clean prose describing the company's core operations, concession/plantation permits, subsidiaries, and primary business activities. (Do NOT include auditor boilerplate).",
    ),
    ExtractionNarrativeRule(
        topic="Segment Operations & Revenue Drivers",
        target_note_description="Catatan Informasi Segmen Operasi / Segment Reporting",
        expected_section="FOOTNOTE",
        guideline="Extract text explaining product contributions, geographic distribution, and market drivers for sales changes.",
    ),
    ExtractionNarrativeRule(
        topic="Financial Risk & Market Factors",
        target_note_description="Catatan Manajemen Risiko Keuangan / Financial Risk Management",
        expected_section="RISK",
        guideline="Extract descriptions of commodity price risks, foreign exchange exposure, and interest rate policies.",
    ),
    ExtractionNarrativeRule(
        topic="Subsequent Events & Material Commitments",
        target_note_description="Catatan Peristiwa Setelah Tanggal Pelaporan / Subsequent Events",
        expected_section="MGMT_STMT",
        guideline="Extract any material events, dividend announcements, or capital commitments occurring after reporting date.",
    ),
]


BASE_GRANULAR_NOTE_MODULES: list[GranularNoteModule] = [
    GranularNoteModule(
        name="REVENUE_BREAKDOWN",
        description="Rincian pendapatan per lini produk, wilayah geografis, dan transaksi pihak ketiga vs pihak berelasi.",
        typical_note_title="Catatan Penjualan / Pendapatan / Informasi Segmen",
        target_concepts=["ifrs:Revenue", "idx:RevenueByProduct", "idx:RevenueByGeography"],
        expected_segment_fields=["segment", "type", "pct_total"],
        guideline="Extract every product line (e.g. CPO, Palm Kernel, Rubber, Coal, Data) as an ExtractedFactItem with segment={'segment': '<product_name>', 'type': 'product'}.",
    ),
    GranularNoteModule(
        name="CUSTOMER_CONCENTRATION",
        description="Pelanggan dengan transaksi penjualan melebihi 10% dari total pendapatan.",
        typical_note_title="Catatan Pelanggan Utama / Konsentrasi Penjualan",
        target_concepts=["idx:CustomerConcentration"],
        expected_segment_fields=["segment", "type", "pct_total", "is_related_party"],
        guideline="Extract major buyers contributing >10% revenue with segment={'segment': '<customer_name>', 'type': 'customer_concentration', 'pct_total': <pct>}.",
    ),
    GranularNoteModule(
        name="COGS_COMPONENTS",
        description="Rincian komponen beban pokok penjualan (bahan baku, pupuk, upah buruh, penyusutan, overhead pabrik).",
        typical_note_title="Catatan Beban Pokok Penjualan / Cost of Goods Sold",
        target_concepts=["ifrs:CostOfSales", "idx:CostOfGoodsSoldComponent"],
        expected_segment_fields=["segment", "type", "pct_cogs"],
        guideline="Extract major cost line items with segment={'segment': '<cost_item_name>', 'type': 'cogs_component'}.",
    ),
    GranularNoteModule(
        name="CASH_BANK_PLACEMENTS",
        description="Rincian penempatan kas di bank dan deposito berjangka per institusi perbankan beserta suku bunga rata-rata.",
        typical_note_title="Catatan Kas dan Setara Kas / Bank & Deposito",
        target_concepts=["ifrs:CashAndCashEquivalents", "idx:TimeDepositsByInstitution"],
        expected_segment_fields=["segment", "type", "currency", "interest_rate"],
        guideline="Extract cash balances per bank with segment={'segment': '<bank_name>', 'type': 'bank_placement', 'currency': 'IDR/USD', 'interest_rate': '<rate>'}.",
    ),
    GranularNoteModule(
        name="SUBSIDIARIES_AND_AFFILIATES",
        description="Daftar entitas anak dan entitas asosiasi, persentase kepemilikan, lokasi operasi, dan total aset anak usaha.",
        typical_note_title="Catatan Informasi Entitas Anak / Penyertaan Saham",
        target_concepts=["idx:SubsidiaryInvestment", "idx:SubsidiaryTotalAssets"],
        expected_segment_fields=["segment", "type", "ownership_pct", "location", "activity"],
        guideline="Extract each operating subsidiary with segment={'segment': '<subsidiary_name>', 'type': 'subsidiary', 'ownership_pct': <pct>, 'location': '<location>'}.",
    ),
    GranularNoteModule(
        name="DEBT_BY_LENDER",
        description="Rincian pinjaman bank jangka pendek dan jangka panjang per kreditur bank, tingkat bunga, dan tahun jatuh tempo.",
        typical_note_title="Catatan Utang Bank / Pinjaman Jangka Panjang",
        target_concepts=["idx:BorrowingsByLender", "ifrs:LongTermBorrowings"],
        expected_segment_fields=["segment", "type", "interest_rate", "maturity_year", "collateral"],
        guideline="Extract debt facilities per bank with segment={'segment': '<bank_name>', 'type': 'debt_facility', 'interest_rate': '<rate>', 'maturity_year': <year>}.",
    ),
    GranularNoteModule(
        name="RELATED_PARTY_BALANCES",
        description="Rincian saldo piutang/utang serta transaksi penjualan/pembelian dengan pihak-pihak berelasi.",
        typical_note_title="Catatan Transaksi dan Saldo Pihak Berelasi",
        target_concepts=["idx:RelatedPartySales", "idx:RelatedPartyPurchases", "idx:RelatedPartyReceivables"],
        expected_segment_fields=["segment", "type", "relationship"],
        guideline="Extract affiliate transactions with segment={'segment': '<affiliate_name>', 'type': 'related_party', 'relationship': '<parent/sister>'}.",
    ),
    GranularNoteModule(
        name="FIXED_ASSETS_DETAIL",
        description="Rincian aset tetap (Tanah/HGU, Bangunan/Pabrik, Mesin, dan Aset dalam Penyelesaian) serta penambahan capex.",
        typical_note_title="Catatan Aset Tetap / Property, Plant & Equipment",
        target_concepts=["ifrs:PropertyPlantAndEquipment"],
        expected_segment_fields=["segment", "type"],
        guideline="Extract fixed asset categories with segment={'segment': '<asset_category>', 'type': 'fixed_asset_category'}.",
    ),
    GranularNoteModule(
        name="SHAREHOLDERS_DETAIL",
        description="Struktur kepemilikan saham, pemegang saham pengendali, kepemilikan publik (free float), dan kepemilikan manajemen.",
        typical_note_title="Catatan Modal Saham / Struktur Pemegang Saham",
        target_concepts=["idx:Shareholders", "idx:SharesOutstanding"],
        expected_segment_fields=["segment", "type", "shares_count", "pct_ownership", "is_free_float"],
        guideline="Extract major shareholders with segment={'segment': '<shareholder_name>', 'type': 'major_shareholder/public', 'pct_ownership': <pct>}.",
    ),
]

SECTOR_GRANULAR_MODULES: dict[str, list[GranularNoteModule]] = {
    "CPO": [
        GranularNoteModule(
            name="BIOLOGICAL_ASSETS_DETAIL",
            description="Profil perkebunan kelapa sawit: luas areal tertanam (tanaman menghasilkan/mature vs belum menghasilkan/immature) dalam hektar.",
            typical_note_title="Catatan Tanaman Produktif / Aset Biologis / Perkebunan",
            target_concepts=["ifrs:BiologicalAssets", "idx:PlantedAreaHectares", "idx:UnplantedAreaHectares"],
            expected_segment_fields=["segment", "type", "planted_area_ha", "average_age_years"],
            guideline="Extract planted hectares breakdown with segment={'segment': 'Mature/Immature/Plasma', 'type': 'biological_asset_maturity', 'planted_area_ha': <ha>}.",
        )
    ],
    "MINING": [
        GranularNoteModule(
            name="MINING_RESERVES_AND_RESOURCES",
            description="Cadangan dan sumber daya tambang (Reserves & Resources) serta konsesi IUP/PKP2B.",
            typical_note_title="Catatan Aset Eksplorasi & Evaluasi / Cadangan Tambang",
            target_concepts=["idx:MiningReservesMt", "idx:MiningResourcesMt", "idx:StripRatio"],
            expected_segment_fields=["segment", "type", "concession_location", "reserves_mt"],
            guideline="Extract mining metrics with segment={'segment': '<mine_concession_name>', 'type': 'mining_asset'}.",
        )
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

    # Combine granular modules
    granular_modules: list[GranularNoteModule] = list(BASE_GRANULAR_NOTE_MODULES)
    for sec_key, extra_mod in SECTOR_GRANULAR_MODULES.items():
        if sec_key in sector_upper:
            granular_modules.extend(extra_mod)

    sector_guidelines = [
        f"Target Issuer: {company_name} ({ticker}) — Sector: {sector_upper}.",
        "Granular Decomposition: Do NOT stop at top-level financial statements. Extract all detailed disclosure tables (Revenue by product, COGS components, Subsidiaries, Debt by lender, Cash placements, Customer concentration) into segmented ExtractedFactItems.",
        "Scaling: Inspect the top of each financial statement table for the phrase: 'Disajikan dalam jutaan rupiah' (multiply by 1,000,000) or 'Disajikan dalam ribuan rupiah' (multiply by 1,000). Always output full unscaled IDR amount in output JSON.",
        "Precision: Capture exact monetary numbers and exact unit/shares. Do not round numbers.",
        "Targeted Page Navigation: Use the 'Index of Notes' (Daftar Catatan) to jump directly to target disclosure note pages. Do NOT read the entire 100+ page PDF sequentially.",
        "Causality Extraction: When management explains *why* a metric changed (e.g. revenue grew due to weather, rainfall, higher CPO ASP, or coal volume), capture this in 'causal_links'.",
        "Sign conventions: Cost of Sales, Expenses, and negative Cash Flows should be positive numbers in the payload; the system applies statement logic.",
        "Provenances: Include exact source_page (1-indexed) and source_label_original for every extracted item.",
    ]

    do_not_extract = [
        "Do NOT extract financial ratios (ROE, ROA, DER, PE, PBV, Margins, NIM). EMIMIND calculates them deterministically.",
        "Do NOT extract prior year comparative columns unless specifically asked.",
        "Do NOT extract decorative or boilerplate auditor opinion letters.",
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
        required_narratives=list(BASE_REQUIRED_NARRATIVES),
        granular_note_modules=granular_modules,
        sector_specific_guidelines=sector_guidelines,
        do_not_extract=do_not_extract,
    )
