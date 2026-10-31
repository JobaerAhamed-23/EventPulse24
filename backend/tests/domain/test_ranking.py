"""The Relevance Pulse: the score, the buckets, the hysteresis, the tags (AD-10, FR-22).

Every rule is pinned at its **boundary** — the exact constant, and one unit either side.
A test that only checks the middle of a band does not know where the band ends.

Two cases this file is built around:

* **The exact bucket boundary.** FR-22 says on an exact boundary the **lower** bucket
  wins, so `0.850 → 4` and not 5. That rule is only honourable with `Decimal`, which is
  why the score is a `Decimal` and never a float.
* **A DST transition.** "Tonight" is decided in the **event's own** zone, and a day can
  be 23 or 25 hours long. Both transitions are pinned.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from domain.ranking import (
    RankingInputs,
    apply_hysteresis,
    city_band,
    interest_overlap,
    recency_band,
    relevance_score,
    score_bucket,
    score_slot_1,
    score_slot_2,
    score_slot_3,
    why_this_tags,
)
from shared.constants import (
    MAX_INTEREST_PICKS,
    RANKING_HYSTERESIS_DELTA,
    RANKING_MAX_TAGS,
    RANKING_PERSONAL_EVENT_BOOST,
    RANKING_SCORE_MAX,
    RANKING_TAG_DISCOVERY,
    RANKING_TAG_NEARBY,
    RANKING_TAG_SAVED,
    RANKING_TAG_TOMORROW,
    RANKING_TAG_TONIGHT,
    RANKING_TAG_WEEKEND,
    RANKING_WEIGHT_CITY,
    RANKING_WEIGHT_CONFIDENCE,
    RANKING_WEIGHT_INTEREST,
    RANKING_WEIGHT_RECENCY,
)

NEW_YORK = "America/New_York"
BERLIN = "Europe/Berlin"


def local(*, year, month, day, hour=0, minute=0, second=0, zone=NEW_YORK) -> datetime:
    """A wall-clock time in `zone`, as the instant it is."""
    return datetime(year, month, day, hour, minute, second, tzinfo=ZoneInfo(zone)).astimezone(UTC)


# A Thursday noon in New York. Most cases are measured from here.
THURSDAY_NOON = local(year=2026, month=5, day=14, hour=12)


def ranking_inputs(
    *,
    interest: Decimal = Decimal("0"),
    recency: Decimal = Decimal("0"),
    city: Decimal = Decimal("0"),
    confidence: Decimal = Decimal("0"),
) -> RankingInputs:
    """The four inputs, defaulted to zero so each test states only what it is about."""
    return RankingInputs(
        interest_overlap=interest,
        recency=recency,
        city_match=city,
        confidence=confidence,
    )


# ── The bucket boundaries (FR-22, exact) ─────────────────────────────────────────────


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        # On an exact boundary the LOWER bucket wins.
        (Decimal("0.850"), 4),
        (Decimal("0.650"), 3),
        (Decimal("0.450"), 2),
        (Decimal("0.250"), 1),
        # One hundredth above each boundary takes the higher bucket.
        (Decimal("0.851"), 5),
        (Decimal("0.651"), 4),
        (Decimal("0.451"), 3),
        (Decimal("0.251"), 2),
        # And just below each boundary stays in the lower one.
        (Decimal("0.849"), 4),
        (Decimal("0.649"), 3),
        (Decimal("0.449"), 2),
        (Decimal("0.249"), 1),
        # The extremes.
        (Decimal("0.000"), 1),
        (Decimal("1.000"), 5),
    ],
)
def test_score_bucket_boundaries_are_exact(score, expected):
    assert score_bucket(score) == expected


def test_score_bucket_clamps_above_one():
    assert score_bucket(Decimal("1.50")) == 5


def test_score_bucket_clamps_below_zero():
    assert score_bucket(Decimal("-0.50")) == 1


def test_score_bucket_is_never_a_float():
    """A float boundary lands in the wrong bucket — and not always the same wrong one.

    This is the reason the whole module uses `Decimal`. The binary float closest to 0.85
    is *below* `Decimal("0.85")`, and the float closest to 0.65 and 0.45 is *above* the
    exact values. So a float score breaks the boundary in **both** directions, and a
    reader who checked only one of them would not know it.
    """
    # The exact values land in the lower bucket, per FR-22.
    assert score_bucket(Decimal("0.85")) == 4
    assert score_bucket(Decimal("0.65")) == 3
    assert score_bucket(Decimal("0.45")) == 2

    # 0.85 as a float is *below* the boundary, so it lands in 4 — where the exact value
    # also lands, but for the opposite reason.
    assert Decimal(0.85) < Decimal("0.85")
    assert score_bucket(Decimal(0.85)) == 4

    # 0.65 as a float is *above* the boundary, so it lands in 4 where the exact value
    # lands in 3. This is the case that silently shows one dot too many.
    assert Decimal(0.65) > Decimal("0.65")
    assert score_bucket(Decimal(0.65)) == 4
    assert score_bucket(Decimal("0.65")) == 3


# ── Hysteresis (EXPERIENCE.md §4) ──────────────────────────────────────────────────


def test_hysteresis_first_composition_maps_the_score_directly():
    assert (
        apply_hysteresis(previous_bucket=None, previous_score=None, new_score=Decimal("0.83")) == 4
    )


def test_hysteresis_holds_a_bucket_within_the_delta():
    """The worked example: 0.83 → 4; a re-score to 0.86 (Δ0.03) stays 4."""
    assert (
        apply_hysteresis(
            previous_bucket=4,
            previous_score=Decimal("0.83"),
            new_score=Decimal("0.86"),
        )
        == 4
    )


def test_hysteresis_moves_a_bucket_past_the_delta():
    """The worked example's second half: a re-score to 0.97 (Δ0.14) moves to 5."""
    assert (
        apply_hysteresis(
            previous_bucket=4,
            previous_score=Decimal("0.83"),
            new_score=Decimal("0.97"),
        )
        == 5
    )


