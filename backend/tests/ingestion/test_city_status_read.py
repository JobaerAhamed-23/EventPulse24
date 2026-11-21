"""The city's collection status, read for the surface that renders it.

**What this file holds.** The read is the seam between the catalog's provisioning status
and the two surfaces that render it — Browse's (`apps.personalization`) and the public
city page's (`apps.catalog`). Neither may import `apps.ingestion.models` (AD-3), so the
read is a service that hands over plain data.

**The three promises this file defends.**

1. **The status is the catalog's own.** `live` is `live`; the surface renders what the
   probation wrote, not a second opinion about it.
2. **A city that was never provisioned is an answer, not a failure.** The status is empty,
   and the surface treats empty as its own state rather than folding it into one of the
   model's.
3. **A read never writes.** It does not mint a `City`, it does not register a source, it
   writes no audit row. A read that minted a city would put a place into the registry
   that no reader ever chose — and it would do it every time somebody opened Browse.
"""

import pytest

from apps.ingestion.models import City, CityProvisioning, IngestionAuditEntry
from apps.ingestion.services.city_status_read import (
    CityCollectionStatus,
    read_city_collection_status,
)
from shared.db import CATALOG

pytestmark = pytest.mark.django_db(databases=[CATALOG])

#: A city in the curated catalog.
CITY = "Portland, OR"


# --- helpers ---------------------------------------------------------------------------------


def _city(name: str = CITY, *, key: str = "", region: str = "", country: str = "US") -> City:
    """A `City` row, written directly.

    **The provisioning service is not used here** because this file is about the *read*,
    and the read must work for a city that was never provisioned at all. A row written
    here with no provisioning row is exactly that case.
    """
    return City.objects.using(CATALOG).create(
        name=name,
        country_code=country,
        normalized_key=key or name.lower(),
        slug=f"slug-{name.lower().replace(' ', '-').replace(',', '')}",
        region=region,
    )


def _provisioned(city: City, *, status: str, source_count: int = 1) -> CityProvisioning:
    """A provisioning row for `city`, in the given status."""
    return CityProvisioning.objects.using(CATALOG).create(
        city=city,
        status=status,
        source_count=source_count,
    )


# --- the status ------------------------------------------------------------------------------


class TestTheStatusIsRead:
    """The status comes from the catalog's own row, verbatim."""

    @pytest.mark.parametrize(
        "status",
        [
            CityProvisioning.Status.COLLECTING,
            CityProvisioning.Status.LIVE,
            CityProvisioning.Status.NO_PROVIDERS,
            CityProvisioning.Status.YIELDED_NOTHING,
            CityProvisioning.Status.PAUSED,
            CityProvisioning.Status.FAILED,
        ],
    )
    def test_every_status_is_read_verbatim(self, status):
        """Each of the model's six statuses comes back as itself.

        **The surface's states are these six plus empty**, so a status the read mangled
        would reach the surface as a state the surface does not know.
        """
        city = _city()
        _provisioned(city, status=status)

        assert read_city_collection_status(city=city.name).status == status

    def test_the_source_count_comes_with_it(self):
        """The count is the provisioning's own — a count, never a list."""
        city = _city()
        _provisioned(city, status=CityProvisioning.Status.COLLECTING, source_count=3)

        assert read_city_collection_status(city=city.name).source_count == 3

    def test_the_status_is_read_by_the_catalogs_own_name(self):
        """The lookup is on the canonical name — the form the picker stores."""
        city = _city(name="Portland, OR", key="portland", region="or")

        _provisioned(city, status=CityProvisioning.Status.LIVE)

        assert read_city_collection_status(city="Portland, OR").status == "live"

    def test_the_status_is_read_by_the_identity_key_too(self):
        """A city minted by a *venue* carries the venue's spelling, not the catalog's.

        **The reader's stored preference is the catalog's canonical form** — but the
        `City` row a venue minted carries whatever that venue wrote. So the lookup falls
        back to the identity key `domain.cities` computes, and the two spellings of one
        place are one city.
        """
        city = _city(name="Portland, Oregon", key="portland", region="or")

        _provisioned(city, status=CityProvisioning.Status.COLLECTING)

        assert read_city_collection_status(city="Portland, OR").status == "collecting"

    def test_the_lookup_ignores_surrounding_whitespace(self):
        """A stored city with a stray space is still the city."""
        city = _city()
        _provisioned(city, status=CityProvisioning.Status.LIVE)

        assert read_city_collection_status(city="  Portland, OR  ").status == "live"


