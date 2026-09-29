-- Migration 020: Announcement (pengumuman) taxonomy
-- Expands the doc_type domain to include IDX announcement classes, adds
-- announcement metadata and classifier rule tables, and a per-doc-type
-- announcement contract table used by the MCP server to route extraction.

-- 1. Expand documents.doc_type domain --------------------------------------

ALTER TABLE documents
    DROP CONSTRAINT IF EXISTS documents_doc_type_check;

ALTER TABLE documents
    ADD CONSTRAINT documents_doc_type_check CHECK (doc_type IN (
        -- Financial classes (pre-M8, retained)
        'PUBEX', 'FS_QUARTERLY', 'FS_ANNUAL', 'ANNUAL_REPORT',
        -- Announcement classes (M8 Phase 2 bespoke)
        'DIVIDEND',
        'RIGHTS_ISSUE',
        'RUPS_RESULT',
        'MATERIAL_INFO',
        'BOND_ISSUE',
        'AFFILIATED_TX',
        'PRIVATE_PLACEMENT',
        'TENDER_OFFER',
        -- Announcement classes (M8 Phase 3 long tail — start as generic, promoted later)
        'INSIDER_TX',
        'BOARD_CHANGE',
        'SHARE_BUYBACK',
        'SUSPEND_NOTICE',
        'UNSUSPEND_NOTICE',
        'PUBLIC_EXPOSE',
        'ARTICLES_AMENDMENT',
        'NAME_CHANGE',
        'LISTING_ACTION',
        -- Safety net for anything the classifier cannot bucket
        'GENERIC_DISCLOSURE'
    ));

-- 2. Announcement metadata (per-doc details captured at ingest) -------------

CREATE TABLE IF NOT EXISTS announcement_metadata (
    doc_id                  UUID PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    announcement_title      TEXT NOT NULL,
    announcement_date       DATE NOT NULL,
    doc_class               TEXT NOT NULL,
    classifier_source       TEXT NOT NULL DEFAULT 'regex'
                             CHECK (classifier_source IN ('regex', 'llm', 'manual', 'sidecar')),
    classifier_confidence   NUMERIC(3, 2) NOT NULL DEFAULT 1.00,
    source_url              TEXT,
    idx_file_id             TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_announcement_metadata_date
    ON announcement_metadata (announcement_date DESC);
CREATE INDEX IF NOT EXISTS ix_announcement_metadata_doc_class
    ON announcement_metadata (doc_class);

-- 3. Classifier rules (regex title → doc_type) -----------------------------

CREATE TABLE IF NOT EXISTS announcement_class_rules (
    id          BIGSERIAL PRIMARY KEY,
    pattern     TEXT NOT NULL,
    doc_type    TEXT NOT NULL,
    priority    INT NOT NULL DEFAULT 100,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    notes       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_announcement_class_rules_priority
    ON announcement_class_rules (priority) WHERE is_active;

-- 4. Announcement extraction contracts (per doc_type, loaded from YAML) ----

CREATE TABLE IF NOT EXISTS announcement_extraction_contracts (
    doc_type            TEXT PRIMARY KEY,
    sector              TEXT NOT NULL DEFAULT 'UNIVERSAL',
    contract_json       JSONB NOT NULL,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    notes               TEXT
);
