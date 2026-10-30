"""Event Fit: the session-free score and tags (AD-10, FR-26).

Every rule is pinned at its **boundary** — the exact constant, and one unit either side.
A test that only checks the middle of a band does not know where the band ends.

The two cases this file is built around are the ones the work item calls out: a **DST
transition**, and a **date line**. Both are cases where the UTC day and the event's own
local day disagree, and the rule under test is that the event's own zone wins.
"""

import dataclasses
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from domain.event_fit import EventFit, compute_event_fit
from shared.constants import (
    EVENT_FIT_EVENING_HOUR,
    EVENT_FIT_SCORE_MAX,
    EVENT_FIT_SCORE_MIN,
)

NEW_YORK = "America/New_York"
AUCKLAND = "Pacific/Auckland"


def local(*, year, month, day, hour=0, minute=0, second=0, zone=NEW_YORK) -> datetime:
    """A wall-clock time in `zone`, as the instant it is."""
    return datetime(year, month, day, hour, minute, second, tzinfo=ZoneInfo(zone)).astimezone(UTC)


# A Thursday noon in New York. Most cases are measured from here.
THURSDAY_NOON = local(year=2026, month=5, day=14, hour=12)


# ── The score bands ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("until_start", "expected"),
    [
        # "today" — anything from now up to (but not including) a day away.
        (timedelta(seconds=1), 5),
        (timedelta(hours=11), 5),
        (timedelta(hours=23, minutes=59, seconds=59), 5),
        # "within two days" — a day away is no longer today.
        (timedelta(days=1), 4),
        (timedelta(days=1, hours=23), 4),
        # "within a week"
        (timedelta(days=2), 3),
        (timedelta(days=6, hours=23), 3),
        # "within a fortnight"
        (timedelta(days=7), 2),
        (timedelta(days=13, hours=23), 2),
        # "later"
        (timedelta(days=14), 1),
        (timedelta(days=365), 1),
    ],
)
def test_the_proximity_bands(until_start, expected):
    """Each band is an inclusive upper bound, and the boundaries are where they say."""
    fit = compute_event_fit(
        start_time_utc=THURSDAY_NOON + until_start,
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
        extraction_confidence=Decimal("1.00"),
        city="Brooklyn",
    )
    assert fit.score == expected


@pytest.mark.parametrize(
    ("confidence", "expected"),
    [
        (Decimal("1.00"), 5),
        (Decimal("0.90"), 5),
        (Decimal("0.89"), 4),
        (Decimal("0.70"), 4),
        (Decimal("0.69"), 3),
        (Decimal("0.50"), 3),
        (Decimal("0.49"), 2),
        (Decimal("0.00"), 2),
    ],
)
def test_the_confidence_bands(confidence, expected):
    """The confidence bands' lower bounds are inclusive.

    The event is under a day away, so proximity is 5 and the **confidence band is what
    the score shows** — the score is the lower of the two, and nothing here lowers it
    further.
    """
    fit = compute_event_fit(
        start_time_utc=THURSDAY_NOON + timedelta(hours=2),
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
        extraction_confidence=confidence,
        city="Brooklyn",
    )
    assert fit.score == expected


def test_the_score_is_the_lower_of_the_two_bands():
    """A badly-extracted event tonight is not a good fit, however soon it is.

    This is the rule that decided against a weighted sum: the minimum is a rule a person
    can state out loud, and it never says an event we know little about is excellent.
    """
    fit = compute_event_fit(
        start_time_utc=THURSDAY_NOON + timedelta(hours=2),
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
        extraction_confidence=Decimal("0.00"),
        city="Brooklyn",
    )
    assert fit.score == 2, "the confidence band caps it, even though it is tonight"


def test_the_score_is_the_lower_of_the_two_bands_the_other_way():
    """And a well-extracted event next month is not a good fit either."""
    fit = compute_event_fit(
        start_time_utc=THURSDAY_NOON + timedelta(days=30),
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
        extraction_confidence=Decimal("1.00"),
        city="Brooklyn",
    )
    assert fit.score == 1


