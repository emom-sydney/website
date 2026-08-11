BEGIN;

ALTER TABLE volunteer_roles
ADD COLUMN IF NOT EXISTS role_scope text;

UPDATE volunteer_roles
SET role_scope = COALESCE(role_scope, 'event');

ALTER TABLE volunteer_roles
ALTER COLUMN role_scope SET NOT NULL;

ALTER TABLE volunteer_roles
DROP CONSTRAINT IF EXISTS volunteer_roles_role_scope_check;

ALTER TABLE volunteer_roles
ADD CONSTRAINT volunteer_roles_role_scope_check
CHECK (role_scope IN ('event', 'general'));

ALTER TABLE profile_submission_volunteer_claims
ALTER COLUMN event_id DROP NOT NULL;

CREATE TABLE IF NOT EXISTS profile_submission_volunteer_general_claims (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  draft_id bigint NOT NULL REFERENCES profile_submission_drafts(id) ON DELETE CASCADE,
  role_key text NOT NULL REFERENCES volunteer_roles(role_key) ON DELETE CASCADE,
  submitted_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (draft_id, role_key)
);

CREATE TABLE IF NOT EXISTS volunteer_general_role_claims (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  role_key text NOT NULL REFERENCES volunteer_roles(role_key) ON DELETE CASCADE,
  profile_id integer NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  source_draft_id bigint REFERENCES profile_submission_drafts(id) ON DELETE SET NULL,
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'withdrawn')),
  claimed_at timestamptz NOT NULL DEFAULT now(),
  withdrawn_at timestamptz,
  UNIQUE (role_key, profile_id)
);

CREATE INDEX IF NOT EXISTS idx_profile_submission_volunteer_general_claims_draft_id
  ON profile_submission_volunteer_general_claims(draft_id);

CREATE INDEX IF NOT EXISTS idx_volunteer_general_role_claims_role_status_claimed
  ON volunteer_general_role_claims(role_key, status, claimed_at);

CREATE INDEX IF NOT EXISTS idx_volunteer_general_role_claims_profile_status
  ON volunteer_general_role_claims(profile_id, status);

INSERT INTO volunteer_roles (role_key, display_name, description, role_scope, default_capacity, sort_order)
VALUES
  ('mc', 'MC', 'Our regular MC Olly does an awesome job but we''d like to be able to give him a break from time to time. If you''ve got enthusiasm and personality and enjoy holding the mic, get in touch.', 'event', 1, 10),
  ('stage_manager', 'Stage manager', 'Help organise the acts to make the changeovers as smooth as possible.', 'event', 1, 20),
  ('lighting', 'Lighting', 'If you are an LD with a bit of spare time, come have a play with Mothership''s system while enjoying the good vibes. Bonus if you have spare fixtures to set up and show off.', 'event', 1, 30),
  ('vj', 'VJ', 'If you are a live video type person, bring your kit and enjoy riffing off the different styles of music presented. We''ll provide the projector.', 'event', 1, 40),
  ('sound', 'Sound', 'Critical to the success of the whole night. If you know your dBs from your DIs, get in touch.', 'event', 1, 50),
  ('video', 'Video', 'Help capture extra footage so regular camera volunteers can have a night off.', 'event', 1, 60),
  ('live_stream', 'Live Stream', 'If you know your way around OBS, come direct the live stream for us.', 'event', 1, 70),
  ('door_bitch', 'Door Bitch', 'Hold the door for guests, guide them in with wit and charm, and scan Humanitix tickets.', 'event', 1, 80),
  ('website', 'Web site', 'Help with the website stack (Eleventy, static hosting, CI/CD and related tooling).', 'general', 1, 90)
ON CONFLICT (role_key) DO UPDATE
SET
  display_name = EXCLUDED.display_name,
  description = EXCLUDED.description,
  role_scope = EXCLUDED.role_scope,
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
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'emom_forms_writer') THEN
    EXECUTE $grant$
      GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
        profile_submission_volunteer_general_claims,
        volunteer_general_role_claims
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
        profile_submission_volunteer_general_claims,
        volunteer_general_role_claims
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
        profile_submission_volunteer_general_claims,
        volunteer_general_role_claims
      TO emom_site_reader
    $grant$;
  END IF;
END;
$$;

COMMIT;
