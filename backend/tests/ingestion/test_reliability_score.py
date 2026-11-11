"""FR-16's score: what an observation is worth, what a week is, and what a re-run does.

The counting rule is the load-bearing decision of this work item, so most of these tests
are about **the sign of each verdict** and about **one verdict counting once**.

---

## The five-reports-one-verdict case

The AC asks how one editorial verdict on an event with five reports is counted, and says
plainly: *"Several reports must not multiply one verdict."* The answer is **once** — and the
interesting part is *how* that is guaranteed. It is not arithmetic applied afterwards; it is
the storage. `SourceObservation.source_observation_item_uq` permits one observation per
review item, and all of an event's reports live on one `user_reported` item, so a verdict on
that event can only ever close one item and record one observation.

So the test asserts two things separately, because they are two different claims:

- **the weight**: the score moves by one negative, not five.
- **the fact**: the report count is still recorded, so the five are not lost.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.db import IntegrityError, transaction

from apps.ingestion.models import (
    Event,
    ReviewItem,
    Source,
    SourceObservation,
    SourceReliabilityScore,
)
from apps.ingestion.services.editorial_review import (
    approve_review_item,
    dismiss_source_item,
    edit_and_publish,
    reject_review_item,
)
from apps.ingestion.services.reliability import (
    counts_for,
    current_score,
    due_sources,
    period_start_for,
    recompute_source,
    weekly_counts,
)
from apps.ingestion.services.review_queue import raise_review_item
from domain.reliability import reliability_score
from shared.actor import Actor
from shared.constants import OBSERVATION_SIGNS
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import EventFactory, SourceFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
EDITOR = Actor.user(uuid4())
SYSTEM = Actor.system("ingest_pipeline")
REPORTER = Actor.system("event_report")

#: The Monday of the week NOW falls in. 2026-11-11 is a Wednesday.
THIS_WEEK = date(2026, 11, 9)
LAST_WEEK = date(2026, 11, 2)


def _observation(
    source: Source, kind: str, *, occurred_at: datetime, item=None
) -> SourceObservation:
    """One observation, for the counting tests that do not need a real verdict behind it."""
    if item is None:
        event = EventFactory(source=source)
        item = raise_review_item(
            event=event, reason=ReviewItem.Reason.IN_REVIEW, actor=SYSTEM, now=occurred_at
        ).item
    return SourceObservation.objects.using(CATALOG).create(
        source=source,
        kind=kind,
        event=item.event,
        review_item=item,
        occurred_at=occurred_at,
        actor_kind=EDITOR.kind,
        actor_id=EDITOR.id,
        actor_label=EDITOR.label,
    )


def _reported_event(source: Source, reports: int = 1) -> tuple[Event, ReviewItem]:
    """An event with `reports` user reports, all on one `user_reported` item."""
    event = EventFactory(source=source)
    item = raise_review_item(
        event=event,
        reason=ReviewItem.Reason.USER_REPORTED,
        category=ReviewItem.ReportCategory.WRONG_VENUE,
        actor=REPORTER,
        now=NOW,
    ).item
    for _ in range(reports - 1):
        item = raise_review_item(
            event=event,
            reason=ReviewItem.Reason.USER_REPORTED,
            category=ReviewItem.ReportCategory.WRONG_DATE_TIME,
            actor=REPORTER,
            now=NOW,
        ).item
    return event, item


# ── The counting table ─────────────────────────────────────────────────────────────────────


def test_the_counting_table_names_every_kind_the_model_can_record():
    """**The table and the model must agree.** A kind the table omits would be counted as
    nothing — silently under-counting a source, which is the direction that hurts."""
    kinds = {kind.value for kind in SourceObservation.Kind}
    assert set(OBSERVATION_SIGNS) == kinds


def test_the_counting_table_holds_the_signs_it_promises():
    """**The signs themselves, not just the set of kinds.**

    `test_the_counting_table_names_every_kind_the_model_can_record` proves the table and
    the model agree on *which* kinds exist. This proves the table says what it says — a
    sign flip (`"rejected": 1`) would pass every other test in the suite, because every
    other test reads the same table to work out what to expect.
    """
    assert OBSERVATION_SIGNS == {
        "approved": 1,
        "rejected": -1,
        "edited": -1,
        "dismissed": 0,
    }


def test_the_escalation_threshold_counts_the_same_observations_the_score_does():
    """**One N, not two.**

    `domain.reliability.reliability_score` floors on `positives + negatives` — a dismissal
    carries no sign, so it is not one of the 30 observations the floor waits for. The
    escalation's min-N has to be the same number, or the two thresholds disagree about what
    "30 observations" means: a source could reach 30 *observations* with fewer than 30
    checks behind them.
    """
    source = SourceFactory()
    _observation(source, SourceObservation.Kind.DISMISSED, occurred_at=NOW)

    counts = counts_for(_observation_rows(source))

    assert counts.observations == 1
    assert counts.total == 0


def test_an_approval_is_positive():
    source = SourceFactory()
    _observation(source, SourceObservation.Kind.APPROVED, occurred_at=NOW)

    counts = counts_for(_observation_rows(source))

    assert counts.positives == 1
    assert counts.negatives == 0


def test_a_rejection_is_negative():
    source = SourceFactory()
    _observation(source, SourceObservation.Kind.REJECTED, occurred_at=NOW)

    counts = counts_for(_observation_rows(source))

    assert counts.negatives == 1
    assert counts.positives == 0


def test_an_edit_is_negative():
    """**The source was wrong** (design D4). A source that gets every event's time wrong
    must not score like one whose times are right."""
    source = SourceFactory()
    _observation(source, SourceObservation.Kind.EDITED, occurred_at=NOW)

    counts = counts_for(_observation_rows(source))

    assert counts.negatives == 1
    assert counts.positives == 0


def test_a_dismissal_is_neutral():
    """FR-25's named, unimplemented input (design D5, D6).

    **Neutral, not absent.** The row exists — an editor looked — and contributes to neither
    count. Treating it as positive would let an editor clear a bad score by dismissing it;
    treating it as negative would punish an editor for doing the review the escalation asked
    for.
    """
    source = SourceFactory()
    _observation(source, SourceObservation.Kind.DISMISSED, occurred_at=NOW)

    counts = counts_for(_observation_rows(source))

    assert counts.positives == 0
    assert counts.negatives == 0
    assert counts.observations == 1


def test_an_unknown_kind_is_refused_rather_than_skipped():
    """**A kind the table does not name is a bug in the table, not a zero.**

    Silently ignoring it would under-count a source and understate its badness — the one
    direction of error that lets a bad source keep being trusted.

    The row is written with an unknown kind directly, because the append-only guard
    refuses to rewrite one — which is the correct behaviour, and the reason the row is
    created rather than updated.
    """
    source = SourceFactory()
    event = EventFactory(source=source)
    item = raise_review_item(
        event=event, reason=ReviewItem.Reason.IN_REVIEW, actor=SYSTEM, now=NOW
    ).item
    SourceObservation.objects.using(CATALOG).create(
        source=source,
        kind="invented",
        event=event,
        review_item=item,
        occurred_at=NOW,
        actor_kind=EDITOR.kind,
        actor_id=EDITOR.id,
        actor_label=EDITOR.label,
    )

    with pytest.raises(ValueError, match="No sign is defined"):
        counts_for(_observation_rows(source))


def _observation_rows(source: Source) -> list[SourceObservation]:
    return list(
        SourceObservation.objects.using(CATALOG)
        .filter(source_id=source.pk)
        .order_by("-occurred_at")
    )


# ── One verdict, one observation ───────────────────────────────────────────────────────────


def test_five_reports_and_one_verdict_count_once():
    """**The case the AC names.** Five reports, one editorial verdict, **one** observation.

    The weight is the assertion that matters: the score moves by one negative, not five.
    """
    source = SourceFactory()
    event, item = _reported_event(source, reports=5)
    assert item.report_count == 5

    reject_review_item(item_id=item.pk, actor=EDITOR, now=NOW)

    observations = _observation_rows(source)
    assert len(observations) == 1
    counts = counts_for(observations)
    assert counts.negatives == 1
    assert counts.negatives != 5


def test_the_five_reports_are_still_recorded_as_a_fact():
    """**The count is not lost — only the weight is not multiplied.**

    The reports themselves live in `personal` and are purged with the account, so the tally
    frozen onto the observation is the only durable record of them.
    """
    source = SourceFactory()
    _event, item = _reported_event(source, reports=5)

    reject_review_item(item_id=item.pk, actor=EDITOR, now=NOW)

    observation = SourceObservation.objects.using(CATALOG).get(review_item=item)
    assert observation.report_count == 5


def test_a_report_on_an_approved_event_counts_for_nothing():
    """**A report the editor contradicted was a bad report** (design D7).

    "Upheld" means the verdict upheld it. An approval says the listing was fine, so the
    report was wrong, and it contributes nothing.
    """
    source = SourceFactory()
    _event, item = _reported_event(source, reports=1)

    approve_review_item(item_id=item.pk, actor=EDITOR, now=NOW)

    counts = counts_for(_observation_rows(source))
    assert counts.positives == 1
    assert counts.negatives == 0


def test_a_report_on_an_edited_event_is_upheld():
    """An edit upholds the report: the source's facts were wrong, so the report was right."""
    source = SourceFactory()
    _event, item = _reported_event(source, reports=1)

    edit_and_publish(
        item_id=item.pk,
        actor=EDITOR,
        fields={"title": "The corrected title"},
        now=NOW,
    )

    counts = counts_for(_observation_rows(source))
    assert counts.negatives == 1


