-- Migration 024: Fallback embedding column for document_pages when pgvector is not installed
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'document_pages' AND column_name = 'embedding'
        ) THEN
            ALTER TABLE document_pages ADD COLUMN embedding float8[];
        END IF;
    END IF;
END $$;
