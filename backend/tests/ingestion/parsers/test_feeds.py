"""RSS 2.0 / Atom parser (FR-56): explicit event times only, untrusted XML refused safely."""

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest

from apps.ingestion.parsers.feeds import parse_feed
from apps.ingestion.parsers.types import SourceContext

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "sources"
CONTEXT = SourceContext(UUID(int=7), "https://community.example.test/feed.xml")
EST = timezone(timedelta(hours=-5))


def wall(text: str) -> datetime:
    return datetime.fromisoformat(text)


def parse_file(name: str):
    return parse_feed((FIXTURES / name).read_bytes(), CONTEXT)


def rss(*items: str, namespaces='xmlns:ev="http://purl.org/rss/1.0/modules/event/"') -> bytes:
    body = "".join(f"<item>{item}</item>" for item in items)
    return (
        f'<rss version="2.0" {namespaces}><channel><title>T</title>{body}</channel></rss>'.encode()
    )


def test_rss_with_the_event_module():
    result = parse_file("events.rss")
    by_title = {c.title: c for c in result.candidates}

    assert sorted(by_title) == ["Board Game Meetup", "Choir Rehearsal", "Mystery Time Event"]
    assert dict(result.skipped) == {"no_event_start": 1, "unparseable_start": 1}

    meetup = by_title["Board Game Meetup"]
    assert meetup.source_event_id == "community-1"
    assert (meetup.start, meetup.end) == (
        datetime(2026, 11, 6, 18, 30, tzinfo=EST),
        datetime(2026, 11, 6, 21, 0, tzinfo=EST),
    )
    assert meetup.venue_name == "Park Slope Library"
    assert meetup.description == "Bring a game!"  # markup stripped, script content dropped

    choir = by_title["Choir Rehearsal"]
    assert choir.start == wall("2026-11-09T19:00") and choir.start.tzinfo is None
    assert choir.canonical_url == "https://community.example.test/events/2"
    assert choir.source_event_id.startswith("derived:")

    mystery = by_title["Mystery Time Event"]
    assert (mystery.venue_name, mystery.start_zone) == ("", None)


def test_pub_date_is_never_an_event_start():
    result = parse_feed(
        rss("<title>News</title><pubDate>Wed, 04 Nov 2026 10:00:00 GMT</pubDate>"), CONTEXT
    )

    assert result.candidates == [] and dict(result.skipped) == {"no_event_start": 1}


def test_atom_with_xcal():
    result = parse_file("events.atom")
    [c] = result.candidates

    assert dict(result.skipped) == {"no_event_start": 1}
    assert c.source_event_id == "urn:uuid:meetup-1"
    assert c.canonical_url == "https://meetups.example.test/python-night"
    assert (c.start, c.end) == (
        datetime(2026, 11, 18, 23, 30, tzinfo=UTC),
        datetime(2026, 11, 19, 2, 0, tzinfo=UTC),
    )
    assert (c.venue_name, c.description) == ("Civic Hall", "Talks and pizza")


def test_all_day_and_overnight_items():
    result = parse_feed(
        rss(
            "<title>Fair</title><guid>a</guid><ev:startdate>2026-11-14</ev:startdate>",
            "<title>Late</title><guid>b</guid><ev:startdate>2026-11-14T22:00:00</ev:startdate>"
            "<ev:enddate>2026-11-14T01:00:00</ev:enddate>",
        ),
        CONTEXT,
    )
    fair, late = result.candidates

    assert fair.all_day and (fair.start, fair.end) == (
        wall("2026-11-14T00:00"),
        wall("2026-11-15T00:00"),
    )
    assert late.end == wall("2026-11-15T01:00")


def test_reused_guid_keeps_the_first_item():
    result = parse_feed(
        rss(
            "<title>A</title><guid>dup</guid><ev:startdate>2026-11-14T10:00:00</ev:startdate>",
            "<title>B</title><guid>dup</guid><ev:startdate>2026-11-15T10:00:00</ev:startdate>",
        ),
        CONTEXT,
    )

    assert [c.title for c in result.candidates] == ["A"]
    assert result.skipped["duplicate_id"] == 1


def test_item_without_a_title_is_counted():
    result = parse_feed(
        rss("<guid>x</guid><ev:startdate>2026-11-14T10:00:00</ev:startdate>"), CONTEXT
    )

    assert dict(result.skipped) == {"no_title": 1}


@pytest.mark.parametrize(
    ("content", "error"),
    [
        ((FIXTURES / "broken.rss").read_bytes(), "invalid_xml"),
        (b"", "invalid_xml"),
        (b"<html><body>not a feed</body></html>", "not_a_feed"),
        (
            b'<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;">'
            b'<!ENTITY c "&b;&b;&b;&b;">]><rss>&c;</rss>',
            "forbidden_xml",
        ),
        (
            b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
            b"<rss><channel><item><title>&x;</title></item></channel></rss>",
            "forbidden_xml",
        ),
    ],
    ids=["truncated", "empty", "not-a-feed", "billion-laughs", "external-entity"],
)
def test_unreadable_or_hostile_documents_return_an_error(content, error):
    result = parse_feed(content, CONTEXT)

    assert (result.candidates, result.error) == ([], error)


def test_legacy_netscape_dtd_reference_is_accepted_without_fetching():
    content = (
        b'<?xml version="1.0"?><!DOCTYPE rss PUBLIC "-//Netscape Communications//DTD RSS 0.91//EN"'
        b' "http://my.netscape.com/publish/formats/rss-0.91.dtd"><rss version="0.91"><channel>'
        b"<title>Old</title></channel></rss>"
    )

    assert parse_feed(content, CONTEXT).error is None


def test_rss_without_a_channel_yields_nothing():
    result = parse_feed(b'<rss version="2.0"></rss>', CONTEXT)

    assert (result.candidates, result.error) == ([], None)


def test_item_cap(monkeypatch):
    monkeypatch.setattr("apps.ingestion.parsers.types.MAX_ITEMS", 2)
    items = [
        f"<title>E{n}</title><guid>{n}</guid><ev:startdate>2026-11-14T10:00:00</ev:startdate>"
        for n in range(4)
    ]

    result = parse_feed(rss(*items), CONTEXT)

    assert len(result.candidates) == 2 and result.skipped["too_many_items"] == 2


def test_atom_entry_without_an_alternate_link_has_no_url():
    content = (
        b'<feed xmlns="http://www.w3.org/2005/Atom" xmlns:xcal="urn:ietf:params:xml:ns:xcal">'
        b'<entry><title>T</title><id>i</id><link rel="self" href="https://a.test/self"/>'
        b"<xcal:dtstart>2026-11-18T23:30:00Z</xcal:dtstart></entry></feed>"
    )

    assert parse_feed(content, CONTEXT).candidates[0].canonical_url == ""


def test_date_only_end_on_a_timed_start_is_dropped_and_impossible_end_counted():
    result = parse_feed(
        rss(
            "<title>A</title><guid>a</guid><ev:startdate>2026-11-14T10:00:00</ev:startdate>"
            "<ev:enddate>2026-11-15</ev:enddate>",
            "<title>B</title><guid>b</guid><ev:startdate>2026-11-14T10:00:00</ev:startdate>"
            "<ev:enddate>2026-11-10T10:00:00</ev:enddate>",
        ),
        CONTEXT,
    )

    assert [c.end for c in result.candidates] == [None, None]
    assert result.skipped["end_before_start"] == 1
