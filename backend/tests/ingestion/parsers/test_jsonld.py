"""JSON-LD parser (FR-14 structured path): fixtures field by field, plus edge cases."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest

from apps.ingestion.parsers.jsonld import EVENT_TYPES, parse_jsonld
from apps.ingestion.parsers.types import MAX_ITEMS, SourceContext, StatusHint
from shared.ids import series_id

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "sources"
SOURCE = UUID(int=7)
CONTEXT = SourceContext(SOURCE, "https://venue.example.test/calendar")
EST = timezone(timedelta(hours=-5))


def wall(text: str) -> datetime:
    """A naive wall-clock time, as a source without a zone writes it."""
    return datetime.fromisoformat(text)


def parse_file(name: str):
    return parse_jsonld((FIXTURES / name).read_bytes(), CONTEXT)


def parse_nodes(*nodes, wrap=lambda n: n):
    blocks = "".join(
        f'<script type="application/ld+json">{json.dumps(wrap(node))}</script>' for node in nodes
    )
    return parse_jsonld(f"<html><head>{blocks}</head></html>".encode(), CONTEXT)


def event(**fields):
    return {"@type": "Event", "name": "Show", "startDate": "2026-11-05T19:30:00", **fields}


@pytest.fixture(scope="module")
def venue():
    result = parse_file("venue-events.html")
    return result, {c.title: c for c in result.candidates}


def test_venue_page_yields_every_event_and_skips_the_bad_block(venue):
    result, by_title = venue

    assert len(result.candidates) == 7
    assert dict(result.skipped) == {"invalid_jsonld": 1}
    assert result.error is None
    assert "Not an event" not in by_title and "Not JSON-LD" not in by_title


def test_offset_event_kept_as_written_with_venue_offers_and_plain_description(venue):
    c = venue[1]["Japanese Breakfast"]

    assert c.source_event_id == "https://venue.example.test/e/101"
    assert c.start == datetime(2026, 11, 5, 19, 30, tzinfo=EST)
    assert c.end == datetime(2026, 11, 5, 23, 0, tzinfo=EST)
    assert c.start_raw == "2026-11-05T19:30:00-05:00" and c.start_zone is None
    assert (c.venue_name, c.venue_city, c.venue_country) == ("Brooklyn Bowl", "Brooklyn", "US")
    assert c.sold_out is True and c.status is StatusHint.SCHEDULED
    assert c.description == "With special guests & friends."
    assert c.raw == {
        "startDate": "2026-11-05T19:30:00-05:00",
        "endDate": "2026-11-05T23:00:00-05:00",
    }


def test_naive_event_without_id_gets_a_derived_id_relative_url_and_overnight_end(venue):
    c = venue[1]["Late Night Jazz"]

    assert c.source_event_id.startswith("derived:") and len(c.source_event_id) == 40
    assert c.canonical_url == "https://venue.example.test/e/102"
    assert c.start == wall("2026-11-12T22:00") and c.start.tzinfo is None
    assert c.end == wall("2026-11-13T02:00")  # 02:00 rolled to the next day
    assert c.venue_city == "Brooklyn, NY"  # a string address is kept as the locality


def test_cancelled_with_a_type_list_http_iri_and_string_location(venue):
    c = venue[1]["Cancelled Play"]

    assert c.status is StatusHint.CANCELLED
    assert c.venue_name == "Brooklyn Bowl"


def test_date_only_event_is_all_day_with_an_exclusive_end(venue):
    c = venue[1]["Weekend Fest"]

    assert c.all_day is True
    assert (c.start, c.end) == (wall("2026-11-20T00:00"), wall("2026-11-22T00:00"))
    assert c.venue_country == "US"  # from a Country node's name


def test_virtual_location_has_no_venue(venue):
    c = venue[1]["Online Talk"]

    assert (c.venue_name, c.venue_city) == ("", "")


def test_event_series_emits_sub_events_with_a_shared_series_id(venue):
    result, _ = venue
    trivia = [c for c in result.candidates if c.title == "Trivia Night"]

    assert [c.source_event_id for c in trivia] == [
        "https://venue.example.test/e/201",
        "https://venue.example.test/e/202",
    ]
    assert {c.series_id for c in trivia} == {
        series_id(SOURCE, "https://venue.example.test/series/trivia")
    }


def test_derived_ids_are_stable_across_parses():
    first, second = parse_file("venue-events.html"), parse_file("venue-events.html")

    assert [c.source_event_id for c in first.candidates] == [
        c.source_event_id for c in second.candidates
    ]


def test_document_with_only_broken_blocks_yields_nothing_but_no_error():
    result = parse_file("broken-jsonld.html")

    assert (result.candidates, dict(result.skipped), result.error) == (
        [],
        {"invalid_jsonld": 2},
        None,
    )


def test_hostile_document_is_sanitized():
    result = parse_file("hostile.html")
    [c] = result.candidates

    assert c.title.startswith("Totally Normal Show") and len(c.title) == 500
    assert "alert" not in c.title and "<" not in c.title
    assert c.canonical_url == ""  # javascript: dropped
    assert c.description == "Real text here"
    assert c.venue_name == "Hall"
    assert len(c.venue_city) == 100
    assert c.venue_country == ""  # "USA" isn't a 2-letter code


@pytest.mark.parametrize("kind", sorted(EVENT_TYPES))
def test_every_event_subtype_is_an_event(kind):
    assert len(parse_nodes(event(**{"@type": kind})).candidates) == 1


@pytest.mark.parametrize(
    ("status", "hint"),
    [
        ("https://schema.org/EventPostponed", StatusHint.POSTPONED),
        ("http://schema.org/EventCancelled", StatusHint.CANCELLED),
        ("EventCancelled", StatusHint.CANCELLED),
        ("https://schema.org/EventRescheduled", StatusHint.SCHEDULED),
        ("https://schema.org/EventMovedOnline", StatusHint.SCHEDULED),
        (None, StatusHint.SCHEDULED),
        (42, StatusHint.SCHEDULED),
    ],
)
def test_event_status_variants(status, hint):
    [c] = parse_nodes(event(eventStatus=status)).candidates

    assert c.status is hint


@pytest.mark.parametrize(
    ("offers", "sold_out"),
    [
        ({"availability": "https://schema.org/SoldOut"}, True),
        ([{"availability": "InStock"}, {"availability": "http://schema.org/SoldOut"}], True),
        ({"availability": "https://schema.org/InStock"}, False),
        ("free", False),
        (None, False),
    ],
)
def test_sold_out_from_offers(offers, sold_out):
    [c] = parse_nodes(event(offers=offers)).candidates

    assert c.sold_out is sold_out


def test_array_and_graph_containers_are_walked():
    result = parse_nodes(
        [event(name="A"), {"@graph": [event(name="B"), {"@graph": [event(name="C")]}]}]
    )

    assert sorted(c.title for c in result.candidates) == ["A", "B", "C"]


def test_location_list_skips_virtual_and_reads_place_timezone():
    location = [
        {"@type": "VirtualLocation", "url": "https://x.test/"},
        {"@type": "Place", "name": "Hall", "timezone": "America/Chicago"},
    ]

    [c] = parse_nodes(event(location=location)).candidates

    assert (c.venue_name, c.start_zone) == ("Hall", "America/Chicago")


@pytest.mark.parametrize(
    ("fields", "reason"),
    [
        ({"startDate": None}, "no_event_start"),
        ({"startDate": "soon"}, "unparseable_start"),
        ({"startDate": 20261105}, "unparseable_start"),
        ({"name": "<b></b>"}, "no_title"),
    ],
)
def test_unusable_events_are_counted_not_guessed(fields, reason):
    result = parse_nodes(event(**fields))

    assert result.candidates == [] and dict(result.skipped) == {reason: 1}


def test_date_only_end_on_a_timed_start_is_dropped():
    [c] = parse_nodes(event(endDate="2026-11-06")).candidates

    assert c.end is None


def test_end_more_than_a_day_before_start_is_dropped_and_counted():
    result = parse_nodes(event(startDate="2026-11-05T19:30:00", endDate="2026-11-03T10:00:00"))

    assert result.candidates[0].end is None and result.skipped["end_before_start"] == 1


def test_script_type_with_charset_suffix_is_read():
    html = '<script type="application/ld+json; charset=utf-8">' + json.dumps(event()) + "</script>"

    assert len(parse_jsonld(html.encode(), CONTEXT).candidates) == 1


def test_comment_wrapped_block_and_latin1_charset_are_read():
    block = "<!--" + json.dumps(event(name="Café")) + "-->"
    html = f'<meta charset="iso-8859-1"><script type="application/ld+json">{block}</script>'

    [c] = parse_jsonld(html.encode("latin-1"), CONTEXT).candidates

    assert c.title == "Café"


def test_item_cap(monkeypatch):
    monkeypatch.setattr("apps.ingestion.parsers.types.MAX_ITEMS", 3)
    result = parse_nodes([event(name=f"E{n}") for n in range(5)])

    assert len(result.candidates) == 3 and result.skipped["too_many_items"] == 2
    assert MAX_ITEMS == 5_000


@pytest.mark.parametrize("local_id", ["_:b0", "#event", "/e/1", "event-1"])
def test_document_local_ids_never_collide_two_events(local_id):
    result = parse_nodes(
        [
            event(**{"@id": local_id, "name": "A"}),
            event(**{"@id": local_id, "name": "B", "startDate": "2026-11-06T19:30:00"}),
        ]
    )

    ids = [c.source_event_id for c in result.candidates]
    assert len(ids) == 2 and len(set(ids)) == 2
    assert all(i.startswith("derived:") for i in ids)


def test_overlong_id_is_hashed_to_fit_the_column():
    [c] = parse_nodes(event(**{"@id": "https://venue.test/" + "x" * 1000})).candidates

    assert c.source_event_id.startswith("long:") and len(c.source_event_id) == 69


def test_same_absolute_id_twice_keeps_the_first():
    result = parse_nodes(
        [
            event(**{"@id": "https://v.test/e/1", "name": "A"}),
            event(**{"@id": "https://v.test/e/1", "name": "B"}),
        ]
    )

    assert [c.title for c in result.candidates] == ["A"]
    assert result.skipped["duplicate_id"] == 1


def test_series_without_id_still_shares_a_derived_series_id():
    series = {
        "@type": "EventSeries",
        "name": "Run Club",
        "subEvent": [event(name="A"), event(name="B")],
    }

    result = parse_nodes(series)

    assert len({c.series_id for c in result.candidates}) == 1
    assert result.candidates[0].series_id is not None


def test_unknown_charset_falls_back_to_utf8():
    html = (
        '<meta charset="klingon"><script type="application/ld+json">'
        + json.dumps(event(name="Ümlaut"))
        + "</script>"
    )

    [c] = parse_jsonld(html.encode("utf-8"), CONTEXT).candidates

    assert c.title == "Ümlaut"


def test_html_the_parser_cant_read_is_an_error(monkeypatch):
    from apps.ingestion.parsers import jsonld

    def explode(self, data):
        raise AssertionError("html.parser internal error")

    monkeypatch.setattr(jsonld._ScriptCollector, "feed", explode)

    assert parse_jsonld(b"<html></html>", CONTEXT).error == "unreadable_html"


def test_item_cap_inside_a_series(monkeypatch):
    monkeypatch.setattr("apps.ingestion.parsers.types.MAX_ITEMS", 1)
    series = {"@type": "EventSeries", "@id": "s", "subEvent": [event(name="A"), event(name="B")]}

    result = parse_nodes(series)

    assert len(result.candidates) == 1 and result.skipped["too_many_items"] == 1


# ── ItemList: how a directory page lists its events ─────────────────────────────────


def item_list(*items):
    """An `ItemList` of `ListItem`s, the shape an events directory page publishes."""
    return {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "itemListElement": [
            {"@type": "ListItem", "position": i, "item": item}
            for i, item in enumerate(items, start=1)
        ],
    }


def test_an_item_list_of_list_items_yields_every_event():
    result = parse_nodes(item_list(event(name="A"), event(name="B"), event(name="C")))

    assert [c.title for c in result.candidates] == ["A", "B", "C"]


def test_an_item_list_carries_each_events_own_fields():
    listed = event(
        name="Admission Day",
        startDate="2026-11-21",
        location={
            "@type": "Place",
            "name": "Edvoy",
            "address": {
                "@type": "PostalAddress",
                "addressLocality": "Dhaka",
                "addressCountry": "BD",
            },
        },
    )

    [c] = parse_nodes(item_list(listed)).candidates

    assert c.title == "Admission Day"
    assert (c.venue_name, c.venue_city, c.venue_country) == ("Edvoy", "Dhaka", "BD")
    assert c.all_day is True


def test_a_non_event_in_an_item_list_is_not_a_candidate():
    product = {"@type": "Product", "name": "A ticket"}

    result = parse_nodes(item_list(event(name="Real"), product))

    assert [c.title for c in result.candidates] == ["Real"]


def test_a_series_inside_an_item_list_still_emits_its_subevents_once():
    series = {"@type": "EventSeries", "@id": "s", "subEvent": [event(name="A"), event(name="B")]}

    result = parse_nodes(item_list(series))

    titles = [c.title for c in result.candidates]
    assert titles == ["A", "B"], "a subEvent reached twice would be listed twice"
    # The series branch is the only emission, so both still share its one id.
    ids = {c.series_id for c in result.candidates}
    assert len(ids) == 1 and None not in ids
