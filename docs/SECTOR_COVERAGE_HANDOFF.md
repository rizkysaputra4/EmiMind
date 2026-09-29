# Sector Coverage & Extraction Scope — Handoff Guide

Written 2026-09-07. This document explains what was done in the LQ45/KOMPAS100/IDX30 gap-coverage pass, what remains, and how a future AI agent should extend coverage without duplicating work.

## The situation this pass addressed

The extraction pipeline downloads reports for the full IDX universe (~995 tickers land under `EmiMind-Extraction/incoming_reports/`), but `issuer_profile` only had sector mappings for ~205 tickers. Documents for the other ~790 tickers had no sector-specific KPI pack, so extraction would fall back to `GENERIC` — filling the database with weakly-classified, low-signal data. The operator's directive: **"i dont want to fill the system with many trash."**

## What Phase 1 did (this pass)

**Scope:** LQ45 + KOMPAS100 + IDX30 constituents for the Aug 2026 – Jan 2027 rebalancing period. Two K100 members (COIN, EMAS) had no PDFs yet in `incoming_reports/`, so we deferred them. The remaining **24 gap tickers** were classified.

**8 new sector codes** (KPI packs seeded in `scripts/seed_metric_ontology.py` and `scripts/seed_idx_tickers.py:SECTOR_KPIS`):

| Sector | Anchor ticker | Regulatory basis |
|---|---|---|
| INSURANCE | PNLF | POJK 71/POJK.05/2016 RBC ≥120%, POJK 5/POJK.05/2022 PAYDI, SEOJK 31/SEOJK.05/2015 retention |
| MULTIFINANCE | BFIN | POJK 35/POJK.05/2018 gearing ≤10x, NPF Net <1% for 0% DP |
| HOTEL_TOURISM | BUVA, MINA | PP 50/2011, UU 10/2009 tourism |
| JEWELRY_LUXURY | HRTA | Permenkeu 30/PMK.03/2014 bullion VAT 0% |
| MEDIA_BROADCAST | SCMA | UU 32/2002 Broadcasting, KPI content quotas |
| INVESTMENT_HOLDING | BNBR | POJK 15/2020 RPT, POJK 42/2020 material transactions |
| TIN_MINING | TINS | UU 3/2020 Minerba, Permen ESDM 7/2020 export permits |
| CHEMICALS | SMIL | UU 32/2009 environmental, BPOM & B3 rules |

**Existing sectors reused** for the other 16 tickers: COAL (BIPI, CUAN, RMKE, SGER), PROPERTY (BKSL, CBDK, KPIG, PANI, SSIA), TELCO (INET, WIFI), BASIC_MATERIALS (IMPC), CONTRACTOR (PTRO), OIL_GAS (RATU), DIGITAL (WIRG).

**Extraction gate:** `services/mcp/server.py:inspect_document` now checks `issuer_profile.sector` and returns `InspectionStatus.OUT_OF_SCOPE` for any ticker without a sector mapping. This is the chokepoint — no document for an unmapped ticker enters the DB. `get_extraction_contract` also prefers `issuer_profile` over the sparse `peer_groups` fallback.

**Files changed in Phase 1:**
- `scripts/seed_metric_ontology.py` — added 65 `METRIC_DEFINITIONS_DATA` entries under sections 25–32
- `scripts/seed_idx_tickers.py` — added 8 keys to `SECTOR_KPIS` and 24 rows to `IDX_TICKERS`
- `services/mcp/types.py` — added `InspectionStatus.OUT_OF_SCOPE`
- `services/mcp/server.py` — wired the scope gate

**To activate Phase 1:** rerun the seeds from the EmiMind workspace:
```
uv run python scripts/seed_metric_ontology.py
uv run python scripts/seed_idx_tickers.py
```

## Research library (the source of truth for future passes)

Two full research packs sit in `docs/`. Future agents should treat these as authoritative — do not re-research what's already covered.

### `docs/SECTOR_KPI_RESEARCH_PACK.md` (~10k words, 28 sectors)

Sector KPI packs for **all** currently-missing IDX-relevant sectors, not just the 8 seeded in Phase 1. Each sector has: thesis statement, 8–14 differentiating KPIs with `metric_id` / EN+ID names / unit / category / one-sentence "why it matters" / search hints / source priority, regulatory disclosure section with POJK/Permen/UU citations, 2–3 international peer benchmarks, and inline source links (heavy 2025–2026 vintage).

