"""Event writes for the ingest pipeline: create, lifecycle update, supersede, silent update.

Every function runs inside the caller's per-item `atomic(using=CATALOG)` (pipeline design D1).
The `catalog.guard_event_write` trigger allows `event_version` to stay or rise by exactly 1 per
statement, so a change of k kinds is k statements, each with its own `EventStateChange` (D9).
Each state change is enqueued for propagation only after the transaction commits (AD-17).
"""

from dataclasses import dataclass, fields
from datetime import datetime
from decimal import Decimal
from functools import partial
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import F

from apps.ingestion.models import Event, EventStateChange, ExtractedRecord, Source
from apps.ingestion.services.outbox import enqueue_propagation
from apps.ingestion.services.slugs import mint_slug
from domain.lifecycle import Change, ChangeKind, EventFacts, EventStatus
from shared.actor import Actor
from shared.db import CATALOG
from shared.ids import uuid7

_STATUS_KINDS = frozenset({ChangeKind.CANCELLED, ChangeKind.REINSTATED, ChangeKind.POSTPONED})
_KIND_FACTS = {
    ChangeKind.TIME_MOVED: frozenset({"start_utc", "end_utc", "start_time_tz"}),
    ChangeKind.SOLD_OUT: frozenset({"is_sold_out"}),
    ChangeKind.DETAIL_CHANGED: frozenset(
        {"start_time_tz", "venue_fingerprint", "title", "description", "canonical_url"}
    ),
}


@dataclass(frozen=True)
class IncomingEvent:
    """A candidate after timezone resolution and normalization: what the Event should say."""

    title: str
    description: str
    canonical_url: str  # normalized (domain.dedup.canonical_url), or ""
    venue_id: UUID | None  # a registry match only; the pipeline never creates venues
    venue_fingerprint: str
    title_fingerprint: str
    start_utc: datetime
    end_utc: datetime | None
    start_time_local: str
    start_time_tz: str
    status: EventStatus
    is_sold_out: bool
    series_id: UUID | None
    tz_inference_confidence: Decimal
    extraction_confidence: Decimal
    publication_status: str
    tz_review_pending: bool

    def facts(self) -> EventFacts:
        return EventFacts(
            start_utc=self.start_utc,
            end_utc=self.end_utc,
            start_time_tz=self.start_time_tz,
            status=self.status,
            is_sold_out=self.is_sold_out,
            venue_fingerprint=self.venue_fingerprint,
            title=self.title,
            description=self.description,
            canonical_url=self.canonical_url,
        )

    def columns(self) -> dict[str, object]:
        """Every Event column the source decides, by column name."""
        return {
            "title": self.title,
            "description": self.description,
            "canonical_url": self.canonical_url,
            "venue_id": self.venue_id,
            "venue_fingerprint": self.venue_fingerprint,
            "title_fingerprint": self.title_fingerprint,
            "start_time_utc": self.start_utc,
            "end_time_utc": self.end_utc,
            "start_time_local": self.start_time_local,
            "start_time_tz": self.start_time_tz,
            "status": self.status.value,
            "is_sold_out": self.is_sold_out,
            "series_id": self.series_id,
            **self.gating(),
        }

    def gating(self) -> dict[str, object]:
        # Follows every new resolution, silently (run-015 plan P1).
        return {
            "tz_inference_confidence": self.tz_inference_confidence,
            "extraction_confidence": self.extraction_confidence,
            "publication_status": self.publication_status,
            "tz_review_pending": self.tz_review_pending,
        }


def facts_of(event: Event) -> EventFacts:
    return EventFacts(
        start_utc=event.start_time_utc,
        end_utc=event.end_time_utc,
        start_time_tz=event.start_time_tz,
        status=EventStatus(event.status),
        is_sold_out=event.is_sold_out,
        venue_fingerprint=event.venue_fingerprint,
        title=event.title,
        description=event.description,
        canonical_url=event.canonical_url,
    )


def _constraint(exc: IntegrityError) -> str | None:
    diag = getattr(exc.__cause__, "diag", None)
    return getattr(diag, "constraint_name", None)


def create_event(
    *,
    source: Source,
    source_event_id: str,
    incoming: IncomingEvent,
    now: datetime,
    event_id: UUID | None = None,
) -> Event:
    """Insert a new Event at version 1, its original start equal to its start (D11).

    The slug is retried once with a longer tail if `event_slug_uq` trips (D18).
    """
    event_id = event_id or uuid7()
    for long_tail in (False, True):
        try:
            with transaction.atomic(using=CATALOG):  # savepoint: only the insert rolls back
                return Event.objects.using(CATALOG).create(
                    id=event_id,
                    source=source,
                    source_event_id=source_event_id,
                    slug=mint_slug(
                        incoming.title, incoming.start_time_local, event_id, long=long_tail
                    ),
                    original_start_utc=incoming.start_utc,
                    first_seen_at=now,
                    last_seen_at=now,
                    **incoming.columns(),
                )
        except IntegrityError as exc:
            if long_tail or _constraint(exc) != "event_slug_uq":
                raise
    raise AssertionError("unreachable")  # pragma: no cover


