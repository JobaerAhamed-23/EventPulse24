"""The Browse read (FR-26, FR-48): one ranked pool of the user's city, this week.

The cases here are the ones that would otherwise be found by a user. The window is cut in
the user's zone, so its edges are the first thing to pin. Paging is a slice of one ranked
pool, so the thing to prove is that two passes agree. And the explanation on a Browse card
is the **Relevance Pulse**, not the Event Fit — AD-10 says those two must never be
substituted, so a test asserts the explanation moves when the *user* changes.

Time is frozen at `NOW` throughout: these assertions are about a seven-day window, and a
suite that ran at a different wall clock would be asking a different question.
"""

import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from django.db import connections
from django.db.models import F
from django.test.utils import CaptureQueriesContext
from freezegun import freeze_time

from apps.ingestion.models import City, CityProvisioning, Event
from apps.ingestion.services.catalog_read import list_public_candidates
from apps.personalization.models import DigestPreference
from apps.personalization.services.browse_read import (
    BROWSE_PAGE_SIZE,
    BROWSE_TIER_1_SIZE,
    _inputs_for,
    read_browse_page,
)
from apps.personalization.services.digest_composition import _inputs_for_public
from shared.db import CATALOG, PERSONAL
from shared.ids import uuid7
from tests.ingestion.factories import EventFactory, SourceFactory, VenueFactory
from tests.personalization.factories import DigestPreferenceFactory, SavedEventFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

#: The instant every test here measures from. 2026-11-10 12:00 UTC is 04:00 in Los Angeles.
NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)

CITY = "Brooklyn"
ZONE = "America/Los_Angeles"


@pytest.fixture(autouse=True)
def _frozen_clock():
    """Pin the clock at `NOW`.

    `tick=True` rather than a hard freeze: the event ids are UUIDv7 and the ranking's total
    order falls back to the id, so a stopped clock would mint ties the order cannot break.
    """
    with freeze_time(NOW, tick=True):
        yield


def _user_with_city(*, city: str | None = CITY, zone: str = ZONE):
    """A user whose digest preference names a city — the city Browse reads.

    **`city_source` travels with the city.** `digest_preference_city_source_ck` holds the
    pair together: a city with no source is a claim about where the user is with no record
    of how we learned it. `choice` is the one that matters here — a city the user picked,
    which is the case Browse's "Change city" link maintains.
    """
    user_id = uuid7()
    DigestPreferenceFactory(
        user_id=user_id,
        city=city,
        city_source=DigestPreference.CitySource.CHOICE if city else None,
        timezone=zone,
    )
    return user_id


def _provisioned_city(city: str, *, status: str) -> City:
    """A `City` with a provisioning row in the given status.

    **The rows are written directly, not provisioned.** The provisioning service mints a
    city from the *curated catalog*, and this file's `CITY` is `"Brooklyn"` — which the
    catalog spells `"Brooklyn, NY"`. What this file is about is the read, and the read
    must work for whatever city a reader picked.
    """
    row = City.objects.using(CATALOG).create(
        name=city,
        country_code="US",
        normalized_key=city.lower(),
        slug=f"slug-{city.lower().replace(' ', '-')}",
    )
    CityProvisioning.objects.using(CATALOG).create(city=row, status=status, source_count=1)
    return row


def _event(*, hours_ahead: float, city: str = CITY, **overrides):
    """A published, fresh, upcoming event in `city`.

    **`last_seen_at` is pinned to `NOW`.** FR-14's staleness bound is measured from it, and
    the candidate read drops anything older than the source's TTL times the multiplier. An
    event built with the factory default would be days stale against a frozen `NOW` and
    would never reach the pool — so the test would pass or fail for the wrong reason.
    """
    venue = VenueFactory(city=city, country_code="US")
    return EventFactory(
        venue=venue,
        start_time_utc=NOW + timedelta(hours=hours_ahead),
        last_seen_at=NOW,
        **overrides,
    )


# ── The window: cut in the user's zone, not in UTC ──────────────────────────────────


