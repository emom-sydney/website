BEGIN;

CREATE TABLE IF NOT EXISTS volunteer_roles (
  role_key text PRIMARY KEY,
  display_name text NOT NULL,
  description text NOT NULL,
  default_capacity integer NOT NULL CHECK (default_capacity >= 0),
  is_active boolean NOT NULL DEFAULT true,
  sort_order integer NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS event_volunteer_role_overrides (
  event_id integer NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  role_key text NOT NULL REFERENCES volunteer_roles(role_key) ON DELETE CASCADE,
  capacity_override integer CHECK (capacity_override >= 0),
  description_override text,
  PRIMARY KEY (event_id, role_key)
);

CREATE TABLE IF NOT EXISTS profile_submission_volunteer_claims (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  draft_id bigint NOT NULL REFERENCES profile_submission_drafts(id) ON DELETE CASCADE,
  event_id integer NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  role_key text NOT NULL REFERENCES volunteer_roles(role_key) ON DELETE CASCADE,
  submitted_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (draft_id, event_id, role_key)
);

CREATE TABLE IF NOT EXISTS event_volunteer_role_claims (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_id integer NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  role_key text NOT NULL REFERENCES volunteer_roles(role_key) ON DELETE CASCADE,
  profile_id integer NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  source_draft_id bigint REFERENCES profile_submission_drafts(id) ON DELETE SET NULL,
  status text NOT NULL DEFAULT 'selected' CHECK (
    status IN ('selected', 'standby', 'cancelled')
  ),
  claimed_at timestamptz NOT NULL DEFAULT now(),
  promoted_at timestamptz,
  cancelled_at timestamptz,
  UNIQUE (event_id, role_key, profile_id)
);

CREATE INDEX IF NOT EXISTS idx_volunteer_roles_active_sort
  ON volunteer_roles(is_active, sort_order, role_key);

CREATE INDEX IF NOT EXISTS idx_profile_submission_volunteer_claims_draft_id
  ON profile_submission_volunteer_claims(draft_id);

CREATE INDEX IF NOT EXISTS idx_profile_submission_volunteer_claims_event_role
  ON profile_submission_volunteer_claims(event_id, role_key);

CREATE INDEX IF NOT EXISTS idx_event_volunteer_role_claims_event_role_status_claimed
  ON event_volunteer_role_claims(event_id, role_key, status, claimed_at);

CREATE INDEX IF NOT EXISTS idx_event_volunteer_role_claims_profile_status
  ON event_volunteer_role_claims(profile_id, status);

INSERT INTO volunteer_roles (role_key, display_name, description, default_capacity, sort_order)
VALUES
  ('mc', 'MC', 'Our regular MC Olly does an awesome job but we''d like to be able to give him a break from time to time. If you''ve got enthusiasm and personality and enjoy holding the mic, get in touch.', 1, 10),
  ('stage_manager', 'Stage manager', 'Help organise the acts to make the changeovers as smooth as possible.', 1, 20),
  ('lighting', 'Lighting', 'If you are an LD with a bit of spare time, come have a play with Mothership''s system while enjoying the good vibes. Bonus if you have spare fixtures to set up and show off.', 1, 30),
  ('vj', 'VJ', 'If you are a live video type person, bring your kit and enjoy riffing off the different styles of music presented. We''ll provide the projector.', 1, 40),
  ('sound', 'Sound', 'Critical to the success of the whole night. If you know your dBs from your DIs, get in touch.', 1, 50),
  ('video', 'Video', 'Help capture extra footage so regular camera volunteers can have a night off.', 1, 60),
  ('live_stream', 'Live Stream', 'If you know your way around OBS, come direct the live stream for us.', 1, 70),
  ('door_bitch', 'Door Bitch', 'Hold the door for guests, guide them in with wit and charm, and scan Humanitix tickets.', 1, 80),
  ('website', 'Web site', 'Help with the website stack (Eleventy, static hosting, CI/CD and related tooling).', 1, 90)
ON CONFLICT (role_key) DO UPDATE
SET
  display_name = EXCLUDED.display_name,
  description = EXCLUDED.description,
  default_capacity = EXCLUDED.default_capacity,
  sort_order = EXCLUDED.sort_order,
  is_active = true;

UPDATE volunteer_roles
SET is_active = false
WHERE role_key NOT IN (
  'mc',
  'stage_manager',
  'lighting',
  'vj',
  'sound',
  'video',
  'live_stream',
  'door_bitch',
  'website'
);

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'action_tokens_action_type_check'
      AND conrelid = 'action_tokens'::regclass
  ) THEN
    EXECUTE 'ALTER TABLE action_tokens DROP CONSTRAINT action_tokens_action_type_check';
    EXECUTE $constraint$
      ALTER TABLE action_tokens
      ADD CONSTRAINT action_tokens_action_type_check CHECK (
        action_type IN (
          ''registration_link'',
          ''moderation_approve'',
          ''moderation_deny'',
          ''availability_confirm'',
          ''availability_cancel'',
          ''admin_selection'',
          ''backup_selection'',
          ''newsletter_subscribe_confirm'',
          ''volunteer_registration_link'',
          ''volunteer_moderation_approve'',
          ''volunteer_moderation_deny'',
          ''volunteer_claims_link''
        )
      )
    $constraint$;
  END IF;
END;
$$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'emom_forms_writer') THEN
    EXECUTE $grant$
      GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
        volunteer_roles,
        event_volunteer_role_overrides,
        profile_submission_volunteer_claims,
        event_volunteer_role_claims
      TO emom_forms_writer
    $grant$;
  END IF;
END;
$$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'emom_site_admin') THEN
    EXECUTE $grant$
      GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
        volunteer_roles,
        event_volunteer_role_overrides,
        profile_submission_volunteer_claims,
        event_volunteer_role_claims
      TO emom_site_admin
    $grant$;
  END IF;
END;
$$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'emom_site_reader') THEN
    EXECUTE $grant$
      GRANT SELECT ON TABLE
        volunteer_roles,
        event_volunteer_role_overrides,
        profile_submission_volunteer_claims,
        event_volunteer_role_claims
      TO emom_site_reader
    $grant$;
  END IF;
END;
$$;

COMMIT;
