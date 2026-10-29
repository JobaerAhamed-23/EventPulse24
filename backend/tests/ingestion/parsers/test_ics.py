"""The catalog's view of an ICS file: `ParsedCandidate`s.

These are the tests for `apps.ingestion.parsers.ics`. The **format's** view of the same
file — the times as written, the zones, the all-day spans — is pinned separately in
`tests/formats/ics/test_parser.py`, so the two paths are proven independently and
neither can drift.

The properties pinned here are the ones the *catalog* adds on top of the format:

- the identity decision: a UID keyed as-is, a series instance keyed by `ics_item_id`;
- the URL resolved against the source's base;
- the status hint, the venue name, the series id;
- the shared parser's skip counts reported under the catalog's own reasons.
"""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from apps.ingestion.parsers.ics import parse_ics
from apps.ingestion.parsers.types import SourceContext, StatusHint
from domain.dedup import ics_item_id
from shared.ids import series_id

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "sources"
SOURCE = UUID(int=7)
CONTEXT = SourceContext(SOURCE, "https://calendar.example.test/cal.ics")
UID_WEEKLY = "weekly@calendar.example.test"


def wall(text: str) -> datetime:
    return datetime.fromisoformat(text)


def calendar(*events: str) -> bytes:
    body = "".join(f"BEGIN:VEVENT\r\n{event}\r\nEND:VEVENT\r\n" for event in events)
    return f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\n{body}END:VCALENDAR\r\n".encode()


@pytest.fixture(scope="module")
def parsed():
    result = parse_ics((FIXTURES / "calendar.ics").read_bytes(), CONTEXT)
    return result, {c.title: c for c in result.candidates}


def test_calendar_fixture_counts(parsed):
    result, _ = parsed

    # 10 VEVENTs: one has no start, and the first-week override replaces its master's instance.
    assert len(result.candidates) == 8
    assert dict(result.skipped) == {"no_event_start": 1}
    assert result.error is None


def test_windows_tzid_is_a_wall_clock_with_an_iana_zone_and_aligned_utc_end(parsed):
    c = parsed[1]["Library Book Club"]

    assert c.start == wall("2026-11-05T19:30") and c.start.tzinfo is None
    assert c.start_zone == "America/New_York"
    assert c.end == wall("2026-11-05T21:00")  # DTEND 02:00Z read in the start's zone
    assert c.start_raw == "TZID=Eastern Standard Time:20261105T193000"
    assert c.raw["DTEND"] == "20261106T020000Z"
    assert (c.source_event_id, c.venue_name) == (
        "windows-tz@calendar.example.test",
        "Central Library",
    )
    assert c.description == "Monthly book club."
    assert c.canonical_url == "https://calendar.example.test/book-club"


def test_utc_time_stays_aware_and_duration_sets_the_end(parsed):
    c = parsed[1]["Global Webinar"]

    assert c.start == datetime(2026, 11, 7, 15, 0, tzinfo=UTC) and c.start_zone is None
    assert c.end == datetime(2026, 11, 7, 16, 30, tzinfo=UTC)


def test_floating_time_stays_naive_without_a_zone(parsed):
    c = parsed[1]["Floating Yoga"]

    assert (c.start, c.end, c.start_zone) == (
        wall("2026-11-08T09:00"),
        wall("2026-11-08T10:00"),
        None,
    )


def test_all_day_event_with_an_exclusive_end(parsed):
    c = parsed[1]["Harvest Fair"]

    assert c.all_day
    assert (c.start, c.end) == (wall("2026-11-14T00:00"), wall("2026-11-16T00:00"))


def test_cancelled_status(parsed):
    assert parsed[1]["Cancelled Concert"].status is StatusHint.CANCELLED


def test_an_ordinary_status_is_scheduled(parsed):
    assert parsed[1]["Library Book Club"].status is StatusHint.SCHEDULED


