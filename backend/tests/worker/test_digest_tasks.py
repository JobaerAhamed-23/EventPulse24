"""The digest worker tasks (D1, D4, D9): the dispatcher, and the composition job.

**What these tests pin.**

- The **tick enqueues the digest dispatcher on every beat** — the digest cadence does
  *not* nest the way the reconciler's does, because "due" is a per-user local wall
  clock comparison, not a minute-modulo rule. A dispatcher that ran only every fifth
  minute would make a user who asked for 09:07 wait until 09:10.
- The dispatcher **enqueues one composition job per claim**, and a broker failure
  **releases the claim** so the next tick retries the user.
- The composition job **releases the claim in a `finally`** — a crash cannot leave a
  user claimed until the TTL expires.
- The composition job **re-raises** an unexpected failure, so Celery sees it and retries.
- The tick **does not change the beat schedule**: one static 60-second tick, still.
"""

import logging
from datetime import time

import pytest

from apps.personalization.models import DigestPreference, PulseDigest
from shared.db import CATALOG, PERSONAL
from tests.personalization.factories import DigestPreferenceFactory
from worker import tasks

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

ZONE = "America/Los_Angeles"


def make_preference(user_id=None, *, delivery_time=time(9, 0), timezone=ZONE):
    fields = {"delivery_time": delivery_time, "timezone": timezone}
    if user_id is not None:
        fields["user_id"] = user_id
    return DigestPreferenceFactory(**fields)


def claim_of(user_id):
    return (
        DigestPreference.objects.using(PERSONAL)
        .filter(user_id=user_id)
        .values_list("digest_claimed_at", flat=True)
        .first()
    )


# --- The tick (D9) ---------------------------------------------------------------------------


def test_the_tick_enqueues_the_digest_dispatcher(enqueued):
    tasks.tick()

    assert ("worker.tasks.schedule_digests", ()) in enqueued


def test_the_digest_dispatcher_runs_on_every_beat(enqueued):
    """**The digest cadence does not nest.** The reconciler's cadence is a divisor of
    the tick's; the digest dispatcher's is not — it runs every minute, because "due" is
    a per-user local comparison and a minute-modulo rule would compose everyone at the
    same instant regardless of the hour they asked for."""
    for _ in range(5):
        tasks.tick()

    assert [name for name, _ in enqueued].count("worker.tasks.schedule_digests") == 5


def test_the_tick_still_uses_exactly_one_static_beat():
    """The schedule is unchanged by this work: one 60-second tick, still."""
    from config.celery import TICK_SECONDS, app

    assert app.conf.beat_schedule == {"tick": {"task": "worker.tasks.tick", "schedule": 60.0}}
    assert TICK_SECONDS == 60.0


# --- The dispatcher (D1) ----------------------------------------------------------------------


def test_the_dispatcher_enqueues_one_composition_per_claim(monkeypatch, enqueued):
    claimed = [make_preference().user_id, make_preference().user_id]
    monkeypatch.setattr(tasks.digest_scheduling, "claim_due_digests", lambda **_: claimed)

    tasks.schedule_digests()

    compositions = [entry for entry in enqueued if entry[0] == "worker.tasks.compose_digest"]
    assert [args for _, args in compositions] == [(str(user_id),) for user_id in claimed]


def test_the_dispatcher_releases_the_claim_when_the_broker_is_down(monkeypatch):
    """A broker outage must not leave the user claimed until the TTL expires — the next
    tick has to be able to retry them."""
    user_id = make_preference().user_id
    monkeypatch.setattr(tasks.digest_scheduling, "claim_due_digests", lambda **_: [user_id])

    def refuse(task, *args):
        raise RuntimeError("broker down")

    monkeypatch.setattr(tasks, "_enqueue", refuse)

    tasks.schedule_digests()

    assert claim_of(user_id) is None


def test_the_dispatcher_logs_the_failure_without_pii(monkeypatch, caplog):
    user_id = make_preference().user_id
    monkeypatch.setattr(tasks.digest_scheduling, "claim_due_digests", lambda **_: [user_id])

    def refuse(task, *args):
        raise RuntimeError("broker down")

    monkeypatch.setattr(tasks, "_enqueue", refuse)

    with caplog.at_level(logging.WARNING, logger="worker.tasks"):
        tasks.schedule_digests()

    [record] = [r for r in caplog.records if r.name == "worker.tasks"]
    assert record.getMessage() == "Digest not enqueued"
    assert record.error_type == "RuntimeError"
    assert record.user_id == str(user_id)


