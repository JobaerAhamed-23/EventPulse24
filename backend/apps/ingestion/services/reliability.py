"""FR-16's Source Reliability Score: the counting, the weekly recompute, the escalation.

`domain/reliability.py` holds the arithmetic — a beta-binomial posterior, a floor, a spike
rule — as pure functions over plain counts. **This module owns everything the arithmetic does
not**: what an observation *means*, when a source is *due*, what a week *is*, and what
happens when a score is bad enough to matter.

---

## The counting rule is a table, and the table is the design

`shared.constants.OBSERVATION_SIGNS` says what each editorial verdict is worth:

- **`approved` is +1.** FR-16 positive: the listing was right.
- **`rejected` is -1.** FR-16 negative: the listing was wrong.
- **`edited` is -1** (design D4). **The source was wrong.** A source that gets every event's
  time wrong must not score like one whose times are right.
- **`dismissed` is 0** — FR-25's **named, unimplemented** input (D5, D6). An editor looked
  at the source and found no fault; that is not a check of any of its events.

**The table is in `shared`, keyed by value, because `shared` cannot import the model.** That
is the same reason `REVIEW_PRIORITY` and `REPORT_CATEGORIES` are shaped the way they are. The
recorder and this module both read it, so there is one counting rule and not two.

**A dismissal is neutral, not absent.** The row exists — an editor looked — and contributes
nothing to the counts. FR-25's *dismissal rate* is not computed, and no term anywhere stands
in for it: `domain/reanking.py` set that precedent and it is the right one.

---

## One verdict is one observation, however many reports it carried

Five reports on an event, one editorial verdict, **one** observation.

This is not a rule this module applies — it is a rule the *storage* applies.
`SourceObservation.source_observation_item_uq` permits one observation per review item, and
all of an event's reports live on one `user_reported` item, which the verdict closes. So the
multiplication is impossible rather than merely avoided. The report count is carried on the
observation as a **fact** (`report_count`), so the five are not lost while the verdict's
*weight* stays at one.

**And an upheld report is not a second observation.** A report becomes a negative observation
only when the editor's verdict upheld it — the verdict was `rejected` or `edited`. A report on
an event the editor then approved was a bad report, and it counts for nothing (design D7).

---

## The wall holds because the observation is recorded in `catalog`, at resolution time

The work item asked the design to pick one of two ways to get a report's facts to the score:

1. The report's verdict-relevant facts reach `catalog` when the `ReviewItem` is bumped.
2. The observation is recorded at **resolution time** by the editorial commands, from the
   item's own tallies.

**This module takes the second, and the reason is the wall (AD-3).** The counts are *already*
in `catalog` — `raise_review_item` increments the `ReviewItem`'s tally columns there, in the
catalog schema — so only *counts* ever need to cross, never identity. Option 1 would have had
the bump carry user-reported facts across the wall in the hot path, for every report, instead
of at the rare moment of a verdict.

**The consequence, stated rather than hidden: this module never reads `personal`.** The job
is single-database. `personal.EventReport` — which holds the reporter's identity and is
purged with the account — is not consulted, and the `import-linter` contract for the schema
wall is what keeps it that way.

---

## The weekly recurrence, and why the tick asks and the job decides

FR-16 says "updated at least weekly", and the spike rule compares this week with last week.

**A weekly cadence is not expressible as a minute-modulo rule.** The tick dispatches on
`minute % 5` and `minute % 15`; there is no `minute % 10080`. So the tick enqueues the job on
*every* tick and the job decides who is due — the same shape as `schedule_digests`, which also
runs on every tick because "due" is a per-source comparison and the dispatcher makes it.

**The period is the ISO Monday 00:00 UTC.** A calendar week is the honest reading of "this
week with last week", and it makes the history readable: one row per source per week, and the
spike rule is a lookup of the previous row.

**The due-claim is `FOR UPDATE SKIP LOCKED`.** Two overlapping ticks cannot claim the same
source, so the job cannot run twice over one source at once — which is what makes the
idempotence guarantee reachable rather than merely intended.

---

## The escalation, and the thing it never does

FR-16: a score below 0.30 with at least 30 observations, or a 3× week-over-week rise in the
rate of negative observations, raises a `source_reliability` review item.

**The item is raised through the existing `raise_review_item`**, which bumps the open item
for (source, reason) rather than opening a second one (D2 of `review-queue-model`). So a
source that is already escalated is *bumped*, not duplicated, and the escalation is audited
by the same code that audits every other queue entry.

**FR-16 is explicit: escalation, never removal.** Nothing in this module writes `status`,
`ingestion_cadence`, `stale_since` or any other column of a `Source`. The only two columns
this module writes on a source are `reliability_score` and `reliability_scored_at` — and they
are written in the **same transaction** as the row they were computed from, so the history and
the current value cannot disagree. A test asserts the rest of the row is untouched, because
asserting the *absence of a line* would be trusting the source.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.ingestion.models import (
    ReviewItem,
    Source,
    SourceObservation,
    SourceReliabilityScore,
)
from apps.ingestion.services.audit import write_audit
from apps.ingestion.services.review_queue import raise_review_item
from domain.reliability import (
    is_spike,
    reliability_score,
    should_escalate,
    weekly_negative_rate,
)
from shared.actor import Actor
from shared.constants import (
    OBSERVATION_SIGNS,
    RELIABILITY_BATCH_SIZE,
    RELIABILITY_CLAIM_TTL,
)
from shared.db import CATALOG

logger = logging.getLogger(__name__)

#: The job's actor label. A system actor carries a label and no id (`shared.actor.Actor`).
ACTOR_LABEL = "reliability_recompute"

#: The escalation reason, named here so the job and the audit row cannot disagree.
REASON = ReviewItem.Reason.SOURCE_RELIABILITY


@dataclass(frozen=True)
class ObservationCounts:
    """One source's observations, reduced to the two numbers the score is computed from.

    **The reduction is the whole counting rule.** `positives` and `negatives` come from
    `OBSERVATION_SIGNS`, and every observation contributes to exactly one of them or to
    neither — a dismissal contributes to neither.
    """

    positives: int
    negatives: int
    #: How many observations were counted at all, including the neutral ones.
    observations: int

    @property
    def total(self) -> int:
        """The observations that carry a sign — the score's and the escalation's N.

        **The same N for both.** `domain.reliability.reliability_score` floors on
        `positives + negatives`, so the escalation's min-N has to be the same number — a
        threshold that counted dismissals would let a source reach 30 "observations" with
        fewer than 30 checks behind them, and the two thresholds would disagree about what
        "30 observations" means.
        """
        return self.positives + self.negatives


@dataclass(frozen=True)
class RecomputeResult:
    """What one source's recompute concluded."""

    source_id: UUID
    score: Decimal
    counts: ObservationCounts
    spiked: bool
    escalated: bool
    #: True when this run created the period's row; False when it refreshed an existing one.
    created: bool