def test_series_overrides_share_a_series_and_key_instances_by_utc_start(parsed):
    result, by_title = parsed
    series = [c for c in result.candidates if c.title.startswith("Weekly Run Club")]
    moved = by_title["Weekly Run Club (late start)"]
    first_override = by_title["Weekly Run Club (first week moved indoors)"]

    assert len(series) == 2 and "Weekly Run Club" not in by_title
    assert {c.series_id for c in series} == {series_id(SOURCE, UID_WEEKLY)}
    # The override of the master's own instance (19:00 EST Nov 3 = 00:00Z Nov 4) replaced it.
    assert first_override.source_event_id == ics_item_id(
        UID_WEEKLY, datetime(2026, 11, 4, tzinfo=UTC)
    )
    assert moved.source_event_id == ics_item_id(UID_WEEKLY, datetime(2026, 11, 11, tzinfo=UTC))
    assert moved.start == wall("2026-11-10T20:00")  # the moved time, as written


def test_a_plain_event_has_no_series_id(parsed):
    assert parsed[1]["Library Book Club"].series_id is None


def test_a_floating_series_master_is_read_and_keyed_as_utc():
    """A floating time names no moment, but the master still needs an id.

    The instance key falls back to the wall clock read as UTC — the same reading a
    floating RECURRENCE-ID gets — so the event is imported rather than dropped.
    """
    result = parse_ics(
        calendar(
            "UID:f@x\r\nSUMMARY:Floating series\r\nDTSTART:20261103T190000\r\nRRULE:FREQ=WEEKLY"
        ),
        CONTEXT,
    )

    [candidate] = result.candidates
    assert candidate.source_event_id == ics_item_id("f@x", datetime(2026, 11, 3, 19, tzinfo=UTC))
    assert candidate.series_id is not None
    assert dict(result.skipped) == {}


def test_a_recurrence_instance_that_names_no_day_is_refused():
    """The instance key needs a date or a datetime; anything else is a broken event."""
    from apps.ingestion.parsers.ics import _instance_utc

    with pytest.raises(TypeError):
        _instance_utc("not a time")


@pytest.mark.parametrize("override_first", [True, False])
def test_override_wins_over_its_master_in_either_file_order(override_first):
    master = "UID:w@x\r\nSUMMARY:Run Club\r\nDTSTART:20261103T190000Z\r\nRRULE:FREQ=WEEKLY"
    override = (
        "UID:w@x\r\nRECURRENCE-ID:20261103T190000Z\r\nSUMMARY:Moved indoors\r\n"
        "DTSTART:20261103T190000Z"
    )
    events = (override, master) if override_first else (master, override)

    result = parse_ics(calendar(*events), CONTEXT)

    assert [c.title for c in result.candidates] == ["Moved indoors"]
    assert "duplicate_id" not in result.skipped


def test_reused_uid_without_recurrence_keeps_the_first_and_counts_the_rest():
    result = parse_ics(
        calendar(
            "UID:same@x\r\nSUMMARY:First\r\nDTSTART:20261103T190000Z",
            "UID:same@x\r\nSUMMARY:Second\r\nDTSTART:20261104T190000Z",
        ),
        CONTEXT,
    )

    assert [c.title for c in result.candidates] == ["First"]
    assert result.skipped["duplicate_id"] == 1


def test_event_without_uid_gets_a_derived_id(parsed):
    assert parsed[1]["No UID Here"].source_event_id.startswith("derived:")


def test_a_relative_url_is_resolved_against_the_source_url():
    result = parse_ics(
        calendar("UID:u@x\r\nSUMMARY:U\r\nURL:/relative\r\nDTSTART:20261114T220000Z"),
        CONTEXT,
    )

    assert result.candidates[0].canonical_url == "https://calendar.example.test/relative"


def test_a_non_http_url_is_dropped():
    result = parse_ics(
        calendar("UID:u@x\r\nSUMMARY:U\r\nURL:javascript:alert(1)\r\nDTSTART:20261114T220000Z"),
        CONTEXT,
    )

    assert result.candidates[0].canonical_url == ""


@pytest.mark.parametrize(
    "content", [(FIXTURES / "broken.ics").read_bytes(), b"", b"\x00\xff garbage"]
)
def test_malformed_calendar_returns_an_error(content):
    result = parse_ics(content, CONTEXT)

    assert (result.candidates, result.error) == ([], "invalid_ics")


def test_floating_recurrence_id_is_keyed_as_utc_for_the_id_only():
    result = parse_ics(
        calendar(
            "UID:float@x\r\nSUMMARY:F\r\nRECURRENCE-ID:20261110T190000\r\nDTSTART:20261110T200000"
        ),
        CONTEXT,
    )
    [c] = result.candidates

    assert c.source_event_id == ics_item_id("float@x", datetime(2026, 11, 10, 19, tzinfo=UTC))
    assert c.start == wall("2026-11-10T20:00")


