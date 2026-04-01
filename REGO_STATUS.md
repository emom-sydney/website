# Performer Registration Status

This file is a continuation handoff for the automatic performer registration workflow work.

## Goal

Build a workflow for automatic performer registration using the existing stack:

- static Eleventy site
- `forms_bridge` Flask API
- Postgres
- nginx
- outbound email relayed from the web server to `mail.f8.com.au`

The registration workflow is for Open Mic events only (`events.type_id = 1`).

## Confirmed Product Requirements

### Registration flow

1. `/perform/` starts with a single email field.
2. Submitting that field sends a 24-hour one-time link to the email address.
3. Clicking the link opens a token-backed registration form.
4. The form supports both:
   - creating a new performer profile
   - editing an existing profile matched by email
5. The form collects:
   - profile type (`person` or `group`)
   - display/stage name
   - first name
   - last name
   - `is_email_public`
   - `is_name_public`
   - private contact phone number
   - artist bio
   - `is_bio_public`
   - social links
   - requested performance dates
6. Phone number is required for operational contact only and must never be shown publicly.
7. Email and first/last name fields have “visible on profile page” checkboxes.

### Date eligibility rules

- Only Open Mic events are eligible for performer registration.
- Eligible dates should be upcoming `events` with `type_id = 1`.
- The cooldown rule is not calendar-based.
- It is: performer must not have played at the last N Open Mic events after their most recent Open Mic performance.
- That N is configurable in `app_settings`.
- Current configured/default value is `3`.

### Moderation / approval

- New and edited submissions go through moderation.
- Existing approved public profiles stay live while pending edits are reviewed.
- New profiles remain hidden until approved.
- Denied submissions should email the artist a reason.
- Moderators use emailed one-time links.
- Approve link acts immediately.
- Deny link opens a small form for entering the denial reason.
- Moderation links must become invalid once the action is taken.

### Public visibility

- Profiles need moderation/approval state.
- New performer profiles become publicly visible on the date of their first performance and remain visible until further notice.
- A long-term expiration mechanism was requested.
- Current schema uses `profile_expires_on`, defaulting to 100 years.

### Roles

- Separate moderator and admin capabilities are desired.
- Moderator/admin profiles must be `profile_type = 'person'`.
- Moderator/admin profiles must also have the `volunteer` role.

### Future workflow still to build

- 10 days before an event:
  - all requesters for that date get a 24-hour confirm/cancel availability link
  - moderators should be reminded if some requesters are still unapproved
- 7 days before an event:
  - admin curates final lineup
  - there are 7 slots per night
  - final selection should be stored separately from `performances`
- `performances` should only reflect who actually played after the event

## Schema / DB Work Completed

### Canonical schema updated

`db/schema.sql` has been updated with:

- new `profiles` fields:
  - `contact_phone`
  - `is_profile_approved`
  - `is_moderator`
  - `is_admin`
  - `profile_visible_from`
  - `profile_expires_on`
  - `approved_at`
  - `approved_by_profile_id`
- new workflow tables:
  - `profile_submission_drafts`
  - `profile_submission_social_profiles`
  - `requested_dates`
  - `action_tokens`
  - `moderation_actions`
  - `event_performer_selections`
  - `app_settings`
- settings seed rows:
  - `performer_request_cooldown_events = 3`
  - `availability_confirmation_lead_days = 10`
  - `final_selection_lead_days = 7`
  - `action_token_ttl_hours = 24`
  - `max_performers_per_event = 7`
- trigger helpers to enforce moderator/admin profiles being volunteer people

### Migrations added

- `db/migrations/2026-04-01-performer-workflow.sql`
  - creates the workflow schema
  - seeds settings
  - backfills existing artist profiles as approved/live
- `db/migrations/2026-04-01-backfill-existing-artist-approvals.sql`
  - for DBs where the main workflow migration was already applied before the backfill was added
- `db/migrations/2026-04-01-performer-workflow-grants.sql`
  - grants workflow table access to the old bridge role `emom_merch_writer`
  - this was only to unblock testing
