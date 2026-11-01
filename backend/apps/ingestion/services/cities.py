"""Canonical city resolution (FR-27). `ingestion` is the sole writer (AD-4, AD-16).

One free-text city string in, one `City` row out. The decision about *what counts as the
same place* is `domain.cities`' and is pure; this module only does the get-or-create and the
slug escalation, which need the database.

The resolution key is the whole `CityIdentity` — key, region and country — never the key
alone. `Portland, OR` and `Portland, ME` share a key and are different cities.
"""

from uuid import UUID

from django.db import IntegrityError, transaction

from apps.ingestion.models import City, EventFit, Venue
from domain.cities import CityIdentity, city_identity, display_name, mint_city_slug
from shared.actor import Actor
from shared.constants import EVENT_FIT_REFRESH_BATCH_SIZE
from shared.db import CATALOG

from .audit import write_audit

# How a slug escalates when the form before it is taken: more of the identity each time,
# then a numbered tail. The same shape `mint_slug` uses for events — retry with a longer
# form rather than inventing a different name.
SLUG_ATTEMPTS = 50


def _slug_candidates(identity: CityIdentity):
    """The slugs to try, in order, for one identity.

    **A city written with a region starts at the region form.** Beginning at the bare key
    would hand `/events-in-portland` to whichever Portland happened to be ingested first and
    leave the other as `portland-me` — an arbitrary winner, and a misleading URL for a city
    whose own name says "OR". The form a city gets is a function of what it is, not of when
    it arrived.
    """
    if identity.region:
        yield mint_city_slug(identity.key, identity.region)
    else:
        yield mint_city_slug(identity.key)
    if identity.country_code:
        yield mint_city_slug(identity.key, identity.region, identity.country_code)
    base = mint_city_slug(identity.key, identity.region, identity.country_code)
    for n in range(2, SLUG_ATTEMPTS):
        yield f"{base}-{n}"


def _lookup_city(**identity):
    """The one query that finds a City by identity. Named so a test can make it miss."""
    return City.objects.using(CATALOG).filter(**identity)


def resolve_city(*, city: str | None, country_code: str | None) -> City | None:
    """The `City` for a free-text city string, creating it if this is the first sighting.

    `None` when the text names no city. That is a real answer, not a failure: a venue with no
    city gets no City, the same rule Event Fit already follows rather than guessing one.

    Call from inside the caller's `transaction.atomic(using=CATALOG)`. Creation is attempted
    in a savepoint so a concurrent writer that wins the race leaves the caller's transaction
    usable — the loser re-reads the row the winner made.
    """
    identity = city_identity(city, country_code)
    if not identity:
        return None

    lookup = {
        "normalized_key": identity.key,
        "region": identity.region,
        "country_code": identity.country_code,
    }
    existing = _lookup_city(**lookup).first()
    if existing is not None:
        return existing

    for slug in _slug_candidates(identity):
        try:
            with transaction.atomic(using=CATALOG):
                return City.objects.using(CATALOG).create(
                    slug=slug, name=display_name(city), **lookup
                )
        except IntegrityError:
            # Either another writer took this slug, or another writer created this very city
            # between our read and our write. The second is the end of the search.
            found = _lookup_city(**lookup).first()
            if found is not None:
                return found
    raise RuntimeError(f"Could not mint a unique slug for {identity!r} in {SLUG_ATTEMPTS} tries.")


def count_venues_without_a_city() -> int:
    """How many venues the backfill would resolve. The `--dry-run` count."""
    return Venue.objects.using(CATALOG).filter(city_ref__isnull=True).exclude(city="").count()


def backfill_cities(
    *, actor: Actor, batch_size: int = EVENT_FIT_REFRESH_BATCH_SIZE
) -> tuple[int, int]:
    """Resolve a City for every venue that has none, then carry it onto their Event Fits.

    Returns `(venues_resolved, fits_linked)`.

    **Idempotent.** It reads only rows whose `city_ref` is null, so a second run finds
    nothing left to do and writes nothing. A venue with no city text is skipped for good:
    it has no city to resolve, which is an answer and not a gap to retry.

    **Batched**, each batch in its own transaction, so a large catalog is never one long
    lock and a partial run is a valid state rather than a rollback — the columns are
    nullable precisely so that half-done is half-done and not broken.

    **`Venue.city` is never written.** It is the input to `domain.dedup.venue_fingerprint`
    and therefore the venue's identity; this backfill adds a relation beside it and leaves
    the string byte-for-byte as it was.
    """
    venues_resolved = 0
    last_id: UUID | None = None
    while True:
        queryset = Venue.objects.using(CATALOG).filter(city_ref__isnull=True).exclude(city="")
        if last_id is not None:
            queryset = queryset.filter(pk__gt=last_id)
        venues = list(queryset.order_by("pk")[:batch_size])
        if not venues:
            break
        with transaction.atomic(using=CATALOG):
            for venue in venues:
                city = resolve_city(city=venue.city, country_code=venue.country_code)
                if city is None:
                    continue
                venue.city_ref = city
                venue.save(using=CATALOG, update_fields=["city_ref", "updated_at"])
                write_audit(
                    actor=actor,
                    action="city.venue_resolved",
                    target_type="venue",
                    target_id=venue.pk,
                    details={"city_id": str(city.pk), "slug": city.slug, "written": venue.city},
                )
                venues_resolved += 1
        last_id = venues[-1].pk

    fits_linked = _link_event_fits(batch_size=batch_size)
    return venues_resolved, fits_linked


def _link_event_fits(*, batch_size: int) -> int:
    """Carry each venue's City onto the Event Fit rows written before it had one.

    No audit row and no `computed_at` move: linking a fit to the city it was always in is
    not a recomputation of the fit, and `write_event_fit` documents that a row which still
    says the same thing is not rewritten.
    """
    linked = 0
    last_id: UUID | None = None
    while True:
        queryset = EventFit.objects.using(CATALOG).filter(
            city_ref__isnull=True, event__venue__city_ref__isnull=False
        )
        if last_id is not None:
            queryset = queryset.filter(pk__gt=last_id)
        rows = list(
            queryset.order_by("pk").values_list("pk", "event__venue__city_ref")[:batch_size]
        )
        if not rows:
            return linked
        by_city: dict[UUID, list[UUID]] = {}
        for pk, city_ref_id in rows:
            by_city.setdefault(city_ref_id, []).append(pk)
        with transaction.atomic(using=CATALOG):
            for city_ref_id, pks in by_city.items():
                # One UPDATE per city in the batch, not one per row: a backfill over a large
                # catalog is the whole point of batching, and a per-row write would undo it.
                linked += (
                    EventFit.objects.using(CATALOG)
                    .filter(pk__in=pks)
                    .update(city_ref_id=city_ref_id)
                )
        last_id = rows[-1][0]


__all__ = ["backfill_cities", "count_venues_without_a_city", "resolve_city"]
