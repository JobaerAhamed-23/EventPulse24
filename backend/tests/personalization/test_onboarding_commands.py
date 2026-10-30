"""The onboarding commands (FR-1): interests, the digest preference, and the progress.

These are the rules the flow actually depends on:

- **Interests replace**, and at most 3 are held. Zero is valid — that is how the step is
  skipped.
- **The digest zone is validated by the same validator personal events use**, and the
  canonical name is stored.
- **A user is resumed at the same step within 7 days**, and the flow restarts at step 1
  after that. The window is inclusive at its boundary.
- **Completion is terminal.** A finished onboarding is never reopened — not by a read, not
  by a write, and not by the window expiring.
- **Every step can be skipped**, and no step requires any input.

The clock is **fixed** throughout: no test sleeps, and the boundary is pinned at the exact
instant rather than "roughly 7 days".
"""

from datetime import UTC, datetime, time, timedelta

import pytest

from apps.personalization.models import DigestPreference, Interest, OnboardingProgress
from apps.personalization.services.onboarding import (
    InvalidDeliveryTimeError,
    advance_step,
    get_onboarding_state,
    list_interest_chips,
    set_digest_preference,
    set_interests,
    skip_all,
    skip_step,
)
from domain.errors import (
    InvalidTimezoneError,
    OnboardingAlreadyCompleteError,
    TooManyInterestsError,
    UnknownInterestError,
)
from shared.actor import Actor
from shared.constants import (
    DEFAULT_DIGEST_DELIVERY_TIME,
    DEFAULT_DIGEST_TIMEZONE,
    ONBOARDING_RESUME_WINDOW,
)
from shared.db import PERSONAL
from shared.ids import uuid7

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

USER = uuid7()
OTHER = uuid7()
NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
LATER = NOW + timedelta(minutes=5)


def actor():
    return Actor.user(USER)


# --- The chips ------------------------------------------------------------------------------


def test_the_chip_list_comes_from_the_constant():
    chips = list_interest_chips()

    assert len(chips) == 10
    assert chips[0].key == "tech_meetups"
    assert chips[0].label == "Tech & meetups"


# --- The interests (FR-1) --------------------------------------------------------------------


def test_setting_interests_stores_them():
    set_interests(
        user_id=USER,
        chip_keys=["tech_meetups", "arts_culture"],
        actor=actor(),
        now=NOW,
    )

    assert sorted(Interest.objects.using(PERSONAL).values_list("chip_key", flat=True)) == [
        "arts_culture",
        "tech_meetups",
    ]


def test_setting_interests_replaces_the_set():
    """The list is the whole set, not a delta. Three chips then one → one chip."""
    set_interests(
        user_id=USER,
        chip_keys=["tech_meetups", "arts_culture", "sports_fitness"],
        actor=actor(),
        now=NOW,
    )

    set_interests(user_id=USER, chip_keys=["family_kids"], actor=actor(), now=LATER)

    assert list(Interest.objects.using(PERSONAL).values_list("chip_key", flat=True)) == [
        "family_kids"
    ]


def test_more_than_three_picks_is_refused():
    """FR-1 caps the picks at 3. The extra picks are refused, not silently dropped."""
    with pytest.raises(TooManyInterestsError):
        set_interests(
            user_id=USER,
            chip_keys=[
                "tech_meetups",
                "sports_fitness",
                "arts_culture",
                "family_kids",
            ],
            actor=actor(),
            now=NOW,
        )

    # Nothing was written.
    assert not Interest.objects.using(PERSONAL).exists()


def test_exactly_three_picks_are_allowed():
    """The limit is three, not two."""
    set_interests(
        user_id=USER,
        chip_keys=["tech_meetups", "sports_fitness", "arts_culture"],
        actor=actor(),
        now=NOW,
    )

    assert Interest.objects.using(PERSONAL).count() == 3


