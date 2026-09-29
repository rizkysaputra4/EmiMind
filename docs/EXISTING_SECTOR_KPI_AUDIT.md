# Existing Sector KPI Pack Audit — Gap Analysis

**Audit target:** `scripts/seed_idx_tickers.py` → `SECTOR_KPIS`
**Cross-reference:** `scripts/seed_metric_ontology.py`
**Objective:** Identify high-signal, thesis-revealing KPIs currently missing from each sector's contract. Focus on unit economics, pricing power, capacity dynamics, mix shifts, and regulatory moats — *not* generic financials (Revenue, EBITDA, ROE).
**Date:** 2026-09-07
**Auditor:** Coverage review vs. 2024–2026 Indonesian LQ45/KOMPAS100 IR disclosures and peer-standard international disclosures.

---

## Reading guide

Each proposed metric follows the schema of `seed_metric_ontology.py` so it can be dropped in with minimal transformation. `search_hints` should be added to the ontology's `synonyms_id`/`synonyms_en` fields; `regulatory_anchor` (where present) documents when the KPI is legally mandated (OJK, POJK, IDX, ESDM RKAB, PP DMO, etc.) and therefore *must* appear somewhere in the audited disclosure.

Priority guidance for adding to `SECTOR_KPIS`:
- **CRITICAL** — thesis-defining, must add.
- **HIGH** — differentiates leaders vs. laggards.
- **MEDIUM** — nice-to-have; adds nuance.

---

## BANK

**Currently covered:** LoansAndAdvances, CustomerDeposits, CASA, CASARatio, NetInterestMargin, LoanToDepositRatio, BOPO, CostToIncomeRatio, ReturnOnAssetsBank, CostOfCredit, LoanAtRiskLAR, NPLCoverageRatio, NonPerformingLoansGross, CapitalAdequacyRatio, PPOP.

The pack over-indexes on income-statement ratios and asset quality *stocks* but misses (a) funding-mix dynamics that drive NIM sustainability, (b) the fee-income engine that defines BBCA/BMRI vs peer valuation gaps, (c) digital channel KPIs that OJK's `POJK 12/2018` (digital banking) essentially requires disclosure of, and (d) the sharia carve-out material for BRIS/BTPS/BANK (Aladin).

**Missed high-signal KPIs (CRITICAL):**

- `metric_id`: `idx:FeeBasedIncomeRatio`
  - name_en: Fee-Based Income to Operating Income (%)
  - name_id: Rasio Pendapatan Berbasis Komisi
  - unit: PERCENT · category: PROFITABILITY
  - why_it_matters: Non-interest income share is the single best proxy for franchise strength — BBCA's ~28% vs peer ~15% explains most of its P/BV premium and insulates against NIM compression cycles.
  - search_hints: "Pendapatan Berbasis Komisi", "Fee Based Income", "Non-Interest Income Ratio", "Fee/Operating Income"
  - source_priority: INVESTOR_PRESENTATION, ANNUAL_REPORT
  - regulatory_anchor: OJK reports operational income breakdown per SEOJK 9/SEOJK.03/2020 (bank publikasi).

- `metric_id`: `idx:CostOfDeposits`
  - name_en: Cost of Deposits (Blended Funding Cost, %)
  - name_id: Biaya Dana (Cost of Fund)
  - unit: PERCENT · category: FUNDING_COST
  - why_it_matters: NIM alone hides whether margin comes from asset repricing or deposit franchise; CoF trajectory vs. BI 7DRR reveals deposit beta — decisive during 2023–2025 tightening cycle.
  - search_hints: "Cost of Fund", "Biaya Dana", "Blended Deposit Rate", "CoF"
  - source_priority: INVESTOR_PRESENTATION, ANNUAL_REPORT

- `metric_id`: `idx:WholesaleFundingRatio`
  - name_en: Wholesale Funding Ratio (%)
  - name_id: Rasio Pendanaan Wholesale
  - unit: PERCENT · category: FUNDING_STRUCTURE
  - why_it_matters: Time deposits >IDR 2bn + interbank + bonds; a >30% share signals franchise fragility (see NISP, BNGA) and drives regulatory NSFR strain.
  - search_hints: "Wholesale Funding", "Deposito Nominal Besar", "Interbank Placement Liabilities"
  - source_priority: PILLAR_3, ANNUAL_REPORT
  - regulatory_anchor: POJK 50/POJK.03/2017 (NSFR) requires deposit categorization.

- `metric_id`: `idx:DigitalActiveUsers`
  - name_en: Digital Channel Active Users (mn)
  - name_id: Pengguna Aktif Kanal Digital
  - unit: USERS_MILLION · category: DIGITAL_ADOPTION
  - why_it_matters: myBCA (~28mn), BRImo (~40mn), Livin' (~28mn) are now primary sales channels — engagement growth is a leading indicator of CASA stickiness and fee income cross-sell.
  - search_hints: "Digital Users", "Pengguna Aktif", "myBCA", "BRImo", "Livin' by Mandiri", "Wondr"
  - source_priority: INVESTOR_PRESENTATION, PUBLIC_EXPOSE

- `metric_id`: `idx:DigitalTransactionCountBn`
  - name_en: Digital Transaction Count (bn/year)
  - name_id: Volume Transaksi Digital
  - unit: TRANSACTIONS_BILLION · category: DIGITAL_ADOPTION
  - why_it_matters: Transactions per active user reveal channel stickiness independent of "user" definition inflation; drives fee-per-transaction economics.
  - search_hints: "Jumlah Transaksi Digital", "Digital Transaction Volume", "Frekuensi Transaksi Mobile Banking"

**HIGH:**

- `idx:LiquidityCoverageRatio` (LCR %) — POJK 42/POJK.03/2015 mandated; separate from LDR and often more binding.
- `idx:NetStableFundingRatio` (NSFR %) — POJK 50/POJK.03/2017; captures term-funding mismatch.
- `idx:CasaCostOfFund` — CASA-only weighted rate; separates transactional vs. deposit-shop deposits.
- `idx:LoanBookByEconomicSegment` (SME/Corp/Micro/Consumer mix %) — thesis differentiator for BBRI (micro/ultra-micro), BBTN (mortgage subsidy), BTPS (grameen).
- `idx:ShariaFinancingReceivables` — for BRIS/BTPS/BANK, distinguish murabahah vs. musyarakah/mudharabah mix.
- `idx:RestructuredLoansCovid` (restructured book residual) — legacy POJK 17/POJK.03/2021 tail; still ~2-3% of book.
- `idx:GrossFeeYieldOnLoans` — trade finance, bancassurance, wealth-mgmt fees / average loans.

## COAL

**Currently covered:** CoalProductionVolume, CoalAveragePriceASP, CoalCashCostPerTon, StripRatio, OverburdenRemoval, DomesticMarketObligationRatio, MiningReservesMt.

The pack captures the volume/price/cost triangle but misses the hedging book (decisive in 2023 downcycle), sales-contract structure (take-or-pay vs. spot), and blending economics that separate BYAN/BUMI from ADRO/PTBA. Life-of-mine and RKAB compliance are also missing.

**CRITICAL:**

- `metric_id`: `idx:CoalSalesContractedForwardPct`
  - name_en: Contracted/Hedged Sales for Next 12M (% of guided volume)
  - name_id: Volume Penjualan Terkontrak 12 Bulan ke Depan
  - unit: PERCENT · category: RISK_HEDGING
  - why_it_matters: A miner with 70% of next-year volume price-hedged (ITMG, PTBA export) has locked earnings visibility; spot-exposed peers (BUMI) swing violently with Newcastle.
  - search_hints: "Hedged Coal Sales", "Volume Terkontrak", "Fixed Price Contract", "Forward Sales"
  - source_priority: INVESTOR_PRESENTATION, ANALYST_BRIEFING

- `metric_id`: `idx:CoalCalorificValueRealized`
  - name_en: Weighted-Avg Realized Calorific Value (kcal/kg GAR)
  - name_id: Nilai Kalori Rata-rata Terealisasi
  - unit: KCAL_PER_KG · category: PRODUCT_MIX
  - why_it_matters: Blend CV determines whether ASP tracks NEX (6,322 kcal), Panamax (5,000), or India spec (4,200); mix shift explains 20%+ ASP moves at flat headline coal price.
  - search_hints: "GAR 4200", "GAR 5000", "Calorific Value", "Nilai Kalori", "Blending Premium"

- `metric_id`: `idx:CoalDMOPriceGap`
  - name_en: DMO Price Discount vs Export ASP (USD/t)
  - name_id: Selisih Harga DMO vs Ekspor
  - unit: USD_PER_TON · category: REGULATORY_COST
  - why_it_matters: Kepmen ESDM 13/K/MB.01/MEM.B/2022 caps DMO price at USD 70/t (PLN); the delta × DMO tonnage is a direct earnings drag that can exceed 8% of net profit.
  - source_priority: MDNA, INVESTOR_PRESENTATION
  - regulatory_anchor: Kepmen ESDM 13/2022, PP 96/2021 revised.

