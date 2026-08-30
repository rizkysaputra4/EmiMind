# Appendix — Postgres Schemas

> Copy each SQL block **verbatim** into the corresponding `db/schema/NNN_*.sql` file. Do not paraphrase, rename, or reorder columns.

Milestone files reference sections here by name (e.g. `appendix-schemas.md § "002_financial_facts.sql"`).

---

## `000_extensions.sql` (M1)

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

---

## `001_documents.sql` (M1)

```sql
CREATE TABLE documents (
  id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  ticker          text NOT NULL,
  doc_type        text NOT NULL CHECK (doc_type IN ('PUBEX','FS_QUARTERLY','FS_ANNUAL','ANNUAL_REPORT')),
  period_end      date NOT NULL,
  fiscal_period   text NOT NULL,
  language        text NOT NULL CHECK (language IN ('id','en','mixed')),
  source_url      text,
  minio_key       text NOT NULL,
  doc_hash        text NOT NULL UNIQUE,
  page_count      int,
  ingested_at     timestamptz NOT NULL DEFAULT now(),
  parser_version  text,
  status          text NOT NULL DEFAULT 'raw'
                    CHECK (status IN ('raw','parsed','facts_extracted','failed'))
);

CREATE INDEX ix_documents_ticker_period ON documents(ticker, fiscal_period);
CREATE INDEX ix_documents_status        ON documents(status);
```

---

## `002_financial_facts.sql` (M1)

```sql
CREATE TABLE financial_facts (
  id                bigserial PRIMARY KEY,
  ticker            text NOT NULL,
  period_end        date NOT NULL,
  fiscal_period     text NOT NULL,
  statement         text NOT NULL CHECK (statement IN ('IS','BS','CF','EQ','NOTE')),
  concept_id        text NOT NULL,
  concept_local     text NOT NULL,
  value_numeric     numeric(24,4),
  unit              text,
  scale             int,
  segment           jsonb,
  period_type       text NOT NULL CHECK (period_type IN ('instant','duration_qtd','duration_ytd')),
  accounting_std    text,
  source_doc_id     uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  source_page       int,
  source_bbox       jsonb,
  extraction_conf   numeric(3,2) NOT NULL CHECK (extraction_conf BETWEEN 0.0 AND 1.0),
  extraction_method text NOT NULL CHECK (extraction_method IN ('xbrl','table_parser','llm_extract','manual')),
  needs_review      boolean NOT NULL DEFAULT false,
  is_restated       boolean NOT NULL DEFAULT false,
  supersedes_id     bigint REFERENCES financial_facts(id),
  created_at        timestamptz NOT NULL DEFAULT now()
);

-- Segment-aware uniqueness (default segment_key = '' when NULL)
CREATE UNIQUE INDEX ux_financial_facts_ticker_period_concept_seg
  ON financial_facts (ticker, fiscal_period, concept_id, (coalesce(segment->>'segment','')))
  WHERE is_restated = false;

CREATE INDEX ix_financial_facts_lookup   ON financial_facts (ticker, fiscal_period, concept_id);
CREATE INDEX ix_financial_facts_ts       ON financial_facts (concept_id, period_end);
CREATE INDEX ix_financial_facts_seg_gin  ON financial_facts USING gin(segment);
CREATE INDEX ix_financial_facts_review   ON financial_facts (needs_review) WHERE needs_review = true;
```

---

## `003_concept_map.sql` (M1)

```sql
CREATE TABLE concept_map (
  id                   bigserial PRIMARY KEY,
  local_label          text NOT NULL,
  sector               text,
  psak_version         text,
  canonical_concept_id text NOT NULL,
  confidence           numeric(3,2) NOT NULL DEFAULT 1.0,
  created_by           text NOT NULL DEFAULT 'manual',
  created_at           timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX ux_concept_map_label_sector
  ON concept_map (local_label, coalesce(sector,''));

CREATE INDEX ix_concept_map_local_trgm
  ON concept_map USING gin (local_label gin_trgm_ops);

CREATE INDEX ix_concept_map_canonical
  ON concept_map (canonical_concept_id);
```

---

## `004_worker_runs.sql` (M1)

```sql
CREATE TABLE worker_runs (
  doc_hash       text NOT NULL,
  worker_name    text NOT NULL,
  worker_version text NOT NULL,
  status         text NOT NULL CHECK (status IN ('ok','failed','running')),
  error          text,
  started_at     timestamptz NOT NULL DEFAULT now(),
  finished_at    timestamptz,
  PRIMARY KEY (doc_hash, worker_name, worker_version)
);

CREATE INDEX ix_worker_runs_status ON worker_runs(status) WHERE status <> 'ok';
```

---

## `005_xbrl_taxonomy.sql` (M2)

