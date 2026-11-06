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
    cancel_saved_event,
    get_saved_event,
    list_saved_events,
    list_savers_for_event,
    reinstate_saved_event,
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

    def read_then_postpone(*, event_id, now=None):
        reads["count"] += 1
        found = real_read(event_id=event_id, now=now)
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

    def read_then_postpone(*, event_id, now=None):
        reads["count"] += 1
        found = real_read(event_id=event_id, now=now)
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


# --- Listing ---------------------------------------------------------------------------------


def _saved_row(*, user_id=USER, start_utc, event_id=None):
    """A saved row written directly, so the list is tested without the save command."""
    return SavedEvent.objects.using(PERSONAL).create(
        user_id=user_id,
        event_id=event_id or uuid7(),
        start_utc=start_utc,
        end_utc=start_utc + timedelta(hours=2),
        event_version=1,
    )


def test_listing_returns_the_users_saves_soonest_first():
    later = _saved_row(start_utc=START + timedelta(days=2))
    sooner = _saved_row(start_utc=START)

    listed = list_saved_events(user_id=USER)

    assert [saved.id for saved in listed] == [sooner.id, later.id]


def test_listing_is_scoped_to_the_user():
    mine = _saved_row(user_id=USER, start_utc=START)
    _saved_row(user_id=OTHER, start_utc=START)

    listed = list_saved_events(user_id=USER)

    assert [saved.id for saved in listed] == [mine.id]


def test_listing_bounds_are_inclusive_and_apply_to_the_snapshot():
    """The bound is applied to the value the list returns, so the two never disagree."""
    before = _saved_row(start_utc=START)
    inside = _saved_row(start_utc=START + timedelta(hours=1))
    after = _saved_row(start_utc=START + timedelta(hours=2))

    listed = list_saved_events(
        user_id=USER,
        starts_after=START + timedelta(hours=1),
        starts_before=START + timedelta(hours=1),
    )

    assert [saved.id for saved in listed] == [inside.id]
    assert before.id not in {saved.id for saved in listed}
    assert after.id not in {saved.id for saved in listed}


def test_listing_without_bounds_returns_every_save():
    _saved_row(start_utc=START)
    _saved_row(start_utc=START + timedelta(days=2))

    listed = list_saved_events(user_id=USER)

    assert len(listed) == 2


# --- The single-save read ----------------------------------------------------------------------
#
# `get_saved_event` is the published read `delivery` needs to resolve a plan's target
# (AD-3). It is keyed by the **catalog event's id**, not by the save row's own id — the
# tree's convention for a saved event's target.


def test_get_saved_event_finds_the_callers_own_save():
    saved = _saved_row(user_id=USER, start_utc=START, event_id=uuid7())

    found = get_saved_event(user_id=USER, event_id=saved.event_id)

    assert found.id == saved.id
    assert found.event_id == saved.event_id


def test_get_saved_event_refuses_another_users_save():
    """A save belonging to another user reads as not found, not as forbidden.

    A 403 would confirm that the record exists, so the endpoint could be used to probe
    for other users' saved event ids.
    """
    saved = _saved_row(user_id=OTHER, start_utc=START, event_id=uuid7())

    with pytest.raises(SavedEventNotFoundError):
        get_saved_event(user_id=USER, event_id=saved.event_id)


def test_get_saved_event_raises_when_there_is_no_save():
    with pytest.raises(SavedEventNotFoundError):
        get_saved_event(user_id=USER, event_id=uuid7())


def test_get_saved_event_raises_for_an_unsaved_event():
    """Un-saved and never-saved are the same fact — the save *is* the target."""
    event_id = uuid7()
    saved = _saved_row(user_id=USER, start_utc=START, event_id=event_id)
    unsave_event(user_id=USER, event_id=event_id, actor=Actor.user(USER), now=NOW)

    with pytest.raises(SavedEventNotFoundError):
        get_saved_event(user_id=USER, event_id=saved.event_id)


