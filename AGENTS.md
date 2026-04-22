# Repository Guide

This file is the Codex-facing source of truth for this repository. The notes in `.amazonq/rules/memory-bank/` and `.github/copilot-instructions.md` are historical context only and should not be treated as authoritative without checking the code.

## What This Repo Is

- Static site for `sydney.emom.me`
- Built with Eleventy and ES modules
- Main source lives in `src/`
- Generated output goes to `_site/`
- Includes a small Flask-based `forms_bridge` app for form writes and tokenized workflow steps

## Build

- Local build: `npx @11ty/eleventy`
- Local dev server: `npx @11ty/eleventy --serve`
- Eleventy config: `.eleventy.js`

## Data Architecture

Relational site data comes from Postgres through:

- `src/_data/emom.js`
- `lib/data/loadEmomData.js`

There is no CSV fallback in the current repo.

Postgres connections are expected to come through the local SSH tunnel described in `DB_SETUP.md`.

Write-side form and workflow actions go through:

- `forms_bridge/app.py`
- `forms_bridge/db.py`
- `forms_bridge/performer_workflow.py`

## Current Schema

Canonical schema is in `db/schema.sql`.

Current relational tables:

- `profiles`
- `profile_roles`
- `profile_images`
- `profile_social_profiles`
- `events`
- `event_types`
- `performances`
- `social_platforms`
- `profile_submission_drafts`
- `profile_submission_social_profiles`
- `requested_dates`
- `action_tokens`
- `moderation_actions`
- `event_performer_selections`
- `app_settings`
- `merch_items`
- `merch_variants`
- `merch_interest_submissions`
- `merch_interest_lines`

Important model details:

- `profiles` is the base entity for both people and groups
- `profiles.profile_type` is `person` or `group`
- `profile_roles.role` is currently `artist` or `volunteer`
- `profiles` now also stores moderation, visibility, and staff flags:
  - `contact_phone`
  - `is_profile_approved`
  - `is_moderator`
  - `is_admin`
  - `profile_visible_from`
  - `profile_expires_on`
- role-specific bio fields live on `profile_roles`:
  - `bio`
  - `is_bio_public`
- shared privacy/contact fields live on `profiles`:
  - `email`
  - `is_email_public`
  - `is_name_public`
- `events.event_date` is the canonical date field
- performer registration is for Open Mic events only, currently `events.type_id = 1`
- `requested_dates` stores performer requests plus availability reminder tracking
- `event_performer_selections` stores pre-event lineup state such as `selected`, `standby`, `reserve`, and `cancelled`
- `action_tokens` powers all one-time emailed workflow links
- `app_settings` stores configurable workflow values in `jsonb`
- gallery identity comes from `events.gallery_url`
- optional per-event gallery video is stored on `events.youtube_embed_url`

## Where Relational Data Is Used

Primary relational usage is concentrated in a few places:

- `src/artists/index.njk`
  - artist listing page
- `src/artists/artist.11ty.js`
  - artist detail pages
- `src/crew/index.njk`
  - crew listing page
- `src/crew/profile.11ty.js`
  - crew detail pages
- `src/gallery/gallery.11ty.js`
  - gallery pages use relational event/profile metadata plus live S3 media listings
  - root event gallery pages may render an embedded YouTube video sourced from `events.youtube_embed_url`
- `src/perform.njk`
  - performer registration start + token-backed submission page

The rest of the site is mostly static Nunjucks templates.

## Normalized Data Shape

`lib/data/loadEmomData.js` returns Eleventy-facing normalized data that currently includes:

- `artistPages`
- `artistPagesSorted`
- `volunteerPages`
- `volunteerPagesSorted`
- `eventsByGalleryUrl`
- `galleries`
- `currentYear`

Compatibility notes:

- artist detail/index templates still use `artistPage.artist` as an alias for `artistPage.profile`
- volunteer pages use `volunteerPage.profile`
- role cross-links are already attached in the loader:
  - artist pages may have `volunteerProfile`
  - volunteer pages may have `artistProfile`
- gallery event metadata includes optional `YouTubeEmbedURL` on `eventsByGalleryUrl` entries
  - accepted DB inputs include watch/share/embed/shorts/live URLs, raw 11-char IDs, or pasted iframe HTML
  - rendering normalizes valid values to `https://www.youtube-nocookie.com/embed/<VIDEO_ID>`
  - if normalization fails, gallery pages render an `Open event video` fallback link
- public artist pages are filtered to approved, currently visible, non-expired profiles

## Shared Rendering Code

Shared profile-page rendering helpers live in:

- `lib/render/profilePage.js`

That module currently handles:

- HTML escaping
- thumbnail rendering
- public bio rendering
- social link rendering
- contact line rendering

Route generators should stay thin and keep only section-specific layout/content.

## Media And S3

The gallery system is hybrid:

- relational metadata comes from Postgres
- media inventory comes live from S3 at build time

Relevant files:

- `src/_data/s3files.js`
- `src/_data/imageHelpers.js`
- `src/_data/media_baseurl.js`
- `src/gallery/gallery.11ty.js`

Moving gallery media off S3 is not part of the current architecture yet.

## Current Site Sections

- `/`
  - home page in `src/index.njk`
- `/artists/`
  - artist list and artist detail pages
- `/crew/`
  - crew list and crew detail pages
- `/volunteer/`
  - volunteer signup/application page, currently separate from the `/crew/` profile section
- `/perform/`
  - performer registration page backed by `forms_bridge`
- `/gallery/`
  - gallery pages backed by S3 + Postgres

## Forms Bridge And Performer Workflow