- `db/migrations/2026-04-01-standard-role-grants.sql`
  - standard grants/default privileges for:
    - `emom_site_reader`
    - `emom_site_admin`
    - `emom_forms_writer`

### Existing public artist visibility fix

When `is_profile_approved` was first added, all existing artists disappeared from the public site because they defaulted to `false`.

That was fixed by backfilling existing artist profiles as approved/live.

## Data Loader / Public Site Work Completed

`lib/data/loadEmomData.js` was updated so public artist queries only include profiles where:

- `is_profile_approved = true`
- `profile_visible_from IS NULL OR <= CURRENT_DATE`
- `profile_expires_on >= CURRENT_DATE`

This keeps the public artist pages aligned with the new moderation/visibility model.

## forms_bridge Work Completed

### App structure

`forms_bridge/app.py` now imports and registers routes from:

- `forms_bridge/performer_workflow.py`

### New API routes implemented

- `POST /api/forms/performer-registration/start`
- `GET /api/forms/performer-registration/session?token=...`
- `POST /api/forms/performer-registration/submit`
- `GET /api/forms/performer-registration/moderation/approve?token=...`
- `GET|POST /api/forms/performer-registration/moderation/deny?token=...`

### What the implemented flow does now

#### Start step

- validates the submitted email
- reads settings from `app_settings`
- invalidates old unused registration tokens for the same email
- creates a 24-hour registration token in `action_tokens`
- sends an email with the token link

#### Session fetch

- validates the token
- loads any existing profile by matching email
- loads social platform options
- computes eligible future Open Mic events using the cooldown rule
- returns JSON to prefill the registration form

#### Submission

- validates token
- validates profile payload
- validates requested event ids against currently allowed events
- validates social platform ids
- supersedes older pending drafts for the same profile/email
- inserts into:
  - `profile_submission_drafts`
  - `profile_submission_social_profiles`
  - `requested_dates`
- creates moderation action tokens for moderators
- emails moderators approve/deny links
- marks the registration token as used

#### Approval

- validates approve token
- applies the approved draft into live data:
  - `profiles`
  - `profile_roles` (`artist`)
  - `profile_social_profiles`
- records the moderation action
- updates draft status to `approved`
- invalidates remaining moderation tokens for that draft
- emails the artist that the profile was approved

#### Denial

- validates deny token
- shows a small HTML form to enter a denial reason
- records the moderation action
- updates draft status to `denied`
- invalidates remaining moderation tokens for that draft
- emails the artist the reason

### Important implementation notes

- `profiles` and `profile_social_profiles` still use integer ids rather than identity columns.
- The bridge currently allocates new ids by:
  - locking the table
  - selecting `MAX(id) + 1`
- This was done in `performer_workflow.py` to safely create new profiles and social links.

### Mail transport

Initial implementation tried local `sendmail`.

That was wrong for this environment.

Current implementation uses direct SMTP relay:

- host defaults to `mail.f8.com.au`
- port defaults to `25`

Config env vars:

- `FORMS_SMTP_HOST`
- `FORMS_SMTP_PORT`
- `FORMS_EMAIL_FROM`
- `FORMS_SITE_BASE_URL`

### Open Mic-only event filtering

The available-date query in `performer_workflow.py` now only considers:

- `events.type_id = 1`

That applies both when:

- finding the performer’s last qualifying performance
- listing future requestable events

## /perform/ Frontend Work Completed

### Template

`src/perform.njk` has been replaced with a real two-step UI:

- no token:
  - shows email-only start form
- token present:
  - shows full profile + dates form

### Browser script

`assets/scripts/performer_registration_form.js` now:

- submits the start form to `/api/forms/performer-registration/start`
- reads `?token=...` from the URL
- fetches the token-backed session JSON
- prefills existing profile data
- lets the user add/remove social links
- renders eligible event checkboxes
- validates required fields
- validates incomplete social-link rows
- submits the registration payload to `/api/forms/performer-registration/submit`

### Styling

`assets/css/style.css` was updated with:

- select styling to match inputs
- status colors
- performer form spacing/layout helpers

