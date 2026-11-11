"""FR-16's escalation: the two paths that raise a review item, and the one thing it never does.

FR-16 raises a `source_reliability` review item in two situations:

- **the low score**: below 0.30 with at least 30 observations
- **the spike**: this week's rate of negative observations is 3× last week's

And it says, in the same breath: *"escalation, never removal."* That last part is the
harder half to test, because it is an **absence** — and an absence asserted by reading the
source would be trusting the source. So the never-removal test asserts the *values* of
every column an escalation could plausibly have touched, and a separate test asserts that
the source is still ingesting on schedule.
"""

from datetime import UTC, date, datetime, timedelta

import pytest

from apps.ingestion.models import (
    Event,
    IngestionAuditEntry,
    ReviewItem,
    Source,
    SourceObservation,
)
from apps.ingestion.services.reliability import (
    ACTOR_LABEL,
    REASON,
    period_start_for,
    recompute_source,
)
from apps.ingestion.services.review_queue import raise_review_item
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import EventFactory, SourceFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
SYSTEM = Actor.system("ingest_pipeline")
THIS_WEEK = date(2026, 11, 9)
LAST_WEEK = date(2026, 11, 2)


def _observation(source: Source, kind: str, *, occurred_at: datetime) -> SourceObservation:
    event = EventFactory(source=source)
    item = raise_review_item(
        event=event, reason=ReviewItem.Reason.IN_REVIEW, actor=SYSTEM, now=occurred_at
    ).item
    return SourceObservation.objects.using(CATALOG).create(
        source=source,
        kind=kind,
        event=event,
        review_item=item,
        occurred_at=occurred_at,
        actor_kind=SYSTEM.kind,
        actor_id=SYSTEM.id,
        actor_label=SYSTEM.label,
    )


def _bad_source(count: int) -> Source:
    """A source with `count` rejections — enough for the score to fall below 0.30."""
    source = SourceFactory()
    for index in range(count):
        _observation(
            source, SourceObservation.Kind.REJECTED, occurred_at=NOW - timedelta(days=index)
        )
    return source


# ── The low-score path ────────────────────────────────────────────────────────────────────


def test_a_low_score_with_thirty_observations_raises_a_review_item():
    """**FR-16's low-score path.** Thirty all-negative observations give a posterior of
    (5+0)/(10+30) = 0.125, which is below 0.30, and n is at least 30."""
    source = _bad_source(30)

    result = recompute_source(source_id=source.pk, now=NOW)

    assert result.escalated is True
    item = ReviewItem.objects.using(CATALOG).get(source=source, reason=REASON)
    assert item.status == ReviewItem.Status.OPEN


def test_a_low_score_with_fewer_than_thirty_observations_raises_nothing():
    """**Both halves of the threshold, and the second is the one that matters.**

    Twenty rejections give (5)/(30) = 0.17 — well below 0.30 — but n is under 30, so there
    is not enough evidence to act on. Escalating here would put noise in the editor's queue,
    which is the queue's worst failure mode.
    """
    source = _bad_source(20)

    result = recompute_source(source_id=source.pk, now=NOW)

    assert result.escalated is False
    assert not ReviewItem.objects.using(CATALOG).filter(source=source).exists()


def test_a_healthy_source_raises_nothing():
    """Thirty approvals give (5+30)/(10+30) = 0.875 — nothing to escalate."""
    source = SourceFactory()
    for index in range(30):
        _observation(
            source, SourceObservation.Kind.APPROVED, occurred_at=NOW - timedelta(days=index)
        )

    result = recompute_source(source_id=source.pk, now=NOW)

    assert result.escalated is False
    assert not ReviewItem.objects.using(CATALOG).filter(source=source).exists()


# ── The spike path ────────────────────────────────────────────────────────────────────────


