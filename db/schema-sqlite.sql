PRAGMA foreign_keys = OFF;

BEGIN;

DROP TABLE IF EXISTS merch_interest_lines;
DROP TABLE IF EXISTS merch_interest_submissions;
DROP TABLE IF EXISTS merch_variants;
DROP TABLE IF EXISTS merch_items;
DROP TABLE IF EXISTS profile_social_profiles;
DROP TABLE IF EXISTS profile_images;
DROP TABLE IF EXISTS performances;
DROP TABLE IF EXISTS events;
DROP TABLE IF EXISTS social_platforms;
DROP TABLE IF EXISTS event_types;
DROP TABLE IF EXISTS profile_roles;
DROP TABLE IF EXISTS profiles;
DROP TABLE IF EXISTS action_tokens;
DROP TABLE IF EXISTS newsletter_subscribe_requests;

CREATE TABLE profiles (
  id INTEGER PRIMARY KEY,
  profile_type TEXT NOT NULL CHECK (profile_type IN ('person', 'group')),
  display_name TEXT NOT NULL,
  first_name TEXT,
  last_name TEXT,
  email TEXT,
  is_email_public INTEGER NOT NULL DEFAULT 0 CHECK (is_email_public IN (0, 1)),
  is_name_public INTEGER NOT NULL DEFAULT 0 CHECK (is_name_public IN (0, 1))
);

CREATE TABLE profile_roles (
  profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('artist', 'volunteer')),
  bio TEXT,
  is_bio_public INTEGER NOT NULL DEFAULT 0 CHECK (is_bio_public IN (0, 1)),
  PRIMARY KEY (profile_id, role)
);

CREATE TABLE event_types (
  id INTEGER PRIMARY KEY,
  description TEXT NOT NULL UNIQUE
);

CREATE TABLE social_platforms (
  id INTEGER PRIMARY KEY,
  platform_name TEXT NOT NULL UNIQUE,
  url_format TEXT NOT NULL
);

CREATE TABLE events (
  id INTEGER PRIMARY KEY,
  event_date TEXT NOT NULL,
  type_id INTEGER NOT NULL REFERENCES event_types(id),
  event_name TEXT NOT NULL,
  gallery_url TEXT UNIQUE,
  youtube_embed_url TEXT
);

CREATE TABLE performances (
  id INTEGER PRIMARY KEY,
  event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  UNIQUE (event_id, profile_id)
);

CREATE TABLE profile_images (
  id INTEGER PRIMARY KEY,
  profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  image_url TEXT NOT NULL
);

CREATE TABLE profile_social_profiles (
  id INTEGER PRIMARY KEY,
  profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  social_platform_id INTEGER NOT NULL REFERENCES social_platforms(id),
  profile_name TEXT NOT NULL,
  UNIQUE (profile_id, social_platform_id, profile_name)
);

CREATE TABLE merch_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  category TEXT NOT NULL CHECK (category IN ('tshirt', 'mug', 'keyring', 'tote_bag')),
  description TEXT,
  suggested_price NUMERIC NOT NULL CHECK (suggested_price >= 0),
  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
  sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE merch_variants (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  merch_item_id INTEGER NOT NULL REFERENCES merch_items(id) ON DELETE CASCADE,
  variant_label TEXT NOT NULL,
  style TEXT,
  size TEXT,
  color TEXT,
  image_url TEXT,
  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE merch_interest_submissions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL,
  comments TEXT,
  submitted_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE merch_interest_lines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  submission_id INTEGER NOT NULL REFERENCES merch_interest_submissions(id) ON DELETE CASCADE,
  merch_variant_id INTEGER NOT NULL REFERENCES merch_variants(id) ON DELETE CASCADE,
  quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
  submitted_price NUMERIC NOT NULL CHECK (submitted_price >= 0),
  UNIQUE (submission_id, merch_variant_id)
);

CREATE TABLE action_tokens (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  token_hash TEXT NOT NULL UNIQUE,
  action_type TEXT NOT NULL,
  email TEXT,
  profile_id INTEGER REFERENCES profiles(id) ON DELETE CASCADE,
  draft_id INTEGER,
  requested_date_id INTEGER,
  event_id INTEGER REFERENCES events(id) ON DELETE CASCADE,
  expires_at TEXT NOT NULL,
  used_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE newsletter_subscribe_requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  action_token_id INTEGER NOT NULL UNIQUE REFERENCES action_tokens(id) ON DELETE CASCADE,
  first_name TEXT,
  last_name TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_events_type_id ON events(type_id);
CREATE INDEX idx_events_gallery_url ON events(gallery_url) WHERE gallery_url IS NOT NULL;
CREATE INDEX idx_performances_event_id ON performances(event_id);
CREATE INDEX idx_performances_profile_id ON performances(profile_id);
CREATE INDEX idx_profile_images_profile_id ON profile_images(profile_id);
CREATE INDEX idx_profile_social_profiles_profile_id ON profile_social_profiles(profile_id);
CREATE INDEX idx_profile_social_profiles_platform_id ON profile_social_profiles(social_platform_id);
CREATE INDEX idx_profile_roles_role ON profile_roles(role);
CREATE INDEX idx_merch_variants_item_id ON merch_variants(merch_item_id);
CREATE UNIQUE INDEX idx_merch_variants_unique_option
  ON merch_variants (
    merch_item_id,
    COALESCE(style, ''),
    COALESCE(size, ''),
    COALESCE(color, ''),
    variant_label
  );
CREATE INDEX idx_merch_interest_lines_submission_id ON merch_interest_lines(submission_id);
CREATE INDEX idx_merch_interest_lines_variant_id ON merch_interest_lines(merch_variant_id);
CREATE INDEX idx_merch_interest_submissions_email ON merch_interest_submissions(email);
CREATE INDEX idx_action_tokens_expires_at
  ON action_tokens(expires_at)
  WHERE used_at IS NULL;
CREATE INDEX idx_action_tokens_event_action
  ON action_tokens(event_id, action_type);
CREATE INDEX idx_action_tokens_draft_action
  ON action_tokens(draft_id, action_type);
CREATE INDEX idx_newsletter_subscribe_requests_action_token_id
  ON newsletter_subscribe_requests(action_token_id);

DROP VIEW IF EXISTS galleries;
CREATE VIEW galleries AS
SELECT
  gallery_url,
  event_name,
  event_date
FROM events
WHERE gallery_url IS NOT NULL
ORDER BY event_date DESC, id DESC;

COMMIT;

PRAGMA foreign_keys = ON;
