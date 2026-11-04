"""The city page read: the events for `/events-in-{city}` (FR-27).

The **rules** about what a city page is — FR-27's ">5 events" threshold, and the
canonical city's identity — are the spec's. This file is about the catalog side: that
the listing reuses the preview's rules rather than reimplementing them, that the count
and the listing are computed by the same filters, that a sparse city degrades to "coming
soon" rather than 404ing, and that a page beyond the last one is empty rather than an
error.

**Every clock is an explicit `now`, like everywhere else in this codebase.** The
qualification window and the upcoming bound are both relative to it, and a test that
pins `now` can sit exactly on either boundary.
"""

from datetime import UTC, datetime, timedelta

import pytest
from django.db.models import F

from apps.ingestion.event_fit.reads import list_city_event_fits
from apps.ingestion.models import City, Event, EventFit
from apps.ingestion.services.city_read import (
    CityNotFoundError,
    get_city_page,
)
from shared.constants import (
    CITY_PAGE_EVENT_THRESHOLD,
    CITY_PAGE_MAX_PAGE_SIZE,
    CITY_PAGE_QUALIFICATION_WINDOW,
)
from shared.db import CATALOG
from tests.ingestion.factories import EventFactory, VenueFactory, make_superseded_pair

pytestmark = pytest.mark.django_db(databases=[CATALOG])

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)
DAY = timedelta(days=1)

# A city no other test uses, so the counts are exact.
CITY_NAME = "Testville"


def _city(name: str = CITY_NAME) -> City:
    """A canonical city row, written the way `resolve_city` writes one."""
    return City.objects.using(CATALOG).create(
        slug=name.lower().replace(" ", "-"),
        name=name,
        country_code="US",
        normalized_key=name.lower(),
        region="",
    )


def _fit(
    event: Event,
    *,
    city: City,
    score: int = 4,
    tags: list[str] | None = None,
    version: int | None = None,
) -> EventFit:
    """A fit row for an event in a city, written the way the writer writes one."""
    return EventFit.objects.using(CATALOG).create(
        event=event,
        city=city.name,
        city_ref=city,
        score=score,
        tags=tags if tags is not None else [],
        event_version=version if version is not None else event.event_version,
        computed_at=NOW,
    )


def _event(city: City | None = None, *, hours: float = 2, **overrides) -> Event:
    """An event in the city's venue, starting `hours` after `NOW`."""
    venue = VenueFactory(city=city.name if city else "Los Angeles", country_code="US")
    if city is not None:
        venue.city_ref = city
        venue.save(using=CATALOG)
    return EventFactory(start_time_utc=NOW + timedelta(hours=hours), venue=venue, **overrides)


def _city_with_events(count: int, *, city: City | None = None, hours: float = 2) -> City:
    """A city with `count` upcoming, published, current fits."""
    city = city or _city()
    for n in range(count):
        event = _event(city, hours=hours + n)
        _fit(event, city=city, score=4)
    return city


# ── The threshold: exactly 5 does not qualify, exactly 6 does ─────────────────────


def test_a_city_with_exactly_five_events_is_not_published():
    """FR-27 says ">5 events", which means **more than** five.

    The boundary is the whole point of the test: a `>=` where the spec says `>` would
    publish a city the spec does not want published, and the difference would never show
    up in any test that used six events.
    """
    city = _city_with_events(CITY_PAGE_EVENT_THRESHOLD)

    page = get_city_page(slug=city.slug, now=NOW)

    assert page.event_count == 5
    assert page.is_published is False


def test_a_city_with_exactly_six_events_is_published():
    city = _city_with_events(CITY_PAGE_EVENT_THRESHOLD + 1)

    page = get_city_page(slug=city.slug, now=NOW)

    assert page.event_count == 6
    assert page.is_published is True


def test_the_threshold_is_the_shared_constant():
    """The number is one constant, not a literal in the read and another in a test."""
    assert CITY_PAGE_EVENT_THRESHOLD == 5


# ── A sparse or empty city degrades gracefully, and does not 404 ───────────────────


