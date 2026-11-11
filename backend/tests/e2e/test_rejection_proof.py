"""An editor rejects a listing, end to end: it leaves the world, and nobody is told.

**Why one file and not six.** The pieces are each tested alone — the trigger, the two
commands, the ten public reads, the ingestion freeze, the propagation. The failures that
matter are in the seams: a reject that hides the event but leaves the reminder, or cancels
the reminder but sends a cancellation email that is a lie. So each journey below is one
user, one event, one editor, driven through the **real** write path.

**The write path is the real one.** `reject_event` is the function the editorial admin
will call; the `0009` trigger refuses a `rejected` boundary without a version bump, so
there is no shortcut that reaches this state. The proof drives the command, drains the
outbox the way the worker does, and runs the real sweep against the memory email adapter —
which is the proof's only window on what actually left the system.

**The clock is frozen.** Every service here takes `now`.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model

from adapters.email.memory import InMemoryEmailAdapter
from apps.delivery.models import ReminderPlan, ScheduledSend, StateChangeNotice
from apps.delivery.services.delivery_messages import renderer_for
from apps.delivery.services.delivery_sweep import sweep_due_sends
from apps.delivery.services.reminder_plans import attach_default_plan, set_plan_slots
from apps.ingestion.models import Event, EventStateChange
from apps.ingestion.services.catalog_read import (
    EventNotFoundError,
    get_public_event,
    get_public_event_by_slug,
    get_public_events,
    list_public_candidates,
    list_public_events,
)
from apps.ingestion.services.editorial_state import reinstate_event, reject_event
from apps.ingestion.services.outbox import reconcile_outbox
from apps.personalization.models import ConflictPair, SavedEvent
from apps.personalization.services.personal_events import create_personal_event
from apps.personalization.services.saved_events import save_event
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import EventFactory, VenueFactory
from tests.personalization.factories import DigestPreferenceFactory
from worker import propagation

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

User = get_user_model()

ZONE = "America/Los_Angeles"
NOW = datetime(2026, 11, 10, 16, 0, tzinfo=UTC)
START_UTC = datetime(2026, 11, 13, 3, 0, tzinfo=UTC)
SWEEP_AT = NOW + timedelta(days=3)
SLOT = "1hr"
EDITOR = Actor.user(uuid4())


def make_user(email: str = "sam@example.test"):
    user = User.objects.create_user(email=email, password="pw")
    DigestPreferenceFactory(
        user_id=user.pk, timezone=ZONE, city="Los Angeles", city_source="choice"
    )
    return user


def make_catalog_event(*, title: str = "Rooftop Cinema") -> Event:
    return EventFactory(
        title=title,
        venue=VenueFactory(city="Los Angeles", venue_fingerprint=f"venue-{title}"),
        start_time_utc=START_UTC,
        end_time_utc=START_UTC + timedelta(hours=2),
        last_seen_at=NOW,
    )


def save_it(user, event: Event):
    """The user saves it and gets a one-slot Reminder Plan, minted against version 1."""
    result = save_event(user_id=user.pk, event_id=event.id, actor=Actor.user(user.pk), now=NOW)
    attach_default_plan(
        user_id=user.pk,
        target_kind=ReminderPlan.TargetKind.SAVED_EVENT,
        target_id=event.id,
        actor=Actor.user(user.pk),
        now=NOW,
    )
    from apps.delivery.services.reminder_plan_read import resolve_target

    set_plan_slots(
        user_id=user.pk,
        target_kind=ReminderPlan.TargetKind.SAVED_EVENT,
        target_id=event.id,
        slots=(SLOT,),
        actor=Actor.user(user.pk),
        now=NOW,
        send_target=resolve_target(user_id=user.pk, target_kind="saved_event", target_id=event.id),
    )
    return result.saved


def drain_the_outbox() -> int:
    """Propagate every unpropagated change, the way the worker's reconciler does."""
    applied = 0
    for change in (
        EventStateChange.objects.using(CATALOG)
        .filter(propagated_at__isnull=True)
        .order_by("event_version")
    ):
        propagation.propagate(state_change_id=change.id, now=NOW)
        applied += 1
    return applied


def run_the_sweep(port, *, now=SWEEP_AT):
    return sweep_due_sends(
        port=port,
        renderer=renderer_for,
        resolve_recipient=lambda user_id: f"{user_id}@example.test",
        now=now,
    )


def pending_reminders(user, event):
    return ScheduledSend.objects.using(PERSONAL).filter(
        user_id=user.pk,
        target_kind="saved_event",
        target_id=event.id,
        status=ScheduledSend.Status.PENDING,
    )


