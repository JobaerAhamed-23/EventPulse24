"""The conflict detection service (AD-21, FR-58): which events are compared, and what is
written when they clash.

`domain/conflict.py` owns the *rules* — the overlap threshold and the duplicate test. This
module owns the *service* around them: the candidate scan, the side normalisation, and the
rows that result. The tests here therefore prove the service's own behaviour, not the rules'
(which are proved in `tests/domain/`).
"""

from datetime import UTC, datetime, timedelta

import pytest

from apps.ingestion.models import Event
from apps.personalization.models import ConflictPair, PersonalEvent, SavedEvent
from apps.personalization.services.conflicts import (
    Candidate,
    ConflictSide,
    close_pairs_for_side,
    detect_conflicts,
    pairs_for_side,
    reconcile_pairs_for_side,
    record_detected_conflicts,
)
from apps.personalization.services.personal_events import create_personal_event
from apps.personalization.services.saved_events import save_event
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from shared.ids import uuid7
from tests.ingestion.factories import EventFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
START = datetime(2026, 11, 6, 3, 30, tzinfo=UTC)
END = START + timedelta(hours=2)
TZ = "America/Los_Angeles"

USER = uuid7()


def make_event(name="Coffee with Sam", start_utc=START, end_utc=END):
    return create_personal_event(
        user_id=USER,
        name=name,
        start_utc=start_utc,
        end_utc=end_utc,
        start_time_tz=TZ,
        actor=Actor.user(USER),
        now=NOW,
    )


def make_saved(start_utc=START, end_utc=END):
    event = EventFactory(start_time_utc=start_utc, end_time_utc=end_utc)
    return save_event(user_id=USER, event_id=event.id, actor=Actor.user(USER), now=NOW)


# --- The candidate scan ----------------------------------------------------------------------


def test_a_saved_event_is_compared_against_a_personal_event():
    # The scan covers both kinds of side: the user's own events and the public events they
    # saved. A saved public event carries its catalog title into the duplicate rule.
    make_event(name="Coffee with Sam")
    result = make_saved()

    assert len(result.conflicts) == 1
    assert result.conflicts[0].kind == "time"
    assert result.conflicts[0].new_side.kind == ConflictPair.SideKind.SAVED_EVENT
    assert result.conflicts[0].other_side.kind == ConflictPair.SideKind.PERSONAL_EVENT


def test_a_personal_event_is_compared_against_a_saved_event():
    # The same scan in the other direction: a personal event created after a public event was
    # saved is compared against that save.
    make_saved()
    result = make_event(name="Coffee with Sam")

    assert len(result.conflicts) == 1
    assert result.conflicts[0].kind == "time"
    assert result.conflicts[0].new_side.kind == ConflictPair.SideKind.PERSONAL_EVENT
    assert result.conflicts[0].other_side.kind == ConflictPair.SideKind.SAVED_EVENT


def test_a_saved_event_uses_the_catalog_title_for_the_duplicate_rule():
    # The title lives in `catalog` and is not copied into the snapshot, so the candidate
    # carries it for the duplicate test.
    make_event(name="Jazz in the Park")
    event = EventFactory(
        title="Jazz in the Park",
        start_time_utc=START + timedelta(hours=5),
        end_time_utc=END + timedelta(hours=5),
    )

    result = save_event(user_id=USER, event_id=event.id, actor=Actor.user(USER), now=NOW)

    assert len(result.conflicts) == 1
    assert result.conflicts[0].kind == "duplicate"
    assert result.conflicts[0].other_side.name == "Jazz in the Park"


def test_the_candidate_is_excluded_from_its_own_scan():
    # The candidate is the row being written; comparing it against itself would report a
    # conflict with everything.
    created = make_event()

    detected = detect_conflicts(
        user_id=USER,
        candidate=Candidate(
            kind=ConflictPair.SideKind.PERSONAL_EVENT,
            id=created.event.id,
            name="Coffee with Sam",
            start_utc=START,
            end_utc=END,
        ),
    )

    assert detected == []


