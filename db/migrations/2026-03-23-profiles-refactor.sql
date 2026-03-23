BEGIN;

ALTER TABLE artists RENAME TO profiles;
ALTER TABLE profiles RENAME COLUMN stage_name TO display_name;

ALTER TABLE profiles
ADD COLUMN profile_type text NOT NULL DEFAULT 'person',
ADD COLUMN first_name text,
ADD COLUMN last_name text,
ADD COLUMN bio text;

ALTER TABLE profiles
ADD CONSTRAINT profiles_profile_type_check
CHECK (profile_type IN ('person', 'group'));

CREATE TABLE IF NOT EXISTS profile_roles (
  profile_id integer NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  role text NOT NULL,
  PRIMARY KEY (profile_id, role),
  CONSTRAINT profile_roles_role_check CHECK (role IN ('artist', 'volunteer'))
);

INSERT INTO profile_roles (profile_id, role)
SELECT id, 'artist'
FROM profiles
ON CONFLICT DO NOTHING;

ALTER TABLE performances RENAME COLUMN artist_id TO profile_id;
ALTER TABLE artist_images RENAME TO profile_images;
ALTER TABLE profile_images RENAME COLUMN artist_id TO profile_id;
ALTER TABLE artist_social_profiles RENAME TO profile_social_profiles;
ALTER TABLE profile_social_profiles RENAME COLUMN artist_id TO profile_id;

DROP INDEX IF EXISTS idx_performances_artist_id;
DROP INDEX IF EXISTS idx_artist_images_artist_id;
DROP INDEX IF EXISTS idx_artist_social_profiles_artist_id;
DROP INDEX IF EXISTS idx_artist_social_profiles_platform_id;

CREATE INDEX IF NOT EXISTS idx_performances_profile_id ON performances(profile_id);
CREATE INDEX IF NOT EXISTS idx_profile_images_profile_id ON profile_images(profile_id);
CREATE INDEX IF NOT EXISTS idx_profile_social_profiles_profile_id ON profile_social_profiles(profile_id);
CREATE INDEX IF NOT EXISTS idx_profile_social_profiles_platform_id ON profile_social_profiles(social_platform_id);
CREATE INDEX IF NOT EXISTS idx_profile_roles_role ON profile_roles(role);

COMMIT;
