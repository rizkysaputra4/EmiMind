# Knowledge Graph & Guidance Tracker (`services/kg/`)

## Architecture Overview
The Knowledge Graph subsystem models longitudinal corporate disclosures, forward-looking targets, realized performance deltas, and causal explanations.

### Schemas:
- `kg_nodes`: `CLAIM`, `EVENT`, `GUIDANCE`, `ACTUAL`, `COMPANY`, `METRIC`, `STANDARD_CHANGE`.
- `kg_edges`: `PREDICTS`, `REALIZED_AS`, `CAUSED_BY`, `PEER_OF`, `CONTRADICTS`, `REVISES`, `AFFECTS`.

### Components:
- `services/kg/guidance_miner.py`: Two-tier extractor (deterministic regex + LLM reasoner tool calling).
- `services/kg/actual_matcher.py`: Links realized actual disclosures to previous guidance targets and emits `CONTRADICTS` edges upon missed bounds.
- `services/kg/causal_linker.py`: Extracts causal effect-cause relationship triples from MDA sections with honest 0.50–0.80 confidence.
- `services/kg/traversal.py`: Recursive CTE graph traversal for multi-hop relationship exploration.