def test_a_spike_raises_a_review_item_even_while_the_score_is_healthy():
    """**The spike path is the early warning, and it fires while the score is fine.**

    Last week: 40 events, 2 bad. This week: 40 events, 24 bad. The rates are 0.14 and
    0.58 — a 4.1× rise — but the cumulative score is still respectable. A rule that only
    fired on the cumulative score would miss this entirely.
    """
    source = SourceFactory()
    for _ in range(2):
        _observation(source, SourceObservation.Kind.REJECTED, occurred_at=NOW - timedelta(days=8))
    for _ in range(38):
        _observation(source, SourceObservation.Kind.APPROVED, occurred_at=NOW - timedelta(days=8))
    for _ in range(24):
        _observation(source, SourceObservation.Kind.REJECTED, occurred_at=NOW)
    for _ in range(16):
        _observation(source, SourceObservation.Kind.APPROVED, occurred_at=NOW)

    result = recompute_source(source_id=source.pk, now=NOW)

    assert result.spiked is True
    assert result.escalated is True
    assert ReviewItem.objects.using(CATALOG).filter(source=source, reason=REASON).exists()


def test_a_steady_bad_rate_is_not_a_spike():
    """**The same badness, every week, is not a spike.**

    Ten rejections a week for two weeks: this week's rate equals last week's, so the ratio
    is 1.0 and nothing fires. The cumulative score is what catches a source that is always
    this bad — the spike rule is for a source that is *getting worse*.
    """
    source = SourceFactory()
    for _ in range(10):
        _observation(source, SourceObservation.Kind.REJECTED, occurred_at=NOW - timedelta(days=8))
        _observation(source, SourceObservation.Kind.APPROVED, occurred_at=NOW - timedelta(days=8))
    for _ in range(10):
        _observation(source, SourceObservation.Kind.REJECTED, occurred_at=NOW)
        _observation(source, SourceObservation.Kind.APPROVED, occurred_at=NOW)

    result = recompute_source(source_id=source.pk, now=NOW)

    assert result.spiked is False
    assert result.escalated is False


def test_a_source_with_no_previous_week_cannot_spike():
    """**A first week has no predecessor, and the prior smooths the comparison away.**

    A week of twenty rejections against no previous week gives a rate of (5+20)/(10+20) =
    0.83 against a prior of 5/10 = 0.50 — a ratio of 1.66, well under the 3× multiplier.
    The domain module's small-sample suppression is what makes this safe to pass
    unconditionally rather than special-casing a source's first week.
    """
    source = SourceFactory()
    for _ in range(20):
        _observation(source, SourceObservation.Kind.REJECTED, occurred_at=NOW)

    result = recompute_source(source_id=source.pk, now=NOW)

    assert result.spiked is False


# ── No duplicate escalation ───────────────────────────────────────────────────────────────


def test_a_second_escalation_bumps_the_item_rather_than_opening_a_second():
    """**One open item per (source, reason)** — the queue's own rule, called rather than
    reimplemented (design D12).

    A source that is escalated twice in a week must not put two items in the editor's
    queue, and the second escalation must leave a trace that it happened.
    """
    source = _bad_source(30)

    recompute_source(source_id=source.pk, now=NOW)
    recompute_source(source_id=source.pk, now=NOW + timedelta(hours=1))

    items = ReviewItem.objects.using(CATALOG).filter(source=source, reason=REASON)
    assert items.count() == 1
    assert items.first().status == ReviewItem.Status.OPEN


def test_the_bump_is_audited():
    """**The second escalation is recorded**, so a reader of the audit log can see that the
    source was escalated again rather than once.

    The audit rows are filtered to the escalation's own item — the fixture's thirty
    `in_review` raises wrote rows of their own, and they are not what this test is about.
    """
    source = _bad_source(30)

    recompute_source(source_id=source.pk, now=NOW)
    item = ReviewItem.objects.using(CATALOG).get(source=source, reason=REASON)
    recompute_source(source_id=source.pk, now=NOW + timedelta(hours=1))

    actions = list(
        IngestionAuditEntry.objects.using(CATALOG)
        .filter(action__in=("review_item_raised", "review_item_bumped"), target_id=item.pk)
        .values_list("action", flat=True)
    )
    assert actions.count("review_item_raised") == 1
    assert actions.count("review_item_bumped") == 1


