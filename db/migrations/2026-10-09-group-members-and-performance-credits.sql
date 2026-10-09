BEGIN;

CREATE TABLE IF NOT EXISTS profile_editors (
  profile_id integer NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  editor_email text NOT NULL,
  editor_profile_id integer REFERENCES profiles(id) ON DELETE SET NULL,
  is_primary boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (profile_id, editor_email),
  CHECK (BTRIM(editor_email) <> '')
);

CREATE TABLE IF NOT EXISTS group_memberships (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  group_profile_id integer NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  member_profile_id integer REFERENCES profiles(id) ON DELETE SET NULL,
  member_display_name text NOT NULL,
  role_label text,
  sort_order integer NOT NULL DEFAULT 0,
  is_primary_contact boolean NOT NULL DEFAULT false,
  is_current boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  ended_at timestamptz,
  CHECK (BTRIM(member_display_name) <> ''),
  CHECK (group_profile_id <> member_profile_id),
  CHECK ((is_current AND ended_at IS NULL) OR (NOT is_current))
);

CREATE TABLE IF NOT EXISTS performance_credits (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  performance_id integer NOT NULL REFERENCES performances(id) ON DELETE CASCADE,
  person_profile_id integer REFERENCES profiles(id) ON DELETE SET NULL,
  credited_display_name text NOT NULL,
  credit_label text,
  sort_order integer NOT NULL DEFAULT 0,
  CHECK (BTRIM(credited_display_name) <> '')
);

CREATE TABLE IF NOT EXISTS profile_submission_associates (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  draft_id bigint NOT NULL REFERENCES profile_submission_drafts(id) ON DELETE CASCADE,
  client_key text NOT NULL,
  profile_id integer REFERENCES profiles(id) ON DELETE SET NULL,
  display_name text NOT NULL,
  sort_order integer NOT NULL DEFAULT 0,
  UNIQUE (draft_id, client_key),
  CHECK (BTRIM(client_key) <> ''),
  CHECK (BTRIM(display_name) <> '')
);

CREATE TABLE IF NOT EXISTS profile_submission_associate_social_profiles (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  associate_id bigint NOT NULL REFERENCES profile_submission_associates(id) ON DELETE CASCADE,
  social_platform_id integer NOT NULL REFERENCES social_platforms(id),
  profile_name text NOT NULL,
  sort_order integer NOT NULL DEFAULT 0,
  UNIQUE (associate_id, social_platform_id, profile_name)
);

CREATE TABLE IF NOT EXISTS profile_submission_group_memberships (
  draft_id bigint NOT NULL REFERENCES profile_submission_drafts(id) ON DELETE CASCADE,
  associate_id bigint NOT NULL REFERENCES profile_submission_associates(id) ON DELETE CASCADE,
  role_label text,
  sort_order integer NOT NULL DEFAULT 0,
  is_primary_contact boolean NOT NULL DEFAULT false,
  PRIMARY KEY (draft_id, associate_id)
);

ALTER TABLE requested_dates
  ADD COLUMN IF NOT EXISTS performer_display_name text;