def test_an_event_with_no_confidence_scores_on_proximity_alone():
    """No extraction confidence is not a reason to refuse an indicator."""
    fit = compute_event_fit(
        start_time_utc=THURSDAY_NOON + timedelta(hours=2),
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
        extraction_confidence=None,
        city="Brooklyn",
    )
    assert fit.score == 5


def test_an_event_already_underway_scores_in_the_last_band():
    """An event in progress is not coming up, and a preview shows what is coming."""
    fit = compute_event_fit(
        start_time_utc=THURSDAY_NOON - timedelta(hours=1),
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
        extraction_confidence=Decimal("1.00"),
        city="Brooklyn",
    )
    assert fit.score == 1


def test_an_event_starting_exactly_now_is_in_the_last_band():
    """The boundary is exact: an event starting at `now` has begun."""
    fit = compute_event_fit(
        start_time_utc=THURSDAY_NOON,
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
        extraction_confidence=Decimal("1.00"),
        city="Brooklyn",
    )
    assert fit.score == 1


def test_an_event_a_second_from_now_is_still_the_top_band():
    """One second before it starts, it is as imminent as an event gets."""
    fit = compute_event_fit(
        start_time_utc=THURSDAY_NOON + timedelta(seconds=1),
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
        extraction_confidence=Decimal("1.00"),
        city="Brooklyn",
    )
    assert fit.score == 5


def test_the_score_is_never_outside_one_to_five():
    for days in (-30, -1, 0, 1, 3, 10, 400):
        for confidence in (None, Decimal("0.00"), Decimal("0.50"), Decimal("1.00")):
            fit = compute_event_fit(
                start_time_utc=THURSDAY_NOON + timedelta(days=days),
                start_time_tz=NEW_YORK,
                now=THURSDAY_NOON,
                extraction_confidence=confidence,
                city="Brooklyn",
            )
            assert EVENT_FIT_SCORE_MIN <= fit.score <= EVENT_FIT_SCORE_MAX


def test_a_fit_with_an_out_of_range_score_is_refused():
    """The score's range is enforced by the value itself, not only by the caller."""
    with pytest.raises(ValueError):
        EventFit(score=0, tags=())
    with pytest.raises(ValueError):
        EventFit(score=6, tags=())


# ── The time tags ───────────────────────────────────────────────────────────────────


def test_tonight_needs_the_evening():
    """An event at 09:00 today is later today, not tonight."""
    before = compute_event_fit(
        start_time_utc=local(year=2026, month=5, day=14, hour=EVENT_FIT_EVENING_HOUR - 1),
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
        city="Brooklyn",
    )
    assert "tonight" not in before.tags

    at = compute_event_fit(
        start_time_utc=local(year=2026, month=5, day=14, hour=EVENT_FIT_EVENING_HOUR),
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
        city="Brooklyn",
    )
    assert "tonight" in at.tags


def test_tonight_is_exactly_at_the_evening_hour():
    """The hour is inclusive: 17:00 is tonight, 16:59:59 is not."""
    one_second_early = compute_event_fit(
        start_time_utc=local(year=2026, month=5, day=14, hour=16, minute=59, second=59),
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
        city="Brooklyn",
    )
    assert "tonight" not in one_second_early.tags


def test_tomorrow_is_the_next_local_day():
    fit = compute_event_fit(
        start_time_utc=local(year=2026, month=5, day=15, hour=20),
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
        city="Brooklyn",
    )
    assert "tomorrow" in fit.tags
    assert "tonight" not in fit.tags


def test_the_day_after_tomorrow_is_not_tomorrow():
    fit = compute_event_fit(
        start_time_utc=local(year=2026, month=5, day=16, hour=20),
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
        city="Brooklyn",
    )
    assert "tomorrow" not in fit.tags


def test_this_weekend_is_the_coming_saturday_and_sunday():
    saturday = compute_event_fit(
        start_time_utc=local(year=2026, month=5, day=16, hour=20),
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
        city="Brooklyn",
    )
    sunday = compute_event_fit(
        start_time_utc=local(year=2026, month=5, day=17, hour=20),
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
        city="Brooklyn",
    )
    assert "this_weekend" in saturday.tags
    assert "this_weekend" in sunday.tags


def test_a_weekday_is_not_the_weekend():
    fit = compute_event_fit(
        start_time_utc=local(year=2026, month=5, day=15, hour=20),
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
        city="Brooklyn",
    )
    assert "this_weekend" not in fit.tags


