# Backend Guide

The Eleventy site remains static. Runtime APIs, staff pages, Postgres writes,
email actions, Keila integration, and scheduled workflow jobs live in
`backend/`.

## Structure

- `backend/app.py` creates the Flask application.
- `backend/admin.py` owns staff authentication, browser pages, authorization,
  and `/api/v1/admin` routes.
- `backend/performer_workflow.py` owns current profile-submission and event
  lineup domain behavior.
- `backend/keila_workflow.py` owns newsletter and Keila behavior.
- `backend/contact_us_workflow.py` owns contact-message delivery.
- `backend/profile_qr.py` owns public artist-profile QR downloads and scan tracking.
- `backend/jobs/` contains standalone scheduled commands.
- `backend/templates/admin/` contains the server-rendered staff shell.

Reusable site read behavior remains under `lib/`; Eleventy adapters remain
thin under `src/_data/`.

## Local Run

Install dependencies:

```bash
python -m pip install -r backend/requirements.txt
```

Run:

```bash
python -m flask --app backend.app run --host 127.0.0.1 --port 5001
```

The nginx production contract proxies `/api/v1/`, `/admin/`,
`/perform/availability/`, and `/newsletter/confirm/` to this process.

## Required Environment

- Postgres: `DATABASE_URL` or standard `PG*` variables
- `PUBLIC_SITE_BASE_URL`
- `API_ALLOWED_ORIGINS`
- `EMAIL_FROM`
- `SMTP_HOST`
- `SMTP_PORT`
- `STAFF_LOGIN_TOKEN_TTL_MINUTES` (default `15`)
- `STAFF_SESSION_TTL_HOURS` (default `12`)
- `LINEUP_SELECTION_LOCK_MINUTES` (default `30`)
- `app_settings.qr_tracking_retention_days` controls QR event retention (default `90` days)
- Keila variables documented in `deploy/etc/emom/backend.env.example`

## Staff Security

Staff request a one-time email link. A valid 15-minute `staff_login` token is
consumed to create a revocable, database-backed 12-hour session. The opaque
session cookie is Secure, HttpOnly, and SameSite=Lax. Mutations also require a
session-bound CSRF token.

Staff eligibility is checked on every request. Administrators receive all
capabilities; moderators receive profile-moderation and standby-promotion
capabilities. Staff must retain a person profile and volunteer role.

Event deletion is available to administrators only for future events through
the admin interface. Past events are treated as historical records and cannot
be deleted there. An exceptional historical deletion—particularly one with
galleries or performances—requires deliberate database-level intervention
after reviewing its dependent records.

## Deployment

Apply `db/migrations/2026-07-29-backend-api-v1-and-admin.sql` before starting
the new service. The migration is intentionally one-way and removes obsolete
workflow tokens.

Apply `db/migrations/2026-08-12-profile-qr-tracking.sql` before deploying QR
tracking, then schedule `python -m backend.jobs.purge_profile_qr_events` daily.

Install:

- `deploy/systemd/emom-backend.service`
- `deploy/nginx/emom-backend.conf`
- an environment file based on `deploy/etc/emom/backend.env.example`

Validate nginx, reload it, and restart `emom-backend`. There is no
legacy compatibility layer.

## WSL/Debian notes

Some parts of Python are not installed on Debian by default, so you need to do the following before
you do anything else:

```bash
apt-get install python3 python3-dev python3-pip python-is-python3
python3 -m venv venv/local
```

This will create a virtual environment which is where all python packages will be created.

Now add the following to your `.bashrc`:

```bash
export VIRTUAL_ENV_DISABLE_PROMPT=1
source ~/venv/local/bin/activate
```
