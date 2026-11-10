"""The state-change path, end to end: a venue cancels, and the user's world follows.

**Why one file and not eight.** The point of a proof is that the steps *compose*. Five
work items of this intent were built and each was tested in isolation: the ingestion
outbox, the propagation consumer, the send lifecycle, the notice, and the two in-app
surfaces. The failures that matter live in the seams between them. A chain of
independent tests proves each step and not the whole — a send cancelled in one test and
a notice raised in another are two events, not one user's evening.

So each journey below is one test, one user, one database, and one transaction's worth of
shared state, driven through the **real** write path.

**The write path is the real one.** A cancellation is not made by writing a row: the
`catalog.guard_event_write` trigger refuses a status change without a version bump, so
the *only* way a cancellation happens is `ingestion.services.event_writes.apply_lifecycle_change`
— which appends the `EventStateChange`, bumps the catalog's version, and enqueues the
propagation. **The proof drives that function**, so the `EventStateChange` the test
asserts on is the one the pipeline would have written, with the version the pipeline
would have given it, and the enqueue is the one the pipeline would have made.

**The version is the spine, and every journey asserts one.** AD-17 gates every consumer
on `EventStateChange.event_version`: the save's snapshot, the send's `event_version`, the
notice's `event_version`. A proof that asserted only *existence* would pass against a
propagation that applied the wrong version to the wrong rows. So each journey names the
version it expects and finds it on the row — not merely "a row exists".

**The clock is frozen, never slept.** Every service on this path takes `now` as an
argument, so the proof passes its own instant and never reads the wall clock. Nothing in
this file sleeps, and nothing waits for a timer.

**What is proved here is the end state.** The assertion surface is the rows the
`personal` schema holds and the messages the memory email adapter recorded — not the
service functions behind them. The unit tests assert each service's own contract; this
asserts the *composition*, which is the only place the whole path is visible at once.

**The hold-and-release journey is first, and it is first on purpose.** It is the one
race that no unit test can prove alone: a send claimed by the sweep *while* its event is
mid-change. The staging it needs — a claim that has already happened, a catalog version
that has already moved — shapes how the other journeys are staged, so it is written
first and the rest follow its conventions.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q

from adapters.email.memory import InMemoryEmailAdapter
from apps.delivery.models import ReminderPlan, ScheduledSend, StateChangeNotice
from apps.delivery.services.delivery_messages import renderer_for
from apps.delivery.services.delivery_sweep import claim_due_sends, hold_stale_sends, sweep_due_sends
from apps.delivery.services.mutes import mute_event_notices
from apps.delivery.services.reminder_plans import attach_default_plan, set_plan_slots
from apps.delivery.services.scheduled_sends import SendTarget, mint_for_plan
from apps.ingestion.models import Event, EventStateChange
from apps.ingestion.services.event_writes import IncomingEvent, apply_lifecycle_change
from apps.ingestion.services.outbox import reconcile_outbox
from apps.personalization.models import ConflictPair, SavedEvent
from apps.personalization.services.personal_events import create_personal_event
from apps.personalization.services.saved_events import save_event
from domain.lifecycle import Change, ChangeKind, EventStatus
from ports.email import Stream
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from tests.e2e.public_pages_fixtures import incoming_for
from tests.ingestion.factories import EventFactory, VenueFactory
from tests.personalization.factories import DigestPreferenceFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

User = get_user_model()

#: The zone the user's days are cut in.
ZONE = "America/Los_Angeles"

#: The instant the journeys act. 2026-11-10 16:00 UTC is 08:00 in Los Angeles (PST).
#:
#: **Frozen, and it has to be a fixed instant rather than "now".** Two reads bound by
#: the wall clock — `get_public_event(event_id, now=...)` and the Detail endpoint — and
#: a proof whose answer depended on the hour it ran would be a flaky proof. The
#: services on this path all take `now` as an argument; the two that do not are read
#: through HTTP, and the HTTP journeys use an event far enough ahead that the wall
#: clock cannot overtake it.
NOW = datetime(2026, 11, 10, 16, 0, tzinfo=UTC)

#: The event's start: 2026-11-12 19:00 in Los Angeles — 2026-11-13 03:00 UTC.
#:
#: **Two days out, on purpose.** The `1hr` slot is due at 18:00 local on the 12th, so
#: a reminder minted at `NOW` is not yet due and the sweep has nothing to claim until
#: `SWEEP_AT` — which is what lets the hold-and-release journey stage a *claim* before
#: the catalog moves. A reminder that were not yet due would never be claimed and the
#: race would not exist.
#:
#: **And two days past the wall clock**, so the Detail endpoint's `now`-bounded read
#: still finds the event however long after the suite was written it is run.
START_UTC = datetime(2026, 11, 13, 3, 0, tzinfo=UTC)
END_UTC = START_UTC + timedelta(hours=2)

#: The event's start after a postponement: two days later, same local time.
MOVED_START_UTC = START_UTC + timedelta(days=2)
MOVED_END_UTC = MOVED_START_UTC + timedelta(hours=2)

#: The actor every write in this file is attributed to.
ACTOR = Actor.system("e2e_proof")

#: The slot the journeys mint against. **`1hr` and nothing else**, because a second slot
#: would double every count and make "one reminder" ambiguous.
SLOT = "1hr"

#: The instant the sweep runs at. **After the reminder's due time.**
#:
#: The `1hr` slot for an event starting at 03:00 UTC on the 13th is due at 02:00 UTC on
#: the 13th, and the sweep's claim filters on `due_at <= now` — so the claim must happen
#: at or after that. `NOW + 3 days` clears it with room to spare, and it is a *fixed*
#: instant so the proof never depends on when the suite ran.
SWEEP_AT = NOW + timedelta(days=3)


# ── The scaffolding ─────────────────────────────────────────────────────────────────────


def make_user(email: str = "sam@example.test"):
    """A real user with a real pk, a zone, and a city.

    **The zone is the point.** The daily cap is the user's *local* day, and a notice's
    `local_date` is read in the user's zone — so a proof without one would be measuring
    the cap against the wrong day.
    """
    user = User.objects.create_user(email=email, password="pw")
    DigestPreferenceFactory(
        user_id=user.pk, timezone=ZONE, city="Los Angeles", city_source="choice"
    )
    return user


def make_catalog_event(*, start_utc: datetime = START_UTC, title: str = "Brooklyn Tech Meetup"):
    """A published, upcoming catalog event at version 1.

    **`last_seen_at` is pinned to `NOW`.** FR-14's staleness bound is measured from it
    against the test's clock, and the column's default is the wall clock — so an event
    built with the default would be days stale against a `NOW` in the future, and the
    catalog read would drop it before the save ever saw it.
    """
    return EventFactory(
        title=title,
        venue=VenueFactory(city="Los Angeles", venue_fingerprint=f"venue-{title}"),
        start_time_utc=start_utc,
        end_time_utc=start_utc + timedelta(hours=2),
        last_seen_at=NOW,
    )


def save_it(user, event: Event):
    """The user saves the catalog event, with a one-slot Reminder Plan attached.

    **The plan is attached by the journey, not by the save.** `save_event` attaches none
    (a save with no plan is the ordinary case, and `propagation` copes with it), so a
    journey that wants a re-minted reminder has to give the event one.

    **One slot, and the default is two.** `DEFAULT_REMINDER_PLAN` is `(1d, 1hr)` — two
    reminders per event — and every count in this file says "one reminder". A two-slot
    plan would make "one" ambiguous: a re-mint would produce two fresh rows, and "the
    old row and the new one" would become "the old row and the two new ones". So the
    plan is narrowed to the `1hr` slot immediately, before anything is minted.
    """
    result = save_event(user_id=user.pk, event_id=event.id, actor=Actor.user(user.pk), now=NOW)
    attach_default_plan(
        user_id=user.pk,
        target_kind=ReminderPlan.TargetKind.SAVED_EVENT,
        target_id=event.id,
        actor=Actor.user(user.pk),
        now=NOW,
    )
    # **The plan is narrowed with the plan's own published command**, not by writing the
    # row. **No `send_target` is passed**, so the resync mints nothing — the journeys
    # mint their reminders explicitly, at the instant they mean to, and a mint that
    # happened here would spend the send key before the journey had a chance to stage
    # the race.
    set_plan_slots(
        user_id=user.pk,
        target_kind=ReminderPlan.TargetKind.SAVED_EVENT,
        target_id=event.id,
        slots=(SLOT,),
        actor=Actor.user(user.pk),
        now=NOW,
    )
    return result.saved


def target_for(event: Event, saved, *, version: int = 1) -> SendTarget:
    """The `SendTarget` the user's reminders for this save are minted against.

    **`target_id` is the catalog event's id** — the tree's convention, the same one
    `reminder_plan_read.resolve_target` uses — and `catalog_event_id` names the same
    event, because the send key is minted from it.
    """
    return SendTarget(
        target_kind=ReminderPlan.TargetKind.SAVED_EVENT,
        target_id=event.id,
        start_utc=saved.start_utc,
        version=version,
        catalog_event_id=event.id,
    )


def mint_one_reminder(user, event: Event, saved) -> ScheduledSend:
    """Mint the user's one reminder for this event, against version 1.

    **The row is not due yet at `NOW`.** The `1hr` slot for an event starting at 03:00
    UTC on the 13th is due at 02:00 UTC on the 13th, and `NOW` is 16:00 UTC on the 10th —
    so the sweep has nothing to claim until `SWEEP_AT`. `mint_for_plan` does not care
    whether a row is due yet; the sweep is what reads the due time, and the journeys
    that need a claim call it at `SWEEP_AT`.
    """
    minted = mint_for_plan(
        user_id=user.pk,
        target=target_for(event, saved),
        slots=(SLOT,),
        actor=ACTOR,
        now=NOW,
    )
    assert minted == 1, "one slot, one reminder"
    return reminder_sends(user)[0]


def reminder_sends(user) -> list[ScheduledSend]:
    """This user's *reminder* rows — the ones for a saved event, not the notices.

    **The two kinds are told apart deliberately.** A state notice is also a
    `ScheduledSend` on this user's rows, and a journey that counts "the rows" without
    saying which kind it means would count the notice as a reminder.
    """
    return list(
        ScheduledSend.objects.using(PERSONAL)
        .filter(user_id=user.pk, kind=ScheduledSend.Kind.EVENT_REMINDER)
        .order_by("created_at", "id")
    )


def notice_sends(user) -> list[ScheduledSend]:
    """This user's *state-notice* rows."""
    return list(
        ScheduledSend.objects.using(PERSONAL)
        .filter(user_id=user.pk, kind=ScheduledSend.Kind.STATE_NOTICE)
        .order_by("created_at", "id")
    )


