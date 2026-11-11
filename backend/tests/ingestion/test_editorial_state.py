"""`reject_event` and `reinstate_event`: the editorial publication commands (design D1, D8, D10)."""

from uuid import uuid4

import pytest

from apps.ingestion.models import Event, EventStateChange, IngestionAuditEntry
from apps.ingestion.services.editorial_state import reinstate_event, reject_event
from domain.errors import ValidationError
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import EventFactory, make_superseded_pair

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

EDITOR = Actor.user(uuid4())


def changes(event) -> list[EventStateChange]:
    return list(
        EventStateChange.objects.using(CATALOG).filter(event_id=event.pk).order_by("event_version")
    )


# --- Reject ---------------------------------------------------------------------------------


def test_reject_event_sets_rejected_and_bumps_the_version():
    event = EventFactory()

    result = reject_event(event_id=event.pk, actor=EDITOR)
    event.refresh_from_db(using=CATALOG)

    assert result.applied is True
    assert event.publication_status == Event.PublicationStatus.REJECTED
    assert event.event_version == 2


def test_reject_event_never_touches_the_lifecycle_status():
    """**The reason this is a publication status and not a lifecycle one.**

    A duplicate or wrong-venue reject says nothing about whether the event happens in the
    world, so claiming `cancelled` would be false.
    """
    event = EventFactory()

    reject_event(event_id=event.pk, actor=EDITOR)
    event.refresh_from_db(using=CATALOG)

    assert event.status == Event.Status.SCHEDULED


def test_reject_event_never_deletes_the_row():
    event = EventFactory()

    reject_event(event_id=event.pk, actor=EDITOR)

    assert Event.objects.using(CATALOG).filter(pk=event.pk).exists()


def test_reject_event_records_a_delisted_state_change_at_the_new_version():
    """Without this row the reject reaches nobody: it is the AD-17 outbox entry."""
    event = EventFactory()

    reject_event(event_id=event.pk, actor=EDITOR)

    (change,) = changes(event)
    assert change.kind == EventStateChange.Kind.DELISTED
    assert change.event_version == 2
    assert change.before == {"publication_status": "published"}
    assert change.after == {"publication_status": "rejected"}
    assert change.propagated_at is None  # the consumer has not run yet


def test_reject_event_is_attributed_to_the_editor():
    event = EventFactory()

    reject_event(event_id=event.pk, actor=EDITOR)

    (change,) = changes(event)
    assert change.actor_kind == "user"
    assert change.actor_id == EDITOR.id


def test_reject_event_writes_an_audit_entry():
    event = EventFactory()

    reject_event(event_id=event.pk, actor=EDITOR)

    entry = IngestionAuditEntry.objects.using(CATALOG).get(action="event.rejected")
    assert entry.target_id == event.pk
    assert entry.actor_id == EDITOR.id
    assert entry.details["from"] == "published"
    assert entry.details["to"] == "rejected"


def test_reject_event_of_an_in_review_event_is_allowed():
    """The queue's own quarantined events are the other source of rejects (FR-57)."""
    event = EventFactory(publication_status=Event.PublicationStatus.IN_REVIEW)

    result = reject_event(event_id=event.pk, actor=EDITOR)

    assert result.applied is True
    assert changes(event)[0].before == {"publication_status": "in_review"}


def test_reject_event_twice_applies_once():
    """Idempotent: a second reject must not send a second `delisted` to every saver."""
    event = EventFactory()

    reject_event(event_id=event.pk, actor=EDITOR)
    second = reject_event(event_id=event.pk, actor=EDITOR)
    event.refresh_from_db(using=CATALOG)

    assert second.applied is False
    assert second.change is None
    assert event.event_version == 2
    assert len(changes(event)) == 1


def test_reject_event_by_a_system_actor_rejected():
    """AD-14: a verdict cannot be recorded by a job."""
    event = EventFactory()

    with pytest.raises(ValidationError) as excinfo:
        reject_event(event_id=event.pk, actor=Actor.system("ingest_pipeline"))

    assert "actor_must_be_user" in excinfo.value.details["errors"]
    event.refresh_from_db(using=CATALOG)
    assert event.publication_status == Event.PublicationStatus.PUBLISHED


def test_reject_event_of_a_superseded_event_rejected():
    """`superseded` is terminal (AD-4) — unlike `rejected`, which is reversible.

    The trigger would refuse the write anyway; refusing in the command names the reason,
    so an editor gets a sentence rather than a database error.
    """
    old, _new = make_superseded_pair()

    with pytest.raises(ValidationError) as excinfo:
        reject_event(event_id=old.pk, actor=EDITOR)

    assert "event_superseded" in excinfo.value.details["errors"]


def test_reject_event_of_a_missing_event_rejected():
    with pytest.raises(ValidationError) as excinfo:
        reject_event(event_id=uuid4(), actor=EDITOR)

    assert "event_not_found" in excinfo.value.details["errors"]


# --- Reinstate ------------------------------------------------------------------------------


def test_reinstate_event_returns_it_to_published_and_bumps_again():
    event = EventFactory()
    reject_event(event_id=event.pk, actor=EDITOR)

    result = reinstate_event(event_id=event.pk, actor=EDITOR)
    event.refresh_from_db(using=CATALOG)

    assert result.applied is True
    assert event.publication_status == Event.PublicationStatus.PUBLISHED
    assert event.event_version == 3


def test_reinstate_event_records_a_relisted_state_change():
    event = EventFactory()
    reject_event(event_id=event.pk, actor=EDITOR)

    reinstate_event(event_id=event.pk, actor=EDITOR)

    kinds = [change.kind for change in changes(event)]
    assert kinds == [EventStateChange.Kind.DELISTED, EventStateChange.Kind.RELISTED]


def test_reinstate_event_that_was_never_rejected_applies_nothing():
    event = EventFactory()

    result = reinstate_event(event_id=event.pk, actor=EDITOR)
    event.refresh_from_db(using=CATALOG)

    assert result.applied is False
    assert event.event_version == 1
    assert changes(event) == []


def test_reinstate_event_by_a_system_actor_rejected():
    """Ingestion never reverses an editor, and neither does any other job (D8)."""
    event = EventFactory()
    reject_event(event_id=event.pk, actor=EDITOR)

    with pytest.raises(ValidationError) as excinfo:
        reinstate_event(event_id=event.pk, actor=Actor.system("ingest_pipeline"))

    assert "actor_must_be_user" in excinfo.value.details["errors"]
    event.refresh_from_db(using=CATALOG)
    assert event.publication_status == Event.PublicationStatus.REJECTED