# `NOW` is 2026-11-10 12:00 UTC, which is 04:00 in Los Angeles. The seventh local day is
# therefore 2026-11-17, and the window's far edge is the midnight after it — 2026-11-18
# 00:00 local, which is 08:00 UTC. The eight-hour gap between that and UTC midnight is
# exactly what a window cut in UTC would get wrong, so both sides of it are pinned.
_ELEVEN_PM_ON_DAY_SEVEN = 7 * 24 + 19  # 2026-11-17 23:00 local == 2026-11-18 07:00 UTC
_ONE_AM_ON_DAY_EIGHT = 7 * 24 + 21  # 2026-11-18 01:00 local == 2026-11-18 09:00 UTC


def test_an_event_late_on_the_seventh_local_day_is_inside_the_window():
    """11pm local on day 7 is this week."""
    user_id = _user_with_city()
    event = _event(hours_ahead=_ELEVEN_PM_ON_DAY_SEVEN)

    page = read_browse_page(user_id=user_id, now=NOW)

    assert event.start_time_utc == datetime(2026, 11, 18, 7, 0, tzinfo=UTC)
    assert event.id in {card.event_id for card in page.cards}


def test_an_event_early_on_the_eighth_local_day_is_outside_it():
    """1am local the next morning is next week — two hours later than the one above, and
    on the other side of the edge. A UTC-cut window would put both on the same side."""
    user_id = _user_with_city()
    event = _event(hours_ahead=_ONE_AM_ON_DAY_EIGHT)

    page = read_browse_page(user_id=user_id, now=NOW)

    assert event.start_time_utc == datetime(2026, 11, 18, 9, 0, tzinfo=UTC)
    assert event.id not in {card.event_id for card in page.cards}


def test_an_event_after_the_window_is_excluded():
    user_id = _user_with_city()
    far = _event(hours_ahead=9 * 24)

    page = read_browse_page(user_id=user_id, now=NOW)

    assert far.id not in {card.event_id for card in page.cards}
    assert page.window_to < far.start_time_utc


def test_an_event_already_started_is_excluded():
    """The lower bound is the candidate read's own, and Browse inherits it."""
    user_id = _user_with_city()
    past = _event(hours_ahead=-2)

    page = read_browse_page(user_id=user_id, now=NOW)

    assert past.id not in {card.event_id for card in page.cards}


def test_an_event_in_another_city_is_excluded():
    user_id = _user_with_city()
    elsewhere = _event(hours_ahead=24, city="Portland")

    page = read_browse_page(user_id=user_id, now=NOW)

    assert elsewhere.id not in {card.event_id for card in page.cards}


# ── Paging: a slice of one ranked pool ──────────────────────────────────────────────


def test_two_passes_over_the_window_show_every_event_exactly_once():
    """The property that makes paging worth having.

    A page is a slice of one ranked pool, so walking the pool twice must produce each event
    once. If the order were only partial — score and start time, with no id to break a tie —
    two events could swap places between pages, and one would be shown twice while the other
    vanished.
    """
    user_id = _user_with_city()
    created = {_event(hours_ahead=h).id for h in range(1, 13)}

    first = read_browse_page(user_id=user_id, now=NOW, limit=5)
    second = read_browse_page(user_id=user_id, now=NOW, offset=5, limit=5)
    third = read_browse_page(user_id=user_id, now=NOW, offset=10, limit=5)

    seen = [card.event_id for page in (first, second, third) for card in page.cards]
    assert len(seen) == len(set(seen)), "an event appeared on two pages"
    assert set(seen) == created, "an event was skipped"
    assert first.total == len(created)
    assert first.has_more is True
    assert third.has_more is False


def test_an_offset_past_the_end_is_an_empty_page_not_an_error():
    user_id = _user_with_city()
    _event(hours_ahead=5)

    page = read_browse_page(user_id=user_id, now=NOW, offset=500)

    assert page.cards == ()
    assert page.total == 1
    assert page.has_more is False


# ── The tiers: named by the server ──────────────────────────────────────────────────