def test_all_day_with_duration_and_without_end():
    result = parse_ics(
        calendar(
            "UID:a@x\r\nSUMMARY:Two Days\r\nDTSTART;VALUE=DATE:20261114\r\nDURATION:P2D",
            "UID:b@x\r\nSUMMARY:One Day\r\nDTSTART;VALUE=DATE:20261114",
        ),
        CONTEXT,
    )
    two, one = result.candidates

    assert two.end == wall("2026-11-16T00:00")
    assert one.end == wall("2026-11-15T00:00")


def test_overnight_floating_end_rolls_forward():
    result = parse_ics(
        calendar("UID:n@x\r\nSUMMARY:Night\r\nDTSTART:20261114T220000\r\nDTEND:20261114T020000"),
        CONTEXT,
    )

    assert result.candidates[0].end == wall("2026-11-15T02:00")


def test_end_that_cant_be_aligned_with_a_floating_start_is_dropped():
    result = parse_ics(
        calendar("UID:m@x\r\nSUMMARY:Mixed\r\nDTSTART:20261114T220000\r\nDTEND:20261115T020000Z"),
        CONTEXT,
    )

    assert result.candidates[0].end is None


def test_event_without_summary_is_counted():
    result = parse_ics(calendar("UID:t@x\r\nDTSTART:20261114T220000Z"), CONTEXT)

    assert dict(result.skipped) == {"no_title": 1}


def test_an_event_without_a_start_is_counted():
    result = parse_ics(calendar("UID:t@x\r\nSUMMARY:T"), CONTEXT)

    assert dict(result.skipped) == {"no_event_start": 1}


def test_one_unreadable_event_doesnt_stop_the_rest(monkeypatch):
    """One candidate the catalog cannot build is counted, and the rest of the file is read."""
    from apps.ingestion.parsers import ics

    real = ics._candidate
    calls = iter([RuntimeError("boom"), None])

    def flaky(event, context):
        outcome = next(calls)
        if outcome:
            raise outcome
        return real(event, context)

    monkeypatch.setattr(ics, "_candidate", flaky)
    result = parse_ics(
        calendar(
            "UID:1@x\r\nSUMMARY:A\r\nDTSTART:20261114T220000Z",
            "UID:2@x\r\nSUMMARY:B\r\nDTSTART:20261114T230000Z",
        ),
        CONTEXT,
    )

    assert [c.title for c in result.candidates] == ["B"]
    assert dict(result.skipped) == {"unreadable_event": 1}


def test_item_cap(monkeypatch):
    monkeypatch.setattr("apps.ingestion.parsers.types.MAX_ITEMS", 1)
    result = parse_ics(
        calendar(
            "UID:1@x\r\nSUMMARY:A\r\nDTSTART:20261114T220000Z",
            "UID:2@x\r\nSUMMARY:B\r\nDTSTART:20261114T230000Z",
        ),
        CONTEXT,
    )

    assert len(result.candidates) == 1 and result.skipped["too_many_items"] == 1


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
def test_end_is_aligned_to_the_start_representation(dtstart, dtend, expected_end):
    result = parse_ics(zoned_calendar(f"UID:e@x\nSUMMARY:E\n{dtstart}\n{dtend}"), CONTEXT)

    assert result.candidates[0].end == expected_end


def test_all_day_recurrence_id_keys_the_instance_at_utc_midnight():
    result = parse_ics(
        calendar(
            "UID:fair@x\r\nSUMMARY:Fair\r\nRECURRENCE-ID;VALUE=DATE:20261121\r\n"
            "DTSTART;VALUE=DATE:20261121"
        ),
        CONTEXT,
    )

    assert result.candidates[0].source_event_id == ics_item_id(
        "fair@x", datetime(2026, 11, 21, tzinfo=UTC)
    )


def test_end_days_before_start_is_dropped_and_counted():
    result = parse_ics(
        calendar("UID:x@x\r\nSUMMARY:X\r\nDTSTART:20261114T220000\r\nDTEND:20261112T090000"),
        CONTEXT,
    )

    assert result.candidates[0].end is None and result.skipped["end_before_start"] == 1
