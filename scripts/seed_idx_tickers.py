"""Seed the full IDX ticker universe into issuer_profile with sector-aligned key_kpis.

For every ticker below this script:
- Upserts issuer_profile with sector, sub_sector, and profile summary
- Assigns a sector-specific list of key_kpis (metric_ids from the ontology) so that
  MCP tools (get_extraction_contract, get_metric_ontology, get_issuer_context) can
  return the relevant KPIs an LLM extractor should search for in the financial
  statements / investor presentations / public exposes of that ticker.
"""

from __future__ import annotations

import sys

import psycopg

from services.shared.config import get_settings

# General baseline KPIs applied to every issuer regardless of sector.
BASELINE_KPIS: list[str] = [
    "ifrs:Revenue",
    "ifrs:CostOfSales",
    "ifrs:GrossProfit",
    "ifrs:OperatingProfit",
    "idx:EBITDA",
    "ifrs:ProfitLossAttributableToOwnersOfParent",
    "ifrs:Assets",
    "ifrs:Liabilities",
    "ifrs:EquityAttributableToOwnersOfParent",
    "ifrs:CashAndCashEquivalents",
    "idx:TotalDebt",
    "ifrs:CashFlowsFromUsedInOperatingActivities",
    "idx:Capex",
    "idx:FreeCashFlow",
]

# Sector-specific KPIs. Keys must match sector codes used in IDX_TICKERS below.
SECTOR_KPIS: dict[str, list[str]] = {
    "BANK": [
        "idx:LoansAndAdvances", "idx:CustomerDeposits", "idx:CASA", "idx:CASARatio",
        "idx:NetInterestMargin", "idx:LoanToDepositRatio", "idx:BOPO",
        "idx:CostToIncomeRatio", "idx:ReturnOnAssetsBank", "idx:CostOfCredit",
        "idx:LoanAtRiskLAR", "idx:NPLCoverageRatio", "idx:NonPerformingLoansGross",
        "idx:CapitalAdequacyRatio", "idx:PPOP",
    ],
    "COAL": [
        "idx:CoalProductionVolume", "idx:CoalAveragePriceASP", "idx:CoalCashCostPerTon",
        "idx:StripRatio", "idx:OverburdenRemoval", "idx:DomesticMarketObligationRatio",
        "idx:MiningReservesMt",
    ],
    "NICKEL": [
        "idx:NickelOreProduction", "idx:FerroNickelOutput", "idx:MHPProduction",
        "idx:NickelCashCostPerTon", "idx:SmelterUtilizationRate", "idx:MiningReservesMt",
    ],
    "GOLD_COPPER": [
        "idx:GoldProductionOz", "idx:CopperCathodeOutputMT", "idx:AllInSustainingCost",
        "idx:CopperConcentrateGrade", "idx:SmelterTCRCDeductions", "idx:GoldReservesOz",
        "idx:ByProductCreditsUSDOz",
    ],
    "OIL_GAS": [
        "idx:ProvedReserves2P", "idx:OilProductionBOPD", "idx:GasProductionMMSCFD",
        "idx:LiftingCostPerBOE", "idx:RealizedICP", "idx:RealizedGasASP",
        "idx:RigUtilization", "idx:ReserveReplacementRatio",
    ],
    "RENEWABLE_ENERGY": [
        "idx:InstalledCapacityMW", "idx:NetGenerationGWh", "idx:CapacityFactor",
        "idx:RealizedElectricityTariff", "idx:SteamProductionTonnes",
        "idx:ProvenGeothermalReservesMWe",
    ],
    "PETROCHEMICAL": [
        "idx:NaphthaCrackerUtilization", "idx:PolyolefinProductionMT",
        "idx:PolymerNaphthaSpread", "idx:AmmoniaProductionMT", "idx:UreaProductionMT",
        "idx:PlantTurnaroundEvent",
    ],
    "PULP_PAPER": [
        "idx:PulpProductionCapacityMT", "idx:PaperPackagingVolumeMT",
        "idx:PulpExportASPUSDMT", "idx:WoodFiberSelfSufficiency", "idx:PulpCashCostUSDMT",
    ],
    "BASIC_MATERIALS": ["ifrs:Revenue", "idx:EBITDA"],
    "TELCO": ["idx:DataTrafficPetabytes", "idx:BlendedARPU", "idx:MobileSubscribers"],
    "TOWER": ["idx:TowerCount", "idx:TenancyRatio"],
    "AUTOMOTIVE": [
        "idx:CarWholesaleUnits", "idx:CarRetailUnits", "idx:MotorcycleUnitSales",
        "idx:MarketShareGaikindo", "idx:ExportVolumeUnits", "idx:EVModelMixShare",
        "idx:ComponentContentPerVehicle",
    ],
    "CONSUMER_STAPLES": [
        "idx:BrandedFoodVolumeMT", "idx:VolumePriceMixDecomp", "idx:InventoryDays",
    ],
    "POULTRY": [
        "idx:FeedMillSalesVolumeMT", "idx:DayOldChickVolume", "idx:DOCFarmgatePrice",
        "idx:LiveBirdPriceIDR", "idx:RawMaterialExposureSoyCorn",
    ],
    "RETAIL": [
        "idx:SameStoreSalesGrowth", "idx:TotalStoreCount", "idx:NetNewStoreOpenings",
        "idx:SalesPerSquareMeter", "idx:PrivateLabelShare", "idx:AverageTicketSize",
        "idx:InventoryDays",
    ],
    "PHARMACEUTICAL": [
        "idx:EthicalRevenueShare", "idx:OTCRevenueShare", "idx:APIImportExposure",
        "idx:TollManufacturingVolume", "idx:BPJSCatalogRevenueShare",
    ],
    "HOSPITAL": [
        "idx:OperationalBedsCount", "idx:BedOccupancyRate", "idx:AverageLengthOfStay",
        "idx:InpatientAdmissions", "idx:OutpatientVisits", "idx:ARPOB",
        "idx:BPJSRevenueShare",
    ],
    "CPO": [
        "idx:MaturePlantedArea", "idx:FfbProduction", "idx:CPOProductionVolume",
        "idx:PalmKernelProduction", "idx:OilExtractionRate", "idx:CPOAveragePriceASP",
        "idx:CPOCashCostPerKg",
    ],
    "PROPERTY": [
        "idx:MarketingSalesPresales", "idx:TotalLandbankHectares",
        "idx:RecurringIncomeShare", "idx:MallOccupancyRate",
        "idx:UnrecognizedRevenueBacklog",
    ],
    "CONTRACTOR": [
        "idx:NewContractWins", "idx:OrderBookBacklog", "idx:BurnRateConversion",
        "idx:GovernmentProjectMix", "idx:ReceivablesDaysContractor",
        "idx:KSOJointOperationCF",
    ],
    "TOLL_ROAD": [
        "idx:AverageDailyTraffic", "idx:TollTariffAdjustment",
        "idx:OperationalTollLengthKm", "idx:ConcessionRemainingYears",
    ],
    "PORT": [
        "idx:ContainerThroughputTEUs", "idx:CBUCarTerminalVolume",
        "idx:StevedoringRevenuePerTEU", "idx:ConcessionRemainingYears",
    ],
    "SHIPPING": [
        "idx:FleetCount", "idx:TotalDWT", "idx:CharterRate",
        "idx:BunkerFuelCost", "idx:VesselUtilization",
    ],
    "DIGITAL": [
        "idx:GrossTransactionValue", "idx:GrossMerchandiseValue", "idx:TakeRate",
        "idx:MonthlyActiveTransactingUsers", "idx:ContributionMargin",
        "idx:AdjustedEBITDADigital", "idx:PromotionalIncentives",
    ],
}

