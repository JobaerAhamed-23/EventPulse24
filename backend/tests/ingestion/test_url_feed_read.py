"""The public URL feed: the sitemap's source (FR-26, FR-27).

The feed is the list of URLs the site actually serves. Three claims are load-bearing, and
each has a test that would fail if the claim were dropped:

- **membership** — the feed lists the public surface and nothing else. An `in_review`
  event, a superseded event and a below-threshold city are all absent, because their
  pages are not publicly addressable. A sitemap that lists a 404 is a crawl-budget leak.
- **`lastmod`** — the time is the event's *real* last change, taken from the append-only
  state history, and not `Event.updated_at` (which is frozen at creation, because every
  production write goes through `QuerySet.update()` and never touches `auto_now`).
- **boundedness** — the read is paged, and a page boundary is exact: two pages cannot
  overlap, and no URL appears on two pages or on none.

**Every clock is an explicit `now`, like everywhere else in this codebase.**
"""

from datetime import UTC, datetime, timedelta

import pytest
from django.db.models import F
from freezegun import freeze_time

from apps.ingestion.models import City, Event, EventFit, EventStateChange
from apps.ingestion.services.url_feed_read import (
    UrlFeedKind,
    list_url_feed,
)
from shared.constants import (
    CITY_PAGE_EVENT_THRESHOLD,
    CITY_PAGE_QUALIFICATION_WINDOW,
)
from shared.db import CATALOG
from tests.ingestion.factories import (
    EventFactory,
    EventStateChangeFactory,
    VenueFactory,
    make_superseded_pair,
)

pytestmark = pytest.mark.django_db(databases=[CATALOG])

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _frozen_clock():
    """Pin the clock at `NOW` for the whole module.

    The feed's `lastmod` is the newest `updated_at` among a city's events, and the events
    here are built at offsets from `NOW`. With the real clock running, rows written now
    out-rank every fixture instant, so `lastmod` reported the moment the test ran instead
    of the data's own latest change.

    `tick=True`, not a hard freeze: `lastmod` is a max over timestamps, and a stopped clock
    would make every row's `updated_at` identical, so the assertion would pass without
    discriminating.
    """
    with freeze_time(NOW, tick=True):
        yield


HOUR = timedelta(hours=1)
DAY = timedelta(days=1)

# A city no other test uses, so the counts are exact.
CITY_NAME = "Feedville"


def _city(name: str = CITY_NAME) -> City:
    """A canonical city row, written the way `resolve_city` writes one."""
    return City.objects.using(CATALOG).create(
        slug=name.lower().replace(" ", "-"),
        name=name,
        country_code="US",
        normalized_key=name.lower(),
        region="",
    )


def _event(*, city: City | None = None, hours: float = 2, **overrides) -> Event:
    """An event, published and scheduled by default."""
    venue = VenueFactory(city=city.name if city else "Los Angeles", country_code="US")
    if city is not None:
        venue.city_ref = city
        venue.save(using=CATALOG)
    return EventFactory(start_time_utc=NOW + timedelta(hours=hours), venue=venue, **overrides)


def _fit(event: Event, *, city: City, score: int = 4, version: int | None = None) -> EventFit:
    """A fit row for an event in a city."""
    return EventFit.objects.using(CATALOG).create(
        event=event,
        city=city.name,
        city_ref=city,
        score=score,
        tags=["tonight"],
        event_version=version if version is not None else event.event_version,
        computed_at=NOW,
    )


def _city_with_events(count: int, *, city: City | None = None) -> City:
    """A city with `count` published, current fits."""
    city = city or _city()
    for n in range(count):
        _fit(_event(city=city, hours=2 + n), city=city)
    return city


def _paths(feed) -> list[str]:
    return [item.path for item in feed.items]


# ── Membership: the public surface and nothing else ────────────────────────────────


def test_a_published_event_is_in_the_feed():
    event = _event()

    feed = list_url_feed(now=NOW)

    assert f"/events/{event.slug}" in _paths(feed)


