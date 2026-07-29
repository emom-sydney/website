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
- Keila variables documented in `deploy/etc/emom/backend.env.example`

## Staff Security

Staff request a one-time email link. A valid 15-minute `staff_login` token is
consumed to create a revocable, database-backed 12-hour session. The opaque
session cookie is Secure, HttpOnly, and SameSite=Lax. Mutations also require a
session-bound CSRF token.

Staff eligibility is checked on every request. Administrators receive all
capabilities; moderators receive profile-moderation and standby-promotion
capabilities. Staff must retain a person profile and volunteer role.

## Deployment

Apply `db/migrations/2026-07-29-backend-api-v1-and-admin.sql` before starting
the new service. The migration is intentionally one-way and removes obsolete
workflow tokens.

Install:

- `deploy/systemd/emom-backend.service`
- `deploy/nginx/emom-backend.conf`
- an environment file based on `deploy/etc/emom/backend.env.example`

Validate nginx, reload it, and restart `emom-backend`. There is no
legacy compatibility layer.