def test_an_unknown_chip_key_is_refused():
    """An unknown key is refused before any write, and the offending key is named."""
    with pytest.raises(UnknownInterestError) as caught:
        set_interests(
            user_id=USER,
            chip_keys=["tech_meetups", "underwater_basket_weaving"],
            actor=actor(),
            now=NOW,
        )

    assert caught.value.details["chip_key"] == "underwater_basket_weaving"
    assert not Interest.objects.using(PERSONAL).exists()


def test_a_label_is_not_a_key():
    """The API takes keys, never labels. A label is prose and may be renamed."""
    with pytest.raises(UnknownInterestError):
        set_interests(user_id=USER, chip_keys=["Tech & meetups"], actor=actor(), now=NOW)


def test_zero_picks_is_valid_and_clears_the_set():
    """Zero picks is how the step is skipped, and it clears the set."""
    set_interests(user_id=USER, chip_keys=["tech_meetups"], actor=actor(), now=NOW)

    state = set_interests(user_id=USER, chip_keys=[], actor=actor(), now=LATER)

    assert state.interests == ()
    assert not Interest.objects.using(PERSONAL).exists()


def test_a_duplicate_key_in_one_call_is_deduplicated():
    """A repeated key is deduplicated, not refused — it is not a mistake worth a refusal."""
    state = set_interests(
        user_id=USER,
        chip_keys=["tech_meetups", "tech_meetups"],
        actor=actor(),
        now=NOW,
    )

    assert state.interests == ("tech_meetups",)
    assert Interest.objects.using(PERSONAL).count() == 1


def test_the_interests_are_the_callers_own():
    """Setting one user's interests leaves another user's alone."""
    set_interests(user_id=USER, chip_keys=["tech_meetups"], actor=actor(), now=NOW)
    set_interests(user_id=OTHER, chip_keys=["arts_culture"], actor=Actor.user(OTHER), now=NOW)

    state = set_interests(user_id=USER, chip_keys=["family_kids"], actor=actor(), now=LATER)

    assert state.interests == ("family_kids",)
    assert list(
        Interest.objects.using(PERSONAL).filter(user_id=OTHER).values_list("chip_key", flat=True)
    ) == ["arts_culture"]


# --- The digest preference (FR-1) ------------------------------------------------------------


def test_setting_the_digest_preference_stores_it():
    state = set_digest_preference(
        user_id=USER,
        delivery_time=time(9, 30),
        timezone_name="America/Los_Angeles",
        actor=actor(),
        now=NOW,
    )

    assert state.digest_delivery_time == time(9, 30)
    assert state.digest_timezone == "America/Los_Angeles"


def test_the_digest_preference_is_one_row_per_user():
    """Setting it twice updates it — there is never a second row."""
    set_digest_preference(
        user_id=USER,
        delivery_time=time(9, 30),
        timezone_name="America/Los_Angeles",
        actor=actor(),
        now=NOW,
    )

    set_digest_preference(
        user_id=USER,
        delivery_time=time(7, 0),
        timezone_name="Europe/London",
        actor=actor(),
        now=LATER,
    )

    assert DigestPreference.objects.using(PERSONAL).filter(user_id=USER).count() == 1
    preference = DigestPreference.objects.using(PERSONAL).get(user_id=USER)
    assert preference.delivery_time == time(7, 0)
    assert preference.timezone == "Europe/London"


def test_a_non_iana_timezone_is_refused():
    """The same validator personal events use."""
    with pytest.raises(InvalidTimezoneError):
        set_digest_preference(
            user_id=USER,
            delivery_time=time(9, 0),
            timezone_name="Mars/Olympus_Mons",
            actor=actor(),
            now=NOW,
        )

    assert not DigestPreference.objects.using(PERSONAL).exists()


def test_an_ambiguous_timezone_is_refused():
    """A fixed offset is not a zone an event can happen in — the same rule everywhere."""
    with pytest.raises(InvalidTimezoneError):
        set_digest_preference(
            user_id=USER,
            delivery_time=time(9, 0),
            timezone_name="EST",
            actor=actor(),
            now=NOW,
        )