def test_the_recompute_is_audited_with_its_counts():
    """**AD-5: every mutation writes an audit row in its transaction.** The recompute is a
    mutation, so it writes one — with the counts the score came from, so the number can be
    checked later."""
    source = _bad_source(30)

    recompute_source(source_id=source.pk, now=NOW)

    entry = IngestionAuditEntry.objects.using(CATALOG).get(
        action="source_reliability_recomputed", target_id=source.pk
    )
    assert entry.actor_label == ACTOR_LABEL
    assert entry.details["negatives"] == 30
    assert entry.details["escalated"] is True


# ── Never removal (FR-16) ─────────────────────────────────────────────────────────────────


def test_an_escalation_changes_nothing_about_the_source():
    """**FR-16: escalation, never removal.**

    The assertion is on the *values*, not on the absence of a line in the service — because
    trusting the absence of a line is trusting the source. Every column an escalation could
    plausibly have touched is compared.
    """
    source = _bad_source(30)
    before = {
        "status": source.status,
        "ingestion_cadence": source.ingestion_cadence,
        "last_ingested_at": source.last_ingested_at,
        "last_attempted_at": source.last_attempted_at,
        "consecutive_failures": source.consecutive_failures,
        "stale_since": source.stale_since,
        "freshness_ttl_hours": source.freshness_ttl_hours,
        "tz_coverage": source.tz_coverage,
        "tos_status": source.tos_status,
    }

    recompute_source(source_id=source.pk, now=NOW)

    source.refresh_from_db(using=CATALOG)
    after = {
        "status": source.status,
        "ingestion_cadence": source.ingestion_cadence,
        "last_ingested_at": source.last_ingested_at,
        "last_attempted_at": source.last_attempted_at,
        "consecutive_failures": source.consecutive_failures,
        "stale_since": source.stale_since,
        "freshness_ttl_hours": source.freshness_ttl_hours,
        "tz_coverage": source.tz_coverage,
        "tos_status": source.tos_status,
    }
    assert after == before


def test_an_escalated_source_is_still_ingesting_on_schedule():
    """**The same promise, from the other side: the source is still active and still due.**

    A reader who only saw the first test could argue that the source was paused *before* the
    escalation and so nothing changed. This test starts from an active source and checks it
    is still active — and still scheduled — afterwards.
    """
    source = _bad_source(30)
    assert source.status == Source.Status.ACTIVE

    recompute_source(source_id=source.pk, now=NOW)

    source.refresh_from_db(using=CATALOG)
    assert source.status == Source.Status.ACTIVE
    assert source.ingestion_cadence > timedelta(0)


def test_the_escalation_does_not_hide_the_events():
    """**A bad source's good events are not collateral damage.**

    The escalation raises a review item about the source. It does not touch the events the
    source published, and an event that was published stays published.
    """
    source = SourceFactory()
    event = EventFactory(source=source, publication_status=Event.PublicationStatus.PUBLISHED)
    for _ in range(30):
        _observation(source, SourceObservation.Kind.REJECTED, occurred_at=NOW)

    recompute_source(source_id=source.pk, now=NOW)

    event.refresh_from_db(using=CATALOG)
    assert event.publication_status == Event.PublicationStatus.PUBLISHED


def test_the_period_of_the_escalated_item_is_the_week_it_was_computed_for():
    """**The escalation is about a period, and the period is on the row.** The review item
    names the source; the history says which week the judgement was about."""
    source = _bad_source(30)

    recompute_source(source_id=source.pk, now=NOW)

    from apps.ingestion.models import SourceReliabilityScore

    row = SourceReliabilityScore.objects.using(CATALOG).get(source=source)
    assert row.period_start == period_start_for(NOW) == THIS_WEEK
