**sydney.emom.me**

This is the codebase for sydney.emom.me website. We are building with the [11ty](https://www.11ty.dev) Static Site Generator. (I appreciate it's called Build Awesome now but yuck it's a terrible name and I can't bring myself to call it that.) I'm using various coding tools which are working pretty well. Yes that includes AI but I also advocate strongly for guillotines.. Happy to talk about that over a beer some time if you want. Otherwise if that's a problem for you just move along thanks.

## Current Architecture

- static site source in `src/`
- generated output in `_site/`
- relational build-time data loaded through:
  - `src/_data/emom.js`
  - `lib/data/loadEmomData.js`
- write-side forms and tokenized workflows handled by:
  - `backend/app.py`
  - `backend/db.py`
  - `backend/performer_workflow.py`

The site currently includes:

- artist and crew profile sections
- gallery pages backed by Postgres metadata & the media server manifest
- performer registration and moderation workflow for Open Mic events

## Build Process
To build the site files, from the top level directory run
```
npx @11ty/eleventy 
```
and the site will be generated in the _site directory. (add the `--serve` flag to have it served to `localhost:8080`)

See the functions defined in [package.json](./package.json) for some useful `npm run` shortcuts

## Postgres runtime

The build process reads relational data from Postgres through an SSH tunnel documented in [DB_SETUP.md](./DB_SETUP.md).

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

`DATABASE_URL` can be used instead of the individual `PG*` variables if preferred, but the current repo workflow uses `.pgenv`.

## Backend

The backend is a Flask app providing `/api/v1`, the `/admin` staff area,
email workflows, and database writes.

It currently handles:

- Regular contact form
- Newsletter & Alumni list subscribe workflow
- [performer registration workflow](PERFORMER_WORKFLOW_FLOW.md)
  - moderator approve/deny actions
  - availability confirm/cancel actions
  - final lineup selection for an event
  - standby promotion after cancellations

Supporting scripts:

- `python -m backend.jobs.send_availability_reminders`
- `python -m backend.jobs.send_lineup_selection_links`
- `python -m backend.jobs.send_moderation_reminders`

Backend deployment and runtime details live in:

- [BACKEND.md](./BACKEND.md)
- [API.md](./API.md)

## Mailing List Subscribe

The backend supports newsletter and alumni mailing list subscription with time-limited email confirmation links.

Required environment variables for this flow:

- `PUBLIC_SITE_BASE_URL` (for confirmation link generation)
- `KEILA_API_BASE_URL` (defaults to `https://keila.emom.me`)
- `KEILA_NEWSLETTER_API_KEY` (Bearer API key for the Keila newsletter project)
- `KEILA_ALUMNI_API_KEY` (Bearer API key for the Keila alumni project)
- `NEWSLETTER_TOKEN_TTL_HOURS` (defaults to `24`)

## Public Data Rules

Public artist pages are filtered by approval and visibility:

- `is_profile_approved = true`
- `profile_visible_from IS NULL OR <= CURRENT_DATE`
- `profile_expires_on >= CURRENT_DATE`

Planned future lineups are stored in `event_performer_selections`, actual played lineups are in `performances`.

## Galleries

Gallery pages are hybrid:

- relational event/profile metadata comes from Postgres
- media inventory is read from the media server manifest (https://media.emom.me:909/.well-known/) at build time

To add a gallery for an event:

1. [Upload files](https://uploades.media.emom.me) to media server and move into place (currently a manual process involving ssh tunnels on non-standard ports through a jump host - not worth documenting ;)
2. set `events.gallery_url` to `<galleryname>` (TODO: more correct would be `events.gallery_slug`) 
3. rebuild the site
4. deploy `_site/`

To add an event video embed on a gallery page:
 - set `events.youtube_embed_url` for the event row that has the matching `events.gallery_url`
 - accepted values include:
   - `https://www.youtube.com/watch?v=VIDEO_ID`
   - `https://youtu.be/VIDEO_ID`
   - `https://www.youtube.com/embed/VIDEO_ID`
   - `https://www.youtube.com/shorts/VIDEO_ID`
   - `https://www.youtube.com/live/VIDEO_ID`
   - raw `VIDEO_ID` (11 chars)
   - pasted iframe embed HTML (the `src` URL is extracted)
 - the site normalizes valid inputs to a privacy-enhanced embed URL on render:
   - `https://www.youtube-nocookie.com/embed/VIDEO_ID`
 - if a value is present but cannot be normalized, gallery pages show a fallback `Open event video` link instead of an iframe


## Key Docs

- [AGENTS.md](./AGENTS.md)
- [DB_SETUP.md](./DB_SETUP.md)
- [BACKEND.md](./BACKEND.md)
- [API.md](./API.md)
- [PERFORMER_WORKFLOW_FLOW.md](./PERFORMER_WORKFLOW_FLOW.md)

# Thoughts

A website for a small community organisation has different resource needs compared to most social or groupware kind of
sites. If you're not chasing user numbers, if the website is run by a small subset of a small group of eager volunteers,
I think there's an opportunity to build something quite effective yet simple and portable.