def test_the_zone_is_stored_canonically():
    """`canonical_zone` normalises, so "Etc/UTC" is stored as "UTC"."""
    state = set_digest_preference(
        user_id=USER,
        delivery_time=time(9, 0),
        timezone_name="Etc/UTC",
        actor=actor(),
        now=NOW,
    )

    assert state.digest_timezone == "UTC"


def test_a_delivery_time_with_an_offset_is_refused():
    """A wall clock carries no offset — an offset-bearing time is an instant."""
    offset_time = time(9, 0, tzinfo=UTC)

    with pytest.raises(InvalidDeliveryTimeError):
        set_digest_preference(
            user_id=USER,
            delivery_time=offset_time,
            timezone_name="UTC",
            actor=actor(),
            now=NOW,
        )


def test_a_delivery_time_that_is_not_a_time_is_refused():
    """The service refuses a non-time even though the API's schema already guarantees one.

    The service is a published interface, and other callers reach it without going
    through the schema.
    """
    with pytest.raises(InvalidDeliveryTimeError):
        set_digest_preference(
            user_id=USER,
            delivery_time="09:00",
            timezone_name="UTC",
            actor=actor(),
            now=NOW,
        )


# --- The progress: advancing and skipping ----------------------------------------------------


def test_a_new_user_is_at_step_one():
    state = get_onboarding_state(user_id=USER, now=NOW)

    assert state.completed is False
    assert state.current_step == 1
    assert state.step_name == "calendar"


def test_a_new_user_has_no_progress_row():
    """The row is created lazily on the first write, so a reader accumulates nothing."""
    get_onboarding_state(user_id=USER, now=NOW)

    assert not OnboardingProgress.objects.using(PERSONAL).exists()


def test_advancing_moves_to_the_next_step():
    advance_step(user_id=USER, actor=actor(), now=NOW)

    state = get_onboarding_state(user_id=USER, now=NOW)

    assert state.current_step == 2
    assert state.step_name == "interests"


def test_advancing_past_the_last_step_completes_the_onboarding():
    """FR-1's cap, enforced at the command layer: there is no step 4."""
    advance_step(user_id=USER, actor=actor(), now=NOW)
    advance_step(user_id=USER, actor=actor(), now=NOW)

    state = advance_step(user_id=USER, actor=actor(), now=NOW)

    assert state.completed is True
    assert state.current_step is None
    assert state.completed_at == NOW


def test_skipping_the_interests_step_clears_the_set():
    """A skipped step 2 writes an empty pick set — zero picks is valid."""
    set_interests(user_id=USER, chip_keys=["tech_meetups"], actor=actor(), now=NOW)
    advance_step(user_id=USER, actor=actor(), now=NOW)

    state = skip_step(user_id=USER, actor=actor(), now=LATER)

    assert state.current_step == 3
    assert state.interests == ()
    assert not Interest.objects.using(PERSONAL).exists()


def test_skipping_the_digest_step_writes_the_default_preference():
    """The default is **written**, not assumed — so `delivery` reads one row."""
    advance_step(user_id=USER, actor=actor(), now=NOW)
    advance_step(user_id=USER, actor=actor(), now=NOW)

    state = skip_step(user_id=USER, actor=actor(), now=LATER)

    assert state.digest_delivery_time == DEFAULT_DIGEST_DELIVERY_TIME
    assert state.digest_timezone == DEFAULT_DIGEST_TIMEZONE
    preference = DigestPreference.objects.using(PERSONAL).get(user_id=USER)
    assert preference.delivery_time == DEFAULT_DIGEST_DELIVERY_TIME
    assert preference.timezone == DEFAULT_DIGEST_TIMEZONE


def test_skipping_the_calendar_step_records_nothing_else():
    """Step 1's connection belongs to `calendar-connect-api`; this flow only records it."""
    state = skip_step(user_id=USER, actor=actor(), now=NOW)

    assert state.current_step == 2
    assert state.interests == ()
    assert state.digest_delivery_time is None