The repo now includes a small Flask bridge for write-side forms and tokenized email workflows.

Primary files:

- `forms_bridge/app.py`
- `forms_bridge/db.py`
- `forms_bridge/performer_workflow.py`
- `forms_bridge/send_availability_reminders.py`
- `forms_bridge/send_admin_selection_links.py`
- `assets/scripts/performer_registration_form.js`
- `src/perform.njk`

Current performer workflow capabilities:

- `POST /api/forms/performer-registration/start`
  - sends a 24-hour one-time registration link
- `GET /api/forms/performer-registration/session?token=...`
  - loads existing profile context, social platforms, and eligible Open Mic dates
- `POST /api/forms/performer-registration/submit`
  - stores a moderated draft, social links, and requested dates
- `GET /api/forms/performer-registration/moderation/approve?token=...`
- `GET|POST /api/forms/performer-registration/moderation/deny?token=...`
- `GET /api/forms/performer-registration/availability/confirm?token=...`
- `GET /api/forms/performer-registration/availability/cancel?token=...`
- `GET|POST /api/forms/performer-registration/admin-selection?token=...`
- `GET|POST /api/forms/performer-registration/backup-selection?token=...`

Current workflow notes:

- registration and moderation are email-link driven, not login-driven
- existing profiles are matched by email first, then exact case-insensitive stage name as a fallback
- session prefill prefers the latest relevant submission for that email, including approved drafts when needed
- moderator emails include both the existing live profile snapshot and the submitted draft
- moderation links are single-use, and the opposite action is invalidated once one action is taken
- availability reminders and admin-selection links are sent by standalone bridge scripts
- SMTP delivery is relayed to `mail.f8.com.au` via bridge environment variables, not local `sendmail`
- `event_performer_selections` is the pre-event lineup source of truth; `performances` should only reflect who actually played

## Migrations

Database migrations currently live in `db/migrations/`.

Notable migrations in the repo:

- `2026-03-23-profiles-refactor.sql`
- `2026-03-23-profile-privacy-columns.sql`
- `2026-03-23-profile-bios.sql`
- `2026-04-01-performer-workflow.sql`
- `2026-04-01-backfill-existing-artist-approvals.sql`
- `2026-04-01-performer-workflow-grants.sql`
- `2026-04-01-standard-role-grants.sql`
- `2026-04-02-profile-id-defaults.sql`
- `2026-04-04-availability-reminder-tracking.sql`
- `2026-04-04-admin-selection-workflow.sql`
- `2026-04-05-cooldown-backup-status.sql`
- `2026-04-15-standby-reserve-status.sql`
- `2026-04-17-events-youtube-embed.sql`

Despite its filename, `2026-03-23-profile-bios.sql` currently moves bio fields onto `profile_roles` and drops the old `profiles.bio` / `profiles.is_bio_public` columns.

The 2026-04 migrations add the performer workflow schema, grants, reminder tracking, admin-selection flow, and identity/default improvements for older integer-key tables.

## Roles And DB Access

The standard DB roles currently expected by the repo are:

- `emom_site_reader`
- `emom_site_admin`
- `emom_forms_writer`

`DB_SETUP.md` is the current source for:

- role creation
- grants on current tables
- default privileges for future tables/sequences
- local SSH tunnel usage

The forms bridge should use `emom_forms_writer`, not the older merch-only writer role.

## Operational Docs

For performer-workflow continuity and diagrams, check:

- `REGO_STATUS.md`
- `PERFORMER_WORKFLOW_FLOW.md`
- `FORMS_API.md`
- `DB_SETUP.md`

## Docs Drift

The older memory-bank and Copilot docs are partly stale. In particular:

- they may describe CSV-era assumptions that no longer apply
- they may not reflect the `profiles` / `profile_roles` model
- they may not mention the `/crew/` section or the shared profile-page renderer

When updating documentation, verify against:

- `db/schema.sql`
- `lib/data/loadEmomData.js`
- `lib/render/profilePage.js`
- `forms_bridge/performer_workflow.py`
- `FORMS_API.md`
- `REGO_STATUS.md`
- `src/_data/`
- `src/artists/`
- `src/crew/`
- `src/gallery/`
- `src/perform.njk`

## Local Development (SQLite)

You can run the site locally without the Postgres SSH tunnel by using a SQLite export:

1. **Export from Postgres** (requires the tunnel to be running):
   ```bash
   npm run db:export
   ```
   This creates `emom.local.sqlite` in the repo root.

2. **Run locally with SQLite**:
   ```bash
   npm run start:local   # dev server
   npm run build:local   # build only
   ```
   These set `USE_SQLITE=true` and read from `emom.local.sqlite`.

The SQLite schema is in `db/schema-sqlite.sql`. The data loader (`lib/data/loadEmomData.js`) supports both Postgres and SQLite backends via the `USE_SQLITE` env var. The export script is at `scripts/export-to-sqlite.js`.

## Notes For Future Agents

- Do not reintroduce CSV assumptions; the current repo is Postgres-backed
- Keep the site statically generated unless there is an explicit architectural change
- Prefer extending the normalized loader and shared render helpers over duplicating section logic
- Do not assume public artist visibility is unconditional; loader output is now approval/visibility filtered
- Do not assume `performances` contains planned future lineups; use `event_performer_selections` for pre-event workflow state
- The performer workflow is in active development; check `REGO_STATUS.md` and `PERFORMER_WORKFLOW_FLOW.md` before changing it
- Treat `/volunteer/` and `/crew/` as different things:
  - `/volunteer/` is the signup/application page
  - `/crew/` is the public volunteer profile section
