BEGIN;

CREATE TABLE IF NOT EXISTS artists (
  id integer PRIMARY KEY,
  stage_name text NOT NULL
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
  artist_id integer NOT NULL REFERENCES artists(id) ON DELETE CASCADE,
  UNIQUE (event_id, artist_id)
);

CREATE TABLE IF NOT EXISTS artist_images (
  id integer PRIMARY KEY,
  artist_id integer NOT NULL REFERENCES artists(id) ON DELETE CASCADE,
  image_url text NOT NULL
);

CREATE TABLE IF NOT EXISTS artist_social_profiles (
  id integer PRIMARY KEY,
  artist_id integer NOT NULL REFERENCES artists(id) ON DELETE CASCADE,
  social_platform_id integer NOT NULL REFERENCES social_platforms(id),
  profile_name text NOT NULL,
  UNIQUE (artist_id, social_platform_id, profile_name)
);

CREATE INDEX IF NOT EXISTS idx_events_type_id ON events(type_id);
CREATE INDEX IF NOT EXISTS idx_events_gallery_url ON events(gallery_url) WHERE gallery_url IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_performances_event_id ON performances(event_id);
CREATE INDEX IF NOT EXISTS idx_performances_artist_id ON performances(artist_id);
CREATE INDEX IF NOT EXISTS idx_artist_images_artist_id ON artist_images(artist_id);
CREATE INDEX IF NOT EXISTS idx_artist_social_profiles_artist_id ON artist_social_profiles(artist_id);
CREATE INDEX IF NOT EXISTS idx_artist_social_profiles_platform_id ON artist_social_profiles(social_platform_id);

CREATE OR REPLACE VIEW galleries AS
SELECT
  gallery_url,
  event_name,
  event_date
FROM events
WHERE gallery_url IS NOT NULL
ORDER BY event_date DESC, id DESC;

COMMIT;
