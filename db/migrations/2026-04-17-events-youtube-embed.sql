BEGIN;

ALTER TABLE events
ADD COLUMN IF NOT EXISTS youtube_embed_url text;

COMMIT;
