BEGIN;

ALTER TABLE profile_roles
ADD COLUMN IF NOT EXISTS bio text,
ADD COLUMN IF NOT EXISTS is_bio_public boolean NOT NULL DEFAULT false;

UPDATE profile_roles pr
SET
  bio = p.bio,
  is_bio_public = COALESCE(p.is_bio_public, false)
FROM profiles p
WHERE pr.profile_id = p.id
  AND pr.role = 'artist'
  AND p.bio IS NOT NULL;

ALTER TABLE profiles
DROP COLUMN IF EXISTS bio,
DROP COLUMN IF EXISTS is_bio_public;

DROP TABLE IF EXISTS profile_bios;

COMMIT;
