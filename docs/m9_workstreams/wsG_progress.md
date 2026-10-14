# Workstream G: router held-out gold for the random test tickers (live tracker)

> **Resume protocol.** Read this file first, continue from "Next action", and don't relabel docs marked `done`. Update after EVERY document.

Labelling is **blind to the router**: labels come from the PDF's own statement titles, notes index and note headings. Never call `get_routed_pages`; never read `services/retrieval/`, `db/seeds/page_router_queries.yaml`, `eval/reports/router_*`, `document_processing_log` ROUTED rows, `docs/m9_workstreams/wsD_*`, or any `m9_stage/*/wsE_*` tracker.

Output: `eval/router_gold/heldout_random/<TICKER>_2025Q4.yaml`, in the same format as `eval/router_gold/heldout/AALI_2021Q1.yaml`.

| Ticker | doc_id | Pages | Modules (from contract) | Status | Notes |
|---|---|---|---|---|---|
| NISP | f67d9be5-9f1d-465e-bb99-0f37697ffd1b | 197 | BALANCE_SHEET, INCOME_STATEMENT, CASH_FLOW, MDA, COGS_COMPONENTS, CUSTOMER_CONCENTRATION, DEBT_BY_LENDER, REVENUE_BREAKDOWN, BANK_LOAN_QUALITY_NPL, BANK_LOANS_BY_SEGMENT, BANK_PROFITABILITY_KPIS | done | BS 12-14, IS 15-16, CF 19-21; MDA = Note 1 + Note 3 FRM (no subsequent-events note); COGS read as Note 31 interest expense (bank); CUSTOMER_CONCENTRATION []; PROFITABILITY_KPIS = Note 52 regulatory ratios (no NIM/BOPO/ROA) |
| TAPG | 257139d8-ed15-45d4-aa79-ace3a36575e7 | 131 | BALANCE_SHEET, INCOME_STATEMENT, CASH_FLOW, MDA, COGS_COMPONENTS, CUSTOMER_CONCENTRATION, DEBT_BY_LENDER, REVENUE_BREAKDOWN, BIOLOGICAL_ASSETS_DETAIL, CPO_UPSTREAM_KPIS | done | BS 14-16, IS 17-18, CF 20-21; MDA = Note 1 + Note 40 FRM (no subsequent-events note); bearer plants sit in Note 12 Fixed assets; CPO_UPSTREAM_KPIS [] (no production KPIs in FS) |
| PTBA | 69967908-f0d2-4a10-9562-4b3a4ea60abc | 168 | BALANCE_SHEET, INCOME_STATEMENT, CASH_FLOW, MDA, COGS_COMPONENTS, CUSTOMER_CONCENTRATION, DEBT_BY_LENDER, REVENUE_BREAKDOWN, MINING_PRODUCTION_AND_SALES, MINING_RESERVES_AND_RESOURCES | done | BS 14-16, IS 17-18, CF 20-21; MDA = Note 1 + Note 31 + Note 37 subsequent events; no coal tonnage or reserve tonnage in FS (mining modules labelled to Note 26/33 and Note 10/18) |
| BSDE | e963c620-478d-499e-a1a3-bd30408d8af6 | 223 | BALANCE_SHEET, INCOME_STATEMENT, CASH_FLOW, MDA, COGS_COMPONENTS, CUSTOMER_CONCENTRATION, DEBT_BY_LENDER, REVENUE_BREAKDOWN, PROPERTY_PRESALES_MARKETING, PROPERTY_RECURRING_INCOME | done | BS 11-12, IS 13, CF 16; MDA = Note 1 (17-37) + Note 56 FRM + Note 61 subsequent events; DEBT includes Note 32 bonds/sukuk; CUSTOMER_CONCENTRATION = negative disclosure p178; no presales/occupancy in FS (property modules mapped to contract liabilities, revenue, segment, inv. property income) |
| UNVR | 070f0223-afb2-4ea5-8e7d-c136ef8a4ace | 97 | BALANCE_SHEET, INCOME_STATEMENT, CASH_FLOW, MDA, COGS_COMPONENTS, CUSTOMER_CONCENTRATION, DEBT_BY_LENDER, REVENUE_BREAKDOWN | todo | |
| ISAT | d7433034-90a3-4cdb-b6b4-9f5fdf97b865 | 152 | BALANCE_SHEET, INCOME_STATEMENT, CASH_FLOW, MDA, COGS_COMPONENTS, CUSTOMER_CONCENTRATION, DEBT_BY_LENDER, REVENUE_BREAKDOWN, TELCO_MOBILE_KPIS | todo | |

## Next action
Label UNVR.
