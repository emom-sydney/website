BEGIN;

CREATE OR REPLACE FUNCTION validate_artist_relationship_profiles()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  parent_type text;
  person_type text;
BEGIN
  -- Branch on the triggering table before resolving table-specific NEW fields.
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
  ELSIF TG_TABLE_NAME = 'performance_credits' THEN
    IF NEW.person_profile_id IS NOT NULL THEN
      SELECT profile_type INTO person_type FROM profiles WHERE id = NEW.person_profile_id;
      IF person_type <> 'person' THEN
        RAISE EXCEPTION 'performance_credits.person_profile_id must reference a person profile';
      END IF;
    END IF;
  ELSIF TG_TABLE_NAME = 'profile_editors' THEN
    IF NEW.editor_profile_id IS NOT NULL THEN
      SELECT profile_type INTO person_type FROM profiles WHERE id = NEW.editor_profile_id;
      IF person_type <> 'person' THEN
        RAISE EXCEPTION 'profile_editors.editor_profile_id must reference a person profile';
      END IF;
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

COMMIT;