def _record_change(
    *,
    event_id: UUID,
    kind: str,
    version: int,
    before: dict,
    after: dict,
    actor: Actor,
    now: datetime,
) -> EventStateChange:
    change = EventStateChange.objects.using(CATALOG).create(
        event_id=event_id,
        kind=kind,
        event_version=version,
        before=before,
        after=after,
        occurred_at=now,
        actor_kind=actor.kind,
        actor_id=actor.id,
        actor_label=actor.label,
    )
    # robust: a failed enqueue (broker down) is logged and the item stays committed; the next
    # callbacks still run, and the reconciler re-sends what was lost (AD-17).
    transaction.on_commit(partial(enqueue_propagation, change.id), using=CATALOG, robust=True)
    return change


def _kind_facts(kind: ChangeKind, changed: frozenset[str]) -> list[str]:
    """Which changed facts a state change of this kind records (run-015 plan P5)."""
    if kind in _STATUS_KINDS:
        wanted = {"status"} | (changed & {"start_utc", "end_utc"})
    else:
        wanted = changed & _KIND_FACTS[kind]
    return [f.name for f in fields(EventFacts) if f.name in wanted]


def apply_lifecycle_change(
    *,
    event: Event,
    incoming: IncomingEvent,
    change: Change,
    actor: Actor,
    now: datetime,
) -> list[EventStateChange]:
    """Apply the incoming facts and append one state change per kind, in precedence order.

    The first statement writes every fact at version + 1; each further kind is a bump-only
    statement, so the versions are v+1..v+k (the trigger allows +1 per statement).
    """
    stored, new = facts_of(event), incoming.facts()
    rows = Event.objects.using(CATALOG).filter(pk=event.pk)
    version = event.event_version
    changes = []
    for position, kind in enumerate(change.kinds, start=1):
        if position == 1:
            rows.update(
                **incoming.columns(), last_seen_at=now, event_version=F("event_version") + 1
            )
        else:
            rows.update(event_version=F("event_version") + 1)
        names = _kind_facts(kind, change.fields)
        changes.append(
            _record_change(
                event_id=event.pk,
                kind=kind.value,
                version=version + position,
                before={n: getattr(stored, n) for n in names},
                after={n: getattr(new, n) for n in names},
                actor=actor,
                now=now,
            )
        )
    return changes


def apply_silent_update(*, event: Event, incoming: IncomingEvent, now: datetime) -> None:
    """Title, description and URL (and the gates) follow the source with no version bump and
    no state change (D9): live reads show the new text, and nobody is notified of a typo fix.
    """
    Event.objects.using(CATALOG).filter(pk=event.pk).update(
        title=incoming.title,
        description=incoming.description,
        canonical_url=incoming.canonical_url,
        title_fingerprint=incoming.title_fingerprint,
        last_seen_at=now,
        **incoming.gating(),
    )


def supersede_event(
    *,
    old: Event,
    incoming: IncomingEvent,
    record_id: UUID,
    actor: Actor,
    now: datetime,
) -> tuple[Event, EventStateChange]:
    """Replace an Event whose start moved beyond ±30 days, in the design D7 order.

    The partial unique index on (source, source_event_id) can't be deferred, so the old row
    leaves the live set before the new one enters it. The superseded_by FK is deferred.
    """
    new_id = uuid7()  # 1. mint
    Event.objects.using(CATALOG).filter(pk=old.pk).update(  # 2. retire, version + 1
        status=Event.Status.SUPERSEDED,
        superseded_by_id=new_id,
        event_version=F("event_version") + 1,
    )
    new = create_event(  # 3. insert at version 1
        source=old.source,
        source_event_id=old.source_event_id,
        incoming=incoming,
        now=now,
        event_id=new_id,
    )
    ExtractedRecord.objects.using(CATALOG).filter(pk=record_id).update(event_id=new_id)  # 4.
    change = _record_change(  # 5. the old Event's terminal state change
        event_id=old.pk,
        kind=EventStateChange.Kind.SUPERSEDED,
        version=old.event_version + 1,
        before={"status": old.status, "start_utc": old.start_time_utc},
        after={
            "status": Event.Status.SUPERSEDED.value,
            "superseded_by": new_id,
            "start_utc": incoming.start_utc,
        },
        actor=actor,
        now=now,
    )
    return new, change
