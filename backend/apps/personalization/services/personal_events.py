"""The personal-event commands (FR-18, FR-20, FR-58): create, update, delete.

These are the only way a `PersonalEvent` changes. Each command takes an explicit `Actor` and
an explicit `now`, opens one `transaction.atomic(using=PERSONAL)`, writes its audit row inside
it, and returns plain data.

Two things make a creation more than an insert:

- **The reminder plan** (FR-20, AD-16). `delivery` owns `REMINDER_PLAN`, so this module calls
  `delivery`'s published `attach_default_plan` rather than writing the table. The call is
  inside this transaction, so the event and its default plan commit or roll back together —
  there is no state in which a personal event exists with no plan.
- **Conflict detection** (FR-58, AD-21). Detection runs on write, never at render. A creation
  that finds a conflict does not silently complete: the result says the flow is awaiting the
  user's forced choice.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db import transaction
from django.db.models import F

from apps.delivery.services.reminder_plans import attach_default_plan
from apps.personalization.models import ConflictPair, PersonalEvent
from apps.personalization.services.audit import write_audit
from apps.personalization.services.conflicts import (
    Candidate,
    ConflictSide,
    DetectedConflict,
    close_pairs_for_side,
    detect_conflicts,
    reconcile_pairs_for_side,
    record_detected_conflicts,
)
from domain.errors import (
    InvalidIntervalError,
    InvalidTimezoneError,
    NotFoundError,
    ValidationError,
)
from domain.timezones import canonical_zone, to_instant
from shared.actor import Actor
from shared.db import PERSONAL


class PersonalEventNotFoundError(NotFoundError):
    """The event doesn't exist, or isn't the caller's."""

    default_message = "We couldn't find that event."


class MissingTimezoneError(ValidationError):
    """The event has no explicit IANA zone.

    A floating local time is refused rather than guessed: the user's wall clock and the
    event's zone are not the same thing, and guessing one from the other is how an event
    lands an hour out on the wrong side of a DST boundary.
    """

    code = "missing_timezone"
    default_message = "That event needs a timezone."


@dataclass(frozen=True)
class PersonalEventSnapshot:
    """A personal event as plain data — the caller never holds a model instance."""

    id: UUID
    user_id: UUID
    name: str
    start_utc: datetime
    end_utc: datetime | None
    start_time_tz: str
    location: str | None
    notes: str | None
    version: int


@dataclass(frozen=True)
class Created:
    """The event was created and no conflict is waiting for an answer."""

    event: PersonalEventSnapshot
    conflicts: tuple[DetectedConflict, ...] = ()


@dataclass(frozen=True)
class ConflictFound:
    """The event was created, and a conflict prompt is awaiting the user's choice.

    The row exists — the pair references it by id — but the creation flow is **incomplete**
    until one of the three resolutions is recorded (FR-58). There is no code path that
    completes a conflicted creation without a `ConflictResolution`.
    """

    event: PersonalEventSnapshot
    conflicts: tuple[DetectedConflict, ...]


def _snapshot(event: PersonalEvent) -> PersonalEventSnapshot:
    return PersonalEventSnapshot(
        id=event.id,
        user_id=event.user_id,
        name=event.name,
        start_utc=event.start_utc,
        end_utc=event.end_utc,
        start_time_tz=event.start_time_tz,
        location=event.location,
        notes=event.notes,
        version=event.version,
    )


def _validated_zone(start_time_tz: str | None) -> str:
    """The canonical IANA zone, or a refusal.

    An explicit zone is required (AD-6): the instant is the truth, and the zone says which
    wall clock the user meant. `domain.timezones.canonical_zone` is the same check the
    catalog's venue registry uses, so "UTC" and "Etc/UTC" mean the same thing everywhere.
    """
    if start_time_tz is None or not start_time_tz.strip():
        raise MissingTimezoneError(details={"field": "start_time_tz"})
    zone = canonical_zone(start_time_tz)
    if zone is None:
        raise InvalidTimezoneError(details={"start_time_tz": start_time_tz})
    return zone