class TestTheEmptyStatus:
    """An empty status is a real answer — "we never provisioned this"."""

    def test_a_city_with_no_provisioning_row_has_no_status(self):
        """The row is absent, so there is nothing to say about the collection."""
        city = _city()

        result = read_city_collection_status(city=city.name)

        assert result.status == ""
        assert result.source_count == 0

    def test_a_city_that_does_not_exist_has_no_status(self):
        """There is no such city, and that is not a failure."""
        result = read_city_collection_status(city="Nowhere, ZZ")

        assert result.status == ""
        assert result.source_count == 0

    def test_an_empty_city_name_has_no_status(self):
        """An empty name names no city, and the read does not guess one."""
        assert read_city_collection_status(city="").status == ""
        assert read_city_collection_status(city="   ").status == ""

    def test_a_name_that_normalises_to_nothing_has_no_status(self):
        """Punctuation alone is not a place.

        **`normalize_city` folds case, whitespace, punctuation and accents**, so a name
        made only of punctuation has no identity key at all. There is no city it could
        name, and the read must not go looking for one — a lookup with an empty key
        would match *every* city whose `normalized_key` is empty, which is a different
        question from the one being asked.
        """
        assert read_city_collection_status(city="!!!").status == ""
        assert read_city_collection_status(city="---").status == ""


class TestTheReadNeverWrites:
    """A read that wrote would be a command wearing a read's name."""

    def test_reading_an_unknown_city_does_not_mint_it(self):
        """**The whole reason this module exists rather than `resolve_city`.**

        A read that minted a `City` would put a place into the registry that no reader
        chose — and it would do it every time somebody opened Browse for a city we have
        never provisioned.
        """
        before = City.objects.using(CATALOG).count()

        read_city_collection_status(city="Nowhere, ZZ")

        assert City.objects.using(CATALOG).count() == before

    def test_reading_writes_no_audit_row(self):
        """A read is not an event, and the audit log is for events."""
        city = _city()
        _provisioned(city, status=CityProvisioning.Status.LIVE)
        before = IngestionAuditEntry.objects.using(CATALOG).count()

        read_city_collection_status(city=city.name)

        assert IngestionAuditEntry.objects.using(CATALOG).count() == before

    def test_reading_a_city_with_no_provisioning_row_mints_nothing(self):
        """Even for a city that *does* exist, the read does not provision it."""
        city = _city()
        before = CityProvisioning.objects.using(CATALOG).count()

        read_city_collection_status(city=city.name)

        assert CityProvisioning.objects.using(CATALOG).count() == before


class TestTheOutcomeIsPlainData:
    """The seam is plain data, so the calling app holds no model reference (AD-3)."""

    def test_the_outcome_is_a_frozen_dataclass(self):
        """A frozen dataclass, not a model instance — the contract `catalog_read` keeps."""
        import dataclasses

        assert dataclasses.is_dataclass(CityCollectionStatus)
        with pytest.raises(dataclasses.FrozenInstanceError):
            CityCollectionStatus().status = "live"  # type: ignore[misc]

    def test_the_outcome_carries_no_model(self):
        """The calling app must not be able to reach a model through the result."""
        outcome = read_city_collection_status(city="Nowhere, ZZ")

        assert not hasattr(outcome, "city")
        assert not hasattr(outcome, "provisioning")
