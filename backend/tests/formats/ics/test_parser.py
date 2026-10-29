"""The shared ICS parser: the format's own facts, with no identity policy.

These are the tests for `formats.ics.parser`. The **catalog's** view of the same file —
the identity decision, the derived ids, the URL resolved against a source base — is pinned
separately in `tests/ingestion/parsers/test_ics.py`, so the two paths are proven
independently and neither can drift.

The properties pinned here are the ones the format layer exists to provide:

- times are handed over **as written** — never converted, never resolved;
- a Windows `TZID` becomes an IANA zone name, and the time stays a wall clock;
- an all-day event is a date, and its span is exclusive at the end;
- recurrence is **never expanded**, and the parser says which kind of event it read;
- one malformed VEVENT never stops the rest, and the whole file's counts are exact.
"""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from formats.ics.parser import parse_ics

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "sources"


def wall(text: str) -> datetime:
    return datetime.fromisoformat(text)


def calendar(*events: str) -> bytes:
    body = "".join(f"BEGIN:VEVENT\r\n{event}\r\nEND:VEVENT\r\n" for event in events)
    return f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\n{body}END:VCALENDAR\r\n".encode()


@pytest.fixture(scope="module")
def parsed():
    result = parse_ics((FIXTURES / "calendar.ics").read_bytes())
    return result, {e.title: e for e in result.events}


# ─── The file ──────────────────────────────────────────────────────────────────


def test_the_calendar_fixture_is_read(parsed):
    result, _ = parsed

    # 10 VEVENTs: one has no start, and the first-week override is its own event.
    assert len(result.events) == 9
    assert dict(result.skipped) == {"no_event_start": 1}
    assert result.error is None


def test_a_malformed_calendar_is_an_error_not_an_exception():
    for content in ((FIXTURES / "broken.ics").read_bytes(), b"", b"\x00\xff garbage"):
        result = parse_ics(content)

        assert (result.events, result.error) == ([], "invalid_ics")


# ─── Times, as written ────────────────────────────────────────────────────────


def test_a_windows_tzid_is_a_wall_clock_with_an_iana_zone(parsed):
    event = parsed[1]["Library Book Club"]

    assert event.start == wall("2026-11-05T19:30") and event.start.tzinfo is None
    assert event.start_zone == "America/New_York"
    assert event.end == wall("2026-11-05T21:00")  # DTEND 02:00Z read in the start's zone
    assert event.raw["DTSTART"] == "TZID=Eastern Standard Time:20261105T193000"
    assert event.raw["DTEND"] == "20261106T020000Z"


def test_the_start_instant_is_the_aware_value_the_file_wrote(parsed):
    """The instant is not `start`: `start` is a wall clock, this is the moment it names.

    `icalendar` resolves a TZID time through the file's own VTIMEZONE, so this is the
    real instant — and it is what an override's RECURRENCE-ID is compared against.
    """
    event = parsed[1]["Library Book Club"]

    assert event.start_instant is not None
    assert event.start_instant.tzinfo is not None
    assert event.start_instant.astimezone(UTC) == datetime(2026, 11, 6, 0, 30, tzinfo=UTC)


def test_a_utc_time_stays_aware(parsed):
    event = parsed[1]["Global Webinar"]

    assert event.start == datetime(2026, 11, 7, 15, 0, tzinfo=UTC)
    assert event.start_zone is None
    assert event.end == datetime(2026, 11, 7, 16, 30, tzinfo=UTC)


def test_a_floating_time_stays_naive_without_a_zone(parsed):
    event = parsed[1]["Floating Yoga"]

    assert (event.start, event.end, event.start_zone) == (
        wall("2026-11-08T09:00"),
        wall("2026-11-08T10:00"),
        None,
    )


def test_a_floating_time_has_no_instant(parsed):
    """A wall clock with no zone denotes no moment, so it has no instant."""
    event = parsed[1]["Floating Yoga"]

    assert event.start_instant is None


def test_an_all_day_event_is_a_date_with_an_exclusive_end(parsed):
    event = parsed[1]["Harvest Fair"]

    assert event.all_day
    assert (event.start, event.end) == (wall("2026-11-14T00:00"), wall("2026-11-16T00:00"))
    assert event.start_instant == datetime(2026, 11, 14, tzinfo=UTC)


def test_a_cancelled_status_is_read(parsed):
    assert parsed[1]["Cancelled Concert"].status == "CANCELLED"


