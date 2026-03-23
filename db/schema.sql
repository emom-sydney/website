BEGIN;

CREATE TABLE IF NOT EXISTS profiles (
  id integer PRIMARY KEY,
  profile_type text NOT NULL CHECK (profile_type IN ('person', 'group')),
  display_name text NOT NULL,
  first_name text,
  last_name text,
  email text,
  is_email_public boolean NOT NULL DEFAULT false,
  is_name_public boolean NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS profile_roles (
  profile_id integer NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  role text NOT NULL CHECK (role IN ('artist', 'volunteer')),
  bio text,
  is_bio_public boolean NOT NULL DEFAULT false,
  PRIMARY KEY (profile_id, role)
);

CREATE TABLE IF NOT EXISTS event_types (
  id integer PRIMARY KEY,
  description text NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS social_platforms (
  id integer PRIMARY KEY,
  platform_name text NOT NULL UNIQUE,
  url_format text NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
  id integer PRIMARY KEY,
  event_date date NOT NULL,
  type_id integer NOT NULL REFERENCES event_types(id),
  event_name text NOT NULL,
  gallery_url text UNIQUE
);

CREATE TABLE IF NOT EXISTS performances (
  id integer PRIMARY KEY,
  event_id integer NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  profile_id integer NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  UNIQUE (event_id, profile_id)
);

CREATE TABLE IF NOT EXISTS profile_images (
  id integer PRIMARY KEY,
  profile_id integer NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  image_url text NOT NULL
);

CREATE TABLE IF NOT EXISTS profile_social_profiles (
  id integer PRIMARY KEY,
  profile_id integer NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  social_platform_id integer NOT NULL REFERENCES social_platforms(id),
  profile_name text NOT NULL,
  UNIQUE (profile_id, social_platform_id, profile_name)
);

CREATE INDEX IF NOT EXISTS idx_events_type_id ON events(type_id);
CREATE INDEX IF NOT EXISTS idx_events_gallery_url ON events(gallery_url) WHERE gallery_url IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_performances_event_id ON performances(event_id);
CREATE INDEX IF NOT EXISTS idx_performances_profile_id ON performances(profile_id);
CREATE INDEX IF NOT EXISTS idx_profile_images_profile_id ON profile_images(profile_id);
CREATE INDEX IF NOT EXISTS idx_profile_social_profiles_profile_id ON profile_social_profiles(profile_id);
CREATE INDEX IF NOT EXISTS idx_profile_social_profiles_platform_id ON profile_social_profiles(social_platform_id);
CREATE INDEX IF NOT EXISTS idx_profile_roles_role ON profile_roles(role);

CREATE OR REPLACE VIEW galleries AS
SELECT
  gallery_url,
  event_name,
  event_date
FROM events
WHERE gallery_url IS NOT NULL
ORDER BY event_date DESC, id DESC;

COMMIT;