# --- The cancellation path (AD-17, FR-55) ------------------------------------------------------
#
# `cancel_saved_event` is `update_saved_event_snapshot`'s twin: the same version gate, the
# same single `personal` transaction, the same audit shape. AD-17's consumer calls one or
# the other depending on the change's kind.


def _overlapping_personal_event(*, user_id=USER, start_utc=START, end_utc=END):
    from apps.personalization.services.personal_events import create_personal_event

    return create_personal_event(
        user_id=user_id,
        name="Coffee with Sam",
        start_utc=start_utc,
        end_utc=end_utc,
        start_time_tz="America/Los_Angeles",
        actor=Actor.user(user_id),
        now=NOW,
    ).event


def _cancel(event_id, *, version, user_id=USER):
    return cancel_saved_event(
        event_id=event_id,
        user_id=user_id,
        new_version=version,
        actor=Actor.system("propagation"),
        now=NOW,
    )


def _reinstate(event_id, *, version, user_id=USER):
    return reinstate_saved_event(
        event_id=event_id,
        user_id=user_id,
        new_version=version,
        actor=Actor.system("propagation"),
        now=NOW,
    )


def test_cancelling_a_save_applies_a_newer_version():
    event = EventFactory(start_time_utc=START, end_time_utc=END)
    result = make_saved_event(event_id=event.id)

    assert _cancel(event.id, version=event.event_version + 1) is True

    saved = SavedEvent.objects.using(PERSONAL).get(pk=result.saved.id)
    assert saved.event_version == event.event_version + 1


def test_cancelling_a_save_refuses_the_version_it_already_has():
    """The gate is `>`, not `>=`, and this is the boundary that decides it.

    A re-delivered propagation carries the same version. If the gate were `>=` it would
    apply twice — harmless for the version bump, but it would also re-run the pair close
    and write a second audit row for one change.
    """
    event = EventFactory(start_time_utc=START, end_time_utc=END)
    make_saved_event(event_id=event.id)

    assert _cancel(event.id, version=event.event_version) is False


def test_cancelling_a_save_refuses_an_older_version():
    """AD-17: an out-of-order run can never let an older change overwrite a newer one."""
    event = EventFactory(start_time_utc=START, end_time_utc=END)
    result = make_saved_event(event_id=event.id)
    _cancel(event.id, version=5)

    assert _cancel(event.id, version=4) is False
    assert SavedEvent.objects.using(PERSONAL).get(pk=result.saved.id).event_version == 5


def test_cancelling_an_event_nobody_saved_does_nothing():
    assert _cancel(uuid7(), version=2) is False


def test_cancelling_a_save_does_not_delete_it():
    """The user made that save. Whether the event happens is the catalog's fact, not ours."""
    event = EventFactory(start_time_utc=START, end_time_utc=END)
    result = make_saved_event(event_id=event.id)

    _cancel(event.id, version=event.event_version + 1)

    assert SavedEvent.objects.using(PERSONAL).filter(pk=result.saved.id).exists()


def test_cancelling_a_save_closes_its_pairs_as_cleared_by_state_change():
    """AD-21: a side going away is **not** a user resolution, so `resolution` stays NULL."""
    _overlapping_personal_event()
    event = EventFactory(start_time_utc=START, end_time_utc=END)
    result = make_saved_event(event_id=event.id)
    assert len(result.conflicts) == 1
    pair_id = result.conflicts[0].pair_id

    _cancel(event.id, version=event.event_version + 1)

    pair = ConflictPair.objects.using(PERSONAL).get(pk=pair_id)
    assert pair.status == ConflictPair.Status.CLEARED_BY_STATE_CHANGE
    assert pair.resolution is None


def test_cancelling_a_save_leaves_the_personal_event_untouched():
    """FR-55: a cancelled public event never auto-cancels a personal event."""
    from apps.personalization.models import PersonalEvent

    personal = _overlapping_personal_event()
    before = PersonalEvent.objects.using(PERSONAL).get(pk=personal.id)
    event = EventFactory(start_time_utc=START, end_time_utc=END)
    make_saved_event(event_id=event.id)

    _cancel(event.id, version=event.event_version + 1)

    after = PersonalEvent.objects.using(PERSONAL).get(pk=personal.id)
    assert after.start_utc == before.start_utc
    assert after.end_utc == before.end_utc
    assert after.version == before.version
    assert after.updated_at == before.updated_at


