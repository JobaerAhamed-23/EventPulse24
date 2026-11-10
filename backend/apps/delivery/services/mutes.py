"""The per-event notice mute (FR-55): one user silencing state-change notices for one event.

`delivery` owns `EVENT_NOTICE_MUTE` (AD-16). `personalization` never writes it — the Detail
screen's toggle reaches it through this module, the way every other cross-module write in
this tree does.

**What a mute silences, and what it does not.** It stops FR-54's "this changed" message —
the email and the in-app notice together. It does **not** touch the event: reminders still
fire on the user's Reminder Plan, and the event still places in the Pulse Digest. A user who
mutes is saying "I know, stop telling me", not "remove this from my life".

**There is no global off switch**, and that is a decision rather than an omission (taken at
capture, 2026-11-04). FR-54's notices are the mechanism that keeps reminders *correct*: a
reminder for an event that moved is wrong, and the notice is what says so. A user who
silenced every notice would be opting into wrong reminders without being told that is what
they had chosen. A per-event mute is a judgement about one event the user is looking at,
which is a thing they can actually make.

**A terminal change is raised anyway.** `state_notices.raise_state_notice` ignores the mute
for `cancelled` and `superseded`. That asymmetry is argued there and in
`EventNoticeMute`'s own docstring; in short, FR-55 has already pulled a cancelled event out
of the digest, so silence about it is the one failure with no second channel to catch it.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db import transaction

from apps.delivery.models import EventNoticeMute
from apps.delivery.services.audit import write_audit
from shared.actor import Actor
from shared.db import PERSONAL


@dataclass(frozen=True)
class MuteResult:
    """The outcome of a mute or unmute.

    `changed` says whether this call did anything. The API needs it: muting an already-muted
    event is a success, not an error, but a response that claimed a change when none happened
    would make the screen redraw something that did not move.
    """

    event_id: UUID
    muted: bool
    changed: bool


def mute_event_notices(*, user_id: UUID, event_id: UUID, actor: Actor, now: datetime) -> MuteResult:
    """Silence FR-54 notices for one event. Idempotent.

    **No existence check on the event.** The id names a row in `catalog`, which this module
    may not read in a write transaction (AD-3), and a mute for an event that has since gone
    is harmless: it silences nothing and is purged with the user's data. Requiring the event
    to exist would also make the mute fail in exactly the case a user most wants it — an
    event mid-supersede.
    """
    with transaction.atomic(using=PERSONAL):
        _, created = EventNoticeMute.objects.using(PERSONAL).get_or_create(
            user_id=user_id, event_id=event_id
        )
        if created:
            write_audit(
                actor=actor,
                action="event_notice_mute.muted",
                target_type="event",
                target_id=event_id,
                details={"at": now.isoformat()},
            )
    return MuteResult(event_id=event_id, muted=True, changed=created)


def unmute_event_notices(
    *, user_id: UUID, event_id: UUID, actor: Actor, now: datetime
) -> MuteResult:
    """Let FR-54 notices through again for one event. Idempotent.

    **Unmuting does not replay what was silenced.** The notices suppressed while the mute
    was on are gone, and raising them now would deliver a correction about a change the user
    has had days to notice — the "calm" in FR-54 cut against. The event's current state is
    on its Detail screen, which is where a user who just unmuted is standing.
    """
    with transaction.atomic(using=PERSONAL):
        deleted, _ = (
            EventNoticeMute.objects.using(PERSONAL)
            .filter(user_id=user_id, event_id=event_id)
            .delete()
        )
        if deleted:
            write_audit(
                actor=actor,
                action="event_notice_mute.unmuted",
                target_type="event",
                target_id=event_id,
                details={"at": now.isoformat()},
            )
    return MuteResult(event_id=event_id, muted=False, changed=bool(deleted))


def is_muted(*, user_id: UUID, event_id: UUID) -> bool:
    """Whether this user has silenced notices for this event."""
    return (
        EventNoticeMute.objects.using(PERSONAL).filter(user_id=user_id, event_id=event_id).exists()
    )


def muted_event_ids(*, user_id: UUID, event_ids: set[UUID]) -> set[UUID]:
    """Which of `event_ids` this user has muted — one query, not one per event.

    Published for the read surfaces: the Detail screen asks about one event, but a list that
    renders a mute control per row would otherwise cost a query per row.
    """
    if not event_ids:
        return set()
    return set(
        EventNoticeMute.objects.using(PERSONAL)
        .filter(user_id=user_id, event_id__in=event_ids)
        .values_list("event_id", flat=True)
    )


__all__ = [
    "MuteResult",
    "is_muted",
    "mute_event_notices",
    "muted_event_ids",
    "unmute_event_notices",
]
