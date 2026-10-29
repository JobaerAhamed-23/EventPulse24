"""Schedule conflicts and duplicate detection (AD-21, FR-33, FR-58).

Golden values pin the two rules: exactly 15 minutes is not a conflict, 15 minutes and a
second is; exactly 80% token overlap is a duplicate, one token short of it is not. If either
threshold or the arithmetic changes, these fail loudly rather than silently re-baselining.

No Django import anywhere: this module is importable with Django absent.
"""

from datetime import UTC, datetime, timedelta
from fractions import Fraction
from zoneinfo import ZoneInfo

import pytest

from domain.conflict import conflicts, is_duplicate
from domain.errors import InvalidIntervalError

START = datetime(2026, 11, 1, 18, 0, tzinfo=UTC)


def at(hours: int = 0, minutes: int = 0, seconds: int = 0) -> datetime:
    return START + timedelta(hours=hours, minutes=minutes, seconds=seconds)


# --- Overlap boundaries ------------------------------------------------------------------------


def test_conflicts_overlap_exactly_15min_returns_false():
    # Arrange
    a_start = datetime(2026, 11, 1, 18, 0, tzinfo=UTC)
    a_end = a_start + timedelta(hours=1)
    b_start = a_end - timedelta(minutes=15)
    b_end = b_start + timedelta(hours=1)

    # Act
    result = conflicts(a_start, a_end, b_start, b_end)

    # Assert
    assert result is False


def test_conflicts_overlap_15min_and_1sec_returns_true():
    assert conflicts(at(), at(hours=1), at(minutes=44, seconds=59), at(hours=2)) is True


def test_conflicts_no_overlap_returns_false():
    assert conflicts(at(), at(hours=1), at(hours=2), at(hours=3)) is False


def test_conflicts_one_second_overlap_returns_false():
    # One second is well under the threshold, and the boundary that matters is 15 minutes.
    assert conflicts(at(), at(hours=1), at(minutes=59, seconds=59), at(hours=2)) is False


def test_conflicts_full_containment_returns_true():
    # The short interval sits entirely inside the long one.
    assert conflicts(at(), at(hours=4), at(hours=1), at(hours=2)) is True


def test_conflicts_partial_overlap_returns_true():
    assert conflicts(at(), at(hours=1), at(minutes=30), at(hours=2)) is True


def test_conflicts_back_to_back_returns_false():
    # One ends exactly when the other starts: zero overlap.
    assert conflicts(at(), at(hours=1), at(hours=1), at(hours=2)) is False


def test_conflicts_spanning_midnight_returns_true():
    # 23:00 -> 01:00 against 00:00 -> 02:00: one hour of overlap across the day boundary.
    assert conflicts(at(hours=5), at(hours=7), at(hours=6), at(hours=8)) is True


def test_conflicts_spanning_midnight_without_overlap_returns_false():
    # 23:00 -> 00:30 against 00:15 -> 01:00: 15 minutes exactly.
    assert (
        conflicts(at(hours=5), at(hours=6, minutes=30), at(hours=6, minutes=15), at(hours=7))
        is False
    )


def test_conflicts_is_symmetric():
    a_start, a_end, b_start, b_end = at(), at(hours=2), at(hours=1), at(hours=3)

    assert conflicts(a_start, a_end, b_start, b_end) is conflicts(b_start, b_end, a_start, a_end)


# --- Open-ended intervals ------------------------------------------------------------------------


def test_conflicts_open_ended_event_overlapping_returns_true():
    # The open-ended event starts inside the other and runs forever.
    assert conflicts(at(), at(hours=1), at(minutes=30), None) is True


def test_conflicts_open_ended_event_entirely_before_returns_false():
    # The open-ended event starts after the other one has ended.
    assert conflicts(at(), at(hours=1), at(hours=2), None) is False


def test_conflicts_zero_length_interval_returns_false():
    # An event occupying no time can never overlap by more than 15 minutes.
    assert conflicts(at(), at(), at(), at(hours=4)) is False


def test_conflicts_end_before_start_raises_invalid_interval():
    with pytest.raises(InvalidIntervalError):
        conflicts(at(hours=2), at(), at(), at(hours=1))