def test_the_observation_records_the_report_count_for_every_verdict():
    """**The count is frozen at the moment of the verdict**, for each kind that carries one."""
    source = SourceFactory()
    _event, item = _reported_event(source, reports=3)

    reject_review_item(item_id=item.pk, actor=EDITOR, now=NOW)

    observation = SourceObservation.objects.using(CATALOG).get(review_item=item)
    assert observation.kind == SourceObservation.Kind.REJECTED
    assert observation.report_count == 3


def test_a_source_item_dismissal_records_no_report_count():
    """A `source_reliability` item carries no reports — the check constraint says so."""
    source = SourceFactory()
    item = raise_review_item(
        source=source, reason=ReviewItem.Reason.SOURCE_RELIABILITY, actor=SYSTEM, now=NOW
    ).item

    dismiss_source_item(item_id=item.pk, actor=EDITOR, now=NOW)

    observation = SourceObservation.objects.using(CATALOG).get(review_item=item)
    assert observation.report_count == 0
    assert observation.event is None


# ── The week ───────────────────────────────────────────────────────────────────────────────


def test_the_period_is_the_monday_of_the_week():
    """**A calendar week, ISO-style.** 2026-11-11 is a Wednesday, so the period starts on
    the Monday, 2026-11-09."""
    assert period_start_for(NOW) == THIS_WEEK


