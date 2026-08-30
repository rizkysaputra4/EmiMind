-- Migration 018: Industry-Aware Financial Metric Ontology Schema
-- Stores canonical metric definitions, dependencies, source priorities, and sector contracts.

CREATE TABLE IF NOT EXISTS metric_definitions (
    metric_id            TEXT PRIMARY KEY,
    name_en              TEXT NOT NULL,
    name_id              TEXT NOT NULL,
    category             TEXT NOT NULL,
    sector_applicability TEXT[] NOT NULL DEFAULT ARRAY['ALL'],
    importance           TEXT NOT NULL DEFAULT 'HIGH',
    value_type           TEXT NOT NULL DEFAULT 'MONETARY',
    unit                 TEXT NOT NULL DEFAULT 'IDR',
    flow_stock_type      TEXT NOT NULL DEFAULT 'FLOW_PERIOD',
    extraction_mode      TEXT NOT NULL DEFAULT 'EXTRACTED_RAW',
    calculation_formula  TEXT,
    dependencies         TEXT[] DEFAULT ARRAY[]::TEXT[],
    source_priority      TEXT[] NOT NULL DEFAULT ARRAY['FS_CORE_STATEMENT', 'FS_NOTES_DETAIL'],
    synonyms_id          TEXT[] DEFAULT ARRAY[]::TEXT[],
    synonyms_en          TEXT[] DEFAULT ARRAY[]::TEXT[],
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_metric_definitions_category ON metric_definitions (category);
CREATE INDEX IF NOT EXISTS ix_metric_definitions_importance ON metric_definitions (importance);
CREATE INDEX IF NOT EXISTS ix_metric_definitions_sectors ON metric_definitions USING gin (sector_applicability);

CREATE TABLE IF NOT EXISTS sector_metric_contracts (
    id                      BIGSERIAL PRIMARY KEY,
    sector_code             TEXT NOT NULL,
    module_name             TEXT NOT NULL,
    typical_note_title      TEXT NOT NULL,
    description             TEXT NOT NULL,
    target_concepts         TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    expected_segment_fields TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    guideline               TEXT NOT NULL,
    is_mandatory            BOOLEAN NOT NULL DEFAULT true,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_sector_metric_contracts ON sector_metric_contracts (sector_code, module_name);
