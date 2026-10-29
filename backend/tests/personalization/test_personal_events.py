"""The personal-event commands (FR-18, FR-20, FR-58): create, update, delete.

The tests pin the *behaviour* — the default plan, the conflict that blocks completion, the
version that only rises, the pairs a delete closes — rather than the ORM calls behind it.
"""

from datetime import UTC, datetime, timedelta

import pytest

from apps.personalization.models import (
    ConflictPair,
    PersonalEvent,
    PersonalizationAuditEntry,
)
from apps.personalization.services.personal_events import (
    ConflictFound,
    Created,
    MissingTimezoneError,
    PersonalEventNotFoundError,
    create_personal_event,
    delete_personal_event,
    update_personal_event,
)
from domain.errors import InvalidIntervalError, InvalidTimezoneError, ValidationError
from shared.actor import Actor
from shared.db import PERSONAL
from shared.ids import uuid7

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
START = datetime(2026, 11, 6, 3, 30, tzinfo=UTC)  # 2026-11-05 19:30 in Los Angeles
END = START + timedelta(hours=2)
TZ = "America/Los_Angeles"

USER = uuid7()
OTHER = uuid7()


def make_event(**kwargs):
    """A create command with sensible defaults."""
    args = {
        "user_id": USER,
        "name": "Coffee with Sam",
        "start_utc": START,
        "end_utc": END,
        "start_time_tz": TZ,
        "actor": Actor.user(USER),
        "now": NOW,
    }
    args.update(kwargs)
    return create_personal_event(**args)


# --- Creating (FR-18) ------------------------------------------------------------------------


def test_creating_an_event_stores_it_with_the_zone_the_user_meant():
    result = make_event()

    assert isinstance(result, Created)
    event = PersonalEvent.objects.get(pk=result.event.id)
    assert event.name == "Coffee with Sam"
    assert event.start_utc == START
    assert event.end_utc == END
    assert event.start_time_tz == TZ
    assert event.source == PersonalEvent.Source.USER_CREATED
    assert event.version == 1


def test_creating_an_event_writes_an_audit_row():
    result = make_event()

    entry = PersonalizationAuditEntry.objects.get(target_id=result.event.id)
    assert entry.action == "personal_event.created"
    assert entry.actor_kind == "user"
    assert entry.actor_id == USER


def test_creating_an_event_refuses_a_missing_timezone():
    # FR-18: a Personal Event is created with a required name and start time. The zone says
    # which wall clock the user meant, and a floating local time is refused rather than
    # guessed — guessing is how an event lands an hour out on the wrong side of DST.
    with pytest.raises(MissingTimezoneError) as excinfo:
        make_event(start_time_tz=None)

    assert excinfo.value.code == "missing_timezone"
    assert isinstance(excinfo.value, ValidationError)
    assert not PersonalEvent.objects.exists()


def test_creating_an_event_refuses_an_unknown_timezone():
    with pytest.raises(InvalidTimezoneError):
        make_event(start_time_tz="Middle Earth")

    assert not PersonalEvent.objects.exists()


def test_creating_an_event_refuses_an_end_before_the_start():
    with pytest.raises(InvalidIntervalError):
        make_event(end_utc=START - timedelta(hours=1))

    assert not PersonalEvent.objects.exists()


def test_creating_an_event_without_an_end_stores_a_null_end():
    # An event with no end is a point in time, not an interval. The end is optional and the
    # NULL is stored as given — the event is not given a made-up end.
    result = make_event(end_utc=None)

    assert isinstance(result, Created)
    event = PersonalEvent.objects.get(pk=result.event.id)
    assert event.end_utc is None
    assert event.start_utc == START


def test_creating_an_event_canonicalises_the_zone():
    # "UTC" and "Etc/UTC" are the same zone; the stored name is the canonical one.
    result = make_event(start_time_tz="Etc/UTC")

    assert PersonalEvent.objects.get(pk=result.event.id).start_time_tz == "UTC"


def test_creating_an_event_attaches_the_default_reminder_plan():
    # FR-20: "A new Personal Event has a Reminder Plan of 1d + 1hr by default." The plan is
    # `delivery`'s to own (AD-16), so it is attached through `delivery`'s published service.
    from apps.delivery.models import ReminderPlan

    result = make_event()

    plan = ReminderPlan.objects.get(target_id=result.event.id)
    assert plan.slots == ["1d", "1hr"]
    assert plan.user_id == USER