def test_an_event_outside_the_scan_window_is_not_compared():
    # The window decides which events are *looked at*; the threshold decides whether two of
    # them clash. An event a day away is not even looked at.
    make_event(name="Coffee with Sam")

    detected = detect_conflicts(
        user_id=USER,
        candidate=Candidate(
            kind=ConflictPair.SideKind.PERSONAL_EVENT,
            id=None,
            name="Coffee with Alex",
            start_utc=START + timedelta(days=2),
            end_utc=END + timedelta(days=2),
        ),
    )

    assert detected == []


# --- The normalisation (one row for (A,B) and (B,A)) -----------------------------------------


def test_the_two_sides_are_stored_in_a_fixed_order():
    # The model's unique constraint is symmetric only if the sides are sorted. Two writes of
    # the same conflict in opposite orders are one row.
    first = make_event(name="Coffee with Sam")
    second = make_event(name="Coffee with Alex")

    pair = ConflictPair.objects.get(pk=second.conflicts[0].pair_id)
    assert pair.left_id == min(first.event.id, second.event.id)
    assert pair.right_id == max(first.event.id, second.event.id)


def test_a_pair_is_written_once_however_many_times_the_conflict_is_detected():
    make_event(name="Coffee with Sam")
    second = make_event(name="Coffee with Alex")

    pair_id = second.conflicts[0].pair_id
    detected = detect_conflicts(
        user_id=USER,
        candidate=Candidate(
            kind=ConflictPair.SideKind.PERSONAL_EVENT,
            id=second.event.id,
            name="Coffee with Alex",
            start_utc=START,
            end_utc=END,
        ),
    )
    record_detected_conflicts(user_id=USER, detected=detected, actor=Actor.user(USER), now=NOW)

    assert ConflictPair.objects.filter(pk=pair_id).count() == 1


def test_a_closed_pair_is_never_re_opened():
    # AD-21: "A resolved pair is immutable and never re-prompted." Re-detecting the same
    # overlap after the pair closed must not make a new prompt.
    make_event(name="Coffee with Sam")
    second = make_event(name="Coffee with Alex")
    pair_id = second.conflicts[0].pair_id
    pair = ConflictPair.objects.get(pk=pair_id)
    pair.status = ConflictPair.Status.RESOLVED
    pair.resolution = ConflictPair.Resolution.KEEP_BOTH
    pair.resolved_at = NOW
    pair.save(update_fields=["status", "resolution", "resolved_at", "updated_at"])

    detected = detect_conflicts(
        user_id=USER,
        candidate=Candidate(
            kind=ConflictPair.SideKind.PERSONAL_EVENT,
            id=second.event.id,
            name="Coffee with Alex",
            start_utc=START,
            end_utc=END,
        ),
    )
    recorded = record_detected_conflicts(
        user_id=USER, detected=detected, actor=Actor.user(USER), now=NOW
    )

    assert recorded == []
    assert ConflictPair.objects.filter(pk=pair_id).count() == 1


def test_a_conflict_found_against_an_unsaved_candidate_is_not_written():
    # A `Candidate` may be detected before its row exists, but a pair names both sides by id
    # and cannot hold a NULL. Such a conflict has nothing to point at, so it is skipped
    # rather than written as a broken row.
    make_event(name="Coffee with Sam")
    detected = detect_conflicts(
        user_id=USER,
        candidate=Candidate(
            kind=ConflictPair.SideKind.PERSONAL_EVENT,
            id=None,
            name="Coffee with Alex",
            start_utc=START,
            end_utc=END,
        ),
    )
    assert len(detected) == 1

    recorded = record_detected_conflicts(
        user_id=USER, detected=detected, actor=Actor.user(USER), now=NOW
    )

    assert recorded == []
    assert not ConflictPair.objects.exists()


# --- Closing a pair --------------------------------------------------------------------------


def test_closing_a_side_closes_every_pair_naming_it():
    make_event(name="Coffee with Sam")
    second = make_event(name="Coffee with Alex")

    closed = close_pairs_for_side(
        user_id=USER,
        kind=ConflictPair.SideKind.PERSONAL_EVENT,
        side_id=second.event.id,
        now=NOW,
    )

    assert closed == 1
    pair = ConflictPair.objects.get(pk=second.conflicts[0].pair_id)
    assert pair.status == ConflictPair.Status.CLEARED_BY_STATE_CHANGE
    assert pair.resolution is None


