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
from apps.ingestion.services.catalog_read import EventNotFoundError
from apps.ingestion.services.outbox import enqueue_propagation
from apps.ingestion.services.revalidation import enqueue_revalidation, request_revalidation
from apps.ingestion.services.slugs import mint_slug
from domain.errors import EventAlreadyRetiredError
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

    def columns(self, *, stored: Event | None = None) -> dict[str, object]:
        """Every Event column the source decides, by column name.

        `stored` is the Event this is about to overwrite, or None on an insert. It is
        passed through to `gating()`, which needs it to leave an editor's reject alone.
        """
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
            **self.gating(stored=stored),
        }

    def gating(self, *, stored: Event | None = None) -> dict[str, object]:
        """The confidence and publication columns the gate decides.

        Follows every new resolution, silently (run-015 plan P1) — **except that a
        rejected Event's `publication_status` is frozen** (event-rejection-state D8).

        **This is the re-entry hole, and without the freeze it is a live one.** The source
        that produced a bad listing keeps sending it on every poll. `gating()` is applied
        on every update, so the very next poll after an editor's reject would write
        `published` straight back over it and the verdict would evaporate within the hour
        — silently, because nothing about that write looks unusual.

        Only the gate is frozen. The title, the times and the `ExtractedRecord` still
        follow the source, so the evidence an editor reviews stays current, and a
        reinstatement shows today's facts rather than the ones that got it rejected.

        Reversing a reject is an editor's command alone (`editorial_state`). Ingestion
        never does it.
        """
        values: dict[str, object] = {
            "tz_inference_confidence": self.tz_inference_confidence,
            "extraction_confidence": self.extraction_confidence,
            "publication_status": self.publication_status,
            "tz_review_pending": self.tz_review_pending,
        }
        if stored is not None and stored.publication_status == Event.PublicationStatus.REJECTED:
            del values["publication_status"]
        return values


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
                **incoming.columns(stored=event),
                last_seen_at=now,
                event_version=F("event_version") + 1,
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
        **incoming.gating(stored=event),
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


def apply_publication_change(
    *,
    event: Event,
    publication_status: str,
    kind: str,
    actor: Actor,
    now: datetime,
) -> EventStateChange:
    """Move an Event's `publication_status` and record the change that travels with it.

    **The low-level half of an editorial reject** (event-rejection-state D1, D2). The
    command layer — guards, the actor rule, the audit entry — is
    `apps.ingestion.services.editorial_state`. This lives here because `_record_change`
    and `_request_revalidation` do, and `EventStateChange` keeps exactly one writer.

    **The version bump is deliberate, and it is the whole point.** `publication_status` is
    not in `Event.LIFECYCLE_FIELDS`, so the trigger does not *demand* a bump here — but
    nor does it forbid one, and without it there is no version for a state change to carry
    and no row for the AD-17 outbox. Hiding the Event would reach nobody, and every saver
    would keep getting reminders for a listing editorial has ruled bad. The `0009`
    trigger rule turns that "deliberate" into "required" at the `rejected` boundary, so a
    future caller cannot quietly drop it.

    Caller supplies the transaction: this runs inside `atomic(using=CATALOG)`, like every
    other write in this module.
    """
    version = event.event_version + 1
    before = {"publication_status": event.publication_status}
    after = {"publication_status": publication_status}

    Event.objects.using(CATALOG).filter(pk=event.pk).update(
        publication_status=publication_status,
        event_version=version,
    )
    change = _record_change(
        event=event,
        kind=kind,
        version=version,
        before=before,
        after=after,
        actor=actor,
        now=now,
    )
    # The public pages still show the old state until they are rebuilt (FR-26): a rejected
    # event's own URL must start 404ing and its city page must drop it. `is_public` is read
    # from `publication_status`, so the request has to be made after the update above.
    event.publication_status = publication_status
    event.event_version = version
    _request_revalidation(event=event, event_version=version, previous_venue_id=None)
    return change


