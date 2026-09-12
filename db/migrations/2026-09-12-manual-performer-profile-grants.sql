-- Allow the backend writer to manage the profile image used by manual profile editing.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'emom_forms_writer') THEN
    GRANT SELECT, INSERT, DELETE ON TABLE profile_images TO emom_forms_writer;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'emom_test_forms_writer') THEN
    GRANT SELECT, INSERT, DELETE ON TABLE profile_images TO emom_test_forms_writer;
  END IF;
END
$$;