def test_a_failed_plan_attachment_rolls_the_event_back():
    # The observable proof that the `delivery` call is inside the personal transaction and
    # not a second one: if the plan fails, the event must not survive.
    from apps.personalization.services import personal_events

    def explode(**kwargs):
        raise RuntimeError("the plan could not be attached")

    original = personal_events.attach_default_plan
    personal_events.attach_default_plan = explode
    try:
        with pytest.raises(RuntimeError, match="plan could not be attached"):
            make_event()
    finally:
        personal_events.attach_default_plan = original

    # Neither the event nor its plan survives the failure.
    assert not PersonalEvent.objects.exists()
    from apps.delivery.models import ReminderPlan

    assert not ReminderPlan.objects.exists()


def test_creating_an_event_with_no_conflict_returns_created():
    result = make_event()

    assert isinstance(result, Created)
    assert result.conflicts == ()


# --- Conflict detection on create (FR-58) ----------------------------------------------------


def test_creating_an_event_that_overlaps_returns_a_conflict():
    # FR-58: the creation flow cannot complete without the user's explicit choice.
    make_event(name="Coffee with Sam", start_utc=START, end_utc=END)

    result = make_event(name="Coffee with Alex", start_utc=START, end_utc=END)

    assert isinstance(result, ConflictFound)
    assert len(result.conflicts) == 1
    conflict = result.conflicts[0]
    assert conflict.kind == "time"
    # The prompt's asymmetry: "the new one" is the event just created.
    assert conflict.new_side.id == result.event.id
    assert conflict.other_side.id != result.event.id


def test_a_conflict_does_not_stop_the_event_from_being_written():
    # The pair references the event by id, so the row has to exist. The *prompt* is what is
    # pending, and the pair is the prompt.
    make_event(name="Coffee with Sam", start_utc=START, end_utc=END)

    result = make_event(name="Coffee with Alex", start_utc=START, end_utc=END)

    assert PersonalEvent.objects.filter(pk=result.event.id).exists()
    pair = ConflictPair.objects.get(pk=result.conflicts[0].pair_id)
    assert pair.status == ConflictPair.Status.ACTIVE
    assert pair.resolution is None


def test_a_pair_is_written_once_however_many_times_the_conflict_is_detected():
    make_event(name="Coffee with Sam", start_utc=START, end_utc=END)

    make_event(name="Coffee with Alex", start_utc=START, end_utc=END)
    make_event(name="Coffee with Robin", start_utc=START, end_utc=END)

    # Three pairs: Sam-Alex, Sam-Robin and Alex-Robin (the last two overlap each other too).
    # What matters is that no pair is written twice — the sides are normalised, so (A,B) and
    # (B,A) are one row.
    assert ConflictPair.objects.count() == 3


def test_the_pair_sides_are_normalised():
    first = make_event(name="Coffee with Sam", start_utc=START, end_utc=END)
    second = make_event(name="Coffee with Alex", start_utc=START, end_utc=END)

    pair = ConflictPair.objects.get(pk=second.conflicts[0].pair_id)
    sides = sorted([(pair.left_kind, str(pair.left_id)), (pair.right_kind, str(pair.right_id))])
    assert sides == sorted(
        [
            (ConflictPair.SideKind.PERSONAL_EVENT, str(first.event.id)),
            (ConflictPair.SideKind.PERSONAL_EVENT, str(second.event.id)),
        ]
    )


def test_a_duplicate_is_detected_by_name_and_a_near_start():
    # FR-58: "the system flags a likely duplicate when another Personal Event has the same
    # name (case-insensitive, >=80% Jaccard overlap on tokens) AND starts within 24 hours."
    make_event(name="Coffee with Sam", start_utc=START, end_utc=END)

    result = make_event(
        name="coffee with sam",
        start_utc=START + timedelta(hours=2),
        end_utc=END + timedelta(hours=2),
    )

    assert isinstance(result, ConflictFound)
    assert result.conflicts[0].kind == "duplicate"


def test_an_event_that_does_not_overlap_is_not_a_conflict():
    # The overlap threshold is 15 minutes; an event two hours later is a different thing.
    make_event(name="Coffee with Sam", start_utc=START, end_utc=END)

    result = make_event(
        name="Coffee with Alex",
        start_utc=START + timedelta(hours=3),
        end_utc=END + timedelta(hours=3),
    )

    assert isinstance(result, Created)


# --- Updating (FR-18) ------------------------------------------------------------------------


def test_updating_an_event_bumps_the_version_by_one():
    created = make_event()

    update_personal_event(
        user_id=USER,
        event_id=created.event.id,
        name="Coffee with Sam and Alex",
        actor=Actor.user(USER),
        now=NOW,
    )

    event = PersonalEvent.objects.get(pk=created.event.id)
    assert event.name == "Coffee with Sam and Alex"
    assert event.version == 2


