"""The recomposition triggers: the three writes that change what today's digest could hold.

**The bug these close.** A digest is composed once, early in the user's local day, from
the pools as they were at that moment. When it came out **empty**, the user was told
"No qualifying events in {city}" — and then set their home city, saved an event or added
one to their agenda, and the page went on saying it until the next day's run. The empty
digest was a statement about pools that had since moved.

**The properties a user would notice if they broke.**

- **Setting a home city** asks for a recomposition, so the digest stops naming the city
  the user just left.
- **Saving an event** asks for one; a **repeat** save does not, because it changes no
  pool — it is the same row returned again.
- **Adding a personal event** asks for one.
- The job is queued **after the commit**, because a worker cannot see an uncommitted
  row — the whole point is to compose from the pool the write just changed.
- A **broker outage does not fail the user's write**: the save, the city and the event
  all stand, and the scheduler is the backstop.
- Only the **user id** travels (AD-13).

**What these tests do not assert.** Whether the digest is actually replaced is
`test_digest_composition.py`'s business — the enqueue only *asks*, and the composition
decides (it replaces an empty digest and never a composed one). Asserting the outcome
here would duplicate that decision in a second place.

**On the `on_commit` callbacks.** `pytest`'s `django_db` fixture wraps every test in a
transaction that is rolled back, so Django's `on_commit` callbacks never fire on their
own. The fixtures capture them, exactly as `test_digest_enqueue.py` does.

**The clock is fixed throughout** — no test sleeps.
"""

from datetime import UTC, datetime, timedelta

import pytest
from django.db import transaction

from apps.personalization.models import DigestPreference
from apps.personalization.services import digest_enqueue
from apps.personalization.services.digest_preferences import (
    set_home_city,
    set_include_personal_events,
)
from apps.personalization.services.personal_events import create_personal_event
from apps.personalization.services.saved_events import save_event
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from shared.ids import uuid7
from tests.ingestion.factories import EventFactory, VenueFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

NOW = datetime(2026, 11, 4, 16, 0, tzinfo=UTC)
COMPOSE = "worker.tasks.compose_digest"


@pytest.fixture
def sent(monkeypatch):
    """Record the jobs the commands enqueue instead of publishing them."""
    jobs: list[tuple[str, list]] = []
    monkeypatch.setattr(digest_enqueue, "_send", lambda name, args: jobs.append((name, list(args))))
    return jobs


@pytest.fixture
def on_commit(monkeypatch):
    """Capture the `on_commit` callbacks the commands register, and run them on demand.

    The real `on_commit` is kept in place — only the dispatch is intercepted — so the
    command still registers through Django's own machinery, and `robust` is honoured the
    way Django's runner honours it.
    """
    captured: list = []
    original = transaction.on_commit

    def capture(func, using=None, robust=False):
        captured.append((func, using, robust))
        return original(func, using=using, robust=robust)

    monkeypatch.setattr(transaction, "on_commit", capture)

    def run():
        import logging

        for func, _using, robust in captured:
            if robust:
                try:
                    func()
                except Exception:
                    logging.getLogger("django.db.backends.base").exception(
                        "Error calling %s in on_commit().", getattr(func, "__qualname__", func)
                    )
            else:
                func()

    run.captured = captured
    return run


def actor(user_id):
    return Actor.user(user_id)


def make_public_event(title="Harbour Lights Trio"):
    """A published event the user can save, starting after `NOW`."""
    return EventFactory(
        title=title,
        venue=VenueFactory(city="Dhaka", venue_fingerprint=f"venue-{title}"),
        start_time_utc=NOW + timedelta(hours=4),
        last_seen_at=NOW,
    )


def add_personal_event(user_id):
    start = NOW + timedelta(hours=3)
    return create_personal_event(
        user_id=user_id,
        name="Standup",
        start_utc=start,
        end_utc=start + timedelta(hours=1),
        start_time_tz="Asia/Dhaka",
        location=None,
        notes=None,
        actor=actor(user_id),
        now=NOW,
    )


# --- the three triggers --------------------------------------------------------------


def test_setting_a_home_city_asks_for_a_recomposition(sent, on_commit):
    """The reported bug: the digest went on naming the city the user had just left."""
    user_id = uuid7()

    set_home_city(user_id=user_id, city="Dhaka", source="choice", actor=actor(user_id), now=NOW)
    on_commit()

    assert sent == [(COMPOSE, [str(user_id)])]


