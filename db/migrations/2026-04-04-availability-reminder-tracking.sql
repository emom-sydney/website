BEGIN;

ALTER TABLE requested_dates
ADD COLUMN IF NOT EXISTS availability_email_sent_at timestamptz,
ADD COLUMN IF NOT EXISTS moderator_reminder_sent_at timestamptz;

COMMIT;
