BEGIN;

GRANT USAGE ON SCHEMA public TO emom_merch_writer;

GRANT SELECT ON TABLE
  app_settings,
  profiles,
  profile_roles,
  profile_social_profiles,
  social_platforms,
  events,
  performances
TO emom_merch_writer;

GRANT SELECT, INSERT, UPDATE ON TABLE
  action_tokens,
  profile_submission_drafts,
  requested_dates
TO emom_merch_writer;

GRANT SELECT, INSERT ON TABLE
  profile_submission_social_profiles,
  moderation_actions,
  event_performer_selections
TO emom_merch_writer;

GRANT INSERT, UPDATE ON TABLE
  profiles,
  profile_roles
TO emom_merch_writer;

GRANT INSERT, DELETE ON TABLE
  profile_social_profiles
TO emom_merch_writer;

GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO emom_merch_writer;

COMMIT;
