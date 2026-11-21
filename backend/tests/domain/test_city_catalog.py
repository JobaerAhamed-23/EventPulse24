"""The world-city catalog (city-catalog-dataset).

This is a hand-written dataset, so the tests are the quality bar: every invariant below
runs over `WORLD_CITIES` **in full**, never a sample. A sampled check passes happily while
a bad row sits three hundred lines down — a wrong IANA zone, a region qualifier that
fights `split_region`, two rows `lookup` cannot tell apart — and each of those reaches a
reader as a wrong city page or a silently wrong event time.

The pair this module exists to get right is Portland: one key, two regions, two countries'
worth of difference in what a reader is shown. It is pinned by name below.

`domain/` carries a hard 100% coverage gate in CI. No Django import anywhere.
"""

import re
from dataclasses import FrozenInstanceError
from zoneinfo import ZoneInfo

import pytest

from domain.cities import REGION_MAX, split_region
from domain.city_catalog import WORLD_CITIES, CityChoice, choices, is_known, lookup
from domain.timezones import canonical_zone

COUNTRY_CODE = re.compile(r"[A-Z]{2}")
COUNTRY_SLUG = re.compile(r"[a-z]+(-[a-z]+)*")


class TestEveryRowHoldsUp:
    """Whole-dataset invariants. Each one names the row that broke it."""

    def test_every_tz_loads_and_is_canonical(self):
        bad = [
            (row.name, row.tz)
            for row in WORLD_CITIES
            if canonical_zone(row.tz) != row.tz or ZoneInfo(row.tz) is None
        ]

        assert bad == []

    def test_every_name_round_trips_through_split_region(self):
        # The row declares what `split_region` will make of its name. When the two
        # disagree, the stored city keys as something other than the row says it does.
        bad = [
            (row.name, split_region(row.name), (row.identity.key, row.region))
            for row in WORLD_CITIES
            if split_region(row.name) != (row.identity.key, row.region)
        ]

        assert bad == []

    def test_no_two_rows_share_an_identity(self):
        identities = [row.identity for row in WORLD_CITIES]

        assert len(set(identities)) == len(identities)

    def test_no_two_rows_share_a_lookup_key(self):
        # Stricter than identity, and it has to be: `lookup` is given a bare stored string
        # with no country, so two rows agreeing on (key, region) would make it return one
        # of two countries at random.
        keys = [split_region(row.name) for row in WORLD_CITIES]

        assert len(set(keys)) == len(keys)

    def test_every_country_code_is_two_uppercase_letters(self):
        bad = [row.name for row in WORLD_CITIES if not COUNTRY_CODE.fullmatch(row.country_code)]

        assert bad == []

    def test_every_country_slug_is_url_safe(self):
        bad = [
            row.country_slug for row in WORLD_CITIES if not COUNTRY_SLUG.fullmatch(row.country_slug)
        ]

        assert bad == []

    def test_every_row_has_a_name_and_a_country_name(self):
        bad = [row for row in WORLD_CITIES if not row.name.strip() or not row.country_name.strip()]

        assert bad == []

    def test_every_region_is_lowercase_alphabetic_and_short_enough(self):
        # `split_region` only ever emits a lowercase alphabetic run of <= REGION_MAX, so a
        # region outside that shape could never have come back from it.
        bad = [
            (row.name, row.region)
            for row in WORLD_CITIES
            if row.region
            and not (
                row.region.isalpha() and row.region.islower() and len(row.region) <= REGION_MAX
            )
        ]

        assert bad == []

    def test_a_region_has_a_display_name_and_a_display_name_has_a_region(self):
        bad = [
            (row.name, row.region, row.region_name)
            for row in WORLD_CITIES
            if bool(row.region) != bool(row.region_name)
        ]

        assert bad == []

    def test_no_two_rows_share_a_label(self):
        # `label` is what the picker renders. Two rows rendering the same string ask the
        # reader a question with no answer — the same reasoning `collapse_aliases` uses
        # for two spellings of one city. Nothing in `label` itself enforces this, so the
        # dataset has to.
        labels = [row.label for row in WORLD_CITIES]

        assert len(set(labels)) == len(labels)

    def test_one_country_code_means_one_country_name_and_slug(self):
        seen: dict[str, tuple[str, str]] = {}
        bad = []
        for row in WORLD_CITIES:
            country = (row.country_name, row.country_slug)
            if seen.setdefault(row.country_code, country) != country:
                bad.append((row.country_code, country, seen[row.country_code]))

        assert bad == []