def test_updating_an_event_re_runs_detection():
    make_event(name="Coffee with Sam", start_utc=START, end_utc=END)
    created = make_event(
        name="Coffee with Alex",
        start_utc=START + timedelta(hours=5),
        end_utc=END + timedelta(hours=5),
    )

    # Moving the second event onto the first creates a conflict.
    result = update_personal_event(
        user_id=USER,
        event_id=created.event.id,
        start_utc=START,
        end_utc=END,
        actor=Actor.user(USER),
        now=NOW,
    )

    assert isinstance(result, ConflictFound)
    assert result.conflicts[0].kind == "time"


def test_updating_an_event_out_of_the_way_closes_the_pair():
    make_event(name="Coffee with Sam", start_utc=START, end_utc=END)
    second = make_event(name="Coffee with Alex", start_utc=START, end_utc=END)
    pair_id = second.conflicts[0].pair_id

    update_personal_event(
        user_id=USER,
        event_id=second.event.id,
        start_utc=START + timedelta(hours=5),
        end_utc=END + timedelta(hours=5),
        actor=Actor.user(USER),
        now=NOW,
    )

    pair = ConflictPair.objects.get(pk=pair_id)
    assert pair.status == ConflictPair.Status.CLEARED_BY_STATE_CHANGE
    assert pair.resolution is None
    assert pair.resolved_at is not None


def test_updating_an_event_that_is_not_the_callers_is_not_found():
    created = make_event()

    with pytest.raises(PersonalEventNotFoundError):
        update_personal_event(
            user_id=OTHER,
            event_id=created.event.id,
            name="Hijacked",
            actor=Actor.user(OTHER),
            now=NOW,
        )


def test_updating_an_event_refuses_a_bad_timezone():
    created = make_event()

    with pytest.raises(InvalidTimezoneError):
        update_personal_event(
            user_id=USER,
            event_id=created.event.id,
            start_time_tz="Middle Earth",
            actor=Actor.user(USER),
            now=NOW,
        )


def test_updating_an_event_does_not_reset_the_reminder_plan():
    # FR-20's default is a property of creation. Re-attaching it on every edit would reset a
    # plan the user had customised through FR-9's picker.
    from apps.delivery.models import ReminderPlan
    from apps.delivery.services.reminder_plans import set_plan_slots

    created = make_event()
    set_plan_slots(
        user_id=USER,
        target_kind="personal_event",
        target_id=created.event.id,
        slots=("5d",),
        actor=Actor.user(USER),
        now=NOW,
    )

    update_personal_event(
        user_id=USER,
        event_id=created.event.id,
        name="Renamed",
        actor=Actor.user(USER),
        now=NOW,
    )

    assert ReminderPlan.objects.get(target_id=created.event.id).slots == ["5d"]


# --- Deleting (FR-18) ------------------------------------------------------------------------


def test_deleting_an_event_removes_it():
    created = make_event()

    delete_personal_event(user_id=USER, event_id=created.event.id, actor=Actor.user(USER), now=NOW)

    assert not PersonalEvent.objects.filter(pk=created.event.id).exists()


def test_deleting_an_event_writes_an_audit_row():
    created = make_event()

    delete_personal_event(user_id=USER, event_id=created.event.id, actor=Actor.user(USER), now=NOW)

    entry = PersonalizationAuditEntry.objects.get(
        target_id=created.event.id, action="personal_event.deleted"
    )
    assert entry.actor_id == USER


def test_deleting_an_event_closes_the_pairs_it_was_in():
    # AD-21: a pair that ends because a side went away closes as `cleared_by_state_change`,
    # which is not a user resolution — so the resolution stays NULL.
    make_event(name="Coffee with Sam", start_utc=START, end_utc=END)
    second = make_event(name="Coffee with Alex", start_utc=START, end_utc=END)
    pair_id = second.conflicts[0].pair_id

    delete_personal_event(user_id=USER, event_id=second.event.id, actor=Actor.user(USER), now=NOW)

    pair = ConflictPair.objects.get(pk=pair_id)
    assert pair.status == ConflictPair.Status.CLEARED_BY_STATE_CHANGE
    assert pair.resolution is None
    assert pair.resolved_at is not None


def test_deleting_an_event_that_is_not_the_callers_is_not_found():
    created = make_event()

    with pytest.raises(PersonalEventNotFoundError):
        delete_personal_event(
            user_id=OTHER, event_id=created.event.id, actor=Actor.user(OTHER), now=NOW
        )

    assert PersonalEvent.objects.filter(pk=created.event.id).exists()


def test_deleting_an_event_leaves_the_reminder_plan_row():
    # `personalization` may not write `REMINDER_PLAN` (AD-16). Deleting the plan is
    # `delivery`'s call, and it has no such command yet; the leftover row is inert.
    from apps.delivery.models import ReminderPlan

    created = make_event()

    delete_personal_event(user_id=USER, event_id=created.event.id, actor=Actor.user(USER), now=NOW)

    assert ReminderPlan.objects.filter(target_id=created.event.id).exists()