def test_skipping_the_last_step_completes_the_onboarding():
    advance_step(user_id=USER, actor=actor(), now=NOW)
    advance_step(user_id=USER, actor=actor(), now=NOW)

    state = skip_step(user_id=USER, actor=actor(), now=LATER)

    assert state.completed is True
    assert state.completed_at == LATER


def test_every_step_can_be_skipped_with_empty_input():
    """FR-1: "every one can be skipped", and no step requires any input."""
    state = skip_step(user_id=USER, actor=actor(), now=NOW)
    assert state.current_step == 2

    state = skip_step(user_id=USER, actor=actor(), now=LATER)
    assert state.current_step == 3

    state = skip_step(user_id=USER, actor=actor(), now=LATER)
    assert state.completed is True


def test_skip_all_completes_the_onboarding():
    """FR-1: "A user who skips everything still finishes onboarding"."""
    state = skip_all(user_id=USER, actor=actor(), now=NOW)

    assert state.completed is True
    assert state.completed_at == NOW
    assert state.current_step is None


def test_skip_all_writes_the_default_digest_preference():
    """The digest has a delivery time to work with, even for a user who skipped."""
    skip_all(user_id=USER, actor=actor(), now=NOW)

    preference = DigestPreference.objects.using(PERSONAL).get(user_id=USER)
    assert preference.delivery_time == DEFAULT_DIGEST_DELIVERY_TIME
    assert preference.timezone == DEFAULT_DIGEST_TIMEZONE


def test_skip_all_clears_the_interests():
    set_interests(user_id=USER, chip_keys=["tech_meetups"], actor=actor(), now=NOW)

    skip_all(user_id=USER, actor=actor(), now=LATER)

    assert not Interest.objects.using(PERSONAL).exists()


# --- The resume window (FR-1) ----------------------------------------------------------------


def test_a_user_is_resumed_at_the_same_step_within_the_window():
    advance_step(user_id=USER, actor=actor(), now=NOW)
    advance_step(user_id=USER, actor=actor(), now=NOW)

    state = get_onboarding_state(
        user_id=USER, now=NOW + ONBOARDING_RESUME_WINDOW - timedelta(seconds=1)
    )

    assert state.current_step == 3
    assert state.completed is False


def test_a_user_at_the_window_boundary_is_still_resumed():
    """The window is **inclusive**: at exactly the window, the step is kept."""
    advance_step(user_id=USER, actor=actor(), now=NOW)
    advance_step(user_id=USER, actor=actor(), now=NOW)

    state = get_onboarding_state(user_id=USER, now=NOW + ONBOARDING_RESUME_WINDOW)

    assert state.current_step == 3
    assert state.completed is False


def test_onboarding_restarts_at_step_one_after_the_window():
    """One second beyond the window, the flow starts again."""
    advance_step(user_id=USER, actor=actor(), now=NOW)
    advance_step(user_id=USER, actor=actor(), now=NOW)

    state = get_onboarding_state(
        user_id=USER, now=NOW + ONBOARDING_RESUME_WINDOW + timedelta(seconds=1)
    )

    assert state.current_step == 1
    assert state.step_name == "calendar"
    assert state.completed is False


def test_a_read_never_writes():
    """A read that mutates is a write behind a GET — and a GET is never CSRF-checked.

    Django Ninja exempts every view from Django's CSRF middleware, and the resolver
    only checks CSRF on *unsafe* methods. A restart behind a `GET` would therefore be a
    **cross-site write**: a hostile page could restart a user's onboarding flow with a
    plain `<img src>`. So the read reports the restart and leaves the row alone.
    """
    advance_step(user_id=USER, actor=actor(), now=NOW)
    expired = NOW + ONBOARDING_RESUME_WINDOW + timedelta(seconds=1)

    state = get_onboarding_state(user_id=USER, now=expired)

    # The read reports step 1...
    assert state.current_step == 1
    # ...but the stored row is untouched.
    progress = OnboardingProgress.objects.using(PERSONAL).get(user_id=USER)
    assert progress.current_step == 2
    assert progress.last_advanced_at == NOW


