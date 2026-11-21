"""The probation: what happens to a provisioned city whose sources publish nothing.

**What it does, in one sentence.** After each ingest run of a provisioned source, it moves
that source's zero-yield counter and — at the threshold — pauses the source, and if every
source of the city is paused that way, marks the city `yielded_nothing`.

**What it deliberately does not do.** It does not fetch anything, and it does not rescue
anything. A source that published nothing three times running is paused, and the city says
so. The surface stops claiming "collecting" about something that is not going to happen.

**A fetch failure is not a zero-yield run.** A run that never reached the feed proves
nothing about the feed's contents, so it does not move the counter. `ingest_source` already
separates `fetch_failed` / `parse_failed` / `not_modified` / `ok`; the probation is built on
those outcomes rather than on a fresh count of published rows.

**`live` is terminal.** A city that has published once stays `live` forever, even if its
sources later go quiet. A quiet covered city (state B) and a city that never produced
anything (state C) are different facts, and `browse-states.tsx` already insists on the
distinction.

**It runs in the ingest path, not on a timer.** A city that yields nothing should say so the
moment it is known, not up to a tick later. The probation is invoked from `ingest_source`
after the run's transaction commits, and from `source_registry` after a source's status
changes.

**The write ownership is total (AD-16).** `ingestion` owns `SOURCE`, `CITY` and
`CITY_PROVISIONING`, and this module is inside `ingestion`, so it writes them.

**The city's name never reaches the audit log or the logger.** The probation's audit row
carries `city_id` and the status, never the name — AD-13's discipline, and the log sink is
exactly the place a person's weak location data must not reach.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from django.db import transaction

from apps.ingestion.models import CityProvisioning, Source
from apps.ingestion.services.audit import write_audit
from apps.ingestion.services.source_registry import pause_source
from shared.actor import Actor
from shared.constants import (
    PUBLISHED_COUNT_KEYS,
    YIELDED_COUNT_KEYS,
    ZERO_YIELD_RUN_THRESHOLD,
)
from shared.db import CATALOG

logger = logging.getLogger(__name__)

#: The actor label the probation writes its audit rows under.
ACTOR_LABEL = "city_probation"

#: The audit action for a city whose provisioning status changed.
PROBATION_ACTION = "city.probation"


class CounterEffect(StrEnum):
    """What one run does to a source's zero-yield counter.

    **Three effects, not two.** "This run does not count toward the threshold" and "this
    run clears the counter" are different claims, and a 304 needs the first without the
    second.
    """

    #: The counter goes back to zero — the run produced something.
    RESET = "reset"
    #: The counter goes up by one — the run reached the feed and produced nothing.
    INCREMENT = "increment"
    #: The counter does not move — the run proved nothing either way.
    LEAVE = "leave"


@dataclass(frozen=True)
class RunClassification:
    """What one ingest run's outcome means for the zero-yield probation."""

    #: What this run does to the source's zero-yield counter.
    counter_effect: CounterEffect
    #: Whether this run published an event — only `new` and `superseded` do.
    published: bool
    #: Whether the fetch reached the feed and produced something usable.
    yielded: bool


@dataclass(frozen=True)
class ProbationOutcome:
    """What a probation decided, as plain data.

    **Not the model.** The same reason `ProvisioningOutcome` is not the model: a caller
    holding a `CityProvisioning` could write it, and `ingestion` is the sole writer of
    `catalog` (AD-16).
    """

    #: The source the probation was about.
    source_id: UUID
    #: The city it belongs to, or None when it belongs to none.
    city_id: UUID | None = None
    #: The source's status after the probation — "active" or "paused".
    source_status: str = Source.Status.ACTIVE
    #: The zero-yield counter after the probation.
    zero_yield_runs: int = 0
    #: The city's provisioning status after the probation, or "" when there is none.
    city_status: str = ""
    #: Whether this call paused the source.
    paused: bool = False
    #: Whether this call changed the city's status.
    city_changed: bool = False