def test_the_first_page_splits_three_cards_into_tier_one():
    user_id = _user_with_city()
    for hour in range(1, 9):
        _event(hours_ahead=hour)

    page = read_browse_page(user_id=user_id, now=NOW)

    assert page.tier_2_starts_at == BROWSE_TIER_1_SIZE


def test_a_later_page_is_all_tier_two():
    """Tier 1 is the top three of the **pool**, so it exists only on the first page."""
    user_id = _user_with_city()
    for hour in range(1, 9):
        _event(hours_ahead=hour)

    page = read_browse_page(user_id=user_id, now=NOW, offset=4, limit=4)

    assert page.tier_2_starts_at == 0


def test_a_pool_smaller_than_a_tier_does_not_claim_cards_it_does_not_have():
    user_id = _user_with_city()
    _event(hours_ahead=3)

    page = read_browse_page(user_id=user_id, now=NOW)

    assert page.tier_2_starts_at == 1
    assert len(page.cards) == 1


# ── The explanation is the Relevance Pulse, not the Event Fit (AD-10) ───────────────


def test_the_ranking_inputs_match_the_digests_for_the_same_candidate():
    """Browse and the Digest must explain the same event the same way.

    Each builds its `RankingInputs` in its own module, from the same public `domain.ranking`
    functions. This pins that the two constructions agree — if they ever diverge, a user
    would see one explanation on the Digest and a different one on Browse for the same
    event, which is the drift AD-10 exists to prevent.
    """
    _user_with_city()
    _event(hours_ahead=10)
    candidates = list_public_candidates(now=NOW, city=CITY)
    assert candidates, "the fixture event should be a candidate"
    candidate = candidates[0]
    chips = ("music", "tech")

    mine = _inputs_for(candidate=candidate, user_chip_keys=chips, user_city=CITY, now=NOW)
    digests = _inputs_for_public(candidate=candidate, user_chip_keys=chips, user_city=CITY, now=NOW)

    assert mine == digests


def test_a_card_carries_tags_and_a_confidence_bucket():
    user_id = _user_with_city()
    _event(hours_ahead=6)

    page = read_browse_page(user_id=user_id, now=NOW)

    card = page.cards[0]
    assert len(card.tags) <= 3
    assert 1 <= card.confidence <= 5


# ── The saved join ──────────────────────────────────────────────────────────────────


def test_an_already_saved_event_reports_itself_saved():
    """So the Save button renders "Saved ✓" on first paint rather than flashing "Save"."""
    user_id = _user_with_city()
    saved = _event(hours_ahead=4)
    other = _event(hours_ahead=5)
    SavedEventFactory(user_id=user_id, event_id=saved.id)

    page = read_browse_page(user_id=user_id, now=NOW)

    by_id = {card.event_id: card for card in page.cards}
    assert by_id[saved.id].is_saved is True
    assert by_id[other.id].is_saved is False


def test_another_users_save_does_not_mark_this_users_card():
    user_id = _user_with_city()
    stranger = uuid7()
    event = _event(hours_ahead=4)
    SavedEventFactory(user_id=stranger, event_id=event.id)

    page = read_browse_page(user_id=user_id, now=NOW)

    assert page.cards[0].is_saved is False


def test_the_saved_state_costs_one_query_however_many_cards_the_page_holds():
    """**The plan promised this measurement, so it is a test and not a claim.**

    A page of 24 cards resolved with one query per card would be 24 round-trips, times every
    user, on a surface people open repeatedly. The join is one `IN` clause over the pool's
    ids — the same shape `get_public_events` uses, for the same stated reason.

    The count is asserted, not inferred: the test fails if the join is rewritten into a
    per-card lookup, and it fails if the query grows with the page size. Twelve cards is
    used rather than 24 so the assertion is about the *shape* of the join and not about a
    number that would move when the page size changes.
    """
    user_id = _user_with_city()
    events = [_event(hours_ahead=hours) for hours in range(1, 13)]
    SavedEventFactory(user_id=user_id, event_id=events[0].id)
    SavedEventFactory(user_id=user_id, event_id=events[5].id)

    with CaptureQueriesContext(connections[PERSONAL]) as captured:
        page = read_browse_page(user_id=user_id, now=NOW)

    assert len(page.cards) == 12
    assert [card.is_saved for card in page.cards].count(True) == 2

    saved_queries = [q for q in captured.captured_queries if "saved" in q["sql"].lower()]
    assert len(saved_queries) == 1, (
        "the saved join must be one IN query, not one per card: "
        f"{[q['sql'] for q in saved_queries]}"
    )


