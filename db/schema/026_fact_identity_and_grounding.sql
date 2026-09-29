-- Migration 026: fact identity includes period_type; how each fact was grounded; narrative dedupe.
-- Idempotent: safe to run more than once.

-- 1. Fact identity: (ticker, fiscal_period, concept_id, period_type, full segment).
--    A quarter-only (duration_qtd) and a year-to-date (duration_ytd) value of the same concept
--    are different facts. Adding a column to the key can only make it less strict, so existing
--    rows cannot violate it.
DROP INDEX IF EXISTS ux_financial_facts_identity;

CREATE UNIQUE INDEX IF NOT EXISTS ux_financial_facts_identity_v2
  ON financial_facts (ticker, fiscal_period, concept_id, period_type, (coalesce(segment, '{}'::jsonb)))
  WHERE is_restated = false;

-- 2. How the committed value was verified against the filing (filled by commit_verified_report):
--    'cell'           the cited table cell holds the value at the table/page scale
--    'text'           the number is printed within ±3 lines of its label on the cited page
--    'ocr_unverified' OCR page where the number could not be confirmed (needs_review = true)
--    NULL             not verified by the MCP path (legacy rows, XBRL, table-parser worker)
ALTER TABLE financial_facts ADD COLUMN IF NOT EXISTS grounding text;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'financial_facts_grounding_check'
          AND conrelid = 'financial_facts'::regclass
    ) THEN
        ALTER TABLE financial_facts
          ADD CONSTRAINT financial_facts_grounding_check
          CHECK (grounding IS NULL OR grounding IN ('cell', 'text', 'ocr_unverified'));
    END IF;
END $$;

-- 3. Narrative dedupe: one chunk per (document, normalized text). text_hash is the SQL twin of
--    services.mcp.narrative_checks.narrative_md5 (lowercase, whitespace collapsed, trimmed) and
--    also serves the cross-issuer duplicate lookup.
ALTER TABLE narrative_chunks
  ADD COLUMN IF NOT EXISTS text_hash text
  GENERATED ALWAYS AS (md5(btrim(regexp_replace(lower(text_original), '\s+', ' ', 'g')))) STORED;

-- Remove pre-existing exact duplicates (keep the oldest row) before enforcing uniqueness.
DELETE FROM narrative_chunks a
USING narrative_chunks b
WHERE a.source_doc_id = b.source_doc_id
  AND a.text_hash = b.text_hash
  AND a.id > b.id;

CREATE UNIQUE INDEX IF NOT EXISTS ux_narrative_chunks_doc_text
  ON narrative_chunks (source_doc_id, text_hash);

CREATE INDEX IF NOT EXISTS ix_narrative_chunks_text_hash
  ON narrative_chunks (text_hash);
