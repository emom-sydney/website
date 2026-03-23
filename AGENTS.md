# Repository Guide

This file is the Codex-facing source of truth for this repository. The notes in `.amazonq/rules/memory-bank/` and `.github/copilot-instructions.md` are historical context only and should not be treated as authoritative without checking the code.

## What This Repo Is

- Static site for `sydney.emom.me`
- Built with Eleventy and ES modules
- Main source lives in `src/`
- Generated output goes to `_site/`

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

Important model details:

- `profiles` is the base entity for both people and groups
- `profiles.profile_type` is `person` or `group`
- `profile_roles.role` is currently `artist` or `volunteer`
- role-specific bio fields live on `profile_roles`:
  - `bio`
  - `is_bio_public`
- shared privacy/contact fields live on `profiles`:
  - `email`
  - `is_email_public`
  - `is_name_public`
- `events.event_date` is the canonical date field
- gallery identity comes from `events.gallery_url`

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
- `/gallery/`
  - gallery pages backed by S3 + Postgres

## Migrations

Database migrations currently live in `db/migrations/`.

Notable migrations in the repo:

- `2026-03-23-profiles-refactor.sql`
- `2026-03-23-profile-privacy-columns.sql`
- `2026-03-23-profile-bios.sql`

Despite its filename, `2026-03-23-profile-bios.sql` currently moves bio fields onto `profile_roles` and drops the old `profiles.bio` / `profiles.is_bio_public` columns.

## Docs Drift

The older memory-bank and Copilot docs are partly stale. In particular:

- they may describe CSV-era assumptions that no longer apply
- they may not reflect the `profiles` / `profile_roles` model
- they may not mention the `/crew/` section or the shared profile-page renderer

When updating documentation, verify against:

- `db/schema.sql`
- `lib/data/loadEmomData.js`
- `lib/render/profilePage.js`
- `src/_data/`
- `src/artists/`
- `src/crew/`
- `src/gallery/`

## Notes For Future Agents

- Do not reintroduce CSV assumptions; the current repo is Postgres-backed
- Keep the site statically generated unless there is an explicit architectural change
- Prefer extending the normalized loader and shared render helpers over duplicating section logic
- Treat `/volunteer/` and `/crew/` as different things:
  - `/volunteer/` is the signup/application page
  - `/crew/` is the public volunteer profile section
