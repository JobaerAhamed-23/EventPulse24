"""Venue registry commands (design D14, plan R7)."""

import pytest

from apps.ingestion.models import IngestionAuditEntry, Venue
from apps.ingestion.services.venue_registry import (
    VenueAlreadyRegisteredError,
    VenueNotFoundError,
    register_venue,
    set_venue_timezone,
)
from domain.dedup import venue_fingerprint
from domain.errors import InvalidTimezoneError, ValidationError
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from shared.ids import uuid7

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

STAFF_ID = uuid7()
STAFF = Actor.user(STAFF_ID)


def _register(**overrides) -> Venue:
    kwargs = {"actor": STAFF, "name": "The Fillmore", "city": "San Francisco", "country_code": "us"}
    return register_venue(**(kwargs | overrides))


def _locs(exc: ValidationError) -> list[list[str]]:
    return [item["loc"] for item in exc.details["errors"]]


def _audit() -> list[IngestionAuditEntry]:
    return list(IngestionAuditEntry.objects.using(CATALOG).order_by("id"))


def test_register_venue_stores_fingerprint_and_audit_row():
    venue = _register(tz="America/Los_Angeles")

    stored = Venue.objects.using(CATALOG).get(pk=venue.pk)
    assert (stored.name, stored.city, stored.country_code, stored.tz) == (
        "The Fillmore",
        "San Francisco",
        "US",
        "America/Los_Angeles",
    )
    assert stored.venue_fingerprint == venue_fingerprint("The Fillmore", "San Francisco", "US")
    [entry] = _audit()
    assert (entry.action, entry.target_type, entry.target_id, entry.actor_id) == (
        "register_venue",
        "venue",
        venue.id,
        STAFF_ID,
    )
    assert entry.details["fields"]["venue_fingerprint"] == stored.venue_fingerprint


def test_register_venue_without_tz_stores_null():
    assert Venue.objects.using(CATALOG).get(pk=_register().pk).tz is None


def test_register_venue_legacy_tz_stored_canonical():
    assert _register(tz="US/Pacific").tz == "America/Los_Angeles"


@pytest.mark.parametrize("tz", ["Mars/Olympus", "PST", "+05:00", "   "])
def test_register_venue_invalid_tz_raises_invalid_timezone_and_writes_nothing(tz):
    with pytest.raises(InvalidTimezoneError) as excinfo:
        _register(tz=tz)

    assert _locs(excinfo.value) == [["tz"]]
    assert not Venue.objects.using(CATALOG).exists()
    assert _audit() == []


def test_register_venue_same_fingerprint_refused():
    first = _register(name="The Fillmore")

    with pytest.raises(VenueAlreadyRegisteredError) as excinfo:
        _register(name="Fillmore", country_code="US")

    assert excinfo.value.details == {"venue_id": str(first.id)}


@pytest.mark.parametrize(
    ("overrides", "locs"),
    [
        ({"name": ""}, [["name"]]),
        ({"name": "!!!"}, [["name"]]),
        ({"name": "v" * 201}, [["name"]]),
        ({"city": " "}, [["city"]]),
        ({"country_code": "USA"}, [["country_code"]]),
        ({"country_code": None}, [["country_code"]]),
        ({"name": "", "tz": "Mars/Olympus"}, [["name"], ["tz"]]),
    ],
)
def test_register_venue_invalid_input_refused(overrides, locs):
    with pytest.raises(ValidationError) as excinfo:
        _register(**overrides)

    assert not isinstance(excinfo.value, InvalidTimezoneError)
    assert _locs(excinfo.value) == locs
    assert not Venue.objects.using(CATALOG).exists()


def test_set_venue_timezone_sets_canonical_tz_with_audit_row():
    venue = _register()

    set_venue_timezone(actor=STAFF, venue_id=venue.id, tz="US/Pacific")

    assert Venue.objects.using(CATALOG).get(pk=venue.pk).tz == "America/Los_Angeles"
    entry = _audit()[-1]
    assert (entry.action, entry.details) == (
        "set_venue_timezone",
        {"from": None, "to": "America/Los_Angeles"},
    )


def test_set_venue_timezone_same_tz_writes_nothing():
    venue = _register(tz="Europe/Berlin")

    set_venue_timezone(actor=STAFF, venue_id=venue.id, tz="Europe/Berlin")

    assert [e.action for e in _audit()] == ["register_venue"]


@pytest.mark.parametrize("tz", ["Mars/Olympus", "", None])
def test_set_venue_timezone_invalid_tz_refused(tz):
    venue = _register(tz="Europe/Berlin")

    with pytest.raises(InvalidTimezoneError):
        set_venue_timezone(actor=STAFF, venue_id=venue.id, tz=tz)

    assert Venue.objects.using(CATALOG).get(pk=venue.pk).tz == "Europe/Berlin"


def test_set_venue_timezone_unknown_venue_not_found():
    with pytest.raises(VenueNotFoundError):
        set_venue_timezone(actor=STAFF, venue_id=uuid7(), tz="Europe/Berlin")
