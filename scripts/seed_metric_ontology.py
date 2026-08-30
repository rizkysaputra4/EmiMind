"""Seed Industry-Aware Financial Metric Ontology & Sector Contracts into PostgreSQL."""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import text
from services.shared.db import create_pool
from services.shared.logging import get_logger

log = get_logger("seed.metric_ontology")

METRIC_DEFINITIONS_DATA: list[dict[str, Any]] = [
    # =========================================================================
    # 1. GENERAL METRICS — INCOME STATEMENT
    # =========================================================================
    {
        "metric_id": "ifrs:Revenue",
        "name_en": "Net Revenue / Sales",
        "name_id": "Pendapatan Usaha / Penjualan Neto",
        "category": "INCOME",
        "sector_applicability": ["ALL"],
        "importance": "CRITICAL",
        "value_type": "MONETARY",
        "unit": "IDR",
        "flow_stock_type": "FLOW_PERIOD",
        "extraction_mode": "EXTRACTED_RAW",
        "source_priority": ["FS_CORE_STATEMENT", "FS_NOTES_DETAIL"],
        "synonyms_id": ["Penjualan", "Penjualan Bersih", "Pendapatan dari Kontrak dengan Pelanggan", "Pendapatan Pokok"],
        "synonyms_en": ["Revenue", "Net Sales", "Revenues", "Operating Revenues"],
    },
    {
        "metric_id": "ifrs:CostOfSales",
        "name_en": "Cost of Goods Sold (COGS)",
        "name_id": "Beban Pokok Pendapatan / Penjualan",
        "category": "INCOME",
        "sector_applicability": ["ALL"],
        "importance": "HIGH",
        "value_type": "MONETARY",
        "unit": "IDR",
        "flow_stock_type": "FLOW_PERIOD",
        "extraction_mode": "EXTRACTED_RAW",
        "source_priority": ["FS_CORE_STATEMENT", "FS_NOTES_DETAIL"],
        "synonyms_id": ["Beban Pokok Penjualan", "Beban Pokok Pendapatan", "Beban Langsung"],
        "synonyms_en": ["Cost of Sales", "Cost of Revenues", "COGS"],
    },
    {
        "metric_id": "ifrs:GrossProfit",
        "name_en": "Gross Profit",
        "name_id": "Laba Kotor",
        "category": "INCOME",
        "sector_applicability": ["ALL"],
        "importance": "HIGH",
        "value_type": "MONETARY",
        "unit": "IDR",
        "flow_stock_type": "FLOW_PERIOD",
        "extraction_mode": "CALCULATED_DETERMINISTIC",
        "calculation_formula": "ifrs:Revenue - ifrs:CostOfSales",
        "dependencies": ["ifrs:Revenue", "ifrs:CostOfSales"],
        "source_priority": ["FS_CORE_STATEMENT"],
        "synonyms_id": ["Laba Kotor", "Marjin Kotor"],
        "synonyms_en": ["Gross Margin", "Gross Profit"],
    },
    {
        "metric_id": "ifrs:OperatingProfit",
        "name_en": "Operating Profit (EBIT)",
        "name_id": "Laba Usaha / Operasi",
        "category": "INCOME",
        "sector_applicability": ["ALL"],
        "importance": "CRITICAL",
        "value_type": "MONETARY",
        "unit": "IDR",
        "flow_stock_type": "FLOW_PERIOD",
        "extraction_mode": "EXTRACTED_RAW",
        "source_priority": ["FS_CORE_STATEMENT"],
        "synonyms_id": ["Laba Usaha", "Laba Operasional", "Laba Sebelum Pajak dan Beban Keuangan"],
        "synonyms_en": ["Operating Income", "EBIT", "Operating Profit"],
    },
    {
        "metric_id": "idx:EBITDA",
        "name_en": "EBITDA",
        "name_id": "EBITDA (Laba Sebelum Bunga, Pajak, Depresiasi, Amortisasi)",
        "category": "INCOME",
        "sector_applicability": ["ALL"],
        "importance": "CRITICAL",
        "value_type": "MONETARY",
        "unit": "IDR",
        "flow_stock_type": "FLOW_PERIOD",
        "extraction_mode": "CALCULATED_DETERMINISTIC",
        "calculation_formula": "ifrs:OperatingProfit + ifrs:DepreciationAndAmortisationExpense",
        "dependencies": ["ifrs:OperatingProfit", "ifrs:DepreciationAndAmortisationExpense"],
        "source_priority": ["FS_CORE_STATEMENT", "FS_NOTES_DETAIL"],
        "synonyms_id": ["EBITDA Konsolidasian"],
        "synonyms_en": ["Consolidated EBITDA"],
    },
    {
        "metric_id": "ifrs:FinanceCosts",
        "name_en": "Finance Costs / Interest Expense",
        "name_id": "Beban Keuangan / Beban Bunga",
        "category": "INCOME",
        "sector_applicability": ["ALL"],
        "importance": "HIGH",
        "value_type": "MONETARY",
        "unit": "IDR",
        "flow_stock_type": "FLOW_PERIOD",
        "extraction_mode": "EXTRACTED_RAW",
        "source_priority": ["FS_CORE_STATEMENT", "FS_NOTES_DETAIL"],
        "synonyms_id": ["Beban Keuangan", "Beban Bunga Pinjaman"],
        "synonyms_en": ["Interest Expense", "Finance Costs"],
    },
    {
        "metric_id": "ifrs:ProfitBeforeTax",
        "name_en": "Profit Before Tax (EBT)",
        "name_id": "Laba Sebelum Pajak Penghasilan",
        "category": "INCOME",
        "sector_applicability": ["ALL"],
        "importance": "HIGH",
        "value_type": "MONETARY",
        "unit": "IDR",
        "flow_stock_type": "FLOW_PERIOD",
        "extraction_mode": "EXTRACTED_RAW",
        "source_priority": ["FS_CORE_STATEMENT"],
        "synonyms_id": ["Laba Sebelum Pajak"],
        "synonyms_en": ["Earnings Before Tax", "EBT", "Profit Before Tax"],
    },
    {
        "metric_id": "ifrs:ProfitLossAttributableToOwnersOfParent",
        "name_en": "Net Income Attributable to Owners of Parent",
        "name_id": "Laba Bersih yang Dapat Diatribusikan ke Pemilik Entitas Induk",
        "category": "INCOME",
        "sector_applicability": ["ALL"],
        "importance": "CRITICAL",
        "value_type": "MONETARY",
        "unit": "IDR",
        "flow_stock_type": "FLOW_PERIOD",
        "extraction_mode": "EXTRACTED_RAW",
        "source_priority": ["FS_CORE_STATEMENT"],
        "synonyms_id": ["Laba Bersih Entitas Induk", "Laba Tahun Berjalan Pemilik Induk"],
        "synonyms_en": ["Net Profit Attributable to Equity Holders", "Net Income"],
    },

    # =========================================================================
    # 2. GENERAL METRICS — BALANCE SHEET
    # =========================================================================
    {
        "metric_id": "ifrs:Assets",
        "name_en": "Total Assets",
        "name_id": "Total Aset / Jumlah Aset",
        "category": "BALANCE_SHEET",
        "sector_applicability": ["ALL"],
        "importance": "CRITICAL",
        "value_type": "MONETARY",
        "unit": "IDR",
        "flow_stock_type": "STOCK_POINT_IN_TIME",
        "extraction_mode": "EXTRACTED_RAW",
        "source_priority": ["FS_CORE_STATEMENT"],
        "synonyms_id": ["Jumlah Aset", "Total Aktiva"],
        "synonyms_en": ["Total Assets"],
    },
    {
        "metric_id": "ifrs:CurrentAssets",
        "name_en": "Current Assets",
        "name_id": "Total Aset Lancar",
        "category": "BALANCE_SHEET",
        "sector_applicability": ["ALL"],
        "importance": "CRITICAL",
        "value_type": "MONETARY",
        "unit": "IDR",
        "flow_stock_type": "STOCK_POINT_IN_TIME",
        "extraction_mode": "EXTRACTED_RAW",
        "source_priority": ["FS_CORE_STATEMENT"],
        "synonyms_id": ["Jumlah Aset Lancar", "Aktiva Lancar"],
        "synonyms_en": ["Current Assets"],
    },
    {
        "metric_id": "ifrs:NonCurrentAssets",
        "name_en": "Non-Current Assets",
        "name_id": "Total Aset Tidak Lancar",
        "category": "BALANCE_SHEET",
        "sector_applicability": ["ALL"],
        "importance": "CRITICAL",
        "value_type": "MONETARY",
        "unit": "IDR",
        "flow_stock_type": "STOCK_POINT_IN_TIME",
        "extraction_mode": "EXTRACTED_RAW",
        "source_priority": ["FS_CORE_STATEMENT"],
        "synonyms_id": ["Jumlah Aset Tidak Lancar", "Aktiva Tetap & Tidak Lancar"],
        "synonyms_en": ["Non-Current Assets"],
    },
    {
        "metric_id": "ifrs:CashAndCashEquivalents",
        "name_en": "Cash and Cash Equivalents",
        "name_id": "Kas dan Setara Kas",
        "category": "BALANCE_SHEET",
        "sector_applicability": ["ALL"],
        "importance": "CRITICAL",
        "value_type": "MONETARY",
        "unit": "IDR",
        "flow_stock_type": "STOCK_POINT_IN_TIME",
        "extraction_mode": "EXTRACTED_RAW",
        "source_priority": ["FS_CORE_STATEMENT", "FS_NOTES_DETAIL"],
        "synonyms_id": ["Kas dan Bank", "Kas dan Deposito"],
        "synonyms_en": ["Cash & Cash Equivalents", "Cash and Bank Balances"],
    },
    {
        "metric_id": "ifrs:Liabilities",
        "name_en": "Total Liabilities",
        "name_id": "Total Liabilitas / Jumlah Kewajiban",
        "category": "BALANCE_SHEET",
        "sector_applicability": ["ALL"],
        "importance": "CRITICAL",
        "value_type": "MONETARY",
        "unit": "IDR",
        "flow_stock_type": "STOCK_POINT_IN_TIME",
        "extraction_mode": "EXTRACTED_RAW",
        "source_priority": ["FS_CORE_STATEMENT"],
        "synonyms_id": ["Jumlah Liabilitas", "Total Kewajiban"],
        "synonyms_en": ["Total Liabilities"],
    },
    {
        "metric_id": "ifrs:EquityAttributableToOwnersOfParent",
        "name_en": "Equity Attributable to Owners of Parent",
        "name_id": "Ekuitas yang Dapat Diatribusikan ke Pemilik Entitas Induk",
        "category": "BALANCE_SHEET",
        "sector_applicability": ["ALL"],
        "importance": "CRITICAL",
        "value_type": "MONETARY",
        "unit": "IDR",
        "flow_stock_type": "STOCK_POINT_IN_TIME",
        "extraction_mode": "EXTRACTED_RAW",
        "source_priority": ["FS_CORE_STATEMENT"],
        "synonyms_id": ["Ekuitas Pemilik Induk", "Modal Bersih Pemegang Saham"],
        "synonyms_en": ["Shareholders Equity", "Total Equity Attributable"],
    },
    {
        "metric_id": "idx:TotalDebt",
        "name_en": "Total Interest-Bearing Debt",
        "name_id": "Total Utang Berbunga",
        "category": "BALANCE_SHEET",
        "sector_applicability": ["ALL"],
        "importance": "CRITICAL",
        "value_type": "MONETARY",
        "unit": "IDR",
        "flow_stock_type": "STOCK_POINT_IN_TIME",
        "extraction_mode": "CALCULATED_DETERMINISTIC",
        "calculation_formula": "ifrs:ShortTermBorrowings + ifrs:LongTermBorrowings",
        "dependencies": ["ifrs:ShortTermBorrowings", "ifrs:LongTermBorrowings"],
        "source_priority": ["FS_NOTES_DETAIL", "FS_CORE_STATEMENT"],
        "synonyms_id": ["Pinjaman Bank dan Surat Berharga"],
        "synonyms_en": ["Total Debt", "Interest-Bearing Borrowings"],
    },

    # =========================================================================
    # 3. GENERAL METRICS — CASH FLOW & CAPITAL ALLOCATION
    # =========================================================================
    {
        "metric_id": "ifrs:CashFlowsFromUsedInOperatingActivities",
        "name_en": "Cash Flow from Operating Activities (CFO)",
        "name_id": "Arus Kas Bersih dari Aktivitas Operasi",
        "category": "CASH_FLOW",
        "sector_applicability": ["ALL"],
        "importance": "CRITICAL",
        "value_type": "MONETARY",
        "unit": "IDR",
        "flow_stock_type": "FLOW_PERIOD",
        "extraction_mode": "EXTRACTED_RAW",
        "source_priority": ["FS_CORE_STATEMENT"],
        "synonyms_id": ["Arus Kas Operasional", "CFO"],
        "synonyms_en": ["Operating Cash Flow", "Cash Generated from Operations"],
    },
    {
        "metric_id": "idx:Capex",
        "name_en": "Capital Expenditures (Capex)",
        "name_id": "Belanja Modal / Perolehan Aset Tetap",
        "category": "CASH_FLOW",
        "sector_applicability": ["ALL"],
        "importance": "CRITICAL",
        "value_type": "MONETARY",
        "unit": "IDR",
        "flow_stock_type": "FLOW_PERIOD",
        "extraction_mode": "EXTRACTED_RAW",
        "source_priority": ["FS_CORE_STATEMENT", "FS_NOTES_DETAIL"],
        "synonyms_id": ["Pembayaran untuk Perolehan Aset Tetap", "Capex"],
        "synonyms_en": ["Additions to PPE", "Capital Expenditures"],
    },
    {
        "metric_id": "idx:FreeCashFlow",
        "name_en": "Free Cash Flow (FCF)",
        "name_id": "Arus Kas Bebas",
        "category": "CASH_FLOW",
        "sector_applicability": ["ALL"],
        "importance": "CRITICAL",
        "value_type": "MONETARY",
        "unit": "IDR",
        "flow_stock_type": "FLOW_PERIOD",
        "extraction_mode": "CALCULATED_DETERMINISTIC",
        "calculation_formula": "ifrs:CashFlowsFromUsedInOperatingActivities - idx:Capex",
        "dependencies": ["ifrs:CashFlowsFromUsedInOperatingActivities", "idx:Capex"],
        "source_priority": ["FS_CORE_STATEMENT"],
        "synonyms_id": ["Arus Kas Bebas"],
        "synonyms_en": ["Free Cash Flow", "FCF"],
    },

    # =========================================================================
    # 4. SECTOR SPECIFIC — BANKING
    # =========================================================================
    {
        "metric_id": "idx:LoansAndAdvances",
        "name_en": "Total Loans and Advances (Gross)",
        "name_id": "Total Kredit yang Diberikan (Gross)",
        "category": "BALANCE_SHEET",
        "sector_applicability": ["BANK", "FINANCIALS"],
        "importance": "CRITICAL",
        "value_type": "MONETARY",
        "unit": "IDR",
        "flow_stock_type": "STOCK_POINT_IN_TIME",
        "extraction_mode": "EXTRACTED_RAW",
        "source_priority": ["FS_CORE_STATEMENT", "FS_NOTES_DETAIL"],
        "synonyms_id": ["Kredit yang Diberikan", "Pinjaman yang Disalurkan"],
        "synonyms_en": ["Loans and Advances", "Gross Loans"],
    },
    {
        "metric_id": "idx:CustomerDeposits",
        "name_en": "Customer Deposits (DPK)",
        "name_id": "Dana Pihak Ketiga (DPK)",
        "category": "BALANCE_SHEET",
        "sector_applicability": ["BANK", "FINANCIALS"],
        "importance": "CRITICAL",
        "value_type": "MONETARY",
        "unit": "IDR",
        "flow_stock_type": "STOCK_POINT_IN_TIME",
        "extraction_mode": "EXTRACTED_RAW",
        "source_priority": ["FS_CORE_STATEMENT", "FS_NOTES_DETAIL"],
        "synonyms_id": ["Simpanan Nasabah", "DPK Total"],
        "synonyms_en": ["Total Deposits", "Customer Deposits"],
    },
    {
        "metric_id": "idx:CASA",
        "name_en": "CASA (Current and Savings Account)",
        "name_id": "Dana Murah (CASA = Giro + Tabungan)",
        "category": "BALANCE_SHEET",
        "sector_applicability": ["BANK", "FINANCIALS"],
        "importance": "CRITICAL",
        "value_type": "MONETARY",
        "unit": "IDR",
        "flow_stock_type": "STOCK_POINT_IN_TIME",
        "extraction_mode": "CALCULATED_DETERMINISTIC",
        "calculation_formula": "idx:DemandDeposits + idx:SavingsDeposits",
        "dependencies": ["idx:DemandDeposits", "idx:SavingsDeposits"],
        "source_priority": ["FS_NOTES_DETAIL", "INVESTOR_PRESENTATION"],
        "synonyms_id": ["Saldo Giro dan Tabungan"],
        "synonyms_en": ["CASA Balances", "Low-Cost Funds"],
    },
    {
        "metric_id": "idx:CASARatio",
        "name_en": "CASA Ratio (%)",
        "name_id": "Rasio Dana Murah (CASA Ratio)",
        "category": "LIQUIDITY",
        "sector_applicability": ["BANK", "FINANCIALS"],
        "importance": "CRITICAL",
        "value_type": "PERCENTAGE",
        "unit": "PERCENT",
        "flow_stock_type": "RATIO",
        "extraction_mode": "HYBRID_FALLBACK",
        "calculation_formula": "(idx:CASA / idx:CustomerDeposits) * 100",
        "dependencies": ["idx:CASA", "idx:CustomerDeposits"],
        "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE", "FS_NOTES_DETAIL"],
        "synonyms_id": ["Rasio CASA", "Porsi Dana Murah terhadap DPK"],
        "synonyms_en": ["CASA Percentage", "CASA Ratio"],
    },
    {
        "metric_id": "idx:NetInterestMargin",
        "name_en": "Net Interest Margin (NIM %)",
        "name_id": "Margin Bunga Bersih (NIM)",
        "category": "PROFITABILITY",
        "sector_applicability": ["BANK", "FINANCIALS"],
        "importance": "CRITICAL",
        "value_type": "PERCENTAGE",
        "unit": "PERCENT",
        "flow_stock_type": "RATIO",
        "extraction_mode": "EXTRACTED_RAW",
        "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE", "ANNUAL_REPORT"],
        "synonyms_id": ["Marjin Bunga Bersih", "NIM"],
        "synonyms_en": ["NIM", "Net Interest Margin"],
    },
    {
        "metric_id": "idx:NonPerformingLoansGross",
        "name_en": "Non-Performing Loans (NPL Gross)",
        "name_id": "Kredit Bermasalah (NPL Gross)",
        "category": "ASSET_QUALITY",
        "sector_applicability": ["BANK", "FINANCIALS"],
        "importance": "CRITICAL",
        "value_type": "MONETARY",
        "unit": "IDR",
        "flow_stock_type": "STOCK_POINT_IN_TIME",
        "extraction_mode": "EXTRACTED_RAW",
        "source_priority": ["FS_NOTES_DETAIL", "INVESTOR_PRESENTATION"],
        "synonyms_id": ["Kredit Kol 3, 4, 5", "NPL Total"],
        "synonyms_en": ["Gross NPL", "Non-Performing Loans"],
    },
    {
        "metric_id": "idx:CapitalAdequacyRatio",
        "name_en": "Capital Adequacy Ratio (CAR %)",
        "name_id": "Rasio Kecukupan Modal (CAR / KPMM)",
        "category": "CAPITAL",
        "sector_applicability": ["BANK", "FINANCIALS"],
        "importance": "CRITICAL",
        "value_type": "PERCENTAGE",
        "unit": "PERCENT",
        "flow_stock_type": "RATIO",
        "extraction_mode": "EXTRACTED_RAW",
        "source_priority": ["FS_NOTES_DETAIL", "INVESTOR_PRESENTATION"],
        "synonyms_id": ["KPMM", "Rasio Permodalan", "CAR"],
        "synonyms_en": ["CAR", "Total Capital Adequacy Ratio"],
    },

    # =========================================================================
    # 5. SECTOR SPECIFIC — MINING & SMELTER
    # =========================================================================
    {
        "metric_id": "idx:CoalProductionVolume",
        "name_en": "Coal Production Volume (MT)",
        "name_id": "Volume Produksi Batubara (Juta Ton)",
        "category": "OPERATIONAL",
        "sector_applicability": ["MINING", "ENERGY", "COAL"],
        "importance": "CRITICAL",
        "value_type": "FLOAT",
        "unit": "MT",
        "flow_stock_type": "FLOW_PERIOD",
        "extraction_mode": "EXTRACTED_RAW",
        "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE", "FS_NOTES_DETAIL"],
        "synonyms_id": ["Produksi Batubara", "Realisasi Produksi"],
        "synonyms_en": ["Coal Production", "Run-of-Mine Production"],
    },
    {
        "metric_id": "idx:NickelOreProduction",
        "name_en": "Nickel Ore Production (WMT)",
        "name_id": "Volume Produksi Bijih Nikel (Saprolite & Limonite)",
        "category": "OPERATIONAL",
        "sector_applicability": ["MINING", "BASIC_MATERIALS", "NICKEL"],
        "importance": "CRITICAL",
        "value_type": "FLOAT",
        "unit": "WMT",
        "flow_stock_type": "FLOW_PERIOD",
        "extraction_mode": "EXTRACTED_RAW",
        "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE", "FS_NOTES_DETAIL"],
        "synonyms_id": ["Produksi Bijih Nikel", "Penambangan Saprolit/Limonit"],
        "synonyms_en": ["Nickel Ore Output", "Saprolite / Limonite Mined"],
    },
    {
        "metric_id": "idx:MHPProduction",
        "name_en": "MHP Output (Mixed Hydroxide Precipitate - Tonnes Ni)",
        "name_id": "Produksi MHP (Mixed Hydroxide Precipitate Nikel)",
        "category": "OPERATIONAL",
        "sector_applicability": ["MINING", "BASIC_MATERIALS", "NICKEL"],
        "importance": "CRITICAL",
        "value_type": "FLOAT",
        "unit": "TONNES_NI",
        "flow_stock_type": "FLOW_PERIOD",
        "extraction_mode": "EXTRACTED_RAW",
        "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE", "ANNUAL_REPORT"],
        "synonyms_id": ["Produksi MHP", "Nikel Hidroksida HPAL"],
        "synonyms_en": ["MHP Production", "Mixed Hydroxide Precipitate"],
    },
    {
        "metric_id": "idx:StripRatio",
        "name_en": "Strip Ratio (BCM/Ton)",
        "name_id": "Nisbah Kupas (Strip Ratio)",
        "category": "OPERATIONAL",
        "sector_applicability": ["MINING", "ENERGY", "COAL"],
        "importance": "CRITICAL",
        "value_type": "FLOAT",
        "unit": "BCM_PER_TON",
        "flow_stock_type": "RATIO",
        "extraction_mode": "EXTRACTED_RAW",
        "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE", "ANNUAL_REPORT"],
        "synonyms_id": ["Nisbah Kupas", "Rasio Pengupasan Tanah"],
        "synonyms_en": ["Strip Ratio", "Overburden to Coal Ratio"],
    },
    {
        "metric_id": "idx:MiningReservesMt",
        "name_en": "JORC Proved & Probable Reserves (MT)",
        "name_id": "Cadangan Tambang Terbukti & Terduga JORC (Juta Ton)",
        "category": "RESERVES",
        "sector_applicability": ["MINING", "ENERGY", "BASIC_MATERIALS"],
        "importance": "CRITICAL",
        "value_type": "FLOAT",
        "unit": "MT",
        "flow_stock_type": "STOCK_POINT_IN_TIME",
        "extraction_mode": "EXTRACTED_RAW",
        "source_priority": ["ANNUAL_REPORT", "INVESTOR_PRESENTATION"],
        "synonyms_id": ["Cadangan JORC", "Cadangan Terbukti"],
        "synonyms_en": ["Proved & Probable Reserves", "Mining Reserves"],
    },

    # =========================================================================
    # 6. SECTOR SPECIFIC — PALM OIL / CPO
    # =========================================================================
    {
        "metric_id": "idx:MaturePlantedArea",
        "name_en": "Mature Plantation Area (Hectares)",
        "name_id": "Luas Tanaman Menghasilkan (Mature Hektar)",
        "category": "OPERATIONAL",
        "sector_applicability": ["CPO", "AGRICULTURE"],
        "importance": "CRITICAL",
        "value_type": "FLOAT",
        "unit": "HECTARES",
        "flow_stock_type": "STOCK_POINT_IN_TIME",
        "extraction_mode": "EXTRACTED_RAW",
        "source_priority": ["FS_NOTES_DETAIL", "INVESTOR_PRESENTATION", "ANNUAL_REPORT"],
        "synonyms_id": ["Tanaman Menghasilkan", "TM", "Areal Menghasilkan"],
        "synonyms_en": ["Mature Area", "Mature Planted Hectares"],
    },
    {
        "metric_id": "idx:FfbProduction",
        "name_en": "Fresh Fruit Bunches (FFB) Production (Tonnes)",
        "name_id": "Produksi Tandan Buah Segar (TBS Ton)",
        "category": "OPERATIONAL",
        "sector_applicability": ["CPO", "AGRICULTURE"],
        "importance": "CRITICAL",
        "value_type": "FLOAT",
        "unit": "TONNES",
        "flow_stock_type": "FLOW_PERIOD",
        "extraction_mode": "EXTRACTED_RAW",
        "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE", "FS_NOTES_DETAIL"],
        "synonyms_id": ["Produksi TBS", "Tandan Buah Segar"],
        "synonyms_en": ["FFB Production", "Fresh Fruit Bunches Output"],
    },
    {
        "metric_id": "idx:OilExtractionRate",
        "name_en": "Oil Extraction Rate (OER %)",
        "name_id": "Tingkat Rendemen Minyak Sawit (OER %)",
        "category": "OPERATIONAL",
        "sector_applicability": ["CPO", "AGRICULTURE"],
        "importance": "CRITICAL",
        "value_type": "PERCENTAGE",
        "unit": "PERCENT",
        "flow_stock_type": "RATIO",
        "extraction_mode": "EXTRACTED_RAW",
        "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"],
        "synonyms_id": ["Rendemen CPO", "OER"],
        "synonyms_en": ["OER", "Oil Extraction Rate"],
    },

    # =========================================================================
    # 7. SECTOR SPECIFIC — PROPERTY
    # =========================================================================
    {
        "metric_id": "idx:MarketingSalesPresales",
        "name_en": "Marketing Sales / Presales",
        "name_id": "Pra-Penjualan / Marketing Sales Properti",
        "category": "OPERATIONAL",
        "sector_applicability": ["PROPERTY", "REAL_ESTATE"],
        "importance": "CRITICAL",
        "value_type": "MONETARY",
        "unit": "IDR",
        "flow_stock_type": "FLOW_PERIOD",
        "extraction_mode": "EXTRACTED_RAW",
        "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE", "IDX_DISCLOSURE"],
        "synonyms_id": ["Marketing Sales", "Realisasi Presales", "Pra-Penjualan"],
        "synonyms_en": ["Presales", "Marketing Sales"],
    },
    {
        "metric_id": "idx:TotalLandbankHectares",
        "name_en": "Total Landbank Area (Hectares)",
        "name_id": "Cadangan Lahan (Landbank Hektar)",
        "category": "RESERVES",
        "sector_applicability": ["PROPERTY", "REAL_ESTATE"],
        "importance": "CRITICAL",
        "value_type": "FLOAT",
        "unit": "HECTARES",
        "flow_stock_type": "STOCK_POINT_IN_TIME",
        "extraction_mode": "EXTRACTED_RAW",
        "source_priority": ["INVESTOR_PRESENTATION", "ANNUAL_REPORT", "FS_NOTES_DETAIL"],
        "synonyms_id": ["Cadangan Tanah", "Luas Landbank"],
        "synonyms_en": ["Landbank", "Undeveloped Land Area"],
    },

    # =========================================================================
    # 8. SECTOR SPECIFIC — TELECOMMUNICATIONS & HEALTHCARE
    # =========================================================================
    {
        "metric_id": "idx:DataTrafficPetabytes",
        "name_en": "Data Traffic Volume (Petabytes)",
        "name_id": "Volume Trafik Data (Petabytes)",
        "category": "OPERATIONAL",
        "sector_applicability": ["TELCO", "INFRASTRUCTURE"],
        "importance": "CRITICAL",
        "value_type": "FLOAT",
        "unit": "PETABYTES",
        "flow_stock_type": "FLOW_PERIOD",
        "extraction_mode": "EXTRACTED_RAW",
        "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"],
        "synonyms_id": ["Trafik Data", "Lalu Lintas Data"],
        "synonyms_en": ["Data Traffic", "Data Payload Volume"],
    },
    {
        "metric_id": "idx:OperationalBedsCount",
        "name_en": "Operational Beds Count",
        "name_id": "Jumlah Tempat Tidur Operasional Rumah Sakit",
        "category": "OPERATIONAL",
        "sector_applicability": ["HEALTHCARE", "HOSPITAL"],
        "importance": "CRITICAL",
        "value_type": "INTEGER",
        "unit": "BEDS",
        "flow_stock_type": "STOCK_POINT_IN_TIME",
        "extraction_mode": "EXTRACTED_RAW",
        "source_priority": ["INVESTOR_PRESENTATION", "FS_NOTES_DETAIL"],
        "synonyms_id": ["Kapasitas Tempat Tidur", "Beds Operasional"],
        "synonyms_en": ["Operational Beds", "Hospital Bed Capacity"],
    },

    # =========================================================================
    # 9. BANKING — GAP CLOSURE (LDR / BOPO / CIR / ROA / CoC / LAR / Coverage / PPOP)
    # =========================================================================
    {"metric_id": "idx:LoanToDepositRatio", "name_en": "Loan to Deposit Ratio (LDR %)", "name_id": "Rasio Kredit terhadap Simpanan (LDR)", "category": "LIQUIDITY", "sector_applicability": ["BANK", "FINANCIALS"], "importance": "CRITICAL", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "RATIO", "extraction_mode": "HYBRID_FALLBACK", "calculation_formula": "(idx:LoansAndAdvances / idx:CustomerDeposits) * 100", "dependencies": ["idx:LoansAndAdvances", "idx:CustomerDeposits"], "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE", "ANNUAL_REPORT"], "synonyms_id": ["LDR", "Rasio Pinjaman terhadap Simpanan"], "synonyms_en": ["LDR", "Loan-to-Deposit Ratio"]},
    {"metric_id": "idx:BOPO", "name_en": "Operating Expenses to Operating Income (BOPO %)", "name_id": "Rasio Beban Operasional terhadap Pendapatan Operasional (BOPO)", "category": "PROFITABILITY", "sector_applicability": ["BANK", "FINANCIALS"], "importance": "CRITICAL", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE", "ANNUAL_REPORT"], "synonyms_id": ["BOPO", "Rasio BOPO", "Efisiensi Bank"], "synonyms_en": ["Cost-to-Income Ratio (OJK definition)", "BOPO"]},
    {"metric_id": "idx:CostToIncomeRatio", "name_en": "Cost to Income Ratio (CIR %)", "name_id": "Rasio Biaya terhadap Pendapatan (CIR)", "category": "PROFITABILITY", "sector_applicability": ["BANK", "FINANCIALS"], "importance": "HIGH", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Rasio CIR", "Biaya Operasional/Pendapatan"], "synonyms_en": ["CIR", "Efficiency Ratio"]},
    {"metric_id": "idx:ReturnOnAssetsBank", "name_en": "Return on Assets (ROA %) — Banking", "name_id": "Imbal Hasil atas Aset (ROA) — OJK", "category": "PROFITABILITY", "sector_applicability": ["BANK", "FINANCIALS"], "importance": "CRITICAL", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["ROA Bank", "Rasio ROA"], "synonyms_en": ["ROA Bank (OJK)", "Return on Average Assets"]},
    {"metric_id": "idx:CostOfCredit", "name_en": "Cost of Credit (CoC %)", "name_id": "Rasio Biaya Kredit (CoC)", "category": "ASSET_QUALITY", "sector_applicability": ["BANK", "FINANCIALS"], "importance": "CRITICAL", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Biaya Kredit", "CoC", "Rasio Provisi terhadap Kredit"], "synonyms_en": ["Cost of Credit", "Provisioning Rate"]},
    {"metric_id": "idx:LoanAtRiskLAR", "name_en": "Loan at Risk (LAR %)", "name_id": "Rasio Loan at Risk (LAR)", "category": "ASSET_QUALITY", "sector_applicability": ["BANK", "FINANCIALS"], "importance": "HIGH", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["LAR", "Kredit Berisiko"], "synonyms_en": ["Loan at Risk", "LAR"]},
    {"metric_id": "idx:NPLCoverageRatio", "name_en": "NPL Coverage Ratio (%)", "name_id": "Rasio Cakupan NPL (Coverage)", "category": "ASSET_QUALITY", "sector_applicability": ["BANK", "FINANCIALS"], "importance": "CRITICAL", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Coverage Ratio", "Cakupan Pencadangan"], "synonyms_en": ["Provision Coverage", "NPL Coverage"]},
    {"metric_id": "idx:PPOP", "name_en": "Pre-Provision Operating Profit (PPOP)", "name_id": "Laba Operasional Sebelum Pencadangan (PPOP)", "category": "PROFITABILITY", "sector_applicability": ["BANK", "FINANCIALS"], "importance": "HIGH", "value_type": "MONETARY", "unit": "IDR", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "FS_CORE_STATEMENT"], "synonyms_id": ["PPOP", "Laba Operasi Sebelum CKPN"], "synonyms_en": ["Pre-Provision Profit", "PPOP"]},

    # =========================================================================
    # 10. COAL / NICKEL / CPO — GAP CLOSURE (ASP, Cash Cost, DMO, FeNi, PK)
    # =========================================================================
    {"metric_id": "idx:CoalAveragePriceASP", "name_en": "Coal Average Selling Price (ASP USD/ton)", "name_id": "Harga Jual Rata-Rata Batubara (ASP)", "category": "OPERATIONAL", "sector_applicability": ["COAL", "MINING", "ENERGY"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "USD_PER_TON", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["ASP Batubara", "Harga Jual Rata-Rata"], "synonyms_en": ["Blended ASP", "Realized Coal Price"]},
    {"metric_id": "idx:CoalCashCostPerTon", "name_en": "Coal Cash Cost per Ton (USD/ton)", "name_id": "Biaya Kas per Ton Batubara", "category": "OPERATIONAL", "sector_applicability": ["COAL", "MINING", "ENERGY"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "USD_PER_TON", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Cash Cost", "Biaya Tunai per Ton"], "synonyms_en": ["Cash Cost", "Unit Production Cost"]},
    {"metric_id": "idx:OverburdenRemoval", "name_en": "Overburden Removal Volume (BCM)", "name_id": "Volume Pengupasan Tanah Penutup (BCM)", "category": "OPERATIONAL", "sector_applicability": ["COAL", "MINING", "ENERGY"], "importance": "HIGH", "value_type": "FLOAT", "unit": "BCM", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Pengupasan OB", "Volume OB"], "synonyms_en": ["Overburden Removed", "OB Volume"]},
    {"metric_id": "idx:DomesticMarketObligationRatio", "name_en": "DMO Realization Ratio (%)", "name_id": "Realisasi Kewajiban Pasar Domestik (DMO)", "category": "OPERATIONAL", "sector_applicability": ["COAL", "MINING", "ENERGY"], "importance": "HIGH", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE", "ANNUAL_REPORT"], "synonyms_id": ["DMO", "Alokasi Domestik"], "synonyms_en": ["DMO Compliance", "Domestic Market Obligation"]},
    {"metric_id": "idx:FerroNickelOutput", "name_en": "FeNi Output (Tonnes Ni)", "name_id": "Produksi Feronikel (Ton Ni)", "category": "OPERATIONAL", "sector_applicability": ["NICKEL", "MINING", "BASIC_MATERIALS"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "TONNES_NI", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Feronikel", "Produksi FeNi"], "synonyms_en": ["FeNi Production", "Ferronickel"]},
    {"metric_id": "idx:NickelCashCostPerTon", "name_en": "Nickel Cash Cost (USD/t Ni)", "name_id": "Biaya Kas per Ton Nikel", "category": "OPERATIONAL", "sector_applicability": ["NICKEL", "MINING", "BASIC_MATERIALS"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "USD_PER_TON", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Cash Cost Nikel", "Biaya Produksi Nikel"], "synonyms_en": ["Nickel Cash Cost", "C1 Cost"]},
    {"metric_id": "idx:SmelterUtilizationRate", "name_en": "Smelter Utilization Rate (%)", "name_id": "Tingkat Utilisasi Smelter", "category": "OPERATIONAL", "sector_applicability": ["NICKEL", "MINING", "BASIC_MATERIALS"], "importance": "HIGH", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Utilisasi Pabrik Peleburan", "Load Factor Smelter"], "synonyms_en": ["Smelter Utilization", "Furnace Utilization"]},
    {"metric_id": "idx:CPOProductionVolume", "name_en": "CPO Production Volume (Tonnes)", "name_id": "Produksi CPO (Ton)", "category": "OPERATIONAL", "sector_applicability": ["CPO", "AGRICULTURE"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "TONNES", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Produksi CPO", "Realisasi CPO"], "synonyms_en": ["CPO Output", "Crude Palm Oil Production"]},
    {"metric_id": "idx:PalmKernelProduction", "name_en": "Palm Kernel Production (Tonnes)", "name_id": "Produksi Inti Sawit (Ton)", "category": "OPERATIONAL", "sector_applicability": ["CPO", "AGRICULTURE"], "importance": "MEDIUM", "value_type": "FLOAT", "unit": "TONNES", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Inti Sawit", "PK"], "synonyms_en": ["PK Production", "Palm Kernel"]},
    {"metric_id": "idx:CPOAveragePriceASP", "name_en": "CPO Average Selling Price (IDR/kg)", "name_id": "Harga Jual Rata-Rata CPO (ASP)", "category": "OPERATIONAL", "sector_applicability": ["CPO", "AGRICULTURE"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "IDR_PER_KG", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["ASP CPO", "Harga Realisasi CPO"], "synonyms_en": ["Realized CPO Price", "CPO ASP"]},
    {"metric_id": "idx:CPOCashCostPerKg", "name_en": "CPO Cash Cost per Kg (IDR/kg)", "name_id": "Biaya Kas per Kg CPO", "category": "OPERATIONAL", "sector_applicability": ["CPO", "AGRICULTURE"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "IDR_PER_KG", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Cash Cost CPO", "Biaya Produksi CPO"], "synonyms_en": ["CPO Cash Cost", "Unit Production Cost"]},

    # =========================================================================
    # 11. PROPERTY / TELCO / TOWER / HOSPITAL — GAP CLOSURE
    # =========================================================================
    {"metric_id": "idx:RecurringIncomeShare", "name_en": "Recurring Income Contribution (%)", "name_id": "Kontribusi Pendapatan Berulang", "category": "OPERATIONAL", "sector_applicability": ["PROPERTY", "REAL_ESTATE"], "importance": "CRITICAL", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Pendapatan Berulang", "Recurring Revenue"], "synonyms_en": ["Recurring Income %", "Investment Property Revenue Share"]},
    {"metric_id": "idx:MallOccupancyRate", "name_en": "Mall Occupancy Rate (%)", "name_id": "Tingkat Hunian Mall / Pusat Perbelanjaan", "category": "OPERATIONAL", "sector_applicability": ["PROPERTY", "REAL_ESTATE"], "importance": "CRITICAL", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Occupancy Mall", "Tingkat Keterisian Mall"], "synonyms_en": ["Mall Occupancy", "Retail Space Occupancy"]},
    {"metric_id": "idx:UnrecognizedRevenueBacklog", "name_en": "Unrecognized Revenue / Sales Backlog (IDR)", "name_id": "Pendapatan Diterima Dimuka / Backlog Penjualan", "category": "OPERATIONAL", "sector_applicability": ["PROPERTY", "REAL_ESTATE"], "importance": "CRITICAL", "value_type": "MONETARY", "unit": "IDR", "flow_stock_type": "STOCK_POINT_IN_TIME", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["FS_NOTES_DETAIL", "INVESTOR_PRESENTATION"], "synonyms_id": ["Uang Muka Pelanggan", "Advance from Customers", "Backlog Presales"], "synonyms_en": ["Sales Backlog", "Unrecognized Revenue"]},
    {"metric_id": "idx:BlendedARPU", "name_en": "Blended ARPU (IDR/month)", "name_id": "Rata-Rata Pendapatan per Pelanggan (Blended ARPU)", "category": "OPERATIONAL", "sector_applicability": ["TELCO", "INFRASTRUCTURE"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "IDR_PER_USER_MONTH", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["ARPU", "Rata-Rata Pendapatan per Pelanggan"], "synonyms_en": ["ARPU", "Blended ARPU"]},
    {"metric_id": "idx:MobileSubscribers", "name_en": "Mobile Subscriber Base", "name_id": "Jumlah Pelanggan Seluler", "category": "OPERATIONAL", "sector_applicability": ["TELCO", "INFRASTRUCTURE"], "importance": "CRITICAL", "value_type": "INTEGER", "unit": "USERS", "flow_stock_type": "STOCK_POINT_IN_TIME", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Total Pelanggan", "Basis Pelanggan"], "synonyms_en": ["Subscriber Base", "Total Subscribers"]},
    {"metric_id": "idx:TowerCount", "name_en": "Total Owned Towers", "name_id": "Jumlah Menara Telekomunikasi", "category": "OPERATIONAL", "sector_applicability": ["TOWER", "TELCO", "INFRASTRUCTURE"], "importance": "CRITICAL", "value_type": "INTEGER", "unit": "SITES", "flow_stock_type": "STOCK_POINT_IN_TIME", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Jumlah Menara", "Menara BTS"], "synonyms_en": ["Tower Count", "Owned Sites"]},
    {"metric_id": "idx:TenancyRatio", "name_en": "Tenancy Ratio (Tenants per Tower)", "name_id": "Rasio Kolokasi Penyewa per Menara", "category": "OPERATIONAL", "sector_applicability": ["TOWER", "TELCO", "INFRASTRUCTURE"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "RATIO", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Rasio Kolokasi", "Tenancy Ratio"], "synonyms_en": ["Tenancy Ratio", "Collocation Ratio"]},
    {"metric_id": "idx:BedOccupancyRate", "name_en": "Bed Occupancy Rate (BOR %)", "name_id": "Tingkat Hunian Tempat Tidur (BOR)", "category": "OPERATIONAL", "sector_applicability": ["HOSPITAL", "HEALTHCARE"], "importance": "CRITICAL", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["BOR", "Utilisasi Tempat Tidur"], "synonyms_en": ["BOR", "Bed Occupancy Rate"]},
    {"metric_id": "idx:AverageLengthOfStay", "name_en": "Average Length of Stay (ALOS days)", "name_id": "Rata-Rata Lama Perawatan (ALOS Hari)", "category": "OPERATIONAL", "sector_applicability": ["HOSPITAL", "HEALTHCARE"], "importance": "HIGH", "value_type": "FLOAT", "unit": "DAYS", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "ANNUAL_REPORT"], "synonyms_id": ["ALOS", "Rata-Rata Lama Rawat Inap"], "synonyms_en": ["ALOS", "Length of Stay"]},
    {"metric_id": "idx:InpatientAdmissions", "name_en": "Inpatient Admissions (Cases)", "name_id": "Jumlah Pasien Rawat Inap", "category": "OPERATIONAL", "sector_applicability": ["HOSPITAL", "HEALTHCARE"], "importance": "CRITICAL", "value_type": "INTEGER", "unit": "PATIENTS", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Pasien Rawat Inap", "Admisi IP"], "synonyms_en": ["Inpatient Admissions", "IP Cases"]},
    {"metric_id": "idx:OutpatientVisits", "name_en": "Outpatient Visits", "name_id": "Jumlah Kunjungan Rawat Jalan", "category": "OPERATIONAL", "sector_applicability": ["HOSPITAL", "HEALTHCARE"], "importance": "CRITICAL", "value_type": "INTEGER", "unit": "VISITS", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Kunjungan Rawat Jalan", "OP Visits"], "synonyms_en": ["OP Visits", "Outpatient Consultations"]},
    {"metric_id": "idx:ARPOB", "name_en": "Average Revenue per Occupied Bed-Day (ARPOB)", "name_id": "Pendapatan Rata-Rata per Bed Terisi", "category": "OPERATIONAL", "sector_applicability": ["HOSPITAL", "HEALTHCARE"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "IDR_PER_BED_DAY", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["ARPOB", "Pendapatan per Bed-Day"], "synonyms_en": ["ARPOB", "Revenue per Bed-Day"]},
    {"metric_id": "idx:BPJSRevenueShare", "name_en": "BPJS Revenue Contribution (%)", "name_id": "Kontribusi Pendapatan dari BPJS Kesehatan", "category": "OPERATIONAL", "sector_applicability": ["HOSPITAL", "HEALTHCARE", "PHARMACEUTICAL"], "importance": "HIGH", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "ANNUAL_REPORT"], "synonyms_id": ["Porsi BPJS", "Kontribusi JKN"], "synonyms_en": ["BPJS Share", "JKN Contribution"]},

    # =========================================================================
    # 12. SHIPPING / LOGISTICS — NEW SECTOR
    # =========================================================================
    {"metric_id": "idx:FleetCount", "name_en": "Total Fleet Count (Vessels)", "name_id": "Jumlah Armada Kapal", "category": "OPERATIONAL", "sector_applicability": ["SHIPPING", "LOGISTICS"], "importance": "CRITICAL", "value_type": "INTEGER", "unit": "VESSELS", "flow_stock_type": "STOCK_POINT_IN_TIME", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "ANNUAL_REPORT"], "synonyms_id": ["Jumlah Kapal", "Armada"], "synonyms_en": ["Fleet Size", "Vessel Count"]},
    {"metric_id": "idx:TotalDWT", "name_en": "Total Deadweight Tonnage (DWT)", "name_id": "Total Bobot Mati Armada (DWT)", "category": "OPERATIONAL", "sector_applicability": ["SHIPPING", "LOGISTICS"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "DWT", "flow_stock_type": "STOCK_POINT_IN_TIME", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "ANNUAL_REPORT"], "synonyms_id": ["Bobot Mati Armada", "Kapasitas Angkut"], "synonyms_en": ["DWT", "Total Deadweight"]},
    {"metric_id": "idx:CharterRate", "name_en": "Time Charter Equivalent Rate (USD/day)", "name_id": "Tarif Sewa Setara Waktu (TCE)", "category": "OPERATIONAL", "sector_applicability": ["SHIPPING", "LOGISTICS"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "USD_PER_DAY", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["TCE", "Charter Rate", "Tarif Sewa Kapal"], "synonyms_en": ["TCE", "Charter Rate"]},
    {"metric_id": "idx:BunkerFuelCost", "name_en": "Bunker Fuel Cost (USD/ton)", "name_id": "Biaya Bahan Bakar Bunker", "category": "OPERATIONAL", "sector_applicability": ["SHIPPING", "LOGISTICS"], "importance": "HIGH", "value_type": "FLOAT", "unit": "USD_PER_TON", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Biaya BBM Kapal", "Bunker"], "synonyms_en": ["Bunker Cost", "VLSFO/MGO Price"]},
    {"metric_id": "idx:VesselUtilization", "name_en": "Vessel Utilization Rate (%)", "name_id": "Tingkat Utilisasi Kapal", "category": "OPERATIONAL", "sector_applicability": ["SHIPPING", "LOGISTICS"], "importance": "HIGH", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "ANNUAL_REPORT"], "synonyms_id": ["Utilisasi Armada", "Laden Days"], "synonyms_en": ["Vessel Utilization", "Fleet Utilization"]},

    # =========================================================================
    # 13. RENEWABLE ENERGY & GEOTHERMAL — NEW SECTOR (BREN, PGEO, KEEN, ARKO, POWR)
    # =========================================================================
    {"metric_id": "idx:InstalledCapacityMW", "name_en": "Installed Capacity (MW)", "name_id": "Kapasitas Terpasang (MW)", "category": "OPERATIONAL", "sector_applicability": ["RENEWABLE_ENERGY", "UTILITIES", "INFRASTRUCTURE"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "MW", "flow_stock_type": "STOCK_POINT_IN_TIME", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE", "ANNUAL_REPORT"], "synonyms_id": ["Kapasitas Terpasang", "Kapasitas Pembangkit"], "synonyms_en": ["Installed Capacity", "Nameplate Capacity"]},
    {"metric_id": "idx:NetGenerationGWh", "name_en": "Net Electricity Generation (GWh)", "name_id": "Produksi Listrik Neto (GWh)", "category": "OPERATIONAL", "sector_applicability": ["RENEWABLE_ENERGY", "UTILITIES"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "GWH", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Produksi Listrik", "Energi yang Disalurkan"], "synonyms_en": ["Net Generation", "Electricity Dispatched"]},
    {"metric_id": "idx:CapacityFactor", "name_en": "Capacity Factor (%)", "name_id": "Faktor Kapasitas Pembangkit", "category": "OPERATIONAL", "sector_applicability": ["RENEWABLE_ENERGY", "UTILITIES"], "importance": "CRITICAL", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "RATIO", "extraction_mode": "HYBRID_FALLBACK", "calculation_formula": "(idx:NetGenerationGWh / (idx:InstalledCapacityMW * 8.76)) * 100", "dependencies": ["idx:NetGenerationGWh", "idx:InstalledCapacityMW"], "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Load Factor", "Faktor Beban"], "synonyms_en": ["Capacity Factor", "Load Factor", "Availability Factor"]},
    {"metric_id": "idx:RealizedElectricityTariff", "name_en": "Realized Electricity Tariff (USD/kWh)", "name_id": "Tarif Listrik Terealisasi (per kWh)", "category": "OPERATIONAL", "sector_applicability": ["RENEWABLE_ENERGY", "UTILITIES"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "USD_PER_KWH", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Tarif Realisasi", "Harga Jual per kWh"], "synonyms_en": ["Realized Tariff", "PPA Rate"]},
    {"metric_id": "idx:SteamProductionTonnes", "name_en": "Steam Production (Tonnes)", "name_id": "Produksi Uap Panas Bumi (Ton)", "category": "OPERATIONAL", "sector_applicability": ["RENEWABLE_ENERGY", "UTILITIES"], "importance": "HIGH", "value_type": "FLOAT", "unit": "TONNES", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "ANNUAL_REPORT"], "synonyms_id": ["Produksi Uap", "Steam Output"], "synonyms_en": ["Steam Production", "Geothermal Steam Output"]},
    {"metric_id": "idx:ProvenGeothermalReservesMWe", "name_en": "Proven Geothermal Reserves (MWe)", "name_id": "Cadangan Panas Bumi Terbukti (MWe)", "category": "RESERVES", "sector_applicability": ["RENEWABLE_ENERGY", "UTILITIES"], "importance": "HIGH", "value_type": "FLOAT", "unit": "MW", "flow_stock_type": "STOCK_POINT_IN_TIME", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["ANNUAL_REPORT", "INVESTOR_PRESENTATION"], "synonyms_id": ["Cadangan Panas Bumi", "Reservoir Terbukti"], "synonyms_en": ["Proven Geothermal Resources", "Geothermal Reserves"]},

    # =========================================================================
    # 14. OIL & GAS E&P, DRILLING & EPC — NEW SECTOR (MEDC, ENRG, ELSA, RAJA)
    # =========================================================================
    {"metric_id": "idx:ProvedReserves2P", "name_en": "2P Reserves (MMBOE)", "name_id": "Cadangan Terbukti + Terduga (2P)", "category": "RESERVES", "sector_applicability": ["OIL_GAS", "ENERGY"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "MMBOE", "flow_stock_type": "STOCK_POINT_IN_TIME", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["ANNUAL_REPORT", "INVESTOR_PRESENTATION"], "synonyms_id": ["Cadangan 2P", "P1+P2"], "synonyms_en": ["2P Reserves", "Proved + Probable Reserves"]},
    {"metric_id": "idx:OilProductionBOPD", "name_en": "Oil Production (BOPD)", "name_id": "Produksi Minyak (Barrel per Hari)", "category": "OPERATIONAL", "sector_applicability": ["OIL_GAS", "ENERGY"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "BOPD", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Produksi Minyak", "Lifting Minyak"], "synonyms_en": ["Oil Production", "Crude Lifting"]},
    {"metric_id": "idx:GasProductionMMSCFD", "name_en": "Gas Production (MMSCFD)", "name_id": "Produksi Gas (Juta Kaki Kubik per Hari)", "category": "OPERATIONAL", "sector_applicability": ["OIL_GAS", "ENERGY"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "MMSCFD", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Produksi Gas Alam", "Gas Bumi"], "synonyms_en": ["Gas Production", "Natural Gas Output"]},
    {"metric_id": "idx:LiftingCostPerBOE", "name_en": "Lifting Cost per BOE (USD/BOE)", "name_id": "Biaya Angkat per BOE", "category": "OPERATIONAL", "sector_applicability": ["OIL_GAS", "ENERGY"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "USD_PER_BOE", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Biaya Produksi per BOE", "Lifting Cost"], "synonyms_en": ["Lifting Cost", "Cash Operating Cost"]},
    {"metric_id": "idx:RealizedICP", "name_en": "Realized Oil Price (ICP USD/bbl)", "name_id": "Harga Jual Realisasi Minyak (ICP)", "category": "OPERATIONAL", "sector_applicability": ["OIL_GAS", "ENERGY"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "USD_PER_BBL", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["ICP", "Harga Minyak Realisasi"], "synonyms_en": ["Realized ICP", "Realized Oil Price"]},
    {"metric_id": "idx:RealizedGasASP", "name_en": "Realized Gas ASP (USD/MMBTU)", "name_id": "Harga Jual Rata-Rata Gas (USD/MMBTU)", "category": "OPERATIONAL", "sector_applicability": ["OIL_GAS", "ENERGY"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "USD_PER_MMBTU", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["ASP Gas", "Harga Gas Realisasi"], "synonyms_en": ["Realized Gas Price", "Gas ASP"]},
    {"metric_id": "idx:RigUtilization", "name_en": "Rig Utilization Rate (%)", "name_id": "Utilisasi Rig Pengeboran", "category": "OPERATIONAL", "sector_applicability": ["OIL_GAS", "ENERGY"], "importance": "CRITICAL", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Utilisasi Rig", "Tingkat Pemakaian Rig"], "synonyms_en": ["Rig Utilization", "Fleet Utilization"]},
    {"metric_id": "idx:ReserveReplacementRatio", "name_en": "Reserve Replacement Ratio (RRR %)", "name_id": "Rasio Pengganti Cadangan (RRR)", "category": "RESERVES", "sector_applicability": ["OIL_GAS", "ENERGY"], "importance": "HIGH", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["ANNUAL_REPORT", "INVESTOR_PRESENTATION"], "synonyms_id": ["RRR", "Rasio Pengganti Cadangan"], "synonyms_en": ["RRR", "Reserve Replacement Ratio"]},

    # =========================================================================
    # 15. AUTOMOTIVE & EV — NEW SECTOR (ASII, AUTO, DRMA, SMSM, VKTR)
    # =========================================================================
    {"metric_id": "idx:CarWholesaleUnits", "name_en": "4W Car Wholesale Unit Sales", "name_id": "Penjualan Mobil (Wholesale, Unit)", "category": "OPERATIONAL", "sector_applicability": ["AUTOMOTIVE", "INDUSTRIALS"], "importance": "CRITICAL", "value_type": "INTEGER", "unit": "UNITS", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Penjualan Mobil Wholesale", "Penjualan Unit 4W"], "synonyms_en": ["4W Wholesale Sales", "Car Wholesale Volume"]},
    {"metric_id": "idx:CarRetailUnits", "name_en": "4W Car Retail Unit Sales", "name_id": "Penjualan Mobil Retail (Unit)", "category": "OPERATIONAL", "sector_applicability": ["AUTOMOTIVE", "INDUSTRIALS"], "importance": "CRITICAL", "value_type": "INTEGER", "unit": "UNITS", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Penjualan Retail Mobil"], "synonyms_en": ["Retail Sales 4W", "Car Retail Units"]},
    {"metric_id": "idx:MotorcycleUnitSales", "name_en": "2W Motorcycle Unit Sales", "name_id": "Penjualan Sepeda Motor (Unit)", "category": "OPERATIONAL", "sector_applicability": ["AUTOMOTIVE", "INDUSTRIALS"], "importance": "CRITICAL", "value_type": "INTEGER", "unit": "UNITS", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Penjualan 2W", "Unit Motor Terjual"], "synonyms_en": ["2W Sales", "Motorcycle Sales"]},
    {"metric_id": "idx:MarketShareGaikindo", "name_en": "Market Share (Gaikindo/AISI %)", "name_id": "Pangsa Pasar Otomotif", "category": "OPERATIONAL", "sector_applicability": ["AUTOMOTIVE", "INDUSTRIALS"], "importance": "CRITICAL", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Pangsa Pasar", "Market Share"], "synonyms_en": ["Market Share", "Sales Share"]},
    {"metric_id": "idx:ExportVolumeUnits", "name_en": "Automotive Export Volume (CBU Units)", "name_id": "Volume Ekspor Kendaraan (CBU)", "category": "OPERATIONAL", "sector_applicability": ["AUTOMOTIVE", "INDUSTRIALS"], "importance": "HIGH", "value_type": "INTEGER", "unit": "UNITS", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Ekspor CBU", "Volume Ekspor Mobil"], "synonyms_en": ["CBU Exports", "Export Volume"]},
    {"metric_id": "idx:EVModelMixShare", "name_en": "EV/HEV Share of Sales Mix (%)", "name_id": "Kontribusi Mobil Elektrifikasi (BEV/HEV) dalam Bauran Penjualan", "category": "OPERATIONAL", "sector_applicability": ["AUTOMOTIVE", "INDUSTRIALS"], "importance": "HIGH", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Porsi Kendaraan Listrik", "Kontribusi BEV/HEV"], "synonyms_en": ["EV Mix", "Electrified Sales Share"]},
    {"metric_id": "idx:ComponentContentPerVehicle", "name_en": "Component Content per Vehicle (IDR/unit)", "name_id": "Kandungan Komponen per Kendaraan", "category": "OPERATIONAL", "sector_applicability": ["AUTOMOTIVE", "INDUSTRIALS"], "importance": "MEDIUM", "value_type": "FLOAT", "unit": "IDR_PER_UNIT", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "ANNUAL_REPORT"], "synonyms_id": ["Content per Unit", "Kandungan Komponen"], "synonyms_en": ["Content per Vehicle", "$/Vehicle"]},

    # =========================================================================
    # 16. CONSUMER STAPLES / POULTRY / FEED — NEW SECTOR (ICBP, INDF, MYOR, CPIN, JPFA, MAIN, CMRY)
    # =========================================================================
    {"metric_id": "idx:FeedMillSalesVolumeMT", "name_en": "Feedmill Sales Volume (Tonnes)", "name_id": "Volume Penjualan Pakan Ternak (Ton)", "category": "OPERATIONAL", "sector_applicability": ["POULTRY", "CONSUMER_STAPLES"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "TONNES", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Volume Pakan", "Penjualan Pakan"], "synonyms_en": ["Feed Sales Volume", "Feedmill Output"]},
    {"metric_id": "idx:DayOldChickVolume", "name_en": "Day-Old-Chick (DOC) Sales Volume (Millions)", "name_id": "Volume Penjualan Ayam Umur Sehari (DOC, Juta Ekor)", "category": "OPERATIONAL", "sector_applicability": ["POULTRY", "CONSUMER_STAPLES"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "MILLIONS_HEADS", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["DOC", "Bibit Ayam"], "synonyms_en": ["DOC Sales", "Day-Old Chick Volume"]},
    {"metric_id": "idx:DOCFarmgatePrice", "name_en": "DOC Farmgate Price (IDR/head)", "name_id": "Harga DOC di Tingkat Peternak", "category": "OPERATIONAL", "sector_applicability": ["POULTRY", "CONSUMER_STAPLES"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "IDR_PER_HEAD", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Harga DOC", "Harga Bibit Ayam"], "synonyms_en": ["DOC Price", "Day-Old Chick Farmgate Price"]},
    {"metric_id": "idx:LiveBirdPriceIDR", "name_en": "Commercial Live Bird Price (IDR/kg)", "name_id": "Harga Ayam Hidup di Peternak (IDR/kg)", "category": "OPERATIONAL", "sector_applicability": ["POULTRY", "CONSUMER_STAPLES"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "IDR_PER_KG", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Harga Ayam Hidup", "Harga Broiler"], "synonyms_en": ["Live Bird Price", "Broiler Farmgate Price"]},
    {"metric_id": "idx:RawMaterialExposureSoyCorn", "name_en": "Raw Material Cost Exposure (Soybean/Corn %)", "name_id": "Eksposur Biaya Bahan Baku (Kedelai/Jagung)", "category": "OPERATIONAL", "sector_applicability": ["POULTRY", "CONSUMER_STAPLES"], "importance": "HIGH", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "ANNUAL_REPORT"], "synonyms_id": ["Kontribusi Bahan Baku", "Porsi Jagung/SBM"], "synonyms_en": ["Feed Raw Material Mix", "SBM/Corn Share"]},
    {"metric_id": "idx:BrandedFoodVolumeMT", "name_en": "Branded Food Sales Volume (Tonnes/Cartons)", "name_id": "Volume Penjualan Produk Bermerek", "category": "OPERATIONAL", "sector_applicability": ["CONSUMER_STAPLES", "CONSUMER"], "importance": "HIGH", "value_type": "FLOAT", "unit": "TONNES", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Volume Penjualan", "Penjualan Kuantitas"], "synonyms_en": ["Volume Sales", "Unit Sales"]},
    {"metric_id": "idx:VolumePriceMixDecomp", "name_en": "Volume vs Price Growth Decomposition (%)", "name_id": "Dekomposisi Pertumbuhan (Volume vs Harga)", "category": "OPERATIONAL", "sector_applicability": ["CONSUMER_STAPLES", "CONSUMER"], "importance": "HIGH", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Volume Growth vs Price Growth"], "synonyms_en": ["Volume/Price Split", "Growth Decomposition"]},

    # =========================================================================
    # 17. RETAIL — NEW SECTOR (AMRT, MIDI, ACES, MAPI, ERAA, RALS, LPPF)
    # =========================================================================
    {"metric_id": "idx:SameStoreSalesGrowth", "name_en": "Same-Store Sales Growth (SSSG %)", "name_id": "Pertumbuhan Penjualan Toko yang Sudah Ada (SSSG)", "category": "OPERATIONAL", "sector_applicability": ["RETAIL", "CONSUMER"], "importance": "CRITICAL", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["SSSG", "Pertumbuhan Toko Same-Store"], "synonyms_en": ["SSSG", "Comparable Sales Growth", "LFL Growth"]},
    {"metric_id": "idx:SalesPerSquareMeter", "name_en": "Sales Density (Sales per Sqm)", "name_id": "Penjualan per Meter Persegi", "category": "OPERATIONAL", "sector_applicability": ["RETAIL", "CONSUMER"], "importance": "HIGH", "value_type": "FLOAT", "unit": "IDR_PER_M2", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "ANNUAL_REPORT"], "synonyms_id": ["Penjualan per m2", "Sales Density"], "synonyms_en": ["Sales/Sqm", "Sales Density"]},
    {"metric_id": "idx:TotalStoreCount", "name_en": "Total Store Count", "name_id": "Jumlah Total Toko", "category": "OPERATIONAL", "sector_applicability": ["RETAIL", "CONSUMER"], "importance": "CRITICAL", "value_type": "INTEGER", "unit": "STORES", "flow_stock_type": "STOCK_POINT_IN_TIME", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Total Gerai", "Jumlah Toko"], "synonyms_en": ["Store Count", "Number of Outlets"]},
    {"metric_id": "idx:NetNewStoreOpenings", "name_en": "Net New Store Openings", "name_id": "Pembukaan Toko Baru Neto", "category": "OPERATIONAL", "sector_applicability": ["RETAIL", "CONSUMER"], "importance": "HIGH", "value_type": "INTEGER", "unit": "STORES", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Toko Baru", "Ekspansi Gerai"], "synonyms_en": ["New Store Openings", "Net Store Additions"]},
    {"metric_id": "idx:InventoryDays", "name_en": "Inventory Days (DIO)", "name_id": "Rata-Rata Hari Persediaan", "category": "LIQUIDITY", "sector_applicability": ["RETAIL", "CONSUMER", "CONSUMER_STAPLES"], "importance": "HIGH", "value_type": "FLOAT", "unit": "DAYS", "flow_stock_type": "RATIO", "extraction_mode": "CALCULATED_DETERMINISTIC", "calculation_formula": "(ifrs:Inventories / ifrs:CostOfSales) * 365", "dependencies": ["ifrs:Inventories", "ifrs:CostOfSales"], "source_priority": ["FS_CORE_STATEMENT", "FS_NOTES_DETAIL"], "synonyms_id": ["DIO", "Perputaran Persediaan (Hari)"], "synonyms_en": ["Days Inventory Outstanding", "Inventory Turnover Days"]},
    {"metric_id": "idx:PrivateLabelShare", "name_en": "Private Label Sales Share (%)", "name_id": "Kontribusi Produk Merek Sendiri (Private Label)", "category": "OPERATIONAL", "sector_applicability": ["RETAIL", "CONSUMER"], "importance": "MEDIUM", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "ANNUAL_REPORT"], "synonyms_id": ["Merek Sendiri", "Private Label"], "synonyms_en": ["Private Label Share", "Own-Brand Contribution"]},
    {"metric_id": "idx:AverageTicketSize", "name_en": "Average Basket / Ticket Size (IDR)", "name_id": "Rata-Rata Nilai Transaksi per Pelanggan", "category": "OPERATIONAL", "sector_applicability": ["RETAIL", "CONSUMER"], "importance": "MEDIUM", "value_type": "FLOAT", "unit": "IDR", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Nilai Transaksi Rata-Rata", "ATV"], "synonyms_en": ["Average Transaction Value", "Basket Size"]},

    # =========================================================================
    # 18. PHARMACEUTICAL — NEW SECTOR (KLBF, SIDO, TSPC, DVLA, PYFA)
    # =========================================================================
    {"metric_id": "idx:EthicalRevenueShare", "name_en": "Ethical (Prescription) Revenue Share (%)", "name_id": "Porsi Pendapatan Obat Resep (Ethical)", "category": "OPERATIONAL", "sector_applicability": ["PHARMACEUTICAL", "HEALTHCARE"], "importance": "HIGH", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "ANNUAL_REPORT"], "synonyms_id": ["Obat Ethical", "Resep Dokter"], "synonyms_en": ["Prescription Drug Share", "Ethical Share"]},
    {"metric_id": "idx:OTCRevenueShare", "name_en": "OTC (Over-the-Counter) Revenue Share (%)", "name_id": "Porsi Pendapatan Obat Bebas (OTC)", "category": "OPERATIONAL", "sector_applicability": ["PHARMACEUTICAL", "HEALTHCARE"], "importance": "HIGH", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "ANNUAL_REPORT"], "synonyms_id": ["Obat Bebas", "OTC"], "synonyms_en": ["OTC Share", "Consumer Health Share"]},
    {"metric_id": "idx:APIImportExposure", "name_en": "API Import Exposure (USD %)", "name_id": "Eksposur Impor Bahan Baku Obat (API)", "category": "OPERATIONAL", "sector_applicability": ["PHARMACEUTICAL", "HEALTHCARE"], "importance": "HIGH", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["ANNUAL_REPORT", "INVESTOR_PRESENTATION"], "synonyms_id": ["Impor Bahan Baku Obat", "API USD"], "synonyms_en": ["API Import Exposure", "USD Raw Material Cost"]},
    {"metric_id": "idx:TollManufacturingVolume", "name_en": "Toll/Contract Manufacturing Volume (Units)", "name_id": "Volume Produksi Kontrak (Toll Manufacturing)", "category": "OPERATIONAL", "sector_applicability": ["PHARMACEUTICAL", "HEALTHCARE"], "importance": "MEDIUM", "value_type": "FLOAT", "unit": "UNITS", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["ANNUAL_REPORT", "INVESTOR_PRESENTATION"], "synonyms_id": ["Produksi Kontrak", "Toll Manufacturing"], "synonyms_en": ["Contract Manufacturing", "Toll Volume"]},
    {"metric_id": "idx:BPJSCatalogRevenueShare", "name_en": "BPJS e-Catalog Revenue Share (%)", "name_id": "Porsi Pendapatan dari e-Katalog BPJS/JKN", "category": "OPERATIONAL", "sector_applicability": ["PHARMACEUTICAL", "HEALTHCARE"], "importance": "HIGH", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["ANNUAL_REPORT", "INVESTOR_PRESENTATION"], "synonyms_id": ["Kontribusi e-Katalog", "BPJS Catalog"], "synonyms_en": ["BPJS e-Catalog Share", "Government Tender Share"]},

    # =========================================================================
    # 19. PETROCHEMICAL — NEW SECTOR (TPIA, BRPT, ESSA)
    # =========================================================================
    {"metric_id": "idx:NaphthaCrackerUtilization", "name_en": "Naphtha Cracker Utilization (%)", "name_id": "Utilisasi Cracker Nafta", "category": "OPERATIONAL", "sector_applicability": ["PETROCHEMICAL", "BASIC_MATERIALS"], "importance": "CRITICAL", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Utilisasi Cracker", "Load Factor Cracker"], "synonyms_en": ["Cracker Utilization", "Ethylene Cracker Load"]},
    {"metric_id": "idx:PolyolefinProductionMT", "name_en": "Polyethylene / Polypropylene Production (MT)", "name_id": "Produksi PE/PP (Ton)", "category": "OPERATIONAL", "sector_applicability": ["PETROCHEMICAL", "BASIC_MATERIALS"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "TONNES", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Produksi Polietilena", "Produksi Polipropilena"], "synonyms_en": ["PE Production", "PP Production", "Polyolefin Output"]},
    {"metric_id": "idx:PolymerNaphthaSpread", "name_en": "Polymer over Naphtha Spread (USD/MT)", "name_id": "Spread Polimer atas Nafta", "category": "OPERATIONAL", "sector_applicability": ["PETROCHEMICAL", "BASIC_MATERIALS"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "USD_PER_TON", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Spread PE-Nafta", "Spread PP-Nafta"], "synonyms_en": ["PE/Naphtha Spread", "Polymer Spread"]},
    {"metric_id": "idx:AmmoniaProductionMT", "name_en": "Ammonia Production Volume (Tonnes)", "name_id": "Produksi Amonia (Ton)", "category": "OPERATIONAL", "sector_applicability": ["PETROCHEMICAL", "BASIC_MATERIALS"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "TONNES", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Produksi Amonia"], "synonyms_en": ["Ammonia Output", "NH3 Production"]},
    {"metric_id": "idx:UreaProductionMT", "name_en": "Urea Production Volume (Tonnes)", "name_id": "Produksi Urea (Ton)", "category": "OPERATIONAL", "sector_applicability": ["PETROCHEMICAL", "BASIC_MATERIALS"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "TONNES", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Produksi Urea"], "synonyms_en": ["Urea Output"]},
    {"metric_id": "idx:PlantTurnaroundEvent", "name_en": "Scheduled Plant Turnaround / Shutdown Days", "name_id": "Hari Turnaround / Perbaikan Terjadwal Pabrik", "category": "OPERATIONAL", "sector_applicability": ["PETROCHEMICAL", "BASIC_MATERIALS"], "importance": "MEDIUM", "value_type": "INTEGER", "unit": "DAYS", "flow_stock_type": "EVENT", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "ANNUAL_REPORT"], "synonyms_id": ["Turnaround", "Shutdown Terjadwal"], "synonyms_en": ["Plant Turnaround", "Maintenance Shutdown"]},

    # =========================================================================
    # 20. CONTRACTORS / CONSTRUCTION — NEW SECTOR (PTPP, WIKA, ADHI, WSKT, TOTL)
    # =========================================================================
    {"metric_id": "idx:NewContractWins", "name_en": "New Contract Wins (Nilai Kontrak Baru)", "name_id": "Nilai Kontrak Baru (New Contract)", "category": "OPERATIONAL", "sector_applicability": ["CONTRACTOR", "CONSTRUCTION", "INFRASTRUCTURE"], "importance": "CRITICAL", "value_type": "MONETARY", "unit": "IDR", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Kontrak Baru", "NKB", "New Contract Achievement"], "synonyms_en": ["New Contract Wins", "Order Intake"]},
    {"metric_id": "idx:OrderBookBacklog", "name_en": "Order Book / Contract Backlog (IDR)", "name_id": "Buku Pesanan / Sisa Kontrak (Backlog)", "category": "OPERATIONAL", "sector_applicability": ["CONTRACTOR", "CONSTRUCTION", "INFRASTRUCTURE"], "importance": "CRITICAL", "value_type": "MONETARY", "unit": "IDR", "flow_stock_type": "STOCK_POINT_IN_TIME", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Order Book", "Sisa Kontrak", "Carry-Over"], "synonyms_en": ["Order Book", "Contract Backlog"]},
    {"metric_id": "idx:BurnRateConversion", "name_en": "Order Book Burn Rate / Revenue Conversion (%)", "name_id": "Rasio Realisasi Pendapatan dari Kontrak (Burn Rate)", "category": "OPERATIONAL", "sector_applicability": ["CONTRACTOR", "CONSTRUCTION", "INFRASTRUCTURE"], "importance": "HIGH", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "RATIO", "extraction_mode": "HYBRID_FALLBACK", "calculation_formula": "(ifrs:Revenue / idx:OrderBookBacklog) * 100", "dependencies": ["ifrs:Revenue", "idx:OrderBookBacklog"], "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Konversi Kontrak", "Burn Rate"], "synonyms_en": ["Burn Rate", "Revenue Conversion Rate"]},
    {"metric_id": "idx:KSOJointOperationCF", "name_en": "Joint Operation (KSO) Cash Flows (IDR)", "name_id": "Arus Kas dari Kerja Sama Operasi (KSO)", "category": "CASH_FLOW", "sector_applicability": ["CONTRACTOR", "CONSTRUCTION", "INFRASTRUCTURE"], "importance": "MEDIUM", "value_type": "MONETARY", "unit": "IDR", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["FS_NOTES_DETAIL"], "synonyms_id": ["KSO", "Kerja Sama Operasi", "Joint Operation"], "synonyms_en": ["KSO Cash Flow", "Joint Operation CF"]},
    {"metric_id": "idx:ReceivablesDaysContractor", "name_en": "Receivables Days (Contractor)", "name_id": "Rata-Rata Hari Piutang Kontraktor", "category": "LIQUIDITY", "sector_applicability": ["CONTRACTOR", "CONSTRUCTION", "INFRASTRUCTURE"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "DAYS", "flow_stock_type": "RATIO", "extraction_mode": "CALCULATED_DETERMINISTIC", "calculation_formula": "(ifrs:TradeReceivables / ifrs:Revenue) * 365", "dependencies": ["ifrs:TradeReceivables", "ifrs:Revenue"], "source_priority": ["FS_CORE_STATEMENT", "FS_NOTES_DETAIL"], "synonyms_id": ["DSO", "Hari Piutang"], "synonyms_en": ["DSO", "Days Sales Outstanding"]},
    {"metric_id": "idx:GovernmentProjectMix", "name_en": "Government vs Private Project Mix (%)", "name_id": "Kontribusi Proyek Pemerintah vs Swasta", "category": "OPERATIONAL", "sector_applicability": ["CONTRACTOR", "CONSTRUCTION", "INFRASTRUCTURE"], "importance": "MEDIUM", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "ANNUAL_REPORT"], "synonyms_id": ["Owner Proyek", "Sumber Pemberi Kerja"], "synonyms_en": ["Project Owner Mix", "Client Mix"]},

    # =========================================================================
    # 21. PULP & PAPER — NEW SECTOR (INKP, TKIM, FASW, SPMA)
    # =========================================================================
    {"metric_id": "idx:PulpProductionCapacityMT", "name_en": "Pulp Production Capacity (MT/year)", "name_id": "Kapasitas Produksi Pulp (Ton/tahun)", "category": "OPERATIONAL", "sector_applicability": ["PULP_PAPER", "BASIC_MATERIALS"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "TONNES", "flow_stock_type": "STOCK_POINT_IN_TIME", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "ANNUAL_REPORT"], "synonyms_id": ["Kapasitas Terpasang Pulp"], "synonyms_en": ["Pulp Capacity", "Nameplate Pulp Capacity"]},
    {"metric_id": "idx:PaperPackagingVolumeMT", "name_en": "Paper & Packaging Sales Volume (Tonnes)", "name_id": "Volume Penjualan Kertas & Kemasan (Ton)", "category": "OPERATIONAL", "sector_applicability": ["PULP_PAPER", "BASIC_MATERIALS"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "TONNES", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Volume Penjualan Kertas"], "synonyms_en": ["Paper Sales Volume", "Packaging Volume"]},
    {"metric_id": "idx:PulpExportASPUSDMT", "name_en": "Pulp Export ASP (USD/MT)", "name_id": "Harga Jual Ekspor Pulp (USD/Ton)", "category": "OPERATIONAL", "sector_applicability": ["PULP_PAPER", "BASIC_MATERIALS"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "USD_PER_TON", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["ASP Pulp Ekspor"], "synonyms_en": ["BHKP/BSKP Price", "Realized Pulp ASP"]},
    {"metric_id": "idx:WoodFiberSelfSufficiency", "name_en": "Wood Fiber Self-Sufficiency (%)", "name_id": "Tingkat Swasembada Bahan Baku Serat Kayu", "category": "OPERATIONAL", "sector_applicability": ["PULP_PAPER", "BASIC_MATERIALS"], "importance": "HIGH", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["ANNUAL_REPORT", "INVESTOR_PRESENTATION"], "synonyms_id": ["Swasembada Bahan Baku", "Pasokan HTI"], "synonyms_en": ["Fiber Self-Sufficiency", "HTI Fiber Coverage"]},
    {"metric_id": "idx:PulpCashCostUSDMT", "name_en": "Pulp Cash Cost (USD/MT)", "name_id": "Biaya Kas Produksi Pulp (USD/Ton)", "category": "OPERATIONAL", "sector_applicability": ["PULP_PAPER", "BASIC_MATERIALS"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "USD_PER_TON", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Cash Cost Pulp"], "synonyms_en": ["Pulp Cash Cost", "Unit Cost"]},

    # =========================================================================
    # 22. GOLD & COPPER — NEW SECTOR (AMMN, MDKA, PSAB, ANTM, BRMS)
    # =========================================================================
    {"metric_id": "idx:GoldProductionOz", "name_en": "Gold Production (Troy Ounces)", "name_id": "Produksi Emas (Ons Troy / Kg)", "category": "OPERATIONAL", "sector_applicability": ["GOLD_COPPER", "MINING", "BASIC_MATERIALS"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "OZ", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Produksi Emas", "Ons Emas"], "synonyms_en": ["Gold Production", "Gold Ounces Produced"]},
    {"metric_id": "idx:CopperCathodeOutputMT", "name_en": "Copper Cathode / Concentrate Output (Tonnes)", "name_id": "Produksi Katoda / Konsentrat Tembaga (Ton)", "category": "OPERATIONAL", "sector_applicability": ["GOLD_COPPER", "MINING", "BASIC_MATERIALS"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "TONNES", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Produksi Tembaga", "Konsentrat Cu"], "synonyms_en": ["Copper Cathode Output", "Copper Concentrate Production"]},
    {"metric_id": "idx:AllInSustainingCost", "name_en": "All-In Sustaining Cost (AISC USD/Oz Au)", "name_id": "Biaya Berkelanjutan Menyeluruh (AISC per Ons Emas)", "category": "OPERATIONAL", "sector_applicability": ["GOLD_COPPER", "MINING", "BASIC_MATERIALS"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "USD_PER_OZ", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["AISC", "Biaya Kas + Sustaining Capex"], "synonyms_en": ["AISC", "All-In Sustaining Cost"]},
    {"metric_id": "idx:CopperConcentrateGrade", "name_en": "Copper Concentrate Grade (%)", "name_id": "Kadar Konsentrat Tembaga", "category": "OPERATIONAL", "sector_applicability": ["GOLD_COPPER", "MINING", "BASIC_MATERIALS"], "importance": "HIGH", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["ANNUAL_REPORT", "INVESTOR_PRESENTATION"], "synonyms_id": ["Kadar Cu", "Grade Konsentrat"], "synonyms_en": ["Copper Grade", "Concentrate Grade"]},
    {"metric_id": "idx:SmelterTCRCDeductions", "name_en": "Treatment & Refining Charges (TC/RC USD/lb Cu)", "name_id": "Biaya Pengolahan & Pemurnian Konsentrat (TC/RC)", "category": "OPERATIONAL", "sector_applicability": ["GOLD_COPPER", "MINING", "BASIC_MATERIALS"], "importance": "HIGH", "value_type": "FLOAT", "unit": "USD_PER_LB", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "ANNUAL_REPORT"], "synonyms_id": ["TC/RC", "Biaya Smelter"], "synonyms_en": ["Treatment Charges", "Refining Charges"]},
    {"metric_id": "idx:GoldReservesOz", "name_en": "Gold Reserves (Proved & Probable, Oz)", "name_id": "Cadangan Emas Terbukti + Terduga (Ons)", "category": "RESERVES", "sector_applicability": ["GOLD_COPPER", "MINING", "BASIC_MATERIALS"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "OZ", "flow_stock_type": "STOCK_POINT_IN_TIME", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["ANNUAL_REPORT", "INVESTOR_PRESENTATION"], "synonyms_id": ["Cadangan Emas JORC"], "synonyms_en": ["Gold P&P Reserves", "Contained Gold Reserves"]},
    {"metric_id": "idx:ByProductCreditsUSDOz", "name_en": "By-Product Credits (USD/Oz Au)", "name_id": "Kredit Hasil Sampingan per Ons Emas", "category": "OPERATIONAL", "sector_applicability": ["GOLD_COPPER", "MINING", "BASIC_MATERIALS"], "importance": "MEDIUM", "value_type": "FLOAT", "unit": "USD_PER_OZ", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "ANNUAL_REPORT"], "synonyms_id": ["Kredit By-Product"], "synonyms_en": ["By-Product Credits"]},

    # =========================================================================
    # 23. DIGITAL PLATFORMS / E-COMMERCE — NEW SECTOR (GOTO, BUKA, EMTK)
    # =========================================================================
    {"metric_id": "idx:GrossTransactionValue", "name_en": "Gross Transaction Value (GTV)", "name_id": "Nilai Transaksi Kotor (GTV)", "category": "OPERATIONAL", "sector_applicability": ["DIGITAL", "TECHNOLOGY"], "importance": "CRITICAL", "value_type": "MONETARY", "unit": "IDR", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["GTV", "Nilai Transaksi Kotor"], "synonyms_en": ["GTV", "Gross Transaction Value"]},
    {"metric_id": "idx:GrossMerchandiseValue", "name_en": "Gross Merchandise Value (GMV)", "name_id": "Nilai Barang Dagangan Kotor (GMV)", "category": "OPERATIONAL", "sector_applicability": ["DIGITAL", "TECHNOLOGY"], "importance": "CRITICAL", "value_type": "MONETARY", "unit": "IDR", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["GMV", "Nilai Barang Diperdagangkan"], "synonyms_en": ["GMV", "Gross Merchandise Value"]},
    {"metric_id": "idx:TakeRate", "name_en": "Take Rate (%)", "name_id": "Rasio Monetisasi (Take Rate)", "category": "OPERATIONAL", "sector_applicability": ["DIGITAL", "TECHNOLOGY"], "importance": "CRITICAL", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Take Rate", "Rasio Monetisasi"], "synonyms_en": ["Take Rate", "Monetization Rate"]},
    {"metric_id": "idx:MonthlyActiveTransactingUsers", "name_en": "Monthly Active Transacting Users (ATU)", "name_id": "Pengguna Aktif Bertransaksi Bulanan", "category": "OPERATIONAL", "sector_applicability": ["DIGITAL", "TECHNOLOGY"], "importance": "CRITICAL", "value_type": "INTEGER", "unit": "USERS", "flow_stock_type": "STOCK_POINT_IN_TIME", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["ATU", "Pengguna Aktif Transaksi"], "synonyms_en": ["Active Transacting Users", "MTU"]},
    {"metric_id": "idx:ContributionMargin", "name_en": "Contribution Margin (%)", "name_id": "Marjin Kontribusi", "category": "PROFITABILITY", "sector_applicability": ["DIGITAL", "TECHNOLOGY"], "importance": "CRITICAL", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Contribution Margin", "Marjin Kontribusi"], "synonyms_en": ["Contribution Margin", "CM"]},
    {"metric_id": "idx:AdjustedEBITDADigital", "name_en": "Adjusted EBITDA (Digital)", "name_id": "EBITDA Disesuaikan (Digital)", "category": "PROFITABILITY", "sector_applicability": ["DIGITAL", "TECHNOLOGY"], "importance": "CRITICAL", "value_type": "MONETARY", "unit": "IDR", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Adjusted EBITDA", "EBITDA Disesuaikan"], "synonyms_en": ["Adjusted EBITDA"]},
    {"metric_id": "idx:PromotionalIncentives", "name_en": "Promotional Incentives / Cash Burn", "name_id": "Beban Promosi & Insentif Pengguna", "category": "INCOME", "sector_applicability": ["DIGITAL", "TECHNOLOGY"], "importance": "HIGH", "value_type": "MONETARY", "unit": "IDR", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "FS_NOTES_DETAIL"], "synonyms_id": ["Promo", "Insentif Pengguna", "Cash Burn"], "synonyms_en": ["Promotional Spend", "User Incentives"]},

    # =========================================================================
    # 24. TOLL ROADS & PORTS — NEW SECTOR (JSMR, META, IPCC, PORT)
    # =========================================================================
    {"metric_id": "idx:AverageDailyTraffic", "name_en": "Average Daily Traffic (LHR Vehicles/Day)", "name_id": "Lalu Lintas Harian Rata-Rata (LHR)", "category": "OPERATIONAL", "sector_applicability": ["TOLL_ROAD", "INFRASTRUCTURE"], "importance": "CRITICAL", "value_type": "INTEGER", "unit": "VEHICLES_PER_DAY", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["LHR", "Lalu Lintas Harian Rata-Rata"], "synonyms_en": ["ADT", "Average Daily Traffic"]},
    {"metric_id": "idx:TollTariffAdjustment", "name_en": "Toll Tariff Adjustment (%)", "name_id": "Penyesuaian Tarif Tol", "category": "OPERATIONAL", "sector_applicability": ["TOLL_ROAD", "INFRASTRUCTURE"], "importance": "HIGH", "value_type": "PERCENTAGE", "unit": "PERCENT", "flow_stock_type": "EVENT", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Penyesuaian Tarif", "Kenaikan Tarif Tol"], "synonyms_en": ["Tariff Adjustment", "Toll Rate Increase"]},
    {"metric_id": "idx:OperationalTollLengthKm", "name_en": "Operational Toll Road Length (Km)", "name_id": "Panjang Ruas Tol Beroperasi (Km)", "category": "OPERATIONAL", "sector_applicability": ["TOLL_ROAD", "INFRASTRUCTURE"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "KM", "flow_stock_type": "STOCK_POINT_IN_TIME", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "ANNUAL_REPORT"], "synonyms_id": ["Panjang Tol Operasional", "Km Beroperasi"], "synonyms_en": ["Operational Length", "Kilometers in Operation"]},
    {"metric_id": "idx:ContainerThroughputTEUs", "name_en": "Container Throughput (TEUs)", "name_id": "Volume Bongkar Muat Kontainer (TEUs)", "category": "OPERATIONAL", "sector_applicability": ["PORT", "INFRASTRUCTURE"], "importance": "CRITICAL", "value_type": "FLOAT", "unit": "TEUS", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Throughput TEUs", "Volume Kontainer"], "synonyms_en": ["Container Throughput", "TEU Handled"]},
    {"metric_id": "idx:CBUCarTerminalVolume", "name_en": "CBU Car Terminal Volume (Units)", "name_id": "Volume Bongkar Muat Kendaraan CBU (Unit)", "category": "OPERATIONAL", "sector_applicability": ["PORT", "INFRASTRUCTURE"], "importance": "CRITICAL", "value_type": "INTEGER", "unit": "UNITS", "flow_stock_type": "FLOW_PERIOD", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "PUBLIC_EXPOSE"], "synonyms_id": ["Volume CBU", "Stevedoring Mobil"], "synonyms_en": ["CBU Volume", "Car Terminal Throughput"]},
    {"metric_id": "idx:StevedoringRevenuePerTEU", "name_en": "Stevedoring Revenue per TEU (USD)", "name_id": "Pendapatan Stevedoring per TEU", "category": "OPERATIONAL", "sector_applicability": ["PORT", "INFRASTRUCTURE"], "importance": "HIGH", "value_type": "FLOAT", "unit": "USD_PER_TEU", "flow_stock_type": "RATIO", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["INVESTOR_PRESENTATION", "ANNUAL_REPORT"], "synonyms_id": ["Tarif Stevedoring per TEU"], "synonyms_en": ["Revenue per TEU", "Stevedoring Tariff"]},
    {"metric_id": "idx:ConcessionRemainingYears", "name_en": "Concession Remaining Life (Years)", "name_id": "Sisa Masa Konsesi (Tahun)", "category": "OPERATIONAL", "sector_applicability": ["TOLL_ROAD", "PORT", "INFRASTRUCTURE"], "importance": "HIGH", "value_type": "FLOAT", "unit": "YEARS", "flow_stock_type": "STOCK_POINT_IN_TIME", "extraction_mode": "EXTRACTED_RAW", "source_priority": ["ANNUAL_REPORT", "FS_NOTES_DETAIL"], "synonyms_id": ["Sisa Konsesi", "Masa Konsesi Tersisa"], "synonyms_en": ["Remaining Concession Term"]},
]

SECTOR_CONTRACTS_DATA: list[dict[str, Any]] = [
    {
        "sector_code": "BANK",
        "module_name": "BANK_LOANS_BY_SEGMENT",
        "typical_note_title": "Catatan Kredit yang Diberikan Berdasarkan Segmen",
        "description": "Rincian penyaluran kredit per segmen (Korporasi, Komersial, UKM/SME, Mikro, Konsumer/KPR).",
        "target_concepts": ["idx:LoansAndAdvances"],
        "expected_segment_fields": ["segment", "type", "pct_total"],
        "guideline": "Extract loan balance per segment with segment={'segment': '<Segment Name>', 'type': 'loan_segment'}.",
        "is_mandatory": True,
    },
    {
        "sector_code": "BANK",
        "module_name": "BANK_LOAN_QUALITY_NPL",
        "typical_note_title": "Catatan Kualitas Aset Produktif / Kolektibilitas Kredit",
        "description": "Kolektibilitas kredit: Kol 1 (Lancar), Kol 2 (DPK), Kol 3 (Kurang Lancar), Kol 4 (Diragukan), Kol 5 (Macet).",
        "target_concepts": ["idx:LoansAndAdvances", "idx:NonPerformingLoansGross"],
        "expected_segment_fields": ["segment", "type", "kol_rating", "npl_status"],
        "guideline": "Extract loan quality per collectibility category with segment={'segment': 'Kol 1 - Lancar / Kol 5 - Macet', 'type': 'loan_collectibility'}.",
        "is_mandatory": True,
    },
    {
        "sector_code": "MINING",
        "module_name": "MINING_PRODUCTION_AND_SALES",
        "typical_note_title": "Catatan Informasi Segmen Tambang / Penjualan Komoditas",
        "description": "Volume produksi dan penjualan per produk (Saprolite, Limonite, FeNi, MHP, Batubara) serta pasar DMO vs Ekspor.",
        "target_concepts": ["idx:CoalProductionVolume", "idx:NickelOreProduction", "ifrs:Revenue"],
        "expected_segment_fields": ["segment", "type", "volume", "unit", "market"],
        "guideline": "Extract production & sales breakdown with segment={'segment': '<Product Name>', 'type': 'mining_product', 'market': 'Domestic/Export'}.",
        "is_mandatory": True,
    },
    {
        "sector_code": "MINING",
        "module_name": "MINING_RESERVES_AND_RESOURCES",
        "typical_note_title": "Catatan Cadangan & Sumber Daya Tambang / Aset Eksplorasi",
        "description": "Cadangan dan sumber daya tambang (JORC Proved & Probable Reserves, Resources) dan konsesi IUP.",
        "target_concepts": ["idx:MiningReservesMt", "idx:StripRatio"],
        "expected_segment_fields": ["segment", "type", "concession_location", "reserves_mt"],
        "guideline": "Extract mining assets and concessions with segment={'segment': '<Mine Name>', 'type': 'mining_asset'}.",
        "is_mandatory": True,
    },
    {
        "sector_code": "CPO",
        "module_name": "BIOLOGICAL_ASSETS_DETAIL",
        "typical_note_title": "Catatan Tanaman Produktif / Aset Biologis / Perkebunan",
        "description": "Profil kebun kelapa sawit: luas areal tertanam (tanaman menghasilkan/mature vs belum menghasilkan/immature).",
        "target_concepts": ["ifrs:BiologicalAssets", "idx:MaturePlantedArea"],
        "expected_segment_fields": ["segment", "type", "planted_area_ha", "average_age_years"],
        "guideline": "Extract planted hectares breakdown with segment={'segment': 'Mature/Immature', 'type': 'biological_asset_maturity', 'planted_area_ha': <ha>}.",
        "is_mandatory": True,
    },
    {
        "sector_code": "PROPERTY",
        "module_name": "PROPERTY_PRESALES_MARKETING",
        "typical_note_title": "Catatan Pendapatan Pra-Penjualan Properti / Segmen Real Estat",
        "description": "Realisasi presales per segmen: Rumah Tapak (Residential), Ruko, Kavling Tanah, dan Apartemen.",
        "target_concepts": ["idx:MarketingSalesPresales", "ifrs:Revenue"],
        "expected_segment_fields": ["segment", "type", "project_location"],
        "guideline": "Extract presales with segment={'segment': '<Project Name>', 'type': 'property_segment'}.",
        "is_mandatory": True,
    },
    {
        "sector_code": "ALL",
        "module_name": "REVENUE_BREAKDOWN",
        "typical_note_title": "Catatan Penjualan / Pendapatan / Informasi Segmen",
        "description": "Rincian pendapatan per lini produk, wilayah geografis, dan pihak ketiga vs berelasi.",
        "target_concepts": ["ifrs:Revenue"],
        "expected_segment_fields": ["segment", "type", "pct_total"],
        "guideline": "Extract every product line as an ExtractedFactItem with segment={'segment': '<product_name>', 'type': 'product'}.",
        "is_mandatory": True,
    },
    {
        "sector_code": "ALL",
        "module_name": "CUSTOMER_CONCENTRATION",
        "typical_note_title": "Catatan Pelanggan Utama / Konsentrasi Penjualan",
        "description": "Pelanggan dengan transaksi penjualan melebihi 10% dari total pendapatan.",
        "target_concepts": ["idx:CustomerConcentration"],
        "expected_segment_fields": ["segment", "type", "pct_total", "is_related_party"],
        "guideline": "Extract major buyers contributing >10% revenue with segment={'segment': '<customer_name>', 'type': 'customer_concentration', 'pct_total': <pct>}.",
        "is_mandatory": True,
    },
    {
        "sector_code": "ALL",
        "module_name": "COGS_COMPONENTS",
        "typical_note_title": "Catatan Beban Pokok Penjualan / Cost of Goods Sold",
        "description": "Rincian beban pokok: bahan baku, pupuk, upah buruh, penyusutan mesin/pabrik.",
        "target_concepts": ["ifrs:CostOfSales", "idx:CostOfGoodsSoldComponent"],
        "expected_segment_fields": ["segment", "type", "pct_cogs"],
        "guideline": "Extract cost line items with segment={'segment': '<cost_item_name>', 'type': 'cogs_component'}.",
        "is_mandatory": True,
    },
    {
        "sector_code": "ALL",
        "module_name": "DEBT_BY_LENDER",
        "typical_note_title": "Catatan Utang Bank / Pinjaman Jangka Panjang",
        "description": "Rincian pinjaman per bank kreditur, suku bunga, dan tahun jatuh tempo.",
        "target_concepts": ["idx:BorrowingsByLender", "ifrs:LongTermBorrowings"],
        "expected_segment_fields": ["segment", "type", "interest_rate", "maturity_year"],
        "guideline": "Extract debt facilities with segment={'segment': '<bank_name>', 'type': 'debt_facility', 'interest_rate': '<rate>', 'maturity_year': <year>}.",
        "is_mandatory": True,
    },

    # -- NEW SECTOR CONTRACTS -------------------------------------------------
    {"sector_code": "BANK", "module_name": "BANK_PROFITABILITY_KPIS", "typical_note_title": "Ikhtisar Rasio Keuangan / OJK Ratios (Public Expose)", "description": "Rasio profitabilitas & efisiensi OJK: NIM, BOPO, ROA Bank, ROE Bank, CIR, CoC, LDR, Coverage.", "target_concepts": ["idx:NetInterestMargin", "idx:BOPO", "idx:ReturnOnAssetsBank", "idx:CostToIncomeRatio", "idx:CostOfCredit", "idx:LoanToDepositRatio", "idx:NPLCoverageRatio", "idx:PPOP"], "expected_segment_fields": ["segment", "type"], "guideline": "Extract each OJK banking ratio as a standalone fact.", "is_mandatory": True},
    {"sector_code": "COAL", "module_name": "COAL_OPERATIONAL_KPIS", "typical_note_title": "Ikhtisar Operasional Batubara (Public Expose / Investor Presentation)", "description": "Volume produksi & penjualan, ASP, cash cost, strip ratio, OB removal, DMO.", "target_concepts": ["idx:CoalProductionVolume", "idx:CoalAveragePriceASP", "idx:CoalCashCostPerTon", "idx:StripRatio", "idx:OverburdenRemoval", "idx:DomesticMarketObligationRatio"], "expected_segment_fields": ["segment", "type", "market"], "guideline": "Extract coal operational metrics per mine site and market (DMO vs Export).", "is_mandatory": True},
    {"sector_code": "NICKEL", "module_name": "NICKEL_VALUE_CHAIN", "typical_note_title": "Ikhtisar Operasional Nikel & Smelter", "description": "Produksi bijih nikel (saprolite/limonite), FeNi, MHP, cash cost, utilisasi smelter.", "target_concepts": ["idx:NickelOreProduction", "idx:FerroNickelOutput", "idx:MHPProduction", "idx:NickelCashCostPerTon", "idx:SmelterUtilizationRate"], "expected_segment_fields": ["segment", "type"], "guideline": "Extract each product line (saprolite/limonite/FeNi/MHP) and cost KPI.", "is_mandatory": True},
    {"sector_code": "CPO", "module_name": "CPO_UPSTREAM_KPIS", "typical_note_title": "Ikhtisar Operasional Kelapa Sawit", "description": "Produksi TBS, CPO, PK, OER, ASP CPO, cash cost per kg.", "target_concepts": ["idx:FfbProduction", "idx:CPOProductionVolume", "idx:PalmKernelProduction", "idx:OilExtractionRate", "idx:CPOAveragePriceASP", "idx:CPOCashCostPerKg"], "expected_segment_fields": ["segment", "type"], "guideline": "Extract each palm oil operational KPI at group and estate-level if available.", "is_mandatory": True},
    {"sector_code": "PROPERTY", "module_name": "PROPERTY_RECURRING_INCOME", "typical_note_title": "Pendapatan Berulang (Recurring Income) — Mall, Hotel, Kantor", "description": "Kontribusi pendapatan berulang, occupancy mall, backlog presales.", "target_concepts": ["idx:RecurringIncomeShare", "idx:MallOccupancyRate", "idx:UnrecognizedRevenueBacklog"], "expected_segment_fields": ["segment", "type"], "guideline": "Extract recurring income share and mall occupancy per asset.", "is_mandatory": True},
    {"sector_code": "TELCO", "module_name": "TELCO_MOBILE_KPIS", "typical_note_title": "Ikhtisar Operasional Telekomunikasi Seluler", "description": "Data traffic, ARPU, subscriber base.", "target_concepts": ["idx:DataTrafficPetabytes", "idx:BlendedARPU", "idx:MobileSubscribers"], "expected_segment_fields": ["segment", "type"], "guideline": "Extract each telco KPI at group level; break down by prepaid/postpaid if available.", "is_mandatory": True},
    {"sector_code": "TOWER", "module_name": "TOWER_INFRASTRUCTURE_KPIS", "typical_note_title": "Ikhtisar Menara Telekomunikasi", "description": "Total menara, tenancy ratio, revenue per tower.", "target_concepts": ["idx:TowerCount", "idx:TenancyRatio"], "expected_segment_fields": ["segment", "type"], "guideline": "Extract tower count and tenancy ratio (with target definition — build to suit vs colocation).", "is_mandatory": True},
    {"sector_code": "HOSPITAL", "module_name": "HOSPITAL_OPERATIONAL_KPIS", "typical_note_title": "Ikhtisar Operasional Rumah Sakit", "description": "Beds, BOR, ALOS, admisi IP & OP visits, ARPOB, BPJS mix.", "target_concepts": ["idx:OperationalBedsCount", "idx:BedOccupancyRate", "idx:AverageLengthOfStay", "idx:InpatientAdmissions", "idx:OutpatientVisits", "idx:ARPOB", "idx:BPJSRevenueShare"], "expected_segment_fields": ["segment", "type"], "guideline": "Extract each hospital operational KPI at group and hospital-level if disclosed.", "is_mandatory": True},
    {"sector_code": "SHIPPING", "module_name": "SHIPPING_FLEET_KPIS", "typical_note_title": "Ikhtisar Armada Kapal & Utilisasi", "description": "Jumlah kapal, DWT, TCE charter rate, bunker cost, utilisasi armada.", "target_concepts": ["idx:FleetCount", "idx:TotalDWT", "idx:CharterRate", "idx:BunkerFuelCost", "idx:VesselUtilization"], "expected_segment_fields": ["segment", "type", "vessel_type"], "guideline": "Extract fleet KPIs; if available, break down by vessel type (tanker/dry bulk/container).", "is_mandatory": True},
    {"sector_code": "RENEWABLE_ENERGY", "module_name": "RENEWABLE_POWER_KPIS", "typical_note_title": "Ikhtisar Operasional Pembangkit Listrik", "description": "Kapasitas terpasang MW, produksi GWh, capacity factor, tarif per kWh, cadangan panas bumi.", "target_concepts": ["idx:InstalledCapacityMW", "idx:NetGenerationGWh", "idx:CapacityFactor", "idx:RealizedElectricityTariff", "idx:SteamProductionTonnes", "idx:ProvenGeothermalReservesMWe"], "expected_segment_fields": ["segment", "type", "plant_name"], "guideline": "Extract per-plant capacity, generation, and tariff KPIs.", "is_mandatory": True},
    {"sector_code": "OIL_GAS", "module_name": "OIL_GAS_UPSTREAM_KPIS", "typical_note_title": "Ikhtisar Operasional Hulu Migas", "description": "Cadangan 2P, produksi minyak (BOPD) dan gas (MMSCFD), lifting cost, ICP, gas ASP.", "target_concepts": ["idx:ProvedReserves2P", "idx:OilProductionBOPD", "idx:GasProductionMMSCFD", "idx:LiftingCostPerBOE", "idx:RealizedICP", "idx:RealizedGasASP", "idx:RigUtilization", "idx:ReserveReplacementRatio"], "expected_segment_fields": ["segment", "type", "block_name"], "guideline": "Extract production and cost KPIs per PSC block if disclosed.", "is_mandatory": True},
    {"sector_code": "AUTOMOTIVE", "module_name": "AUTO_UNIT_SALES_KPIS", "typical_note_title": "Ikhtisar Penjualan Otomotif (Wholesale/Retail/Export)", "description": "Wholesale & retail 4W/2W volume, market share Gaikindo/AISI, ekspor CBU, mix EV/HEV.", "target_concepts": ["idx:CarWholesaleUnits", "idx:CarRetailUnits", "idx:MotorcycleUnitSales", "idx:MarketShareGaikindo", "idx:ExportVolumeUnits", "idx:EVModelMixShare"], "expected_segment_fields": ["segment", "type", "brand", "channel"], "guideline": "Extract volumes per brand (Toyota/Daihatsu/Honda) and channel (wholesale/retail/export).", "is_mandatory": True},
    {"sector_code": "POULTRY", "module_name": "POULTRY_INTEGRATION_KPIS", "typical_note_title": "Ikhtisar Rantai Nilai Perunggasan", "description": "Feedmill volume, DOC volume & harga, harga ayam hidup, bauran bahan baku.", "target_concepts": ["idx:FeedMillSalesVolumeMT", "idx:DayOldChickVolume", "idx:DOCFarmgatePrice", "idx:LiveBirdPriceIDR", "idx:RawMaterialExposureSoyCorn"], "expected_segment_fields": ["segment", "type"], "guideline": "Extract poultry integration KPIs by segment (Feed / DOC / Broiler / Processed).", "is_mandatory": True},
    {"sector_code": "CONSUMER_STAPLES", "module_name": "STAPLES_VOLUME_PRICE_MIX", "typical_note_title": "Ikhtisar Volume vs Harga (Investor Presentation)", "description": "Dekomposisi pertumbuhan penjualan menjadi volume, harga, dan mix produk.", "target_concepts": ["idx:BrandedFoodVolumeMT", "idx:VolumePriceMixDecomp"], "expected_segment_fields": ["segment", "type", "brand"], "guideline": "Extract volume/price decomposition per brand or category.", "is_mandatory": True},
    {"sector_code": "RETAIL", "module_name": "RETAIL_STORE_KPIS", "typical_note_title": "Ikhtisar Operasional Retail (SSSG, Store Count)", "description": "SSSG, jumlah toko, sales density per m2, private label share, ticket size.", "target_concepts": ["idx:SameStoreSalesGrowth", "idx:TotalStoreCount", "idx:NetNewStoreOpenings", "idx:SalesPerSquareMeter", "idx:PrivateLabelShare", "idx:AverageTicketSize", "idx:InventoryDays"], "expected_segment_fields": ["segment", "type", "store_format"], "guideline": "Extract retail KPIs by store format (minimarket / supermarket / department store).", "is_mandatory": True},
    {"sector_code": "PHARMACEUTICAL", "module_name": "PHARMA_REVENUE_MIX", "typical_note_title": "Ikhtisar Bauran Pendapatan Farmasi (Ethical vs OTC)", "description": "Kontribusi ethical vs OTC, eksposur API impor, toll manufacturing.", "target_concepts": ["idx:EthicalRevenueShare", "idx:OTCRevenueShare", "idx:APIImportExposure", "idx:TollManufacturingVolume", "idx:BPJSCatalogRevenueShare"], "expected_segment_fields": ["segment", "type"], "guideline": "Extract revenue mix by channel and API exposure disclosure.", "is_mandatory": True},
    {"sector_code": "PETROCHEMICAL", "module_name": "PETROCHEM_PRODUCTION_KPIS", "typical_note_title": "Ikhtisar Operasional Petrokimia", "description": "Utilisasi cracker, produksi PE/PP, produksi amonia/urea, polymer-naphtha spread.", "target_concepts": ["idx:NaphthaCrackerUtilization", "idx:PolyolefinProductionMT", "idx:PolymerNaphthaSpread", "idx:AmmoniaProductionMT", "idx:UreaProductionMT", "idx:PlantTurnaroundEvent"], "expected_segment_fields": ["segment", "type", "product"], "guideline": "Extract production volumes per product family (Olefins, Polyolefins, Ammonia-Urea).", "is_mandatory": True},
    {"sector_code": "CONTRACTOR", "module_name": "CONTRACTOR_ORDER_BOOK", "typical_note_title": "Ikhtisar Order Book & New Contracts (Public Expose)", "description": "Nilai kontrak baru, order book, burn rate, mix pemerintah/swasta, DSO.", "target_concepts": ["idx:NewContractWins", "idx:OrderBookBacklog", "idx:BurnRateConversion", "idx:GovernmentProjectMix", "idx:ReceivablesDaysContractor", "idx:KSOJointOperationCF"], "expected_segment_fields": ["segment", "type", "project_owner"], "guideline": "Extract order book breakdown by project owner (Government/SOE/Private/Foreign).", "is_mandatory": True},
    {"sector_code": "PULP_PAPER", "module_name": "PULP_PAPER_OPERATIONAL", "typical_note_title": "Ikhtisar Operasional Pulp & Kertas", "description": "Kapasitas pulp, volume kertas & packaging, ASP ekspor, cash cost, HTI self-sufficiency.", "target_concepts": ["idx:PulpProductionCapacityMT", "idx:PaperPackagingVolumeMT", "idx:PulpExportASPUSDMT", "idx:WoodFiberSelfSufficiency", "idx:PulpCashCostUSDMT"], "expected_segment_fields": ["segment", "type", "product"], "guideline": "Extract pulp vs paper vs packaging volumes and ASPs.", "is_mandatory": True},
    {"sector_code": "GOLD_COPPER", "module_name": "PRECIOUS_METALS_KPIS", "typical_note_title": "Ikhtisar Operasional Tambang Emas & Tembaga", "description": "Produksi emas (oz), tembaga (t), AISC, kadar konsentrat, TC/RC deductions.", "target_concepts": ["idx:GoldProductionOz", "idx:CopperCathodeOutputMT", "idx:AllInSustainingCost", "idx:CopperConcentrateGrade", "idx:SmelterTCRCDeductions", "idx:GoldReservesOz", "idx:ByProductCreditsUSDOz"], "expected_segment_fields": ["segment", "type", "mine_name"], "guideline": "Extract precious-metal production and cost KPIs per mine site.", "is_mandatory": True},
    {"sector_code": "DIGITAL", "module_name": "DIGITAL_PLATFORM_KPIS", "typical_note_title": "Ikhtisar Operasional Platform Digital", "description": "GTV, GMV, take rate, MTU, contribution margin, adjusted EBITDA, promotional spend.", "target_concepts": ["idx:GrossTransactionValue", "idx:GrossMerchandiseValue", "idx:TakeRate", "idx:MonthlyActiveTransactingUsers", "idx:ContributionMargin", "idx:AdjustedEBITDADigital", "idx:PromotionalIncentives"], "expected_segment_fields": ["segment", "type", "business_line"], "guideline": "Extract KPIs per business line (On-Demand / E-commerce / Fintech).", "is_mandatory": True},
    {"sector_code": "TOLL_ROAD", "module_name": "TOLL_ROAD_TRAFFIC_KPIS", "typical_note_title": "Ikhtisar Operasional Jalan Tol", "description": "LHR per ruas, penyesuaian tarif, panjang tol operasional, sisa konsesi.", "target_concepts": ["idx:AverageDailyTraffic", "idx:TollTariffAdjustment", "idx:OperationalTollLengthKm", "idx:ConcessionRemainingYears"], "expected_segment_fields": ["segment", "type", "route_name"], "guideline": "Extract LHR & tariff per toll route (ruas).", "is_mandatory": True},
    {"sector_code": "PORT", "module_name": "PORT_TERMINAL_KPIS", "typical_note_title": "Ikhtisar Operasional Terminal Pelabuhan", "description": "TEU throughput, CBU volume, revenue per TEU, sisa konsesi.", "target_concepts": ["idx:ContainerThroughputTEUs", "idx:CBUCarTerminalVolume", "idx:StevedoringRevenuePerTEU", "idx:ConcessionRemainingYears"], "expected_segment_fields": ["segment", "type", "terminal_name"], "guideline": "Extract throughput per terminal (container vs car vs bulk).", "is_mandatory": True},
]


async def seed_metric_ontology():
    pool = create_pool()
    async with pool.connect() as conn:
        log.info("Seeding metric_definitions...")
        for m in METRIC_DEFINITIONS_DATA:
            params = {
                "metric_id": m["metric_id"],
                "name_en": m["name_en"],
                "name_id": m["name_id"],
                "category": m["category"],
                "sector_applicability": m.get("sector_applicability", ["ALL"]),
                "importance": m.get("importance", "HIGH"),
                "value_type": m.get("value_type", "MONETARY"),
                "unit": m.get("unit", "IDR"),
                "flow_stock_type": m.get("flow_stock_type", "FLOW_PERIOD"),
                "extraction_mode": m.get("extraction_mode", "EXTRACTED_RAW"),
                "calculation_formula": m.get("calculation_formula", None),
                "dependencies": m.get("dependencies", []),
                "source_priority": m.get("source_priority", ["FS_CORE_STATEMENT"]),
                "synonyms_id": m.get("synonyms_id", []),
                "synonyms_en": m.get("synonyms_en", []),
            }
            await conn.execute(
                text(
                    """
                    INSERT INTO metric_definitions (
                        metric_id, name_en, name_id, category, sector_applicability, importance,
                        value_type, unit, flow_stock_type, extraction_mode, calculation_formula,
                        dependencies, source_priority, synonyms_id, synonyms_en, updated_at
                    ) VALUES (
                        :metric_id, :name_en, :name_id, :category, :sector_applicability, :importance,
                        :value_type, :unit, :flow_stock_type, :extraction_mode, :calculation_formula,
                        :dependencies, :source_priority, :synonyms_id, :synonyms_en, now()
                    )
                    ON CONFLICT (metric_id) DO UPDATE SET
                        name_en = EXCLUDED.name_en,
                        name_id = EXCLUDED.name_id,
                        category = EXCLUDED.category,
                        sector_applicability = EXCLUDED.sector_applicability,
                        importance = EXCLUDED.importance,
                        value_type = EXCLUDED.value_type,
                        unit = EXCLUDED.unit,
                        flow_stock_type = EXCLUDED.flow_stock_type,
                        extraction_mode = EXCLUDED.extraction_mode,
                        calculation_formula = EXCLUDED.calculation_formula,
                        dependencies = EXCLUDED.dependencies,
                        source_priority = EXCLUDED.source_priority,
                        synonyms_id = EXCLUDED.synonyms_id,
                        synonyms_en = EXCLUDED.synonyms_en,
                        updated_at = now();
                    """
                ),
                params,
            )

        log.info("Seeding sector_metric_contracts...")
        for c in SECTOR_CONTRACTS_DATA:
            c_params = {
                "sector_code": c["sector_code"],
                "module_name": c["module_name"],
                "typical_note_title": c["typical_note_title"],
                "description": c["description"],
                "target_concepts": c.get("target_concepts", []),
                "expected_segment_fields": c.get("expected_segment_fields", []),
                "guideline": c["guideline"],
                "is_mandatory": c.get("is_mandatory", True),
            }
            await conn.execute(
                text(
                    """
                    INSERT INTO sector_metric_contracts (
                        sector_code, module_name, typical_note_title, description,
                        target_concepts, expected_segment_fields, guideline, is_mandatory
                    ) VALUES (
                        :sector_code, :module_name, :typical_note_title, :description,
                        :target_concepts, :expected_segment_fields, :guideline, :is_mandatory
                    )
                    ON CONFLICT (sector_code, module_name) DO UPDATE SET
                        typical_note_title = EXCLUDED.typical_note_title,
                        description = EXCLUDED.description,
                        target_concepts = EXCLUDED.target_concepts,
                        expected_segment_fields = EXCLUDED.expected_segment_fields,
                        guideline = EXCLUDED.guideline,
                        is_mandatory = EXCLUDED.is_mandatory;
                    """
                ),
                c_params,
            )

        await conn.commit()

        # Print summary
        m_count = (await conn.execute(text("SELECT count(*) FROM metric_definitions"))).scalar()
        c_count = (await conn.execute(text("SELECT count(*) FROM sector_metric_contracts"))).scalar()
        print(f"=== METRIC ONTOLOGY SEEDING COMPLETE ===")
        print(f"Total Canonical Metrics in DB: {m_count}")
        print(f"Total Sector Disclosure Contracts in DB: {c_count}")

    await pool.dispose()


if __name__ == "__main__":
    asyncio.run(seed_metric_ontology())
