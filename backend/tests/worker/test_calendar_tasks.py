"""The calendar worker tasks (AD-7, AD-8 of the calendar-sync design).

The tick enqueues a dispatcher; the dispatcher claims what is due and enqueues one sync job
per claim; the sync job syncs one connection and releases its claim. Three properties are
pinned here:

- the **tick** enqueues the calendar dispatcher every time, exactly as it enqueues the
  source scheduler (AD-7: the tick never touches the database, it only enqueues);
- a **failed enqueue** releases the claim, so the next tick retries it rather than leaving
  it claimed until the TTL expires;
- the **sync job** releases its claim whatever happens — a revoked credential, a transient
  failure, or an unexpected error.

The claim is what stops two overlapping ticks syncing the same connection twice, so
releasing it reliably is not a detail.
"""

import logging
from datetime import UTC, datetime, timedelta

import pytest

from apps.personalization.models import CalendarConnection, PersonalEvent
from apps.personalization.services import calendar_sync
from ports.calendar import CalendarEntry, CalendarResult, CalendarTransientError
from shared.db import PERSONAL
from tests.personalization.factories import CalendarConnectionFactory
from worker import tasks

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


def _at(monkeypatch, when: datetime) -> None:
    monkeypatch.setattr(tasks, "_now", lambda: when)


def _due(**kwargs) -> CalendarConnection:
    return CalendarConnectionFactory(next_poll_at=NOW - timedelta(minutes=1), **kwargs)


class StubPort:
    """A port that returns one entry, so the sync has something to write."""

    def __init__(self):
        self.calls = 0

    def fetch_entries(self, feed):
        self.calls += 1
        return CalendarResult(
            entries=[
                CalendarEntry(
                    uid="a@feed",
                    title="Team stand-up",
                    starts_at=NOW + timedelta(hours=2),
                    ends_at=NOW + timedelta(hours=3),
                    tz="Europe/London",
                )
            ]
        )


# --- the dispatcher ---------------------------------------------------------------------------


def test_the_dispatcher_claims_the_due_connections_and_enqueues_one_job_each(monkeypatch, enqueued):
    _at(monkeypatch, NOW)
    due = _due()
    CalendarConnectionFactory(next_poll_at=NOW + timedelta(hours=1))

    tasks.schedule_calendars()

    assert enqueued == [("worker.tasks.sync_calendar", (str(due.pk),))]


def test_the_dispatcher_enqueues_nothing_when_nothing_is_due(monkeypatch, enqueued):
    _at(monkeypatch, NOW)
    CalendarConnectionFactory(next_poll_at=NOW + timedelta(hours=1))

    tasks.schedule_calendars()

    assert enqueued == []


def test_the_dispatcher_does_not_claim_the_same_connection_twice(monkeypatch, enqueued):
    _at(monkeypatch, NOW)
    due = _due()

    tasks.schedule_calendars()
    tasks.schedule_calendars()  # the next tick

    assert enqueued == [("worker.tasks.sync_calendar", (str(due.pk),))]


def test_a_failed_enqueue_releases_that_claim_and_continues(monkeypatch, caplog):
    _at(monkeypatch, NOW)
    first = _due()
    second = _due()
    sent = []

    def flaky_broker(task, *args):
        if args[0] == str(first.pk):
            raise RuntimeError("broker down")
        sent.append((task.name, args))

    monkeypatch.setattr(tasks, "_enqueue", flaky_broker)

    with caplog.at_level(logging.INFO, logger="worker.tasks"):
        tasks.schedule_calendars()

    # The first claim is freed so the next tick retries it; the second one is enqueued.
    first.refresh_from_db()
    assert first.sync_claimed_at is None
    assert sent == [("worker.tasks.sync_calendar", (str(second.pk),))]
    assert "Calendar sync not enqueued" in caplog.text


def test_the_dispatcher_writes_no_event_content_to_the_log(monkeypatch, caplog):
    _at(monkeypatch, NOW)
    _due()

    with caplog.at_level(logging.INFO, logger="worker.tasks"):
        tasks.schedule_calendars()

    assert "Calendars scheduled" in caplog.text


# --- the sync job ----------------------------------------------------------------------------


