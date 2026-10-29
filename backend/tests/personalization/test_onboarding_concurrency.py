"""The onboarding commands under concurrency (FR-1).

Two requests for the same user can be in flight at once: a double-click, a retried
request, two browser tabs, a mobile client and a web client. Each of these tests races
two writers against each other and asserts that the loser of the race gets a **correct
answer**, not a 500.

**The rule these pin:** a unique constraint must not surface as an `IntegrityError`.
The constraint is the last line of defence, not the error handler. A caller who races
another caller should end up with one row and one answer, never with a stack trace.

The clock is fixed throughout — no test sleeps, and each writer is released by a barrier
so the two really do overlap.
"""

import threading
from datetime import UTC, datetime, time

import pytest
from django.db import connections

from apps.personalization.models import DigestPreference, Interest, OnboardingProgress
from apps.personalization.services.onboarding import (
    advance_step,
    set_digest_preference,
    set_interests,
    skip_step,
)
from shared.actor import Actor
from shared.db import PERSONAL
from shared.ids import uuid7

# `transaction=True` so the rows are committed and the other thread can see them —
# without it the second thread would find nothing and the test would pass vacuously.
pytestmark = pytest.mark.django_db(databases=[PERSONAL], transaction=True)

USER = uuid7()
NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)


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


# --- The digest preference --------------------------------------------------------------------


def test_two_concurrent_digest_writes_do_not_collide():
    """Two writers, one row, no error.

    Without the lock, both writers find no row and both insert — and the loser of that
    race gets a raw `IntegrityError` from the unique constraint, which reaches the
    caller as a 500.
    """

    def write(zone: str) -> callable:
        return lambda: set_digest_preference(
            user_id=USER,
            delivery_time=time(9, 0),
            timezone_name=zone,
            actor=Actor.user(USER),
            now=NOW,
        )

    errors = race(write("UTC"), write("Europe/London"))

    assert errors == []
    assert DigestPreference.objects.using(PERSONAL).count() == 1


def test_two_concurrent_digest_writes_leave_one_coherent_row():
    """The row that survives is a whole row — not half of each writer's values."""
    errors = race(
        lambda: set_digest_preference(
            user_id=USER,
            delivery_time=time(9, 0),
            timezone_name="UTC",
            actor=Actor.user(USER),
            now=NOW,
        ),
        lambda: set_digest_preference(
            user_id=USER,
            delivery_time=time(17, 30),
            timezone_name="Europe/London",
            actor=Actor.user(USER),
            now=NOW,
        ),
    )

    assert errors == []
    preference = DigestPreference.objects.using(PERSONAL).get()
    # Either writer's pair, but never a mix of the two.
    assert (preference.delivery_time, preference.timezone) in {
        (time(9, 0), "UTC"),
        (time(17, 30), "Europe/London"),
    }


def test_a_concurrent_digest_write_over_an_existing_row_does_not_collide():
    """The row exists, so both writers take the update path — and both succeed."""
    set_digest_preference(
        user_id=USER,
        delivery_time=time(9, 0),
        timezone_name="UTC",
        actor=Actor.user(USER),
        now=NOW,
    )

    errors = race(
        lambda: set_digest_preference(
            user_id=USER,
            delivery_time=time(10, 0),
            timezone_name="UTC",
            actor=Actor.user(USER),
            now=NOW,
        ),
        lambda: set_digest_preference(
            user_id=USER,
            delivery_time=time(11, 0),
            timezone_name="UTC",
            actor=Actor.user(USER),
            now=NOW,
        ),
    )

    assert errors == []
    assert DigestPreference.objects.using(PERSONAL).count() == 1


# --- The interests ----------------------------------------------------------------------------


def test_two_concurrent_interest_writes_do_not_collide():
    """Two writers pick the same chip. The constraint must not surface as a 500."""

    def write(keys: list[str]) -> callable:
        return lambda: set_interests(
            user_id=USER,
            chip_keys=keys,
            actor=Actor.user(USER),
            now=NOW,
        )

    errors = race(write(["tech_meetups"]), write(["tech_meetups"]))

    assert errors == []
    assert Interest.objects.using(PERSONAL).count() == 1


def test_two_concurrent_interest_writes_leave_one_whole_set():
    """The surviving set is one writer's set, not a mix of the two."""
    errors = race(
        lambda: set_interests(
            user_id=USER,
            chip_keys=["tech_meetups", "arts_culture"],
            actor=Actor.user(USER),
            now=NOW,
        ),
        lambda: set_interests(
            user_id=USER,
            chip_keys=["family_kids", "sports_fitness"],
            actor=Actor.user(USER),
            now=NOW,
        ),
    )

    assert errors == []
    keys = set(Interest.objects.using(PERSONAL).values_list("chip_key", flat=True))
    assert keys in (
        {"tech_meetups", "arts_culture"},
        {"family_kids", "sports_fitness"},
    )


# --- The progress row --------------------------------------------------------------------------


def test_two_concurrent_advances_do_not_collide():
    """Both writers want a progress row, and there is only one slot for it.

    Without the lock, both writers find no row and both create one — and the loser gets
    a raw `IntegrityError` from the unique constraint.
    """
    errors = race(
        lambda: advance_step(user_id=USER, actor=Actor.user(USER), now=NOW),
        lambda: advance_step(user_id=USER, actor=Actor.user(USER), now=NOW),
    )

    assert errors == []
    assert OnboardingProgress.objects.using(PERSONAL).count() == 1


def test_two_concurrent_advances_leave_one_row():
    """One row, and it is the one row the user is allowed."""
    errors = race(
        lambda: advance_step(user_id=USER, actor=Actor.user(USER), now=NOW),
        lambda: advance_step(user_id=USER, actor=Actor.user(USER), now=NOW),
    )

    assert errors == []
    progress = OnboardingProgress.objects.using(PERSONAL).get()
    assert progress.current_step in (2, 3)


def test_a_concurrent_advance_and_skip_do_not_collide():
    """An advance and a skip race for the same row."""
    errors = race(
        lambda: advance_step(user_id=USER, actor=Actor.user(USER), now=NOW),
        lambda: skip_step(user_id=USER, actor=Actor.user(USER), now=NOW),
    )

    assert errors == []
    assert OnboardingProgress.objects.using(PERSONAL).count() == 1


def test_a_concurrent_skip_and_interest_write_do_not_collide():
    """A skip that clears the interests and a write that sets them, at once.

    The skip deletes the rows and the write inserts one of the same keys. Without a
    shared lock, they interleave into a unique-constraint violation.
    """
    set_interests(
        user_id=USER,
        chip_keys=["tech_meetups"],
        actor=Actor.user(USER),
        now=NOW,
    )
    advance_step(user_id=USER, actor=Actor.user(USER), now=NOW)

    errors = race(
        lambda: skip_step(user_id=USER, actor=Actor.user(USER), now=NOW),
        lambda: set_interests(
            user_id=USER,
            chip_keys=["tech_meetups"],
            actor=Actor.user(USER),
            now=NOW,
        ),
    )

    assert errors == []
    assert Interest.objects.using(PERSONAL).count() <= 1
