BEGIN;

CREATE SEQUENCE IF NOT EXISTS profiles_id_seq;
ALTER SEQUENCE profiles_id_seq OWNED BY profiles.id;
SELECT setval('profiles_id_seq', COALESCE((SELECT MAX(id) FROM profiles), 0) + 1, false);
ALTER TABLE profiles ALTER COLUMN id SET DEFAULT nextval('profiles_id_seq');

CREATE SEQUENCE IF NOT EXISTS profile_social_profiles_id_seq;
ALTER SEQUENCE profile_social_profiles_id_seq OWNED BY profile_social_profiles.id;
SELECT setval(
  'profile_social_profiles_id_seq',
  COALESCE((SELECT MAX(id) FROM profile_social_profiles), 0) + 1,
  false
);
ALTER TABLE profile_social_profiles ALTER COLUMN id SET DEFAULT nextval('profile_social_profiles_id_seq');

COMMIT;
