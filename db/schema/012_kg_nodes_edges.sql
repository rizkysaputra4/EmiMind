-- Migration 012: Knowledge Graph Nodes and Edges (Layer 5)

CREATE TABLE IF NOT EXISTS kg_nodes (
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

CREATE INDEX IF NOT EXISTS ix_kg_nodes_lookup ON kg_nodes(node_type, ticker, fiscal_period);

CREATE TABLE IF NOT EXISTS kg_edges (
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

CREATE INDEX IF NOT EXISTS ix_kg_edges_out  ON kg_edges(src_id, edge_type);
CREATE INDEX IF NOT EXISTS ix_kg_edges_in   ON kg_edges(dst_id, edge_type);
CREATE INDEX IF NOT EXISTS ix_kg_edges_type ON kg_edges(edge_type);
