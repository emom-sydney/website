# Forms API

This repo includes a small Flask bridge for writing static-site form submissions into Postgres.

## Current Endpoints

- `GET /health` (typically exposed as `GET /api/forms/health` via nginx)
- `POST /api/forms/merch-interest`
- `POST /api/forms/performer-registration/start`
- `GET /api/forms/performer-registration/session?token=...`
- `POST /api/forms/performer-registration/submit`
- `GET /api/forms/performer-registration/moderation/approve?token=...`
- `GET|POST /api/forms/performer-registration/moderation/deny?token=...`
- `GET /api/forms/performer-registration/availability/confirm?token=...`
- `GET /api/forms/performer-registration/availability/cancel?token=...`
- `GET|POST /api/forms/performer-registration/admin-selection?token=...`
- `GET /api/forms/performer-registration/admin-selection/send-confirmation?token=...&requested_date_id=...`
- `POST /api/forms/performer-registration/admin-selection/lock?token=...`
- `POST /api/forms/performer-registration/admin-selection/lock/release?token=...`
- `GET /api/forms/performer-registration/admin-selection/events`
- `POST /api/forms/performer-registration/admin-selection/start`
- `GET|POST /api/forms/performer-registration/backup-selection?token=...`
- `POST /api/forms/volunteer-registration/start`
- `GET /api/forms/volunteer-registration/session?token=...`
- `POST /api/forms/volunteer-registration/submit`
- `GET /api/forms/volunteer-registration/moderation/approve?token=...`
- `GET|POST /api/forms/volunteer-registration/moderation/deny?token=...`
- `POST /api/forms/volunteer-registration/claims/start`
- `GET /api/forms/volunteer-registration/claims/session?token=...`
- `POST /api/forms/volunteer-registration/claims/cancel`

The bridge code lives in:

- `forms_bridge/app.py`
- `forms_bridge/db.py`
- `forms_bridge/performer_workflow.py`
- `forms_bridge/send_availability_reminders.py`
- `forms_bridge/send_admin_selection_links.py`
- `forms_bridge/send_moderation_token_reminders.py`
- `forms_bridge/volunteer_workflow.py`
- `forms_bridge/requirements.txt`

## Purpose

The website is statically generated with Eleventy, so browser forms cannot write directly to Postgres. This bridge is the runtime server component for writes, token workflows, and workflow emails.

## Environment

Database:

- `DATABASE_URL`
- or `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`

Optional:

- `FORMS_API_ALLOWED_ORIGINS`
  - comma-separated allowlist for CORS
  - if unset, the app reflects any incoming origin
- `FORMS_SITE_BASE_URL`
  - required for absolute workflow links in emails
- `FORMS_EMAIL_FROM`
  - sender address for workflow mail
- `FORMS_SMTP_HOST`
  - SMTP relay host
- `FORMS_SMTP_PORT`
  - SMTP relay port (default `25`)