def test_clearing_the_home_city_asks_for_one_too(sent, on_commit):
    """Having no city is a different pool, not an absent one — the nearby slot widens."""
    user_id = uuid7()
    set_home_city(user_id=user_id, city="Dhaka", source="choice", actor=actor(user_id), now=NOW)
    sent.clear()
    on_commit.captured.clear()

    set_home_city(user_id=user_id, city=None, source="choice", actor=actor(user_id), now=NOW)
    on_commit()

    assert sent == [(COMPOSE, [str(user_id)])]


def test_saving_an_event_asks_for_a_recomposition(sent, on_commit):
    user_id = uuid7()
    event = make_public_event()

    save_event(user_id=user_id, event_id=event.id, actor=actor(user_id), now=NOW)
    on_commit()

    assert sent == [(COMPOSE, [str(user_id)])]


def test_saving_the_same_event_again_asks_for_nothing(sent, on_commit):
    """A repeat save is the same row returned again, so no pool changed."""
    user_id = uuid7()
    event = make_public_event()
    save_event(user_id=user_id, event_id=event.id, actor=actor(user_id), now=NOW)
    on_commit()
    sent.clear()
    on_commit.captured.clear()

    save_event(user_id=user_id, event_id=event.id, actor=actor(user_id), now=NOW)
    on_commit()

    assert sent == []


def test_adding_a_personal_event_asks_for_a_recomposition(sent, on_commit):
    user_id = uuid7()

    add_personal_event(user_id)
    on_commit()

    assert sent == [(COMPOSE, [str(user_id)])]


def test_a_write_that_changes_no_pool_asks_for_nothing(sent, on_commit):
    """A guard against enqueueing from every preference write.

    The personal-events opt-out does change the digest — but it is FR-19's own switch,
    with its own behaviour, and it is deliberately not wired here. This test is what
    would notice if the enqueue were added to `_write_preference` wholesale instead of
    to the commands that change a candidate pool.
    """
    user_id = uuid7()

    set_include_personal_events(user_id=user_id, include=False, actor=actor(user_id), now=NOW)
    on_commit()

    assert sent == []


# --- how it is enqueued ---------------------------------------------------------------


def test_the_job_is_queued_after_the_commit_not_inside_it(sent, on_commit):
    """A worker cannot see an uncommitted row, so composing before the commit composes
    from the pool as it was *before* the write the enqueue exists to react to."""
    user_id = uuid7()

    set_home_city(user_id=user_id, city="Dhaka", source="choice", actor=actor(user_id), now=NOW)

    assert sent == [], "nothing is sent until the transaction commits"
    on_commit()
    assert sent == [(COMPOSE, [str(user_id)])]


def test_the_callback_is_registered_on_the_personal_alias_and_robustly(on_commit):
    """`robust=True` is what keeps a broker outage from failing the user's write.

    **Two callbacks now, and both are robust.** Setting a home city asks for a
    recomposition *and* asks `ingestion` to start collecting for the city
    (city-picker-and-auto-collection) — and the second one writes in the `catalog`
    schema, which is exactly the kind of slow or broken call that must not fail the
    reader's save. The assertion is on **every** callback, so a future one registered
    without `robust=True` fails here rather than at a reader's expense.
    """
    user_id = uuid7()

    set_home_city(user_id=user_id, city="Dhaka", source="choice", actor=actor(user_id), now=NOW)

    captured = [(using, robust) for _f, using, robust in on_commit.captured]
    assert captured, "no callback was registered at all"
    assert set(captured) == {(PERSONAL, True)}
    assert all(using == PERSONAL for using, _robust in captured)
    assert all(robust for _using, robust in captured)


def test_a_broker_outage_does_not_fail_the_write(monkeypatch, on_commit):
    """The city is set either way. What the user does not get is an immediate digest."""
    user_id = uuid7()

    def explode(name, args):
        raise RuntimeError("broker is down")

    monkeypatch.setattr(digest_enqueue, "_send", explode)

    preference = set_home_city(
        user_id=user_id, city="Dhaka", source="choice", actor=actor(user_id), now=NOW
    )
    on_commit()  # robust: the exception is logged, not raised

    # The row is durable, and it is the row the command returned. (`set_home_city`
    # resolves an unsupported city to the fallback, so the stored value is asserted
    # against what the command decided, not against the string passed in.)
    stored = DigestPreference.objects.using(PERSONAL).get(user_id=user_id)
    assert stored.city == preference.city
    assert stored.city is not None


def test_only_the_user_id_travels(sent, on_commit):
    """AD-13: no email, no city, no title goes through the broker."""
    user_id = uuid7()

    set_home_city(user_id=user_id, city="Dhaka", source="choice", actor=actor(user_id), now=NOW)
    on_commit()

    (_name, args) = sent[0]
    assert args == [str(user_id)]
