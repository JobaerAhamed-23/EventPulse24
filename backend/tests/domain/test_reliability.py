"""FR-16's reliability arithmetic: the posterior, the floor, escalation and spike detection.

No Django anywhere in this file — `domain` is pure, and these tests are the proof that it
stays that way as much as they are the proof the numbers are right.

**The two readings this module settled are pinned here**, because they are readings of a
contradictory requirement rather than transcriptions of it: the floor is live under 30
observations (FR-16's two sentences cannot both be literal), and the 3x spike is measured on
the rate of bad events rather than on the score (a ratio of scores provably cannot fire).
"""

from decimal import Decimal

import pytest

from domain.reliability import (
    checked_count,
    is_spike,
    posterior_mean,
    reliability_score,
    should_escalate,
    weekly_negative_rate,
)
from shared.constants import (
    RELIABILITY_ESCALATION_SCORE,
    RELIABILITY_MIN_OBSERVATIONS,
    RELIABILITY_NEW_SOURCE_FLOOR,
)

D = Decimal


# ── The posterior ───────────────────────────────────────────────────────────────────────


def test_posterior_mean_with_no_observations_is_the_prior_mean():
    """A Source with no history is neither trusted nor distrusted."""
    assert posterior_mean(0, 0) == D("0.50")


def test_posterior_mean_one_negative_does_not_crater_the_score():
    """FR-16, verbatim: "a single negative event cannot crater a source."

    A raw rate would be 0.00 here. That is the entire reason for the prior.
    """
    assert posterior_mean(0, 1) == D("0.45")


def test_posterior_mean_all_negative_approaches_zero_slowly():
    """The published shape of the curve, which is also where 0.32 comes from."""
    assert [posterior_mean(0, n) for n in range(7)] == [
        D("0.50"),
        D("0.45"),
        D("0.42"),
        D("0.38"),
        D("0.36"),
        D("0.33"),
        D("0.31"),
    ]


def test_posterior_mean_all_positive_approaches_one():
    assert posterior_mean(30, 0) == D("0.88")
    assert posterior_mean(100, 0) == D("0.95")


def test_posterior_mean_is_unclamped_below_the_minimum():
    """The difference between `posterior_mean` and `reliability_score`, made visible."""
    assert posterior_mean(0, 29) == D("0.13")
    assert reliability_score(0, 29) == RELIABILITY_NEW_SOURCE_FLOOR


# ── The floor (D1: FR-16's two sentences reconciled) ─────────────────────────────────────


def test_reliability_score_of_a_new_source_is_the_prior_mean():
    assert reliability_score(0, 0) == D("0.50")


def test_reliability_score_moves_from_the_first_observation():
    """**The half of D1 that departs from FR-16's literal text.**

    "A source needs at least 30 observations before its score moves" is not implemented
    literally, because a frozen score never approaches the 0.32 floor the same requirement
    demands. The score moves; the floor holds the bottom.
    """
    assert reliability_score(0, 1) == D("0.45")
    assert reliability_score(0, 5) == D("0.33")


def test_reliability_score_is_floored_under_the_minimum():
    """**The other half of D1.** Five or six strikes is as bad as it gets without evidence."""
    assert reliability_score(0, 6) == RELIABILITY_NEW_SOURCE_FLOOR
    assert reliability_score(0, 10) == RELIABILITY_NEW_SOURCE_FLOOR
    assert reliability_score(0, 29) == RELIABILITY_NEW_SOURCE_FLOOR


def test_reliability_score_floor_lifts_at_exactly_thirty():
    """The boundary. At 29 the floor holds; at 30 the true posterior shows through.

    This discontinuity is deliberate and is the price of the reading: the floor is a
    statement about *evidence*, so it ends the moment there is enough of it.
    """
    assert reliability_score(0, 29) == D("0.32")
    assert reliability_score(0, 30) == D("0.13")


def test_reliability_score_never_floors_a_score_that_is_already_above_it():
    """The clamp is a floor, not a replacement: a healthy new Source is untouched."""
    assert reliability_score(5, 0) == D("0.67")
    assert reliability_score(2, 2) == D("0.50")


# ── Escalation ───────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("score", "observations", "expected"),
    [
        (D("0.29"), 30, True),  # both halves true
        (D("0.30"), 30, False),  # at the line, not below it
        (D("0.29"), 29, False),  # low, but not yet measurable
        (D("0.30"), 29, False),  # neither
    ],
)
def test_should_escalate_needs_both_halves(score, observations, expected):
    """All four corners of "below 0.30 **and** at least 30 observations"."""
    assert should_escalate(score, observations) is expected


def test_should_escalate_is_exclusive_at_the_threshold():
    """`< 0.30`, not `<=`. The constant is the line, and the line itself is acceptable."""
    assert should_escalate(RELIABILITY_ESCALATION_SCORE, 100) is False
    assert should_escalate(RELIABILITY_ESCALATION_SCORE - D("0.01"), 100) is True


def test_a_floored_new_source_can_never_escalate():
    """**Why the clamp is safe.** The floor (0.32) sits above the escalation line (0.30), and
    the clamp only applies below 30 observations where escalation is barred anyway. So the
    clamp cannot hide a Source that deserves review — belt and braces, asserted.
    """
    for n in range(RELIABILITY_MIN_OBSERVATIONS):
        score = reliability_score(0, n)
        assert should_escalate(score, n) is False


def test_an_all_negative_source_escalates_the_moment_it_is_measurable():
    assert should_escalate(reliability_score(0, 30), 30) is True


# ── Spike detection (D2) ─────────────────────────────────────────────────────────────────


def test_weekly_negative_rate_of_a_clean_week_is_not_zero():
    """Smoothed, so a ratio against it is finite. A raw rate would be 0.00."""
    assert weekly_negative_rate(0, 40) == D("0.10")


