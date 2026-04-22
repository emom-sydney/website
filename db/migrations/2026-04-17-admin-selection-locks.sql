BEGIN;

CREATE TABLE IF NOT EXISTS admin_selection_locks (
  event_id integer PRIMARY KEY REFERENCES events(id) ON DELETE CASCADE,
  locked_by_profile_id integer NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  lock_started_at timestamptz NOT NULL DEFAULT now(),
  lock_expires_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_admin_selection_locks_expires_at
  ON admin_selection_locks(lock_expires_at);

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'emom_forms_writer') THEN
    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE admin_selection_locks TO emom_forms_writer';
  END IF;
END;
$$;

COMMIT;
