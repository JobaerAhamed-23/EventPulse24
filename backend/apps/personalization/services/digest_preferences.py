"""The user's home city and the personal-events opt-out (FR-19, FR-5, FR-8).

Two stored preferences, both columns on `DigestPreference`:

- **the home city** — the city the digest ranks "nearby" against, and the city the
  empty state names. It is stored in the **catalog's own spelling**, because the events
  are filed under that spelling.
- **the personal-events opt-out** — a boolean, defaulting to *included*, because PRD
  `[ASSUMPTION-7]` makes personal events opt-out rather than opt-in.

**Why the city exists at all.** The composition service runs in the worker (AD-11),
where there is no request and therefore no headers. `GeoPort.resolve_city` takes "a bag
of headers, not a request", by deliberate design — so the city must already be stored
by the time the job runs. Nothing in this module reads a header at composition time.

**Which cities may be stored, and why the answer changed.** The rule used to be the
preview's: `list_supported_cities()` says which cities the catalog can serve *right
now*, and anything else was stored as `PREVIEW_FALLBACK_CITY`. That made the picker a
mirror of the catalog — a city could only be picked once something had been ingested in
it, so a city nobody had picked was never collected — and it made the server answer a
reader who chose Chittagong with New York City.

The rule now is the **curated catalog** in `domain.city_catalog`: the answer to *"which
places may a reader choose?"*, which is the same whether or not one event has ever been
ingested there. It is the same table the picker is populated from
(`GET /api/public/cities`), so a city on offer is a city that resolves. The preview's
coverage list still answers the preview's question — *"which cities can the preview serve
today?"* — and this module no longer reads it, which is what removes the hazard of two
rules for one question that could disagree.

**The stored city is the picked city.** A city the reader chose is stored **exactly as
picked**, and a city outside the catalog is **refused** — not silently rewritten. The
exceptions are the cities **nobody chose**: a *geo* city, which falls back exactly as it
always did, and the local dev seed's *fictional* city, which the server chose and so
stores verbatim. The distinction is the point, and `resolve_home_city` is where it lives.

**The import is legal.** `domain.city_catalog` is a `domain` module, and the AD-2 layers
contract points inward — `apps` may import `domain`. The `models-ingestion` contract
protects `apps.ingestion.models` — the *models* module — not the services.

**The city is never logged (AD-13).** It is weak location data about a real person.
It is not in `__str__`, and it is not in the audit row's `details` — the audit row
records *that* the city changed, and the value stays out of the log. A refused city is
in the API error and nowhere else.

Design: .specs-fire/intents/pulse-digest-and-trust/work-items/
digest-user-preferences-design.md (decisions D1-D14).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, time
from hashlib import blake2b
from uuid import UUID

from django.db import connections, transaction

from apps.personalization.models import DigestPreference
from apps.personalization.services.audit import write_audit
from apps.personalization.services.digest_enqueue import (
    enqueue_digest_composition_on_commit,
)
from domain.city_catalog import lookup
from domain.errors import UnknownHomeCityError
from shared.actor import Actor
from shared.constants import GEO_CITY_MAX_LENGTH, PREVIEW_FALLBACK_CITY
from shared.db import PERSONAL

#: The advisory-lock key space for these commands.
#:
#: The **same** person bytes as `onboarding.py`'s lock, because the same user is being
#: written and the two command families must not race each other: onboarding writes
#: this row, and this module writes it too, and two writers that took different locks
#: would both find no row and both insert.
_LOCK_PERSON = b"eventpulse24-onb"

#: The sources a city can arrive from, in the model's vocabulary.
SOURCE_GEO = "geo"
SOURCE_CHOICE = "choice"
SOURCE_FALLBACK = "fallback"
SOURCE_BACKFILL = "backfill"

#: A city the **server** chose — the local dev seed's fixture city, and nothing else.
#:
#: It is not one of the model's four, because the model's four describe how a *reader's*
#: city arrives: a header, a pick, a gap, a backfill. The seed is not a reader. It
#: authors a fictional city for a local walk-through, and the value it writes is stored
#: verbatim because **the server chose it** — which is exactly the reasoning that already
#: exempts the fallback from the catalog check.
SOURCE_SEED = "seed"


def _user_lock_key(user_id: UUID) -> int:
    """The advisory-lock key for one user's rows.

    Stable across processes: `blake2b`, never the per-process-salted `hash()`.
    """
    digest = blake2b(str(user_id).encode(), digest_size=8, person=_LOCK_PERSON).digest()
    return int.from_bytes(digest, "big", signed=True)


def _lock_user(user_id: UUID) -> None:
    """Serialise the commands for one user.

    **Why an advisory lock and not a row lock.** A row lock can only lock a row that
    exists, and the interesting case is precisely the one where it does not: a user who
    has never set a digest preference. Two concurrent writers would both find nothing
    to lock and both insert — and the loser gets a raw `IntegrityError` from the unique
    constraint, which reaches the caller as a 500.

    `pg_advisory_xact_lock` is **transaction-scoped**: the lock is released when the
    transaction commits or rolls back, so a crashed worker cannot leave a user's
    preference wedged.
    """
    with connections[PERSONAL].cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_user_lock_key(user_id)])


def _read_preference(user_id: UUID) -> DigestPreference | None:
    """The user's digest preference, if they have one."""
    return DigestPreference.objects.using(PERSONAL).filter(user_id=user_id).order_by("id").last()