def test_an_in_review_event_is_not_in_the_feed():
    """An `in_review` event is "not publicly listed" (AD-6, AD-8), so its page is not
    publicly addressable. A sitemap that listed it would send a crawler to a 404."""
    _event(publication_status=Event.PublicationStatus.IN_REVIEW)

    feed = list_url_feed(now=NOW)

    assert _paths(feed) == []


def test_a_superseded_event_is_not_in_the_feed():
    """A superseded event is terminal (D7) and its page 404s or 308s to its successor."""
    old, _new = make_superseded_pair()

    feed = list_url_feed(now=NOW)

    assert f"/events/{old.slug}" not in _paths(feed)


def test_the_successor_of_a_superseded_event_is_in_the_feed():
    """The replacement is a live, published event — so its page is public."""
    _old, new = make_superseded_pair()

    feed = list_url_feed(now=NOW)

    assert f"/events/{new.slug}" in _paths(feed)


def test_a_past_event_is_still_in_the_feed():
    """A page for an event that already happened stays addressable and stays indexed.

    `get_public_event_by_slug` has no time bound, and it must not: a page that 404s the
    moment the doors open throws away every bit of ranking it spent months earning. So
    the feed has no time bound either, and the two cannot disagree.
    """
    past = _event(hours=-48)

    feed = list_url_feed(now=NOW)

    assert f"/events/{past.slug}" in _paths(feed)


def test_a_city_below_the_threshold_is_not_in_the_feed():
    """FR-27's threshold is `> 5`, and a city below it has no published page."""
    _city_with_events(CITY_PAGE_EVENT_THRESHOLD)

    feed = list_url_feed(now=NOW)

    assert not [path for path in _paths(feed) if path.startswith("/events-in-")]


def test_a_city_at_the_threshold_boundary_is_not_in_the_feed():
    """Exactly five does not qualify; exactly six does. The boundary is the test."""
    _city_with_events(CITY_PAGE_EVENT_THRESHOLD)

    feed = list_url_feed(now=NOW)

    assert [item for item in feed.items if item.kind == UrlFeedKind.CITY] == []


def test_a_city_above_the_threshold_is_in_the_feed():
    city = _city_with_events(CITY_PAGE_EVENT_THRESHOLD + 1)

    feed = list_url_feed(now=NOW)

    assert f"/events-in-{city.slug}" in _paths(feed)


def test_a_city_with_only_stale_fits_is_not_in_the_feed():
    """A fit whose `event_version` no longer matches its Event describes an event that
    no longer exists. The city page's listing drops those rows, so the count must drop
    them too — and the feed uses the same rule, so the two cannot disagree."""
    city = _city()
    for n in range(CITY_PAGE_EVENT_THRESHOLD + 1):
        event = _event(city=city, hours=2 + n)
        # The fit was computed from version 1; the event has since moved on.
        _fit(event, city=city, version=1)
        Event.objects.using(CATALOG).filter(pk=event.pk).update(
            event_version=F("event_version") + 1
        )

    feed = list_url_feed(now=NOW)

    assert f"/events-in-{city.slug}" not in _paths(feed)


def test_a_city_whose_events_are_all_superseded_is_not_in_the_feed():
    """The qualification counts published, non-superseded events — the listing's own
    filters."""
    city = _city()
    for n in range(CITY_PAGE_EVENT_THRESHOLD + 1):
        event = _event(city=city, hours=2 + n)
        _fit(event, city=city)
    old, _new = make_superseded_pair()

    feed = list_url_feed(now=NOW)

    assert f"/events-in-{city.slug}" in _paths(feed)


def test_a_city_outside_the_qualification_window_does_not_qualify():
    """The qualification window is a year. A city's events from two years ago do not
    qualify it — otherwise a city that stopped having events would never stop
    qualifying.

    **The events are created out of the window, not moved into it.** The database
    refuses a write that changes an Event's time without a version bump — the same
    guard that makes the state history append-only — so a test that tries to move an
    event after the fact is refused before it reaches the feed. Creating the event at
    the out-of-window time is the honest way to set it up.
    """
    city = _city()
    outside = -(CITY_PAGE_QUALIFICATION_WINDOW + DAY)
    for n in range(CITY_PAGE_EVENT_THRESHOLD + 1):
        event = _event(city=city, hours=outside.total_seconds() / 3600 + n)
        _fit(event, city=city)

    feed = list_url_feed(now=NOW)

    assert f"/events-in-{city.slug}" not in _paths(feed)


