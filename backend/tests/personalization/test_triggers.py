"""The database triggers from migration 0001 (design D24, D28), tested below the ORM.

Every statement is raw SQL on the personal connection (the owner role in tests), so the
Python-level guards are never in the path: a pass here proves the trigger itself.
Rejections are asserted as psycopg's RestrictViolation, the trigger's ERRCODE.
"""

from contextlib import contextmanager

import psycopg
import pytest
from django.db import IntegrityError, connections, transaction

from apps.personalization.models import ConflictPair
from shared.db import PERSONAL
from tests.personalization.factories import (
    FIRST_START,
    ConflictPairFactory,
    PersonalizationAuditEntryFactory,
)

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

CONFLICT_PAIR = "personal.personalization_conflictpair"
AUDIT = "personal.personalization_personalizationauditentry"


def execute(sql: str, params=()) -> int:
    with connections[PERSONAL].cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.rowcount


@contextmanager
def restricted(message: str):
    """Expect the block to fail in a trigger with this message (rolled back to a savepoint)."""
    with pytest.raises(IntegrityError) as excinfo, transaction.atomic(using=PERSONAL):
        yield
    assert isinstance(excinfo.value.__cause__, psycopg.errors.RestrictViolation)
    assert message in str(excinfo.value.__cause__)


def column(table: str, name: str, row_id):
    with connections[PERSONAL].cursor() as cursor:
        cursor.execute(f"SELECT {name} FROM {table} WHERE id = %s", [row_id])
        return cursor.fetchone()[0]


# --- A closed conflict pair is immutable (D24) ------------------------------------------------


def test_resolved_pair_status_update_rejected():
    pair = ConflictPairFactory.create(
        status=ConflictPair.Status.RESOLVED,
        resolution=ConflictPair.Resolution.KEEP_BOTH,
        resolved_at=FIRST_START,
    )

    with restricted("is immutable"):
        execute(
            f"UPDATE {CONFLICT_PAIR} SET status = 'active' WHERE id = %s",
            [pair.id],
        )


def test_resolved_pair_resolution_rewrite_rejected():
    # AD-21: a resolved pair's resolution is never rewritten.
    pair = ConflictPairFactory.create(
        status=ConflictPair.Status.RESOLVED,
        resolution=ConflictPair.Resolution.KEEP_BOTH,
        resolved_at=FIRST_START,
    )

    with restricted("is immutable"):
        execute(
            f"UPDATE {CONFLICT_PAIR} SET resolution = 'delete_new' WHERE id = %s",
            [pair.id],
        )


def test_resolved_pair_resolved_at_change_rejected():
    pair = ConflictPairFactory.create(
        status=ConflictPair.Status.RESOLVED,
        resolution=ConflictPair.Resolution.KEEP_BOTH,
        resolved_at=FIRST_START,
    )

    with restricted("is immutable"):
        execute(
            f"UPDATE {CONFLICT_PAIR} SET resolved_at = now() + interval '1 hour' WHERE id = %s",
            [pair.id],
        )


def test_cleared_pair_update_rejected():
    # A pair closed by a state change is not a user resolution, and is equally final.
    pair = ConflictPairFactory.create(
        status=ConflictPair.Status.CLEARED_BY_STATE_CHANGE,
        resolved_at=FIRST_START,
    )

    with restricted("is immutable"):
        execute(f"UPDATE {CONFLICT_PAIR} SET status = 'active' WHERE id = %s", [pair.id])


def test_active_pair_may_still_be_updated():
    # An active pair is the one row a command still writes to: it resolves it.
    pair = ConflictPairFactory.create()

    assert execute(
        f"UPDATE {CONFLICT_PAIR} SET status = 'resolved', resolution = 'keep_both', "
        f"resolved_at = now() WHERE id = %s",
        [pair.id],
    )
    assert column(CONFLICT_PAIR, "status", pair.id) == "resolved"


def test_active_pair_unrelated_field_may_be_updated():
    pair = ConflictPairFactory.create()

    assert execute(f"UPDATE {CONFLICT_PAIR} SET detected_at = now() WHERE id = %s", [pair.id])


def test_resolved_pair_unrelated_field_may_be_updated():
    # The trigger guards the three state columns, not the whole row: `updated_at` moves on
    # every save, and freezing that would make a resolved row un-saveable.
    pair = ConflictPairFactory.create(
        status=ConflictPair.Status.RESOLVED,
        resolution=ConflictPair.Resolution.KEEP_BOTH,
        resolved_at=FIRST_START,
    )

    assert execute(
        f"UPDATE {CONFLICT_PAIR} SET updated_at = now() WHERE id = %s",
        [pair.id],
    )
    assert column(CONFLICT_PAIR, "status", pair.id) == "resolved"
    assert column(CONFLICT_PAIR, "resolution", pair.id) == "keep_both"


# --- The audit table is append-only (D28) -----------------------------------------------------


def test_audit_entry_update_rejected():
    entry = PersonalizationAuditEntryFactory.create()

    with restricted("is append-only"):
        execute(f"UPDATE {AUDIT} SET action = 'edited' WHERE id = %s", [entry.id])


def test_audit_entry_delete_rejected():
    entry = PersonalizationAuditEntryFactory.create()

    with restricted("is append-only"):
        execute(f"DELETE FROM {AUDIT} WHERE id = %s", [entry.id])
