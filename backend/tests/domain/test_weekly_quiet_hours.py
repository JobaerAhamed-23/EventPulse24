"""Seven quiet-hours windows, one per weekday (FR-51).

The single-window cases live in `test_quiet_hours.py` and are untouched by this item. What
is new here is everything that only exists once a user can set a *different* window on a
different day:

- a weeknight and a weekend behaving differently for the same user;
- a window that crosses midnight running into the next day's window;
- two windows covering one instant, where deferring to the earlier end would release a send
  into the middle of the other;
- a chain of three days, where a single pass is not enough;
- and the claim the shift's termination rests on: that seven day-anchored windows can
  never cover a whole week, so a sendable moment always exists.

The third and fourth are the ones that put a notification at 3am, which is why this module
exists before the model does.

No Django import anywhere: this module is importable with Django absent.
"""

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from domain.quiet_hours import (
    DAYS_IN_WEEK,
    MAX_DEFERRALS,
    QuietHours,
    WeeklyQuietHours,
    _ends_covering,
    shift_to_sendable,
)

NY = "America/New_York"

MON, TUE, WED, THU, FRI, SAT, SUN = range(DAYS_IN_WEEK)

# November 2026: the 9th is a Monday, so the 13th is a Friday and the 14th a Saturday.
WEEKNIGHT = QuietHours(start=time(22, 0), end=time(8, 0))
WEEKEND = QuietHours(start=time(23, 30), end=time(10, 0))