def test_an_ordinary_status_is_empty(parsed):
    assert parsed[1]["Library Book Club"].status == ""


# ─── Recurrence: never expanded, but always identified ─────────────────────────


def test_a_master_is_not_expanded(parsed):
    """An RRULE master is one event for its own DTSTART. No instances are generated."""
    masters = [e for e in parsed[0].events if e.has_rrule]

    assert len(masters) == 1
    assert masters[0].uid == "weekly@calendar.example.test"
    assert masters[0].recurrence_id is None


def test_an_override_carries_its_recurrence_id(parsed):
    override = parsed[1]["Weekly Run Club (late start)"]

    assert override.recurrence_id is not None
    assert override.has_rrule is False
    assert override.raw["RECURRENCE-ID"].startswith("TZID=Eastern Standard Time:")


def test_a_master_and_its_override_have_the_same_instance_instant(parsed):
    """They must, or the override would not replace the master but duplicate it."""
    master = next(e for e in parsed[0].events if e.has_rrule)
    override = parsed[1]["Weekly Run Club (first week moved indoors)"]

    assert master.start_instant == override.recurrence_id


def test_a_plain_event_has_neither_a_rule_nor_a_recurrence_id(parsed):
    event = parsed[1]["Library Book Club"]

    assert (event.has_rrule, event.recurrence_id) == (False, None)


# ─── The other facts ──────────────────────────────────────────────────────────


def test_the_location_and_description_are_read(parsed):
    event = parsed[1]["Library Book Club"]

    assert event.location == "Central Library"
    assert event.description == "Monthly book club."
    assert event.url == "https://calendar.example.test/book-club"


def test_the_url_is_kept_as_written(parsed):
    """The parser does not resolve a URL: only the catalog has a base to resolve against."""
    event = parsed[1]["Library Book Club"]

    assert event.url.startswith("https://")


def test_a_url_is_not_resolved_against_anything():
    result = parse_ics(
        calendar("UID:u@x\r\nSUMMARY:U\r\nURL:/relative\r\nDTSTART:20261114T220000Z")
    )

    assert result.events[0].url == "/relative"


def test_an_event_without_a_uid_has_an_empty_uid():
    result = parse_ics(calendar("SUMMARY:No UID\r\nDTSTART:20261114T220000Z"))

    assert result.events[0].uid == ""


def test_an_event_without_a_summary_is_counted():
    result = parse_ics(calendar("UID:t@x\r\nDTSTART:20261114T220000Z"))

    assert dict(result.skipped) == {"no_title": 1}


def test_an_event_without_a_start_is_counted():
    result = parse_ics(calendar("UID:t@x\r\nSUMMARY:T"))

    assert dict(result.skipped) == {"no_event_start": 1}


# ─── The ends ──────────────────────────────────────────────────────────────────


def test_all_day_with_duration_and_without_end():
    result = parse_ics(
        calendar(
            "UID:a@x\r\nSUMMARY:Two Days\r\nDTSTART;VALUE=DATE:20261114\r\nDURATION:P2D",
            "UID:b@x\r\nSUMMARY:One Day\r\nDTSTART;VALUE=DATE:20261114",
        )
    )
    two, one = result.events

    assert two.end == wall("2026-11-16T00:00")
    assert one.end == wall("2026-11-15T00:00")


def test_an_overnight_floating_end_rolls_forward():
    result = parse_ics(
        calendar("UID:n@x\r\nSUMMARY:Night\r\nDTSTART:20261114T220000\r\nDTEND:20261114T020000")
    )

    assert result.events[0].end == wall("2026-11-15T02:00")


def test_an_end_that_cant_be_aligned_with_a_floating_start_is_dropped():
    result = parse_ics(
        calendar("UID:m@x\r\nSUMMARY:Mixed\r\nDTSTART:20261114T220000\r\nDTEND:20261115T020000Z")
    )

    assert result.events[0].end is None


def test_an_end_days_before_start_is_dropped_and_counted():
    result = parse_ics(
        calendar("UID:x@x\r\nSUMMARY:X\r\nDTSTART:20261114T220000\r\nDTEND:20261112T090000")
    )

    assert result.events[0].end is None and result.skipped["end_before_start"] == 1


# ─── The instance instants ─────────────────────────────────────────────────────


