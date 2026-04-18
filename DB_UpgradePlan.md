# Database Upgrade Runbook

This runbook upgrades production schema to match the target branch schema using a generated catch-up SQL script, with staging performed inside Postgres (same host/cluster).

It is written so we can later automate it in Ansible.

## Scope

- In scope:
  - Postgres schema upgrade and validation
  - forms bridge reconfiguration/checks
  - site data-loader connectivity checks (Eleventy build path)
- Out of scope:
  - content/data parity checks for test vs prod records
  - infrastructure provisioning

## Components That Currently Use Postgres

1. `forms_bridge` Flask app
2. `forms_bridge` scheduled scripts:
   - `python -m forms_bridge.send_availability_reminders`
   - `python -m forms_bridge.send_admin_selection_links`
3. Eleventy data loader for builds:
   - `src/_data/emom.js` -> `lib/data/loadEmomData.js`

Notes:
- If DB name changes at cutover, both forms bridge and any build/deploy job that runs Eleventy with Postgres credentials must point to the new DB.
- In this repo, DB config is via `DATABASE_URL` or `PG*` env vars.

## Prerequisites

- Shell access on DB host with a superuser-capable account (often `postgres`).
- `psql`, `pg_dump`, `createdb`, `dropdb` installed.
- A production schema dump already saved as `db/prod-schema.sql`.
- A target schema dump from the release branch test DB (or an equivalent DB with desired final schema), saved as `db/target-schema.sql`.
- Maintenance window for write downtime (forms bridge writes should be paused during cutover).

## Naming Convention Used Below

Adjust names to your environment:

- Current production DB: `emomweb`
- In-DB staging copy: `emomweb_stage`
- Safety backup copy at cutover: `emomweb_old`

## Phase 1: Generate and Review Catch-up SQL

### 1. Build a normalized forward-only diff source

Use schema-only dumps with stable options:

```bash
pg_dump --dbname=emomweb --schema-only --no-owner --no-privileges --no-comments --quote-all-identifiers --file=db/prod-schema.sql

# target schema should come from branch test DB that represents desired final state
pg_dump --dbname=<target_db> --schema-only --no-owner --no-privileges --no-comments --quote-all-identifiers --file=db/target-schema.sql
```

### 2. Generate a catch-up script

Use your preferred diff tooling (for example `migra`, `apgdiff`, `sqldef`, or manual curated SQL).

Requirements for `catchup.sql`:

- Forward-only changes from prod -> target
- Idempotent where practical (`IF EXISTS`/`IF NOT EXISTS`)
- No destructive data operations unless explicitly required and reviewed
- Include role grants for new objects (`emom_site_reader`, `emom_site_admin`, `emom_forms_writer`)

Save as:

- `db/migrations/<YYYY-MM-DD>-prod-catchup.sql`

### 3. Review checklist for `catchup.sql`

Confirm all of the following before applying anywhere:

- New tables/columns/constraints/indexes are present.
- Trigger/function changes are included where required.
- No accidental `DROP TABLE`/`DROP COLUMN` on live data.
- No renames that should have been additive changes.
- Grants include new tables/sequences for forms bridge role.

## Phase 2: Postgres-Only Staging Rehearsal

This validates the upgrade against a production-like copy before cutover.

### 1. Freeze write traffic (temporary)

Stop forms bridge and scheduled jobs so production data stays consistent while cloning.

Example (adjust service names):

```bash
sudo systemctl stop emom-forms-bridge
sudo systemctl stop emom-send-availability-reminders || true
sudo systemctl stop emom-send-admin-selection-links || true
```

If jobs are cron-based, disable/comment them for the window.

### 2. Clone production DB to staging DB inside Postgres

Run as superuser:

```sql
-- connect to postgres db, not emomweb
\c postgres

-- terminate stale connections to staging db name if it already exists
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = 'emomweb_stage' AND pid <> pg_backend_pid();

DROP DATABASE IF EXISTS emomweb_stage;
CREATE DATABASE emomweb_stage TEMPLATE emomweb;
```

### 3. Apply catch-up SQL to staging DB

```bash
psql --dbname=emomweb_stage --set ON_ERROR_STOP=1 --file=db/migrations/<YYYY-MM-DD>-prod-catchup.sql
```

### 4. Re-run role grants safety block (recommended)