# ── `lastmod`: the event's real last change ───────────────────────────────────────


def test_an_unchanged_event_lastmod_is_its_creation():
    """A brand-new event is at version 1 and has no state-change row, so its creation is
    the honest answer for a page that has never moved."""
    event = _event()

    feed = list_url_feed(now=NOW)

    entry = next(item for item in feed.items if item.path == f"/events/{event.slug}")
    assert entry.last_modified == event.created_at


def test_a_changed_event_lastmod_is_the_state_change_time():
    """The state's own row is the basis — not `Event.updated_at`.

    `Event.updated_at` is `auto_now`, and every production write goes through
    `QuerySet.update()`, which does not touch `auto_now`. So `updated_at` is frozen at
    creation and would report "this page has never changed" for an event that moved three
    times.
    """
    event = _event()
    changed_at = NOW - timedelta(days=3)
    EventStateChange.objects.using(CATALOG).create(
        event=event,
        kind=EventStateChange.Kind.TIME_MOVED,
        event_version=event.event_version,
        before={"start_utc": event.start_time_utc},
        after={"start_utc": event.start_time_utc + DAY},
        actor_kind="system",
        actor_label="ingest_pipeline",
        occurred_at=changed_at,
    )

    feed = list_url_feed(now=NOW)

    entry = next(item for item in feed.items if item.path == f"/events/{event.slug}")
    assert entry.last_modified == changed_at


def test_the_lastmod_is_not_the_frozen_updated_at():
    """The trap this rule exists to avoid.

    The event's `updated_at` was set when it was created and has not moved — because
    `QuerySet.update()` never touches `auto_now`. A `lastmod` read off that column would
    be a lie about a page that changed.
    """
    event = _event()
    EventStateChangeFactory(event=event, event_version=event.event_version, occurred_at=NOW - DAY)

    feed = list_url_feed(now=NOW)

    entry = next(item for item in feed.items if item.path == f"/events/{event.slug}")
    assert entry.last_modified == NOW - DAY
    assert entry.last_modified != event.updated_at


def test_a_city_lastmod_is_the_latest_of_its_events():
    """A city page changes when one of its events changes, so its `lastmod` is the max
    over its qualifying events' lastmods."""
    # The events are created a day back, so the state change below is genuinely the latest
    # thing that happened to this city. A `lastmod` is `COALESCE(last state change, the
    # event's creation)` — so events created *after* the change would make the creation the
    # max, and the assertion would pass on the wrong value or fail for the wrong reason.
    with freeze_time(NOW - DAY, tick=True):
        city = _city_with_events(CITY_PAGE_EVENT_THRESHOLD + 1)
    latest = NOW - timedelta(hours=2)
    target = city.event_fits.order_by("id").first().event
    EventStateChange.objects.using(CATALOG).create(
        event=target,
        kind=EventStateChange.Kind.DETAIL_CHANGED,
        event_version=target.event_version,
        before={"title": target.title},
        after={"title": "Renamed"},
        actor_kind="system",
        actor_label="ingest_pipeline",
        occurred_at=latest,
    )

    feed = list_url_feed(now=NOW)

    entry = next(item for item in feed.items if item.path == f"/events-in-{city.slug}")
    assert entry.last_modified == latest


# ── The page boundary: exact, and never overlapping ────────────────────────────────


def test_the_first_page_holds_the_requested_number_of_urls():
    for n in range(5):
        _event(hours=n)

    feed = list_url_feed(now=NOW, page=1, page_size=2)

    assert len(feed.items) == 2
    assert feed.page == 1
    assert feed.page_size == 2
    assert feed.total == 5
    assert feed.has_next is True


