"""The `personalization` models: the constraints the database holds (design D1-D28).

Every invariant here is a check constraint or a unique constraint, so a violation is an
`IntegrityError` from Postgres rather than a Python assertion. The tests pin the *rule*, not
Django's rendering of it.
"""

from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction

from apps.personalization.models import ConflictPair, PersonalEvent, SavedEvent
from shared.db import PERSONAL
from shared.ids import uuid7
from tests.personalization.factories import (
    FIRST_START,
    ConflictPairFactory,
    PersonalEventFactory,
    PersonalizationAuditEntryFactory,
    SavedEventFactory,
)

pytestmark = pytest.mark.django_db(databases=[PERSONAL])


# --- PersonalEvent ----------------------------------------------------------------------------


def test_personal_event_defaults_to_source_user_created():
    event = PersonalEventFactory.create()

    assert event.source == PersonalEvent.Source.USER_CREATED
    assert event.source == "user_created"


def test_personal_event_starts_at_version_one():
    assert PersonalEventFactory.create().version == 1


def test_personal_event_accepts_an_open_ended_interval():
    # A missing end is legal: an open-ended interval overlaps everything after it
    # (domain.conflict).
    event = PersonalEventFactory.create(end_utc=None)

    assert PersonalEvent.objects.get(pk=event.pk).end_utc is None


def test_personal_event_rejects_an_end_before_its_start():
    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        PersonalEventFactory.create(end_utc=FIRST_START - timedelta(minutes=1))


def test_personal_event_accepts_an_end_equal_to_its_start():
    # A zero-length interval is legal at the model layer; it occupies no time and never
    # conflicts (domain.conflict).
    event = PersonalEventFactory.create(end_utc=FIRST_START)

    assert PersonalEvent.objects.get(pk=event.pk).end_utc == FIRST_START


def test_personal_event_rejects_a_zero_version():
    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        PersonalEventFactory.create(version=0)


# --- SavedEvent -------------------------------------------------------------------------------


def test_saved_event_holds_the_catalog_event_id_by_value():
    # The id is stored as a plain UUID column. No catalog Event needs to exist: the wall means
    # this app never joins `catalog` to check.
    catalog_event_id = uuid7()

    saved = SavedEventFactory.create(event_id=catalog_event_id)

    assert SavedEvent.objects.get(pk=saved.pk).event_id == catalog_event_id


def test_saved_event_rejects_a_second_save_of_the_same_event():
    first = SavedEventFactory.create()

    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        SavedEventFactory.create(user_id=first.user_id, event_id=first.event_id)


def test_saved_event_allows_two_users_to_save_the_same_event():
    first = SavedEventFactory.create()

    SavedEventFactory.create(event_id=first.event_id)

    assert SavedEvent.objects.filter(event_id=first.event_id).count() == 2


def test_saved_event_rejects_a_zero_event_version():
    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        SavedEventFactory.create(event_version=0)


def test_saved_event_accepts_an_open_ended_snapshot():
    saved = SavedEventFactory.create(end_utc=None)

    assert SavedEvent.objects.get(pk=saved.pk).end_utc is None


# --- ConflictPair -----------------------------------------------------------------------------
#
# The three legal status shapes, the resolution/kind pairing, and the pair's symmetry.


def test_conflict_pair_defaults_to_active_with_no_resolution():
    pair = ConflictPairFactory.create()

    assert pair.status == ConflictPair.Status.ACTIVE
    assert pair.resolution is None
    assert pair.resolved_at is None


def test_conflict_pair_accepts_a_resolved_pair_with_a_resolution():
    pair = ConflictPairFactory.create(
        status=ConflictPair.Status.RESOLVED,
        resolution=ConflictPair.Resolution.KEEP_BOTH,
        resolved_at=FIRST_START,
    )

    assert pair.status == ConflictPair.Status.RESOLVED


def test_conflict_pair_accepts_a_pair_cleared_by_a_state_change():
    # Cleared by a state change: no user decision, so the resolution stays NULL. That NULL is
    # exactly what distinguishes it from a resolved pair.
    pair = ConflictPairFactory.create(
        status=ConflictPair.Status.CLEARED_BY_STATE_CHANGE,
        resolution=None,
        resolved_at=FIRST_START,
    )

    assert pair.resolution is None