```bash
psql --dbname=emomweb_stage --set ON_ERROR_STOP=1 --file=db/migrations/2026-04-01-standard-role-grants.sql
```

If applicable for your release:

```bash
psql --dbname=emomweb_stage --set ON_ERROR_STOP=1 --file=db/migrations/2026-04-17-admin-selection-locks.sql
```

### 5. Schema validation checks on staging DB

```bash
# full schema dump for diff
pg_dump --dbname=emomweb_stage --schema-only --no-owner --no-privileges --no-comments --quote-all-identifiers --file=/tmp/stage-schema.sql

diff -u db/target-schema.sql /tmp/stage-schema.sql > /tmp/schema-stage-vs-target.diff || true
```

Expected: empty diff or only accepted non-functional ordering differences.

### 6. Runtime sanity checks against staging DB

Run these as each role where possible:

- `emom_site_reader`: can `SELECT` from required tables/views.
- `emom_forms_writer`: can insert/update workflow tables and read required reference tables.
- `emom_site_admin`: broad write sanity.

Minimal smoke SQL:

```sql
-- as reader
SELECT count(*) FROM profiles;
SELECT count(*) FROM events;

-- as forms writer
SELECT count(*) FROM app_settings;
SELECT count(*) FROM profile_submission_drafts;
SELECT count(*) FROM action_tokens;

-- as admin
SELECT count(*) FROM event_performer_selections;
```

Optional app-level smoke:

- Point forms bridge env to `PGDATABASE=emomweb_stage`.
- Start bridge.
- Hit health and a safe read endpoint (or dry-run workflow start).

After rehearsal success, proceed to cutover.

## Phase 3: Cutover

1. Stop forms bridge + scheduled jobs (freeze writes).
2. Upgrade `emomweb_stage` as above.
3. Terminate active DB sessions to `emomweb`/`emomweb_stage`.
4. Rename DBs: `emomweb -> emomweb_old`, `emomweb_stage -> emomweb`.
5. Keep service env on `PGDATABASE=emomweb` (usually no env change needed).
6. Restart services/jobs.
7. Validate.
8. Keep `emomweb_old` for rollback window, then drop later.

### 4. Post-cutover checks

- forms bridge logs show successful DB connections
- a safe workflow read path responds
- Eleventy build can connect/read via `emom_site_reader`

## Phase 4: Validation After Cutover

Run and record outputs:

```bash
pg_dump --dbname=emomweb --schema-only --no-owner --no-privileges --no-comments --quote-all-identifiers --file=/tmp/prod-after-cutover.sql

diff -u db/target-schema.sql /tmp/prod-after-cutover.sql > /tmp/prod-after-vs-target.diff || true
```

Expected: no unexpected differences.

Application checks:

1. forms bridge boot and request handling
2. reminder/admin selection scripts start without schema errors
3. Eleventy build (`npx @11ty/eleventy`) succeeds with production reader credentials

## Phase 5: Data Integrity Fingerprint Check

This verifies no unexpected data changed during the upgrade.

### 1. Capture pre-upgrade snapshot from source prod DB

Run before applying changes

```bash
psql --dbname=emomweb --set ON_ERROR_STOP=1 --file=/tmp/data-fingerprint.sql > /tmp/prod-before-fingerprint.txt
```

### 2. Capture post-cutover snapshot from new prod DB

Run immediately after cutover:

```bash
psql --dbname=emomweb --set ON_ERROR_STOP=1 --file=/tmp/data-fingerprint.sql > /tmp/prod-after-fingerprint.txt
```

### 3. Compare snapshots

```bash
diff -u /tmp/prod-before-fingerprint.txt /tmp/prod-after-fingerprint.txt > /tmp/prod-data-fingerprint.diff || true
```

Expected: no differences unless explicitly planned.

### 4. Fingerprint SQL file

Create `/tmp/data-fingerprint.sql` with the following:

