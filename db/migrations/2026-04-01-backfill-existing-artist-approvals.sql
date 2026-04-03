BEGIN;

UPDATE profiles p
SET
  is_profile_approved = true,
  approved_at = COALESCE(approved_at, now()),
  profile_visible_from = NULL,
  profile_expires_on = COALESCE(profile_expires_on, CURRENT_DATE + INTERVAL '100 years')
WHERE EXISTS (
  SELECT 1
  FROM profile_roles pr
  WHERE pr.profile_id = p.id
    AND pr.role = 'artist'
);

COMMIT;