CREATE TABLE IF NOT EXISTS profile_submission_guest_credits (
  requested_date_id bigint NOT NULL REFERENCES requested_dates(id) ON DELETE CASCADE,
  associate_id bigint NOT NULL REFERENCES profile_submission_associates(id) ON DELETE CASCADE,
  credit_label text,
  sort_order integer NOT NULL DEFAULT 0,
  PRIMARY KEY (requested_date_id, associate_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_profile_editors_email_ci
  ON profile_editors (profile_id, lower(editor_email));
CREATE UNIQUE INDEX IF NOT EXISTS uq_profile_editors_one_primary
  ON profile_editors (profile_id) WHERE is_primary;
CREATE INDEX IF NOT EXISTS idx_profile_editors_email_ci
  ON profile_editors (lower(editor_email));
CREATE UNIQUE INDEX IF NOT EXISTS uq_group_memberships_current_member
  ON group_memberships (group_profile_id, member_profile_id)
  WHERE is_current AND member_profile_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_group_memberships_primary_contact
  ON group_memberships (group_profile_id)
  WHERE is_current AND is_primary_contact;
CREATE INDEX IF NOT EXISTS idx_group_memberships_group_current_order
  ON group_memberships (group_profile_id, is_current, sort_order, id);
CREATE INDEX IF NOT EXISTS idx_group_memberships_member
  ON group_memberships (member_profile_id) WHERE member_profile_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_performance_credits_performance_order
  ON performance_credits (performance_id, sort_order, id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_performance_credits_person
  ON performance_credits (performance_id, person_profile_id)
  WHERE person_profile_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_performance_credits_person
  ON performance_credits (person_profile_id) WHERE person_profile_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_profile_submission_associates_draft
  ON profile_submission_associates (draft_id, sort_order, id);
CREATE INDEX IF NOT EXISTS idx_profile_submission_associate_socials_associate
  ON profile_submission_associate_social_profiles (associate_id, sort_order, id);
CREATE INDEX IF NOT EXISTS idx_profile_submission_guest_credits_requested_date
  ON profile_submission_guest_credits (requested_date_id, sort_order, associate_id);

INSERT INTO profile_editors (profile_id, editor_email, editor_profile_id, is_primary)
SELECT p.id, lower(BTRIM(p.email)), CASE WHEN p.profile_type = 'person' THEN p.id ELSE NULL END, true
FROM profiles p
WHERE NULLIF(BTRIM(p.email), '') IS NOT NULL
ON CONFLICT DO NOTHING;

CREATE OR REPLACE FUNCTION validate_artist_relationship_profiles()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  parent_type text;
  person_type text;
BEGIN
  IF TG_TABLE_NAME = 'group_memberships' THEN
    SELECT profile_type INTO parent_type FROM profiles WHERE id = NEW.group_profile_id;
    IF parent_type <> 'group' THEN
      RAISE EXCEPTION 'group_memberships.group_profile_id must reference a group profile';
    END IF;
    IF NEW.member_profile_id IS NOT NULL THEN
      SELECT profile_type INTO person_type FROM profiles WHERE id = NEW.member_profile_id;
      IF person_type <> 'person' THEN
        RAISE EXCEPTION 'group_memberships.member_profile_id must reference a person profile';
      END IF;
    END IF;
  ELSIF TG_TABLE_NAME = 'performance_credits' AND NEW.person_profile_id IS NOT NULL THEN
    SELECT profile_type INTO person_type FROM profiles WHERE id = NEW.person_profile_id;
    IF person_type <> 'person' THEN
      RAISE EXCEPTION 'performance_credits.person_profile_id must reference a person profile';
    END IF;
  ELSIF TG_TABLE_NAME = 'profile_editors' AND NEW.editor_profile_id IS NOT NULL THEN
    SELECT profile_type INTO person_type FROM profiles WHERE id = NEW.editor_profile_id;
    IF person_type <> 'person' THEN
      RAISE EXCEPTION 'profile_editors.editor_profile_id must reference a person profile';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_group_memberships_profile_types ON group_memberships;
CREATE TRIGGER trg_group_memberships_profile_types
BEFORE INSERT OR UPDATE ON group_memberships
FOR EACH ROW EXECUTE FUNCTION validate_artist_relationship_profiles();
DROP TRIGGER IF EXISTS trg_performance_credits_profile_types ON performance_credits;
CREATE TRIGGER trg_performance_credits_profile_types
BEFORE INSERT OR UPDATE ON performance_credits
FOR EACH ROW EXECUTE FUNCTION validate_artist_relationship_profiles();
DROP TRIGGER IF EXISTS trg_profile_editors_profile_types ON profile_editors;
CREATE TRIGGER trg_profile_editors_profile_types
BEFORE INSERT OR UPDATE ON profile_editors
FOR EACH ROW EXECUTE FUNCTION validate_artist_relationship_profiles();

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'emom_site_reader') THEN
    GRANT SELECT ON group_memberships, performance_credits TO emom_site_reader;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'emom_site_admin') THEN
    GRANT SELECT, INSERT, UPDATE, DELETE ON profile_editors, group_memberships, performance_credits,
      profile_submission_associates, profile_submission_associate_social_profiles,
      profile_submission_group_memberships, profile_submission_guest_credits TO emom_site_admin;
    GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO emom_site_admin;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'emom_forms_writer') THEN
    GRANT SELECT, INSERT, UPDATE, DELETE ON profile_editors, group_memberships, performance_credits,
      profile_submission_associates, profile_submission_associate_social_profiles,
      profile_submission_group_memberships, profile_submission_guest_credits TO emom_forms_writer;
    GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO emom_forms_writer;
  END IF;
END;
$$;

COMMIT;
