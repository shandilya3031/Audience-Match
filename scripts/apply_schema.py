# Run from the repo root as a module: python -m scripts.apply_schema
# Applies infra/db/schema.sql against settings.postgres_dsn. Safe to re-run
# (schema.sql is idempotent). Substitutes the app_readonly role's password via
# psycopg2.sql.Literal (safely quoted) rather than the psql-CLI-specific
# `:'var'` syntax, since Postgres runs in Docker and psql isn't assumed to be
# on the host.
from pathlib import Path

import psycopg2
from psycopg2 import sql

from app.config import settings

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "infra" / "db" / "schema.sql"


def main() -> None:
    conn = psycopg2.connect(settings.postgres_dsn)
    conn.autocommit = True
    try:
        password_literal = sql.Literal(settings.postgres_readonly_password).as_string(conn)
        rendered = SCHEMA_PATH.read_text(encoding="utf-8").replace(
            "__APP_READONLY_PASSWORD__", password_literal
        )
        with conn.cursor() as cur:
            cur.execute(rendered)
    finally:
        conn.close()
    print("Schema applied.")


if __name__ == "__main__":
    main()
