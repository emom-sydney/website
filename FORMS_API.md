# API v1

This repo includes a small Python bridge for runtime writes and tokenized workflows that cannot run inside the static Eleventy build.

The public bridge API is now domain-based under `/api/v1/`. The old form-centric endpoints were removed in the v1 hard cutover.

## Current Endpoints

- `GET /api/v1/health`
- `POST /api/v1/contact/messages`
- `POST /api/v1/newsletter/subscriptions/start`
- `GET /api/v1/newsletter/subscriptions/confirm?token=...`
- `POST /api/v1/artists/registration/start`
- `GET /api/v1/artists/registration/session?token=...`
- `POST /api/v1/artists/registration/submissions`
- `GET /api/v1/profiles/submissions/moderation/approve?token=...`
- `GET|POST /api/v1/profiles/submissions/moderation/deny?token=...`
- `GET /api/v1/events/performer-requests/availability/confirm?token=...`
- `GET /api/v1/events/performer-requests/availability/cancel?token=...`
- `GET|POST /api/v1/events/performer-selections/admin?token=...`
- `GET /api/v1/events/performer-selections/send-confirmation?token=...&requested_date_id=...`
- `POST /api/v1/events/performer-selections/lock?token=...`
- `POST /api/v1/events/performer-selections/lock/release?token=...`
- `GET /api/v1/events/open-mic/selection-candidates`
- `POST /api/v1/events/performer-selections/admin-links`
- `GET|POST /api/v1/events/performer-selections/backup?token=...`

Deprecated merch interest submission handling has been removed. Static merch catalog rendering may still use merch tables at build time.

## Runtime

The bridge code lives in:

- `forms_bridge/app.py`
- `forms_bridge/db.py`
- `forms_bridge/contact_us_workflow.py`
- `forms_bridge/newsletter_workflow.py`
- `forms_bridge/performer_workflow.py`
- `forms_bridge/send_availability_reminders.py`
- `forms_bridge/send_admin_selection_links.py`
- `forms_bridge/requirements.txt`

For local development:

```bash
export FLASK_APP=forms_bridge.app
flask run --host 127.0.0.1 --port 5001
```

In production, run it behind a reverse proxy or WSGI server and expose `/api/v1/` on the same domain as the static site.

## Environment

Database connections use:

- `DATABASE_URL`
- or `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`

Optional bridge settings:

- `FORMS_API_ALLOWED_ORIGINS`
  - comma-separated list of allowed origins for CORS
  - if unset, the app reflects any incoming origin
- `FORMS_SITE_BASE_URL`
  - base public site URL used to build token workflow links
- `FORMS_EMAIL_FROM`
  - sender address for workflow emails
- `FORMS_SMTP_HOST`
  - SMTP relay host for bridge-generated emails
- `FORMS_SMTP_PORT`
  - SMTP relay port, defaults to `25`
- `ADMIN_SELECTION_LOCK_MINUTES`
  - lock TTL for admin lineup editing sessions
  - defaults to `30`
- `NEWSLETTER_TOKEN_TTL_HOURS`
  - newsletter confirmation token TTL
  - defaults to `24`
- `KEILA_API_BASE_URL`, `KEILA_API_KEY`, `KEILA_TIMEOUT_SECONDS`
  - newsletter confirmation upstream integration

## Domain Workflows

### Contact

`POST /api/v1/contact/messages`

Accepts:

```json
{
  "name": "Sender Name",
  "email": "sender@example.com",
  "message": "Message body"
}
```

Sends an email to the configured contact mailbox. No database rows are written.

### Newsletter

`POST /api/v1/newsletter/subscriptions/start`

Accepts:

```json
{
  "email": "subscriber@example.com",
  "first_name": "Optional",
  "last_name": "Optional"
}
```

Creates an `action_tokens` row plus `newsletter_subscribe_requests` row, then emails a one-time confirmation link.

`GET /api/v1/newsletter/subscriptions/confirm?token=...`

Validates the one-time token, upserts the contact into Keila, marks the token used, and renders an HTML result page.

### Artist Registration

`POST /api/v1/artists/registration/start`

Accepts `{ "email": "artist@example.com" }`, creates a 24-hour one-time registration token, and sends the artist a link to `/perform/?token=...`.

`GET /api/v1/artists/registration/session?token=...`

Validates the registration token and returns JSON containing:

- matched or latest-prefill profile context
- social platform options
- eligible future Open Mic dates
- performer cooldown settings

`POST /api/v1/artists/registration/submissions`

Accepts the registration token plus profile fields, social links, and requested event ids. It writes:

- `profile_submission_drafts`
- `profile_submission_social_profiles`
- `requested_dates`
- moderation `action_tokens`

Moderator emails include approve and deny links under `/api/v1/profiles/submissions/moderation/...`.

### Profile Moderation

`GET /api/v1/profiles/submissions/moderation/approve?token=...`

Applies the draft to the live `profiles` and `profile_roles` records, records the moderation action, invalidates sibling moderation tokens, sends the approval email, and renders an HTML success page.

`GET|POST /api/v1/profiles/submissions/moderation/deny?token=...`

Renders a denial reason form on `GET`. On `POST`, records the denial, optionally creates a fresh artist registration link, emails the artist, and renders an HTML result page.

### Event Performer Requests

`GET /api/v1/events/performer-requests/availability/confirm?token=...`

Marks the related `requested_dates` row as `availability_confirmed`.

`GET /api/v1/events/performer-requests/availability/cancel?token=...`

Marks the related `requested_dates` row as `availability_cancelled`. If the artist was already selected, the workflow can trigger backup selection notifications.

Availability reminder job:

```bash
python -m forms_bridge.send_availability_reminders
python -m forms_bridge.send_availability_reminders --run-date 2026-04-04
```

### Event Performer Selections

`GET|POST /api/v1/events/performer-selections/admin?token=...`

Tokenized admin lineup page. It uses `admin_selection_locks` to avoid concurrent edits, stores selected/standby/reserve states in `event_performer_selections`, and renders HTML.

Supporting endpoints:

- `GET /api/v1/events/performer-selections/send-confirmation?token=...&requested_date_id=...`
- `POST /api/v1/events/performer-selections/lock?token=...`
- `POST /api/v1/events/performer-selections/lock/release?token=...`
- `GET /api/v1/events/open-mic/selection-candidates`
- `POST /api/v1/events/performer-selections/admin-links`
- `GET|POST /api/v1/events/performer-selections/backup?token=...`

Admin selection reminder job:

```bash
python -m forms_bridge.send_admin_selection_links
python -m forms_bridge.send_admin_selection_links --run-date 2026-04-04
```

## Deployment Notes

Deployment templates are included in:

- `deploy/systemd/emom-forms-bridge.service`
- `deploy/nginx/emom-forms-bridge.conf`
- `deploy/forms_bridge.env.example`

The nginx template proxies `/api/v1/` to the bridge service.