def test_hysteresis_threshold_is_exactly_the_delta():
    """Δ ≥ 0.10 moves the bucket; Δ just under it does not."""
    moved = apply_hysteresis(
        previous_bucket=4,
        previous_score=Decimal("0.83"),
        new_score=Decimal("0.83") + RANKING_HYSTERESIS_DELTA,
    )
    assert moved == 5

    held = apply_hysteresis(
        previous_bucket=4,
        previous_score=Decimal("0.83"),
        new_score=Decimal("0.83") + RANKING_HYSTERESIS_DELTA - Decimal("0.01"),
    )
    assert held == 4


def test_hysteresis_applies_to_a_falling_score():
    """The rule is about the score *moving*, not about it rising.

    0.83 → 0.60 is a fall of 0.23, well past the threshold, so the bucket follows the new
    score down to 3.
    """
    assert (
        apply_hysteresis(
            previous_bucket=4,
            previous_score=Decimal("0.83"),
            new_score=Decimal("0.60"),
        )
        == 3
    )


def test_hysteresis_holds_a_falling_score_within_the_delta():
    """A fall smaller than the threshold keeps the bucket, even though it fell."""
    assert (
        apply_hysteresis(
            previous_bucket=4,
            previous_score=Decimal("0.83"),
            new_score=Decimal("0.78"),
        )
        == 4
    )


def test_hysteresis_resets_across_days_by_passing_no_previous_bucket():
    """Across days the caller passes no previous bucket, and the score maps directly."""
    assert (
        apply_hysteresis(previous_bucket=None, previous_score=None, new_score=Decimal("0.30")) == 2
    )


def test_hysteresis_without_a_previous_score_maps_the_new_score():
    assert (
        apply_hysteresis(
            previous_bucket=4,
            previous_score=None,
            new_score=Decimal("0.30"),
        )
        == 2
    )


# ── The interest overlap ───────────────────────────────────────────────────────────


def test_interest_overlap_is_normalised_by_the_maximum_picks():
    # One of three chips matched → 1/3.
    assert interest_overlap(
        event_chip_keys=("arts_culture",),
        user_chip_keys=("arts_culture", "tech_meetups", "sports_fitness"),
    ) == Decimal(1) / Decimal(3)


def test_interest_overlap_of_all_three_is_one():
    assert interest_overlap(
        event_chip_keys=("arts_culture", "tech_meetups", "sports_fitness"),
        user_chip_keys=("arts_culture", "tech_meetups", "sports_fitness"),
    ) == Decimal("1")


def test_interest_overlap_with_no_user_chips_is_zero():
    """The skip-everything onboarding path: not rewarded, not erased."""
    assert interest_overlap(
        event_chip_keys=("arts_culture",),
        user_chip_keys=(),
    ) == Decimal("0")