def notices(user) -> list[StateChangeNotice]:
    """This user's raised notices, newest first."""
    return list(
        StateChangeNotice.objects.using(PERSONAL)
        .filter(user_id=user.pk)
        .order_by("-created_at", "-id")
    )


def saved_row(user, event: Event) -> SavedEvent:
    """The user's snapshot row for this event."""
    return SavedEvent.objects.using(PERSONAL).get(user_id=user.pk, event_id=event.id)


def change_the_catalog(event: Event, *, kinds, fields, incoming_overrides=None, now=NOW):
    """Apply a lifecycle change to the catalog event, through the real write path.

    **This is the ingestion half of every journey.** `apply_lifecycle_change` is what
    the ingest pipeline calls, and it is the only thing that can move an event's status
    or version: the `catalog.guard_event_write` trigger refuses any other write. So a
    proof that drove the catalog any other way would be proving a state the database
    does not permit.

    It returns the `EventStateChange` rows it appended — one per kind, in precedence
    order, with the versions the pipeline gave them.
    """
    incoming: IncomingEvent = incoming_for(event, **(incoming_overrides or {}))
    with transaction.atomic(using=CATALOG):
        rows = apply_lifecycle_change(
            event=event,
            incoming=incoming,
            change=Change(kinds=tuple(kinds), fields=frozenset(fields), is_lifecycle=True),
            actor=ACTOR,
            now=now,
        )
    event.refresh_from_db(using=CATALOG)
    return rows


def cancel_it(event: Event, *, now=NOW) -> EventStateChange:
    """Cancel the event upstream. The one change every cancellation journey shares."""
    rows = change_the_catalog(
        event,
        kinds=(ChangeKind.CANCELLED,),
        fields={"status"},
        incoming_overrides={"status": EventStatus.CANCELLED},
        now=now,
    )
    return rows[0]


def postpone_it(event: Event, *, now=NOW) -> EventStateChange:
    """Move the event two days later, and postpone it."""
    rows = change_the_catalog(
        event,
        kinds=(ChangeKind.POSTPONED,),
        fields={"status", "start_utc", "end_utc"},
        incoming_overrides={
            "status": EventStatus.POSTPONED,
            "start_utc": MOVED_START_UTC,
            "end_utc": MOVED_END_UTC,
            "start_time_local": MOVED_START_UTC.astimezone(
                __import__("zoneinfo").ZoneInfo(ZONE)
            ).strftime("%Y-%m-%dT%H:%M:%S"),
        },
        now=now,
    )
    return rows[0]


def sell_it_out(event: Event, *, now=NOW) -> EventStateChange:
    """Mark the event sold out. **The event still happens** — that is the whole point."""
    rows = change_the_catalog(
        event,
        kinds=(ChangeKind.SOLD_OUT,),
        fields={"is_sold_out"},
        incoming_overrides={"is_sold_out": True},
        now=now,
    )
    return rows[0]


def reinstate_it(event: Event, *, now=NOW) -> EventStateChange:
    """Bring a cancelled event back, at the time it was already at."""
    rows = change_the_catalog(
        event,
        kinds=(ChangeKind.REINSTATED,),
        fields={"status"},
        incoming_overrides={"status": EventStatus.SCHEDULED},
        now=now,
    )
    return rows[0]


def run_the_sweep(port, *, now=NOW):
    """Run the real sweep against the memory adapter, and return its counts.

    **The sweep is the real one** — `delivery_sweep.sweep_due_sends`, the same function
    the worker task calls. Only the port is swapped, and the swap is how the proof sees
    what left the system.
    """
    return sweep_due_sends(
        port=port,
        renderer=renderer_for,
        resolve_recipient=lambda user_id: f"{user_id}@example.test",
        now=now,
    )


def save_conflict(user, event: Event) -> ConflictPair:
    """A personal event that overlaps the saved one, so the pair exists.

    **The overlap is an hour**, so the personal event starts *inside* the saved event's
    window — the pair is a genuine conflict and not a touching-ends adjacency.

    **The pair's two sides are found by either side, not by position.** `conflicts.
    _normalise` orders them lexicographically on `(kind, id)`, so which side is `left`
    and which is `right` depends on the ids — a helper that assumed a position would
    find nothing half the time.
    """
    personal = create_personal_event(
        user_id=user.pk,
        name="Dinner with Priya",
        start_utc=START_UTC + timedelta(hours=1),
        end_utc=START_UTC + timedelta(hours=3),
        start_time_tz=ZONE,
        actor=Actor.user(user.pk),
        now=NOW,
    )
    pair = (
        ConflictPair.objects.using(PERSONAL)
        .filter(user_id=user.pk, status=ConflictPair.Status.ACTIVE)
        .filter(
            Q(left_kind=ConflictPair.SideKind.PERSONAL_EVENT, left_id=personal.event.id)
            | Q(right_kind=ConflictPair.SideKind.PERSONAL_EVENT, right_id=personal.event.id)
        )
        .first()
    )
    assert pair is not None, "the overlap produced a pair"
    return pair


# ── The hold-and-release journey ────────────────────────────────────────────────────────


