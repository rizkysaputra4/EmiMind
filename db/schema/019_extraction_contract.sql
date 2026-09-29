-- Migration 019: Extraction Contract Enrichment
-- Adds the columns and narrative table that let the MCP server build the
-- full extraction contract from the database instead of hardcoded Python.

ALTER TABLE metric_definitions
    ADD COLUMN IF NOT EXISTS search_hints            TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    ADD COLUMN IF NOT EXISTS extraction_guideline    TEXT,
    ADD COLUMN IF NOT EXISTS expected_segment_fields TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    ADD COLUMN IF NOT EXISTS statement_type          TEXT NOT NULL DEFAULT 'NOTE',
    ADD COLUMN IF NOT EXISTS label_bilingual         TEXT;

CREATE INDEX IF NOT EXISTS ix_metric_definitions_statement_type ON metric_definitions (statement_type);

CREATE TABLE IF NOT EXISTS extraction_narrative_rules (
    id                   BIGSERIAL PRIMARY KEY,
    topic                TEXT NOT NULL,
    sector_applicability TEXT[] NOT NULL DEFAULT ARRAY['ALL'],
    importance           TEXT NOT NULL DEFAULT 'HIGH',
    expected_section     TEXT NOT NULL DEFAULT 'MDA',
    target_note_description TEXT NOT NULL,
    guideline            TEXT NOT NULL,
    expected_link_types  TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_extraction_narrative_topic ON extraction_narrative_rules (topic);
CREATE INDEX IF NOT EXISTS ix_extraction_narrative_sectors ON extraction_narrative_rules USING gin (sector_applicability);

-- Fully-materialized view: caller passes sector_code and gets one row per
-- applicable metric with everything the LLM needs upfront.
CREATE OR REPLACE VIEW v_sector_extraction_contract_metrics AS
SELECT
    md.metric_id,
    md.name_en,
    md.name_id,
    md.label_bilingual,
    md.category,
    md.sector_applicability,
    md.importance,
    md.value_type,
    md.unit,
    md.flow_stock_type,
    md.extraction_mode,
    md.calculation_formula,
    md.dependencies,
    md.source_priority,
    md.synonyms_id,
    md.synonyms_en,
    md.search_hints,
    md.extraction_guideline,
    md.expected_segment_fields,
    md.statement_type
FROM metric_definitions md;

COMMENT ON VIEW v_sector_extraction_contract_metrics IS
  'Server queries: SELECT * FROM v_sector_extraction_contract_metrics WHERE sector_applicability && ARRAY[:sector, ''ALL'']';
