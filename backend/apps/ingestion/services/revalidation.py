"""The revalidation outbox: record that a public page must be rebuilt, and deliver it
(FR-26, FR-27).

This is AD-17's outbox, for a different consumer. The shape is deliberately the same, because
the shape is already proven:

- A row is written **in the same transaction as the change that caused it**. That is what
  makes "never lost" true: a broker outage at enqueue time, or a crash between the commit
  and the enqueue, leaves the row behind for the reconciler.
- The enqueue is registered with `transaction.on_commit(..., robust=True)`, so it fires
  **after** the transaction commits. A rebuild fired from inside an uncommitted write would
  read the old row back and re-cache exactly the stale page it was meant to fix.
- The reconciler re-offers the rows nobody finished, on a cadence.

**What differs from AD-17's outbox:** the consumer. AD-17's is the *personal* propagation,
which is a reserved slot (`worker.tasks.propagate_state_change`) and whose marker is
`EventStateChange.propagated_at`. This one's consumer is the frontend's revalidation route
handler, and its marker is its own table — because `EventStateChange` is append-only with
exactly one mutable column and that column is spoken for.

**The paths are computed once, here, at enqueue time.** The frontend revalidates what it is
given and infers nothing, so the cascade rules live in one place (`domain.revalidation`) and
a path computed at delivery time — from a row that has since moved again — cannot drift from
the change that caused it.
"""

import logging
from datetime import datetime
from functools import partial
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from apps.ingestion.models import Event, RevalidationRequest, Venue
from domain.revalidation import paths_for_event
from shared.constants import (
    REVALIDATION_MAX_ATTEMPTS,
    REVALIDATION_RECONCILE_AFTER,
    REVALIDATION_RECONCILE_BATCH,
)
from shared.db import CATALOG

logger = logging.getLogger(__name__)

REVALIDATE_TASK = "worker.tasks.revalidate_public_pages"


def _send(task_name: str, args: list[str]) -> None:
    """Hand a job to the broker. The one seam tests replace."""
    from celery import current_app

    current_app.send_task(task_name, args=args)


def _city_slug_of(venue_id: UUID | None) -> str:
    """The canonical city's slug for a venue, or `""` when there is no city page.

    **A venue with no `city_ref` has no city page.** The backfill links venues to their
    city, and a venue that named no city resolves to none — the same rule Event Fit
    follows rather than guessing one. So there is nothing to revalidate for it.
    """
    if not venue_id:
        return ""
    venue = Venue.objects.using(CATALOG).select_related("city_ref").filter(pk=venue_id).first()
    if venue is None or venue.city_ref is None:
        return ""
    return venue.city_ref.slug


def paths_for_event_row(
    *,
    event: Event,
    previous_venue_id: UUID | None = None,
) -> tuple[str, ...]:
    """The paths one event's change makes stale.

    **The previous venue's city is why the state change records a venue id.** A venue
    fingerprint is a hash, and a hash cannot be reversed to "the old city was Brooklyn" — so
    an event that moved between cities could not have its old city page revalidated without
    it. `previous_venue_id` is read from the state change's `before` facts.
    """
    return paths_for_event(
        slug=event.slug,
        city_slug=_city_slug_of(event.venue_id),
        previous_city_slug=_city_slug_of(previous_venue_id),
        is_public=event.publication_status == Event.PublicationStatus.PUBLISHED,
        is_superseded=event.status == Event.Status.SUPERSEDED,
    )


def enqueue_revalidation(request_id: UUID) -> None:
    """Queue one request for delivery. Run it from `on_commit(using=CATALOG)` only."""
    _send(REVALIDATE_TASK, [str(request_id)])


