"""Parser helpers: plain text, URLs, derived ids, ISO times, all-day and overnight rules,
the Windows zone table, and the dispatcher's never-raise promise."""

import random
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest

from apps.ingestion.parsers import PARSERS, parse
from apps.ingestion.parsers.text import absolute_iri, derived_id, http_url, item_id, plain_text
from apps.ingestion.parsers.types import SourceContext
from domain.timezones import canonical_zone
from formats.ics.windows_zones import WINDOWS_ZONES, map_zone
from formats.times import all_day_span, parse_iso, roll_overnight

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "sources"
CONTEXT = SourceContext(UUID(int=7), "https://source.example.test/")


def wall(text: str) -> datetime:
    return datetime.fromisoformat(text)


# --- plain_text --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("<p>Hello <b>world</b></p>", "Hello world"),
        ("<script>alert(1)</script>Safe", "Safe"),
        ("<style>p{}</style><template>x</template><noscript>y</noscript>Text", "Text"),
        ("Fish &amp; Chips &lt;3", "Fish & Chips <3"),
        ("Line\nbreak\t\ttabs   spaces", "Line break tabs spaces"),
        ("Null\x00and\x07bell", "Null and bell"),
        ("a<br>b<p>c", "a b c"),
        # The MMFA JSON-LD description, verbatim: entity-escaped tags, double-escaped newlines.
        (
            "&lt;p&gt;Tuesday, November 3&lt;br /&gt;\\n9:30 AM&lt;br /&gt;\\n"
            "Permanent Collection Galleries&lt;/p&gt;\\n",
            "Tuesday, November 3 9:30 AM Permanent Collection Galleries",
        ),
        ("&lt;script&gt;alert(1)&lt;/script&gt;Safe", "Safe"),
        ("Fish &amp; Chips &lt;3 &lt;b&gt;bold&lt;/b&gt;", "Fish & Chips <3 bold"),
        (None, ""),
        (42, "42"),
    ],
)
def test_plain_text(value, expected):
    assert plain_text(value, 100) == expected


def test_plain_text_truncates_after_stripping():
    assert plain_text("<b>" + "x" * 20 + "</b>", 10) == "x" * 10


# --- http_url ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "base", "expected"),
    [
        ("https://a.test/e", "", "https://a.test/e"),
        ("/e/1", "https://a.test/feed", "https://a.test/e/1"),
        ("javascript:alert(1)", "", ""),
        ("data:text/html,x", "", ""),
        ("ftp://a.test/x", "", ""),
        ("//", "", ""),
        ("http://[::1", "", ""),
        ("https://a.test/" + "x" * 2100, "", ""),
        (None, "", ""),
        ("  ", "", ""),
    ],
)
def test_http_url(value, base, expected):
    assert http_url(value, base) == expected


def test_item_id_keeps_ids_that_fit_and_hashes_ones_that_dont():
    assert item_id("  community-1 ") == "community-1"
    assert item_id("x" * 512) == "x" * 512
    long = item_id("x" * 513)

    assert long.startswith("long:") and len(long) == 69 and long == item_id("x" * 513)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://venue.test/e/1", "https://venue.test/e/1"),
        ("urn:uuid:1234", "urn:uuid:1234"),
        ("tag:venue.test,2026:e1", "tag:venue.test,2026:e1"),
        ("_:b0", None),
        ("#event", None),
        ("/e/1", None),
        ("event-1", None),
        ("http://[::1", None),  # urlsplit raises
        ("", None),
        (None, None),
        (42, None),
    ],
)
def test_absolute_iri(value, expected):
    assert absolute_iri(value) == expected


def test_derived_id_is_stable_prefixed_and_distinct():
    a = derived_id("https://a.test/e", "Show", "2026-11-05T19:30")

    assert a == derived_id("https://a.test/e", "Show", "2026-11-05T19:30")
    assert a != derived_id("https://a.test/e", "Show", "2026-11-12T19:30")
    assert a.startswith("derived:") and len(a) == 40


# --- times -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-11-05T19:30:00Z", datetime(2026, 11, 5, 19, 30, tzinfo=UTC)),
        (
            "2026-11-05T19:30:00-05:00",
            datetime(2026, 11, 5, 19, 30, tzinfo=timezone(timedelta(hours=-5))),
        ),
        ("2026-11-05T19:30", wall("2026-11-05T19:30")),
        ("2026-11-05", date(2026, 11, 5)),
        ("next Tuesday", None),
        ("", None),
        (None, None),
        (1730000000, None),
    ],
)
def test_parse_iso(value, expected):
    assert parse_iso(value) == expected