# ── The quota: shown, never spent ───────────────────────────────────────────────────


def test_reading_browse_does_not_spend_the_save_allowance():
    """The failure this guards is a user losing their one free save by opening a page.

    `check_save_allowed` counts an attempt by contract. If Browse reported the quota by
    asking the gate, a page load would be a save.
    """
    user_id = _user_with_city()
    _event(hours_ahead=4)

    first = read_browse_page(user_id=user_id, now=NOW)
    second = read_browse_page(user_id=user_id, now=NOW)
    third = read_browse_page(user_id=user_id, now=NOW)

    assert first.quota.used == 0
    assert second.quota.used == 0
    assert third.quota.used == 0
    assert third.quota.exhausted is False


def test_a_free_user_has_a_cap():
    user_id = _user_with_city()

    page = read_browse_page(user_id=user_id, now=NOW)

    assert page.quota.is_pro is False
    assert page.quota.cap == 1


# ── The stripe cap ──────────────────────────────────────────────────────────────────


def test_at_most_one_card_a_page_carries_the_must_know_stripe():
    """The <10% rule, enforced server-side.

    A client-side cap is per page: two pages would each show "their one", and the surface
    as a whole would flood — which is the category-colour flood the anti-pattern list bans.
    """
    user_id = _user_with_city()
    for hour in (2, 3, 4):
        event = _event(hours_ahead=hour)
        # `guard_event_write()` refuses a lifecycle change that does not bump the version —
        # a cancellation *is* a new version of the event, and the database holds that rather
        # than trusting every writer to remember it.
        Event.objects.using(CATALOG).filter(pk=event.pk).update(
            status=Event.Status.CANCELLED,
            event_version=F("event_version") + 1,
        )

    page = read_browse_page(user_id=user_id, now=NOW)

    stripes = [card.stripe for card in page.cards]
    assert stripes.count("must_know") == 1
    assert stripes.count("public") == 2


def test_only_two_stripe_colours_exist():
    """Amendment A-12 drops the discovery stripe. Three would be the flood."""
    user_id = _user_with_city()
    for hour in range(1, 6):
        _event(hours_ahead=hour)

    page = read_browse_page(user_id=user_id, now=NOW)

    assert {card.stripe for card in page.cards} <= {"public", "must_know"}


# ── The two emptinesses, and the one that is not an error ───────────────────────────


def test_a_city_with_nothing_on_is_an_empty_page_with_a_city():
    user_id = _user_with_city()

    page = read_browse_page(user_id=user_id, now=NOW)

    assert page.cards == ()
    assert page.total == 0
    assert page.city == CITY
    assert page.city_missing is False


def test_a_user_with_no_city_says_so_rather_than_failing():
    """Onboarding can be skipped, so this is a real state and not an error.

    It is deliberately **not** a geo-IP guess: a city the user never chose is worse than no
    city, because the surface's "Change city" link would then be correcting our guess
    instead of setting their preference.
    """
    user_id = _user_with_city(city=None)
    _event(hours_ahead=4)

    page = read_browse_page(user_id=user_id, now=NOW)

    assert page.city_missing is True
    assert page.cards == ()
    assert page.total == 0


def test_a_user_with_no_preference_at_all_is_the_same_quiet_answer():
    user_id = uuid7()

    page = read_browse_page(user_id=user_id, now=NOW)

    assert page.city_missing is True
    assert page.cards == ()


