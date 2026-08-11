ALTER TABLE performances
ADD COLUMN IF NOT EXISTS sort_order integer NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_performances_event_order
ON performances(event_id, sort_order, id);

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'emom_forms_writer') THEN
    GRANT SELECT ON TABLE event_types TO emom_forms_writer;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'emom_site_reader') THEN
    GRANT SELECT ON TABLE event_types TO emom_site_reader;
  END IF;
END;
$$;
