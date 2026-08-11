BEGIN;

ALTER TABLE action_tokens
DROP CONSTRAINT IF EXISTS action_tokens_action_type_check;

DELETE FROM action_tokens
WHERE action_type IN (
  'registration_link',
  'moderation_approve',
  'moderation_deny',
  'admin_selection',
  'backup_selection',
  'volunteer_registration_link',
  'volunteer_moderation_approve',
  'volunteer_moderation_deny',
  'volunteer_claims_link'
);

ALTER TABLE action_tokens
ADD CONSTRAINT action_tokens_action_type_check
CHECK (
  action_type IN (
    'profile_submission_access',
    'availability_confirm',
    'availability_cancel',
    'newsletter_subscribe_confirm',
    'staff_login'
  )
);

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'events'
      AND column_name = 'admin_selection_email_sent_at'
  ) THEN
    ALTER TABLE events
    RENAME COLUMN admin_selection_email_sent_at TO lineup_selection_email_sent_at;
  END IF;
END;
$$;

DO $$
BEGIN
  IF to_regclass('public.admin_selection_locks') IS NOT NULL
     AND to_regclass('public.lineup_selection_locks') IS NULL THEN
    ALTER TABLE admin_selection_locks RENAME TO lineup_selection_locks;
  END IF;
END;
$$;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'admin_selection_locks_pkey'
      AND conrelid = 'lineup_selection_locks'::regclass
  ) THEN
    ALTER TABLE lineup_selection_locks
    RENAME CONSTRAINT admin_selection_locks_pkey TO lineup_selection_locks_pkey;
  END IF;
  IF EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'admin_selection_locks_event_id_fkey'
      AND conrelid = 'lineup_selection_locks'::regclass
  ) THEN
    ALTER TABLE lineup_selection_locks
    RENAME CONSTRAINT admin_selection_locks_event_id_fkey
      TO lineup_selection_locks_event_id_fkey;
  END IF;
  IF EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'admin_selection_locks_locked_by_profile_id_fkey'
      AND conrelid = 'lineup_selection_locks'::regclass
  ) THEN
    ALTER TABLE lineup_selection_locks
    RENAME CONSTRAINT admin_selection_locks_locked_by_profile_id_fkey
      TO lineup_selection_locks_locked_by_profile_id_fkey;
  END IF;
END;
$$;

DO $$
BEGIN
  IF to_regclass('public.idx_admin_selection_locks_expires_at') IS NOT NULL
     AND to_regclass('public.idx_lineup_selection_locks_expires_at') IS NULL THEN
    ALTER INDEX idx_admin_selection_locks_expires_at
    RENAME TO idx_lineup_selection_locks_expires_at;
  END IF;
END;
$$;

CREATE TABLE IF NOT EXISTS staff_sessions (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  session_token_hash text NOT NULL UNIQUE,
  csrf_token_hash text NOT NULL,
  profile_id integer NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_staff_sessions_profile_active
  ON staff_sessions(profile_id, expires_at)
  WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_staff_sessions_expires_at
  ON staff_sessions(expires_at);

INSERT INTO app_settings (key, value_json, updated_at)
SELECT 'lineup_selection_lead_days', value_json, updated_at
FROM app_settings
WHERE key = 'final_selection_lead_days'
ON CONFLICT (key) DO UPDATE
SET value_json = EXCLUDED.value_json,
    updated_at = EXCLUDED.updated_at;

INSERT INTO app_settings (key, value_json)
VALUES ('lineup_selection_lead_days', '7'::jsonb)
ON CONFLICT (key) DO NOTHING;

DELETE FROM app_settings WHERE key = 'final_selection_lead_days';

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'emom_forms_writer') THEN
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE staff_sessions TO emom_forms_writer;
    GRANT USAGE, SELECT ON SEQUENCE staff_sessions_id_seq TO emom_forms_writer;
  END IF;
END;
$$;

COMMIT;
