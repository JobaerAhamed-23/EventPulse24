"""The Schema.org `Event` projection for the public page (FR-26, AD-12).

Every rule is a statement about what the registry **does not know** as much as about what
it does. The omissions are the interesting cases:

- A **venue-less event** has no `location` — not an empty `Place`.
- An event with **no description** has no `description` property.
- An event with **no known price** has an `Offer` with no `price` — never a fabricated zero.
- A **superseded** event has no `eventStatus`, because Schema.org has no term for it.

The two cases the work item calls out by name are the **non-UTC zone** and the **DST
boundary**, and both are here: the times carry the offset the zone had *at that instant*,
so an event that straddles the November fall-back carries **two different offsets** — one
for the start and one for the end. One offset for both would state a false end time.

The last test is the **validation** one: the emitted object is checked against the
properties Schema.org requires of an `Event`. There is no `jsonschema` dependency in this
project, so the check is hand-written and structural — in the shape of
`tests/domain/test_domain_api.py`.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from domain.schema_org import project_schema_org_event
from shared.constants import (
    SCHEMA_ORG_AVAILABILITY_IN_STOCK,
    SCHEMA_ORG_AVAILABILITY_SOLD_OUT,
    SCHEMA_ORG_EVENT_STATUS,
)

NEW_YORK = "America/New_York"
BERLIN = "Europe/Berlin"
AUCKLAND = "Pacific/Auckland"


def local(*, year, month, day, hour=0, minute=0, second=0, zone=NEW_YORK) -> datetime:
    """A wall-clock time in `zone`, as the instant it is."""
    return datetime(year, month, day, hour, minute, second, tzinfo=ZoneInfo(zone)).astimezone(UTC)


def project(**overrides):
    """The projection with sensible defaults, so each test states only what it is about."""
    payload = {
        "title": "Winter Sessions",
        "description": "An evening of quiet music.",
        "start_time_utc": local(year=2026, month=8, day=28, hour=18, minute=30),
        "start_time_tz": NEW_YORK,
        "end_time_utc": local(year=2026, month=8, day=28, hour=20, minute=30),
        "status": "scheduled",
        "is_sold_out": False,
        "venue_name": "Town Hall",
        "venue_city": "Brooklyn",
        "venue_country_code": "US",
        "canonical_url": "https://events.example.test/winter-sessions",
    }
    payload.update(overrides)
    return project_schema_org_event(**payload)


# ── The shape of the object ────────────────────────────────────────────────────────


def test_the_object_is_a_schema_org_event():
    event = project()

    assert event["@context"] == "https://schema.org"
    assert event["@type"] == "Event"
    assert event["name"] == "Winter Sessions"


def test_the_object_is_json_serializable():
    """JSON-LD is JSON. A `datetime` left in the object would break the page's embed."""
    import json

    serialized = json.dumps(project())

    assert json.loads(serialized)["@type"] == "Event"


def test_the_projection_is_pure():
    """The same inputs give the same output. No clock, no randomness, no query."""
    first = project()
    second = project()

    assert first == second


# ── eventStatus ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("scheduled", "https://schema.org/EventScheduled"),
        ("postponed", "https://schema.org/EventPostponed"),
        ("cancelled", "https://schema.org/EventCancelled"),
    ],
)
def test_each_status_maps_to_its_schema_org_term(status, expected):
    event = project(status=status)

    assert event["eventStatus"] == expected


def test_a_superseded_event_has_no_event_status():
    """Schema.org's `EventStatus` vocabulary has no term for a superseded event.

    It is terminal — the public read 404s it before it ever builds a payload — so the
    projection never sees one. But the guard matters: a projection that emitted
    `EventScheduled` for a superseded event would be a lie the day anyone called it
    directly. **Omitting is the honest answer.**
    """
    event = project(status="superseded")

    assert "eventStatus" not in event


