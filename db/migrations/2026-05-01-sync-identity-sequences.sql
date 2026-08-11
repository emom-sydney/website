BEGIN;

-- Keep identity/sequence values ahead of existing primary keys.
-- This is non-destructive: it only advances sequences and does not modify table rows.
DO $$
DECLARE
  item record;
  sequence_name text;
  max_id bigint;
BEGIN
  FOR item IN
    SELECT *
    FROM (
      VALUES
        ('public', 'profiles', 'id'),
        ('public', 'profile_social_profiles', 'id'),
        ('public', 'profile_submission_drafts', 'id'),
        ('public', 'profile_submission_social_profiles', 'id'),
        ('public', 'requested_dates', 'id'),
        ('public', 'action_tokens', 'id'),
        ('public', 'moderation_actions', 'id'),
        ('public', 'event_performer_selections', 'id'),
        ('public', 'profile_submission_volunteer_claims', 'id'),
        ('public', 'profile_submission_volunteer_general_claims', 'id'),
        ('public', 'event_volunteer_role_claims', 'id'),
        ('public', 'volunteer_general_role_claims', 'id'),
        ('public', 'newsletter_subscribe_requests', 'id')
    ) AS identity_columns(schema_name, table_name, column_name)
  LOOP
    sequence_name := pg_get_serial_sequence(
      format('%I.%I', item.schema_name, item.table_name),
      item.column_name
    );

    IF sequence_name IS NULL THEN
      CONTINUE;
    END IF;

    EXECUTE format(
      'LOCK TABLE %I.%I IN SHARE ROW EXCLUSIVE MODE',
      item.schema_name,
      item.table_name
    );

    EXECUTE format(
      'SELECT COALESCE(MAX(%I), 0) FROM %I.%I',
      item.column_name,
      item.schema_name,
      item.table_name
    )
    INTO max_id;

    EXECUTE format(
      'SELECT setval(%L::regclass, %s, false)',
      sequence_name,
      max_id + 1
    );
  END LOOP;
END;
$$;

COMMIT;
