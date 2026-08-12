# Backend API v1

The dynamic backend exposes JSON under `/api/v1/`. Human-facing staff and
email-action pages deliberately live outside the API namespace.

## Public API

- `GET /api/v1/health`
- `POST /api/v1/profiles/submissions/access-links`
- `GET /api/v1/profiles/submissions/context`
  - requires `Authorization: Bearer <profile-submission-access-token>`
- `POST /api/v1/profiles/submissions`
  - requires the same Bearer token
- `POST /api/v1/newsletter/subscriptions`
- `POST /api/v1/contact/messages`
- `GET /api/v1/artists/<profile_id>/qr/scan`
  - records a QR scan then redirects to the current public artist profile
- `GET /api/v1/artists/<profile_id>/qr/download.svg`
- `GET /api/v1/artists/<profile_id>/qr/download.png`
  - record the download and return a QR image encoding the scan URL

Successful JSON responses use:

```json
{"data": {}}
```

Errors use:

```json
{"error": {"code": "machine_readable_code", "message": "Human-readable message."}}
```

## Staff API

Authentication:

- `POST /api/v1/admin/login-links`
- `GET /api/v1/admin/session`
- `DELETE /api/v1/admin/session`

Dashboard and domains:

- `GET /api/v1/admin/dashboard`
- `GET /api/v1/admin/events`
- `GET|PUT /api/v1/admin/events/<event_id>/lineup`
- `POST|DELETE /api/v1/admin/events/<event_id>/lineup/lock`
- `POST /api/v1/admin/events/<event_id>/performer-requests/<request_id>/availability-reminders`
- `POST /api/v1/admin/events/<event_id>/performer-requests/<request_id>/lineup-status-notifications`
- `DELETE /api/v1/admin/events/<event_id>/performer-requests/<request_id>`
- `GET /api/v1/admin/events/<event_id>/standby`
- `POST /api/v1/admin/events/<event_id>/lineup/promotions`
- `GET /api/v1/admin/profiles/submissions?status=pending`
- `GET /api/v1/admin/profiles/submissions/<draft_id>`
- `POST /api/v1/admin/profiles/submissions/<draft_id>/decisions`

Staff APIs use the secure session established by `/admin/login/verify/`.
Every state-changing request must also send the `emom_staff_csrf` cookie value
in `X-CSRF-Token`.

Administrators can use every staff endpoint. Moderators can use profile
moderation and standby-promotion endpoints but cannot edit a full lineup.

## Human-Facing Backend Routes

- `/admin/login/`
- `/admin/login/verify/?token=...&next=...`
- `/admin/`
- `/admin/events/`
- `/admin/events/<event_id>/lineup/`
- `/admin/events/<event_id>/standby/`
- `/admin/profiles/`
- `/admin/profiles/submissions/<draft_id>/`
- `/perform/availability/confirm/?token=...`
- `/perform/availability/cancel/?token=...`
- `/newsletter/confirm/?token=...`

## Scheduled Jobs

```bash
python -m backend.jobs.send_availability_reminders
python -m backend.jobs.send_lineup_selection_links
python -m backend.jobs.send_moderation_reminders
python -m backend.jobs.purge_profile_qr_events
```

Each job supports the same operational environment as the backend. The
availability and lineup jobs accept `--run-date YYYY-MM-DD`.

Run `purge_profile_qr_events` daily. It reads `app_settings.qr_tracking_retention_days`
(default `90`) and removes older QR scan/download records.