class TestTheHoldAndRelease:
    """**The race AD-17 exists for, and the one no unit test can prove alone.**

    The sweep claims a send. *Then* the catalog moves ahead of it. The claimed send must
    be **held, not sent** — and propagation must **release** it.

    **Why the order matters and cannot be reversed.** The sweep's guard reads the
    catalog's version *after* the claim has committed, and holds the row when the
    catalog has moved past the version the row was minted against. If the catalog moves
    *before* the claim, the row is stale in a different way and the propagation's own
    version gate handles it — a different branch, a different test. The claim-then-move
    order is the one where a send would otherwise go out for an event that had already
    changed, and it is the one the AD names.

    **The hold is not a cancellation.** A held row is still `pending` — deliberately, so
    every other writer in `scheduled_sends` keeps seeing it — and it carries a
    `held_at`. The claim excludes it (`held_at__isnull=True`), so the next sweep leaves
    it alone until propagation clears the hold.
    """

    def test_a_claimed_send_for_a_mid_change_event_is_held_and_not_sent(self):
        """**The send does not go out, and the row says why.**

        The claim happens first; the catalog moves second; the sweep's guard sees the
        newer catalog version and holds the row. **Nothing reaches the adapter.**
        """
        user = make_user()
        event = make_catalog_event()
        saved = save_it(user, event)
        row = mint_one_reminder(user, event, saved)

        # ── The claim ────────────────────────────────────────────────────────────────
        # The sweep's claim is the real one. `claim_due_sends` filters on `due_at <=
        # now`, so the instant it is called at must be past the reminder's due time.
        claimed = claim_due_sends(now=SWEEP_AT)
        assert row.id in claimed, "the due reminder was claimed"

        # ── The catalog moves ────────────────────────────────────────────────────────
        # **After the claim.** This is the whole race: the sweep has already taken the
        # row, and now the world moves under it.
        sell_it_out(event)

        # ── The guard ────────────────────────────────────────────────────────────────
        # The sweep's guard, run against the claimed ids exactly as the sweep runs it.
        still_sendable, held_count = hold_stale_sends(send_ids=claimed, now=SWEEP_AT)

        assert held_count == 1, "the send was held"
        assert still_sendable == [], "nothing was left sendable"

        row.refresh_from_db()
        assert row.status == ScheduledSend.Status.PENDING, "a hold is not a cancellation"
        assert row.held_at is not None, "the row carries the hold"
        assert row.claimed_at is None, "the claim was released with the hold"

        # **And nothing went out.** The adapter is the proof's window on the world.
        port = InMemoryEmailAdapter()
        counts = run_the_sweep(port, now=SWEEP_AT)

        assert counts.sent == 0
        assert port.sent == [], "a held send is not sent"

    def test_the_hold_excludes_the_row_from_the_next_claim(self):
        """**A held row is not claimable again.** The claim filters on `held_at IS NULL`,
        and a held row is not null — so the next sweep cannot pick it up and send it
        while it is waiting for propagation.

        This is asserted through the *claim*, not through the sweep, because the claim
        is where the exclusion lives: a sweep that found nothing to claim would prove
        the same thing less directly.
        """
        user = make_user()
        event = make_catalog_event()
        saved = save_it(user, event)
        row = mint_one_reminder(user, event, saved)

        claimed = claim_due_sends(now=SWEEP_AT)
        assert row.id in claimed

        sell_it_out(event)
        _, held_count = hold_stale_sends(send_ids=claimed, now=SWEEP_AT)
        assert held_count == 1

        # **The next claim finds nothing.** The row is held, so it is not claimable —
        # and this is the assertion that would fail if the hold were only a marker and
        # not an exclusion.
        again = claim_due_sends(now=SWEEP_AT + timedelta(days=1))

        assert row.id not in again, "a held row is not claimable again"
        assert again == [], "and it was the only row"

    def test_propagation_releases_the_hold_and_the_next_sweep_sends_it(self):
        """**The hold's only exit is propagation.** A `sold_out` is `KEEP`, so the
        propagation re-stamps the row's version and clears `held_at` — and the next
        sweep claims it and sends it.

        **This is the half that makes the hold safe.** A hold that nothing releases
        would strand the user's reminder forever, and the worker's stuck-hold alarm
        would fire over a condition propagation can fix. The release is asserted on
        the row (`held_at` is null) *and* on the world (the mail went out).
        """
        user = make_user()
        event = make_catalog_event()
        saved = save_it(user, event)
        row = mint_one_reminder(user, event, saved)

        claimed = claim_due_sends(now=SWEEP_AT)
        assert row.id in claimed

        change = sell_it_out(event)
        _, held_count = hold_stale_sends(send_ids=claimed, now=SWEEP_AT)
        assert held_count == 1

        # ── The propagation ──────────────────────────────────────────────────────────
        from worker.propagation import propagate

        result = propagate(state_change_id=change.id, now=SWEEP_AT)

        assert result.failed == 0, "the propagation did not fail"
        assert result.marked is True, "the change is marked propagated"

        row.refresh_from_db()
        assert row.held_at is None, "propagation released the hold"
        assert row.status == ScheduledSend.Status.PENDING, "and the row is still pending"
        assert row.event_version == change.event_version, "re-stamped to the new version"

        # ── The world ────────────────────────────────────────────────────────────────
        # **The count is two, and both are wanted**: the released reminder *and* the
        # notice the `sold_out` raised. The assertion is therefore on the *keys*, not
        # on a total — a total would be a claim about how many things the system did,
        # and this journey's claim is about which one went out.
        port = InMemoryEmailAdapter()
        counts = run_the_sweep(port, now=SWEEP_AT + timedelta(days=1))

        keys = [message.idempotency_key for message in port.sent]
        assert row.send_key in keys, "the released reminder goes out, under the same key"
        assert counts.sent == 2, "the reminder and the sold-out notice"

        reminder = next(message for message in port.sent if message.idempotency_key == row.send_key)
        assert reminder.stream is Stream.TRANSACTIONAL

    def test_a_cancellation_cancels_the_held_row_rather_than_releasing_it(self):
        """**`CANCEL` does not release a hold — it cancels the row.**

        A cancelled event's reminder must not go out *at all*, so the `CANCEL` branch
        of `apply_lifecycle_change` cancels the stale row rather than re-stamping it.
        The held row is stale (its version is below the change's), so it is cancelled
        with everything else — and no mail is sent, then or later.

        **The two branches are told apart here.** `KEEP` releases, `CANCEL` terminates,
        and a proof that only exercised `KEEP` would not notice a `CANCEL` that
        mistakenly re-stamped.
        """
        user = make_user()
        event = make_catalog_event()
        saved = save_it(user, event)
        row = mint_one_reminder(user, event, saved)

        claimed = claim_due_sends(now=SWEEP_AT)
        assert row.id in claimed

        change = cancel_it(event)
        _, held_count = hold_stale_sends(send_ids=claimed, now=SWEEP_AT)
        assert held_count == 1

        from worker.propagation import propagate

        result = propagate(state_change_id=change.id, now=SWEEP_AT)
        assert result.failed == 0

        row.refresh_from_db()
        assert row.status == ScheduledSend.Status.CANCELLED, "a cancelled event's send is cancelled"

        # **The hold's marker is still on the row, and that is harmless — deliberately.**
        #
        # `apply_lifecycle_change`'s `CANCEL` branch sets `status = CANCELLED` and does
        # not touch `held_at`. The `KEEP` branch clears it, because that row survives and
        # must become claimable again; a cancelled row never becomes claimable, so
        # clearing the marker would be work for no reader.
        #
        # **Two readers could have been misled by a stale marker, and neither can be.**
        # The claim filters on `status = PENDING` *and* `held_at IS NULL`, so a cancelled
        # row is excluded by its status whatever its marker says. And `count_stuck_holds`
        # filters on `status = PENDING` too, so the stuck-hold alarm cannot fire over a
        # cancelled row. The marker is inert on a terminal row.
        #
        # **The assertion is that the row is inert, not that the marker is gone** — a
        # proof that demanded the marker be cleared would be demanding a behaviour the
        # code does not promise, and would fail for a reason no user would ever see.
        assert row.held_at is not None, "the marker stays, and is inert on a terminal row"

        port = InMemoryEmailAdapter()
        run_the_sweep(port, now=SWEEP_AT + timedelta(days=1))

        # **The reminder is not what went out.** The *notice* is — a cancellation is
        # terminal, and FR-55 has already pulled the event out of the digest, so the mail
        # saying so is the only channel left. The assertion is on the reminder's key,
        # because "the reminder did not go out" is the claim; a total would also be a
        # claim about the notice, which is a different journey's business.
        keys = [message.idempotency_key for message in port.sent]
        assert row.send_key not in keys, "a cancelled event's reminder never goes out"

        # **And it cannot be claimed, so it cannot be resurrected by a later sweep.**
        assert claim_due_sends(now=SWEEP_AT + timedelta(days=2)) == []