def test_a_sunday_belongs_to_the_week_that_began_on_monday():
    """**The boundary is the ISO week, not the calendar week.**

    A Sunday is the last day of its ISO week — the week that began the previous Monday —
    and Monday is the first day of the next one. The half-open interval `[period, period + 7)`
    partitions the timeline exactly once.
    """
    sunday = datetime(2026, 11, 15, 23, 59, tzinfo=UTC)
    monday = datetime(2026, 11, 16, 0, 0, tzinfo=UTC)

    assert period_start_for(sunday) == THIS_WEEK
    assert period_start_for(monday) == date(2026, 11, 16)


def test_the_weekly_counts_split_the_observations_at_the_boundary():
    source = SourceFactory()
    _observation(
        source, SourceObservation.Kind.REJECTED, occurred_at=datetime(2026, 11, 10, tzinfo=UTC)
    )
    _observation(
        source, SourceObservation.Kind.APPROVED, occurred_at=datetime(2026, 11, 16, tzinfo=UTC)
    )

    negatives, total = weekly_counts(_observation_rows(source), THIS_WEEK)

    assert total == 1
    assert negatives == 1


# ── The weekly guarantee ──────────────────────────────────────────────────────────────────


def test_a_source_with_no_row_for_this_week_is_due():
    source = SourceFactory()

    due = due_sources(now=NOW)

    assert source.pk in {s.pk for s in due}


