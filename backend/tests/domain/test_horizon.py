"""The user's local horizon: "the next 48 hours", in their own zone (FR-10).

**The property worth having is that the horizon is a local wall clock, not a UTC
arithmetic.** A naive `now + timedelta(hours=48)` is 47 local hours on a spring-forward
day and 49 on a fall-back day — and the user said "48 hours". These tests pin the
difference at exactly those two moments, because a horizon that is only correct on
ordinary days is a horizon that is wrong twice a year and never noticed.

**The other thing worth pinning is that the zone is the user's.** Two users at the same
instant in different zones must get different horizons, or "the next 48 hours" means one
place's next 48 hours for everybody.

**An unknown zone falls back to UTC rather than raising**, for the same reason
`local_date_for` does: a hand-edited zone name must not take down the user's digest.
"""

from datetime import UTC, datetime, timedelta

import pytest

from domain.horizon import local_horizon

#: The one 48-hour window in the codebase (AD-8). The function takes the window as a
#: parameter precisely so this stays the only place the number is written.
WINDOW = timedelta(hours=48)

#: A Wednesday. 2026-11-04 16:00 UTC is 09:00 in Los Angeles (PST) and 08:00 in New York
#: (EST).
NOW = datetime(2026, 11, 4, 16, 0, tzinfo=UTC)

LA = "America/Los_Angeles"
NY = "America/New_York"
TOKYO = "Asia/Tokyo"


def horizon(now=NOW, zone=LA, window=WINDOW):
    return local_horizon(now=now, zone_name=zone, window=window)


def local_wall_clock(instant, zone):
    """The instant's reading on the wall clock in `zone`, with no offset attached."""
    from zoneinfo import ZoneInfo

    return instant.astimezone(ZoneInfo(zone)).replace(tzinfo=None)


def clock(year, month, day, hour=0, minute=0):
    """A floating wall clock — a reading with no offset, and deliberately none.

    **The wall clock is the thing under test.** The horizon is read on the user's
    clock, so the expectations here are readings rather than instants, and a reading
    has no `tzinfo` to give it.
    """
    return datetime(year, month, day, hour, minute)  # noqa: DTZ001 — a floating wall clock


# --- the ordinary day -----------------------------------------------------------------


def test_on_an_ordinary_day_the_horizon_is_forty_eight_hours_later():
    assert horizon() == NOW + WINDOW


def test_the_horizon_is_aware():
    assert horizon().tzinfo is not None


# --- the zone is the user's ------------------------------------------------------------


def test_two_users_in_different_zones_get_different_horizons():
    """The horizon is read in **each user's own zone**, so two users' horizons differ.

    The two zones here are 17 hours apart, and the wall clocks are correspondingly 17
    hours apart — the same rule read in two frames. (The *instants* coincide here,
    because 48 wall-clock hours is the same span in both; the readings do not, and the
    readings are what the horizon is about.)
    """
    la = horizon(zone=LA)
    tokyo = horizon(zone=TOKYO)

    assert local_wall_clock(la, LA) == clock(2026, 11, 6, 8, 0)
    assert local_wall_clock(tokyo, TOKYO) == clock(2026, 11, 7, 1, 0)
    # The two readings are 17 hours apart — the difference between the two zones.
    assert (local_wall_clock(tokyo, TOKYO) - local_wall_clock(la, LA)) == timedelta(hours=17)


def test_a_zone_far_enough_from_utc_shifts_the_horizon_by_a_day():
    """The horizon's *date* can differ between two users at the same instant.

    At `NOW` the Los Angeles user reads 08:00 on the 4th and the Tokyo user already
    reads 01:00 on the 5th. Their 48-hour horizons therefore land on different calendar
    days — which is the whole reason the digest's key is a **local** date and not a UTC
    one.
    """
    assert local_wall_clock(horizon(zone=LA), LA).date() == clock(2026, 11, 6).date()
    assert local_wall_clock(horizon(zone=TOKYO), TOKYO).date() == clock(2026, 11, 7).date()


def test_the_horizon_advances_with_now():
    # The horizon is always `window` ahead of the instant you ask from, in wall-clock
    # terms — so asking an hour later gives an hour later.
    assert horizon(now=NOW + timedelta(hours=1), zone="Asia/Tokyo") == horizon(
        zone="Asia/Tokyo"
    ) + timedelta(hours=1)


# --- the DST days, which is where the difference lives ---------------------------------


def test_a_spring_forward_day_keeps_forty_eight_local_hours():
    """2026-03-08: the US clocks go forward at 02:00 local.

    The day is 23 hours long, so 48 elapsed hours lands on **01:00** on the wall clock.
    The local horizon is **00:00** — the wall clock 48 hours on — which is what the user
    asked for, and it is an hour *earlier* than the naive arithmetic.
    """
    start = datetime(2026, 3, 8, 8, 0, tzinfo=UTC)  # 00:00 PST

    reached = local_horizon(now=start, zone_name=LA, window=WINDOW)

    assert local_wall_clock(reached, LA) == clock(2026, 3, 10, 0, 0)
    assert reached == start + WINDOW - timedelta(hours=1)


