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
