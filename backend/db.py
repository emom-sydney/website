import os
import psycopg


def get_connection_string():
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    host = os.getenv("PGHOST", "127.0.0.1")
    port = os.getenv("PGPORT", "15432")
    database = os.getenv("PGDATABASE", "emomweb")
    user = os.getenv("PGUSER")
    password = os.getenv("PGPASSWORD")

    parts = [f"host={host}", f"port={port}", f"dbname={database}"]
    if user:
        parts.append(f"user={user}")
    if password:
        parts.append(f"password={password}")

    return " ".join(parts)


def connect():
    return psycopg.connect(get_connection_string())
