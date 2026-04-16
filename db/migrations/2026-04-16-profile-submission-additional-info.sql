BEGIN;

ALTER TABLE profile_submission_drafts
  ADD COLUMN IF NOT EXISTS additional_info text;

COMMIT;
