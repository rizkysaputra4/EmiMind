-- Append-only audit trail for every PDF the ingest pipeline considers.
-- One row per ingest DECISION (inspect, skip, extract, error). Multiple rows
-- per document are expected — a file may be inspected, then later skipped
-- by the LLM triage, then re-inspected after a rerun.
--
-- Purpose: operator can answer "why didn't this file get extracted?" without
-- reading logs. Every skip decision, whether server-side (scope gate,
-- dedupe) or client-side (LLM decided this is admin), lands here.

CREATE TABLE document_processing_log (
  id            bigserial PRIMARY KEY,
  ticker        text,
  file_name     text NOT NULL,           -- basename only, human-readable
  file_path     text,                    -- full path when known
  doc_hash      text,                    -- null if never hashed (e.g. file not found)
  doc_id        uuid REFERENCES documents(id) ON DELETE SET NULL,
  action        text NOT NULL,           -- see values below
  reason        text,                    -- freetext explanation (from server or LLM)
  source        text NOT NULL,           -- 'inspect_document' | 'mark_document_skipped' | 'submit_draft_extraction' | 'commit_verified_report'
  metadata      jsonb NOT NULL DEFAULT '{}'::jsonb,  -- classifier hints, LLM confidence, etc.
  created_at    timestamptz NOT NULL DEFAULT now()
);

-- Action values (documented, not enforced — new values may be added without migration):
--   INSPECTED_AUTHORIZED       document passed scope gate + dedupe; ready for extraction
--   SKIPPED_OUT_OF_SCOPE       ticker not in issuer_profile
--   SKIPPED_DUPLICATE          hash already committed, file was archived
--   SKIPPED_NOT_FOUND          file_path did not resolve
--   SKIPPED_BY_LLM             extraction agent triaged this file as non-financial
--   EXTRACTED                  facts submitted (may still be pending validation)
--   COMMITTED                  facts committed to financial_facts
--   ERROR                      unrecoverable error during ingest

CREATE INDEX ix_processing_log_ticker      ON document_processing_log (ticker, created_at DESC);
CREATE INDEX ix_processing_log_action      ON document_processing_log (action, created_at DESC);
CREATE INDEX ix_processing_log_doc_hash    ON document_processing_log (doc_hash) WHERE doc_hash IS NOT NULL;
CREATE INDEX ix_processing_log_doc_id      ON document_processing_log (doc_id) WHERE doc_id IS NOT NULL;
CREATE INDEX ix_processing_log_created_at  ON document_processing_log (created_at DESC);
