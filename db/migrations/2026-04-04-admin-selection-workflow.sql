BEGIN;

ALTER TABLE events
ADD COLUMN IF NOT EXISTS admin_selection_email_sent_at timestamptz;

ALTER TABLE action_tokens
DROP CONSTRAINT IF EXISTS action_tokens_action_type_check;

ALTER TABLE action_tokens
ADD CONSTRAINT action_tokens_action_type_check
CHECK (
  action_type IN (
    'registration_link',
    'moderation_approve',
    'moderation_deny',
    'availability_confirm',
    'availability_cancel',
    'admin_selection',
    'backup_selection'
  )
);

COMMIT;
