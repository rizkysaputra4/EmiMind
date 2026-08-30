-- Migration 017: MCP Ingestion Review Queue (Exception Handling)

CREATE TABLE IF NOT EXISTS ingest_review_queue (
    id                uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    ticker            text NOT NULL,
    fiscal_period     text NOT NULL,
    doc_id            uuid REFERENCES documents(id) ON DELETE CASCADE,
    issue_type        text NOT NULL,
    severity          text NOT NULL DEFAULT 'ERROR' CHECK (severity IN ('ERROR','WARNING','INFO')),
    validation_report jsonb NOT NULL,
    draft_payload     jsonb NOT NULL,
    status            text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','APPROVED','REJECTED','RESOLVED')),
    created_at        timestamptz NOT NULL DEFAULT now(),
    resolved_by       text,
    resolved_at       timestamptz
);

CREATE INDEX IF NOT EXISTS ix_ingest_review_queue_status ON ingest_review_queue(status) WHERE status = 'PENDING';
CREATE INDEX IF NOT EXISTS ix_ingest_review_queue_ticker ON ingest_review_queue(ticker, fiscal_period);