# --- The composition job (D4) ------------------------------------------------------------------


def test_the_composition_job_composes_the_digest(monkeypatch):
    user_id = make_preference().user_id
    composed = []

    def fake_compose(*, user_id, actor, now):
        composed.append(user_id)
        PulseDigest.objects.using(PERSONAL).create(
            user_id=user_id,
            local_date=now.date(),
            timezone=ZONE,
            composed_at=now,
            is_empty=True,
        )

        class Result:
            created = True
            is_empty = True

        return Result()

    monkeypatch.setattr(tasks, "compose_digest", fake_compose)

    tasks.compose_digest_task(str(user_id))

    assert composed == [user_id]


def test_the_composition_job_releases_the_claim(monkeypatch):
    user_id = make_preference().user_id

    def fake_compose(*, user_id, actor, now):
        class Result:
            created = True
            is_empty = True

        return Result()

    monkeypatch.setattr(tasks, "compose_digest", fake_compose)

    tasks.compose_digest_task(str(user_id))

    assert claim_of(user_id) is None


def test_the_composition_job_releases_the_claim_when_the_composition_fails(monkeypatch):
    """The release is in a `finally`, so a crash cannot leave the user claimed until the
    TTL expires."""
    user_id = make_preference().user_id

    def fake_compose(*, user_id, actor, now):
        raise RuntimeError("boom")

    monkeypatch.setattr(tasks, "compose_digest", fake_compose)

    with pytest.raises(RuntimeError):
        tasks.compose_digest_task(str(user_id))

    assert claim_of(user_id) is None


def test_the_composition_job_re_raises_so_celery_retries(monkeypatch):
    """A swallowed failure would leave the user with no digest and no retry."""
    user_id = make_preference().user_id

    def fake_compose(*, user_id, actor, now):
        raise RuntimeError("boom")

    monkeypatch.setattr(tasks, "compose_digest", fake_compose)

    with pytest.raises(RuntimeError):
        tasks.compose_digest_task(str(user_id))


def test_the_composition_job_logs_the_error_type_and_no_pii(monkeypatch, caplog):
    user_id = make_preference().user_id

    def fake_compose(*, user_id, actor, now):
        raise RuntimeError("boom")

    monkeypatch.setattr(tasks, "compose_digest", fake_compose)

    with caplog.at_level(logging.WARNING, logger="worker.tasks"):
        with pytest.raises(RuntimeError):
            tasks.compose_digest_task(str(user_id))

    [record] = [r for r in caplog.records if r.name == "worker.tasks"]
    assert record.getMessage() == "Digest composition failed"
    assert record.error_type == "RuntimeError"
    assert record.user_id == str(user_id)


# --- The task names ---------------------------------------------------------------------------


def test_the_tasks_are_registered_under_their_dotted_names():
    from config.celery import app

    app.loader.import_default_modules()

    assert (
        app.tasks["worker.tasks.schedule_digests"] is tasks.schedule_digests._get_current_object()
    )
    assert (
        app.tasks["worker.tasks.compose_digest"] is tasks.compose_digest_task._get_current_object()
    )


def test_the_enqueue_seam_sends_only_the_user_id(monkeypatch):
    """**Nothing about the user travels through the broker.** No email, no city, no
    delivery time — the worker reads what it needs from the rows (AD-13)."""
    from apps.personalization.services import digest_enqueue

    sent = []
    monkeypatch.setattr(digest_enqueue, "_send", lambda name, args: sent.append((name, args)))

    digest_enqueue.enqueue_digest_composition(user_id="00000000-0000-0000-0000-000000000001")

    assert sent == [("worker.tasks.compose_digest", ["00000000-0000-0000-0000-000000000001"])]


def test_the_seam_sends_the_job_through_the_loaded_celery_app(monkeypatch):
    """**The real `_send` goes through the Celery app by dotted name.**

    `personalization` cannot import `worker` or `config` (the layers contract), so the
    job is sent by its name rather than by its function. That is the whole reason the
    seam exists — so this test pins the shape the layers contract forces.
    """
    from apps.personalization.services import digest_enqueue

    sent = []
    monkeypatch.setattr(
        digest_enqueue.current_app, "send_task", lambda name, args: sent.append((name, args))
    )

    digest_enqueue._send("worker.tasks.compose_digest", ["00000000-0000-0000-0000-000000000001"])

    assert sent == [("worker.tasks.compose_digest", ["00000000-0000-0000-0000-000000000001"])]
