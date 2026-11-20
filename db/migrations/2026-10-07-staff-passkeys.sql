BEGIN;

CREATE TABLE IF NOT EXISTS staff_passkey_credentials (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  profile_id integer NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  credential_id text NOT NULL UNIQUE,
  public_key text NOT NULL,
  sign_count bigint NOT NULL DEFAULT 0,
  transports jsonb NOT NULL DEFAULT '[]'::jsonb,
  label text NOT NULL DEFAULT 'Passkey',
  created_at timestamptz NOT NULL DEFAULT now(),
  last_used_at timestamptz,
  revoked_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_staff_passkeys_profile
  ON staff_passkey_credentials(profile_id) WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS staff_passkey_challenges (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  challenge text NOT NULL UNIQUE,
  purpose text NOT NULL CHECK (purpose IN ('registration', 'authentication')),
  profile_id integer REFERENCES profiles(id) ON DELETE CASCADE,
  expires_at timestamptz NOT NULL,
  used_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_staff_passkey_challenges_expiry
  ON staff_passkey_challenges(expires_at);

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'emom_forms_writer') THEN
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE staff_passkey_credentials TO emom_forms_writer;
    GRANT USAGE, SELECT ON SEQUENCE staff_passkey_credentials_id_seq TO emom_forms_writer;
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE staff_passkey_challenges TO emom_forms_writer;
    GRANT USAGE, SELECT ON SEQUENCE staff_passkey_challenges_id_seq TO emom_forms_writer;
  END IF;
END;
$$;

COMMIT;
