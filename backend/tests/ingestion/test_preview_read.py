"""The Pulse Preview's published read: the cards and the supported cities (FR-2).

**This module is the seam between the public surface and the catalog.** The endpoint
lives in `apps.catalog`, which may not import `apps.ingestion.models` (import contract
`models-ingestion`). So the cards and the cities come through here — a published read
interface that hands over plain data.

**The Source Badge is derived here**, because the badge is a function of the *source*
and the Event Fit read deliberately does not join the source.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.ingestion.event_fit.writes import write_event_fit
from apps.ingestion.models import Event, EventFit, Source
from apps.ingestion.services.preview_read import (
    SOURCE_BADGE_AGGREGATOR,
    SOURCE_BADGE_COMMUNITY,
    SOURCE_BADGE_CRAWLED,
    SOURCE_BADGE_OFFICIAL,
    list_preview_cards,
    list_supported_cities,
    source_badge_for,
)
from shared.actor import Actor
from shared.db import CATALOG
from tests.ingestion.factories import EventFactory, SourceFactory, VenueFactory

pytestmark = pytest.mark.django_db(databases=[CATALOG])

ACTOR = Actor.system("preview_read_test")
BASE = timezone.now() + timedelta(days=30)
SOLO_CITY = "Zzyzx-read-city"


def make_event(city: str, *, source=None):
    venue = VenueFactory(city=city, venue_fingerprint=f"venue-{city}|{city}")
    overrides = {
        "venue": venue,
        "start_time_utc": BASE,
        "start_time_tz": "America/New_York",
    }
    if source is not None:
        overrides["source"] = source
    event = EventFactory(**overrides)
    write_event_fit(event=event, now=timezone.now(), actor=ACTOR)
    return event


# ── The cards ──────────────────────────────────────────────────────────────────────


def test_the_cards_carry_the_fit_and_the_badge():
    source = SourceFactory(source_type=Source.SourceType.VENUE)
    make_event(SOLO_CITY, source=source)

    cards = list_preview_cards(city=SOLO_CITY, now=timezone.now())

    assert len(cards) == 1
    card = cards[0]
    assert 1 <= card.score <= 5
    assert isinstance(card.tags, tuple)
    assert card.source_name == source.name
    assert card.source_badge == SOURCE_BADGE_OFFICIAL


def test_the_cards_are_the_top_three_by_fit():
    """The preview shows three, and the three are the best fits."""
    for index in range(5):
        venue = VenueFactory(city=SOLO_CITY, venue_fingerprint=f"venue-{index}|{SOLO_CITY}")
        event = EventFactory(
            venue=venue,
            start_time_utc=BASE + index * timedelta(hours=1),
            start_time_tz="America/New_York",
        )
        write_event_fit(event=event, now=timezone.now(), actor=ACTOR)
        EventFit.objects.using(CATALOG).filter(event_id=event.pk).update(score=index + 1)

    cards = list_preview_cards(city=SOLO_CITY, now=timezone.now())

    assert len(cards) == 3
    assert [card.score for card in cards] == [5, 4, 3]


def test_an_unsupported_city_has_no_cards():
    make_event(SOLO_CITY)

    assert list_preview_cards(city="Nowhere-at-all", now=timezone.now()) == []


def test_a_card_whose_source_is_missing_is_dropped_rather_than_raised():
    """The defensive branch, and it is a real one.

    Every Event has a Source (a non-null FK), so this "cannot happen" — and a test is
    exactly the thing that can say so out loud. If it *did* happen, a card with no
    badge would violate FR-23 ("a Pulse Card always shows a Source Badge"), and a
    crash would take the whole preview down over one missing row.

    The card is **dropped**: the other cards still serve, and the preview answers
    with the ones it can vouch for.
    """
    from apps.ingestion.services import preview_read

    make_event(SOLO_CITY)

    # The source lookup comes back empty, as it would if the row had been removed
    # between the fit read and the source read.
    original = preview_read._sources_for
    try:
        preview_read._sources_for = lambda event_ids: {}
        cards = preview_read.list_preview_cards(city=SOLO_CITY, now=timezone.now())
    finally:
        preview_read._sources_for = original

    assert cards == []


def test_the_source_lookup_of_no_events_asks_the_database_nothing():
    """The empty case short-circuits: no ids, no query."""
    from apps.ingestion.services.preview_read import _sources_for

    assert _sources_for([]) == {}


# ── The Source Badge ───────────────────────────────────────────────────────────────


def test_a_venue_source_is_official():
    source = SourceFactory(source_type=Source.SourceType.VENUE)

    assert source_badge_for(source) == SOURCE_BADGE_OFFICIAL


def test_a_promoter_source_is_official():
    source = SourceFactory(source_type=Source.SourceType.PROMOTER)

    assert source_badge_for(source) == SOURCE_BADGE_OFFICIAL


def test_a_community_source_is_a_community_badge():
    source = SourceFactory(source_type=Source.SourceType.COMMUNITY)

    assert source_badge_for(source) == SOURCE_BADGE_COMMUNITY


def test_a_government_source_is_a_community_badge():
    source = SourceFactory(source_type=Source.SourceType.GOVERNMENT)

    assert source_badge_for(source) == SOURCE_BADGE_COMMUNITY


def test_a_ticketing_source_is_an_aggregator():
    source = SourceFactory(source_type=Source.SourceType.TICKETING)

    assert source_badge_for(source) == SOURCE_BADGE_AGGREGATOR


def test_a_media_source_is_an_aggregator():
    source = SourceFactory(source_type=Source.SourceType.MEDIA)

    assert source_badge_for(source) == SOURCE_BADGE_AGGREGATOR


def test_a_crawled_source_is_the_crawled_badge():
    """*How* the facts were obtained is what the ⚠ means: scraped, not published to us.

    The crawl wins over the source's type, because a crawled venue site is still a
    scrape.
    """
    source = SourceFactory(source_type=Source.SourceType.VENUE, acquisition_method="crawl")

    assert source_badge_for(source) == SOURCE_BADGE_CRAWLED


def test_an_unknown_source_type_is_an_aggregator():
    """The least specific claim, and the one that asserts no verification."""
    source = SourceFactory(source_type=Source.SourceType.OTHER)

    assert source_badge_for(source) == SOURCE_BADGE_AGGREGATOR


def test_the_badge_is_never_the_user_imported_one():
    """FR-2 puts personal events out of scope for the preview.

    A user-imported event is a *personal* event, so the preview can never produce this
    badge — and the mapping says so rather than pretending the fifth badge is reachable.
    """
    from apps.ingestion.services.preview_read import source_badge_for as badge

    source = SourceFactory(source_type=Source.SourceType.OTHER, acquisition_method="email_ics")

    assert badge(source) != "user_imported"


# ── The supported cities ───────────────────────────────────────────────────────────


def test_the_supported_cities_are_the_cities_with_a_current_fit():
    make_event(SOLO_CITY)

    supported = list_supported_cities(now=timezone.now())

    assert SOLO_CITY in supported.cities


def test_a_city_with_no_fit_is_not_supported():
    EventFactory(
        venue=VenueFactory(city="No-fit-city", venue_fingerprint="venue-nofit|No-fit-city"),
        start_time_utc=BASE,
        start_time_tz="America/New_York",
    )

    supported = list_supported_cities(now=timezone.now())

    assert "No-fit-city" not in supported.cities


def test_a_stale_fit_does_not_support_its_city():
    from django.db.models import F

    event = make_event("Stale-fit-city")
    Event.objects.using(CATALOG).filter(pk=event.pk).update(event_version=F("event_version") + 1)

    supported = list_supported_cities(now=timezone.now())

    assert "Stale-fit-city" not in supported.cities


def test_a_past_event_does_not_support_its_city():
    """A city whose only event has already started has no upcoming preview."""
    venue = VenueFactory(city="Past-city", venue_fingerprint="venue-past|Past-city")
    event = EventFactory(
        venue=venue,
        start_time_utc=timezone.now() - timedelta(hours=1),
        start_time_tz="America/New_York",
    )
    write_event_fit(event=event, now=timezone.now(), actor=ACTOR)

    supported = list_supported_cities(now=timezone.now())

    assert "Past-city" not in supported.cities


def test_the_cities_are_alphabetical():
    """The order is an alphabet, and it is the *same* alphabet everywhere.

    **The pair `"A-preview"` and `"a-preview"` is not usable as a discriminator**, and
    that is worth saying: the catalog's dedup is case-insensitive, so `"A-preview"`
    and `"a-preview"` are *one* city and only one of them is ever listed. A test
    cannot use a pair the data will not hold.

    So the order is checked **structurally**, in
    `tests/architecture/test_preview_anonymity.py`: the read must not ask the database
    to sort at all, because a text `ORDER BY` is a locale collation and two
    deployments with different locales would list the same cities in a different
    order. Here the check is that the result really is in alphabetical order — which
    is what the picker shows.
    """
    for city in ("Zebra-read", "Alpha-read", "Mango-read"):
        make_event(city)

    supported = list_supported_cities(now=timezone.now())

    listed = [name for name in supported.cities if name.endswith("-read")]
    assert listed == sorted(listed, key=str.casefold)


def test_a_city_is_supported_case_insensitively():
    make_event(SOLO_CITY)

    supported = list_supported_cities(now=timezone.now())

    assert supported.supports(SOLO_CITY.lower())
    assert supported.supports(SOLO_CITY.upper())
    assert supported.supports(f"  {SOLO_CITY}  ")
    assert not supported.supports("Somewhere-else")


def test_the_same_city_spelled_two_ways_is_listed_once():
    """Two spellings of one city would put the city in the picker twice."""
    make_event("Case City")
    make_event("case city")

    supported = list_supported_cities(now=timezone.now())

    listed = [name for name in supported.cities if name.casefold() == "case city"]
    assert len(listed) == 1
