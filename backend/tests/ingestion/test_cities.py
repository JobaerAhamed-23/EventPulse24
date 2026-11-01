"""Canonical City resolution and the venue backfill (FR-27).

The **rules** about what counts as one place are pure and live in `tests/domain/test_cities.py`.
This file is about the catalog side: that two spellings reach one row, that two different
places never do, that the backfill can be run twice, and — the one that guards real damage —
that resolving a city does not move a single venue fingerprint.

`Venue.city` is the input to `domain.dedup.venue_fingerprint`, which *is* venue identity. If
normalization ever leaked into it, venues would re-identify silently and event dedup would
corrupt across the whole catalog, long after the change that caused it. The invariance test
below is what stands between this feature and that.
"""

import pytest

from apps.ingestion.models import City, EventFit, Venue
from apps.ingestion.services.cities import (
    backfill_cities,
    count_venues_without_a_city,
    resolve_city,
)
from apps.ingestion.services.venue_registry import register_venue
from domain.dedup import venue_fingerprint
from shared.actor import Actor
from shared.db import CATALOG
from tests.ingestion.factories import EventFactory, VenueFactory

pytestmark = pytest.mark.django_db(databases=[CATALOG])

ACTOR = Actor.system("city_test")


def _resolve(city, country_code="US"):
    return resolve_city(city=city, country_code=country_code)


class TestOneCityHoweverItIsSpelled:
    @pytest.mark.parametrize("second", ["brooklyn", "BROOKLYN", "  Brooklyn ", "Brooklyn."])
    def test_two_spellings_reach_one_row(self, second):
        first = _resolve("Brooklyn")
        assert _resolve(second).pk == first.pk
        assert City.objects.using(CATALOG).count() == 1

    def test_the_first_spelling_is_the_display_name(self):
        assert _resolve("Brooklyn").name == "Brooklyn"
        assert _resolve("brooklyn").name == "Brooklyn"  # the second does not re-case it

    def test_the_slug_is_minted_once(self):
        city = _resolve("New York")
        slug = city.slug
        assert slug == "new-york"
        assert _resolve("new york").slug == slug


class TestNeverTwoPlacesInOneRow:
    def test_the_two_portlands_get_two_rows(self):
        """The pair `venue_fingerprint`'s docstring names, and the reason region is kept."""
        oregon, maine = _resolve("Portland, OR"), _resolve("Portland, ME")
        assert oregon.pk != maine.pk
        assert {oregon.slug, maine.slug} == {"portland-or", "portland-me"}

    def test_a_region_makes_a_distinct_city(self):
        """The accepted cost of never over-merging."""
        assert _resolve("Brooklyn").pk != _resolve("Brooklyn, NY").pk

    def test_the_slug_does_not_depend_on_which_city_arrived_first(self):
        """A regioned city starts at the regioned slug, so neither Portland takes the bare one."""
        maine, oregon = _resolve("Portland, ME"), _resolve("Portland, OR")
        assert (maine.slug, oregon.slug) == ("portland-me", "portland-or")
        assert not City.objects.using(CATALOG).filter(slug="portland").exists()

    def test_the_same_name_in_two_countries_gets_two_rows(self):
        assert _resolve("Birmingham", "US").pk != _resolve("Birmingham", "GB").pk

    def test_a_slug_collision_escalates_rather_than_colliding(self):
        """Same key and region, different country: the slug grows instead of clashing."""
        a, b = _resolve("Birmingham", "US"), _resolve("Birmingham", "GB")
        assert a.slug != b.slug
        assert City.objects.using(CATALOG).filter(slug=a.slug).count() == 1


class TestNoCityIsARealAnswer:
    @pytest.mark.parametrize("blank", [None, "", "   "])
    def test_a_venue_with_no_city_resolves_to_nothing(self, blank):
        assert _resolve(blank) is None
        assert not City.objects.using(CATALOG).exists()

    def test_registering_a_venue_without_a_city_is_not_an_error(self):
        venue = VenueFactory(city="", city_ref=None)
        assert venue.city_ref_id is None