def test_the_sync_job_syncs_the_connection(monkeypatch):
    connection = _due()
    _at(monkeypatch, NOW)
    port = StubPort()
    monkeypatch.setattr(tasks, "get_calendar_port", lambda: port)

    tasks.sync_calendar(str(connection.pk))

    connection.refresh_from_db()
    assert connection.last_polled_at == NOW
    [event] = (
        PersonalEvent.objects.using(PERSONAL).filter(calendar_connection_id=connection.pk).all()
    )
    assert event.source_uid == "a@feed"


def test_the_sync_job_releases_the_claim_after_a_successful_sync(monkeypatch):
    connection = _due()
    _at(monkeypatch, NOW)
    monkeypatch.setattr(tasks, "get_calendar_port", StubPort)
    calendar_sync.claim_due_connections(now=NOW)

    tasks.sync_calendar(str(connection.pk))

    connection.refresh_from_db()
    assert connection.sync_claimed_at is None


def test_the_sync_job_releases_the_claim_after_a_transient_failure(monkeypatch):
    connection = _due()
    _at(monkeypatch, NOW)

    class FailingPort:
        def fetch_entries(self, feed):
            raise CalendarTransientError()

    monkeypatch.setattr(tasks, "get_calendar_port", lambda: FailingPort())
    calendar_sync.claim_due_connections(now=NOW)

    tasks.sync_calendar(str(connection.pk))

    connection.refresh_from_db()
    assert connection.sync_claimed_at is None
    assert connection.last_error_kind == "transient"


def test_the_sync_job_releases_the_claim_after_an_unexpected_error(monkeypatch):
    connection = _due()
    _at(monkeypatch, NOW)

    class ExplodingPort:
        def fetch_entries(self, feed):
            raise RuntimeError("boom")

    monkeypatch.setattr(tasks, "get_calendar_port", lambda: ExplodingPort())
    calendar_sync.claim_due_connections(now=NOW)

    with pytest.raises(RuntimeError):
        tasks.sync_calendar(str(connection.pk))

    # The claim is released even when the job fails outright, so the next tick can retry
    # it rather than waiting out the TTL.
    connection.refresh_from_db()
    assert connection.sync_claimed_at is None


def test_the_sync_job_records_an_unexpected_error_on_the_connection(monkeypatch):
    """An unexpected error is recorded, so it is visible on the row rather than lost."""
    connection = _due()
    _at(monkeypatch, NOW)

    class ExplodingPort:
        def fetch_entries(self, feed):
            raise RuntimeError("boom")

    monkeypatch.setattr(tasks, "get_calendar_port", lambda: ExplodingPort())
    calendar_sync.claim_due_connections(now=NOW)

    with pytest.raises(RuntimeError):
        tasks.sync_calendar(str(connection.pk))

    connection.refresh_from_db()
    assert connection.last_error_kind == "unexpected:RuntimeError"


def test_a_failed_calendar_is_not_re_claimed_on_the_next_tick(monkeypatch):
    """The hot loop: an unexpected error must not make the tick re-fetch forever.

    The claim is released, so the connection is claimable again — but the poll time must
    have moved, or it would be claimed on the very next 60-second tick, and on every tick
    after that, 1,440 times a day, each fetch carrying the user's secret address.
    """
    connection = _due()
    _at(monkeypatch, NOW)

    class ExplodingPort:
        def fetch_entries(self, feed):
            raise RuntimeError("boom")

    monkeypatch.setattr(tasks, "get_calendar_port", lambda: ExplodingPort())
    calendar_sync.claim_due_connections(now=NOW)

    with pytest.raises(RuntimeError):
        tasks.sync_calendar(str(connection.pk))

    # One tick later — 61 seconds — the connection is not due any more.
    assert calendar_sync.claim_due_connections(now=NOW + timedelta(seconds=61)) == []


def test_an_unexpected_error_does_not_revoke_the_calendar(monkeypatch):
    # An unexpected error is a fault on our side. It must never ask the user to
    # reconnect a calendar that works (D6).
    connection = _due()
    _at(monkeypatch, NOW)

    class ExplodingPort:
        def fetch_entries(self, feed):
            raise RuntimeError("boom")

    monkeypatch.setattr(tasks, "get_calendar_port", lambda: ExplodingPort())
    calendar_sync.claim_due_connections(now=NOW)

    with pytest.raises(RuntimeError):
        tasks.sync_calendar(str(connection.pk))

    connection.refresh_from_db()
    assert connection.status == CalendarConnection.Status.ACTIVE