def test_cancelling_a_save_writes_an_audit_row():
    event = EventFactory(start_time_utc=START, end_time_utc=END)
    result = make_saved_event(event_id=event.id)

    _cancel(event.id, version=7)

    entry = PersonalizationAuditEntry.objects.using(PERSONAL).get(
        target_id=result.saved.id, action="saved_event.cancelled"
    )
    assert entry.details["event_version"] == 7
    assert entry.details["event_id"] == str(event.id)


def test_a_refused_cancellation_writes_no_audit_row():
    """The gate returns before the write, so a duplicate delivery leaves no trace."""
    event = EventFactory(start_time_utc=START, end_time_utc=END)
    result = make_saved_event(event_id=event.id)

    _cancel(event.id, version=event.event_version)

    assert (
        not PersonalizationAuditEntry.objects.using(PERSONAL)
        .filter(target_id=result.saved.id, action="saved_event.cancelled")
        .exists()
    )


# --- Reinstatement, and the one thing it cannot undo -------------------------------------------


def test_reinstating_applies_a_newer_version():
    event = EventFactory(start_time_utc=START, end_time_utc=END)
    result = make_saved_event(event_id=event.id)
    _cancel(event.id, version=2)

    assert _reinstate(event.id, version=3) is True
    assert SavedEvent.objects.using(PERSONAL).get(pk=result.saved.id).event_version == 3


def test_reinstating_refuses_an_older_version():
    event = EventFactory(start_time_utc=START, end_time_utc=END)
    make_saved_event(event_id=event.id)
    _cancel(event.id, version=5)

    assert _reinstate(event.id, version=4) is False


def test_reinstating_an_event_nobody_saved_does_nothing():
    """`False` means "this user was not affected", and the consumer acts on it.

    AD-17's propagation reads the return value to decide whether a user is part of the
    change — a `True` here would queue an FR-54 notice to someone who has no save to be
    notified about. `cancel_saved_event` has the same guard; the pair must agree.
    """
    assert _reinstate(uuid7(), version=2) is False


def test_reinstating_a_save_belonging_to_someone_else_does_nothing():
    """Propagation is per-user. Naming the wrong user must not apply the change."""
    event = EventFactory(start_time_utc=START, end_time_utc=END)
    make_saved_event(event_id=event.id)
    _cancel(event.id, version=2)

    assert _reinstate(event.id, version=3, user_id=OTHER) is False


def test_reinstating_does_not_move_the_snapshot():
    """A reinstatement says the event is happening again, not that it moved.

    A move is always its own `time_moved` change — one state change per kind — which
    `update_saved_event_snapshot` applies.
    """
    event = EventFactory(start_time_utc=START, end_time_utc=END)
    result = make_saved_event(event_id=event.id)
    _cancel(event.id, version=2)

    _reinstate(event.id, version=3)

    saved = SavedEvent.objects.using(PERSONAL).get(pk=result.saved.id)
    assert saved.start_utc == START
    assert saved.end_utc == END


def test_an_overlap_acquired_while_the_event_was_dead_is_recorded_without_reinstatement():
    """Why `reinstate_saved_event` does **not** re-run detection.

    A `SavedEvent` carries no cancelled flag — liveness is read from the catalog, never
    mirrored — so a personal event created while the save is dead is detected against it
    by `create_personal_event`, at the moment it is created. The pair is already there
    before any reinstatement arrives, which is why a detection call inside `reinstate`
    was dead code: a mutation deleting it broke nothing.

    The count is asserted **before** the reinstatement as well as after. An `exists()`
    afterwards would pass whether or not `reinstate` did anything, which is exactly what
    the first version of this test got wrong.
    """
    event = EventFactory(start_time_utc=START, end_time_utc=END)
    make_saved_event(event_id=event.id)
    _cancel(event.id, version=2)

    _overlapping_personal_event()

    active = ConflictPair.objects.using(PERSONAL).filter(
        user_id=USER, status=ConflictPair.Status.ACTIVE
    )
    assert active.count() == 1

    _reinstate(event.id, version=3)

    assert active.count() == 1