def resolve_home_city(
    *,
    city: str | None,
    source: str,
    now: datetime,
) -> tuple[str | None, str | None]:
    """The city to store, and the source to store with it.

    **The rule, in one place.** A city in the curated catalog is stored in the catalog's
    own spelling, with the source it arrived under. A city **not** in the catalog is
    refused — loudly, and with nothing written — when the reader chose it, and falls
    back to `PREVIEW_FALLBACK_CITY` when nobody did.

    **The choice-versus-geo distinction is the whole of this function.** Two callers
    reach it and they are not the same kind of caller:

    - the reader picking from the dropdown (`source="choice"`) — their choice is
      authoritative, and a city outside the catalog is a **client bug**. So it is
      refused: the caller is told, and nothing is stored. Storing the fallback instead
      would answer the reader with a city they did not choose while appearing to
      succeed, and the heading would then lie about where they are.
    - the edge's geo header (`source="geo"`) — **nobody chose it**. An uncoverable value
      falls back silently, exactly as it always has, because refusing it would turn an
      edge's guess into a 4xx on a path the reader never asked for.

    **And a third caller, the server itself** (`source="seed"`): the local dev seed
    authors a *fictional* city for a walk-through, and the value is stored **verbatim**.
    The reasoning is the same one that exempts the fallback: the server chose it, so
    there is no reader to mislead and no rule to break. It is not in the model's
    four-source vocabulary because those four describe how a *reader's* city arrives.

    **The refusal raises before anything is written**, so it leaves no `DigestPreference`
    row and no audit row behind.

    **An absent city stays absent.** `city=None` means "we do not know", and that is a
    real state — it is what an account has before the backfill, and what a user who
    declined location inference has. Storing the fallback for it would be storing an
    inferred city for someone who declined inference, which is the one thing this
    module will not do. It is also **not** a refusal: nothing was wrong with the request.

    The city is length-bounded by the same constant the geo adapter uses, because a
    city name is a city name whichever way it arrived, and an over-long value is an
    attempt to put a value somewhere it should not go.

    `now` is not read. The catalog does not change with the clock — that is the whole
    difference between it and the preview's coverage list, which it replaces. The
    parameter stays because every caller has a `now` to hand and removing it would churn
    them for no gain.
    """
    if city is None:
        return None, None

    if source == SOURCE_SEED:
        # **The server chose this city, so it is stored as it is.** There is no reader to
        # mislead and no catalog rule to break — and the length bound still applies,
        # because a value that long is a value put somewhere it should not go.
        wanted = city.strip()
        if not wanted or len(wanted) > GEO_CITY_MAX_LENGTH:
            return PREVIEW_FALLBACK_CITY, SOURCE_FALLBACK
        return wanted, source

    wanted = city.strip()
    if not wanted or len(wanted) > GEO_CITY_MAX_LENGTH:
        if source == SOURCE_CHOICE:
            raise _refused(city)
        return PREVIEW_FALLBACK_CITY, SOURCE_FALLBACK

    row = lookup(wanted)
    if row is None:
        if source == SOURCE_CHOICE:
            raise _refused(city)
        return PREVIEW_FALLBACK_CITY, SOURCE_FALLBACK

    # The catalog's spelling, not the caller's. "brooklyn" and "Brooklyn" are the same
    # city, and the catalog's is the one the events are filed under.
    return row.name, source