def test_a_source_with_a_row_for_this_week_is_not_due():
    source = SourceFactory()
    SourceReliabilityScore.objects.using(CATALOG).create(
        source=source,
        period_start=THIS_WEEK,
        score=Decimal("0.50"),
        positives=0,
        negatives=0,
        computed_at=NOW,
    )

    due = due_sources(now=NOW)

    assert source.pk not in {s.pk for s in due}


def test_a_source_not_recomputed_for_seven_days_is_due():
    """**The weekly guarantee, stated as a number rather than as a week boundary.**

    A source scored last week has no row for *this* week, so it is due — which is the
    guarantee FR-16 asks for, in the only terms a schedule can enforce.
    """
    source = SourceFactory()
    SourceReliabilityScore.objects.using(CATALOG).create(
        source=source,
        period_start=LAST_WEEK,
        score=Decimal("0.50"),
        positives=0,
        negatives=0,
        computed_at=NOW - timedelta(days=7),
    )

    due = due_sources(now=NOW)

    assert source.pk in {s.pk for s in due}


def test_a_paused_source_is_not_due():
    """**Only active sources are scored.** A paused source is not ingesting, so its score
    is not changing, and recomputing it would only produce noise."""
    source = SourceFactory(status=Source.Status.PAUSED)

    due = due_sources(now=NOW)

    assert source.pk not in {s.pk for s in due}


# ── The score and its history ─────────────────────────────────────────────────────────────


def test_a_source_with_no_score_reads_as_the_prior():
    """**The 0.50 prior** (design D15), asked of the domain module rather than written down
    again here."""
    source = SourceFactory()

    assert current_score(source) == reliability_score(0, 0) == Decimal("0.50")


def test_a_recompute_writes_the_score_to_the_source_and_the_history():
    source = SourceFactory()
    _observation(source, SourceObservation.Kind.REJECTED, occurred_at=NOW)

    result = recompute_source(source_id=source.pk, now=NOW)

    source.refresh_from_db(using=CATALOG)
    assert source.reliability_score == result.score
    assert source.reliability_scored_at is not None
    row = SourceReliabilityScore.objects.using(CATALOG).get(source=source, period_start=THIS_WEEK)
    assert row.score == result.score
    assert row.negatives == 1


def test_the_field_and_the_latest_row_never_disagree():
    """**They are written in one transaction**, so a crash cannot leave one behind."""
    source = SourceFactory()
    for _ in range(3):
        _observation(source, SourceObservation.Kind.REJECTED, occurred_at=NOW)

    recompute_source(source_id=source.pk, now=NOW)

    source.refresh_from_db(using=CATALOG)
    latest = SourceReliabilityScore.objects.using(CATALOG).filter(source=source).first()
    assert source.reliability_score == latest.score