# ── The cancellation journey ───────────────────────────────────────────────────────────


class TestTheCancellationJourney:
    """**The whole intent, in one path.**

    The chain: a published event, a user who saved it, a pending reminder, a venue that
    cancels upstream, a re-ingest that records the change, the propagation, the cancelled
    send, the closed conflict, the card's status, and one notice in the strip and one
    email. **Asserted end to end, not per step.**

    **The order in the assertions is the order of the journey**, and the journey is the
    one a user's evening actually takes: the world changes, the reminders stop, the
    conflict stops asking, the card says so, and the user is told once.

    **Each seam is asserted on the version.** The snapshot, the send and the notice all
    carry the change's `event_version`, and each assertion names it — so a propagation
    that applied the right *effects* to the wrong *version* would fail here.
    """

    def test_a_cancelled_event_stops_the_reminder_closes_the_conflict_and_tells_the_user_once(
        self,
    ):
        """**The cancellation, end to end.**"""
        user = make_user()
        event = make_catalog_event()
        saved = save_it(user, event)
        row = mint_one_reminder(user, event, saved)
        pair = save_conflict(user, event)

        # ── The world changes ───────────────────────────────────────────────────────
        change = cancel_it(event)

        assert change.kind == ChangeKind.CANCELLED.value
        assert change.event_version == 2, "the cancellation is version 2"

        # ── The propagation ──────────────────────────────────────────────────────────
        from worker.propagation import propagate

        result = propagate(state_change_id=change.id, now=NOW)

        assert result.failed == 0, "the propagation did not fail"
        assert result.users == 1, "one saver"
        assert result.applied == 1, "one saver applied"
        assert result.marked is True, "and the change is marked propagated"

        # **The change is marked on the row itself**, not only in the result — that is
        # what the reconciler reads to decide whether to offer it again.
        change.refresh_from_db(using=CATALOG)
        assert change.propagated_at is not None, "the row says it was propagated"

        # ── The reminders stop ──────────────────────────────────────────────────────
        row.refresh_from_db()
        assert row.status == ScheduledSend.Status.CANCELLED, "the pending reminder is cancelled"

        # **The cancelled row keeps the version it was minted against.** Only the `KEEP`
        # branch re-stamps a row — a `CANCEL` terminates it, and a terminated row records
        # the version that was current when it was minted, which is the fact the row is
        # for. Re-stamping it would say "this reminder was planned against version 2",
        # which was never true.
        assert row.event_version == 1, "the cancelled row keeps the version it was minted at"

        # **And no new one was minted.** A cancelled event has no reminder to re-mint,
        # and a proof that only counted the cancelled row would miss a stray second one.
        assert len(reminder_sends(user)) == 1, "one row, and it is the cancelled one"

        # ── The conflict closes ─────────────────────────────────────────────────────
        pair.refresh_from_db(using=PERSONAL)
        assert pair.status == ConflictPair.Status.CLEARED_BY_STATE_CHANGE, (
            "the pair closes as cleared by the state change, not as a user resolution"
        )
        assert pair.resolution is None, "and nobody answered it"

        # ── The snapshot carries the version ────────────────────────────────────────
        snapshot = saved_row(user, event)
        assert snapshot.event_version == change.event_version, (
            "the save's snapshot carries the change's version"
        )

        # ── The user is told once ───────────────────────────────────────────────────
        raised = notices(user)
        assert len(raised) == 1, "exactly one notice — FR-54's 'one calm correction'"
        assert raised[0].change_kind == ChangeKind.CANCELLED.value
        assert raised[0].event_version == change.event_version, "carrying the change's version"

        # **One email, on the transactional stream, with no unsubscribe URL.**
        # AD-20 requires an unsubscribe URL on the *bulk* stream only; a state notice is
        # a one-time correction about a record the user made themselves.
        port = InMemoryEmailAdapter()
        run_the_sweep(port, now=SWEEP_AT)

        notice_mails = [
            message for message in port.sent if message.idempotency_key.endswith(str(change.id))
        ]
        assert len(notice_mails) == 1, "one email about the cancellation"
        assert notice_mails[0].stream is Stream.TRANSACTIONAL
        assert "EventPulse24:" in notice_mails[0].message.subject, "the PRD's subject prefix"

        # **And the reminder itself did not go out.** The two keys are told apart: one
        # is the reminder's, one is the notice's, and only the notice went.
        keys = [message.idempotency_key for message in port.sent]
        assert row.send_key not in keys, "the cancelled reminder never went out"

    def test_the_cancelled_event_leaves_the_digest_with_a_cancelled_card(self):
        """**The card says so.** The card's status is a *live* read of the catalog, so a
        card composed before the cancellation still says `cancelled` — AD-10's rule that
        digest rows are served as stored, with the catalog's current facts joined on.

        **The card is composed before the cancellation, on purpose.** That is the case
        that would break: a digest written yesterday, read today, about an event that has
        since been cancelled. A card composed *after* the cancellation would be dropped
        by the candidate stage, and would prove nothing about the join.
        """
        user = make_user()
        event = make_catalog_event()
        save_it(user, event)

        from apps.personalization.services.digest_composition import compose_digest

        composed = compose_digest(user_id=user.pk, actor=ACTOR, now=NOW)
        assert composed.is_empty is False, "the event placed in the digest"

        cancel_it(event)

        from worker.propagation import propagate

        change = (
            EventStateChange.objects.using(CATALOG)
            .filter(event=event, kind=ChangeKind.CANCELLED.value)
            .first()
        )
        assert change is not None
        propagate(state_change_id=change.id, now=NOW)

        from apps.personalization.services.digest_read import read_digest

        digest = read_digest(user_id=user.pk, now=NOW)

        assert digest.status == "composed", "the digest is still there"
        assert len(digest.cards) == 1, "and the card is still on it"

        card = digest.cards[0]
        assert card.status == "cancelled", "the card says the event is cancelled"
        assert card.catalog_event_missing is False, "the catalog still holds the event"

    def test_a_cancellation_with_no_savers_propagates_immediately(self):
        """**A change nobody is affected by is still propagated.**

        The common case is an unsaved event, and the propagation must mark it rather
        than churning the outbox forever — the reconciler has no attempts counter to
        retire a poisoned change with, because `EventStateChange` is append-only.
        """
        event = make_catalog_event()
        change = cancel_it(event)

        from worker.propagation import propagate

        result = propagate(state_change_id=change.id, now=NOW)

        assert result.users == 0, "nobody saved it"
        assert result.applied == 0
        assert result.failed == 0
        assert result.marked is True, "and it is marked propagated anyway"

        change.refresh_from_db(using=CATALOG)
        assert change.propagated_at is not None


# ── The postponement journey ───────────────────────────────────────────────────────────