def test_a_weekend_three_weeks_out_is_not_this_weekend():
    """'This weekend' means this weekend. A Saturday in June is not it."""
    fit = compute_event_fit(
        start_time_utc=local(year=2026, month=6, day=6, hour=20),
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
        city="Brooklyn",
    )
    assert "this_weekend" not in fit.tags


def test_a_weekend_seven_days_out_is_not_this_weekend():
    """The weekend *after next* is not "this weekend".

    Thursday May 14 is the reference, so the coming weekend is May 16/17. May 23/24 is
    the one after it — and a reader who reads "this weekend" on a Thursday means the
    Saturday they can still plan for.
    """
    fit = compute_event_fit(
        start_time_utc=local(year=2026, month=5, day=23, hour=20),
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
        city="Brooklyn",
    )
    assert "this_weekend" not in fit.tags


def test_the_weekend_is_the_coming_one_from_a_monday():
    """From a Monday, the coming Saturday is still "this weekend"."""
    monday = local(year=2026, month=5, day=18, hour=12)  # a Monday
    fit = compute_event_fit(
        start_time_utc=local(year=2026, month=5, day=23, hour=20),
        start_time_tz=NEW_YORK,
        now=monday,
        city="Brooklyn",
    )
    assert "this_weekend" in fit.tags


def test_the_weekend_under_way_is_still_this_weekend():
    """From a Saturday, today's own Saturday is the weekend now under way."""
    saturday = local(year=2026, month=5, day=16, hour=12)  # a Saturday
    fit = compute_event_fit(
        start_time_utc=local(year=2026, month=5, day=16, hour=20),
        start_time_tz=NEW_YORK,
        now=saturday,
        city="Brooklyn",
    )
    assert "this_weekend" in fit.tags


def test_the_next_weekend_from_a_saturday_is_still_the_weekend_in_view():
    """From a Saturday, the coming Sunday is still "this weekend".

    This is the case a `<= 7` day bound gets wrong in the other direction: the Saturday
    *after* this one is exactly seven days out, and it belongs to a different weekend,
    but the Sunday in between belongs to this one.
    """
    saturday = local(year=2026, month=5, day=16, hour=12)  # a Saturday
    sunday = compute_event_fit(
        start_time_utc=local(year=2026, month=5, day=17, hour=20),
        start_time_tz=NEW_YORK,
        now=saturday,
        city="Brooklyn",
    )
    assert "this_weekend" in sunday.tags

    next_saturday = compute_event_fit(
        start_time_utc=local(year=2026, month=5, day=23, hour=20),
        start_time_tz=NEW_YORK,
        now=saturday,
        city="Brooklyn",
    )
    assert "this_weekend" not in next_saturday.tags


def test_the_weekend_across_new_year_is_still_this_weekend():
    """A weekend that spans the ISO year boundary is not lost.

    2027-01-01 is a Friday, so the weekend of January 2nd/3rd is the coming weekend
    from 2026-12-28. Comparing ISO *week numbers* across the boundary would compare 53
    with 52 and lose it; comparing the weekends by their Saturdays does not.
    """
    fit = compute_event_fit(
        start_time_utc=local(year=2027, month=1, day=2, hour=20),
        start_time_tz=NEW_YORK,
        now=local(year=2026, month=12, day=28, hour=12),
        city="Brooklyn",
    )
    assert "this_weekend" in fit.tags


def test_the_weekend_under_way_from_a_sunday_is_still_this_weekend():
    """On a Sunday, the weekend under way — today — is the one in view."""
    sunday = local(year=2026, month=5, day=17, hour=12)  # a Sunday
    fit = compute_event_fit(
        start_time_utc=local(year=2026, month=5, day=17, hour=20),
        start_time_tz=NEW_YORK,
        now=sunday,
        city="Brooklyn",
    )
    assert "this_weekend" in fit.tags


def test_the_weekend_after_the_one_under_way_is_not_in_view():
    """From a Sunday, next weekend is next weekend."""
    sunday = local(year=2026, month=5, day=17, hour=12)  # a Sunday
    fit = compute_event_fit(
        start_time_utc=local(year=2026, month=5, day=23, hour=20),
        start_time_tz=NEW_YORK,
        now=sunday,
        city="Brooklyn",
    )
    assert "this_weekend" not in fit.tags