def _validated_interval(
    start_utc: datetime, end_utc: datetime | None
) -> tuple[datetime, datetime | None]:
    """The start and end as UTC instants, with the end not before the start.

    The interval rule is the model's `personal_event_end_after_start_ck` and
    `domain.errors.InvalidIntervalError` — the same condition, refused with the same error,
    so a bad interval is a 422 rather than a database error.
    """
    start = to_instant(start_utc)
    if end_utc is None:
        return start, None
    end = to_instant(end_utc)
    if end < start:
        raise InvalidIntervalError(details={"start": start.isoformat(), "end": end.isoformat()})
    return start, end


def create_personal_event(
    *,
    user_id: UUID,
    name: str,
    start_utc: datetime,
    end_utc: datetime | None,
    start_time_tz: str | None,
    location: str | None = None,
    notes: str | None = None,
    actor: Actor,
    now: datetime,
) -> Created | ConflictFound:
    """Create a personal event, attach its default plan, and detect conflicts (FR-18, FR-20).

    The zone is required and the interval is checked before anything is written. The default
    reminder plan is attached by calling `delivery`'s published service, inside this
    transaction — so a plan failure rolls the creation back rather than leaving an event with
    no plan (FR-20's default is part of what a created event *is*).

    A conflict does not fail the command and does not silently complete it either: the result
    is a `ConflictFound`, and the pair row — `active`, with no resolution — is the pending
    prompt.
    """
    zone = _validated_zone(start_time_tz)
    start, end = _validated_interval(start_utc, end_utc)

    with transaction.atomic(using=PERSONAL):
        event = PersonalEvent.objects.using(PERSONAL).create(
            user_id=user_id,
            name=name,
            start_utc=start,
            end_utc=end,
            start_time_tz=zone,
            location=location,
            notes=notes,
        )
        # AD-16: `delivery` owns `REMINDER_PLAN`. This is the published seam, and it is the
        # only way this module touches a plan. The nested atomic is a savepoint on the same
        # alias, so the plan cannot commit apart from its event.
        attach_default_plan(
            user_id=user_id,
            target_kind=ConflictPair.SideKind.PERSONAL_EVENT,
            target_id=event.id,
            actor=actor,
            now=now,
        )
        candidate = Candidate(
            kind=ConflictPair.SideKind.PERSONAL_EVENT,
            id=event.id,
            name=event.name,
            start_utc=event.start_utc,
            end_utc=event.end_utc,
        )
        detected = detect_conflicts(user_id=user_id, candidate=candidate)
        conflicts = tuple(
            record_detected_conflicts(user_id=user_id, detected=detected, actor=actor, now=now)
        )
        write_audit(
            actor=actor,
            action="personal_event.created",
            target_type="personal_event",
            target_id=event.id,
            details={
                "start_utc": start.isoformat(),
                "end_utc": end.isoformat() if end else None,
                "start_time_tz": zone,
                "conflicts": [c.kind for c in conflicts],
            },
        )
        snapshot = _snapshot(event)

    if conflicts:
        return ConflictFound(event=snapshot, conflicts=conflicts)
    return Created(event=snapshot, conflicts=())