def test_two_reads_of_an_expired_flow_agree():
    """The step is derived from the stored facts, so two reads a second apart agree."""
    advance_step(user_id=USER, actor=actor(), now=NOW)
    expired = NOW + ONBOARDING_RESUME_WINDOW + timedelta(seconds=1)

    first = get_onboarding_state(user_id=USER, now=expired)
    second = get_onboarding_state(user_id=USER, now=expired + timedelta(minutes=5))

    assert first.current_step == second.current_step == 1
    assert first.step_name == second.step_name == "calendar"


def test_a_command_restarts_the_expired_flow():
    """The row catches up the moment the user does something with it."""
    advance_step(user_id=USER, actor=actor(), now=NOW)
    expired = NOW + ONBOARDING_RESUME_WINDOW + timedelta(seconds=1)

    # The read leaves the row alone...
    get_onboarding_state(user_id=USER, now=expired)
    progress = OnboardingProgress.objects.using(PERSONAL).get(user_id=USER)
    assert progress.current_step == 2

    # ...and the command restarts it for real.
    state = advance_step(user_id=USER, actor=actor(), now=expired)

    assert state.current_step == 2
    progress = OnboardingProgress.objects.using(PERSONAL).get(user_id=USER)
    assert progress.current_step == 2
    assert progress.last_advanced_at == expired


def test_a_write_against_an_expired_progress_row_restarts_it():
    """A write sees the same expiry the read does.

    The restart is not a read-time-only courtesy: a user who comes back after the window
    and *advances* must start from step 1, not from the step they left weeks ago.
    """
    advance_step(user_id=USER, actor=actor(), now=NOW)
    advance_step(user_id=USER, actor=actor(), now=NOW)

    expired = NOW + ONBOARDING_RESUME_WINDOW + timedelta(seconds=1)
    state = advance_step(user_id=USER, actor=actor(), now=expired)

    # The row restarted at step 1, and the advance moved it to step 2 — not to step 4.
    assert state.current_step == 2
    assert state.completed is False


# --- Completion is terminal ------------------------------------------------------------------


def test_a_completed_user_is_never_sent_back_into_onboarding():
    skip_all(user_id=USER, actor=actor(), now=NOW)

    state = get_onboarding_state(user_id=USER, now=NOW)

    assert state.completed is True
    assert state.current_step is None


def test_a_completed_user_stays_complete_after_the_window_expires():
    """Completion outranks the resume rule — the window never reopens a finished flow."""
    skip_all(user_id=USER, actor=actor(), now=NOW)

    state = get_onboarding_state(
        user_id=USER, now=NOW + ONBOARDING_RESUME_WINDOW + timedelta(days=365)
    )

    assert state.completed is True
    assert state.current_step is None


def test_advancing_a_completed_onboarding_is_refused():
    skip_all(user_id=USER, actor=actor(), now=NOW)

    with pytest.raises(OnboardingAlreadyCompleteError):
        advance_step(user_id=USER, actor=actor(), now=LATER)


def test_skipping_a_completed_onboarding_is_refused():
    skip_all(user_id=USER, actor=actor(), now=NOW)

    with pytest.raises(OnboardingAlreadyCompleteError):
        skip_step(user_id=USER, actor=actor(), now=LATER)


def test_skipping_all_twice_is_refused():
    skip_all(user_id=USER, actor=actor(), now=NOW)

    with pytest.raises(OnboardingAlreadyCompleteError):
        skip_all(user_id=USER, actor=actor(), now=LATER)


def test_a_completed_onboarding_is_not_reopened_by_a_write():
    """The refusal is at the command, so the row is untouched."""
    skip_all(user_id=USER, actor=actor(), now=NOW)

    with pytest.raises(OnboardingAlreadyCompleteError):
        skip_step(user_id=USER, actor=actor(), now=LATER)

    progress = OnboardingProgress.objects.using(PERSONAL).get(user_id=USER)
    assert progress.completed_at == NOW
    assert progress.current_step == 3
