"""The Reminder Plan read: the computed delivery time per slot (FR-9, AD-7, AD-16).

**What this file pins is the read's own behaviour**, not the HTTP surface's (which
`test_reminder_plan_api.py` owns):

- the shift is applied **server-side**, and the delivery time is the **post-Quiet-Hours**
  instant — the same one the minting path stores in `due_at`;
- a deferred slot reports the window's end, and that end **is** the delivery instant —
  one instant, not two;
- a slot outside the window is not deferred, and says so;
- the target is resolved first, so a target of the wrong kind is refused rather than
  given a plan about a nonsense target;
- the query count is bounded and does not grow with the slot count.
"""

from datetime import UTC, datetime, time, timedelta
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.test.utils import CaptureQueriesContext

from apps.delivery.services.reminder_plan_read import (
    ReminderTargetNotFoundError,
    compute_deliveries,
    read_plan,
    resolve_target,
)
from apps.personalization.services.personal_events import create_personal_event
from apps.personalization.services.saved_events import save_event
from domain.quiet_hours import QuietHours
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import EventFactory, VenueFactory
from tests.personalization.factories import DigestPreferenceFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

User = get_user_model()

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
ZONE = "America/Los_Angeles"

#: 2026-11-11 18:00 in Los Angeles — outside the default quiet window.
AFTERNOON_START = datetime(2026, 11, 12, 2, 0, tzinfo=UTC)

#: 2026-11-13 23:30 in Los Angeles — inside the quiet window's evening side.
LATE_START = datetime(2026, 11, 14, 7, 30, tzinfo=UTC)

#: The default window, 22:00–08:00 local.
DEFAULT_WINDOW = QuietHours(start=time(22, 0), end=time(8, 0))


def a_user():
    user = User.objects.create_user(email=f"{uuid4()}@example.test", password="pw")
    DigestPreferenceFactory(user_id=user.pk, timezone=ZONE)
    return user


def a_personal_event(user, *, start_utc=AFTERNOON_START):
    result = create_personal_event(
        user_id=user.pk,
        name="Personal Event",
        start_utc=start_utc,
        end_utc=start_utc + timedelta(hours=2),
        start_time_tz=ZONE,
        actor=Actor.user(user.pk),
        now=NOW,
    )
    return result.event


def a_saved_event(user, *, start_utc=AFTERNOON_START):
    event = EventFactory(
        title="Brooklyn Tech Meetup",
        venue=VenueFactory(city="New York City", venue_fingerprint=f"venue-{uuid4()}"),
        start_time_utc=start_utc,
        last_seen_at=NOW,
    )
    save_event(user_id=user.pk, event_id=event.id, actor=Actor.user(user.pk), now=NOW)
    return event


# --- The shift ----------------------------------------------------------------------------------


def test_a_slot_outside_the_window_is_not_deferred():
    deliveries = compute_deliveries(
        slots=("1d",),
        start_utc=AFTERNOON_START,
        zone=ZONE,
        window=DEFAULT_WINDOW,
    )

    assert deliveries[0].deferred is False
    assert deliveries[0].deferred_to is None
    assert deliveries[0].delivery_at == AFTERNOON_START - timedelta(days=1)


def test_a_slot_inside_the_window_is_deferred_to_the_windows_end():
    """The UX spec's worked example, computed on the server.

    An event at 11:30pm local with a 1-hour slot would deliver at 10:30pm — inside Quiet
    Hours — so the chip dims and the tooltip reads *"Will deliver at 8:00 am Saturday."*
    """
    deliveries = compute_deliveries(
        slots=("1hr",),
        start_utc=LATE_START,
        zone=ZONE,
        window=DEFAULT_WINDOW,
    )

    delivery = deliveries[0]
    assert delivery.deferred is True
    # The window's end **is** the delivery instant — one instant, not two.
    assert delivery.deferred_to == delivery.delivery_at
    # 2026-11-13 22:30 local defers to 08:00 local on the 14th → 16:00Z.
    assert delivery.delivery_at == datetime(2026, 11, 14, 16, 0, tzinfo=UTC)


def test_no_window_means_no_deferral():
    deliveries = compute_deliveries(
        slots=("1hr",),
        start_utc=LATE_START,
        zone=ZONE,
        window=None,
    )

    assert deliveries[0].deferred is False
    assert deliveries[0].delivery_at == LATE_START - timedelta(hours=1)


def test_a_disabled_window_means_no_deferral():
    """A window whose start equals its end is "off", and the shift says so."""
    disabled = QuietHours(start=DEFAULT_WINDOW.start, end=DEFAULT_WINDOW.start)

    deliveries = compute_deliveries(
        slots=("1hr",),
        start_utc=LATE_START,
        zone=ZONE,
        window=disabled,
    )

    assert deliveries[0].deferred is False


def test_a_custom_slots_offset_is_honoured():
    deliveries = compute_deliveries(
        slots=("custom:90",),
        start_utc=AFTERNOON_START,
        zone=ZONE,
        window=DEFAULT_WINDOW,
    )

    assert deliveries[0].delivery_at == AFTERNOON_START - timedelta(minutes=90)
    assert deliveries[0].deferred is False