def test_every_status_the_model_can_hold_is_mapped_or_deliberately_absent():
    """The vocabulary is closed and the map has no default.

    A status added to `Event` must fail a test rather than silently produce an event with
    no `eventStatus` — which is a structured-data warning a crawler would raise. The only
    status absent from the map is `superseded`, and its absence is deliberate.
    """
    assert set(SCHEMA_ORG_EVENT_STATUS) == {"scheduled", "postponed", "cancelled"}
    assert "superseded" not in SCHEMA_ORG_EVENT_STATUS


# ── offers ─────────────────────────────────────────────────────────────────────────


def test_a_sold_out_event_offers_sold_out():
    event = project(is_sold_out=True)

    assert event["offers"]["availability"] == SCHEMA_ORG_AVAILABILITY_SOLD_OUT


def test_an_available_event_offers_in_stock():
    event = project(is_sold_out=False)

    assert event["offers"]["availability"] == SCHEMA_ORG_AVAILABILITY_IN_STOCK


def test_the_offer_carries_no_price():
    """The registry knows no price, so the `Offer` states no price.

    An `Offer` with only an `availability` is a valid Schema.org object and says exactly
    what we know. A fabricated `"price": "0"` says something nobody told us.
    """
    event = project()

    assert "price" not in event["offers"]
    assert "priceCurrency" not in event["offers"]


# ── The times, and the DST boundary ───────────────────────────────────────────────


def test_the_start_carries_the_offset_implied_by_the_zone():
    """`-04:00` in August — not `Z`, and not a string-formatted UTC."""
    event = project()

    assert event["startDate"] == "2026-08-28T18:30:00-04:00"


def test_a_utc_event_carries_a_zero_offset():
    event = project(
        start_time_utc=local(year=2026, month=8, day=28, hour=18, minute=30, zone="UTC"),
        start_time_tz="UTC",
    )

    assert event["startDate"] == "2026-08-28T18:30:00+00:00"


def test_a_non_utc_zone_is_honoured():
    """Berlin in August is UTC+2 — a zone the naive "always -04:00" answer would miss."""
    event = project(
        start_time_utc=local(year=2026, month=8, day=28, hour=18, minute=30, zone=BERLIN),
        start_time_tz=BERLIN,
    )

    assert event["startDate"] == "2026-08-28T18:30:00+02:00"


def test_a_zone_with_a_half_hour_offset_keeps_its_half_hour():
    """Auckland is UTC+12; Kathmandu is UTC+05:45. A whole-hour assumption would be wrong."""
    event = project(
        start_time_utc=local(year=2026, month=8, day=28, hour=18, minute=30, zone=AUCKLAND),
        start_time_tz=AUCKLAND,
    )

    assert event["startDate"] == "2026-08-28T18:30:00+12:00"


def test_an_event_across_the_dst_fall_back_carries_two_offsets():
    """The case the DST rule exists for.

    The American fall-back is 2026-11-01 at 02:00 EDT, when the clock reads 01:00 EST. An
    event that starts at 23:30 **EDT** on October 31 and ends at 03:30 **EST** on November 1
    **straddles it**: the start is `-04:00` and the end is `-05:00`. One offset for both
    would state a false end time — the end would read as 04:30 to a reader in New York
    rather than 03:30.

    The end is at 03:30 rather than 01:30 on purpose: 01:30 is the **ambiguous hour**, the
    one local time that happens twice, and an event ending there does not have one offset.
    """
    event = project(
        start_time_utc=local(year=2026, month=10, day=31, hour=23, minute=30),
        end_time_utc=local(year=2026, month=11, day=1, hour=3, minute=30),
        start_time_tz=NEW_YORK,
    )

    assert event["startDate"] == "2026-10-31T23:30:00-04:00"
    assert event["endDate"] == "2026-11-01T03:30:00-05:00"


def test_an_event_across_the_dst_spring_forward_carries_two_offsets():
    """The other direction: 2026-03-08 is the American spring-forward."""
    event = project(
        start_time_utc=local(year=2026, month=3, day=8, hour=1, minute=30),
        end_time_utc=local(year=2026, month=3, day=8, hour=3, minute=30),
        start_time_tz=NEW_YORK,
    )

    assert event["startDate"] == "2026-03-08T01:30:00-05:00"
    assert event["endDate"] == "2026-03-08T03:30:00-04:00"


