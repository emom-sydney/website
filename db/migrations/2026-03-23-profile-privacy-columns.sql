BEGIN;

ALTER TABLE profiles
ADD COLUMN IF NOT EXISTS email text,
ADD COLUMN IF NOT EXISTS is_email_public boolean NOT NULL DEFAULT false,
ADD COLUMN IF NOT EXISTS is_bio_public boolean NOT NULL DEFAULT false,
ADD COLUMN IF NOT EXISTS is_name_public boolean NOT NULL DEFAULT false;

COMMIT;
