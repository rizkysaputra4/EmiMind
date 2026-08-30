CREATE TABLE concept_map (
  id                   bigserial PRIMARY KEY,
  local_label          text NOT NULL,
  sector               text,
  psak_version         text,
  canonical_concept_id text NOT NULL,
  confidence           numeric(3,2) NOT NULL DEFAULT 1.0,
  created_by           text NOT NULL DEFAULT 'manual',
  created_at           timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX ux_concept_map_label_sector
  ON concept_map (local_label, coalesce(sector,''));

CREATE INDEX ix_concept_map_local_trgm
  ON concept_map USING gin (local_label gin_trgm_ops);

CREATE INDEX ix_concept_map_canonical
  ON concept_map (canonical_concept_id);
