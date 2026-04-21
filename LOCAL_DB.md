# Setting up a local Postgres database

Follow the instructions from the [PostGres website](https://www.postgresql.org/download/).

It should install the `pgAdmin` tool as well as the database which you will need for the following steps.

## 1. Create the database

Connect to pgAdmin with your admin user.

Using the Object Explorer:

- right click on Databases
- select Create >> Database...
- enter `emomweb` as the Database name.


Using the Tool workspace:

```sql
CREATE DATABASE emomweb;
```

## 2. Create A Read-Only Postgres Role

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

Put the password you set into your `.pgenv` file or wherever you setup database access.

## 3. Create the schema

Load the file `db/schemas.sql` into the Tool workspace.

## 4. Assign read access

```sql
\c emomweb

GRANT USAGE ON SCHEMA public TO emom_site_reader;

GRANT SELECT ON TABLE
    profiles,
    profile_roles,
    event_types,
    social_platforms,
    events,
    performances,
    profile_images,
    profile_social_profiles
    TO emom_site_reader;

GRANT SELECT ON galleries TO emom_site_reader;
```

Make future tables and views readable too (this is one statement):

```sql
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT ON TABLES TO emom_site_reader;
```

## 5. Configure app access

Local tools can connect with:

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

## Notes

- You cannot use a tunnel and a local database at the same time unless you change the port one of them is listening on.