def local(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    """A UTC instant written as a New York wall-clock time."""
    return datetime(year, month, day, hour, minute, tzinfo=ZoneInfo(NY)).astimezone(UTC)


def as_local(instant: datetime) -> datetime:
    return instant.astimezone(ZoneInfo(NY))


def week(**by_weekday: QuietHours | None) -> WeeklyQuietHours:
    """A schedule written by weekday name, with every unnamed day left open."""
    names = {"mon": MON, "tue": TUE, "wed": WED, "thu": THU, "fri": FRI, "sat": SAT, "sun": SUN}
    windows: list[QuietHours | None] = [None] * DAYS_IN_WEEK
    for name, window in by_weekday.items():
        windows[names[name]] = window
    return WeeklyQuietHours(windows=tuple(windows))


# --- A week is seven days, and a day's window begins on that day --------------------------


def test_a_weeknight_and_a_weekend_window_differ_for_the_same_user():
    schedule = week(thu=WEEKNIGHT, fri=WEEKEND)

    # Thursday 23:00 is inside the weeknight window, which ends Friday 08:00.
    thursday = shift_to_sendable(local(2026, 11, 12, 23, 0), window=schedule, zone=NY)
    # Friday 23:00 is *before* the weekend window opens at 23:30, so it goes out as it is.
    friday = shift_to_sendable(local(2026, 11, 13, 23, 0), window=schedule, zone=NY)

    assert as_local(thursday) == datetime(2026, 11, 13, 8, 0, tzinfo=ZoneInfo(NY))
    assert friday == local(2026, 11, 13, 23, 0)


def test_a_days_window_owns_the_small_hours_of_the_next_day():
    # Friday 22:00-08:00 is *Friday night*. Saturday 02:00 belongs to it, and the send
    # defers to Saturday 08:00 — Friday's end, not Saturday's.
    schedule = week(fri=WEEKNIGHT, sat=WEEKEND)

    result = shift_to_sendable(local(2026, 11, 14, 2, 0), window=schedule, zone=NY)

    assert as_local(result) == datetime(2026, 11, 14, 8, 0, tzinfo=ZoneInfo(NY))


def test_saturdays_own_window_does_not_govern_saturday_morning():
    """The rule this item could most easily have got backwards.

    Saturday's 23:30-10:00 window is Saturday *night*. If the shift asked each instant's own
    weekday for a window and called `covers()`, Saturday 02:00 would match through that
    window's morning side and defer to Saturday 10:00 — the user's Saturday-night setting
    silently governing Saturday morning.
    """
    schedule = week(sat=WEEKEND)

    result = shift_to_sendable(local(2026, 11, 14, 2, 0), window=schedule, zone=NY)

    assert result == local(2026, 11, 14, 2, 0)


def test_a_day_with_no_window_sends_at_the_due_time():
    schedule = week(fri=WEEKNIGHT)

    result = shift_to_sendable(local(2026, 11, 11, 23, 0), window=schedule, zone=NY)

    assert result == local(2026, 11, 11, 23, 0)


# --- Two windows over one instant: the later end wins -------------------------------------


def test_two_windows_covering_one_instant_defer_to_the_later_end():
    """The acceptance criterion's explicit case.

    Friday 22:00-10:00 runs into Saturday morning; Saturday 09:00-11:00 is an ordinary
    daytime window. Saturday 09:30 sits in both. Releasing the send at 10:00 — Friday's end,
    the earlier one — would drop it into the middle of Saturday's window.
    """
    schedule = week(
        fri=QuietHours(start=time(22, 0), end=time(10, 0)),
        sat=QuietHours(start=time(9, 0), end=time(11, 0)),
    )

    result = shift_to_sendable(local(2026, 11, 14, 9, 30), window=schedule, zone=NY)

    assert as_local(result) == datetime(2026, 11, 14, 11, 0, tzinfo=ZoneInfo(NY))


def test_a_deferral_that_lands_inside_a_third_days_window_defers_again():
    """One pass is not enough, which is why the shift runs to a fixpoint.

    Monday 01:00-00:30 crosses midnight and ends Tuesday 00:30. Tuesday 00:00-23:00 covers
    that instant. A single-pass shift would send at 00:30 on Tuesday — inside quiet hours.
    """
    schedule = week(
        mon=QuietHours(start=time(1, 0), end=time(0, 30)),
        tue=QuietHours(start=time(0, 0), end=time(23, 0)),
    )

    result = shift_to_sendable(local(2026, 11, 9, 2, 0), window=schedule, zone=NY)

    assert as_local(result) == datetime(2026, 11, 10, 23, 0, tzinfo=ZoneInfo(NY))


def test_the_shift_is_idempotent_on_a_weekly_schedule():
    schedule = week(fri=WEEKNIGHT, sat=WEEKEND)

    once = shift_to_sendable(local(2026, 11, 13, 23, 0), window=schedule, zone=NY)
    twice = shift_to_sendable(once, window=schedule, zone=NY)

    assert twice == once


def test_the_shift_never_moves_a_send_backwards():
    schedule = week(mon=WEEKNIGHT, tue=WEEKEND, wed=WEEKNIGHT, thu=WEEKEND, fri=WEEKNIGHT)

    for day in range(9, 16):
        for hour in range(24):
            due = local(2026, 11, day, hour, 0)
            assert shift_to_sendable(due, window=schedule, zone=NY) >= due


# --- A Free user's single window is unchanged ---------------------------------------------


def test_one_window_every_day_is_the_same_answer_as_the_bare_window():
    """A Free user's single window and `every_day` of it are the same arithmetic.

    This is what makes the reshape safe: the single-window path is not a special case
    bolted on beside the weekly one, it is the weekly one with seven identical days.
    """
    everyday = WeeklyQuietHours.every_day(WEEKNIGHT)

    for day in range(9, 16):
        for hour in range(24):
            due = local(2026, 11, day, hour, 0)
            assert shift_to_sendable(due, window=everyday, zone=NY) == shift_to_sendable(
                due, window=WEEKNIGHT, zone=NY
            )


def test_an_empty_week_leaves_every_send_alone():
    schedule = WeeklyQuietHours.every_day(None)

    due = local(2026, 11, 13, 23, 0)

    assert shift_to_sendable(due, window=schedule, zone=NY) is due


def test_a_disabled_day_is_a_day_with_no_quiet_hours():
    """`start == end` stays disabled rather than "defer forever" — as for one window."""
    schedule = week(fri=QuietHours(start=time(9, 0), end=time(9, 0)))

    due = local(2026, 11, 13, 9, 0)

    assert shift_to_sendable(due, window=schedule, zone=NY) is due


# --- DST, in both directions, with the window unchanged -----------------------------------


def test_a_window_survives_spring_forward():
    """8 March 2026: New York skips 02:00-03:00. The window is wall-clock and does not move."""
    schedule = week(sat=QuietHours(start=time(22, 0), end=time(2, 30)))

    result = shift_to_sendable(local(2026, 3, 7, 23, 0), window=schedule, zone=NY)

    # 02:30 does not exist that night; `read_wall_clock` resolves it deterministically, and
    # the send lands after the gap rather than before it.
    assert result > local(2026, 3, 7, 23, 0)
    assert as_local(result).date() == date(2026, 3, 8)


def test_a_window_survives_fall_back():
    """1 November 2026: New York repeats 01:00-02:00. The window is still 22:00-01:30."""
    schedule = week(sat=QuietHours(start=time(22, 0), end=time(1, 30)))

    result = shift_to_sendable(local(2026, 10, 31, 23, 0), window=schedule, zone=NY)

    assert as_local(result).hour == 1
    assert as_local(result).minute == 30


def test_the_window_is_read_in_the_users_own_zone():
    schedule = week(fri=WEEKNIGHT)

    # 23:00 in New York is the next midday in Dhaka — inside the window for one, not the
    # other, from the same instant.
    due = local(2026, 11, 13, 23, 0)

    assert shift_to_sendable(due, window=schedule, zone=NY) != due
    assert shift_to_sendable(due, window=schedule, zone="Asia/Dhaka") is due


# --- Seven windows can never cover a whole week -------------------------------------------


def test_every_schedule_leaves_a_sendable_moment():
    """The claim `shift_to_sendable`'s termination rests on, checked by brute force.

    A window spans `(end - start) mod 1440` minutes, at most 1439 — a span of 0 is
    `disabled`, not 24 hours. Closing every seam around the week would need the seven spans
    to sum to 10080, and they can sum to at most 7 x 1439 = 10073. So every schedule leaves
    at least seven minutes open.

    This walks the worst case the arithmetic allows — seven maximal windows, every
    alignment of their starts — and asserts a sendable minute survives each one.
    """
    longest = 1439

    for offset in range(0, 1440, 7):
        windows = []
        for weekday in range(DAYS_IN_WEEK):
            start_minute = (weekday * offset) % 1440
            start = time(start_minute // 60, start_minute % 60)
            end_minute = (start_minute + longest) % 1440
            windows.append(QuietHours(start=start, end=time(end_minute // 60, end_minute % 60)))
        schedule = WeeklyQuietHours(windows=tuple(windows))

        # Monday 9 November 2026 through Sunday the 15th, minute by minute.
        open_minutes = [
            minute
            for day in range(9, 16)
            for hour in range(24)
            for minute in range(60)
            # Naive on purpose: `_ends_covering` takes a *wall clock*, reading only its
            # `.date()` and `.time()`, and its docstring calls the ends it returns naive.
            # A `tzinfo` here would assert an instant this value does not mean.
            if not _ends_covering(
                schedule,
                datetime(2026, 11, day, hour, minute),  # noqa: DTZ001
            )
        ]
        assert open_minutes, f"a schedule with starts stepping by {offset} covered the week"


def test_the_shift_always_reaches_an_uncovered_instant_well_inside_its_bound():
    """The loop's bound is a guarantee for the reader, not a policy that ever fires."""
    maximal = QuietHours(start=time(0, 0), end=time(23, 59))
    schedule = WeeklyQuietHours.every_day(maximal)

    result = shift_to_sendable(local(2026, 11, 9, 12, 0), window=schedule, zone=NY)

    # It lands in the one-minute seam each day leaves, and sitting there it is covered by
    # nothing — so a further shift would be a no-op.
    assert _ends_covering(schedule, as_local(result).replace(tzinfo=None)) == []
    assert shift_to_sendable(result, window=schedule, zone=NY) == result
    assert MAX_DEFERRALS == 8


# --- The type's own rules ------------------------------------------------------------------


def test_a_week_must_have_seven_days():
    import pytest

    with pytest.raises(ValueError, match="7 days"):
        WeeklyQuietHours(windows=(WEEKNIGHT, None))


def test_no_schedule_at_all_covers_nothing():
    """A user with Quiet Hours switched off entirely.

    `None` is a third shape alongside a bare `QuietHours` and a `WeeklyQuietHours`, and it
    means "no window": nothing is covered, so nothing is ever deferred. Empty ends are how
    this module spells "send now".
    """
    assert (
        _ends_covering(
            None,
            datetime(2026, 11, 9, 23, 30),  # noqa: DTZ001 — a wall clock, see above
        )
        == []
    )
