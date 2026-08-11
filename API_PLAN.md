# API v1 Restructure Plan

## Summary

Rework the bridge API from form-centric routes to domain-based `/api/v1/*` routes that reflect the database model and site sections. This is a hard cutover: old `/api/forms/*` routes are removed, deprecated merch interest handling is removed, and frontend scripts, admin pages, docs, and generated email links move to v1.

Token-backed workflow/admin pages may continue to render HTML from API routes.

## Endpoint Map

| Old endpoint | New endpoint |
|---|---|
| `GET /health` | `GET /api/v1/health` |
| `POST /api/forms/contact-us` | `POST /api/v1/contact/messages` |
| `POST /api/forms/newsletter-subscribe/start` | `POST /api/v1/newsletter/subscriptions/start` |
| `GET /api/forms/newsletter-subscribe/confirm?token=...` | `GET /api/v1/newsletter/subscriptions/confirm?token=...` |
| `POST /api/forms/performer-registration/start` | `POST /api/v1/artists/registration/start` |
| `GET /api/forms/performer-registration/session?token=...` | `GET /api/v1/artists/registration/session?token=...` |
| `POST /api/forms/performer-registration/submit` | `POST /api/v1/artists/registration/submissions` |
| `GET /api/forms/performer-registration/moderation/approve?token=...` | `GET /api/v1/profiles/submissions/moderation/approve?token=...` |
| `GET\|POST /api/forms/performer-registration/moderation/deny?token=...` | `GET\|POST /api/v1/profiles/submissions/moderation/deny?token=...` |
| `GET /api/forms/performer-registration/availability/confirm?token=...` | `GET /api/v1/events/performer-requests/availability/confirm?token=...` |
| `GET /api/forms/performer-registration/availability/cancel?token=...` | `GET /api/v1/events/performer-requests/availability/cancel?token=...` |
| `GET\|POST /api/forms/performer-registration/admin-selection?token=...` | `GET\|POST /api/v1/events/performer-selections/admin?token=...` |
| `GET /api/forms/performer-registration/admin-selection/send-confirmation?...` | `GET /api/v1/events/performer-selections/send-confirmation?...` |
| `POST /api/forms/performer-registration/admin-selection/lock?token=...` | `POST /api/v1/events/performer-selections/lock?token=...` |
| `POST /api/forms/performer-registration/admin-selection/lock/release?token=...` | `POST /api/v1/events/performer-selections/lock/release?token=...` |
| `GET /api/forms/performer-registration/admin-selection/events` | `GET /api/v1/events/open-mic/selection-candidates` |
| `POST /api/forms/performer-registration/admin-selection/start` | `POST /api/v1/events/performer-selections/admin-links` |
| `GET\|POST /api/forms/performer-registration/backup-selection?token=...` | `GET\|POST /api/v1/events/performer-selections/backup?token=...` |

Removed without replacement:

| Deprecated endpoint | Action |
|---|---|
| `POST /api/forms/merch-interest` | Delete route, helpers, docs, and frontend submit path. Keep static merch catalog/site content only if still needed. |

## Key Changes

- Organize bridge routes by domain: artists, profiles, events, newsletter, and contact.
- Do not create `/api/v1/forms/*`; forms disappear from the public API vocabulary.
- Keep first-pass request and response bodies stable except where removed merch code makes fields obsolete.
- Update hardcoded route references in frontend scripts, hidden admin pages, generated emails, reminder scripts, deploy config, and docs.
- Keep `/api/v1/*` able to return either JSON or token-backed HTML depending on workflow.

## Test Plan

- Search runtime code for `/api/forms/` and require zero active references.
- Verify old `/api/forms/*` endpoints return 404 after the hard cutover.
- Test token URL generation for registration, moderation, availability, admin selection, backup selection, and newsletter confirmation.
- Run `npx @11ty/eleventy` to catch stale static references.
- Run Python import/compile checks and route-map checks for the Flask bridge.

## Assumptions

- Hard cutover means no aliases, redirects, or wrappers for old `/api/forms/*` routes.
- Deprecated merch interest submission is removed entirely; merch catalog/data can remain for static rendering.
- Artist registration belongs under `/api/v1/artists/registration/*`.
- Moderation remains under `/api/v1/profiles/*` because drafts become canonical profile changes.
- Event availability and lineup workflows belong under `/api/v1/events/*`.
- Future `/api/v1/gallery` and `/api/v1/media` routes are later work only.
