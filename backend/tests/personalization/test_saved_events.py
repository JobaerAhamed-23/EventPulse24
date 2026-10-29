"""The save commands (AD-21, FR-33): save, unsave, and the save-race protocol.

The race is the interesting part. AD-21: "A save re-reads the Event's version after commit and
requests re-propagation for that user if it moved meanwhile, so a save racing a postponement
cannot keep a stale snapshot."
"""

from datetime import UTC, datetime, timedelta

import pytest

from apps.ingestion.models import Event
from apps.personalization.models import ConflictPair, PersonalizationAuditEntry, SavedEvent
from apps.personalization.services.saved_events import (
    SavedEventNotFoundError,
    save_event,
    unsave_event,
    update_saved_event_snapshot,
)
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from shared.ids import uuid7
from tests.ingestion.factories import EventFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
START = datetime(2026, 11, 6, 3, 30, tzinfo=UTC)
END = START + timedelta(hours=2)

USER = uuid7()
OTHER = uuid7()


def make_saved_event(**kwargs):
    args = {
        "user_id": USER,
        "event_id": uuid7(),
        "actor": Actor.user(USER),
        "now": NOW,
    }
    args.update(kwargs)
    return save_event(**args)


# --- Saving (AD-21) --------------------------------------------------------------------------


def test_saving_an_event_writes_the_snapshot():
    event = EventFactory(start_time_utc=START, end_time_utc=END)

    result = make_saved_event(event_id=event.id)

    saved = SavedEvent.objects.get(pk=result.saved.id)
    assert saved.event_id == event.id
    assert saved.start_utc == START
    assert saved.end_utc == END
    assert saved.event_version == event.event_version


def test_saving_an_event_writes_an_audit_row():
    event = EventFactory(start_time_utc=START, end_time_utc=END)

    result = make_saved_event(event_id=event.id)

    entry = PersonalizationAuditEntry.objects.get(
        target_id=result.saved.id, action="saved_event.saved"
    )
    assert entry.actor_id == USER
    assert entry.details["event_id"] == str(event.id)


def test_saving_the_same_event_twice_is_idempotent():
    # The work item's AC: "Saving the same event twice is idempotent — one row, not two."
    event = EventFactory(start_time_utc=START, end_time_utc=END)

    make_saved_event(event_id=event.id)
    make_saved_event(event_id=event.id)

    assert SavedEvent.objects.filter(user_id=USER, event_id=event.id).count() == 1


def test_saving_an_event_that_is_not_public_is_not_found():
    from apps.ingestion.services.catalog_read import EventNotFoundError

    event = EventFactory(start_time_utc=START, publication_status=Event.PublicationStatus.IN_REVIEW)

    with pytest.raises(EventNotFoundError):
        make_saved_event(event_id=event.id)

    assert not SavedEvent.objects.exists()


def test_saving_an_event_that_does_not_exist_is_not_found():
    from apps.ingestion.services.catalog_read import EventNotFoundError

    with pytest.raises(EventNotFoundError):
        make_saved_event(event_id=uuid7())

    assert not SavedEvent.objects.exists()


# --- The save-race (AD-21) -------------------------------------------------------------------


def test_a_save_that_races_a_postponement_reports_a_stale_snapshot(monkeypatch):
    # AD-21: "A save re-reads the Event's version after commit and requests re-propagation
    # for that user if it moved meanwhile, so a save racing a postponement cannot keep a stale
    # snapshot."
    #
    # The postponement lands between the read that stamps the snapshot and the read that
    # checks it. The catalog's version moves; the save's snapshot does not.
    event = EventFactory(start_time_utc=START, end_time_utc=END)

    from apps.personalization.services import saved_events

    reads = {"count": 0}
    real_read = saved_events.get_public_event

    def read_then_postpone(*, event_id):
        reads["count"] += 1
        found = real_read(event_id=event_id)
        if reads["count"] == 1:
            # The first read (inside the transaction) stamps the snapshot at version 1.
            # The postponement lands right after it.
            Event.objects.using(CATALOG).filter(pk=event.id).update(event_version=2)
        return found

    monkeypatch.setattr(saved_events, "get_public_event", read_then_postpone)

    result = make_saved_event(event_id=event.id)

    assert result.stale is True
    assert result.current_version == 2
    assert SavedEvent.objects.get(pk=result.saved.id).event_version == 1


def test_a_stale_save_records_the_fact_in_the_audit_log(monkeypatch):
    event = EventFactory(start_time_utc=START, end_time_utc=END)

    from apps.personalization.services import saved_events

    reads = {"count": 0}
    real_read = saved_events.get_public_event

    def read_then_postpone(*, event_id):
        reads["count"] += 1
        found = real_read(event_id=event_id)
        if reads["count"] == 1:
            Event.objects.using(CATALOG).filter(pk=event.id).update(event_version=2)
        return found

    monkeypatch.setattr(saved_events, "get_public_event", read_then_postpone)

    result = make_saved_event(event_id=event.id)

    entry = PersonalizationAuditEntry.objects.get(
        target_id=result.saved.id, action="saved_event.stale_detected"
    )
    assert entry.details["stamped_version"] == 1
    assert entry.details["current_version"] == 2
    assert entry.details["repropagation_requested"] is True


def test_a_save_that_races_nothing_is_not_stale():
    event = EventFactory(start_time_utc=START, end_time_utc=END)

    result = make_saved_event(event_id=event.id)

    assert result.stale is False


# --- Conflict detection on save (FR-33) -------------------------------------------------------