def test_the_row_records_the_counts_it_was_computed_from():
    """**A row can be checked without re-reading the observations.**"""
    source = SourceFactory()
    _observation(source, SourceObservation.Kind.REJECTED, occurred_at=NOW)
    _observation(source, SourceObservation.Kind.REJECTED, occurred_at=NOW)
    _observation(source, SourceObservation.Kind.APPROVED, occurred_at=NOW)

    recompute_source(source_id=source.pk, now=NOW)

    row = SourceReliabilityScore.objects.using(CATALOG).get(source=source)
    assert row.positives == 1
    assert row.negatives == 2


# ── Idempotence ───────────────────────────────────────────────────────────────────────────


def test_a_re_run_in_the_same_period_writes_no_second_row():
    """**The AC's idempotence, enforced by the database.**

    The unique constraint on `(source, period_start)` is the guarantee; the code is careful
    only so that the second run *updates* the row rather than colliding.
    """
    source = SourceFactory()
    _observation(source, SourceObservation.Kind.REJECTED, occurred_at=NOW)

    first = recompute_source(source_id=source.pk, now=NOW)
    second = recompute_source(source_id=source.pk, now=NOW)

    assert first.created is True
    assert second.created is False
    assert SourceReliabilityScore.objects.using(CATALOG).filter(source=source).count() == 1


def test_a_re_run_refreshes_the_score_rather_than_leaving_it_stale():
    """**A score that is a week stale is a score that is wrong**, so the re-run updates the
    row's conclusion with the observations that have arrived since."""
    source = SourceFactory()
    _observation(source, SourceObservation.Kind.REJECTED, occurred_at=NOW)
    recompute_source(source_id=source.pk, now=NOW)

    _observation(source, SourceObservation.Kind.REJECTED, occurred_at=NOW)
    later = recompute_source(source_id=source.pk, now=NOW + timedelta(hours=1))

    row = SourceReliabilityScore.objects.using(CATALOG).get(source=source)
    assert row.negatives == 2
    assert row.score == later.score


def test_the_database_refuses_a_second_row_for_the_same_source_and_period():
    """**The constraint, proven on the database rather than through the service.**

    A test that only exercises the service would pass even if the constraint were missing.
    """
    source = SourceFactory()
    SourceReliabilityScore.objects.using(CATALOG).create(
        source=source,
        period_start=THIS_WEEK,
        score=Decimal("0.50"),
        positives=0,
        negatives=0,
        computed_at=NOW,
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic(using=CATALOG):
            SourceReliabilityScore.objects.using(CATALOG).create(
                source=source,
                period_start=THIS_WEEK,
                score=Decimal("0.40"),
                positives=1,
                negatives=1,
                computed_at=NOW,
            )


def test_the_period_must_be_a_week_start():
    """**The row is a week, not a moment**, and the database says so.

    `date_trunc('week', ...)` is Postgres's own ISO-week-to-Monday truncation, so the
    service and the database agree on where a week starts without either hard-coding an
    offset.
    """
    source = SourceFactory()

    with pytest.raises(IntegrityError):
        with transaction.atomic(using=CATALOG):
            SourceReliabilityScore.objects.using(CATALOG).create(
                source=source,
                period_start=date(2026, 11, 10),  # a Tuesday
                score=Decimal("0.50"),
                positives=0,
                negatives=0,
                computed_at=NOW,
            )


# ── The write is one statement ────────────────────────────────────────────────────────────


def test_two_writes_for_the_same_period_leave_one_row():
    """**The write cannot collide.**

    A `SELECT` followed by an `INSERT` is a race: two runs for the same (source, period)
    can both read "no row" and both insert, and the loser gets an uncaught
    `IntegrityError` that fails the whole job. The write is one statement, so the database
    resolves it — the second run refreshes the row the first one made.
    """
    source = SourceFactory()
    _observation(source, SourceObservation.Kind.REJECTED, occurred_at=NOW)

    first = recompute_source(source_id=source.pk, now=NOW)
    second = recompute_source(source_id=source.pk, now=NOW)

    assert first.created is True
    assert second.created is False
    assert SourceReliabilityScore.objects.using(CATALOG).filter(source=source).count() == 1