- `metric_id`: `idx:MineLifeYears`
  - name_en: Weighted Life-of-Mine (Years at Guided Production)
  - name_id: Umur Tambang Tersisa
  - unit: YEARS · category: RESERVE_QUALITY
  - why_it_matters: Distinguishes ADRO's ~25-yr reserve backbone from tail-end operators like HRUM's Mahakam pit; drives capex reinvestment vs. dividend policy.
  - source_priority: ANNUAL_REPORT, TECHNICAL_REPORT
  - regulatory_anchor: RKAB submission (Kepmen ESDM 1806/2018) requires production plan vs reserves.

**HIGH:**

- `idx:RoyaltyRateEffective` — post-PP 26/2022 progressive royalty (up to 28%); actual paid vs. statutory reveals thin/thick seam mix.
- `idx:HaulingDistanceKm` — pit-to-port distance; every +5km ≈ USD 0.5/t cost.
- `idx:BargePortThroughputMT` — captive infrastructure moat (PTBA Tarahan, ADRO Kelanis).
- `idx:MetCoalHardCokingShare` — ADMR/BUMI diversification; met-coal ASP 2-3× thermal.
- `idx:StrippingRatioLifeOfMine` vs. current — reveals whether current ratio is sustainable or "cherry-picking" nearer seams.

## NICKEL

**Currently covered:** NickelOreProduction, FerroNickelOutput, MHPProduction, NickelCashCostPerTon, SmelterUtilizationRate, MiningReservesMt.

Missing the entire product-mix axis (matte vs. MHP vs. NPI vs. sulfate), recovery rates, and the EV-battery premium capture story that defines the INCO/HRUM/NCKL vs. ANTM thesis divergence. RKAB tonnage vs. actual is also not tracked.

**CRITICAL:**

- `metric_id`: `idx:NickelProductByForm`
  - name_en: Nickel Output by Product Form (Matte/MHP/NPI/FeNi split)
  - name_id: Komposisi Produk Nikel (Matte/MHP/NPI/FeNi)
  - unit: PERCENT · category: PRODUCT_MIX
  - why_it_matters: Class-1 (matte, MHP → sulfate for EV batteries) commands USD 3-5k/t premium over Class-2 (NPI/FeNi for stainless); mix shift is INCO's core investment thesis vs. NPI-heavy peers.
  - search_hints: "Nickel Matte", "MHP", "Nickel Pig Iron", "Ferronickel", "Nikel Sulfat"

- `metric_id`: `idx:HPALRecoveryRate`
  - name_en: HPAL Nickel Recovery Rate (%)
  - name_id: Tingkat Perolehan HPAL
  - unit: PERCENT · category: PROCESS_EFFICIENCY
  - why_it_matters: HPAL projects (Halmahera, Weda Bay) target 90%+ Ni recovery; sub-85% signals leaching chemistry failure — the exact issue that has plagued Ramu (PNG) and early Sulawesi HPAL trains.
  - search_hints: "HPAL Recovery", "Leaching Efficiency", "Autoclave Recovery"

- `metric_id`: `idx:NickelSulfatePremiumUSD`
  - name_en: Nickel Sulfate Premium vs LME Nickel (USD/t Ni)
  - name_id: Premium Nikel Sulfat terhadap LME
  - unit: USD_PER_TON · category: PRICING_POWER
  - why_it_matters: Battery-grade sulfate has historically traded USD 1,500-3,000/t premium; premium erosion (post-2024 CN oversupply) directly threatens HPAL project IRRs.
  - source_priority: INVESTOR_PRESENTATION, ANALYST_BRIEFING

- `metric_id`: `idx:OreGradeMinedPctNi`
  - name_en: Average Mined Ore Grade (% Ni)
  - name_id: Kadar Nikel Bijih Tertambang
  - unit: PERCENT · category: RESERVE_QUALITY
  - why_it_matters: Saprolite (>1.7% Ni) for RKEF vs. limonite (1.0-1.4%) for HPAL — grade decline signals reserve depletion before tonnage does.

**HIGH:**

- `idx:RKABQuotaUtilization` — actual production vs. ESDM-approved RKAB (Kepmen ESDM 1806.K/30/MEM/2018); overquota triggers moratoriums.
- `idx:SmelterPowerCostUSDPerMWh` — captive coal PP vs. PLN grid; INCO's LNG shift is a differentiator.
- `idx:DownstreamJVEquityShare` — % of smelter output attributable via JV structures (HRUM-CATL/Vale, MDKA-Tsingshan).
- `idx:LimoniteInventoryMT` — feedstock for HPAL; strategic given ore export ban.
- `idx:CarbonIntensityKgCO2PerTNi` — EU CBAM (effective 2026) will price this; Indonesian NPI ~60 kgCO2 vs. Class-1 target <20.

## GOLD_COPPER

**Currently covered:** GoldProductionOz, CopperCathodeOutputMT, AllInSustainingCost, CopperConcentrateGrade, SmelterTCRCDeductions, GoldReservesOz, ByProductCreditsUSDOz.

