# Forms Guide

This repo is a statically generated Eleventy site. That matters for forms: the browser cannot write directly to Postgres, and there is no Node/Express app sitting behind the pages.

The pattern used here is:

1. build a static page in `src/`
2. optionally load build-time data from Postgres through Eleventy
3. submit the form with browser-side JavaScript to a same-origin API path
4. handle the POST in the small Python bridge in `forms_bridge/`
5. write to Postgres there

## Current Example

The reference implementation is the merch interest form.

Relevant files:

- `src/merch/index.njk`
- `src/merch/thanks.njk`
- `assets/scripts/merch_interest_form.js`
- `lib/data/loadEmomData.js`
- `forms_bridge/app.py`
- `forms_bridge/db.py`
- `FORMS_API.md`

The merch page is static HTML generated at build time. The form submits JSON to:

- `POST /api/forms/merch-interest`

That endpoint is served by the Python bridge, not by Eleventy.

## Repo Structure

There are three distinct layers.

### 1. Static page layer

This is the Eleventy page the user sees.

Typical location:

- `src/<section>/index.njk`
- or `src/<page>.njk`

This layer is responsible for:

- page layout
- form fields
- success/error UI
- loading any build-time options from `emom.*` data

### 2. Browser script layer

This is the client-side JavaScript that collects the form fields and submits them.

Typical location:

- `assets/scripts/<form_name>.js`

This layer is responsible for:

- reading form values from the DOM
- light validation
- shaping the JSON payload
- `fetch()` POST to `/api/forms/...`
- redirecting or showing errors

### 3. Forms bridge layer

This is the Python service that accepts the POST and writes to Postgres.

Files:

- `forms_bridge/app.py`
- `forms_bridge/db.py`

This layer is responsible for:

- request validation
- database validation
- transaction boundaries
- writing rows to Postgres
- returning JSON responses

## How Eleventy Fits In

Eleventy reads files in `src/` and generates static HTML into `_site/`.

Some forms need only fixed fields. In that case, you can build the page entirely in Nunjucks and skip the data loader.

Other forms need build-time options from the database. The merch form does that by loading data through:

- `src/_data/emom.js`
- `lib/data/loadEmomData.js`

That data is available to Nunjucks as `emom`.

Example from the merch page:

```njk
{% set merchItems = emom.merchItems %}
```

If you need a new form that uses relational data at build time, the usual place to extend is:

- `lib/data/loadEmomData.js`

Do not fetch directly from the database in a template.

## Standard Workflow For A New Form

For a new form, work in this order.

### 1. Define the database tables

Add the schema change in:

- `db/schema.sql`

Add a migration in:

- `db/migrations/`

Also decide on the database writer role for the new form. Do not automatically reuse the merch writer role for unrelated forms.

The recommended pattern is one DB role per logical form area, for example:

- `emom_merch_writer`
- `emom_contact_writer`
- `emom_volunteer_writer`

### 2. Decide whether the form needs build-time DB data

If the form is simple, you may not need any loader changes.

If the form needs options from Postgres, add those to:

- `lib/data/loadEmomData.js`

and expose them through `emom`.

Keep the loader data normalized for the template. Do not put template-specific DOM logic in the loader.

### 3. Create the static page

Add a new page in `src/`.

Examples:

- `src/merch/index.njk`
- `src/volunteer.njk`

At minimum, set:

```yaml
---
layout: "main.njk"
pageTitle: "My Form"
---
```

Then build the form HTML in Nunjucks.

### 4. Add a browser script

Create a script in:

- `assets/scripts/`

The usual shape is:

- find the form node
- read values
- validate obvious errors client-side
- send JSON to `/api/forms/<endpoint>`
- handle success and error states

The current merch script is a good template if you need:

- dynamic field resolution
- JSON submission
- redirect-on-success

### 5. Add a Python endpoint

Add a route in:

- `forms_bridge/app.py`

The current app uses Flask and a very direct style:

- validate `request.is_json`
- parse the payload
- normalize values
- write inside one transaction
- return JSON

For simple forms, copying the merch route and then narrowing it to the new payload is a sensible approach.

Keep shared helpers small and local. If a pattern repeats across multiple forms, then extract a helper.

### 6. Deploy both parts

A form usually has two deploy surfaces:

1. the static site
2. the Python bridge

