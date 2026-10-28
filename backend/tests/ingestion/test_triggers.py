"""Database triggers from migrations 0001 and 0002 (design D7, D10, D12; pipeline design D11),
tested below the ORM.

Every statement is raw SQL on the catalog connection (the owner role in tests), so the Python
append-only guards are never in the path: a pass here proves the trigger itself. Rejections are
asserted as psycopg's RestrictViolation, the trigger's ERRCODE.
"""

from contextlib import contextmanager
from datetime import timedelta

import psycopg
import pytest
from django.db import IntegrityError, connections, transaction

from apps.ingestion.models import Event
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import (
    FIRST_START,
    EventFactory,
    EventStateChangeFactory,
    IngestionAuditEntryFactory,
    make_superseded_pair,
)

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

STATE_CHANGE = "catalog.ingestion_eventstatechange"
AUDIT = "catalog.ingestion_ingestionauditentry"
EVENT = "catalog.ingestion_event"


def execute(sql: str, params=()) -> int:
    with connections[CATALOG].cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.rowcount


@contextmanager
def restricted(message: str):
    """Expect the block to fail in a trigger with this message (rolled back to a savepoint)."""
    with pytest.raises(IntegrityError) as excinfo, transaction.atomic(using=CATALOG):
        yield
    assert isinstance(excinfo.value.__cause__, psycopg.errors.RestrictViolation)
    assert message in str(excinfo.value.__cause__)


def column(table: str, name: str, row_id):
    with connections[CATALOG].cursor() as cursor:
        cursor.execute(f"SELECT {name} FROM {table} WHERE id = %s", [row_id])
        return cursor.fetchone()[0]


# --- Append-only state changes and audit rows (D12) ----------------------------------------


def test_state_change_update_of_history_column_rejected():
    change = EventStateChangeFactory()

    with restricted("ingestion_eventstatechange is append-only"):
        execute(f"UPDATE {STATE_CHANGE} SET kind = 'cancelled' WHERE id = %s", [change.id])


def test_state_change_propagated_at_null_to_value_allowed():
    change = EventStateChangeFactory()

    assert execute(f"UPDATE {STATE_CHANGE} SET propagated_at = now() WHERE id = %s", [change.id])
    assert column(STATE_CHANGE, "propagated_at", change.id) is not None


def test_state_change_propagated_at_value_to_other_value_rejected():
    change = EventStateChangeFactory()
    execute(f"UPDATE {STATE_CHANGE} SET propagated_at = now() WHERE id = %s", [change.id])

    with restricted("is append-only"):
        execute(
            f"UPDATE {STATE_CHANGE} SET propagated_at = now() + interval '1 hour' WHERE id = %s",
            [change.id],
        )


def test_state_change_propagated_at_value_to_null_rejected():
    change = EventStateChangeFactory()
    execute(f"UPDATE {STATE_CHANGE} SET propagated_at = now() WHERE id = %s", [change.id])

    with restricted("is append-only"):
        execute(f"UPDATE {STATE_CHANGE} SET propagated_at = NULL WHERE id = %s", [change.id])


def test_state_change_propagated_at_with_another_column_rejected():
    change = EventStateChangeFactory()

    with restricted("is append-only"):
        execute(
            f"UPDATE {STATE_CHANGE} SET propagated_at = now(), kind = 'cancelled' WHERE id = %s",
            [change.id],
        )


@pytest.mark.parametrize(
    ("table", "factory"),
    [(STATE_CHANGE, EventStateChangeFactory), (AUDIT, IngestionAuditEntryFactory)],
    ids=["state-change", "audit"],
)
def test_history_delete_rejected(table, factory):
    row = factory()

    with restricted("is append-only"):
        execute(f"DELETE FROM {table} WHERE id = %s", [row.id])


@pytest.mark.parametrize(
    ("table", "factory"),
    [(STATE_CHANGE, EventStateChangeFactory), (AUDIT, IngestionAuditEntryFactory)],
    ids=["state-change", "audit"],
)
def test_history_delete_inside_retention_purge_allowed(table, factory):
    row = factory()

    with transaction.atomic(using=CATALOG):
        execute("SET LOCAL eventpulse.retention_purge = 'on'")
        assert execute(f"DELETE FROM {table} WHERE id = %s", [row.id]) == 1


def test_audit_update_rejected():
    entry = IngestionAuditEntryFactory()

    with restricted("ingestion_ingestionauditentry is append-only"):
        execute(f"UPDATE {AUDIT} SET action = 'edited' WHERE id = %s", [entry.id])


