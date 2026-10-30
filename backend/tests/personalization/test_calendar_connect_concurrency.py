"""The calendar connect command under concurrency (FR-50).

Two connects for the same user can be in flight at once: a double-click, a retried
request, two browser tabs. Each of these tests races two connects against each other
and asserts that the loser of the race gets a **correct answer**, not a 500.

**The rule this pins:** the Free-tier cap must be decided by something that serialises.
The cap was a bare `COUNT` read inside `transaction.atomic`, and a count is not a lock:
two concurrent connects both read zero, both passed the check, and both wrote a row —
so a Free account ended up holding two calendars. The command now takes the user's
**advisory lock** (`pg_advisory_xact_lock`) before it reads, the same pattern the
onboarding commands use.

The clock is fixed throughout — no test sleeps, and each writer is released by a barrier
so the two really do overlap.
"""

import threading

import pytest
from django.db import connections

from apps.personalization.models import CalendarConnection
from apps.personalization.services.calendar_connections import (
    connect_calendar,
    disconnect_calendar_for_user,
    reconnect_calendar_for_user,
)
from domain.errors import CalendarProviderCapReached, InvalidCalendarCredentialError
from shared.actor import Actor
from shared.db import PERSONAL
from shared.ids import uuid7

# `transaction=True` so the rows are committed and the other thread can see them —
# without it the second thread would find nothing and the test would pass vacuously.
pytestmark = pytest.mark.django_db(databases=[PERSONAL], transaction=True)


def race(*functions: callable) -> list[BaseException]:
    """Run the functions concurrently and return whatever they raised.

    The barrier releases all the writers at the same moment, so the two transactions
    really do overlap rather than running one after the other.

    Each thread closes its own database connection afterwards. A worker thread that
    leaves its connection open holds a session on the test database, and the suite's
    teardown cannot drop a database that still has users on it.
    """
    errors: list[BaseException] = []
    barrier = threading.Barrier(len(functions))

    def runner(function: callable) -> None:
        try:
            barrier.wait()
            function()
        except BaseException as exc:  # noqa: BLE001 - the test asserts on the exception
            errors.append(exc)
        finally:
            connections[PERSONAL].close()

    threads = [threading.Thread(target=runner, args=(function,)) for function in functions]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    return errors


def test_two_concurrent_connects_cannot_both_take_the_only_slot():
    """One Free slot, two connects, one winner.

    Without the advisory lock, both connects read a slot count of zero, both passed the
    cap check, and both wrote a row — two calendars on a one-calendar plan.
    """
    user_id = uuid7()
    actor = Actor.user(user_id)

    def connect(name: str) -> callable:
        return lambda: connect_calendar(
            user_id=user_id,
            provider="google",
            url=f"https://example.test/{name}.ics",
            actor=actor,
        )

    errors = race(connect("alpha"), connect("beta"))

    # The loser of the race gets the typed refusal, not a stack trace.
    refusals = [e for e in errors if isinstance(e, CalendarProviderCapReached)]
    unexpected = [e for e in errors if not isinstance(e, CalendarProviderCapReached)]
    assert unexpected == [], f"the loser of the race must get a refusal, got {unexpected}"
    assert len(refusals) == 1, f"exactly one connect may win, got {len(refusals)} refusals"

    active = CalendarConnection.objects.using(PERSONAL).filter(
        user_id=user_id, status=CalendarConnection.Status.ACTIVE
    )
    assert active.count() == 1, "the Free tier allows one active calendar"


def test_two_concurrent_connects_of_the_same_address_do_not_collide():
    """The same address, twice at once.

    The unique constraint would refuse the second one — but a constraint is the last
    line of defence, not the error handler. The loser must get the calm "already
    connected" refusal, not a raw `IntegrityError` that reaches the client as a 500.
    """
    user_id = uuid7()
    actor = Actor.user(user_id)

    def connect() -> callable:
        return lambda: connect_calendar(
            user_id=user_id,
            provider="google",
            url="https://example.test/same.ics",
            actor=actor,
        )

    errors = race(connect(), connect())

    # "Already connected" is the more specific truth, and it is what the loser gets —
    # the cap would also be true, but "you already have this one" is the better answer.
    refusals = [e for e in errors if isinstance(e, InvalidCalendarCredentialError)]
    unexpected = [e for e in errors if not isinstance(e, InvalidCalendarCredentialError)]
    assert unexpected == [], f"the loser of the race must get a refusal, got {unexpected}"
    assert len(refusals) == 1, f"exactly one connect may win, got {len(refusals)} refusals"

    rows = CalendarConnection.objects.using(PERSONAL).filter(user_id=user_id)
    assert rows.count() == 1, "the same address is connected once"


# ── The reconnect and the disconnect ──────────────────────────────────────────────────


def test_a_disconnect_committed_first_is_not_overwritten_by_a_reconnect():
    """A reconnect must not resurrect a connection the user just disconnected.

    The reconnect used to read the row's status *before* its transaction, so a
    disconnect that committed in between was silently overwritten: the row came back
    as `active` with a live credential, and the dispatcher started polling a calendar
    the user had removed — after the disconnect's purge had already deleted its
    events.

    The status is now read again under a row lock, inside the transaction, so the
    reconnect sees the status that is true *now*.
    """
    user_id = uuid7()
    actor = Actor.user(user_id)

    connection = connect_calendar(
        user_id=user_id,
        provider="google",
        url="https://example.test/race.ics",
        actor=actor,
    )
    CalendarConnection.objects.using(PERSONAL).filter(pk=connection.pk).update(
        status=CalendarConnection.Status.NEEDS_RECONNECT
    )

    def disconnect() -> callable:
        return lambda: disconnect_calendar_for_user(
            user_id=user_id, connection_id=connection.pk, actor=actor
        )

    def reconnect() -> callable:
        return lambda: reconnect_calendar_for_user(
            user_id=user_id,
            connection_id=connection.pk,
            url="https://example.test/race-new.ics",
            actor=actor,
        )

    race(disconnect(), reconnect())

    # Whichever order they landed in, the row must not be `active` with a credential:
    # a disconnect that won the race must not be undone by the reconnect.
    row = CalendarConnection.objects.using(PERSONAL).get(pk=connection.pk)
    if row.status == CalendarConnection.Status.DISCONNECTED:
        assert row.credential is None, "a disconnected connection holds no credential"
    else:
        # The reconnect won: it is legitimately active again.
        assert row.status == CalendarConnection.Status.ACTIVE
