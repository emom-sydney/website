# Forms API

This repo now includes a small Python bridge for writing static-site form submissions into Postgres.

Current endpoint:

- `POST /api/forms/merch-interest`
- `POST /api/forms/performer-registration/start`
- `GET /api/forms/performer-registration/session?token=...`
- `POST /api/forms/performer-registration/submit`
- `GET /api/forms/performer-registration/moderation/approve?token=...`
- `GET|POST /api/forms/performer-registration/moderation/deny?token=...`
- `GET /api/forms/performer-registration/availability/confirm?token=...`
- `GET /api/forms/performer-registration/availability/cancel?token=...`

The bridge code lives in:

- `forms_bridge/app.py`
- `forms_bridge/db.py`
- `forms_bridge/requirements.txt`

## Purpose

The website is statically generated with Eleventy, so browser forms cannot write directly to Postgres. This bridge is the server-side component that accepts form submissions and inserts rows into the database.

The merch endpoint is intentionally narrow, but the app structure is reusable for future forms.

## Environment

The bridge uses the same database environment pattern as the site:

- `DATABASE_URL`
- or `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`

Optional:

- `FORMS_API_ALLOWED_ORIGINS`
  - comma-separated list of allowed origins for CORS
  - if unset, the app reflects any incoming origin
- `FORMS_SITE_BASE_URL`
  - base public site URL used to build performer registration and moderation links
- `FORMS_EMAIL_FROM`
  - sender address for performer workflow emails
- `FORMS_SMTP_HOST`
  - SMTP relay host for bridge-generated emails
- `FORMS_SMTP_PORT`
  - SMTP relay port, defaults to `25`

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r forms_bridge/requirements.txt
```

## Run

For local development:

```bash
export FLASK_APP=forms_bridge.app
flask run --host 127.0.0.1 --port 5001
```

Or with Python directly:

```bash
python -m flask --app forms_bridge.app run --host 127.0.0.1 --port 5001
```

In production, run it behind a reverse proxy or WSGI server. The intended pattern is to expose it under the same site/domain so frontend forms can post to a same-origin path such as `/api/forms/merch-interest`.

## Debian / systemd / nginx

Deployment templates are included in:

- `deploy/systemd/emom-forms-bridge.service`
- `deploy/nginx/emom-forms-bridge.conf`
- `deploy/forms_bridge.env.example`

Suggested server layout:

- repo checkout: `/opt/emom/website`
- virtualenv: `/opt/emom/website/.venv`
- env file: `/etc/emom/forms_bridge.env`

Recommended install sequence:

```bash
sudo mkdir -p /opt/emom
sudo chown "$USER":"$USER" /opt/emom
git clone <repo-url> /opt/emom/website
cd /opt/emom/website

python3 -m venv .venv
source .venv/bin/activate
pip install -r forms_bridge/requirements.txt
```

Create the runtime env file:

```bash
sudo mkdir -p /etc/emom
sudo cp deploy/forms_bridge.env.example /etc/emom/forms_bridge.env
sudo chmod 600 /etc/emom/forms_bridge.env
```

Install the `systemd` unit:

```bash
sudo cp deploy/systemd/emom-forms-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now emom-forms-bridge
sudo systemctl status emom-forms-bridge
```

Wire nginx into the existing `sydney.emom.me` server block by including the contents of:

- `deploy/nginx/emom-forms-bridge.conf`

Then reload nginx:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

The expected public paths are:

- `GET /api/forms/health`
- `POST /api/forms/merch-interest`
- `POST /api/forms/performer-registration/start`
- `GET /api/forms/performer-registration/session?token=...`
- `POST /api/forms/performer-registration/submit`
- `GET /api/forms/performer-registration/availability/confirm?token=...`
- `GET /api/forms/performer-registration/availability/cancel?token=...`

## Request Shape

`POST /api/forms/merch-interest`

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
- `lines` must contain at least one item
- each line must include `submitted_price`
- duplicate `merch_variant_id` values are merged by the API before insert
- only active merch variants are accepted

## Response Shape

Success:

```json
{
  "ok": true,
  "submission_id": 123,
  "line_count": 2
}
```

Error:

```json
{
  "ok": false,
  "error": "A valid email address is required."
}
```

## Current Tables Used

- `merch_interest_submissions`
- `merch_interest_lines`
- `merch_variants`

The API validates the submitted variant ids against `merch_variants` and inserts rows into the submissions/lines tables in one transaction.

## Performer Registration

The performer workflow is now staged through the forms bridge:

- `POST /api/forms/performer-registration/start`
  - accepts `{ "email": "artist@example.com" }`
  - creates a 24-hour token in `action_tokens`
  - sends a registration email using local `sendmail`
- `GET /api/forms/performer-registration/session?token=...`
  - validates the registration token
  - returns any existing profile data for that email, social platform options, and currently eligible future events
- `POST /api/forms/performer-registration/submit`
  - accepts the token plus draft profile fields, social links, and requested event ids
  - writes into `profile_submission_drafts`, `profile_submission_social_profiles`, and `requested_dates`
  - emails moderators one-time approve/deny links
- moderation links:
  - approval applies the draft to the live profile and artist role
  - denial presents a small reason form and emails the artist the reason
- availability links:
  - confirm marks `requested_dates.status = 'availability_confirmed'`
  - cancel marks `requested_dates.status = 'availability_cancelled'`

Availability reminder job:

- script: `python -m forms_bridge.send_availability_reminders`
- optional override: `python -m forms_bridge.send_availability_reminders --run-date 2026-04-04`
- behavior:
  - reads `availability_confirmation_lead_days` from `app_settings`
  - finds due Open Mic events
  - emails all unsent requesters one-time confirm/cancel links
  - emails moderators if any requesters for that event are still unapproved

Current performer flow environment assumptions:

- the database already has the new performer workflow schema
- moderator profiles exist in `profiles` with `is_moderator = true`
- moderator profiles also have the `volunteer` role in `profile_roles`
- the host can relay mail through the configured SMTP server
