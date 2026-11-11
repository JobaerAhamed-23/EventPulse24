"""`raise_review_item` (design: review-queue-model D2, D4, D8, D10): raise, bump, refuse."""

from datetime import timedelta

import pytest
from django.db import transaction
from django.utils import timezone

from apps.ingestion.models import IngestionAuditEntry, ReviewItem
from apps.ingestion.services import review_queue
from apps.ingestion.services.review_queue import raise_review_item
from domain.errors import ValidationError
from shared.actor import Actor
from shared.constants import REVIEW_SLA_USER_REPORTED
from shared.db import CATALOG, PERSONAL
from shared.ids import uuid7
from tests.ingestion.factories import EventFactory, SourceFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

NOW = timezone.now()
REPORTS = Actor.system("event_report")
PIPELINE = Actor.system("ingest_pipeline")
WRONG_VENUE = ReviewItem.ReportCategory.WRONG_VENUE
DUPLICATE = ReviewItem.ReportCategory.DUPLICATE


def items():
    return ReviewItem.objects.using(CATALOG)


def audits(item: ReviewItem):
    return IngestionAuditEntry.objects.using(CATALOG).filter(target_id=item.id).order_by("at")


def report(event, category=WRONG_VENUE, now=NOW):
    return raise_review_item(
        actor=REPORTS, reason="user_reported", event=event, category=category, now=now
    )


# --- raising -----------------------------------------------------------------------------


def test_a_first_report_opens_an_item_due_in_24_hours():
    event = EventFactory()

    result = report(event)

    assert result.created is True
    item = items().get(pk=result.item.pk)
    assert item.status == ReviewItem.Status.OPEN
    assert item.event_id == event.id
    assert item.reports_wrong_venue == 1
    assert item.report_count == 1
    assert item.raised_at == item.last_raised_at == NOW
    assert item.due_at == NOW + REVIEW_SLA_USER_REPORTED


def test_an_in_review_item_has_no_deadline_and_no_tallies():
    result = raise_review_item(actor=PIPELINE, reason="in_review", event=EventFactory(), now=NOW)

    assert result.item.due_at is None
    assert result.item.report_count == 0


def test_a_source_item_targets_the_source():
    source = SourceFactory()

    result = raise_review_item(
        actor=Actor.system("reliability_job"), reason="source_reliability", source=source
    )

    assert result.item.source_id == source.id
    assert result.item.event_id is None


# --- bumping -----------------------------------------------------------------------------


def test_a_second_report_bumps_the_open_item_and_keeps_the_deadline():
    event = EventFactory()
    first = report(event, WRONG_VENUE, now=NOW)
    later = NOW + timedelta(hours=5)

    second = report(event, DUPLICATE, now=later)

    assert second.created is False
    assert second.item.pk == first.item.pk
    assert items().filter(event=event).count() == 1
    item = items().get(pk=first.item.pk)
    assert (item.reports_wrong_venue, item.reports_duplicate) == (1, 1)
    assert item.report_count == 2
    assert item.last_raised_at == later
    assert item.raised_at == NOW
    assert item.due_at == NOW + REVIEW_SLA_USER_REPORTED


def test_the_same_category_twice_counts_twice():
    event = EventFactory()
    report(event)

    result = report(event)

    assert result.item.reports_wrong_venue == 2


def test_a_report_on_a_quarantined_event_opens_its_own_item():
    event = EventFactory()
    raise_review_item(actor=PIPELINE, reason="in_review", event=event)

    result = report(event)

    assert result.created is True
    assert set(items().filter(event=event).values_list("reason", flat=True)) == {
        "in_review",
        "user_reported",
    }


def test_a_raise_after_the_item_closed_opens_a_new_one():
    event = EventFactory()
    first = report(event).item
    items().filter(pk=first.pk).update(
        status="resolved",
        resolution="rejected",
        resolved_at=NOW,
        resolved_by_kind="user",
        resolved_by_id=uuid7(),
    )

    second = report(event)

    assert second.created is True
    assert second.item.pk != first.pk
    closed = items().get(pk=first.pk)
    assert closed.reports_wrong_venue == 1  # history untouched