def _refused(city: str) -> UnknownHomeCityError:
    """The refusal for a city the reader chose that the catalog does not hold.

    **The rejected city is in `details`, not in the message.** The message is for a
    person and stays calm; the value is machine-readable data the client needs in order
    to re-select. AD-13 keeps the city out of the audit log and out of the log sink,
    which is a different audience from the reader who just sent it.
    """
    return UnknownHomeCityError(
        details={
            "errors": [
                {"loc": ["city"], "msg": UnknownHomeCityError.default_message},
            ],
            "rejected_city": city,
        },
    )


def store_fallback_city(
    *,
    user_id: UUID,
    source: str,
    actor: Actor,
    now: datetime,
) -> DigestPreference:
    """Store the fallback city, under the source the caller names.

    **The fallback is not catalog-checked, because the server chose it.** Every other
    path into this module hands a *caller's* city to `resolve_home_city`, which asks the
    catalog whether it holds it — and a city it does not hold is refused (a choice) or
    replaced by the fallback (a geo guess). Applying that rule to the fallback itself
    would be circular: the fallback is by definition the city the catalog may not hold,
    so it would be refused, and the backfill would be unable to record what it did — a
    backfilled city would be indistinguishable from a city the catalog rejected.

    So the fallback is stored **as it is**, with the source the caller names — `backfill`
    for the management command, `fallback` for a geo city the catalog does not hold.
    """
    with transaction.atomic(using=PERSONAL):
        _lock_user(user_id)
        preference = _write_preference(
            user_id=user_id,
            city=PREVIEW_FALLBACK_CITY,
            city_source=source,
            set_city=True,
        )
        _write_city_audit(actor=actor, preference=preference, has_city=True, now=now)

    return preference


def set_home_city(
    *,
    user_id: UUID,
    city: str | None,
    source: str,
    actor: Actor,
    now: datetime,
) -> DigestPreference:
    """Set the user's home city, and write the audit row.

    **The city value is not in the audit details.** AD-13's discipline: a city is weak
    location data about a real person. The audit row says *that* the city changed —
    which is what an audit row is for — and the value stays out of the log.

    **An absent city clears the stored one**, because "the user has no city" is a
    state the digest handles (the nearby slot falls back to the timezone). It is not
    the same as leaving the city alone, and it is explicit here rather than inferred
    from an omitted field at the API edge.

    **A refused city writes nothing.** `resolve_home_city` raises before this opens a
    transaction, so a city the reader chose that the catalog does not hold leaves no
    preference row, no audit row and no recomposition behind.
    """
    resolved_city, resolved_source = resolve_home_city(city=city, source=source, now=now)

    with transaction.atomic(using=PERSONAL):
        _lock_user(user_id)
        preference = _write_preference(
            user_id=user_id,
            city=resolved_city,
            city_source=resolved_source,
            set_city=True,
        )
        _write_city_audit(
            actor=actor,
            preference=preference,
            has_city=resolved_city is not None,
            now=now,
        )
        # **The city is the nearby slot's filter, so changing it changes the pool.** A
        # user who sets their city and finds "No qualifying events in <the old city>"
        # still on today's digest is being told something the product can already see is
        # false. The recomposition replaces the day's digest only while it is **empty**,
        # so a user with cards keeps the cards they were shown (AD-10).
        enqueue_digest_composition_on_commit(user_id)

    return preference


