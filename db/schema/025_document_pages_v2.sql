-- Migration 025: document_pages v2 (M9 remediation, workstream A)
--
-- 1. document_pages.embedding_model: the model id that produced `embedding`
--    ('BAAI/bge-m3' in production, 'fake-hash-v1' in tests). NULL = legacy vector of
--    unknown origin (the M9 md5 hash vectors) and must be re-embedded.
-- 2. text_source may be 'ocr_failed': the page had no usable text layer and OCR raised
--    or produced < EMI_OCR_MIN_CHARS characters. Such pages are never silently blank.
--
-- Idempotent: safe to apply any number of times.

ALTER TABLE document_pages ADD COLUMN IF NOT EXISTS embedding_model text;

ALTER TABLE document_pages DROP CONSTRAINT IF EXISTS document_pages_text_source_check;
ALTER TABLE document_pages ADD CONSTRAINT document_pages_text_source_check
    CHECK (text_source IN ('pdf_text', 'ocr', 'ocr_failed'));

-- Finds pages still needing a (re-)embed quickly: embed_pages selects
-- `embedding IS NULL OR embedding_model IS DISTINCT FROM :model` per document.
CREATE INDEX IF NOT EXISTS ix_doc_pages_embedding_model
    ON document_pages (doc_id, embedding_model);

COMMENT ON COLUMN document_pages.embedding_model IS
    'Model id that produced embedding (e.g. BAAI/bge-m3); NULL = unknown/legacy, re-embed';
