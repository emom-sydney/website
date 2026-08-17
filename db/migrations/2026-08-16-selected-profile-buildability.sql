ALTER TABLE profiles
  ADD COLUMN IF NOT EXISTS is_profile_index_visible boolean NOT NULL DEFAULT false;

UPDATE profiles
SET is_profile_index_visible = true
WHERE is_profile_approved = true
  AND (profile_visible_from IS NULL OR profile_visible_from <= CURRENT_DATE)
  AND profile_expires_on >= CURRENT_DATE;
