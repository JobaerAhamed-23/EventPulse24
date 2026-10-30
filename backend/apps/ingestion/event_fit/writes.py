"""Event Fit: the one writer for the catalog's per-city fit rows (AD-10, FR-26).

**This module is the only thing that writes `EventFit`.** AD-10 says the explanation is
persisted and never recomputed at render; that means somebody has to write it, and there
is exactly one somebody: this command, called from the ingest path and from the tick.

**Why a service and not a model method.** AD-5: writes are named commands that take an
explicit `Actor` and `now`, and that leave an audit row in the same transaction. A
`Model.save()` that quietly recomputed a fit would break every one of those rules at
once — no actor, no clock it controls, no audit trail, and a write that can happen from
anywhere.

**The staleness problem.** "Tonight" is a statement about *now*, so a persisted tag goes
stale as time passes, not only when the event changes. The choice is in the run's plan:
the row is **recomputed on a cadence, by a writer** — `refresh_event_fits` — and the read
path serves the persisted row and computes nothing. AD-10's rule is that the *render*
never computes; a writer that recomputes on a schedule is the opposite of that.

**`event_version` is the staleness check.** Every fit records the Event version it was
computed from. A row whose version no longer matches its Event is stale and is never
served. The check lives in the read (`catalog_read.list_event_fit_for_city`) rather than
in a trigger, because the refresh is a writer's work and a trigger cannot decide that a
row *should* be refreshed — only that a row is now out of date, which the read already
knows how to skip.

**A city with no fit row.** An event whose venue has no city gets no Event Fit row at
all. The city is not guessed from the source, the event's title, or the source's city:
an event in an unknown city is not in any city's preview, and a preview that puts it in
the wrong one is worse than a preview that leaves it out.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from django.db import transaction

from apps.ingestion.models import Event, EventFit
from apps.ingestion.services.audit import write_audit
from domain.event_fit import compute_event_fit
from shared.actor import Actor
from shared.constants import EVENT_FIT_REFRESH_BATCH_SIZE
from shared.db import CATALOG

# The audit action for a fit recomputation. One action for every write, so the audit log
# reads as "the fits were recomputed" rather than as a log of every tag.
AUDIT_ACTION = "event_fit.recomputed"


def _city_of(event: Event) -> str:
    """The venue's city, or "" when the event has no venue city.

    `venue` is the registry venue; `venue_fingerprint` is a copy of the venue's identity
    string and carries no city, so the city can only come from the relation.
    """
    return event.venue.city.strip() if event.venue_id and event.venue else ""


def _confidence_of(event: Event) -> Decimal | None:
    """The event's extraction confidence, or None when it was never scored.

    The column is not nullable on `Event` today, so this is None only for an event
    written by hand. The domain function treats None as "score on proximity alone",
    which is the right behaviour: no confidence is not a reason to refuse an indicator.
    """
    return event.extraction_confidence


def compute_fit_for_event(event: Event, *, now: datetime) -> tuple[int, tuple[str, ...]] | None:
    """The fit for one event in its own city's local terms, or None if it has no city.

    This is the seam between the domain function and the row: it reads the event's
    columns, calls the pure function, and hands back the result. It writes nothing.
    """
    city = _city_of(event)
    if not city:
        return None
    fit = compute_event_fit(
        start_time_utc=event.start_time_utc,
        end_time_utc=event.end_time_utc,
        start_time_tz=event.start_time_tz,
        extraction_confidence=_confidence_of(event),
        city=city,
        now=now,
    )
    return fit.score, fit.tags


def write_event_fit(
    *,
    event: Event,
    now: datetime,
    actor: Actor,
) -> EventFit | None:
    """Compute the event's fit and persist it. Returns the row, or None if it has no city.

    The write is an **upsert** on `(event, city)`: a recomputation replaces the previous
    row's score and tags rather than adding a second one. That is what makes the command
    idempotent, and it is why the backfill can be run twice without doubling the rows.

    **A row for the same event under a *different* city is retired.** The key is
    `(event, city)`, so a venue whose city changes would otherwise leave the old city's
    row behind and the event would appear in **two** previews — with the old city's
    place tag on one of them. Nothing else would catch it: a venue edit does not bump
    the event's `event_version`, so the old row's version still matches and the read's
    staleness guard passes it straight through. A preview that shows an event in a city
    it has left is worse than one that leaves it out.

    **A row that already says the same thing is not rewritten.** The plan's own words:
    "a row that already matches is not rewritten (the `computed_at` does not move, so a
    test can assert that)". That is what makes the backfill idempotent in the strong
    sense — not merely "the row count does not grow", but "nothing about the row
    changes". A `computed_at` that moves on every run is a lie about when the fit was
    last computed, and it also means the refresh writes the whole published catalog
    every fifteen minutes whether or not anything about it changed.

    The row's `event_version` is the event's version **as it stands after the caller's
    write**, so a fit computed immediately after a lifecycle change records the new
    version and is not stale. The caller must pass the event as it is after its own
    write — that is, the one whose `event_version` the fit is computed from.
    """
    city = _city_of(event)
    if not city:
        return None

    computed = compute_fit_for_event(event, now=now)
    if computed is None:  # pragma: no cover — the city check above already returned
        return None
    score, tags = computed

    existing = (
        EventFit.objects.using(CATALOG).filter(event_id=event.pk).filter(city__iexact=city).first()
    )
    if (
        existing is not None
        and existing.score == score
        and list(existing.tags) == list(tags)
        and existing.event_version == event.event_version
    ):
        # The row already says exactly this. Leave it alone — including its
        # `computed_at`, which says when the fit was last *computed*, and it has not
        # been computed again.
        row = existing
    else:
        row, _created = EventFit.objects.using(CATALOG).update_or_create(
            event_id=event.pk,
            city=city,
            defaults={
                "score": score,
                "tags": list(tags),
                "event_version": event.event_version,
                "computed_at": now,
            },
        )
    # The event belongs to exactly one city, so any other row for this event is a row
    # for a city it has left. The city comparison is case-insensitive because the read
    # is: "Brooklyn" and "brooklyn" are the same city, and two rows for the same city
    # spelled two ways would put the event in that city's preview twice.
    EventFit.objects.using(CATALOG).filter(event_id=event.pk).exclude(city__iexact=city).delete()
    write_audit(
        actor=actor,
        action=AUDIT_ACTION,
        target_type="event_fit",
        target_id=row.pk,
        details={
            "event_id": str(event.pk),
            "city": city,
            "score": score,
            "tags": list(tags),
            "event_version": event.event_version,
        },
    )
    return row


def refresh_event_fits(
    *,
    events: list[Event],
    now: datetime,
    actor: Actor,
) -> int:
    """Recompute the fit for each event given. Returns how many rows were written.

    The caller owns the transaction and the batching: this function writes a fit for
    every event in the list, in one transaction, and reports how many rows that was.
    Events with no venue city are skipped — they have no row to write.
    """
    written = 0
    for event in events:
        if write_event_fit(event=event, now=now, actor=actor) is not None:
            written += 1
    return written


def refresh_stale_event_fits(
    *,
    now: datetime,
    actor: Actor,
    batch_size: int = EVENT_FIT_REFRESH_BATCH_SIZE,
) -> int:
    """Recompute the fit for every published event that has one.

    This is the **staleness refresh**: the tick's answer to "Tonight" going out of date.
    It recomputes the fits of published, non-superseded events — the ones a preview can
    show — and leaves the rest alone. A cancelled or superseded event's fit is never
    served, so recomputing it would be work for nothing.

    The events are read in batches and each batch is written in its own transaction, so
    a run over a large catalog does not hold one long transaction open. The cost is
    bounded, as the work item asks: one pass over the published events, in batches.

    The batches are walked by **primary key**, not by an offset: the first batch of a
    run has to move forward, or the second read would return the first batch again and
    the loop would never end.
    """
    written, _seen = _fit_published_events(now=now, actor=actor, batch_size=batch_size)
    return written


def backfill_event_fits(
    *,
    now: datetime,
    actor: Actor,
    batch_size: int = EVENT_FIT_REFRESH_BATCH_SIZE,
) -> tuple[int, int]:
    """Compute and persist the fit for every published event. Returns `(written, seen)`.

    **Idempotent.** The write is an upsert on `(event, city)`, so a second run replaces
    the rows rather than adding more. The command calls this, and so does anything else
    that needs the catalog brought up to date.

    `seen` is how many published events were considered and `written` is how many rows
    were written. The two differ when an event has no venue city — it has no row to
    write — and the difference is worth reporting rather than hiding.

    This and the staleness refresh do the same work — the fit of every published event
    is recomputed either way — so they share one implementation. The difference is only
    what the caller does with the count.
    """
    return _fit_published_events(now=now, actor=actor, batch_size=batch_size)


def _fit_published_events(
    *,
    now: datetime,
    actor: Actor,
    batch_size: int,
) -> tuple[int, int]:
    """The one pass over the published events: recompute each fit, in batches."""
    written = 0
    seen = 0
    last_id: UUID | None = None
    while True:
        queryset = (
            Event.objects.using(CATALOG)
            .filter(
                publication_status=Event.PublicationStatus.PUBLISHED,
                venue__isnull=False,
            )
            .exclude(status=Event.Status.SUPERSEDED)
        )
        if last_id is not None:
            queryset = queryset.filter(pk__gt=last_id)
        events = list(queryset.order_by("pk")[:batch_size])
        if not events:
            return written, seen
        with transaction.atomic(using=CATALOG):
            written += refresh_event_fits(events=events, now=now, actor=actor)
        seen += len(events)
        last_id = events[-1].pk


def count_published_events_with_a_city() -> int:
    """How many published events could have a fit row.

    This is the `--dry-run` count: the events the backfill would consider. It excludes
    the events with no venue city, because those have no row to write and are not
    candidates.
    """
    return (
        Event.objects.using(CATALOG)
        .filter(
            publication_status=Event.PublicationStatus.PUBLISHED,
            venue__isnull=False,
        )
        .exclude(status=Event.Status.SUPERSEDED)
        .count()
    )


__all__ = [
    "AUDIT_ACTION",
    "backfill_event_fits",
    "compute_fit_for_event",
    "count_published_events_with_a_city",
    "refresh_event_fits",
    "refresh_stale_event_fits",
    "write_event_fit",
]