def published_something(counts: Mapping[str, int]) -> bool:
    """Whether this run **published** an event.

    **Publication is narrow on purpose.** Only `new` and `superseded` put a row into the
    catalogue for the first time. `updated` and `silent_updated` re-affirm a row that is
    already there; `unchanged` recognises one; `bound_other_source` says the event is in
    the catalogue because *another* source published it.

    Only publication can move a city to `live`. Yield cannot: a city whose sources all
    re-affirm the same three events forever is covered and producing, but it never
    *published* anything, and "live" must mean "there are events in this city's
    catalogue".
    """
    return any(counts.get(key, 0) > 0 for key in PUBLISHED_COUNT_KEYS)


def yielded_something(counts: Mapping[str, int]) -> bool:
    """Whether this run's fetch reached the feed and produced anything usable.

    **`unchanged` counts.** A source that re-reports events it already published is not a
    zero-yield run — and it is what a *healthy* source returns on every poll after the
    first. Without this, every healthy source would accrue a zero-yield run per poll and
    be paused after twelve hours of doing its job perfectly.
    """
    return any(counts.get(key, 0) > 0 for key in YIELDED_COUNT_KEYS)


def classify_run(outcome: str, counts: Mapping[str, int]) -> RunClassification:
    """Classify one run's outcome for the probation.

    **A pure function.** No database, no clock, no actor — so it can be exhaustively
    unit-tested, and so `ingest_source` can call it *inside* its transaction while
    `probate_after_run` calls the same logic *after* it. One classification, two call
    sites, no drift.

    | outcome | effect | why |
    |---|---|---|
    | `ok`, yielded something | reset | the feed gave us something |
    | `ok`, yielded nothing | increment | the honest zero-yield run |
    | `not_modified` | leave | a 304 proves neither emptiness nor content |
    | `fetch_failed` / `parse_failed` | leave | the run never reached the feed |

    **`not_modified` leaves the counter alone rather than resetting it.** The AC says a run
    "that never reached the feed must not count toward the zero-yield probation" — a 304
    *did* reach the feed, so it is not a zero-yield run. But it is also not evidence that
    the previous zero-yield runs were wrong. Resetting on a 304 would let a source
    alternate "empty" and "304" forever and never be condemned. **Leave** is the only
    effect that moves the counter only on evidence.
    """
    if outcome == "ok":
        published = published_something(counts)
        yielded = yielded_something(counts)
        return RunClassification(
            counter_effect=CounterEffect.RESET if yielded else CounterEffect.INCREMENT,
            published=published,
            yielded=yielded,
        )
    if outcome == "not_modified":
        return RunClassification(counter_effect=CounterEffect.LEAVE, published=False, yielded=True)
    return RunClassification(counter_effect=CounterEffect.LEAVE, published=False, yielded=False)


def probation_actor() -> Actor:
    """The actor the probation writes its audit rows under."""
    return Actor.system(ACTOR_LABEL)


def _source_is_active(source: Source) -> bool:
    return source.status == Source.Status.ACTIVE


