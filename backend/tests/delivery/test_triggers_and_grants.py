"""The delivery audit table's append-only trigger and the runtime role's grants.

The trigger is the real guarantee (it binds every role and raw SQL); the REVOKE is the
runtime role's half of it. Denials must be exactly InsufficientPrivilege: a trigger's
RestrictViolation would hide a missing REVOKE.
"""

from importlib import import_module

import psycopg
import pytest
from django.db import DatabaseError, connections, transaction

from config.env import env
from shared.db import CATALOG, PERSONAL
from tests.delivery.factories import DeliveryAuditEntryFactory
from tests.roles import expect_denied, run_as

AUDIT = "personal.delivery_deliveryauditentry"
PERSONAL_ROLE = env.database_url_personal

committed = pytest.mark.django_db(databases=[PERSONAL, CATALOG], transaction=True)


# --- The append-only trigger -------------------------------------------------------------------


@committed
def test_audit_entry_update_rejected():
    entry = DeliveryAuditEntryFactory()

    with pytest.raises(Exception) as excinfo, transaction.atomic(using=PERSONAL):
        with connections[PERSONAL].cursor() as cursor:
            cursor.execute(f"UPDATE {AUDIT} SET action = 'edited' WHERE id = %s", [entry.id])

    assert isinstance(excinfo.value.__cause__, psycopg.errors.RestrictViolation)
    assert "is append-only" in str(excinfo.value.__cause__)


@committed
def test_audit_entry_delete_rejected():
    entry = DeliveryAuditEntryFactory()

    with pytest.raises(Exception) as excinfo, transaction.atomic(using=PERSONAL):
        with connections[PERSONAL].cursor() as cursor:
            cursor.execute(f"DELETE FROM {AUDIT} WHERE id = %s", [entry.id])

    assert isinstance(excinfo.value.__cause__, psycopg.errors.RestrictViolation)
    assert "is append-only" in str(excinfo.value.__cause__)


# --- The runtime role's grants ------------------------------------------------------------------


@committed
def test_personal_role_update_of_audit_entry_denied():
    entry = DeliveryAuditEntryFactory()

    expect_denied(
        PERSONAL_ROLE, denied=f"UPDATE {AUDIT} SET action = 'edited' WHERE id = '{entry.id}'"
    )


@committed
def test_personal_role_delete_of_audit_entry_denied():
    entry = DeliveryAuditEntryFactory()

    expect_denied(PERSONAL_ROLE, denied=f"DELETE FROM {AUDIT} WHERE id = '{entry.id}'")


@pytest.mark.django_db(databases=[PERSONAL, CATALOG])
@pytest.mark.parametrize(
    "table",
    [
        AUDIT,
        "personal.delivery_reminderplan",
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
def test_personal_role_may_write_the_reminder_plan_table():
    # The plan is an ordinary DML table; only the audit table is fenced off.
    table = "personal.delivery_reminderplan"

    rows = run_as(
        PERSONAL_ROLE,
        f"SELECT has_table_privilege('{table}', 'UPDATE'), "
        f"has_table_privilege('{table}', 'DELETE')",
    )

    assert rows == [(True, True)]


@pytest.mark.django_db(databases=[PERSONAL, CATALOG])
def test_migration_privilege_assertion_fails_when_revoke_missing():
    grants = import_module("apps.delivery.migrations.0001_initial").GRANTS
    assertion = grants[grants.index("DO $$") :]

    with pytest.raises(DatabaseError) as excinfo, transaction.atomic(using=PERSONAL):
        with connections[PERSONAL].cursor() as cursor:
            cursor.execute(f"GRANT UPDATE, DELETE ON {AUDIT} TO ep_personal")
            cursor.execute(assertion)

    assert isinstance(excinfo.value.__cause__, psycopg.errors.RaiseException)
    assert "privileges on the append-only tables were not applied" in str(excinfo.value)
