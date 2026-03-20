# Postgres Tunnel Setup

This project uses a remote Postgres database that is not exposed directly to the internet. Access is intended to happen through an SSH tunnel to the remote host, with Postgres listening only on `127.0.0.1` on that host.

The database name is:

- `emomweb`

The recommended pattern is:

- a dedicated read-only Postgres role for the website build
- a dedicated SSH user and SSH key for tunneling only
- SSH key restrictions that allow forwarding only to `127.0.0.1:5432`

## 1. Create A Read-Only Postgres Role

SSH to the remote host using your normal admin account, then open `psql` as a superuser or database owner.

Create the read-only role:

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

Connect to the database and grant read access:

```sql
\c emomweb

GRANT USAGE ON SCHEMA public TO emom_site_reader;

GRANT SELECT ON TABLE
  artists,
  event_types,
  social_platforms,
  events,
  performances,
  artist_images,
  artist_social_profiles
TO emom_site_reader;

GRANT SELECT ON galleries TO emom_site_reader;
```

Make future tables and views readable too:

```sql
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT ON TABLES TO emom_site_reader;
```

Notes:

- Run `ALTER DEFAULT PRIVILEGES` as the role that owns future schema objects.
- Keep a separate write-capable role for imports and admin work.

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
    HostName your.server.example
    User emom-db-tunnel
    IdentityFile ~/.ssh/emom_db_tunnel
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
```

This should fail:

```sql
INSERT INTO events VALUES (999, CURRENT_DATE, 'x', 1, 'x', NULL);
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
- Use a different Postgres role for imports, migrations, and admin work.
- Use a different SSH key from the one used for normal interactive login.
- The repo now expects Postgres to be the only relational data source at build time.
