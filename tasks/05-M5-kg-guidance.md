# M5 — Knowledge Graph + Guidance (Weeks 21–26)

**Goal:** L5 nodes and edges populate on ingest. The guidance miner extracts management targets from GUIDANCE chunks; the actual matcher creates `PREDICTS/REALIZED_AS` edges when the target period lands. The causal linker emits `CAUSED_BY` edges from MDA chunks. The `GUIDANCE_CHECK` intent works end-to-end for banks. Rolling summaries and sticky slots feel natural.

**Prerequisite:** M4 exit gate green.

---

## 1. KG schemas

### M5.1.1 — KG nodes & edges
**File:** `db/schema/012_kg_nodes_edges.sql`
**Copy verbatim:** appendix-schemas.md § "012_kg_nodes_edges.sql"

Includes `kg_nodes` and `kg_edges` per BLUEPRINT §6.5.

**Acceptance:** migration applies.

---

## 2. Guidance miner

### M5.2.1 — Guidance types
**File:** `services/kg/types.py`

```python
class GuidancePayload(BaseModel):
    metric: str  # canonical concept_id or metric_id
    low: Decimal | None
    high: Decimal | None
    period_target: FiscalPeriod
    qualifier: Literal["at_least", "at_most", "exact", "range", "direction"] = "range"
    direction: Literal["up", "down", "flat"] | None = None
    unit: str
    verbatim: str  # the source sentence for citation
```

### M5.2.2 — Deterministic guidance miner
**File:** `services/kg/guidance_miner.py`

Function: `async mine_guidance(chunk: NarrativeChunk) -> list[GuidancePayload]`.

Two-tier extraction:
1. **Regex pass** for common patterns:
    - `"loan growth of 8-10% for 2025"` → metric=`loan_growth`, range=(0.08,0.10), period=2025FY.
    - `"NIM target of 5.2%"` → metric=`bank.nim`, exact=0.052.
    - `"we expect revenue to grow at least 15%"` → direction=up, qualifier=at_least.
2. **LLM fallback** — `get_llm("reasoner")` with `force_tool="GuidancePayload"` for GUIDANCE-marked chunks that regex didn't extract from. Batch 10 chunks per call.

Only emits high-confidence guidance (regex ≥ 0.9, LLM only when structured extraction succeeds).

### M5.2.3 — Miner worker
**File:** `services/ingest/tasks/mine_guidance.py`

`WORKER_VERSION = "1.0"`.

For each `narrative_chunks` row with `claim_type='GUIDANCE'` from the current doc:
- Extract payloads.
- Insert one `kg_nodes` row per payload: `node_type='GUIDANCE'`, `ticker`, `fiscal_period` (source period), `payload=GuidancePayload`, `source_ref={"doc_id","page","chunk_id"}`.

**Acceptance:**
- Integration test: fixture with ≥3 known GUIDANCE statements produces ≥3 GUIDANCE nodes.

---

## 3. Actual matcher

### M5.3.1 — Actual matcher
**File:** `services/kg/actual_matcher.py`

`async match_actuals_for(ticker: Ticker, new_period: FiscalPeriod) -> MatchReport`.