```sql
CREATE TABLE xbrl_alias (
  taxonomy_concept     text PRIMARY KEY,
  canonical_concept_id text NOT NULL,
  description          text,
  created_at           timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_xbrl_alias_canonical ON xbrl_alias(canonical_concept_id);
```

---

## `006_review_queue.sql` (M2)

```sql
CREATE TABLE concept_review (
  id                  bigserial PRIMARY KEY,
  ticker              text NOT NULL,
  doc_id              uuid REFERENCES documents(id) ON DELETE CASCADE,
  local_label         text NOT NULL,
  suggested_canonical text,
  similarity_score    numeric(3,2),
  status              text NOT NULL DEFAULT 'open'
                        CHECK (status IN ('open','resolved','rejected')),
  canonical_final     text,
  resolved_by         text,
  resolved_at         timestamptz,
  created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_concept_review_open ON concept_review(status) WHERE status = 'open';
CREATE UNIQUE INDEX ux_concept_review_label_doc ON concept_review(ticker, doc_id, local_label);
```

---

## `007_narrative_chunks.sql` (M2)

> Note: this file initially declares `embedding halfvec(768)`; M3.2.1a alters it to `halfvec(1024)` before embeddings are written. If M3 is being applied for the first time on a fresh install, prefer to bake `1024` in from the start.

```sql
CREATE TABLE narrative_chunks (
  id                 bigserial PRIMARY KEY,
  ticker             text NOT NULL,
  source_doc_id      uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  source_page        int NOT NULL,
  period_end         date,
  fiscal_period      text,
  section            text NOT NULL
                       CHECK (section IN ('MDA','RISK','GUIDANCE','MGMT_STMT','FOOTNOTE','OTHER')),
  language           text CHECK (language IN ('id','en','mixed')),
  text_original      text NOT NULL,
  text_en            text,
  speaker            text,
  claim_type         text CHECK (claim_type IN ('GUIDANCE','EXPLANATION','FORWARD_LOOKING','RISK','NEUTRAL')),
  mentioned_concepts text[] NOT NULL DEFAULT '{}',
  mentioned_periods  text[] NOT NULL DEFAULT '{}',
  embedding          halfvec(1024),
  tsv                tsvector,
  extracted_at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_narrative_chunks_hnsw
  ON narrative_chunks USING hnsw (embedding halfvec_cosine_ops);

CREATE INDEX ix_narrative_chunks_tsv
  ON narrative_chunks USING gin(tsv);

CREATE INDEX ix_narrative_chunks_concepts
  ON narrative_chunks USING gin(mentioned_concepts);

CREATE INDEX ix_narrative_chunks_lookup
  ON narrative_chunks(ticker, fiscal_period, section);
```

---

## `008_derived_metrics.sql` (M3)

```sql
CREATE TABLE peer_groups (
  id          text PRIMARY KEY,
  name        text NOT NULL,
  tickers     text[] NOT NULL,
  sector      text,
  sub_sector  text,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE derived_metrics (
  id              bigserial PRIMARY KEY,
  ticker          text NOT NULL,
  fiscal_period   text NOT NULL,
  metric_id       text NOT NULL,
  value_numeric   numeric(24,6),
  unit            text,
  inputs          jsonb,
  peer_group_id   text REFERENCES peer_groups(id),
  computed_at     timestamptz NOT NULL DEFAULT now(),
  recipe_version  text NOT NULL
);

CREATE UNIQUE INDEX ux_derived_metrics_key
  ON derived_metrics (ticker, fiscal_period, metric_id, coalesce(peer_group_id,''));

CREATE INDEX ix_derived_metrics_metric_period_val
  ON derived_metrics (metric_id, fiscal_period, value_numeric);

CREATE INDEX ix_derived_metrics_ticker_metric
  ON derived_metrics (ticker, metric_id, fiscal_period);
```

---

## `009_narrative_embedding_dim.sql` (M3, only if `007_...` used 768)

```sql
-- Only run if narrative_chunks.embedding is halfvec(768) and no rows yet have embeddings populated.
ALTER TABLE narrative_chunks
  ALTER COLUMN embedding TYPE halfvec(1024);
```

---

## `010_issuer_profile.sql` (M3)

```sql
CREATE TABLE issuer_profile (
  ticker              text PRIMARY KEY,
  name                text,
  sector              text,
  sub_sector          text,
  psak_ifrs_status    text,
  reporting_cadence   text,
  segments            jsonb,
  key_kpis            text[] NOT NULL DEFAULT '{}',
  profile_summary_en  text,
  profile_embedding   halfvec(1024),
  last_facts_period   text,
  last_refreshed_at   timestamptz,
  refresh_recipe_ver  text,
  top_metrics_hash    text,
  recent_events       jsonb NOT NULL DEFAULT '[]'
);

CREATE INDEX ix_issuer_profile_sector ON issuer_profile(sector);
```