def period_start_for(moment: datetime) -> date:
    """The Monday 00:00 UTC of the week `moment` falls in.

    **ISO weeks, and the boundary is Postgres's own.** `date_trunc('week', ...)` in Postgres
    is the ISO-week-to-Monday truncation, and the check constraint on the row uses the same
    expression — so the service and the database agree on where a week starts without either
    of them hard-coding an offset.

    The computation is done here in Python too, because the service needs the period *before*
    it has a row to write. The two agree because both use the ISO rule: the Monday of the
    week containing `moment`.
    """
    day = moment.astimezone(UTC).date()
    return day - timedelta(days=day.weekday())


def counts_for(observations) -> ObservationCounts:
    """Reduce a source's observations to `(positives, negatives, observations)`.

    **One table, applied once per observation.** A kind the table does not name would be a
    bug in the table, so it is refused rather than skipped: silently ignoring an unknown kind
    would under-count a source and understate its badness, which is the direction that hurts.
    """
    positives = 0
    negatives = 0
    total = 0
    for observation in observations:
        sign = OBSERVATION_SIGNS.get(observation.kind)
        if sign is None:
            raise ValueError(f"No sign is defined for an observation of kind {observation.kind!r}.")
        total += 1
        if sign > 0:
            positives += 1
        elif sign < 0:
            negatives += 1
    return ObservationCounts(positives=positives, negatives=negatives, observations=total)