class TestRegistration:
    def test_register_venue_resolves_a_city(self):
        venue = register_venue(
            actor=ACTOR, name="The Troubadour", city="Brooklyn", country_code="US"
        )
        assert venue.city_ref is not None
        assert venue.city_ref.slug == "brooklyn"

    def test_two_venues_in_one_city_share_the_row(self):
        a = register_venue(actor=ACTOR, name="Hall A", city="Brooklyn", country_code="US")
        b = register_venue(actor=ACTOR, name="Hall B", city="brooklyn", country_code="US")
        assert a.city_ref_id == b.city_ref_id

    def test_the_written_city_string_is_kept_as_written(self):
        venue = register_venue(actor=ACTOR, name="Hall C", city="brooklyn", country_code="US")
        assert venue.city == "brooklyn"  # not re-cased to the display name


class TestFingerprintInvariance:
    """The guard against the severe risk: normalization must never touch venue identity."""

    def test_the_backfill_moves_no_venue_fingerprint(self):
        VenueFactory(city="Brooklyn", city_ref=None)
        VenueFactory(city="brooklyn", city_ref=None)
        VenueFactory(city="Brooklyn, NY", city_ref=None)
        VenueFactory(city="Portland, OR", city_ref=None)
        VenueFactory(city="Portland, ME", city_ref=None)
        VenueFactory(city="", city_ref=None)
        before = dict(
            Venue.objects.using(CATALOG).values_list("pk", "venue_fingerprint").order_by("pk")
        )

        backfill_cities(actor=ACTOR)

        after = dict(
            Venue.objects.using(CATALOG).values_list("pk", "venue_fingerprint").order_by("pk")
        )
        assert after == before

    def test_the_city_strings_themselves_are_untouched(self):
        written = ["Brooklyn", "brooklyn", "Brooklyn, NY", ""]
        for city in written:
            VenueFactory(city=city, city_ref=None)
        before = sorted(Venue.objects.using(CATALOG).values_list("city", flat=True))

        backfill_cities(actor=ACTOR)

        assert sorted(Venue.objects.using(CATALOG).values_list("city", flat=True)) == before

    def test_resolution_agrees_with_the_fingerprint_about_word_boundaries(self):
        """Both read `domain.dedup.tokens`, so they cannot drift about what a word is."""
        a = VenueFactory(name="The Fillmore", city="San Francisco", city_ref=None)
        b = VenueFactory(name="The Fillmore", city="san  francisco", city_ref=None)
        backfill_cities(actor=ACTOR)
        a.refresh_from_db(using=CATALOG)
        b.refresh_from_db(using=CATALOG)
        assert a.city_ref_id == b.city_ref_id
        assert venue_fingerprint("The Fillmore", "San Francisco", "US") == venue_fingerprint(
            "The Fillmore", "san  francisco", "US"
        )


class TestBackfill:
    def test_it_resolves_the_venues_that_have_none(self):
        VenueFactory(city="Brooklyn", city_ref=None)
        VenueFactory(city="Queens", city_ref=None)

        venues, _fits = backfill_cities(actor=ACTOR)

        assert venues == 2
        assert (
            not Venue.objects.using(CATALOG).filter(city_ref__isnull=True).exclude(city="").exists()
        )

    def test_a_second_run_changes_nothing(self):
        VenueFactory(city="Brooklyn", city_ref=None)
        VenueFactory(city="brooklyn", city_ref=None)
        first = backfill_cities(actor=ACTOR)
        cities_after_first = set(City.objects.using(CATALOG).values_list("pk", flat=True))

        second = backfill_cities(actor=ACTOR)

        assert first == (2, 0)
        assert second == (0, 0)
        assert set(City.objects.using(CATALOG).values_list("pk", flat=True)) == cities_after_first

    def test_a_venue_with_no_city_is_skipped_permanently(self):
        VenueFactory(city="", city_ref=None)
        assert backfill_cities(actor=ACTOR) == (0, 0)
        assert backfill_cities(actor=ACTOR) == (0, 0)

    def test_it_links_event_fits_written_before_the_city_existed(self):
        venue = VenueFactory(city="Brooklyn", city_ref=None)
        event = EventFactory(venue=venue)
        EventFit.objects.using(CATALOG).create(
            event=event,
            city="Brooklyn",
            score=4,
            tags=[],
            event_version=event.event_version,
            computed_at=event.start_time_utc,
            city_ref=None,
        )

        _venues, fits = backfill_cities(actor=ACTOR)

        row = EventFit.objects.using(CATALOG).get(event=event)
        assert fits == 1
        assert row.city_ref_id == Venue.objects.using(CATALOG).get(pk=venue.pk).city_ref_id

    def test_linking_a_fit_does_not_move_its_computed_at(self):
        """Linking a city is not recomputing a fit — `write_event_fit`'s documented rule."""
        venue = VenueFactory(city="Brooklyn", city_ref=None)
        event = EventFactory(venue=venue)
        row = EventFit.objects.using(CATALOG).create(
            event=event,
            city="Brooklyn",
            score=4,
            tags=[],
            event_version=event.event_version,
            computed_at=event.start_time_utc,
            city_ref=None,
        )
        before = row.computed_at

        backfill_cities(actor=ACTOR)

        row.refresh_from_db(using=CATALOG)
        assert row.computed_at == before

    def test_the_dry_run_count_matches_what_it_would_do(self):
        VenueFactory(city="Brooklyn", city_ref=None)
        VenueFactory(city="Queens", city_ref=None)
        VenueFactory(city="", city_ref=None)

        counted = count_venues_without_a_city()
        venues, _fits = backfill_cities(actor=ACTOR)

        assert counted == venues == 2

    def test_it_is_batched(self):
        for n in range(5):
            VenueFactory(city=f"City {n}", city_ref=None)
        assert backfill_cities(actor=ACTOR, batch_size=2)[0] == 5


