"""FR-59's report service: the tally counts people, the throttle holds, the outbox recovers."""

from datetime import UTC, datetime, timedelta

import pytest

from apps.ingestion.models import IngestionAuditEntry, ReviewItem
from apps.personalization.models import EventReport
from apps.personalization.services import event_reports as service
from apps.personalization.services.event_reports import (
    reconcile_unraised_reports,
    report_event,
)
from domain.errors import ThrottledError
from shared.constants import EVENT_REPORT_DAILY_LIMIT
from shared.db import CATALOG, PERSONAL
from shared.ids import uuid7
from tests.ingestion.factories import EventFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
WRONG_DATE = "wrong_date_time"
WRONG_VENUE = "wrong_venue"


@pytest.fixture(autouse=True)
def throttle(monkeypatch):
    """A fresh in-memory throttle per test, with an injected clock.

    The adapter is swapped at the module that calls it, the way `test_preview_api` does, so
    the limit is deterministic: no sleeping, no Redis, no shared counters between tests.
    """
    from adapters.throttle.memory import InMemoryThrottleAdapter

    clock = {"now": 1_000_000.0}
    adapter = InMemoryThrottleAdapter(now=lambda: clock["now"])
    monkeypatch.setattr(service, "get_throttle_port", lambda: adapter)
    adapter.test_clock = clock  # type: ignore[attr-defined]
    return adapter


def items(event):
    return list(
        ReviewItem.objects.using(CATALOG).filter(
            event_id=event.pk, reason=ReviewItem.Reason.USER_REPORTED
        )
    )


# ── The report, and the tally ────────────────────────────────────────────────────────────


def test_a_report_is_stored_and_raises_a_review_item():
    event = EventFactory()
    user = uuid7()

    report = report_event(user_id=user, event_id=event.pk, category=WRONG_DATE, now=NOW)

    assert report.raised_at == NOW
    (item,) = items(event)
    assert item.status == ReviewItem.Status.OPEN
    assert item.reports_wrong_date_time == 1


def test_the_same_user_reporting_twice_counts_once():
    """**The tally counts people, not taps** — the AC's "must not inflate" requirement."""
    event = EventFactory()
    user = uuid7()

    report_event(user_id=user, event_id=event.pk, category=WRONG_DATE, now=NOW)
    report_event(user_id=user, event_id=event.pk, category=WRONG_DATE, now=NOW)

    assert EventReport.objects.using(PERSONAL).count() == 1
    (item,) = items(event)
    assert item.reports_wrong_date_time == 1


def test_two_users_reporting_the_same_thing_count_twice():
    event = EventFactory()

    report_event(user_id=uuid7(), event_id=event.pk, category=WRONG_DATE, now=NOW)
    report_event(user_id=uuid7(), event_id=event.pk, category=WRONG_DATE, now=NOW)

    (item,) = items(event)
    assert item.reports_wrong_date_time == 2


def test_one_user_can_report_two_different_things():
    """A second *category* is a genuine second signal, not a duplicate."""
    event = EventFactory()
    user = uuid7()

    report_event(user_id=user, event_id=event.pk, category=WRONG_DATE, now=NOW)
    report_event(user_id=user, event_id=event.pk, category=WRONG_VENUE, now=NOW)

    assert EventReport.objects.using(PERSONAL).count() == 2
    (item,) = items(event)
    assert item.reports_wrong_date_time == 1
    assert item.reports_wrong_venue == 1


def test_reports_on_one_event_collapse_onto_one_item():
    """FR-57: "several reports on one event collapse onto one ReviewItem with a count"."""
    event = EventFactory()
    for _ in range(3):
        report_event(user_id=uuid7(), event_id=event.pk, category=WRONG_DATE, now=NOW)

    assert len(items(event)) == 1


# ── AD-3: no user identity crosses the wall ──────────────────────────────────────────────


def test_the_review_item_carries_no_user_identity():
    """**The property AD-3's ER note exists to protect**, asserted over every column."""
    event = EventFactory()
    user = uuid7()

    report_event(user_id=user, event_id=event.pk, category=WRONG_DATE, now=NOW)

    (item,) = items(event)
    values = {str(value) for value in item.__dict__.values() if value is not None}
    assert str(user) not in values


def test_the_catalog_audit_row_carries_no_user_identity():
    """The subtler half: the editorial group can read `catalog`'s audit log."""
    event = EventFactory()
    user = uuid7()

    report_event(user_id=user, event_id=event.pk, category=WRONG_DATE, now=NOW)

    entry = IngestionAuditEntry.objects.using(CATALOG).get(action="review_item_raised")
    assert entry.actor_kind == "system"
    assert entry.actor_label == "event_report"
    assert entry.actor_id is None
    assert str(user) not in str(entry.details)


