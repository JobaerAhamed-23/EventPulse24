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
- The composition job **mints the Pulse Ping** after the composition, and **running it
  twice mints one row** (FR-10) — the composition is idempotent and the send matches it.
- The tick **does not change the beat schedule**: one static 60-second tick, still.
"""

import logging
from datetime import date, time

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


class FakeResult:
    """The shape of `DigestCompositionResult`, as the composition job reads it.

    **The four attributes the Ping decision needs are part of the contract.** The job
    hands the composition's own pool counts to `mint_ping_send` rather than re-querying
    them, so a stubbed composition must carry them — otherwise the job would be reading
    counts from somewhere the real composition never reads them.
    """

    created = True
    is_empty = True
    local_date = date(2026, 11, 4)
    public_qualifying_count = 0
    personal_qualifying_count = 0
    has_qualifying_events = False


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

        return FakeResult()

    monkeypatch.setattr(tasks, "compose_digest", fake_compose)

    tasks.compose_digest_task(str(user_id))

    assert composed == [user_id]


def test_the_composition_job_releases_the_claim(monkeypatch):
    user_id = make_preference().user_id

    def fake_compose(*, user_id, actor, now):
        return FakeResult()

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


# --- The composition job, end to end (FR-10) ---------------------------------------------------


def test_running_the_composition_job_twice_mints_one_send(monkeypatch):
    """**"Tested by running the job twice"** (FR-10's second consequence).

    The composition is idempotent and the send must match it: a duplicated job — the
    first lost to a broker hiccup, a retried enqueue — must not produce a second email.
    The unique key `user_id · digest · local_date` is what makes it so, so the row
    count is the assertion rather than a return value.
    """
    from apps.delivery.models import ScheduledSend

    user_id = make_preference().user_id

    def fake_compose(*, user_id, actor, now):
        PulseDigest.objects.using(PERSONAL).get_or_create(
            user_id=user_id,
            local_date=date(2026, 11, 4),
            defaults={"timezone": ZONE, "composed_at": now, "is_empty": True},
        )

        class Qualifying(FakeResult):
            public_qualifying_count = 3
            has_qualifying_events = True

        return Qualifying()

    monkeypatch.setattr(tasks, "compose_digest", fake_compose)

    tasks.compose_digest_task(str(user_id))
    tasks.compose_digest_task(str(user_id))

    rows = ScheduledSend.objects.using(PERSONAL).filter(user_id=user_id)
    assert rows.count() == 1
    row = rows.get()
    assert row.kind == ScheduledSend.Kind.DIGEST
    assert row.status == ScheduledSend.Status.PENDING
    assert row.send_key == f"{user_id}:digest:2026-11-04"


def test_a_user_with_nothing_to_say_gets_no_send_from_the_job(monkeypatch):
    """**FR-10's first consequence, through the job.** A composition that found
    nothing qualifying mints no row at all — not a `pending` row that is later
    skipped."""
    from apps.delivery.models import ScheduledSend

    user_id = make_preference().user_id

    def fake_compose(*, user_id, actor, now):
        return FakeResult()

    monkeypatch.setattr(tasks, "compose_digest", fake_compose)

    tasks.compose_digest_task(str(user_id))

    assert not ScheduledSend.objects.using(PERSONAL).filter(user_id=user_id).exists()


def test_the_job_logs_the_pings_outcome(monkeypatch, caplog):
    """**The Ping's outcome rides on the composition's own log line.** It is the one
    line that says what happened to this user's day: a row was minted, the Ping was
    suppressed, or the user had unsubscribed."""
    user_id = make_preference().user_id

    def fake_compose(*, user_id, actor, now):
        class Qualifying(FakeResult):
            public_qualifying_count = 1
            has_qualifying_events = True

        return Qualifying()

    monkeypatch.setattr(tasks, "compose_digest", fake_compose)

    with caplog.at_level(logging.INFO, logger="worker.tasks"):
        tasks.compose_digest_task(str(user_id))

    [record] = [r for r in caplog.records if r.getMessage() == "Digest composed"]
    assert record.ping_minted is True
    assert record.ping_suppressed is False
    assert record.ping_reason is None


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