def test_an_empty_city_is_a_well_formed_empty_result():
    """FR-27: "a city page degrades gracefully when no events are present"."""
    city = _city()

    page = get_city_page(slug=city.slug, now=NOW)

    assert page.items == ()
    assert page.event_count == 0
    assert page.is_published is False
    assert page.slug == city.slug


def test_a_sparse_city_still_answers_with_its_identity():
    """The page is about a *city*, so even an empty one says which city it is."""
    city = _city()

    page = get_city_page(slug=city.slug, now=NOW)

    assert page.name == city.name
    assert page.country_code == "US"
    assert page.region == ""


def test_an_unknown_city_slug_is_not_found():
    """An unknown slug is a URL that does not exist — a different question from a sparse
    city, and a different answer."""
    with pytest.raises(CityNotFoundError) as caught:
        get_city_page(slug="no-such-city", now=NOW)

    assert caught.value.code == "not_found"
    assert caught.value.details == {"slug": "no-such-city"}


def test_a_sparse_city_is_not_an_error():
    """The two cases are different, and the sparse one must not raise."""
    city = _city_with_events(2)

    page = get_city_page(slug=city.slug, now=NOW)

    assert page.is_published is False
    assert len(page.items) == 2


# ── The listing and the qualification measure different things ────────────────────


def test_a_city_that_has_had_events_keeps_its_page_between_seasons():
    """**This is why the qualification window is broader than the listing.**

    A city's events all pass. The listing is now empty — nothing is upcoming — but the
    city still had six events in the last year, so it still deserves its URL and its
    page still resolves. Without this, a city's page would 404 the moment its last
    event started, and a URL that 404s after ranking is worse than one that never
    ranked.
    """
    city = _city()
    for n in range(CITY_PAGE_EVENT_THRESHOLD + 1):
        event = _event(city, hours=-24 * (n + 1))  # all in the past
        _fit(event, city=city, score=4)

    page = get_city_page(slug=city.slug, now=NOW)

    assert page.items == (), "nothing is upcoming"
    assert page.event_count == 6, "but the city still had six events"
    assert page.is_published is True, "so the page still exists"


def test_the_qualification_window_has_a_boundary():
    """An event exactly at the window's edge is inside it; one just outside is not.

    The comparison is inclusive at the lower edge, so the window's length is what it
    says it is.

    **The start time is moved with a queryset update**, because `start_time_utc` is a
    lifecycle column: the database's guard trigger requires `event_version + 1` with
    any lifecycle change, and `original_start_utc` never moves at all. The update moves
    the start and bumps the version together, which is what the trigger asks for.
    """
    city = _city()
    at_the_edge = _event(city, hours=0)
    Event.objects.using(CATALOG).filter(pk=at_the_edge.pk).update(
        start_time_utc=NOW - CITY_PAGE_QUALIFICATION_WINDOW,
        event_version=F("event_version") + 1,
    )
    at_the_edge.refresh_from_db(using=CATALOG)
    _fit(at_the_edge, city=city, score=4)

    outside = _event(city, hours=-1)
    Event.objects.using(CATALOG).filter(pk=outside.pk).update(
        start_time_utc=NOW - CITY_PAGE_QUALIFICATION_WINDOW - timedelta(seconds=1),
        event_version=F("event_version") + 1,
    )
    outside.refresh_from_db(using=CATALOG)
    _fit(outside, city=city, score=4)

    page = get_city_page(slug=city.slug, now=NOW)

    assert page.event_count == 1, "only the event at the edge is inside the window"


def test_the_listing_shows_only_upcoming_events():
    """The listing looks forwards; the qualification looks backwards."""
    city = _city()
    past = _event(city, hours=-24)
    _fit(past, city=city, score=4)
    upcoming = _event(city, hours=2)
    _fit(upcoming, city=city, score=4)

    page = get_city_page(slug=city.slug, now=NOW)

    assert [item.id for item in page.items] == [upcoming.id]
    assert page.event_count == 2, "the count covers the window, not just the listing"


# ── The rules are the preview's rules ─────────────────────────────────────────────


