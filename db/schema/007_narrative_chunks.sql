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
  tsv                tsvector,
  extracted_at       timestamptz NOT NULL DEFAULT now()
);

-- Conditionally add embedding column and HNSW index if vector extension is enabled
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        ALTER TABLE narrative_chunks ADD COLUMN IF NOT EXISTS embedding halfvec(1024);
        CREATE INDEX IF NOT EXISTS ix_narrative_chunks_hnsw
          ON narrative_chunks USING hnsw (embedding halfvec_cosine_ops);
    END IF;
END $$;

CREATE INDEX ix_narrative_chunks_tsv
  ON narrative_chunks USING gin(tsv);

CREATE INDEX ix_narrative_chunks_concepts
  ON narrative_chunks USING gin(mentioned_concepts);

CREATE INDEX ix_narrative_chunks_lookup
  ON narrative_chunks(ticker, fiscal_period, section);
