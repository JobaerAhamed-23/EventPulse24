"""Runtime-role privileges on the append-only tables (design D28, grant layer; D11).

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
from tests.personalization.factories import (
    DigestCompositionFactory,
    PersonalizationAuditEntryFactory,
)
from tests.roles import expect_denied, run_as

AUDIT = "personal.personalization_personalizationauditentry"
COMPOSITION = "personal.personalization_digestcomposition"
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


@committed
def test_personal_role_update_of_digest_composition_denied():
    """AD-10: a composition is immutable, so the runtime role may not rewrite one (D11)."""
    composition = DigestCompositionFactory()

    expect_denied(
        PERSONAL_ROLE,
        denied=f"UPDATE {COMPOSITION} SET bucket = 5 WHERE id = '{composition.id}'",
    )


@committed
def test_personal_role_delete_of_digest_composition_denied():
    composition = DigestCompositionFactory()

    expect_denied(PERSONAL_ROLE, denied=f"DELETE FROM {COMPOSITION} WHERE id = '{composition.id}'")


@pytest.mark.django_db(databases=[PERSONAL, CATALOG])
@pytest.mark.parametrize(
    "table",
    [
        AUDIT,
        COMPOSITION,
        "personal.personalization_personalevent",
        "personal.personalization_savedevent",
        "personal.personalization_conflictpair",
        "personal.personalization_pulsedigest",
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
    # The product tables are ordinary DML tables; only the append-only ones are fenced off.
    # `PulseDigest` is one of them: it is a fact about a day, not an append-only history
    # (D11).
    for table in (
        "personal.personalization_personalevent",
        "personal.personalization_savedevent",
        "personal.personalization_conflictpair",
        "personal.personalization_pulsedigest",
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


@pytest.mark.django_db(databases=[PERSONAL, CATALOG])
def test_the_digest_composition_grant_assertion_fails_when_revoke_missing():
    """The migration's own assertion block, on the table this item added (D11).

    A `REVOKE` by a non-owner merely *warns*, so the migration carries a `DO $$` block
    that fails it if the REVOKE did not apply. This test proves the block is not
    decorative: with the privilege granted, the block raises.
    """
    grants = import_module(
        "apps.personalization.migrations.0007_digestcomposition_pulsedigest"
    ).GRANTS
    assertion = grants[grants.index("DO $$") :]

    with pytest.raises(DatabaseError) as excinfo, transaction.atomic(using=PERSONAL):
        with connections[PERSONAL].cursor() as cursor:
            cursor.execute(f"GRANT UPDATE, DELETE ON {COMPOSITION} TO ep_personal")
            cursor.execute(assertion)

    assert isinstance(excinfo.value.__cause__, psycopg.errors.RaiseException)
    assert "privileges on the append-only tables were not applied" in str(excinfo.value)
