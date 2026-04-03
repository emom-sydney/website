BEGIN;

ALTER TABLE profiles
ADD COLUMN IF NOT EXISTS contact_phone text,
ADD COLUMN IF NOT EXISTS is_profile_approved boolean NOT NULL DEFAULT false,
ADD COLUMN IF NOT EXISTS is_moderator boolean NOT NULL DEFAULT false,
ADD COLUMN IF NOT EXISTS is_admin boolean NOT NULL DEFAULT false,
ADD COLUMN IF NOT EXISTS profile_visible_from date,
ADD COLUMN IF NOT EXISTS profile_expires_on date NOT NULL DEFAULT (CURRENT_DATE + INTERVAL '100 years'),
ADD COLUMN IF NOT EXISTS approved_at timestamptz,
ADD COLUMN IF NOT EXISTS approved_by_profile_id integer REFERENCES profiles(id);

ALTER TABLE profiles
DROP CONSTRAINT IF EXISTS profiles_moderator_person_check,
DROP CONSTRAINT IF EXISTS profiles_admin_person_check;

ALTER TABLE profiles
ADD CONSTRAINT profiles_moderator_person_check
CHECK (NOT is_moderator OR profile_type = 'person'),
ADD CONSTRAINT profiles_admin_person_check
CHECK (NOT is_admin OR profile_type = 'person');

CREATE TABLE IF NOT EXISTS profile_submission_drafts (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  profile_id integer REFERENCES profiles(id) ON DELETE CASCADE,
  email text NOT NULL,
  profile_type text NOT NULL CHECK (profile_type IN ('person', 'group')),
  display_name text NOT NULL,
  first_name text,
  last_name text,
  contact_phone text,
  is_email_public boolean NOT NULL DEFAULT false,
  is_name_public boolean NOT NULL DEFAULT false,
  artist_bio text,
  is_artist_bio_public boolean NOT NULL DEFAULT false,
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'denied', 'superseded')),
  submitted_at timestamptz NOT NULL DEFAULT now(),
  submitted_by_email text NOT NULL,
  reviewed_at timestamptz,
  reviewed_by_profile_id integer REFERENCES profiles(id),
  denial_reason text
);

CREATE TABLE IF NOT EXISTS profile_submission_social_profiles (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  draft_id bigint NOT NULL REFERENCES profile_submission_drafts(id) ON DELETE CASCADE,
  social_platform_id integer NOT NULL REFERENCES social_platforms(id),
  profile_name text NOT NULL,
  sort_order integer NOT NULL DEFAULT 0,
  UNIQUE (draft_id, social_platform_id, profile_name)
);

CREATE TABLE IF NOT EXISTS requested_dates (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  draft_id bigint NOT NULL REFERENCES profile_submission_drafts(id) ON DELETE CASCADE,
  event_id integer NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  status text NOT NULL DEFAULT 'requested' CHECK (
    status IN ('requested', 'availability_confirmed', 'availability_cancelled', 'selected', 'not_selected', 'withdrawn')
  ),
  requested_at timestamptz NOT NULL DEFAULT now(),
  availability_responded_at timestamptz,
  selected_at timestamptz,
  selected_by_profile_id integer REFERENCES profiles(id),
  UNIQUE (draft_id, event_id)
);