def _write_city_audit(
    *,
    actor: Actor,
    preference: DigestPreference,
    has_city: bool,
    now: datetime,
) -> None:
    """The audit row for a city change — and **not the city**.

    AD-13's discipline: a city is weak location data about a real person. The action
    name says the city changed; the value is one read of the row away, and is under the
    same access control as the row itself.

    **`has_city` and not the value.** The row answers "did the user end up with a
    city?", which is the question an audit reader has, and it answers it without writing
    where the user lives into a log that crosses into `catalog`.
    """
    write_audit(
        actor=actor,
        action="preferences.home_city_set",
        target_type="DigestPreference",
        target_id=preference.id,
        details={"has_city": has_city, "at": now.isoformat()},
    )


def set_include_personal_events(
    *,
    user_id: UUID,
    include: bool,
    actor: Actor,
    now: datetime,
) -> DigestPreference:
    """Set whether personal events appear in the user's digest (FR-19).

    **The boolean is in the audit details**, because it is not location data and
    "did they opt in or out" is exactly the question an audit row should answer.
    """
    with transaction.atomic(using=PERSONAL):
        _lock_user(user_id)
        preference = _write_preference(
            user_id=user_id,
            include_personal_events=include,
        )
        write_audit(
            actor=actor,
            action="preferences.personal_events_set",
            target_type="DigestPreference",
            target_id=preference.id,
            details={"include_personal_events": include, "at": now.isoformat()},
        )

    return preference


def _write_preference(
    *,
    user_id: UUID,
    city: str | None = None,
    city_source: str | None = None,
    include_personal_events: bool | None = None,
    set_city: bool = False,
) -> DigestPreference:
    """Write the preference — one row per user, so this is an upsert.

    **The caller holds the user's advisory lock**, so a concurrent writer for the same
    user has already waited and committed: the lookup below sees that writer's row, and
    the update path is taken. Without the lock, two writers would both find no row and
    both insert — and the loser of that race would get a raw `IntegrityError` from the
    unique constraint, which reaches the caller as a 500.

    **A `None` argument means "leave it alone", except for the city, which carries its
    own flag.** `set_city=True` says *this call is about the city*; then `city=None`
    means **clear it** — the user genuinely has no city, which is a real state the
    digest handles. `set_city=False` (the default) means the city is not this call's
    business and the stored value is untouched.

    The distinction needs a flag because `None` alone cannot carry both meanings: the
    opt-out path has to *remove* a stored city, and an unrelated command must not be
    able to remove it by accident. A sentinel would have to mean "clear" in one call
    and "leave alone" in another, which is exactly the ambiguity the flag removes.
    """
    existing = _read_preference(user_id)

    if existing is None:
        return DigestPreference.objects.using(PERSONAL).create(
            user_id=user_id,
            delivery_time=_default_delivery_time(),
            timezone="UTC",
            city=city if set_city else None,
            city_source=city_source if set_city else None,
            include_personal_events=(
                True if include_personal_events is None else include_personal_events
            ),
        )

    fields: list[str] = []
    if set_city:
        # A cleared city is written as two nulls, so the check constraint holds.
        existing.city = city
        existing.city_source = city_source
        fields.extend(["city", "city_source"])

    if include_personal_events is not None:
        existing.include_personal_events = include_personal_events
        fields.append("include_personal_events")

    if fields:
        existing.save(using=PERSONAL, update_fields=fields)
    return existing


