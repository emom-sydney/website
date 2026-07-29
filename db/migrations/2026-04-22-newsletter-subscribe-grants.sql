BEGIN;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'emom_forms_writer') THEN
    IF EXISTS (
      SELECT 1
      FROM information_schema.tables
      WHERE table_schema = 'public'
        AND table_name = 'newsletter_subscribe_requests'
    ) THEN
      EXECUTE $grant$
        -- Newsletter subscription writes use both tables in one transaction.
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
          action_tokens,
          newsletter_subscribe_requests
        TO emom_forms_writer
      $grant$;
    END IF;

    IF EXISTS (
      SELECT 1
      FROM information_schema.sequences
      WHERE sequence_schema = 'public'
        AND sequence_name = 'action_tokens_id_seq'
    ) THEN
      EXECUTE 'GRANT USAGE, SELECT, UPDATE ON SEQUENCE action_tokens_id_seq TO emom_forms_writer';
    END IF;

    IF EXISTS (
      SELECT 1
      FROM information_schema.sequences
      WHERE sequence_schema = 'public'
        AND sequence_name = 'newsletter_subscribe_requests_id_seq'
    ) THEN
      EXECUTE 'GRANT USAGE, SELECT, UPDATE ON SEQUENCE newsletter_subscribe_requests_id_seq TO emom_forms_writer';
    END IF;
  END IF;
END;
$$;

COMMIT;
