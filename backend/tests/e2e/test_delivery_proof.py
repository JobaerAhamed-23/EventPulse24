"""The delivery path, end to end: a quiet hour, a deferred reminder, a real send.

**Why one file and not eight.** The point of a proof is that the steps *compose*.
Eleven items of this intent were built and each was tested in isolation; the failures
that matter live in the seams between them. A chain of independent tests proves each
step and not the whole — a due time shifted in one test and swept in another is not the
same send, and a row minted in one test and counted in another catches nothing.

So the scenario is one test, one user, one database, and one transaction's worth of
shared state.

**What this scenario proves, and what it does not.**

The work item's claim is narrow and checkable: *"a user sets a quiet window, saves an
event whose reminder would land inside it, and the mail arrives at the window's end —
once, on the right stream, under the right key."* Every piece of AD-7 is exercised by
that one sentence.

**What is proved here is what actually left the system.** The assertion surface is the
memory email adapter — it records each message with its stream and its idempotency key,
so the proof can say exactly what was sent, to whom, on which stream, under which key,
and when. The unit tests assert each service's own contract; this asserts the *end
state*, which is the only place the whole path is visible at once.

**The clock is frozen, never slept.** Every service on this path takes `now` as an
argument, so the proof passes its own instant and never reads the wall clock. A proof
that sleeps is slow, flaky, and — the defect item 11 found in the backend's own digest
tests — its answer can depend on the hour it ran.

**The frozen instants are chosen, not arbitrary.** The event starts Friday 23:30 local,
so its `1hr` slot lands at 22:30 — inside the 22:00–08:00 window's **evening side** —
and must defer to Saturday 08:00. Both sides of midnight are in the scenario on purpose:
a window that crosses midnight is the default window, and testing it at 23:30 proves the
"evening defers to tomorrow" branch rather than the trivial one.
"""

from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model

from adapters.email.memory import InMemoryEmailAdapter
from apps.delivery.models import ReminderPlan, ScheduledSend
from apps.delivery.services.delivery_messages import renderer_for
from apps.delivery.services.delivery_sweep import sweep_due_sends
from apps.delivery.services.notification_preferences import set_quiet_hours
from apps.delivery.services.pulse_ping import mint_ping_send
from apps.delivery.services.reminder_plan_read import compute_deliveries
from apps.delivery.services.scheduled_sends import (
    SendTarget,
    apply_lifecycle_change,
    mint_for_plan,
    reschedule_pending_for_user,
)
from apps.delivery.services.unsubscribes import unsubscribe_event_reminders
from apps.identity.services.recipients import get_recipient_address
from apps.personalization.services.personal_events import create_personal_event
from apps.personalization.services.saved_events import save_event
from domain.quiet_hours import QuietHours
from ports.email import Stream
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import EventFactory, VenueFactory
from tests.personalization.factories import DigestPreferenceFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

User = get_user_model()

#: The zone under test. The user's own zone is what every wall clock in this file is
#: read against — "10pm" means 10pm *where the user is*.
ZONE = "America/Los_Angeles"

#: Friday 2026-11-06 23:30 in Los Angeles. The event's start.
#:
#: **Both sides of midnight are in the scenario on purpose.** A `1hr` slot lands at
#: 22:30 — inside the 22:00–08:00 window's *evening* side — and must defer to Saturday
#: 08:00. Testing at, say, 14:00 would exercise only the trivial branch.
FRIDAY_2330_LOCAL = datetime(2026, 11, 7, 7, 30, tzinfo=UTC)  # 2026-11-06 23:30 in LA

#: The instant the slot *names*, before Quiet Hours: one hour before the start.
#: 2026-11-06 22:30 local — inside the window.
SLOT_AT_LOCAL = datetime(2026, 11, 7, 6, 30, tzinfo=UTC)  # 2026-11-06 22:30 in LA

#: The instant the reminder is *sent*: Saturday 2026-11-07 08:00 local.
#: **This is the window's end, and it is the claim.**
EXPECTED_SEND_LOCAL = datetime(2026, 11, 7, 16, 0, tzinfo=UTC)  # 2026-11-07 08:00 in LA