class TestThePostponementJourney:
    """**The event moves, and the user's world moves with it.**

    A postponement is `REMINT`: the stale reminder is cancelled and a fresh one is
    minted against the new version and the new time. **And the save's snapshot moves**,
    because the snapshot stores the time the user planned around.

    **The overlapping pair is the interesting part.** A postponement that creates a *new*
    overlap must surface it — as the calm Detail notice, not the FR-58 forced prompt.
    The two are different things: FR-58's prompt interrupts, the Detail notice does not.
    """

    def test_a_postponement_re_mints_the_reminder_against_the_new_time(self):
        """**The stale reminder is cancelled and a fresh one is minted.**"""
        user = make_user()
        event = make_catalog_event()
        saved = save_it(user, event)
        row = mint_one_reminder(user, event, saved)

        change = postpone_it(event)

        from worker.propagation import propagate

        result = propagate(state_change_id=change.id, now=NOW)
        assert result.failed == 0

        # **The old row is cancelled, not deleted** — the record of what was supposed to
        # happen survives (AD-7's `CANCELLED`).
        row.refresh_from_db()
        assert row.status == ScheduledSend.Status.CANCELLED, "the stale reminder is cancelled"

        # **And a new one is minted**, against the new version and the new time.
        rows = reminder_sends(user)
        assert len(rows) == 2, "the old row and the new one"
        fresh = next(r for r in rows if r.status == ScheduledSend.Status.PENDING)
        assert fresh.event_version == change.event_version, "the new one carries the new version"
        assert fresh.send_key != row.send_key, "and a new key"
        assert f":{change.event_version}" in fresh.send_key, "the version is in the key"

        # **The snapshot moved too.** The user's plan was made around the old time.
        snapshot = saved_row(user, event)
        assert snapshot.event_version == change.event_version
        assert snapshot.start_utc == MOVED_START_UTC, "the snapshot carries the new time"

    def test_a_postponement_raises_the_calm_detail_notice(self):
        """**The user is told, once, and the notice names the new time.**

        FR-54's subject for a postponement is *"EventPulse24: {event name} was moved to
        {new date}"* — and the new date is the change's own `after`, not the live Event.
        """
        user = make_user()
        event = make_catalog_event()
        save_it(user, event)

        change = postpone_it(event)

        from worker.propagation import propagate

        result = propagate(state_change_id=change.id, now=NOW)
        assert result.failed == 0

        raised = notices(user)
        assert len(raised) == 1, "one notice"
        assert raised[0].change_kind == ChangeKind.POSTPONED.value

        # **The mail carries the PRD's subject.**
        port = InMemoryEmailAdapter()
        run_the_sweep(port, now=SWEEP_AT)

        subject = port.sent[0].message.subject
        assert subject.startswith("EventPulse24: "), subject
        assert "was moved to" in subject, subject

    def test_a_postponement_that_creates_a_new_overlap_surfaces_it_calmly(self):
        """**A newly-created overlap is a Detail notice, not the FR-58 forced prompt.**

        The postponement moved the saved event two days later — *onto* the user's
        personal event, which was originally the day before. The pair that did not
        exist before now exists, and the user must learn about it.

        **The point is what the overlap surfaces as.** FR-58's forced prompt is the
        thing that interrupts; the state-change notice is the calm correction. A
        postponement is a *change the user did not make*, so the calm one is right.
        """
        user = make_user()
        event = make_catalog_event()
        save_it(user, event)

        # **A personal event on the day the event is moving to.**
        from apps.personalization.services.personal_events import create_personal_event

        create_personal_event(
            user_id=user.pk,
            name="Dentist",
            start_utc=MOVED_START_UTC + timedelta(hours=1),
            end_utc=MOVED_START_UTC + timedelta(hours=3),
            start_time_tz=ZONE,
            actor=Actor.user(user.pk),
            now=NOW,
        )

        # **No pair before the move** — the personal event is two days away from the
        # saved one, so the two do not overlap.
        before = (
            ConflictPair.objects.using(PERSONAL)
            .filter(user_id=user.pk, status=ConflictPair.Status.ACTIVE)
            .count()
        )
        assert before == 0, "no overlap yet"

        change = postpone_it(event)

        from worker.propagation import propagate

        result = propagate(state_change_id=change.id, now=NOW)
        assert result.failed == 0

        # **A pair exists now.** The snapshot moved, the pairs were re-judged, and the
        # new overlap was detected and recorded.
        after = (
            ConflictPair.objects.using(PERSONAL)
            .filter(user_id=user.pk, status=ConflictPair.Status.ACTIVE)
            .count()
        )
        assert after == 1, "the move created an overlap"

        # **And the user was told once, calmly.** One notice — the state-change one.
        # The pair is there for the conflicts list; the notice is what the Detail
        # screen renders.
        raised = notices(user)
        assert len(raised) == 1
        assert raised[0].change_kind == ChangeKind.POSTPONED.value


# ── The sold-out journey ──────────────────────────────────────────────────────────────


class TestTheSoldOutJourney:
    """**A sold-out event still happens.**

    This is the kind that reads wrong at a glance and is right: a user who saved a
    sold-out event still wants their reminder, because they bought a ticket. So
    `LIFECYCLE_SEND_BEHAVIOUR` maps `sold_out → KEEP` — the sends are kept, only their
    working version is re-stamped.

    **And the badge is on the card and on the Detail screen**, while the "Save Reminder"
    CTA goes away: there is nothing left to save a reminder *for*, because the tickets
    are gone.
    """

    def test_a_sold_out_event_keeps_its_reminder(self):
        """**`KEEP`: the reminder is kept, re-stamped, and still goes out.**"""
        user = make_user()
        event = make_catalog_event()
        saved = save_it(user, event)
        row = mint_one_reminder(user, event, saved)

        change = sell_it_out(event)

        from worker.propagation import propagate

        result = propagate(state_change_id=change.id, now=NOW)
        assert result.failed == 0

        row.refresh_from_db()
        assert row.status == ScheduledSend.Status.PENDING, "a sold-out event still happens"
        assert row.event_version == change.event_version, "the row is re-stamped"

        # **And no new row was minted.** `KEEP` is not `REMINT`: the user's reminder
        # was never wrong, so there is nothing to replace.
        assert len(reminder_sends(user)) == 1, "one row, and it is the original"

        # **The mail goes out.**
        port = InMemoryEmailAdapter()
        run_the_sweep(port, now=SWEEP_AT)

        keys = [message.idempotency_key for message in port.sent]
        assert row.send_key in keys, "the reminder still goes out"

    def test_a_sold_out_event_is_told_once(self):
        """**One notice, and it says the event is sold out.**"""
        user = make_user()
        event = make_catalog_event()
        save_it(user, event)

        change = sell_it_out(event)

        from worker.propagation import propagate

        result = propagate(state_change_id=change.id, now=NOW)
        assert result.failed == 0

        raised = notices(user)
        assert len(raised) == 1
        assert raised[0].change_kind == ChangeKind.SOLD_OUT.value

        port = InMemoryEmailAdapter()
        run_the_sweep(port, now=SWEEP_AT)

        subject = port.sent[0].message.subject
        assert "is sold out" in subject, subject

    def test_a_sold_out_event_shows_the_badge_on_the_card(self):
        """**The card carries the badge.** The `is_sold_out` flag is a live read of the
        catalog, joined onto the card at render time — so a card composed before the
        sell-out still shows it.
        """
        user = make_user()
        event = make_catalog_event()
        save_it(user, event)

        from apps.personalization.services.digest_composition import compose_digest

        compose_digest(user_id=user.pk, actor=ACTOR, now=NOW)

        sell_it_out(event)

        from apps.personalization.services.digest_read import read_digest

        digest = read_digest(user_id=user.pk, now=NOW)

        assert len(digest.cards) == 1
        card = digest.cards[0]
        assert card.is_sold_out is True, "the card carries the sold-out badge"
        assert card.status == "scheduled", "and the event is still scheduled, not cancelled"

    def test_the_snapshot_does_not_move_for_a_sold_out_event(self):
        """**`LIFECYCLE_PERSONAL_BEHAVIOUR` maps `sold_out → NONE`.**

        A sold-out event moved nothing the snapshot stores — no time, no status. So the
        snapshot's version **lags** the catalog's, and that is deliberate: every gate in
        this tree is `>` and not `==`, so a snapshot at v1 that skipped a `sold_out` at v2
        still accepts a `time_moved` at v3.
        """
        user = make_user()
        event = make_catalog_event()
        save_it(user, event)

        change = sell_it_out(event)

        from worker.propagation import propagate

        result = propagate(state_change_id=change.id, now=NOW)
        assert result.failed == 0

        snapshot = saved_row(user, event)
        assert snapshot.event_version == 1, "the snapshot's version did not move"
        assert snapshot.start_utc == START_UTC, "and neither did its time"
        assert change.event_version == 2, "while the catalog's did"


