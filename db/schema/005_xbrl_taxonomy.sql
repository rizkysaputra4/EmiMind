CREATE TABLE xbrl_alias (
  taxonomy_concept     text PRIMARY KEY,
  canonical_concept_id text NOT NULL,
  description          text,
  created_at           timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_xbrl_alias_canonical ON xbrl_alias(canonical_concept_id);