def probate_after_run(
    *,
    source: Source,
    outcome: str,
    counts: Mapping[str, int],
    zero_yield_runs: int,
    actor: Actor,
) -> ProbationOutcome:
    """Apply one run's outcome to a source's zero-yield counter, and maybe more.

    **Called after the ingest run's transaction has committed.** The counter itself is
    moved inside `ingest_source`'s transaction; this call does the *city-wide*
    consequence, and it must not hold the source's row lock while it does.

    **Why after the commit.** Two concurrent runs of two different sources of the same
    city would each hold their own source's row lock while reaching for the city — and
    would deadlock. After the commit the row locks are released and the probation takes
    the rows one at a time, in a deterministic order.

    **A source with no city is not provisioned.** A hand-registered seed has no
    `city_ref`; it gets its counter moved but never a city consequence.
    """
    city_id = source.city_ref_id
    base = ProbationOutcome(
        source_id=source.id,
        city_id=city_id,
        source_status=source.status,
        zero_yield_runs=zero_yield_runs,
    )

    # An already-paused source is out of scope: its counter is frozen, and the city has
    # already been told about it.
    if not _source_is_active(source):
        return base

    classification = classify_run(outcome, counts)

    if classification.published:
        # **A published run makes the city `live`, and only a published run does.**
        # `probate_city` is not called here: it would re-derive `collecting` from the
        # sources, and a city that has just published is `live`.
        if city_id is not None:
            city_status, changed = _mark_city_live(city_id=city_id, actor=actor)
            return ProbationOutcome(
                source_id=source.id,
                city_id=city_id,
                source_status=source.status,
                zero_yield_runs=zero_yield_runs,
                city_status=city_status,
                city_changed=changed,
            )
        return base

    if outcome != "ok":
        # A failed run, or a 304. Neither is a zero-yield run, and neither moves the
        # counter — so there is nothing to do.
        return base

    if zero_yield_runs < ZERO_YIELD_RUN_THRESHOLD:
        # Not yet condemned. The city may still need re-deciding (another source may have
        # been paused by hand since), so it is re-decided — but no source is paused.
        if city_id is None:
            return base
        city_status, changed = _probate_city_status(city_id=city_id, actor=actor)
        return ProbationOutcome(
            source_id=source.id,
            city_id=city_id,
            source_status=source.status,
            zero_yield_runs=zero_yield_runs,
            city_status=city_status,
            city_changed=changed,
        )

    # **The threshold.** The source is paused through the registry — audited, never
    # deleted (FR-13) — and then the city is re-decided.
    #
    # **Two transactions, never nested.** `pause_source` opens its own atomic block and
    # writes its own audit row; `_probate_city_status` opens another. Nesting them would
    # hold the source's lock while taking the provisioning row's — the lock order a
    # concurrent hand-pause would invert.
    pause_source(
        actor=actor,
        source_id=source.id,
        reason=Source.PausedReason.ZERO_YIELD,
    )
    city_status = ""
    changed = False
    if city_id is not None:
        city_status, changed = _probate_city_status(city_id=city_id, actor=actor)
    return ProbationOutcome(
        source_id=source.id,
        city_id=city_id,
        source_status=Source.Status.PAUSED,
        zero_yield_runs=zero_yield_runs,
        city_status=city_status,
        paused=True,
        city_changed=changed,
    )


def _mark_city_live(*, city_id: UUID, actor: Actor) -> tuple[str, bool]:
    """Move a city to `live`, and report whether it moved.

    **`live` is terminal.** A city that has published once has published; a later drought
    does not unpublish it, and the surface's state B ("covered, quiet") is strictly more
    informative than state C ("never produced anything").

    **A city with no provisioning row is not provisioned.** Nothing to say, and nothing
    written.
    """
    with transaction.atomic(using=CATALOG):
        provisioning = (
            CityProvisioning.objects.using(CATALOG)
            .select_for_update()
            .filter(city_id=city_id)
            .first()
        )
        if provisioning is None:
            return "", False
        if provisioning.status == CityProvisioning.Status.LIVE:
            return provisioning.status, False
        # `no_providers` and `failed` are facts about *why there are no sources*. A city
        # with no sources cannot have published an event, so this is unreachable in
        # practice — and the guard is here because "unreachable" is a claim, not a proof.
        if provisioning.status in (
            CityProvisioning.Status.NO_PROVIDERS,
            CityProvisioning.Status.FAILED,
        ):
            return provisioning.status, False
        provisioning.status = CityProvisioning.Status.LIVE
        provisioning.save(using=CATALOG, update_fields=["status", "updated_at"])
        _write_probation_audit(
            actor=actor,
            provisioning=provisioning,
            details={
                "city_id": str(city_id),
                "status": CityProvisioning.Status.LIVE,
                "sources": provisioning.source_count,
            },
        )
        return provisioning.status, True


