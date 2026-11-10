"""The single writer of the `SCHEDULED_SEND` **schedule** (AD-7, AD-17).

**What "single writer" means here, precisely.** This module owns every write that *plans*
a send: minting it, moving it, cancelling it, rewriting it, and applying a lifecycle
change to it. The one other module that writes the table is `delivery_sweep`, and it
writes the **execution** half — the claim, the mark as sent, the record of a provider
failure — because a row's fate at the moment it is delivered is not a planning decision
and cannot be made by a module that does not hold the claim.

**So the rule is: the status a row is *given* is decided here, and the status a row
*reaches* is recorded there.** Two modules, two halves of one table, and no third.

**There are two minting commands, because there are two kinds of send.** `mint_for_plan`
creates a row for an event's Reminder Plan slots — a row addressed by a target, whose
`due_at` is a slot offset before the event's start. `mint_digest` creates the one daily
digest row — a row about a user and a day, with no target, whose `due_at` is the user's
delivery time. **One creating path in this module, two commands in it:** the difference is
the shape of the row, not a second writer.

Three kinds of change reach this module, and **they must behave differently**. They all read as
"recompute the time", which is the trap:
**1. Preference change** — quiet hours, timezone, delivery time, a plan edit. The key is
**unchanged**; `due_at` is rewritten in place on `pending` rows.

**2. Lifecycle change (AD-17)** — the source moved, cancelled or superseded the event. The
key is **new**: the old `pending` rows are cancelled and fresh ones minted.

**3. Disappearance** — un-saved, deleted, unsubscribed, account closed. `pending` rows are
cancelled and nothing is minted.

**Cancelling has two commands, because the rows have two shapes.** A reminder row is
addressed by its `(target_kind, target_id)` pair, and `cancel_sends_for_targets` cancels it.
A **digest** row has no target at all — `target_id` is `NULL` and `target_kind` is empty,
because the row is about a user and a day rather than an event — so it cannot be addressed
that way, and `cancel_pending_digests_for_user` cancels it by kind. **Two commands, one
writer:** every status write on `SCHEDULED_SEND` happens in this module, which is the
property the module's name claims. A row's shape is a reason for a second command, never
for a second writer.

Conflating 1 and 2 is the expensive mistake. If a preference change minted, every settings edit
would add a duplicate reminder; if a lifecycle change only rewrote, a moved event would keep a
reminder keyed to the old date forever. This is what AD-7's "the key is never derived from
`due_at`" buys, and this module is where it is spent.

**There is no `recompute(..., remint=bool)`.** A boolean is how three behaviours collapse into
one function whose caller has to get a flag right, and the caller who gets it wrong gets
duplicate sends with no error. Four names, four behaviours. `reschedule_pending_for_user` has
**no code path that creates a row** — a structural test asserts that, so "a settings change
duplicated my reminders" is unreachable rather than merely discouraged.

**`apply_lifecycle_change` is the `delivery` half of AD-17's propagation.** `worker.propagation`
calls it, after the `personalization` half has run, because that order is the only survivable
one: a crash between the halves leaves sends carrying an old version, and the sweep's guard
*holds* those rows rather than sending them — whereas the reverse order would leave a user's
reminders re-minted for a new time while their Timeline still showed the old one.

It writes only `delivery` rows, and it is version-gated like every other published service
here: a change whose version is not newer than what the row already holds changes nothing.
(Decided with the user 2026-10-31; design doc D8.)
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction

from apps.delivery.models import ReminderPlan, ScheduledSend
from apps.delivery.send_keys import (
    digest_key,
    digest_local_date_from_key,
    event_reminder_key,
    personal_reminder_key,
    state_notice_key,
)
from apps.delivery.services.audit import write_audit
from apps.delivery.services.notification_preferences import get_preference
from apps.delivery.services.slots import custom_slot_minutes
from domain.quiet_hours import QuietHours, shift_to_sendable
from ports.email import Stream
from shared.actor import Actor
from shared.constants import (
    DEFAULT_DIGEST_DELIVERY_TIME,
    DEFAULT_DIGEST_TIMEZONE,
    LIFECYCLE_SEND_BEHAVIOUR,
    REMINDER_SLOT_OFFSET,
    LifecycleSendBehaviour,
    ReminderSlot,
)
from shared.db import PERSONAL


class TerminalSendError(RuntimeError):
    """A write tried to move a `sent`, `cancelled` or `failed` row.

    A programming error, never mapped to HTTP. A terminal row is a fact about something that
    already happened (or definitively did not); re-timing or resurrecting one is how a user
    receives the same email twice.
    """


@dataclass(frozen=True)
class SendTarget:
    """One personal-side record whose reminders are being minted or cancelled.

    `version` is the event's version (a catalog `event_version`) or the personal event's
    revision — whichever applies to `target_kind`. It goes **into the key**, frozen at minting.
    """

    target_kind: str
    target_id: UUID
    start_utc: datetime
    version: int
    catalog_event_id: UUID | None = None


def zone_for(user_id: UUID) -> str:
    """The user's IANA zone, read through `personalization`'s published interface (AD-3).

    **Published**, because `state_notices` needs the same zone to date a notice and a third
    private copy of this fallback would be a third place for it to drift (there is already
    one in `reminder_plan_read`).

    Imported inside the function: `apps.personalization.services.personal_events` imports
    `apps.delivery.services.reminder_plans`, which reaches this module, so a module-level
    import here would close a loop at import time. The call itself is the ordinary published
    seam — `delivery` never touches `apps.personalization.models`.

    Falls back to `DEFAULT_DIGEST_TIMEZONE` rather than guessing: a guessed zone sends a
    reminder at the wrong hour and looks like a bug in the reminder rather than in the guess.
    """
    return _zone_and_delivery_time(user_id)[0]


def _zone_and_delivery_time(user_id: UUID) -> tuple[str, time]:
    """The user's zone **and** their digest delivery time, from one published read.

    **One read, two facts.** They live on the same row — `DigestPreference.timezone` and
    `.delivery_time` — and they are read together because a digest's due time needs both: the
    wall clock says *when*, and the zone says *where*, and neither is meaningful alone.

    The import is function-local for the same reason `zone_for`'s is: a module-level import
    here would close the cycle at import time.

    **Both fall back to the shared constants**, never to a guess. A user with no preference
    row — an account that has not finished onboarding — still gets a coherent answer: the
    default hour in the default zone, which is what their digest would be scheduled at if it
    were minted today.
    """
    from apps.personalization.services.digest_preferences import get_delivery_settings

    settings = get_delivery_settings(user_id=user_id)
    if settings is None:
        return DEFAULT_DIGEST_TIMEZONE, DEFAULT_DIGEST_DELIVERY_TIME
    return settings.timezone, settings.delivery_time


def _guard_not_terminal(row: ScheduledSend) -> None:
    """Every status write passes through here (design D6)."""
    if row.status in ScheduledSend.TERMINAL_STATUSES:
        raise TerminalSendError(f"{row.send_key} is {row.status} and cannot be changed")


def slot_due_at(*, start_utc: datetime, slot: str, zone: str, window) -> datetime | None:
    """When a slot's reminder should actually go out — the post-Quiet-Hours instant.

    **Published, not private**, because the Reminder Plan API has to tell the client the
    same instant this function computes. The picker dims a chip whose delivery falls
    inside Quiet Hours and shows *"Will deliver at 8:00 am Saturday"*; if the browser
    re-implemented the shift, DST and midnight-crossing would be rediscovered there and
    got wrong differently. The server knows; let it say (AD-16, AD-7).

    `None` means the slot has no computable due time — a slot that is neither a named tier
    nor a well-formed custom slot. It is skipped rather than guessed at.

    **The custom slot's offset rides in its id** (`custom:90` — 90 minutes before the
    event), so a custom slot is now computable. It was not: before the picker existed a
    custom slot was stored, listed, and **never minted**.
    """
    offset = slot_offset(slot)
    if offset is None:
        return None
    return shift_to_sendable(start_utc - offset, window=window, zone=zone)


def slot_instant(*, start_utc: datetime, slot: str) -> datetime | None:
    """The instant a slot names — **before** Quiet Hours moves it.

    **This is the fact `slot_at` stores, and the fact a rewrite needs.** `slot_due_at`
    returns the *shifted* instant, and the shift loses the original: a reminder pushed from
    22:30 to 08:00 no longer says it was for 22:30. A quiet-hours write has to re-time a
    deferred row — that is the whole point of it — and it can only do that from the
    unshifted instant.

    `None` means the slot has no computable offset, and the caller skips the row rather
    than guessing at one.
    """
    offset = slot_offset(slot)
    if offset is None:
        return None
    return start_utc - offset


def slot_offset(slot: str) -> timedelta | None:
    """How far before the event a slot fires, or None if the slot has no offset.

    The named tiers' offsets live in `shared.constants.REMINDER_SLOT_OFFSET` (AD-8, one
    literal each). A custom slot's offset is **in its id** — `custom:90` is 90 minutes —
    so there is no second place for the same fact and the two cannot disagree.

    Published, because the read path needs the *unshifted* due instant to decide whether
    the shift moved anything, and it must use the same arithmetic the minting path uses.
    """
    if slot in set(ReminderSlot):
        return REMINDER_SLOT_OFFSET[ReminderSlot(slot)]
    minutes = custom_slot_minutes(slot)
    if minutes is None:
        return None
    return timedelta(minutes=minutes)


def _key_for(target: SendTarget, *, user_id: UUID, slot: str) -> str:
    if target.target_kind == ScheduledSend.Kind.EVENT_REMINDER.value or target.catalog_event_id:
        return event_reminder_key(
            user_id=user_id,
            event_id=target.catalog_event_id or target.target_id,
            slot=slot,
            event_version=target.version,
        )
    return personal_reminder_key(
        user_id=user_id,
        personal_event_id=target.target_id,
        slot=slot,
        personal_event_revision=target.version,
    )


def _kind_for(target: SendTarget) -> str:
    return (
        ScheduledSend.Kind.EVENT_REMINDER.value
        if target.catalog_event_id
        else ScheduledSend.Kind.PERSONAL_REMINDER.value
    )


# ── 1. Minting (the only creating path) ─────────────────────────────────────────


def mint_digest(
    *,
    user_id: UUID,
    local_date: date,
    delivery_time: time,
    zone: str,
    actor: Actor,
    now: datetime,
) -> bool:
    """Create the one Pulse Digest send for this user's local day. Returns whether it did.

    **The digest email is the Pulse Ping** (FR-10, decided 2026-10-31): MVP is email-only,
    so one send carries the digest *and* is the Ping. The separate `pulse_ping` key kind is
    reserved for the Phase 2 push channel and is never minted here.

    **The key is `user_id · digest · local_date`,** so there is exactly one row per user
    per local date — FR-10's "a user with 3 qualifying events receives exactly 1 Pulse
    Ping, not 3" is true by construction rather than by a count. A retried mint finds the
    key and adds nothing; that is what makes the send idempotent the way the composition
    already is.

    **The due time is the user's local delivery time, shifted by Quiet Hours** — computed
    here, once, and stored already shifted (AD-7). The sweep must never re-check it: a
    send deferred twice is a send that never leaves. The quiet window is `delivery`'s own
    row and `shift_to_sendable` is `delivery`'s arithmetic, so both stay here.

    **A digest row has no target.** `target_kind` is empty and `target_id` is `NULL`,
    because the row is about a user and a day rather than an event. That is the shape
    `cancel_pending_digests_for_user` addresses by kind.

    **The stream is BULK, not TRANSACTIONAL** (AD-20). RFC 8058 is not optional on the
    bulk stream: `EmailPort.send` refuses a bulk message with no `unsubscribe_url`, and
    the digest renderer always builds one.

    **The row is minted only when there is something to send.** The decision — FR-10's
    suppression rule — belongs to `apps.delivery.services.pulse_ping`, which asks before
    calling this. A row that exists but is never sent is indistinguishable from a bug,
    and AD-7's whole premise is that a `pending` row is a promise.
    """
    preference = get_preference(user_id=user_id)
    # **Both instants are written, and the pair is the point.** For a digest the unshifted
    # instant is the user's delivery time on that local day — the same instant the key
    # names. A row that carried only `due_at` could not be re-timed, because the shift
    # loses the original.
    slot_at = _local_delivery_instant(local_date=local_date, delivery_time=delivery_time, zone=zone)
    due_at = shift_to_sendable(slot_at, window=preference.quiet_hours, zone=zone)

    send_key = digest_key(user_id=user_id, local_date=local_date)
    with transaction.atomic(using=PERSONAL):
        _, created = ScheduledSend.objects.using(PERSONAL).get_or_create(
            send_key=send_key,
            defaults={
                "user_id": user_id,
                "kind": ScheduledSend.Kind.DIGEST,
                "target_kind": "",
                "target_id": None,
                "slot": "",
                "event_version": None,
                "stream": Stream.BULK.value,
                "slot_at": slot_at,
                "due_at": due_at,
                "status": ScheduledSend.Status.PENDING,
            },
        )

        if created:
            write_audit(
                actor=actor,
                action="scheduled_send.minted",
                target_type="user",
                target_id=user_id,
                details={
                    "count": 1,
                    "kind": ScheduledSend.Kind.DIGEST.value,
                    "local_date": local_date.isoformat(),
                    "at": now.isoformat(),
                },
            )
    return created


def _local_delivery_instant(*, local_date: date, delivery_time: time, zone: str) -> datetime:
    """The user's delivery time on their local date, as an instant.

    **The wall clock is read in the user's zone**, so "9:00 on the 4th" is 9:00 wherever
    the user is, and it survives a DST change the way the stored pair does. `to_instant`
    is `domain.timezones`' own conversion and truncates to whole seconds.

    **The zone falls back to UTC** rather than raising — the same choice
    `digest_scheduling._local_time` makes, and for the same reason: a hand-edited zone
    name must not take down the user's Ping.
    """
    from domain.timezones import to_instant

    try:
        tz = ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        tz = ZoneInfo(DEFAULT_DIGEST_TIMEZONE)
    return to_instant(datetime.combine(local_date, delivery_time).replace(tzinfo=tz))


def mint_for_plan(
    *,
    user_id: UUID,
    target: SendTarget,
    slots: Sequence[str],
    actor: Actor,
    now: datetime,
) -> int:
    """Create the pending rows for one event's Reminder Plan. Returns how many were minted.

    **Quiet Hours is applied here, at compute time** (AD-7), so the stored `due_at` is already
    the true send time and the sweep never re-checks it.

    **A slot whose moment has already passed is not minted** — a 5-day slot on an event three
    days away would otherwise become a row the next sweep fires at once, sending "5 days
    until…" about an event in three days.

    A plan of **0 slots mints nothing and is not an error** (FR-9: "0 slots = no reminders
    (still in feed)").

    Idempotent: a slot whose key already exists is skipped, so a retried mint adds nothing.
    """
    preference = get_preference(user_id=user_id)
    zone = zone_for(user_id)
    minted = 0

    for slot in slots:
        # **Both instants are written, and the pair is the point.** `slot_at` is the instant
        # the slot names; `due_at` is that instant after Quiet Hours. A row that carried
        # only `due_at` could not be re-timed from the slot, because the shift loses the
        # original — so a later quiet-hours change could not move it back.
        slot_at = slot_instant(start_utc=target.start_utc, slot=slot)
        if slot_at is None:
            continue
        due_at = slot_due_at(
            start_utc=target.start_utc, slot=slot, zone=zone, window=preference.quiet_hours
        )
        if due_at is None or due_at <= now:
            continue
        send_key = _key_for(target, user_id=user_id, slot=slot)
        _, created = ScheduledSend.objects.using(PERSONAL).get_or_create(
            send_key=send_key,
            defaults={
                "user_id": user_id,
                "kind": _kind_for(target),
                "target_kind": target.target_kind,
                "target_id": target.target_id,
                "slot": slot,
                "event_version": target.version,
                "stream": Stream.TRANSACTIONAL.value,
                "slot_at": slot_at,
                "due_at": due_at,
                "status": ScheduledSend.Status.PENDING,
            },
        )
        minted += int(created)

    if minted:
        write_audit(
            actor=actor,
            action="scheduled_send.minted",
            target_type=target.target_kind,
            target_id=target.target_id,
            details={"count": minted, "slots": list(slots), "at": now.isoformat()},
        )
    return minted


def mint_state_notice(
    *,
    user_id: UUID,
    event_id: UUID,
    state_change_id: UUID,
    event_start_utc: datetime | None,
    actor: Actor,
    now: datetime,
) -> bool:
    """Create the email send for one FR-54 state-change notice. Returns whether it did.

    **The key is AD-7's, unchanged**: `user_id · state_notice · state_change_id`. One send
    per user per state change, so a propagation retried after a partial run adds nothing.
    The one-per-day cap is **not** expressed here and must not be — re-keying it on
    `(event, local_date)` would make a cancellation collide with a sold-out minted earlier
    the same day and be dropped as a duplicate. The cap belongs to
    `services.state_notices`, which resolves it by `domain.lifecycle.PRECEDENCE`.

    **The stream is TRANSACTIONAL** (AD-20), and `ScheduledSend.stream` has no default
    precisely so this is a decision rather than an inheritance. A state notice is a one-time
    correction about a record the user created themselves, sent because the facts under it
    moved — not a broadcast. It therefore carries **no RFC 8058 unsubscribe URL**: that is a
    requirement of the *bulk* stream, `EmailPort.send` refuses a bulk message without one,
    and the opt-out here is the per-event mute rather than a list unsubscribe.

    **`slot_at` is null, and Quiet Hours still apply.** A state notice has no slot — its
    moment is *now*, not an offset from the event's start — but `shift_to_sendable` takes
    any aware instant, so the quiet window defers it like anything else. The null means
    "no slot", and it is also what makes a later preference change skip this row: the
    unshifted instant is the change itself, which is in the past and never moves.

    **Except when the deferral would outlast the message.** Decided at capture
    (2026-11-04): Quiet Hours apply unless the shift would push the notice past the point of
    being useful. "Past the event's start" is the obvious predicate and the wrong one — a
    notice landing ninety seconds before the doors open is technically in time and no use at
    all. The margin is `REMINDER_SLOT_OFFSET[ReminderSlot.ONE_HOUR]`, reused rather than
    invented (AD-8: a threshold lives in one place): the `1hr` slot is already this
    project's statement of the last moment a message about an event is still worth sending,
    being the tightest reminder a user can choose. A notice that cannot beat the `1hr`
    reminder is not actionable either, so it goes out now instead.

    An event that starts *inside* the user's quiet window therefore always notifies
    immediately: every deferral available is already too late.

    `event_start_utc` is None when the catalog no longer holds the event — a supersede, or a
    source that dropped it. There is then no start to be late for, and the quiet window
    applies unconditionally.
    """
    preference = get_preference(user_id=user_id)
    zone = zone_for(user_id)
    due_at = shift_to_sendable(now, window=preference.quiet_hours, zone=zone)
    if event_start_utc is not None:
        latest_useful = event_start_utc - REMINDER_SLOT_OFFSET[ReminderSlot.ONE_HOUR]
        if due_at > latest_useful:
            # The window would hold it past the point of being worth sending. The
            # correction matters more than the quiet night.
            due_at = now

    send_key = state_notice_key(user_id=user_id, state_change_id=state_change_id)
    with transaction.atomic(using=PERSONAL):
        _, created = ScheduledSend.objects.using(PERSONAL).get_or_create(
            send_key=send_key,
            defaults={
                "user_id": user_id,
                "kind": ScheduledSend.Kind.STATE_NOTICE,
                "target_kind": ReminderPlan.TargetKind.SAVED_EVENT.value,
                "target_id": event_id,
                "slot": "",
                "event_version": None,
                "stream": Stream.TRANSACTIONAL.value,
                # No slot, so no pre-shift instant to re-shift later. See the docstring.
                "slot_at": None,
                "due_at": due_at,
                "status": ScheduledSend.Status.PENDING,
            },
        )
        if created:
            write_audit(
                actor=actor,
                action="scheduled_send.minted",
                target_type=ReminderPlan.TargetKind.SAVED_EVENT.value,
                target_id=event_id,
                details={
                    "count": 1,
                    "kind": ScheduledSend.Kind.STATE_NOTICE.value,
                    "state_change_id": str(state_change_id),
                    "deferred": due_at != now,
                    "at": now.isoformat(),
                },
            )
    return created


def cancel_state_notice_sends(
    *,
    state_change_ids: Sequence[UUID],
    user_id: UUID,
    actor: Actor,
    now: datetime,
) -> int:
    """Cancel the pending emails of state notices that a newer notice superseded.

    **Here rather than in `state_notices`, because AD-7 has one writer.** The notice module
    owns `STATE_CHANGE_NOTICE` and decides *which* notices lose to a more important change;
    it does not get to write the schedule, or the schedule has two rule sets — one that
    mints and one that cancels — and `tests/architecture/test_schedule_writes.py` exists to
    stop exactly that.

    **The keys come from `send_keys`.** A second spelling of AD-7's key in a caller would
    cancel nothing the day the key changed, silently, because a filter matching no rows
    raises nothing.

    **Only `pending` rows.** A sent email cannot be taken back, and marking it cancelled
    would make the ledger lie about what the user received.
    """
    if not state_change_ids:
        return 0
    keys = [
        state_notice_key(user_id=user_id, state_change_id=state_change_id)
        for state_change_id in state_change_ids
    ]
    cancelled = (
        ScheduledSend.objects.using(PERSONAL)
        .filter(
            user_id=user_id,
            kind=ScheduledSend.Kind.STATE_NOTICE,
            status=ScheduledSend.Status.PENDING,
            send_key__in=keys,
        )
        .update(status=ScheduledSend.Status.CANCELLED, updated_at=now)
    )
    if cancelled:
        write_audit(
            actor=actor,
            action="scheduled_send.cancelled",
            target_type="user",
            target_id=user_id,
            details={
                "count": cancelled,
                "kind": ScheduledSend.Kind.STATE_NOTICE.value,
                "reason": "superseded_notice",
                "at": now.isoformat(),
            },
        )
    return cancelled


# ── 2. Rewriting (never mints, never cancels) ───────────────────────────────────


def reschedule_pending_for_user(*, user_id: UUID, actor: Actor, now: datetime) -> int:
    """Recompute `due_at` on this user's `pending` rows after a preference change.

    Quiet hours, timezone, delivery time, tier — AD-7: these *"rewrite `due_at` on `pending`
    rows only and never touch the key, so a recompute can never produce a second send."*

    **This function cannot mint.** It has no create path, which is asserted structurally by
    `test_the_reschedule_path_has_no_create_call`. `sent`, `cancelled` and `failed` rows are
    untouched: they are facts, not schedules.

    The zone is read **once**, not once per row (design D4).

    **The rewrite is one arithmetic, applied to every row.** A row carries two instants:
    `slot_at`, the instant it was *for*, and `due_at`, the instant it *goes out*. The two
    differ by exactly one thing — the Quiet Hours shift — so re-timing a row is
    `shift_to_sendable(slot_at, window, zone)` and nothing else.

    **That uniformity is the point, and it is why `slot_at` exists.** A row carries two
    instants: `slot_at`, the instant it was *for*, and `due_at`, the instant it *goes out*.
    The two differ by exactly one thing — the Quiet Hours shift — so re-timing a row is
    `shift_to_sendable(slot_at, window, zone)` and nothing else.

    **A reminder's `slot_at` is its slot before the shift** (`event_start - offset`), and it
    stays put when the delivery time changes — a reminder is about an event, not about a
    clock. **A digest's `slot_at` is its local delivery instant**, and it *moves* when the
    delivery time changes: the digest is about a time of day. So a digest's pre-shift
    instant is rebuilt from **its local date** — which is in its key, and is immutable —
    and the *current* delivery time.

    **The alternative to keeping `slot_at` is deriving the pre-shift instant from the
    stored `due_at` as `due_at + offset`, and that compounds the deferral**: a row already
    pushed from 22:30 to 08:00 reads as one that was for 09:00, and re-shifting that lands
    on the wrong hour again. **The whole point of a Quiet Hours write is to move a deferred
    row**, so the pre-shift instant has to be kept, not reconstructed.

    **The rewrite reads the user's calendar not at all.** The row holds the instant, so
    there is nothing to look up: the zone is read once, the rows are read once, and the
    work is O(rows) with **no query per row and no query per event**.
    """
    preference = get_preference(user_id=user_id)
    zone, delivery_time = _zone_and_delivery_time(user_id)
    rewritten = 0

    with transaction.atomic(using=PERSONAL):
        rows = (
            ScheduledSend.objects.using(PERSONAL)
            .select_for_update()
            .filter(user_id=user_id, status=ScheduledSend.Status.PENDING)
        )
        for row in rows:
            _guard_not_terminal(row)
            if row.kind == ScheduledSend.Kind.DIGEST:
                due_at = _digest_due_at(
                    row=row,
                    delivery_time=delivery_time,
                    zone=zone,
                    window=preference.quiet_hours,
                )
            elif row.slot_at is None:
                # **A row with no `slot_at` has no pre-shift instant to re-shift** — a
                # `state_notice`, whose unshifted instant is the moment the change happened
                # rather than an offset from the event. Quiet Hours *did* apply when it was
                # minted; what it lacks is a slot. That moment is in the past and never
                # moves, so a preference change has nothing to recompute here, and skipping
                # is the right answer rather than a guess.
                continue
            else:
                due_at = shift_to_sendable(row.slot_at, window=preference.quiet_hours, zone=zone)
            if due_at is None or due_at == row.due_at:
                continue
            row.due_at = due_at
            row.save(using=PERSONAL, update_fields=["due_at", "updated_at"])
            rewritten += 1

        if rewritten:
            write_audit(
                actor=actor,
                action="scheduled_send.rescheduled",
                target_type="user",
                target_id=user_id,
                details={"count": rewritten, "at": now.isoformat()},
            )
    return rewritten


def _digest_due_at(
    *,
    row: ScheduledSend,
    delivery_time: time,
    zone: str,
    window: QuietHours | None,
) -> datetime | None:
    """A pending digest's due time, recomputed — or `None` if it cannot be recomputed.

    **The local date comes out of the key.** A digest row is about a user and a *day*, and
    the day is named in the key — `user_id · digest · local_date` — and nowhere else: `slot`
    is empty and `target_id` is `NULL`. The date is immutable (a digest is about one day),
    so it is parsed back out of the key by `send_keys.digest_local_date_from_key`, the
    inverse of the builder that wrote it. **The parser lives beside the builder**, because a
    key shape parsed in two places is a key shape that will be parsed wrongly in one of them.

    **The time of day is the *current* delivery time** — that is what a delivery-time change
    is for — and the date is the one the key names. So the digest moves to 07:00 on the day
    it was always going to be, and never to a different day.

    **`None` means "this digest's day cannot be read"**, and the row is skipped rather than
    re-timed to a guessed day. A digest moved to the wrong date is a digest that goes out on
    the wrong day.

    **The arithmetic is `mint_digest`'s**, unchanged: the user's delivery time on that local
    date, in their zone, shifted by Quiet Hours. Same functions, same order — so the rewritten
    time and a freshly minted time cannot disagree.
    """
    local_date = digest_local_date_from_key(row.send_key)
    if local_date is None:
        return None
    return shift_to_sendable(
        _local_delivery_instant(local_date=local_date, delivery_time=delivery_time, zone=zone),
        window=window,
        zone=zone,
    )


# ── 3. Cancelling ───────────────────────────────────────────────────────────────


def cancel_sends_for_targets(
    *,
    user_id: UUID,
    targets: Sequence[tuple[str, UUID]],
    actor: Actor,
    now: datetime,
) -> int:
    """Cancel this user's `pending` rows for the given `(target_kind, target_id)` pairs.

    Un-saving an event, deleting a personal event, unsubscribing, closing an account. Only
    `pending` rows move: a `sent` row is a fact about an email that already went out.
    """
    if not targets:
        return 0

    cancelled = 0
    with transaction.atomic(using=PERSONAL):
        for target_kind, target_id in targets:
            rows = (
                ScheduledSend.objects.using(PERSONAL)
                .select_for_update()
                .filter(
                    user_id=user_id,
                    target_kind=target_kind,
                    target_id=target_id,
                    status=ScheduledSend.Status.PENDING,
                )
            )
            for row in rows:
                _guard_not_terminal(row)
                row.status = ScheduledSend.Status.CANCELLED
                row.save(using=PERSONAL, update_fields=["status", "updated_at"])
                cancelled += 1

        if cancelled:
            write_audit(
                actor=actor,
                action="scheduled_send.cancelled",
                target_type="user",
                target_id=user_id,
                details={"count": cancelled, "at": now.isoformat()},
            )
    return cancelled


def cancel_pending_digests_for_user(
    *,
    user_id: UUID,
    actor: Actor,
    now: datetime,
) -> int:
    """Cancel this user's `pending` digest rows.

    **By kind, because a digest row has no target.** `ScheduledSend.target_id` is `NULL` for
    a digest and `target_kind` is empty — the row is about a user and a day, not an event —
    so `cancel_sends_for_targets`, which matches on a target pair, cannot address one.

    **This is a second cancellation path, and it lives here so that there is only one
    writer.** The alternative was a `cancel_sends_for_targets` that also reached
    target-less rows, which would change a command four other callers depend on for the
    benefit of one new caller. The rule the module exists to keep is that **every status
    write on `SCHEDULED_SEND` happens in this module**, and the shape of the row is a
    reason for a second *command*, never for a second *writer*.

    Only `pending` rows move: a `sent` row is a fact about an email that already went out,
    and unsubscribing now does not un-send it. The filter says so before the write, so the
    terminal-state guard cannot fire here.
    """
    with transaction.atomic(using=PERSONAL):
        rows = (
            ScheduledSend.objects.using(PERSONAL)
            .select_for_update()
            .filter(
                user_id=user_id,
                kind=ScheduledSend.Kind.DIGEST,
                status=ScheduledSend.Status.PENDING,
            )
        )
        cancelled = 0
        for row in rows:
            _guard_not_terminal(row)
            row.status = ScheduledSend.Status.CANCELLED
            row.save(using=PERSONAL, update_fields=["status", "updated_at"])
            cancelled += 1

        if cancelled:
            write_audit(
                actor=actor,
                action="scheduled_send.cancelled",
                target_type="user",
                target_id=user_id,
                details={"count": cancelled, "kind": "digest", "at": now.isoformat()},
            )
    return cancelled


# ── 4. Lifecycle (AD-17) ────────────────────────────────────────────────────────


def apply_lifecycle_change(
    *,
    user_id: UUID,
    target: SendTarget,
    kind: str,
    slots: Sequence[str],
    actor: Actor,
    now: datetime,
) -> dict[str, int]:
    """Apply one event state change to one user's sends (AD-17's `delivery` half).

    **Versioned and idempotent.** Only rows whose working `event_version` is *below* the
    change's version are cancelled, and minting is skipped when a row already carries the
    change's version. So:

    - a **re-run** finds nothing below the version and nothing to mint — a no-op;
    - an **older** change arriving after a newer one is a no-op;
    - a **partial run** that is retried completes without losing a row.

    That guard is not decoration. Without it, a re-run would cancel the rows it just minted,
    then fail to re-mint them against their now-spent keys, and the user would be left with
    **no pending reminder at all** — a reminder silently deleted by a retry.

    Not wired to `propagate_state_change` yet; see the module docstring.
    """
    behaviour = LIFECYCLE_SEND_BEHAVIOUR[kind]
    result = {"cancelled": 0, "minted": 0, "restamped": 0}

    with transaction.atomic(using=PERSONAL):
        # **The staleness gate, and it has to come first.** AD-17 applies a change "only if"
        # its version exceeds what the user already has. Cancelling stale rows is not enough
        # on its own: an older change would cancel nothing (correctly) and then still *mint*
        # its own rows, because its key differs from the newer one already pending. The user
        # would end up with reminders for two different versions of one event.
        already = (
            ScheduledSend.objects.using(PERSONAL)
            .filter(
                user_id=user_id,
                target_kind=target.target_kind,
                target_id=target.target_id,
                status=ScheduledSend.Status.PENDING,
                event_version__gte=target.version,
            )
            .exists()
        )
        if already:
            return result

        stale = (
            ScheduledSend.objects.using(PERSONAL)
            .select_for_update()
            .filter(
                user_id=user_id,
                target_kind=target.target_kind,
                target_id=target.target_id,
                status=ScheduledSend.Status.PENDING,
                event_version__lt=target.version,
            )
        )

        if behaviour is LifecycleSendBehaviour.KEEP:
            # Sold out or a detail change: the event still happens, so a user who saved it
            # still wants their reminder. Only the working version is re-stamped.
            #
            # **And the propagation hold is released here** (AD-17). A row the sweep held
            # because the catalog had moved ahead is released by clearing `held_at`; the next
            # sweep claims and sends it. `REMINT` and `CANCEL` need no equivalent — a re-minted
            # row is born unheld and a cancelled one is terminal.
            #
            # **`due_at` is deliberately not recomputed.** Only `sold_out` and `detail_changed`
            # map to `KEEP`, and a time change is always its own `time_moved` row (one state
            # change per kind — `event_writes.py`), which is `REMINT`. So a `KEEP` change never
            # moved the event, `due_at` is still the right instant, and re-timing it would move
            # a reminder that nothing moved. The row is past due, so it goes out slightly late:
            # the correct outcome for a send paused to verify it was still true.
            for row in stale:
                row.event_version = target.version
                row.held_at = None
                row.save(using=PERSONAL, update_fields=["event_version", "held_at", "updated_at"])
                result["restamped"] += 1
        else:
            for row in stale:
                _guard_not_terminal(row)
                row.status = ScheduledSend.Status.CANCELLED
                row.save(using=PERSONAL, update_fields=["status", "updated_at"])
                result["cancelled"] += 1

        if behaviour is LifecycleSendBehaviour.REMINT:
            result["minted"] = mint_for_plan(
                user_id=user_id, target=target, slots=slots, actor=actor, now=now
            )

        if any(result.values()):
            write_audit(
                actor=actor,
                action="scheduled_send.lifecycle_applied",
                target_type=target.target_kind,
                target_id=target.target_id,
                details={"kind": kind, "version": target.version, **result, "at": now.isoformat()},
            )
    return result


__all__ = [
    "SendTarget",
    "resync_plan",
    "TerminalSendError",
    "apply_lifecycle_change",
    "cancel_pending_digests_for_user",
    "cancel_sends_for_targets",
    "cancel_state_notice_sends",
    "mint_digest",
    "mint_for_plan",
    "mint_state_notice",
    "reschedule_pending_for_user",
    "slot_due_at",
    "slot_offset",
    "zone_for",
]


def resync_plan(
    *,
    user_id: UUID,
    target: SendTarget,
    slots: Sequence[str],
    actor: Actor,
    now: datetime,
) -> dict[str, int]:
    """Make this event's pending sends match a just-saved Reminder Plan, atomically.

    A plan edit is a **preference change** (design D1), not a lifecycle change: the event has
    not moved, so the keys of surviving slots are unchanged and only the set of slots differs.
    The honest implementation is therefore "cancel what is no longer chosen, mint what is newly
    chosen" — not a cancel-everything-and-re-mint, which would spend the keys of slots the user
    kept and leave them unable to be re-minted.

    Called from inside `reminder_plans`' transaction, so a plan that saves and sends that do
    not cannot both be true. `mint_for_plan`'s own `get_or_create` makes the kept slots no-ops.
    """
    chosen = set(slots)
    cancelled = 0

    with transaction.atomic(using=PERSONAL):
        dropped = (
            ScheduledSend.objects.using(PERSONAL)
            .select_for_update()
            .filter(
                user_id=user_id,
                target_kind=target.target_kind,
                target_id=target.target_id,
                status=ScheduledSend.Status.PENDING,
            )
            .exclude(slot__in=chosen)
        )
        for row in dropped:
            _guard_not_terminal(row)
            row.status = ScheduledSend.Status.CANCELLED
            row.save(using=PERSONAL, update_fields=["status", "updated_at"])
            cancelled += 1

        minted = mint_for_plan(user_id=user_id, target=target, slots=slots, actor=actor, now=now)

    return {"cancelled": cancelled, "minted": minted}