Static page changes require:

- Eleventy rebuild
- redeploy `_site/`

Forms bridge changes require:

- sync `forms_bridge/`
- restart `emom-forms-bridge`

Current deploy scripts live in:

- `package.json`

## Build-Time Data Pattern

If your form needs DB-backed choices, the merch flow is the reference.

The path is:

1. `loadEmomData()` queries Postgres
2. the returned object is exposed through `src/_data/emom.js`
3. the Nunjucks page reads from `emom`

That means the HTML is baked at build time.

Important implication:

- changing form option data in Postgres does not update the live page until the site is rebuilt and redeployed

This is different from the Python bridge, which reads the database at request time.

## Browser Submission Pattern

The browser script should post to a same-origin path, not to a hardcoded hostname.

Current pattern:

```js
await fetch("/api/forms/merch-interest", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
  },
  body: JSON.stringify(payload),
});
```

That keeps the same static build portable between:

- `test.emom.me`
- `sydney.emom.me`

as long as nginx proxies `/api/forms/` to the forms bridge on that host.

## Python Bridge Pattern

The forms bridge currently exposes:

- `GET /health`
- `POST /api/forms/merch-interest`

The bridge uses:

- Flask
- `psycopg`
- direct SQL

Database connections come from:

- `DATABASE_URL`
- or `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`

See:

- `forms_bridge/db.py`

The current code keeps the API logic inside `forms_bridge/app.py`. That is fine for a small number of forms. If the bridge grows, the next cleanup would be splitting routes or handlers into separate modules.

## Response Pattern

The current convention is JSON like this.

Success:

```json
{
  "ok": true,
  "submission_id": 123
}
```

Error:

```json
{
  "ok": false,
  "error": "A valid email address is required."
}
```

Try to keep future endpoints consistent with this shape. It makes browser-side handling simpler.

## Validation Guidance

Split validation across the two layers:

### Browser-side validation

Use this for:

- required fields
- obvious formatting checks
- friendly immediate feedback

Do not rely on it for correctness.

### Server-side validation

Use this for:

- type validation
- integrity checks
- verifying foreign keys against active rows
- deduping or normalization
- final acceptance or rejection

The server must be able to reject a bad request even if the browser script is bypassed.

## Suggested Checklist For A New Form

When adding a form, verify all of these:

1. schema exists in `db/schema.sql`
2. migration exists in `db/migrations/`
3. write-role permissions are correct
4. static page exists in `src/`
5. browser script exists in `assets/scripts/`
6. API route exists in `forms_bridge/app.py`
7. nginx exposes `/api/forms/...`
8. the forms bridge has been redeployed and restarted
9. the static site has been rebuilt and redeployed
10. `curl` can submit a valid payload successfully

## Example: Minimal New Form

Suppose you want a simple contact form.

You would typically:

1. add `contact_messages` table + migration
2. create `src/contact/index.njk`
3. create `assets/scripts/contact_form.js`
4. add `POST /api/forms/contact` in `forms_bridge/app.py`
5. create a DB role such as `emom_contact_writer`
6. grant only the required privileges
7. deploy the static page and the bridge

If the contact form has no dynamic options, you do not need to touch `loadEmomData.js`.

## Operational Notes

The bridge is intended to run behind nginx and `systemd`.

Deployment templates live in:

- `deploy/systemd/emom-forms-bridge.service`
- `deploy/nginx/emom-forms-bridge.conf`
- `deploy/forms_bridge.env.example`

See:

- `FORMS_API.md`

for the environment and runtime setup details.

## Current Limitations

A few repo-specific limitations are worth knowing:

- the forms bridge is small and intentionally direct; it is not a full application framework
- changes to build-time form options require an Eleventy rebuild
- the current deploy scripts sync `forms_bridge/`, but do not automatically reinstall Python dependencies on the server
- the bridge currently logs server-side exceptions, but there is no richer admin dashboard or audit UI yet

## Recommended Style For Future Work

When adding forms in this repo:

- keep the public page static
- keep runtime writes in the Python bridge
- keep DB-driven option lists in `loadEmomData.js`
- use one DB writer role per logical form area
- prefer small explicit SQL over heavy abstraction
- keep frontend scripts small and purpose-built

That matches how the repo works today and should scale cleanly to a few more forms without introducing unnecessary complexity.
