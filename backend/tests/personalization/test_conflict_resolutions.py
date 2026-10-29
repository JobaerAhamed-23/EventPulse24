"""Resolving a conflict (FR-58): the three buttons, and nothing else.

FR-58: "The prompt lists the conflicting event(s) and presents exactly three buttons. **There
is no 'dismiss' or 'X' button.** The user must choose one." And every prompt ends in a
recorded resolution — AD-21: "A resolved pair is immutable and never re-prompted."
"""

from datetime import UTC, datetime, timedelta

import pytest

from apps.personalization.models import ConflictPair, PersonalEvent, PersonalizationAuditEntry
from apps.personalization.services.conflict_resolutions import (
    RESOLUTIONS_BY_KIND,
    ConflictAlreadyResolvedError,
    ConflictPairNotFoundError,
    IllegalResolutionError,
    resolve_conflict,
)
from apps.personalization.services.personal_events import create_personal_event
from shared.actor import Actor
from shared.db import PERSONAL
from shared.ids import uuid7

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
START = datetime(2026, 11, 6, 3, 30, tzinfo=UTC)
END = START + timedelta(hours=2)
TZ = "America/Los_Angeles"

USER = uuid7()
OTHER = uuid7()


def make_conflict():
    """Two overlapping personal events, and the pair between them."""
    first = create_personal_event(
        user_id=USER,
        name="Coffee with Sam",
        start_utc=START,
        end_utc=END,
        start_time_tz=TZ,
        actor=Actor.user(USER),
        now=NOW,
    )
    second = create_personal_event(
        user_id=USER,
        name="Coffee with Alex",
        start_utc=START,
        end_utc=END,
        start_time_tz=TZ,
        actor=Actor.user(USER),
        now=NOW,
    )
    return first, second, second.conflicts[0]


# --- The three buttons ------------------------------------------------------------------------


def test_keeping_both_records_the_resolution():
    _, second, conflict = make_conflict()

    result = resolve_conflict(
        user_id=USER,
        pair_id=conflict.pair_id,
        resolution="keep_both",
        new_side_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        new_side_id=second.event.id,
        actor=Actor.user(USER),
        now=NOW,
    )

    assert result.resolution == "keep_both"
    pair = ConflictPair.objects.get(pk=conflict.pair_id)
    assert pair.status == ConflictPair.Status.RESOLVED
    assert pair.resolution == "keep_both"
    assert pair.resolved_at == NOW


def test_keeping_both_leaves_both_events_in_place():
    # FR-58: "Confirms both events. The conflict indicator remains on both Pulse Cards
    # permanently."
    _, second, conflict = make_conflict()

    resolve_conflict(
        user_id=USER,
        pair_id=conflict.pair_id,
        resolution="keep_both",
        new_side_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        new_side_id=second.event.id,
        actor=Actor.user(USER),
        now=NOW,
    )

    assert PersonalEvent.objects.filter(pk=second.event.id).exists()
    assert PersonalEvent.objects.count() == 2


def test_editing_the_new_one_records_the_resolution_and_keeps_the_event():
    _, second, conflict = make_conflict()

    result = resolve_conflict(
        user_id=USER,
        pair_id=conflict.pair_id,
        resolution="edit_new",
        new_side_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        new_side_id=second.event.id,
        actor=Actor.user(USER),
        now=NOW,
    )

    assert result.resolution == "edit_new"
    # The caller opens the new event in edit mode; the command does not edit it.
    assert result.new_side_id == second.event.id
    assert PersonalEvent.objects.filter(pk=second.event.id).exists()
    pair = ConflictPair.objects.get(pk=conflict.pair_id)
    assert pair.status == ConflictPair.Status.RESOLVED
    assert pair.resolution == "edit_new"


def test_deleting_the_new_one_records_the_resolution_and_removes_the_event():
    # FR-58: "Delete the new one — Removes the new event."
    _, second, conflict = make_conflict()

    result = resolve_conflict(
        user_id=USER,
        pair_id=conflict.pair_id,
        resolution="delete_new",
        new_side_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        new_side_id=second.event.id,
        actor=Actor.user(USER),
        now=NOW,
    )

    assert result.resolution == "delete_new"
    assert not PersonalEvent.objects.filter(pk=second.event.id).exists()
    # The resolution is recorded, even though the event is gone.
    pair = ConflictPair.objects.get(pk=conflict.pair_id)
    assert pair.status == ConflictPair.Status.RESOLVED
    assert pair.resolution == "delete_new"


