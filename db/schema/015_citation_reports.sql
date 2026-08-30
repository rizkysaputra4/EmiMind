-- Migration 015: Citation Reports for Fact and Extraction Audit (Milestone 7)

CREATE TABLE IF NOT EXISTS citation_reports (
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

CREATE INDEX IF NOT EXISTS ix_citation_reports_status ON citation_reports(status);
