"""The editor's four verbs, as `ingestion` commands (FR-57, AD-14).

AD-14: `editorial` owns no tables and *"writes through `ingestion` services like any other
client; it gets no privileged write path"*. This module is that path. The admin in
`editorial-admin-queue` is a thin caller of these four functions and writes nothing itself.

---

## One verdict closes every open item on the event

`review-queue-model` D2 lets an event carry two open items at once — quarantined by the
confidence gate **and** reported by users — on the reasoning that they are two different
questions. They are not two different *decisions*: an editor looking at the event answers
both by looking once. So every command closes **all** of the event's open items with its
resolution, and D2 pinned that here as an integration requirement.

---

## Staleness is checked twice, because there are two things to be stale about

- **The item.** Already resolved means someone else got there first. The
  `guard_review_item` trigger would refuse the write anyway; refusing in the command turns a
  database error into a sentence an editor can read.
- **The event.** `expected_event_version` is the version the editor's page was rendered
  from. If ingestion has moved the event since, the edit in front of them describes facts
  that no longer hold, and applying it would silently overwrite an update nobody saw.

---

## The editorial lock, which turns out to need no code

An editor's correction is not undone by the next poll, and nothing here enforces that:
`ingest_item` hashes the **source's** payload and returns `unchanged` *before* touching the
Event when that hash matches. A source repeating the same bad data cannot overwrite a
correction, however many times it repeats it.

A source publishing something *new* does win. That is the decision (2026-11-10): it has said
something it did not say before, and the remedy for a source that is repeatedly wrong is
FR-16's score, not a permanent per-event veto that would also block a real cancellation.
`tests/ingestion/test_editorial_lock.py` pins both halves.

---

## Edits go through ingestion's own write path

A time or venue edit calls `apply_lifecycle_change` — the same function the pipeline calls —
so it bumps `event_version`, appends an `EventStateChange`, and reaches saved users through
AD-17's outbox with no parallel path to keep in step. A title-only edit calls
`apply_silent_update`, because `domain/notices.py` already decided that a typo fix is not
worth an email.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.ingestion.models import Event, ReviewItem, Source, SourceObservation, Venue
from apps.ingestion.services.audit import write_audit
from apps.ingestion.services.editorial_state import reject_event
from apps.ingestion.services.event_writes import (
    IncomingEvent,
    apply_lifecycle_change,
    apply_silent_update,
    facts_of,
)
from domain.errors import ConflictError, ValidationError
from domain.lifecycle import EventStatus, classify_change
from shared.actor import Actor, ActorKind
from shared.db import CATALOG

#: The fields an editor may correct. Deliberately short.
#:
#: **What is absent is the point.** The slug is a public URL and changing it breaks every
#: link that already exists. `source` and `source_event_id` are the event's *identity*
#: (AD-4) — editing them would make this event a different event. The confidences belong to
#: the gate that computed them, not to the person reading the result. And
#: `publication_status` is not here because approve and reject *are* the way it moves.
EDITABLE_FIELDS = frozenset(
    {"title", "start_time_utc", "end_time_utc", "start_time_tz", "venue_id"}
)

#: The fields whose change is a lifecycle change (`Event.LIFECYCLE_FIELDS` ∩ editable).
_LIFECYCLE_EDITS = frozenset({"start_time_utc", "end_time_utc", "start_time_tz", "venue_id"})


@dataclass(frozen=True)
class ResolutionResult:
    item: ReviewItem
    closed: int
    observation: SourceObservation | None


def _editor(actor: Actor) -> None:
    """AD-14: every editorial action is attributed to a person.

    `ReviewItem`'s own D6 check enforces this at the database for every resolution but
    `withdrawn`. Refusing here names the reason instead of surfacing a constraint violation.
    """
    if actor.kind is not ActorKind.USER:
        raise ValidationError(
            "An editorial verdict needs a user actor.",
            details={"errors": ["actor_must_be_user"]},
        )


def _load_item(item_id: UUID) -> ReviewItem:
    item = (
        ReviewItem.objects.using(CATALOG)
        # `of=("self",)` locks the item row only. Both target FKs are nullable, so a plain
        # `select_for_update()` with `select_related` builds a LEFT OUTER JOIN and Postgres
        # refuses: "FOR UPDATE cannot be applied to the nullable side of an outer join".
        # The item is the row two editors race for; the event is locked separately below.
        .select_for_update(of=("self",))
        .filter(pk=item_id)
        .select_related("event", "source")
        .first()
    )
    if item is None:
        raise ValidationError("No such review item.", details={"errors": ["item_not_found"]})
    if item.status == ReviewItem.Status.RESOLVED:
        raise ConflictError(
            "Someone has already resolved this item.",
            details={"errors": ["item_already_resolved"]},
        )
    return item


def _checked_event(item: ReviewItem, expected_event_version: int | None) -> Event:
    if item.event is None:
        raise ValidationError(
            "That item is about a source, not an event.",
            details={"errors": ["item_has_no_event"]},
        )
    event = Event.objects.using(CATALOG).select_for_update().get(pk=item.event_id)
    if expected_event_version is not None and event.event_version != expected_event_version:
        raise ConflictError(
            "This event changed while you were looking at it. Reload and check again.",
            details={
                "errors": ["event_version_stale"],
                "expected": expected_event_version,
                "actual": event.event_version,
            },
        )
    return event


def _close_open_items(
    *, event: Event, resolution: str, actor: Actor, now: datetime
) -> tuple[int, list[UUID]]:
    """Close every open item on this event with one resolution (D2). Returns (count, ids).

    A filtered UPDATE on `status='open'`, not a read-then-save: two editors acting at once
    would otherwise both read an open row and the loser would hit `guard_review_item`'s
    "a resolved ReviewItem is immutable".
    """
    open_items = ReviewItem.objects.using(CATALOG).filter(
        event_id=event.pk, status=ReviewItem.Status.OPEN
    )
    item_ids = list(open_items.values_list("id", flat=True))
    if not item_ids:
        return 0, []
    closed = (
        ReviewItem.objects.using(CATALOG)
        .filter(id__in=item_ids, status=ReviewItem.Status.OPEN)
        .update(
            status=ReviewItem.Status.RESOLVED,
            resolution=resolution,
            resolved_at=now,
            resolved_by_kind=actor.kind,
            resolved_by_id=actor.id,
            resolved_by_label=actor.label,
            updated_at=now,
        )
    )
    return closed, item_ids


def _observe(
    *,
    source: Source,
    kind: str,
    event: Event | None,
    item: ReviewItem,
    actor: Actor,
    now: datetime,
) -> SourceObservation:
    """Record the FR-16 observation for one resolution. One per item, enforced by a constraint.

    **The report count is frozen here, from the item being closed.** The `ReviewItem`'s
    tally columns are the only cross-wall-safe record of the reports: the reports themselves
    live in `personal.EventReport` and are purged with the account, and the reporter's
    identity never crosses into `catalog` at all (D4 of `review-queue-model`). So the count is
    read here, in `catalog`, and written onto the observation as a fact.

    **It does not multiply the observation.** One verdict is one observation, however many
    reports it answered — `SourceObservation.source_observation_item_uq` permits one row per
    review item, and all of an event's reports live on one `user_reported` item, so the
    multiplication is impossible rather than merely avoided (design D8).

    **This is where the wall is held.** The observation is written at *resolution time* from
    the item's own tallies, so the recompute job never has to read `personal` (design D9).
    """
    return SourceObservation.objects.using(CATALOG).create(
        source=source,
        kind=kind,
        event=event,
        review_item=item,
        report_count=item.report_count,
        occurred_at=now,
        actor_kind=actor.kind,
        actor_id=actor.id,
        actor_label=actor.label,
    )


def _audit(actor: Actor, action: str, item: ReviewItem, details: dict) -> None:
    write_audit(
        actor=actor, action=action, target_type="review_item", target_id=item.id, details=details
    )


def approve_review_item(
    *,
    item_id: UUID,
    actor: Actor,
    expected_event_version: int | None = None,
    now: datetime | None = None,
) -> ResolutionResult:
    """Publish a quarantined event, or confirm a reported one is fine. Closes `approved`.

    **Approving is idempotent on an already-published event.** A reported event is usually
    already public — the report never hid it (FR-59) — so "approve" there means "I looked,
    it is correct", and the publication status does not move.
    """
    _editor(actor)
    moment = now or timezone.now()

    with transaction.atomic(using=CATALOG):
        item = _load_item(item_id)
        event = _checked_event(item, expected_event_version)

        if event.publication_status == Event.PublicationStatus.IN_REVIEW:
            # Out of review, into the light. Publication is not a lifecycle field, so this
            # bumps nothing and notifies nobody: the event was never visible to be changed.
            Event.objects.using(CATALOG).filter(pk=event.pk).update(
                publication_status=Event.PublicationStatus.PUBLISHED
            )
            event.publication_status = Event.PublicationStatus.PUBLISHED

        closed, item_ids = _close_open_items(
            event=event, resolution=ReviewItem.Resolution.APPROVED, actor=actor, now=moment
        )
        observation = _observe(
            source=event.source,
            kind=SourceObservation.Kind.APPROVED,
            event=event,
            item=item,
            actor=actor,
            now=moment,
        )
        _audit(actor, "review_item_approved", item, {"closed": closed, "event_id": str(event.pk)})
        item.refresh_from_db(using=CATALOG)
        return ResolutionResult(item=item, closed=closed, observation=observation)


def check_review_edit(
    *,
    item_id: UUID,
    fields: dict,
    expected_event_version: int | None = None,
) -> None:
    """Every check `edit_and_publish` makes, and nothing it does not. Raises on a refusal.

    **This is the write-free half of the command, so the admin's form and the command
    cannot drift.** The edit form's `clean()` calls it, so a refusal shows on the form
    before anything is written; `edit_and_publish` calls it too, so a caller that skips the
    form — a script, a future API — is refused the same way. One set of rules, two doors.

    What it checks, in order:

    - **The fields are editable.** The set is `EDITABLE_FIELDS`, and it is deliberately
      short: the slug is a public URL, the source and `source_event_id` are the event's
      identity (AD-4), the confidences belong to the gate, and `publication_status` is
      what approve and reject are for.
    - **Something was actually changed.** An edit that changes nothing would close the item
      as `edited` and record an observation, which would count against the source for a
      correction nobody made.
    - **The item is open.** Someone else may have resolved it while the form was open.
    - **The event has not moved.** `expected_event_version` is the version the editor's
      page was rendered from; if ingestion has written to the event since, the edit in
      front of them describes facts that no longer hold.

    **It writes nothing and locks nothing.** The checks read; the command does the writing.
    """
    unknown = set(fields) - EDITABLE_FIELDS
    if unknown:
        raise ValidationError(
            "Those fields cannot be edited here.",
            details={
                "errors": [{"loc": [name], "msg": "not editable"} for name in sorted(unknown)]
            },
        )
    if not fields:
        raise ValidationError("Nothing to change.", details={"errors": ["no_fields"]})

    item = ReviewItem.objects.using(CATALOG).filter(pk=item_id).first()
    if item is None:
        raise ValidationError("No such review item.", details={"errors": ["item_not_found"]})
    if item.status == ReviewItem.Status.RESOLVED:
        raise ConflictError(
            "Someone has already resolved this item.",
            details={"errors": ["item_already_resolved"]},
        )
    if item.event_id is None:
        raise ValidationError(
            "That item is about a source, not an event.",
            details={"errors": ["item_has_no_event"]},
        )
    event_version = (
        Event.objects.using(CATALOG)
        .filter(pk=item.event_id)
        .values_list("event_version", flat=True)
        .first()
    )
    if event_version is None:
        raise ValidationError("No such event.", details={"errors": ["event_not_found"]})
    if expected_event_version is not None and event_version != expected_event_version:
        raise ConflictError(
            "This event changed while you were looking at it. Reload and check again.",
            details={
                "errors": ["event_version_stale"],
                "expected": expected_event_version,
                "actual": event_version,
            },
        )


def edit_and_publish(
    *,
    item_id: UUID,
    actor: Actor,
    fields: dict,
    expected_event_version: int | None = None,
    now: datetime | None = None,
) -> ResolutionResult:
    """Correct an event, publish it, and close the item as `edited`.

    The edit goes through ingestion's own write path, so a time or venue change is
    indistinguishable downstream from one the source made: version bumped, `EventStateChange`
    appended, saved users reached through AD-17.

    **The checks run twice on purpose.** `check_review_edit` runs first, outside the
    transaction, so a refusal is raised before anything is opened; then the transaction
    re-checks the same things under a lock, because the world can move between the two
    reads. The second check is the authoritative one.
    """
    _editor(actor)
    moment = now or timezone.now()

    check_review_edit(item_id=item_id, fields=fields, expected_event_version=expected_event_version)

    with transaction.atomic(using=CATALOG):
        item = _load_item(item_id)
        event = _checked_event(item, expected_event_version)

        incoming = _incoming_for(event, fields)
        if _LIFECYCLE_EDITS & set(fields):
            change = classify_change(facts_of(event), incoming.facts(), event.original_start_utc)
            if change is not None:
                apply_lifecycle_change(
                    event=event, incoming=incoming, change=change, actor=actor, now=moment
                )
            else:
                apply_silent_update(event=event, incoming=incoming, now=moment)
        else:
            # Title only. `domain/notices.py` already decided a typo fix is not an email.
            apply_silent_update(event=event, incoming=incoming, now=moment)

        event.refresh_from_db(using=CATALOG)
        if event.publication_status == Event.PublicationStatus.IN_REVIEW:
            Event.objects.using(CATALOG).filter(pk=event.pk).update(
                publication_status=Event.PublicationStatus.PUBLISHED
            )
            event.publication_status = Event.PublicationStatus.PUBLISHED

        closed, _ids = _close_open_items(
            event=event, resolution=ReviewItem.Resolution.EDITED, actor=actor, now=moment
        )
        observation = _observe(
            source=event.source,
            kind=SourceObservation.Kind.EDITED,
            event=event,
            item=item,
            actor=actor,
            now=moment,
        )
        _audit(
            actor,
            "review_item_edited",
            item,
            {"closed": closed, "event_id": str(event.pk), "fields": sorted(fields)},
        )
        item.refresh_from_db(using=CATALOG)
        return ResolutionResult(item=item, closed=closed, observation=observation)


def reject_review_item(
    *,
    item_id: UUID,
    actor: Actor,
    expected_event_version: int | None = None,
    now: datetime | None = None,
) -> ResolutionResult:
    """Reject the listing and close the item as `rejected`.

    **This is the verdict half that `editorial_state.reject_event` deliberately left out.**
    That command owns the state transition — hiding the event and cancelling saved users'
    reminders — and says nothing about the queue, because a reject is an editorial judgement
    and belongs to whoever records judgements. This is that caller.
    """
    _editor(actor)
    moment = now or timezone.now()

    with transaction.atomic(using=CATALOG):
        item = _load_item(item_id)
        event = _checked_event(item, expected_event_version)

        reject_event(event_id=event.pk, actor=actor, now=moment)

        closed, _ids = _close_open_items(
            event=event, resolution=ReviewItem.Resolution.REJECTED, actor=actor, now=moment
        )
        observation = _observe(
            source=event.source,
            kind=SourceObservation.Kind.REJECTED,
            event=event,
            item=item,
            actor=actor,
            now=moment,
        )
        _audit(actor, "review_item_rejected", item, {"closed": closed, "event_id": str(event.pk)})
        item.refresh_from_db(using=CATALOG)
        return ResolutionResult(item=item, closed=closed, observation=observation)


def dismiss_source_item(
    *, item_id: UUID, actor: Actor, now: datetime | None = None
) -> ResolutionResult:
    """Close a `source_reliability` item, having found no fault. The Source is not touched.

    **FR-16 is explicit: escalation, never removal.** A low score raises this item and
    nothing else; it does not pause, hide or remove the Source, and neither does dismissing
    the item. That this function writes no `Source` column is the whole content of it, and a
    test asserts the Source is untouched rather than trusting the absence of a line.
    """
    _editor(actor)
    moment = now or timezone.now()

    with transaction.atomic(using=CATALOG):
        item = _load_item(item_id)
        if item.source is None:
            raise ValidationError(
                "That item is about an event, not a source.",
                details={"errors": ["item_has_no_source"]},
            )

        closed = (
            ReviewItem.objects.using(CATALOG)
            .filter(pk=item.pk, status=ReviewItem.Status.OPEN)
            .update(
                status=ReviewItem.Status.RESOLVED,
                resolution=ReviewItem.Resolution.DISMISSED,
                resolved_at=moment,
                resolved_by_kind=actor.kind,
                resolved_by_id=actor.id,
                resolved_by_label=actor.label,
                updated_at=moment,
            )
        )
        observation = _observe(
            source=item.source,
            kind=SourceObservation.Kind.DISMISSED,
            event=None,
            item=item,
            actor=actor,
            now=moment,
        )
        _audit(actor, "review_item_dismissed", item, {"source_id": str(item.source_id)})
        item.refresh_from_db(using=CATALOG)
        return ResolutionResult(item=item, closed=closed, observation=observation)


def _incoming_for(event: Event, fields: dict) -> IncomingEvent:
    """The event's current facts with the editor's changes applied.

    Built from the stored event rather than from the source, so an edit changes exactly what
    the editor named and nothing else — including the gates, which stay where the pipeline
    put them.
    """
    venue_id = fields.get("venue_id", event.venue_id)
    fingerprint = event.venue_fingerprint
    if venue_id != event.venue_id:
        # **The fingerprint is the lifecycle fact, not the id.** `EventFacts` carries
        # `venue_fingerprint`, so `classify_change` compares hashes — leave it alone and a
        # venue move classifies as *no change at all*, the edit falls through to the silent
        # path, and the venue never actually moves. Carrying the new venue's fingerprint is
        # what makes it a `detail_changed`, bumps the version, and produces FR-54's third
        # subject ("moved to [new location]") for every saved user.
        venue = Venue.objects.using(CATALOG).filter(pk=venue_id).first()
        if venue is None:
            raise ValidationError(
                "No such venue.", details={"errors": [{"loc": ["venue_id"], "msg": "not found"}]}
            )
        fingerprint = venue.venue_fingerprint

    return IncomingEvent(
        title=fields.get("title", event.title),
        description=event.description,
        canonical_url=event.canonical_url,
        venue_id=venue_id,
        venue_fingerprint=fingerprint,
        title_fingerprint=event.title_fingerprint,
        start_utc=fields.get("start_time_utc", event.start_time_utc),
        end_utc=fields.get("end_time_utc", event.end_time_utc),
        start_time_local=event.start_time_local,
        start_time_tz=fields.get("start_time_tz", event.start_time_tz),
        status=EventStatus(event.status),
        is_sold_out=event.is_sold_out,
        series_id=event.series_id,
        tz_inference_confidence=event.tz_inference_confidence,
        extraction_confidence=event.extraction_confidence,
        publication_status=event.publication_status,
        tz_review_pending=event.tz_review_pending,
    )


__all__ = [
    "EDITABLE_FIELDS",
    "ResolutionResult",
    "approve_review_item",
    "check_review_edit",
    "dismiss_source_item",
    "edit_and_publish",
    "reject_review_item",
]
