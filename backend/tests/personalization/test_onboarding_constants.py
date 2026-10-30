"""The onboarding constants (FR-1): the chips, the steps, the window and the defaults.

These are the vocabulary the whole onboarding flow is written in, so the tests here are
about the **shape** of that vocabulary: that there are exactly ten chips with the labels
the mockup shows, that the keys are stable slugs, that the flow has exactly three steps,
and that the defaults are documented in one place rather than written at each use.
"""

from datetime import time

from shared.constants import (
    DEFAULT_DIGEST_DELIVERY_TIME,
    DEFAULT_DIGEST_TIMEZONE,
    INTEREST_CHIPS,
    MAX_INTEREST_PICKS,
    ONBOARDING_RESUME_WINDOW,
    ONBOARDING_STEP_COUNT,
    ONBOARDING_STEPS,
)

# --- The chips (FR-1) --------------------------------------------------------------------------


def test_the_chip_list_is_the_ten_from_the_mockup():
    """The ten chips, in the order the step-2 mockup shows them."""
    assert [label for _key, label in INTEREST_CHIPS] == [
        "Tech & meetups",
        "Sports & fitness",
        "Arts & culture",
        "Family & kids",
        "Community & volunteering",
        "Outdoors & nature",
        "Classes & workshops",
        "Markets & fairs",
        "Talks & lectures",
        "Government & civic",
    ]


def test_there_are_exactly_ten_chips():
    assert len(INTEREST_CHIPS) == 10


def test_the_chip_keys_are_unique():
    """Two chips sharing a key would make one of them unselectable."""
    keys = [key for key, _label in INTEREST_CHIPS]
    assert len(set(keys)) == len(keys)


def test_the_chip_keys_are_stable_slugs():
    """A key is a slug: lowercase letters, digits and underscores only.

    The key is the contract — it is what the API accepts, what the database stores and
    what identifies a chip forever. A slug is a stable identifier; a label is prose, and
    prose changes.
    """
    for key, _label in INTEREST_CHIPS:
        assert key == key.lower()
        assert all(char.isalnum() or char == "_" for char in key), key
        assert not key.startswith("_") and not key.endswith("_"), key


def test_a_chip_label_is_not_its_key():
    """The label is prose; the key is a slug. They are different things."""
    for key, label in INTEREST_CHIPS:
        assert key != label
        assert " " not in key


def test_the_maximum_is_three_picks():
    """FR-1: "up to 3 picks"."""
    assert MAX_INTEREST_PICKS == 3


# --- The steps (FR-1) --------------------------------------------------------------------------


def test_there_are_exactly_three_onboarding_steps():
    """FR-1 caps the flow at 3 steps.

    The count **and** the membership are asserted. A bare `== 3` would pass on three
    steps of the wrong identity — and a fourth step would have to change the count, this
    assertion and the database's check constraint before anything stopped it.
    """
    assert ONBOARDING_STEP_COUNT == 3
    assert ONBOARDING_STEPS == ("calendar", "interests", "digest")


def test_the_step_count_is_derived_from_the_steps():
    """The count cannot drift from the tuple, because it is the tuple's length."""
    assert ONBOARDING_STEP_COUNT == len(ONBOARDING_STEPS)


def test_the_step_names_are_unique():
    assert len(set(ONBOARDING_STEPS)) == len(ONBOARDING_STEPS)


# --- The resume window (FR-1) ------------------------------------------------------------------


def test_the_resume_window_is_seven_days():
    """FR-1: "resumed at the same step on return within 7 days"."""
    assert ONBOARDING_RESUME_WINDOW.days == 7
    assert ONBOARDING_RESUME_WINDOW.total_seconds() == 7 * 24 * 60 * 60


# --- The defaults (FR-1) -----------------------------------------------------------------------


def test_the_default_digest_preference_is_the_documented_one():
    """A user who skips step 3 gets 9:00 UTC.

    The default is **documented**, and it is boring on purpose: a default that guessed
    the user's local zone would need the guess, and the guess would be wrong for most of
    the world.
    """
    assert DEFAULT_DIGEST_DELIVERY_TIME == time(9, 0)
    assert DEFAULT_DIGEST_TIMEZONE == "UTC"


def test_the_default_delivery_time_is_a_plain_wall_clock():
    """A wall clock carries no UTC offset — an offset-bearing time is an instant."""
    assert DEFAULT_DIGEST_DELIVERY_TIME.tzinfo is None


def test_the_default_timezone_is_an_iana_zone():
    """The default zone must pass the same validator the user's own zone does."""
    from domain.timezones import canonical_zone

    assert canonical_zone(DEFAULT_DIGEST_TIMEZONE) == DEFAULT_DIGEST_TIMEZONE