```sql
\pset tuples_only on
\pset format unaligned

\echo === ROW COUNTS (all public tables) ===
SELECT format(
  'SELECT %L AS table_name, count(*)::bigint AS row_count FROM %I.%I;',
  tablename, schemaname, tablename
)
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY tablename;
\gexec

\echo === CRITICAL TABLE CHECKSUMS ===
-- For these tables we hash deterministic, ordered JSON rows.
-- If IDs are not unique or if table structure changes, update ordering/key choice.
SELECT 'profiles' AS table_name,
       md5(COALESCE(string_agg(md5(row_to_json(t)::text), '' ORDER BY t.id::text), '')) AS checksum
FROM profiles t;

SELECT 'profile_roles' AS table_name,
       md5(COALESCE(string_agg(md5(row_to_json(t)::text), '' ORDER BY t.profile_id::text, t.role), '')) AS checksum
FROM profile_roles t;

SELECT 'events' AS table_name,
       md5(COALESCE(string_agg(md5(row_to_json(t)::text), '' ORDER BY t.id::text), '')) AS checksum
FROM events t;

SELECT 'performances' AS table_name,
       md5(COALESCE(string_agg(md5(row_to_json(t)::text), '' ORDER BY t.id::text), '')) AS checksum
FROM performances t;

SELECT 'profile_images' AS table_name,
       md5(COALESCE(string_agg(md5(row_to_json(t)::text), '' ORDER BY t.id::text), '')) AS checksum
FROM profile_images t;

SELECT 'profile_social_profiles' AS table_name,
       md5(COALESCE(string_agg(md5(row_to_json(t)::text), '' ORDER BY t.id::text), '')) AS checksum
FROM profile_social_profiles t;

SELECT 'social_platforms' AS table_name,
       md5(COALESCE(string_agg(md5(row_to_json(t)::text), '' ORDER BY t.id::text), '')) AS checksum
FROM social_platforms t;

\echo === SEQUENCE SANITY ===
-- Confirms sequence current position is not behind max(id).
-- Ignore tables where IDs are not sequence-backed.
SELECT 'profiles_id_seq' AS sequence_name,
       (SELECT COALESCE(MAX(id), 0) FROM profiles) AS max_id,
       (SELECT last_value FROM profiles_id_seq) AS seq_last_value;

SELECT 'profile_social_profiles_id_seq' AS sequence_name,
       (SELECT COALESCE(MAX(id), 0) FROM profile_social_profiles) AS max_id,
       (SELECT last_value FROM profile_social_profiles_id_seq) AS seq_last_value;
```

### 5. Interpretation guidance

- Row counts differ:
  - likely write traffic occurred during window, or data-mutating SQL ran unexpectedly.
- Checksums differ with same row counts:
  - row values changed; inspect migration/update statements and app writes during the window.
- Sequence last value behind max ID:
  - run `setval(...)` to advance sequence before resuming normal writes.

## Rollback Plan

## If using Option A (repoint)

- Revert env `PGDATABASE`/`DATABASE_URL` to old prod DB.
- Restart forms bridge/jobs.
- Investigate and fix staging DB before next attempt.

## If using Option B (rename swap)

If immediate rollback is needed:

```sql
\c postgres
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname IN ('emomweb', 'emomweb_old')
  AND pid <> pg_backend_pid();

ALTER DATABASE emomweb RENAME TO emomweb_bad;
ALTER DATABASE emomweb_old RENAME TO emomweb;
```

Then restart services.

## Reconfiguration Checklist

Ensure these are verified at cutover:

- forms bridge env (`DATABASE_URL` or `PG*`):
  - `PGHOST`
  - `PGPORT`
  - `PGDATABASE`
  - `PGUSER` (expected: `emom_forms_writer`)
  - `PGPASSWORD`
- any service/cron invoking:
  - `python -m forms_bridge.send_availability_reminders`
  - `python -m forms_bridge.send_admin_selection_links`
- build/deploy environment for Eleventy:
  - `DATABASE_URL` or `PG*` used by `lib/data/loadEmomData.js`
  - reader role (`emom_site_reader`) still valid in target DB

## Operational Notes

- Do not drop old prod immediately after cutover. Keep `emomweb_old` until confidence window passes.
- If a column already exists (for example `events.youtube_embed_url`), additive migrations with `IF NOT EXISTS` are safe and should not require pre-deletion.
- Preserve migration files in git history even if using catch-up scripts for release upgrades.

## Evidence to Capture (for change record)

- `catchup.sql` file path and commit hash
- rehearsal apply log on `emomweb_stage`
- schema diffs:
  - `stage vs target`
  - `prod-after-cutover vs target`
- service restart timestamps
- smoke test results
