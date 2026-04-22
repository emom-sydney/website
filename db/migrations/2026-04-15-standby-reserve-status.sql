BEGIN;

UPDATE event_performer_selections
SET status = 'standby'
WHERE status = 'backup';

UPDATE event_performer_selections
SET status = 'reserve'
WHERE status = 'cooldown_backup';

ALTER TABLE event_performer_selections
  DROP CONSTRAINT IF EXISTS event_performer_selections_status_check;

ALTER TABLE event_performer_selections
  ADD CONSTRAINT event_performer_selections_status_check
  CHECK (status IN ('selected', 'declined', 'cancelled', 'standby', 'reserve'));

COMMIT;
