"""Quiet Hours due-time shifting (FR-12, AD-7).

The cases that matter are the ones a range test would get wrong. The default window
(22:00-08:00) crosses midnight, so "inside" is a disjunction, and which *day* the window ends
on depends on which side of midnight the due time sits. Both sides are pinned below, as are
the two boundaries, both DST shapes, and idempotency.

Testing-standards names this a critical path: "Quiet Hours due-time shifting at compute time
(AD-7)". `domain/` carries a hard 100% coverage gate in CI.

No Django import anywhere: this module is importable with Django absent.
"""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from domain.quiet_hours import QuietHours, shift_to_sendable
from shared.constants import DEFAULT_QUIET_HOURS_END, DEFAULT_QUIET_HOURS_START

# The default window, crossing midnight. Used for most cases precisely because it is the one
# every user gets and the one a range test breaks on.
NIGHT = QuietHours(start=DEFAULT_QUIET_HOURS_START, end=DEFAULT_QUIET_HOURS_END)
# An ordinary window that does not cross midnight, to prove one branch serves both shapes.
AFTERNOON = QuietHours(start=time(13, 0), end=time(14, 0))

NY = "America/New_York"
DHAKA = "Asia/Dhaka"


def local(
    year: int, month: int, day: int, hour: int, minute: int = 0, *, zone: str = NY
) -> datetime:
    """A UTC instant written as a local wall-clock time in `zone`."""
    return datetime(year, month, day, hour, minute, tzinfo=ZoneInfo(zone)).astimezone(UTC)


def as_local(instant: datetime, zone: str = NY) -> datetime:
    return instant.astimezone(ZoneInfo(zone))


# --- Outside the window: untouched -------------------------------------------------------------


def test_shift_outside_window_returns_instant_unchanged():
    # Arrange: midday, nowhere near a 22:00-08:00 window.
    due = local(2026, 11, 10, 12, 0)

    # Act
    result = shift_to_sendable(due, window=NIGHT, zone=NY)

    # Assert: the same object, not merely an equal one. An unaffected send is never re-zoned.
    assert result is due


def test_shift_crossing_window_midday_returns_unchanged():
    due = local(2026, 11, 10, 15, 30)

    assert shift_to_sendable(due, window=NIGHT, zone=NY) is due


# --- Crossing midnight: which day does the window end on? --------------------------------------


def test_shift_crossing_window_evening_side_defers_to_next_morning():
    """23:30 Friday is on the evening side: the window runs into Saturday."""
    # Arrange
    due = local(2026, 11, 13, 23, 30)  # Friday

    # Act
    result = shift_to_sendable(due, window=NIGHT, zone=NY)

    # Assert
    assert as_local(result) == datetime(2026, 11, 14, 8, 0, tzinfo=ZoneInfo(NY))


def test_shift_crossing_window_morning_side_defers_to_same_morning():
    """02:00 Saturday is on the morning side of a window that began Friday night."""
    due = local(2026, 11, 14, 2, 0)  # Saturday

    result = shift_to_sendable(due, window=NIGHT, zone=NY)

    assert as_local(result) == datetime(2026, 11, 14, 8, 0, tzinfo=ZoneInfo(NY))


def test_shift_crossing_window_evening_and_morning_land_on_same_instant():
    """The two sides of one window converge: both defer to the same 08:00."""
    evening = shift_to_sendable(local(2026, 11, 13, 23, 30), window=NIGHT, zone=NY)
    morning = shift_to_sendable(local(2026, 11, 14, 2, 0), window=NIGHT, zone=NY)

    assert evening == morning


# --- An ordinary window takes the same branch --------------------------------------------------


def test_shift_ordinary_window_defers_to_same_day_end():
    due = local(2026, 11, 10, 13, 30)

    result = shift_to_sendable(due, window=AFTERNOON, zone=NY)

    assert as_local(result) == datetime(2026, 11, 10, 14, 0, tzinfo=ZoneInfo(NY))


def test_shift_ordinary_window_before_start_returns_unchanged():
    due = local(2026, 11, 10, 12, 59)

    assert shift_to_sendable(due, window=AFTERNOON, zone=NY) is due


# --- Boundaries: start inclusive, end exclusive -------------------------------------------------


def test_shift_at_window_start_is_inside_and_defers():
    """Exactly 22:00 is inside the window."""
    due = local(2026, 11, 13, 22, 0)

    result = shift_to_sendable(due, window=NIGHT, zone=NY)

    assert as_local(result) == datetime(2026, 11, 14, 8, 0, tzinfo=ZoneInfo(NY))


def test_shift_at_window_end_is_outside_and_returns_unchanged():
    """Exactly 08:00 is outside. This is what makes the shift idempotent."""
    due = local(2026, 11, 14, 8, 0)

    assert shift_to_sendable(due, window=NIGHT, zone=NY) is due


def test_shift_at_ordinary_window_end_returns_unchanged():
    due = local(2026, 11, 10, 14, 0)

    assert shift_to_sendable(due, window=AFTERNOON, zone=NY) is due


# --- Disabled and absent windows ----------------------------------------------------------------


def test_shift_disabled_window_returns_unchanged():
    """start == end is disabled, never "defer forever" — see InvalidQuietHoursWindowError."""
    midnight_to_midnight = QuietHours(start=time(0, 0), end=time(0, 0))
    due = local(2026, 11, 10, 3, 0)

    assert shift_to_sendable(due, window=midnight_to_midnight, zone=NY) is due


