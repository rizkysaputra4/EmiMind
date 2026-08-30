ALTER TABLE documents DROP CONSTRAINT documents_status_check;
ALTER TABLE documents ADD CONSTRAINT documents_status_check
  CHECK (status IN ('pending_review','raw','parsed','facts_extracted','failed'));

ALTER TABLE documents ADD COLUMN proposed_metadata JSONB;