Sectors already researched but **not yet seeded** (Phase 2 candidates — only seed once tickers become in-scope):

| Sector | Ticker examples |
|---|---|
| INSURANCE_REINSURANCE | MREI, Indonesia Re |
| SECURITIES_BROKER | PANS, TRIM, RELI, YULE, KREN, PEGE, AKSI |
| AIRLINES | GIAA, IATA |
| LOGISTICS_FORWARDING | ASSA, JAYA, TRAM, NELY, TAMU, SAPX, SDMU |
| TEXTILE_GARMENT | PBRX, INDR, POLY, TFCO, RICY, MYTX, ERTX |
| STEEL_METAL | KRAS, GDST, ISSP, ALKA, JKSW, NIKL |
| CERAMIC_GLASS | ARNA, AMFG, MLIA, TOTO, KIAS |
| BEVERAGE_ALCOHOL | MLBI, DLTA, BEER |
| FOOD_INGREDIENT | TBLA, BUDI, CEKA, SKBM, PSDN, DMND |
| PACKAGING | AKPI, IGAR, IPOL, TRST, TALF, KDSI, BRNA |
| INDUSTRIAL_GAS | AGII, SAMF |
| WATER_UTILITY | PDES |
| FOOTWEAR | BATA |
| PLASTICS_HOUSEWARE | APLI, CINT, LTLS, LPIN, LMPI |
| FOOD_RESTAURANT | PZZA, FAST, ENAK, FORE, MAPB |
| PROPERTY_REIT | DIRE Bowsprit, DIRE Ciptadana |
| HEAVY_EQUIP_MINING_SERVICES | DEWA, BUKK, MYOH, SIMS (PTRO seeded under CONTRACTOR — reassess if separate) |
| EDUCATION | CBPE, PTPS |
| HEALTHCARE_DEVICE | (nascent — few pure-plays) |

### `docs/EXISTING_SECTOR_KPI_AUDIT.md` (~135 additional KPIs across 24 existing sectors)

Gap analysis for the 24 sectors already covered. Each sector has: `## SECTOR_CODE` → **Currently covered** (existing metric_ids) → **Missed high-signal KPIs** (3–10 additions per sector, same schema as the research pack). Total ~85 CRITICAL + ~50 HIGH additions; 22 with cited POJK/ESDM/Kemenkes/EU EUDR regulatory anchors.

Highest-conviction additions the auditor flagged:
1. `idx:FeeBasedIncomeRatio` (BANK) — proxy for franchise quality
2. `idx:PPAContractedCapacityMW` + `idx:TariffPPAUSCentsPerKWh` (RENEWABLE_ENERGY)
3. `idx:CoalSalesContractedForwardPct` (COAL)
4. `idx:BiodieselOfftakeShare` + `idx:DMOComplianceVolumeMT` (CPO)
5. `idx:WeightedAvgContractTenureYears` + `idx:ColocationCountTotal` (TOWER)

Sectors with the widest coverage gaps in the audit: **BASIC_MATERIALS** (has only Revenue + EBITDA today), **TOWER** (only 2 KPIs), **TELCO** (missing fixed broadband, enterprise, capex intensity), **BANK** (no fee-income, no digital-user KPIs), **RENEWABLE_ENERGY** (no PPA framework).

## Instructions for the next AI agent

### Task A — Apply the existing-sector KPI audit (fastest wins)

Read `docs/EXISTING_SECTOR_KPI_AUDIT.md` section by section. For each sector, for each proposed KPI:

1. Grep `scripts/seed_metric_ontology.py` for the proposed `metric_id` — skip if it already exists.
2. Add a new entry to `METRIC_DEFINITIONS_DATA` following the one-line format at the bottom of the file (mirror the style used for sectors 25–32).
3. Append the `metric_id` to the corresponding sector's list in `SECTOR_KPIS` (`scripts/seed_idx_tickers.py`).
4. When a KPI is regulatory-mandated (audit cites POJK/ESDM/etc.), set `importance="CRITICAL"` so the validator forces the LLM to justify any omission.

