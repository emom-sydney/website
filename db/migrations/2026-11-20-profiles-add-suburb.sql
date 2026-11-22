BEGIN;

ALTER TABLE profiles
  ADD COLUMN IF NOT EXISTS suburb text;

ALTER TABLE profiles
  ADD COLUMN IF NOT EXISTS is_location_public boolean NOT NULL DEFAULT false;

ALTER TABLE profile_submission_drafts
  ADD COLUMN IF NOT EXISTS suburb text;

ALTER TABLE profile_submission_drafts
  ADD COLUMN IF NOT EXISTS is_location_public boolean NOT NULL DEFAULT false;

COMMIT;
