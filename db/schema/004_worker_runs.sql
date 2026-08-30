CREATE TABLE worker_runs (
  doc_hash       text NOT NULL,
  worker_name    text NOT NULL,
  worker_version text NOT NULL,
  status         text NOT NULL CHECK (status IN ('ok','failed','running')),
  error          text,
  started_at     timestamptz NOT NULL DEFAULT now(),
  finished_at    timestamptz,
  PRIMARY KEY (doc_hash, worker_name, worker_version)
);

CREATE INDEX ix_worker_runs_status ON worker_runs(status) WHERE status <> 'ok';