# Full IDX ticker universe. (ticker, company_name, sector_code, sub_sector, index_membership)
IDX_TICKERS: list[tuple[str, str, str, str, str]] = [
    # ---- BANK ----
    ("BMRI", "PT Bank Mandiri (Persero) Tbk", "BANK", "State-Owned Banks", "LQ45"),
    ("BBRI", "PT Bank Rakyat Indonesia (Persero) Tbk", "BANK", "State-Owned Banks", "LQ45"),
    ("BBCA", "PT Bank Central Asia Tbk", "BANK", "Private Commercial Banks", "LQ45"),
    ("BBNI", "PT Bank Negara Indonesia (Persero) Tbk", "BANK", "State-Owned Banks", "LQ45"),
    ("BRIS", "PT Bank Syariah Indonesia Tbk", "BANK", "Sharia Banking", "LQ45"),
    ("BDMN", "PT Bank Danamon Indonesia Tbk", "BANK", "Private Commercial Banks", "KOMPAS100"),
    ("BNGA", "PT Bank CIMB Niaga Tbk", "BANK", "Private Commercial Banks", "KOMPAS100"),
    ("BBTN", "PT Bank Tabungan Negara (Persero) Tbk", "BANK", "State-Owned Banks", "KOMPAS100"),
    ("BJBR", "PT Bank Pembangunan Daerah Jawa Barat Tbk", "BANK", "Regional Development Banks", "KOMPAS100"),
    ("BJTM", "PT Bank Pembangunan Daerah Jawa Timur Tbk", "BANK", "Regional Development Banks", "KOMPAS100"),
    ("BTPN", "PT Bank BTPN Tbk", "BANK", "Private Commercial Banks", "KOMPAS100"),
    ("NISP", "PT Bank OCBC NISP Tbk", "BANK", "Private Commercial Banks", "KOMPAS100"),
    ("ARTO", "PT Bank Jago Tbk", "BANK", "Digital Banking", "KOMPAS100"),
    ("BBHI", "PT Allo Bank Indonesia Tbk", "BANK", "Digital Banking", "KOMPAS100"),
    ("BBYB", "PT Bank Neo Commerce Tbk", "BANK", "Digital Banking", "IDX"),
    ("BANK", "PT Bank Aladin Syariah Tbk", "BANK", "Digital Sharia Banking", "IDX"),
    ("AMAR", "PT Bank Amar Indonesia Tbk", "BANK", "Digital Banking", "IDX"),
    ("BTPS", "PT Bank BTPN Syariah Tbk", "BANK", "Sharia Banking", "KOMPAS100"),
    ("BABP", "PT Bank MNC Internasional Tbk", "BANK", "Private Commercial Banks", "IDX"),
    ("BMAS", "PT Bank Maspion Indonesia Tbk", "BANK", "Private Commercial Banks", "IDX"),
    ("MEGA", "PT Bank Mega Tbk", "BANK", "Private Commercial Banks", "IDX"),
    ("PNBN", "PT Bank Pan Indonesia Tbk", "BANK", "Private Commercial Banks", "KOMPAS100"),
    ("BNII", "PT Bank Maybank Indonesia Tbk", "BANK", "Private Commercial Banks", "IDX"),
    # ---- COAL ----
    ("ADRO", "PT Adaro Energy Indonesia Tbk", "COAL", "Thermal Coal", "LQ45"),
    ("PTBA", "PT Bukit Asam Tbk", "COAL", "Thermal Coal", "LQ45"),
    ("ITMG", "PT Indo Tambangraya Mega Tbk", "COAL", "Thermal Coal", "LQ45"),
    ("HRUM", "PT Harum Energy Tbk", "COAL", "Coal & Nickel", "LQ45"),
    ("INDY", "PT Indika Energy Tbk", "COAL", "Diversified Coal & Energy", "LQ45"),
    ("BUMI", "PT Bumi Resources Tbk", "COAL", "Thermal Coal", "KOMPAS100"),
    ("BYAN", "PT Bayan Resources Tbk", "COAL", "Thermal Coal", "KOMPAS100"),
    ("GEMS", "PT Golden Energy Mines Tbk", "COAL", "Thermal Coal", "KOMPAS100"),
    ("ITMA", "PT Sumber Global Energy Tbk", "COAL", "Thermal Coal", "IDX"),
    ("MCOL", "PT Prima Andalan Mandiri Tbk", "COAL", "Coal Mining", "KOMPAS100"),
    ("DOID", "PT Delta Dunia Makmur Tbk", "COAL", "Mining Services", "KOMPAS100"),
    ("ABMM", "PT ABM Investama Tbk", "COAL", "Integrated Mining Services", "KOMPAS100"),
    ("UNTR", "PT United Tractors Tbk", "COAL", "Heavy Equipment & Mining Contracting", "LQ45"),
    ("DEWA", "PT Darma Henwa Tbk", "COAL", "Mining Services", "IDX"),
    ("KKGI", "PT Resource Alam Indonesia Tbk", "COAL", "Coal Mining", "IDX"),
    ("BOSS", "PT Borneo Olah Sarana Sukses Tbk", "COAL", "Coal Mining", "IDX"),
    ("BSSR", "PT Baramulti Suksessarana Tbk", "COAL", "Coal Mining", "IDX"),
    ("TOBA", "PT TBS Energi Utama Tbk", "COAL", "Coal & Renewable Energy", "IDX"),
    # ---- NICKEL ----
    ("NCKL", "PT Trimegah Bangun Persada Tbk", "NICKEL", "Nickel Smelting & Mining", "KOMPAS100"),
    ("INCO", "PT Vale Indonesia Tbk", "NICKEL", "Nickel Mining", "LQ45"),
    ("MBMA", "PT Merdeka Battery Materials Tbk", "NICKEL", "Nickel & Battery Materials", "KOMPAS100"),
    ("IFSH", "PT Ifishdeco Tbk", "NICKEL", "Nickel Mining", "IDX"),
    ("DKFT", "PT Central Omega Resources Tbk", "NICKEL", "Nickel Mining", "IDX"),
    # ---- GOLD_COPPER ----
    ("PSAB", "PT J Resources Asia Pasifik Tbk", "GOLD_COPPER", "Gold Mining", "IDX"),
    ("AMMN", "PT Amman Mineral Internasional Tbk", "GOLD_COPPER", "Gold & Copper Mining", "LQ45"),
    ("MDKA", "PT Merdeka Copper Gold Tbk", "GOLD_COPPER", "Gold & Copper", "LQ45"),
    ("ANTM", "PT Aneka Tambang Tbk", "GOLD_COPPER", "Gold & Nickel Mining", "LQ45"),
    ("BRMS", "PT Bumi Resources Minerals Tbk", "GOLD_COPPER", "Gold & Zinc Mining", "IDX"),
    ("ARCI", "PT Archi Indonesia Tbk", "GOLD_COPPER", "Gold Mining", "IDX"),
    # ---- OIL_GAS ----
    ("MEDC", "PT Medco Energi Internasional Tbk", "OIL_GAS", "Oil & Gas E&P", "LQ45"),
    ("PGAS", "PT Perusahaan Gas Negara Tbk", "OIL_GAS", "Gas Distribution", "LQ45"),
    ("AKRA", "PT AKR Corporindo Tbk", "OIL_GAS", "Fuel Distribution & Logistics", "LQ45"),
    ("ELSA", "PT Elnusa Tbk", "OIL_GAS", "Upstream Energy Services", "KOMPAS100"),
    ("ENRG", "PT Energi Mega Persada Tbk", "OIL_GAS", "Oil & Gas E&P", "KOMPAS100"),
    ("RAJA", "PT Rukun Raharja Tbk", "OIL_GAS", "Gas Infrastructure", "KOMPAS100"),
    ("APEX", "PT Apexindo Pratama Duta Tbk", "OIL_GAS", "Drilling Services", "IDX"),
    ("WINS", "PT Wintermar Offshore Marine Tbk", "OIL_GAS", "Offshore Support Services", "IDX"),
    ("SUNI", "PT Sunindo Pratama Tbk", "OIL_GAS", "Oilfield Services", "IDX"),
    ("LEAD", "PT Logindo Samudramakmur Tbk", "OIL_GAS", "Offshore Marine Services", "IDX"),
    # ---- RENEWABLE_ENERGY ----
    ("BREN", "PT Barito Renewables Energy Tbk", "RENEWABLE_ENERGY", "Geothermal Power Generation", "LQ45"),
    ("PGEO", "PT Pertamina Geothermal Energy Tbk", "RENEWABLE_ENERGY", "Geothermal Utilities", "IDX"),
    ("KEEN", "PT Kencana Energi Lestari Tbk", "RENEWABLE_ENERGY", "Hydro & Renewable Power", "IDX"),
    ("ARKO", "PT Arkora Hydro Tbk", "RENEWABLE_ENERGY", "Mini-Hydro Power", "IDX"),
    ("POWR", "PT Cikarang Listrindo Tbk", "RENEWABLE_ENERGY", "Power Generation", "KOMPAS100"),
    ("TGRA", "PT Terregra Asia Energy Tbk", "RENEWABLE_ENERGY", "Renewable Power", "IDX"),
    # ---- PETROCHEMICAL ----
    ("TPIA", "PT Chandra Asri Pacific Tbk", "PETROCHEMICAL", "Petrochemicals", "LQ45"),
    ("BRPT", "PT Barito Pacific Tbk", "PETROCHEMICAL", "Petrochemicals & Energy Conglomerate", "LQ45"),
    ("ESSA", "PT Essa Industries Indonesia Tbk", "PETROCHEMICAL", "Ammonia & LPG", "IDX"),
    # ---- PULP_PAPER ----
    ("INKP", "PT Indah Kiat Pulp & Paper Tbk", "PULP_PAPER", "Pulp & Paper Integrated", "LQ45"),
    ("TKIM", "PT Pabrik Kertas Tjiwi Kimia Tbk", "PULP_PAPER", "Paper Integrated", "LQ45"),
    ("FASW", "PT Fajar Surya Wisesa Tbk", "PULP_PAPER", "Paper & Packaging", "IDX"),
    ("SPMA", "PT Suparma Tbk", "PULP_PAPER", "Paper Manufacturing", "IDX"),
    ("KBRI", "PT Kertas Basuki Rachmat Indonesia Tbk", "PULP_PAPER", "Paper Manufacturing", "IDX"),
    # ---- BASIC_MATERIALS (cement / paints) ----
    ("INTP", "PT Indocement Tunggal Prakarsa Tbk", "BASIC_MATERIALS", "Cement", "LQ45"),
    ("SMGR", "PT Semen Indonesia (Persero) Tbk", "BASIC_MATERIALS", "Cement", "LQ45"),
    ("SMBR", "PT Semen Baturaja (Persero) Tbk", "BASIC_MATERIALS", "Cement", "IDX"),
    ("AVIA", "PT Avia Avian Tbk", "BASIC_MATERIALS", "Paints & Coatings", "KOMPAS100"),
    # ---- TELCO ----
    ("TLKM", "PT Telkom Indonesia (Persero) Tbk", "TELCO", "Integrated Telecommunications", "LQ45"),
    ("ISAT", "PT Indosat Tbk", "TELCO", "Wireless Telecommunications", "LQ45"),
    ("EXCL", "PT XL Axiata Tbk", "TELCO", "Wireless Telecommunications", "LQ45"),
    ("FREN", "PT Smartfren Telecom Tbk", "TELCO", "Wireless Telecommunications", "IDX"),
    # ---- TOWER ----
    ("MTEL", "PT Dayamitra Telekomunikasi Tbk", "TOWER", "Telecom Infrastructure", "LQ45"),
    ("TOWR", "PT Sarana Menara Nusantara Tbk", "TOWER", "Telecom Towers", "LQ45"),
    ("TBIG", "PT Tower Bersama Infrastructure Tbk", "TOWER", "Telecom Towers", "LQ45"),
    ("IBST", "PT Inti Bangun Sejahtera Tbk", "TOWER", "Telecom Towers", "IDX"),
    ("BALI", "PT Bali Towerindo Sentra Tbk", "TOWER", "Telecom Towers", "IDX"),
    ("CENT", "PT Centratama Telekomunikasi Indonesia Tbk", "TOWER", "Telecom Towers", "IDX"),
    # ---- AUTOMOTIVE ----
    ("ASII", "PT Astra International Tbk", "AUTOMOTIVE", "Automotive & Conglomerate", "LQ45"),
    ("AUTO", "PT Astra Otoparts Tbk", "AUTOMOTIVE", "Automotive Components", "KOMPAS100"),
    ("DRMA", "PT Dharma Polimetal Tbk", "AUTOMOTIVE", "Automotive Components", "IDX"),
    ("SMSM", "PT Selamat Sempurna Tbk", "AUTOMOTIVE", "Automotive Filters", "IDX"),
    ("VKTR", "PT VKTR Teknologi Mobilitas Tbk", "AUTOMOTIVE", "Electric Vehicle Components", "IDX"),
    ("GJTL", "PT Gajah Tunggal Tbk", "AUTOMOTIVE", "Tires", "IDX"),
    ("MASA", "PT Multistrada Arah Sarana Tbk", "AUTOMOTIVE", "Tires", "IDX"),
    ("IMAS", "PT Indomobil Sukses Internasional Tbk", "AUTOMOTIVE", "Automotive Distributor", "IDX"),
    ("HEXA", "PT Hexindo Adiperkasa Tbk", "AUTOMOTIVE", "Heavy Equipment", "KOMPAS100"),
    # ---- CONSUMER_STAPLES ----
    ("ICBP", "PT Indofood CBP Sukses Makmur Tbk", "CONSUMER_STAPLES", "Packaged Food & Beverages", "LQ45"),
    ("INDF", "PT Indofood Sukses Makmur Tbk", "CONSUMER_STAPLES", "Diversified Food", "LQ45"),
    ("MYOR", "PT Mayora Indah Tbk", "CONSUMER_STAPLES", "Packaged Food", "LQ45"),
    ("UNVR", "PT Unilever Indonesia Tbk", "CONSUMER_STAPLES", "Personal & Home Care", "LQ45"),
    ("CMRY", "PT Cisarua Mountain Dairy Tbk", "CONSUMER_STAPLES", "Dairy & Processed Meats", "KOMPAS100"),
    ("ULTJ", "PT Ultra Jaya Milk Industry Tbk", "CONSUMER_STAPLES", "Dairy & Beverages", "IDX"),
    ("CLEO", "PT Sariguna Primatirta Tbk", "CONSUMER_STAPLES", "Bottled Drinking Water", "KOMPAS100"),
    ("ROTI", "PT Nippon Indosari Corpindo Tbk", "CONSUMER_STAPLES", "Packaged Bakery", "IDX"),
    ("GOOD", "PT Garudafood Putra Putri Jaya Tbk", "CONSUMER_STAPLES", "Packaged Snacks", "IDX"),
    ("STTP", "PT Siantar Top Tbk", "CONSUMER_STAPLES", "Packaged Snacks", "IDX"),
    ("HMSP", "PT H.M. Sampoerna Tbk", "CONSUMER_STAPLES", "Tobacco & Cigarettes", "KOMPAS100"),
    ("GGRM", "PT Gudang Garam Tbk", "CONSUMER_STAPLES", "Tobacco & Cigarettes", "KOMPAS100"),
    ("WIIM", "PT Wismilak Inti Makmur Tbk", "CONSUMER_STAPLES", "Tobacco", "KOMPAS100"),
    # ---- POULTRY ----
    ("CPIN", "PT Charoen Pokphand Indonesia Tbk", "POULTRY", "Poultry & Feed Integration", "LQ45"),
    ("JPFA", "PT Japfa Comfeed Indonesia Tbk", "POULTRY", "Poultry & Feed Integration", "LQ45"),
    ("MAIN", "PT Malindo Feedmill Tbk", "POULTRY", "Poultry & Feed", "KOMPAS100"),
    ("SIPD", "PT Sreeya Sewu Indonesia Tbk", "POULTRY", "Poultry Processing", "IDX"),
    ("CPRO", "PT Central Proteina Prima Tbk", "POULTRY", "Aquaculture", "KOMPAS100"),
    # ---- RETAIL ----
    ("AMRT", "PT Sumber Alfaria Tbk", "RETAIL", "Retail & Minimarkets", "LQ45"),
    ("MIDI", "PT Midi Utama Indonesia Tbk", "RETAIL", "Minimarkets", "IDX"),
    ("ACES", "PT Aspirasi Hidup Indonesia Tbk", "RETAIL", "Home Improvement Retail", "LQ45"),
    ("MAPI", "PT Mitra Adiperkasa Tbk", "RETAIL", "Fashion & Department Stores", "KOMPAS100"),
    ("MAPA", "PT MAP Aktif Adiperkasa Tbk", "RETAIL", "Sports Retail", "KOMPAS100"),
    ("ERAA", "PT Erajaya Swasembada Tbk", "RETAIL", "Mobile Device Retail", "KOMPAS100"),
    ("RALS", "PT Ramayana Lestari Sentosa Tbk", "RETAIL", "Department Stores", "KOMPAS100"),
    ("LPPF", "PT Matahari Department Store Tbk", "RETAIL", "Department Stores", "IDX"),
    ("CSAP", "PT Catur Sentosa Adiprana Tbk", "RETAIL", "Home Improvement Distribution", "IDX"),
    # ---- PHARMACEUTICAL ----
    ("KLBF", "PT Kalbe Farma Tbk", "PHARMACEUTICAL", "Pharmaceuticals & Healthcare", "LQ45"),
    ("SIDO", "PT Industri Jamu dan Farmasi Sido Muncul Tbk", "PHARMACEUTICAL", "Herbal & Consumer Health", "KOMPAS100"),
    ("TSPC", "PT Tempo Scan Pacific Tbk", "PHARMACEUTICAL", "Pharmaceuticals & Consumer", "IDX"),
    ("DVLA", "PT Darya-Varia Laboratoria Tbk", "PHARMACEUTICAL", "Pharmaceuticals", "IDX"),
    ("PYFA", "PT Pyridam Farma Tbk", "PHARMACEUTICAL", "Pharmaceuticals", "IDX"),
    ("KAEF", "PT Kimia Farma Tbk", "PHARMACEUTICAL", "State-Owned Pharma & Retail", "IDX"),
    ("INAF", "PT Indofarma Tbk", "PHARMACEUTICAL", "State-Owned Pharma", "IDX"),
    ("PEHA", "PT Phapros Tbk", "PHARMACEUTICAL", "Pharmaceuticals", "IDX"),
    ("MERK", "PT Merck Tbk", "PHARMACEUTICAL", "Pharmaceuticals", "IDX"),
    ("SOHO", "PT Soho Global Health Tbk", "PHARMACEUTICAL", "Pharmaceuticals & Distribution", "IDX"),
    # ---- HOSPITAL ----
    ("MIKA", "PT Mitra Keluarga Karyasehat Tbk", "HOSPITAL", "Private Hospitals", "LQ45"),
    ("HEAL", "PT Medikaloka Hermina Tbk", "HOSPITAL", "Private Hospitals", "LQ45"),
    ("SILO", "PT Siloam International Hospitals Tbk", "HOSPITAL", "Private Hospitals", "KOMPAS100"),
    ("SAME", "PT Sarana Meditama Metropolitan Tbk", "HOSPITAL", "Private Hospitals", "IDX"),
    ("SRAJ", "PT Sejahteraraya Anugrahjaya Tbk", "HOSPITAL", "Private Hospitals", "IDX"),
    ("PRDA", "PT Prodia Widyahusada Tbk", "HOSPITAL", "Clinical Laboratories", "KOMPAS100"),
    ("DGNS", "PT Diagnos Laboratorium Utama Tbk", "HOSPITAL", "Clinical Laboratories", "IDX"),
    ("CARE", "PT Metro Healthcare Indonesia Tbk", "HOSPITAL", "Private Hospitals", "IDX"),
    # ---- CPO ----
    ("AALI", "PT Astra Agro Lestari Tbk", "CPO", "Palm Oil Plantations", "KOMPAS100"),
    ("LSIP", "PT PP London Sumatra Indonesia Tbk", "CPO", "Palm Oil Plantations", "KOMPAS100"),
    ("SIMP", "PT Salim Ivomas Pratama Tbk", "CPO", "Agribusiness & Edible Oils", "KOMPAS100"),
    ("TAPG", "PT Triputra Agro Persada Tbk", "CPO", "Palm Oil Plantations", "KOMPAS100"),
    ("DSNG", "PT Dharma Satya Nusantara Tbk", "CPO", "Palm Oil & Wood Products", "KOMPAS100"),
    ("SSMS", "PT Sawit Sumbermas Sarana Tbk", "CPO", "Palm Oil", "KOMPAS100"),
    ("STAA", "PT Sumber Tani Agung Resources Tbk", "CPO", "Palm Oil", "KOMPAS100"),
    ("SGRO", "PT Sampoerna Agro Tbk", "CPO", "Palm Oil Plantations", "IDX"),
    ("BWPT", "PT Eagle High Plantations Tbk", "CPO", "Palm Oil Plantations", "IDX"),
    ("ANJT", "PT Austindo Nusantara Jaya Tbk", "CPO", "Palm Oil Plantations", "IDX"),
    ("SMAR", "PT SMART Tbk", "CPO", "Palm Oil Integrated", "IDX"),
    ("UNSP", "PT Bakrie Sumatera Plantations Tbk", "CPO", "Palm Oil & Rubber", "IDX"),
    # ---- PROPERTY ----
    ("CTRA", "PT Ciputra Development Tbk", "PROPERTY", "Residential & Commercial Property", "KOMPAS100"),
    ("BSDE", "PT Bumi Serpong Damai Tbk", "PROPERTY", "Township & Residential Property", "KOMPAS100"),
    ("PWON", "PT Pakuwon Jati Tbk", "PROPERTY", "Retail Malls & Mixed-Use Property", "KOMPAS100"),
    ("SMRA", "PT Summarecon Agung Tbk", "PROPERTY", "Township Property", "KOMPAS100"),
    ("ASRI", "PT Alam Sutera Realty Tbk", "PROPERTY", "Township Property", "KOMPAS100"),
    ("LPKR", "PT Lippo Karawaci Tbk", "PROPERTY", "Integrated Real Estate & Healthcare", "KOMPAS100"),
    ("DILD", "PT Intiland Development Tbk", "PROPERTY", "Real Estate", "KOMPAS100"),
    ("APLN", "PT Agung Podomoro Land Tbk", "PROPERTY", "Mixed-Use Property", "IDX"),
    ("CTRS", "PT Ciputra Surya Tbk", "PROPERTY", "Residential Property", "IDX"),
    ("JRPT", "PT Jaya Real Property Tbk", "PROPERTY", "Residential Property", "IDX"),
    ("BAPA", "PT Bekasi Asri Pemula Tbk", "PROPERTY", "Residential Property", "IDX"),
    ("LPCK", "PT Lippo Cikarang Tbk", "PROPERTY", "Industrial Property", "IDX"),
    ("KIJA", "PT Kawasan Industri Jababeka Tbk", "PROPERTY", "Industrial Estate", "IDX"),
    ("BEST", "PT Bekasi Fajar Industrial Estate Tbk", "PROPERTY", "Industrial Estate", "IDX"),
    ("DMAS", "PT Puradelta Lestari Tbk", "PROPERTY", "Industrial Estate", "IDX"),
    # ---- CONTRACTOR ----
    ("PTPP", "PT PP (Persero) Tbk", "CONTRACTOR", "State-Owned Infrastructure Construction", "KOMPAS100"),
    ("WIKA", "PT Wijaya Karya (Persero) Tbk", "CONTRACTOR", "State-Owned Construction & EPC", "KOMPAS100"),
    ("ADHI", "PT Adhi Karya (Persero) Tbk", "CONTRACTOR", "State-Owned Rail & EPC Construction", "KOMPAS100"),
    ("WSKT", "PT Waskita Karya (Persero) Tbk", "CONTRACTOR", "State-Owned Infrastructure Construction", "IDX"),
    ("TOTL", "PT Total Bangun Persada Tbk", "CONTRACTOR", "Building Construction", "KOMPAS100"),
    ("WEGE", "PT Wijaya Karya Bangunan Gedung Tbk", "CONTRACTOR", "Building Construction", "KOMPAS100"),
    ("DGIK", "PT Nusa Konstruksi Enjiniring Tbk", "CONTRACTOR", "General Contractor", "IDX"),
    ("PPRE", "PT PP Presisi Tbk", "CONTRACTOR", "Civil Construction", "IDX"),
    ("NRCA", "PT Nusa Raya Cipta Tbk", "CONTRACTOR", "Building Construction", "IDX"),
    ("ACST", "PT Acset Indonusa Tbk", "CONTRACTOR", "Civil Construction", "IDX"),
    ("JKON", "PT Jaya Konstruksi Manggala Pratama Tbk", "CONTRACTOR", "Civil Construction", "IDX"),
    # ---- TOLL_ROAD ----
    ("JSMR", "PT Jasa Marga (Persero) Tbk", "TOLL_ROAD", "Toll Road Operator", "KOMPAS100"),
    ("META", "PT Nusantara Infrastructure Tbk", "TOLL_ROAD", "Toll Road Operator", "IDX"),
    ("CMNP", "PT Citra Marga Nusaphala Persada Tbk", "TOLL_ROAD", "Toll Road Operator", "IDX"),
    ("JTPE", "PT Jasuindo Tiga Perkasa Tbk", "TOLL_ROAD", "Toll Related Services", "IDX"),
    # ---- PORT ----
    ("IPCC", "PT Indonesia Kendaraan Terminal Tbk", "PORT", "Car Terminal", "IDX"),
    ("PORT", "PT Nusantara Pelabuhan Handal Tbk", "PORT", "Port Terminal Services", "IDX"),
    ("IPCM", "PT Jasa Armada Indonesia Tbk", "PORT", "Marine Port Services", "IDX"),
    ("TMAS", "PT Temas Tbk", "PORT", "Container Shipping", "IDX"),
    # ---- SHIPPING ----
    ("SHIP", "PT Sillo Maritime Perdana Tbk", "SHIPPING", "Marine Shipping", "IDX"),
    ("SMDR", "PT Samudera Indonesia Tbk", "SHIPPING", "Integrated Shipping", "IDX"),
    ("BULL", "PT Buana Lintas Lautan Tbk", "SHIPPING", "Tanker Shipping", "IDX"),
    ("HITS", "PT Humpuss Intermoda Transportasi Tbk", "SHIPPING", "LNG & Tanker Shipping", "IDX"),
    ("SOCI", "PT Soechi Lines Tbk", "SHIPPING", "Tanker & Offshore Shipping", "IDX"),
    ("MBSS", "PT Mitrabahtera Segara Sejati Tbk", "SHIPPING", "Coal Barge Shipping", "IDX"),
    ("TCPI", "PT Transcoal Pacific Tbk", "SHIPPING", "Coal Shipping", "IDX"),
    ("WEHA", "PT WEHA Transportasi Indonesia Tbk", "SHIPPING", "Land Transportation", "IDX"),
    ("BIRD", "PT Blue Bird Tbk", "SHIPPING", "Taxi & Passenger Transport", "IDX"),
    # ---- DIGITAL ----
    ("GOTO", "PT GoTo Gojek Tokopedia Tbk", "DIGITAL", "Digital Ecosystem", "LQ45"),
    ("BUKA", "PT Bukalapak.com Tbk", "DIGITAL", "E-Commerce & Digital", "KOMPAS100"),
    ("EMTK", "PT Elang Mahkota Teknologi Tbk", "DIGITAL", "Media & Technology", "KOMPAS100"),
    ("DCII", "PT DCI Indonesia Tbk", "DIGITAL", "Data Center", "IDX"),
    ("MTDL", "PT Metrodata Electronics Tbk", "DIGITAL", "IT Distribution", "IDX"),
    ("DMMX", "PT Digital Mediatama Maxima Tbk", "DIGITAL", "Digital Advertising", "IDX"),
    ("BELI", "PT Global Digital Niaga Tbk", "DIGITAL", "E-Commerce", "IDX"),
    ("NETV", "PT Net Visi Media Tbk", "DIGITAL", "Digital Media", "IDX"),
    ("KIOS", "PT Kioson Komersial Indonesia Tbk", "DIGITAL", "Digital Distribution", "IDX"),
]