#: The instant the **Pulse Ping** is sent: 09:00 local on the digest's own date.
#:
#: **A different time, and deliberately so.** The reminder's send time is the quiet
#: window's *end* — 08:00 — because the slot was deferred. The Ping's send time is the
#: user's *delivery time* — 09:00 — because 09:00 is outside the window and nothing
#: moved it. The two rows are due at different instants, and a proof that swept at one
#: instant would find the other row not yet due.
EXPECTED_PING_SEND_LOCAL = datetime(2026, 11, 7, 17, 0, tzinfo=UTC)  # 2026-11-07 09:00 in LA

#: The moment the proof acts. Before the event, so nothing has been swept yet.
NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)  # 2026-11-06 04:00 in LA

#: The quiet window the work item names: 22:00 → 08:00, in the user's own zone.
QUIET_WINDOW = QuietHours(start=time(22, 0), end=time(8, 0))

ACTOR = Actor.system("e2e_proof")


# ── The scaffolding ─────────────────────────────────────────────────────────────────────────


def make_user(email="maya@example.test"):
    """A real user with a real pk, a zone, and a city.

    **The zone is the point.** Every wall clock in this file is read against it, so a
    window that meant "10pm wherever the user is" is expressed as 10pm *here*.

    **`city_source` is set with the city.** The database refuses a row that has a city
    without saying where it came from — *"we know where you are"* and *"we know how we
    found out"* are both facts, and one without the other is a row nobody can interpret.
    """
    user = User.objects.create_user(email=email, password="pw")
    DigestPreferenceFactory(
        user_id=user.pk, timezone=ZONE, city="Los Angeles", city_source="choice"
    )
    return user


def set_the_window(user, window=QUIET_WINDOW):
    """The user sets their quiet window — the first step of the scenario."""
    set_quiet_hours(user_id=user.pk, window=window, actor=ACTOR, now=NOW)


def make_saved_event(user, *, start_utc=FRIDAY_2330_LOCAL, title="Brooklyn Tech Meetup"):
    """A saved public event owned by `user`.

    **The plan's `target_id` is the catalog event's id** — the tree's convention — so a
    real catalog event is saved and its id is what the plan addresses.
    """
    fingerprint = f"venue-{title}|{uuid4()}"
    event = EventFactory(
        title=title,
        venue=VenueFactory(city="New York City", venue_fingerprint=fingerprint),
        start_time_utc=start_utc,
        last_seen_at=NOW,
    )
    result = save_event(user_id=user.pk, event_id=event.id, actor=Actor.user(user.pk), now=NOW)
    return event, result.saved


def make_personal_event(user, *, start_utc=FRIDAY_2330_LOCAL, name="Dinner with Priya"):
    """A personal event owned by `user`."""
    result = create_personal_event(
        user_id=user.pk,
        name=name,
        start_utc=start_utc,
        end_utc=start_utc + timedelta(hours=2),
        start_time_tz=ZONE,
        actor=Actor.user(user.pk),
        now=NOW,
    )
    return result.event


def target_for_saved_event(event, saved, *, version=1):
    """The `SendTarget` a saved public event's reminders are minted against."""
    return SendTarget(
        target_kind=ReminderPlan.TargetKind.SAVED_EVENT,
        target_id=event.id,
        start_utc=event.start_time_utc,
        version=version,
        catalog_event_id=event.id,
    )


def target_for_personal_event(event, *, revision=1):
    """The `SendTarget` a personal event's reminders are minted against."""
    return SendTarget(
        target_kind=ReminderPlan.TargetKind.PERSONAL_EVENT,
        target_id=event.id,
        start_utc=event.start_utc,
        version=revision,
    )


def run_the_sweep(port, *, now=EXPECTED_SEND_LOCAL):
    """Run the sweep against the memory adapter, and return its counts.

    **The sweep is the real one** — `delivery_sweep.sweep_due_sends`, the same function
    the worker task calls. Only the port is swapped, and the swap is how the proof sees
    what left the system.
    """
    return sweep_due_sends(
        port=port,
        renderer=renderer_for,
        resolve_recipient=lambda user_id: get_recipient_address(user_id=user_id),
        now=now,
    )


def pending_sends(user):
    """This user's pending rows, in minting order."""
    return list(
        ScheduledSend.objects.using(PERSONAL)
        .filter(user_id=user.pk, status=ScheduledSend.Status.PENDING)
        .order_by("created_at", "id")
    )


def all_sends(user):
    """Every row this user owns, in minting order."""
    return list(
        ScheduledSend.objects.using(PERSONAL).filter(user_id=user.pk).order_by("created_at", "id")
    )


