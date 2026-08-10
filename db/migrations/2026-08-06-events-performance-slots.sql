BEGIN;

ALTER TABLE events
  ADD COLUMN IF NOT EXISTS performance_slots integer;

UPDATE events
SET performance_slots = 7
WHERE performance_slots IS NULL;

ALTER TABLE events
  ALTER COLUMN performance_slots SET DEFAULT 7,
  ALTER COLUMN performance_slots SET NOT NULL;

ALTER TABLE events
  DROP CONSTRAINT IF EXISTS events_performance_slots_positive;

ALTER TABLE events
  ADD CONSTRAINT events_performance_slots_positive CHECK (performance_slots > 0);

DELETE FROM app_settings
WHERE key = 'max_performers_per_event';

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'emom_test_site_admin') THEN
    GRANT UPDATE (performance_slots) ON TABLE public.events TO emom_test_site_admin;
  END IF;
END
$$;

COMMIT;