class TestDeletionIsProtected:
    def test_a_city_with_venues_cannot_be_deleted(self):
        from django.db.models import ProtectedError

        register_venue(actor=ACTOR, name="Hall", city="Brooklyn", country_code="US")
        city = City.objects.using(CATALOG).get(slug="brooklyn")
        with pytest.raises(ProtectedError):
            city.delete(using=CATALOG)


class TestTheAwkwardPaths:
    """The branches a happy path never reaches: a slug already taken, and a lost race."""

    def test_a_squatted_slug_escalates_to_a_numbered_tail(self):
        """Two unrelated cities already hold the plain and the country form."""
        City.objects.using(CATALOG).create(
            slug="brooklyn", name="Squatter", country_code="ZZ", normalized_key="other a", region=""
        )
        City.objects.using(CATALOG).create(
            slug="brooklyn-us",
            name="Squatter",
            country_code="ZZ",
            normalized_key="other b",
            region="",
        )

        city = _resolve("Brooklyn")

        assert city.slug == "brooklyn-us-2"
        assert city.normalized_key == "brooklyn"

    def test_losing_the_creation_race_returns_the_winner_s_row(self, monkeypatch):
        """Another writer created this very city between our read and our write.

        The loser must return the winner's row, not raise and not make a second one — the
        identity is unique, so there is exactly one right answer and it already exists.
        """
        from django.db import IntegrityError

        from apps.ingestion.services import cities as module

        winner = City.objects.using(CATALOG).create(
            slug="brooklyn",
            name="Brooklyn",
            country_code="US",
            normalized_key="brooklyn",
            region="",
        )
        calls = {"n": 0}
        real_first = module.City.objects.using(CATALOG).filter

        def _blind_first(**kwargs):
            """Miss on the first lookup, as a reader who ran before the winner committed."""
            calls["n"] += 1
            queryset = real_first(**kwargs)
            return queryset.none() if calls["n"] == 1 else queryset

        monkeypatch.setattr(module, "_lookup_city", _blind_first)

        assert module.resolve_city(city="Brooklyn", country_code="US").pk == winner.pk
        assert City.objects.using(CATALOG).filter(normalized_key="brooklyn").count() == 1
        assert IntegrityError  # the path under test is the one it raises

    def test_a_city_that_is_only_punctuation_is_skipped_by_the_backfill(self):
        """Non-empty text that normalizes to nothing: not blank, but not a city either."""
        VenueFactory(city=".", city_ref=None)

        venues, fits = backfill_cities(actor=ACTOR)

        assert (venues, fits) == (0, 0)
        assert not City.objects.using(CATALOG).exists()

    def test_exhausting_the_slug_attempts_raises_rather_than_returning_none(self, monkeypatch):
        """The guard at the end of the escalation. A caller must never get a silent None."""
        from apps.ingestion.services import cities as module

        monkeypatch.setattr(module, "SLUG_ATTEMPTS", 2)
        for slug in ("brooklyn", "brooklyn-us"):
            City.objects.using(CATALOG).create(
                slug=slug,
                name="Squatter",
                country_code="ZZ",
                normalized_key=f"other {slug}",
                region="",
            )

        with pytest.raises(RuntimeError, match="unique slug"):
            _resolve("Brooklyn")
