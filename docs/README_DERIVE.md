# Derived Metrics Engine (`services/derive/`)

## Architecture Overview
The derived metrics engine guarantees that **numeric calculations live in code/SQL, never in LLM hallucinations**.

### Structure:
- `services/derive/registry.py`: `@recipe` decorator, `RecipeContext`, `RecipeResult`, `REGISTRY`, `FactsAccessor`, `PeersAccessor`.
- `services/derive/recipes/generic.py`: Margins (gross, operating, net), debt-to-equity, current ratio, ROE, ROA, YoY deltas, QoQ deltas, 3-year CAGR.
- `services/derive/recipes/bank.py`: NIM, NPL, CASA, LDR, CoC, BOPO, CIR.
- `services/derive/recipes/mining.py`: Cash cost per ton, strip ratio, ASP, nickel margin.
- `services/derive/recipes/cpo.py`: CPO realized price, FFB yield, cash cost per ton, oil extraction rate (OER).
- `services/derive/recipes/telco.py`: EBITDA margin, ARPU, Capex intensity.
- `services/derive/recipes/insurance.py`: RBC solvency ratio, loss ratio, combined ratio.
- `services/derive/recipes/peer_percentile.py`: Cross-sectional cohort rankings across peer groups.
- `services/derive/engine.py`: Parallel recipe evaluation with topological dependency resolution.
