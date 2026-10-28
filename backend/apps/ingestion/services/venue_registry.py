"""Venue registry commands: the FR-60 `partial` tier's timezone source (design D14).

A venue's name, city and country make its identity fingerprint, so they are fixed once it is
registered; only its timezone can be filled in later (plan R7). Renames belong to the editorial
intent.
"""

import re
from uuid import UUID

from django.db import transaction

from apps.ingestion.models import Venue
from apps.ingestion.services.audit import write_audit
from domain.dedup import venue_fingerprint
from domain.errors import ConflictError, InvalidTimezoneError, NotFoundError, ValidationError
from domain.timezones import canonical_zone
from shared.actor import Actor
from shared.db import CATALOG

_COUNTRY_CODE = re.compile(r"[A-Za-z]{2}")


class VenueNotFoundError(NotFoundError):
    default_message = "We couldn't find that venue."


class VenueAlreadyRegisteredError(ConflictError):
    code = "venue_already_registered"
    default_message = "That venue is already registered."


def _raise(errors: list[dict]) -> None:
    if errors:
        only_tz = all(e["loc"] == ["tz"] for e in errors)
        raise (InvalidTimezoneError if only_tz else ValidationError)(details={"errors": errors})


def _text(value: object, field: str, max_length: int, errors: list[dict]) -> str:
    if not isinstance(value, str) or not value.strip():
        errors.append({"loc": [field], "msg": "This can't be empty."})
        return ""
    if len(value.strip()) > max_length:
        errors.append({"loc": [field], "msg": f"Keep this to {max_length} characters."})
    return value.strip()


def _zone(tz: object, errors: list[dict]) -> str | None:
    zone = canonical_zone(tz) if isinstance(tz, str) else None
    if zone is None:
        errors.append({"loc": ["tz"], "msg": "Use an IANA timezone such as Europe/Berlin."})
    return zone


def check_new_venue(*, name: object, city: object, country_code: object, tz: object) -> dict:
    """Validate a venue registration and refuse a duplicate; returns the fields to store.

    The tz is stored in canonical form (`US/Pacific` becomes `America/Los_Angeles`); an
    invalid one raises InvalidTimezoneError. Admin forms call this from `clean()`.
    """
    errors: list[dict] = []
    name = _text(name, "name", 200, errors)
    city = _text(city, "city", 100, errors)
    if not isinstance(country_code, str) or not _COUNTRY_CODE.fullmatch(country_code.strip()):
        errors.append({"loc": ["country_code"], "msg": "Use a two-letter country code."})
        country_code = ""
    country_code = country_code.strip().upper()
    zone = None if tz is None or tz == "" else _zone(tz, errors)
    fingerprint = venue_fingerprint(name, city, country_code)
    if name and not fingerprint:
        errors.append({"loc": ["name"], "msg": "The name needs at least one letter or digit."})
    _raise(errors)

    existing = Venue.objects.using(CATALOG).filter(venue_fingerprint=fingerprint).first()
    if existing is not None:
        raise VenueAlreadyRegisteredError(details={"venue_id": str(existing.id)})
    return {
        "name": name,
        "city": city,
        "country_code": country_code,
        "tz": zone,
        "venue_fingerprint": fingerprint,
    }


def clean_venue_tz(tz: object) -> str:
    """A required, canonical IANA zone, or InvalidTimezoneError."""
    errors: list[dict] = []
    zone = _zone(tz, errors)
    _raise(errors)
    return zone


def register_venue(
    *, actor: Actor, name: str, city: str, country_code: str, tz: str | None = None
) -> Venue:
    """Add a venue to the registry. Its fingerprint is `domain.dedup.venue_fingerprint`."""
    with transaction.atomic(using=CATALOG):
        fields = check_new_venue(name=name, city=city, country_code=country_code, tz=tz)
        venue = Venue.objects.using(CATALOG).create(**fields)
        write_audit(
            actor=actor,
            action="register_venue",
            target_type="venue",
            target_id=venue.id,
            details={"fields": fields},
        )
    return venue


def set_venue_timezone(*, actor: Actor, venue_id: UUID, tz: str) -> Venue:
    """Fill in or correct a venue's IANA timezone. Existing Events keep their own tz; the
    venue's applies to later ingests.
    """
    zone = clean_venue_tz(tz)
    with transaction.atomic(using=CATALOG):
        try:
            venue = Venue.objects.using(CATALOG).select_for_update().get(pk=venue_id)
        except Venue.DoesNotExist:
            raise VenueNotFoundError(details={"venue_id": str(venue_id)}) from None
        if venue.tz == zone:
            return venue
        previous, venue.tz = venue.tz, zone
        venue.save(using=CATALOG, update_fields=["tz", "updated_at"])
        write_audit(
            actor=actor,
            action="set_venue_timezone",
            target_type="venue",
            target_id=venue.id,
            details={"from": previous, "to": zone},
        )
    return venue