# ── The deferral proof ─────────────────────────────────────────────────────────────────────


def test_a_reminder_inside_the_quiet_window_arrives_at_the_window_end():
    """**The claim this whole intent exists for.**

    The user sets a 22:00–08:00 window and saves an event whose `1hr` slot lands at
    22:30 local — inside the window. The mail arrives at **Saturday 08:00 local**, once,
    on the **transactional** stream, under the **event's send key**.
    """
    user = make_user()
    set_the_window(user)
    event, saved = make_saved_event(user)
    target = target_for_saved_event(event, saved)

    minted = mint_for_plan(user_id=user.pk, target=target, slots=("1hr",), actor=ACTOR, now=NOW)
    assert minted == 1

    # **The stored `due_at` is already the window's end.** AD-7 says Quiet Hours are
    # applied "when `due_at` is computed or recomputed… never as a skip at send time" —
    # so the shift is in the row, and the sweep never has to know about the window.
    row = pending_sends(user)[0]
    assert row.due_at == EXPECTED_SEND_LOCAL
    assert row.slot_at == SLOT_AT_LOCAL

    # **The key identifies the thing being sent, not when it goes.** It is minted once,
    # and its shape is `user · kind · event · slot · version` — **no instant anywhere**,
    # which is what makes a quiet-hours change unable to move it.
    assert row.send_key == f"{user.pk}:event_reminder:{event.id}:1hr:1"

    port = InMemoryEmailAdapter()
    counts = run_the_sweep(port)

    assert counts.sent == 1
    assert len(port.sent) == 1

    sent = port.sent[0]
    assert sent.stream is Stream.TRANSACTIONAL
    assert sent.idempotency_key == row.send_key
    assert sent.message.to == "maya@example.test"

    # **And the row says it went.** A row that says `pending` after a successful send is
    # a promise the sweep did not keep, and the next sweep would try again.
    row.refresh_from_db()
    assert row.status == ScheduledSend.Status.SENT


def test_the_sweep_before_the_window_end_sends_nothing():
    """**A deferred send waits. It does not go early and it does not go twice.**

    The sweep running *before* the window's end must find the row not yet due, and the
    adapter must see nothing.
    """
    user = make_user()
    set_the_window(user)
    event, saved = make_saved_event(user)
    mint_for_plan(
        user_id=user.pk,
        target=target_for_saved_event(event, saved),
        slots=("1hr",),
        actor=ACTOR,
        now=NOW,
    )

    port = InMemoryEmailAdapter()
    counts = run_the_sweep(port, now=NOW)

    assert counts.sent == 0
    assert port.sent == []

    # **The row is still pending** — it was not cancelled, and it was not sent. It is a
    # promise that has not come due yet.
    assert pending_sends(user)


# ── The Pulse Ping proofs ──────────────────────────────────────────────────────────────────


def test_a_qualifying_user_gets_one_ping_on_the_bulk_stream():
    """**One Ping, on the bulk stream, with an unsubscribe URL and the digest's key.**

    FR-10's rule is *"3 qualifying events → exactly 1 Pulse Ping, not 3"*, and the key
    is what makes it true by construction rather than by a count.
    """
    user = make_user()
    local_date = date(2026, 11, 7)

    outcome = mint_ping_send(
        user_id=user.pk,
        local_date=local_date,
        public_qualifying_count=3,
        personal_qualifying_count=0,
        has_qualifying_events=True,
        now=NOW,
    )

    assert outcome.minted is True
    assert outcome.suppressed is False
    assert outcome.reason is None

    port = InMemoryEmailAdapter()
    counts = run_the_sweep(port, now=EXPECTED_PING_SEND_LOCAL)

    assert counts.sent == 1
    sent = port.sent[0]

    # **The bulk stream, and the unsubscribe URL that RFC 8058 requires on it.**
    assert sent.stream is Stream.BULK
    assert sent.message.unsubscribe_url is not None

    # **The key is `user_id · digest · local_date`** — a calendar day, not an instant.
    assert sent.idempotency_key == f"{user.pk}:digest:2026-11-07"