def _default_delivery_time() -> time:
    """The delivery time a newly-created preference starts with.

    Only reached when a preference is created by a command that did not set one — the
    sign-up path, which knows the city but not when the user wants their digest. The
    onboarding flow overwrites both when the user reaches step 3.
    """
    return time(9, 0)


def backfill_home_cities(*, now: datetime, actor: Actor) -> tuple[int, int]:
    """Give every account without a city the fallback city.

    **Idempotent.** Running it twice writes the same value twice, not two rows: the
    write is an upsert on the one row per user, and it **never overwrites a city that
    is already set** — so a user who has picked a city keeps it, and a second run
    changes nothing.

    **It writes the fallback**, because it has no better information: there is no geo
    header in a management command, and the accounts it fills were created before this
    item existed. The source is recorded as `backfill`, so the digest can tell a
    backfilled city from one the user chose.

    Returns `(written, seen)` — how many rows were written, and how many were examined.
    """
    missing = list(
        DigestPreference.objects.using(PERSONAL)
        .filter(city__isnull=True)
        .values_list("user_id", flat=True)
    )

    written = 0
    for user_id in missing:
        store_fallback_city(
            user_id=user_id,
            source=SOURCE_BACKFILL,
            actor=actor,
            now=now,
        )
        written += 1

    return written, len(missing)


def count_users_without_a_city() -> int:
    """How many accounts have no city — the backfill's `--dry-run` count."""
    return DigestPreference.objects.using(PERSONAL).filter(city__isnull=True).count()


__all__ = [
    "SOURCE_BACKFILL",
    "SOURCE_CHOICE",
    "SOURCE_FALLBACK",
    "SOURCE_GEO",
    "SOURCE_SEED",
    "backfill_home_cities",
    "count_users_without_a_city",
    "resolve_home_city",
    "set_home_city",
    "set_include_personal_events",
    "store_fallback_city",
]


@dataclass(frozen=True)
class DeliverySettings:
    """When and where a user's digest is due — the half `delivery` needs (AD-7).

    Plain data, never a model instance: `personalization` owns `DIGEST_PREFERENCE` (AD-16) and
    a caller holding the model could write it.

    **The zone is the reason this read exists.** `delivery` computes every `due_at` through
    `domain.quiet_hours`, which needs the user's IANA zone — and the zone lives here, on
    `DIGEST_PREFERENCE`, deliberately kept in one place so it cannot drift from a second copy
    (see `NotificationPreference`'s docstring). This is the published interface `delivery`
    reads it through, once per command rather than once per row.
    """

    user_id: UUID
    delivery_time: time
    timezone: str


def get_delivery_settings(*, user_id: UUID) -> DeliverySettings | None:
    """This user's digest delivery time and zone, or None if they have no preference row.

    None is a real state — an account that predates the preference, or one that has not
    finished onboarding. The caller decides what to do with it; `delivery` falls back to the
    constants rather than guessing a zone, because a guessed zone sends a reminder at the
    wrong hour and looks like a bug in the reminder rather than in the guess.
    """
    row = _read_preference(user_id)
    if row is None:
        return None
    return DeliverySettings(
        user_id=row.user_id, delivery_time=row.delivery_time, timezone=row.timezone
    )


def get_delivery_settings_for(*, user_ids: Sequence[UUID]) -> dict[UUID, DeliverySettings]:
    """The same, for many users in **one** query.

    The batched form exists so a command that touches many users' sends reads zones once
    rather than once per user — the same move `catalog_read.get_public_events` makes for
    titles. A user with no preference row is simply absent from the map.
    """
    rows = DigestPreference.objects.using(PERSONAL).filter(user_id__in=list(user_ids))
    return {
        row.user_id: DeliverySettings(
            user_id=row.user_id, delivery_time=row.delivery_time, timezone=row.timezone
        )
        for row in rows
    }
