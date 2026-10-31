"""The digest dispatcher under concurrency (D1, D4).

Two workers can be ticking at the same moment. The acceptance criterion is explicit:
"Two workers ticking at once must not compose the same user's digest twice … **A test
exercises the concurrent path rather than assuming the constraint covers it.**"

So this file races two real dispatchers against each other, in two real threads, over
a real committed row — and asserts that **one digest** comes out.

**Why `transaction=True`.** Without it, pytest wraps the test in a transaction that is
never committed, and the second thread's connection cannot see the first thread's rows.
The test would pass vacuously: both threads would find nothing to claim, and "one
digest" would be true because there were no digests at all. With it, the rows are
committed and the other thread really does see them.

**The clock is fixed throughout** — no test sleeps, and the two dispatchers are
released by a barrier so they really do overlap.
"""

import threading
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

import pytest
from django.db import connections

from apps.personalization.models import DigestPreference, PulseDigest
from apps.personalization.services.digest_composition import compose_digest
from apps.personalization.services.digest_scheduling import claim_due_digests
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from tests.personalization.factories import DigestPreferenceFactory

#: `transaction=True` so the rows are committed and the other thread can see them —
#: without it the second thread would find nothing and the test would pass vacuously.
pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG], transaction=True)

ZONE = "America/Los_Angeles"
NOW = datetime(2026, 11, 4, 17, 0, tzinfo=UTC)


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
            # **Every** alias, not just `personal`. The composition reads the catalog as
            # well as the personal schema, and a thread that leaves a connection open
            # holds a session on the test database — which the suite's teardown cannot
            # drop.
            for alias in (PERSONAL, CATALOG):
                connections[alias].close()

    threads = [threading.Thread(target=runner, args=(function,)) for function in functions]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    return errors


def make_due_preference():
    """A preference whose delivery time has already arrived."""
    return DigestPreferenceFactory(
        delivery_time=time(9, 0),
        timezone=ZONE,
    )


# --- The claim ------------------------------------------------------------------------------


def test_two_concurrent_dispatchers_claim_the_user_once():
    """**One claim, one job.**

    The claim is taken under a **row lock** (`SELECT … FOR UPDATE`), so the two
    dispatchers are serialised: the second one waits for the first to commit, and then
    re-reads the row and finds it already claimed.

    **`SKIP LOCKED` is the liveness half, not the correctness half.** With the lock
    but without `SKIP LOCKED`, the second dispatcher would *block* on the row the first
    is holding — and would still find it claimed when it woke up. `SKIP LOCKED` is what
    stops it blocking: the dispatcher moves on to the next user instead of waiting.

    **The test was checked against a broken implementation.** Removing the row lock
    makes this test fail with the user claimed twice; removing only `SKIP LOCKED`
    makes it still pass. That is the honest division of labour, and the test's
    assertion names it.
    """
    preference = make_due_preference()
    claimed: list[list] = []
    lock = threading.Lock()

    def dispatch() -> None:
        result = claim_due_digests(now=NOW)
        with lock:
            claimed.append(result)

    errors = race(dispatch, dispatch)

    assert errors == []
    total = [user_id for batch in claimed for user_id in batch]
    assert total.count(preference.user_id) == 1, (
        "the two dispatchers claimed the same user; the row lock should have "
        "serialised them, so the second one finds the row already claimed"
    )


def test_two_concurrent_dispatchers_do_not_collide():
    """Neither dispatcher raises. A unique-constraint violation must not surface as an
    error — the constraint is the last line of defence, not the error handler."""
    make_due_preference()

    errors = race(lambda: claim_due_digests(now=NOW), lambda: claim_due_digests(now=NOW))

    assert errors == []


def test_the_claim_is_left_on_the_preference():
    """The winning dispatcher set the claim, and it is still there."""
    preference = make_due_preference()

    race(lambda: claim_due_digests(now=NOW), lambda: claim_due_digests(now=NOW))

    assert (
        DigestPreference.objects.using(PERSONAL)
        .filter(user_id=preference.user_id)
        .values_list("digest_claimed_at", flat=True)
        .first()
        is not None
    )


# --- The digest ------------------------------------------------------------------------------


def test_two_concurrent_dispatchers_produce_one_digest():
    """**The criterion, end to end.**

    Two dispatchers claim the same due user at the same moment, and both compose it.
    The composition is idempotent — it takes a per-user advisory lock and returns the
    existing digest with `created=False` — so the outcome is **one digest**, not two.

    This is the case the criterion names: "Two workers ticking at once must not compose
    the same user's digest twice."
    """
    preference = make_due_preference()
    composed: list = []
    lock = threading.Lock()

    def dispatch_and_compose() -> None:
        for user_id in claim_due_digests(now=NOW):
            result = compose_digest(
                user_id=user_id,
                actor=Actor.system("digest_composer"),
                now=NOW,
            )
            with lock:
                composed.append(result.created)

    errors = race(dispatch_and_compose, dispatch_and_compose)

    assert errors == []
    assert (
        PulseDigest.objects.using(PERSONAL)
        .filter(
            user_id=preference.user_id,
            local_date=NOW.astimezone(ZoneInfo(ZONE)).date(),
        )
        .count()
        == 1
    )
    # And exactly one of the two compositions created it — the other found it there.
    assert sum(composed) == 1


def test_two_concurrent_compositions_of_the_same_digest_do_not_collide():
    """**The composition's own guard**, exercised directly.

    Even when two workers compose the same user at the same moment — which the claim
    is supposed to prevent — the per-user advisory lock makes the second one wait and
    find the first one's digest. The loser gets an answer, not an `IntegrityError`.
    """
    preference = make_due_preference()
    results: list = []
    lock = threading.Lock()

    def compose() -> None:
        result = compose_digest(
            user_id=preference.user_id,
            actor=Actor.system("digest_composer"),
            now=NOW,
        )
        with lock:
            results.append(result)

    errors = race(compose, compose)

    assert errors == []
    assert len(results) == 2
    assert sum(1 for result in results if result.created) == 1
    assert len({result.digest_id for result in results}) == 1