CREATE TABLE IF NOT EXISTS action_tokens (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  token_hash text NOT NULL UNIQUE,
  action_type text NOT NULL CHECK (
    action_type IN (
      'registration_link',
      'moderation_approve',
      'moderation_deny',
      'availability_confirm',
      'availability_cancel',
      'admin_selection'
    )
  ),
  email text,
  profile_id integer REFERENCES profiles(id) ON DELETE CASCADE,
  draft_id bigint REFERENCES profile_submission_drafts(id) ON DELETE CASCADE,
  requested_date_id bigint REFERENCES requested_dates(id) ON DELETE CASCADE,
  event_id integer REFERENCES events(id) ON DELETE CASCADE,
  expires_at timestamptz NOT NULL,
  used_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS moderation_actions (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  draft_id bigint NOT NULL REFERENCES profile_submission_drafts(id) ON DELETE CASCADE,
  moderator_profile_id integer NOT NULL REFERENCES profiles(id),
  action text NOT NULL CHECK (action IN ('approved', 'denied')),
  reason text,
  acted_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS event_performer_selections (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_id integer NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  profile_id integer NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  requested_date_id bigint REFERENCES requested_dates(id) ON DELETE SET NULL,
  slot_number integer,
  status text NOT NULL DEFAULT 'selected' CHECK (status IN ('selected', 'declined', 'cancelled', 'backup')),
  selected_at timestamptz NOT NULL DEFAULT now(),
  selected_by_profile_id integer REFERENCES profiles(id),
  notes text,
  UNIQUE (event_id, profile_id)
);

CREATE TABLE IF NOT EXISTS app_settings (
  key text PRIMARY KEY,
  value_json jsonb NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_profiles_email ON profiles(email);
CREATE INDEX IF NOT EXISTS idx_profiles_is_profile_approved ON profiles(is_profile_approved);
CREATE INDEX IF NOT EXISTS idx_profiles_visible_window
  ON profiles(profile_visible_from, profile_expires_on);
CREATE INDEX IF NOT EXISTS idx_profile_submission_drafts_profile_status
  ON profile_submission_drafts(profile_id, status);
CREATE INDEX IF NOT EXISTS idx_profile_submission_drafts_email_status
  ON profile_submission_drafts(email, status);
CREATE INDEX IF NOT EXISTS idx_profile_submission_social_profiles_draft_id
  ON profile_submission_social_profiles(draft_id);
CREATE INDEX IF NOT EXISTS idx_requested_dates_event_status
  ON requested_dates(event_id, status);
CREATE INDEX IF NOT EXISTS idx_requested_dates_draft_id
  ON requested_dates(draft_id);
CREATE INDEX IF NOT EXISTS idx_action_tokens_expires_at
  ON action_tokens(expires_at)
  WHERE used_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_action_tokens_event_action
  ON action_tokens(event_id, action_type);
CREATE INDEX IF NOT EXISTS idx_action_tokens_draft_action
  ON action_tokens(draft_id, action_type);
CREATE INDEX IF NOT EXISTS idx_moderation_actions_draft_id
  ON moderation_actions(draft_id);
CREATE INDEX IF NOT EXISTS idx_event_performer_selections_event_status
  ON event_performer_selections(event_id, status);

INSERT INTO app_settings (key, value_json)
VALUES
  ('performer_request_cooldown_events', '3'::jsonb),
  ('availability_confirmation_lead_days', '10'::jsonb),
  ('final_selection_lead_days', '7'::jsonb),
  ('action_token_ttl_hours', '24'::jsonb),
  ('max_performers_per_event', '7'::jsonb)
ON CONFLICT (key) DO NOTHING;

UPDATE profiles p
SET
  is_profile_approved = true,
  approved_at = COALESCE(approved_at, now()),
  profile_visible_from = NULL,
  profile_expires_on = COALESCE(profile_expires_on, CURRENT_DATE + INTERVAL '100 years')
WHERE EXISTS (
  SELECT 1
  FROM profile_roles pr
  WHERE pr.profile_id = p.id
    AND pr.role = 'artist'
);

CREATE OR REPLACE FUNCTION ensure_staff_profile_is_valid(target_profile_id integer)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
  profile_row profiles%ROWTYPE;
BEGIN
  IF target_profile_id IS NULL THEN
    RETURN;
  END IF;

  SELECT *
  INTO profile_row
  FROM profiles
  WHERE id = target_profile_id;

  IF NOT FOUND THEN
    RETURN;
  END IF;

  IF NOT (profile_row.is_moderator OR profile_row.is_admin) THEN
    RETURN;
  END IF;

  IF profile_row.profile_type <> 'person' THEN
    RAISE EXCEPTION 'Only person profiles can be moderators or admins.';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM profile_roles pr
    WHERE pr.profile_id = target_profile_id
      AND pr.role = 'volunteer'
  ) THEN
    RAISE EXCEPTION 'Moderator/admin profiles must also have the volunteer role.';
  END IF;
END;
$$;

CREATE OR REPLACE FUNCTION trigger_validate_staff_profile_from_profiles()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  PERFORM ensure_staff_profile_is_valid(NEW.id);
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION trigger_validate_staff_profile_from_roles()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    PERFORM ensure_staff_profile_is_valid(OLD.profile_id);
    RETURN OLD;
  END IF;

  PERFORM ensure_staff_profile_is_valid(NEW.profile_id);
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_profiles_ensure_staff_roles ON profiles;
CREATE TRIGGER trg_profiles_ensure_staff_roles
AFTER INSERT OR UPDATE OF profile_type, is_moderator, is_admin
ON profiles
FOR EACH ROW
EXECUTE FUNCTION trigger_validate_staff_profile_from_profiles();

DROP TRIGGER IF EXISTS trg_profile_roles_ensure_staff_roles ON profile_roles;
CREATE TRIGGER trg_profile_roles_ensure_staff_roles
AFTER INSERT OR UPDATE OF role OR DELETE
ON profile_roles
FOR EACH ROW
EXECUTE FUNCTION trigger_validate_staff_profile_from_roles();

COMMIT;
