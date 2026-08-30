# Stock Screener Engine (`services/screener/`)

## Architecture Overview
The stock screener engine enables natural-language multi-criteria screening over the entire Indonesian public universe.

### Subsystem Flow:
1. **DSL Grammar (`services/screener/dsl.py`):** Pydantic v2 schemas (`Universe`, `Filter`, `Sort`, `ScreenerDSL`, `ScreenerResult`).
2. **NL Parser (`services/screener/parser.py`):** Utility LLM tool use with deterministic regex fallback parsing queries into valid `ScreenerDSL`.
3. **SQL Compiler (`services/screener/compiler.py`):** Compiles DSL into a parameterized query with `INTERSECT` candidate filtering and JSONB provenance tracking.
4. **Executor (`services/screener/executor.py`):** Runs the compiled query over `derived_metrics` and `issuer_profile`.
5. **Renderer (`services/screener/renderers.py`):** Formats output into clean markdown tables with source citations.