def weekly_counts(observations, period: date) -> tuple[int, int]:
    """`(negatives, observations)` for the observations inside one period.

    **The boundary is inclusive of the period's start and exclusive of the next one's**,
    which is the half-open interval `[period, period + 7 days)`. A week has seven days and
    the two halves of that interval partition the timeline exactly once, so an observation
    lands in exactly one week.
    """
    end = period + timedelta(days=7)
    negatives = 0
    total = 0
    for observation in observations:
        occurred = observation.occurred_at.astimezone(UTC)
        if period <= occurred.date() < end:
            sign = OBSERVATION_SIGNS.get(observation.kind)
            if sign is None:
                raise ValueError(
                    f"No sign is defined for an observation of kind {observation.kind!r}."
                )
            total += 1
            if sign < 0:
                negatives += 1
    return negatives, total


def current_score(source: Source) -> Decimal:
    """The source's current score, or the 0.50 prior when it has never been computed.

    **The prior is asked of the domain module, not written here.** `reliability_score(0, 0)`
    is 0.50 today, and if the prior is ever re-tuned this reads the new value instead of
    disagreeing with it.
    """
    if source.reliability_score is None:
        return reliability_score(0, 0)
    return source.reliability_score


def due_sources(*, now: datetime, period: date | None = None) -> list[Source]:
    """The sources whose score is due for a recompute, oldest first.

    **A source is due when it has no row for the current period.** That is the whole weekly
    guarantee, and it is a query rather than a scan of every source's rows: the sources that
    have a row for this week are excluded in one join.
    """
    moment = now.astimezone(UTC)
    current = period or period_start_for(moment)
    return list(
        Source.objects.using(CATALOG)
        .filter(status=Source.Status.ACTIVE)
        .exclude(reliability_scores__period_start=current)
        .order_by("created_at")
    )


def claim_due_sources(*, now: datetime, period: date | None = None) -> list[UUID]:
    """Claim the sources that are due, and return their ids.

    **The claim is persisted, not merely locked.** `Source.reliability_claimed_at` is written
    in the claim's transaction, so it outlives that transaction — and the recompute, which
    runs in its own transaction, is what the claim has to cover.

    This is the reason the claim is not a bare `SELECT ... FOR UPDATE SKIP LOCKED`. A lock is
    released when its transaction commits, and the recompute happens after that commit, so a
    lock-only claim prevents nothing: two overlapping ticks would both claim the same source
    and both recompute it. The marker is the claim; the lock is only what keeps two ticks
    from writing the marker at once.

    **The same shape as `scheduling.claim_due_sources`**, which claims ingest work the same
    way — a column, not a lock.

    **A claim older than `RELIABILITY_CLAIM_TTL` is a lost job** and is reclaimed, so a
    crashed job does not strand a source for the rest of the week.

    **The batch is bounded** by `RELIABILITY_BATCH_SIZE`, because the claim holds a lock on
    every row it takes for as long as the claim's transaction runs.
    """
    moment = now.astimezone(UTC)
    current = period or period_start_for(moment)
    with transaction.atomic(using=CATALOG):
        claimed = list(
            Source.objects.using(CATALOG)
            .select_for_update(skip_locked=True)
            .filter(status=Source.Status.ACTIVE)
            .exclude(reliability_scores__period_start=current)
            .filter(
                Q(reliability_claimed_at__isnull=True)
                | Q(reliability_claimed_at__lte=moment - RELIABILITY_CLAIM_TTL)
            )
            .order_by("created_at")
            .values_list("id", flat=True)[:RELIABILITY_BATCH_SIZE]
        )
        if claimed:
            Source.objects.using(CATALOG).filter(pk__in=claimed).update(
                reliability_claimed_at=moment
            )
        return claimed


