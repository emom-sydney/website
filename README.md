# sydney.emom.me

Static website for `sydney.emom.me`, built with Eleventy and backed by Postgres for relational site data.

## Current Architecture

- static site source in `src/`
- generated output in `_site/`
- relational build-time data loaded through:
  - `src/_data/emom.js`
  - `lib/data/loadEmomData.js`
- write-side forms and tokenized workflows handled by:
  - `forms_bridge/app.py`
  - `forms_bridge/db.py`
  - `forms_bridge/performer_workflow.py`

The site currently includes:

- artist and crew profile sections
- gallery pages backed by Postgres metadata plus live S3 listings
- merch interest form
- performer registration and moderation workflow for Open Mic events

## Build

Generate the site:

```bash
npx @11ty/eleventy
```

Run a local dev server:

```bash
npx @11ty/eleventy --serve
```

## Postgres Runtime

The site now reads relational data from Postgres through the SSH tunnel documented in [DB_SETUP.md](./DB_SETUP.md).

Canonical schema:

- `db/schema.sql`

Typical local setup:

```bash
cp .pgenv-example .pgenv
$EDITOR .pgenv

set -a
source ./.pgenv
set +a
```

Then build normally with Eleventy.

`DATABASE_URL` can be used instead of individual `PG*` variables if preferred.

## Forms Bridge

The forms bridge is a small Flask app used because Eleventy pages are static and cannot write directly to Postgres.

It currently handles:

- `POST /api/forms/merch-interest`
- performer registration start/session/submit
- moderator approve/deny actions
- availability confirm/cancel actions
- admin lineup selection
- backup promotion after cancellations

Supporting scripts:

- `python -m forms_bridge.send_availability_reminders`
- `python -m forms_bridge.send_admin_selection_links`

Bridge deployment and runtime details live in:

- [FORMS.md](./FORMS.md)
- [FORMS_API.md](./FORMS_API.md)

## Public Data Rules

Public artist pages are now filtered by approval and visibility:

- `is_profile_approved = true`
- `profile_visible_from IS NULL OR <= CURRENT_DATE`
- `profile_expires_on >= CURRENT_DATE`

Planned future lineups are stored in `event_performer_selections`.

Actual played lineups should still end up in `performances`.

## Galleries

Gallery pages are hybrid:

- relational event/profile metadata comes from Postgres
- media inventory is read live from S3 at build time

To add a gallery for an event:

1. upload files to `s3://sydney.emom.me/gallery/<galleryname>`
2. set `events.gallery_url` to `<galleryname>`
3. rebuild the site
4. deploy `_site/`

## Key Docs

- [AGENTS.md](./AGENTS.md)
- [DB_SETUP.md](./DB_SETUP.md)
- [FORMS.md](./FORMS.md)
- [FORMS_API.md](./FORMS_API.md)
- [REGO_STATUS.md](./REGO_STATUS.md)
- [PERFORMER_WORKFLOW_FLOW.md](./PERFORMER_WORKFLOW_FLOW.md)
