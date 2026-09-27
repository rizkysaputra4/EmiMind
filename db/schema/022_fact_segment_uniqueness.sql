-- Migration 022: full-segment fact uniqueness
-- Replaces (segment->>'segment') with full jsonb equality so multi-dimensional segments participate in identity.

DROP INDEX IF EXISTS ux_financial_facts_ticker_period_concept_seg;

CREATE UNIQUE INDEX IF NOT EXISTS ux_financial_facts_identity
  ON financial_facts (ticker, fiscal_period, concept_id, (coalesce(segment, '{}'::jsonb)))
  WHERE is_restated = false;
