# Postgres Tunnel Setup

This project uses a remote Postgres database that is not exposed directly to the internet. Access is intended to happen through an SSH tunnel to the remote host, with Postgres listening only on `127.0.0.1` on that host.

The database name is:

- `emomweb`

The recommended pattern is:

- a dedicated read-only Postgres role for the website build
- a dedicated SSH user and SSH key for tunneling only
- SSH key restrictions that allow forwarding only to `127.0.0.1:5432`

A local database will also work, in which case you will not need the tunnel (post 5432 is the standard PostGresQL port).
See [LOCAL_DB.md](./LOCAL_DB.md) for setting up a local database.

## 1. Create A Dedicated SSH User For Tunneling

This should be named for the user doing the tunneling.

On the remote host:

```bash
sudo adduser --disabled-password --gecos "" emom-db-tunnel
sudo mkdir -p /home/emom-db-tunnel/.ssh
sudo chmod 700 /home/emom-db-tunnel/.ssh
sudo chown -R emom-db-tunnel:emom-db-tunnel /home/emom-db-tunnel/.ssh
```

## 2. Generate A Dedicated Local SSH Key

On your local machine:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/emom_db_tunnel -C "emom-db-tunnel"
```

This key should be used only for the database tunnel, not for normal shell login.

## 3. Restrict The Remote Authorized Key

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

## 4. Check SSH Daemon Settings

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

## 5. Add A Local SSH Config Entry

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

## 6. Validate The Tunnel

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

## 7. App Connection Settings

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

For this repo, those values can live in a local `.pgenv` file. A sanitized template is provided in `.pgenv-example`. *Do not* check your local `.pgenv` file in to GitHub!

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
