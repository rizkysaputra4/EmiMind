-- Migration 014: Users and Authentication Tokens (Milestone 7)

CREATE TABLE IF NOT EXISTS users (
  id         uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  email      text UNIQUE NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS auth_tokens (
  token      text PRIMARY KEY,
  user_id    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind       text NOT NULL CHECK (kind IN ('magic_link','session')),
  expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_auth_tokens_user ON auth_tokens(user_id);
CREATE INDEX IF NOT EXISTS ix_auth_tokens_exp  ON auth_tokens(expires_at);