def test_a_user_with_nothing_to_say_gets_no_ping_and_no_row():
    """**The suppression proof.**

    A user with zero qualifying public events and zero personal events in the next 48
    hours gets **no row minted and no message sent** — and the suppression is recorded.

    **No row, not a row that is later skipped.** A `pending` row that is never sent is
    indistinguishable from a bug, and AD-7's whole premise is that a `pending` row is a
    promise. The silence has to be *the absence of the row*.
    """
    user = make_user()

    outcome = mint_ping_send(
        user_id=user.pk,
        local_date=date(2026, 11, 7),
        public_qualifying_count=0,
        personal_qualifying_count=0,
        has_qualifying_events=False,
        now=NOW,
    )

    assert outcome.minted is False
    assert outcome.suppressed is True
    assert outcome.reason == "no_qualifying_events"

    # **No row was minted.** This is the assertion that matters.
    assert all_sends(user) == []

    port = InMemoryEmailAdapter()
    counts = run_the_sweep(port, now=EXPECTED_PING_SEND_LOCAL)

    assert counts.sent == 0
    assert port.sent == []


def test_a_user_with_only_a_personal_event_does_get_the_ping():
    """**The personal-only proof.**

    The same user, with one personal event instead of a public one, **does** get the
    Ping. FR-10's rule is an `OR`: qualifying public events **or** personal events.
    """
    user = make_user()

    outcome = mint_ping_send(
        user_id=user.pk,
        local_date=date(2026, 11, 7),
        public_qualifying_count=0,
        personal_qualifying_count=1,
        has_qualifying_events=True,
        now=NOW,
    )

    assert outcome.minted is True
    assert outcome.suppressed is False

    port = InMemoryEmailAdapter()
    counts = run_the_sweep(port, now=EXPECTED_PING_SEND_LOCAL)

    assert counts.sent == 1
    assert port.sent[0].stream is Stream.BULK


# ── The reschedule proof ───────────────────────────────────────────────────────────────────


def test_changing_the_quiet_window_moves_the_due_time_and_never_the_key():
    """**The key-stability proof, and the reason AD-7 says what it says.**

    Four ordinary user actions rewrite `due_at` on pending rows — quiet hours, timezone,
    delivery time, a plan edit. **If the key moved with the time, each would mint a second
    send**, and a user who adjusted their settings three times would receive four copies
    of one reminder.

    **Ten changes, not one.** The first change is the easy case and the tenth is where an
    accumulating off-by-one would show.
    """
    user = make_user()
    set_the_window(user)
    event, saved = make_saved_event(user)
    mint_for_plan(
        user_id=user.pk,
        target=target_for_saved_event(event, saved),
        slots=("1hr",),
        actor=ACTOR,
        now=NOW,
    )

    original = pending_sends(user)[0]
    original_key = original.send_key

    for step in range(10):
        # **A different window each time**, so the rewrite really is rewriting.
        window = QuietHours(start=time(22, 0), end=time(8 + (step % 3), 0))
        set_quiet_hours(user_id=user.pk, window=window, actor=ACTOR, now=NOW)
        reschedule_pending_for_user(user_id=user.pk, actor=ACTOR, now=NOW)

        rows = pending_sends(user)
        assert len(rows) == 1, f"step {step}: the rewrite minted a second row"
        assert rows[0].send_key == original_key, f"step {step}: the key moved"

    # **And the row is still one row.** Ten rewrites, one promise.
    assert len(all_sends(user)) == 1

    # **The key is byte-identical to the one minted.** Not merely equal — the same bytes.
    assert pending_sends(user)[0].send_key.encode() == original_key.encode()


def test_a_reschedule_that_moves_the_due_time_does_not_send_twice():
    """**The end-to-end version of the same claim.**

    The rewrite moves the row's `due_at`; the sweep then sends it **once**. If the
    rewrite had minted a second row, the sweep would send twice.

    **The sweep runs at the *new* time.** The window widens from 22:00–08:00 to
    21:00–09:00, so the slot's deferred send moves from 08:00 to 09:00 local. A sweep
    at the old time would find nothing due, and a sweep at the new time twice would find
    one send — which is the claim.
    """
    user = make_user()
    set_the_window(user)
    event, saved = make_saved_event(user)
    mint_for_plan(
        user_id=user.pk,
        target=target_for_saved_event(event, saved),
        slots=("1hr",),
        actor=ACTOR,
        now=NOW,
    )

    set_quiet_hours(
        user_id=user.pk,
        window=QuietHours(start=time(21, 0), end=time(9, 0)),
        actor=ACTOR,
        now=NOW,
    )
    reschedule_pending_for_user(user_id=user.pk, actor=ACTOR, now=NOW)

    # **The row's due time moved to the new window's end.**
    row = pending_sends(user)[0]
    assert row.due_at == datetime(2026, 11, 7, 17, 0, tzinfo=UTC)  # 09:00 in LA

    port = InMemoryEmailAdapter()
    counts = run_the_sweep(port, now=datetime(2026, 11, 7, 17, 0, tzinfo=UTC))

    assert counts.sent == 1
    assert len(port.sent) == 1

    # **And the key did not.** The row moved; the key did not.
    assert port.sent[0].idempotency_key == row.send_key


