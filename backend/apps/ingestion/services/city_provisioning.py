"""Provisioning a city on first pick: the service that turns a pick into collection.

**What it does, in one sentence.** A reader picks a city; this mints the `City` row, walks
the provider templates, registers a `Source` per spec, and records what happened so the
surface can tell the truth about it.

**What it deliberately does not do.** It does not fetch anything. A registered source with
`last_attempted_at IS NULL` is due immediately, so the existing scheduler takes it on its
next 60-second tick — provisioning's whole job is to make sure the source *exists* by then.

**The write ownership is total (AD-16).** `ingestion` owns `SOURCE` and `CITY`, and this
module is inside `ingestion`, so it writes them. `personalization` reaches it through this
service, never through `apps.ingestion.models` (AD-3's `models-ingestion` contract).

**The city must be in the curated catalog, or nothing happens.** `domain.city_catalog` is
the list of places a reader may pick, and a provider template is a function of a
`CityChoice`. A city outside the catalog has no `CityChoice`, so there is nothing to
resolve — and minting a `City` row for it would put a place into the registry that no
reader chose. The stored preference still says whatever the reader picked; it is simply
not provisioned.

**The lock is on the city, not on a user.** Two readers picking Chittagong at the same
moment must produce one set of sources, not two. `pg_advisory_xact_lock` keyed on the
city's id, in **its own key space** (`b"eventpulse24-cty"`) — a user id and a city id are
both UUIDs, and a hash of one must never be mistaken for a hash of the other.

**A deployment cannot provision what it cannot authenticate.** A Ticketmaster source
without `TICKETMASTER_API_KEY` would be registered, picked up by the scheduler within a
minute, fail with a 401, and burn a slot in the reliability score — for a source that was
never going to work. So a spec whose host needs a credential this deployment does not have
is **skipped**, and the reason is recorded. The decision is driven by
`provider_keys.PROVIDER_KEYS`, so there is exactly one table of "hosts that need a key" and
not a second list here.

**The template stays pure.** `domain.city_providers` describes what a provider *is*; this
module describes what *this installation* can use. The template never asks for a key —
`domain` cannot read `settings` — and the split is what lets the registry stay stdlib-only.

**A failed provisioning is not retried by a later pick.** The row's existence means
"provisioned", whatever its status says. A reader's pick is not a retry request: they did
not know anything failed, and a retry would be invisible to them. A retry belongs to a
person or to the scheduler (the probation job).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from hashlib import blake2b
from urllib.parse import urlsplit
from uuid import UUID

from django.conf import settings
from django.db import connections, transaction

from apps.ingestion.models import CityProvisioning
from apps.ingestion.parsers import PARSERS
from apps.ingestion.services.audit import write_audit
from apps.ingestion.services.cities import resolve_city
from apps.ingestion.services.provider_keys import PROVIDER_KEYS
from apps.ingestion.services.source_registry import register_source
from domain.city_catalog import CityChoice, lookup
from domain.city_providers import SourceSpec, resolve
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL

logger = logging.getLogger(__name__)


#: The advisory-lock key space for city provisioning.
#:
#: **Separate from `digest_preferences`' `_LOCK_PERSON` on purpose.** Both lock on a UUID,
#: and a hash of a user id must never be mistaken for a hash of a city id — the two would
#: then serialise against each other for no reason, and a bug in one would look like a bug
#: in the other.
_LOCK_PERSON = b"eventpulse24-cty"

#: The actor label the provisioning writes its audit rows under.
ACTOR_LABEL = "city_provisioning"


@dataclass(frozen=True)
class ProvisioningOutcome:
    """What a provisioning did, as plain data.

    **Not the model.** The same reason `catalog_read.PublicEvent` is not the model: a
    caller holding a `CityProvisioning` could write it, and `ingestion` is the sole writer
    of `catalog` (AD-16).

    **`city_id` is None when nothing was provisioned** — a city the catalog does not
    hold. There is no city to point at, and inventing one would be a lie about what
    happened.
    """

    city_id: UUID | None
    status: str
    source_count: int
    #: The provisioning row's id, or None when nothing was provisioned.
    provisioning_id: UUID | None = None
    #: The failure that stopped provisioning, when one did.
    error_code: str = ""

    @property
    def provisioned(self) -> bool:
        """Whether a provisioning row now exists for this city."""
        return self.provisioning_id is not None


def _city_lock_key(city_id: UUID) -> int:
    """The advisory-lock key for one city's rows.

    Stable across processes: `blake2b`, never the per-process-salted `hash()`.
    """
    digest = blake2b(str(city_id).encode(), digest_size=8, person=_LOCK_PERSON).digest()
    return int.from_bytes(digest, "big", signed=True)


def _lock_city(city_id: UUID) -> None:
    """Serialise the provisioning of one city.

    **Why an advisory lock and not a row lock.** A row lock can only lock a row that
    exists, and the interesting case is precisely the one where it does not: a city
    nobody has provisioned yet. Two concurrent provisioners would both find nothing to
    lock and both register sources — and the loser would get a raw `IntegrityError` from
    the unique constraint, which reaches the caller as a 500.

    `pg_advisory_xact_lock` is **transaction-scoped**: the lock is released when the
    transaction commits or rolls back, so a crashed worker cannot leave a city wedged.
    """
    with connections[CATALOG].cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_city_lock_key(city_id)])


def _spec_needs_a_key(spec: SourceSpec) -> str:
    """The settings attribute holding the key this spec's host needs, or "".

    **Exact hosts, never suffixes** — the same rule the parser and the key injector use,
    for the same reason: `app.ticketmaster.com.evil.test` must never be handed our key,
    and must never be *assumed* to need one.

    **One table, not two.** `PROVIDER_KEYS` is already the list of hosts that authenticate
    with a query parameter. A second list here would be a second place for the same fact to
    go wrong, and it would be wrong silently.
    """
    try:
        host = (urlsplit(spec.url).hostname or "").lower()
    except ValueError:
        return ""
    provider = PROVIDER_KEYS.get(host)
    if provider is None:
        return ""
    return provider[1]


def _has_its_key(spec: SourceSpec) -> bool:
    """Whether this deployment can authenticate the spec's provider."""
    setting = _spec_needs_a_key(spec)
    if not setting:
        return True  # a host that needs no key is always usable
    return bool(getattr(settings, setting, ""))