def test_reinstating_leaves_the_conflict_rows_exactly_as_it_found_them():
    """A reinstatement moves nothing, so it judges nothing.

    `update_saved_event_snapshot` re-detects because the save's *times* changed under rows
    nobody else will re-judge. A reinstatement changes no time, so every pair that should
    exist already does — and the pair the cancellation closed is immutable anyway.
    """
    _overlapping_personal_event()
    event = EventFactory(start_time_utc=START, end_time_utc=END)
    make_saved_event(event_id=event.id)
    _cancel(event.id, version=2)
    before = {
        (pair.id, pair.status, pair.resolution)
        for pair in ConflictPair.objects.using(PERSONAL).filter(user_id=USER)
    }

    _reinstate(event.id, version=3)

    after = {
        (pair.id, pair.status, pair.resolution)
        for pair in ConflictPair.objects.using(PERSONAL).filter(user_id=USER)
    }
    assert after == before


def test_reinstating_cannot_reopen_a_pair_cancellation_closed():
    """**A known hole, pinned so it stays documented rather than silent.**

    AD-17 makes a cancellation close conflicts. AD-21's D24 makes a closed pair immutable,
    enforced by the `guard_conflict_pair` trigger, and `conflict_pair_pair_uq` forbids a
    replacement row for the same two sides. So a pair closed by a cancellation can be
    neither reopened nor replaced — by this service or by anything else.

    The user consequence is real: a saved event that clashed, was cancelled, and is then
    reinstated clashes again, and `/conflicts` will not say so. Closing it needs a spine
    amendment, not a code change.
    """
    _overlapping_personal_event()
    event = EventFactory(start_time_utc=START, end_time_utc=END)
    result = make_saved_event(event_id=event.id)
    pair_id = result.conflicts[0].pair_id
    _cancel(event.id, version=2)

    assert _reinstate(event.id, version=3) is True

    pair = ConflictPair.objects.using(PERSONAL).get(pk=pair_id)
    assert pair.status == ConflictPair.Status.CLEARED_BY_STATE_CHANGE
    assert (
        not ConflictPair.objects.using(PERSONAL)
        .filter(user_id=USER, status=ConflictPair.Status.ACTIVE)
        .exists()
    )


def test_cancel_reinstate_cancel_is_idempotent_at_every_step():
    event = EventFactory(start_time_utc=START, end_time_utc=END)
    result = make_saved_event(event_id=event.id)

    assert _cancel(event.id, version=2) is True
    assert _cancel(event.id, version=2) is False
    assert _reinstate(event.id, version=3) is True
    assert _reinstate(event.id, version=3) is False
    assert _cancel(event.id, version=4) is True
    assert _cancel(event.id, version=4) is False

    assert SavedEvent.objects.using(PERSONAL).get(pk=result.saved.id).event_version == 4


def test_a_cancellation_applies_to_the_named_user_only():
    """Propagation is per-user (AD-17); one user's transaction never touches another's."""
    event = EventFactory(start_time_utc=START, end_time_utc=END)
    mine = make_saved_event(event_id=event.id)
    theirs = save_event(user_id=OTHER, event_id=event.id, actor=Actor.user(OTHER), now=NOW)

    _cancel(event.id, version=9, user_id=USER)

    assert SavedEvent.objects.using(PERSONAL).get(pk=mine.saved.id).event_version == 9
    assert (
        SavedEvent.objects.using(PERSONAL).get(pk=theirs.saved.id).event_version
        == event.event_version
    )


# --- The reverse read (AD-17) ------------------------------------------------------------------
#
# Every other read here is keyed `(user_id, event_id)`. A state change names only an event,
# so propagation needs this one: who saved it?


