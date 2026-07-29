BEGIN;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'emom_site_reader') THEN
    EXECUTE 'GRANT USAGE ON SCHEMA public TO emom_site_reader';
    EXECUTE 'GRANT SELECT ON ALL TABLES IN SCHEMA public TO emom_site_reader';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO emom_site_reader';
  END IF;
END;
$$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'emom_site_admin') THEN
    EXECUTE 'GRANT USAGE ON SCHEMA public TO emom_site_admin';
    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO emom_site_admin';
    EXECUTE 'GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO emom_site_admin';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO emom_site_admin';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO emom_site_admin';
  END IF;
END;
$$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'emom_forms_writer') THEN
    EXECUTE 'GRANT USAGE ON SCHEMA public TO emom_forms_writer';
    -- Keep this list limited to tables created by migrations dated 2026-04-01
    -- or earlier. Later migrations grant their own tables when they create them.
    EXECUTE $grant$
      GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
        app_settings,
        profiles,
        profile_roles,
        profile_social_profiles,
        social_platforms,
        events,
        performances,
        action_tokens,
        profile_submission_drafts,
        profile_submission_social_profiles,
        requested_dates,
        moderation_actions,
        event_performer_selections
      TO emom_forms_writer
    $grant$;
    EXECUTE 'GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO emom_forms_writer';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO emom_forms_writer';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO emom_forms_writer';
  END IF;
END;
$$;

COMMIT;
