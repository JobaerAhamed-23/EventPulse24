"""An editor's reject, and its reversal (design: event-rejection-state D1, D2, D8, D10).

FR-57 calls Reject "deletes from registry". It is a **soft reject**: the Event is never
deleted, its `Event.Status` is never touched, and only `publication_status` moves. That
matches a codebase that pauses sources rather than removing them and keeps
`EventStateChange` append-only.

**A reject is two things, and this module exists because neither works alone.**

1. `publication_status = rejected` makes the Event invisible. Every public read filters
   `publication_status == published` by equality, so it leaves all of them at once with no
   read changed — but it bumps no version and writes no row, so it reaches *nobody*.
2. An `EventStateChange(kind=delisted)` reaches the people who saved it. It rides the
   AD-17 outbox, which is the only fan-out across the schema wall, and
   `LIFECYCLE_SEND_BEHAVIOUR` cancels their pending reminders.

Without (1) the event stays listed. Without (2) a saver keeps getting "your event is in 3
hours" for a listing editorial ruled bad.

**No notice email is sent** — `domain.notices.UNNOTIFIED_KINDS` carries the reasoning.
The saver's card falls back to "event no longer available", the same path a superseded or
unpublished event takes.

**This module owns the state transition, not the verdict.** Closing the `ReviewItem`,
recording the resolution and raising the FR-16 observation belong to the editorial
commands, which call these two functions.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.ingestion.models import Event, EventStateChange
from apps.ingestion.services.audit import write_audit
from apps.ingestion.services.event_writes import apply_publication_change
from domain.errors import ValidationError
from shared.actor import Actor, ActorKind
from shared.db import CATALOG


@dataclass(frozen=True)
class PublicationResult:
    event: Event
    change: EventStateChange | None
    applied: bool


def _editor(actor: Actor) -> None:
    """Refuse anything but a signed-in human.

    **AD-14: every editorial action is attributed.** A reject is a judgement, and a
    judgement needs someone's name on it — the audit row and the `EventStateChange` both
    carry the actor. Letting `Actor.system(...)` through would mean a scheduled job could
    pull an event from the catalogue, or silently reverse an editor who pulled one, with
    nothing in the log but a label.

    This is the same rule `ReviewItem`'s D6 check holds at the database level for a
    resolution: a verdict cannot be recorded by a job.
    """
    if actor.kind is not ActorKind.USER:
        raise ValidationError(
            "An editorial publication change needs a user actor.",
            details={"errors": ["actor_must_be_user"]},
        )


def _load(event_id: UUID) -> Event:
    """Read the Event for update, inside the command's transaction.

    **`select_for_update` because the version is computed in Python.** Two editors acting on
    one event at the same moment would both read version N and both write N+1; the second
    `EventStateChange` would then collide on `state_change_version_uq` and the command would
    fail with a database error instead of doing the obvious thing. The lock makes the second
    editor wait, see `rejected`, and return `applied=False` — the idempotent path.
    """
    event = Event.objects.using(CATALOG).select_for_update().filter(pk=event_id).first()
    if event is None:
        raise ValidationError("No such Event.", details={"errors": ["event_not_found"]})
    if event.status == Event.Status.SUPERSEDED:
        # The trigger would refuse the write anyway; refusing here names the reason.
        # A superseded Event was replaced by a different one and is terminal (AD-4).
        raise ValidationError(
            "A superseded Event cannot change publication state.",
            details={"errors": ["event_superseded"]},
        )
    return event


def reject_event(*, event_id: UUID, actor: Actor, now: datetime | None = None) -> PublicationResult:
    """Reject a listing: hide it, and cancel its savers' reminders. FR-57.

    **Idempotent.** Rejecting an already-rejected Event applies nothing and returns
    `applied=False`, rather than bumping the version and sending a second `delisted`
    through the outbox to every saver for no reason.

    The Event is never deleted and its `Event.Status` is untouched — a duplicate or
    wrong-venue reject says nothing about whether the event happens in the world.
    """
    _editor(actor)
    now = now or timezone.now()

    with transaction.atomic(using=CATALOG):
        event = _load(event_id)
        if event.publication_status == Event.PublicationStatus.REJECTED:
            return PublicationResult(event=event, change=None, applied=False)

        previous = event.publication_status
        change = apply_publication_change(
            event=event,
            publication_status=Event.PublicationStatus.REJECTED,
            kind=EventStateChange.Kind.DELISTED,
            actor=actor,
            now=now,
        )
        write_audit(
            actor=actor,
            action="event.rejected",
            target_type="event",
            target_id=event.pk,
            details={
                "from": previous,
                "to": Event.PublicationStatus.REJECTED.value,
                "event_version": change.event_version,
            },
        )
        return PublicationResult(event=event, change=change, applied=True)


def reinstate_event(
    *, event_id: UUID, actor: Actor, now: datetime | None = None
) -> PublicationResult:
    """Reverse a reject. Only an editor can; ingestion never does (D8).

    The Event returns to `published` and a `relisted` change re-mints its savers'
    reminders. It does **not** return to `in_review`: an editor reinstating a listing has
    just reviewed it, so sending it back to the queue it came from would re-ask the
    question they answered.
    """
    _editor(actor)
    now = now or timezone.now()

    with transaction.atomic(using=CATALOG):
        event = _load(event_id)
        if event.publication_status != Event.PublicationStatus.REJECTED:
            return PublicationResult(event=event, change=None, applied=False)

        change = apply_publication_change(
            event=event,
            publication_status=Event.PublicationStatus.PUBLISHED,
            kind=EventStateChange.Kind.RELISTED,
            actor=actor,
            now=now,
        )
        write_audit(
            actor=actor,
            action="event.reinstated",
            target_type="event",
            target_id=event.pk,
            details={
                "from": Event.PublicationStatus.REJECTED.value,
                "to": Event.PublicationStatus.PUBLISHED.value,
                "event_version": change.event_version,
            },
        )
        return PublicationResult(event=event, change=change, applied=True)


__all__ = ["PublicationResult", "reinstate_event", "reject_event"]