def test_list_savers_for_event_returns_every_users_save():
    event_id = uuid7()
    mine = _saved_row(user_id=USER, start_utc=START, event_id=event_id)
    theirs = _saved_row(user_id=OTHER, start_utc=START, event_id=event_id)

    savers = list_savers_for_event(event_id=event_id)

    assert {s.id for s in savers} == {mine.id, theirs.id}
    assert {s.user_id for s in savers} == {USER, OTHER}


def test_list_savers_for_event_is_scoped_to_the_event():
    wanted = uuid7()
    mine = _saved_row(user_id=USER, start_utc=START, event_id=wanted)
    _saved_row(user_id=USER, start_utc=START, event_id=uuid7())

    assert [s.id for s in list_savers_for_event(event_id=wanted)] == [mine.id]


def test_list_savers_for_event_returns_nothing_when_nobody_saved_it():
    assert list_savers_for_event(event_id=uuid7()) == []


def test_list_savers_for_event_pages_by_keyset():
    """Paging to exhaustion returns every saver exactly once, in id order.

    **The page budget is part of the test, not defensive clutter.** Five rows at two a
    page is three calls; the loop is allowed four. A cursor that failed to advance would
    otherwise re-serve page one forever and the test would *hang* rather than fail —
    which is not a test that can fail. The budget turns that into an assertion.
    """
    event_id = uuid7()
    rows = [_saved_row(user_id=uuid7(), start_utc=START, event_id=event_id) for _ in range(5)]
    expected = sorted(row.id for row in rows)
    budget = len(expected) // 2 + 2

    seen = []
    after = None
    for _ in range(budget):
        page = list_savers_for_event(event_id=event_id, after=after, limit=2)
        if not page:
            break
        seen.extend(saver.id for saver in page)
        after = page[-1].id
    else:
        raise AssertionError(
            f"paging did not finish within {budget} calls — the cursor is not advancing; "
            f"saw {len(seen)} rows for {len(expected)} savers"
        )

    assert seen == expected


def test_a_row_deleted_between_pages_does_not_hide_the_next_one():
    """Why keyset and not offset.

    With `OFFSET 2` the second page would start at the third *remaining* row — so deleting
    one row from the first page silently skips a saver, and the state change reaches
    everyone except them. A keyset page names where it stopped, so it cannot skip.
    """
    event_id = uuid7()
    rows = sorted(
        (_saved_row(user_id=uuid7(), start_utc=START, event_id=event_id) for _ in range(4)),
        key=lambda row: row.id,
    )

    first = list_savers_for_event(event_id=event_id, limit=2)
    assert [s.id for s in first] == [rows[0].id, rows[1].id]
    # A user unsaves while propagation is paging.
    SavedEvent.objects.using(PERSONAL).filter(pk=rows[0].id).delete()

    second = list_savers_for_event(event_id=event_id, after=first[-1].id, limit=2)

    assert [s.id for s in second] == [rows[2].id, rows[3].id]


def test_list_savers_for_event_refuses_a_non_positive_limit():
    """A `limit` of 0 is a caller bug; returning the whole table would be the worse answer."""
    event_id = uuid7()
    _saved_row(user_id=USER, start_utc=START, event_id=event_id)

    assert list_savers_for_event(event_id=event_id, limit=0) == []


# --- The unsave takes the Reminder Plan with it ------------------------------------------------
#
# A plan for a saved event is addressed by the **catalog** event's id and resolved through
# `reminder_plan_read.resolve_target`, which 404s once the save is gone. So a plan that
# outlives its save reads as "no plan" while still holding live `SCHEDULED_SEND` rows that
# nothing re-resolves before sending: the user keeps getting reminders for an event they
# removed. `personalization` may not write `REMINDER_PLAN` (AD-16), so the unsave calls
# `delivery`'s own `remove_plans_for_targets` — the same service the calendar disconnect
# uses, for the same reason.