def test_a_stale_fit_is_absent_from_the_listing():
    """The Event moved on since the fit was computed, so the fit describes an event
    that no longer exists. It is skipped, not served."""
    city = _city()
    event = _event(city)
    _fit(event, city=city, score=5, version=1)
    Event.objects.using(CATALOG).filter(pk=event.pk).update(event_version=F("event_version") + 1)

    page = get_city_page(slug=city.slug, now=NOW)

    assert page.items == ()
    assert page.event_count == 0, "a stale fit does not count either"


def test_a_city_whose_only_fits_are_stale_is_below_the_threshold():
    """The count and the listing are computed by the same filters, so a city whose
    events have all gone stale does not qualify."""
    city = _city()
    for n in range(CITY_PAGE_EVENT_THRESHOLD + 1):
        event = _event(city, hours=2 + n)
        _fit(event, city=city, score=5, version=1)
    Event.objects.using(CATALOG).update(event_version=F("event_version") + 1)

    page = get_city_page(slug=city.slug, now=NOW)

    assert page.event_count == 0
    assert page.is_published is False
    assert page.items == ()


def test_an_unpublished_event_is_not_listed():
    city = _city()
    event = _event(city)
    _fit(event, city=city, score=5)
    Event.objects.using(CATALOG).filter(pk=event.pk).update(
        publication_status=Event.PublicationStatus.IN_REVIEW
    )

    page = get_city_page(slug=city.slug, now=NOW)

    assert page.items == ()
    assert page.event_count == 0


def test_a_superseded_event_is_not_listed():
    """A superseded Event is terminal (D7), and its live replacement is listed instead.

    **The pair is built the way the database allows.** `event_superseded_consistent_ck`
    says a superseded Event must name its replacement, and the insert guard says a
    superseded Event cannot be created directly — so `make_superseded_pair` is the only
    way to get one, and this test uses it rather than writing the row by hand.
    """
    city = _city()
    old, _new = make_superseded_pair(
        start_time_utc=NOW + 2 * HOUR, venue=VenueFactory(city=city.name, country_code="US")
    )
    _fit(old, city=city, score=5)

    page = get_city_page(slug=city.slug, now=NOW)

    assert page.items == ()
    assert page.event_count == 0


def test_the_score_and_the_tags_are_served_as_stored():
    """AD-10: the fit is persisted and served as it stands. The read is not a
    calculator."""
    city = _city()
    event = _event(city)
    _fit(event, city=city, score=1, tags=["tomorrow", "in_testville"])

    item = get_city_page(slug=city.slug, now=NOW).items[0]

    assert item.score == 1, "the persisted score, not a recomputed one"
    assert item.tags == ("tomorrow", "in_testville")


# ── The ordering ──────────────────────────────────────────────────────────────────


def test_the_best_fit_comes_first():
    """The fit is the reason an event is on the page, so the score leads.

    The better-fit event is deliberately the **later** one: a soon event that also
    happens to be the best fit would not tell the two orderings apart.
    """
    city = _city()
    sooner = _event(city, hours=2)
    better_fit_but_later = _event(city, hours=48)
    _fit(sooner, city=city, score=3)
    _fit(better_fit_but_later, city=city, score=5)

    page = get_city_page(slug=city.slug, now=NOW)

    assert [item.id for item in page.items] == [better_fit_but_later.pk, sooner.pk]


def test_a_score_tie_is_broken_on_the_start_time():
    """Two events with the same fit: the sooner one is the more useful one."""
    city = _city()
    later = _event(city, hours=48)
    sooner = _event(city, hours=2)
    _fit(later, city=city, score=3)
    _fit(sooner, city=city, score=3)

    page = get_city_page(slug=city.slug, now=NOW)

    assert [item.id for item in page.items] == [sooner.pk, later.pk]


def test_the_order_is_total():
    """Two events that agree on score *and* start time still have a defined order.

    The tiebreak is the event id, which is a UUIDv7 — time-ordered, and unique. Without
    it, two rows could swap places between two requests and a row could appear on two
    pages, or on none.
    """
    city = _city()
    first = _event(city, hours=2)
    second = _event(city, hours=2)
    _fit(first, city=city, score=3)
    _fit(second, city=city, score=3)

    page = get_city_page(slug=city.slug, now=NOW)

    assert {item.id for item in page.items} == {first.pk, second.pk}
    assert len(page.items) == 2


