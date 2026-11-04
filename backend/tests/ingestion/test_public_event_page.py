"""The public event page read: `get_public_event_by_slug`.

The endpoint tests live in `tests/api/test_public_event_page_api.py`. This file tests
the read on its own, without the HTTP layer — because the read carries the rules that
matter and the endpoint only carries them to the wire.

**The rules under test, and why each one exists:**

- **A past event resolves.** The listing's read refuses one; this one must not. A page
  that 404s the moment the doors open throws away every bit of ranking it spent months
  earning (FR-26).
- **An `in_review` event is not found.** The model's own comment says it — "not
  digest-eligible, not publicly listed" (AD-6, AD-8) — so it must never be publicly
  addressable.
- **A superseded event is not found, but says where to go.** The 404 carries the
  successor's slug, so the link a crawler already holds resolves forward rather than
  dying.
- **The slug match is exact.** A case-insensitive match would make two URLs for one page.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from django.db import connections
from django.test.utils import CaptureQueriesContext

from apps.ingestion.models import Event
from apps.ingestion.services.catalog_read import (
    EventNotFoundError,
    get_public_event_by_slug,
)
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import EventFactory, VenueFactory, make_superseded_pair

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)


def test_an_upcoming_published_event_resolves():
    event = EventFactory(start_time_utc=NOW + HOUR)

    page = get_public_event_by_slug(slug=event.slug)

    assert page.id == event.id
    assert page.slug == event.slug
    assert page.title == event.title


def test_a_past_event_resolves():
    """The case `get_event` deliberately refuses: the page stays addressable."""
    event = EventFactory(start_time_utc=NOW - HOUR)

    page = get_public_event_by_slug(slug=event.slug)

    assert page.id == event.id


def test_an_event_that_ended_long_ago_still_resolves():
    event = EventFactory(start_time_utc=NOW - timedelta(days=400))

    page = get_public_event_by_slug(slug=event.slug)

    assert page.id == event.id


def test_a_cancelled_event_still_resolves():
    """A cancelled event is a real event with a real page — the page reports the status."""
    event = EventFactory(start_time_utc=NOW - HOUR, status=Event.Status.CANCELLED)

    page = get_public_event_by_slug(slug=event.slug)

    assert page.id == event.id
    assert page.status == Event.Status.CANCELLED


def test_an_in_review_event_is_not_found():
    event = EventFactory(
        start_time_utc=NOW + HOUR, publication_status=Event.PublicationStatus.IN_REVIEW
    )

    with pytest.raises(EventNotFoundError):
        get_public_event_by_slug(slug=event.slug)


def test_an_in_review_event_that_has_already_started_is_not_found():
    """`in_review` is not public whatever its date — the two rules are independent."""
    event = EventFactory(
        start_time_utc=NOW - HOUR, publication_status=Event.PublicationStatus.IN_REVIEW
    )

    with pytest.raises(EventNotFoundError):
        get_public_event_by_slug(slug=event.slug)


def test_an_unknown_slug_is_not_found():
    with pytest.raises(EventNotFoundError):
        get_public_event_by_slug(slug="no-such-event")


def test_a_superseded_event_is_not_found():
    old, _ = make_superseded_pair(start_time_utc=NOW + HOUR)

    with pytest.raises(EventNotFoundError):
        get_public_event_by_slug(slug=old.slug)


def test_a_superseded_event_names_its_successor():
    """The 404 carries the successor's slug, so the link resolves forward."""
    old, new = make_superseded_pair(start_time_utc=NOW + HOUR)

    with pytest.raises(EventNotFoundError) as caught:
        get_public_event_by_slug(slug=old.slug)

    assert caught.value.details["superseded_by_slug"] == new.slug


def test_the_successor_itself_resolves():
    old, new = make_superseded_pair(start_time_utc=NOW + HOUR)

    page = get_public_event_by_slug(slug=new.slug)

    assert page.id == new.id


def test_the_slug_match_is_exact():
    """Two case variants would be two URLs for one page — a duplicate-URL fault."""
    event = EventFactory(start_time_utc=NOW + HOUR)

    with pytest.raises(EventNotFoundError):
        get_public_event_by_slug(slug=event.slug.upper())


def test_the_payload_carries_the_fields_the_page_and_json_ld_need():
    venue = VenueFactory(name="Town Hall", city="Brooklyn", country_code="US")
    event = EventFactory(
        start_time_utc=NOW + HOUR,
        end_time_utc=NOW + 2 * HOUR,
        venue=venue,
        title="Winter Sessions",
        description="An evening of quiet music.",
        canonical_url="https://events.example.test/winter-sessions",
        is_sold_out=True,
    )

    page = get_public_event_by_slug(slug=event.slug)

    assert page.title == "Winter Sessions"
    assert page.description == "An evening of quiet music."
    assert page.start_time_utc == event.start_time_utc
    assert page.end_time_utc == event.end_time_utc
    assert page.start_time_tz == event.start_time_tz
    assert page.venue_name == "Town Hall"
    assert page.venue_city == "Brooklyn"
    assert page.venue_country_code == "US"
    assert page.canonical_url == "https://events.example.test/winter-sessions"
    assert page.status == event.status
    assert page.is_sold_out is True


def test_the_venue_address_carries_the_name_the_city_and_the_country():
    """`Venue` has no street line, so the address is everything the schema actually holds."""
    venue = VenueFactory(name="Town Hall", city="Brooklyn", country_code="US")
    event = EventFactory(start_time_utc=NOW + HOUR, venue=venue)

    page = get_public_event_by_slug(slug=event.slug)

    assert page.venue_address == "Town Hall, Brooklyn, US"