class TestAnEditorRejectsAListing:
    """One journey: a user has saved it, an editor pulls it, nothing false reaches anyone."""

    def test_the_whole_path(self):
        user = make_user()
        event = make_catalog_event()
        saved = save_it(user, event)

        # The world before: it is public, and the user has a reminder waiting.
        items, _ = list_public_events(now=NOW)
        assert [item.id for item in items] == [event.id]
        assert pending_reminders(user, event).count() == 1

        # --- The editor rejects it. ---
        result = reject_event(event_id=event.pk, actor=EDITOR, now=NOW)
        assert result.applied is True

        # The outbox carries exactly one new change: the reject reaches users through
        # the AD-17 path and not through a second mechanism of its own.
        assert reconcile_outbox(now=NOW + timedelta(minutes=10)) == 1
        drain_the_outbox()

        event.refresh_from_db(using=CATALOG)

        # 1. It is never deleted.
        assert Event.objects.using(CATALOG).filter(pk=event.pk).exists()
        assert event.publication_status == Event.PublicationStatus.REJECTED

        # 2. Its lifecycle status is untouched — we never claimed it was cancelled.
        assert event.status == Event.Status.SCHEDULED

        # 3. It is absent from every public read.
        items, total = list_public_events(now=NOW)
        assert items == [] and total == 0
        assert list_public_candidates(now=NOW) == []
        assert get_public_events(event_ids={event.id}) == {}
        with pytest.raises(EventNotFoundError):
            get_public_event(event_id=event.id, now=NOW)
        with pytest.raises(EventNotFoundError):
            get_public_event_by_slug(slug=event.slug)

        # 4. The saver's reminders are cancelled, so nothing false can fire.
        assert pending_reminders(user, event).count() == 0

        # 5. And no email of any kind goes out — not a reminder, not a notice.
        port = InMemoryEmailAdapter()
        counts = run_the_sweep(port)
        assert counts.sent == 0
        assert port.sent == []
        assert not StateChangeNotice.objects.using(PERSONAL).filter(user_id=user.pk).exists()

        # 6. Their save itself is untouched: they chose it, and it stays theirs.
        assert (
            SavedEvent.objects.using(PERSONAL).filter(user_id=user.pk, event_id=event.id).exists()
        )
        assert (
            SavedEvent.objects.using(PERSONAL).get(user_id=user.pk, event_id=event.id).event_version
            == saved.event_version
        )


class TestTheEditorChangesTheirMind:
    """The reversal, and the reason the personal side was left alone."""

    def test_a_reinstated_event_comes_all_the_way_back(self):
        user = make_user()
        event = make_catalog_event()
        save_it(user, event)

        reject_event(event_id=event.pk, actor=EDITOR, now=NOW)
        drain_the_outbox()
        assert pending_reminders(user, event).count() == 0

        reinstate_event(event_id=event.pk, actor=EDITOR, now=NOW)
        drain_the_outbox()

        # Public again...
        items, _ = list_public_events(now=NOW)
        assert [item.id for item in items] == [event.id]
        # ...and the reminder is back, because their Reminder Plan was never deleted.
        assert pending_reminders(user, event).count() == 1
        # ...and still no email either way.
        assert not StateChangeNotice.objects.using(PERSONAL).filter(user_id=user.pk).exists()

    def test_a_conflict_survives_the_round_trip(self):
        """**The AD-17/AD-21 defect, routed around rather than walked into.**

        A cancellation closes conflict pairs, and a closed pair is immutable — so if a
        reject closed them, this clash would be real again after the reinstatement and
        `/conflicts` could never say so. Nothing is closed, so nothing is lost.
        """
        user = make_user()
        event = make_catalog_event()
        create_personal_event(
            user_id=user.pk,
            name="Dinner",
            start_utc=START_UTC + timedelta(hours=1),
            end_utc=START_UTC + timedelta(hours=3),
            start_time_tz=ZONE,
            actor=Actor.user(user.pk),
            now=NOW,
        )
        save_it(user, event)
        pair = ConflictPair.objects.using(PERSONAL).get(user_id=user.pk)
        assert pair.status == ConflictPair.Status.ACTIVE

        reject_event(event_id=event.pk, actor=EDITOR, now=NOW)
        drain_the_outbox()
        reinstate_event(event_id=event.pk, actor=EDITOR, now=NOW)
        drain_the_outbox()

        pair.refresh_from_db(using=PERSONAL)
        assert pair.status == ConflictPair.Status.ACTIVE