def retire_event(*, event_id: UUID, actor: Actor, now: datetime) -> Event:
    """Take an Event out of the catalog for good, keeping its row and its history.

    **Why there is a service for this at all.** An Event is never deleted (FR-13): the row
    is the record of what the source said and when, and a saver who was told about an event
    must be able to find out what became of it. So "remove it" means "move it out of every
    live read", and the way this catalog says that is `status = superseded`.

    **Why a second row.** `event_superseded_consistent_ck` says a superseded Event names
    its replacement, and a row may not name *itself*
    (`event_not_self_superseded_ck`) — so a superseded row needs another row to point at.
    The replacement created here is a **tombstone**: it carries the event's facts, it is
    never published, and it is superseded too, pointing back at the row it replaced.

    **The two rows point at each other, and that is what frees the slot.**
    `event_live_source_item_uq` is *partial* — one live Event per
    `(source, source_event_id)`, counting only the rows that are not superseded. The
    original row and its tombstone are both superseded, so neither holds the slot, and a
    later write for the same source item can create a fresh live row. A tombstone that
    was left *live* would hold the slot forever, and the source item could never be
    ingested again — so the tombstone is superseded from the moment it is created.

    **What it is for.** A seed's data file is the source of truth for what the catalog
    should contain, and a file that drops an event has to be able to say so. Cancelling
    the dropped event would not do it: a cancelled Event is a *must-know card* — the
    surface's amber stripe — so "the file forgot about this" would become "the surface
    tells the user this was cancelled", which is a different and untrue statement.

    **The caller names the event by id, not by row.** AD-2's `models-ingestion` contract
    says only `apps.ingestion` may import `apps.ingestion.models`, so a caller outside
    this app — the seed command in `config`, say — cannot hand over an `Event`. It hands
    over the id and this looks the row up.

    Caller supplies the transaction: this runs inside `atomic(using=CATALOG)`, like every
    other write in this module.
    """
    try:
        event = Event.objects.using(CATALOG).get(pk=event_id)
    except Event.DoesNotExist:
        raise EventNotFoundError(details={"event_id": str(event_id)}) from None
    if event.status == Event.Status.SUPERSEDED:
        # **Already retired.** Retiring twice would create a second tombstone for a row
        # that already has one, and the row's own `superseded_by` would still name the
        # first — so the second tombstone would sit in the catalog with nothing pointing
        # at it. Refusing is the honest answer.
        raise EventAlreadyRetiredError(details={"event_id": str(event_id)})

    tombstone_id = uuid7()
    facts = facts_of(event)
    incoming = IncomingEvent(
        title=event.title,
        description=event.description,
        canonical_url=event.canonical_url,
        venue_id=event.venue_id,
        venue_fingerprint=event.venue_fingerprint,
        title_fingerprint=event.title_fingerprint,
        start_utc=facts.start_utc,
        end_utc=facts.end_utc,
        start_time_local=event.start_time_local,
        start_time_tz=event.start_time_tz,
        status=EventStatus.SCHEDULED,
        is_sold_out=event.is_sold_out,
        series_id=event.series_id,
        tz_inference_confidence=event.tz_inference_confidence,
        extraction_confidence=event.extraction_confidence,
        # **Never published.** The tombstone is a record, not a listing.
        publication_status=Event.PublicationStatus.IN_REVIEW,
        tz_review_pending=False,
    )
    # The old row leaves the live set first: the partial unique index counts only the rows
    # that are not superseded, so the slot is free before the tombstone takes it. The
    # version bump is required — `status` and `superseded_by` are lifecycle fields, and the
    # `catalog.guard_event_write` trigger demands exactly +1 for a change to either.
    Event.objects.using(CATALOG).filter(pk=event.pk).update(
        status=Event.Status.SUPERSEDED,
        superseded_by_id=tombstone_id,
        event_version=F("event_version") + 1,
    )
    tombstone = create_event(
        source=event.source,
        source_event_id=event.source_event_id,
        incoming=incoming,
        now=now,
        event_id=tombstone_id,
    )
    # **The tombstone points back at the row it replaced**, and is superseded itself. That
    # is what satisfies `event_superseded_consistent_ck` in both directions while keeping
    # the source item's slot free: `event_not_self_superseded_ck` forbids a row naming
    # *itself*, and these two name each other.
    Event.objects.using(CATALOG).filter(pk=tombstone_id).update(
        status=Event.Status.SUPERSEDED,
        superseded_by_id=event.pk,
        event_version=F("event_version") + 1,
    )
    _record_change(
        event=event,
        kind=ChangeKind.SUPERSEDED.value,
        version=event.event_version + 1,
        before={"status": event.status},
        after={"status": Event.Status.SUPERSEDED.value, "superseded_by": tombstone_id},
        actor=actor,
        now=now,
    )
    _record_change(
        event=tombstone,
        kind=ChangeKind.SUPERSEDED.value,
        version=tombstone.event_version + 1,
        before={"status": tombstone.status},
        after={"status": Event.Status.SUPERSEDED.value, "superseded_by": event.pk},
        actor=actor,
        now=now,
    )
    return tombstone