Algorithm (BLUEPRINT §5.5):
1. Find `GUIDANCE` nodes where `payload.period_target == new_period`.
2. For each: look up the ACTUAL value from `financial_facts` (or `derived_metrics` if the guidance is on a derived metric like NIM).
3. If no ACTUAL yet, do nothing (this quarter's ingest may complete it).
4. Else: create/upsert an `ACTUAL` node with the observed value + source_ref.
5. Create `REALIZED_AS` edge: `src=GUIDANCE, dst=ACTUAL, payload={delta, hit_bounds}`.
6. If actual outside guidance range: also create `CONTRADICTS` edge with `confidence=1.0`.

### M5.3.2 — Matcher worker
**File:** `services/ingest/tasks/match_actuals.py`

Runs on every ingest completion for the ticker; walks all outstanding GUIDANCE for that ticker.

`WORKER_VERSION = "1.0"`.

**Acceptance:**
- Given a fixture with a Q3-issued guidance for Q4 and a Q4 filing that matches, running the pipeline creates a REALIZED_AS edge with populated delta.

---

## 4. Causal linker

### M5.4.1 — Causal linker
**File:** `services/kg/causal_linker.py`

`async link_causes_for_doc(doc_id: UUID) -> LinkReport`.

Algorithm:
1. Select `narrative_chunks` for the doc where `section='MDA'` and text mentions both a metric-alias and a driver phrase (regex prefilter: e.g. `"karena|because|due to|didorong oleh|driven by|attributable to"`).
2. Batch chunks (10 per LLM call). Prompt `get_llm("reasoner")` (forced tool-use) to emit for each chunk a list of `(effect_metric, cause_metric_or_phrase, direction, confidence 0.5..0.8)` triples.
3. Emit `CAUSED_BY` edges: src = CLAIM node for the chunk, dst = an EFFECT node (or an existing METRIC node), payload = cause description, confidence.

**Never** create edges above 0.8 — the linker is honest about its uncertainty.

### M5.4.2 — Causal linker worker
**File:** `services/ingest/tasks/link_causes.py`

`WORKER_VERSION = "1.0"`.

**Cost cap:** at most 5 batches per doc. Skip if over budget.

**Acceptance:**
- Integration test on a fixture with ≥5 causal MDA sentences yields ≥3 CAUSED_BY edges.

---

## 5. KG traversal

### M5.5.1 — Traversal helper
**File:** `services/kg/traversal.py`

`async traverse(root_id: int, edge_types: list[str], max_hops: int, limit: int) -> list[KGTriple]`.

Uses the recursive CTE from BLUEPRINT §6.5 with parameter binding. Statement timeout 500ms.

`KGTriple` (Pydantic): `src_node, edge, dst_node, depth`.

### M5.5.2 — Wire into planner
**File:** `services/retrieval/planner.py` (edit)

For `EXPLANATION`: L5Step invokes `traverse(...)` from the current `focus` node (find the most recent ACTUAL/CLAIM node matching the concept).

For `GUIDANCE_CHECK`: L5Step returns matched (GUIDANCE, REALIZED_AS, ACTUAL) triples for the ticker & period.

For `COMPARE_PEERS`: pull `PEER_OF` edges (populated from `peer_groups`).

**Acceptance:**
- End-to-end: asking "Did BMRI hit their loan growth guidance for 2025?" surfaces GUIDANCE + REALIZED_AS triples, and the answer cites both the guidance page and the actual fact.

---

## 6. Conversation continuity polish

### M5.6.1 — Rolling summary quality pass
**File:** `services/retrieval/summarizer.py` (edit)

Add guardrails from BLUEPRINT §13:
- Never re-embed history.
- Preserve last decided claims (kg_edge ids) in a `decided_claims: list[int]` field alongside the prose summary.
- Refresh triggered every 4 turns OR on topic_change.

### M5.6.2 — Sticky slots persistence
Ensure `StickyState` mutation on drill/pivot/topic_change matches BLUEPRINT §13.4 exactly. Add unit tests for 20 turn sequences.

### M5.6.3 — Last-claim expansion
**File:** `services/retrieval/executor.py` (edit)

If `sticky.last_claim_node_id` is set and `turn_kind == 'drill'`: L5Step traversal starts from that node instead of the newly-matched one.

---

## 7. `GUIDANCE_CHECK` intent

### M7.1 — Planner + renderer
Add renderer `render_guidance_actual_table(triples) -> str` producing:

```
| Guidance (source) | Actual (source) | Delta | Hit? |
|---|---|---|---|
| Loan growth 8–10% FY25 [BMRI-PUBEX-2024FY#p14] | 9.2% [BMRI-FS-2025Q4#p6] | +0.2pp above midpoint | ✅ |
```

Wire into `planner.py` and `chat.py`.

**Acceptance:**
- End-to-end for BMRI: `GUIDANCE_CHECK` intent returns a table with ≥ 2 rows of guidance/actual.

---

## M5 exit gate

- [ ] Ingest of a filing writes GUIDANCE nodes when applicable.
- [ ] Actual matcher populates REALIZED_AS / CONTRADICTS edges.
- [ ] Causal linker populates CAUSED_BY edges with honest 0.5–0.8 confidence.
- [ ] KG traversal serves L5Step in <100ms for depth-3 walks.
- [ ] `GUIDANCE_CHECK` intent works for the covered tickers.
- [ ] Rolling summary and sticky slots stay coherent across a hand-tested 12-turn conversation.
- [ ] Eval Suite A stays ≥ 99%, B == 100%, C ≥ 4.1 (slight uplift expected).
- [ ] `make lint`, `make typecheck`, `make test` green.
