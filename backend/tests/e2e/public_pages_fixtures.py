"""The catalog the public-pages proof walks: a city, its events, and the three absences.

**Why these are functions and not factories.** `tests/ingestion/factories.py` builds an
`Event` at version 1 with a `Venue` that has **no `city_ref`** — and the city page is
keyed on the canonical city. Three of the shapes this proof needs cannot be built with
`factory_boy` alone:

- **a city with six current fits.** FR-27's threshold is `> CITY_PAGE_EVENT_THRESHOLD`,
  and the threshold is 5 — so *five* does not qualify and *six* does. A city that
  qualifies needs six events, six venues that point at it, and six fit rows whose
  `event_version` matches their event's.
- **a stale fit.** The staleness rule is `fit.event_version == event.event_version`. The
  insert guard refuses a lifecycle change without a version bump, so the only way to
  make a fit stale is to bump the event's version *through the write path* — which is
  exactly what the proof should do, because that is what really happens. **So
  `make_fit` does not take an `event_version` override**: the proof builds a stale row
  by moving the *event* on, and a helper that could write a deliberately wrong version
  would be a second way to say the same thing — and the wrong one, because it would
  describe a row the write path can never produce.
- **an `in_review` event.** `EventFactory` publishes everything; the gate is flipped
  with a plain update, which the trigger allows (publication is not a lifecycle
  column).

**The city is a real `City` row, written the way `resolve_city` writes one.** The
identity is `(normalized_key, region, country_code)`, so the fixtures use a slug and a
name no other test uses — the counts the proof asserts are then exact.

**Every event starts in the future, except the one that must not.** `EventFactory`'s
default `start_time_utc` is `FIRST_START + n days`, which is in the future relative to
this project's frozen dates but is a *fixed* instant — and a proof whose events are
pinned to a fixed instant would be pinned to a moment in the past as soon as the
calendar moved on. So the fixtures compute their starts from `now`, the same way
`tests/api/test_city_page_api.py` does: `BASE = timezone.now() + timedelta(days=30)`.
The one exception is the **past event**, which is deliberately in the past — it is the
case `catalog.get_event` refuses and `get_public_event_by_slug` serves.
"""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.ingestion.models import City, Event, EventFit
from apps.ingestion.services.event_writes import IncomingEvent
from domain.lifecycle import EventStatus
from shared.db import CATALOG
from tests.ingestion.factories import EventFactory, VenueFactory

#: How far ahead of "now" the proof's events start.
#:
#: **Thirty days**, so the events are comfortably "upcoming" for any read that bounds
#: by the wall clock, and comfortably inside FR-27's 365-day qualification window.
BASE = timezone.now() + timedelta(days=30)

#: The city every count in the proof is exact for.
#:
#: **A slug and a name no other test uses.** The threshold is a count, so a shared slug
#: would make every count in the suite depend on every other test's rows.
CITY_SLUG = "proofville"
CITY_NAME = "Proofville"

#: The number of current fits the proof's city carries.
#:
#: **Six, and the number matters.** FR-27's threshold is `> 5`, so five does not
#: publish a city page and six does. A city with five would make the whole proof
#: vacuous — every listing would be empty and every "the event is on the page" assertion
#: would fail for the wrong reason.
QUALIFYING_FITS = 6


def make_city(*, slug: str = CITY_SLUG, name: str = CITY_NAME) -> City:
    """A canonical city row, written the way `resolve_city` writes one."""
    return City.objects.using(CATALOG).create(
        slug=slug,
        name=name,
        country_code="US",
        normalized_key=name.lower(),
        region="",
    )


def make_venue(city: City, *, name: str = "The Proof Room") -> object:
    """A venue that points at the canonical city.

    **`city_ref` is set explicitly, and it is the whole point.** `VenueFactory` leaves
    it null — the backfill is what fills it in production — and a venue with no
    `city_ref` produces a fit row with no `city_ref`, which no city page ever reads. A
    city page built on such rows is empty for a reason that has nothing to do with the
    rules the proof is about.
    """
    venue = VenueFactory(name=name, city=city.name, country_code="US")
    venue.city_ref = city
    venue.save(using=CATALOG)
    return venue


def make_event(city: City, *, hours: float = 2, title: str = "Proof Event", **overrides) -> Event:
    """An event in the city's venue, starting `hours` after `BASE`.

    **The venue is the city's venue**, so the event's own `venue.city_ref` is the city
    — which is what the revalidation signal reads when it computes the city page's
    path.

    **The description is set, because a page with no description is not a page.** The
    public event page's payload carries the description as one of the facts a reader
    needs, and `EventFactory` leaves it blank — so a proof that asserted the description
    was present would be asserting something the factory never provided.
    """
    venue = make_venue(city, name=f"{title}'s Room")
    overrides.setdefault("description", f"{title} — a proof event at {venue.name} in {city.name}.")
    return EventFactory(
        start_time_utc=BASE + timedelta(hours=hours),
        end_time_utc=BASE + timedelta(hours=hours + 1),
        venue=venue,
        title=title,
        **overrides,
    )