class TestTheCatalogIsAMapOfTheWorld:
    """Not a mirror of what has been ingested — that is the point of the whole item."""

    def test_covers_many_countries(self):
        assert len({row.country_code for row in WORLD_CITIES}) >= 50

    def test_covers_every_inhabited_continent(self):
        areas = {row.tz.split("/", 1)[0] for row in WORLD_CITIES}

        assert {"Africa", "America", "Asia", "Australia", "Europe", "Pacific"} <= areas

    @pytest.mark.parametrize("city", ["Dhaka", "Lisbon", "Brooklyn"])
    def test_the_cities_already_ingested_are_pickable(self, city):
        # Non-regression: these are stored on real preferences and registered venues today.
        # "Brooklyn" in particular is carried without a qualifier because that is the
        # string already in the database; "Brooklyn, NY" would be a different city.
        assert is_known(city)

    def test_offers_cities_that_have_never_been_ingested(self):
        assert is_known("Chittagong")
        assert is_known("Reykjavik")


class TestThePortlandPair:
    """`dedup.venue_fingerprint` warns about this pair by name. It stays two cities here."""

    def test_the_two_portlands_are_two_rows_with_two_identities(self):
        oregon, maine = lookup("Portland, OR"), lookup("Portland, ME")

        assert oregon is not None and maine is not None
        assert oregon.identity != maine.identity
        assert oregon.identity.key == maine.identity.key  # the key alone never decides

    def test_the_two_portlands_are_told_apart_by_what_a_reader_sees(self):
        assert lookup("Portland, OR").label == "Portland, Oregon"
        assert lookup("Portland, ME").label == "Portland, Maine"

    def test_the_two_portlands_keep_their_own_zones(self):
        assert lookup("Portland, OR").tz == "America/Los_Angeles"
        assert lookup("Portland, ME").tz == "America/New_York"


class TestLookup:
    @pytest.mark.parametrize(
        "written",
        ["Portland, OR", "portland, or", "  PORTLAND ,  OR  ", "Portland OR"],
    )
    def test_finds_a_city_however_it_is_written(self, written):
        assert lookup(written) is not None
        assert lookup(written).name == "Portland, OR"

    @pytest.mark.parametrize("written", [None, "", "   ", "Fixtureville", "Atlantis"])
    def test_a_city_outside_the_catalog_is_none_not_an_error(self, written):
        assert lookup(written) is None

    def test_a_qualifier_that_was_not_offered_does_not_resolve_to_the_bare_city(self):
        # "Brooklyn" is in the catalog; "Brooklyn, NY" is a different city and is not.
        assert lookup("Brooklyn") is not None
        assert lookup("Brooklyn, NY") is None

    def test_is_known_answers_the_same_question(self):
        assert is_known("Dhaka") is True
        assert is_known("Atlantis") is False


class TestLabel:
    def test_a_qualifier_is_replaced_by_its_display_form_never_shown_raw(self):
        assert lookup("Sydney, NSW").label == "Sydney, New South Wales"

    def test_a_city_with_no_qualifier_is_placed_by_its_country(self):
        assert lookup("Chittagong").label == "Chittagong, Bangladesh"
        assert lookup("Brooklyn").label == "Brooklyn, United States"

    def test_the_label_is_never_the_stored_value(self):
        # The picker shows `label`; `name` is what is written to the preference. A row
        # where they coincided would make it impossible to tell which one got stored.
        assert all(row.label != row.name for row in WORLD_CITIES)

    def test_every_label_names_a_place_a_reader_can_place(self):
        bad = [row.name for row in WORLD_CITIES if ", " not in row.label]

        assert bad == []


class TestChoices:
    def test_offers_every_row_exactly_once(self):
        assert sorted(choices(), key=lambda row: row.name) == sorted(
            WORLD_CITIES, key=lambda row: row.name
        )

    def test_is_alphabetical_by_what_a_reader_reads(self):
        labels = [row.label for row in choices()]

        assert labels == sorted(labels, key=str.casefold)


class TestCityChoiceIsPureData:
    def test_a_row_is_frozen(self):
        # The catalog is a module-level tuple every caller shares. A row that could be
        # written to would let one caller change what another one reads.
        with pytest.raises(FrozenInstanceError):
            lookup("Dhaka").name = "Somewhere else"

    def test_a_row_built_by_hand_behaves_like_one_from_the_catalog(self):
        row = CityChoice(
            name="Portland, OR",
            country_code="US",
            country_name="United States",
            country_slug="united-states",
            region="or",
            region_name="Oregon",
            tz="America/Los_Angeles",
        )

        assert row.identity == lookup("Portland, OR").identity
        assert row.label == "Portland, Oregon"