def test_interest_overlap_with_no_event_chips_is_zero():
    assert interest_overlap(
        event_chip_keys=(),
        user_chip_keys=("arts_culture",),
    ) == Decimal("0")


def test_interest_overlap_with_no_shared_chip_is_zero():
    assert interest_overlap(
        event_chip_keys=("arts_culture",),
        user_chip_keys=("tech_meetups",),
    ) == Decimal("0")


def test_interest_overlap_counts_distinct_event_chips():
    """An event listing the same chip twice cannot claim twice."""
    assert interest_overlap(
        event_chip_keys=("arts_culture", "arts_culture"),
        user_chip_keys=("arts_culture", "tech_meetups", "sports_fitness"),
    ) == Decimal(1) / Decimal(3)


def test_interest_overlap_is_divided_by_the_maximum_picks_constant():
    """The divisor is `MAX_INTEREST_PICKS` (3, per FR-1's "up to 3 picks").

    Pinned against the constant rather than a literal, so a change to the constant is
    visible here — and a change to the *divisor* without a PRD amendment still rescales
    every interest term in every score.
    """
    assert MAX_INTEREST_PICKS == 3
    assert interest_overlap(
        event_chip_keys=("arts_culture",),
        user_chip_keys=("arts_culture",),
    ) == Decimal(1) / Decimal(MAX_INTEREST_PICKS)


def test_a_one_chip_user_does_not_outrank_a_three_chip_user():
    """The reason the divisor is the maximum and not the user's own count.

    A user who picked one chip and matches it would score 1.0 if the divisor were their
    own count — the same as a user who picked three and matched all three. The chip
    count is not a measure of how well anything is known.
    """
    one_chip_user = interest_overlap(
        event_chip_keys=("arts_culture",),
        user_chip_keys=("arts_culture",),
    )
    three_chip_user = interest_overlap(
        event_chip_keys=("arts_culture", "tech_meetups", "sports_fitness"),
        user_chip_keys=("arts_culture", "tech_meetups", "sports_fitness"),
    )
    assert one_chip_user < three_chip_user


# ── The recency band ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("until_start", "expected"),
    [
        (timedelta(seconds=1), RANKING_SCORE_MAX),
        (timedelta(days=1), RANKING_SCORE_MAX),
        (timedelta(days=1, seconds=1), Decimal("0.75")),
        (timedelta(days=3), Decimal("0.75")),
        (timedelta(days=3, seconds=1), Decimal("0.50")),
        (timedelta(days=7), Decimal("0.50")),
        (timedelta(days=7, seconds=1), Decimal("0.25")),
        (timedelta(days=14), Decimal("0.25")),
        (timedelta(days=14, seconds=1), Decimal("0.00")),
    ],
)
def test_recency_band_boundaries(until_start, expected):
    assert recency_band(start_time_utc=THURSDAY_NOON + until_start, now=THURSDAY_NOON) == expected


def test_recency_band_of_a_started_event_is_zero():
    assert recency_band(start_time_utc=THURSDAY_NOON - timedelta(hours=1), now=THURSDAY_NOON) == (
        Decimal("0.00")
    )


# ── The city band ──────────────────────────────────────────────────────────────────


def test_city_band_same_city():
    assert city_band(
        event_city="Brooklyn",
        event_country="US",
        user_city="Brooklyn",
        user_country="US",
    ) == Decimal("1.00")


def test_city_band_is_case_and_whitespace_insensitive():
    assert city_band(
        event_city="  brooklyn ",
        event_country="us",
        user_city="Brooklyn",
        user_country="US",
    ) == Decimal("1.00")


def test_city_band_same_country_different_city():
    assert city_band(
        event_city="Queens",
        event_country="US",
        user_city="Brooklyn",
        user_country="US",
    ) == Decimal("0.50")


def test_city_band_other_country():
    assert city_band(
        event_city="Berlin",
        event_country="DE",
        user_city="Brooklyn",
        user_country="US",
    ) == Decimal("0.00")


def test_city_band_with_an_empty_event_city_is_not_the_same_city():
    assert city_band(
        event_city="",
        event_country="US",
        user_city="Brooklyn",
        user_country="US",
    ) == Decimal("0.50")