def test_a_malformed_slot_has_no_delivery_time():
    """The validator refuses such a slot on write, so this is defensive — not a guess."""
    deliveries = compute_deliveries(
        slots=("custom:soon",),
        start_utc=AFTERNOON_START,
        zone=ZONE,
        window=DEFAULT_WINDOW,
    )

    assert deliveries[0].delivery_at is None
    assert deliveries[0].deferred is False


def test_the_deliveries_keep_the_slots_order():
    deliveries = compute_deliveries(
        slots=("5d", "2d", "1d", "1hr"),
        start_utc=AFTERNOON_START,
        zone=ZONE,
        window=DEFAULT_WINDOW,
    )

    assert [delivery.slot for delivery in deliveries] == ["5d", "2d", "1d", "1hr"]


# --- The target --------------------------------------------------------------------------------


def test_a_personal_event_resolves():
    user = a_user()
    event = a_personal_event(user)

    target = resolve_target(user_id=user.pk, target_kind="personal_event", target_id=event.id)

    assert target.target_id == event.id
    assert target.start_utc == event.start_utc
    assert target.version == event.version


def test_a_saved_event_resolves():
    """A saved event's target id is the **catalog** event's id — the tree's convention."""
    user = a_user()
    event = a_saved_event(user)

    target = resolve_target(user_id=user.pk, target_kind="saved_event", target_id=event.id)

    assert target.target_id == event.id
    assert target.catalog_event_id == event.id


def test_another_users_target_is_refused():
    owner = a_user()
    intruder = a_user()
    event = a_personal_event(owner)

    with pytest.raises(ReminderTargetNotFoundError):
        resolve_target(user_id=intruder.pk, target_kind="personal_event", target_id=event.id)


def test_a_target_of_the_other_kind_is_refused():
    """A personal event's id is not a saved event's id."""
    user = a_user()
    event = a_personal_event(user)

    with pytest.raises(ReminderTargetNotFoundError):
        resolve_target(user_id=user.pk, target_kind="saved_event", target_id=event.id)


def test_an_unknown_kind_is_refused():
    user = a_user()

    with pytest.raises(ReminderTargetNotFoundError):
        resolve_target(user_id=user.pk, target_kind="nonsense", target_id=uuid4())


# --- The read ----------------------------------------------------------------------------------


def test_reading_a_plan_with_no_slots():
    user = a_user()
    event = a_personal_event(user)

    view = read_plan(user_id=user.pk, target_kind="personal_event", target_id=event.id)

    assert view.slots == ("1d", "1hr")
    assert len(view.deliveries) == 2


def test_reading_a_plan_that_does_not_exist_is_the_empty_state():
    """A saved event has no plan until one is saved — and the picker shows the empty state."""
    user = a_user()
    event = a_saved_event(user)

    view = read_plan(user_id=user.pk, target_kind="saved_event", target_id=event.id)

    assert view.slots == ()
    assert view.deliveries == ()


def test_reading_a_missing_target_is_refused():
    user = a_user()

    with pytest.raises(ReminderTargetNotFoundError):
        read_plan(user_id=user.pk, target_kind="personal_event", target_id=uuid4())


def test_the_query_count_does_not_grow_with_the_slot_count():
    """Four slots cost the same queries as one.

    The per-slot delivery times are computed **in Python** over four facts — the plan,
    the preference, the zone and the target — not with a query per slot.

    **Both reads are measured in the steady state.** The first read of a user's
    notification preference *creates* the row (`get_preference` reads by writing), so it
    costs one extra INSERT. That is a one-time cost per user, not a per-slot cost, and
    measuring the first read against a later one would report a difference that has
    nothing to do with the slot count.
    """
    user = a_user()
    event = a_personal_event(user)

    # The first read creates the notification preference row; it is not part of the
    # steady-state cost.
    read_plan(user_id=user.pk, target_kind="personal_event", target_id=event.id)

    with CaptureQueriesContext(connections[PERSONAL]) as one_slot:
        read_plan(user_id=user.pk, target_kind="personal_event", target_id=event.id)
    one_count = len(one_slot.captured_queries)

    from apps.delivery.services.reminder_plans import save_plan_slots
    from apps.delivery.services.scheduled_sends import SendTarget

    save_plan_slots(
        user_id=user.pk,
        target_kind="personal_event",
        target_id=event.id,
        slots=("5d", "2d", "1d", "1hr"),
        actor=Actor.user(user.pk),
        now=NOW,
        send_target=SendTarget(
            target_kind="personal_event",
            target_id=event.id,
            start_utc=event.start_utc,
            version=event.version,
        ),
    )

    with CaptureQueriesContext(connections[PERSONAL]) as four_slots:
        read_plan(user_id=user.pk, target_kind="personal_event", target_id=event.id)
    four_count = len(four_slots.captured_queries)

    assert one_count == four_count
