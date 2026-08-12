BEGIN;

CREATE TABLE IF NOT EXISTS profile_qr_events (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  profile_id integer NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  action text NOT NULL CHECK (action IN ('scan', 'download')),
  occurred_at timestamptz NOT NULL DEFAULT now(),
  ip_address text,
  user_agent text,
  referrer text
);

CREATE INDEX IF NOT EXISTS idx_profile_qr_events_profile_occurred
  ON profile_qr_events(profile_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_profile_qr_events_occurred
  ON profile_qr_events(occurred_at);

INSERT INTO app_settings (key, value_json)
VALUES ('qr_tracking_retention_days', '90'::jsonb)
ON CONFLICT (key) DO NOTHING;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'emom_forms_writer') THEN
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE profile_qr_events TO emom_forms_writer;
    GRANT USAGE, SELECT ON SEQUENCE profile_qr_events_id_seq TO emom_forms_writer;
  END IF;

  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'emom_test_forms_writer') THEN
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE profile_qr_events TO emom_test_forms_writer;
    GRANT USAGE, SELECT ON SEQUENCE profile_qr_events_id_seq TO emom_test_forms_writer;
  END IF;
END;
$$;

COMMIT;