def test_city_band_with_an_empty_country_is_other():
    assert city_band(
        event_city="Brooklyn",
        event_country="",
        user_city="Berlin",
        user_country="DE",
    ) == Decimal("0.00")


# ── The score ──────────────────────────────────────────────────────────────────────


def test_relevance_score_of_the_maximum_is_one():
    assert relevance_score(
        ranking_inputs(
            interest=RANKING_SCORE_MAX,
            recency=RANKING_SCORE_MAX,
            city=RANKING_SCORE_MAX,
            confidence=RANKING_SCORE_MAX,
        )
    ) == Decimal("1.00")


def test_relevance_score_of_nothing_is_zero():
    assert relevance_score(ranking_inputs()) == Decimal("0.00")


def test_relevance_score_is_the_weighted_sum():
    """A reader can compute any card's score by hand — FR-22's actual promise."""
    score = relevance_score(
        ranking_inputs(
            interest=Decimal("1.00"),
            recency=Decimal("0.75"),
            city=Decimal("0.50"),
            confidence=Decimal("1.00"),
        )
    )
    expected = (
        RANKING_WEIGHT_INTEREST * Decimal("1.00")
        + RANKING_WEIGHT_RECENCY * Decimal("0.75")
        + RANKING_WEIGHT_CITY * Decimal("0.50")
        + RANKING_WEIGHT_CONFIDENCE * Decimal("1.00")
    ).quantize(Decimal("0.01"))
    assert score == expected


def test_relevance_score_is_clamped():
    """A score above 1.0 is clamped before it is returned."""
    assert relevance_score(
        ranking_inputs(
            interest=Decimal("2.00"),
            recency=Decimal("2.00"),
            city=Decimal("2.00"),
            confidence=Decimal("2.00"),
        )
    ) == Decimal("1.00")


# ── The slots ──────────────────────────────────────────────────────────────────────


def test_slot_2_is_the_standard_score():
    assert score_slot_2(
        inputs=ranking_inputs(interest=Decimal("1.00"), recency=Decimal("1.00"))
    ) == (relevance_score(ranking_inputs(interest=Decimal("1.00"), recency=Decimal("1.00"))))


def test_slot_1_boosts_a_personal_event():
    standard = score_slot_1(inputs=ranking_inputs(interest=Decimal("1.00")))
    personal = score_slot_1(inputs=ranking_inputs(interest=Decimal("1.00")), is_personal_event=True)
    assert personal == standard + RANKING_PERSONAL_EVENT_BOOST


def test_slot_1_boost_is_clamped_at_one():
    personal = score_slot_1(
        inputs=ranking_inputs(
            interest=RANKING_SCORE_MAX,
            recency=RANKING_SCORE_MAX,
            city=RANKING_SCORE_MAX,
            confidence=RANKING_SCORE_MAX,
        ),
        is_personal_event=True,
    )
    assert personal == Decimal("1.00")


def test_slot_3_inverts_the_preference_term():
    """Slot 3 is the card the user's own signals would not have picked."""
    high_interest = ranking_inputs(interest=Decimal("1.00"), recency=Decimal("1.00"))
    low_interest = ranking_inputs(interest=Decimal("0.00"), recency=Decimal("1.00"))

    assert score_slot_3(inputs=high_interest) < score_slot_3(inputs=low_interest)


def test_slot_3_leaves_the_other_terms_alone():
    """The anti-popularity bias is about popularity; recency is not popularity."""
    a = score_slot_3(inputs=ranking_inputs(interest=Decimal("0.50"), recency=Decimal("1.00")))
    b = score_slot_3(inputs=ranking_inputs(interest=Decimal("0.50"), recency=Decimal("0.00")))
    assert a > b


# ── The Why-this Tags ──────────────────────────────────────────────────────────────


def test_tags_include_nearby_for_the_same_city():
    tags = why_this_tags(
        inputs=ranking_inputs(city=Decimal("1.00")),
        event_chip_keys=(),
        user_chip_keys=(),
        start_time_utc=THURSDAY_NOON + timedelta(days=30),
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
    )
    assert RANKING_TAG_NEARBY in tags


def test_tags_omit_nearby_outside_the_city():
    tags = why_this_tags(
        inputs=ranking_inputs(city=Decimal("0.50")),
        event_chip_keys=(),
        user_chip_keys=(),
        start_time_utc=THURSDAY_NOON + timedelta(days=30),
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
    )
    assert RANKING_TAG_NEARBY not in tags