def _plan_with_sends(event, *, user_id=USER, slots=("1d", "1hr")):
    """A saved event with a real Reminder Plan and the pending sends it minted."""
    from apps.delivery.services.reminder_plan_read import resolve_target
    from apps.delivery.services.reminder_plans import save_plan_slots
    from tests.personalization.factories import DigestPreferenceFactory

    DigestPreferenceFactory(user_id=user_id, timezone="America/Los_Angeles")
    target = resolve_target(user_id=user_id, target_kind="saved_event", target_id=event.id)
    save_plan_slots(
        user_id=user_id,
        target_kind="saved_event",
        target_id=event.id,
        slots=slots,
        actor=Actor.user(user_id),
        now=NOW,
        send_target=target,
    )


def _pending_sends(event_id, *, user_id=USER):
    from apps.delivery.models import ScheduledSend

    return ScheduledSend.objects.using(PERSONAL).filter(
        user_id=user_id,
        target_kind="saved_event",
        target_id=event_id,
        status=ScheduledSend.Status.PENDING,
    )


def test_unsaving_removes_the_reminder_plan():
    from apps.delivery.models import ReminderPlan

    event = EventFactory(start_time_utc=START, end_time_utc=END)
    make_saved_event(event_id=event.id)
    _plan_with_sends(event)
    assert (
        ReminderPlan.objects.using(PERSONAL)
        .filter(user_id=USER, target_kind="saved_event", target_id=event.id)
        .exists()
    )

    unsave_event(user_id=USER, event_id=event.id, actor=Actor.user(USER), now=NOW)

    assert (
        not ReminderPlan.objects.using(PERSONAL)
        .filter(user_id=USER, target_kind="saved_event", target_id=event.id)
        .exists()
    )


def test_unsaving_cancels_the_pending_sends_the_plan_minted():
    """The plan's removal is only half of it: a live send is what actually reaches the user."""
    event = EventFactory(start_time_utc=START, end_time_utc=END)
    make_saved_event(event_id=event.id)
    _plan_with_sends(event)
    assert _pending_sends(event.id).count() == 2

    unsave_event(user_id=USER, event_id=event.id, actor=Actor.user(USER), now=NOW)

    assert _pending_sends(event.id).count() == 0


def test_unsaving_records_how_many_plans_it_removed():
    event = EventFactory(start_time_utc=START, end_time_utc=END)
    result = make_saved_event(event_id=event.id)
    _plan_with_sends(event)

    unsave_event(user_id=USER, event_id=event.id, actor=Actor.user(USER), now=NOW)

    entry = PersonalizationAuditEntry.objects.using(PERSONAL).get(
        target_id=result.saved.id, action="saved_event.unsaved"
    )
    assert entry.details["reminder_plans_removed"] == 1


def test_unsaving_an_event_with_no_plan_still_succeeds():
    """A save with no plan is the common case — the removal must be a no-op, not an error."""
    event = EventFactory(start_time_utc=START, end_time_utc=END)
    result = make_saved_event(event_id=event.id)

    unsave_event(user_id=USER, event_id=event.id, actor=Actor.user(USER), now=NOW)

    entry = PersonalizationAuditEntry.objects.using(PERSONAL).get(
        target_id=result.saved.id, action="saved_event.unsaved"
    )
    assert entry.details["reminder_plans_removed"] == 0


def test_unsaving_leaves_another_users_plan_for_the_same_event_alone():
    """Two users save one popular event; one of them unsaves."""
    from apps.delivery.models import ReminderPlan

    event = EventFactory(start_time_utc=START, end_time_utc=END)
    make_saved_event(event_id=event.id)
    _plan_with_sends(event)
    save_event(user_id=OTHER, event_id=event.id, actor=Actor.user(OTHER), now=NOW)
    _plan_with_sends(event, user_id=OTHER)

    unsave_event(user_id=USER, event_id=event.id, actor=Actor.user(USER), now=NOW)

    assert (
        ReminderPlan.objects.using(PERSONAL)
        .filter(user_id=OTHER, target_kind="saved_event", target_id=event.id)
        .exists()
    )
    assert _pending_sends(event.id, user_id=OTHER).count() == 2