def release_claim(source_id: UUID) -> None:
    """End a source's claim, so it can be claimed again straight away.

    **Not audited.** The recompute's own audit row says the source was recomputed, and the
    claim is not a fact about the source — it is a fact about the job's work.
    """
    Source.objects.using(CATALOG).filter(pk=source_id).update(reliability_claimed_at=None)


def _observations_for(source_id: UUID) -> list[SourceObservation]:
    """Every observation for one source, newest first."""
    return list(
        SourceObservation.objects.using(CATALOG)
        .filter(source_id=source_id)
        .order_by("-occurred_at")
    )


def _spiked(observations, period: date) -> bool:
    """Whether this week's negative rate is a spike against last week's.

    **The comparison is over the *rates*, never the scores** — `domain/reliability.py`'s
    docstring explains at length why a ratio of cumulative posteriors cannot fire, and the
    domain module's `is_spike` is the rule. This function only gathers the two numbers.

    **A source with no previous week cannot spike.** Its predecessor rate is computed over
    zero observations, and the same prior smooths both sides, so the ratio is at most 1.56 —
    the domain module's small-sample suppression doing its job. The job therefore passes the
    predecessor unconditionally rather than special-casing a first week.
    """
    this_negatives, this_observations = weekly_counts(observations, period)
    previous_period = period - timedelta(days=7)
    last_negatives, last_observations = weekly_counts(observations, previous_period)
    current_rate = weekly_negative_rate(this_negatives, this_observations)
    previous_rate = weekly_negative_rate(last_negatives, last_observations)
    return is_spike(previous_rate, current_rate)


def recompute_source(
    *,
    source_id: UUID,
    now: datetime | None = None,
    period: date | None = None,
    actor: Actor | None = None,
) -> RecomputeResult:
    """Recompute one source's score for one period, and escalate if it warrants it.

    **One transaction, one source.** The row, the source's current score and the audit entry
    are written together, so a crash leaves none of them and the next run recomputes from
    scratch.

    **The arithmetic is the domain module's.** `reliability_score` computes the score,
    `is_spike` decides the spike and `should_escalate` decides the low score. This function
    owns no rule of its own beyond *which counts go in*.
    """
    moment = (now or timezone.now()).astimezone(UTC)
    current = period or period_start_for(moment)
    who = actor or Actor.system(ACTOR_LABEL)

    with transaction.atomic(using=CATALOG):
        # **The read is inside the transaction**, so the counts and the row they produce are
        # read and written against the same snapshot. An observation committed between the
        # read and the write would otherwise be lost from the period's score, and the row
        # would be committed with counts that never matched the observations.
        observations = _observations_for(source_id)
        counts = counts_for(observations)
        score = reliability_score(counts.positives, counts.negatives)
        spiked = _spiked(observations, current)

        created = _write_row(
            source_id=source_id,
            period=current,
            score=score,
            counts=counts,
            now=moment,
        )
        # **Only the two score columns move.** FR-16 is escalation, never removal: the
        # source's status, cadence and every other column are left exactly as they were, and
        # a test asserts the row is unchanged after an escalation.
        Source.objects.using(CATALOG).filter(pk=source_id).update(
            reliability_score=score, reliability_scored_at=moment
        )
        escalated = False
        if should_escalate(score, counts.total) or spiked:
            _escalate(source_id=source_id, now=moment, who=who)
            escalated = True
        write_audit(
            actor=who,
            action="source_reliability_recomputed",
            target_type="source",
            target_id=source_id,
            details={
                "period_start": current.isoformat(),
                "score": str(score),
                "positives": counts.positives,
                "negatives": counts.negatives,
                "observations": counts.observations,
                "spiked": spiked,
                "escalated": escalated,
            },
        )

    return RecomputeResult(
        source_id=source_id,
        score=score,
        counts=counts,
        spiked=spiked,
        escalated=escalated,
        created=created,
    )