def test_tags_include_tonight_for_an_evening_event_today():
    tonight = local(year=2026, month=5, day=14, hour=20)
    tags = why_this_tags(
        inputs=ranking_inputs(),
        event_chip_keys=(),
        user_chip_keys=(),
        start_time_utc=tonight,
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
    )
    assert RANKING_TAG_TONIGHT in tags


def test_tags_do_not_call_a_morning_event_tonight():
    """An event at 09:00 is later today, not tonight."""
    morning = local(year=2026, month=5, day=14, hour=9)
    tags = why_this_tags(
        inputs=ranking_inputs(),
        event_chip_keys=(),
        user_chip_keys=(),
        start_time_utc=morning,
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
    )
    assert RANKING_TAG_TONIGHT not in tags


def test_tags_include_tomorrow():
    tomorrow = local(year=2026, month=5, day=15, hour=12)
    tags = why_this_tags(
        inputs=ranking_inputs(),
        event_chip_keys=(),
        user_chip_keys=(),
        start_time_utc=tomorrow,
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
    )
    assert RANKING_TAG_TOMORROW in tags


def test_tags_include_the_weekend_for_a_saturday_event():
    # Thursday the 14th → the coming Saturday is the 16th.
    saturday = local(year=2026, month=5, day=16, hour=12)
    tags = why_this_tags(
        inputs=ranking_inputs(),
        event_chip_keys=(),
        user_chip_keys=(),
        start_time_utc=saturday,
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
    )
    assert RANKING_TAG_WEEKEND in tags


def test_tags_omit_the_weekend_for_a_weekday_event():
    friday = local(year=2026, month=5, day=15, hour=12)
    tags = why_this_tags(
        inputs=ranking_inputs(),
        event_chip_keys=(),
        user_chip_keys=(),
        start_time_utc=friday,
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
    )
    assert RANKING_TAG_WEEKEND not in tags


def test_tags_include_saved():
    tags = why_this_tags(
        inputs=ranking_inputs(),
        event_chip_keys=(),
        user_chip_keys=(),
        start_time_utc=THURSDAY_NOON + timedelta(days=30),
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
        is_saved=True,
    )
    assert RANKING_TAG_SAVED in tags


def test_tags_include_a_chip_match():
    tags = why_this_tags(
        inputs=ranking_inputs(),
        event_chip_keys=("arts_culture",),
        user_chip_keys=("arts_culture",),
        start_time_utc=THURSDAY_NOON + timedelta(days=30),
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
    )
    assert "matches_arts_culture" in tags


def test_tags_are_capped_at_three():
    """More than three tags apply; the first three in the fixed order win."""
    tags = why_this_tags(
        inputs=ranking_inputs(city=Decimal("1.00")),
        event_chip_keys=("arts_culture", "tech_meetups", "sports_fitness"),
        user_chip_keys=("arts_culture", "tech_meetups", "sports_fitness"),
        start_time_utc=local(year=2026, month=5, day=14, hour=20),
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
        is_saved=True,
    )
    assert len(tags) == RANKING_MAX_TAGS
    assert tags == (RANKING_TAG_NEARBY, RANKING_TAG_TONIGHT, RANKING_TAG_SAVED)


def test_serendipity_tags_show_discovery_and_never_a_chip():
    """FR-25 and the Glossary: Slot 3's tag is `discovery`, never a category name."""
    tags = why_this_tags(
        inputs=ranking_inputs(city=Decimal("1.00")),
        event_chip_keys=("arts_culture",),
        user_chip_keys=("arts_culture",),
        start_time_utc=THURSDAY_NOON + timedelta(days=30),
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
        serendipity=True,
    )
    assert tags[0] == RANKING_TAG_DISCOVERY
    assert not any(tag.startswith("matches_") for tag in tags)


def test_serendipity_tags_hold_discovery_even_when_the_cap_is_reached():
    tags = why_this_tags(
        inputs=ranking_inputs(city=Decimal("1.00")),
        event_chip_keys=("arts_culture",),
        user_chip_keys=("arts_culture",),
        start_time_utc=local(year=2026, month=5, day=14, hour=20),
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
        is_saved=True,
        serendipity=True,
    )
    assert tags == (RANKING_TAG_DISCOVERY, RANKING_TAG_NEARBY, RANKING_TAG_TONIGHT)