# ── The throttle ─────────────────────────────────────────────────────────────────────────


def test_the_sixth_report_in_a_day_is_refused():
    user = uuid7()
    events = [EventFactory() for _ in range(EVENT_REPORT_DAILY_LIMIT + 1)]

    for event in events[:EVENT_REPORT_DAILY_LIMIT]:
        report_event(user_id=user, event_id=event.pk, category=WRONG_DATE, now=NOW)

    with pytest.raises(ThrottledError) as excinfo:
        report_event(user_id=user, event_id=events[-1].pk, category=WRONG_DATE, now=NOW)

    assert excinfo.value.code == "rate_limited"
    assert excinfo.value.details["retry_after_seconds"] > 0


def test_one_users_limit_does_not_touch_another():
    first, second = uuid7(), uuid7()
    events = [EventFactory() for _ in range(EVENT_REPORT_DAILY_LIMIT)]
    for event in events:
        report_event(user_id=first, event_id=event.pk, category=WRONG_DATE, now=NOW)

    report = report_event(user_id=second, event_id=events[0].pk, category=WRONG_DATE, now=NOW)

    assert report.raised_at == NOW


def test_a_repeat_still_spends_an_attempt():
    """The throttle is checked **before** the idempotence shortcut.

    A limit a repeat could slip past is not a limit: a client hammering one report would
    otherwise be free.
    """
    user = uuid7()
    event = EventFactory()
    for _ in range(EVENT_REPORT_DAILY_LIMIT):
        report_event(user_id=user, event_id=event.pk, category=WRONG_DATE, now=NOW)

    with pytest.raises(ThrottledError):
        report_event(user_id=user, event_id=event.pk, category=WRONG_DATE, now=NOW)


# ── The outbox ───────────────────────────────────────────────────────────────────────────


def test_a_failing_catalog_write_still_stores_the_report(monkeypatch):
    """**The user's fact survives the hop failing**, which is why it is written first."""
    event = EventFactory()
    user = uuid7()

    def boom(**kwargs):
        raise RuntimeError("catalog is unreachable")

    monkeypatch.setattr(service, "raise_user_report", boom)

    report = report_event(user_id=user, event_id=event.pk, category=WRONG_DATE, now=NOW)

    assert report.raised_at is None
    assert items(event) == []


def test_the_reconciler_raises_what_the_request_could_not(monkeypatch):
    event = EventFactory()
    user = uuid7()
    monkeypatch.setattr(
        service, "raise_user_report", lambda **kw: (_ for _ in ()).throw(RuntimeError())
    )
    report_event(user_id=user, event_id=event.pk, category=WRONG_DATE, now=NOW)
    monkeypatch.undo()

    assert reconcile_unraised_reports(now=NOW + timedelta(minutes=5)) == 1

    (item,) = items(event)
    assert item.reports_wrong_date_time == 1
    assert EventReport.objects.using(PERSONAL).get(user_id=user).raised_at is not None


def test_the_reconciler_is_idempotent(monkeypatch):
    event = EventFactory()
    monkeypatch.setattr(
        service, "raise_user_report", lambda **kw: (_ for _ in ()).throw(RuntimeError())
    )
    report_event(user_id=uuid7(), event_id=event.pk, category=WRONG_DATE, now=NOW)
    monkeypatch.undo()

    assert reconcile_unraised_reports(now=NOW) == 1
    assert reconcile_unraised_reports(now=NOW) == 0
    assert len(items(event)) == 1


def test_the_reconciler_stamps_a_report_whose_event_has_gone():
    """Nothing to review and nothing to retry, so it leaves the queue rather than looping."""
    event = EventFactory()
    user = uuid7()
    EventReport.objects.using(PERSONAL).create(
        user_id=user, event_id=event.pk, category=WRONG_DATE, created_at=NOW
    )
    event.delete(using=CATALOG)

    assert reconcile_unraised_reports(now=NOW) == 1
    assert EventReport.objects.using(PERSONAL).get(user_id=user).raised_at is not None


# ── A report changes nothing a user can see ──────────────────────────────────────────────


def test_a_reported_event_is_still_public():
    """FR-59, and the intent's "calm, not punitive" constraint: one person cannot pull it."""
    from apps.ingestion.services.catalog_read import (
        get_public_event,
        list_public_candidates,
        list_public_events,
    )

    event = EventFactory(start_time_utc=NOW + timedelta(days=5), last_seen_at=NOW)
    report_event(user_id=uuid7(), event_id=event.pk, category="does_not_exist", now=NOW)

    items_out, _ = list_public_events(now=NOW)
    assert [item.id for item in items_out] == [event.pk]
    assert [c.id for c in list_public_candidates(now=NOW)] == [event.pk]
    assert get_public_event(event_id=event.pk, now=NOW).id == event.pk