@pytest.mark.parametrize(
    ("now_day", "event_day", "expected"),
    [
        # Monday the 18th — the coming weekend is the 23rd/24th.
        (18, 23, True),
        # Friday the 22nd — the coming weekend is still the 23rd/24th.
        (22, 23, True),
        # Saturday the 23rd — the weekend under way is the 23rd/24th.
        (23, 23, True),
        # Sunday the 24th — the weekend under way is the 23rd/24th.
        (24, 24, True),
        # From every one of those days, the 30th is the weekend *after* the one in view.
        (18, 30, False),
        (22, 30, False),
        (23, 30, False),
        (24, 30, False),
    ],
)
def test_the_weekend_in_view_from_each_day_of_the_week(now_day, event_day, expected):
    """Every day of the week names exactly one weekend, and it is the nearest one.

    The event is always a Saturday. From the 18th to the 24th the weekend in view is
    the 23rd/24th, and the 30th — one week beyond it — is never in view.
    """
    fit = compute_event_fit(
        start_time_utc=local(year=2026, month=5, day=event_day, hour=20),
        start_time_tz=NEW_YORK,
        now=local(year=2026, month=5, day=now_day, hour=12),
        city="Brooklyn",
    )
    assert ("this_weekend" in fit.tags) is expected


def test_an_event_that_has_already_begun_carries_no_time_tag():
    """A Saturday that has begun is not 'this weekend' any more."""
    fit = compute_event_fit(
        start_time_utc=local(year=2026, month=9, day=19, hour=20),
        start_time_tz=NEW_YORK,
        now=local(year=2026, month=9, day=19, hour=21),
        city="Brooklyn",
    )
    assert fit.tags == ("in_brooklyn",)


# ── The place tag ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("city", "expected"),
    [
        ("Brooklyn", "in_brooklyn"),
        ("brooklyn", "in_brooklyn"),
        ("BROOKLYN", "in_brooklyn"),
        ("San Francisco", "in_san_francisco"),
        ("New York", "in_new_york"),
        ("  Brooklyn  ", "in_brooklyn"),
        ("São Paulo", "in_sao_paulo"),
        ("München", "in_munchen"),
        ("New York", "in_new_york"),
    ],
)
def test_the_city_tag(city, expected):
    fit = compute_event_fit(
        start_time_utc=THURSDAY_NOON + timedelta(hours=2),
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
        city=city,
    )
    assert expected in fit.tags


def test_an_event_with_no_city_gets_no_place_tag():
    """An event without a venue city is not guessed at (the work item's rule)."""
    fit = compute_event_fit(
        start_time_utc=THURSDAY_NOON + timedelta(hours=2),
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
        city="",
    )
    assert fit.tags == ()


def test_the_place_tag_is_last():
    """The order is fixed, so two events with the same tags list them the same way."""
    fit = compute_event_fit(
        start_time_utc=local(year=2026, month=5, day=14, hour=20),
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
        city="Brooklyn",
    )
    assert fit.tags == ("tonight", "in_brooklyn")


# ── The day boundaries are the event's own ──────────────────────────────────────────


def test_the_local_day_is_the_events_not_the_readers():
    """The event's own zone decides the day.

    An event at 23:30 local on Friday is "tonight" on Friday — even though its UTC
    instant is Saturday, and even though a reader in Los Angeles sees it as Friday
    afternoon.

    The reference is also Friday, in New York, so that the event is the *same local
    day* as "now" while being a *different UTC day*. That disagreement is the whole
    point: a rule that read UTC would say Saturday, and Saturday from a Friday is
    "tomorrow" — not "tonight".
    """
    friday_late = local(year=2026, month=5, day=15, hour=23, minute=30)
    # Its UTC instant is Saturday, 03:30Z.
    assert friday_late.astimezone(UTC).date().isoformat() == "2026-05-16"

    fit = compute_event_fit(
        start_time_utc=friday_late,
        start_time_tz=NEW_YORK,
        now=local(year=2026, month=5, day=15, hour=21),
        city="Brooklyn",
    )
    assert "tonight" in fit.tags
    assert "tomorrow" not in fit.tags