def test_shift_none_window_returns_unchanged():
    due = local(2026, 11, 10, 3, 0)

    assert shift_to_sendable(due, window=None, zone=NY) is due


def test_covers_disabled_window_is_false_at_its_own_start():
    assert QuietHours(start=time(9, 0), end=time(9, 0)).covers(time(9, 0)) is False


# --- DST: the window's end is a wall clock, and some days it misbehaves -------------------------


def test_shift_window_end_in_dst_gap_resolves_to_real_instant():
    """US spring-forward 2026-03-08: 02:00-03:00 does not exist.

    A window ending at 02:30 has no 02:30 to end at. `read_wall_clock` resolves at fold=0
    rather than raising, so the send gets a real instant and is never lost.
    """
    # Arrange: window 22:00-02:30, due 23:00 on the night the clocks go forward.
    gap_window = QuietHours(start=time(22, 0), end=time(2, 30))
    due = local(2026, 3, 7, 23, 0)

    # Act
    result = shift_to_sendable(due, window=gap_window, zone=NY)

    # Assert: a real instant, after the due time, on the far side of the gap.
    assert result > due
    assert result.tzinfo is not None
    # 02:30 EST does not exist; the fold=0 reading lands at 03:30 EDT.
    assert as_local(result) == datetime(2026, 3, 8, 3, 30, tzinfo=ZoneInfo(NY))


def test_shift_window_end_in_dst_fold_resolves_deterministically():
    """US fall-back 2026-11-01: 01:00-02:00 happens twice. The first occurrence wins."""
    # Arrange
    fold_window = QuietHours(start=time(22, 0), end=time(1, 30))
    due = local(2026, 10, 31, 23, 0)

    # Act
    result = shift_to_sendable(due, window=fold_window, zone=NY)

    # Assert: the earlier of the two 01:30s (EDT, -04:00), not the later (EST, -05:00).
    assert result == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)


def test_shift_across_dst_is_still_idempotent():
    gap_window = QuietHours(start=time(22, 0), end=time(2, 30))
    once = shift_to_sendable(local(2026, 3, 7, 23, 0), window=gap_window, zone=NY)

    assert shift_to_sendable(once, window=gap_window, zone=NY) == once


# --- Idempotency and zones -----------------------------------------------------------------------


def test_shift_is_idempotent():
    """AD-7: a deferred send is moved once. Shifting the result must change nothing."""
    once = shift_to_sendable(local(2026, 11, 13, 23, 30), window=NIGHT, zone=NY)

    twice = shift_to_sendable(once, window=NIGHT, zone=NY)

    assert twice is once


def test_shift_non_utc_zone_defers_in_local_time():
    """Asia/Dhaka (+06, no DST) — the zone the timeline intent flagged as a live data case."""
    due = local(2026, 11, 13, 23, 30, zone=DHAKA)

    result = shift_to_sendable(due, window=NIGHT, zone=DHAKA)

    assert as_local(result, DHAKA) == datetime(2026, 11, 14, 8, 0, tzinfo=ZoneInfo(DHAKA))


def test_shift_same_instant_differs_by_zone():
    """One instant, two users: inside one user's night and outside the other's."""
    # 2026-11-14 04:00 UTC = 23:00 Nov 13 in New York (inside), 10:00 in Dhaka (outside).
    due = datetime(2026, 11, 14, 4, 0, tzinfo=UTC)

    assert shift_to_sendable(due, window=NIGHT, zone=NY) != due
    assert shift_to_sendable(due, window=NIGHT, zone=DHAKA) is due


# --- The window value itself ----------------------------------------------------------------------


def test_crosses_midnight_is_true_for_the_default_window():
    assert NIGHT.crosses_midnight is True
    assert AFTERNOON.crosses_midnight is False


def test_covers_crossing_window_both_sides_and_outside():
    assert NIGHT.covers(time(23, 30)) is True
    assert NIGHT.covers(time(2, 0)) is True
    assert NIGHT.covers(time(12, 0)) is False


def test_shift_rejects_naive_instant():
    """AD-6 forbids naive datetimes; to_instant raises rather than guessing a zone."""
    # The naive datetime is the point of the test, so DTZ001 is waived here and only here.
    naive = datetime(2026, 11, 13, 23, 30)  # noqa: DTZ001

    with pytest.raises(TypeError):
        shift_to_sendable(naive, window=NIGHT, zone=NY)


def test_shift_preserves_subsecond_instant_when_outside():
    due = local(2026, 11, 10, 12, 0) + timedelta(microseconds=500)

    assert shift_to_sendable(due, window=NIGHT, zone=NY) is due


def test_shift_never_moves_a_send_backwards():
    """The invariant behind every branch: a deferred send is later, never earlier.

    A send moved backwards would be in the past, and the next sweep would fire it at once —
    the opposite of what Quiet Hours is for. Swept across every hour of a day, against both
    window shapes and a zone with DST and one without.
    """
    for window in (NIGHT, AFTERNOON):
        for zone in (NY, DHAKA):
            for hour in range(24):
                for day in (7, 8, 13):  # includes the US spring-forward day
                    due = local(2026, 3, day, hour, 0, zone=zone)

                    assert shift_to_sendable(due, window=window, zone=zone) >= due
