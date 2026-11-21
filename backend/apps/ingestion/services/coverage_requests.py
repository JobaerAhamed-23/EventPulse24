"""The coverage request: a reader asks us to cover a city we have not covered.

**The fallback for the cities automatic collection cannot reach.** When a city's
provisioning says `no_providers`, `failed`, `yielded_nothing` or `paused`, the surface says
so and offers the reader the one way out — ask us to go and cover it. This module is what
that ask becomes: a row, a count, and an audit entry.

**The row is about a place, not about a person.** It holds a `City` foreign key and a
counter, and **no user id anywhere** — the same discipline `CityProvisioning` follows, and
for the same reason. The editorial question is *"how many people want this city covered?"*,
and the answer to that is a number. A per-user answer would put a user id beside a city,
which is the pairing AD-13 is careful about, and nobody could act on it: the reader's own
state is in their own session, and the count is what editorial reads.

**One row per city, and the database says so.** The `UniqueConstraint` on
`CityCoverageRequest.city` is the guarantee — not a promise the service makes. A second
writer that did not know about the first would be stopped by PostgreSQL rather than by a
code path somebody has to remember to write.

**A request never mints a city.** `resolve_city` *creates* a `City`, and this module does
not call it. A request is raised for a city we **already have** — one whose provisioning
failed. A city we have never heard of is a *pick*, and a pick provisions
(`services/city_provisioning.py`), which is a better answer than a request: it does the work
rather than queueing it. **So a request for an unknown city is refused**, with the project's
own unknown-city refusal, and nothing is written.

**The throttle is checked before the idempotence shortcut.** A reader pressing the button
forty times is spending forty attempts, and a limit a repeat could slip past is not a limit.
That is `services/event_reports.py`'s rule, for the same reason.

**The count goes up on a repeat; the row does not change shape.** Two readers asking for
Chittagong is two people wanting it covered, and that is the number editorial prioritises
on. The increment is `F("request_count") + 1` — an atomic database update, not a
read-modify-write in Python, which would lose a concurrent increment.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.ingestion.models import City, CityCoverageRequest
from domain.cities import normalize_city
from domain.errors import ThrottledError, UnknownHomeCityError
from ports.registry import get_throttle_port
from shared.actor import Actor
from shared.constants import COVERAGE_REQUEST_LIMIT, COVERAGE_REQUEST_WINDOW_SECONDS
from shared.db import CATALOG

from .audit import write_audit

#: The audit action. Dotted, in the `city.provisioned` / `city.resumed` family — a
#: city-scoped command on the catalog side.
COVERAGE_REQUEST_ACTION = "city.coverage_requested"


def throttle_key(user_id: UUID) -> str:
    """The throttle key for one reader's coverage requests.

    **Keyed by user, not by IP**, for the same reason `event_reports.throttle_key` is: the
    limit is "5 per reader per day", and the endpoint is session-scoped, so there is always
    exactly one reader. A user id is already an opaque identifier, so unlike the auth keys
    it needs no digest — AD-13 is about addresses.
    """
    return f"coverage_request:{user_id}"


@dataclass(frozen=True)
class CoverageRequestOutcome:
    """What one request produced. Plain data, so the API layer has nothing to map.

    **The city is named, because it goes back to the person who asked.** The name is in
    the *response*, over the reader's own session, which is a different audience from the
    audit log and the catalog row — the same distinction `UnknownHomeCityError`'s
    docstring draws. AD-13 keeps a city out of the audit row and out of the log sink; it
    does not stop the server answering the person who just sent it.
    """

    #: The city that was asked for, as the catalog names it.
    city: str
    #: How many readers have asked for this city, including this one.
    request_count: int
    #: Whether this call is the one that created the row. False for a repeat.
    created: bool


def request_coverage(
    *, city: str, actor: Actor, now: datetime | None = None
) -> CoverageRequestOutcome:
    """Record that a reader asked us to cover this city.

    **Idempotent about the row, not about the count.** A second request for the same city
    does not create a second row — the database would refuse it — but it does move the
    count up, because two readers asking is two people wanting it covered.

    **The throttle is checked first.** A client hammering the button is still spending
    attempts, and a limit that a repeat could slip past is not a limit.

    **The city must already exist.** This is the difference between a request and a pick:
    a request says *"we know this city and we have failed to cover it; please go and cover
    it"*, and a city we have never heard of is handled by picking it — which provisions it
    immediately. A request never mints.

    Raises:
        ThrottledError: The reader has spent their attempts for the window.
        UnknownHomeCityError: We have no such city. The reader should pick it instead.
    """
    moment = now or timezone.now()

    decision = get_throttle_port().check(
        throttle_key(actor.id),
        limit=COVERAGE_REQUEST_LIMIT,
        window_seconds=COVERAGE_REQUEST_WINDOW_SECONDS,
    )
    if not decision.allowed:
        # **The shared `ThrottledError`, not a bespoke one.** `config/errors.py` already
        # maps it to 429 with the `{code, message}` body every other endpoint answers
        # with, so a new exception type here would mean a second mapping that could drift
        # from the first.
        raise ThrottledError(
            "You've asked us to cover enough cities for today. Please try again tomorrow.",
            details={"retry_after_seconds": decision.retry_after_seconds},
        )

    name = (city or "").strip()
    if not name:
        raise UnknownHomeCityError()

    with transaction.atomic(using=CATALOG):
        city_row = _find_city(name)
        if city_row is None:
            # **Refused before anything is written**, so an unknown city leaves no row, no
            # audit row and no count behind. The reader is told to pick the city instead,
            # which is the action that actually covers it.
            raise UnknownHomeCityError()

        row, created = CityCoverageRequest.objects.using(CATALOG).get_or_create(
            city=city_row,
            defaults={"request_count": 1, "created_at": moment},
        )
        if not created:
            # **The count moves atomically in the database**, so two readers asking at the
            # same moment cannot lose an increment between them.
            CityCoverageRequest.objects.using(CATALOG).filter(pk=row.pk).update(
                request_count=F("request_count") + 1, updated_at=moment
            )
            row.refresh_from_db()

        write_audit(
            actor=actor,
            action=COVERAGE_REQUEST_ACTION,
            target_type="CityCoverageRequest",
            target_id=row.id,
            # **The city *id* and the count — never the city name and never a user id.**
            # The name is a location, and the id is not; the count is the number editorial
            # reads. This is the same shape `city.provisioned` and `city.resumed` use.
            details={"city_id": str(city_row.id), "request_count": row.request_count},
        )

    return CoverageRequestOutcome(
        city=city_row.name,
        request_count=row.request_count,
        created=created,
    )


def _find_city(name: str) -> City | None:
    """The `City` with this name, or `None`.

    **A lookup, not a resolution.** `resolve_city` *creates* a `City`, and this module
    must not: a request that minted a city would put a place into the registry that no
    reader chose, and would do it every time somebody asked about a city we had not
    heard of.

    **Two names, one city.** The catalog's canonical name (`"Portland, OR"`) and the
    identity key `domain.cities` computes, for a city a *venue* minted under its own
    spelling. Both are asked in one query, and the exact name wins over the key.
    """
    key = normalize_city(name)
    if not key:
        return None
    return (
        City.objects.using(CATALOG)
        .filter(Q(name=name) | Q(normalized_key=key))
        .order_by("-name", "pk")
        .first()
    )


def read_coverage_request(*, city: str) -> CoverageRequestOutcome | None:
    """The request for this city, or `None` when there is not one.

    **A read, and it never writes.** The same rule `city_status_read` holds: a read that
    minted would put a place into the registry that nobody chose.
    """
    name = (city or "").strip()
    if not name:
        return None
    key = normalize_city(name)
    if not key:
        return None
    row = CityCoverageRequest.objects.using(CATALOG).filter(city__name=name).order_by("pk").first()
    if row is None:
        row = (
            CityCoverageRequest.objects.using(CATALOG)
            .filter(city__normalized_key=key)
            .order_by("pk")
            .first()
        )
    if row is None:
        return None
    return CoverageRequestOutcome(
        city=row.city.name,
        request_count=row.request_count,
        created=False,
    )


__all__ = [
    "COVERAGE_REQUEST_ACTION",
    "CoverageRequestOutcome",
    "read_coverage_request",
    "request_coverage",
    "throttle_key",
]