def seed_idx_tickers() -> int:
    settings = get_settings()

    upsert_sql = """
    INSERT INTO issuer_profile (ticker, name, sector, sub_sector, profile_summary_en, last_facts_period, key_kpis)
    VALUES (%(ticker)s, %(name)s, %(sector)s, %(sub_sector)s, %(summary)s, '2025Q4', %(kpis)s)
    ON CONFLICT (ticker) DO UPDATE SET
        name = EXCLUDED.name,
        sector = EXCLUDED.sector,
        sub_sector = EXCLUDED.sub_sector,
        profile_summary_en = COALESCE(issuer_profile.profile_summary_en, EXCLUDED.profile_summary_en),
        key_kpis = EXCLUDED.key_kpis;
    """

    conn_str = settings.postgres_dsn.replace("+asyncpg", "")
    seen: set[str] = set()
    inserted = 0

    with psycopg.connect(conn_str) as conn:
        with conn.cursor() as cur:
            for ticker, name, sector, sub_sector, _index in IDX_TICKERS:
                if ticker in seen:
                    continue
                seen.add(ticker)
                summary = (
                    f"{name} ({ticker}) is an Indonesian issuer classified in sector "
                    f"{sector} ({sub_sector}). Extractors should prioritize the "
                    f"sector-specific KPIs listed in key_kpis when parsing filings."
                )
                sector_kpis = SECTOR_KPIS.get(sector, [])
                kpis = list(dict.fromkeys(BASELINE_KPIS + sector_kpis))

                cur.execute(
                    upsert_sql,
                    {
                        "ticker": ticker,
                        "name": name,
                        "sector": sector,
                        "sub_sector": sub_sector,
                        "summary": summary,
                        "kpis": kpis,
                    },
                )
                inserted += 1
            conn.commit()

    print(f"Successfully seeded/upserted {inserted} issuer profiles into issuer_profile")
    return inserted


if __name__ == "__main__":
    sys.exit(0 if seed_idx_tickers() > 0 else 1)