@pytest.mark.parametrize(
    ("status", "resolution", "resolved_at"),
    [
        ("resolved", None, FIRST_START),
        ("resolved", "keep_both", None),
        ("active", "keep_both", FIRST_START),
        ("cleared_by_state_change", "keep_both", FIRST_START),
        ("cleared_by_state_change", None, None),
    ],
    ids=[
        "resolved-without-a-resolution",
        "resolved-without-a-timestamp",
        "active-with-a-resolution",
        "cleared-with-a-resolution",
        "cleared-without-a-timestamp",
    ],
)
def test_conflict_pair_rejects_an_illegal_status_shape(status, resolution, resolved_at):
    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        ConflictPairFactory.create(status=status, resolution=resolution, resolved_at=resolved_at)


def test_conflict_pair_rejects_the_same_side_twice():
    # A conflict is between two distinct events. The unique constraint can't catch this one:
    # the two sides differ, so the row is unique.
    side_id = uuid7()

    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        ConflictPairFactory.create(
            left_kind="personal_event",
            left_id=side_id,
            right_kind="personal_event",
            right_id=side_id,
        )


def test_conflict_pair_rejects_a_duplicate_pair():
    first = ConflictPairFactory.create()

    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        ConflictPairFactory.create(
            user_id=first.user_id,
            left_kind=first.left_kind,
            left_id=first.left_id,
            right_kind=first.right_kind,
            right_id=first.right_id,
        )


def test_conflict_pair_allows_the_same_pair_for_two_users():
    first = ConflictPairFactory.create()

    second = ConflictPairFactory.create(
        left_kind=first.left_kind,
        left_id=first.left_id,
        right_kind=first.right_kind,
        right_id=first.right_id,
    )

    assert ConflictPair.objects.filter(left_id=first.left_id).count() == 2
    assert second.user_id != first.user_id


@pytest.mark.parametrize(
    ("kind", "resolution"),
    [
        ("time", "keep_both"),
        ("time", "edit_new"),
        ("time", "delete_new"),
        ("duplicate", "keep_both"),
        ("duplicate", "update_existing"),
        ("duplicate", "delete_new"),
    ],
)
def test_conflict_pair_accepts_a_resolution_legal_for_its_kind(kind, resolution):
    pair = ConflictPairFactory.create(
        kind=kind,
        status=ConflictPair.Status.RESOLVED,
        resolution=resolution,
        resolved_at=FIRST_START,
    )

    assert pair.resolution == resolution


@pytest.mark.parametrize(
    ("kind", "resolution"),
    [("time", "update_existing"), ("duplicate", "edit_new")],
)
def test_conflict_pair_rejects_a_resolution_illegal_for_its_kind(kind, resolution):
    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        ConflictPairFactory.create(
            kind=kind,
            status=ConflictPair.Status.RESOLVED,
            resolution=resolution,
            resolved_at=FIRST_START,
        )


def test_conflict_pair_has_no_dismiss_resolution():
    # PRD §3: there is no dismiss resolution; the user must make an explicit choice.
    assert "dismiss" not in ConflictPair.Resolution.values
    assert set(ConflictPair.Resolution.values) == {
        "keep_both",
        "edit_new",
        "delete_new",
        "update_existing",
        "skip_public",
    }


# --- The audit table --------------------------------------------------------------------------


def test_personalization_audit_entry_stores_the_actor_by_value():
    entry = PersonalizationAuditEntryFactory.create()

    assert entry.actor_kind == "system"
    assert entry.actor_label == "personalization"
    assert entry.actor_id is None


# --- Readable representations -----------------------------------------------------------------


def test_personal_event_reads_as_its_name():
    assert str(PersonalEventFactory.create(name="Jazz Night")) == "Jazz Night"


def test_saved_event_reads_as_its_catalog_event_id():
    saved = SavedEventFactory.create()

    assert str(saved) == f"saved {saved.event_id}"


def test_conflict_pair_reads_as_its_kind_and_status():
    pair = ConflictPairFactory.create(kind="time", status="active")

    assert str(pair) == "time conflict active"