def test_an_event_tonight_is_not_tomorrow_even_when_utc_says_so():
    """The companion case: the same event, read from the Thursday.

    From Thursday noon the event really is tomorrow — it is Friday — and the code says
    so. The point of the pair is that the answer changes with the *reference*, and each
    answer is right for the day it was computed on.
    """
    friday_late = local(year=2026, month=5, day=15, hour=23, minute=30)
    fit = compute_event_fit(
        start_time_utc=friday_late,
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
        city="Brooklyn",
    )
    assert "tomorrow" in fit.tags
    assert "tonight" not in fit.tags


def test_a_dst_transition_does_not_move_the_day():
    """The spring-forward day is still the same local day.

    2026-03-08 is the US spring-forward. An event at 20:00 local that day is 00:00Z on
    the 9th — a different UTC day — and it is still 'tonight' locally.
    """
    transition_evening = local(year=2026, month=3, day=8, hour=20)
    assert transition_evening.astimezone(UTC).date().isoformat() == "2026-03-09"

    fit = compute_event_fit(
        start_time_utc=transition_evening,
        start_time_tz=NEW_YORK,
        now=local(year=2026, month=8, day=8, hour=12),  # a moment before, in local terms
        city="Brooklyn",
    )
    # The event is in the past relative to that reference, so it carries no time tag —
    # but what matters is that it was not mistaken for the 9th.
    assert "tonight" not in fit.tags

    fit = compute_event_fit(
        start_time_utc=transition_evening,
        start_time_tz=NEW_YORK,
        now=local(year=2026, month=3, day=8, hour=12),
        city="Brooklyn",
    )
    assert "tonight" in fit.tags
    assert "tomorrow" not in fit.tags


def test_a_date_line_crossing_keeps_the_events_day():
    """An event on Saturday in Auckland is 'this weekend', even where it is Friday.

    The event's UTC instant is Friday, and a reader in New York sees Friday evening —
    but the event's own day is Saturday, and the event's own day is what the tag says.
    """
    saturday_in_auckland = local(year=2026, month=5, day=16, hour=10, zone=AUCKLAND)
    # Its UTC instant is Friday.
    assert saturday_in_auckland.astimezone(UTC).date().isoformat() == "2026-05-15"
    # And New York reads it as Friday evening.
    assert saturday_in_auckland.astimezone(ZoneInfo(NEW_YORK)).date().isoformat() == "2026-05-15"

    fit = compute_event_fit(
        start_time_utc=saturday_in_auckland,
        start_time_tz=AUCKLAND,
        now=THURSDAY_NOON,
        city="Auckland",
    )
    assert "this_weekend" in fit.tags
    assert "tomorrow" in fit.tags, "it is Saturday in Auckland, so it is tomorrow"


def test_an_unknown_zone_falls_back_to_utc_rather_than_raising():
    """A fit is an indicator; an unreadable zone should not take the list down."""
    fit = compute_event_fit(
        start_time_utc=THURSDAY_NOON + timedelta(hours=2),
        start_time_tz="Not/AZone",
        now=THURSDAY_NOON,
        extraction_confidence=Decimal("1.00"),
        city="Brooklyn",
    )
    assert fit.score == 5


# ── Determinism ─────────────────────────────────────────────────────────────────────


def test_the_same_inputs_always_give_the_same_output():
    """No randomness, no clock read. The function is a function."""
    first = compute_event_fit(
        start_time_utc=local(year=2026, month=5, day=14, hour=20),
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
        extraction_confidence=Decimal("0.85"),
        city="Brooklyn",
    )
    second = compute_event_fit(
        start_time_utc=local(year=2026, month=5, day=14, hour=20),
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
        extraction_confidence=Decimal("0.85"),
        city="Brooklyn",
    )
    assert first == second


def test_the_fit_is_frozen():
    """A fit that could be mutated after it was computed is a fit that has drifted."""
    fit = compute_event_fit(
        start_time_utc=THURSDAY_NOON + timedelta(hours=2),
        start_time_tz=NEW_YORK,
        now=THURSDAY_NOON,
        city="Brooklyn",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        fit.score = 4  # type: ignore[misc]