def test_resolving_writes_an_audit_row():
    _, second, conflict = make_conflict()

    resolve_conflict(
        user_id=USER,
        pair_id=conflict.pair_id,
        resolution="keep_both",
        new_side_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        new_side_id=second.event.id,
        actor=Actor.user(USER),
        now=NOW,
    )

    entry = PersonalizationAuditEntry.objects.get(
        target_id=conflict.pair_id, action="conflict.resolved"
    )
    assert entry.actor_id == USER
    assert entry.details["resolution"] == "keep_both"


def test_deleting_the_new_one_also_writes_the_deletion_audit_row():
    _, second, conflict = make_conflict()

    resolve_conflict(
        user_id=USER,
        pair_id=conflict.pair_id,
        resolution="delete_new",
        new_side_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        new_side_id=second.event.id,
        actor=Actor.user(USER),
        now=NOW,
    )

    # One path to delete an event, one audit trail for it.
    assert PersonalizationAuditEntry.objects.filter(
        target_id=second.event.id, action="personal_event.deleted"
    ).exists()


# --- The closed pair (AD-21) ------------------------------------------------------------------


def test_a_resolved_pair_is_never_re_prompted():
    _, second, conflict = make_conflict()
    resolve_conflict(
        user_id=USER,
        pair_id=conflict.pair_id,
        resolution="keep_both",
        new_side_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        new_side_id=second.event.id,
        actor=Actor.user(USER),
        now=NOW,
    )

    with pytest.raises(ConflictAlreadyResolvedError):
        resolve_conflict(
            user_id=USER,
            pair_id=conflict.pair_id,
            resolution="keep_both",
            new_side_kind=ConflictPair.SideKind.PERSONAL_EVENT,
            new_side_id=second.event.id,
            actor=Actor.user(USER),
            now=NOW,
        )


def test_a_cleared_pair_is_never_re_prompted():
    from apps.personalization.services.personal_events import delete_personal_event

    _, second, conflict = make_conflict()
    delete_personal_event(user_id=USER, event_id=second.event.id, actor=Actor.user(USER), now=NOW)

    with pytest.raises(ConflictAlreadyResolvedError):
        resolve_conflict(
            user_id=USER,
            pair_id=conflict.pair_id,
            resolution="keep_both",
            new_side_kind=ConflictPair.SideKind.PERSONAL_EVENT,
            new_side_id=second.event.id,
            actor=Actor.user(USER),
            now=NOW,
        )


def test_resolving_a_pair_that_is_not_the_callers_is_not_found():
    _, second, conflict = make_conflict()

    with pytest.raises(ConflictPairNotFoundError):
        resolve_conflict(
            user_id=OTHER,
            pair_id=conflict.pair_id,
            resolution="keep_both",
            new_side_kind=ConflictPair.SideKind.PERSONAL_EVENT,
            new_side_id=second.event.id,
            actor=Actor.user(OTHER),
            now=NOW,
        )


# --- The three buttons, and nothing else (FR-58) ----------------------------------------------


def test_a_time_conflict_offers_exactly_three_resolutions():
    assert RESOLUTIONS_BY_KIND[ConflictPair.Kind.TIME] == frozenset(
        {"keep_both", "edit_new", "delete_new"}
    )


def test_a_duplicate_offers_exactly_three_resolutions():
    assert RESOLUTIONS_BY_KIND[ConflictPair.Kind.DUPLICATE] == frozenset(
        {"keep_both", "update_existing", "delete_new"}
    )


def test_a_time_conflict_refuses_the_duplicate_resolution():
    # "Edit the new one" is the time prompt's button; "Update the existing one" is the
    # duplicate prompt's. Neither prompt offers the other's.
    _, second, conflict = make_conflict()

    with pytest.raises(IllegalResolutionError):
        resolve_conflict(
            user_id=USER,
            pair_id=conflict.pair_id,
            resolution="update_existing",
            new_side_kind=ConflictPair.SideKind.PERSONAL_EVENT,
            new_side_id=second.event.id,
            actor=Actor.user(USER),
            now=NOW,
        )

    assert ConflictPair.objects.get(pk=conflict.pair_id).status == ConflictPair.Status.ACTIVE


