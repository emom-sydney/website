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

Eleventy loads CSV files from `src/_data/` via `.eleventy.js` using `csv-parse/sync`.

Current CSV-backed collections:
- `artists.csv`
- `artistimages.csv`
- `artistsocialprofiles.csv`
- `events.csv`
- `eventtypes.csv`
- `performances.csv`
- `socialplatforms.csv`

Current row counts as of 2026-03-18:
- artists: 51
- artistimages: 37
- artistsocialprofiles: 54
- events: 14
- eventtypes: 2
- performances: 63
- socialplatforms: 14

ID handling:
- `.eleventy.js` converts any column named `ID` or ending in `ID` to integers
- This means CSV header casing matters
- Mixed conventions exist today: `ArtistID` and `EventID` are PascalCase, while `artistID` and `socialPlatformID` are lower camel case

## Where The CSV Data Is Used

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

## Non-CSV Data Sources

- `src/_data/s3files.js`
  - Lists S3 objects under `gallery/<prefix>`
- `src/_data/imageHelpers.js`
  - Generates thumbnails under `assets/img/th/`
- `src/_data/emom.js`
  - Loads normalized site data through the repository layer in `lib/data/loadEmomData.js`

The gallery system is already hybrid:
- Relational metadata comes from CSV
- Media inventory comes live from S3 at build time

## Current Constraints And Drift

The older memory-bank and Copilot docs are partly stale:

- The repo has artist pages and more templates than the older structure notes describe
- `.github/copilot-instructions.md` mentions files and behavior that do not exactly match the current repo

When updating docs, prefer this file and verify against code first.

## If We Migrate To Postgres

Recommended approach:
- Keep the site statically generated with Eleventy
- Replace CSV reads with a build-time data access layer that fetches from Postgres
- Keep S3-backed gallery media as a separate concern

Practical first step:
- Keep one repository-local loader that can read from CSV now and Postgres later
- Make templates consume normalized objects without caring whether they came from CSV or Postgres

Current status:
- The repository-local loader now supports both CSV and Postgres
- Select the source with `EMOM_DATA_SOURCE`
- Postgres connections are expected to come through the local SSH tunnel described in `DB_SETUP.md`

Suggested schema:
- `artists`
- `artist_images`
- `social_platforms`
- `artist_social_profiles`
- `event_types`
- `events`
- `performances`
- optional later: `galleries`

Migration principle:
- Preserve current field names at the template boundary during the first migration phase
- Normalize DB column names in SQL if desired, but map them back before handing data to Eleventy

## Sensible Migration Sequence

1. Keep the repository-local data access layer that can read from CSV or Postgres.
2. Keep moving join logic out of templates into precomputed view-model data.
3. Switch `EMOM_DATA_SOURCE` to `postgres` once tunnel access and credentials are in place.
4. Only after the build is stable, add write paths or admin tooling.

## Notes For Future Agents

- Do not assume the guidance files under `.amazonq/` or `.github/` are current.
- Verify claims against `.eleventy.js`, `src/_data/`, and the templates/generators.
- Preserve the static-site deployment model unless there is an explicit decision to introduce a runtime app tier.