Enum reminders (from the current schema):
- `category`: ASSET_QUALITY, BALANCE_SHEET, CAPITAL, CASH_FLOW, INCOME, LIQUIDITY, OPERATIONAL, PROFITABILITY, RESERVES (schema has no CHECK constraint — new values allowed but ontology should stay consistent)
- `unit`: see `grep -oE '"unit": "[A-Z_]+"' scripts/seed_metric_ontology.py | sort -u`
- `value_type`: FLOAT, INTEGER, MONETARY, PERCENTAGE
- `importance`: CRITICAL, HIGH, MEDIUM
- `flow_stock_type`: EVENT, FLOW_PERIOD, RATIO, STOCK_POINT_IN_TIME

### Task B — Seed the 20 remaining sectors from the research pack

Only do this **when the relevant tickers become in-scope** (e.g. an LQ45 rebalancing brings GIAA back). Otherwise you're seeding metrics no ticker will use. When you do:

1. Read the target section from `docs/SECTOR_KPI_RESEARCH_PACK.md`.
2. Add its KPIs to `METRIC_DEFINITIONS_DATA` (sections 33+).
3. Add a `SECTOR_KPIS[<NEW_SECTOR>]` list.
4. Append the tickers to `IDX_TICKERS` with the new sector code.
5. If the sector needs a `sector_metric_contracts` module (e.g. INSURANCE would benefit from an `INSURANCE_UNDERWRITING_MIX` module for GWP-by-line disclosure), add it to `SECTOR_CONTRACTS_DATA` in the same file.

### Task C — Expand beyond LQ45/KOMPAS100 (deferred)

The remaining ~700 unmapped tickers are mostly small caps, delisted, or newly-listed. Do not blanket-add them. When the operator asks to expand, use this workflow:

1. Get current IDX80 / IDX200 constituent list via web search (source: IDX press release for the current 6-month rebalancing window).
2. Cross-reference against `issuer_profile` (`SELECT ticker FROM issuer_profile WHERE sector IS NOT NULL`).
3. For each gap, classify by sector using company name + industry keywords (this is usually enough — full IR research is only needed when the sector is ambiguous).
4. Follow Task B for any newly-required sector.

The `OUT_OF_SCOPE` gate is the safety net: it costs nothing to leave a ticker unmapped, because the pipeline will just skip it.

## What NOT to do

- **Don't remove the `peer_groups` fallback in `get_extraction_contract`.** It exists so historical documents for tickers that were later removed from `issuer_profile` can still produce a contract if queried. The primary path is `issuer_profile`; the fallback is for lineage.
- **Don't re-classify the 8 new sectors** — they were placed after live cross-reference against Aug 2026 KOMPAS100 official IDX release. Reclassification risks breaking already-extracted facts if the sector code changes.
- **Don't seed sectors that have no in-scope tickers.** Every unused sector code adds noise to `get_metric_ontology` responses and slows contract building.
- **Don't propose generic metrics (Revenue, Net Profit, EBITDA, ROE, ROA) as sector-specific KPIs.** They live under `sector_applicability=["ALL"]` already. Sector KPI packs exist to surface *differentiated* KPIs — the ones that reveal the business's thesis. See `docs/SECTOR_KPI_RESEARCH_PACK.md` intro for the "big idea from small detail" principle.
- **Don't skip the regulatory citation when one exists.** Auditors, analysts, and the operator all use POJK/ESDM/Permen references to validate whether an extractor's omission was legitimate. Cite the exact regulation number.

## Verification checklist for future passes

After adding new sectors or KPIs:

- [ ] `uv run python scripts/seed_metric_ontology.py` runs clean (no PK conflicts on `metric_id`)
- [ ] `uv run python scripts/seed_idx_tickers.py` runs clean (every ticker's `key_kpis` list contains only metric_ids that exist in `metric_definitions`)
- [ ] MCP call `get_metric_ontology` returns the new metrics with correct `sector_applicability`
- [ ] MCP call `inspect_document` for a newly-added ticker returns `AUTHORIZED` (not `OUT_OF_SCOPE`)
- [ ] MCP call `get_extraction_contract` for that ticker includes the new sector's KPIs in `required_facts`
- [ ] MCP call `inspect_document` for a still-unmapped ticker returns `OUT_OF_SCOPE` with the seed-script instructions
- [ ] Add a unit test to `tests/unit/test_mcp_server.py` covering the OUT_OF_SCOPE branch if not already there