- `ADMIN_SELECTION_LOCK_MINUTES`
  - admin lineup lock TTL in minutes (default `30`)

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r forms_bridge/requirements.txt
```

## Run

```bash
export FLASK_APP=forms_bridge.app
flask run --host 127.0.0.1 --port 5001
```

Or:

```bash
python -m flask --app forms_bridge.app run --host 127.0.0.1 --port 5001
```

In production, run behind nginx/systemd.

## Deployment Templates

- `deploy/systemd/emom-forms-bridge.service`
- `deploy/nginx/emom-forms-bridge.conf`
- `deploy/forms_bridge.env.example`

`deploy/nginx/emom-forms-bridge.conf` maps:

- `/api/forms/` to the Flask app
- `/api/forms/health` to Flask `/health`

## Merch Interest API

`POST /api/forms/merch-interest`

Request:

```json
{
  "email": "user@example.com",
  "comments": "Interested in a mug and a tee.",
  "lines": [
    { "merch_variant_id": 1, "quantity": 1, "submitted_price": "35.00" },
    { "merch_variant_id": 12, "quantity": 2, "submitted_price": "18.00" }
  ]
}
```

Notes:

- `email` is required
- `comments` is optional
- `lines` must be a non-empty array
- each line requires `submitted_price`
- duplicate `merch_variant_id` rows are merged before insert
- only active variants are accepted

Success response:

```json
{
  "ok": true,
  "submission_id": 123,
  "line_count": 2
}
```

Error response:

```json
{
  "ok": false,
  "error": "A valid email address is required."
}
```

Tables:

- `merch_interest_submissions`
- `merch_interest_lines`
- `merch_variants`

## Performer Registration Workflow

### Start

`POST /api/forms/performer-registration/start`

- request body: `{ "email": "artist@example.com" }`
- invalidates existing unused `registration_link` tokens for that email
- creates a new one-time token in `action_tokens`
- sends registration link email

### Session

`GET /api/forms/performer-registration/session?token=...`

- validates token (`registration_link`)
- loads profile prefill
  - prefers latest relevant draft for that email (`pending`, `denied`, `approved`)
  - falls back to live profile
- returns social platform metadata and available Open Mic dates
- includes `cooldown_events` from app settings

### Submit

`POST /api/forms/performer-registration/submit`

- requires `token` plus profile payload
- validates requested event IDs against currently available events
- validates social platform IDs
- supersedes old pending drafts for matched profile/email
- inserts:
  - `profile_submission_drafts`
  - `profile_submission_social_profiles`
  - `requested_dates`
- creates moderation approve/deny tokens for each moderator
- marks registration token used
- emails moderators with:
  - submitted draft
  - live profile snapshot (if matched)
  - requested dates and social links
  - current next-event status summary

### Moderation

- `GET /api/forms/performer-registration/moderation/approve?token=...`
  - applies draft to live profile
  - upserts artist role/social links
  - finalizes draft as approved
  - records moderation action
  - invalidates all pending moderation tokens for draft
  - sends performer approval email

- `GET|POST /api/forms/performer-registration/moderation/deny?token=...`
  - GET returns denial reason form
  - POST requires `reason`
  - optional `include_edit_link` (default on) sends fresh registration link
  - finalizes draft as denied
  - records moderation action
  - invalidates all pending moderation tokens for draft
  - sends performer denial email

### Availability

- `GET /api/forms/performer-registration/availability/confirm?token=...`
  - sets `requested_dates.status = 'availability_confirmed'`
  - sets `availability_responded_at`
  - invalidates both availability tokens for that request

- `GET /api/forms/performer-registration/availability/cancel?token=...`
  - sets `requested_dates.status = 'availability_cancelled'`
  - sets `availability_responded_at`
  - invalidates both availability tokens for that request
  - if lineup impacts apply, updates selection state and may trigger moderator alerts

### Admin Selection

- `GET /api/forms/performer-registration/admin-selection/events`
  - lists upcoming Open Mic events

- `POST /api/forms/performer-registration/admin-selection/start`
  - request body: `{ "email": "...", "event_id": 123 }`
  - if email belongs to an admin profile, sends a fresh selection link
  - always returns generic success message

- `GET|POST /api/forms/performer-registration/admin-selection?token=...`
  - tokenized lineup page + save action
  - event-level lock via `admin_selection_locks`
  - only approved + availability-confirmed candidates are selectable
  - allowed statuses: `selected`, `standby`, `reserve`
  - selected count capped by `max_performers_per_event`

- `GET /api/forms/performer-registration/admin-selection/send-confirmation?token=...&requested_date_id=...`
  - sends/re-sends availability confirmation email for an unconfirmed request on that event

- `POST /api/forms/performer-registration/admin-selection/lock?token=...`
  - lock heartbeat/refresh endpoint
  - returns `409` if another admin holds the lock

- `POST /api/forms/performer-registration/admin-selection/lock/release?token=...`
  - best-effort lock release endpoint

### Backup Selection

`GET|POST /api/forms/performer-registration/backup-selection?token=...`

- used when selected performer cancels and backup pool exists
- promotes a `standby`/`reserve` candidate to `selected`
- invalidates backup-selection tokens for event
- sends promoted performer fresh availability confirm/cancel links

## Scheduled Workflow Scripts

Availability reminders:

```bash
python -m forms_bridge.send_availability_reminders
python -m forms_bridge.send_availability_reminders --run-date 2026-04-04
```

- computes target date using `availability_confirmation_lead_days`
- sends availability emails for due `requested` rows with unsent reminders
- sends moderators an unapproved-requester reminder for that event when needed

Admin selection links:

```bash
python -m forms_bridge.send_admin_selection_links
python -m forms_bridge.send_admin_selection_links --run-date 2026-04-04
```

- computes target date using `final_selection_lead_days`
- emails admins lineup selection links for due events
- sets `events.admin_selection_email_sent_at`

Expired moderation reminders:

```bash
python -m forms_bridge.send_moderation_token_reminders
```

- finds pending drafts where moderation links expired unused
- reissues fresh moderation links per moderator
- marks old expired links as replaced

## Current Performer Workflow Assumptions

- performer workflow migrations are applied
- moderator/admin profiles are configured in `profiles`
- moderator/admin profiles also have `volunteer` role in `profile_roles`
- SMTP relay is reachable from bridge host

## Volunteer Registration Workflow

`/api/forms/volunteer-registration/...` adds a role-bidding flow parallel to performer registration.

Core endpoints:

- `POST /api/forms/volunteer-registration/start`
  - sends one-time volunteer registration link
- `GET /api/forms/volunteer-registration/session?token=...`
  - returns profile prefill, social platforms, future events, and role availability by event
- `POST /api/forms/volunteer-registration/submit`
  - accepts profile fields, social links, and `role_claims: [{ event_id, role_key }]`
  - auto-approves immediately when the matched profile is already approved and already has volunteer role
  - otherwise sends moderator approve/deny links
- `GET /api/forms/volunteer-registration/moderation/approve?token=...`
- `GET|POST /api/forms/volunteer-registration/moderation/deny?token=...`
  - same moderation pattern as performer flow, including optional fresh edit link on deny
- `POST /api/forms/volunteer-registration/claims/start`
  - sends one-time claims management link
- `GET /api/forms/volunteer-registration/claims/session?token=...`
  - returns selected/standby/cancelled claims for upcoming events
- `POST /api/forms/volunteer-registration/claims/cancel`
  - cancels a selected/standby claim
  - selected cancellation auto-promotes the oldest standby claim for the same role/event

Role/capacity model:

- global role definitions: `volunteer_roles`
- optional per-event capacity/description overrides: `event_volunteer_role_overrides`
- pending draft claims: `profile_submission_volunteer_claims`
- live claim state: `event_volunteer_role_claims`

Selection rule:

- if `selected_count < effective_capacity` then new claim is `selected`
- otherwise claim is `standby`
