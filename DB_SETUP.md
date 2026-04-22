# Postgres Tunnel Setup

This project uses a remote Postgres database that is not exposed directly to the internet. Access is intended to happen through an SSH tunnel to the remote host, with Postgres listening only on `127.0.0.1` on that host.

The database name is:

- `emomweb`

The recommended pattern is:

- a dedicated read-only Postgres role for the website build: `emom_site_reader`
- a dedicated write-capable Postgres role for admin/editor work: `emom_site_admin`
- a dedicated forms bridge writer role: `emom_forms_writer`
- a dedicated SSH user and SSH key for tunneling only
- SSH key restrictions that allow forwarding only to `127.0.0.1:5432`

## 1. Create The Standard Postgres Roles

SSH to the remote host using your normal admin account, then open `psql` as a superuser or database owner.

Create the read-only site role:

```sql
CREATE ROLE emom_site_reader
LOGIN
PASSWORD 'choose-a-long-random-password'
NOSUPERUSER
NOCREATEDB
NOCREATEROLE
NOINHERIT;

GRANT CONNECT ON DATABASE emomweb TO emom_site_reader;
```

Create the site admin role:

```sql
CREATE ROLE emom_site_admin
LOGIN
PASSWORD 'choose-a-long-random-password'
NOSUPERUSER
NOCREATEDB
NOCREATEROLE
NOINHERIT;

GRANT CONNECT, TEMP ON DATABASE emomweb TO emom_site_admin;
```

Create the forms bridge writer role:

```sql
CREATE ROLE emom_forms_writer
LOGIN
PASSWORD 'choose-a-long-random-password'
NOSUPERUSER
NOCREATEDB
NOCREATEROLE
NOINHERIT;

GRANT CONNECT, TEMP ON DATABASE emomweb TO emom_forms_writer;
```

Connect to the database and grant the baseline privileges:

```sql
\c emomweb

GRANT USAGE ON SCHEMA public TO emom_site_reader;
GRANT USAGE ON SCHEMA public TO emom_site_admin;
GRANT USAGE ON SCHEMA public TO emom_forms_writer;

GRANT SELECT ON ALL TABLES IN SCHEMA public TO emom_site_reader;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO emom_site_admin;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO emom_site_admin;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
  app_settings,
  profiles,
  profile_roles,
  profile_social_profiles,
  social_platforms,
  events,
  performances,
  action_tokens,
  profile_submission_drafts,
  profile_submission_social_profiles,
  requested_dates,
  moderation_actions,
  event_performer_selections,
  admin_selection_locks,
  newsletter_subscribe_requests,
  merch_interest_submissions,
  merch_interest_lines,
  merch_variants
TO emom_forms_writer;

GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO emom_forms_writer;
```

Make future tables and views inherit the same default privileges:

```sql
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT ON TABLES TO emom_site_reader;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO emom_site_admin;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO emom_site_admin;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO emom_forms_writer;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO emom_forms_writer;
```

Notes:

- Run `ALTER DEFAULT PRIVILEGES` as the role that owns future schema objects.
- `GRANT ... ON ALL TABLES IN SCHEMA public` covers ordinary tables and views such as `galleries`.
- `emom_site_reader` is intentionally broad read-only access because the static build and admin tooling may need to inspect multiple parts of the schema.
- `emom_forms_writer` is the intended DB role for `forms_bridge`, including the performer registration, moderation, reminder, and admin-selection workflows.
- If you already have older roles such as `emom_merch_writer`, migrate the bridge config over to `emom_forms_writer` rather than continuing to widen the merch-only role.

## 1A. Promote An Existing Profile To Moderator/Admin

If you are promoting an existing profile, do it in this order:

1. ensure the profile is a `person`
2. ensure it has a `volunteer` role in `profile_roles`
3. then set `is_moderator` / `is_admin`

That order matters because trigger validation requires moderator/admin profiles to also be volunteers.

```sql
\c emomweb

BEGIN;

-- Replace this value with the target profile id.
-- You can also locate by email first:
-- SELECT id, profile_name, email FROM profiles WHERE lower(email) = lower('person@example.com');

UPDATE profiles
SET profile_type = 'person'
WHERE id = 123;

INSERT INTO profile_roles (profile_id, role)
VALUES (123, 'volunteer')
ON CONFLICT (profile_id, role) DO NOTHING;

UPDATE profiles
SET is_moderator = TRUE,
    is_admin = TRUE
WHERE id = 123;

COMMIT;
```

Verify:

