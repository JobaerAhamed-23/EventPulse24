"""Migrations put every table in its AD-3 schema."""

import pytest
from django.db import connections

from shared.db import CATALOG, PERSONAL

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])


def tables_in(schema: str) -> set[str]:
    with connections[PERSONAL].cursor() as cursor:
        cursor.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = %s", [schema]
        )
        return {row[0] for row in cursor.fetchall()}


def test_personal_schema_holds_user_framework_and_personal_probe_tables():
    expected = {
        "identity_user",
        "auth_group",
        "auth_permission",
        "django_content_type",
        "django_session",
        "django_admin_log",
        "personal_probe_note",
        "django_migrations",
    }

    assert expected <= tables_in("personal")


def test_catalog_schema_holds_only_catalog_tables():
    assert tables_in("catalog") == {"catalog_probe_thing", "django_migrations"}


def test_public_schema_has_no_tables():
    assert tables_in("public") == set()


def test_each_alias_records_its_own_migrations():
    for alias, schema in ((PERSONAL, "personal"), (CATALOG, "catalog")):
        with connections[alias].cursor() as cursor:
            cursor.execute("SELECT current_schema()")
            assert cursor.fetchone()[0] == schema
            cursor.execute("SELECT count(*) FROM django_migrations")
            assert cursor.fetchone()[0] > 0
