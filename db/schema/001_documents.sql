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
