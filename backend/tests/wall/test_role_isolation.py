"""Runtime roles: each can use its own schema and nothing else (AD-3), in the migrated test DB."""

import psycopg
import pytest
from django.db import connections

from config.env import env
from shared.db import CATALOG, PERSONAL

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

CATALOG_TABLE = "catalog.catalog_probe_thing"
PERSONAL_TABLE = "personal.personal_probe_note"


def run_as(role_url: str, sql: str):
    """Run one statement as a runtime role against the test DB; always roll back."""
    test_db = connections[PERSONAL].settings_dict["NAME"]
    with psycopg.connect(role_url, dbname=test_db) as conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                return cursor.fetchall() if cursor.description else None
        finally:
            conn.rollback()


def test_catalog_role_reads_and_writes_catalog():
    rows = run_as(
        env.database_url_catalog,
        f"INSERT INTO {CATALOG_TABLE} (name) VALUES ('x') RETURNING name",
    )

    assert rows == [("x",)]
    assert run_as(env.database_url_catalog, f"SELECT count(*) FROM {CATALOG_TABLE}") == [(0,)]


def test_personal_role_reads_personal():
    assert run_as(env.database_url_personal, f"SELECT count(*) FROM {PERSONAL_TABLE}") == [(0,)]


@pytest.mark.parametrize(
    ("role_url", "table"),
    [
        (env.database_url_catalog, PERSONAL_TABLE),
        (env.database_url_personal, CATALOG_TABLE),
    ],
    ids=["catalog-reads-personal", "personal-reads-catalog"],
)
def test_role_reading_other_schema_denied(role_url, table):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        run_as(role_url, f"SELECT * FROM {table}")


@pytest.mark.parametrize(
    ("role_url", "schema"),
    [
        (env.database_url_catalog, "catalog"),
        (env.database_url_personal, "personal"),
        (env.database_url_catalog, "public"),
        (env.database_url_personal, "public"),
    ],
    ids=["catalog-ddl", "personal-ddl", "catalog-public", "personal-public"],
)
def test_runtime_role_create_table_denied(role_url, schema):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        run_as(role_url, f"CREATE TABLE {schema}.ddl_probe (id int)")
