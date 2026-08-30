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
