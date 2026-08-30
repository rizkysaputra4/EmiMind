# Manual L4 Narrative Memory Retrieval Smoke Test Log

This document records the manual verification of 5 sample queries against the hybrid retrieval pipeline (ANN + FTS + Cross-Encoder Rerank) for Milestone 3.

---

## Benchmark Results Summary

- **Model:** BGE-M3 (1024-dim dense) + Cross-Encoder Reranking
- **Coverage:** BMRI 2024Q4 Management Discussion & Analysis, Risk Profiling, Guidance, and Financial Footnotes

| Query ID | Query Text | Target Section | Top Citation | Relevance Judgment |
|:---|:---|:---|:---|:---:|
| **C-001** | `net interest margin NIM loan growth` | MDA | `[BMRI-FS-2024Q4#p1]` | 🟢 PASS |
| **C-002** | `credit risk liquidity management non performing loans` | RISK | `[BMRI-FS-2024Q4#p1]` | 🟢 PASS |
| **C-003** | `target pertumbuhan kredit panduan manajemen 2025` | GUIDANCE | `[BMRI-FS-2024Q4#p1]` | 🟢 PASS |
| **C-004** | `transformasi digital aplikasi Livin dan Kopra` | MDA | `[BMRI-FS-2024Q4#p1]` | 🟢 PASS |
| **C-005** | `pencadangan penurunan nilai CKPN PSAK 71` | FOOTNOTE | `[BMRI-FS-2024Q4#p2]` | 🟢 PASS |

---

## Verifications & Assertions

1. **Mandatory Citations:** Every retrieved chunk includes standard citation format `[TICKER-DOCTYPE-PERIOD#pPAGE]`.
2. **Translation:** Indonesian narrative chunks have `text_en` translated and indexed alongside original text.
3. **Token Budgets:** Renderers format outputs adhering to prompt token caps.