def _probate_city_status(*, city_id: UUID, actor: Actor) -> tuple[str, bool]:
    """Decide what a city's provisioning status should be, given its sources.

    **The rule, in full.**

    1. A city with no provisioning row is not provisioned — nothing to say.
    2. A city whose status is `live` **stays `live`**. Always. A quiet covered city is
       state B and must not be confused with state C.
    3. A city whose status is `no_providers` or `failed` keeps it. Those are facts about
       *why there are no sources*, and a probation run cannot improve on them.
    4. If **any** source of the city is paused by hand, the city becomes `paused`. An
       editor paused it; the cause is a decision, and the surface says so.
    5. Otherwise, if **every** source of the city is paused for zero yield (and there is
       at least one source), the city becomes `yielded_nothing`.
    6. Otherwise the city is `collecting`.

    **A city with no sources at all is not `yielded_nothing`.** That is `no_providers` — a
    more specific fact: "we never tried", not "we tried and got nothing". Overwriting it
    would tell the surface the city was tried and failed, when in fact nothing was ever
    registered for it. `yielded_nothing` requires **at least one source that was tried
    and gave nothing**.

    **A source paused with no reason is treated as a hand-pause.** "Somebody paused this"
    is a stronger claim than "the probation paused this", and only the probation's pauses
    should produce `yielded_nothing`.
    """
    with transaction.atomic(using=CATALOG):
        provisioning = (
            CityProvisioning.objects.using(CATALOG)
            .select_for_update()
            .filter(city_id=city_id)
            .first()
        )
        if provisioning is None:
            return "", False
        if provisioning.status == CityProvisioning.Status.LIVE:
            return provisioning.status, False
        if provisioning.status in (
            CityProvisioning.Status.NO_PROVIDERS,
            CityProvisioning.Status.FAILED,
        ):
            return provisioning.status, False

        sources = list(Source.objects.using(CATALOG).filter(city_ref_id=city_id))
        if not sources:
            # **Nothing was ever registered for this city.** Leave the status alone.
            return provisioning.status, False

        paused_sources = [s for s in sources if not _source_is_active(s)]
        if any(s.paused_reason != Source.PausedReason.ZERO_YIELD for s in paused_sources):
            # A hand-pause dominates: somebody stopped this on purpose.
            new_status = CityProvisioning.Status.PAUSED
        elif len(paused_sources) < len(sources):
            # Something is still running — the city is still collecting.
            new_status = CityProvisioning.Status.COLLECTING
        else:
            # Every source is paused, and every one of them by the probation.
            new_status = CityProvisioning.Status.YIELDED_NOTHING

        if new_status == provisioning.status:
            return provisioning.status, False

        provisioning.status = new_status
        provisioning.save(using=CATALOG, update_fields=["status", "updated_at"])
        _write_probation_audit(
            actor=actor,
            provisioning=provisioning,
            details={
                "city_id": str(city_id),
                "status": new_status,
                "sources": provisioning.source_count,
            },
        )
        return new_status, True


def _write_probation_audit(*, actor: Actor, provisioning: CityProvisioning, details) -> None:
    """The probation's audit row.

    **The city id, never the city name.** AD-13's discipline: the row says *that* a
    city's provisioning status changed and what it changed to; where a reader lives stays
    out of a log that crosses into `catalog`.
    """
    write_audit(
        actor=actor,
        action=PROBATION_ACTION,
        target_type="CityProvisioning",
        target_id=provisioning.id,
        details=details,
    )


__all__ = [
    "ACTOR_LABEL",
    "CounterEffect",
    "PROBATION_ACTION",
    "ProbationOutcome",
    "RunClassification",
    "classify_run",
    "probation_actor",
    "probate_after_run",
    "published_something",
    "yielded_something",
]