def test_all_day_span_defaults_to_one_day_and_ignores_bad_ends():
    assert all_day_span(date(2026, 11, 14), None) == (
        wall("2026-11-14T00:00"),
        wall("2026-11-15T00:00"),
    )
    assert all_day_span(date(2026, 11, 14), date(2026, 11, 14))[1] == wall("2026-11-15T00:00")


@pytest.mark.parametrize(
    ("start", "end", "expected", "dropped"),
    [
        (wall("2026-11-14T22:00"), wall("2026-11-14T02:00"), wall("2026-11-15T02:00"), False),
        (wall("2026-11-14T22:00"), wall("2026-11-14T23:00"), wall("2026-11-14T23:00"), False),
        (wall("2026-11-14T22:00"), wall("2026-11-12T23:00"), None, True),
        (wall("2026-11-14T22:00"), None, None, False),
    ],
)
def test_roll_overnight(start, end, expected, dropped):
    assert roll_overnight(start, end) == (expected, dropped)


def test_roll_overnight_leaves_mixed_representations_alone():
    start = datetime(2026, 11, 14, 22, tzinfo=UTC)
    end = wall("2026-11-14T02:00")

    assert roll_overnight(start, end) == (end, False)
    assert roll_overnight(
        start, datetime(2026, 11, 14, 2, tzinfo=timezone(timedelta(hours=1)))
    ) == (
        datetime(2026, 11, 14, 2, tzinfo=timezone(timedelta(hours=1))),
        False,
    )


# --- Windows zones -----------------------------------------------------------------------------


@pytest.mark.parametrize(("windows", "iana"), sorted(WINDOWS_ZONES.items()))
def test_every_windows_zone_maps_to_a_canonical_zone(windows, iana):
    assert canonical_zone(iana) == iana


def test_map_zone_passes_unknown_names_through():
    assert map_zone(" Eastern Standard Time ") == "America/New_York"
    assert map_zone("Mars Standard Time") == "Mars Standard Time"
    assert map_zone("America/Chicago") == "America/Chicago"
    assert map_zone(None) is None and map_zone("  ") is None


# --- Dispatcher --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "fixture", "count"),
    [
        ("jsonld", "venue-events.html", 7),
        ("rss", "events.rss", 3),
        ("ics", "calendar.ics", 8),
        ("email_ics", "calendar.ics", 8),
    ],
)
def test_dispatch_by_acquisition_method(method, fixture, count):
    assert len(parse(method, (FIXTURES / fixture).read_bytes(), CONTEXT).candidates) == count


def test_dispatch_covers_every_structured_method():
    from apps.ingestion.models import AcquisitionMethod

    structured = {
        AcquisitionMethod.JSONLD,
        AcquisitionMethod.RSS,
        AcquisitionMethod.ICS,
        AcquisitionMethod.EMAIL_ICS,
    }
    assert set(PARSERS) == {m.value for m in structured}


@pytest.mark.parametrize("method", ["api", "partnership", "crawl", "nonsense"])
def test_unsupported_methods_return_an_error(method):
    assert parse(method, b"<rss/>", CONTEXT).error == "unsupported_method"


def test_a_parser_that_raises_is_contained(monkeypatch):
    def explode(content, context):
        raise RuntimeError("bug")

    monkeypatch.setitem(PARSERS, "rss", explode)

    assert parse("rss", b"", CONTEXT).error == "parser_failure"


ALL_FIXTURES = sorted(p.name for p in FIXTURES.iterdir() if p.name != "index.json")
# Seeded, so a failure reproduces (not a security use of randomness).
NOISE = random.Random("parsers").randbytes(4096)  # noqa: S311
HOSTILE_INPUTS = [b"", b"\x00" * 64, NOISE, b"<" * 10_000, b"BEGIN:VCALENDAR\r\n" * 500]


@pytest.mark.parametrize("method", sorted(PARSERS))
@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_every_fixture_through_every_parser_never_raises(method, name):
    result = parse(method, (FIXTURES / name).read_bytes(), CONTEXT)

    assert result.error is None or isinstance(result.error, str)
    assert all(c.source_event_id for c in result.candidates)


@pytest.mark.parametrize("method", sorted(PARSERS))
@pytest.mark.parametrize(
    "content", HOSTILE_INPUTS, ids=["empty", "nulls", "random", "angles", "ics-headers"]
)
def test_garbage_never_raises(method, content):
    result = parse(method, content, CONTEXT)

    assert result.candidates == [] or all(c.source_event_id for c in result.candidates)
