-- Ensure narrative_chunks.embedding is halfvec(1024) if vector extension is enabled
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'narrative_chunks' AND column_name = 'embedding'
        ) THEN
            -- Safe alter column type if already exists
            BEGIN
                ALTER TABLE narrative_chunks ALTER COLUMN embedding TYPE halfvec(1024);
            EXCEPTION
                WHEN OTHERS THEN NULL;
            END;
        ELSE
            ALTER TABLE narrative_chunks ADD COLUMN embedding halfvec(1024);
            CREATE INDEX IF NOT EXISTS ix_narrative_chunks_hnsw
              ON narrative_chunks USING hnsw (embedding halfvec_cosine_ops);
        END IF;
    END IF;
END $$;