# ── The reinstatement journey ──────────────────────────────────────────────────────────


class TestTheReinstatementJourney:
    """**The event comes back, and the user's world comes back with it.**

    A reinstatement is `REMINT` on the send side and `REINSTATE` on the personal side:
    the reminders are re-minted from the plan that survived, and the save returns to
    live.

    **And the old spent send key does not block the new send.** That is the sharp part.
    AD-7's key is `user · kind · event · slot · version`, so a re-mint against a *new*
    version produces a *new* key — the old one stays spent and the new one is fresh. A
    key that did not include the version would make the re-mint a no-op, and the user's
    reminder would silently never go out again.
    """

    def test_a_reinstated_event_re_mints_the_reminder_from_the_surviving_plan(self):
        """**The reminder comes back, under a new key.**"""
        user = make_user()
        event = make_catalog_event()
        saved = save_it(user, event)
        row = mint_one_reminder(user, event, saved)

        # ── It is cancelled first ────────────────────────────────────────────────────
        cancellation = cancel_it(event)

        from worker.propagation import propagate

        propagate(state_change_id=cancellation.id, now=NOW)

        row.refresh_from_db()
        assert row.status == ScheduledSend.Status.CANCELLED, "the cancellation stopped it"

        # ── And then it comes back ───────────────────────────────────────────────────
        reinstatement = reinstate_it(event)
        assert reinstatement.event_version == 3, "the reinstatement is version 3"

        result = propagate(state_change_id=reinstatement.id, now=NOW)
        assert result.failed == 0

        rows = reminder_sends(user)
        assert len(rows) == 2, "the cancelled row and the new one"

        fresh = next(r for r in rows if r.status == ScheduledSend.Status.PENDING)
        assert fresh is not row
        assert fresh.event_version == reinstatement.event_version, "against the new version"

        # **The old key does not block the new one.** The key carries the version, so
        # the new row's key is a different string — and the old key stays spent.
        assert fresh.send_key != row.send_key, "a new key"
        assert fresh.send_key.endswith(f":{reinstatement.event_version}"), (
            "the version is in the key, which is what makes the re-mint a new row"
        )

        # **And the mail goes out** — under the new key, once.
        port = InMemoryEmailAdapter()
        run_the_sweep(port, now=SWEEP_AT + timedelta(days=3))

        keys = [message.idempotency_key for message in port.sent]
        assert fresh.send_key in keys, "the reinstated reminder goes out"
        assert row.send_key not in keys, "and the cancelled one does not"

    def test_the_save_returns_to_live(self):
        """**The save comes back completely.** `cancel_saved_event` writes no flag, so
        there is none to clear — the row was never marked, and every surface reads the
        catalog, which says `scheduled` again. **What the reinstatement does write is the
        version**, and that is the part that matters: without it a later out-of-order
        change would be gated against the cancellation's version instead of this one.
        """
        user = make_user()
        event = make_catalog_event()
        save_it(user, event)

        cancellation = cancel_it(event)

        from worker.propagation import propagate

        propagate(state_change_id=cancellation.id, now=NOW)

        snapshot = saved_row(user, event)
        assert snapshot.event_version == cancellation.event_version, "the cancellation's version"

        reinstatement = reinstate_it(event)

        result = propagate(state_change_id=reinstatement.id, now=NOW)
        assert result.failed == 0

        snapshot = saved_row(user, event)
        assert snapshot.event_version == reinstatement.event_version, "the reinstatement's version"

        # **And the catalog says the event is live again.**
        event.refresh_from_db(using=CATALOG)
        assert event.status == "scheduled"

    def test_a_reinstatement_raises_a_notice(self):
        """**The user is told the event is back.** FR-54 has a subject for it —
        *"EventPulse24: {event name} is back on."* — even though the PRD names none.

        **The reinstatement is on the next day, and that is the point.** FR-54's cap is
        *one notice per event per local day* — so a cancellation and a reinstatement in
        the same day are competing for one slot, and the cancellation wins (it outranks
        `reinstated` in `PRECEDENCE`). A reinstatement is realistically a later event
        anyway: a venue cancels on Monday and un-cancels on Tuesday.
        """
        user = make_user()
        event = make_catalog_event()
        save_it(user, event)

        cancellation = cancel_it(event)

        from worker.propagation import propagate

        propagate(state_change_id=cancellation.id, now=NOW)

        # **The next day, in the user's own zone.** The cap is on the *local* date, so
        # the instant has to cross midnight in Los Angeles — and it does, because
        # `NOW` is 08:00 local and `NOW + 1 day` is 08:00 local the day after.
        later = NOW + timedelta(days=1)
        reinstatement = reinstate_it(event, now=later)
        propagate(state_change_id=reinstatement.id, now=later)

        raised = notices(user)
        assert len(raised) == 2, "one for the cancellation, one for the reinstatement"
        assert raised[0].change_kind == ChangeKind.REINSTATED.value, "the newest is first"

        port = InMemoryEmailAdapter()
        run_the_sweep(port, now=SWEEP_AT + timedelta(days=3))

        subjects = [message.message.subject for message in port.sent]
        assert any("is back on" in subject for subject in subjects), subjects

    def test_the_daily_cap_keeps_the_second_notice_of_one_day_out(self):
        """**The cap is FR-54's second rule, and it is proved here rather than assumed.**

        One notice per event per local day — *a different rule about different changes*,
        not the same as "never repeats". A cancellation and a reinstatement on the same
        day are two changes about one event, and only one of them is worth an email.

        **The cancellation wins, because it outranks the reinstatement.** `PRECEDENCE`
        is the tree's own ordering, and the cap resolves by it: the more important
        change keeps the slot, and the less important one is refused.
        """
        user = make_user()
        event = make_catalog_event()
        save_it(user, event)

        cancellation = cancel_it(event)

        from worker.propagation import propagate

        propagate(state_change_id=cancellation.id, now=NOW)

        # **The same day.** The cap is on the local date, and this is the same local
        # date — so the reinstatement cannot take a second slot.
        reinstatement = reinstate_it(event)
        result = propagate(state_change_id=reinstatement.id, now=NOW)

        assert result.failed == 0

        raised = notices(user)
        assert len(raised) == 1, "one notice for the day"
        assert raised[0].change_kind == ChangeKind.CANCELLED.value, "and it is the cancellation"

        # **The reinstatement's email was not minted either.** The cap decides *before*
        # minting, so the suppressed change leaves no row behind for a later sweep to
        # find — a notice that was never raised must not leave a pending send.
        assert len(notice_sends(user)) == 1, "one notice email, not two"


# ── The backlog drain ─────────────────────────────────────────────────────────────────