def _registerable(specs: tuple[SourceSpec, ...]) -> tuple[list[SourceSpec], list[str]]:
    """The specs this deployment can register, and why the others were skipped.

    **Two reasons a spec is skipped, and both are facts about this installation:**

    - **No credential.** The provider's host needs a key and this deployment has none.
    - **No parser.** `parse()` would answer `unsupported_method`, so the source would
      never ingest. Item 6's registry already guarantees every method it can emit has a
      parser — over the whole cross-product of every city and every template — but the
      check is repeated **at the point of registration**, because that is where the defect
      would bite, and because a future template must not be able to slip past.
    """
    usable: list[SourceSpec] = []
    skipped: list[str] = []
    for spec in specs:
        if spec.acquisition_method not in PARSERS:
            skipped.append(f"no_parser:{spec.acquisition_method}")
            continue
        if not _has_its_key(spec):
            skipped.append(f"no_credential:{_spec_needs_a_key(spec)}")
            continue
        usable.append(spec)
    return usable, skipped


#: Why a city ended with no sources, when **no template covered it at all**.
#:
#: **A different fact from "we could not authenticate the providers we have".** The first
#: is about the *city* — no provider serves Bangladesh, and adding one is a matter of
#: writing a template. The second is about *this installation* — the provider serves the
#: city, and we simply have not been given a key. An operator will want to tell them
#: apart: the first needs a new template, the second needs a secret.
NO_TEMPLATE_COVERS_THIS_CITY = "no_template_covers_this_city"


def provision_city(
    *,
    city_name: str,
    actor: Actor | None = None,
) -> ProvisioningOutcome:
    """Provision the collection for one city: mint it, and register its sources.

    **Idempotent.** A second call for an already-provisioned city registers nothing and
    leaves the status **untouched** — a city that has gone `live` must not be dragged back
    to `collecting` by a reader who picks it again.

    **A failure does not roll back the reader's pick.** The pick is stored by
    `personalization` in a different transaction and a different schema; this one records
    the failure on its own row and returns. The pick stands.

    **Nothing happens for a city the catalog does not hold.** The stored preference keeps
    whatever the reader picked; there is simply nothing to provision.

    **The country comes from the catalog row, never from the caller.** A `country_code`
    parameter would be a second source of truth that could disagree with the row, and a
    disagreement mints a *second* `City` for the same place — the split `domain.cities`
    exists to prevent. The catalog is the only place a city's country is written down.
    """
    actor = actor or Actor.system(ACTOR_LABEL)

    # **The catalog first.** No row, no provisioning — and no `City` row minted for a
    # place no reader chose.
    choice = lookup(city_name)
    if choice is None:
        return ProvisioningOutcome(city_id=None, status="", source_count=0)
    return _provision_choice(choice=choice, actor=actor)


