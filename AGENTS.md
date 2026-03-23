# Repository Guide

This file is the Codex-facing source of truth for this repository. The notes in `.amazonq/rules/memory-bank/` and `.github/copilot-instructions.md` are useful historical context, but they have drifted from the current codebase in several places.

## What This Repo Is

- Static site for `sydney.emom.me`
- Built with Eleventy and ES modules
- Main content lives in `src/`
- Generated output goes to `_site/`

## Build And Deployment

- Local build: `npx @11ty/eleventy`
- Local dev server: `npx @11ty/eleventy --serve`
- Eleventy config lives in `.eleventy.js`

## Actual Data Architecture

Relational site data now comes from Postgres through `src/_data/emom.js`, which loads and normalizes rows via `lib/data/loadEmomData.js`.

Current relational tables:
- `profiles`
- `profile_roles`
- `profile_images`
- `profile_social_profiles`
- `events`
- `event_types`
- `performances`
- `social_platforms`

## Where Relational Data Is Used

Primary relational usage is limited and explicit:

- `src/artists/index.njk`
  - Lists artists from normalized artist page data
- `src/artists/artist.11ty.js`
  - Generates one page per artist from normalized data
- `src/gallery/gallery.11ty.js`
  - Builds gallery pages from S3 object listings
  - Derives gallery prefixes from `events.GalleryURL`
  - For root gallery pages, uses normalized event -> artist data

The rest of the site is mostly static templates.

## Data Sources

- `src/_data/s3files.js`
  - Lists S3 objects under `gallery/<prefix>`
- `src/_data/imageHelpers.js`
  - Generates thumbnails under `assets/img/th/`
- `src/_data/emom.js`
  - Loads normalized site data through the repository layer in `lib/data/loadEmomData.js`

The gallery system is already hybrid:
- Relational metadata comes from Postgres
- Media inventory comes live from S3 at build time

## Current Constraints And Drift

The older memory-bank and Copilot docs are partly stale:

- The repo has artist pages and more templates than the older structure notes describe
- `.github/copilot-instructions.md` mentions files and behavior that do not exactly match the current repo

When updating docs, prefer this file and verify against code first.

## Postgres

Recommended approach:
- Keep the site statically generated with Eleventy
- Keep S3-backed gallery media as a separate concern

Current status:
- The repository-local loader is Postgres-backed
- Postgres connections are expected to come through the local SSH tunnel described in `DB_SETUP.md`

Suggested schema:
- `profiles`
- `profile_roles`
- `profile_images`
- `social_platforms`
- `profile_social_profiles`
- `event_types`
- `events`
- `performances`
- optional later: `galleries`

Compatibility principle:
- Preserve current field names at the template boundary during the first migration phase
- Normalize DB column names in SQL if desired, but map them back before handing data to Eleventy

## Notes For Future Agents

- Do not assume the guidance files under `.amazonq/` or `.github/` are current.
- Verify claims against `.eleventy.js`, `src/_data/`, and the templates/generators.
- Preserve the static-site deployment model unless there is an explicit decision to introduce a runtime app tier.