# ── The DST cases ──────────────────────────────────────────────────────────────────


def test_tonight_is_decided_in_the_events_own_zone():
    """An event at 23:30 in Berlin is tonight on **Berlin's** day, not the reader's.

    `now` is Thursday noon in New York, which is Thursday 18:00 in Berlin. The event is
    at 23:30 on the **14th** in Berlin — the same Berlin day as `now`, and therefore
    "tonight" in Berlin.

    The reader's own day is a different day entirely in other cases; the rule is that the
    event's day decides, and this test pins it by putting the event in a zone whose day
    boundary differs from the reader's.
    """
    berlin_evening = local(year=2026, month=5, day=14, hour=23, minute=30, zone=BERLIN)
    tags = why_this_tags(
        inputs=ranking_inputs(),
        event_chip_keys=(),
        user_chip_keys=(),
        start_time_utc=berlin_evening,
        start_time_tz=BERLIN,
        now=THURSDAY_NOON,
    )
    assert RANKING_TAG_TONIGHT in tags
    assert RANKING_TAG_TOMORROW not in tags


def test_an_event_on_the_events_next_day_is_tomorrow_not_tonight():
    """The same Berlin event, one day later: tomorrow in Berlin, however late it is."""
    berlin_evening = local(year=2026, month=5, day=15, hour=23, minute=30, zone=BERLIN)
    tags = why_this_tags(
        inputs=ranking_inputs(),
        event_chip_keys=(),
        user_chip_keys=(),
        start_time_utc=berlin_evening,
        start_time_tz=BERLIN,
        now=THURSDAY_NOON,
    )
    assert RANKING_TAG_TOMORROW in tags
    assert RANKING_TAG_TONIGHT not in tags


def test_tonight_across_a_spring_forward_transition():
    """2026-03-08 in New York: the day is 23 hours long.

    The event at 23:30 on the 7th is tonight on the 7th, and the event at 23:30 on the
    8th is tonight on the 8th — a day boundary that a fixed 24-hour window would miss.
    """
    before = local(year=2026, month=3, day=7, hour=23, minute=30)
    tags_before = why_this_tags(
        inputs=ranking_inputs(),
        event_chip_keys=(),
        user_chip_keys=(),
        start_time_utc=before,
        start_time_tz=NEW_YORK,
        now=local(year=2026, month=3, day=7, hour=12),
    )
    assert RANKING_TAG_TONIGHT in tags_before

    after = local(year=2026, month=3, day=8, hour=23, minute=30)
    tags_after = why_this_tags(
        inputs=ranking_inputs(),
        event_chip_keys=(),
        user_chip_keys=(),
        start_time_utc=after,
        start_time_tz=NEW_YORK,
        now=local(year=2026, month=3, day=8, hour=12),
    )
    assert RANKING_TAG_TONIGHT in tags_after


def test_tonight_across_a_fall_back_transition():
    """2026-10-25 in Berlin: the day is 25 hours long."""
    before = local(year=2026, month=10, day=25, hour=23, minute=30, zone=BERLIN)
    tags_before = why_this_tags(
        inputs=ranking_inputs(),
        event_chip_keys=(),
        user_chip_keys=(),
        start_time_utc=before,
        start_time_tz=BERLIN,
        now=local(year=2026, month=10, day=25, hour=12, zone=BERLIN),
    )
    assert RANKING_TAG_TONIGHT in tags_before

    after = local(year=2026, month=10, day=26, hour=23, minute=30, zone=BERLIN)
    tags_after = why_this_tags(
        inputs=ranking_inputs(),
        event_chip_keys=(),
        user_chip_keys=(),
        start_time_utc=after,
        start_time_tz=BERLIN,
        now=local(year=2026, month=10, day=26, hour=12, zone=BERLIN),
    )
    assert RANKING_TAG_TONIGHT in tags_after


def test_an_unknown_zone_falls_back_to_utc():
    """An unreadable zone still gets a score, as in `domain/event_fit.py`."""
    tags = why_this_tags(
        inputs=ranking_inputs(),
        event_chip_keys=(),
        user_chip_keys=(),
        start_time_utc=THURSDAY_NOON + timedelta(days=30),
        start_time_tz="Not/AZone",
        now=THURSDAY_NOON,
    )
    assert isinstance(tags, tuple)