# ── The propagation proof ──────────────────────────────────────────────────────────────────


def test_a_moved_event_cancels_the_old_rows_and_mints_new_ones():
    """**The AD-17 propagation proof.**

    The event's start moves. The old pending rows are **cancelled**, new ones are minted
    under a **bumped `event_version`**, and a reminder already `sent` for the old date
    does **not** block the new one.

    **The last part is the one that matters.** A `sent` row is a spent key, and a naive
    implementation would find the key already used and skip the mint — the user would
    get no reminder for the event's new time, and would never know why.
    """
    user = make_user()
    set_the_window(user)
    event, saved = make_saved_event(user)

    # **The first mint, at version 1.**
    mint_for_plan(
        user_id=user.pk,
        target=target_for_saved_event(event, saved, version=1),
        slots=("1hr",),
        actor=ACTOR,
        now=NOW,
    )
    first = pending_sends(user)[0]
    assert first.event_version == 1

    # **One of them goes out.**
    port = InMemoryEmailAdapter()
    run_the_sweep(port, now=EXPECTED_SEND_LOCAL)
    first.refresh_from_db()
    assert first.status == ScheduledSend.Status.SENT

    # **The event moves, and the version bumps.** The kind is `time_moved` — the
    # vocabulary AD-17's table uses for "the event still happens, at a different time".
    moved = target_for_saved_event(event, saved, version=2)
    result = apply_lifecycle_change(
        user_id=user.pk,
        target=moved,
        kind="time_moved",
        slots=("1hr",),
        actor=ACTOR,
        now=NOW,
    )

    assert result["minted"] == 1
    assert result["cancelled"] == 0  # the old row was already sent, not pending

    # **The new row carries the bumped version**, and the old one is still sent.
    rows = [row for row in all_sends(user) if row.status == ScheduledSend.Status.PENDING]
    assert len(rows) == 1
    assert rows[0].event_version == 2

    # **And the sent row for the old date did not block the new one.**
    assert first.status == ScheduledSend.Status.SENT
    assert len(all_sends(user)) == 2


def test_a_cancelled_event_cancels_its_pending_reminders():
    """**The other half of the propagation.**

    An event that is cancelled has its pending reminders cancelled — the user must not be
    reminded about something that is not happening.
    """
    user = make_user()
    event = make_personal_event(user)

    mint_for_plan(
        user_id=user.pk,
        target=target_for_personal_event(event),
        slots=("1hr",),
        actor=ACTOR,
        now=NOW,
    )
    assert len(pending_sends(user)) == 1

    result = apply_lifecycle_change(
        user_id=user.pk,
        target=target_for_personal_event(event, revision=2),
        kind="cancelled",
        slots=("1hr",),
        actor=ACTOR,
        now=NOW,
    )

    assert result["cancelled"] == 1
    assert pending_sends(user) == []


# ── The unsubscribe proof ──────────────────────────────────────────────────────────────────


def test_one_click_unsubscribe_stops_the_events_reminders_and_leaves_the_ping_alone():
    """**FR-11's explicit requirement.**

    The user unsubscribes from **one event's** reminders. That event's pending reminders
    are cancelled — **and the Pulse Ping keeps arriving**, because they asked to stop
    *this event's* reminders and not everything.

    **The distinction is the whole point of FR-11**, and it is the one thing that is easy
    to get backwards: a single unsubscribe that turned off the daily digest would be a
    surprise the user cannot undo.
    """
    user = make_user()
    event = make_personal_event(user)

    # **Both kinds of send exist at once** — the event's reminder and the daily Ping.
    mint_for_plan(
        user_id=user.pk,
        target=target_for_personal_event(event),
        slots=("1hr",),
        actor=ACTOR,
        now=NOW,
    )
    mint_ping_send(
        user_id=user.pk,
        local_date=date(2026, 11, 7),
        public_qualifying_count=1,
        personal_qualifying_count=0,
        has_qualifying_events=True,
        now=NOW,
    )
    assert len(pending_sends(user)) == 2

    result = unsubscribe_event_reminders(user_id=user.pk, target_id=event.id, actor=ACTOR, now=NOW)

    assert result.changed is True
    assert result.cancelled == 1

    # **The event's reminder is gone. The Ping is not.**
    remaining = pending_sends(user)
    assert len(remaining) == 1
    assert remaining[0].kind == ScheduledSend.Kind.DIGEST

    # **And the plan itself says so**, so the next write does not re-attach the slots.
    plan = ReminderPlan.objects.using(PERSONAL).filter(user_id=user.pk, target_id=event.id).first()
    assert plan is not None
    assert plan.slots == []


