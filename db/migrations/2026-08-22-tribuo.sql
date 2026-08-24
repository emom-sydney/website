BEGIN;

ALTER TABLE profiles
  ADD COLUMN IF NOT EXISTS tribuo_tag text DEFAULT NULL;

ALTER TABLE profile_submission_drafts
  ADD COLUMN IF NOT EXISTS show_tribuo_link boolean NOT NULL DEFAULT false;

CREATE UNIQUE INDEX IF NOT EXISTS idx_profiles_tribuo_tag_unique
  ON profiles(tribuo_tag)
  WHERE tribuo_tag IS NOT NULL;

INSERT INTO app_settings (key, value_json)
VALUES ('tribuo_base_url', '"https://example.com"'::jsonb)
ON CONFLICT (key) DO NOTHING;

COMMIT;
