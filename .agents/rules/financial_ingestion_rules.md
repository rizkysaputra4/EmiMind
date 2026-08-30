---
description: Strict token-efficient extraction protocol for incoming financial statement PDFs
trigger: always_on
---

# Financial PDF Ingestion & Token Optimization Rules

When processing financial statements or files located in `incoming_reports/`:

1. **NEVER read the full PDF document from page 1 to end.**
2. Always call the EMIMIND MCP tool `inspect_document` first. If `ALREADY_PROCESSED`, terminate immediately with 0 tokens spent.
3. Call `get_extraction_contract(doc_id)` to receive the exact sector checklist.
4. Target ONLY the 4 core financial statement pages:
   - Balance Sheet (~2-3 pages)
   - Income Statement (~1-2 pages)
   - Cash Flow Statement (~1-2 pages)
   - Specific Sector Notes (only if requested by contract)
5. Detect table scale ("dalam jutaan rupiah" vs "dalam ribuan rupiah") and convert values to full IDR integer scale in the JSON payload.
6. Submit draft payload to `submit_draft_extraction` for mathematical validation.
7. If validation fails, re-examine ONLY the specific `target_pages` returned in the MCP error feedback.
8. Call `commit_verified_report` only when the report is valid.