---

## `011_sessions.sql` (M4)

```sql
CREATE TABLE chat_sessions (
  id                uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id           text,
  title             text,
  sticky_state      jsonb NOT NULL DEFAULT '{}',
  rolling_summary   text NOT NULL DEFAULT '',
  created_at        timestamptz NOT NULL DEFAULT now(),
  last_activity_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_chat_sessions_user ON chat_sessions(user_id, last_activity_at DESC);

CREATE TABLE conversation_turns (
  id                  bigserial PRIMARY KEY,
  session_id          uuid NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
  role                text NOT NULL CHECK (role IN ('user','assistant','tool')),
  content             text NOT NULL,
  retrieval_manifest  jsonb,
  token_usage         jsonb,
  latency_ms          int,
  ts                  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_conversation_turns_session_ts ON conversation_turns(session_id, ts);
```

---

## `012_kg_nodes_edges.sql` (M5)

```sql
CREATE TABLE kg_nodes (
  id            bigserial PRIMARY KEY,
  node_type     text NOT NULL
                  CHECK (node_type IN ('CLAIM','EVENT','GUIDANCE','ACTUAL',
                                       'COMPANY','METRIC','STANDARD_CHANGE')),
  ticker        text,
  fiscal_period text,
  payload       jsonb NOT NULL,
  source_ref    jsonb,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_kg_nodes_lookup ON kg_nodes(node_type, ticker, fiscal_period);

CREATE TABLE kg_edges (
  id            bigserial PRIMARY KEY,
  src_id        bigint NOT NULL REFERENCES kg_nodes(id) ON DELETE CASCADE,
  dst_id        bigint NOT NULL REFERENCES kg_nodes(id) ON DELETE CASCADE,
  edge_type     text NOT NULL
                  CHECK (edge_type IN ('PREDICTS','REALIZED_AS','CAUSED_BY',
                                       'PEER_OF','CONTRADICTS','REVISES','AFFECTS')),
  confidence    numeric(3,2) NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
  evidence_ref  jsonb,
  payload       jsonb,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_kg_edges_out  ON kg_edges(src_id, edge_type);
CREATE INDEX ix_kg_edges_in   ON kg_edges(dst_id, edge_type);
CREATE INDEX ix_kg_edges_type ON kg_edges(edge_type);
```

---

## `013_market.sql` (M6)

```sql
CREATE TABLE market_prices (
  ticker text NOT NULL,
  dt     date NOT NULL,
  o      numeric,
  h      numeric,
  l      numeric,
  c      numeric,
  v      bigint,
  PRIMARY KEY (ticker, dt)
);

CREATE INDEX ix_market_prices_dt ON market_prices(dt);

CREATE TABLE technical_state (
  ticker             text PRIMARY KEY,
  as_of              date NOT NULL,
  sma20              numeric,
  sma50              numeric,
  sma200             numeric,
  rsi14              numeric,
  macd               numeric,
  macd_signal        numeric,
  bb_upper           numeric,
  bb_lower           numeric,
  atr14              numeric,
  vol_avg20          numeric,
  dist_52wk_high_pct numeric,
  dist_52wk_low_pct  numeric,
  trend              text,
  momentum           text,
  volatility         text,
  volume_regime      text,
  regime_label       text,
  stale_as_of        date
);

CREATE TABLE technical_state_history (
  ticker       text NOT NULL,
  as_of        date NOT NULL,
  snapshot     jsonb NOT NULL,
  PRIMARY KEY (ticker, as_of)
);
```

---

## `014_users_auth.sql` (M7)

```sql
CREATE TABLE users (
  id         uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  email      text UNIQUE NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE auth_tokens (
  token      text PRIMARY KEY,
  user_id    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind       text NOT NULL CHECK (kind IN ('magic_link','session')),
  expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_auth_tokens_user ON auth_tokens(user_id);
CREATE INDEX ix_auth_tokens_exp  ON auth_tokens(expires_at);
```

---

## `015_citation_reports.sql` (M7)

```sql
CREATE TABLE citation_reports (
  id           bigserial PRIMARY KEY,
  user_id      uuid REFERENCES users(id) ON DELETE SET NULL,
  session_id   uuid REFERENCES chat_sessions(id) ON DELETE SET NULL,
  citation_str text NOT NULL,
  doc_id       uuid REFERENCES documents(id) ON DELETE SET NULL,
  fact_id      bigint REFERENCES financial_facts(id) ON DELETE SET NULL,
  chunk_id     bigint REFERENCES narrative_chunks(id) ON DELETE SET NULL,
  reason       text,
  status       text NOT NULL DEFAULT 'open'
                 CHECK (status IN ('open','triaged','resolved','rejected')),
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_citation_reports_status ON citation_reports(status);
```
