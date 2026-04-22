**sydney.emom.me**

This is the codebase for sydney.emom.me website. We are building with the [11ty](https://www.11ty.dev) Static Site Generator. I have used
CoPilot extensively to kick things off because I'm too impatient to read the doco, but I have very little idea what I'm
doing within VSCode so it's all default settings and stuff but (somewhat to my surprise) it seems to be mostly working
reasonably well and the only hallucinations that have been happening are by me.

However the fact remains that all good code here is mine, everything else is the LLM's fault.

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

### Starting to introduce role based actions.

| Volunteer role | Description | Key constraints |
|---|---|---|
| moderator | Gets moderation emails/links for approving or denying performer submissions, plus reminder/open-slot/backup-selection notifications. | Must be a `person`, and must have `profile_roles.role = 'volunteer'`. |
| admin | Gets admin lineup-selection links and can start/access the admin selection flow for event lineup curation. | Must be a `person`, and must have `profile_roles.role = 'volunteer'`. |

## Build Process
To build the site files, from the top level directory run
```
npx @11ty/eleventy 
```
and the site will be generated in the _site directory. (add the `--serve` flag to have it served to `localhost:8080`)

See the functions defined in [package.json](./package.json) for some useful `npm run` shortcuts

To add a gallery for an event:
 - upload files to https://media.emom.me/gallery/*galleryname* (TODO add a file uploader)
 - set *galleryname* in the `events.gallery_url` value in Postgres
 - build the site as detailed above
 - sync to the test webserver `rsync -rv --delete _site/ root@sydney.emom.me:/var/www/html/test.emom.me/`
 - sync to the live webserver `rsync -rv --delete _site/ root@sydney.emom.me:/var/www/html/sydney.emom.me/`

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

## Postgres runtime

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

`DATABASE_URL` can be used instead of the individual `PG*` variables if preferred, but the current repo workflow uses `.pgenv`.

## Forms Bridge Newsletter Subscribe

The forms bridge now supports newsletter subscribe with time-limited email confirmation links.

Required environment variables for this flow:

- `FORMS_SITE_BASE_URL` (for confirmation link generation)
- `KEILA_API_BASE_URL` (defaults to `https://keila.emom.me`)
- `KEILA_API_KEY` (Bearer API key for Keila contacts API)
- `NEWSLETTER_TOKEN_TTL_HOURS` (defaults to `24`)

## Forms Bridge

The forms bridge is a small Flask app for handling a variety of form inputs on the site.

It currently handles:

- A merch survey form
- TODO: Regular contact form
- [performer registration workflow](PERFORMER_WORKFLOW_FLOW.md)
  - moderator approve/deny actions
  - availability confirm/cancel actions
  - final lineup selection for an event
  - standby promotion after cancellations

Supporting scripts:

- `python -m forms_bridge.send_availability_reminders`
- `python -m forms_bridge.send_admin_selection_links`

Bridge deployment and runtime details live in:

- [FORMS.md](./FORMS.md)
- [FORMS_API.md](./FORMS_API.md)

## Forms Bridge Newsletter Subscribe

The forms bridge now supports newsletter subscribe with time-limited email confirmation links.

Required environment variables for this flow:

- `FORMS_SITE_BASE_URL` (for confirmation link generation)
- `KEILA_API_BASE_URL` (defaults to `https://keila.emom.me`)
- `KEILA_API_KEY` (Bearer API key for Keila contacts API)
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
- media inventory is read live from S3 at build time

To add a gallery for an event:

1. TODO: upload files to media server (currently a manual process involving ssh tunnels on non-standard ports through a jump host - not worth documenting ;)
2. set `events.gallery_url` to `<galleryname>` (TODO: more correct would be `events.gallery_slug`) 
3. rebuild the site
4. deploy `_site/`

## Key Docs

- [AGENTS.md](./AGENTS.md)
- [DB_SETUP.md](./DB_SETUP.md)
- [FORMS.md](./FORMS.md)
- [FORMS_API.md](./FORMS_API.md)
- [REGO_STATUS.md](./REGO_STATUS.md)
- [PERFORMER_WORKFLOW_FLOW.md](./PERFORMER_WORKFLOW_FLOW.md)

## TODO:

  - media uploads page
  - reinstate contact form
  - move code repo to forgejo instance git.emom.me 
  - calendar/contacts (https://sabre.io/baikal ?)
  - work out a way for 11ty to build galleries without having to be logged in to AWS :DONE
  - thumbnails for images in galleries: :DONE
  - artist profile pages: :DONE
  - set up MX for the domain :DONE

# Thoughts

A website for a small community organisation has different resource needs compared to most social or groupware kind of
sites. If you're not chasing user numbers, if the website is run by a small subset of a small group of eager volunteers,
I think there's an opportunity to build something quite effective yet simple and portable.

My theory is that an emom event will likely only ever have a handful of volunteers running it at any one time, usually
out of a Google spreadsheet which is basically just lists of text information anyway. So what if the backend was just a
text document that anyone could understand and edit? Obviously you'd put that behind secure authentication etc but
again, we don't have to necessarily spin up an entire MFA infrastructure when everyone involved actually physically
knows each other from having met at the music nights. In other words, we can base the security architecture around the
idea of physical presence and contacts, which I think would open up a bunch of unique possibilities. Some scripts on a
USB stick with an embedded ssh key could just about do everything we want if we set up the workflows right.

Imagine a performer arrives at the venue and gets a QR code with URL and a one-time token on a piece of wood (make it an
art item they can keep) which activates their profile page on the emom website, and where they can enter their details (
stage name, name of tunes they’re playing, social URLs etc) and not only do they get a free profile page right away, we
can also generate images & html that OBS can use for title screens and text crawls while they’re playing.

We had a data projector showing the artists names at the November event, but that was a static image generated before we
knew the order the acts would be playing in. Have the projector instead show a web page that dynamically updates with
Now Playing. Another page would allow selection of the artist name so that MC - having it open on their phone alongside
the profile page and their own notes for each act - just has to tap on it to update all the signage. (I simplify, but I
think it's all quite doable by putting the right pieces together in the right way)

## Resources
- [logos](https://drive.google.com/drive/u/0/mobile/folders/1oDfZQdZb9NQhx_in6vafl0fO-Ktstt2t/1EMySK_hN9GL3JIHSHvwSoSFfeiV8tKy9?usp=sharing&sort=13&direction=a)