def make_fit(event: Event, *, city: City, score: int = 4) -> EventFit:
    """A fit row for an event in a city.

    **The row records the event's own version** — which is what makes it *current*. A
    stale row is one whose version is behind the event's, and the proof builds it by
    moving the *event* on through the write path, not by writing a wrong version here.
    """
    return EventFit.objects.using(CATALOG).create(
        event=event,
        city=city.name,
        city_ref=city,
        score=score,
        tags=["tonight"],
        event_version=event.event_version,
        computed_at=BASE,
    )


def make_published_city(*, count: int = QUALIFYING_FITS) -> tuple[City, list[Event]]:
    """A city with `count` upcoming, published, **current** fits.

    **The fits are current by construction** — each row records the event's own
    version — so the city page's qualifying count is exactly `count`, and the proof's
    "this event is on the page" assertions are about the *staleness* rule rather than
    about a miscount.
    """
    city = make_city()
    events: list[Event] = []
    for n in range(count):
        event = make_event(city, hours=2 + n, title=f"Proof Event {n + 1}")
        make_fit(event, city=city)
        events.append(event)
    return city, events


def make_in_review_event(city: City, *, title: str = "Unreviewed Event") -> Event:
    """An event that is **not** published.

    **Publication is a gate, not a lifecycle fact** — so flipping it is a plain update,
    no version bump, and the trigger allows it (`publication_status` is not one of the
    lifecycle columns it guards).

    The event is otherwise ordinary: it has a venue in the city and a start in the
    future, so the *only* reason it can be missing from a public surface is its
    publication gate. **That is what makes the proof's `in_review` assertions worth
    anything** — the event differs from the published ones in exactly one respect.
    """
    event = make_event(city, hours=5, title=title)
    Event.objects.using(CATALOG).filter(pk=event.pk).update(
        publication_status=Event.PublicationStatus.IN_REVIEW
    )
    event.refresh_from_db(using=CATALOG)
    return event


def make_past_event(city: City, *, title: str = "Last Month's Event") -> Event:
    """An event that has already happened — the case `get_public_event` refuses.

    **`get_public_event_by_slug` has no time bound**, so this event still has a page.
    The proof asserts that it does, and that the page has content — a 200 with an empty
    body would satisfy a status-only assertion and prove nothing.
    """
    return EventFactory(
        start_time_utc=timezone.now() - timedelta(days=30),
        end_time_utc=timezone.now() - timedelta(days=30) + timedelta(hours=2),
        venue=make_venue(city, name="Last Month's Room"),
        title=title,
    )


def incoming_for(event: Event, **overrides) -> IncomingEvent:
    """The `IncomingEvent` the write path takes, built from the event as it stands.

    **This exists because the write path writes the incoming row *wholesale*.**
    `apply_lifecycle_change` does `rows.update(**incoming.columns(), …)` — it does not
    merge, and it does not know which fields the change touched. So an `IncomingEvent`
    that does not carry the event's own facts *erases them*: a builder with
    `venue_id=None` un-hooks the event from its venue, and a builder with a fixed
    `start_utc` moves the event to a day it never said it would be at.

    **And erasing the venue would erase the city.** The revalidation signal names the
    city page by reading the event's *current* venue — so an event whose venue was
    nulled by the write path names no city page at all, and the proof would be
    asserting the wrong thing about the wrong page.

    So the builder starts from the event's own columns and **overrides only what the
    change is about**. Everything else — the venue, the start, the times, the zone, the
    fingerprints, the gates — is carried over unchanged, which is what the ingest
    pipeline does when the source re-reports the same event with one fact changed.
    """
    defaults = {
        "title": event.title,
        "description": event.description,
        "canonical_url": event.canonical_url,
        "venue_id": event.venue_id,
        "venue_fingerprint": event.venue_fingerprint,
        "title_fingerprint": event.title_fingerprint,
        "start_utc": event.start_time_utc,
        "end_utc": event.end_time_utc,
        "start_time_local": event.start_time_local,
        "start_time_tz": event.start_time_tz,
        "status": EventStatus(event.status),
        "is_sold_out": event.is_sold_out,
        "series_id": event.series_id,
        "tz_inference_confidence": Decimal("1.00"),
        "extraction_confidence": Decimal("1.00"),
        "publication_status": event.publication_status,
        "tz_review_pending": event.tz_review_pending,
    }
    return IncomingEvent(**(defaults | overrides))


__all__ = [
    "BASE",
    "CITY_NAME",
    "CITY_SLUG",
    "QUALIFYING_FITS",
    "incoming_for",
    "make_city",
    "make_event",
    "make_fit",
    "make_in_review_event",
    "make_past_event",
    "make_published_city",
    "make_venue",
]