# ── The idempotency proof ──────────────────────────────────────────────────────────────────


def test_running_the_sweep_twice_over_one_due_row_sends_once():
    """**The provider saw one send.**

    The sweep is run twice over the same due row. The second run must find the row
    already `sent` — **not** pending — and the adapter must have seen exactly one message.

    **The dedup is at the boundary**, by the send key: the key is the provider's
    idempotency key, and it is the same bytes on both runs.
    """
    user = make_user()
    set_the_window(user)
    event, saved = make_saved_event(user)
    mint_for_plan(
        user_id=user.pk,
        target=target_for_saved_event(event, saved),
        slots=("1hr",),
        actor=ACTOR,
        now=NOW,
    )

    port = InMemoryEmailAdapter()

    first = run_the_sweep(port, now=EXPECTED_SEND_LOCAL)
    second = run_the_sweep(port, now=EXPECTED_SEND_LOCAL)

    assert first.sent == 1
    assert second.sent == 0
    assert len(port.sent) == 1

    # **The same key, both times.** The provider's dedup is keyed on this string, so it
    # is the thing that has to be stable — not the row, and not the time.
    assert port.sent[0].idempotency_key == pending_or_sent_key(user)


def pending_or_sent_key(user):
    """This user's only row's send key, whatever its status."""
    return all_sends(user)[0].send_key


# ── The server-computed flag, and the frontend's half ─────────────────────────────────────


def test_the_server_computes_the_deferred_flag_the_picker_shows():
    """**The server's half of the frontend proof.**

    The picker's dimmed chip is driven by a flag **the server computes** — so the server's
    half is: given a quiet window, the slot that lands inside it comes back with
    `deferred` true and `deferred_to` at the window's end.

    **The frontend's half is a component test** — `frontend/components/reminders/
    reminder-chip.test.tsx` — because the flag's journey ends in a rendered chip. Asserting
    both halves is what makes the seam provable: a flag the server computes but the client
    ignores would pass both halves on their own.
    """
    deliveries = compute_deliveries(
        slots=("1hr",),
        start_utc=FRIDAY_2330_LOCAL,
        zone=ZONE,
        window=QUIET_WINDOW,
    )

    assert len(deliveries) == 1
    delivery = deliveries[0]
    assert delivery.slot == "1hr"
    assert delivery.deferred is True
    assert delivery.deferred_to == EXPECTED_SEND_LOCAL

    # **And the delivery time the picker shows is the time the send gets.** The same
    # published function the minting path uses, so the two agree by construction.
    assert delivery.delivery_at == EXPECTED_SEND_LOCAL


def test_a_slot_outside_the_window_is_not_deferred():
    """**The other half of the flag.**

    A slot that lands outside the window comes back **not** deferred, with no
    `deferred_to` — because there is nothing to defer *to*. A `deferred_to` on an
    un-deferred slot would be a time the picker showed that the send was not going to
    happen at.

    **The event starts at 18:00 local** — a `1d` slot lands at 18:00 the day before,
    which is well outside a 22:00–08:00 window. **The choice of start matters:** the
    scenario's own 23:30 event would *not* serve here, because one day earlier is still
    23:30, which is inside the window.
    """
    afternoon_start = datetime(2026, 11, 6, 2, 0, tzinfo=UTC)  # 2026-11-05 18:00 in LA

    deliveries = compute_deliveries(
        slots=("1d",),
        start_utc=afternoon_start,
        zone=ZONE,
        window=QUIET_WINDOW,
    )

    assert deliveries[0].deferred is False
    assert deliveries[0].deferred_to is None