def test_an_event_with_no_venue_resolves_and_carries_no_venue_facts():
    event = EventFactory(start_time_utc=NOW + HOUR, venue=None)

    page = get_public_event_by_slug(slug=event.slug)

    assert page.id == event.id
    assert page.venue_name is None
    assert page.venue_address is None
    assert page.venue_city is None
    assert page.venue_country_code is None


def test_the_event_version_is_the_rows_own_counter():
    """The revalidation work item compares it against a cached copy, so it must be the
    number the `guard_event_write` trigger wrote — not a re-derived one."""
    event = EventFactory(start_time_utc=NOW + HOUR)
    assert event.event_version == 1

    page = get_public_event_by_slug(slug=event.slug)

    assert page.event_version == event.event_version


def test_the_read_does_not_change_the_rows_version():
    event = EventFactory(start_time_utc=NOW + HOUR)

    get_public_event_by_slug(slug=event.slug)

    event.refresh_from_db(using=CATALOG)
    assert event.event_version == 1


def test_the_not_found_error_carries_the_slug():
    with pytest.raises(EventNotFoundError) as caught:
        get_public_event_by_slug(slug="nothing-here")

    assert caught.value.details["slug"] == "nothing-here"


def test_two_events_have_different_slugs_so_the_slug_addresses_one():
    """The premise of the whole read: `event_slug_uq` makes the slug a global address."""
    first = EventFactory(start_time_utc=NOW + HOUR)
    second = EventFactory(start_time_utc=NOW + 2 * HOUR)

    assert first.slug != second.slug
    assert get_public_event_by_slug(slug=first.slug).id == first.id
    assert get_public_event_by_slug(slug=second.slug).id == second.id


def test_a_slug_belonging_to_no_event_does_not_resolve_to_another_events_facts():
    """The lookup is by slug, so a wrong slug finds nothing rather than something else."""
    event = EventFactory(start_time_utc=NOW + HOUR)

    with pytest.raises(EventNotFoundError):
        get_public_event_by_slug(slug=f"{event.slug}-wrong")


def test_the_source_name_is_carried():
    event = EventFactory(start_time_utc=NOW + HOUR)

    page = get_public_event_by_slug(slug=event.slug)

    assert page.source_name == event.source.name


def test_an_id_is_not_a_slug():
    """The two reads are keyed differently; a UUID does not resolve as a slug."""
    EventFactory(start_time_utc=NOW + HOUR)

    with pytest.raises(EventNotFoundError):
        get_public_event_by_slug(slug=str(uuid4()))


# ── The structured data the read carries (AD-12) ───────────────────────────────────
#
# The projection itself is tested in `tests/domain/test_schema_org.py`. What matters
# here is that the read **carries** it, and that what it carries is built from the same
# row — one query, one source of truth.


def test_the_read_carries_the_finished_structured_data():
    event = EventFactory(start_time_utc=NOW + HOUR, title="Winter Sessions")

    page = get_public_event_by_slug(slug=event.slug)

    assert page.schema_org["@context"] == "https://schema.org"
    assert page.schema_org["@type"] == "Event"
    assert page.schema_org["name"] == "Winter Sessions"


def test_the_structured_data_is_projected_from_the_same_row():
    """The AD-12 guarantee, at the read.

    If the structured data were built by a second query, the two could describe
    different events. Asserting they describe the *same* one is the point.
    """
    event = EventFactory(start_time_utc=NOW + HOUR, title="Winter Sessions")

    page = get_public_event_by_slug(slug=event.slug)

    assert page.schema_org["name"] == page.title
    assert page.schema_org["name"] == event.title


def test_the_structured_data_reflects_the_events_own_status():
    event = EventFactory(start_time_utc=NOW + HOUR, status=Event.Status.CANCELLED)

    page = get_public_event_by_slug(slug=event.slug)

    assert page.schema_org["eventStatus"] == "https://schema.org/EventCancelled"


def test_the_structured_data_reflects_the_sold_out_flag():
    event = EventFactory(start_time_utc=NOW + HOUR, is_sold_out=True)

    page = get_public_event_by_slug(slug=event.slug)

    assert page.schema_org["offers"]["availability"] == "https://schema.org/SoldOut"


def test_the_structured_data_of_an_event_with_no_venue_has_no_location():
    event = EventFactory(start_time_utc=NOW + HOUR, venue=None)

    page = get_public_event_by_slug(slug=event.slug)

    assert "location" not in page.schema_org


def test_the_structured_data_carries_the_venue_when_there_is_one():
    venue = VenueFactory(name="Town Hall", city="Brooklyn", country_code="US")
    event = EventFactory(start_time_utc=NOW + HOUR, venue=venue)

    page = get_public_event_by_slug(slug=event.slug)

    assert page.schema_org["location"]["name"] == "Town Hall"
    assert page.schema_org["location"]["address"]["addressLocality"] == "Brooklyn"


def test_the_read_does_not_query_the_database_twice_for_the_structured_data():
    """The projection is pure, so the structured data costs no extra round trip."""
    event = EventFactory(start_time_utc=NOW + HOUR)

    with CaptureQueriesContext(connections[CATALOG]) as queries:
        get_public_event_by_slug(slug=event.slug)

    assert len(queries) == 1, "the read made more than one query: " + "; ".join(
        str(q["sql"]) for q in queries
    )