def update_personal_event(
    *,
    user_id: UUID,
    event_id: UUID,
    name: str | None = None,
    start_utc: datetime | None = None,
    end_utc: datetime | None = None,
    start_time_tz: str | None = None,
    location: str | None = None,
    notes: str | None = None,
    actor: Actor,
    now: datetime,
) -> Created | ConflictFound:
    """Edit a personal event and re-run conflict detection (FR-18, FR-58).

    The version rises by exactly one: AD-7's send key uses it, so it may only go up. The
    increment uses `F()` so it is atomic against a concurrent write.

    Detection re-runs because the pair's existence is a claim about the two events' *current*
    times. A pair whose overlap is gone closes as `cleared_by_state_change`; a pair that still
    overlaps stays active; a new overlap creates a new pair.

    The reminder plan is **not** touched. FR-20's default is a property of creation, and
    re-attaching it here would reset a plan the user had customised through FR-9's picker.
    """
    with transaction.atomic(using=PERSONAL):
        event = PersonalEvent.objects.using(PERSONAL).filter(user_id=user_id, pk=event_id).first()
        if event is None:
            raise PersonalEventNotFoundError(details={"event_id": str(event_id)})

        zone = event.start_time_tz if start_time_tz is None else _validated_zone(start_time_tz)
        start = event.start_utc if start_utc is None else to_instant(start_utc)
        end = event.end_utc if end_utc is None else end_utc
        start, end = _validated_interval(start, end)

        PersonalEvent.objects.using(PERSONAL).filter(pk=event.pk).update(
            name=event.name if name is None else name,
            start_utc=start,
            end_utc=end,
            start_time_tz=zone,
            location=event.location if location is None else location,
            notes=event.notes if notes is None else notes,
            version=F("version") + 1,
        )
        event.refresh_from_db()

        # A pair is a claim about the two events' times. If the time moved, the pairs that
        # referenced the old time are re-judged: one that no longer overlaps closes, one that
        # still overlaps stays, and a new overlap creates a new pair.
        _reconcile_pairs(user_id=user_id, event=event, now=now)

        candidate = Candidate(
            kind=ConflictPair.SideKind.PERSONAL_EVENT,
            id=event.id,
            name=event.name,
            start_utc=event.start_utc,
            end_utc=event.end_utc,
        )
        detected = detect_conflicts(user_id=user_id, candidate=candidate)
        conflicts = tuple(
            record_detected_conflicts(user_id=user_id, detected=detected, actor=actor, now=now)
        )
        write_audit(
            actor=actor,
            action="personal_event.updated",
            target_type="personal_event",
            target_id=event.id,
            details={
                "version": event.version,
                "start_utc": start.isoformat(),
                "conflicts": [c.kind for c in conflicts],
            },
        )
        snapshot = _snapshot(event)

    if conflicts:
        return ConflictFound(event=snapshot, conflicts=conflicts)
    return Created(event=snapshot, conflicts=())


def _reconcile_pairs(*, user_id: UUID, event: PersonalEvent, now: datetime) -> None:
    """Close the event's active pairs that no longer overlap, after a time change.

    A pair stays `active` only while the two events really do clash. When an edit moves the
    event out of the other's way, the pair closes as `cleared_by_state_change` — AD-21's name
    for a pair that ended because the world moved, not because the user chose.
    """
    reconcile_pairs_for_side(
        user_id=user_id,
        kind=ConflictPair.SideKind.PERSONAL_EVENT,
        side_id=event.id,
        side=ConflictSide(
            kind=ConflictPair.SideKind.PERSONAL_EVENT,
            id=event.id,
            name=event.name,
            start_utc=event.start_utc,
            end_utc=event.end_utc,
        ),
        now=now,
    )


def delete_personal_event(
    *,
    user_id: UUID,
    event_id: UUID,
    actor: Actor,
    now: datetime,
) -> None:
    """Delete a personal event and close the pairs it took part in (FR-18, FR-21).

    The pairs close as `cleared_by_state_change`: the pair ended because a side went away,
    which AD-21 says is *not* a user resolution. The resolution stays NULL.

    The reminder plan row stays behind. `delivery` owns `REMINDER_PLAN`, and `personalization`
    may not write it — deleting the plan is `delivery`'s call, and it has no such command yet.
    The leftover row is inert.
    """
    with transaction.atomic(using=PERSONAL):
        event = PersonalEvent.objects.using(PERSONAL).filter(user_id=user_id, pk=event_id).first()
        if event is None:
            raise PersonalEventNotFoundError(details={"event_id": str(event_id)})
        close_pairs_for_side(
            user_id=user_id,
            kind=ConflictPair.SideKind.PERSONAL_EVENT,
            side_id=event.id,
            now=now,
        )
        event.delete()
        write_audit(
            actor=actor,
            action="personal_event.deleted",
            target_type="personal_event",
            target_id=event_id,
            details={"name": event.name, "at": now.isoformat()},
        )


__all__ = [
    "ConflictFound",
    "Created",
    "MissingTimezoneError",
    "PersonalEventNotFoundError",
    "PersonalEventSnapshot",
    "create_personal_event",
    "delete_personal_event",
    "update_personal_event",
]
