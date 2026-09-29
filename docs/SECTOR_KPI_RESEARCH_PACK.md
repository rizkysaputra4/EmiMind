# Sector KPI Research Pack — IDX Missing Sectors

**Purpose:** Seed the EmiMind extraction ontology with *differentiating* sector KPIs — the metrics that reveal a company's thesis (unit economics, mix, capacity, risk posture) rather than generic income-statement lines. Written to be consumed by an LLM agent that later loads these into the `metric_ontology` and `announcement_contracts` tables.

**Rules applied:**
- No generic KPIs (Revenue, Net Profit, EBITDA, ROE, ROA) unless there is a sector-specific twist required by OJK/POJK definition.
- Volume × Price decomposition wherever the business is a physical-good/service producer.
- Segment/mix KPIs when the P&L has multiple lines.
- Leading indicators (order book, presales, subscribers, MKBD, RBC, gearing) preferred over lagging ones.
- OJK/POJK regulatory ratios cited as ground truth where they exist.
- `metric_id` proposed in `idx:CamelCase`; `TBD` where uncertain.
- Vintage: 2025–2026 sources preferred.

**Global source_priority legend:** `INVESTOR_PRESENTATION` (IP), `PUBLIC_EXPOSE` (PE), `ANNUAL_REPORT` (AR), `OJK_RBC_REPORT` (RBC), `FS_NOTES` (FSN), `IDX_DISCLOSURE` (IDX).

---

## Table of Contents

1. INSURANCE_GENERAL (Asuransi Umum / Kerugian)
2. INSURANCE_LIFE (Asuransi Jiwa)
3. INSURANCE_REINSURANCE (Reasuransi)
4. MULTIFINANCE (Perusahaan Pembiayaan)
5. SECURITIES_BROKER (Perusahaan Efek — PPE/PEE)
6. AIRLINES (Penerbangan Berjadwal)
7. LOGISTICS_FORWARDING (Logistik & Freight Forwarding)
8. HOTEL_TOURISM (Hotel & Pariwisata)
9. MEDIA_BROADCAST (Media Penyiaran)
10. TEXTILE_GARMENT (Tekstil & Garmen)
11. STEEL_METAL (Baja & Logam Dasar)
12. TIN_MINING (Pertambangan Timah)
13. CERAMIC_GLASS (Keramik & Kaca)
14. BEVERAGE_ALCOHOL (Minuman Beralkohol)
15. FOOD_INGREDIENT (Bahan Pangan / Ingredients)
16. PACKAGING (Kemasan)
17. CHEMICALS (Kimia Dasar)
18. INDUSTRIAL_GAS (Gas Industri)
19. WATER_UTILITY (Air Bersih Swasta)
20. FOOTWEAR (Alas Kaki)
21. PLASTICS_HOUSEWARE (Plastik & Peralatan RT)
22. JEWELRY_LUXURY (Perhiasan & Emas)
23. FOOD_RESTAURANT (QSR & Casual Dining)
24. INVESTMENT_HOLDING (Perusahaan Investasi Diversifikasi)
25. PROPERTY_REIT (DIRE)
26. HEAVY_EQUIP_MINING_SERVICES (Jasa Kontraktor Tambang)
27. EDUCATION (Pendidikan Swasta)
28. HEALTHCARE_DEVICE (Alat Kesehatan / MedTech)

---

## INSURANCE_GENERAL (General / Non-Life Insurance)

**Thesis:** A general insurer's story is *underwriting discipline* × *investment leverage on float* × *solvency headroom*. Revenue growth is uninteresting unless combined ratio is < 100% (i.e. they are underwriting profitably, not buying market share by mispricing risk). RBC ratio tells you how much room they have before the regulator intervenes.

**Thesis KPIs:**

| metric_id | name_en / name_id | unit | category | why_it_matters | search_hints | source_priority |
|---|---|---|---|---|---|---|
| `idx:RiskBasedCapitalRatio` | Risk-Based Capital Ratio / Rasio Solvabilitas RBC | PERCENT | RISK | Regulatory solvency margin; POJK 71/2016 mandates min 120% — anything below signals OJK-supervision risk and possible dividend suspension. | "Risk Based Capital", "Rasio Solvabilitas", "RBC 120%", "Tingkat Solvabilitas" | RBC, AR |
| `idx:LossRatio` | Loss Ratio / Rasio Klaim | PERCENT | ASSET_QUALITY | Claims incurred / earned premium — the core measure of pricing accuracy vs actual claims experience. TUGU improved from 62.05% → 54.41% in 2025 [tugu.com]. | "Rasio Klaim", "Loss Ratio", "Beban Klaim / Pendapatan Premi" | AR, IP |
| `idx:ExpenseRatio` | Expense Ratio / Rasio Beban Usaha | PERCENT | EFFICIENCY | Operating expenses / earned premium — indicates distribution efficiency (agent commissions vs direct/digital). | "Rasio Beban", "Expense Ratio", "Beban Usaha / Premi Neto" | AR |
| `idx:CombinedRatio` | Combined Ratio / Rasio Kombinasi | PERCENT | PROFITABILITY | Loss + expense ratio; <100% = underwriting profit, >100% = losing money on policies (must recover via investment income). | "Combined Ratio", "Rasio Kombinasi" | AR, IP |
| `idx:GrossWrittenPremium` | Gross Written Premium (GWP) / Premi Bruto | IDR | GROWTH | Top-line new business booked — must be paired with loss ratio to know if growth is quality or dumping. | "Premi Bruto", "GWP", "Gross Written Premium" | AR, IP |
| `idx:NetRetentionRatio` | Net Retention Ratio / Rasio Retensi Sendiri | PERCENT | RISK | (GWP − Ceded) / GWP — how much risk they keep vs cede to reinsurers; POJK/SEOJK 31/2015 sets minimum retention by class of business. | "Retensi Sendiri", "Retention Ratio", "Premi Reasuransi" | AR, FSN |
| `idx:GwpByLineOfBusiness` | GWP by Line (Property/Motor/Marine/Health) / Premi per Lini Usaha | IDR | MARKET_SHARE | Mix matters: motor is high-frequency-low-severity; property CAT-exposed; health is inflation-linked; marine/aviation is IDR/USD mixed. | "Premi per Lini", "Property", "Kendaraan Bermotor", "Marine Cargo", "Kesehatan" | AR, FSN |
| `idx:UnderwritingResult` | Underwriting Result / Hasil Underwriting | IDR | PROFITABILITY | GWP − reinsurance − claims − commissions; TUGU jumped from Rp699bn to Rp923bn in 2025 [tugu.com]. | "Hasil Underwriting", "Underwriting Result" | AR, IP |
| `idx:InvestmentYield` | Investment Yield / Hasil Investasi | PERCENT | PROFITABILITY | Return on the float; for a general insurer with combined ratio near 100%, investment yield is often the entire profit. | "Hasil Investasi", "Yield Investasi", "Pendapatan Investasi" | AR, FSN |
| `idx:ClaimsSettlementRatio` | Claims Settlement Ratio / Rasio Klaim Dibayar | PERCENT | OPERATIONAL | Claims paid / claims reported — proxy for customer trust; low ratio can indicate reserving disputes. | "Klaim Dibayar", "Claims Settlement" | AR |
| `idx:ReserveAdequacyRatio` | Technical Reserve Adequacy / Kecukupan Cadangan Teknis | PERCENT | RISK | Reserves / minimum required per POJK 71/2016 — under-reserving flatters current EPS at future cost. | "Cadangan Teknis", "Technical Reserve", "PAYDI" | RBC, FSN |
| `idx:CatastropheExposure` | Catastrophe Exposure (PML) / Eksposur Bencana | IDR | RISK | Probable maximum loss from a single event — critical for property lines in earthquake/flood zones. | "PML", "Probable Maximum Loss", "CAT Exposure" | AR, IP |

**Regulatory disclosures:**
- **POJK 71/POJK.05/2016** — Kesehatan Keuangan Perusahaan Asuransi/Reasuransi; RBC minimum **120%** [milliman.com], target level 120%, with SEOJK 24/SEOJK.05/2017 specifying the five risk-charge categories (credit, insurance, market, operational, catastrophe).
- **SEOJK 31/SEOJK.05/2015** — self-retention limits by line of business, and mandatory domestic reinsurance placement thresholds [lexology.com].
- **POJK 28/2020 & POJK 3/2020** — mandatory audited actuarial report and technical reserves calculation.
- Industry-wide (March 2025): general insurers/reinsurers RBC = **316.96%**, life = **467.73%** [insuranceeurope.eu]. So most listed IDX names sit comfortably above the 120% floor; use the *delta* vs peer as a signal, not the absolute number.

**Peer references:**
- **AIG, Chubb, Zurich** — disclose "accident-year combined ratio ex-CAT", "prior-year reserve development", and cat losses by event; IDX peers rarely split accident year vs calendar year.
- **QBE (Australia)** — publishes attritional loss ratio, large-loss ratio, and CAT loss ratio separately. IDX peers should but usually don't.
- **Ping An P&C (HK)** — discloses e-commerce/direct channel mix as % of GWP; increasingly relevant as GoTo/Grab embed insurance.

