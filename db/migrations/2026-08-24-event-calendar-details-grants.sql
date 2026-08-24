BEGIN;

-- Catch-up migration for installations where the event-details migration was
-- applied before the new table grants were added, or where test and production
-- databases use different backend roles.
DO $$
BEGIN
  IF to_regclass('public.locations') IS NULL THEN
    RAISE EXCEPTION 'locations table does not exist; apply 2026-08-24-event-calendar-details.sql first';
  END IF;

  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'emom_forms_writer') THEN
    GRANT USAGE ON SCHEMA public TO emom_forms_writer;
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.locations TO emom_forms_writer;
    GRANT USAGE, SELECT, UPDATE ON SEQUENCE public.locations_id_seq TO emom_forms_writer;
  END IF;

  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'emom_test_forms_writer') THEN
    GRANT USAGE ON SCHEMA public TO emom_test_forms_writer;
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.locations TO emom_test_forms_writer;
    GRANT USAGE, SELECT, UPDATE ON SEQUENCE public.locations_id_seq TO emom_test_forms_writer;
  END IF;
END;
$$;

COMMIT;
