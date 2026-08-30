---
description: Strict token-efficient extraction protocol for incoming financial statement PDFs
trigger: always_on
---

# Financial PDF Ingestion & Granular Extraction Rules

When processing financial statements or files located in `incoming_reports/`:

1. **NEVER read the entire 150+ page PDF from start to end.**
2. Always call the EMIMIND MCP tool `inspect_document` first. If `ALREADY_PROCESSED`, terminate immediately with 0 tokens spent.
3. Call `get_extraction_contract(doc_id)` to receive the exact sector checklist and `granular_note_modules`.
4. **Mandatory Targeted Extraction (8–12 pages total)**:
   - **4 Core Statements (~4–5 pages)**: Balance Sheet, Income Statement, Cash Flow Statement.
   - **Index of Notes (Daftar Catatan) (1 page)**: Use page numbers to jump directly to disclosure notes.
   - **Granular Disclosure Notes (~3–5 pages)**:
     - Revenue by Product Line (e.g. CPO, PK, Rubber) $\to$ `ifrs:Revenue` with `segment: {"segment": "<Product>", "type": "product"}`
     - Customer Concentration (>10%) $\to$ `idx:CustomerConcentration` with `segment: {"segment": "<Buyer>", "type": "customer_concentration"}`
     - COGS Breakdown (Pupuk, Upah, Bahan Baku, Penyusutan) $\to$ `idx:CostOfGoodsSoldComponent` with `segment: {"segment": "<Cost Item>", "type": "cogs_component"}`
     - Cash & Deposits per Bank $\to$ `ifrs:CashAndCashEquivalents` with `segment: {"segment": "<Bank>", "type": "bank_placement"}`
     - Biological Assets / Hectares (if Agri/CPO) $\to$ `idx:PlantedAreaHectares` with `segment: {"segment": "Mature/Immature", "type": "biological_asset_maturity"}`
     - Debt by Lender $\to$ `idx:BorrowingsByLender` with `segment: {"segment": "<Bank>", "type": "debt_facility"}`
     - Management Causality $\to$ `causal_links: [...]` (explaining why revenue/margins changed).
5. Detect table scale ("dalam jutaan rupiah" vs "dalam ribuan rupiah") and convert values to full IDR integer scale in the JSON payload.
6. Submit draft payload to `submit_draft_extraction` for mathematical validation.
7. If validation fails, re-examine ONLY the specific `target_pages` returned in the MCP error feedback.
8. Call `commit_verified_report` only when the report is valid.
