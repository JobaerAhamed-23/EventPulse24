"""The cascade rules: which public pages a change to an event makes stale.

Pure — no database, no clock, no Django. The `domain-pure` import contract is what makes this
file runnable on its own, and the rules it pins are the ones the whole signal rests on: a
page that is not in the list is a page that stays stale, and a page that is in the list when
it should not be is a page that gets rebuilt for nothing.
"""

import pytest

from domain.revalidation import (
    CITY_PATH_PREFIX,
    EVENT_PATH_PREFIX,
    EventPaths,
    paths_for_event,
)


def test_the_path_conventions_are_the_ones_the_page_items_build_against():
    assert EVENT_PATH_PREFIX == "/events/"
    assert CITY_PATH_PREFIX == "/events-in-"


def test_a_published_event_revalidates_its_own_page():
    assert paths_for_event(slug="summer-fest") == ("/events/summer-fest",)


def test_a_published_event_in_a_city_revalidates_its_page_and_the_city_page():
    assert paths_for_event(slug="summer-fest", city_slug="brooklyn") == (
        "/events/summer-fest",
        "/events-in-brooklyn",
    )


def test_an_event_with_no_city_revalidates_only_its_own_page():
    assert paths_for_event(slug="summer-fest", city_slug="") == ("/events/summer-fest",)


def test_an_unpublished_event_still_revalidates_its_own_page():
    """**The most important rule in this file.**

    An event that has just been unpublished still has a cached page, and that cached page is
    serving content that is no longer public. The path must be rebuilt so the rebuild reads
    the public read, which refuses it, and the 404 replaces the cached 200.

    Dropping the path here would leave the stale page live — which is precisely the failure
    the whole work item exists to prevent.
    """
    assert paths_for_event(slug="summer-fest", is_public=False) == ("/events/summer-fest",)


def test_an_unpublished_event_does_not_revalidate_the_city_page():
    """The city listing shows published events only, so an unpublished one is not in it."""
    assert paths_for_event(slug="summer-fest", city_slug="brooklyn", is_public=False) == (
        "/events/summer-fest",
    )


def test_a_superseded_event_revalidates_its_own_page_and_the_city_page():
    """A superseded event must stop serving, and must leave the city's listing."""
    assert paths_for_event(slug="summer-fest", city_slug="brooklyn", is_superseded=True) == (
        "/events/summer-fest",
        "/events-in-brooklyn",
    )


def test_an_event_that_moved_between_cities_revalidates_both_city_pages():
    """**The old city is the whole reason the state change records a venue id.**

    The new city gains the event; the old city loses it. Revalidating only the new one
    leaves the old city's listing showing an event that is no longer in it.
    """
    assert paths_for_event(
        slug="summer-fest",
        city_slug="queens",
        previous_city_slug="brooklyn",
    ) == (
        "/events/summer-fest",
        "/events-in-brooklyn",
        "/events-in-queens",
    )


def test_an_event_that_moved_within_the_same_city_names_that_city_once():
    """A path repeated in the payload is a path rebuilt twice."""
    assert paths_for_event(
        slug="summer-fest",
        city_slug="brooklyn",
        previous_city_slug="brooklyn",
    ) == (
        "/events/summer-fest",
        "/events-in-brooklyn",
    )


def test_an_event_with_no_city_on_either_side_names_no_city_page():
    assert paths_for_event(slug="summer-fest", previous_city_slug="brooklyn") == (
        "/events/summer-fest",
        "/events-in-brooklyn",
    )


def test_the_city_paths_are_in_a_stable_order():
    """The previous city comes first, so two lists built from two events have one order."""
    facts = EventPaths(slug="s", city_slug="queens", previous_city_slug="brooklyn", is_public=True)

    assert facts.city_paths() == ("/events-in-brooklyn", "/events-in-queens")


def test_the_event_path_is_derived_from_the_slug():
    assert EventPaths(slug="summer-fest").event_path == "/events/summer-fest"


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"slug": "a", "city_slug": "c"}, ("/events/a", "/events-in-c")),
        ({"slug": "a", "city_slug": "c", "is_public": False}, ("/events/a",)),
        ({"slug": "a", "city_slug": "c", "is_superseded": True}, ("/events/a", "/events-in-c")),
        (
            {"slug": "a", "city_slug": "q", "previous_city_slug": "b"},
            ("/events/a", "/events-in-b", "/events-in-q"),
        ),
    ],
)
def test_the_rules_are_a_table(kwargs, expected):
    """The whole rule set, as one table, so a change to any case is visible."""
    assert paths_for_event(**kwargs) == expected
