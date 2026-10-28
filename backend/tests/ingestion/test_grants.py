"""Runtime-role privileges on the append-only tables (design D12, grant layer).

Rows are created by factories and committed (`transaction=True`), because the `ep_catalog`
connection opened by tests/roles.py can't see a test's uncommitted rows. Denials must be exactly
InsufficientPrivilege: a trigger's RestrictViolation would hide a missing REVOKE.
"""

from importlib import import_module

import psycopg
import pytest
from django.db import DatabaseError, connections, transaction

from config.env import env
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import EventStateChangeFactory, IngestionAuditEntryFactory
from tests.roles import expect_denied, run_as

STATE_CHANGE = "catalog.ingestion_eventstatechange"
AUDIT = "catalog.ingestion_ingestionauditentry"
CATALOG_ROLE = env.database_url_catalog

committed = pytest.mark.django_db(databases=[PERSONAL, CATALOG], transaction=True)


@committed
def test_catalog_role_update_of_state_change_history_denied():
    change = EventStateChangeFactory()

    expect_denied(
        CATALOG_ROLE,
        denied=f"UPDATE {STATE_CHANGE} SET kind = 'cancelled' WHERE id = '{change.id}'",
    )


@committed
def test_catalog_role_delete_of_state_change_denied():
    change = EventStateChangeFactory()

    expect_denied(CATALOG_ROLE, denied=f"DELETE FROM {STATE_CHANGE} WHERE id = '{change.id}'")


@committed
def test_catalog_role_update_of_audit_entry_denied():
    entry = IngestionAuditEntryFactory()

    expect_denied(
        CATALOG_ROLE, denied=f"UPDATE {AUDIT} SET action = 'edited' WHERE id = '{entry.id}'"
    )


@committed
def test_catalog_role_delete_of_audit_entry_denied():
    entry = IngestionAuditEntryFactory()

    expect_denied(CATALOG_ROLE, denied=f"DELETE FROM {AUDIT} WHERE id = '{entry.id}'")


@committed
def test_catalog_role_sets_propagated_at():
    change = EventStateChangeFactory()

    rows = run_as(
        CATALOG_ROLE,
        f"UPDATE {STATE_CHANGE} SET propagated_at = now() "
        f"WHERE id = '{change.id}' AND propagated_at IS NULL RETURNING id",
    )

    assert rows == [(change.id,)]


@pytest.mark.django_db(databases=[PERSONAL, CATALOG])
@pytest.mark.parametrize("table", [STATE_CHANGE, AUDIT])
def test_catalog_role_may_insert_and_read(table):
    rows = run_as(
        CATALOG_ROLE,
        f"SELECT has_table_privilege('{table}', 'INSERT'), "
        f"has_table_privilege('{table}', 'SELECT')",
    )

    assert rows == [(True, True)]


@pytest.mark.django_db(databases=[PERSONAL, CATALOG])
def test_migration_privilege_assertion_fails_when_revoke_missing():
    grants = import_module("apps.ingestion.migrations.0001_initial").GRANTS
    assertion = grants[grants.index("DO $$") :]

    with pytest.raises(DatabaseError) as excinfo, transaction.atomic(using=CATALOG):
        with connections[CATALOG].cursor() as cursor:
            cursor.execute(f"GRANT UPDATE ON {STATE_CHANGE} TO ep_catalog")
            cursor.execute(assertion)

    assert isinstance(excinfo.value.__cause__, psycopg.errors.RaiseException)
    assert "privileges on the append-only tables were not applied" in str(excinfo.value)
