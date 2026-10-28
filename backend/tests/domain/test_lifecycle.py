"""Lifecycle (AD-4, AD-17): ±30 days from the original start, and the change classifier."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from domain.lifecycle import (
    LIFECYCLE_FACTS,
    NOT_YET_STORED,
    PRECEDENCE,
    ChangeKind,
    EventFacts,
    EventStatus,
    TimeMove,
    classify_change,
    classify_time_move,
)

ORIGINAL = datetime(2026, 11, 6, 0, 30, tzinfo=UTC)
WINDOW = timedelta(days=30)

STORED = EventFacts(
    start_utc=ORIGINAL,
    end_utc=ORIGINAL + timedelta(hours=3),
    start_time_tz="America/New_York",
    status=EventStatus.SCHEDULED,
    is_sold_out=False,
    venue_fingerprint="v1:venue",
    title="Japanese Breakfast",
    description="With special guests.",
    canonical_url="https://example.com/e/1",
)


def kinds(stored=STORED, original=ORIGINAL, **incoming):
    change = classify_change(stored, replace(stored, **incoming), original)
    return change.kinds if change else None


# --- classify_time_move ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("delta", "move"),
    [
        (timedelta(0), TimeMove.SAME),
        (timedelta(microseconds=500), TimeMove.SAME),  # whole seconds
        (timedelta(days=1), TimeMove.WITHIN_WINDOW),
        (WINDOW, TimeMove.WITHIN_WINDOW),  # exactly 30 days keeps the event_id
        (-WINDOW, TimeMove.WITHIN_WINDOW),
        (WINDOW + timedelta(seconds=1), TimeMove.SUPERSEDE),
        (-WINDOW - timedelta(seconds=1), TimeMove.SUPERSEDE),
    ],
)
def test_classify_time_move_boundaries(delta, move):
    assert classify_time_move(ORIGINAL, ORIGINAL + delta) is move


def test_classify_time_move_compares_instants_across_zones():
    same_instant = ORIGINAL.astimezone(ZoneInfo("Asia/Tokyo"))

    assert classify_time_move(ORIGINAL, same_instant) is TimeMove.SAME


def test_classify_time_move_requires_aware_datetimes():
    with pytest.raises(TypeError):
        classify_time_move(ORIGINAL, ORIGINAL.replace(tzinfo=None))


def test_two_small_moves_measured_from_the_original_supersede():
    # 20 days, then 20 more: each move is small, the drift is 40 days.
    after_first_move = replace(STORED, start_utc=ORIGINAL + timedelta(days=20))

    result = kinds(stored=after_first_move, start_utc=ORIGINAL + timedelta(days=40))

    assert result == (ChangeKind.SUPERSEDED,)


# --- classify_change ---------------------------------------------------------------------------


def test_classify_change_nothing_changed_is_none():
    assert classify_change(STORED, replace(STORED), ORIGINAL) is None


def test_classify_change_sub_second_difference_is_no_change():
    assert kinds(start_utc=ORIGINAL + timedelta(microseconds=10)) is None


@pytest.mark.parametrize(
    ("incoming", "expected"),
    [
        ({"start_utc": ORIGINAL + timedelta(days=2)}, (ChangeKind.TIME_MOVED,)),
        ({"end_utc": ORIGINAL + timedelta(hours=4)}, (ChangeKind.TIME_MOVED,)),
        ({"start_utc": ORIGINAL + timedelta(days=45)}, (ChangeKind.SUPERSEDED,)),
        ({"status": EventStatus.CANCELLED}, (ChangeKind.CANCELLED,)),
        ({"status": EventStatus.POSTPONED}, (ChangeKind.POSTPONED,)),
        ({"is_sold_out": True}, (ChangeKind.SOLD_OUT,)),
        ({"title": "Japanese Breakfast (Late Show)"}, (ChangeKind.DETAIL_CHANGED,)),
        ({"description": ""}, (ChangeKind.DETAIL_CHANGED,)),
        ({"canonical_url": "https://example.com/e/2"}, (ChangeKind.DETAIL_CHANGED,)),
        ({"start_time_tz": "America/Toronto"}, (ChangeKind.DETAIL_CHANGED,)),
        ({"venue_fingerprint": "v1:other"}, (ChangeKind.DETAIL_CHANGED,)),
    ],
    ids=[
        "time-moved",
        "end-only",
        "beyond-window",
        "cancelled",
        "postponed",
        "sold-out",
        "title",
        "description",
        "url",
        "tz-only",
        "venue",
    ],
)
def test_classify_change_single_kind(incoming, expected):
    assert kinds(**incoming) == expected


def test_cancellation_that_also_moves_the_date_is_only_a_cancellation():
    result = kinds(status=EventStatus.CANCELLED, start_utc=ORIGINAL + timedelta(days=40))

    assert result == (ChangeKind.CANCELLED,)


def test_time_move_and_sold_out_keep_both_kinds_in_precedence_order():
    result = kinds(start_utc=ORIGINAL + timedelta(days=1), is_sold_out=True)

    assert result == (ChangeKind.TIME_MOVED, ChangeKind.SOLD_OUT)


def test_sold_out_turning_back_off_is_a_sold_out_change():
    sold_out = replace(STORED, is_sold_out=True)

    change = classify_change(sold_out, replace(sold_out, is_sold_out=False), ORIGINAL)

    assert change.kinds == (ChangeKind.SOLD_OUT,)
    assert change.fields == {"is_sold_out"}


@pytest.mark.parametrize(
    ("stored_status", "incoming", "expected"),
    [
        (EventStatus.CANCELLED, {"status": EventStatus.SCHEDULED}, (ChangeKind.REINSTATED,)),
        (
            EventStatus.CANCELLED,
            {"status": EventStatus.POSTPONED},
            (ChangeKind.REINSTATED, ChangeKind.POSTPONED),
        ),
        (EventStatus.POSTPONED, {"status": EventStatus.SCHEDULED}, (ChangeKind.REINSTATED,)),
        (
            EventStatus.POSTPONED,
            {"status": EventStatus.SCHEDULED, "start_utc": ORIGINAL + timedelta(days=10)},
            (ChangeKind.TIME_MOVED,),
        ),
        (
            EventStatus.POSTPONED,
            {"status": EventStatus.SCHEDULED, "start_utc": ORIGINAL + timedelta(days=60)},
            (ChangeKind.SUPERSEDED,),
        ),
        (EventStatus.POSTPONED, {"status": EventStatus.CANCELLED}, (ChangeKind.CANCELLED,)),
    ],
    ids=[
        "uncancelled",
        "uncancelled-to-postponed",
        "postponed-back-same-date",
        "postponed-to-new-date",
        "postponed-far-out",
        "postponed-then-cancelled",
    ],
)
def test_classify_change_status_transitions(stored_status, incoming, expected):
    assert kinds(stored=replace(STORED, status=stored_status), **incoming) == expected


def test_classify_change_zone_alias_is_no_change():
    assert kinds(start_time_tz="US/Eastern") is None


def test_classify_change_real_zone_change_is_still_a_change():
    assert kinds(start_time_tz="America/Toronto") == (ChangeKind.DETAIL_CHANGED,)


def test_classify_change_lifecycle_flag():
    title_only = classify_change(STORED, replace(STORED, title="New"), ORIGINAL)
    tz_only = classify_change(STORED, replace(STORED, start_time_tz="America/Toronto"), ORIGINAL)

    assert title_only.is_lifecycle is False
    assert tz_only.is_lifecycle is True


@pytest.mark.parametrize("side", ["stored", "incoming"])
def test_classify_change_rejects_superseded_events(side):
    superseded = replace(STORED, status=EventStatus.SUPERSEDED)
    stored, incoming = (superseded, STORED) if side == "stored" else (STORED, superseded)

    with pytest.raises(ValueError):
        classify_change(stored, incoming, ORIGINAL)


def test_precedence_order():
    assert PRECEDENCE == (
        ChangeKind.CANCELLED,
        ChangeKind.SUPERSEDED,
        ChangeKind.REINSTATED,
        ChangeKind.POSTPONED,
        ChangeKind.TIME_MOVED,
        ChangeKind.SOLD_OUT,
        ChangeKind.DETAIL_CHANGED,
    )


def test_lifecycle_facts_are_event_facts_fields():
    assert LIFECYCLE_FACTS <= set(EventFacts.__dataclass_fields__)
    assert NOT_YET_STORED == frozenset()  # reinstated is stored since run-eventpulse24-015