def test_an_item_closed_between_the_refused_insert_and_the_lock_gets_a_fresh_item(monkeypatch):
    """D10's one interleaving a two-thread test can't hit on demand: our insert collides with
    the open item, and an editor resolves it before we lock it. The report must not be lost
    and must not land on the closed item."""
    event = EventFactory()
    first = report(event).item
    real_reread = review_queue._reread_open

    def resolve_then_reread(**kwargs):
        items().filter(pk=first.pk).update(
            status="resolved",
            resolution="approved",
            resolved_at=NOW,
            resolved_by_kind="user",
            resolved_by_id=uuid7(),
        )
        return real_reread(**kwargs)

    monkeypatch.setattr(review_queue, "_reread_open", resolve_then_reread)

    result = report(event, DUPLICATE)

    assert result.created is True
    assert result.item.pk != first.pk
    assert result.item.reports_duplicate == 1
    assert items().get(pk=first.pk).reports_duplicate == 0


# --- the audit row (AD-5) and reporter anonymity (D4) ------------------------------------


def test_a_raise_then_a_bump_write_one_audit_row_each():
    event = EventFactory()
    item = report(event).item
    report(event, DUPLICATE)

    rows = list(audits(item))

    assert [row.action for row in rows] == ["review_item_raised", "review_item_bumped"]
    assert rows[0].target_type == "review_item"
    assert rows[0].details == {
        "reason": "user_reported",
        "event_id": str(event.id),
        "category": "wrong_venue",
    }
    assert rows[1].details["category"] == "duplicate"


def test_a_report_raised_as_the_reporter_is_refused_and_writes_nothing():
    """D4 is enforced, not trusted: the reporter's id must never reach a catalog audit row."""
    event = EventFactory()

    with pytest.raises(ValueError, match="system actor"):
        raise_review_item(
            actor=Actor.user(uuid7()), reason="user_reported", event=event, category=WRONG_VENUE
        )

    assert not items().filter(event=event).exists()
    assert not IngestionAuditEntry.objects.using(CATALOG).filter(target_type="review_item").exists()


def test_an_editor_may_raise_a_non_report_item():
    """The guard is about reports only; an editor flagging an event for review is fine."""
    result = raise_review_item(actor=Actor.user(uuid7()), reason="in_review", event=EventFactory())

    assert result.created is True


def test_a_report_raised_item_names_no_user_in_its_audit_row():
    item = report(EventFactory()).item

    row = audits(item).get()

    assert row.actor_kind == "system"
    assert row.actor_id is None
    assert row.actor_label == "event_report"


# --- refusals ----------------------------------------------------------------------------


def _refused(**kwargs) -> list[str]:
    with pytest.raises(ValidationError) as excinfo:
        raise_review_item(actor=PIPELINE, **kwargs)
    return [error["loc"][-1] for error in excinfo.value.details["errors"]]


def test_a_report_without_a_category_is_refused():
    assert _refused(reason="user_reported", event=EventFactory()) == ["category"]


def test_an_unknown_category_is_refused():
    assert _refused(reason="user_reported", event=EventFactory(), category="rude") == ["category"]


def test_a_category_on_a_non_report_is_refused():
    assert _refused(reason="in_review", event=EventFactory(), category=WRONG_VENUE) == ["category"]


@pytest.mark.parametrize(
    ("reason", "target"),
    [
        ("in_review", "source"),
        ("user_reported", "none"),
        ("source_reliability", "event"),
        ("source_reliability", "none"),
    ],
)
def test_a_target_that_does_not_fit_the_reason_is_refused(reason, target):
    kwargs = {"source": SourceFactory()} if target == "source" else {}
    if target == "event":
        kwargs = {"event": EventFactory()}
    category = WRONG_VENUE if reason == "user_reported" else None

    locs = _refused(reason=reason, category=category, **kwargs)

    assert locs == ["source" if reason == "source_reliability" else "event"]


def test_an_event_item_with_both_targets_is_refused():
    locs = _refused(reason="in_review", event=EventFactory(), source=SourceFactory())

    assert locs == ["event"]


def test_a_refusal_writes_nothing():
    with pytest.raises(ValidationError):
        raise_review_item(actor=PIPELINE, reason="user_reported", event=EventFactory())

    assert not items().exists()
    assert not IngestionAuditEntry.objects.using(CATALOG).filter(target_type="review_item").exists()


# --- the caller's transaction ------------------------------------------------------------


def test_the_item_rolls_back_with_the_callers_transaction():
    event = EventFactory()

    with pytest.raises(RuntimeError), transaction.atomic(using=CATALOG):
        report(event)
        raise RuntimeError("the change that raised it failed")

    assert not items().filter(event=event).exists()
    assert not IngestionAuditEntry.objects.using(CATALOG).filter(target_type="review_item").exists()
