"""What a reject does to someone who already saved the event (design D4, D5, D6).

The three halves of the user's choice, each pinned separately:

- their **reminders stop** — `delisted -> CANCEL`, so no reminder ever fires for a listing
  editorial has ruled bad;
- they get **no email** — `domain.notices.UNNOTIFIED_KINDS`, because FR-54 has no honest
  wording for a listing we pulled;
- their **conflict pair stays open** — so an editor's reversal is lossless and the open
  AD-17/AD-21 immutability defect is never reached.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from apps.delivery.models import ScheduledSend, StateChangeNotice
from apps.delivery.services.reminder_plan_read import resolve_target
from apps.delivery.services.reminder_plans import save_plan_slots
from apps.ingestion.models import EventStateChange
from apps.ingestion.services.editorial_state import reinstate_event, reject_event
from apps.personalization.models import ConflictPair, SavedEvent
from apps.personalization.services.personal_events import create_personal_event
from apps.personalization.services.saved_events import save_event
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from shared.ids import uuid7
from tests.ingestion.factories import EventFactory, VenueFactory
from tests.personalization.factories import DigestPreferenceFactory
from worker import propagation

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

NOW = datetime(2026, 11, 10, 20, 0, tzinfo=UTC)
START = datetime(2026, 12, 10, 3, 0, tzinfo=UTC)
TZ = "America/Los_Angeles"
EDITOR = Actor.user(uuid4())


def make_user(*, zone=TZ):
    user_id = uuid7()
    DigestPreferenceFactory(user_id=user_id, timezone=zone)
    return user_id


def make_event(*, start=START):
    return EventFactory(
        title="Rooftop Cinema",
        venue=VenueFactory(city="New York City", venue_fingerprint=f"v|{uuid7()}"),
        start_time_utc=start,
        end_time_utc=start + timedelta(hours=2),
        last_seen_at=NOW,
    )


def save(user_id, event):
    return save_event(user_id=user_id, event_id=event.id, actor=Actor.user(user_id), now=NOW)


def with_plan(user_id, event, slots=("1d", "1hr")):
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


def latest_change(event) -> EventStateChange:
    return (
        EventStateChange.objects.using(CATALOG)
        .filter(event_id=event.pk)
        .order_by("-event_version")
        .first()
    )


def propagate_reject(event):
    reject_event(event_id=event.pk, actor=EDITOR, now=NOW)
    return propagation.propagate(state_change_id=latest_change(event).id, now=NOW)


def pending(user_id, event):
    return ScheduledSend.objects.using(PERSONAL).filter(
        user_id=user_id,
        target_kind="saved_event",
        target_id=event.id,
        status=ScheduledSend.Status.PENDING,
    )


# --- The reminders stop (D5) -------------------------------------------------------------


def test_a_reject_cancels_the_savers_pending_reminders():
    """**The reason a reject writes a state change at all.**

    Hiding the event changes no version and reaches nobody, so without this the saver would
    still be told "your event is in 3 hours" for an event editorial deleted.
    """
    user_id = make_user()
    event = make_event()
    save(user_id, event)
    with_plan(user_id, event)
    assert pending(user_id, event).count() == 2

    propagate_reject(event)

    assert pending(user_id, event).count() == 0
    assert (
        ScheduledSend.objects.using(PERSONAL)
        .filter(user_id=user_id, target_id=event.id, status=ScheduledSend.Status.CANCELLED)
        .count()
        == 2
    )


def test_a_reject_with_no_savers_marks_propagated_without_touching_anything():
    event = make_event()

    result = propagate_reject(event)

    assert result.users == 0
    assert result.failed == 0
    assert result.marked is True


# --- No email (D4) -------------------------------------------------------------------------


def test_a_reject_raises_no_notice():
    """FR-54 has no wording for a listing we pulled, and "was cancelled" would be a lie.

    A duplicate or wrong-venue reject says nothing about whether the event happens, so the
    only honest options were silence or new copy no requirement ratifies.
    """
    user_id = make_user()
    event = make_event()
    save(user_id, event)
    with_plan(user_id, event)

    propagate_reject(event)

    assert not StateChangeNotice.objects.using(PERSONAL).filter(user_id=user_id).exists()


def test_a_reject_mints_no_notice_email():
    user_id = make_user()
    event = make_event()
    save(user_id, event)
    with_plan(user_id, event)

    propagate_reject(event)

    assert not (
        ScheduledSend.objects.using(PERSONAL)
        .filter(user_id=user_id, kind=ScheduledSend.Kind.STATE_NOTICE)
        .exists()
    )


# --- The personal side is untouched (D6) ---------------------------------------------------


def test_a_reject_leaves_the_saved_event_snapshot_alone():
    user_id = make_user()
    event = make_event()
    save(user_id, event)
    before = SavedEvent.objects.using(PERSONAL).get(user_id=user_id, event_id=event.id)

    propagate_reject(event)

    after = SavedEvent.objects.using(PERSONAL).get(user_id=user_id, event_id=event.id)
    assert after.event_version == before.event_version
    assert after.start_utc == before.start_utc


def test_a_reject_leaves_the_conflict_pair_open():
    """**The defect this design routes around.**

    `cancel_saved_event` would close the pair as `cleared_by_state_change`, and AD-21 D24
    makes a closed pair immutable — so an editor reinstating the event would restore a real
    clash that `/conflicts` could never mention again.
    """
    user_id = make_user()
    event = make_event()
    # The personal event comes first: the clash is detected when the public one is saved.
    create_personal_event(
        user_id=user_id,
        name="Dinner",
        start_utc=START,
        end_utc=START + timedelta(hours=2),
        start_time_tz=TZ,
        actor=Actor.user(user_id),
        now=NOW,
    )
    assert len(save(user_id, event).conflicts) == 1
    pair = ConflictPair.objects.using(PERSONAL).filter(user_id=user_id).first()
    assert pair is not None and pair.status == ConflictPair.Status.ACTIVE

    propagate_reject(event)

    pair.refresh_from_db(using=PERSONAL)
    assert pair.status == ConflictPair.Status.ACTIVE


def test_a_reinstated_event_still_has_its_conflict_pair():
    """The payoff: reversal is lossless, because nothing was closed."""
    user_id = make_user()
    event = make_event()
    create_personal_event(
        user_id=user_id,
        name="Dinner",
        start_utc=START,
        end_utc=START + timedelta(hours=2),
        start_time_tz=TZ,
        actor=Actor.user(user_id),
        now=NOW,
    )
    save(user_id, event)

    propagate_reject(event)
    reinstate_event(event_id=event.pk, actor=EDITOR, now=NOW)
    propagation.propagate(state_change_id=latest_change(event).id, now=NOW)

    pair = ConflictPair.objects.using(PERSONAL).filter(user_id=user_id).first()
    assert pair.status == ConflictPair.Status.ACTIVE


# --- And the reminders come back (D5) -------------------------------------------------------


def test_a_reinstatement_re_mints_the_savers_reminders():
    user_id = make_user()
    event = make_event()
    save(user_id, event)
    with_plan(user_id, event)
    propagate_reject(event)
    assert pending(user_id, event).count() == 0

    reinstate_event(event_id=event.pk, actor=EDITOR, now=NOW)
    propagation.propagate(state_change_id=latest_change(event).id, now=NOW)

    assert pending(user_id, event).count() == 2


def test_a_reinstatement_raises_no_notice_either():
    """Silent in both directions, as the user chose."""
    user_id = make_user()
    event = make_event()
    save(user_id, event)
    with_plan(user_id, event)
    propagate_reject(event)

    reinstate_event(event_id=event.pk, actor=EDITOR, now=NOW)
    propagation.propagate(state_change_id=latest_change(event).id, now=NOW)

    assert not StateChangeNotice.objects.using(PERSONAL).filter(user_id=user_id).exists()


# --- Idempotency (AD-17) ---------------------------------------------------------------------


def test_propagating_a_reject_twice_is_a_no_op():
    user_id = make_user()
    event = make_event()
    save(user_id, event)
    with_plan(user_id, event)
    change = None

    reject_event(event_id=event.pk, actor=EDITOR, now=NOW)
    change = latest_change(event)
    propagation.propagate(state_change_id=change.id, now=NOW)
    propagation.propagate(state_change_id=change.id, now=NOW)

    assert pending(user_id, event).count() == 0
    assert (
        ScheduledSend.objects.using(PERSONAL)
        .filter(user_id=user_id, target_id=event.id, status=ScheduledSend.Status.CANCELLED)
        .count()
        == 2
    )