# --- Event guard: updates (D7, D10) --------------------------------------------------------


def test_event_superseded_row_update_rejected():
    old, _ = make_superseded_pair()

    with restricted("is terminal"):
        execute(f"UPDATE {EVENT} SET title = 'Edited' WHERE id = %s", [old.id])


def test_event_version_decrease_rejected():
    event = EventFactory()
    execute(f"UPDATE {EVENT} SET event_version = 2, is_sold_out = true WHERE id = %s", [event.id])

    with restricted("may only stay or rise by 1"):
        execute(f"UPDATE {EVENT} SET event_version = 1 WHERE id = %s", [event.id])


def test_event_version_jump_by_two_rejected():
    event = EventFactory()

    with restricted("may only stay or rise by 1"):
        execute(
            f"UPDATE {EVENT} SET event_version = 3, is_sold_out = true WHERE id = %s", [event.id]
        )


@pytest.mark.parametrize(
    "assignment",
    [
        "start_time_utc = start_time_utc + interval '1 day'",
        "end_time_utc = start_time_utc + interval '2 hours'",
        "start_time_tz = 'America/New_York'",
        "status = 'cancelled'",
        "is_sold_out = true",
        "venue_id = NULL",
    ],
)
def test_event_lifecycle_change_without_version_bump_rejected(assignment):
    event = EventFactory()

    with restricted("needs event_version + 1"):
        execute(f"UPDATE {EVENT} SET {assignment} WHERE id = %s", [event.id])


def test_event_superseded_by_change_without_version_bump_rejected():
    event, other = EventFactory(), EventFactory()

    with restricted("needs event_version + 1"):
        execute(
            f"UPDATE {EVENT} SET status = 'superseded', superseded_by_id = %s WHERE id = %s",
            [other.id, event.id],
        )


def test_event_lifecycle_change_with_version_bump_allowed():
    event = EventFactory()

    execute(
        f"UPDATE {EVENT} SET status = 'cancelled', event_version = event_version + 1 WHERE id = %s",
        [event.id],
    )

    assert column(EVENT, "event_version", event.id) == 2


def test_event_non_lifecycle_change_at_same_version_allowed():
    event = EventFactory()

    execute(
        f"UPDATE {EVENT} SET last_seen_at = now(), title = 'Retitled' WHERE id = %s", [event.id]
    )

    assert column(EVENT, "event_version", event.id) == 1


def test_event_trigger_lifecycle_columns_match_model():
    # The trigger's column list is hand-written SQL; keep it in step with the model's tuple.
    # Read the live function: migration 0002 replaced 0001's text (run-015 plan P6).
    with connections[CATALOG].cursor() as cursor:
        cursor.execute("SELECT pg_get_functiondef('catalog.guard_event_write'::regproc)")
        sql = cursor.fetchone()[0]
    columns = [Event._meta.get_field(name).column for name in Event.LIFECYCLE_FIELDS]

    assert all(f"NEW.{column} IS DISTINCT FROM OLD.{column}" in sql for column in columns)


def test_event_original_start_change_rejected():
    event = EventFactory()

    with restricted("original_start_utc of Event"):
        execute(
            f"UPDATE {EVENT} SET original_start_utc = original_start_utc + interval '1 day', "
            "event_version = event_version + 1 WHERE id = %s",
            [event.id],
        )


def test_event_original_start_unchanged_by_a_start_move():
    event = EventFactory()

    execute(
        f"UPDATE {EVENT} SET start_time_utc = start_time_utc + interval '2 days', "
        "event_version = event_version + 1 WHERE id = %s",
        [event.id],
    )

    assert column(EVENT, "original_start_utc", event.id) == event.start_time_utc


# --- Event guard: inserts -------------------------------------------------------------------


def test_event_insert_at_version_other_than_one_rejected():
    with restricted("starts at event_version 1"):
        EventFactory(event_version=2)  # no Python guard on Event: this reaches the trigger


def test_event_insert_with_other_original_start_rejected():
    with restricted("original_start_utc is its start_time_utc"):
        EventFactory(original_start_utc=FIRST_START - timedelta(days=1))


def test_event_insert_already_superseded_rejected():
    other = EventFactory()

    with restricted("is not superseded"):
        EventFactory(status=Event.Status.SUPERSEDED, superseded_by=other)
