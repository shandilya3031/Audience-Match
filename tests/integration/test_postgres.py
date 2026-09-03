# Needs a live local PostgreSQL instance (see infra/db/schema.sql /
# scripts/apply_schema.py) -- not run as part of tests/unit.
import psycopg2
import pytest

from app.db.postgres import get_connection, get_readonly_connection


def test_get_connection_succeeds():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            assert cur.fetchone() == (1,)
    finally:
        conn.close()


def test_get_readonly_connection_succeeds():
    conn = get_readonly_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            assert cur.fetchone() == (1,)
    finally:
        conn.close()


def test_readonly_connection_cannot_write():
    conn = get_readonly_connection()
    try:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO chat_history (session_key, turn_index, role, content) "
                    "VALUES ('test_module_test', 0, 'human', 'should not be allowed')"
                )
    finally:
        conn.rollback()
        conn.close()
