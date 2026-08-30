CREATE TABLE chat_sessions (
  id                uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id           text,
  title             text,
  sticky_state      jsonb NOT NULL DEFAULT '{}',
  rolling_summary   text NOT NULL DEFAULT '',
  created_at        timestamptz NOT NULL DEFAULT now(),
  last_activity_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_chat_sessions_user ON chat_sessions(user_id, last_activity_at DESC);

CREATE TABLE conversation_turns (
  id                  bigserial PRIMARY KEY,
  session_id          uuid NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
  role                text NOT NULL CHECK (role IN ('user','assistant','tool')),
  content             text NOT NULL,
  retrieval_manifest  jsonb,
  token_usage         jsonb,
  latency_ms          int,
  ts                  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_conversation_turns_session_ts ON conversation_turns(session_id, ts);
