"""Python append-only guards (design D12 layer 3, D23): fail fast before any SQL is sent.

The database triggers are tested separately in test_triggers.py with raw SQL.
"""

import pytest
from django.utils import timezone

from apps.ingestion.models import EventStateChange, IngestionAuditEntry
from shared.db import CATALOG, PERSONAL
from shared.models import AppendOnlyViolation
from tests.ingestion.factories import (
    EventFactory,
    EventStateChangeFactory,
    IngestionAuditEntryFactory,
)

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])


def changes():
    return EventStateChange.objects.using(CATALOG)


# --- EventStateChange: model --------------------------------------------------------------


def test_state_change_full_save_of_existing_row_raises():
    change = EventStateChangeFactory()
    change.kind = EventStateChange.Kind.CANCELLED

    with pytest.raises(AppendOnlyViolation):
        change.save(using=CATALOG)


@pytest.mark.parametrize("update_fields", [{"propagated_at"}, ("propagated_at",)])
def test_state_change_save_of_propagated_at_only_allowed(update_fields):
    change = EventStateChangeFactory()
    change.propagated_at = timezone.now()

    change.save(using=CATALOG, update_fields=update_fields)

    change.refresh_from_db(using=CATALOG)
    assert change.propagated_at is not None


def test_state_change_save_of_propagated_at_and_another_field_raises():
    change = EventStateChangeFactory()
    change.propagated_at = timezone.now()

    with pytest.raises(AppendOnlyViolation):
        change.save(using=CATALOG, update_fields=["propagated_at", "kind"])


def test_state_change_save_clearing_propagated_at_raises():
    change = EventStateChangeFactory()

    with pytest.raises(AppendOnlyViolation, match="never cleared"):
        change.save(using=CATALOG, update_fields={"propagated_at"})


def test_state_change_force_update_of_fresh_instance_raises():
    change = EventStateChangeFactory()
    forged = EventStateChange(
        pk=change.pk,
        event=change.event,
        kind=EventStateChange.Kind.CANCELLED,
        event_version=change.event_version,
        actor_kind="system",
        actor_label="ingest_pipeline",
    )

    with pytest.raises(AppendOnlyViolation):
        forged.save(using=CATALOG, force_update=True)


def test_state_change_instance_delete_raises():
    with pytest.raises(AppendOnlyViolation):
        EventStateChangeFactory().delete()


# --- EventStateChange: QuerySet (D23) -----------------------------------------------------


def test_state_change_queryset_delete_raises():
    EventStateChangeFactory()

    with pytest.raises(AppendOnlyViolation):
        changes().all().delete()


def test_state_change_queryset_update_of_history_field_raises():
    EventStateChangeFactory()

    with pytest.raises(AppendOnlyViolation):
        changes().update(kind=EventStateChange.Kind.CANCELLED)


def test_state_change_queryset_update_clearing_propagated_at_raises():
    EventStateChangeFactory()

    with pytest.raises(AppendOnlyViolation, match="never cleared"):
        changes().update(propagated_at=None)


def test_state_change_conditional_outbox_update_sets_once_then_matches_nothing():
    change = EventStateChangeFactory()
    unpropagated = changes().filter(pk=change.pk, propagated_at__isnull=True)

    assert unpropagated.update(propagated_at=timezone.now()) == 1
    assert unpropagated.update(propagated_at=timezone.now()) == 0  # the D23 retry is a no-op


@pytest.mark.parametrize("fields", [["kind"], ["propagated_at", "kind"], []])
def test_state_change_bulk_update_of_other_fields_raises(fields):
    change = EventStateChangeFactory()

    with pytest.raises(AppendOnlyViolation):
        changes().bulk_update([change], fields)


def test_state_change_bulk_update_of_propagated_at_allowed():
    change = EventStateChangeFactory()
    change.propagated_at = timezone.now()

    assert changes().bulk_update([change], ["propagated_at"]) == 1


def test_state_change_bulk_create_upsert_raises():
    change = EventStateChangeFactory.build(event=EventFactory())

    with pytest.raises(AppendOnlyViolation, match="no upserts"):
        changes().bulk_create(
            [change],
            update_conflicts=True,
            unique_fields=["event", "event_version"],
            update_fields=["kind"],
        )


def test_state_change_plain_bulk_create_allowed():
    change = EventStateChangeFactory.build(event=EventFactory())

    changes().bulk_create([change])

    assert changes().filter(pk=change.pk).exists()


def test_state_change_delete_through_related_manager_raises():
    change = EventStateChangeFactory()

    with pytest.raises(AppendOnlyViolation):
        change.event.state_changes.all().delete()


def test_state_change_update_through_related_manager_raises():
    change = EventStateChangeFactory()

    with pytest.raises(AppendOnlyViolation):
        change.event.state_changes.update(kind=EventStateChange.Kind.CANCELLED)


def test_state_change_base_manager_is_the_guarded_one():
    assert isinstance(EventStateChange._base_manager.all(), type(changes().all()))
    assert EventStateChange._meta.base_manager_name == "objects"


# --- IngestionAuditEntry ------------------------------------------------------------------


def audit():
    return IngestionAuditEntry.objects.using(CATALOG)


def test_audit_entry_save_of_existing_row_raises():
    entry = IngestionAuditEntryFactory()
    entry.action = "edited"

    with pytest.raises(AppendOnlyViolation):
        entry.save(using=CATALOG)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda qs, entry: qs.update(action="edited"),
        lambda qs, entry: qs.all().delete(),
        lambda qs, entry: qs.bulk_update([entry], ["action"]),
        lambda qs, entry: entry.delete(),
    ],
    ids=["update", "delete", "bulk_update", "instance-delete"],
)
def test_audit_entry_mutation_raises(mutate):
    entry = IngestionAuditEntryFactory()

    with pytest.raises(AppendOnlyViolation):
        mutate(audit(), entry)


def test_audit_entry_base_manager_is_the_guarded_one():
    assert IngestionAuditEntry._meta.base_manager_name == "objects"
