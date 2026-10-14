# wsR dev2 router gold labelling progress

## Resume protocol
1. Read this file first. Never relabel a doc whose status is `done`.
2. Doc ids come only from `eval/reports/router_dev2_manifest.json` (entries with `"status": "ready"`).
3. BLIND: labels come only from the doc's own page text (dump helper in session scratchpad `rd2/label/dump.py`: `uv run python dump.py <doc_id> <out.txt>`). Never call router functions or read router outputs/other gold sets.
4. Output: `eval/router_gold/dev2/<TICKER>_2025Q4.yaml`. Continue from "Next action".

## Status

| ticker | doc_id | pages | status | notes |
|---|---|---|---|---|
| SIMP | 6ddb93aa-b2af-4652-a31e-26996ab33703 | 136 | done | doubtful: DEBT incl. p121 related-party shareholder loans; PLANTATION_AREA excludes p76 HTI timber ha |
| BUMI | ec90ce9e-6c6a-4335-853e-889909e1e7c9 | 173 | done | production+reserves table only on p22 (Note 1.e); BNI facility in commitments p163 excluded from DEBT |
| CTRA | 7f3423bc-c5c7-491b-b990-6cfffaf7015b | 165 | done | PROPERTY_PRESALES_MARKETING [] (not in FS) |
| INDF | 147f35f2-e599-4ea6-93e2-6fbdfab3088e | 161 | done | DEBT incl. Note 31 PWL related-party loans p137,p140 (same convention as SIMP p121) |
| TLKM | 7ebf92c5-dafa-4b38-95c0-6140e96b9fce | 129 | done | TELCO_MOBILE_KPIS []; COGS = Note 25 OM&TS expenses (no COGS note, doubtful); FRM is Note 37b |
| BRIS | 0b336c7e-0fe3-40cc-8f65-7dffd43b24c4 | 183 | done | CUSTOMER_CONCENTRATION [], BANK_PROFITABILITY_KPIS []; collectibility/NPF only in Note 54; no ECL stage tables |

Next action: none - all six docs labelled. Report to caller.
