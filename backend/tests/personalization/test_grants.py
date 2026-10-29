"""Runtime-role privileges on the append-only audit table (design D28, grant layer).

Rows are created by factories and committed (`transaction=True`), because the `ep_personal`
connection opened by tests/roles.py can't see a test's uncommitted rows. Denials must be
exactly InsufficientPrivilege: a trigger's RestrictViolation would hide a missing REVOKE.
"""

from importlib import import_module

import psycopg
import pytest
from django.db import DatabaseError, connections, transaction

from config.env import env
from shared.db import CATALOG, PERSONAL
from tests.personalization.factories import PersonalizationAuditEntryFactory
from tests.roles import expect_denied, run_as

AUDIT = "personal.personalization_personalizationauditentry"
PERSONAL_ROLE = env.database_url_personal

committed = pytest.mark.django_db(databases=[PERSONAL, CATALOG], transaction=True)


@committed
def test_personal_role_update_of_audit_entry_denied():
    entry = PersonalizationAuditEntryFactory()

    expect_denied(
        PERSONAL_ROLE, denied=f"UPDATE {AUDIT} SET action = 'edited' WHERE id = '{entry.id}'"
    )


@committed
def test_personal_role_delete_of_audit_entry_denied():
    entry = PersonalizationAuditEntryFactory()

    expect_denied(PERSONAL_ROLE, denied=f"DELETE FROM {AUDIT} WHERE id = '{entry.id}'")


@pytest.mark.django_db(databases=[PERSONAL, CATALOG])
@pytest.mark.parametrize(
    "table",
    [
        AUDIT,
        "personal.personalization_personalevent",
        "personal.personalization_savedevent",
        "personal.personalization_conflictpair",
    ],
)
def test_personal_role_may_insert_and_read(table):
    rows = run_as(
        PERSONAL_ROLE,
        f"SELECT has_table_privilege('{table}', 'INSERT'), "
        f"has_table_privilege('{table}', 'SELECT')",
    )

    assert rows == [(True, True)]


@pytest.mark.django_db(databases=[PERSONAL, CATALOG])
def test_personal_role_may_write_the_product_tables():
    # The three product tables are ordinary DML tables; only the audit table is fenced off.
    for table in (
        "personal.personalization_personalevent",
        "personal.personalization_savedevent",
        "personal.personalization_conflictpair",
    ):
        rows = run_as(
            PERSONAL_ROLE,
            f"SELECT has_table_privilege('{table}', 'UPDATE'), "
            f"has_table_privilege('{table}', 'DELETE')",
        )

        assert rows == [(True, True)], table


@pytest.mark.django_db(databases=[PERSONAL, CATALOG])
def test_migration_privilege_assertion_fails_when_revoke_missing():
    grants = import_module("apps.personalization.migrations.0001_initial").GRANTS
    assertion = grants[grants.index("DO $$") :]

    with pytest.raises(DatabaseError) as excinfo, transaction.atomic(using=PERSONAL):
        with connections[PERSONAL].cursor() as cursor:
            cursor.execute(f"GRANT UPDATE, DELETE ON {AUDIT} TO ep_personal")
            cursor.execute(assertion)

    assert isinstance(excinfo.value.__cause__, psycopg.errors.RaiseException)
    assert "privileges on the append-only tables were not applied" in str(excinfo.value)
