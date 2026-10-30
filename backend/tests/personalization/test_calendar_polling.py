"""The calendar polling dispatcher (AD-7, AD-8 of the calendar-sync design).

The polling path mirrors `ingestion`'s scheduling exactly, and the properties pinned here
are the ones that make it safe to run two ticks at once:

- a **due** connection (active, and due now or overdue) is claimed;
- a connection that is **not due** is not claimed;
- a **disconnected** or **needs_reconnect** connection is never claimed — there is no
  credential to fetch with, or the user has to paste a new one first;
- the claim is **atomic**: two overlapping claims never take the same connection;
- an **expired** claim is a lost job (a worker died) and the connection becomes claimable
  again;
- the claim is **bounded**, so one tick cannot take the whole table;
- the **ordering** is least-recently-polled first, so no connection starves.

The claim is the whole mechanism: it is what stops two overlapping ticks syncing the same
connection twice.
"""

import threading
from datetime import UTC, datetime, timedelta

import pytest
from django.db import connections, transaction

from apps.personalization.models import CalendarConnection
from apps.personalization.services.calendar_sync import (
    claim_due_connections,
    record_unexpected_failure,
    release_claim,
)
from shared.constants import CALENDAR_CLAIM_TTL, CALENDAR_POLL_INTERVAL, CALENDAR_SYNC_BATCH
from shared.db import PERSONAL
from tests.personalization.factories import CalendarConnectionFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


def _due(**kwargs) -> CalendarConnection:
    return CalendarConnectionFactory(next_poll_at=NOW - timedelta(minutes=1), **kwargs)


def _not_due(**kwargs) -> CalendarConnection:
    return CalendarConnectionFactory(next_poll_at=NOW + timedelta(hours=1), **kwargs)


def test_a_due_connection_is_claimed():
    connection = _due()

    claimed = claim_due_connections(now=NOW)

    assert claimed == [connection.pk]


def test_a_connection_that_is_not_due_is_not_claimed():
    _not_due()

    assert claim_due_connections(now=NOW) == []


def test_a_connection_that_has_never_been_polled_is_due():
    # A NULL `next_poll_at` means "never polled", so it is due at once. The connect
    # command sets the due time, but a row written by any other path is still picked up.
    connection = CalendarConnectionFactory(next_poll_at=None)

    assert claim_due_connections(now=NOW) == [connection.pk]


def test_a_needs_reconnect_connection_is_not_claimed():
    _due(status=CalendarConnection.Status.NEEDS_RECONNECT)

    # The provider revoked the credential; the user must paste a new address before there
    # is anything to fetch.
    assert claim_due_connections(now=NOW) == []


def test_a_disconnected_connection_is_not_claimed():
    # A disconnected connection has no credential — the model says so — so there is
    # nothing to fetch with.
    _due(status=CalendarConnection.Status.DISCONNECTED, credential=None)

    assert claim_due_connections(now=NOW) == []


def test_a_claimed_connection_is_not_claimed_again():
    connection = _due()

    first = claim_due_connections(now=NOW)
    second = claim_due_connections(now=NOW)

    assert first == [connection.pk]
    assert second == []


def test_an_expired_claim_becomes_claimable_again():
    connection = _due()
    claim_due_connections(now=NOW)
    CalendarConnection.objects.using(PERSONAL).filter(pk=connection.pk).update(
        sync_claimed_at=NOW - CALENDAR_CLAIM_TTL - timedelta(minutes=1)
    )

    # The worker died holding the claim, so the job was lost. The connection becomes
    # claimable again — well before the next scheduled poll, since the TTL is shorter than
    # the poll interval.
    assert claim_due_connections(now=NOW) == [connection.pk]


def test_a_live_claim_is_not_claimable_again():
    connection = _due()
    claim_due_connections(now=NOW)
    CalendarConnection.objects.using(PERSONAL).filter(pk=connection.pk).update(
        sync_claimed_at=NOW - timedelta(minutes=1)
    )

    assert claim_due_connections(now=NOW) == []


def test_the_claim_is_bounded():
    for _ in range(CALENDAR_SYNC_BATCH + 5):
        _due()

    claimed = claim_due_connections(now=NOW)

    assert len(claimed) == CALENDAR_SYNC_BATCH


def test_the_claim_batch_size_is_configurable():
    for _ in range(3):
        _due()

    assert len(claim_due_connections(now=NOW, limit=2)) == 2