**Sources used:**
- [Milliman — Indonesia RBC PDF](https://media.milliman.com/v1/media/edge/images/millimaninc5660-milliman6442-prod27d5-0001/media/Milliman/importedfiles/uploadedFiles/insight/Periodicals/asia-ealert/indonesia-rbc-requirements.pdf)
- [Tugu Insurance 2025 performance](https://www.tugu.com/en/news/tugu-insurance-gelar-rups-tahunan-dan-paparkan-kinerja-cemerlang)
- [Insurance Europe — Indonesia June 2025 fact sheet](https://www.insuranceeurope.eu/mediaitem/9de9f245-0b47-4460-8caa-bedef26f393e/Country+fact+sheet-Indonesia_+June+2025.pdf)
- [Lexology — Indonesia insurance regulation Q&A](https://www.lexology.com/library/detail.aspx?g=1f6db539-5c39-440e-957f-eccf71238af2)

---

## INSURANCE_LIFE (Life Insurance)

**Thesis:** Life insurance is a *long-duration liability* business. The story is: (a) is new business (APE / VNB) growing profitably? (b) is persistency high enough that acquisition costs earn back? (c) is the general account matched to liabilities? PAYDI-linked (unit-linked) restructuring under POJK 5/2022 has forced a channel and product mix change.

**Thesis KPIs:**

| metric_id | name_en / name_id | unit | category | why_it_matters | search_hints | source_priority |
|---|---|---|---|---|---|---|
| `idx:RiskBasedCapitalRatio` | RBC Ratio (Life) / Rasio Solvabilitas RBC Jiwa | PERCENT | RISK | POJK 71/2016 min 120%; life industry avg 467.73% (Mar 2025) [insuranceeurope.eu]. | "RBC", "Rasio Solvabilitas Jiwa" | RBC |
| `idx:AnnualPremiumEquivalent` | APE / Setara Premi Tahunan | IDR | GROWTH | Standard new-business metric: regular premium + 10% of single premium. | "APE", "Annualized Premium Equivalent" | IP, AR |
| `idx:ValueOfNewBusiness` | VNB / Nilai Bisnis Baru | IDR | PROFITABILITY | PV of future profits from new policies — the actuarial forward indicator of shareholder value creation. | "VNB", "Value of New Business", "Nilai Bisnis Baru" | IP, AR |
| `idx:EmbeddedValue` | Embedded Value (EV) / Nilai Intrinsik | IDR | PROFITABILITY | Net worth + PV of in-force business; the "book value" measure that matters for life insurers. | "Embedded Value", "EV Movement" | AR |
| `idx:PersistencyRatio13m` | 13-Month Persistency / Persistensi Bulan ke-13 | PERCENT | ASSET_QUALITY | % of policies still in force after 13 months; <80% signals mis-sold policies or agent churn. | "Persistensi", "Persistency Ratio", "Lapse Rate" | AR |
| `idx:PersistencyRatio25m` | 25-Month Persistency / Persistensi Bulan ke-25 | PERCENT | ASSET_QUALITY | Deeper cohort quality signal, especially for PAYDI/unit-linked. | "25-month persistency" | AR |
| `idx:ProductMixTraditionalUL` | Traditional vs Unit-Linked Mix / Bauran Produk Tradisional-Unitlink | PERCENT | MARKET_SHARE | POJK 5/2022 tightened PAYDI rules; shift back to traditional protection is a strategic re-pivot. | "PAYDI", "Unit Link", "Tradisional", "Product Mix" | AR, IP |
| `idx:DistributionChannelMix` | Distribution Mix (Agency/Bancassurance/Digital) / Bauran Kanal | PERCENT | MARKET_SHARE | Bancassurance yields lower VNB margin but larger tickets; agency is high-touch high-margin. | "Bancassurance", "Keagenan", "Kanal Distribusi" | AR, IP |
| `idx:ClaimsIncurredRatio` | Claims Incurred Ratio / Rasio Klaim Jiwa | PERCENT | ASSET_QUALITY | Death/health claims vs earned premium; health rider inflation is a real 2025-26 pressure point. | "Rasio Klaim", "Beban Klaim" | AR |
| `idx:InvestmentReturnGeneralAccount` | General Account Investment Return / Imbal Hasil Investasi | PERCENT | PROFITABILITY | Return on backing assets vs guaranteed policy rates — negative spread destroys EV. | "Hasil Investasi", "Yield Portofolio" | AR, FSN |
| `idx:AgentProductivity` | Agent Productivity / Produktivitas Agen | IDR / AGENT | EFFICIENCY | APE per active agent; measures the sales force health of agency-led insurers (PNIN, PNLF). | "Produktivitas Agen", "APE per Agent", "Agen Aktif" | IP, PE |
| `idx:AssetLiabilityDurationGap` | ALM Duration Gap / Kesenjangan Durasi | YEARS | RISK | Duration of assets vs liabilities; large positive gap = rate-cut exposure, negative gap = rate-rise exposure. | "Duration Gap", "ALM", "Asset-Liability Matching" | AR, FSN |

**Regulatory disclosures:**
- **POJK 71/POJK.05/2016** — same RBC framework as general insurance, minimum **120%**.
- **POJK 5/POJK.05/2022** — PAYDI (Produk Asuransi Yang Dikaitkan Dengan Investasi) product governance; mandates cooling-off period, illustration standards.
- **POJK 20/2023** — mandatory Anti-Fraud & AML framework disclosure.
- **SEOJK 27/SEOJK.05/2017** — actuarial valuation of technical reserves (Gross Premium Valuation).

**Peer references:**
- **AIA Group (HK)** — publishes VNB, VNB margin, ANP, EV movement, sensitivities to interest rates and mortality. IDX peers (esp. PNIN/PNLF) publish some but rarely the VNB sensitivity.
- **Prudential plc / Manulife Asia** — disclose new business margin by market and product; strong benchmark for what a mature life insurer should reveal.
- **Ping An Life** — publishes NBV per agent and MDRT count; measures agent quality, not just headcount.

**Sources used:**
- [Insurance Europe Indonesia Country Fact Sheet](https://www.insuranceeurope.eu/mediaitem/9de9f245-0b47-4460-8caa-bedef26f393e/Country+fact+sheet-Indonesia_+June+2025.pdf)
- [Lexology insurance regulation Indonesia](https://www.lexology.com/library/detail.aspx?g=1f6db539-5c39-440e-957f-eccf71238af2)
- [ARMA Law — Q&A insurance reinsurance Indonesia](https://www.mondaq.com/reinsurance/1219698/insurance-comparative-guide)

---

## INSURANCE_REINSURANCE (Reinsurance — MREI, Indonesia Re, Nasional Re)

**Thesis:** Reinsurance is a *capacity provider* with a portfolio-level view. The story is: retrocession pattern, treaty vs facultative mix, and — critically — CAT concentration. Under POJK/SEOJK 31/2015, primary insurers must place minimum treaty capacity domestically, which supports Indonesian Re / MREI top line but leaves them exposed to Indonesian CAT risk.

**Thesis KPIs:**

| metric_id | name_en / name_id | unit | category | why_it_matters | search_hints | source_priority |
|---|---|---|---|---|---|---|
| `idx:RiskBasedCapitalRatio` | RBC Ratio | PERCENT | RISK | Same POJK 71/2016 floor of 120%; industry avg for general/re 316.96% (Mar 2025). | "RBC", "Rasio Solvabilitas" | RBC |
| `idx:CombinedRatio` | Combined Ratio | PERCENT | PROFITABILITY | Same metric as general insurers, but reinsurers must earn ~95% combined for adequate ROE. | "Combined Ratio", "Rasio Kombinasi" | AR |
| `idx:TreatyFacultativeMix` | Treaty vs Facultative GWP Mix / Bauran Treaty-Fakultatif | PERCENT | MARKET_SHARE | Treaty = stable recurring; facultative = higher-margin but volatile large single risks. | "Treaty", "Fakultatif", "Facultative" | AR, IP |
| `idx:ProportionalNonProportionalMix` | Proportional vs Non-Proportional / Proporsional-Non Proporsional | PERCENT | RISK | Non-proportional (XL) = tail risk transfer; growth here = client hedging catastrophe. | "Excess of Loss", "XL Treaty", "Kuota Bagian" | AR, FSN |
| `idx:RetrocessionRatio` | Retrocession Ratio / Rasio Retrosesi | PERCENT | RISK | % of assumed risk they pass to global retrocessionaires (Munich Re, Swiss Re); high ratio = low own capacity. | "Retrosesi", "Retrocession" | AR, FSN |
| `idx:CatConcentration` | CAT Concentration (Earthquake/Flood) / Konsentrasi Bencana | IDR / PERCENT | RISK | Java earthquake and Jakarta flood are top-2 aggregations; single-event PML disclosure is a differentiator. | "PML", "Konsentrasi CAT", "Gempa Bumi" | AR, IP |
| `idx:DomesticVsOverseasCession` | Domestic vs Overseas Ceded Premium Split | PERCENT | REGULATORY | SEOJK 31/2015 mandates minimum domestic placement; overseas share signals capacity headroom. | "Reasuransi Dalam Negeri", "Luar Negeri", "Domestic Reinsurance" | AR, FSN |
| `idx:InvestmentYield` | Investment Yield | PERCENT | PROFITABILITY | Reserves are longer-tail than general insurance → duration risk is amplified. | "Yield", "Hasil Investasi" | AR |
| `idx:GwpGrowthByTreatyYear` | Renewal Rate Change / Perubahan Suku Premi | PERCENT | PRICING | Global hard market 2023-25 has lifted treaty rates; magnitude of renewal price change is the key alpha. | "Rate Change", "Suku Premi", "Renewal" | IP |

**Regulatory disclosures:**
- **POJK 71/POJK.05/2016** — RBC framework applies to reinsurers.
- **SEOJK 31/SEOJK.05/2015** — self-retention limits and mandatory domestic reinsurance placement by primary insurers.
- **OJK Regulation drafts 2025-26** — allowing foreign reinsurer branches domestically [reinsurancene.ws], which may compress MREI/Indonesia Re margins.

**Peer references:**
- **Munich Re, Swiss Re, Hannover Re** — publish CAT budget, combined ratio ex-CAT, and reserve triangles. IDX peers rarely publish reserve triangles.
- **Korean Re** — a good Asia peer; discloses treaty vs facultative and proportional vs XL splits clearly.

**Sources used:**
- [Reinsurance News — Indonesia branch regulation](https://www.reinsurancene.ws/indonesia-explores-relaxing-regulations-to-allow-reinsurers-to-establish-domestic-branches/)
- [Mondaq Insurance Comparative Guide — Indonesia](https://www.mondaq.com/reinsurance/1219698/insurance-comparative-guide)

---

## MULTIFINANCE (Consumer Finance & Leasing)

**Thesis:** Multifinance = *financing spread on wheels*. Story is (a) receivables growth mix (auto/motor/heavy-eq/multiguna), (b) NPF trajectory as leading credit signal, (c) gearing (regulatory hard cap = 10x per POJK 35/2018), and (d) cost of funds vs yield on receivables. Down-payment relaxation and NPF-below-1% rule create asymmetric quality winners.

**Thesis KPIs:**

| metric_id | name_en / name_id | unit | category | why_it_matters | search_hints | source_priority |
|---|---|---|---|---|---|---|
| `idx:GearingRatio` | Gearing Ratio / Rasio Gearing | RATIO | RISK | POJK 35/2018 hard cap **10.0x** (debt/equity); July 2025 industry avg 2.21x [kontan.co.id] leaves headroom, but company-level ratios vary from 1x (BFIN) to 7x+ (ADMF). | "Gearing Ratio", "Rasio Gearing", "10 kali" | AR, IP |
| `idx:NpfGrossRatio` | Gross NPF Ratio / NPF Bruto | PERCENT | ASSET_QUALITY | Gross non-performing financing; July 2025 industry 2.52% [kontan.co.id]. Threshold for consumer distress. | "NPF Bruto", "Gross NPF", "Non-Performing Financing" | AR, IP |
| `idx:NpfNetRatio` | Net NPF Ratio / NPF Neto | PERCENT | ASSET_QUALITY | POJK 35/2018 uses **1.0%** NPF Net threshold to permit 0% DP; a competitive-cost gating metric. | "NPF Neto", "NPF Net" | AR, IP |
| `idx:NewBookingsByProduct` | New Bookings by Product (Auto/Motor/HE/Multiguna) / Pembiayaan Baru per Segmen | IDR | GROWTH | Mix signals: 4W = margin-thin volume; 2W = high-yield high-risk; heavy-eq = commodity-cycle linked; multiguna = fastest-growing but riskiest. | "Pembiayaan Baru", "New Bookings", "Roda Empat", "Roda Dua", "Alat Berat" | IP, PE |
| `idx:FinancingReceivablesOutstanding` | Financing Receivables (Managed) / Piutang Pembiayaan Kelolaan | IDR | CAPACITY | Book size including joint-financing (channeling) with banks; the base for NIM math. | "Piutang Pembiayaan", "Managed Portfolio" | AR, FSN |
| `idx:NimFinancing` | Net Interest Margin (Financing) / NIM Pembiayaan | PERCENT | PROFITABILITY | Yield on receivables − cost of funds; multifinance NIMs typically 8-12%, compressed by MTN cost. | "NIM", "Net Interest Margin", "Marjin Bunga Bersih" | IP |
| `idx:CostOfFunds` | Cost of Funds / Biaya Dana | PERCENT | EFFICIENCY | Bank loans + MTN + bond mix cost; ADMF, BFIN benefit from strong ratings and channel to bank parents. | "Cost of Fund", "Biaya Dana" | AR, IP |
| `idx:CoveragingRatio` | Coverage Ratio (Reserves/NPF) / Rasio Pencadangan | PERCENT | ASSET_QUALITY | CKPN provisions vs NPF; PSAK 71 ECL adoption raised the bar. | "CKPN", "Pencadangan", "Coverage Ratio" | AR, FSN |
| `idx:ChannelMixDealerDirect` | Channel Mix (Dealer/Direct/Digital) / Bauran Kanal | PERCENT | MARKET_SHARE | Dealer-heavy = high acquisition cost, sticky flow; direct/digital = margin expansion. | "Dealer", "Digital", "Kanal Direct" | IP |
| `idx:CostToIncomeRatio` | Cost-to-Income Ratio / BOPO Pembiayaan | PERCENT | EFFICIENCY | Operating cost / operating income; scale winners (ADMF, BFIN) sit ~35-40%. | "Cost to Income", "BOPO" | AR |
| `idx:AverageContractTenor` | Average Contract Tenor / Rata-rata Tenor | MONTHS | RISK | Longer tenor = higher rate risk and duration mismatch. | "Tenor", "Jangka Waktu Kontrak" | IP |
| `idx:CollectionEfficiencyRate` | Collection Efficiency / Rasio Penagihan | PERCENT | OPERATIONAL | Cash collected / due; leading indicator of NPF 90 days before it prints. | "Collection Rate", "Penagihan" | IP, PE |

**Regulatory disclosures:**
- **POJK 35/POJK.05/2018** — Penyelenggaraan Usaha Perusahaan Pembiayaan. Sets gearing cap **≤ 10x**, NPF ≤ 5% for standard operations, and 0% DP allowed only when NPF Net < 1% [conventuslaw.com, kontan.co.id].
- **POJK 10/POJK.05/2019** — asset quality, restructuring, and CKPN calculation for financing companies.
- **POJK 47/POJK.03/2020** & **PSAK 71** — ECL provisioning methodology.
- **POJK 40/POJK.05/2019** — governance & risk management for financing companies.
- July 2025 industry stats: growth +1.79% YoY, NPF gross 2.52%, NPF net 0.88%, gearing 2.21x [kontan.co.id].

**Peer references:**
- **Bajaj Finance (India)** — publishes AUM growth split by product, cross-sell franchise metric, and NIM waterfall. IDX peers rarely disclose cross-sell.
- **Home Credit / Krungsri Consumer (Thailand)** — publishes vintage delinquency curves (30+, 60+, 90+ DPD by cohort) which are far more informative than a single NPF number.
- **Hong Leong Bank / Public Bank Auto (MY)** — publishes yield-on-receivables and cost-of-funds tables quarterly.

**Sources used:**
- [Kontan — gearing ratio multifinance trend](https://keuangan.kontan.co.id/news/gearing-ratio-multifinance-masih-menunjukkan-tren-penurunan)
- [Conventus Law — OJK financing company regulation](https://conventuslaw.com/report/indonesia-ojk-issues-new-financing-company/)
- [HBT Law — Multi-finance regulatory update](https://www.hbtlaw.com/insights/2019-03/regulatory-update-and-market-developments-indonesias-multi-finance-sector)

---

## SECURITIES_BROKER (Perusahaan Efek — Broker-Dealer & Underwriter)

**Thesis:** Broker economics = *velocity × spread on top of a regulatory capital gate*. Story: (a) MKBD headroom vs the 110% supervisory trigger, (b) brokerage market share on IDX total value, (c) mix between low-margin retail flow, high-margin IB fees, and margin-financing spread. POJK 3/2026 introduces PEKU tiering, changing the strategic calculus for smaller brokers.

**Thesis KPIs:**

| metric_id | name_en / name_id | unit | category | why_it_matters | search_hints | source_priority |
|---|---|---|---|---|---|---|
| `idx:MkbdAmount` | MKBD Absolute / Modal Kerja Bersih Disesuaikan | IDR | RISK | Net Adjusted Working Capital; OJK-mandated minimum varies by PEKU tier under POJK 3/2026 — supervision triggered at 110% of minimum [hbtlaw.com, arma-law.com]. | "MKBD", "Modal Kerja Bersih Disesuaikan", "NAWC" | IDX, AR |
| `idx:MkbdRatio` | MKBD / Min-MKBD Ratio | RATIO | RISK | Headroom vs regulatory floor; <110% triggers OJK oversight. | "MKBD ratio", "Rasio MKBD" | IDX, AR |
| `idx:PekuTier` | PEKU Classification Tier / Klasifikasi PEKU | UNITS | REGULATORY | POJK 3/2026 three-tier system based on paid-up capital + NAWC; determines allowed activities. | "PEKU", "Pengelompokan Kegiatan Usaha", "PEKU 1/2/3" | AR, IDX |
| `idx:BrokerageMarketShare` | Brokerage Market Share (Value) / Pangsa Nilai Transaksi | PERCENT | MARKET_SHARE | Share of IDX RNTH (Rata-rata Nilai Transaksi Harian); top-10 vs rest defines pricing power. | "Pangsa Pasar Broker", "RNTH", "Market Share Nilai Transaksi" | IP, PE |
| `idx:BrokerageCommissionRate` | Blended Commission Rate / Rate Komisi Blended | BPS | PRICING | Retail online brokers compressed rate to <10 bps; institutional flow still 15-25 bps. | "Rate Komisi", "Commission Rate", "bps" | AR, FSN |
| `idx:RevenueMixBrokerageIbMargin` | Revenue Mix (Brokerage/IB/Margin Financing/Asset Mgmt) / Bauran Pendapatan | PERCENT | MARKET_SHARE | The core diversification story: IB fees are lumpy but high-margin, margin financing is spread-based recurring. | "IB Fees", "Underwriting", "Margin Financing", "Bauran Pendapatan" | AR, IP |
| `idx:MarginFinancingBook` | Margin Financing Outstanding / Piutang Margin | IDR | CAPACITY | Direct spread income and — under POJK — capital-consuming; a stealth NIM business inside a broker. | "Piutang Margin", "Margin Financing" | AR, FSN |
| `idx:IbLeagueTablePosition` | IB League Table Rank / Peringkat IB | RANK | MARKET_SHARE | Equity/DCM league table position; drives fee opportunity in the next IPO/rights-issue cycle. | "League Table", "Underwriting Rank", "Lead Manager" | IP, PE |
| `idx:ClientAssetsUnderCustody` | Client Assets Under Custody / Aset Nasabah | IDR | CAPACITY | Sticky asset base; drives margin-financing capacity and cross-sell to AM/wealth. | "Aset Nasabah", "AUC" | AR |
| `idx:ActiveInvestorAccounts` | Active Investor Accounts / Rekening Nasabah Aktif | UNITS | GROWTH | Monthly active investors; a Gen-Z acquisition proxy differentiator vs KSEI-registered SID. | "Nasabah Aktif", "Active Investor" | IP |
| `idx:CostToIncomeRatio` | Cost-to-Income Ratio / BOPO Broker | PERCENT | EFFICIENCY | Scale winners (Mirae, Mandiri Sekuritas) < 60%; smaller brokers 80%+. | "Cost to Income" | AR |
| `idx:ProprietaryTradingPnl` | Prop Trading P&L / Laba Trading Sendiri | IDR | PROFITABILITY | Increasingly restricted under POJK 3/2026; disclose separately from client-flow revenue. | "Trading Sendiri", "Prop Trading" | AR, FSN |

**Regulatory disclosures:**
- **POJK 20/POJK.04/2016** — legacy MKBD calculation methodology (superseded 2026 by tiered regime).
- **POJK 3/POJK.04/2026** — new tiered PEKU regime for underwriters and broker-dealers; effective transition by 29 Oct 2026 [veritask.ai, arma-law.com].
- **POJK 5/POJK.04/2026** — investment manager licensing and capital standards for asset-management subsidiaries.
- **IDX Rule II-A** — participant obligations, MKBD daily reporting.

**Peer references:**
- **Charles Schwab / Interactive Brokers (US)** — DARTs (Daily Average Revenue Trades) and net new client assets are the modern gold standard; IDX peers rarely disclose DARTs.
- **Nomura / Daiwa** — publish IB fee breakdown by product (ECM/DCM/M&A) and geography.
- **Korea Investment & Securities** — publishes "brokerage share by segment" (retail cash, retail derivatives, institutional) which is a much better mix disclosure than IDX peers.

**Sources used:**
- [Veritask — POJK 3/2026 overview](https://veritask.ai/en/artikel/the-financial-services-authority-regulates-the-activities-capital-and-risk-management-of-securities-companies-through-regulation-of-the-financial-services-authority-number-3-of-2026)
- [HBT Law — risk & capital based regime for broker-dealers](https://www.hbtlaw.com/insights/2026-04/indonesian-implements-risk-and-capital-based-regime-for-underwriters-and-broker-dealers)
- [ARMA Law — POJK 3/2026 impacts](https://www.arma-law.com/news-event/newsflash/navigating-ojk-regulation-3/2026-key-impacts-and-compliance-considerations-for-securities-companies)

---

## AIRLINES (Penerbangan Berjadwal — GIAA, IATA)

**Thesis:** Airline = *seat-mile factory*. Revenue = ASK × Load Factor × Yield. Cost = ASK × CASK. Profit = (RASK − CASK) × ASK. Fuel is 30-40% of CASK; USD-IDR is a dagger. Story is whether they can beat CASK-ex-fuel down while yield holds.

**Thesis KPIs:**

| metric_id | name_en / name_id | unit | category | why_it_matters | search_hints | source_priority |
|---|---|---|---|---|---|---|
| `idx:AvailableSeatKilometers` | ASK / Kapasitas Kursi Kilometer | UNITS (SK) | CAPACITY | Supply metric — seats × distance. Drives all unit economics. | "ASK", "Available Seat Kilometer", "Kapasitas Produksi" | AR, IP |
| `idx:RevenuePassengerKilometers` | RPK / Penumpang Kilometer | UNITS (PK) | VOLUME | Actual passenger-km sold; RPK/ASK = load factor. | "RPK", "Revenue Passenger Kilometer" | AR, IP |
| `idx:PassengerLoadFactor` | Passenger Load Factor / Tingkat Isian Penumpang | PERCENT | OPERATIONAL | Break-even load factor typically 75-80%; below = loss-making seat pricing. | "Load Factor", "Tingkat Isian", "Kursi Terisi" | AR, IP |
| `idx:PassengerYield` | Passenger Yield / Yield per PK | USD_CENTS_PER_KM | PRICING | Revenue per RPK; the pricing signal ex-mix. | "Yield", "Yield per RPK", "Yield Penumpang" | AR, IP |
| `idx:RaskUnit` | RASK / Revenue per ASK | USD_CENTS_PER_KM | PROFITABILITY | Total revenue per ASK; combines yield and load factor. | "RASK", "Revenue per ASK" | AR, IP |
| `idx:CaskUnit` | CASK / Cost per ASK | USD_CENTS_PER_KM | EFFICIENCY | Total unit cost; must be paired with fuel to see structural efficiency. | "CASK", "Cost per ASK" | AR, IP |
| `idx:CaskExFuel` | CASK ex-Fuel / CASK Tanpa Bahan Bakar | USD_CENTS_PER_KM | EFFICIENCY | The "controllable" cost line; SIA and Cathay disclose it — IDX peers should. | "CASK ex-fuel", "Non-fuel CASK" | IP |
| `idx:FuelCostPercentOfOpex` | Fuel Cost % OpEx / Persentase Bahan Bakar | PERCENT | RISK | Sensitivity indicator; 30-40% typical. | "Bahan Bakar", "Fuel Cost", "Jet Fuel" | AR |
| `idx:AverageStageLength` | Avg Stage Length / Rata-rata Panjang Rute | KM | OPERATIONAL | Longer stage = lower unit cost; mix shift to international expands stage length. | "Stage Length", "Panjang Rute" | AR |
| `idx:AircraftUtilization` | Aircraft Utilization / Utilisasi Pesawat | HOURS_PER_DAY | EFFICIENCY | Block hours/day per aircraft; 10+ hrs = efficient short-haul, 14+ hrs = long-haul. | "Utilisasi Pesawat", "Block Hours", "Aircraft Utilization" | AR, IP |
| `idx:FleetSizeAndAge` | Fleet Size & Average Age / Ukuran & Umur Armada | UNITS / YEARS | CAPACITY | Older fleet = higher maintenance, worse fuel burn; fleet renewal capex signal. | "Armada", "Umur Rata-rata Pesawat", "Fleet Age" | AR |
| `idx:OnTimePerformance` | On-Time Performance (OTP) / Ketepatan Waktu | PERCENT | OPERATIONAL | Customer NPS proxy; drives yield premium. | "OTP", "On-Time Performance", "Ketepatan Waktu" | AR |
| `idx:AncillaryRevenuePerPax` | Ancillary Revenue per Pax / Pendapatan Tambahan per Penumpang | USD | PRICING | Baggage, seat select, cargo belly — margin-expanding for LCC-adjacent carriers. | "Ancillary Revenue", "Pendapatan Non-Tiket" | IP |
| `idx:CargoTonKilometers` | Cargo FTK / Ton Kilometer Kargo | TON_KM | VOLUME | Belly cargo is high-margin; GIAA's freight arm materially moves quarters. | "FTK", "Freight Ton Kilometer", "Kargo" | AR |

**Regulatory disclosures:**
- **Kementerian Perhubungan Regulation PM 78/2019** — tariff bands (Tarif Batas Atas / Bawah) for domestic economy class; a direct cap on yield.
- **UU 1/2009** on Aviation — safety, licensing, ownership rules (max 49% foreign).
- IATA guidelines (voluntary) — RASK/CASK disclosure standards; GIAA discloses partially in Annual Report.

**Peer references:**
- **Singapore Airlines** — publishes CASK-ex-fuel, breakeven load factor, and fuel-hedge cover ratio quarterly. GIAA does not disclose fuel-hedge cover.
- **Cathay Pacific** — cargo yield published separately from passenger yield; a critical split.
- **AirAsia (MY)** — LCC benchmark; publishes ancillary revenue per pax and % of total revenue as headline KPI.

**Sources used:**
- [Garuda Indonesia AR 2025](https://www.garuda-indonesia.com/static/content/dam/garuda/hubungan-investor/AR-GARUDA-2025_Final.pdf)
- [IDX Garuda Q2 2025 audited FS](https://www.idx.co.id/StaticData/NewsAndAnnouncement/ANNOUNCEMENTSTOCK/From_EREP/202509/20250923201233-57599-0/GIAA%20Report%20%20Juni%20Auditied%202025.pdf)

---

## LOGISTICS_FORWARDING (Logistics & Freight Forwarding)

**Thesis:** IDX logistics is a mixed bag — ASSA is rent-a-car + last-mile courier; TRAM/NELY are marine/tug; SAPX is courier. The unifying thesis is *asset turnover × yield per asset × utilization*. For freight forwarders, non-asset commission spread and route mix dominate.

**Thesis KPIs:**

| metric_id | name_en / name_id | unit | category | why_it_matters | search_hints | source_priority |
|---|---|---|---|---|---|---|
| `idx:FleetSize` | Fleet Size (Trucks/Vessels/Rental Cars) / Jumlah Armada | UNITS | CAPACITY | ASSA operates 1,600 first/last-mile vehicles [aldiracita, ken research]; direct capacity gate. | "Jumlah Armada", "Fleet Size", "Truk", "Kapal" | AR, IP |
| `idx:FleetUtilizationRate` | Fleet Utilization / Utilisasi Armada | PERCENT | OPERATIONAL | Days-in-service / available days; the alpha metric. | "Utilisasi Armada", "Fleet Utilization" | IP |
| `idx:RevenuePerVehiclePerMonth` | Revenue per Vehicle per Month / Pendapatan per Kendaraan | IDR | EFFICIENCY | Yield per asset — comparable across fleet mix. | "Revenue per Truck", "Revenue per Vehicle" | IP |
| `idx:ParcelVolume` | Parcel Volume / Volume Paket | UNITS | VOLUME | E-commerce fulfillment story; SAPX/Coldspace/AnterAja. | "Volume Paket", "Parcel Volume" | IP |
| `idx:AveragePricePerParcel` | Avg Price per Parcel / Harga Rata-rata Paket | IDR | PRICING | Post-Shopee-Xpress war, blended parcel yield has collapsed to ~Rp8-12k. | "Yield per Paket", "ASP Paket" | IP |
| `idx:RevenueMixByService` | Revenue Mix (Rental/Courier/Warehouse/ColdChain) / Bauran Segmen | PERCENT | MARKET_SHARE | Warehouse/cold-chain is capex-heavy but sticky; courier is scale-driven margin-thin. | "Segmen Usaha", "Bauran Pendapatan" | AR |
| `idx:WarehouseOccupancyRate` | Warehouse Occupancy / Okupansi Gudang | PERCENT | OPERATIONAL | For 3PL: >90% signals capacity build-out need; <75% signals demand weakness. | "Okupansi Gudang", "Warehouse Occupancy" | IP |
| `idx:AverageContractDuration` | Avg Contract Duration / Tenor Kontrak Rata-rata | MONTHS | RISK | Long contract = revenue visibility; short = re-price risk. | "Tenor Kontrak" | IP |
| `idx:CustomerConcentration` | Top-5 Customer Concentration / Konsentrasi Pelanggan | PERCENT | RISK | If Shopee/Tokopedia = 40%+ of revenue, a single-relationship risk. | "Konsentrasi Pelanggan", "Top Customer" | AR, FSN |
| `idx:VesselDayRate` | Vessel Day Rate (Tug/Barge) / Tarif Harian Kapal | USD | PRICING | For TRAM/NELY marine logistics; tug rates track coal spot and Brent. | "Day Rate", "Tarif Kapal" | IP |
| `idx:FuelCostPassThroughRatio` | Fuel Pass-Through / Pass-Through Bahan Bakar | PERCENT | RISK | % of fuel cost recovered via surcharge; determines fuel-price sensitivity. | "Fuel Surcharge", "Pass-Through" | AR, IP |
| `idx:DeliverySuccessRate` | Delivery Success Rate (First Attempt) / Sukses Antar | PERCENT | OPERATIONAL | E-commerce fulfillment quality metric; drives repeat customer share. | "Success Rate", "Sukses Antar Pertama" | IP |

**Regulatory disclosures:**
- **UU 22/2009** on Road Traffic — commercial vehicle licensing.
- **UU 17/2008** on Shipping (Marine) — cabotage principle; only Indonesian-flagged vessels may operate domestic routes (favors NELY, TRAM, POSA).
- **PM 63/2019** & **PM 118/2018** on freight forwarding.

**Peer references:**
- **JB Hunt (US)**, **DSV (DK)** — publish revenue-per-load, tractor count, and detention-per-load.
- **YCP Solidiance / SF Express (CN)** — publish delivery success rate, parcel volume, average revenue per parcel monthly.
- **Kerry Logistics (HK)** — clear segment revenue-and-EBIT margin split by mode (air, sea, road, warehousing).

**Sources used:**
- [Aldiracita Sunrise 24 Feb 2025 — ASSA](https://aldiracita.com/aldira-sunrise-24-february-2025/)
- [Ken Research — Indonesia Logistics Market 2025](https://www.kenresearch.com/industry-reports/indonesia-logistics-market)

---

## HOTEL_TOURISM (Hotel & Tourism — PJAA, JIHD, BUVA, PANR, HOTL)

**Thesis:** Hotel = *RevPAR* (ADR × Occupancy) × room count. Bali-heavy names ride international-arrivals cycle; Jakarta MICE names ride corporate spend cycle. Theme-park names (PJAA) are ticket + F&B unit-economics stories.

**Thesis KPIs:**

| metric_id | name_en / name_id | unit | category | why_it_matters | search_hints | source_priority |
|---|---|---|---|---|---|---|
| `idx:OccupancyRate` | Occupancy Rate / Tingkat Hunian | PERCENT | OPERATIONAL | Rooms sold / rooms available; STR April 2025 SE Asia peak forecast 77-80% [hotelnewsresource]. | "Tingkat Hunian", "Occupancy", "Okupansi" | IP, PE |
| `idx:AverageDailyRate` | ADR / Tarif Kamar Rata-rata | IDR | PRICING | Room revenue / rooms sold; the pricing decision variable. | "ADR", "Tarif Rata-rata", "Room Rate" | IP, PE |
| `idx:RevenuePerAvailableRoom` | RevPAR / Pendapatan per Kamar Tersedia | IDR | PROFITABILITY | ADR × Occupancy; the single most important hotel KPI. Bali RevPAR +14% YoY 2025. | "RevPAR", "Revenue per Available Room" | IP, PE |
| `idx:TotalRevenuePerAvailableRoom` | TRevPAR (incl F&B/Spa) / TRevPAR | IDR | PROFITABILITY | Includes non-room revenue; the true asset-yield metric. | "TRevPAR", "Total Revenue per Available Room" | IP |
| `idx:GopParRatio` | GOPPAR / Gross Operating Profit per Available Room | IDR | PROFITABILITY | Post-departmental-expense profit per room; scale efficiency metric. | "GOPPAR", "GOP per Room" | AR |
| `idx:RoomInventoryCount` | Room Inventory (Owned/Managed/Franchised) | UNITS | CAPACITY | Room count mix by ownership model; capex intensity differs. | "Jumlah Kamar", "Room Inventory" | AR |
| `idx:PropertyPortfolioByLocation` | Portfolio by Location (Bali/Jakarta/Others) | PERCENT | MARKET_SHARE | Location mix drives cyclicality — Bali (leisure) vs Jakarta (MICE). | "Portofolio Lokasi", "Portfolio by Region" | AR |
| `idx:PropertyPortfolioByBrand` | Portfolio by Brand Tier (Luxury/Upscale/Midscale) | PERCENT | MARKET_SHARE | ADR tier segments — luxury = high-margin high-volatility. | "Segmen Bintang", "Brand Tier" | AR |
| `idx:ThemeParkVisitorCount` | Theme Park Visitors / Kunjungan Taman Rekreasi | UNITS | VOLUME | For PJAA (Ancol); volume × ticket ASP = park revenue. | "Kunjungan", "Visitor Count", "Ancol" | AR, IP |
| `idx:AverageSpendPerVisitor` | Avg Spend per Visitor / Pengeluaran Rata-rata per Pengunjung | IDR | PRICING | Ticket + in-park F&B/merchandise per head. | "ASP Pengunjung", "Spend per Visitor" | IP |
| `idx:InternationalArrivalMix` | International Arrival Mix / Bauran Wisatawan Internasional | PERCENT | MARKET_SHARE | International guests spend 2-3x domestic; leading indicator of RevPAR mix. | "Wisatawan Asing", "International Arrival" | IP |
| `idx:FoodBeverageRevenueMix` | F&B Revenue % of Total / Bauran F&B | PERCENT | MARKET_SHARE | MICE hotels get 40%+ F&B; leisure gets 15-25%. | "Bauran F&B", "F&B Revenue" | AR |

**Regulatory disclosures:**
- **PP 50/2011** & **UU 10/2009** on tourism.
- **Perda Bali** on hotel moratorium in specific zones — affects supply growth.
- **PP 24/2022** on creative economy — related to theme parks.

**Peer references:**
- **Shangri-La Asia (HK)**, **Genting Singapore** — publish GOPPAR by property, F&B captured revenue.
- **Marriott/Hilton** — publish "system-wide RevPAR" splits (owned vs managed vs franchised).
- **Dusit Thani (TH)** — Southeast Asia comparable; discloses ADR and occupancy by property.

**Sources used:**
- [STR Asia Pacific April 2025 update](https://www.hotelnewsresource.com/article136788.html)
- [Horwath HTL — Bali hotel & branded residences 2025](https://horwathhtl.com/publication/bali-hotel-branded-residences/)
- [JIHD Investor Relations Annual Report](https://jihd.co.id/en/investor-relations/annual-report)

---

## MEDIA_BROADCAST (Media & Broadcasting — SCMA, MNCN, VIVA, FILM)

**Thesis:** Broadcast is *audience share × ad rate × sold-out inventory*, and the whole platform is being disintermediated by streaming. The alpha is (a) primetime audience share defense, (b) mix shift to subscription/digital OTT, (c) content library IP monetization. SCMA had 34.3% ad share, MNCN largest primetime share (Aug 2023) [statista, samuel.co.id].

**Thesis KPIs:**

| metric_id | name_en / name_id | unit | category | why_it_matters | search_hints | source_priority |
|---|---|---|---|---|---|---|
| `idx:PrimetimeAudienceShare` | Primetime All-People Audience Share | PERCENT | MARKET_SHARE | The rating that determines ad-rate power; SCMA & MNCN duopoly. | "Audience Share", "Primetime Share", "AMR", "Rating" | IP, PE |
| `idx:AllTimeAudienceShare` | All-Time Audience Share | PERCENT | MARKET_SHARE | 24-hour share — proxy for total inventory sell-through. | "All-Time Share", "Share Sepanjang Hari" | IP |
| `idx:AdvertisingShareOfWallet` | Ad Share of Wallet / Pangsa Belanja Iklan | PERCENT | MARKET_SHARE | Company's ad revenue / total FTA-TV ad spend. SCMA ~34%. | "Pangsa Iklan", "Ad Share" | IP |
| `idx:GrossRatingPointDelivery` | GRP Delivered / Poin Rating Kotor Ditayangkan | UNITS | VOLUME | Total rating-points sold to advertisers; volume side of ad math. | "GRP", "Gross Rating Point" | IP |
| `idx:AverageCostPerGRP` | Average CPRP / Biaya per GRP | IDR | PRICING | Effective ad rate per rating point — pricing power indicator. | "CPRP", "Cost per Rating Point" | IP |
| `idx:AdInventoryUtilization` | Ad Inventory Fill Rate / Utilisasi Inventori Iklan | PERCENT | OPERATIONAL | % of ad slots sold vs total available; softness first appears here. | "Inventory Fill", "Fill Rate" | IP |
| `idx:DigitalRevenueMix` | Digital Revenue % of Total / Bauran Pendapatan Digital | PERCENT | MARKET_SHARE | OTT/Vidio (SCMA), RCTI+ (MNCN); the strategic pivot indicator. | "Digital Revenue", "OTT", "Streaming" | AR, IP |
| `idx:SubscriberCountOTT` | OTT Paid Subscriber Count / Pelanggan Berbayar OTT | UNITS | GROWTH | Vidio, RCTI+, WeTV; scale gates unit economics. | "Pelanggan Vidio", "Subscriber OTT" | IP |
| `idx:ArpuOtt` | OTT ARPU / ARPU OTT | IDR | PRICING | ~Rp30-50k/month typical; heavy discounting depresses. | "ARPU OTT", "Average Revenue per User" | IP |
| `idx:ContentInvestmentCapex` | Content Investment / Investasi Konten | IDR | CAPACITY | Original content spend — the streaming arms race. | "Investasi Konten", "Content Cost" | AR |
| `idx:PayTvSubscribers` | Pay-TV Subscribers (MSKY/LINK) / Pelanggan TV Berbayar | UNITS | CAPACITY | Legacy K-Vision/IndiHome bundle; declining. | "Pelanggan TV Berbayar" | IP |
| `idx:ContentLibrarySize` | Content Library (Hours) / Perpustakaan Konten | UNITS (HOURS) | CAPACITY | IP monetization asset; drives licensing revenue. | "Library Konten", "Content Hours" | AR |

**Regulatory disclosures:**
- **UU 32/2002** on Broadcasting; **KPI regulations** on content quotas.
- **PP 46/2021** on Postelekomunikasi & Broadcasting.
- **UU 27/2022 (PDP)** — for OTT platforms; user data compliance.
- Digital ad growth: Indonesia total ad spend projected US$12.5bn by 2025, digital ~60% [zipdo.co, samuel.co.id].

**Peer references:**
- **ABS-CBN (PH) / Astro (MY)** — publish subscriber ARPU by tier and churn rate.
- **NetEase / iQIYI (CN)** — publish paying-ratio (paid / MAU), content cost as % of revenue.
- **Nine Entertainment (AU)** — publishes ad share, digital contribution %, and streaming EBITDA margin.

**Sources used:**
- [Samuel Sekuritas Media Sector Report](https://samuel.co.id/wp-content/uploads/2023/07/Media-Sector_20230726-EN.pdf)
- [Statista — FTA primetime TV audience share Indonesia](https://statista.com/statistics/1425908/indonesia-fta-primetime-tv-audience-share-by-company)

---

## TEXTILE_GARMENT (Textile & Garment — PBRX, INDR, POLY, TFCO, RICY)

**Thesis:** IDX textile-garment is a *dollar-revenue / rupiah-cost play* under global brand-order flow. Story is (a) capacity utilization (spindles, looms, sewing lines), (b) US/EU order book, (c) ASP by product mix, (d) sourcing-relocation tailwind from China+1. SRIL's 2024 bankruptcy [voi.id] underscores balance-sheet sensitivity.

**Thesis KPIs:**

| metric_id | name_en / name_id | unit | category | why_it_matters | search_hints | source_priority |
|---|---|---|---|---|---|---|
| `idx:SpindleCount` | Spindle Count / Jumlah Spindel | UNITS | CAPACITY | Spinning capacity; SRIL had 320,000+ spindles [oxfordbusinessgroup]. | "Spindel", "Spindle", "Ring Spinning" | AR |
| `idx:LoomCount` | Loom Count / Jumlah Alat Tenun | UNITS | CAPACITY | Weaving capacity. | "Alat Tenun", "Loom", "Weaving Machine" | AR |
| `idx:SewingLineCount` | Sewing Line Count / Jumlah Jalur Jahit | UNITS | CAPACITY | Garment finishing capacity; PBRX-relevant. | "Jalur Jahit", "Sewing Line" | AR |
| `idx:CapacityUtilization` | Capacity Utilization by Stage (Spinning/Weaving/Dyeing/Garment) | PERCENT | OPERATIONAL | Below 70% = margin destruction; above 85% = pricing power. | "Utilisasi Kapasitas", "Capacity Utilization" | IP |
| `idx:OrderBookMonths` | Order Book Coverage (Months) / Order Book | MONTHS | GROWTH | Forward orders coverage — leading indicator of the next 2 quarters. | "Order Book", "Buku Pesanan", "Booking" | IP |
| `idx:ExportRevenueMix` | Export Revenue % / Bauran Pendapatan Ekspor | PERCENT | MARKET_SHARE | USD revenue mix; drives FX sensitivity in the right direction. | "Ekspor", "Export Revenue", "Foreign Sales" | AR |
| `idx:AverageSellingPricePerKg` | ASP per Kg (Yarn/Fabric) | USD_PER_KG | PRICING | Yarn/fabric commodity price signal. | "ASP", "Harga Jual Rata-rata" | IP |
| `idx:AverageSellingPricePerPiece` | ASP per Piece (Garment) | USD | PRICING | Garment price mix; premium brands = higher ASP. | "Harga per Potong", "Price per Piece" | IP |
| `idx:CottonPolyesterMix` | Cotton vs Polyester Mix / Bauran Katun-Poliester | PERCENT | RISK | Cotton exposure = commodity risk; polyester = crude/PTA-linked. | "Katun", "Poliester", "Fiber Mix" | AR |
| `idx:TopCustomerConcentration` | Top-5 Customer Concentration / Konsentrasi Merek Pelanggan | PERCENT | RISK | Uniqlo/Nike/Adidas exposure — high concentration = single-brand risk. | "Konsentrasi Pelanggan", "Top Brand" | AR, FSN |
| `idx:UsdDebtRatio` | USD Debt / Total Debt | PERCENT | RISK | The killer — USD debt vs USD revenue matching. SRIL failure = USD debt without USD hedge. | "USD Debt", "Utang Dollar" | AR, FSN |
| `idx:InventoryDaysOnHand` | Inventory Days / Hari Persediaan | DAYS | EFFICIENCY | Fabric price volatility → inventory write-down risk if >90 days. | "Days Inventory", "Hari Persediaan" | AR |
| `idx:LaborCostPerUnit` | Labor Cost per Piece / Biaya Tenaga Kerja per Unit | USD | EFFICIENCY | Wage inflation vs Vietnam/Bangladesh competitiveness. | "Biaya TK", "Labor Cost per Unit" | AR |

**Regulatory disclosures:**
- **Permendag 8/2024** & subsequent revisions on textile import safeguards.
- **UU Cipta Kerja 2020** — labor cost & minimum wage regime; UMP annually per province.
- **Permenperin 26/2022** on TKDN for domestic content.

**Peer references:**
- **Shenzhou International (HK)** — publishes capacity by product line, capacity utilization, top-5 customer concentration.
- **Trident (India), Vardhman (India)** — publish spindle count, ASP per kg, cotton cost.
- **Interloop (PK)** — publishes production capacity per year (dozens of socks/tops) and average unit price.

**Sources used:**
- [VOI — Indonesian textile issuers list](https://voi.id/en/economy/429122)
- [Indonesia-Investments — Sri Rejeki Isman](https://www.indonesia-investments.com/business/indonesian-companies/sri-rejeki-isman/item1310)
- [OpenPR — Top 30 Indonesian Textiles Q3 2025](https://www.openpr.com/news/4332754/top-30-indonesian-textiles-public-companies-q3-2025-revenue)

---

## STEEL_METAL (Steel & Metal Products — KRAS, GDST, ISSP, ALKA)

**Thesis:** Steel = *tonnage × spread over scrap/iron-ore*. Utilization is dispositive — KRAS reportedly ~22.5% rolling utilization [metal.com] = structural loss maker. Story: is domestic anti-dumping / Chinese import defense sufficient? What is HRC-scrap spread?

**Thesis KPIs:**

| metric_id | name_en / name_id | unit | category | why_it_matters | search_hints | source_priority |
|---|---|---|---|---|---|---|
| `idx:CrudeSteelCapacity` | Crude Steel Capacity / Kapasitas Baja Kasar | TON | CAPACITY | KRAS 2.45 mtpa; capacity vs 10 mtpa target [statista, metal.com]. | "Kapasitas Baja", "Steel Capacity" | AR |
| `idx:CapacityUtilization` | Capacity Utilization / Utilisasi Kapasitas | PERCENT | OPERATIONAL | KRAS ~22.5% is the crisis signal; healthy = >70%. | "Utilisasi", "Capacity Utilization" | IP |
| `idx:SalesVolumeByProduct` | Sales Volume by Product (HRC/CRC/Wire Rod/Section) | TON | VOLUME | KRAS steel sales +29% YoY to 944,562 tonnes 2025 [metal.com]. | "Volume Penjualan", "HRC", "CRC", "Wire Rod" | AR, IP |
| `idx:AverageSellingPricePerTon` | ASP per Ton / Harga Jual per Ton | USD_PER_TON | PRICING | KRAS blended ASP -30% in 2025 [metal.com]; the pain metric. | "ASP", "Harga per Ton" | IP |
| `idx:HrcScrapSpread` | HRC-Scrap Spread / Spread HRC-Scrap | USD_PER_TON | PROFITABILITY | Metal margin per ton; the true operating profit signal. | "Metal Margin", "HRC-Scrap Spread" | IP |
| `idx:BilletProduction` | Billet Production / Produksi Billet | TON | VOLUME | Upstream metric for long-product mills (GDST, ISSP). | "Produksi Billet", "Billet" | AR |
| `idx:ExportImportBalance` | Export/Import Mix / Bauran Ekspor-Impor | PERCENT | MARKET_SHARE | Chinese import share of domestic market — the competitive threat. | "Ekspor", "Impor Baja" | IP |
| `idx:ElectricityCostPerTon` | Electricity Cost per Ton (EAF) / Biaya Listrik per Ton | USD_PER_TON | EFFICIENCY | For EAF mills (GDST, ISSP); electricity = 15-20% of conversion cost. | "Biaya Listrik", "Electricity Cost" | AR |
| `idx:ScrapConsumption` | Scrap Consumption / Konsumsi Scrap | TON | OPERATIONAL | For EAF; imported scrap availability is a supply risk. | "Konsumsi Scrap", "Scrap Consumption" | AR |
| `idx:PipeApiVsCommercialMix` | Pipe Mix (API/OCTG vs Commercial) — for ISSP | PERCENT | MARKET_SHARE | API/OCTG = high-margin oil-country tubular; commercial = commodity. | "API Pipe", "OCTG", "Commercial Pipe" | AR |
| `idx:DebtToEbitda` | Net Debt / EBITDA | RATIO | RISK | KRAS restructuring left elevated leverage; the covenant metric. | "Net Debt/EBITDA", "Leverage" | AR |

**Regulatory disclosures:**
- **Permendag 20/2021 & 6/2024** — steel import safeguards, Persetujuan Impor.
- **KPPU / Kementerian Perdagangan** anti-dumping investigations vs Chinese HRC.
- **Permenperin 21/2020** on TKDN steel for government projects.

**Peer references:**
- **POSCO (KR)** — publishes crude steel production, HRC spread, and utilization by mill.
- **Tata Steel (India)** — publishes EBITDA per ton by geography; a benchmark disclosure.
- **Ternium (LATAM)** — reports "steel shipments" and "revenue per ton" quarterly.

**Sources used:**
- [SMM Metal — KRAS turnaround analysis](https://news.metal.com/newscontent/103891522-smm-steel-enterprise-feature-truth-behind-the-turnaround-the-core-business-dilemma-of-indonesian-giant-krakatau-steel)
- [Statista — Krakatau Steel production capacity](https://www.statista.com/statistics/1331131/krakatau-steel-production-capacity-by-product/)

---

## TIN_MINING (Tin Mining — TINS Timah)

**Thesis:** Single-name sector. TINS = *tin production × LME tin price × cost curve position*. Onshore vs offshore mix + IUP permit status is the swing. 2025 export-permit halt caused revenue collapse to IDR 8.9tn [tradingview]; Q1 2026 refined output +81.9% YoY [internationaltin.org].

**Thesis KPIs:**

| metric_id | name_en / name_id | unit | category | why_it_matters | search_hints | source_priority |
|---|---|---|---|---|---|---|
| `idx:TinInOreProduction` | Tin-in-Ore Production / Produksi Bijih Timah | TON | VOLUME | Upstream mining output; Q1 2026 = 6,312 mt +96.3% YoY. | "Produksi Bijih Timah", "Tin-in-Ore" | IP, AR |
| `idx:RefinedTinProduction` | Refined Tin Production / Produksi Logam Timah | TON | VOLUME | Downstream smelter output; Q1 2026 = 5,630 t +81.9% YoY. | "Logam Timah", "Refined Tin" | IP, AR |
| `idx:RefinedTinSalesVolume` | Refined Tin Sales / Penjualan Logam Timah | TON | VOLUME | Sold vs produced (inventory build/drawdown). | "Penjualan Logam Timah" | IP, AR |
| `idx:OnshoreOffshoreMix` | Onshore vs Offshore Mining Mix | PERCENT | OPERATIONAL | Offshore = higher-cost dredge; onshore = lower cost but IUP/illegal-mining friction. | "Tambang Darat", "Tambang Laut", "Onshore Offshore" | AR, IP |
| `idx:AverageSellingPricePerTonTin` | ASP Tin per Ton / Harga Jual Rata-rata Timah | USD_PER_TON | PRICING | Q1 2026 = US$49,221/t; LME-linked. | "ASP Timah", "Tin Price" | IP, AR |
| `idx:CashCostPerTon` | C1 Cash Cost per Ton / Biaya Tunai per Ton | USD_PER_TON | EFFICIENCY | Position on global cost curve — determines survival at low LME. | "C1 Cost", "Cash Cost per Ton" | IP |
| `idx:OreGradeSn` | Ore Grade (Sn %) / Kadar Bijih | PERCENT | ASSET_QUALITY | Declining grade = rising unit cost long-term; TINS grades typically 0.3-0.5% Sn. | "Kadar Sn", "Ore Grade" | AR |
| `idx:ReserveResourceLife` | Reserve Life (Years) / Umur Cadangan | YEARS | CAPACITY | JORC-based; regulatory-mandated in AMDAL. | "Umur Tambang", "Reserve Life" | AR |
| `idx:IupConcessionArea` | IUP Concession Area | HA | CAPACITY | Onshore + offshore permit area; the resource footprint. | "IUP", "Wilayah Izin Usaha Pertambangan" | AR |
| `idx:CooperativeMinerContribution` | Cooperative Miner Feed % / Kontribusi Mitra Tambang | PERCENT | OPERATIONAL | Feed from partner cooperatives — regulatory-sensitive since 2018 crackdown. | "Mitra Tambang", "Cooperative Mining" | AR |
| `idx:ExportPermitStatus` | Export Permit (Persetujuan Ekspor) Status | UNITS | REGULATORY | 2025 halt caused revenue collapse; binary switch. | "Persetujuan Ekspor", "Export Permit" | IDX, AR |

**Regulatory disclosures:**
- **UU 3/2020 (Minerba)** — mineral & coal law; IUP framework.
- **Permen ESDM 7/2020 & 25/2018** — export permit rules; RKAB annual plan.
- **PP 96/2021** — coal & mineral royalty regime; tin royalty ~3-6% of ASP.

**Peer references:**
- **Malaysia Smelting Corporation (MSC)** — publishes refined tin production, cash cost per ton, and ore grade.
- **Yunnan Tin (CN)** — largest global producer; publishes C1 costs, reserve grade movement.
- **Minsur (PE)** — publishes ore-processed tonnage, tin recovered, and mine-site all-in sustaining cost.

**Sources used:**
- [International Tin Association — TINS Q1 2026](https://www.internationaltin.org/pt-timah-q1-production-82-higher-than-in-2025/)
- [Samuel Sekuritas TINS Initiation Oct 2025](https://samuel.co.id/wp-content/uploads/2025/10/TINS_Initation-Report_171025.pdf)
- [BRIDS — TINS Oct 2025](https://link.brights.id/brids/storage/41788/20251008-TINS.pdf)

---

## CERAMIC_GLASS (Ceramic Tiles & Glass — ARNA, AMFG, MLIA, TOTO, KIAS)

**Thesis:** Ceramics = *m² output × ASP × gas-cost per m²*. Glass = *tonnage × spread over soda-ash + natural gas*. Utilization + gas subsidy (HGBT) are the critical policy variables. Indonesia is 5th globally at 625m m² capacity [ceramicworldweb], ARNA leading at 75m m² [ceramicworldweb].

**Thesis KPIs:**

| metric_id | name_en / name_id | unit | category | why_it_matters | search_hints | source_priority |
|---|---|---|---|---|---|---|
| `idx:InstalledCapacityM2` | Installed Capacity (m²/year) — Ceramics / Kapasitas m² | UNITS (M2) | CAPACITY | ARNA ~75m m²; MLIA and other players below. | "Kapasitas m2", "Installed Capacity" | AR |
| `idx:InstalledCapacityTon` | Installed Capacity (Ton) — Glass / Kapasitas Ton Kaca | TON | CAPACITY | For AMFG, MLIA float-glass lines. | "Kapasitas Kaca", "Ton Kaca" | AR |
| `idx:CapacityUtilization` | Capacity Utilization / Utilisasi | PERCENT | OPERATIONAL | Ceramic industry Q2 2025 grew 10.07% YoY [antaranews]. | "Utilisasi", "Utilization Rate" | IP |
| `idx:SalesVolumeM2` | Sales Volume (m²) / Volume Penjualan m² | UNITS (M2) | VOLUME | Domestic tile demand driven by residential completion. | "Volume Penjualan m2", "Sales Volume" | AR, IP |
| `idx:AverageSellingPricePerM2` | ASP per m² / Harga per m² | IDR | PRICING | Chinese import competition suppresses ASP. | "ASP", "Harga Rata-rata per m2" | IP |
| `idx:GasCostPerM2` | Gas Cost per m² / Biaya Gas per m² | IDR | EFFICIENCY | HGBT (US$6/MMBTU) is the cost gate; non-HGBT = ~US$10-12. | "Biaya Gas", "HGBT", "Gas Cost" | AR |
| `idx:HgbtEligibilityStatus` | HGBT Eligibility (Yes/No) | UNITS | REGULATORY | Government-set industrial gas price subsidy; binary competitive gate. | "HGBT", "Harga Gas Bumi Tertentu" | IDX, AR |
| `idx:ExportRevenueMix` | Export Mix / Bauran Ekspor | PERCENT | MARKET_SHARE | ARNA is domestic-heavy; growth story is import substitution. | "Ekspor", "Export Mix" | AR |
| `idx:ProductMixTilesSanitary` | Product Mix (Wall/Floor/Sanitary/Glass) | PERCENT | MARKET_SHARE | TOTO = sanitary premium; ARNA = mass-market floor tiles. | "Bauran Produk", "Product Mix" | AR |
| `idx:DistributionChannelMix` | Channel Mix (Modern Retail/Traditional/Project) | PERCENT | MARKET_SHARE | Project channel = property-cycle exposed; retail = consumer income exposed. | "Kanal Distribusi", "Modern Retail", "Project" | AR |
| `idx:ImportSubstitutionShare` | Import Substitution Share | PERCENT | MARKET_SHARE | % of domestic market taken from imports YoY — the anti-dumping / SNI-mandatory effect. | "Import Substitusi", "SNI Wajib" | IP |

**Regulatory disclosures:**
- **Kepmen ESDM 91.K/HK.02/MEM.M/2023 & Permen ESDM 8/2020** — HGBT (US$6/MMBTU) certain industrial gas price; ceramics is one of 7 eligible sectors.
- **Permenperin 11/2019 (Amended)** — SNI wajib for ceramic tiles.
- **Permendag 39/2023** — Persetujuan Impor ceramics.

**Peer references:**
- **Kajaria Ceramics (India), Somany** — publish capacity utilization, ASP per m², gas cost per m² transparently.
- **Guardian Glass (US), NSG (JP)** — publish tonnage produced, spread over soda-ash + fuel.
- **Mohawk Industries (US)** — global tile leader; publishes segment volume, ASP, and mix.

**Sources used:**
- [Ceramic World Web — Arwana growth](https://ceramicworldweb.com/en/news/arwana-ceramics-responsible-growth-largest-indonesian-ceramic-company)
- [Antara — Indonesia ceramic industry global top-four](https://en.antaranews.com/news/391245/indonesias-ceramic-industry-on-track-for-global-top-four-position)
- [IDNFinancials — ARNA 1H 2026 profit growth](https://www.idnfinancials.com/news/66301/produsen-keramik-arna-cetak-laba-tumbuh-8-1-di-paruh-pertama-2026)

---

## BEVERAGE_ALCOHOL (Alcoholic Beverages — MLBI, DLTA)

**Thesis:** Small, concentrated, regulation-constrained market. MLBI + DLTA = 90%+ of legal beer market. Story = *hectoliter volume × ASP × excise (cukai) exposure*. Any excise hike is a demand shock. DLTA installed capacity 1.1m HL/year [wikipedia].

**Thesis KPIs:**

| metric_id | name_en / name_id | unit | category | why_it_matters | search_hints | source_priority |
|---|---|---|---|---|---|---|
| `idx:BeerVolumeHectoliters` | Beer Sales Volume / Volume Penjualan Bir | HECTOLITERS | VOLUME | Core volume metric; excise-suppressed. | "Hektoliter", "Volume Bir", "HL" | AR, IP |
| `idx:InstalledCapacityHl` | Installed Brewing Capacity / Kapasitas Terpasang | HECTOLITERS | CAPACITY | DLTA 1.1m HL; MLBI multi-plant. | "Kapasitas Terpasang", "Brewing Capacity" | AR |
| `idx:CapacityUtilization` | Brewery Utilization / Utilisasi Pabrik | PERCENT | OPERATIONAL | Below 60% = margin pressure from fixed cost. | "Utilisasi Pabrik" | AR |
| `idx:PriceMixPremiumMainstream` | Price Mix (Premium/Mainstream) — Heineken/Bintang/Zero | PERCENT | MARKET_SHARE | Premium (Heineken 0.0) = margin-accretive mix shift. | "Bauran Premium", "Product Mix" | AR, IP |
| `idx:ChannelMixOnPremiseOff` | Channel Mix (On-Premise/Off-Premise/Modern Retail) | PERCENT | MARKET_SHARE | On-premise = high margin, tourism-linked (Bali); off-premise = supermarket. | "On-Trade", "Off-Trade", "Modern Trade" | AR, IP |
| `idx:GeographicMixBaliRest` | Geographic Mix (Bali/Java/Others) | PERCENT | MARKET_SHARE | Bali is 40%+ of national on-trade — international tourism sensitivity. | "Segmen Geografis", "Bali Mix" | AR |
| `idx:ExciseAsPctOfRevenue` | Excise as % of Revenue / Cukai per Pendapatan | PERCENT | REGULATORY | Excise = ~40-50% of retail price; hike passes through to volume. | "Cukai", "Excise Duty" | AR, FSN |
| `idx:AsePerHectoliter` | ASP per Hectoliter (ex-excise) | IDR_PER_HL | PRICING | True pricing signal net of excise. | "ASP HL", "Price per Hectoliter" | IP |
| `idx:GrossMarginPerHl` | Gross Margin per HL / Marjin Kotor per HL | IDR_PER_HL | PROFITABILITY | Barley/hops (imported, USD) and packaging cost per HL; the unit-econ metric. | "Gross Margin per HL", "GP per HL" | AR |
| `idx:MarketShareLegalBeer` | Legal Beer Market Share | PERCENT | MARKET_SHARE | MLBI ~60%, DLTA ~15%; balance = imports + micro. | "Pangsa Pasar Bir", "Beer Market Share" | IP |

**Regulatory disclosures:**
- **UU 39/2007 & PMK 158/2018** — excise (cukai) on alcohol; tariff MMEA A (0-5%), B (5-20%), C (>20%).
- **Permendag 20/2014** — alcohol distribution zone restrictions.
- **Perda daerah** — local zonation (Aceh, Papua) bans.

**Peer references:**
- **Heineken NV (parent)** — publishes volume growth, price mix, premium share, EBIT per HL by region.
- **Carlsberg Asia** — same discipline; publishes hectoliter volume and net revenue per HL by market.
- **Thai Beverage** — publishes market share, on-trade/off-trade split, ASP per case.

**Sources used:**
- [Delta Djakarta Wikipedia](https://en.wikipedia.org/wiki/Delta_Djakarta)
- [Gentala Institute — Analisa Awal Industri Bir Indonesia Aug 2025](https://gentala.institute/wp-content/uploads/2025/08/Analisa-Awal-Industri-Bir-di-Indonesia-Bahasa-Indonesia.pdf)

---

## FOOD_INGREDIENT (Food Ingredients — TBLA, BUDI, CEKA, SKBM, PSDN, DMND)

**Thesis:** Diverse subsector — sugar refining (TBLA), starch/glucose (BUDI), edible oil trading (CEKA/SKBM), dairy (DMND). Common thread: *commodity input pass-through × conversion margin × capacity utilization*. Sugar HET (Harga Eceran Tertinggi) and cane availability drive TBLA; corn/cassava for BUDI.

**Thesis KPIs:**

| metric_id | name_en / name_id | unit | category | why_it_matters | search_hints | source_priority |
|---|---|---|---|---|---|---|
| `idx:RefinedSugarProduction` | Refined Sugar Production (TBLA/GULA) / Produksi Gula Rafinasi | TON | VOLUME | Refined-sugar quota is government-set; quota = revenue ceiling. | "Gula Rafinasi", "Refined Sugar" | AR |
| `idx:CaneCrushingCapacity` | Cane Crushing Capacity (TCD) / Kapasitas Giling Tebu | TCD | CAPACITY | Tons cane per day; base metric for cane sugar mills. | "TCD", "Kapasitas Giling" | AR |
| `idx:CaneYieldPerHa` | Cane Yield per Ha / Hasil Tebu per Hektar | TON_PER_HA | ASSET_QUALITY | Own plantation productivity; Indonesian yield ~70-90 t/ha vs Thai 100+. | "Yield Tebu", "Rendemen", "Cane Yield" | AR |
| `idx:SugarRecoveryRate` | Sugar Recovery / Rendemen Gula | PERCENT | OPERATIONAL | % of sugar extracted per ton cane; a proxy for mill quality and cane maturity. | "Rendemen", "Recovery Rate" | AR |
| `idx:StarchGlucoseProduction` | Starch/Glucose Production (BUDI) | TON | VOLUME | Cassava/tapioca conversion; downstream to F&B customers. | "Tapioka", "Glucose", "Starch" | AR |
| `idx:AsePerTonProduct` | ASP per Ton (by product) | IDR_PER_TON | PRICING | Sugar HET vs industrial; edible oil vs pack size. | "ASP Ton", "Harga per Ton" | AR |
| `idx:RawMaterialCostRatio` | Raw Material Cost Ratio / Rasio COGS Bahan Baku | PERCENT | EFFICIENCY | For BUDI: cassava = 55-65% of COGS; sensitivity gauge. | "COGS Bahan Baku", "Raw Material Cost" | AR |
| `idx:ExportRevenueMix` | Export Revenue Mix | PERCENT | MARKET_SHARE | BUDI exports starch derivatives; USD hedge. | "Ekspor" | AR |
| `idx:CustomerConcentration` | Top-5 F&B Customer Concentration | PERCENT | RISK | Sales to Indofood/Mayora/GarudaFood — single-relationship risk. | "Konsentrasi Pelanggan" | AR, FSN |
| `idx:HetComplianceStatus` | HET/HAP Regulatory Status (Sugar) | UNITS | REGULATORY | Government retail price ceiling; binding for consumer sugar. | "HET", "HAP", "Harga Eceran Tertinggi" | AR |
| `idx:CookingOilQuotaShare` | Cooking Oil DMO/Quota Share | TON | REGULATORY | For CEKA/related: DMO obligation per Permendag. | "DMO", "Domestic Market Obligation" | IP |

**Regulatory disclosures:**
- **Permentan 15/2013** & Permentan 6/2020 — sugar cane and refined-sugar quotas.
- **Permendag 27/2017 & 20/2021** — sugar import allocation.
- **Permendag 6/2022** — cooking oil DMO framework.
- **Badan Pangan Nasional (Bapanas)** — HAP (Harga Acuan Pemerintah) sets floor and ceiling for key ingredients.

**Peer references:**
- **Cosan (BR)** — publishes cane crushed, TRS (sugar recovered per ton), sugar/ethanol mix.
- **Cargill / Wilmar** — publish crushing volume, refining margin, and origin split.
- **Roquette (FR)** — starch peer; publishes tonnage by product family and value-added derivative share.

**Sources used:**
- [OpenPR — Indonesian Beverage & Ingredient Q3 2025](https://www.openpr.com/news/4348459/top-30-indonesian-beverages-public-companies-q3-2025-revenue)

---

## PACKAGING (Packaging — AKPI, IGAR, IPOL, TRST, TALF, KDSI, BRNA)

**Thesis:** Converter economics — *resin cost pass-through × conversion margin × utilization*. IGAR (pharma packaging) has stickier customers than AKPI (BOPP films) which competes on commodity spread. Domestic upstream utilization <55% early 2024 [mordorintelligence].

**Thesis KPIs:**

| metric_id | name_en / name_id | unit | category | why_it_matters | search_hints | source_priority |
|---|---|---|---|---|---|---|
| `idx:ConversionCapacityTon` | Conversion Capacity (Ton/year) / Kapasitas Konversi | TON | CAPACITY | Base metric for flexible/rigid packaging. | "Kapasitas Konversi", "Conversion Capacity" | AR |
| `idx:CapacityUtilization` | Utilization / Utilisasi | PERCENT | OPERATIONAL | Above 80% = pricing power; below 70% = margin destruction. | "Utilisasi" | IP |
| `idx:ProductMixFlexibleRigid` | Product Mix (Flexible/Rigid/BOPP/Preform) | PERCENT | MARKET_SHARE | Pharma-grade rigid (IGAR) commands premium vs commodity BOPP. | "Bauran Produk", "Product Mix" | AR |
| `idx:EndMarketMixFoodBevPharma` | End-Market Mix (Food/Beverage/Pharma/Industrial) | PERCENT | MARKET_SHARE | Pharma & consumer = defensive; industrial = cyclical. | "Segmen Pasar", "End Market" | AR |
| `idx:ResinPassThroughLag` | Resin Pass-Through Lag / Lag Pass-Through | MONTHS | RISK | Typically 1-3 months; short lag = margin stability. | "Pass-through", "Kontrak Formula" | IP |
| `idx:AsePerTonConverted` | ASP per Ton / Harga per Ton Konversi | IDR_PER_TON | PRICING | Blended converter yield. | "ASP", "Harga per Ton" | AR |
| `idx:ConversionMarginPerTon` | Conversion Margin per Ton / Marjin Konversi | IDR_PER_TON | PROFITABILITY | (ASP − Resin) = the true operating spread. | "Conversion Margin" | IP |
| `idx:ResinInputMix` | Resin Input Mix (PP/PE/PET) | PERCENT | RISK | Different feedstock cycles; PET = MEG/PTA-linked. | "Bauran Bahan Baku", "PP", "PE", "PET" | AR |
| `idx:ExportRevenueMix` | Export Revenue Mix | PERCENT | MARKET_SHARE | AKPI/TRST have USD-revenue mix — FX-positive. | "Ekspor" | AR |
| `idx:RecycledContentRatio` | Recycled Content (%) / Kandungan Daur Ulang | PERCENT | ESG | EPR (Extended Producer Responsibility) drives brand-owner mandate. | "Daur Ulang", "Recycled Content", "EPR" | AR |
| `idx:TopBrandCustomerConcentration` | Top-5 Brand Customer Concentration | PERCENT | RISK | Unilever/Indofood/Nestle mono-dependence risk. | "Konsentrasi Pelanggan" | AR, FSN |

**Regulatory disclosures:**
- **PP 27/2020 & PermenLHK 75/2019** — EPR (Extended Producer Responsibility) for packaging.
- **BPOM regulations** — food-contact & pharmaceutical packaging standards.
- **Permenperin 11/2019** — SNI for pharma packaging.

**Peer references:**
- **Amcor (AU/US)** — publishes volume, price-mix, and conversion margin per segment.
- **Berry Global (US)** — reports "organic volume", "pricing", and "raw material pass-through" separately.
- **Uflex (India)** — flexible packaging peer; publishes capacity utilization, resin cost as % of COGS.

**Sources used:**
- [Mordor — Indonesia Rigid Plastic Packaging Market](https://www.mordorintelligence.com/industry-reports/indonesia-rigid-plastic-packaging-market)
- [OpenPR — Indonesian Plastic Bottle Q3 2025](https://www.openpr.com/news/4469463/top-30-indonesian-plastic-bottle-public-companies-q3-2025)

---

## CHEMICALS (Basic Chemicals — SRSN, EKAD, INCI, DPNS, ETWA)

**Thesis:** Specialty & commodity chemical converters. SRSN (ethanol/acetic acid), EKAD (adhesive tape base), INCI (formaldehyde), DPNS (adhesives). Story = *specialty vs commodity mix × input cost hedge × downstream industrial demand*.

**Thesis KPIs:**

| metric_id | name_en / name_id | unit | category | why_it_matters | search_hints | source_priority |
|---|---|---|---|---|---|---|
| `idx:PlantCapacityByProduct` | Plant Capacity by Product / Kapasitas Pabrik per Produk | TON | CAPACITY | Ethanol vs acetic vs specialty split. | "Kapasitas per Produk", "Plant Capacity" | AR |
| `idx:CapacityUtilization` | Utilization | PERCENT | OPERATIONAL | Below 70% = fixed cost drag. | "Utilisasi" | AR |
| `idx:SpecialtyCommodityMix` | Specialty vs Commodity Revenue Mix | PERCENT | MARKET_SHARE | Specialty = 25%+ margin, commodity = 5-10%. | "Bauran Spesialti", "Specialty Mix" | AR, IP |
| `idx:EndMarketMix` | End-Market Mix (Textile/F&B/Construction/Auto) | PERCENT | MARKET_SHARE | Textile finishing chemicals (SRSN) vs adhesives (EKAD/DPNS). | "Segmen Pasar", "End Market" | AR |
| `idx:FeedstockCostRatio` | Feedstock Cost Ratio | PERCENT | EFFICIENCY | Molasses (SRSN ethanol), methanol (INCI), etc. | "Bahan Baku", "Feedstock Cost" | AR |
| `idx:AsePerTon` | ASP per Ton | IDR_PER_TON | PRICING | Weighted by product family. | "ASP" | AR |
| `idx:ExportRevenueMix` | Export Revenue Mix | PERCENT | MARKET_SHARE | Regional export exposure. | "Ekspor" | AR |
| `idx:ImportSubstitutionShare` | Import Substitution Share | PERCENT | MARKET_SHARE | Domestic replacement of imported chemicals (safeguard-tariff-supported). | "Substitusi Impor" | IP |
| `idx:EnvironmentalComplianceCapex` | ESG/Env Compliance Capex | IDR | ESG | Effluent treatment; PROPER rating exposure. | "PROPER", "Env Capex", "Wastewater" | AR |
| `idx:BpomCosmeticFoodCertMix` | BPOM Cert Coverage (food/cosmetic grade) | PERCENT | REGULATORY | Higher grade = higher ASP but capex-heavy. | "Sertifikasi BPOM", "Food Grade" | AR |

**Regulatory disclosures:**
- **UU 32/2009** on Environmental Protection; PROPER rating public.
- **BPOM & Permen LHK** on hazardous chemicals (B3).
- **Permendag 84/2022** on chemical imports.

**Peer references:**
- **Aditya Birla Chemicals (IN), Deepak Nitrite (IN)** — publish product-family volumes, ASP, and capacity utilization.
- **BASF, Evonik** — segment-level EBITDA per ton by product family.

**Sources used:**
- [OpenPR — Indonesian Petrochemical Q3 2025](https://www.openpr.com/news/4534031/top-30-indonesian-petrochemical-public-companies-q3-2025)

---

## INDUSTRIAL_GAS (Industrial Gas — AGII Samator)

**Thesis:** Duopoly-ish market (AGII + Air Liquide + Linde). Story = *on-site (tonnage) contract mix × merchant + package mix × plant utilization*. On-site is 15-20 year take-or-pay = utility-like. AGII operates 44 plants across 26 provinces [samatorgas.com]; market USD 7.67bn 2025 [expertmarketresearch].

**Thesis KPIs:**

| metric_id | name_en / name_id | unit | category | why_it_matters | search_hints | source_priority |
|---|---|---|---|---|---|---|
| `idx:AsuCapacityTpd` | ASU Capacity (Tons per Day) / Kapasitas Air Separation | TON_PER_DAY | CAPACITY | Air Separation Unit capacity — the primary asset. | "ASU", "Air Separation Unit", "Kapasitas TPD" | AR |
| `idx:OnSiteRevenueMix` | On-Site Revenue % / Bauran Pendapatan On-Site | PERCENT | MARKET_SHARE | On-site = take-or-pay = utility-margin. | "On-site", "Take-or-Pay" | AR, IP |
| `idx:MerchantPackagedRevenueMix` | Merchant + Packaged Revenue % | PERCENT | MARKET_SHARE | Merchant (liquid bulk) + cylinder retail; margin bimodal. | "Merchant Gas", "Packaged Gas", "Cylinder" | AR |
| `idx:VolumeByGasType` | Volume by Gas Type (O2/N2/Ar/CO2/H2/Med) | TON | VOLUME | Product mix; medical O2 spiked 2020-22 then normalized. | "Oksigen", "Nitrogen", "Argon", "CO2", "Medical Gas" | AR, IP |
| `idx:PlantUtilization` | Plant Utilization | PERCENT | OPERATIONAL | On-site utilization = take-or-pay contract enforcement. | "Utilisasi Pabrik" | AR |
| `idx:AverageContractDuration` | Avg On-Site Contract Duration / Rata-rata Kontrak On-Site | YEARS | RISK | 10-20 years typical; longer = better cash-flow visibility. | "Tenor Kontrak On-site" | AR, IP |
| `idx:EndMarketMix` | End-Market Mix (Steel/Petchem/Health/Food/Electronics) | PERCENT | MARKET_SHARE | Steel (KRAS/nickel smelters) is dominant; electronics = emerging. | "Segmen Pengguna", "End Market Mix" | AR |
| `idx:HydrogenCapacity` | Hydrogen Capacity | TON_PER_DAY | CAPACITY | Refinery hydrogen for Pertamina; energy-transition growth optionality. | "Hidrogen", "Hydrogen Capacity" | IP |
| `idx:ElectricityCostPerNm3` | Electricity Cost per Nm³ | IDR_PER_NM3 | EFFICIENCY | Electricity is 50-60% of ASU opex. | "Biaya Listrik", "Electricity per Nm3" | AR |
| `idx:GeographicFootprintProvinces` | Provinces Served / Cakupan Provinsi | UNITS | CAPACITY | AGII: 26 provinces — distribution moat. | "Cakupan Provinsi", "Distribution Network" | AR |

**Regulatory disclosures:**
- **Permen ESDM 8/2020 & Kepmen ESDM 91/2023** — HGBT eligibility (AGII eligible via industrial-gas classification for some sites).
- **BPOM** — medical gas grade certification.
- **Permenperin** — TKDN for industrial gas equipment.

**Peer references:**
- **Air Liquide (FR), Linde (DE), Air Products (US)** — publish on-site backlog, sale of gas vs sale of equipment, revenue per end-market.
- **Nippon Sanso (JP)** — publishes plant count, on-site vs merchant mix, packaged mix.

**Sources used:**
- [Samator Gas company site](https://samatorgas.com/)
- [Expert Market Research — Indonesia industrial gas](https://www.expertmarketresearch.com/reports/indonesia-industrial-gases-market)
- [Air Liquide Indonesia](https://id.airliquide.com/product-services/gases/industrial-gas)

---

## WATER_UTILITY (Private Water — PDES, TIRT-adjacent)

**Thesis:** Concession-based regulated utility. Story = *volume billed × tariff × NRW (non-revenue water) × collection efficiency*. Municipal/PDAM offtake concentration is a single-counterparty risk.

**Thesis KPIs:**

| metric_id | name_en / name_id | unit | category | why_it_matters | search_hints | source_priority |
|---|---|---|---|---|---|---|
| `idx:InstalledTreatmentCapacityM3S` | Treatment Capacity (m³/second) | UNITS (M3_S) | CAPACITY | Base water production capacity. | "Kapasitas Produksi", "m3/detik" | AR |
| `idx:WaterVolumeSoldM3` | Water Sold (m³) / Volume Air Terjual | UNITS (M3) | VOLUME | Metered billed volume. | "Volume Terjual", "Water Sold" | AR |
| `idx:BulkTariffPerM3` | Bulk Tariff per m³ / Tarif Air Curah | IDR_PER_M3 | PRICING | Concession-set; annual/multi-year adjustment formula. | "Tarif Air", "Bulk Tariff" | AR |
| `idx:NonRevenueWaterRatio` | Non-Revenue Water (NRW) | PERCENT | EFFICIENCY | Leakage + theft; PDAM average >30%, benchmarking gap. | "NRW", "Air Tak Berpenghasilan" | AR, IP |
| `idx:CollectionEfficiency` | Collection Efficiency / Efisiensi Penagihan | PERCENT | OPERATIONAL | Cash collected / billed. | "Efisiensi Penagihan" | AR |
| `idx:ConnectionCount` | Active Connections / Jumlah Sambungan | UNITS | CAPACITY | Retail customer base metric. | "Sambungan", "Connections" | AR |
| `idx:ConcessionRemainingYears` | Concession Remaining Life / Sisa Konsesi | YEARS | CAPACITY | BOT/BOO tenure remaining. | "Sisa Konsesi", "Concession Life" | AR |
| `idx:OfftakerConcentration` | PDAM/Municipal Offtaker Concentration | PERCENT | RISK | Single-buyer risk (usually >80%). | "Konsentrasi Pelanggan", "Offtaker" | AR, FSN |
| `idx:EnergyCostPerM3` | Energy Cost per m³ | IDR_PER_M3 | EFFICIENCY | Pumping-heavy operation; PLN tariff sensitivity. | "Biaya Listrik per m3" | AR |
| `idx:CapexToRevenueRatio` | Capex / Revenue | PERCENT | CAPACITY | Network expansion intensity. | "Capex" | AR |

**Regulatory disclosures:**
- **UU 17/2019** on Water Resources.
- **PP 122/2015 & Permen PUPR 25/2016** on SPAM (drinking water) tariff.
- **PP 121/2015** on private-sector water concessions.

**Peer references:**
- **Manila Water (PH), Maynilad (PH)** — publish NRW %, connections, tariff track, capex per new connection.
- **China Water Affairs (HK)** — publishes water sold, tariff, connection count by city.
- **SembCorp Utilities (SG)** — publishes capacity utilization for water treatment.

**Sources used:** general water-utility literature; company-specific IDX disclosures limited.

---

## FOOTWEAR (Footwear — BATA, KBLM-adjacent)

**Thesis:** Retail + light manufacturing. Story = *store count × SSSG × ASP × store productivity*. BATA has been in structural decline (SSSG negative) vs Q3 2025 footwear industry recovery [openpr Indonesian footwear].

**Thesis KPIs:**

| metric_id | name_en / name_id | unit | category | why_it_matters | search_hints | source_priority |
|---|---|---|---|---|---|---|
| `idx:StoreCount` | Store Count / Jumlah Gerai | UNITS | CAPACITY | Retail footprint. | "Jumlah Gerai", "Store Count" | AR |
| `idx:SameStoreSalesGrowth` | SSSG / Pertumbuhan Toko Sama | PERCENT | GROWTH | Ex-new-store growth; the true retail health metric. | "SSSG", "Same Store Sales" | IP, PE |
| `idx:SalesPerStorePerMonth` | Sales Density per Store | IDR | EFFICIENCY | Store productivity. | "Sales per Store", "Produktivitas Gerai" | IP |
| `idx:PairsSoldVolume` | Pairs Sold / Volume Pasang | UNITS (PAIRS) | VOLUME | Unit sales volume. | "Volume Penjualan", "Pairs Sold" | AR, IP |
| `idx:AverageSellingPricePerPair` | ASP per Pair / Harga per Pasang | IDR | PRICING | Product mix ASP. | "ASP per Pair" | IP |
| `idx:ProductMixCasualSportSchool` | Product Mix (Casual/Sport/School/Safety) | PERCENT | MARKET_SHARE | School shoes = high-seasonality; safety = B2B recurring. | "Bauran Produk" | AR |
| `idx:ChannelMixOwnFranchiseWholesale` | Channel Mix (Own/Franchise/Wholesale/Online) | PERCENT | MARKET_SHARE | Own = full margin; wholesale = volume, thin margin. | "Bauran Kanal", "Channel Mix" | AR |
| `idx:OnlineRevenueMix` | Online Revenue % | PERCENT | GROWTH | E-commerce migration; Tokopedia/Shopee dependency. | "Online Sales", "E-commerce" | AR, IP |
| `idx:InventoryDaysOnHand` | Inventory Days / Hari Persediaan | DAYS | EFFICIENCY | Fashion obsolescence risk; >180 days = markdown coming. | "Days Inventory" | AR |
| `idx:GrossMargin` | Gross Margin | PERCENT | PROFITABILITY | Sourcing (China/Vietnam) vs sell-through; the retail-health metric. | "Gross Margin", "Marjin Kotor" | AR |

**Regulatory disclosures:**
- **UU Cipta Kerja 2020 (labor)** and UMP annual wage.
- **Permendag 8/2024** on footwear imports (anti-dumping enforcement).

**Peer references:**
- **Nike, Adidas** — publish DTC vs Wholesale split, digital revenue, ASP per pair by category.
- **Belle International (HK)** — publishes SSSG, store count, ASP by brand.
- **Bata (parent, CH)** — publishes retail productivity, store openings, closures.

**Sources used:**
- [OpenPR — Indonesian Footwear Q3 2025](https://www.openpr.com/news/4495550/top-30-indonesian-footwear-public-companies-q3-2025-revenue)

---

## PLASTICS_HOUSEWARE (Plastics & Houseware — APLI, CINT, IMPC, LTLS, LPIN, LMPI)

**Thesis:** Consumer-durable plastics — piping (IMPC), houseware (CINT), industrial trading (LTLS). Story = *tonnage × resin pass-through × brand-premium capture in retail*.

**Thesis KPIs:**

| metric_id | name_en / name_id | unit | category | why_it_matters | search_hints | source_priority |
|---|---|---|---|---|---|---|
| `idx:ProductionCapacityTon` | Production Capacity (Ton) | TON | CAPACITY | Base metric. | "Kapasitas Produksi" | AR |
| `idx:CapacityUtilization` | Utilization | PERCENT | OPERATIONAL | | "Utilisasi" | AR |
| `idx:SegmentMixPipeHousewareIndustrial` | Segment Mix (Pipe/Houseware/Industrial) | PERCENT | MARKET_SHARE | Pipe = infrastructure-cycle; houseware = consumer; industrial = B2B. | "Bauran Segmen" | AR |
| `idx:AsePerTonOrUnit` | ASP per Ton (Pipe) / per Unit (Houseware) | IDR | PRICING | Blended pricing. | "ASP" | AR |
| `idx:BrandPremiumRatio` | Branded vs Private-Label Revenue | PERCENT | MARKET_SHARE | Rucika (IMPC) has premium; unbranded competes on price only. | "Bauran Merek", "Branded Sales" | AR |
| `idx:ResinPassThroughLag` | Resin Pass-Through Lag | MONTHS | RISK | 1-3 months typical. | "Pass-Through" | IP |
| `idx:ChannelMixModernTradeTraditional` | Channel (Modern Trade/Traditional/Project) | PERCENT | MARKET_SHARE | Project (pipe → contractors) = lumpy; modern-trade = recurring. | "Kanal Distribusi" | AR |
| `idx:ExportRevenueMix` | Export Mix | PERCENT | MARKET_SHARE | | "Ekspor" | AR |
| `idx:TradingVsManufacturingRevenue` | Trading vs Manufacturing (LTLS) | PERCENT | MARKET_SHARE | LTLS is largely distributor; margin structure differs vs manufacturer. | "Trading Revenue", "Distribusi" | AR |
| `idx:InventoryDaysOnHand` | Inventory Days | DAYS | EFFICIENCY | Resin price volatility risk. | "Days Inventory" | AR |

**Regulatory disclosures:**
- **SNI wajib** for PVC pipe and water-carrying products.
- **EPR** framework for single-use plastic (LHK PP 27/2020).

**Peer references:**
- **Supreme Industries (IN)** — publishes tonnage, value-mix, capacity utilization by product line.
- **Astral Poly (IN)** — publishes volume growth, ASP, and segment EBITDA/kg.

**Sources used:** general packaging/plastics literature referenced in PACKAGING section above.

---

## JEWELRY_LUXURY (Jewelry — HRTA Hartadinata, KING)

**Thesis:** Gold jewelry = *tonnes sold × gold price × making-margin*. HRTA: pure-gold volume +29.61% YoY to 14.79t in 9M25, market share 28.5% in bullion FY23 [icmssfebui, brights.id]. Bullion vs jewelry mix is the margin swing.

**Thesis KPIs:**

| metric_id | name_en / name_id | unit | category | why_it_matters | search_hints | source_priority |
|---|---|---|---|---|---|---|
| `idx:PureGoldVolumeTonnes` | Pure Gold Volume Sold / Volume Emas Murni Terjual | TON | VOLUME | 14.79t in 9M25 for HRTA — headline growth metric. | "Volume Emas", "Pure Gold Tonnes" | IP, AR |
| `idx:BullionJewelryMix` | Bullion vs Jewelry Mix / Bauran Bullion-Perhiasan | PERCENT | MARKET_SHARE | Bullion = ~1-3% margin, high volume; jewelry = 8-15% margin. | "Bauran Bullion", "Jewelry Mix" | IP |
| `idx:AverageGoldContentPerPiece` | Avg Gold Content per Piece (Grams) | GRAMS | PRICING | Karat + design; heavier pieces = margin-accretive. | "Gram per Piece", "Karat" | AR |
| `idx:MakingChargePerGram` | Making Charge per Gram / Ongkos per Gram | IDR_PER_GRAM | PRICING | The value-added spread over gold spot; the true jewelry alpha. | "Ongkos Bikin", "Making Charge" | IP |
| `idx:MarketShareGoldRetail` | Gold Retail Market Share | PERCENT | MARKET_SHARE | HRTA 18.5% FY23; scaling. | "Pangsa Pasar Emas", "Market Share" | IP |
| `idx:StoreCountAndPartnerRetailers` | Store/Partner Retailer Count | UNITS | CAPACITY | Direct + partner retailer network. | "Jumlah Toko", "Mitra Retailer" | AR |
| `idx:InventoryTurnover` | Inventory Turnover / Perputaran Persediaan | UNITS_PER_YEAR | EFFICIENCY | Gold inventory = working-capital hungry; turns >6x = efficient. | "Inventory Turnover", "Perputaran Persediaan" | AR |
| `idx:GoldHedgeRatio` | Gold Hedge Ratio | PERCENT | RISK | % of inventory hedged via futures/leasing; leaves directional gold exposure. | "Hedge Ratio", "Lindung Nilai Emas" | AR, FSN |
| `idx:EmaskuSubscriberCount` | EMASKU Digital Gold Users (HRTA) | UNITS | GROWTH | Digital gold-savings scheme; a fintech-adjacent moat. | "EMASKU", "Digital Gold" | IP |
| `idx:GrossMarginBlended` | Blended Gross Margin | PERCENT | PROFITABILITY | Compressed as bullion mix rises. | "Gross Margin" | AR |

**Regulatory disclosures:**
- **PPN emas batangan 0%** (Permenkeu 30/PMK.03/2014) — bullion VAT exempt.
- **Bank Indonesia** rules on digital-gold platform partnerships.
- **OJK ITSK sandbox** for digital-gold savings apps.

**Peer references:**
- **Titan Company (India, Tanishq)** — publishes pure-gold tonnes, studded-ratio, making-charge as % of ticket.
- **Chow Tai Fook (HK)** — publishes store count, SSSG for gold vs jewelry separately.
- **PC Jeweller (IN)** — publishes hedge ratio, inventory in tonnes.

**Sources used:**
- [BRIDS — HRTA Rp2740 initiation](https://www.brights.id/en/research-and-news/research-report/hartadinata-abadi-hrtaij-rp2740-buy-tp-rp3300-riding-the-gold-bullion-upcycle-resuming-coverage-with-buy-rating-and-tp-of-rp3300)
- [ICMSS FEB UI — HRTA 9M25](https://www.icmssfebui.com/post/tgif-25-53)
- [IDNFinancials — HRTA 40% profit target](https://www.idnfinancials.com/news/64367/hrta-maintains-40-profit-growth-target-despite-gold-price-pullback)

---

## FOOD_RESTAURANT (QSR & Casual Dining — PZZA, FAST, ENAK, FORE, MAPB)

**Thesis:** Restaurant = *store count × SSSG × store-level EBITDA margin × new-store payback*. Universal QSR framework. Indonesia QSR market projected 8.5% CAGR 2026-2032 [6wresearch].

**Thesis KPIs:**

| metric_id | name_en / name_id | unit | category | why_it_matters | search_hints | source_priority |
|---|---|---|---|---|---|---|
| `idx:StoreCount` | Store Count (Total) / Jumlah Gerai | UNITS | CAPACITY | Footprint. | "Jumlah Gerai" | AR, IP |
| `idx:NetNewStoreOpenings` | Net New Store Openings / Bukaan Bersih Gerai | UNITS | GROWTH | Openings − closures; slowing new-store = late-cycle signal. | "Bukaan Baru", "Net New Stores" | IP |
| `idx:SameStoreSalesGrowth` | SSSG | PERCENT | GROWTH | The alpha metric. | "SSSG", "Same Store Sales Growth" | IP, PE |
| `idx:AverageDailyRevenuePerStore` | Avg Daily Revenue per Store / Rata-rata Harian per Gerai | IDR | EFFICIENCY | Store productivity. | "Sales per Store", "Daily Sales" | IP |
| `idx:AverageCheckSize` | Avg Check Size / Rata-rata Bon | IDR | PRICING | Basket size × transaction mix. | "Average Check", "Ticket Size" | IP |
| `idx:TransactionCountPerStore` | Transactions per Store per Day / Transaksi per Gerai | UNITS | VOLUME | Traffic — the demand signal. | "Transaksi", "Transaction Count" | IP |
| `idx:DeliveryRevenueMix` | Delivery Revenue % (GoFood/GrabFood/ShopeeFood) | PERCENT | MARKET_SHARE | Delivery is dilutive to margin (aggregator fees 20%+) but expands basket. | "Delivery Mix", "GoFood" | IP, AR |
| `idx:StoreLevelEbitdaMargin` | Store-Level EBITDA Margin / Marjin Gerai | PERCENT | PROFITABILITY | Pre-corporate-overhead unit economics. | "Store-Level Margin", "Restaurant EBITDA" | IP |
| `idx:CogsAsPercentOfSales` | COGS % (Food Cost) / Rasio COGS | PERCENT | EFFICIENCY | 30-35% typical; commodity input pass-through discipline. | "Food Cost", "COGS Ratio" | AR |
| `idx:LaborCostPercentOfSales` | Labor Cost % | PERCENT | EFFICIENCY | UMP-linked; 20-25% typical. | "Labor Cost", "Biaya TK" | AR |
| `idx:NewStorePaybackPeriod` | New-Store Payback (Months) | MONTHS | EFFICIENCY | Discipline metric for greenfield expansion; <36 months = good. | "Payback Period", "Gerai Baru" | IP |
| `idx:FormatMixDineInDeliveryTakeaway` | Format Mix (Dine-In/Delivery/Takeaway/Kiosk) | PERCENT | MARKET_SHARE | Post-COVID delivery is 30-40% for QSR. | "Dine-In", "Take Away" | IP |

**Regulatory disclosures:**
- **BPOM & MUI Halal** certification — mandatory food service.
- **UU Cipta Kerja 2020** — labor; UMP.
- **PP 15/2018** — restaurant hygiene (Laik Higiene Sanitasi).

**Peer references:**
- **McDonald's, Yum Brands** — publish SSSG, ticket & traffic split, delivery % of sales, store-level margin.
- **Jubilant FoodWorks (IN — Domino's franchisee)** — publishes SSSG, LFL EBITDA margin, digital ordering share.
- **Jollibee (PH)** — publishes system-wide sales, franchise vs owned split, SSSG by geography.

**Sources used:**
- [6WResearch — Indonesia QSR market](https://www.6wresearch.com/industry-report/indonesia-quick-service-restaurants-and-fast-food-market)
- [Databoks — Kopi Kenangan store count](https://databoks.katadata.co.id/en/consumer-durables-apparel/statistics/67c94dd680d73/the-number-of-kopi-kenangan-outlets-surpasses-starbucks-in-indonesia)

---

## INVESTMENT_HOLDING (Diversified Holdings — SRTG, MPMX, BHIT, BMTR, BCAP, MLPL)

**Thesis:** Holdcos = *NAV per share × discount to NAV × dividend inflow from portfolio*. Story is (a) NAV growth from underlying, (b) narrowing / widening discount, (c) capital recycling activity. SRTG NAV IDR 53.99tn in 1H 2025 [saratoga-investama].

**Thesis KPIs:**

| metric_id | name_en / name_id | unit | category | why_it_matters | search_hints | source_priority |
|---|---|---|---|---|---|---|
| `idx:NetAssetValue` | NAV (Net Asset Value) / Nilai Aktiva Bersih | IDR | PROFITABILITY | Portfolio marked-to-market; the fundamental value anchor. | "NAV", "Nilai Aktiva Bersih", "Portfolio Value" | IP, PE |
| `idx:NavPerShare` | NAV per Share / NAV per Saham | IDR | PROFITABILITY | The per-share comparable to share price. | "NAV per Saham" | IP |
| `idx:DiscountToNav` | Discount / Premium to NAV | PERCENT | MARKET_SHARE | Persistent discount = market's view on capital-allocation quality. | "Discount to NAV", "Diskon NAV" | IP |
| `idx:PortfolioMixByAssetClass` | Portfolio Mix (Listed/Unlisted/Cash) | PERCENT | MARKET_SHARE | Listed = liquid, mark-to-market; unlisted = judgment-based. | "Portfolio Mix", "Listed vs Unlisted" | IP |
| `idx:PortfolioMixByIndustry` | Portfolio Mix by Industry / Bauran Sektor | PERCENT | MARKET_SHARE | Natural resources vs consumer vs digital — thesis signal. | "Bauran Sektor", "Industry Split" | IP |
| `idx:DividendIncomeReceived` | Dividend Income Received / Dividen Diterima | IDR | PROFITABILITY | The recurring cash flow; SRTG IDR 1.26tn 1H 2025 (ADRO/MPMX/TBIG). | "Dividen Diterima", "Dividend Income" | AR, IP |
| `idx:CapitalDeployedToInvestments` | Capital Deployed (Follow-On + New) / Modal Ditanamkan | IDR | GROWTH | New-investment pace = compounding potential. | "Investasi Baru", "Capital Deployed" | IP |
| `idx:CapitalRealizedExits` | Capital Realized (Exits) / Realisasi Divestasi | IDR | GROWTH | Exit velocity = liquidity + track-record. | "Divestasi", "Exit", "Realized Gain" | IP |
| `idx:HoldcoDebtVsAssets` | Holdco Net Debt / NAV | PERCENT | RISK | Structural leverage at holdco level; <20% = conservative. | "Net Debt to NAV", "Holdco Leverage" | AR |
| `idx:LookThroughEbitda` | Look-Through EBITDA / EBITDA Konsolidasi Portofolio | IDR | PROFITABILITY | Proportionate share of portfolio EBITDA — the "economic earnings". | "Look-Through", "Proportionate EBITDA" | IP |
| `idx:Top3HoldingConcentration` | Top-3 Portfolio Holding % | PERCENT | RISK | Concentration = alpha or single-name risk. | "Top Holdings", "Konsentrasi Portofolio" | IP |
| `idx:CashHoldingsIdrUsdMix` | Cash Holdings & IDR/USD Mix | IDR | OPERATIONAL | Dry powder + FX position. | "Kas & Setara Kas" | AR |

**Regulatory disclosures:**
- **UUPT & POJK 15/2020** — related-party transactions (RPT) disclosure critical for holdcos.
- **POJK 42/2020** — material transaction (Transaksi Material) & change-of-business rules; holdcos frequently trigger.

**Peer references:**
- **Berkshire Hathaway** — publishes look-through earnings; the gold-standard concept.
- **Jardine Matheson (HK)** — publishes NAV, discount, top-10 holdings, look-through EBITDA.
- **Investor AB (SE)** — publishes NAV per share, discount, capital deployed/realized.
- **First Pacific (HK)** — regional peer; publishes attributable NAV by holding.

**Sources used:**
- [Saratoga NAV 1H 2025 press release](https://saratoga-investama.com/press-release/portfolio-companies-deliver-solid-growth-saratogas-nav-reaches-idr53-qC32PwfNZBw1)
- [Samuel Sekuritas — SRTG 1Q25 Result May 2025](https://samuel.co.id/wp-content/uploads/2025/05/SRTG-1Q25-Result-21052025.pdf)

---

## PROPERTY_REIT (DIRE — Dana Investasi Real Estate)

**Thesis:** REITs = *stable rental yield × occupancy × NAV per unit*. Not fully separable from PROPERTY on IDX — only a handful of DIRE (e.g. DIRE Bowsprit, DIRE Ciptadana). Story = property yield + distribution stability, unlike developers whose story is presales.

**Thesis KPIs:**

| metric_id | name_en / name_id | unit | category | why_it_matters | search_hints | source_priority |
|---|---|---|---|---|---|---|
| `idx:GrossPropertyYield` | Gross Property Yield / Yield Kotor Properti | PERCENT | PROFITABILITY | Gross rental / property value. | "Gross Yield", "Yield Properti" | AR |
| `idx:NetPropertyYield` | Net Property Yield (NPI/Value) | PERCENT | PROFITABILITY | After property operating expenses. | "Net Property Income", "NPI" | AR |
| `idx:OccupancyRate` | Occupancy Rate / Tingkat Hunian | PERCENT | OPERATIONAL | Portfolio-weighted occupancy. | "Tingkat Hunian" | AR |
| `idx:WaultWeightedLeaseExpiry` | WALE (Weighted Avg Lease Expiry) | YEARS | RISK | Cash-flow visibility; >5 years = defensive. | "WALE", "Weighted Average Lease" | AR |
| `idx:RentalReversion` | Rental Reversion / Reversi Sewa | PERCENT | PRICING | Renewal rate change; positive = pricing power. | "Rental Reversion", "Reversi Sewa" | IP |
| `idx:DistributionPerUnit` | DPU (Distribution per Unit) | IDR | PROFITABILITY | REIT payout metric — the yield-investor metric. | "DPU", "Distribusi per Unit" | AR |
| `idx:NavPerUnit` | NAV per Unit | IDR | PROFITABILITY | Fair-value based book value. | "NAV per Unit" | AR |
| `idx:AssetsUnderManagement` | Total AUM / Aset Kelolaan | IDR | CAPACITY | Portfolio size. | "AUM", "Aset Kelolaan" | AR |
| `idx:GearingRatio` | Gearing Ratio (Debt/AUM) | PERCENT | RISK | Local rule caps ~35-45%; SGX REITs 50% cap. | "Gearing", "Loan-to-Value" | AR |
| `idx:AssetMixByType` | Asset Mix (Office/Retail/Industrial/Hospitality) | PERCENT | MARKET_SHARE | Sub-sector allocation drives yield & cyclicality. | "Bauran Aset", "Asset Type" | AR |

**Regulatory disclosures:**
- **POJK 19/2016** on DIRE (KIK DIRE).
- **POJK 30/2016** — SPC and DIRE ownership.
- **PP 34/2017 & PMK 200/PMK.03/2015** — pass-through tax treatment.

**Peer references:**
- **CapitaLand REITs (SG)** — publish WALE, rental reversion, NPI margin, DPU coverage.
- **Link REIT (HK)** — publishes NPI yield, occupancy, tenant mix, rental reversion by property.

**Sources used:** general REIT literature; IDX DIRE disclosures limited given small market.

---

## HEAVY_EQUIP_MINING_SERVICES (Mining Contractors — PTRO, DEWA, BUKK, MYOH, SIMS)

**Thesis:** Coal-adjacent but *cost-plus service margin*, not commodity-price exposed. Story = *overburden removed × coal produced × strip ratio × equipment utilization × contract book*. Split from COAL because economics are contractor-margin, not miner-royalty. DEWA IDR 22tn Sebuku Sejaka contract, PTRO IDR 4tn recent contract, Singaraja Putra 234.9m BCM OB / 26m t coal [idnfinancials, indonesiabusinesspost].

**Thesis KPIs:**

| metric_id | name_en / name_id | unit | category | why_it_matters | search_hints | source_priority |
|---|---|---|---|---|---|---|
| `idx:OverburdenRemoved` | Overburden Removed (BCM) / Pengupasan Tanah | UNITS (BCM) | VOLUME | The volume-based revenue driver. | "Overburden", "BCM", "Pengupasan" | AR, IP |
| `idx:CoalProduced` | Coal Produced (Ton) / Batu Bara Diproduksi | TON | VOLUME | Companion volume metric. | "Coal Getting", "Produksi Batubara" | AR, IP |
| `idx:StrippingRatio` | Stripping Ratio (BCM/ton) | RATIO | OPERATIONAL | Client-set; higher = more work but same coal price; low coal price → clients cut. [snips.stockbit] | "Stripping Ratio", "SR", "Rasio Pengupasan" | AR, IP |
| `idx:RevenuePerBcm` | Revenue per BCM | USD_PER_BCM | PRICING | Contract rate; USD-linked. | "Rate per BCM", "USD per BCM" | IP |
| `idx:RevenuePerTonCoal` | Revenue per Ton Coal Getting | USD_PER_TON | PRICING | Complementary rate. | "Rate per Ton Coal" | IP |
| `idx:EquipmentFleetSize` | Equipment Fleet Size (HD Trucks, Excavators) | UNITS | CAPACITY | Yellow-goods count; determines capacity ceiling. | "Fleet Size", "Jumlah Alat Berat" | AR |
| `idx:EquipmentUtilization` | Equipment Utilization / Utilisasi Alat Berat | PERCENT | OPERATIONAL | Physical availability × mechanical availability × operator availability. | "Utilisasi Alat", "Equipment Utilization" | AR |
| `idx:ContractBacklog` | Contract Backlog / Nilai Kontrak Sisa | USD | GROWTH | Forward-revenue visibility; DEWA IDR 22tn recent. | "Backlog Kontrak", "Contract Value" | IP, PE |
| `idx:ClientConcentration` | Top-3 Client Concentration | PERCENT | RISK | Adaro/KPC/Berau exposure; single-client risk. | "Konsentrasi Pelanggan" | AR, FSN |
| `idx:FuelCostPassThroughRatio` | Fuel Pass-Through % | PERCENT | RISK | Contract may or may not indexed to diesel; sensitivity gauge. | "Fuel Pass-through" | IP |
| `idx:EbitdaMarginContract` | EBITDA Margin by Contract Type | PERCENT | PROFITABILITY | New contracts often lower margin than legacy; a mix disclosure. | "EBITDA Margin per Kontrak" | IP |
| `idx:CapexToRevenueRatio` | Capex / Revenue | PERCENT | CAPACITY | Fleet renewal drives forward capacity. | "Capex Ratio" | AR |
| `idx:MineralDiversificationRevenueMix` | Coal vs Non-Coal (Nickel/Gold) Revenue Mix | PERCENT | MARKET_SHARE | PTRO/UNTR diversifying to nickel; the strategic de-risking metric. | "Non-Coal", "Nickel Contract" | IP, PE |

**Regulatory disclosures:**
- **PP 96/2021** — coal royalty (client-side but affects contractor's commercial framework).
- **Permen ESDM 5/2021** — mining contracting rules; local content (TKDN).
- **UU 3/2020 (Minerba)** — client-side but affects contract renewal certainty.

**Peer references:**
- **Thiess (Australia — via CIMIC → HOCHTIEF)** — publishes BCM moved, coal produced, fleet count.
- **Downer EDI (AU)** — segment mining reporting includes utilization, backlog by client.
- **Larsen & Toubro Mining (IN)** — publishes contract backlog and BCM by project.

**Sources used:**
- [Stockbit Snips — Mining Contractors Coal Headwinds](https://snips.stockbit.com/unboxing/mining-contractors-navigating-coal-headwinds-positive-on-dewa-ptro-neutral-on-untr)
- [Indonesia Business Post — PTRO Singaraja Putra](https://indonesiabusinesspost.com/5874/corporate-affairs/petrosea-reports-progress-at-singaraja-putra-coal-mining-project)
- [Indonesia Miner — DEWA IDR 22tn contract](https://indonesiaminer.com/news/detail/darma-henwa-dewa-secures-idr-22-trillion-mining-services-contract-from-sebuku-sejaka-coal)

---

## EDUCATION (Private Education — CBPE, PTPS)

**Thesis:** Micro-sector on IDX. Story = *enrollment × tuition × campus utilization × student:staff ratio*. Regulator-heavy (BAN-PT accreditation drives tuition-power).

**Thesis KPIs:**

| metric_id | name_en / name_id | unit | category | why_it_matters | search_hints | source_priority |
|---|---|---|---|---|---|---|
| `idx:StudentEnrollmentCount` | Total Enrollment / Jumlah Mahasiswa Aktif | UNITS | CAPACITY | Base metric. | "Jumlah Mahasiswa", "Enrollment" | AR, IP |
| `idx:NewStudentIntakePerYear` | New Intake per Year / Penerimaan Mahasiswa Baru | UNITS | GROWTH | Leading indicator of next year's revenue. | "PMB", "Penerimaan Mahasiswa Baru" | IP |
| `idx:AverageTuitionPerStudent` | Avg Tuition per Student per Year | IDR | PRICING | Blended tuition. | "SPP", "Tuition Fee" | AR, IP |
| `idx:CampusUtilizationRate` | Campus/Classroom Utilization | PERCENT | OPERATIONAL | Occupancy of physical capacity. | "Utilisasi Kampus" | AR |
| `idx:StudentToStaffRatio` | Student:Faculty Ratio | RATIO | OPERATIONAL | BAN-PT / KKNI regulatory ratio (varies by program). | "Rasio Mahasiswa Dosen", "Student-Faculty" | AR |
| `idx:BanPtAccreditationMix` | Accreditation Mix (A/B/C or Unggul/Baik Sekali/Baik) | PERCENT | REGULATORY | Higher accreditation = pricing & enrollment power. | "Akreditasi", "BAN-PT" | AR |
| `idx:ProgramMixByFaculty` | Program Mix (STEM/Business/Health/Humanities) | PERCENT | MARKET_SHARE | STEM/Health = higher tuition; humanities = volume. | "Bauran Program" | AR |
| `idx:GraduateEmploymentRate` | Graduate Employment Rate (6 months) | PERCENT | ASSET_QUALITY | Brand equity metric; drives PMB. | "Serapan Alumni", "Employment Rate" | IP |
| `idx:CampusCount` | Campus Count / Jumlah Kampus | UNITS | CAPACITY | Multi-campus scale. | "Jumlah Kampus" | AR |
| `idx:OperatingMarginPerStudent` | Contribution Margin per Student | IDR | PROFITABILITY | Unit economics. | "Margin per Mahasiswa" | IP |

**Regulatory disclosures:**
- **UU 12/2012** on Higher Education.
- **Permendikbud & BAN-PT** accreditation frameworks.
- **PP 4/2014** — organization of higher education.

**Peer references:**
- **Laureate Education (US, pre-privatization)** — publishes enrollment, tuition, EBITDA per student.
- **New Oriental (CN)**, **TAL Education (CN)** (pre-crackdown) — publish enrollment count, ARPU, utilization.
- **Byjus / Manipal (IN)** — publish student count, ASP, retention.

**Sources used:** general education-sector literature; IDX-listed education issuer disclosures limited.

---

## HEALTHCARE_DEVICE (Medical Device / MedTech — distinct from PHARMA / HOSPITAL)

**Thesis:** IDX has few pure-play medical-device names; may overlap PHARMA (Kimia Farma, Kalbe medical-devices arm) or HOSPITAL (in-house device). Story = *procedures done × device ASP × BPJS reimbursement × TKDN eligibility*. Government TKDN (Tingkat Komponen Dalam Negeri) drives domestic procurement.

**Thesis KPIs:**

| metric_id | name_en / name_id | unit | category | why_it_matters | search_hints | source_priority |
|---|---|---|---|---|---|---|
| `idx:DeviceUnitsSoldByCategory` | Units Sold by Category (Consumables/Diagnostics/Capital Equipment) | UNITS | VOLUME | Consumables = recurring razor-blade; capital = lumpy. | "Volume Unit", "Units Sold" | AR |
| `idx:AverageSellingPricePerDevice` | ASP per Device Category | IDR | PRICING | Wide range; PCR reagent vs MRI scanner. | "ASP", "Harga Rata-rata" | AR |
| `idx:BpjsReimbursementEligibilityRatio` | BPJS-Reimbursed SKU % | PERCENT | REGULATORY | E-Katalog + BPJS listing = scale-multiplier for a SKU. | "E-Katalog", "BPJS", "JKN" | AR, IP |
| `idx:TkdnCertificationRatio` | TKDN Certified SKU % | PERCENT | REGULATORY | ≥40% TKDN = government-procurement preference. | "TKDN", "Sertifikat Kandungan Lokal" | AR |
| `idx:MarketShareByCategory` | Market Share by Device Category | PERCENT | MARKET_SHARE | Fragmented import-dominated market; local scale matters. | "Pangsa Pasar Alkes" | IP |
| `idx:HospitalAccountCoverage` | Hospital Accounts Covered / Cakupan RS | UNITS | CAPACITY | Sales-channel breadth. | "Jumlah RS", "Hospital Accounts" | IP |
| `idx:GovernmentTenderWinRate` | Government Tender Win Rate | PERCENT | MARKET_SHARE | LKPP/e-catalog conversion rate; a competitive-signal metric. | "Tender Win", "LKPP" | IP |
| `idx:DiagnosticsRevenueMix` | Diagnostics (POC/Lab) Revenue Mix | PERCENT | MARKET_SHARE | POCT (point-of-care) is the growth pocket. | "Diagnostics", "POCT" | AR |
| `idx:RndCapexRatio` | R&D + Capex / Revenue | PERCENT | GROWTH | Innovation intensity. | "R&D Ratio", "Litbang" | AR |
| `idx:AverageContractDuration` | Avg Contract Duration (Reagent/Instrument) | MONTHS | RISK | Longer instrument-place contract = reagent lock-in. | "Kontrak Reagen" | IP |

**Regulatory disclosures:**
- **UU 36/2009 (Kesehatan)** & **UU 17/2023 (Kesehatan)** — device registration.
- **Permenkes 62/2017** — Izin Edar Alkes.
- **BPOM & Kemenkes** device classification (Class A/B/C/D).
- **LKPP e-Katalog & TKDN** — Permenperin 16/2020.
- **BPJS Kesehatan** reimbursement listing.

**Peer references:**
- **Medtronic, Boston Scientific** — publish revenue by product, geography, and organic volume/price split.
- **Mindray (CN)** — publishes revenue by device category, R&D as % of revenue, install-base for razor-blade.
- **Poly Medicure (IN)** — consumables peer; publishes volume, ASP, and exports vs domestic.

**Sources used:** general medical-device regulatory literature; IDX-listed medtech coverage limited.

---

# Cross-Sector Implementation Notes

## Naming conventions

- All `metric_id` values follow `idx:CamelCase`, matching the existing ontology (e.g. `idx:CombinedRatio`, `idx:StrippingRatio`).
- Regulatory-mandated ratios (RBC, gearing, MKBD, NPF) are **prefixed with the exact Bahasa Indonesia term** in `search_hints` because that is how they appear verbatim in FS notes.
- Where an existing ontology KPI applies (e.g. `idx:Revenue`, `idx:EBITDA`), we deliberately did **not** re-propose it; each sector's list is *incremental* on top of the generic base.

## Priority sectors for phase-1 seeding

Based on IDX free-float weight and disclosure quality:

1. **Tier A (seed first)**: INSURANCE_GENERAL, MULTIFINANCE, AIRLINES, MEDIA_BROADCAST, INVESTMENT_HOLDING, MINING_SERVICES, HOTEL_TOURISM, STEEL_METAL, CERAMIC_GLASS, JEWELRY_LUXURY, TIN_MINING.
2. **Tier B**: INSURANCE_LIFE, INSURANCE_REINSURANCE, SECURITIES_BROKER, LOGISTICS_FORWARDING, TEXTILE_GARMENT, PACKAGING, BEVERAGE_ALCOHOL, FOOD_RESTAURANT, INDUSTRIAL_GAS.
3. **Tier C (small market cap / few issuers)**: FOOD_INGREDIENT, CHEMICALS, WATER_UTILITY, FOOTWEAR, PLASTICS_HOUSEWARE, PROPERTY_REIT, EDUCATION, HEALTHCARE_DEVICE.

## Ontology hooks

- Regulatory-mandated ratios (RBC, gearing, MKBD, HGBT eligibility) should be tagged with a `regulatory_source` attribute pointing to the POJK/Permen number.
- Volume × price KPIs should be linked pairs so the validator can catch a broken decomposition (e.g. if only `RefinedTinSalesVolume` is submitted without `AverageSellingPricePerTonTin`, warn but don't block).
- Where a sector already exists (e.g. CPO vs FOOD_INGREDIENT for edible oil), the classifier should default to the more specific sector; only fall back on the generic label if the announcement contract explicitly requires it.

---

**End of pack.**