class TestTheBacklogDrain:
    """**A change nobody propagated is propagated anyway.**

    `EventStateChange` is append-only, so a change that was never propagated — the
    worker was down, the broker was down, the job was lost — has no attempts counter to
    retire it with. **The reconciler is the answer**: it re-offers the unpropagated
    changes, and the propagation's own idempotence makes the retry safe.

    **The idempotence is the point.** A change that was *partly* applied — one saver
    done, another not — is re-offered, and the done saver's rows are already at the
    change's version, so the version gates make the second visit a no-op.

    **The backlog predates this intent**, which is the case the work item names: rows
    that were written before the propagation existed at all. Nothing about them is
    special except that they were never propagated, and the reconciler cannot tell the
    difference — which is the point.
    """

    def test_the_reconciler_re_offers_a_change_that_predates_the_intent(self, sent_jobs):
        """**The reconciler offers the backlog, and the propagation drains it.**

        **`sent_jobs` is the outbox seam** — `apps/ingestion/services/outbox._send` —
        so the proof sees what would have gone to the broker without reaching it.
        """
        user = make_user()
        event = make_catalog_event()
        save_it(user, event)

        # ── The backlog ─────────────────────────────────────────────────────────────
        # **A change written before the propagation existed.** `occurred_at` is in the
        # past — well past `OUTBOX_RECONCILE_AFTER` — so the reconciler sees it.
        change = cancel_it(event, now=NOW - timedelta(hours=2))

        from apps.ingestion.models import EventStateChange as _Change

        stale = _Change.objects.using(CATALOG).get(pk=change.id)
        assert stale.propagated_at is None, "it was never propagated"
        assert stale.occurred_at < NOW, "and it is old"

        # ── The reconciler ──────────────────────────────────────────────────────────

        offered = reconcile_outbox(now=NOW)

        assert offered == 1, "the backlog was offered"

        # **And it was offered by task name, with the change's id as the argument.**
        # The seam records `(task_name, args)`, and the assertion is on the two things
        # that matter — the name the worker registers the task under, and the id it was
        # asked to propagate — rather than on the recorder's own tuple shape.
        assert len(sent_jobs) == 1, "one job was offered"
        task_name, args = sent_jobs[0]
        assert task_name == "worker.tasks.propagate_state_change", "by the worker's own name"
        assert str(change.id) in str(args), "carrying the change's id"

        # ── The drain ────────────────────────────────────────────────────────────────
        from worker.propagation import propagate

        result = propagate(state_change_id=change.id, now=NOW)

        assert result.failed == 0
        assert result.marked is True

        stale.refresh_from_db(using=CATALOG)
        assert stale.propagated_at is not None, "the backlog is drained"

        # **And the user's world caught up** — which is the part that matters. A drained
        # backlog that did not reach the user would be a drained backlog and nothing else.
        raised = notices(user)
        assert len(raised) == 1, "the user was told about the change they missed"

    def test_a_re_propagation_is_a_no_op(self):
        """**The retry is safe.** A change that was already propagated is not applied
        again — the early return on `propagated_at` is what makes the reconciler's
        re-offer harmless.

        **And it does not raise a second notice**, because the notice's own unique
        constraint and version gate both refuse it.
        """
        user = make_user()
        event = make_catalog_event()
        save_it(user, event)

        change = cancel_it(event)

        from worker.propagation import propagate

        first = propagate(state_change_id=change.id, now=NOW)
        assert first.marked is True

        second = propagate(state_change_id=change.id, now=NOW)

        assert second.marked is False, "it was already propagated"
        assert second.users == 0, "and nobody was walked again"

        assert len(notices(user)) == 1, "still one notice"

    def test_a_partly_applied_change_is_completed_by_the_retry(self):
        """**A partial run is completed, and the applied half is not applied twice.**

        The propagation walks savers one at a time and records a failure without
        stopping. **So a change can be half done** — and the retry must finish it
        without disturbing the half that was already done.
        """
        first_user = make_user("one@example.test")
        second_user = make_user("two@example.test")

        event = make_catalog_event()
        save_it(first_user, event)
        save_it(second_user, event)

        change = cancel_it(event)

        # **The first user is applied, and then the run fails for the second.** The
        # failure is simulated by making the second user's save unreadable to the
        # propagation — the simplest faithful way to do that is to remove the save
        # between the walk and the apply, which is what a concurrent unsave does.
        from worker.propagation import propagate

        original = propagate.__globals__["_apply_to_user"]
        calls: list[UUID] = []

        def flaky(*, change, user_id, now, event_start):
            calls.append(user_id)
            if user_id == second_user.pk:
                # **This saver fails.** The propagation records it and carries on.
                raise RuntimeError("this saver is poisoned")
            return original(change=change, user_id=user_id, now=now, event_start=event_start)

        propagate.__globals__["_apply_to_user"] = flaky
        try:
            first = propagate(state_change_id=change.id, now=NOW)
        finally:
            propagate.__globals__["_apply_to_user"] = original

        assert first.failed == 1, "one saver failed"
        assert first.marked is False, "and the change is not marked propagated"

        change.refresh_from_db(using=CATALOG)
        assert change.propagated_at is None, "so the reconciler will offer it again"

        # **The first user was applied**, despite the second one failing.
        assert len(notices(first_user)) == 1, "the saver that worked was told"
        assert len(notices(second_user)) == 0, "and the one that failed was not"

        # ── The retry ────────────────────────────────────────────────────────────────
        second = propagate(state_change_id=change.id, now=NOW)

        assert second.failed == 0, "the retry succeeded"
        assert second.marked is True

        # **The first user was not told twice.**
        assert len(notices(first_user)) == 1, "still one notice — the retry did not repeat it"

        # **And the second user was caught up.**
        assert len(notices(second_user)) == 1, "the failed saver was caught up"


# ── The mute journey ──────────────────────────────────────────────────────────────────


class TestTheMuteJourney:
    """**A muted event's change says nothing — and its reminders still fire.**

    FR-55's mute silences *the correction*, not the event. A user who mutes is saying
    "I know, stop telling me" — not "remove this from my life". **So the reminders
    still go out on the plan, and the event still places in the digest.**

    **And the terminal exception.** A `cancelled` or `superseded` change is raised
    *despite* the mute. FR-55 has already pulled the event out of the digest, so
    silence about it is the one failure with no second channel to catch it. A mute
    means "stop telling me about tweaks to this event"; reading it as "do not tell me
    it is off" turns a preference into a trap.
    """

    def test_a_muted_events_change_produces_no_notice_and_no_email(self):
        """**Silence, on both channels.**"""
        user = make_user()
        event = make_catalog_event()
        save_it(user, event)

        mute_event_notices(user_id=user.pk, event_id=event.id, actor=Actor.user(user.pk), now=NOW)

        change = sell_it_out(event)

        from worker.propagation import propagate

        result = propagate(state_change_id=change.id, now=NOW)
        assert result.failed == 0

        # **No notice, and no email.**
        assert notices(user) == [], "the mute silenced the notice"
        assert notice_sends(user) == [], "and the email that would have carried it"

        port = InMemoryEmailAdapter()
        run_the_sweep(port, now=SWEEP_AT)

        assert port.sent == [], "nothing at all went out"

    def test_a_muted_events_reminders_still_fire(self):
        """**The mute silences the correction, not the event.** The user's reminder
        still goes out — a user who muted a sold-out event still wants to be told the
        doors are at the time they planned for.
        """
        user = make_user()
        event = make_catalog_event()
        saved = save_it(user, event)
        row = mint_one_reminder(user, event, saved)

        mute_event_notices(user_id=user.pk, event_id=event.id, actor=Actor.user(user.pk), now=NOW)

        change = sell_it_out(event)

        from worker.propagation import propagate

        result = propagate(state_change_id=change.id, now=NOW)
        assert result.failed == 0

        row.refresh_from_db()
        assert row.status == ScheduledSend.Status.PENDING, "the reminder is untouched"

        port = InMemoryEmailAdapter()
        run_the_sweep(port, now=SWEEP_AT)

        keys = [message.idempotency_key for message in port.sent]
        assert row.send_key in keys, "the reminder still goes out"

    def test_a_muted_events_cancellation_is_still_raised(self):
        """**The terminal exception.** The mute does not swallow a cancellation.

        **This is the asymmetry the whole mute design turns on**, and it is asserted
        here because it is the case a user would be harmed by if it were wrong: the
        event is gone from their digest, and if the mute also silenced the
        cancellation, nothing anywhere would tell them their evening is off.
        """
        user = make_user()
        event = make_catalog_event()
        save_it(user, event)

        mute_event_notices(user_id=user.pk, event_id=event.id, actor=Actor.user(user.pk), now=NOW)

        change = cancel_it(event)

        from worker.propagation import propagate

        result = propagate(state_change_id=change.id, now=NOW)
        assert result.failed == 0

        raised = notices(user)
        assert len(raised) == 1, "the cancellation was raised despite the mute"
        assert raised[0].change_kind == ChangeKind.CANCELLED.value

        port = InMemoryEmailAdapter()
        run_the_sweep(port, now=SWEEP_AT)

        assert len(port.sent) == 1, "and the email went out too"
        assert "was cancelled" in port.sent[0].message.subject

    def test_unmuting_does_not_replay_what_was_silenced(self):
        """**Unmuting does not raise the notices the mute suppressed.**

        FR-55's own rule: *"Unmuting does not replay what was silenced."* Raising them
        now would deliver a correction about a change the user has had days to notice —
        and the event's current state is on its Detail screen, which is where a user who
        just unmuted is standing.
        """
        user = make_user()
        event = make_catalog_event()
        save_it(user, event)

        mute_event_notices(user_id=user.pk, event_id=event.id, actor=Actor.user(user.pk), now=NOW)

        change = sell_it_out(event)

        from worker.propagation import propagate

        propagate(state_change_id=change.id, now=NOW)
        assert notices(user) == [], "the mute silenced it"

        from apps.delivery.services.mutes import unmute_event_notices

        result = unmute_event_notices(
            user_id=user.pk, event_id=event.id, actor=Actor.user(user.pk), now=NOW
        )
        assert result.muted is False
        assert result.changed is True

        # **The change is not re-propagated.** The reconciler does not offer it — it is
        # marked propagated — and nothing replays it.
        assert notices(user) == [], "the silenced notice is not replayed"