def test_pairs_for_side_returns_the_pairs_naming_it():
    make_event(name="Coffee with Sam")
    second = make_event(name="Coffee with Alex")

    pairs = pairs_for_side(
        user_id=USER, kind=ConflictPair.SideKind.PERSONAL_EVENT, side_id=second.event.id
    )

    assert [p.pk for p in pairs] == [second.conflicts[0].pair_id]


# --- Reconciling a moved side ----------------------------------------------------------------


def test_reconciling_a_moved_side_closes_the_pairs_that_no_longer_clash():
    make_event(name="Coffee with Sam")
    second = make_event(name="Coffee with Alex")
    pair_id = second.conflicts[0].pair_id

    closed = reconcile_pairs_for_side(
        user_id=USER,
        kind=ConflictPair.SideKind.PERSONAL_EVENT,
        side_id=second.event.id,
        side=ConflictSide(
            kind=ConflictPair.SideKind.PERSONAL_EVENT,
            id=second.event.id,
            name="Coffee with Alex",
            start_utc=START + timedelta(hours=5),
            end_utc=END + timedelta(hours=5),
        ),
        now=NOW,
    )

    assert closed == 1
    pair = ConflictPair.objects.get(pk=pair_id)
    assert pair.status == ConflictPair.Status.CLEARED_BY_STATE_CHANGE


def test_reconciling_a_side_that_still_clashes_closes_nothing():
    make_event(name="Coffee with Sam")
    second = make_event(name="Coffee with Alex")
    pair_id = second.conflicts[0].pair_id

    closed = reconcile_pairs_for_side(
        user_id=USER,
        kind=ConflictPair.SideKind.PERSONAL_EVENT,
        side_id=second.event.id,
        side=ConflictSide(
            kind=ConflictPair.SideKind.PERSONAL_EVENT,
            id=second.event.id,
            name="Coffee with Alex",
            start_utc=START,
            end_utc=END,
        ),
        now=NOW,
    )

    assert closed == 0
    assert ConflictPair.objects.get(pk=pair_id).status == ConflictPair.Status.ACTIVE


def test_reconciling_a_side_whose_other_side_is_gone_closes_nothing():
    # The other side of the pair no longer exists, so there is nothing to re-judge. The pair
    # is left alone rather than closed on a guess.
    first = make_event(name="Coffee with Sam")
    second = make_event(name="Coffee with Alex")
    pair_id = second.conflicts[0].pair_id
    # Delete the *other* side of the pair, keeping the side being reconciled.
    if first.event.id == ConflictPair.objects.get(pk=pair_id).left_id:
        PersonalEvent.objects.filter(pk=first.event.id).delete()
    else:
        PersonalEvent.objects.filter(pk=second.event.id).delete()

    closed = reconcile_pairs_for_side(
        user_id=USER,
        kind=ConflictPair.SideKind.PERSONAL_EVENT,
        side_id=second.event.id,
        side=ConflictSide(
            kind=ConflictPair.SideKind.PERSONAL_EVENT,
            id=second.event.id,
            name="Coffee with Alex",
            start_utc=START,
            end_utc=END,
        ),
        now=NOW,
    )

    assert closed == 0
    assert ConflictPair.objects.get(pk=pair_id).status == ConflictPair.Status.ACTIVE


def test_reconciling_a_side_whose_other_side_is_a_deleted_save_closes_nothing():
    make_event(name="Coffee with Sam")
    saved = make_saved()
    pair_id = saved.conflicts[0].pair_id
    SavedEvent.objects.filter(pk=saved.saved.id).delete()

    closed = reconcile_pairs_for_side(
        user_id=USER,
        kind=ConflictPair.SideKind.SAVED_EVENT,
        side_id=saved.saved.id,
        side=ConflictSide(
            kind=ConflictPair.SideKind.SAVED_EVENT,
            id=saved.saved.id,
            name="saved",
            start_utc=START,
            end_utc=END,
        ),
        now=NOW,
    )

    assert closed == 0
    assert ConflictPair.objects.get(pk=pair_id).status == ConflictPair.Status.ACTIVE


