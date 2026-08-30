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
  last_facts_period   text,
  last_refreshed_at   timestamptz,
  refresh_recipe_ver  text,
  top_metrics_hash    text,
  recent_events       jsonb NOT NULL DEFAULT '[]'
);

CREATE INDEX ix_issuer_profile_sector ON issuer_profile(sector);

-- Conditionally add profile_embedding column and HNSW index if vector extension is enabled
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        ALTER TABLE issuer_profile ADD COLUMN IF NOT EXISTS profile_embedding halfvec(1024);
        CREATE INDEX IF NOT EXISTS ix_issuer_profile_hnsw
          ON issuer_profile USING hnsw (profile_embedding halfvec_cosine_ops);
    END IF;
END $$;