def test_an_event_with_no_end_has_no_end_date():
    """`end_time_utc` is nullable on the model. A missing end is omitted, not guessed."""
    event = project(end_time_utc=None)

    assert "endDate" not in event


def test_an_unknown_zone_falls_back_to_utc_rather_than_raising():
    """A zone on an `Event` was validated at write time.

    An unknown name here means the data is older or hand-edited — not that the event is
    invalid. A structured-data warning on one page is a worse answer than a page that
    states the time in UTC.
    """
    event = project(start_time_tz="Mars/Olympus_Mons")

    assert event["startDate"] == "2026-08-28T22:30:00+00:00"


def test_a_naive_start_is_refused_rather_than_assumed():
    """`astimezone` would silently read a naive value as UTC and convert it.

    18:30 naive, read as UTC and converted to New York, becomes **08:30-04:00** — a
    ten-hour lie about the event's start time, and a lie that would reach a search
    result. `Event` stores UTC (AD-6), so a naive value means a caller passed the wrong
    thing; the honest answer is to refuse it.
    """
    naive = datetime(2026, 8, 28, 18, 30)  # noqa: DTZ001 - the naive value is the point
    with pytest.raises(ValueError, match="timezone-aware"):
        project(start_time_utc=naive)


def test_a_naive_end_is_refused_rather_than_assumed():
    naive = datetime(2026, 8, 28, 20, 30)  # noqa: DTZ001 - the naive value is the point
    with pytest.raises(ValueError, match="timezone-aware"):
        project(end_time_utc=naive)


# ── location ───────────────────────────────────────────────────────────────────────


def test_the_venue_is_a_place_with_the_address_parts_that_exist():
    event = project()

    assert event["location"]["@type"] == "Place"
    assert event["location"]["name"] == "Town Hall"
    assert event["location"]["address"]["@type"] == "PostalAddress"
    assert event["location"]["address"]["addressLocality"] == "Brooklyn"
    assert event["location"]["address"]["addressCountry"] == "US"


def test_the_place_has_no_street_address():
    """`Venue` has no address column.

    A street line here would be a fiction in the structured data — and the structured data
    is what a crawler believes.
    """
    event = project()

    assert "streetAddress" not in event["location"]["address"]


def test_a_venue_less_event_omits_the_location():
    """An empty `Place` is a node that says nothing and validates.

    That is the kind of thing that draws a structured-data warning, so a venue-less event
    omits the property entirely.
    """
    event = project(venue_name=None, venue_city=None, venue_country_code=None)

    assert "location" not in event


def test_a_venue_without_a_city_still_has_a_place():
    """The venue is known even when its city is not. The place says what it knows."""
    event = project(venue_city=None, venue_country_code=None)

    assert event["location"]["name"] == "Town Hall"
    assert "addressLocality" not in event["location"]["address"]
    assert "addressCountry" not in event["location"]["address"]


# ── The fields the registry does not have ──────────────────────────────────────────


def test_an_event_with_no_description_omits_the_description():
    """`Event.description` is `TextField(blank=True)`. An empty string is noise."""
    event = project(description="")

    assert "description" not in event


def test_the_offer_is_absent_when_there_is_nothing_to_offer():
    """Every event has an availability, so the `Offer` is always present."""
    event = project()

    assert "offers" in event
    assert event["offers"]["@type"] == "Offer"


def test_an_event_with_no_attendance_mode_omits_the_property():
    """The registry has no attendance mode, so the property is omitted.

    Defaulting to `Offline` would be a guess that a crawler reads as fact — and the work
    item says exactly that: never defaulted for an event the registry says nothing about.
    """
    event = project()

    assert "eventAttendanceMode" not in event


