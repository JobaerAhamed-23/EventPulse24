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
from apps.ingestion.services.revalidation import enqueue_revalidation, request_revalidation
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
            venue_id=self.venue_id,
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
        venue_id=event.venue_id,
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
    event: Event,
    kind: str,
    version: int,
    before: dict,
    after: dict,
    actor: Actor,
    now: datetime,
) -> EventStateChange:
    change = EventStateChange.objects.using(CATALOG).create(
        event_id=event.pk,
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


def _request_revalidation(
    *,
    event: Event,
    event_version: int,
    previous_venue_id: UUID | None,
) -> None:
    """Record the revalidation signal for one change, and register its enqueue (FR-26, FR-27).

    **This is called once per logical change, not once per kind.** A change of *k* kinds is
    *k* statements and *k* state changes, but it is **one** change to the public page: the
    page ends up in one state, and the page that must be rebuilt is the same page either
    way. Registering the enqueue per kind would send the same request to the broker twice
    for one change.

    **The enqueue fires on commit too** — a rebuild fired from inside an uncommitted write
    would read the old row back and re-cache exactly the stale page it was meant to fix.

    **`previous_venue_id` is the event's venue *before* this change.** It is what makes the
    **old** city nameable: the recorded `venue_fingerprint` is a hash, and a hash cannot be
    reversed to a city, so an event that moved between cities could not have its old city
    page revalidated without the id.
    """
    request = request_revalidation(
        event=event,
        event_version=event_version,
        previous_venue_id=previous_venue_id,
        enqueue=False,
    )
    if request is not None:
        transaction.on_commit(partial(enqueue_revalidation, request.id), using=CATALOG, robust=True)


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
    # The event's venue *before* this change. Recorded on the state change so the previous
    # city stays nameable: the recorded fingerprint is a hash, and a hash cannot be reversed
    # to a city (FR-27).
    previous_venue_id = event.venue_id
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
                event=event,
                kind=kind.value,
                version=version + position,
                before={n: getattr(stored, n) for n in names},
                after={n: getattr(new, n) for n in names},
                actor=actor,
                now=now,
            )
        )
    # **One revalidation per logical change**, not one per kind. The change is *k*
    # statements and *k* state changes, but it leaves the public page in one state, and the
    # page that must be rebuilt is the same page either way. The version recorded is the
    # change's **final** version — the last kind's — so the guard compares the rebuild
    # against the newest state the change produced, not an intermediate one.
    _request_revalidation(
        event=event,
        event_version=version + len(change.kinds),
        previous_venue_id=previous_venue_id,
    )
    return changes


def apply_silent_update(*, event: Event, incoming: IncomingEvent, now: datetime) -> None:
    """Title, description and URL (and the gates) follow the source with no version bump and
    no state change (D9): live reads show the new text, and nobody is notified of a typo fix.

    **But the public page still shows the old text until it is rebuilt**, so this does
    enqueue a revalidation (FR-26). The version did not move, and that is fine: the
    version guard says the rebuild must not be *older* than the signal, not that the
    version must have *changed*. A signal at version N is satisfied by a rebuild at
    version N.
    """
    Event.objects.using(CATALOG).filter(pk=event.pk).update(
        title=incoming.title,
        description=incoming.description,
        canonical_url=incoming.canonical_url,
        title_fingerprint=incoming.title_fingerprint,
        last_seen_at=now,
        **incoming.gating(),
    )
    # The request row is written in this transaction, so it commits with the change that
    # caused it; only the enqueue waits for the commit.
    _request_revalidation(
        event=event,
        event_version=event.event_version,
        previous_venue_id=None,
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
        event=old,
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
    # The revalidation signal for the old event (FR-27). The old event's venue is the one
    # it is leaving, so the city page it leaves is revalidated too. The successor has its own
    # slug and its own page, which has never been built and so has nothing stale to fix.
    _request_revalidation(
        event=old,
        event_version=old.event_version + 1,
        previous_venue_id=old.venue_id,
    )
    return new, change