def test_saving_an_event_that_overlaps_a_personal_event_detects_the_conflict():
    from apps.personalization.services.personal_events import create_personal_event

    create_personal_event(
        user_id=USER,
        name="Coffee with Sam",
        start_utc=START,
        end_utc=END,
        start_time_tz="America/Los_Angeles",
        actor=Actor.user(USER),
        now=NOW,
    )
    event = EventFactory(start_time_utc=START, end_time_utc=END)

    result = make_saved_event(event_id=event.id)

    assert len(result.conflicts) == 1
    assert result.conflicts[0].kind == "time"
    pair = ConflictPair.objects.get(pk=result.conflicts[0].pair_id)
    assert pair.status == ConflictPair.Status.ACTIVE


# --- Unsaving (AD-21) ------------------------------------------------------------------------


def test_unsaving_an_event_removes_the_save():
    event = EventFactory(start_time_utc=START, end_time_utc=END)
    result = make_saved_event(event_id=event.id)

    unsave_event(user_id=USER, event_id=event.id, actor=Actor.user(USER), now=NOW)

    assert not SavedEvent.objects.filter(pk=result.saved.id).exists()


def test_unsaving_an_event_writes_an_audit_row():
    event = EventFactory(start_time_utc=START, end_time_utc=END)
    result = make_saved_event(event_id=event.id)

    unsave_event(user_id=USER, event_id=event.id, actor=Actor.user(USER), now=NOW)

    entry = PersonalizationAuditEntry.objects.get(
        target_id=result.saved.id, action="saved_event.unsaved"
    )
    assert entry.actor_id == USER


def test_unsaving_an_event_closes_the_pairs_it_was_in():
    from apps.personalization.services.personal_events import create_personal_event

    create_personal_event(
        user_id=USER,
        name="Coffee with Sam",
        start_utc=START,
        end_utc=END,
        start_time_tz="America/Los_Angeles",
        actor=Actor.user(USER),
        now=NOW,
    )
    event = EventFactory(start_time_utc=START, end_time_utc=END)
    result = make_saved_event(event_id=event.id)
    pair_id = result.conflicts[0].pair_id

    unsave_event(user_id=USER, event_id=event.id, actor=Actor.user(USER), now=NOW)

    pair = ConflictPair.objects.get(pk=pair_id)
    assert pair.status == ConflictPair.Status.CLEARED_BY_STATE_CHANGE
    assert pair.resolution is None


def test_unsaving_an_event_that_is_not_the_callers_is_not_found():
    event = EventFactory(start_time_utc=START, end_time_utc=END)
    make_saved_event(event_id=event.id)

    with pytest.raises(SavedEventNotFoundError):
        unsave_event(user_id=OTHER, event_id=event.id, actor=Actor.user(OTHER), now=NOW)

    assert SavedEvent.objects.filter(user_id=USER).exists()


# --- The propagation-shaped snapshot update (AD-17) -------------------------------------------


def test_the_snapshot_update_applies_a_newer_version():
    event = EventFactory(start_time_utc=START, end_time_utc=END)
    result = make_saved_event(event_id=event.id)

    applied = update_saved_event_snapshot(
        event_id=event.id,
        user_id=USER,
        new_version=2,
        new_start_utc=START + timedelta(days=1),
        new_end_utc=END + timedelta(days=1),
        actor=Actor.system("propagation"),
        now=NOW,
    )

    assert applied is True
    saved = SavedEvent.objects.get(pk=result.saved.id)
    assert saved.event_version == 2
    assert saved.start_utc == START + timedelta(days=1)


def test_the_snapshot_update_refuses_an_older_version():
    # AD-17: "only if the change's `event_version` is greater than the version already stored
    # — so a retried, partial or out-of-order run can neither double-apply nor let an older
    # postponement overwrite a newer one."
    event = EventFactory(start_time_utc=START, end_time_utc=END)
    result = make_saved_event(event_id=event.id)

    applied = update_saved_event_snapshot(
        event_id=event.id,
        user_id=USER,
        new_version=1,
        new_start_utc=START + timedelta(days=5),
        new_end_utc=END + timedelta(days=5),
        actor=Actor.system("propagation"),
        now=NOW,
    )

    assert applied is False
    assert SavedEvent.objects.get(pk=result.saved.id).start_utc == START


def test_the_snapshot_update_of_an_unsaved_event_does_nothing():
    applied = update_saved_event_snapshot(
        event_id=uuid7(),
        user_id=USER,
        new_version=2,
        new_start_utc=START,
        new_end_utc=END,
        actor=Actor.system("propagation"),
        now=NOW,
    )

    assert applied is False


def test_the_snapshot_update_re_evaluates_the_conflicts():
    from apps.personalization.services.personal_events import create_personal_event

    create_personal_event(
        user_id=USER,
        name="Coffee with Sam",
        start_utc=START,
        end_utc=END,
        start_time_tz="America/Los_Angeles",
        actor=Actor.user(USER),
        now=NOW,
    )
    event = EventFactory(start_time_utc=START, end_time_utc=END)
    result = make_saved_event(event_id=event.id)
    assert len(result.conflicts) == 1

    update_saved_event_snapshot(
        event_id=event.id,
        user_id=USER,
        new_version=2,
        new_start_utc=START + timedelta(days=3),
        new_end_utc=END + timedelta(days=3),
        actor=Actor.system("propagation"),
        now=NOW,
    )

    pair = ConflictPair.objects.get(pk=result.conflicts[0].pair_id)
    assert pair.status == ConflictPair.Status.CLEARED_BY_STATE_CHANGE