def test_an_attendance_mode_is_stated_when_it_is_known():
    """The projection accepts the value, so the day the registry learns it, nothing moves."""
    event = project(attendance_mode="https://schema.org/OfflineEventAttendanceMode")

    assert event["eventAttendanceMode"] == "https://schema.org/OfflineEventAttendanceMode"


def test_no_organizer_is_invented():
    """The registry has no organizer entity and no organizer URL.

    The mockup has one, but deriving an organizer from the venue would be a guess about
    the relationship between the two. Omitted, per ASSUMPTION-9.
    """
    event = project()

    assert "organizer" not in event


def test_no_event_status_is_invented_for_an_unknown_status():
    """A status the vocabulary does not know yields no property, not a wrong one."""
    event = project(status="rescheduled")

    assert "eventStatus" not in event


def test_the_canonical_url_is_the_url_when_the_registry_has_one():
    event = project()

    assert event["url"] == "https://events.example.test/winter-sessions"


def test_an_event_with_no_canonical_url_omits_the_url():
    event = project(canonical_url="")

    assert "url" not in event


# ── The validation test ───────────────────────────────────────────────────────────


def _assert_valid_schema_org_event(event: dict) -> None:
    """Assert `event` has the properties Schema.org requires of an `Event`.

    A hand-written structural check, because this project has no `jsonschema` dependency
    and adding one for a single assertion would not be warranted. The properties below are
    the ones a crawler actually reads.
    """
    assert event["@context"] == "https://schema.org"
    assert event["@type"] == "Event"
    assert isinstance(event["name"], str) and event["name"].strip()
    assert isinstance(event["startDate"], str)
    # ISO-8601 with an offset.
    datetime.fromisoformat(event["startDate"])
    assert event["startDate"][-6] in "+-" or event["startDate"].endswith("+00:00")

    if "endDate" in event:
        datetime.fromisoformat(event["endDate"])
        assert datetime.fromisoformat(event["endDate"]) >= datetime.fromisoformat(
            event["startDate"]
        )

    if "eventStatus" in event:
        assert event["eventStatus"].startswith("https://schema.org/")
        assert event["eventStatus"].rsplit("/", 1)[-1] in {
            "EventScheduled",
            "EventPostponed",
            "EventCancelled",
        }

    if "location" in event:
        assert event["location"]["@type"] == "Place"
        assert event["location"]["name"].strip()
        assert event["location"]["address"]["@type"] == "PostalAddress"

    if "offers" in event:
        assert event["offers"]["@type"] == "Offer"
        assert event["offers"]["availability"] in {
            SCHEMA_ORG_AVAILABILITY_SOLD_OUT,
            SCHEMA_ORG_AVAILABILITY_IN_STOCK,
        }


def test_the_emitted_object_is_a_valid_schema_org_event():
    """The validation the AC asks for, on the ordinary case."""
    _assert_valid_schema_org_event(project())


@pytest.mark.parametrize("status", ["scheduled", "postponed", "cancelled"])
def test_the_emitted_object_is_valid_for_every_status(status):
    _assert_valid_schema_org_event(project(status=status))


def test_the_emitted_object_is_valid_for_a_sold_out_event():
    _assert_valid_schema_org_event(project(is_sold_out=True))


def test_the_emitted_object_is_valid_for_a_venue_less_event():
    _assert_valid_schema_org_event(
        project(venue_name=None, venue_city=None, venue_country_code=None)
    )


def test_the_emitted_object_is_valid_for_an_event_with_no_description():
    _assert_valid_schema_org_event(project(description=""))


def test_the_emitted_object_is_valid_across_a_dst_boundary():
    _assert_valid_schema_org_event(
        project(
            start_time_utc=local(year=2026, month=10, day=31, hour=23, minute=30),
            end_time_utc=local(year=2026, month=11, day=1, hour=3, minute=30),
        )
    )


def test_the_emitted_object_is_valid_for_a_non_utc_zone():
    _assert_valid_schema_org_event(
        project(
            start_time_utc=local(year=2026, month=8, day=28, hour=18, minute=30, zone=BERLIN),
            start_time_tz=BERLIN,
        )
    )