@pytest.mark.django_db(databases=[PERSONAL], transaction=True)
def test_the_claim_takes_the_row_atomically():
    """SKIP LOCKED: while one claim holds its rows, the other takes the rest.

    `transaction=True` because the rows must be **committed** for the other thread's own
    connection to see them — inside a test transaction they would be invisible.
    """
    connections_to_claim = [_due() for _ in range(4)]
    holding, release = threading.Event(), threading.Event()
    results: dict = {}

    def first_claimer():
        try:  # this thread's own connection
            with transaction.atomic(using=PERSONAL):
                ids = list(
                    CalendarConnection.objects.using(PERSONAL)
                    .select_for_update()
                    .filter(pk__in=[c.pk for c in connections_to_claim[:2]])
                    .values_list("pk", flat=True)
                )
                results["held"] = ids
                holding.set()
                release.wait(timeout=10)
        finally:
            connections.close_all()

    thread = threading.Thread(target=first_claimer)
    thread.start()
    holding.wait(timeout=10)
    try:
        claimed = claim_due_connections(now=NOW)
    finally:
        release.set()
        thread.join(timeout=10)

    held = set(results["held"])
    assert held
    # The two claims are disjoint: the second one skipped the rows the first was holding.
    assert set(claimed).isdisjoint(held)
    assert len(set(claimed)) == len(claimed)


def test_the_claim_marks_the_connection():
    connection = _due()

    claim_due_connections(now=NOW)

    connection.refresh_from_db()
    assert connection.sync_claimed_at == NOW


def test_releasing_the_claim_makes_the_connection_claimable_again():
    connection = _due()
    claim_due_connections(now=NOW)

    release_claim(connection.pk)

    connection.refresh_from_db()
    assert connection.sync_claimed_at is None
    assert claim_due_connections(now=NOW) == [connection.pk]


def test_the_least_recently_polled_connection_is_claimed_first():
    # The ordering is by the last poll, oldest first, so no connection starves.
    oldest = _due(last_polled_at=NOW - timedelta(days=3))
    newest = _due(last_polled_at=NOW - timedelta(hours=1))

    claimed = claim_due_connections(now=NOW)

    assert claimed[0] == oldest.pk
    assert set(claimed) == {oldest.pk, newest.pk}


def test_the_claim_writes_an_audit_row():
    from apps.personalization.models import PersonalizationAuditEntry

    connection = _due()

    claim_due_connections(now=NOW)

    [row] = (
        PersonalizationAuditEntry.objects.using(PERSONAL).filter(action="claim_calendar_sync").all()
    )
    assert row.target_id == connection.pk
    assert row.actor_kind == "system"
    assert row.actor_label == "calendar_scheduler"


def test_releasing_a_claim_writes_no_audit_row():
    from apps.personalization.models import PersonalizationAuditEntry

    connection = _due()
    claim_due_connections(now=NOW)

    release_claim(connection.pk)

    # The sync's own audit row closes the claim; a second row would be noise.
    assert (
        PersonalizationAuditEntry.objects.using(PERSONAL)
        .filter(action="release_calendar_sync")
        .count()
        == 0
    )


def test_an_unexpected_failure_schedules_the_next_poll():
    """An error the sync does not handle must still move the next poll time.

    The four handled failures each write the next poll time. An unhandled one — a
    malformed feed entry, a constraint violation — used to skip that, leaving the poll
    time in the past. The connection was then due again on the very next 60-second tick,
    and on every tick after that, forever.
    """
    connection = _due()

    record_unexpected_failure(
        connection_id=connection.pk,
        error_kind="unexpected:ValueError",
        now=NOW,
    )

    connection.refresh_from_db()
    assert connection.next_poll_at == NOW + CALENDAR_POLL_INTERVAL
    assert connection.last_error_kind == "unexpected:ValueError"


def test_an_unexpected_failure_does_not_revoke_the_connection():
    # An unexpected error is a fault on our side. It must never ask the user to
    # reconnect a calendar that works (D6).
    connection = _due()

    record_unexpected_failure(
        connection_id=connection.pk,
        error_kind="unexpected:ValueError",
        now=NOW,
    )

    connection.refresh_from_db()
    assert connection.status == CalendarConnection.Status.ACTIVE


def test_a_failed_connection_is_not_re_claimed_on_the_next_tick():
    """The hot loop: a failed connection must not be re-fetched every 60 seconds.

    Without the failure being recorded, the claim was released and the poll time stayed
    in the past, so the connection was claimed again on the next tick — 1,440 times a day,
    each fetch carrying the user's secret calendar address.
    """
    connection = _due()
    claim_due_connections(now=NOW)

    # The job failed unexpectedly, so the worker recorded the failure and released the
    # claim.
    record_unexpected_failure(
        connection_id=connection.pk,
        error_kind="unexpected:ValueError",
        now=NOW,
    )
    release_claim(connection.pk)

    # One tick later — 61 seconds — the connection is not due any more.
    assert claim_due_connections(now=NOW + timedelta(seconds=61)) == []