def request_revalidation(
    *,
    event: Event,
    event_version: int,
    previous_venue_id: UUID | None = None,
    now: datetime | None = None,
    enqueue: bool = True,
) -> RevalidationRequest | None:
    """Record that this event's public pages must be rebuilt.

    **One open request per event.** A second lifecycle change while a request is open
    **updates** the open row's version and paths rather than opening a second one — that is
    the enqueue-side idempotency. The delivery side needs no dedup table, because
    rebuilding a page twice is harmless: `revalidatePath` is idempotent by construction.

    **The row is written in the caller's transaction**, so it commits with the change that
    caused it.

    **`enqueue=False` is what the write path uses.** The caller registers its own
    `transaction.on_commit` callback that calls `enqueue_revalidation` *after* the commit;
    the enqueue then happens there, outside any transaction, and needs no second
    `on_commit` registration. Registering one here as well would queue a callback that
    fires inside a transaction that has already committed — which Django runs immediately,
    but which makes the "one callback per change" count wrong and the mechanism harder to
    read than it needs to be.

    The enqueue is idempotent in any case: the delivery task finds nothing open when the
    request has already been closed.
    """
    moment = now or timezone.now()
    # **The paths come from the row as it stands, not from the caller's copy.** The write
    # path updates the Event with a queryset `.update()`, so the instance it holds still
    # shows the *old* venue — and a signal computed from it would name the old city page
    # and miss the new one. Reading the row back is also the rule the whole design rests
    # on: the page is built from the row as it stands.
    current = Event.objects.using(CATALOG).filter(pk=event.pk).first()
    if current is None:  # pragma: no cover - the event was deleted between write and here
        return None
    paths = paths_for_event_row(event=current, previous_venue_id=previous_venue_id)

    existing = (
        RevalidationRequest.objects.using(CATALOG)
        .filter(event=event, state=RevalidationRequest.State.OPEN)
        .first()
    )
    if existing is not None:
        existing.event_version = event_version
        existing.paths = list(paths)
        existing.requested_at = moment
        existing.last_error = ""
        existing.save(
            using=CATALOG,
            update_fields=["event_version", "paths", "requested_at", "last_error", "updated_at"],
        )
        request = existing
    else:
        try:
            request = RevalidationRequest.objects.using(CATALOG).create(
                event=event,
                event_version=event_version,
                paths=list(paths),
                state=RevalidationRequest.State.OPEN,
                requested_at=moment,
            )
        except IntegrityError:
            # Another writer opened a request for this event between our read and our write.
            # Theirs is the open one; update it rather than opening a second.
            request = (
                RevalidationRequest.objects.using(CATALOG)
                .filter(event=event, state=RevalidationRequest.State.OPEN)
                .first()
            )
            if request is None:  # pragma: no cover - the row was closed between the two reads
                return None
            request.event_version = event_version
            request.paths = list(paths)
            request.requested_at = moment
            request.last_error = ""
            request.save(
                using=CATALOG,
                update_fields=[
                    "event_version",
                    "paths",
                    "requested_at",
                    "last_error",
                    "updated_at",
                ],
            )

    # robust: a failed enqueue (broker down) is logged and the item stays committed; the
    # request row is already written, so the reconciler finds it (AD-17's guarantee).
    if enqueue:
        transaction.on_commit(partial(enqueue_revalidation, request.id), using=CATALOG, robust=True)
    return request


def open_request(request_id: UUID) -> RevalidationRequest | None:
    """The open request with this id, or `None` when it is not open any more."""
    return (
        RevalidationRequest.objects.using(CATALOG)
        .filter(pk=request_id, state=RevalidationRequest.State.OPEN)
        .first()
    )


def mark_delivered(request_id: UUID, *, now: datetime | None = None) -> bool:
    """Close a request that the frontend acknowledged. False if it was already closed.

    The conditional form is idempotent under the worker's retries and the reconciler, and it
    is what makes a **double delivery harmless**: the second attempt finds nothing open and
    does nothing.
    """
    updated = (
        RevalidationRequest.objects.using(CATALOG)
        .filter(pk=request_id, state=RevalidationRequest.State.OPEN)
        .update(
            state=RevalidationRequest.State.DELIVERED,
            closed_at=now or timezone.now(),
            last_error="",
        )
    )
    return updated == 1


def mark_failed(
    request_id: UUID,
    *,
    reason: str,
    permanent: bool = False,
    now: datetime | None = None,
) -> bool:
    """Record a failed delivery. The request stays open unless it is exhausted.

    **The attempt count is the bound.** A request that has failed `REVALIDATION_MAX_ATTEMPTS`
    times is **exhausted**: it is kept and surfaced, not retried forever. "This page is stale
    and we gave up" is a fact an operator needs to see, and a queue that retries forever hides
    it.

    **A permanent failure is not retried at all.** A wrong secret is a deployment
    misconfiguration, not a transient fault; retrying it forever is noise. It is recorded as
    `failed` and surfaced.

    **The increment is atomic.** Two workers can hold the same request — the reconciler and
    a direct enqueue — and a read-then-write would let both read `attempts=4` and both write
    `5`, losing an attempt and stretching the bound. `F("attempts") + 1` makes the database
    do the adding, so the count is right however many workers arrive.

    `reason` is a slug only — never a URL, never a response body (AD-13).
    """
    updated = (
        RevalidationRequest.objects.using(CATALOG)
        .filter(pk=request_id, state=RevalidationRequest.State.OPEN)
        .update(
            attempts=F("attempts") + 1,
            last_error=reason,
            **(
                {"state": RevalidationRequest.State.FAILED, "closed_at": now or timezone.now()}
                if permanent
                else {}
            ),
        )
    )
    if updated != 1:
        return False
    if permanent:
        return True
    # The bound is checked after the increment, because the increment is what decides
    # whether this attempt was the last one. A row that is already exhausted is not
    # touched again — it is a fact, not a thing to keep counting.
    RevalidationRequest.objects.using(CATALOG).filter(
        pk=request_id,
        state=RevalidationRequest.State.OPEN,
        attempts__gte=REVALIDATION_MAX_ATTEMPTS,
    ).update(
        state=RevalidationRequest.State.EXHAUSTED,
        closed_at=now or timezone.now(),
    )
    return True


def reconcile_revalidation(
    *, now: datetime | None = None, limit: int = REVALIDATION_RECONCILE_BATCH
) -> int:
    """Re-enqueue the open requests nobody has delivered, oldest first. Returns how many."""
    cutoff = (now or timezone.now()) - REVALIDATION_RECONCILE_AFTER
    ids = list(
        RevalidationRequest.objects.using(CATALOG)
        .filter(state=RevalidationRequest.State.OPEN, requested_at__lt=cutoff)
        .order_by("requested_at", "id")
        .values_list("id", flat=True)[:limit]
    )
    for request_id in ids:
        _send(REVALIDATE_TASK, [str(request_id)])
    return len(ids)
