"""Applying an unsubscribe, and cancelling what it stops (FR-11, FR-10, AD-7, AD-16).

**Two scopes, two commands, two places the state lives.** FR-11: a reminder's link stops
*that event's* reminders; the digest's link stops *the Pulse Ping*. They are different user
decisions about different things, and one never touches the other.

| scope | state lives on | what it stops |
|---|---|---|
| `event_reminders` | the event's `ReminderPlan` (zero slots) | that event's reminder sends |
| `pulse_ping` | `NotificationPreference.pulse_ping_unsubscribed` | the digest sends |

---

## Why the event scope is a zero-slot plan

A reminder's unsubscribe is **per event**, so it cannot be a flag on the user's preference
row — one event's reminders can be off while another event's are on. The natural home is the
`ReminderPlan`, which is already per `(user_id, target_kind, target_id)`, is already owned by
`delivery` (AD-16), and already holds the slots.

And **a zero-slot plan is already a valid state** — FR-9: "0 slots = no reminders (still in
feed)", the user's own "No reminders. You'll still see this event in Pulse Digest." So
"unsubscribed from this event's reminders" and "no reminders on this event" are **the same
fact**, and that is exactly right, because they are the same thing. One representation, not
two.

---

## Cancelling the pending sends, not swallowing them

**Unsubscribing cancels that scope's pending sends through the minting service**, rather than
leaving rows that are swallowed at send time. A row left pending would be claimed by the
sweep, rendered, and sent — and the user would receive the very mail they just turned off.
The alternative, filtering at send time, would mean the schedule still held a promise the
user had withdrawn.

The cancellation for the **event** scope goes through `cancel_sends_for_targets`, and the
cancellation for the **Ping** scope goes through `cancel_pending_digests_for_user`. Both
live in `scheduled_sends.py`, which is the single writer of `SCHEDULED_SEND` — **every
status write on that table happens in that module**, and this one writes none.

**Two commands, because the rows have two shapes.** A reminder row is addressed by its
`(target_kind, target_id)` pair, so `cancel_sends_for_targets` can cancel it. A **digest**
row has no target — `ScheduledSend.target_id` is `NULL` and `target_kind` is empty,
because the row is about a user and a day rather than an event — and so it cannot be
addressed that way. The digest cancellation is by **kind**, and it is a second *command*
rather than a second *writer*: the alternative would have been to widen
`cancel_sends_for_targets` to reach target-less rows, which changes a command four other
callers depend on for the benefit of one new caller.

**The cancellation is in the same transaction as the state change.** A plan emptied without
its sends cancelled leaves reminders for an event the user has turned off, and nothing would
ever come back to clean them up.

---

## The Ping scope cancels the digest sends, and nothing else

The Pulse Ping is a **per-user** scope, so its pending sends are the digest rows — every
`pending` row of kind `digest` for that user.

**It touches no reminder plan.** The two scopes are separate rows, separate commands and
separate cancellations, and a test asserts that unsubscribing from the Ping leaves every
reminder plan exactly as it was.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db import transaction

from apps.delivery.models import NotificationPreference, ReminderPlan
from apps.delivery.services.audit import write_audit
from apps.delivery.services.notification_preferences import get_preference
from apps.delivery.services.scheduled_sends import (
    cancel_pending_digests_for_user,
    cancel_sends_for_targets,
)
from shared.actor import Actor
from shared.db import PERSONAL


@dataclass(frozen=True)
class UnsubscribeResult:
    """What one unsubscribe changed.

    Counts only, and ids — never an address and never a title (AD-13). The audit row the
    command writes carries the same things.
    """

    scope: str
    #: The event the unsubscribe was about, for the event scope. `None` for the Ping.
    target_id: UUID | None
    #: How many pending sends were cancelled.
    cancelled: int
    #: Whether the state actually changed. Unsubscribing twice is a no-op, not an error.
    changed: bool

    @property
    def already_unsubscribed(self) -> bool:
        """Whether the scope was already off when this call arrived."""
        return not self.changed


def unsubscribe_event_reminders(
    *,
    user_id: UUID,
    target_id: UUID,
    actor: Actor,
    now: datetime,
) -> UnsubscribeResult:
    """Stop this event's reminders, and cancel their pending sends.

    **The event scope, and only the event scope.** The Pulse Ping is untouched — the user's
    daily digest keeps arriving, because they asked to stop *this event's* reminders and not
    everything. That distinction is FR-11's whole point, and it has its own test.

    A user who never had a plan for this event is not an error: there was nothing to stop,
    and the answer says so.

    **The plan is found by `(user_id, target_id)`, and the plan's own `target_kind` is
    used.** The signed token names the event, and the event's id is enough to find the
    plan — and the plan is the thing that knows whether it is about a personal event or a
    saved public event. So the kind is *read*, never carried in the token and never
    inferred: a token that named the kind would be a second place for that fact to live,
    and the two could disagree.

    Args:
        user_id: whose reminders stop.
        target_id: the event.
        actor: for the audit row.
        now: the moment, for the audit row.

    Returns:
        What changed.
    """
    with transaction.atomic(using=PERSONAL):
        plan = (
            ReminderPlan.objects.using(PERSONAL)
            .select_for_update()
            .filter(user_id=user_id, target_id=target_id)
            .first()
        )

        if plan is None:
            # No plan, so no reminders, so nothing to stop. Not an error: the user reached
            # the link from a mail about an event whose plan has since been removed.
            return UnsubscribeResult(
                scope="event_reminders", target_id=target_id, cancelled=0, changed=False
            )

        if not plan.slots:
            # Already off. Unsubscribing twice is a no-op, and saying "changed" when
            # nothing changed would make the caller think it had done something.
            return UnsubscribeResult(
                scope="event_reminders", target_id=target_id, cancelled=0, changed=False
            )

        plan.slots = []
        plan.save(using=PERSONAL, update_fields=["slots", "updated_at"])

        # The pending sends go **in this transaction**. A plan emptied without its sends
        # cancelled leaves reminders that the sweep would still deliver — the user would get
        # the mail they just turned off.
        cancelled = cancel_sends_for_targets(
            user_id=user_id,
            targets=[(plan.target_kind, target_id)],
            actor=actor,
            now=now,
        )

        write_audit(
            actor=actor,
            action="unsubscribe.event_reminders",
            target_type=plan.target_kind,
            target_id=target_id,
            details={"cancelled": cancelled, "at": now.isoformat()},
        )

        return UnsubscribeResult(
            scope="event_reminders", target_id=target_id, cancelled=cancelled, changed=True
        )


def unsubscribe_pulse_ping(
    *,
    user_id: UUID,
    actor: Actor,
    now: datetime,
) -> UnsubscribeResult:
    """Stop the Pulse Ping, and cancel the pending digest sends.

    **The Ping scope, and only the Ping scope.** No reminder plan is read and none is
    written — the user asked to stop the daily digest, not their event reminders. That
    distinction is FR-11's whole point, and it has its own test.

    Unsubscribing twice is a no-op, not an error.
    """
    with transaction.atomic(using=PERSONAL):
        # `get_preference` creates the row with the defaults if it is missing, and takes
        # the advisory lock while it does — the same lazy creation every other read of
        # this row uses.
        get_preference(user_id=user_id)

        row = (
            NotificationPreference.objects.using(PERSONAL)
            .select_for_update()
            .filter(user_id=user_id)
            .first()
        )
        if row is None:  # pragma: no cover - `get_preference` just created it
            return UnsubscribeResult(scope="pulse_ping", target_id=None, cancelled=0, changed=False)

        if row.pulse_ping_unsubscribed:
            return UnsubscribeResult(scope="pulse_ping", target_id=None, cancelled=0, changed=False)

        row.pulse_ping_unsubscribed = True
        row.save(
            using=PERSONAL,
            # `updated_at` is auto_now, and Django only writes it when update_fields names
            # it — otherwise the timestamp silently never advances. Same as
            # `notification_preferences.set_quiet_hours`.
            update_fields=["pulse_ping_unsubscribed", "updated_at"],
        )

        # The pending **digest** sends for this user, and only those. A digest row has no
        # target — it is about a user and a day — so the cancellation is by kind, and it
        # goes through the module that owns every status write on `SCHEDULED_SEND`.
        cancelled = cancel_pending_digests_for_user(user_id=user_id, actor=actor, now=now)

        write_audit(
            actor=actor,
            action="unsubscribe.pulse_ping",
            target_type="user",
            target_id=user_id,
            details={"cancelled": cancelled, "at": now.isoformat()},
        )

        return UnsubscribeResult(
            scope="pulse_ping", target_id=None, cancelled=cancelled, changed=True
        )


def pulse_ping_unsubscribed(*, user_id: UUID) -> bool:
    """Whether the user has turned the Pulse Ping off.

    **A read that creates nothing.** It looks the row up and answers `False` when there is
    none — a user who has never opened settings has not unsubscribed, and asking the
    question must not be the thing that creates their preferences.
    """
    row = NotificationPreference.objects.using(PERSONAL).filter(user_id=user_id).first()
    return bool(row and row.pulse_ping_unsubscribed)


__all__ = [
    "UnsubscribeResult",
    "pulse_ping_unsubscribed",
    "unsubscribe_event_reminders",
    "unsubscribe_pulse_ping",
]