```sql
SELECT
  p.id,
  p.profile_name,
  p.email,
  p.profile_type,
  p.is_moderator,
  p.is_admin,
  EXISTS (
    SELECT 1
    FROM profile_roles pr
    WHERE pr.profile_id = p.id
      AND pr.role = 'volunteer'
  ) AS has_volunteer_role
FROM profiles p
WHERE p.id = 123;
```

## 2. Create A Dedicated SSH User For Tunneling

On the remote host:

```bash
sudo adduser --disabled-password --gecos "" emom-db-tunnel
sudo mkdir -p /home/emom-db-tunnel/.ssh
sudo chmod 700 /home/emom-db-tunnel/.ssh
sudo chown -R emom-db-tunnel:emom-db-tunnel /home/emom-db-tunnel/.ssh
```

## 3. Generate A Dedicated Local SSH Key

On the local machine:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/emom_db_tunnel -C "emom-db-tunnel"
```

This key should be used only for the database tunnel, not for normal shell login.

## 4. Restrict The Remote Authorized Key

Add the public key to:

- `/home/emom-db-tunnel/.ssh/authorized_keys`

Use a restricted entry like this:

```text
restrict,port-forwarding,permitopen="127.0.0.1:5432" ssh-ed25519 AAAAC3... emom-db-tunnel
```

Then fix permissions:

```bash
sudo chmod 600 /home/emom-db-tunnel/.ssh/authorized_keys
sudo chown emom-db-tunnel:emom-db-tunnel /home/emom-db-tunnel/.ssh/authorized_keys
```

What this does:

- `restrict` disables most SSH features by default
- `port-forwarding` re-enables forwarding
- `permitopen="127.0.0.1:5432"` allows forwarding only to the local Postgres port on the remote host

## 5. Check SSH Daemon Settings

In `/etc/ssh/sshd_config`, make sure public key auth and TCP forwarding are allowed:

```text
PubkeyAuthentication yes
AllowTcpForwarding yes
```

Optional per-user restriction:

```text
Match User emom-db-tunnel
    AllowTcpForwarding yes
    X11Forwarding no
    PermitTTY no
```

Reload SSH after config changes:

```bash
sudo systemctl reload sshd
```

On some systems:

```bash
sudo service ssh reload
```

## 6. Add A Local SSH Config Entry

Add this to `~/.ssh/config` on the local machine:

```sshconfig
Host emom-db
    HostName sydney.emom.me
    User emom-db-tunnel
    IdentityFile ~/.ssh/{the private key who's public key you sent to Stewart}
    IdentitiesOnly yes
    LocalForward 15432 127.0.0.1:5432
```

Start the tunnel:

```bash
ssh -N emom-db
```

This exposes the remote Postgres server locally on:

- `127.0.0.1:15432`

## 7. Validate The Tunnel

If `psql` is not installed locally, a quick connectivity check is:

```bash
nc -zv 127.0.0.1 15432
```

If `psql` is available locally, test the read-only role like this:

```bash
psql -h 127.0.0.1 -p 15432 -U emom_site_reader -d emomweb
```

Inside `psql`, these should work:

```sql
SELECT current_user;
SELECT * FROM events LIMIT 3;
SELECT * FROM profiles LIMIT 3;
```

This should fail:

```sql
INSERT INTO events (id, event_date, type_id, event_name, gallery_url)
VALUES (999, CURRENT_DATE, 1, 'x', NULL);
```

## 8. App Connection Settings

Once the tunnel is running, local tools can connect with:

```text
postgres://emom_site_reader:YOUR_PASSWORD@127.0.0.1:15432/emomweb
```

Or with separate env vars:

```text
PGHOST=127.0.0.1
PGPORT=15432
PGDATABASE=emomweb
PGUSER=emom_site_reader
PGPASSWORD=...
```

For this repo, those values can live in a local `.pgenv` file. A sanitized template is provided in `.pgenv-example`.

Typical usage:

```bash
cp .pgenv-example .pgenv
$EDITOR .pgenv

set -a
source ./.pgenv
set +a
```

## Operational Notes

- Keep the database bound to `127.0.0.1` on the remote host.
- Use `emom_site_reader` only for the website build and read-only tooling.
- Use `emom_site_admin` for admin/editor workflows that need write access across the schema.
- Use `emom_forms_writer` for the `forms_bridge` service and its scheduled scripts.
- Use a different Postgres role for schema migrations and ownership-level work.
- Use a different SSH key from the one used for normal interactive login.
- The repo now expects Postgres to be the only relational data source at build time.