Missing: hedge book, smelter progression (AMMN Batu Hijau smelter is the ticker's whole thesis), by-product recovery, mine plan life. Also missing local content share (TKDN, Kepmen ESDM 5/2017).

**CRITICAL:**

- `metric_id`: `idx:GoldHedgeBookOz`
  - name_en: Forward/Hedged Gold Sales (oz, tenor-weighted)
  - name_id: Kontrak Penjualan Emas Berjangka
  - unit: OUNCES · category: RISK_HEDGING
  - why_it_matters: MDKA, BRMS historically hedge 20-40% of production 12M forward at pre-rally prices — hedge book explains why headline gold ASP diverges from spot.
  - source_priority: ANNUAL_REPORT, NOTES_TO_FINANCIAL_STATEMENTS

- `metric_id`: `idx:SmelterProgressPct`
  - name_en: Downstream Smelter Physical Progress (%)
  - name_id: Progres Fisik Smelter (%)
  - unit: PERCENT · category: PROJECT_EXECUTION
  - why_it_matters: AMMN's Batu Hijau smelter (target 2024, delayed to 2025-26) directly determines whether concentrate export ban (UU 3/2020) forces production shutdown vs. margin expansion via cathode sales.
  - regulatory_anchor: UU 3/2020, PP 96/2021 — mandates domestic processing by 2023 (extended).

- `metric_id`: `idx:ConcentrateExportQuotaMT`
  - name_en: Concentrate Export Quota (MT/year, ESDM-approved)
  - name_id: Kuota Ekspor Konsentrat
  - unit: TONNES · category: REGULATORY_QUOTA
  - why_it_matters: ESDM allocates residual concentrate export quotas year-by-year (Kepmen ESDM 89.K/2023); shortfall vs. production = forced stockpiling.
  - regulatory_anchor: Kepmen ESDM 89.K/MB.01/MEM.B/2023.

- `metric_id`: `idx:MineablePitLifeYears`
  - name_en: Mineable Pit Life at Guided Throughput (Years)
  - name_id: Umur Tambang Aktif
  - unit: YEARS · category: RESERVE_QUALITY

**HIGH:**

- `idx:CopperRecoveryRate` (%) — flotation efficiency, drives concentrate output per ore ton.
- `idx:TollingRefiningMarginUSDlb` — for MDKA Wetar cathode, PTFI Gresik smelter.
- `idx:GoldStrippingRatio` — waste:ore in gold pits (Tujuh Bukit, Awak Mas).
- `idx:LocalContentTKDNPct` — Kepmen ESDM 5/2017 mandates progressive local content; below-threshold projects face permit risk.
- `idx:BullionSalesVsDoréMix` — cash cycle & pricing power differential.

## OIL_GAS

**Currently covered:** ProvedReserves2P, OilProductionBOPD, GasProductionMMSCFD, LiftingCostPerBOE, RealizedICP, RealizedGasASP, RigUtilization, ReserveReplacementRatio.

Missing: gas contract structure (Take-or-Pay fixed vs. oil-linked HoA), abandonment/site restoration liability trajectory, cost recovery balance under PSC gross-split vs. cost-recovery scheme (PP 27/2017), unitized field share.

**CRITICAL:**

- `metric_id`: `metric_id`: `idx:GasContractMixFixedVsLinked`
  - name_en: Gas Sales Contract Mix (Fixed Price vs. Oil-Linked, %)
  - name_id: Komposisi Kontrak Gas (Harga Tetap vs. Linked)
  - unit: PERCENT · category: PRICING_STRUCTURE
  - why_it_matters: MEDC/PGAS earnings volatility hinges on this — fixed-price PGN contracts (USD 6-7/MMBtu Kepmen ESDM 91/2023) vs. LNG spot-linked cargoes swing gross margin by USD 3-4/MMBtu.
  - regulatory_anchor: Kepmen ESDM 91.K/2023 — HGBT US$6.5/MMBtu for 7 sectors.

- `metric_id`: `idx:CostRecoveryBalanceUSDmn`
  - name_en: Unrecovered Cost Recovery Balance (USD mn)
  - name_id: Saldo Cost Recovery Belum Terpulihkan
  - unit: USD_MILLION · category: PSC_ECONOMICS
  - why_it_matters: For PSC contracts, unrecovered costs sit on SKK Migas ledger and directly convert to future cash; a growing balance signals capex ahead of production.
  - regulatory_anchor: PP 79/2010 (PSC cost recovery mechanism), PP 27/2017 (gross split alternative).

- `metric_id`: `idx:AbandonmentSiteRestorationLiability`
  - name_en: ASR (Abandonment & Site Restoration) Liability Balance
  - name_id: Kewajiban Pembongkaran & Restorasi (ASR)
  - unit: USD_MILLION · category: END_OF_LIFE_OBLIGATIONS
  - why_it_matters: Rokan, Cepu, Mahakam blocks carry USD 1-4bn ASR — PP 79/2010 mandates escrow contributions per BOE; balance vs. escrowed funds is a hidden liability item.
  - source_priority: NOTES_TO_FINANCIAL_STATEMENTS, ANNUAL_REPORT
  - regulatory_anchor: PP 79/2010 art. 20; PermenESDM 15/2018 on ASR fund.

- `metric_id`: `idx:WorkingInterestWeightedProduction`
  - name_en: WI-Adjusted Net Production (BOEPD)
  - name_id: Produksi Net Working Interest
  - unit: BOEPD · category: OWNERSHIP_ADJUSTED_VOLUME
  - why_it_matters: Gross vs. net (post-JV, post-govt share) production can differ 50%+ — MEDC's Corridor, Rokan farm-in economics require this disaggregation.

**HIGH:**

- `idx:FindingDevelopmentCostUSDBoe` — 3-yr rolling F&D cost; benchmark vs. current oil price defines organic reinvestment IRR.
- `idx:GasHeatingValueBTUscf` — pipeline vs. LNG spec; lean gas vs. rich gas pricing.
- `idx:PSCTerminationYears` — Blok expiry (Rokan 2041, Corridor 2026); reinvestment risk.
- `idx:DomesticLPGSubsidyRecovery` (Pertamina) — subsidized LPG under-recovery balance vs. APBN reimbursement.

## RENEWABLE_ENERGY

**Currently covered:** InstalledCapacityMW, NetGenerationGWh, CapacityFactor, RealizedElectricityTariff, SteamProductionTonnes, ProvenGeothermalReservesMWe.

Missing PPA structure (the entire IPP thesis), RUPTL alignment (PLN's plan is the only demand source), curtailment, and the JOC/JOB structure for geothermal (Pertamina Geothermal, Barito Renewables).

**CRITICAL:**

- `metric_id`: `idx:PPAContractedCapacityMW`
  - name_en: PPA-Contracted Capacity (MW, weighted-avg tenor)
  - name_id: Kapasitas Terkontrak PPA (MW, sisa tenor)
  - unit: MW · category: REVENUE_VISIBILITY
  - why_it_matters: PGEO, BREN essentially trade as bond-like PPA cash-flow vehicles; PPA-covered % of capacity and residual tenor set the equity duration.
  - regulatory_anchor: Perpres 112/2022, Permen ESDM 5/2025 on renewable tariffs.

- `metric_id`: `idx:TariffPPAUSCentsPerKWh`
  - name_en: Weighted PPA Tariff (US¢/kWh)
  - name_id: Tarif PPA Rata-rata Terbobot
  - unit: USD_CENTS_PER_KWH · category: PRICING_POWER
  - why_it_matters: Geothermal at 9-11 US¢, solar at 5-7 US¢, hydro at 6-8 US¢ — mix of legacy high-tariff (Salak, Kamojang) vs. new Perpres 112/2022 lower-tariff projects defines margin.

- `metric_id`: `idx:CurtailmentRatePct`
  - name_en: Curtailment Rate (%)
  - name_id: Rasio Pemadaman Terpaksa (Curtailment)
  - unit: PERCENT · category: OFFTAKE_RISK
  - why_it_matters: PLN grid stability limits new-renewable dispatch (esp. Sulawesi/Sumatra); solar/wind IPPs report curtailment as revenue loss — invisible in nameplate capacity factor.

- `metric_id`: `idx:RUPTLAlignmentPipelineMW`
  - name_en: Project Pipeline within RUPTL (MW)
  - name_id: Pipeline Proyek Selaras RUPTL
  - unit: MW · category: REGULATORY_MOAT
  - why_it_matters: PLN's RUPTL 2025-2034 is the sole demand plan; being outside RUPTL means no PPA. Pipeline-in-RUPTL is a hard moat filter.
  - regulatory_anchor: Kepmen ESDM 188.K/HK.02/MEM.L/2021 RUPTL.

**HIGH:**

- `idx:JOCJOBRevenueShare` — Geothermal JOC (Chevron→Star Energy) revenue share to Pertamina; ownership economics.
- `idx:StreamAvailabilityFactor` (%) — geothermal downtime vs. capacity factor.
- `idx:GreenBondIssuanceIDRbn` — POJK 60/POJK.04/2017 green bond compliance; capex financing cost differential.
- `idx:CarbonCreditRevenueIDRbn` — Perpres 98/2021, IDX Carbon (IDXCarbon) traded volume.

## PETROCHEMICAL

**Currently covered:** NaphthaCrackerUtilization, PolyolefinProductionMT, PolymerNaphthaSpread, AmmoniaProductionMT, UreaProductionMT, PlantTurnaroundEvent.

Missing feedstock flex (naphtha vs. propane vs. ethane arbitrage), integrated margin walk from crude/gas to finished polymer, and downstream mix.

**CRITICAL:**

- `metric_id`: `idx:FeedstockFlexibilityShare`
  - name_en: Alternative Feedstock (Propane/LPG) Share of Cracker Feed (%)
  - name_id: Porsi Feedstock Alternatif (Propana)
  - unit: PERCENT · category: FEEDSTOCK_OPTIMIZATION
  - why_it_matters: TPIA Lotte Chandra cracker's ability to swing LPG at 30%+ vs. pure naphtha captures USD 100-150/t margin during naphtha strength; single-feed peers can't.
  - search_hints: "Propane Feed", "Feedstock Mix", "LPG Cracker", "Naphtha Substitution"

- `metric_id`: `idx:IntegratedPetchemMarginUSDMT`
  - name_en: Integrated Polymer-Naphtha Margin (USD/t)
  - name_id: Margin Terintegrasi Polimer-Naphtha
  - unit: USD_PER_TON · category: PRICING_POWER
  - why_it_matters: HDPE/PP price minus naphtha × yield ratio — captures the value chain squeeze that naphtha-only spread misses.

- `metric_id`: `idx:HighValueProductShare`
  - name_en: High-Value Petrochemical Product Mix (%)
  - name_id: Porsi Produk Nilai Tambah Tinggi
  - unit: PERCENT · category: PRODUCT_MIX
  - why_it_matters: Specialty polymers (film-grade, injection-grade) command USD 200+/t premium over commodity homo-polymer; mix shift is the CAP thesis.

- `metric_id`: `idx:GasFeedstockPriceUSDMMBTU`
  - name_en: Ammonia/Urea Gas Feedstock Cost (USD/MMBtu)
  - name_id: Biaya Gas Bumi Pupuk (USD/MMBtu)
  - unit: USD_PER_MMBTU · category: COST_STRUCTURE
  - why_it_matters: Pupuk Indonesia group (unlisted) and PKT benefit from HGBT US$6.5/MMBtu (Kepmen 91/2023); expiry risk is thesis-critical.
  - regulatory_anchor: Kepmen ESDM 91.K/MG.01/MEM.M/2023.

**HIGH:**

- `idx:AromaticsBTXProductionMT` — Benzene/Toluene/Xylene split (TPIA).
- `idx:PolymerConversionYield` (kg polymer / kg naphtha) — technical efficiency proxy.
- `idx:UnplannedOutageDays` — reliability KPI; each shutdown ≈ USD 5-10mn.
- `idx:BiofertilizerSubsidyRecovery` — for Pupuk KAP.

## PULP_PAPER

**Currently covered:** PulpProductionCapacityMT, PaperPackagingVolumeMT, PulpExportASPUSDMT, WoodFiberSelfSufficiency, PulpCashCostUSDMT.

Missing recycled fiber share (rising ESG-linked), plantation productivity (m³/ha), OKI/PDM new capacity ramp curve, and dissolving pulp mix.

**CRITICAL:**

- `metric_id`: `idx:RecycledFiberSharePct`
  - name_en: Recycled Fiber Content in Paper/Board (%)
  - name_id: Porsi Serat Daur Ulang
  - unit: PERCENT · category: SUSTAINABILITY_MIX
  - why_it_matters: EU EUDR (effective 2026) and buyer ESG mandates increasingly require certified/recycled content; below-threshold mills face export loss.
  - regulatory_anchor: EU Reg. 2023/1115 (EUDR) — applies to exports.

- `metric_id`: `idx:PlantationYieldM3PerHa`
  - name_en: HTI Plantation Yield (m³/ha/year)
  - name_id: Produktivitas HTI (m³/ha/tahun)
  - unit: CUBIC_METERS_PER_HA · category: PLANTATION_PRODUCTIVITY
  - why_it_matters: INKP/TKIM acacia MAI of 25-35 m³/ha vs. peer 15-20 sets the fiber cost floor; declining MAI signals soil/clone issues.

- `metric_id`: `idx:DissolvingPulpProductionMT`
  - name_en: Dissolving Pulp Output (MT)
  - name_id: Produksi Dissolving Pulp (Rayon)
  - unit: TONNES · category: PRODUCT_MIX
  - why_it_matters: Dissolving pulp for viscose/rayon (SRIL demand) trades USD 300-500/t premium to BHKP; new lines (OKI Mill II) shift TKIM's mix.

- `metric_id`: `idx:TissuePackagingShareRevenue`
  - name_en: Tissue & Packaging vs. Commodity Pulp Revenue Mix (%)
  - name_id: Porsi Pendapatan Tissue & Kemasan
  - unit: PERCENT · category: PRODUCT_MIX
  - why_it_matters: Downstream conversion (tissue, corrugated box) captures 2-3× pulp margin — thesis distinction between INKP/TKIM and pure-pulp peers.

**HIGH:**

- `idx:FSCPEFCCertifiedFiberPct` — buyer-mandated in EU/US.
- `idx:MillEnergySelfSufficiency` — black liquor recovery + biomass; drives cost floor.
- `idx:OKIExpansionCapacityMTOnline` — TKIM/APRIL capacity ramp schedule.

## BASIC_MATERIALS

**Currently covered:** (essentially empty — only Revenue, EBITDA).

This is a coverage gap. Basic Materials at IDX includes cement (SMGR, INTP, SMCB), paints (AVIA, TOTO), glass (AMFG), and rayon (SRIL). Each has distinct KPIs.

**CRITICAL (Cement — SMGR/INTP/SMCB):**

- `metric_id`: `idx:CementDomesticSalesVolumeMT`
  - name_en: Domestic Cement Sales Volume (MT)
  - name_id: Volume Penjualan Semen Domestik
  - unit: TONNES · category: OPERATIONAL

- `metric_id`: `idx:CementCapacityUtilizationPct`
  - name_en: Cement Grinding Capacity Utilization (%)
  - name_id: Utilisasi Kapasitas Semen
  - unit: PERCENT · category: CAPACITY_UTILIZATION
  - why_it_matters: Indonesian cement industry has run at ~55-65% utilization (structural oversupply); every point of utilization gain lifts pricing power. ASI (Asosiasi Semen Indonesia) publishes national numbers.

- `metric_id`: `idx:BulkVsBagMix`
  - name_en: Bulk vs. Bag Cement Mix (%)
  - name_id: Komposisi Semen Curah vs. Kantong
  - unit: PERCENT · category: PRODUCT_MIX
  - why_it_matters: Bulk (infra/RMC) is lower-price, higher-volume, project-linked; bag (retail) has stickier pricing. Mix reveals infra vs. property demand.

- `metric_id`: `idx:ClinkerCementRatio`
  - name_en: Clinker-to-Cement Ratio (%)
  - name_id: Rasio Klinker terhadap Semen
  - unit: PERCENT · category: COST_STRUCTURE
  - why_it_matters: Blended cements (PCC, PPC, slag) use less clinker → lower coal & CO2 per ton; SNI 8363-2017 permits blended formulations. Ratio decline = margin & ESG.

- `metric_id`: `idx:AlternativeFuelRateCement` (%)
  - RDF/biomass co-processing; carbon cost hedge.

**Paints (AVIA/TOTO):**

- `metric_id`: `idx:DistributionReachDealers`
  - Number of active dealer touchpoints — moat proxy vs. e-commerce entrants.

- `metric_id`: `idx:PremiumMassMarketMixPaints`
  - Decorative premium share vs. mass; drives blended GPM.

## TELCO

**Currently covered:** DataTrafficPetabytes, BlendedARPU, MobileSubscribers.

Missing: fixed broadband (IndiHome, MyRepublic, MNC Play), enterprise/wholesale mix, tower/fiber divestments income, 5G capex intensity, and subscriber quality (SIM consolidation).

**CRITICAL:**

- `metric_id`: `idx:FixedBroadbandSubscribers`
  - name_en: Fixed Broadband Subscribers (mn)
  - name_id: Pelanggan Fixed Broadband
  - unit: SUBSCRIBERS_MILLION · category: OPERATIONAL
  - why_it_matters: IndiHome (~10mn), FMC convergence is TLKM/EXCL entire strategy post-2023 merger; mobile-only view misses this leg entirely.

- `metric_id`: `idx:FBBAverageRevenuePerUser`
  - name_en: Fixed Broadband ARPU (IDR '000/month)
  - name_id: ARPU Fixed Broadband
  - unit: IDR_THOUSAND · category: PRICING_POWER
  - why_it_matters: IndiHome ARPU ~IDR 275k vs. mobile ARPU ~IDR 45k; growth in FBB base is IRR-defining given fiber capex.

- `metric_id`: `idx:CapexIntensityPct`
  - name_en: Capex/Revenue (%)
  - name_id: Intensitas Belanja Modal
  - unit: PERCENT · category: CAPITAL_ALLOCATION
  - why_it_matters: 5G build + fiber = telco capex intensity 25-30%; falling capex intensity is the FCF thesis for TLKM & post-merger XL-Smartfren.

- `metric_id`: `idx:EnterpriseB2BRevenueShare`
  - name_en: Enterprise/B2B Revenue Share (%)
  - name_id: Porsi Pendapatan Enterprise
  - unit: PERCENT · category: REVENUE_MIX
  - why_it_matters: TelkomSat, TelkomSigma, cloud/data-center revenue diversifies away from consumer mobile — commands higher multiples.

- `metric_id`: `idx:DataMonetizationYieldPerGB`
  - name_en: Data Yield (IDR/GB)
  - name_id: Yield Data per GB
  - unit: IDR_PER_GB · category: PRICING_POWER
  - why_it_matters: Traffic doubles annually while ARPU is flat = yield/GB compressing 30-40% p.a.; inflection point is thesis-critical.

**HIGH:**

- `idx:PostpaidSubShare` — quality-of-subscriber; churn 1/5th of prepaid.
- `idx:SIMConsolidationCumulativeMn` — post-2023 real-name registration (Kepmen Kominfo) shed ghost SIMs; the reset base is what to model from.
- `idx:MobileSubsSpectrumMHz` — spectrum efficiency (subs per MHz) after 5G auction.
- `idx:TowerFiberDivestmentGainIDRbn` — one-off but recurring theme (Mitratel spin, XL-Protelindo).
- `idx:MobileBTSSitesTotal` — coverage moat proxy.

## TOWER

**Currently covered:** TowerCount, TenancyRatio.

Massively under-specified given how large TOWR/TBIG/MTEL are. Missing colo count, fiberization, lock-in tenure, MLA-linked escalators.

**CRITICAL:**

- `metric_id`: `idx:ColocationCountTotal`
  - name_en: Total Tenancies (Colo Contracts)
  - name_id: Jumlah Kolokasi/Tenancy
  - unit: TENANCIES · category: OPERATIONAL
  - why_it_matters: Tenancies grow faster than towers (colo-led growth); the absolute tenancy count is what MSA revenue tracks against, not raw tower count.

- `metric_id`: `idx:WeightedAvgContractTenureYears`
  - name_en: Weighted-Avg Remaining MSA Tenure (Years)
  - name_id: Sisa Rata-rata Tenor MSA
  - unit: YEARS · category: REVENUE_VISIBILITY
  - why_it_matters: MTEL/TOWR trade at 10-14× EV/EBITDA precisely because ~10-yr locked MSAs = bond-like cash flow; a shortening tenure is the first warning sign.

- `metric_id`: `idx:FiberOpticKmDeployed`
  - name_en: Fiber Optic Route km Deployed
  - name_id: Panjang Kabel Serat Optik Terpasang
  - unit: KILOMETERS · category: NON_TOWER_INFRASTRUCTURE
  - why_it_matters: Tower → TowerCo → InfraCo pivot; TOWR/MTEL fiber build (~180k km) supports FTTH & wholesale — future growth beyond tenancy.

- `metric_id`: `idx:CPICMEEscalatorRate`
  - name_en: MSA Escalator Rate (%, formula-linked)
  - name_id: Formula Eskalasi Sewa MSA
  - unit: PERCENT · category: PRICING_POWER
  - why_it_matters: 3-5% CPI-linked annual step-up in MSA is the built-in organic growth engine; renegotiation risk on renewal is thesis-critical.

**HIGH:**

- `idx:BuildToSuitPipelineNet` — new-tower demand from telco 5G rollout; leading indicator of tenancy adds.
- `idx:B2BMicrocellPoleCount` — small-cell/pole for urban 5G densification.
- `idx:DataCenterPowerCapacityMW` — TBIG/EDGE DC expansion (adjacency).
- `idx:CustomerConcentrationTop3Pct` — Telkomsel/XL/IOH ≈ 90% revenue; monitoring merger effects.

## AUTOMOTIVE

**Currently covered:** CarWholesaleUnits, CarRetailUnits, MotorcycleUnitSales, MarketShareGaikindo, ExportVolumeUnits, EVModelMixShare, ComponentContentPerVehicle.

Missing: LCGC/segment mix, financing penetration (ACC, TAF, FIF), Astra group JV pass-through, parts/aftermarket, insurance.

**CRITICAL:**

- `metric_id`: `idx:LCGCVolumeShare`
  - name_en: LCGC Volume Share of Wholesales (%)
  - name_id: Porsi LCGC dari Wholesales
  - unit: PERCENT · category: PRODUCT_MIX
  - why_it_matters: LCGC (PP 41/2013) has ~10% price advantage but ~40% lower unit profit — mix shift toward LCGC (Agya, Ayla, Sigra) reveals downtrading and squeezes ASII margin.
  - regulatory_anchor: PP 41/2013, PMK 33/2017 LCGC luxury tax exemption.

- `metric_id`: `idx:AutoFinancingPenetrationPct`
  - name_en: Financing Penetration (% of Retail Sales)
  - name_id: Penetrasi Pembiayaan (% dari Penjualan Ritel)
  - unit: PERCENT · category: SALES_CHANNEL
  - why_it_matters: ACC + TAF finance ~70-80% of Astra's 4W sales; interest-rate cycle × penetration = credit-driven sales elasticity.

- `metric_id`: `idx:AftersalesRevenueShare`
  - name_en: Aftersales & Parts Revenue Share (%)
  - name_id: Porsi Pendapatan Purna Jual
  - unit: PERCENT · category: REVENUE_MIX
  - why_it_matters: Aftersales carries 3-4× margin of new-car sales; parked-fleet driven, not cyclical — the Astra moat vs. import-only distributors.

- `metric_id`: `idx:JVConsolidationEquityMethodShareIDRbn`
  - name_en: Equity-Method JV Income Contribution (IDR bn)
  - name_id: Kontribusi Laba JV (Metode Ekuitas)
  - unit: IDR_BILLION · category: GROUP_STRUCTURE
  - why_it_matters: ~50% of ASII's auto income is TAM/AHM JV pass-through via equity method; not consolidated revenue-line.

**HIGH:**

- `idx:EVBEVVolumeUnits` — pure BEV vs. HEV vs. PHEV.
- `idx:EVIncentiveSubsidyIDRbn` — PP 74/2021 & Perpres 55/2019; DP subsidy IDR 7mn/unit for select BEV.
- `idx:ExportShareOfProduction` — Toyota Innova, Fortuner, DFSK exports; TKDN & ASEAN-linked.
- `idx:TKDNPctPerModel` — PermenPerin 27/2020 requires >40% domestic content for tax incentives.
- `idx:Motor2WShareByCC` — 110cc (matic) vs. 150cc+ (sport); H2 skew.

## CONSUMER_STAPLES

**Currently covered:** BrandedFoodVolumeMT, VolumePriceMixDecomp, InventoryDays.

Sparse. Missing channel mix (MT vs. GT vs. e-commerce), A&P intensity, category share (Nielsen), excise dynamics for tobacco (GGRM/HMSP).

**CRITICAL:**

- `metric_id`: `idx:ModernTradeChannelShare`
  - name_en: Modern Trade / GT / OT / E-commerce Channel Mix (%)
  - name_id: Komposisi Kanal Distribusi (MT/GT/OT/E-com)
  - unit: PERCENT · category: DISTRIBUTION
  - why_it_matters: ICBP/MYOR/UNVR — MT growth 8-12% vs. GT flat; e-commerce >5% is a new pricing dynamic (price transparency). Channel shift explains gross margin drift.

- `metric_id`: `idx:AdvertisingPromotionRatioAnP`
  - name_en: A&P Spend to Revenue (%)
  - name_id: Rasio Beban Iklan & Promosi
  - unit: PERCENT · category: MARKETING_INVESTMENT
  - why_it_matters: A&P step-up defends volume in inflationary passes; step-down flags share loss. UNVR's declining A&P vs. rising ICBP is thesis-relevant.

- `metric_id`: `idx:NielsenCategoryMarketShare`
  - name_en: Nielsen Category Market Share (%)
  - name_id: Pangsa Pasar Kategori Nielsen
  - unit: PERCENT · category: COMPETITIVE_POSITION
  - why_it_matters: Category-level share (not company-level) is the pricing-power proxy; Indomie share ~70% is why ICBP has pricing autonomy.

- `metric_id`: `idx:CigaretteExciseRatePerStick` (SKM/SKT tier)
  - name_en: Effective Cigarette Excise Rate (IDR/stick)
  - name_id: Tarif Cukai Efektif per Batang
  - unit: IDR_PER_STICK · category: REGULATORY_COST
  - why_it_matters: PMK 143/2023 raised SKM tier I ~10%; excise share of retail price ~63% → pricing pass-through elasticity defines GGRM/HMSP volume-price trade-off.
  - regulatory_anchor: PMK 143/PMK.010/2023 tobacco excise tariff.

- `metric_id`: `idx:DownTradingSKMToSKTShare`
  - name_en: Down-Trading SKM (machine) → SKT (hand-rolled) Volume Share
  - name_id: Downtrading SKM ke SKT
  - unit: PERCENT · category: CONSUMER_BEHAVIOR
  - why_it_matters: Excise gap between SKM tier I and SKT (~40%) drives consumer downtrading in weak macro; SKT resurgence signals affordability stress.

**HIGH:**

- `idx:PalmOilInputHedgePct` — RBD/olein cost hedged for ICBP noodles/margarine.
- `idx:DistributorInventoryDaysDownstream` — reveals trade-loading vs. sell-through health.
- `idx:NewProductLaunchRevenueContribution` — innovation velocity.
- `idx:ExportRevenueShare` — MYOR (>40%), ICBP subsidiaries.

## POULTRY

**Currently covered:** FeedMillSalesVolumeMT, DayOldChickVolume, DOCFarmgatePrice, LiveBirdPriceIDR, RawMaterialExposureSoyCorn.

Missing spread economics (DOC vs. broiler), farm-gate margin, feed-conversion economics, integrated vs. commercial mix.

**CRITICAL:**

- `metric_id`: `idx:DOCLBSpreadIDRPerKg`
  - name_en: DOC-to-Live-Bird Spread (IDR/kg)
  - name_id: Selisih Harga DOC-Broiler
  - unit: IDR_PER_KG · category: UNIT_ECONOMICS
  - why_it_matters: Spread between DOC farmgate (~IDR 6,000/chick) and broiler LB (~IDR 20,000/kg × 1.8kg mature weight) is the plasma/farmer margin — collapse triggers government cull orders (Kepmen Pertanian 32/2017 supply management).

- `metric_id`: `idx:FeedCostPerKgLiveweight`
  - name_en: Feed Cost per kg Liveweight (IDR/kg)
  - name_id: Biaya Pakan per kg Bobot Hidup
  - unit: IDR_PER_KG · category: UNIT_ECONOMICS
  - why_it_matters: Feed = 65-70% of production cost; FCR × feed price = the entire poultry P&L. CPIN, JPFA & MAIN converge to industry unit-cost benchmark.

- `metric_id`: `idx:FeedConversionRatioFCR`
  - name_en: Feed Conversion Ratio (FCR)
  - name_id: Rasio Konversi Pakan (FCR)
  - unit: RATIO · category: PROCESS_EFFICIENCY
  - why_it_matters: Best-in-class integrator FCR ~1.55 vs. commercial farmer ~1.75 — the integration moat that separates CPIN/JPFA from open-market farmers.

- `metric_id`: `idx:ProcessedFoodShareRevenue`
  - name_en: Processed Food (Nugget/Sausage) Revenue Share (%)
  - name_id: Porsi Pendapatan Makanan Olahan
  - unit: PERCENT · category: PRODUCT_MIX
  - why_it_matters: CPIN Fiesta, JPFA So Good — processed carries 2-3× broiler margin and smooths cyclicality.

**HIGH:**

- `idx:GrandparentStockGPImports` — capacity of GP imports = supply pipeline 18M ahead.
- `idx:CornDomesticSourcingShare` — Bulog imports subject to Kementan quota.
- `idx:CulledParentStockThousands` — Kementan supply-mgmt cull orders (2022-2024).

## RETAIL

**Currently covered:** SameStoreSalesGrowth, TotalStoreCount, NetNewStoreOpenings, SalesPerSquareMeter, PrivateLabelShare, AverageTicketSize, InventoryDays.

Reasonably strong. Missing SSSG decomposition (traffic vs. ticket), digital sales, category mix.

**CRITICAL:**

- `metric_id`: `idx:SSSGTrafficVsTicketDecomp`
  - name_en: SSSG Decomposition — Traffic vs. Ticket (%)
  - name_id: Dekomposisi SSSG (Traffic vs. Ticket)
  - unit: PERCENT · category: SALES_QUALITY
  - why_it_matters: SSSG +5% via traffic +3%/ticket +2% (healthy) vs. traffic -2%/ticket +7% (price-led, unsustainable) — Ramayana vs. Matahari divergence.

- `metric_id`: `idx:DigitalOmnichannelSalesShare`
  - name_en: Digital/Omnichannel Sales Share (%)
  - name_id: Porsi Penjualan Digital/Omnichannel
  - unit: PERCENT · category: CHANNEL_MIX
  - why_it_matters: MAPI (~15%), Erafone/MAPB (~20%) — digital share = e-commerce marketplace resilience without cannibalizing store base.

- `metric_id`: `idx:BasketSizeItemsPerTransaction`
  - name_en: Basket Size (Items per Transaction)
  - name_id: Ukuran Keranjang (Item per Transaksi)
  - unit: ITEMS · category: SHOPPER_BEHAVIOR
  - why_it_matters: Together with ticket-size, isolates trading-up vs. trading-down beyond raw revenue movement.

- `metric_id`: `idx:StoreClosureRateNegNSO`
  - name_en: Store Closures / Portfolio Rationalization (Units)
  - name_id: Penutupan Gerai
  - unit: STORES · category: PORTFOLIO_ACTION
  - why_it_matters: Net-new-store hides gross closures; MAP closed 50+ Sogo/Sports Warehouse doors 2022-24 — health signal.

**HIGH:**

- `idx:LoyaltyProgramMembers` — active member base; frequency & wallet share.
- `idx:CashierlessCheckoutShare` — Alfamart digital checkout penetration.
- `idx:GrossMerchandiseValueDigital` — for hybrid retailers (Blibli/MAP JVs).

## PHARMACEUTICAL

**Currently covered:** EthicalRevenueShare, OTCRevenueShare, APIImportExposure, TollManufacturingVolume, BPJSCatalogRevenueShare.

Good foundation. Missing BPJS reimbursement lag, R&D pipeline, local API substitution (Kemenkes Permenkes 17/2017 target 50% API domestic by 2030), export share.

**CRITICAL:**

- `metric_id`: `idx:BPJSReceivableDaysOutstanding`
  - name_en: BPJS Receivables Days Outstanding
  - name_id: Hari Piutang BPJS
  - unit: DAYS · category: WORKING_CAPITAL
  - why_it_matters: BPJS delays (60-120 days) tie working capital and drive interest cost; INAF/PEHA/KAEF critical.

- `metric_id`: `idx:ActiveIngredientLocalContentPct`
  - name_en: API (Bahan Baku Obat) Local Content (%)
  - name_id: Porsi Bahan Baku Obat Domestik
  - unit: PERCENT · category: SUPPLY_CHAIN_LOCALIZATION
  - why_it_matters: Permenkes 17/2017 targets 50% domestic API by 2030; INAF/Kimia Farma API JVs are strategic — imports vulnerable to rupiah + China supply.
  - regulatory_anchor: Permenkes 17/2017; Kepmenkes HK.01.07/MENKES/1027/2023 API roadmap.

- `metric_id`: `idx:EKatalogTenderWinRatePct`
  - name_en: E-Katalog (LKPP) Tender Win Rate (%)
  - name_id: Tingkat Kemenangan Tender E-Katalog
  - unit: PERCENT · category: GOVERNMENT_CHANNEL

- `metric_id`: `idx:RNDPipelineNewMoleculesCount`
  - name_en: R&D Pipeline (# molecules/formulations in phase)
  - name_id: Pipeline R&D (Jumlah Molekul dalam Uji)
  - unit: COUNT · category: INNOVATION
  - why_it_matters: KLBF pipeline diversifies away from mature Extra Joss/Promag; single-drug reliance = patent cliff.

- `metric_id`: `idx:GenericBrandedShareEthical`
  - name_en: Generic vs. Branded-Generic Share in Ethical
  - name_id: Porsi Generik vs. Branded pada Ethical
  - unit: PERCENT · category: PRODUCT_MIX
  - why_it_matters: BPJS Formularium Nasional (FORNAS) favors unbranded generics at low margin; branded-generic share = pricing power residual.

**HIGH:**

- `idx:ExportRevenueSharePharma` — SIDO (~15%), KLBF ASEAN.
- `idx:MilkNutritionSegmentRevenue` — SIDO (Kuku Bima susu), KLBF Prenagen — non-cyclical adjacency.

## HOSPITAL

**Currently covered:** OperationalBedsCount, BedOccupancyRate, AverageLengthOfStay, InpatientAdmissions, OutpatientVisits, ARPOB, BPJSRevenueShare.

Good clinical KPIs. Missing accreditation, doctor productivity, EMR maturity, greenfield ramp curve.

**CRITICAL:**

- `metric_id`: `idx:JCIAccreditationShare`
  - name_en: JCI-Accredited Hospitals (Count / % of network)
  - name_id: Rumah Sakit Terakreditasi JCI
  - unit: COUNT_OR_PERCENT · category: QUALITY_MOAT
  - why_it_matters: JCI accreditation is medical-tourism gate & premium-payor moat (MIKA Pondok Indah, Siloam MRCCC); Kemenkes KARS Paripurna is domestic equivalent.

- `metric_id`: `idx:CashOutOfPocketRevenueShare`
  - name_en: Cash/OOP Revenue Share (% ex-BPJS ex-insurance)
  - name_id: Porsi Pendapatan Cash/Tunai (Non-BPJS/Asuransi)
  - unit: PERCENT · category: PAYER_MIX
  - why_it_matters: OOP has 3× BPJS EBITDA margin; cash share differentiates MIKA (~40% cash) from Siloam (~25%) — thesis-critical for pricing power.

- `metric_id`: `idx:DoctorProductivityRevenuePerDoctor`
  - name_en: Revenue per Active Doctor (IDR mn)
  - name_id: Pendapatan per Dokter Aktif
  - unit: IDR_MILLION · category: HUMAN_CAPITAL_EFFICIENCY
  - why_it_matters: Specialist availability is Indonesia's binding hospital constraint (~1 specialist per 12k pop, WHO min 1:5k); productivity gap explains occupancy plateau.

- `metric_id`: `idx:MatureHospitalContributionEBITDA`
  - name_en: Mature Hospital (>5-yr) EBITDA Contribution (%)
  - name_id: Kontribusi EBITDA RS Mature (>5 tahun)
  - unit: PERCENT · category: PORTFOLIO_MATURITY
  - why_it_matters: Greenfield RS take 4-6 years to breakeven; separating mature vs. ramp exposes the true earnings power of expansion-heavy names (Siloam).

- `metric_id`: `idx:ComplexCasemixIndex`
  - name_en: Casemix Complexity Index (INA-CBG severity level II/III share)
  - name_id: Indeks Kompleksitas Kasus (INA-CBG)
  - unit: PERCENT · category: SERVICE_MIX
  - why_it_matters: BPJS reimburses via INA-CBG; complex-case share drives BPJS ARPOB × margin equation.
  - regulatory_anchor: Permenkes 3/2023 INA-CBG tariff.

**HIGH:**

- `idx:EMRDigitalMaturityLevel` — Kemenkes SATUSEHAT integration (Permenkes 24/2022 digital roadmap).
- `idx:MedicalEquipmentImportContentPct` — TKDN alat kesehatan (PermenPerin 31/2022).
- `idx:CorporatePayerAccountsCount` — corporate insurance contracts = predictable volume.

## CPO

**Currently covered:** MaturePlantedArea, FfbProduction, CPOProductionVolume, PalmKernelProduction, OilExtractionRate, CPOAveragePriceASP, CPOCashCostPerKg.

Strong operational coverage. Missing: DMO/DPO impact, biodiesel offtake, PSR replanting compliance, EUDR certification, downstream refining margin.

**CRITICAL:**

- `metric_id`: `idx:DMOComplianceVolumeMT`
  - name_en: DMO/DPO Compliance Volume (MT) & Price Discount
  - name_id: Pemenuhan DMO/DPO (Volume & Diskon Harga)
  - unit: TONNES · category: REGULATORY_COST
  - why_it_matters: Permendag 26/2023 & subsequent revisions require DMO for export permission; the discount (typically 15-25% below CPO Rotterdam) × DMO tonnage is a real margin haircut.
  - regulatory_anchor: Permendag 26/2023, Kepmendag 100/2023 export levy & DMO.

- `metric_id`: `idx:BiodieselOfftakeShare`
  - name_en: Biodiesel (B35/B40) Offtake Share of CPO Sales (%)
  - name_id: Porsi Penjualan CPO untuk Biodiesel
  - unit: PERCENT · category: OFFTAKE_MIX
  - why_it_matters: B35 (mandatory Feb 2023) → B40 (2025) roadmap absorbs ~13mn MT domestic CPO; BPDPKS-guaranteed pricing = risk-adjusted revenue floor.
  - regulatory_anchor: Kepmen ESDM 45.K/2023 B35, Permen ESDM 41/2023 biofuel roadmap.

- `metric_id`: `idx:PSRReplantingComplianceHa`
  - name_en: PSR (Peremajaan Sawit Rakyat) & Own-Estate Replanting (Hectares)
  - name_id: Replanting PSR & Kebun Inti
  - unit: HECTARES · category: LONG_TERM_YIELD
  - why_it_matters: Aging plantations >25yr (~30% of national area) crash FFB yields; replanting compliance = 4-yr forward FFB output. BPDPKS subsidy IDR 60mn/ha for smallholder PSR.
  - regulatory_anchor: Permentan 3/2022 PSR.

- `metric_id`: `idx:EUDRCertifiedAreaShare`
  - name_en: EUDR-Compliant Certified Estate Area (%)
  - name_id: Porsi Kebun Bersertifikasi EUDR
  - unit: PERCENT · category: EXPORT_ACCESS
  - why_it_matters: EU EUDR (effective Dec 2025) requires deforestation-free chain-of-custody; non-compliant volume redirected to lower-price India/China at 5-8% discount.
  - regulatory_anchor: EU Regulation 2023/1115 (EUDR); PP 44/2020 ISPO.

- `metric_id`: `idx:DownstreamRefiningMarginUSDMT`
  - name_en: Downstream Refining Margin (RBD/Olein − CPO, USD/MT)
  - name_id: Margin Refinasi (Olein/RBD − CPO)
  - unit: USD_PER_TON · category: INTEGRATION_MARGIN
  - why_it_matters: Wilmar/Musim Mas integrated vs. AALI/LSIP upstream-only; downstream captures USD 30-80/MT which upstream ASP misses.

**HIGH:**

- `idx:ExportLevyUSDPerMT` — Permenkeu-set levy (BPDPKS); progressive scale by CPO price.
- `idx:OldPalmAreaShare` — estate >25yr; yield-decline pipeline.
- `idx:ISPO_RSPOCoveragePct` — sustainability certification for buyer access.
- `idx:SmallholderPlasmaFFBShare` — plasma inti-plasma structure vs. own-estate FFB.
- `idx:PKOtoCPORevenueMix` — palm kernel oil (specialty, oleochem) higher margin.

## PROPERTY

**Currently covered:** MarketingSalesPresales, TotalLandbankHectares, RecurringIncomeShare, MallOccupancyRate, UnrecognizedRevenueBacklog.

Good. Missing: secondary-market pricing, KPR/FLPP exposure, product mix (landed vs. high-rise), take-up rate, JO/JV recognized profits.

**CRITICAL:**

- `metric_id`: `idx:LandedVsHighRiseMixMarketingSales`
  - name_en: Landed vs. High-Rise Marketing Sales Mix (%)
  - name_id: Komposisi Marketing Sales (Landed vs. High-Rise)
  - unit: PERCENT · category: PRODUCT_MIX
  - why_it_matters: Landed carries higher GPM (~55%) vs. apartment (~35%); post-2020 apartment glut → landed pivot at CTRA/SMRA drives margin expansion.

- `metric_id`: `idx:KPRFLPPSubsidizedSalesShare`
  - name_en: KPR FLPP / Subsidized Mortgage Sales Share (%)
  - name_id: Porsi Penjualan KPR FLPP/Subsidi
  - unit: PERCENT · category: POLICY_LINKED_DEMAND
  - why_it_matters: PUPR FLPP quota (Kepmen PUPR 995/2021) is countercyclical; BSDE/BBTN/PWON secondary developers highly exposed. Also PPN DTP (VAT-borne-by-govt) programs 2024-25.
  - regulatory_anchor: PMK 61/2024 PPN DTP properti, KepmenPUPR 995/KPTS/M/2021 FLPP.

- `metric_id`: `idx:TakeUpRateNewLaunchPct`
  - name_en: New Launch Take-Up Rate (% units sold within 90 days)
  - name_id: Take-Up Rate Peluncuran Baru
  - unit: PERCENT · category: DEMAND_STRENGTH
  - why_it_matters: 60%+ within launch weekend = strong (CTRA Vanya, SMRA Bandung); sub-30% = pricing miscalibration. Leading indicator of gross margin.

- `metric_id`: `idx:LandbankNBVPerSqm`
  - name_en: Landbank Carrying Value per sqm (IDR '000)
  - name_id: Nilai Tercatat Landbank per m²
  - unit: IDR_THOUSAND_PER_SQM · category: HIDDEN_ASSET
  - why_it_matters: Historical-cost landbank (esp. BSDE/SMRA acquired 20+ years ago) is materially below market — RNAV vs. book gap is the property thesis.

- `metric_id`: `idx:RecurringIncomeYieldOnCost`
  - name_en: Recurring Assets (Mall/Office) Yield on Cost (%)
  - name_id: Yield on Cost Aset Recurring
  - unit: PERCENT · category: INVESTMENT_RETURN
  - why_it_matters: PWON's Kota Kasablanka 12%+ yield-on-cost vs. new mall 8% — determines whether recurring pivot creates value or just switches income mix.

**HIGH:**

- `idx:SecondaryMarketPricePremiumPct` — Rumah123/OLX secondary vs. primary; healthy market =primary at slight premium.
- `idx:JOJVEquityIncomeIDRbn` — SMRA/DILD JO with Mitsubishi/Hankyu etc.
- `idx:AverageInventoryUnitsFinished` — completed but unsold; margin call risk.
- `idx:LandBankExhaustionYears` — landbank ÷ current marketing sales pace.

## CONTRACTOR

**Currently covered:** NewContractWins, OrderBookBacklog, BurnRateConversion, GovernmentProjectMix, ReceivablesDaysContractor, KSOJointOperationCF.

Good. Missing: gross vs. net order book, penalties/LDs, turnkey vs. cost-plus, cost overruns on IKN/toll projects.

**CRITICAL:**

- `metric_id`: `idx:NetOrderBookExKSOandRoyalty`
  - name_en: Net Order Book (Excluding KSO & Royalty-based) IDR bn
  - name_id: Order Book Bersih (Ex-KSO)
  - unit: IDR_BILLION · category: BACKLOG_QUALITY
  - why_it_matters: Gross order book inflates because KSO partner share isn't stripped; PTPP, WSKT, ADHI net order book can be 60-70% of gross — real revenue conversion basis.

- `metric_id`: `idx:LiquidatedDamagesPenaltiesIDRbn`
  - name_en: Liquidated Damages / Penalties (IDR bn, cumulative)
  - name_id: Denda Keterlambatan Proyek
  - unit: IDR_BILLION · category: EXECUTION_RISK
  - why_it_matters: WSKT/WIKA toll & LRT overruns triggered material LDs (>IDR 100bn on single projects); disclosed sparingly, so leakage in note X of financials.

- `metric_id`: `idx:TurnkeyContractShare`
  - name_en: Turnkey / EPC-Financed Contract Share (%)
  - name_id: Porsi Kontrak Turnkey
  - unit: PERCENT · category: CONTRACT_STRUCTURE
  - why_it_matters: Turnkey (payment on completion) balloons receivables & working capital; the Waskita crisis was a turnkey exposure story.

- `metric_id`: `idx:IKNProjectBacklogIDRbn`
  - name_en: IKN (New Capital) Project Backlog (IDR bn)
  - name_id: Order Book Proyek IKN
  - unit: IDR_BILLION · category: STRATEGIC_PROJECT
  - why_it_matters: IKN (UU 3/2022) is a >IDR 500tn multi-year program; SOE-contractor allocation is a policy-linked earnings driver.
  - regulatory_anchor: UU 3/2022 IKN, Perpres 63/2022.

**HIGH:**

- `idx:AdvancePaymentReceivedPct` — DP received on new contract; working-capital signal.
- `idx:BUMNProjectBacklogVsSwasta` — SOE-sponsor vs. private (rev quality differs).
- `idx:TollRoadDivestmentGainsIDRbn` — WIKA, WSKT toll-asset recycling into INA.

## TOLL_ROAD

**Currently covered:** AverageDailyTraffic, TollTariffAdjustment, OperationalTollLengthKm, ConcessionRemainingYears.

Adequate. Missing: elasticity, average trip length, vehicle-class mix (weight-based pricing), maintenance capex intensity.

**CRITICAL:**

- `metric_id`: `idx:AverageTripLengthKm`
  - name_en: Average Trip Length per Vehicle (km)
  - name_id: Rata-rata Jarak Tempuh per Kendaraan
  - unit: KILOMETERS · category: REVENUE_QUALITY
  - why_it_matters: Traffic × trip length = "vehicle-km" — the actual revenue-driving variable, insensitive to gate-count changes. JSMR TransJava vs. Jabodetabek intracity differ 5-10× on this.

- `metric_id`: `idx:VehicleClassMixGolIIIVIntensity`
  - name_en: Golongan II-V (Heavy Vehicle) Traffic Share (%)
  - name_id: Porsi Kendaraan Gol II-V (Truk/Bus)
  - unit: PERCENT · category: PRICING_MIX
  - why_it_matters: Gol II charges ~1.5×, Gol V ~3× Gol I tariff (Permen PU 16/2014); freight-heavy corridors (Trans Sumatera) monetize much higher per ADT.
  - regulatory_anchor: PermenPUPR 16/PRT/M/2014 vehicle classification.

- `metric_id`: `idx:TariffElasticityAdjustmentYoY`
  - name_en: Traffic Response to Tariff Adjustment (% traffic change post-adjustment)
  - name_id: Elastisitas Traffic terhadap Tarif
  - unit: PERCENT · category: PRICING_POWER
  - why_it_matters: 2-year tariff hike (PP 15/2005) typically induces -1 to -3% short-term traffic; elasticity above -5% signals affordability stress.

- `metric_id`: `idx:MaintenanceCapexOfRevenue`
  - name_en: Maintenance Capex / Revenue (%)
  - name_id: Capex Pemeliharaan (% Pendapatan)
  - unit: PERCENT · category: CAPITAL_INTENSITY
  - why_it_matters: BUJT concessionaires must maintain SPM (Standar Pelayanan Minimum, Permen PU 16/2014); underspend = penalty; overspend = FCF drag.

**HIGH:**

- `idx:AssetRecycledDivestedIDRbn` — JSMR to INA/foreign; capital recycling signal.
- `idx:MLFFElectronicTollShare` — MLFF (Multi-Lane Free Flow) implementation timing; reduces staff cost.
- `idx:CorridorProfitabilityRevenuePerKm` — per-corridor P&L; loss-making toll drags total.

## PORT

**Currently covered:** ContainerThroughputTEUs, CBUCarTerminalVolume, StevedoringRevenuePerTEU, ConcessionRemainingYears.

Missing: berth productivity, dwell time, transshipment share, hinterland connectivity.

**CRITICAL:**

- `metric_id`: `idx:BerthProductivityBoxesPerHour`
  - name_en: Berth Productivity (Box Moves per Ship Hour, BMH)
  - name_id: Produktivitas Dermaga (BMH)
  - unit: BOXES_PER_HOUR · category: OPERATIONAL_EFFICIENCY
  - why_it_matters: JICT/NPCT1 ~30 BMH vs. Singapore PSA ~40+; determines liner willingness to call Tanjung Priok as regional hub vs. transship via Singapore/PTP.

- `metric_id`: `idx:AverageContainerDwellTimeDays`
  - name_en: Average Container Dwell Time (Days)
  - name_id: Rata-rata Dwelling Time Kontainer
  - unit: DAYS · category: OPERATIONAL_EFFICIENCY
  - why_it_matters: Kemenko target <3 days; longer dwell = capacity waste + gov't performance metric. Kemenhub PM 20/2021 SPM Kepelabuhanan sets standard.
  - regulatory_anchor: PermenHub PM 20/2021 SPM Pelabuhan.

- `metric_id`: `idx:TransshipmentVolumeShare`
  - name_en: Transshipment Volume Share (%)
  - name_id: Porsi Volume Transshipment
  - unit: PERCENT · category: HUB_STATUS
  - why_it_matters: Kuala Tanjung (Pelindo) transshipment thesis vs. mostly gateway Tanjung Priok; transshipment yields higher stevedoring revenue.

- `metric_id`: `idx:HinterlandTruckIntermodalShare`
  - name_en: Rail/Barge Hinterland Modal Share (%)
  - name_id: Porsi Distribusi Hinterland Rail/Tongkang
  - unit: PERCENT · category: LOGISTICS_INTEGRATION
  - why_it_matters: Kereta Api Logistik + Cikarang Dry Port integration reduces Priok congestion; hinterland modal share above 15% is competitive moat.

**HIGH:**

- `idx:PilotageTowageRevenueIDRbn` — captive marine services (cross-subsidy).
- `idx:CraneQuayCountUnits` — capacity proxy (QC × BMH × utilization).
- `idx:PelindoPostMergerSubsidiarySynergy` — post-2021 PelindoI-IV merger cost synergies.

## SHIPPING

**Currently covered:** FleetCount, TotalDWT, CharterRate, BunkerFuelCost, VesselUtilization.

Missing: cabotage compliance, chartered-in vs. owned, contract-of-affreightment vs. spot, bunker hedging.

**CRITICAL:**

- `metric_id`: `idx:CoASpotRevenueMix`
  - name_en: Contract-of-Affreightment (CoA) vs. Spot Revenue Mix (%)
  - name_id: Komposisi Pendapatan CoA vs. Spot
  - unit: PERCENT · category: REVENUE_VISIBILITY
  - why_it_matters: TMAS, HITS 60-70% CoA locks in floor rates; spot exposure captures BDI upside/downside. Explains earnings volatility divergence.

- `metric_id`: `idx:CharteredInVsOwnedFleetPct`
  - name_en: Chartered-In Fleet Share (%)
  - name_id: Porsi Kapal Chartered-In
  - unit: PERCENT · category: FLEET_STRUCTURE
  - why_it_matters: Asset-light model (charter-in) scales fast but locks in rates; TMAS mixed model vs. SMDR asset-heavy — thesis inversion in charter-rate down-cycles.

- `metric_id`: `idx:CoastalDomesticVsInternationalRevenue`
  - name_en: Domestic Coastal (Cabotage) vs. International Revenue Mix (%)
  - name_id: Komposisi Pendapatan Domestik vs. Internasional
  - unit: PERCENT · category: REVENUE_MIX
  - why_it_matters: Cabotage protected under UU 17/2008 & Inpres 5/2005 → domestic rates less volatile, moat for Indonesian-flagged carriers (TMAS, SMDR).
  - regulatory_anchor: UU 17/2008 Pelayaran; Inpres 5/2005 asas cabotage.

- `metric_id`: `idx:BunkerHedgedPct`
  - name_en: Bunker Fuel Hedged Volume (%)
  - name_id: Porsi BBM Bunker yang Dilindung Nilai
  - unit: PERCENT · category: RISK_HEDGING
  - why_it_matters: VLSFO/MGO price 40% of opex; hedge programs (BLTA legacy, SMDR) determine earnings smoothness.

**HIGH:**

- `idx:VesselAgeAverageYears` — fleet renewal capex profile & IMO 2020/2023 emissions compliance.
- `idx:TCEDailyRateUSD` — Time Charter Equivalent — normalizes CoA/spot for benchmarking.
- `idx:DrydockDaysUtilizationHit` — planned maintenance revenue impact.
- `idx:GreenAmmoniaLNGReadyFleetShare` — IMO 2030 fuel-transition readiness.

## DIGITAL

**Currently covered:** GrossTransactionValue, GrossMerchandiseValue, TakeRate, MonthlyActiveTransactingUsers, ContributionMargin, AdjustedEBITDADigital, PromotionalIncentives.

Reasonably deep. Missing: segment-level contribution margin, cost-per-transaction, monetization mix, cohort retention.

**CRITICAL:**

- `metric_id`: `idx:ContributionMarginBySegment`
  - name_en: Contribution Margin by Segment (On-demand/E-commerce/Fintech %)
  - name_id: Contribution Margin per Segmen
  - unit: PERCENT · category: UNIT_ECONOMICS_MIX
  - why_it_matters: GOTO/BUKA blended contribution margin masks segment divergence — Gojek on-demand +ve while Tokopedia -ve, or vice versa post-TikTok deal. Segment split reveals subsidy migration.

- `metric_id`: `idx:CostPerTransactionIDR`
  - name_en: Cost per Transaction / Order (IDR)
  - name_id: Biaya per Transaksi/Order
  - unit: IDR · category: UNIT_ECONOMICS
  - why_it_matters: Operating cost less incentives ÷ transactions; the leading FCF indicator once take-rate saturates.

- `metric_id`: `idx:TakeRateTrajectoryTrend`
  - name_en: Take Rate Delta YoY (bps)
  - name_id: Perubahan Take Rate YoY (bps)
  - unit: BASIS_POINTS · category: MONETIZATION_TREND
  - why_it_matters: Take-rate expansion is the primary monetization lever post-user-growth; -30bps in a segment signals promo re-escalation.

- `metric_id`: `idx:PaylaterBnplLoanBookIDRbn`
  - name_en: BNPL / Paylater Loan Book (IDR bn)
  - name_id: Outstanding Paylater/BNPL
  - unit: IDR_BILLION · category: FINTECH_EXPOSURE
  - why_it_matters: GoPayLater, ShopeePL, Kredivo — regulated under POJK 10/POJK.05/2022 P2P lending & POJK 40/POJK.05/2024 BNPL; loan-book growth & NPL are credit-cycle exposure.
  - regulatory_anchor: POJK 40/POJK.05/2024 BNPL rules.

- `metric_id`: `idx:CohortMonthlyRetentionPct`
  - name_en: Monthly Cohort Retention @ M6/M12 (%)
  - name_id: Retensi Cohort Bulanan @M6/M12
  - unit: PERCENT · category: USER_STICKINESS
  - why_it_matters: Retention curve slope determines LTV/CAC math; below-40% M6 retention flags subsidy-dependent users.

**HIGH:**

- `idx:AdsRevenueShare` — high-margin monetization (TikTok Shop, Tokopedia Ads).
- `idx:CashInLimitPerUserGoPayOVO` — BI wallet limit compliance.
- `idx:FreshFoodGroceryVolume` — new-category penetration.
- `idx:CloudDataCenterRevenueShare` — infra adjacency (GOTO Tokopedia Cloud).

---

# Consolidated Summary

- Total proposed additions across 24 sectors: **~135** high-signal KPIs (CRITICAL ~85, HIGH ~50), all non-duplicative of existing SECTOR_KPIS.
- Sectors with the largest coverage gaps: **BASIC_MATERIALS** (essentially uncovered), **TELCO** (missing FBB/enterprise leg), **TOWER** (only 2 KPIs today), **BANK** (missing fee-income + digital + funding mix), **RENEWABLE_ENERGY** (missing PPA/RUPTL structure).
- Regulatory anchors cited for 22 KPIs across POJK (banking, BNPL, green bond), ESDM/RKAB (coal, nickel, oil-gas, biodiesel), Kemenkes (BPJS, pharma API), PUPR (toll SPM, FLPP), Kemendag (CPO DMO), and EU EUDR (palm, pulp) — these become mandatory-transmit KPIs under the validator's contract framework.
- All proposed metric_ids follow the `idx:CamelCase` convention and use the ontology's existing category taxonomy where possible; a handful of new categories introduced (PPA_STRUCTURE, PAYER_MIX, CONTRACT_STRUCTURE, FEEDSTOCK_OPTIMIZATION, HUB_STATUS) which can be added to the ontology's category enum.