# ── The paging ─────────────────────────────────────────────────────────────────────


def test_a_city_above_the_threshold_pages_across_two_pages():
    """The listing is unbounded, and a crawler walks it a page at a time.

    Seven events, three to a page: the first two pages hold six of them and the
    seventh is on the third. The two pages **do not overlap** — that is the property
    that makes the walk a walk rather than a loop — and together they hold the first
    six in the listing's order.
    """
    city = _city_with_events(CITY_PAGE_EVENT_THRESHOLD + 2)
    everything = get_city_page(slug=city.slug, now=NOW).items

    first = get_city_page(slug=city.slug, now=NOW, page=1, page_size=3)
    second = get_city_page(slug=city.slug, now=NOW, page=2, page_size=3)
    third = get_city_page(slug=city.slug, now=NOW, page=3, page_size=3)

    assert len(first.items) == 3
    assert len(second.items) == 3
    assert len(third.items) == 1
    walked = [item.id for item in (*first.items, *second.items, *third.items)]
    assert walked == [item.id for item in everything], "the walk visits every event, in order"
    assert len(set(walked)) == len(walked), "and visits none of them twice"


def test_a_page_beyond_the_last_one_is_empty_rather_than_an_error():
    """A crawler walking off the end of a listing is doing something ordinary."""
    city = _city_with_events(3)

    page = get_city_page(slug=city.slug, now=NOW, page=99, page_size=3)

    assert page.items == ()
    assert page.page == 99
    assert page.has_next is False


def test_the_page_size_is_capped():
    """A request cannot ask for a city's whole history in one response."""
    city = _city_with_events(3)

    page = get_city_page(slug=city.slug, now=NOW, page_size=10_000)

    assert page.page_size == CITY_PAGE_MAX_PAGE_SIZE


def test_a_page_below_one_is_the_first_page():
    city = _city_with_events(2)

    page = get_city_page(slug=city.slug, now=NOW, page=0)

    assert page.page == 1
    assert len(page.items) == 2


def test_has_next_says_whether_there_is_another_page():
    city = _city_with_events(3)

    first = get_city_page(slug=city.slug, now=NOW, page=1, page_size=2)
    second = get_city_page(slug=city.slug, now=NOW, page=2, page_size=2)

    assert first.has_next is True
    assert second.has_next is False


def test_an_off_season_city_has_no_next_page():
    """**The paging flag is measured against the listing, not against the
    qualification.**

    A city whose six events have all passed has a qualifying count of six and an empty
    listing. If `has_next` were measured against the qualifying count, it would be
    `True` — and a crawler would follow "next" to an empty page, and follow it again,
    forever. The listing is empty, so there is no next page.
    """
    city = _city()
    for n in range(CITY_PAGE_EVENT_THRESHOLD + 1):
        event = _event(city, hours=-24 * (n + 1))  # all in the past
        _fit(event, city=city, score=4)

    page = get_city_page(slug=city.slug, now=NOW)

    assert page.items == ()
    assert page.event_count == 6, "the city still qualifies"
    assert page.has_next is False, "but there is nothing on the page to page through"


def test_has_next_is_measured_against_the_upcoming_count():
    """The listing's total is the denominator, not the qualifying count.

    Six events qualify the city; only three of them are upcoming. A page of two must
    report a next page (the third is there) and the page of three must not — even
    though the qualifying count is six and would say "next" for several pages more.
    """
    city = _city()
    for n in range(3):
        _fit(_event(city, hours=-24 * (n + 1)), city=city, score=4)  # in the past
    for n in range(3):
        _fit(_event(city, hours=2 + n), city=city, score=4)  # upcoming

    page = get_city_page(slug=city.slug, now=NOW, page=1, page_size=2)

    assert page.event_count == 6, "all six qualify"
    assert len(page.items) == 2, "but only the upcoming three are listed"
    assert page.has_next is True, "there is a third upcoming event to page to"


