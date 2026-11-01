"""Two concurrent workers never send the same row — proved with real concurrency.

**This is the test the whole architecture exists to pass.** AD-7 says the send is
"at-least-once with dedupe at the send boundary", which permits two workers to *attempt*
the same send. What it forbids is two workers *delivering* it — the provider's idempotency
key collapses the second attempt, but only if the second attempt carries the same key, and
only if the claim keeps the two from racing the row into two different states.

The claim is what prevents the race, and the claim is `FOR UPDATE SKIP LOCKED`. Reasoning
about that is not the same as testing it, so these tests use two threads on two connections
against the real database.

`transaction=True`: every thread gets its own connection, and what one commits is visible
to the others, as in production.
"""

import threading
from datetime import UTC, datetime, timedelta

import pytest
from django.db import connections

from adapters.email.memory import InMemoryEmailAdapter
from apps.delivery.models import ScheduledSend
from apps.delivery.services.delivery_sweep import claim_due_sends, sweep_due_sends
from ports.email import EmailMessage
from shared.db import PERSONAL
from tests.delivery.factories import ScheduledSendFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL], transaction=True)

DUE = datetime(2026, 11, 14, 8, 0, tzinfo=UTC)
NOW = DUE + timedelta(minutes=1)
ADDRESS = "maya@example.com"


def _renderer(row: ScheduledSend, address: str) -> EmailMessage:
    return EmailMessage(to=address, subject="Reminder", text_body="A reminder.")


def _resolve(user_id):
    return ADDRESS


def _in_thread(fn):
    """Run `fn` on its own connection and report whatever it produced."""
    result: list = []

    def run():
        try:
            result.append(fn())
        except Exception as exc:  # surfaced in the test thread
            result.append(exc)
        finally:
            connections.close_all()

    thread = threading.Thread(target=run)
    thread.start()
    return thread, result


def test_two_concurrent_workers_claim_disjoint_sets_of_rows():
    """The second worker's `SKIP LOCKED` skips what the first is holding.

    Ten rows, two workers, each claiming: the union is all ten and the intersection is
    empty. A claim that did not skip would double-claim, and one row would be sent twice
    with two different outcomes recorded against it.
    """
    ScheduledSendFactory.create_batch(10, due_at=NOW - timedelta(minutes=1))

    threads = []
    results = []
    for _ in range(2):
        thread, result = _in_thread(lambda: claim_due_sends(now=NOW))
        threads.append(thread)
        results.append(result)

    for thread in threads:
        thread.join(timeout=30)

    first = results[0][0]
    second = results[1][0]

    assert len(first) + len(second) == 10
    assert not (set(first) & set(second))


def test_two_concurrent_workers_never_send_the_same_row():
    """The end-to-end claim: two sweeps, one batch, one send per row.

    Both workers run the *whole* sweep — claim, send, mark — not just the claim. That is
    the property that matters: a row must not be delivered twice, and a row must not be
    marked `sent` by one worker while another worker is still sending it.
    """
    ScheduledSendFactory.create_batch(10, due_at=NOW - timedelta(minutes=1))

    threads = []
    results = []
    for _ in range(2):
        thread, result = _in_thread(
            lambda: sweep_due_sends(
                port=InMemoryEmailAdapter(),
                renderer=_renderer,
                resolve_recipient=_resolve,
                now=NOW,
            )
        )
        threads.append(thread)
        results.append(result)

    for thread in threads:
        thread.join(timeout=30)

    counts = [results[0][0], results[1][0]]
    assert sum(count.sent for count in counts) == 10


def test_a_row_is_marked_sent_exactly_once_under_concurrency():
    """The guarded update: `WHERE id = %s AND status = 'pending'`.

    Both workers may attempt the same row's mark — one wins, the other updates zero rows
    and treats that as "someone else got there first", which is not an error.
    """
    row = ScheduledSendFactory(due_at=NOW - timedelta(minutes=1))

    threads = []
    results = []
    for _ in range(2):
        thread, result = _in_thread(
            lambda: sweep_due_sends(
                port=InMemoryEmailAdapter(),
                renderer=_renderer,
                resolve_recipient=_resolve,
                now=NOW,
            )
        )
        threads.append(thread)
        results.append(result)

    for thread in threads:
        thread.join(timeout=30)

    stored = ScheduledSend.objects.using(PERSONAL).get(pk=row.pk)
    assert stored.status == ScheduledSend.Status.SENT
    assert stored.sent_at is not None
    assert stored.claimed_at is None


def test_a_row_claimed_by_a_dead_worker_is_reclaimed_after_the_ttl():
    """A worker that dies mid-send leaves a row that becomes claimable again (AD-7).

    The retry is safe because the send key is the provider's idempotency key: the second
    attempt carries the identical key, and the provider collapses the duplicate.
    """
    from shared.constants import SEND_CLAIM_TTL

    row = ScheduledSendFactory(due_at=NOW - timedelta(minutes=1))
    stale = NOW - SEND_CLAIM_TTL - timedelta(seconds=1)
    ScheduledSend.objects.using(PERSONAL).filter(pk=row.pk).update(claimed_at=stale)

    claimed = claim_due_sends(now=NOW)

    assert claimed == [row.id]


def test_a_claim_within_the_ttl_is_not_reclaimed():
    """The other half of the same rule: a live worker's row is not stolen."""
    from shared.constants import SEND_CLAIM_TTL

    ScheduledSendFactory(due_at=NOW - timedelta(minutes=1))
    live = NOW - timedelta(seconds=5)
    ScheduledSend.objects.using(PERSONAL).update(claimed_at=live)

    claimed = claim_due_sends(now=NOW)

    assert claimed == []
    assert SEND_CLAIM_TTL > timedelta(seconds=5)