def _provision_choice(*, choice: CityChoice, actor: Actor) -> ProvisioningOutcome:
    """The provisioning for a catalog row."""
    with transaction.atomic(using=CATALOG):
        city = resolve_city(city=choice.name, country_code=choice.country_code)
        if city is None:
            # `resolve_city` returns None only when the text names no city, and the
            # catalog's name always does. Reaching here would mean the two disagree.
            raise RuntimeError(f"The catalog row {choice.name!r} names no city.")

        _lock_city(city.id)

        # **The idempotency check, under the lock.** The lock orders the writers; the
        # re-read is what makes the second one a no-op rather than an exception.
        existing = CityProvisioning.objects.using(CATALOG).filter(city=city).first()
        if existing is not None:
            return ProvisioningOutcome(
                city_id=city.id,
                status=existing.status,
                source_count=existing.source_count,
                provisioning_id=existing.id,
                error_code=existing.last_error_code,
            )

        specs = resolve(choice)
        usable, skipped = _registerable(specs)

        if not usable:
            # **No provider this deployment can use.** A normal outcome — and the reason
            # is recorded, because "no provider serves this city" and "the providers that
            # do serve it need a credential we have not been given" are different facts
            # and an operator will want to tell them apart.
            reason = skipped[0] if skipped else NO_TEMPLATE_COVERS_THIS_CITY
            row = _write_row(
                city=city,
                status=CityProvisioning.Status.NO_PROVIDERS,
                source_count=0,
                error_code=reason,
                actor=actor,
            )
            return ProvisioningOutcome(
                city_id=city.id,
                status=row.status,
                source_count=0,
                provisioning_id=row.id,
                error_code=row.last_error_code,
            )

        registered = 0
        for spec in usable:
            register_source(
                actor=actor,
                name=spec.name,
                source_type=spec.source_type,
                url=spec.url,
                acquisition_method=spec.acquisition_method,
                tz_coverage=spec.tz_coverage,
                # **The catalog's name and the catalog's zone.** The name is what the
                # events are filed under and what the reader picked; the zone is the last
                # link in FR-60's fallback chain (row C1b), so a brand-new city resolves a
                # date-only event time with no registered venue to borrow a zone from.
                city=choice.name,
                city_tz=choice.tz,
            )
            registered += 1

        row = _write_row(
            city=city,
            status=CityProvisioning.Status.COLLECTING,
            source_count=registered,
            error_code="",
            actor=actor,
        )
        return ProvisioningOutcome(
            city_id=city.id,
            status=row.status,
            source_count=registered,
            provisioning_id=row.id,
        )


def _write_row(
    *,
    city,
    status: str,
    source_count: int,
    error_code: str,
    actor: Actor,
) -> CityProvisioning:
    """The provisioning row and its audit row.

    **The audit row carries the city id, never the city name.** AD-13's discipline: the
    row says *that* a city was provisioned and how it went; where a reader lives stays out
    of a log that crosses into `catalog`. (The `Source` rows' own audit rows keep the
    source's city — a source's city is a public fact about a place, and `register_source`
    is FR-13's contract, not this item's to change.)
    """
    row = CityProvisioning.objects.using(CATALOG).create(
        city=city,
        status=status,
        source_count=source_count,
        last_error_code=error_code,
    )
    write_audit(
        actor=actor,
        action="city.provisioned",
        target_type="CityProvisioning",
        target_id=row.id,
        details={
            "city_id": str(city.id),
            "status": status,
            "sources": source_count,
            **({"error_code": error_code} if error_code else {}),
        },
    )
    return row


def provision_city_on_commit(
    *,
    city_name: str,
) -> None:
    """Provision the city once the caller's transaction has committed.

    **The one seam the pick path uses**, for the same reason
    `enqueue_digest_composition_on_commit` is: the row must be committed before the work
    reads it, and a slow registry write must not fail the reader's save.

    **It runs after the commit, in its own transaction.** The pick is written in the
    `personal` schema; the sources are written in the `catalog` schema. Django will not
    enlist two databases in one `atomic()` block, so a transaction spanning both would be
    a lie about what is atomic.

    **`robust=True`: a failure does not roll back the stored city.** The pick stands; the
    status on the provisioning row reflects the failure. That is an AC, and it is the
    difference between a reader who picked a city and got one, and a reader who picked a
    city and lost it because a registry write was slow.

    **Only the name travels.** The country is not passed in: the service reads the city's
    own catalog row, and a country supplied from here could disagree with it — which
    would mint a *second* `City` for the same place. One source of truth, and it is the
    catalog.
    """
    transaction.on_commit(
        lambda: _provision_quietly(city_name=city_name),
        using=PERSONAL,
        robust=True,
    )


def _provision_quietly(*, city_name: str) -> None:
    """Run the provisioning, turning a failure into a recorded one rather than a crash.

    **A failure is recorded, not swallowed.** `robust=True` stops the exception reaching
    the reader; this stops it vanishing entirely — the failure lands on the provisioning
    row's `last_error_code`, so a city that failed to provision looks different from a
    city that was never provisioned.

    **The log carries no city name.** AD-13: a city is weak location data about a real
    person, and the log sink is exactly the place it must not reach. So the warning says
    *that* provisioning failed and nothing about which city.
    """
    try:
        provision_city(city_name=city_name)
    except Exception:
        logger.warning("City provisioning failed")


__all__ = [
    "ACTOR_LABEL",
    "ProvisioningOutcome",
    "provision_city",
    "provision_city_on_commit",
]
