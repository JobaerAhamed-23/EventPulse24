"""The published read of one city's collection status — the sentence the surface reads.

**Why this module exists.** The provisioning status lives on `catalog.ingestion_cityprovisioning`,
and the surfaces that read it live in other apps: Browse's read is in `apps.personalization`
and the public city page's is in `apps.catalog`. Neither may import `apps.ingestion.models`
(import contract `models-ingestion`, AD-3). The contract protects *the models module only* —
its own name says it: *"only `apps.ingestion` imports `apps.ingestion.models` (others call
its services)"* — and the precedent is everywhere: `catalog_read`, `preview_read` and
`city_read` are all services that hand over plain data so the wall holds without either side
knowing the other's models.

**This module reads and never writes.** That is the whole difference between it and
`city_provisioning.provision_city`, which mints a `City` and registers sources. A read that
minted a city would put a place into the registry that no reader chose — a reader opening
Browse for a city we have never provisioned would create the row that says we are collecting
it. **So the lookup here is a lookup, not a resolution**: no `resolve_city`, no creation, no
audit row.

**The empty status is a real answer, not a missing one.** `status=""` means *this city has
no provisioning row* — it was never picked, or provisioning never started for it. It is
different from every one of the model's six statuses, and the surface treats it as its own
case rather than folding it into one of them.

**Two names, one city.** A `City` minted by the picker carries the catalog's canonical name
(`"Portland, OR"`); a `City` minted by a *venue* carries whatever spelling that venue wrote
(`"Portland, Oregon"`). The stored reader preference is the catalog's canonical form, so the
lookup tries the canonical name first and falls back to the identity key `domain.cities`
computes. **Neither lookup creates anything.**
"""

from dataclasses import dataclass

from django.db.models import F, Q

from apps.ingestion.models import City
from domain.cities import normalize_city
from shared.db import CATALOG


@dataclass(frozen=True)
class CityCollectionStatus:
    """How the collection of one city is going.

    **Plain data, never a model** — so the calling app never holds a reference to
    `apps.ingestion.models` and the wall holds without either side knowing the other's
    models. The same contract `catalog_read` hands over.
    """

    #: The `CityProvisioning.Status` value, or `""` when the city has no provisioning row.
    status: str = ""
    #: How many sources the provisioning registered. A count, never a list.
    source_count: int = 0


def read_city_collection_status(*, city: str) -> CityCollectionStatus:
    """The collection status of the city with this name.

    **`status=""` when there is no provisioning row** — including when there is no such
    city at all. Both are "we have not provisioned this", and both are honest answers
    rather than failures: a reader's Browse must not 404 because their city was never
    provisioned.

    **One query, and it never creates.** The canonical name — the form the picker stores
    and the form a provisioned city carries — and the identity key, for a city that was
    minted by a venue rather than by a reader's pick, whose `name` is the venue's own
    spelling. Both are asked in the same query, because Browse's read is on the hot path
    and a second round trip would be paid on every request.

    **The name wins over the key.** A city that answers to both is one row, and the row
    whose `name` matches exactly is the more precise of the two answers.

    **The provisioning row is joined, not fetched after.** Two queries would be two round
    trips for one sentence, and `tests/personalization/test_browse_read.py` holds the
    catalog side of Browse's read to a single query.

    **`normalize_city` is `domain.cities`'s pure function** (AD-2: `domain` is stdlib only),
    so this module can use it without crossing the wall in the other direction.
    """
    name = (city or "").strip()
    if not name:
        return CityCollectionStatus()

    key = normalize_city(name)
    if not key:
        return CityCollectionStatus()

    row = (
        City.objects.using(CATALOG)
        .filter(Q(name=name) | Q(normalized_key=key))
        .annotate(
            provisioning_status=F("provisioning__status"),
            provisioning_source_count=F("provisioning__source_count"),
        )
        .order_by("-name", "pk")
        .values("provisioning_status", "provisioning_source_count")
        .first()
    )
    if row is None:
        return CityCollectionStatus()

    status = row["provisioning_status"]
    if not status:
        return CityCollectionStatus()

    return CityCollectionStatus(
        status=status,
        source_count=row["provisioning_source_count"] or 0,
    )


__all__ = ["CityCollectionStatus", "read_city_collection_status"]
