import psycopg2

from app.config import settings


def get_connection() -> "psycopg2.extensions.connection":
    """Connection using the app_user (read-write) DSN."""
    return psycopg2.connect(settings.postgres_dsn)


def get_readonly_connection() -> "psycopg2.extensions.connection":
    """Connection using the app_readonly (SELECT-only) DSN -- this is the
    connection the Aggregator agent (Phase 3) will use."""
    return psycopg2.connect(settings.postgres_readonly_dsn)