def test_conflicts_end_before_start_on_the_second_interval_raises():
    with pytest.raises(InvalidIntervalError):
        conflicts(at(), at(hours=1), at(hours=2), at())


# --- Instants -----------------------------------------------------------------------------------


def test_conflicts_rejects_a_naive_datetime():
    naive = datetime.fromisoformat("2026-11-01T18:00")

    with pytest.raises(TypeError, match="aware datetime"):
        conflicts(naive, at(hours=1), at(), at(hours=1))


def test_conflicts_compares_instants_in_another_zone():
    # The same instant written in another zone is the same instant.
    elsewhere = START.astimezone(ZoneInfo("Asia/Tokyo"))

    assert conflicts(elsewhere, at(hours=1), at(), at(hours=1)) is True


def test_conflicts_ignores_sub_second_precision():
    # Instants are compared to whole seconds, like the rest of the domain.
    assert (
        conflicts(at(), at(hours=1), at(hours=1) - timedelta(microseconds=1), at(hours=2)) is False
    )


def test_is_duplicate_rejects_a_naive_datetime():
    naive = datetime.fromisoformat("2026-11-01T18:00")

    with pytest.raises(TypeError, match="aware datetime"):
        is_duplicate("Jazz Night", naive, "Jazz Night", at())


def test_is_duplicate_compares_instants_in_another_zone():
    elsewhere = START.astimezone(ZoneInfo("Asia/Tokyo"))

    assert is_duplicate("Jazz Night", elsewhere, "Jazz Night", at(hours=1)) is True


# --- Duplicate detection -------------------------------------------------------------------------


def test_is_duplicate_identical_names_differing_in_case_returns_true():
    assert is_duplicate("Jazz Night", at(), "jazz night", at(hours=1)) is True


def test_is_duplicate_names_at_exactly_80_percent_overlap_returns_true():
    # 4 shared content tokens of a 5-token union: exactly 4/5.
    assert (
        is_duplicate("Alpha Beta Gamma Delta", at(), "Alpha Beta Gamma Delta Epsilon", at()) is True
    )


def test_is_duplicate_names_just_below_80_percent_overlap_returns_false():
    # 3 shared content tokens of a 5-token union: 3/5, under the threshold.
    assert is_duplicate("Alpha Beta Gamma Delta", at(), "Alpha Beta Gamma Zeta", at()) is False


def test_is_duplicate_starts_outside_the_24_hour_window_returns_false():
    assert is_duplicate("Jazz Night", at(), "Jazz Night", at(hours=24, seconds=1)) is False


def test_is_duplicate_starts_exactly_24_hours_apart_returns_true():
    assert is_duplicate("Jazz Night", at(), "Jazz Night", at(hours=24)) is True


def test_is_duplicate_24_hours_earlier_is_within_the_window():
    # The window is absolute: a candidate that started earlier is still within it.
    assert is_duplicate("Jazz Night", at(), "Jazz Night", at(hours=-23)) is True


def test_is_duplicate_different_names_returns_false():
    assert is_duplicate("Jazz Night", at(), "Rock Concert", at()) is False


def test_is_duplicate_ignores_accents_and_case_like_the_identity_rule():
    assert is_duplicate("Café Night", at(), "cafe night", at()) is True


def test_is_duplicate_ignores_stop_words():
    # "The" is a stop word, so the content tokens still match exactly.
    assert is_duplicate("The Night Market", at(), "Night Market", at()) is True


def test_is_duplicate_matches_the_identity_rule_threshold_exactly():
    # The duplicate rule and identity rule (b) must not disagree about "the same name":
    # both compare the same 4/5 token overlap.
    from domain.dedup import jaccard, title_fingerprint

    overlap = jaccard(
        title_fingerprint("Alpha Beta Gamma Delta"),
        title_fingerprint("Alpha Beta Gamma Delta Epsilon"),
    )

    assert overlap == Fraction(4, 5)
    assert (
        is_duplicate("Alpha Beta Gamma Delta", at(), "Alpha Beta Gamma Delta Epsilon", at()) is True
    )


def test_is_duplicate_empty_names_are_not_duplicates():
    assert is_duplicate("", at(), "", at()) is False
    assert is_duplicate(None, at(), None, at()) is False