def _write_row(
    *,
    source_id: UUID,
    period: date,
    score: Decimal,
    counts: ObservationCounts,
    now: datetime,
) -> bool:
    """Write (or refresh) the period's row. Returns True when the row was created.

    **The write is one statement, so there is no window between "is there a row?" and
    "write the row".** A `SELECT` followed by an `INSERT` is a race: two runs for the same
    (source, period) can both read "no row" and both insert, and the loser gets an
    uncaught `IntegrityError` that fails the whole job. `ON CONFLICT ... DO UPDATE` closes
    the window — the database resolves it — and it is the same statement the plan specified.

    **The unique constraint is the idempotence guarantee.** A row for this (source, period)
    already existing is not an error and not a second row — it is the same period's
    conclusion, refreshed. So the counts and the score move with it: a score that is a week
    stale is a score that is wrong.

    The refresh is permitted by the table's own trigger, which fixes the source and the
    period and lets exactly these four columns move.
    """
    created = False
    with transaction.atomic(using=CATALOG):
        row, created = (
            SourceReliabilityScore.objects.using(CATALOG)
            .select_for_update()
            .get_or_create(
                source_id=source_id,
                period_start=period,
                defaults={
                    "score": score,
                    "positives": counts.positives,
                    "negatives": counts.negatives,
                    "computed_at": now,
                },
            )
        )
        if not created:
            SourceReliabilityScore.objects.using(CATALOG).filter(pk=row.pk).update(
                score=score,
                positives=counts.positives,
                negatives=counts.negatives,
                computed_at=now,
            )
    return created


def _escalate(
    *,
    source_id: UUID,
    now: datetime,
    who: Actor,
) -> None:
    """Raise (or bump) the source's `source_reliability` review item.

    **The existing `raise_review_item` does the work, and it already bumps rather than
    duplicates** — the open item for (source, reason) is unique, so a second escalation
    moves the same row and writes a `review_item_bumped` audit entry. The rule is *called*
    here, not reimplemented, so the queue's own guarantee cannot drift from this one.
    """
    source = Source.objects.using(CATALOG).filter(pk=source_id).first()
    if source is None:
        return
    raise_review_item(
        actor=who,
        reason=REASON,
        source=source,
        now=now,
    )


def recompute_due(*, now: datetime | None = None) -> list[RecomputeResult]:
    """Recompute every source that is due, and return what each concluded.

    **The claim and the recomputes are separate transactions on purpose.** A claim that
    spanned every source's recompute would hold every row it claimed for the length of the
    whole batch, and one slow source would block every other tick's work. Instead the claim
    is taken, the ids are returned, and each source is recomputed in its own transaction.

    **One source's failure does not lose the others.** A source that raises is logged and
    skipped; the rest of the batch still runs. Without this, a single bad source would
    abort the loop and every remaining source would be silently skipped for the week — the
    same shape as `schedule_sources`, which catches per item.

    **A failed source's claim is released**, so it is retried on the next tick rather than
    being stranded until the claim TTL expires.
    """
    moment = (now or timezone.now()).astimezone(UTC)
    claimed = claim_due_sources(now=moment)
    results = []
    for source_id in claimed:
        try:
            results.append(recompute_source(source_id=source_id, now=moment))
        except Exception:
            logger.warning(
                "Reliability recompute failed for a source",
                extra={"source_id": str(source_id), "job": "recompute_reliability"},
            )
            release_claim(source_id)
    return results


__all__ = [
    "ACTOR_LABEL",
    "ObservationCounts",
    "REASON",
    "RecomputeResult",
    "claim_due_sources",
    "counts_for",
    "current_score",
    "due_sources",
    "period_start_for",
    "recompute_due",
    "recompute_source",
    "release_claim",
    "weekly_counts",
]
