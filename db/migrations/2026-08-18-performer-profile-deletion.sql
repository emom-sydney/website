BEGIN;

ALTER TABLE performances
  ADD COLUMN IF NOT EXISTS performer_display_name text;

UPDATE performances perf
SET performer_display_name = p.display_name
FROM profiles p
WHERE perf.profile_id = p.id
  AND perf.performer_display_name IS NULL;

ALTER TABLE performances
  ALTER COLUMN performer_display_name SET NOT NULL;

ALTER TABLE performances
  DROP CONSTRAINT IF EXISTS performances_profile_id_fkey;

ALTER TABLE performances
  ALTER COLUMN profile_id DROP NOT NULL;

ALTER TABLE performances
  ADD CONSTRAINT performances_profile_id_fkey
  FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE SET NULL;

COMMIT;