# ── The collection status ────────────────────────────────────────────────────────────────
#
# **A city with no events is not one thing.** The status is the catalog's sentence about
# whether our collection of this city is working, and the surface needs it because
# "collecting" and "quiet" and "gave nothing" are three different facts.
#
# **The status is read from the catalog, never denormalised onto the personal side.** A
# copy on `DigestPreference` would be a second writer of one fact (AD-16), and it would go
# stale the moment the probation moved the city to `live`.


def test_the_status_is_the_catalogs_own_for_a_provisioned_city():
    """The status comes from the provisioning row, verbatim."""
    city = _provisioned_city(CITY, status=CityProvisioning.Status.COLLECTING)
    user_id = _user_with_city()

    page = read_browse_page(user_id=user_id, now=NOW)

    assert page.city_collection_status == "collecting"
    assert city.provisioning.status == "collecting"


def test_the_status_is_read_for_a_live_city():
    """A city that has published says `live` — and the surface's quiet state is a
    *different* answer from the no-sources one."""
    _provisioned_city(CITY, status=CityProvisioning.Status.LIVE)
    user_id = _user_with_city()

    page = read_browse_page(user_id=user_id, now=NOW)

    assert page.city_collection_status == "live"


def test_a_city_that_was_never_provisioned_has_no_status():
    """**Empty is its own state, not a missing one.**

    A city with no provisioning row is a city we never provisioned — the reader picked it
    before automatic collection existed, or provisioning never started for it. It is
    **not** the "no sources" state: that one says we could not find any event sources,
    which is a claim about the provider registry that a city with no provisioning row has
    never made.
    """
    user_id = _user_with_city()

    page = read_browse_page(user_id=user_id, now=NOW)

    assert page.city_collection_status == ""


def test_a_user_with_no_city_has_no_status():
    """There is no collection to report about a city the reader does not have."""
    user_id = _user_with_city(city=None)

    page = read_browse_page(user_id=user_id, now=NOW)

    assert page.city_missing is True
    assert page.city_collection_status == ""


def test_the_status_does_not_change_the_cards():
    """The status is a *fact about the collection*, not a filter.

    **A city that is `collecting` has no cards** — that is what collecting means. But a
    `live` city has them, and the status must not change what the surface shows.
    """
    _provisioned_city(CITY, status=CityProvisioning.Status.LIVE)
    user_id = _user_with_city()
    _event(hours_ahead=4)

    page = read_browse_page(user_id=user_id, now=NOW)

    assert page.city_collection_status == "live"
    assert len(page.cards) == 1


# ── The shared read it borrows ──────────────────────────────────────────────────────


def test_omitting_starts_before_leaves_the_candidate_pool_unchanged():
    """`list_public_candidates` is the **Digest's** pool read, and Browse added a parameter
    to it. The digest never passes one, so the digest's pool must be exactly what it was."""
    near = _event(hours_ahead=4)
    far = _event(hours_ahead=40 * 24)

    unbounded = {c.id for c in list_public_candidates(now=NOW, city=CITY)}

    assert near.id in unbounded
    assert far.id in unbounded, "an unbounded pool must still reach far-future events"


def test_starts_before_is_exclusive_at_the_boundary():
    """So two windows asked back to back neither overlap nor leave a gap."""
    boundary = NOW + timedelta(days=3)
    on_the_boundary = _event(hours_ahead=3 * 24)

    pool = {c.id for c in list_public_candidates(now=NOW, city=CITY, starts_before=boundary)}

    assert on_the_boundary.start_time_utc == boundary
    assert on_the_boundary.id not in pool


# ── Ordering ────────────────────────────────────────────────────────────────────────


def test_a_higher_scoring_event_outranks_a_sooner_one():
    """Browse is ranked, not chronological — that is what makes the section head true.

    The sooner event has the weaker source, so if the order were by start time it would come
    first. It does not.
    """
    user_id = _user_with_city()
    weak = SourceFactory(reliability_score=Decimal("0.10"))
    strong = SourceFactory(reliability_score=Decimal("0.99"))
    sooner = _event(hours_ahead=2, source=weak)
    later = _event(hours_ahead=30, source=strong)

    page = read_browse_page(user_id=user_id, now=NOW)

    order = [card.event_id for card in page.cards]
    assert order.index(later.id) < order.index(sooner.id)