def test_an_unknown_resolution_is_refused():
    _, second, conflict = make_conflict()

    with pytest.raises(IllegalResolutionError):
        resolve_conflict(
            user_id=USER,
            pair_id=conflict.pair_id,
            resolution="dismiss",
            new_side_kind=ConflictPair.SideKind.PERSONAL_EVENT,
            new_side_id=second.event.id,
            actor=Actor.user(USER),
            now=NOW,
        )


def test_there_is_no_dismiss_resolution():
    # FR-58: "There is no 'dismiss' resolution — the user must make an explicit choice."
    assert "dismiss" not in {r.value for r in ConflictPair.Resolution}


# --- Which side is "new" ---------------------------------------------------------------------


def test_resolving_names_the_other_side_as_the_existing_one():
    # The pair row is symmetric — it stores both sides sorted — so the prompt's asymmetry
    # cannot live in the row. The caller says which side is the new one.
    first, second, conflict = make_conflict()

    result = resolve_conflict(
        user_id=USER,
        pair_id=conflict.pair_id,
        resolution="keep_both",
        new_side_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        new_side_id=second.event.id,
        actor=Actor.user(USER),
        now=NOW,
    )

    assert result.new_side_id == second.event.id
    assert result.existing_side_id == first.event.id
    assert result.existing_side_kind == ConflictPair.SideKind.PERSONAL_EVENT


def test_resolving_names_the_other_side_whatever_the_pairs_order():
    # The pair stores its sides sorted, so the new side may be the row's *right* side. The
    # resolution still has to point at the right other side.
    first, second, conflict = make_conflict()
    pair = ConflictPair.objects.get(pk=conflict.pair_id)
    assert pair.right_id == max(first.event.id, second.event.id)

    # Resolve with whichever side is the row's right-hand one.
    right_id = pair.right_id
    right_kind = pair.right_kind
    other_id = pair.left_id

    result = resolve_conflict(
        user_id=USER,
        pair_id=conflict.pair_id,
        resolution="keep_both",
        new_side_kind=right_kind,
        new_side_id=right_id,
        actor=Actor.user(USER),
        now=NOW,
    )

    assert result.new_side_id == right_id
    assert result.existing_side_id == other_id


def test_resolving_names_the_other_side_when_the_new_side_is_the_pairs_left():
    # The same resolution, from the other end of the sorted pair: the new side is the row's
    # left-hand one, and the existing side is its right-hand one.
    first, second, conflict = make_conflict()
    pair = ConflictPair.objects.get(pk=conflict.pair_id)

    result = resolve_conflict(
        user_id=USER,
        pair_id=conflict.pair_id,
        resolution="keep_both",
        new_side_kind=pair.left_kind,
        new_side_id=pair.left_id,
        actor=Actor.user(USER),
        now=NOW,
    )

    assert result.new_side_id == pair.left_id
    assert result.existing_side_id == pair.right_id


def test_resolving_with_a_side_that_is_not_in_the_pair_leaves_the_other_side_unnamed():
    # A caller that names a side the pair does not contain gets a resolution with no
    # "existing" side to point at. The pair is still resolved — the user answered it — and
    # the audit row records what was chosen.
    _, second, conflict = make_conflict()
    stranger = uuid7()

    result = resolve_conflict(
        user_id=USER,
        pair_id=conflict.pair_id,
        resolution="keep_both",
        new_side_kind=ConflictPair.SideKind.PERSONAL_EVENT,
        new_side_id=stranger,
        actor=Actor.user(USER),
        now=NOW,
    )

    assert result.new_side_id == stranger
    assert result.existing_side_id is None
    assert result.existing_side_kind is None
    pair = ConflictPair.objects.get(pk=conflict.pair_id)
    assert pair.status == ConflictPair.Status.RESOLVED
    assert pair.resolution == "keep_both"
