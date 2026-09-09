BEGIN;

ALTER TABLE moderation_actions
DROP CONSTRAINT IF EXISTS moderation_actions_action_check;

ALTER TABLE moderation_actions
ADD CONSTRAINT moderation_actions_action_check
CHECK (action IN ('approved', 'denied', 'selected', 'standby', 'reserve', 'cancelled', 'declined'));

DROP INDEX IF EXISTS uq_moderation_actions_lineup_status;

CREATE UNIQUE INDEX uq_moderation_actions_lineup_status
  ON moderation_actions (draft_id, event_id, requested_date_id, action)
  WHERE action IN ('selected', 'standby', 'reserve', 'cancelled', 'declined');

COMMIT;
