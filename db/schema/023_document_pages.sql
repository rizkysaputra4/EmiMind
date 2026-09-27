-- Migration 023: Document Pages and Page Tables Schema
-- Enables page-level indexing, full-text search, semantic retrieval, and table grounding

CREATE TABLE IF NOT EXISTS document_pages (
    id            bigserial PRIMARY KEY,
    doc_id        uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_index    int  NOT NULL,          -- 1-based physical PDF page; this is what source_page means
    page_label    text,                   -- printed page number/label, if detectable (display only)
    page_text     text NOT NULL,
    text_source   text NOT NULL CHECK (text_source IN ('pdf_text', 'ocr')),
    language      text,                   -- 'id' | 'en' | 'mixed' via services/extraction/pdf.py::detect_language
    tsv           tsvector GENERATED ALWAYS AS (to_tsvector('simple', page_text)) STORED,
    image_key     text,                   -- MinIO key: thumbnails/{doc_id}/page_{page_index}.webp
    created_at    timestamptz DEFAULT now(),
    UNIQUE (doc_id, page_index)
);

CREATE INDEX IF NOT EXISTS ix_doc_pages_tsv  ON document_pages USING gin (tsv);

-- Conditionally add embedding column and HNSW index if vector extension is enabled
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        ALTER TABLE document_pages ADD COLUMN IF NOT EXISTS embedding halfvec(1024);
        CREATE INDEX IF NOT EXISTS ix_doc_pages_hnsw ON document_pages USING hnsw (embedding halfvec_cosine_ops);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS document_page_tables (
    id                bigserial PRIMARY KEY,
    doc_id            uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_index        int  NOT NULL,
    table_index       int  NOT NULL,          -- order of the table on the page
    extraction_method text NOT NULL,          -- 'camelot_lattice' | 'camelot_stream' | 'pdfplumber'
    confidence        numeric(3,2) NOT NULL,
    unit_hint         text,                   -- from detect_unit_from_header, e.g. 'IDR_MILLIONS'
    cells             jsonb NOT NULL,         -- [{row, col, text, value, bbox:[x0,y0,x1,y1], confidence}]
    created_at        timestamptz DEFAULT now(),
    UNIQUE (doc_id, page_index, table_index)
);