## Role / Grant Work Completed

### Docs updated

`DB_SETUP.md` was expanded to include:

- `emom_site_reader`
- `emom_site_admin`
- `emom_forms_writer`
- baseline grants
- `ALTER DEFAULT PRIVILEGES` statements

### Bridge env example updated

`deploy/forms_bridge.env.example` now uses:

- `PGUSER=emom_forms_writer`

and includes:

- `FORMS_SITE_BASE_URL`
- `FORMS_EMAIL_FROM`
- `FORMS_SMTP_HOST`
- `FORMS_SMTP_PORT`

## Current Test/Deploy Status

### Working

- Main schema migration works.
- Existing public artists remain visible after backfill.
- `/perform/` page loads on test.
- Start step works far enough to send the email through the SMTP relay.
- Token link reaches the registration form.

### Not yet working / blocked

- Full registration submit is currently blocked because there are no moderator email addresses configured yet.
- The bridge correctly fails when no moderators are found.

### Also noted

- Outgoing registration emails are currently being tagged by SpamAssassin on the mail host.
- That is an infrastructure/mail-host issue rather than an application bug, but it affects the UX.

## Immediate Next Steps For Tomorrow

1. Configure at least one moderator profile in the test DB:
   - `profiles.is_moderator = true`
   - `profiles.email` populated
   - corresponding `profile_roles` row with `role = 'volunteer'`
2. Retry full registration submission end-to-end.
3. Verify:
   - draft row created
   - social links saved
   - requested dates saved
   - moderation emails sent
4. Test approve flow.
5. Test deny flow with a reason.

## Important Known Gaps / Not Implemented Yet

### Final visibility behavior is only partially implemented

The product requirement is:

- new performer profiles become visible on the date of their first performance

Current implementation approximates this by setting `profile_visible_from` to the earliest requested event date at approval time.

That is not the final intended rule.

Proper behavior will require the later admin-selection workflow so visibility can key off the first actually selected/confirmed performance date rather than merely requested dates.

### Availability confirmation workflow not built yet

Still missing:

- 10-day confirmation emails
- confirm/cancel availability tokens and endpoints
- reminder emails for unapproved profiles

### Admin lineup selection not built yet

Still missing:

- tokenized admin page for final lineup selection
- selecting up to `max_performers_per_event`
- storing curated selections in `event_performer_selections`
- later copying actual played lineups into `performances`

### No image uploads yet

This was intentionally deferred.

### No explicit frontend success page yet

Current `/perform/` flow stays on the same page and shows inline status messages.

## Likely Useful Server-Side Checks Tomorrow

If something fails again, likely checks:

- `journalctl -u emom-forms-bridge -n 100 --no-pager`
- confirm bridge env has:
  - `PGUSER=emom_forms_writer`
  - matching password
  - `FORMS_SITE_BASE_URL`
  - `FORMS_EMAIL_FROM`
  - `FORMS_SMTP_HOST=mail.f8.com.au`
  - `FORMS_SMTP_PORT=25`
- restart bridge after env changes

## Files Touched In This Work

- `db/schema.sql`
- `db/migrations/2026-04-01-performer-workflow.sql`
- `db/migrations/2026-04-01-backfill-existing-artist-approvals.sql`
- `db/migrations/2026-04-01-performer-workflow-grants.sql`
- `db/migrations/2026-04-01-standard-role-grants.sql`
- `lib/data/loadEmomData.js`
- `forms_bridge/app.py`
- `forms_bridge/performer_workflow.py`
- `src/perform.njk`
- `assets/scripts/performer_registration_form.js`
- `assets/css/style.css`
- `deploy/forms_bridge.env.example`
- `FORMS_API.md`
- `DB_SETUP.md`

## Recommended Resume Point

Tomorrow, resume by setting up one moderator record in the test DB and running the end-to-end flow from:

1. request registration email
2. open token link
3. submit profile draft
4. approve/deny via moderator email links

Only after that should the next implementation chunk begin:

- 10-day availability confirmation workflow
- 7-day admin selection workflow
