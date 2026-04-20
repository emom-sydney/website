CREATE TABLE IF NOT EXISTS action_tokens (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  token_hash text NOT NULL UNIQUE,
  action_type text NOT NULL,
  email text,
  profile_id integer REFERENCES profiles(id) ON DELETE CASCADE,
  draft_id bigint,
  requested_date_id bigint,
  event_id integer REFERENCES events(id) ON DELETE CASCADE,
  expires_at timestamptz NOT NULL,
  used_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS newsletter_subscribe_requests (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  action_token_id bigint NOT NULL UNIQUE REFERENCES action_tokens(id) ON DELETE CASCADE,
  first_name text,
  last_name text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_action_tokens_expires_at
  ON action_tokens(expires_at)
  WHERE used_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_action_tokens_event_action
  ON action_tokens(event_id, action_type);

CREATE INDEX IF NOT EXISTS idx_action_tokens_draft_action
  ON action_tokens(draft_id, action_type);

CREATE INDEX IF NOT EXISTS idx_newsletter_subscribe_requests_action_token_id
  ON newsletter_subscribe_requests(action_token_id);

ALTER TABLE action_tokens
DROP CONSTRAINT IF EXISTS action_tokens_action_type_check;
