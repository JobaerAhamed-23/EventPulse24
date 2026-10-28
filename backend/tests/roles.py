"""Run SQL as a runtime role against the test database, to test privileges (AD-3, D12).

Tests connect as the owner role; these helpers open a separate raw `psycopg` connection as a
runtime role. It can't see the calling test's uncommitted rows, so privilege tests that need
existing rows create them with `transaction=True` (committed) first. Every connection rolls back.
"""

import psycopg
import pytest
from django.db import connections

from shared.db import PERSONAL

LOCK_TIMEOUT = "2s"  # a lock wait fails the test instead of hanging it


def _connect(role_url: str) -> psycopg.Connection:
    test_db = connections[PERSONAL].settings_dict["NAME"]
    return psycopg.connect(role_url, dbname=test_db)


def run_as(role_url: str, *statements: str):
    """Run statements in order as the role, in one transaction that always rolls back.

    Returns the last statement's rows (`None` if it returns none). On failure, re-raises the
    original psycopg error with a note naming the failing statement.
    """
    with _connect(role_url) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute(f"SET lock_timeout = '{LOCK_TIMEOUT}'")
                rows = None
                for index, sql in enumerate(statements, start=1):
                    try:
                        cursor.execute(sql)
                    except psycopg.Error as error:
                        error.add_note(f"statement {index} of {len(statements)}: {sql}")
                        raise
                    rows = cursor.fetchall() if cursor.description else None
                return rows
        finally:
            conn.rollback()


def expect_denied(role_url: str, *setup: str, denied: str) -> psycopg.errors.InsufficientPrivilege:
    """Assert `denied` fails with exactly InsufficientPrivilege after `setup` succeeds.

    "Exactly" matters: a trigger's RestrictViolation must not pass for a missing REVOKE.
    """
    with _connect(role_url) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute(f"SET lock_timeout = '{LOCK_TIMEOUT}'")
                for index, sql in enumerate(setup, start=1):
                    try:
                        cursor.execute(sql)
                    except psycopg.Error as error:
                        pytest.fail(f"setup statement {index} failed ({error!r}): {sql}")
                try:
                    cursor.execute(denied)
                except psycopg.Error as error:
                    if type(error) is not psycopg.errors.InsufficientPrivilege:
                        pytest.fail(f"expected InsufficientPrivilege, got {error!r}: {denied}")
                    return error
                pytest.fail(f"statement was allowed: {denied}")
        finally:
            conn.rollback()
