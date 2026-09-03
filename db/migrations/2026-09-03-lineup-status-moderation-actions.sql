ALTER TABLE moderation_actions
  DROP CONSTRAINT IF EXISTS moderation_actions_action_check;

ALTER TABLE moderation_actions
  ADD CONSTRAINT moderation_actions_action_check
  CHECK (action IN ('approved', 'denied', 'selected', 'standby', 'reserve'));

ALTER TABLE moderation_actions
  ADD COLUMN IF NOT EXISTS event_id integer REFERENCES events(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS requested_date_id bigint REFERENCES requested_dates(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS notification_sent_at timestamptz;

CREATE UNIQUE INDEX IF NOT EXISTS uq_moderation_actions_lineup_status
  ON moderation_actions (draft_id, event_id, requested_date_id, action)
  WHERE action IN ('selected', 'standby', 'reserve');