def test_reconciling_a_side_that_is_not_in_the_pair_closes_nothing():
    make_event(name="Coffee with Sam")
    second = make_event(name="Coffee with Alex")
    pair_id = second.conflicts[0].pair_id

    closed = reconcile_pairs_for_side(
        user_id=USER,
        kind=ConflictPair.SideKind.PERSONAL_EVENT,
        side_id=uuid7(),
        side=ConflictSide(
            kind=ConflictPair.SideKind.PERSONAL_EVENT,
            id=uuid7(),
            name="Someone else",
            start_utc=START,
            end_utc=END,
        ),
        now=NOW,
    )

    assert closed == 0
    assert ConflictPair.objects.get(pk=pair_id).status == ConflictPair.Status.ACTIVE


# --- The saved event's own side ----------------------------------------------------------------


def test_a_saved_event_side_is_labelled_with_its_catalog_event_id():
    event = EventFactory(start_time_utc=START, end_time_utc=END)
    result = save_event(user_id=USER, event_id=event.id, actor=Actor.user(USER), now=NOW)

    saved = SavedEvent.objects.get(pk=result.saved.id)
    from apps.personalization.services.conflicts import _saved_side

    side = _saved_side(saved)
    assert side.name == f"saved {event.id}"
    assert side.kind == ConflictPair.SideKind.SAVED_EVENT


def test_a_non_public_event_is_not_saved_and_never_compared():
    # The catalog read refuses an unpublished event, so it never becomes a candidate.
    from apps.ingestion.services.catalog_read import EventNotFoundError

    event = EventFactory(start_time_utc=START, publication_status=Event.PublicationStatus.IN_REVIEW)

    with pytest.raises(EventNotFoundError):
        save_event(user_id=USER, event_id=event.id, actor=Actor.user(USER), now=NOW)

    assert not SavedEvent.objects.exists()


# --- The normalisation ------------------------------------------------------------------------


def test_the_normalisation_swaps_the_sides_into_a_fixed_order():
    # The pair's unique constraint is symmetric only if the sides are sorted, so `(A, B)` and
    # `(B, A)` are one row. Whichever order the sides arrive in, the row is the same.
    from apps.personalization.services.conflicts import _normalise

    left = ConflictSide(
        kind=ConflictPair.SideKind.PERSONAL_EVENT,
        id=uuid7(),
        name="Coffee with Sam",
        start_utc=START,
        end_utc=END,
    )
    right = ConflictSide(
        kind=ConflictPair.SideKind.PERSONAL_EVENT,
        id=uuid7(),
        name="Coffee with Alex",
        start_utc=START,
        end_utc=END,
    )

    first, second = _normalise(left, right)
    assert (first.id, second.id) == (left.id, right.id)

    flipped_first, flipped_second = _normalise(right, left)
    assert (flipped_first.id, flipped_second.id) == (left.id, right.id)


def test_the_normalisation_orders_the_kind_before_the_id():
    # The order is total and puts the kind first, so a saved event and a personal event are
    # ordered by kind rather than by id.
    from apps.personalization.services.conflicts import _normalise

    personal = ConflictSide(
        kind=ConflictPair.SideKind.PERSONAL_EVENT,
        id=uuid7(),
        name="Coffee with Sam",
        start_utc=START,
        end_utc=END,
    )
    saved = ConflictSide(
        kind=ConflictPair.SideKind.SAVED_EVENT,
        id=uuid7(),
        name="saved",
        start_utc=START,
        end_utc=END,
    )

    first, second = _normalise(personal, saved)

    assert first.kind == ConflictPair.SideKind.PERSONAL_EVENT
    assert second.kind == ConflictPair.SideKind.SAVED_EVENT


# --- The other side of a pair ------------------------------------------------------------------


def test_the_other_side_is_found_when_the_side_is_the_pairs_left():
    from apps.personalization.services.conflicts import _other_side_of

    make_event(name="Coffee with Sam")
    second = make_event(name="Coffee with Alex")
    pair = ConflictPair.objects.get(pk=second.conflicts[0].pair_id)

    other = _other_side_of(pair, pair.left_kind, pair.left_id)

    assert other is not None
    assert other.id == pair.right_id
    assert other.kind == pair.right_kind