# ── The cost, measured rather than assumed ──────────────────────────────────────────


def test_scoring_a_full_pool_costs_a_query_and_a_bounded_amount_of_python():
    """**Design Risk 3, measured. The number is reported, not assumed.**

    `relevance_score` is per event, in Python — the score is domain logic and `domain/` is
    where it is allowed to live, so it cannot be pushed into SQL. The cost of that choice
    is one Python pass over the pool, and this test measures it: **one query** (the
    candidate pool) plus one saved-state join, and the scoring itself does no I/O.

    The timing bound is deliberately loose. A tight wall-clock assertion is a flaky test
    on a loaded CI box, and a flaky test is worse than no test — so the bound is set far
    above what this actually costs, to catch a *regression of kind* (the score starting to
    hit the database, or the pool growing without bound) rather than to police
    microseconds. The measured value is printed so the report carries the real number.
    """
    user_id = _user_with_city()
    for hours in range(1, 61):
        _event(hours_ahead=hours)

    with CaptureQueriesContext(connections[PERSONAL]) as personal_queries:
        with CaptureQueriesContext(connections[CATALOG]) as catalog_queries:
            started = time.perf_counter()
            page = read_browse_page(user_id=user_id, now=NOW)
            elapsed = time.perf_counter() - started

    assert page.total == 60
    assert len(page.cards) == BROWSE_PAGE_SIZE
    assert page.has_more is True

    # The catalog side is the pool fetch and the city's collection status; the personal side
    # is the saved-state join and the preference, interest and source-visibility reads.
    # Neither grows with the pool size.
    #
    # **The bound was raised from one to two for this item's status read.** The status is
    # a *separate* fact from the pool — the pool says which events are on, the status says
    # whether we are collecting this city at all — and it comes from a different table
    # (`ingestion_cityprovisioning`), so one query cannot serve both without a join that
    # would multiply the pool's rows by the provisioning's.
    #
    # **It is a fixed bound, not a per-card one**, which is the property this assertion is
    # for: a new per-card query would break it, and a new constant read would have to
    # raise it deliberately.
    assert len(catalog_queries) == 2, (
        f"the pool must be one query and the status one, not one per card: "
        f"{[q['sql'][:120] for q in catalog_queries]}"
    )
    # **The bound is the number of *user-preference* reads, not a number of cards.** Every
    # query here is one row-set for the user, whatever the pool size: the digest
    # preference, the entitlement, the interest chips, the saved-event join, the
    # source-visibility read (FR-13's mute and show-less), and the category-mute read
    # (FR-25's "less of that category"). None of them is per candidate, so the page costs
    # the same at 60 candidates as at 6 — which is the property this assertion is actually
    # for.
    #
    # It is a *fixed* bound, so a new per-card query would break it, and a new constant
    # user-preference read would have to raise it deliberately — which is the point: the
    # number is a reviewed decision, not an accident.
    #
    # **The bound was raised from five to six for FR-25's category mute**, and the reason
    # is on the record. The user now has a second kind of "less of this" — a category,
    # alongside a source — and the two live in two tables with no relationship to each
    # other, so one query cannot serve both without a cross join of two unrelated mute
    # tables. The alternative, folding the category mutes into the source-mute read,
    # would make one table's shape the other table's business. Six constant reads is
    # still a constant: the page costs the same at 6 candidates as at 60.
    assert len(personal_queries) <= 6, (
        "the personal side must not grow with the pool: "
        f"{[q['sql'][:120] for q in personal_queries]}"
    )

    # A loose bound: 60 scored candidates must not take a second of pure Python. The real
    # figure is an order of magnitude below this.
    assert elapsed < 1.0, f"scoring 60 candidates took {elapsed:.3f}s"
    print(f"\nBrowse read: 60 candidates scored and paged in {elapsed * 1000:.1f}ms")
