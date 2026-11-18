"""Canonical city keys and slugs (FR-27).

The case this module exists to get right is the one the first draft got wrong: a rule that
drops a trailing "NY" to unify Brooklyn also unifies Portland, Oregon with Portland, Maine.
`dedup.venue_fingerprint` warns about that pair by name. The two Portlands are pinned below,
and so is the cost of keeping them apart — "Brooklyn" and "Brooklyn, NY" are two cities here.

What may be folded is only what is certainly one place: case, whitespace, punctuation,
accents. Each is pinned.

`domain/` carries a hard 100% coverage gate in CI. No Django import anywhere.
"""

import pytest

from domain.cities import (
    CITY_ALIAS_GROUPS,
    KEY_MAX,
    NAME_MAX,
    REGION_MAX,
    SLUG_MAX,
    canonical_spelling,
    city_identity,
    city_spellings,
    collapse_aliases,
    display_name,
    mint_city_slug,
    normalize_city,
    split_region,
)


class TestFoldsWhatIsCertainlyOnePlace:
    @pytest.mark.parametrize(
        "written",
        [
            "Brooklyn",
            "brooklyn",
            "BROOKLYN",
            "  Brooklyn  ",
            "Brooklyn.",
            "(Brooklyn)",
            "Brooklyn ",  # non-breaking space
        ],
    )
    def test_one_city_however_it_is_written(self, written):
        assert normalize_city(written) == "brooklyn"

    def test_accents_fold_on_latin(self):
        assert normalize_city("Montréal") == normalize_city("Montreal")

    def test_internal_punctuation_folds(self):
        assert normalize_city("'s-Hertogenbosch") == normalize_city("s Hertogenbosch")

    def test_multi_word_city_keeps_its_words(self):
        assert normalize_city("New York") == "new york"


class TestNeverMergesTwoPlaces:
    def test_the_two_portlands_stay_apart(self):
        """The pair `dedup.venue_fingerprint`'s docstring names. Same country, different city."""
        assert city_identity("Portland, OR", "US") != city_identity("Portland, ME", "US")
        assert split_region("Portland, OR") == ("portland", "or")
        assert split_region("Portland, ME") == ("portland", "me")

    def test_the_key_alone_is_not_an_identity(self):
        """Why `city_identity` exists: the key cannot tell the two Portlands apart."""
        assert normalize_city("Portland, OR") == normalize_city("Portland, ME") == "portland"

    def test_same_name_in_two_countries_stays_apart(self):
        assert city_identity("Birmingham", "US") != city_identity("Birmingham", "GB")

    def test_a_region_is_kept_not_discarded(self):
        """The accepted cost: a qualifier makes a distinct city rather than vanishing."""
        assert split_region("Brooklyn, NY") == ("brooklyn", "ny")
        assert split_region("Brooklyn") == ("brooklyn", "")
        assert mint_city_slug(*split_region("Brooklyn, NY")) != mint_city_slug(
            *split_region("Brooklyn")
        )

    def test_a_short_whole_name_is_not_eaten(self):
        """ "Ur" is the city, not a region: nothing precedes it."""
        assert split_region("Ur") == ("ur", "")

    def test_a_long_final_word_is_a_word_not_a_region(self):
        assert split_region("Salt Lake City") == ("salt lake city", "")

    def test_a_numeric_final_token_is_not_a_region(self):
        """A postcode fragment is not a region code; it stays in the key."""
        assert split_region("Sector 17") == ("sector 17", "")


class TestEmptyIsARealAnswer:
    @pytest.mark.parametrize("blank", [None, "", "   ", ".", "()"])
    def test_nothing_to_key_on(self, blank):
        assert normalize_city(blank) == ""
        assert split_region(blank) == ("", "")

    def test_a_venue_with_no_city_gets_no_city(self):
        """The rule Event Fit already follows: no row, rather than a guess."""
        assert not city_identity(None, "US")
        assert city_identity("Brooklyn", "US")

    def test_country_is_folded_to_upper(self):
        assert city_identity("Brooklyn", "us") == city_identity("Brooklyn", " US ")


class TestNonLatinScripts:
    def test_a_non_latin_name_survives_normalization(self):
        assert normalize_city("東京") != ""

    def test_cyrillic_folds_case_like_latin(self):
        assert normalize_city("Москва") == normalize_city("МОСКВА")


class TestDisplayName:
    def test_the_spelling_as_written_is_kept(self):
        assert display_name("NYC") == "NYC"
        assert display_name("São Paulo") == "São Paulo"
        assert display_name("'s-Hertogenbosch") == "'s-Hertogenbosch"

    def test_whitespace_is_tidied_but_case_is_not(self):
        assert display_name("  new   YORK  ") == "new YORK"

    def test_absent_name(self):
        assert display_name(None) == ""

    def test_bounded_to_the_column(self):
        assert len(display_name("x" * (NAME_MAX + 50))) == NAME_MAX


