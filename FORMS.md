# Forms Guide

This repo is a statically generated Eleventy site, so browser forms cannot write directly to Postgres. All runtime writes go through the small Python bridge in `forms_bridge/`.

## Current Pattern

The current stack for forms and tokenized workflows is:

1. static page in `src/`
2. browser-side JavaScript in `assets/scripts/`
3. same-origin request to `/api/forms/...`
4. Flask handler in `forms_bridge/`
5. Postgres write and email/token workflow there

## Current Implementations

There are currently two active form areas:

- merch interest
- performer registration and scheduling workflow
- volunteer role-bidding workflow

Relevant files:

- `src/merch/index.njk`
- `assets/scripts/merch_interest_form.js`
- `src/perform.njk`
- `assets/scripts/performer_registration_form.js`
- `forms_bridge/app.py`
- `forms_bridge/db.py`
- `forms_bridge/performer_workflow.py`
- `forms_bridge/volunteer_workflow.py`
- `forms_bridge/send_availability_reminders.py`
- `forms_bridge/send_admin_selection_links.py`
- `forms_bridge/send_moderation_token_reminders.py`
- `FORMS_API.md`

## Repo Layers

### Static page layer

Files in `src/` define:

- page layout
- form fields
- any static copy or helper text
- success/error presentation

Examples:

- `src/merch/index.njk`
- `src/perform.njk`

### Browser script layer

Files in `assets/scripts/` define:

- DOM reads/writes
- light client-side validation
- JSON payload shaping
- `fetch()` calls to `/api/forms/...`
- in-page success/error updates

Examples:

- `assets/scripts/merch_interest_form.js`
- `assets/scripts/performer_registration_form.js`

### Forms bridge layer

Files in `forms_bridge/` define:

- request validation
- DB validation and writes
- token creation and invalidation
- email sending
- HTML responses for token-driven moderation/admin actions

Main files:

- `forms_bridge/app.py`
- `forms_bridge/db.py`
- `forms_bridge/performer_workflow.py`

## Build-Time Data

If a form page needs build-time relational data, load it through:

- `src/_data/emom.js`
- `lib/data/loadEmomData.js`

Do not fetch directly from Postgres in Nunjucks templates.

Important distinction:

- Eleventy build-time data changes require a rebuild and redeploy
- forms bridge requests read Postgres live at request time

## Current Browser Submission Pattern

Use same-origin paths, not hardcoded hostnames:

```js
await fetch("/api/forms/merch-interest", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
  },
  body: JSON.stringify(payload),
});
```

That keeps the same build portable between environments such as `test.emom.me` and `sydney.emom.me`, assuming nginx proxies `/api/forms/` correctly.

## Current Bridge Pattern

The bridge currently exposes:

- `GET /api/forms/health`
- `POST /api/forms/merch-interest`
- performer registration start/session/submit
- moderation approve/deny actions
- availability confirm/cancel actions
- admin lineup selection (events/start/page/save)
- admin selection lock heartbeat + release
- admin confirmation resend action
- standby promotion
- volunteer registration start/session/submit
- volunteer moderation approve/deny actions
- volunteer claims-link start/session/cancel actions

The bridge uses:

- Flask
- `psycopg`
- direct SQL
- SMTP relay for outbound email

Database connections come from:

- `DATABASE_URL`
- or `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`

Bridge mail configuration comes from:

- `FORMS_EMAIL_FROM`
- `FORMS_SMTP_HOST`
- `FORMS_SMTP_PORT`
- `FORMS_SITE_BASE_URL`

## Performer Workflow Notes

The performer registration system is no longer just a simple form POST. It is a tokenized workflow built around:

- email-first registration
- moderated profile drafts
- requested Open Mic dates
- availability reminders
- final lineup selection
- standby and reserve states
- event-level admin editing locks

Current pre-event lineup state lives in:

- `event_performer_selections`

The volunteer role-bidding workflow is similarly tokenized and uses:

- `volunteer_roles` (global role defaults)
- `event_volunteer_role_overrides` (per-event overrides)
- `profile_submission_volunteer_claims` (pending claims on draft)
- `profile_submission_volunteer_general_claims` (pending non-event claims on draft)
- `event_volunteer_role_claims` (live selected/standby/cancelled claims)
- `volunteer_general_role_claims` (live active/withdrawn non-event claims)

Actual played sets should still be written later to:

- `performances`

## Standard Workflow For A New Form

When adding a new form area:

1. define schema in `db/schema.sql`
2. add migration in `db/migrations/`
3. update grants/default privileges if needed
4. create the static page in `src/`
5. create the browser script in `assets/scripts/`
6. add bridge handlers in `forms_bridge/`
7. deploy both the static site and the bridge

Do not assume rebuilding Eleventy is enough if the logic lives in the bridge.

## Validation Guidance

### Browser-side validation

Use this for:

- required fields
- obvious formatting checks
- friendly immediate feedback

### Server-side validation

Use this for:

- type validation
- integrity checks
- foreign key validation
- deduping and normalization
- token validation
- final acceptance or rejection

The server must be able to reject bad requests even if the browser script is bypassed.

## Deployment Surfaces

Most form changes affect one or both of:

1. static site output in `_site/`
2. `forms_bridge` runtime code

Typical checklist:

1. schema/migration updated
2. grants updated
3. static page exists
4. browser script exists
5. bridge route/helper exists
6. site rebuilt with Eleventy
7. `_site/` redeployed
8. bridge code redeployed
9. bridge service restarted
10. end-to-end request tested with browser and `curl`

## Operational Notes

Deployment templates live in:

- `deploy/systemd/emom-forms-bridge.service`
- `deploy/nginx/emom-forms-bridge.conf`
- `deploy/forms_bridge.env.example`

See:

- `FORMS_API.md`
- `PERFORMER_WORKFLOW_FLOW.md`
- `DB_SETUP.md`

for runtime and DB role details.

## Recommended Style

When adding forms in this repo:

- keep the public page static
- keep runtime writes in the Python bridge
- keep DB-backed option lists in `loadEmomData.js` when they are build-time concerns
- use explicit SQL
- prefer purpose-built browser scripts over generic abstractions
- document token/email workflows clearly when a “form” is really a multi-step process