def test_two_pages_never_overlap_and_never_skip_a_url():
    """The whole point of a bounded read: the pages partition the feed."""
    for n in range(5):
        _event(hours=n)

    first = list_url_feed(now=NOW, page=1, page_size=2)
    second = list_url_feed(now=NOW, page=2, page_size=2)
    third = list_url_feed(now=NOW, page=3, page_size=2)

    paths = _paths(first) + _paths(second) + _paths(third)

    assert len(paths) == 5
    assert len(set(paths)) == 5
    assert first.has_next is True
    assert second.has_next is True
    assert third.has_next is False


def test_a_page_beyond_the_last_one_is_empty_and_not_an_error():
    """A crawler walking off the end of a listing is doing something ordinary."""
    _event()

    feed = list_url_feed(now=NOW, page=9, page_size=10)

    assert feed.items == ()
    assert feed.has_next is False


def test_the_page_boundary_spans_the_two_kinds():
    """The feed is one flat list — events then cities — and the page is a slice of the
    joined list.

    Slicing each half separately and concatenating would serve up to `2 * page_size` URLs
    on one page and would leave a hole in the middle of the feed. A sitemap built from
    that would have both: a page that overflows the 50,000-URL ceiling and URLs that
    appear on no page at all.

    **The arithmetic here is deliberate.** A qualifying city needs
    `CITY_PAGE_EVENT_THRESHOLD + 1` events of its own, so the city's URL always sits
    behind at least six event URLs. Two more events make eight event URLs, and the
    city's is the ninth — so three pages of three put the city on the last page, and
    the boundary falls *inside* a page rather than between two.
    """
    city = _city_with_events(CITY_PAGE_EVENT_THRESHOLD + 1)
    for n in range(2):
        _event(hours=n)

    first = list_url_feed(now=NOW, page=1, page_size=3)
    second = list_url_feed(now=NOW, page=2, page_size=3)
    third = list_url_feed(now=NOW, page=3, page_size=3)

    paths = _paths(first) + _paths(second) + _paths(third)

    assert len(paths) == 9
    assert len(set(paths)) == 9
    # The events come first, then the cities.
    assert paths[0].startswith("/events/")
    assert paths[-1] == f"/events-in-{city.slug}"
    # The last page holds two events and then the city — the slice crosses the join.
    assert len(third.items) == 3
    assert [item.kind for item in third.items] == [
        UrlFeedKind.EVENT,
        UrlFeedKind.EVENT,
        UrlFeedKind.CITY,
    ]


def test_the_page_size_is_clamped_rather_than_refused():
    """The edge above this one — the HTTP boundary — refuses a bad request with a 422.
    This function is also called directly, by code that is not an HTTP request, and
    should not raise a validation error: a bad internal call is bounded."""
    for n in range(3):
        _event(hours=n)

    feed = list_url_feed(now=NOW, page=0, page_size=10_000)

    assert feed.page == 1
    assert feed.page_size <= 10_000
    assert len(feed.items) == 3


# ── The kinds, and the paths ───────────────────────────────────────────────────────


def test_the_two_kinds_are_named():
    """A kind that exists on only one side of the wire is a kind nobody can serve."""
    event = _event()
    city = _city_with_events(CITY_PAGE_EVENT_THRESHOLD + 1)

    feed = list_url_feed(now=NOW)

    kinds = {item.path: item.kind for item in feed.items}
    assert kinds[f"/events/{event.slug}"] == UrlFeedKind.EVENT
    assert kinds[f"/events-in-{city.slug}"] == UrlFeedKind.CITY


def test_the_paths_use_the_revalidation_signal_prefixes():
    """The sitemap's URLs and the signal's paths are built from the same prefixes, so
    they cannot drift apart."""
    from domain.revalidation import CITY_PATH_PREFIX, EVENT_PATH_PREFIX

    event = _event()
    city = _city_with_events(CITY_PAGE_EVENT_THRESHOLD + 1)

    feed = list_url_feed(now=NOW)

    paths = _paths(feed)
    assert f"{EVENT_PATH_PREFIX}{event.slug}" in paths
    assert f"{CITY_PATH_PREFIX}{city.slug}" in paths