def test_the_last_page_of_the_listing_has_no_next():
    """The final page of the *upcoming* events ends the walk, whatever the
    qualification count says."""
    city = _city()
    for n in range(3):
        _fit(_event(city, hours=-24 * (n + 1)), city=city, score=4)
    for n in range(3):
        _fit(_event(city, hours=2 + n), city=city, score=4)

    page = get_city_page(slug=city.slug, now=NOW, page=2, page_size=2)

    assert len(page.items) == 1, "the third upcoming event"
    assert page.has_next is False, "and there is nothing after it"


# ── The canonical city, not the raw string ────────────────────────────────────────


def test_the_events_carry_the_canonical_city_name():
    """The page's events carry the **canonical** city's name, not the fit row's free
    text.

    A fit row stores whatever spelling the venue wrote — `"Brooklyn"`, `"brooklyn "`,
    `"Brooklyn, NY"` — and the preview is keyed on that free text, so it needs it. But
    this page is keyed on the canonical city, and its heading is the canonical name.
    Serving the free text would put two spellings side by side under one heading.
    """
    city = _city()
    event = _event(city)
    fit = _fit(event, city=city, score=5)
    # The fit row's own city, written the way the writer writes it: the venue's spelling.
    EventFit.objects.using(CATALOG).filter(pk=fit.pk).update(city="  brooklyn  ")

    page = get_city_page(slug=city.slug, now=NOW)

    assert page.name == "Testville", "the heading is the canonical name"
    assert page.items[0].city == "Testville", "and so is each event's city"


def test_the_page_is_keyed_on_the_canonical_city():
    """`Brooklyn` and `Brooklyn, NY` are two cities by construction, and each gets its
    own page — the slug is what addresses them."""
    brooklyn = City.objects.using(CATALOG).create(
        slug="brooklyn", name="Brooklyn", country_code="US", normalized_key="brooklyn", region=""
    )
    brooklyn_ny = City.objects.using(CATALOG).create(
        slug="brooklyn-ny",
        name="Brooklyn",
        country_code="US",
        normalized_key="brooklyn",
        region="ny",
    )
    assert brooklyn_ny.pk != brooklyn.pk, "the two spellings are two cities"
    event = _event(brooklyn)
    _fit(event, city=brooklyn, score=5)

    page = get_city_page(slug="brooklyn", now=NOW)

    assert len(page.items) == 1
    assert get_city_page(slug="brooklyn-ny", now=NOW).items == ()


def test_the_slug_match_is_exact():
    """Two case variants would be two URLs for one page — a duplicate-URL fault."""
    city = _city()

    with pytest.raises(CityNotFoundError):
        get_city_page(slug=city.slug.upper(), now=NOW)


# ── The read is a read ────────────────────────────────────────────────────────────


def test_the_read_never_writes():
    """`ingestion` is the sole writer (AD-16), and this read is not the exception."""
    from django.db import connections
    from django.test.utils import CaptureQueriesContext

    city = _city_with_events(3)

    with CaptureQueriesContext(connections[CATALOG]) as queries:
        get_city_page(slug=city.slug, now=NOW)

    writes = ("INSERT", "UPDATE", "DELETE")
    assert all(not q["sql"].lstrip().upper().startswith(writes) for q in queries)


def test_the_read_does_not_reach_the_personal_schema():
    """AD-12: not "does not return personal data" — does not *query* `personal`."""
    from django.db import connections
    from django.test.utils import CaptureQueriesContext

    from shared.db import PERSONAL

    city = _city_with_events(3)

    with CaptureQueriesContext(connections[PERSONAL]) as personal_queries:
        get_city_page(slug=city.slug, now=NOW)

    assert len(personal_queries) == 0


def test_the_canonical_reader_is_the_same_rules_as_the_preview():
    """The two reads share the rules; this asserts they share the *results*.

    The preview is keyed on the free-text city and the page on the canonical city, so
    they see the same rows when both spellings name the same city — and a divergence
    here would mean the staleness rule had been implemented twice.
    """
    from apps.ingestion.event_fit.reads import list_event_fit_for_city

    city = _city_with_events(3)

    by_name = [entry.id for entry in list_event_fit_for_city(city=city.name, now=NOW)]
    by_ref = [entry.id for entry in list_city_event_fits(city_ref_id=city.pk, now=NOW)]

    assert by_name == by_ref
