BEGIN;

ALTER TABLE event_performer_selections
  DROP CONSTRAINT IF EXISTS event_performer_selections_status_check;

ALTER TABLE event_performer_selections
  ADD CONSTRAINT event_performer_selections_status_check
  CHECK (status IN ('selected', 'declined', 'cancelled', 'backup', 'cooldown_backup'));

COMMIT;
