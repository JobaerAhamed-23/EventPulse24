"""The exported ICS, read back by this project's own iCalendar parser (FR-52).

**What this proves, and what it does not.** The acceptance criterion asks that the export
*"imports cleanly into Google Calendar / Apple Calendar / Outlook"*, and none of those can
be run here. What can be proved is that the file this project **emits** is accepted by the
RFC 5545 parser this project already **ships** — `formats/ics/parser.py`, built on the
`icalendar` library, and the same code path that reads a user's subscribed calendar feed.

That is a real test of a real round trip, and it is weaker than the criterion as written.
The test report says so rather than implying three clients were checked.

The structural requirements those three clients actually disagree about are asserted
directly: `UID` and `DTSTAMP` on every event, `CRLF` line endings, `VERSION` and `PRODID` on
the calendar, no content line over 75 octets, and no invented `DTEND`.
"""

from datetime import UTC, datetime, timedelta

import pytest

from apps.identity.services.export_serializer import build_ics
from formats.ics.parser import parse_ics
from shared.db import PERSONAL
from shared.ids import uuid7
from tests.personalization.factories import PersonalEventFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
EVENING = datetime(2026, 11, 20, 3, 30, tzinfo=UTC)


def one_event(**overrides) -> dict:
    return {
        "uid": f"personal-{uuid7()}@eventpulse24",
        "summary": "Jazz at the Fillmore",
        "start": EVENING,
        "end": EVENING + timedelta(hours=2),
        "location": "The Fillmore, SF",
        **overrides,
    }


def parsed(events):
    result = parse_ics(build_ics(events=events, generated_at=NOW).encode("utf-8"))
    return result


# ── The round trip ─────────────────────────────────────────────────────────────────


def test_an_exported_event_is_read_back_by_this_projects_own_parser():
    """The whole point: what we write, we can read."""
    source = one_event()

    result = parsed([source])

    assert len(result.events) == 1
    event = result.events[0]
    assert event.title == "Jazz at the Fillmore"
    assert event.location == "The Fillmore, SF"


def test_the_times_survive_the_round_trip_unmoved():
    """**The failure that would matter most**: a shifted evening. The export writes UTC
    with a `Z`, so the instant that comes back is the instant that went in."""
    source = one_event()

    event = parsed([source]).events[0]

    assert event.start_instant == EVENING
    assert event.end is not None


def test_a_whole_week_round_trips():
    sources = [one_event(summary=f"Event {n}", start=EVENING + timedelta(days=n)) for n in range(7)]

    result = parsed(sources)

    assert len(result.events) == 7
    assert [event.title for event in result.events] == [f"Event {n}" for n in range(7)]


def test_an_event_with_no_end_does_not_gain_one():
    """**No invented `DTEND`.** A calendar that guessed an hour would be putting a time in
    the user's calendar that nobody ever said."""
    source = one_event(end=None)

    ics = build_ics(events=[source], generated_at=NOW)

    assert "DTEND" not in ics


def test_an_empty_calendar_is_still_a_valid_file():
    """A new account exports a calendar with no events — which is an answer, not an error."""
    result = parsed([])

    assert result.events == []


# ── The structure the three clients disagree about ─────────────────────────────────


def test_every_event_carries_a_uid_and_a_dtstamp():
    """RFC 5545 requires both, and the clients enforce them unevenly — a file without them
    imports into some and silently fails in others."""
    ics = build_ics(events=[one_event(), one_event()], generated_at=NOW)

    assert ics.count("UID:") == 2
    assert ics.count("DTSTAMP:") == 2


def test_the_calendar_names_its_version_and_producer():
    ics = build_ics(events=[one_event()], generated_at=NOW)

    assert "VERSION:2.0" in ics
    assert "PRODID:-//EventPulse24//Data Export//EN" in ics


def test_the_lines_end_in_crlf():
    """RFC 5545 §3.1, and the strictest importers mean it."""
    ics = build_ics(events=[one_event()], generated_at=NOW)

    assert "\r\n" in ics
    assert ics.endswith("\r\n")
    # No bare LF anywhere: every newline is part of a CRLF pair.
    assert ics.replace("\r\n", "").count("\n") == 0


def test_no_content_line_exceeds_seventy_five_octets():
    """Folding is not tidiness — an over-long line is exactly what one client accepts and
    another rejects."""
    long_title = "A very long event title that keeps going " * 4
    ics = build_ics(events=[one_event(summary=long_title)], generated_at=NOW)

    for line in ics.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75, f"unfolded line: {line[:90]}…"


def test_a_folded_title_still_round_trips():
    """The fold has to be reversible, or the test above would be satisfied by corruption."""
    long_title = "Jazz " * 30

    event = parsed([one_event(summary=long_title.strip())]).events[0]

    assert event.title == long_title.strip()


@pytest.mark.parametrize("hostile", ["Comma, here", "Semi; colon", "Back\\slash"])
def test_structural_characters_are_escaped_and_survive(hostile):
    """RFC 5545 §3.3.11: a comma in a summary is structural, and an unescaped one splits
    the value into two."""
    event = parsed([one_event(summary=hostile)]).events[0]

    assert event.title == hostile


def test_a_redacted_location_appears_as_text_not_as_a_missing_field():
    """The opt-out withholds the value; it does not corrupt the file."""
    event = parsed([one_event(location="[redacted]")]).events[0]

    assert event.location == "[redacted]"


def test_an_event_with_no_location_omits_the_property():
    ics = build_ics(events=[one_event(location="")], generated_at=NOW)

    assert "LOCATION" not in ics


# ── The real records, end to end ───────────────────────────────────────────────────


def test_a_users_personal_events_reach_the_calendar_file():
    """From the database through `personalization`'s published read and back out of the
    parser — the path the worker actually runs."""
    from apps.personalization.services.export_source import dated_records_for

    user_id = uuid7()
    PersonalEventFactory(
        user_id=user_id, name="Dentist", start_utc=EVENING, end_utc=EVENING + timedelta(hours=1)
    )

    records = list(dated_records_for(user_id=user_id, redact_location=False))
    result = parsed(records)

    assert [event.title for event in result.events] == ["Dentist"]


def test_a_redacting_user_gets_their_events_without_their_addresses():
    from apps.personalization.services.export_source import dated_records_for

    user_id = uuid7()
    PersonalEventFactory(
        user_id=user_id,
        name="Dentist",
        start_utc=EVENING,
        end_utc=EVENING + timedelta(hours=1),
        location="21 Harley St",
    )

    records = list(dated_records_for(user_id=user_id, redact_location=True))
    event = parsed(records).events[0]

    assert event.title == "Dentist"
    assert "21 Harley St" not in event.location