def test_weekly_negative_rate_of_a_bad_week():
    assert weekly_negative_rate(24, 40) == D("0.58")


def test_a_source_going_bad_fast_is_a_spike():
    """The scenario spike detection exists for: 5% bad to 60% bad in a week.

    The cumulative score would still be respectable, so `should_escalate` stays silent —
    which is exactly why this rule is not redundant with it.
    """
    previous = weekly_negative_rate(2, 40)
    current = weekly_negative_rate(24, 40)

    assert is_spike(previous, current) is True


def test_a_two_event_week_is_not_a_spike():
    """**Small-sample suppression, for free.** One bad event out of two is 50% raw — and
    would be an infinite ratio against a clean week — but the prior makes it 1.2x.
    """
    previous = weekly_negative_rate(0, 2)
    current = weekly_negative_rate(1, 2)

    assert is_spike(previous, current) is False


def test_is_spike_at_exactly_three_times_fires():
    """`>=`, so the stated multiplier itself is a spike."""
    assert is_spike(D("0.10"), D("0.30")) is True


def test_is_spike_just_below_three_times_does_not():
    assert is_spike(D("0.10"), D("0.29")) is False


def test_a_steady_source_is_never_a_spike():
    rate = weekly_negative_rate(4, 40)

    assert is_spike(rate, rate) is False


def test_an_improving_source_is_never_a_spike():
    assert is_spike(weekly_negative_rate(20, 40), weekly_negative_rate(1, 40)) is False


def test_a_ratio_of_scores_could_not_have_fired():  # noqa: N802
    """**The finding behind D2, made executable.**

    If `is_spike` were fed *scores* instead of negative rates, it would be dead code. Under
    30 observations the floor pins the score between 0.50 and 0.32 — at most 1.56x — and
    above 30 anything low enough is already escalating. This test fails if someone "fixes"
    the floor or the multiplier in a way that quietly revives the broken reading.
    """
    best = reliability_score(0, 0)
    worst = min(reliability_score(0, n) for n in range(RELIABILITY_MIN_OBSERVATIONS))

    assert best / worst < 3  # a score ratio can never reach the multiplier under the floor


def test_weekly_negative_rate_refuses_more_negatives_than_observations():
    with pytest.raises(ValueError, match="cannot exceed"):
        weekly_negative_rate(5, 2)


# ── Type discipline ──────────────────────────────────────────────────────────────────────


def test_counts_refuse_floats():
    with pytest.raises(TypeError, match="must be an int"):
        posterior_mean(1.0, 0)


def test_counts_refuse_decimals():
    with pytest.raises(TypeError, match="must be an int"):
        posterior_mean(D("1"), 0)


def test_counts_refuse_booleans():
    """`True` is an `int`, so without this `posterior_mean(True, False)` returns 0.55."""
    with pytest.raises(TypeError, match="must be an int"):
        posterior_mean(True, False)


def test_counts_refuse_negatives():
    with pytest.raises(ValueError, match="non-negative"):
        posterior_mean(0, -1)


def test_checked_count_names_the_argument_it_refused():
    with pytest.raises(TypeError, match="negatives must be an int"):
        posterior_mean(0, 1.5)


def test_checked_count_accepts_a_plain_int():
    assert checked_count(7) == 7


def test_rates_refuse_floats():
    """The `checked_confidence` rule: a float 0.3 is not Decimal("0.30")."""
    with pytest.raises(TypeError, match="must be a Decimal"):
        is_spike(0.1, D("0.30"))


def test_rates_refuse_more_than_two_decimals():
    with pytest.raises(ValueError, match="two-decimal"):
        is_spike(D("0.105"), D("0.30"))


def test_rates_refuse_values_outside_the_unit_interval():
    with pytest.raises(ValueError, match="two-decimal"):
        should_escalate(D("1.50"), 30)


def test_should_escalate_refuses_a_bad_observation_count():
    with pytest.raises(TypeError, match="observations must be an int"):
        should_escalate(D("0.20"), 30.0)


# ── Properties (exhaustive; `hypothesis` is not a dependency) ────────────────────────────


def test_the_score_is_always_a_two_decimal_value_in_the_unit_interval():
    for total in range(0, 201):
        for positives in {0, total // 3, total // 2, total}:
            score = reliability_score(positives, total - positives)
            assert D("0") <= score <= D("1")
            assert score == score.quantize(D("0.01"))


def test_the_score_is_monotone_non_increasing_in_negatives():
    """More bad events never makes a Source look better. Checked at every fixed count of
    positives from 0 to 20, across 200 negatives."""
    for positives in range(0, 21):
        scores = [reliability_score(positives, negatives) for negatives in range(0, 201)]
        assert all(b <= a for a, b in zip(scores[:-1], scores[1:], strict=True))


def test_the_score_is_monotone_non_decreasing_in_positives():
    for negatives in range(0, 21):
        scores = [reliability_score(positives, negatives) for positives in range(0, 201)]
        assert all(b >= a for a, b in zip(scores[:-1], scores[1:], strict=True))


def test_the_floor_holds_everywhere_below_the_minimum():
    for total in range(0, RELIABILITY_MIN_OBSERVATIONS):
        for positives in range(0, total + 1):
            assert reliability_score(positives, total - positives) >= RELIABILITY_NEW_SOURCE_FLOOR


def test_the_weekly_rate_is_always_a_two_decimal_value_in_the_unit_interval():
    for observations in range(0, 101):
        for negatives in {0, observations // 2, observations}:
            rate = weekly_negative_rate(negatives, observations)
            assert D("0") <= rate <= D("1")
            assert rate == rate.quantize(D("0.01"))