class TestSlug:
    def test_the_plain_form(self):
        assert mint_city_slug("brooklyn") == "brooklyn"

    def test_spaces_become_hyphens(self):
        assert mint_city_slug("new york") == "new-york"

    def test_the_region_form(self):
        assert mint_city_slug("brooklyn", "ny") == "brooklyn-ny"

    def test_the_country_form_is_the_last_escalation(self):
        assert mint_city_slug("brooklyn", "ny", "US") == "brooklyn-ny-us"

    def test_country_is_lowercased(self):
        assert mint_city_slug("ur", "", "GB") == "ur-gb"

    def test_bounded_to_the_column_and_never_trailing_a_hyphen(self):
        slug = mint_city_slug("x " * SLUG_MAX, "ny")
        assert len(slug) <= SLUG_MAX
        assert not slug.endswith("-")

    def test_empty_key_yields_empty_slug(self):
        assert mint_city_slug("") == ""


class TestBounds:
    def test_key_is_bounded_to_its_column(self):
        assert len(normalize_city("x" * (KEY_MAX + 50))) <= KEY_MAX

    def test_key_is_bounded_when_a_region_is_split_off(self):
        key, region = split_region("x" * (KEY_MAX + 50) + " ny")
        assert len(key) <= KEY_MAX
        assert len(region) <= REGION_MAX


# ── Alias groups: one place, written more than one way ──────────────────────────────
#
# The table is a factual claim that two names are one city, so these pin both halves of
# it: that a known alias is found from either side, and that a city with no alias is
# completely unaffected — the second is what keeps the table from quietly widening what
# every other city matches.


def test_a_city_with_no_alias_is_only_itself():
    assert city_spellings("Brooklyn") == ("Brooklyn",)


@pytest.mark.parametrize("nothing", ["", "   ", None])
def test_no_city_has_no_spellings(nothing):
    assert city_spellings(nothing) == ()


def test_an_alias_is_found_from_either_side():
    assert city_spellings("Dhaka") == ("Dhaka", "ঢাকা")
    assert city_spellings("ঢাকা") == ("ঢাকা", "Dhaka")


def test_the_callers_own_spelling_comes_first():
    """The caller asked for a city; its own form leads, whatever the table's order is."""
    assert city_spellings("ঢাকা")[0] == "ঢাকা"


def test_casing_and_spacing_still_find_the_group_and_are_not_repeated():
    spellings = city_spellings("  dhaka  ")

    # Trimmed, the caller's own form; "Dhaka" is the same key and so is not added again.
    assert spellings == ("dhaka", "ঢাকা")


def test_every_group_has_at_least_two_forms():
    """A group of one claims nothing, and would only be a row waiting to be wrong."""
    assert all(len(group) >= 2 for group in CITY_ALIAS_GROUPS)


def test_no_written_form_belongs_to_two_groups():
    """Two groups sharing a form would make the lookup depend on table order."""
    keys = [normalize_city(form) for group in CITY_ALIAS_GROUPS for form in group]

    assert len(keys) == len(set(keys))


def test_a_groups_forms_are_distinct_once_normalized():
    """Two forms with the same key are one form; the table should not say otherwise."""
    for group in CITY_ALIAS_GROUPS:
        keys = [normalize_city(form) for form in group]
        assert len(keys) == len(set(keys)), group


def test_every_form_resolves_to_its_whole_group():
    for group in CITY_ALIAS_GROUPS:
        for form in group:
            assert set(city_spellings(form)) == set(group)


# ── Collapsing a group for a picker ─────────────────────────────────────────────────


def test_a_group_is_offered_once_under_its_first_form():
    assert collapse_aliases(["Dhaka", "Montgomery", "ঢাকা"]) == ("Dhaka", "Montgomery")


def test_the_label_does_not_depend_on_which_spelling_the_catalog_holds():
    """A picker entry that renamed itself as venues came and went would move under the
    reader between visits, so the group's first form is the label either way."""
    assert collapse_aliases(["ঢাকা"]) == ("Dhaka",)
    assert canonical_spelling("ঢাকা") == "Dhaka"


def test_a_city_outside_every_group_is_its_own_label():
    assert canonical_spelling("Queens") == "Queens"
    assert canonical_spelling("") == ""


def test_order_is_preserved_and_duplicates_drop_out():
    assert collapse_aliases(["Queens", "queens", "Brooklyn"]) == ("Queens", "Brooklyn")


def test_empty_names_are_not_offered():
    assert collapse_aliases(["", "   ", "Brooklyn"]) == ("Brooklyn",)


def test_collapsing_nothing_offers_nothing():
    assert collapse_aliases([]) == ()
