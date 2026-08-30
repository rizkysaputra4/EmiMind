# Retrieval Pipeline (`services/retrieval/`)

## Architecture Overview
The retrieval subsystem coordinates multi-layer evidence gathering, token budgeting, prompt assembly, and multi-turn stateful reasoning.

### Layer Stack:
- **Layer 1 (L1):** Turn routing & state classification (`services/retrieval/turn_router.py`).
- **Layer 2 (L2):** Normalized financial facts lookup (`financial_facts`).
- **Layer 3 (L3):** Formula-derived metrics and peer percentiles (`derived_metrics`).
- **Layer 4 (L4):** Hybrid vector ANN (BGE-M3 1024-dim) + BM25 FTS + Cross-Encoder reranker (`narrative_chunks`).
- **Layer 5 (L5):** Recursive CTE causal knowledge graph traversal & guidance actuals (`kg_nodes`, `kg_edges`).
- **Layer 6 (L6):** Long-range issuer profiles (`issuer_profile`).
- **Layer 7 (L7):** Market technical regime & momentum indicators (`technical_state`).

### Budgeting & Assembly:
`services/retrieval/budgeter.py` enforces hard caps per evidence category. `prompt_assembler.py` wraps structured evidence in `<evidence type="...">` XML tags, providing strict prompt injection immunity.