def test_an_all_day_recurrence_id_names_a_utc_midnight():
    """A date-only RECURRENCE-ID identifies its instance by the UTC midnight of that day."""
    from formats.ics.parser import _instance_utc

    assert _instance_utc(date(2026, 11, 14)) == datetime(2026, 11, 14, tzinfo=UTC)


def test_a_floating_recurrence_id_is_read_as_utc():
    """A floating RECURRENCE-ID denotes no moment, so it is read as UTC — for the id only."""
    from formats.ics.parser import _instance_utc

    floating = datetime(2026, 11, 14, 22, 0)  # noqa: DTZ001 — a floating wall clock, deliberately

    assert _instance_utc(floating) == datetime(2026, 11, 14, 22, 0, tzinfo=UTC)


def test_an_aware_recurrence_id_is_converted_to_utc():
    from datetime import timedelta, timezone

    from formats.ics.parser import _instance_utc

    aware = datetime(2026, 11, 14, 22, 0, tzinfo=timezone(timedelta(hours=2)))

    assert _instance_utc(aware) == datetime(2026, 11, 14, 20, 0, tzinfo=UTC)


def test_a_value_that_is_neither_a_date_nor_a_datetime_has_no_instant():
    """A `RECURRENCE-ID` the parser cannot read names no moment."""
    from formats.ics.parser import _instant_of

    assert _instant_of("not a time") is None


EST_VTIMEZONE = (
    (FIXTURES / "calendar.ics").read_text().split("BEGIN:VEVENT")[0].split("VERSION:2.0\n", 1)[1]
)


def zoned_calendar(*events: str) -> bytes:
    body = "".join(f"BEGIN:VEVENT\n{event}\nEND:VEVENT\n" for event in events)
    return f"BEGIN:VCALENDAR\nVERSION:2.0\n{EST_VTIMEZONE}{body}END:VCALENDAR\n".encode()


@pytest.mark.parametrize(
    ("dtstart", "dtend", "expected_end"),
    [
        # TZID start, floating end: already a wall clock in the same frame.
        (
            "DTSTART;TZID=Eastern Standard Time:20261105T193000",
            "DTEND:20261105T210000",
            wall("2026-11-05T21:00"),
        ),
        # TZID start, date-only end: can't be placed.
        ("DTSTART;TZID=Eastern Standard Time:20261105T193000", "DTEND;VALUE=DATE:20261106", None),
        # UTC start, TZID end: converted to UTC.
        (
            "DTSTART:20261106T003000Z",
            "DTEND;TZID=Eastern Standard Time:20261105T210000",
            datetime(2026, 11, 6, 2, 0, tzinfo=UTC),
        ),
        # UTC start, floating end: can't be placed.
        ("DTSTART:20261106T003000Z", "DTEND:20261105T210000", None),
    ],
    ids=["tzid-floating", "tzid-date", "utc-tzid", "utc-floating"],
)
def test_an_end_is_aligned_to_the_start_representation(dtstart, dtend, expected_end):
    result = parse_ics(zoned_calendar(f"UID:e@x\nSUMMARY:E\n{dtstart}\n{dtend}"))

    assert result.events[0].end == expected_end


# ─── The limits ────────────────────────────────────────────────────────────────


def test_one_unreadable_event_doesnt_stop_the_rest(monkeypatch):
    """One VEVENT the parser cannot read is counted, and the rest of the file is read."""
    from formats.ics import parser as ics_parser

    real = ics_parser._event
    calls = iter([RuntimeError("boom"), None])

    def flaky(event, result):
        outcome = next(calls)
        if outcome:
            raise outcome
        real(event, result)

    monkeypatch.setattr(ics_parser, "_event", flaky)
    result = parse_ics(
        calendar(
            "UID:1@x\r\nSUMMARY:A\r\nDTSTART:20261114T220000Z",
            "UID:2@x\r\nSUMMARY:B\r\nDTSTART:20261114T230000Z",
        )
    )

    assert [e.title for e in result.events] == ["B"]
    assert dict(result.skipped) == {"unreadable_event": 1}


def test_the_item_cap(monkeypatch):
    monkeypatch.setattr("formats.ics.parser.MAX_EVENTS", 1)
    result = parse_ics(
        calendar(
            "UID:1@x\r\nSUMMARY:A\r\nDTSTART:20261114T220000Z",
            "UID:2@x\r\nSUMMARY:B\r\nDTSTART:20261114T230000Z",
        )
    )

    assert len(result.events) == 1 and result.skipped["too_many_items"] == 1