def test_the_other_side_is_found_when_the_side_is_the_pairs_right():
    from apps.personalization.services.conflicts import _other_side_of

    make_event(name="Coffee with Sam")
    second = make_event(name="Coffee with Alex")
    pair = ConflictPair.objects.get(pk=second.conflicts[0].pair_id)

    other = _other_side_of(pair, pair.right_kind, pair.right_id)

    assert other is not None
    assert other.id == pair.left_id
    assert other.kind == pair.left_kind


def test_the_other_side_of_a_pair_naming_a_saved_event_is_the_save():
    from apps.personalization.services.conflicts import _other_side_of

    make_event(name="Coffee with Sam")
    saved = make_saved()
    pair = ConflictPair.objects.get(pk=saved.conflicts[0].pair_id)
    # The sides are sorted by (kind, id), and `personal_event` sorts before `saved_event`.
    if pair.left_kind == ConflictPair.SideKind.SAVED_EVENT:
        saved_kind, saved_id = pair.left_kind, pair.left_id
        other_id = pair.right_id
    else:
        saved_kind, saved_id = pair.right_kind, pair.right_id
        other_id = pair.left_id
    assert saved_kind == ConflictPair.SideKind.SAVED_EVENT

    other = _other_side_of(pair, saved_kind, saved_id)

    assert other is not None
    assert other.kind == ConflictPair.SideKind.PERSONAL_EVENT
    assert other.id == other_id


def test_the_other_side_of_a_pair_reads_the_save_from_the_database():
    # The same pair, asked from the personal side. The helper reads the save's row to build
    # its side — a saved public event has no name of its own in `personal`, so the row has
    # to be read to say what the side is.
    from apps.personalization.services.conflicts import _other_side_of

    make_event(name="Coffee with Sam")
    saved = make_saved()
    pair = ConflictPair.objects.get(pk=saved.conflicts[0].pair_id)

    if pair.left_kind == ConflictPair.SideKind.PERSONAL_EVENT:
        other = _other_side_of(pair, pair.left_kind, pair.left_id)
        saved_id = pair.right_id
    else:
        other = _other_side_of(pair, pair.right_kind, pair.right_id)
        saved_id = pair.left_id

    assert other is not None
    assert other.kind == ConflictPair.SideKind.SAVED_EVENT
    assert other.id == saved_id
    assert other.name == f"saved {saved.saved.event_id}"


def test_the_other_side_of_a_pair_whose_side_is_gone_is_none():
    from apps.personalization.services.conflicts import _other_side_of

    make_event(name="Coffee with Sam")
    second = make_event(name="Coffee with Alex")
    pair = ConflictPair.objects.get(pk=second.conflicts[0].pair_id)
    PersonalEvent.objects.filter(pk=second.event.id).delete()

    # The other side of the pair is the personal event that has just been deleted.
    gone_kind, gone_id = pair.right_kind, pair.right_id
    other = _other_side_of(pair, pair.left_kind, pair.left_id)

    assert other is None
    assert (gone_kind, gone_id) != (pair.left_kind, pair.left_id)


def test_the_other_side_of_a_pair_whose_save_is_gone_is_none():
    from apps.personalization.services.conflicts import _other_side_of

    make_event(name="Coffee with Sam")
    saved = make_saved()
    pair = ConflictPair.objects.get(pk=saved.conflicts[0].pair_id)
    SavedEvent.objects.filter(pk=saved.saved.id).delete()

    # Ask for the *personal* side of the pair. The other side is the save, which has just
    # been deleted — so there is nothing to read, and the helper says so rather than
    # inventing a side.
    if pair.left_kind == ConflictPair.SideKind.PERSONAL_EVENT:
        other = _other_side_of(pair, pair.left_kind, pair.left_id)
    else:
        other = _other_side_of(pair, pair.right_kind, pair.right_id)

    assert other is None


def test_the_other_side_of_a_pair_that_does_not_name_the_side_is_none():
    from apps.personalization.services.conflicts import _other_side_of

    make_event(name="Coffee with Sam")
    second = make_event(name="Coffee with Alex")
    pair = ConflictPair.objects.get(pk=second.conflicts[0].pair_id)

    # A side the pair does not name has no other side: the helper refuses to guess which of
    # the pair's two sides was meant.
    other = _other_side_of(pair, ConflictPair.SideKind.PERSONAL_EVENT, uuid7())

    assert other is None