# ── The two in-app surfaces ───────────────────────────────────────────────────────────


class TestTheStripAndTheBanner:
    """**The two surfaces the correction is told on, through the real HTTP stack.**

    The strip is on the digest home; the banner is on the Detail screen of the affected
    event. **Both read the same `StateChangeNotice` row**, so they cannot drift — and
    this proves it end to end, over HTTP, with the session cookie a browser would send.

    **Why HTTP and not the services.** A service-level call cannot observe the seam
    that matters here: the strip's *list* is bounded by the server, the banner's *mute*
    is the server's fact, and the dismissal is a write the server records. Those are
    the things the work item is about, and they only exist over HTTP.

    **The detail read is `now`-bounded**, so these calls happen at an instant before the
    event starts — the same bound a save is subject to.
    """

    def test_the_cancellation_reaches_the_strip_and_the_detail_banner(self):
        """**One notice, two surfaces, one row.**"""
        user = make_user()
        event = make_catalog_event()
        save_it(user, event)

        change = cancel_it(event)

        from worker.propagation import propagate

        result = propagate(state_change_id=change.id, now=NOW)
        assert result.failed == 0

        from tests.csrf import CsrfClient

        client = CsrfClient()
        client.force_login(user)

        # ── The strip ───────────────────────────────────────────────────────────────
        strip = client.get("/api/notices")
        assert strip.status_code == 200, strip.content
        items = strip.json()["items"]

        assert len(items) == 1, "the strip carries one notice"
        assert items[0]["event_id"] == str(event.id), "and it names the event"
        assert items[0]["change_kind"] == ChangeKind.CANCELLED.value
        assert items[0]["event_version"] == change.event_version, "carrying the version"

        # **The notice payload carries no title** (AD-13). The strip cannot name the
        # event, and that is why its link is the event's own page.
        assert "title" not in items[0], "no title on the wire"

        # ── The banner ──────────────────────────────────────────────────────────────
        detail = client.get(f"/api/events/{event.id}")
        assert detail.status_code == 200, detail.content
        personal = detail.json()["personal"]

        assert personal["muted"] is False, "the event is not muted"
        assert personal["notice"] is not None, "the banner has its notice"
        assert personal["notice"]["change_kind"] == ChangeKind.CANCELLED.value
        assert personal["notice"]["id"] == items[0]["id"], (
            "the banner and the strip name the same row"
        )

    def test_dismissing_the_notice_empties_the_strip_but_not_the_banner(self):
        """**The strip empties; the banner stays.** A dismissal is the user closing the
        strip's entry — and the banner is about *this* event, on a page the user came to
        on purpose. So a dismissed notice still shows there, and says so.
        """
        user = make_user()
        event = make_catalog_event()
        save_it(user, event)

        change = cancel_it(event)

        from worker.propagation import propagate

        propagate(state_change_id=change.id, now=NOW)

        from tests.csrf import CsrfClient

        client = CsrfClient()
        client.force_login(user)

        items = client.get("/api/notices").json()["items"]
        assert len(items) == 1
        notice_id = items[0]["id"]

        # ── The dismissal ───────────────────────────────────────────────────────────
        dismissed = client.post(f"/api/notices/{notice_id}/dismiss")
        assert dismissed.status_code == 200, dismissed.content
        assert dismissed.json()["dismissed"] is True
        assert dismissed.json()["changed"] is True

        # ── The strip is empty ──────────────────────────────────────────────────────
        assert client.get("/api/notices").json()["items"] == [], "the strip emptied"

        # **And the dismissal is idempotent** — a second dismissal is a success that
        # changed nothing.
        again = client.post(f"/api/notices/{notice_id}/dismiss")
        assert again.status_code == 200
        assert again.json()["changed"] is False, "nothing moved the second time"

        # ── The banner stays ───────────────────────────────────────────────────────
        detail = client.get(f"/api/events/{event.id}")
        personal = detail.json()["personal"]

        assert personal["notice"] is not None, "the banner still shows the notice"
        assert personal["notice"]["dismissed_at"] is not None, "and says it was dismissed"

    def test_a_muted_event_has_no_banner_and_no_strip_entry(self):
        """**The mute silences both surfaces.** The banner *is* the correction, and the
        strip's entry is the same correction — so a muted event has neither.
        """
        user = make_user()
        event = make_catalog_event()
        save_it(user, event)

        from tests.csrf import CsrfClient

        client = CsrfClient()
        client.force_login(user)

        muted = client.put(f"/api/notices/events/{event.id}/mute")
        assert muted.status_code == 200, muted.content
        assert muted.json()["muted"] is True
        assert muted.json()["changed"] is True

        change = sell_it_out(event)

        from worker.propagation import propagate

        propagate(state_change_id=change.id, now=NOW)

        assert client.get("/api/notices").json()["items"] == [], "no strip entry"

        detail = client.get(f"/api/events/{event.id}")
        personal = detail.json()["personal"]
        assert personal["muted"] is True, "the banner's mute control shows the mute"
        assert personal["notice"] is None, "and there is no notice for it"

    def test_a_muted_events_cancellation_still_reaches_the_banner(self):
        """**The terminal exception, over HTTP.** A cancelled event is announced even
        when muted — the mute has already removed it from the digest, so silence about
        it would have no second channel to catch it.
        """
        user = make_user()
        event = make_catalog_event()
        save_it(user, event)

        from tests.csrf import CsrfClient

        client = CsrfClient()
        client.force_login(user)

        client.put(f"/api/notices/events/{event.id}/mute")

        change = cancel_it(event)

        from worker.propagation import propagate

        propagate(state_change_id=change.id, now=NOW)

        detail = client.get(f"/api/events/{event.id}")
        personal = detail.json()["personal"]

        assert personal["muted"] is True, "still muted"
        assert personal["notice"] is not None, "but the cancellation is still there"
        assert personal["notice"]["change_kind"] == ChangeKind.CANCELLED.value

    def test_the_strip_is_bounded_by_the_server(self):
        """**A few, not a history.** FR-54 promises one calm correction, and the strip's
        list is bounded by the server — a query parameter would make the bound the
        client's choice, and there is no inbox to page through.
        """
        from shared.constants import NOTICE_STRIP_LIMIT

        user = make_user()
        event = make_catalog_event()
        save_it(user, event)

        change = cancel_it(event)

        from worker.propagation import propagate

        propagate(state_change_id=change.id, now=NOW)

        from tests.csrf import CsrfClient

        client = CsrfClient()
        client.force_login(user)

        items = client.get("/api/notices").json()["items"]

        assert len(items) <= NOTICE_STRIP_LIMIT, "the strip is bounded"
        assert len(items) == 1, "and it holds the one notice"
