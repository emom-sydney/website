BEGIN;

ALTER TABLE action_tokens
DROP CONSTRAINT IF EXISTS action_tokens_action_type_check;

ALTER TABLE action_tokens
ADD CONSTRAINT action_tokens_action_type_check
CHECK (
  action_type IN (
    'profile_submission_access',
    'availability_confirm',
    'availability_cancel',
    'newsletter_subscribe_confirm',
    'staff_login',
    'profile_moderation_approve',
    'profile_moderation_deny'
  )
);

COMMIT;