def test_a_fall_back_day_keeps_forty_eight_local_hours():
    """2026-11-01: the US clocks go back at 02:00 local, to 01:00.

    **The wall clock gains an hour.** So the local clock reads 00:00, 01:00, **01:00
    again**, 02:00 — and a wall-clock window of 48 hours from midnight reaches **00:00 on
    the third**, while 48 elapsed hours would have reached 23:00 on the second. The local
    horizon is the one that says 00:00, and it is an hour *later* than the naive
    arithmetic.
    """
    start = datetime(2026, 11, 1, 7, 0, tzinfo=UTC)  # 00:00 PDT, before the transition

    reached = local_horizon(now=start, zone_name=LA, window=WINDOW)

    assert local_wall_clock(reached, LA) == clock(2026, 11, 3, 0, 0)
    # The naive arithmetic would have reached 23:00 on the second — an hour short.
    assert local_wall_clock(start + WINDOW, LA) == clock(2026, 11, 2, 23, 0)
    assert reached == start + WINDOW + timedelta(hours=1)


def test_a_utc_horizon_would_be_the_wrong_thing_and_these_tests_prove_it():
    """The naive arithmetic is *wrong* on the DST days — this is why the module exists.

    It is the negative control: without it, a future change that swapped `local_horizon`
    for `now + window` would still pass an ordinary-day test.

    **On a spring-forward day the day is 23 hours long.** So 48 *elapsed* hours from
    midnight is 01:00 on the wall clock, while 48 hours *on the wall clock* is 00:00 —
    and the two are an hour apart as instants. The local horizon is the one that says
    00:00, because the user said "48 hours" and their clock is what they read.
    """
    spring = datetime(2026, 3, 8, 8, 0, tzinfo=UTC)  # 00:00 PST on the transition day
    naive = spring + WINDOW
    local = local_horizon(now=spring, zone_name=LA, window=WINDOW)

    assert naive != local
    # The local horizon is the wall clock 48 hours on.
    assert local_wall_clock(local, LA) == clock(2026, 3, 10, 0, 0)
    # The naive one overshoots the wall clock by the hour the day gained.
    assert local_wall_clock(naive, LA) == clock(2026, 3, 10, 1, 0)
    # And the local one is the earlier instant, because it is an hour *short* of the
    # naive one — 47 elapsed hours for a 48-hour wall-clock window.
    assert local == naive - timedelta(hours=1)


# --- the fallbacks ----------------------------------------------------------------------


def test_an_unknown_zone_falls_back_to_utc_rather_than_raising():
    reached = horizon(zone="Not/AZone")

    assert reached == NOW + WINDOW


def test_an_empty_zone_falls_back_to_utc_rather_than_raising():
    assert horizon(zone="") == NOW + WINDOW


# --- the window is a parameter ------------------------------------------------------------


def test_the_window_is_the_caller_s():
    assert horizon(window=timedelta(hours=1)) == NOW + timedelta(hours=1)


def test_a_zero_window_is_now():
    assert horizon(window=timedelta(0)) == NOW


# --- the DST gap and fold, resolved rather than crashed -----------------------------------


def test_a_horizon_that_falls_in_a_dst_gap_is_still_an_instant():
    """The horizon's local reading can land on a time that does not exist.

    `read_wall_clock` resolves it deterministically, and this test only asserts that the
    answer is an instant rather than an exception — the exact reading is `read_wall_clock`
    's, and it has its own tests.
    """
    # 2026-03-07 02:30 local in Los Angeles, plus 24 hours lands on 2026-03-08 02:30 —
    # which does not exist.
    start = datetime(2026, 3, 7, 10, 30, tzinfo=UTC)

    reached = local_horizon(now=start, zone_name=LA, window=timedelta(hours=24))

    assert reached.tzinfo is not None
    assert reached > start


def test_the_horizon_is_truncated_to_whole_seconds():
    reached = horizon(now=datetime(2026, 11, 4, 16, 0, 0, 123456, tzinfo=UTC))

    assert reached.microsecond == 0


# --- the boundary the suppression rule compares against ------------------------------------


def test_an_event_exactly_at_the_horizon_qualifies():
    """The boundary is inclusive, so `<=` is the right comparison.

    FR-5's "within the next 48 hours" includes the boundary, and the ranking boost it
    carries applies at exactly the same boundary — so the candidate set and the boost
    cannot disagree about which events are "soon".
    """
    reached = horizon()

    assert reached <= reached
    assert (reached + timedelta(seconds=1)) > reached


@pytest.mark.parametrize("zone", [LA, NY, TOKYO, "UTC"])
def test_the_horizon_is_after_now_in_every_zone(zone):
    assert horizon(zone=zone) > NOW
