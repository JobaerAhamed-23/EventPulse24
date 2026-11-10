"""AD-17's propagation consumer: one catalog state change reaching every user it touches.

**What is pinned here is the orchestration**, not the services it calls — each of those has
its own tests, and this job deliberately adds no logic they already hold.

- **It writes nothing itself.** Every mutation goes through a published command (AD-16).
- **The order is personalization, then delivery, then the notice** — the only order whose
  crash window is survivable, because a snapshot ahead of the sends leaves rows the sweep
  *holds* rather than sends.
- **It is idempotent by composition, not by a marker.** Every service it calls is
  version-gated and stores the version it applied, so a re-run is a no-op and a partial run
  retried completes. There is no per-user table, and these tests are why none is needed.
- **One user's failure is not the job's.** The loop continues, `propagated_at` stays NULL,
  and the reconciler re-offers the change.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from django.db import connections

from apps.delivery.models import ReminderPlan, ScheduledSend, StateChangeNotice
from apps.delivery.services.reminder_plan_read import resolve_target
from apps.delivery.services.reminder_plans import save_plan_slots
from apps.ingestion.models import Event, EventStateChange
from apps.ingestion.services import outbox
from apps.personalization.models import ConflictPair, SavedEvent
from apps.personalization.services.personal_events import create_personal_event
from apps.personalization.services.saved_events import save_event
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from shared.ids import uuid7
from tests.ingestion.factories import EventFactory, VenueFactory
from tests.personalization.factories import DigestPreferenceFactory
from worker import propagation

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

NOW = datetime(2026, 11, 10, 20, 0, tzinfo=UTC)  # 12:00 in Los Angeles
START = datetime(2026, 12, 10, 3, 0, tzinfo=UTC)
TZ = "America/Los_Angeles"


def make_user(*, zone=TZ):
    user_id = uuid7()
    DigestPreferenceFactory(user_id=user_id, timezone=zone)
    return user_id


def make_event(*, start=START, title="Rooftop Cinema"):
    return EventFactory(
        title=title,
        venue=VenueFactory(city="New York City", venue_fingerprint=f"v|{uuid7()}"),
        start_time_utc=start,
        end_time_utc=start + timedelta(hours=2),
        last_seen_at=NOW,
    )


def save(user_id, event):
    return save_event(user_id=user_id, event_id=event.id, actor=Actor.user(user_id), now=NOW)


def with_plan(user_id, event, slots=("1d", "1hr")):
    target = resolve_target(user_id=user_id, target_kind="saved_event", target_id=event.id)
    save_plan_slots(
        user_id=user_id,
        target_kind="saved_event",
        target_id=event.id,
        slots=slots,
        actor=Actor.user(user_id),
        now=NOW,
        send_target=target,
    )


def bump_catalog(event, *, status=None, sold_out=None, start=None):
    """Move the catalog event one version forward, the way production does.

    The `guard_event_write` trigger refuses an Event born above version 1 and refuses a jump
    of more than 1, so a moved event is made by updating a lifecycle field rather than by
    constructing one at a version the database would never produce.
    """
    sets, params = ["event_version = event_version + 1"], []
    if status is not None:
        sets.append("status = %s")
        params.append(status)
    if sold_out is not None:
        sets.append("is_sold_out = %s")
        params.append(sold_out)
    if start is not None:
        # The end moves with the start: `event_end_after_start_ck` refuses a row whose end
        # is before its start, and a lifecycle move does not shorten an event.
        sets.append("start_time_utc = %s")
        params.append(start)
        sets.append("end_time_utc = %s")
        params.append(start + timedelta(hours=2))
    params.append(event.id)
    with connections[CATALOG].cursor() as cursor:
        cursor.execute(
            f"UPDATE catalog.ingestion_event SET {', '.join(sets)} WHERE id = %s", params
        )
    event.refresh_from_db(using=CATALOG)
    return event.event_version


def a_change(event, *, kind, version, after=None, occurred_at=NOW):
    """One state change row.

    `occurred_at` is set **at creation**, never afterwards: `EventStateChange` is
    append-only and `propagated_at` is its one mutable column, so an age cannot be
    backdated with an update. That constraint is the reason this job has no attempts
    counter, so a test that worked around it would be testing a table this tree does not
    have.
    """
    return EventStateChange.objects.using(CATALOG).create(
        event=event,
        kind=kind,
        event_version=version,
        before={},
        after=after or {},
        occurred_at=occurred_at,
        actor_kind="system",
        actor_label="ingest_pipeline",
    )


@pytest.fixture
def sent_jobs(monkeypatch):
    """Record the jobs the outbox sends instead of reaching the broker."""
    jobs: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(outbox, "_send", lambda name, args: jobs.append((name, list(args))))
    return jobs


def pending(user_id, event):
    """This user's pending **reminders** for the event.

    Scoped by kind on purpose: a state notice's send also carries the event as its target,
    so an unscoped filter would count the notice among the reminders it is a notice about —
    and "the cancellation cancelled the sends" would read as false while being true.
    """
    return ScheduledSend.objects.using(PERSONAL).filter(
        user_id=user_id,
        target_id=event.id,
        kind=ScheduledSend.Kind.EVENT_REMINDER,
        status=ScheduledSend.Status.PENDING,
    )


def notice_sends(user_id, event):
    return ScheduledSend.objects.using(PERSONAL).filter(
        user_id=user_id, target_id=event.id, kind=ScheduledSend.Kind.STATE_NOTICE
    )


def notices(user_id):
    return StateChangeNotice.objects.using(PERSONAL).filter(user_id=user_id)


def run(change, *, now=NOW):
    return propagation.propagate(state_change_id=change.id, now=now)


# --- The common case: nobody saved it -----------------------------------------------------------


def test_a_change_nobody_saved_marks_propagated_and_touches_nothing():
    """The overwhelmingly common case, and it must be the fast one.

    An unsaved event's state change reaches no user. It has to mark propagated immediately:
    `EventStateChange` is append-only, so there is no attempts counter to retire a change
    that never marks, and the reconciler would offer it forever.
    """
    event = make_event()
    version = bump_catalog(event, sold_out=True)
    change = a_change(event, kind=EventStateChange.Kind.SOLD_OUT, version=version)

    result = run(change)

    assert result.users == 0
    assert result.marked is True
    change.refresh_from_db(using=CATALOG)
    assert change.propagated_at == NOW


def test_a_change_that_no_longer_exists_is_not_an_error():
    result = propagation.propagate(state_change_id=uuid7(), now=NOW)

    assert result.missing is True


def test_an_already_propagated_change_is_not_applied_again():
    event = make_event()
    user_id = make_user()
    save(user_id, event)
    version = bump_catalog(event, start=START + timedelta(days=1))
    change = a_change(
        event,
        kind=EventStateChange.Kind.TIME_MOVED,
        version=version,
        after={"start_utc": (START + timedelta(days=1)).isoformat()},
    )
    run(change)

    second = run(change)

    assert second.users == 0


# --- time_moved: the snapshot, the sends and the notice all move ---------------------------------


def _move(event, *, days=1):
    new_start = START + timedelta(days=days)
    version = bump_catalog(event, start=new_start)
    return new_start, a_change(
        event,
        kind=EventStateChange.Kind.TIME_MOVED,
        version=version,
        after={
            "start_utc": new_start.isoformat(),
            "end_utc": (new_start + timedelta(hours=2)).isoformat(),
        },
    )


def test_a_time_move_restamps_the_snapshot():
    event = make_event()
    user_id = make_user()
    saved = save(user_id, event).saved
    new_start, change = _move(event)

    run(change)

    row = SavedEvent.objects.using(PERSONAL).get(pk=saved.id)
    assert row.start_utc == new_start
    assert row.event_version == change.event_version


def test_a_time_move_reminds_the_new_time_and_raises_a_notice():
    event = make_event()
    user_id = make_user()
    save(user_id, event)
    with_plan(user_id, event)
    before = set(pending(user_id, event).values_list("send_key", flat=True))
    assert before

    new_start, change = _move(event)
    run(change)

    after_keys = set(pending(user_id, event).values_list("send_key", flat=True))
    assert after_keys and after_keys.isdisjoint(before)
    assert notices(user_id).get().change_kind == EventStateChange.Kind.TIME_MOVED


def test_the_new_time_comes_from_the_change_not_the_live_event():
    """A poll appends one change per kind, so the live Event already holds the *last*
    kind's facts. Reading the start from the Event would stamp this change's version
    against times that belong to a later one."""
    event = make_event()
    user_id = make_user()
    saved = save(user_id, event).saved
    changes_start = START + timedelta(days=1)
    version = bump_catalog(event, start=changes_start)
    change = a_change(
        event,
        kind=EventStateChange.Kind.TIME_MOVED,
        version=version,
        after={"start_utc": changes_start.isoformat()},
    )
    # The catalog moves on again before this change is propagated.
    bump_catalog(event, start=START + timedelta(days=9))

    run(change)

    assert SavedEvent.objects.using(PERSONAL).get(pk=saved.id).start_utc == changes_start


# --- cancelled: sends cancelled, pairs closed, personal event untouched --------------------------


def _cancel(event):
    version = bump_catalog(event, status=Event.Status.CANCELLED)
    return a_change(event, kind=EventStateChange.Kind.CANCELLED, version=version)


def test_a_cancellation_cancels_the_sends_and_closes_the_pairs():
    event = make_event()
    user_id = make_user()
    create_personal_event(
        user_id=user_id,
        name="Dinner",
        start_utc=START,
        end_utc=START + timedelta(hours=2),
        start_time_tz=TZ,
        actor=Actor.user(user_id),
        now=NOW,
    )
    result = save(user_id, event)
    assert len(result.conflicts) == 1
    with_plan(user_id, event)
    assert pending(user_id, event).exists()

    run(_cancel(event))

    assert not pending(user_id, event).exists()
    pair = ConflictPair.objects.using(PERSONAL).get(pk=result.conflicts[0].pair_id)
    assert pair.status == ConflictPair.Status.CLEARED_BY_STATE_CHANGE


def test_a_cancellation_never_touches_the_users_own_event():
    """FR-55: a cancelled public event never auto-cancels a personal event."""
    from apps.personalization.models import PersonalEvent

    event = make_event()
    user_id = make_user()
    personal = create_personal_event(
        user_id=user_id,
        name="Dinner",
        start_utc=START,
        end_utc=START + timedelta(hours=2),
        start_time_tz=TZ,
        actor=Actor.user(user_id),
        now=NOW,
    ).event
    save(user_id, event)
    before = PersonalEvent.objects.using(PERSONAL).get(pk=personal.id)

    run(_cancel(event))

    after = PersonalEvent.objects.using(PERSONAL).get(pk=personal.id)
    assert (after.start_utc, after.version) == (before.start_utc, before.version)


# --- sold_out: the personal side is skipped, the hold is still released ---------------------------


def test_a_sold_out_change_leaves_the_snapshot_alone():
    """`LIFECYCLE_PERSONAL_BEHAVIOUR` maps it to NONE: nothing the snapshot holds moved."""
    event = make_event()
    user_id = make_user()
    saved = save(user_id, event).saved
    version = bump_catalog(event, sold_out=True)

    run(a_change(event, kind=EventStateChange.Kind.SOLD_OUT, version=version))

    row = SavedEvent.objects.using(PERSONAL).get(pk=saved.id)
    assert row.start_utc == START
    assert row.event_version == 1  # deliberately lagging; every gate is `>`, not `==`


def test_a_sold_out_change_still_restamps_and_releases_the_sends():
    """The hold's only exit.

    The catalog's version moved, so the sweep has already held this user's pending sends.
    `apply_lifecycle_change`'s KEEP branch clearing `held_at` is what releases them — and it
    only fires if the version it is given is the *change's*, not the lagging snapshot's.
    """
    event = make_event()
    user_id = make_user()
    save(user_id, event)
    with_plan(user_id, event)
    version = bump_catalog(event, sold_out=True)
    pending(user_id, event).update(held_at=NOW)

    run(a_change(event, kind=EventStateChange.Kind.SOLD_OUT, version=version))

    rows = list(pending(user_id, event))
    assert rows
    assert all(row.held_at is None for row in rows)
    assert all(row.event_version == version for row in rows)


def test_a_sold_out_change_still_raises_a_notice():
    event = make_event()
    user_id = make_user()
    save(user_id, event)
    version = bump_catalog(event, sold_out=True)

    run(a_change(event, kind=EventStateChange.Kind.SOLD_OUT, version=version))

    assert notices(user_id).get().change_kind == EventStateChange.Kind.SOLD_OUT


def test_a_time_move_releases_the_held_rows_it_replaces():
    """The hold's exit, for the `REMINT` behaviour.

    A held row is still `pending`, so the `REMINT` path cancels it and mints a fresh one.
    The fresh row is born unheld — a re-minted row has never been behind the catalog, so
    there is nothing to release. The held row itself is terminal, so its `held_at` is left
    as the forensic record of why it never went out.
    """
    event = make_event()
    user_id = make_user()
    save(user_id, event)
    with_plan(user_id, event)
    version = bump_catalog(event, start=START + timedelta(days=1))
    held = pending(user_id, event)
    held.update(held_at=NOW)

    run(
        a_change(
            event,
            kind=EventStateChange.Kind.TIME_MOVED,
            version=version,
            after={"start_utc": (START + timedelta(days=1)).isoformat()},
        )
    )

    rows = list(pending(user_id, event))
    assert rows
    # The new rows are the re-minted ones, and none of them is held.
    assert all(row.held_at is None for row in rows)
    assert all(row.event_version == version for row in rows)


def test_a_cancellation_releases_the_held_rows_it_cancels():
    """The hold's exit, for the `CANCEL` behaviour.

    A cancelled event's reminders must not go out at all, so the held rows are cancelled
    rather than released. A held row that stayed `pending` would be picked up by the next
    sweep and sent — a reminder for an event that is not happening.
    """
    event = make_event()
    user_id = make_user()
    save(user_id, event)
    with_plan(user_id, event)
    version = bump_catalog(event, status=Event.Status.CANCELLED)
    pending(user_id, event).update(held_at=NOW)

    run(a_change(event, kind=EventStateChange.Kind.CANCELLED, version=version))

    assert not pending(user_id, event).exists()


# --- Idempotency, which is the whole design ------------------------------------------------------


def test_a_full_re_run_changes_nothing():
    """The property that removes the need for a per-user marker.

    `propagate` short-circuits on `propagated_at`, so the re-application is driven through
    the saver walk directly — otherwise this would only be testing the short-circuit, which
    a lost acknowledgement does not give us.
    """
    event = make_event()
    user_id = make_user()
    save(user_id, event)
    with_plan(user_id, event)
    _, change = _move(event)
    run(change)
    keys = set(pending(user_id, event).values_list("send_key", flat=True))
    snapshot = SavedEvent.objects.using(PERSONAL).get(user_id=user_id, event_id=event.id)

    facts = outbox.get_state_change(change.pk)
    result = propagation._apply_to_savers(
        change=facts, now=NOW, event_start=propagation._current_start(change.event_id)
    )

    assert (result.users, result.failed) == (1, 0)
    assert set(pending(user_id, event).values_list("send_key", flat=True)) == keys
    assert notices(user_id).count() == 1
    again = SavedEvent.objects.using(PERSONAL).get(pk=snapshot.id)
    assert (again.start_utc, again.event_version) == (
        snapshot.start_utc,
        snapshot.event_version,
    )


def test_an_older_change_arriving_after_a_newer_one_does_nothing():
    """AD-17: an out-of-order run can never let an older change overwrite a newer one."""
    event = make_event()
    user_id = make_user()
    saved = save(user_id, event).saved
    older_start = START + timedelta(days=1)
    older = a_change(
        event,
        kind=EventStateChange.Kind.TIME_MOVED,
        version=bump_catalog(event, start=older_start),
        after={"start_utc": older_start.isoformat()},
    )
    newer_start = START + timedelta(days=5)
    newer = a_change(
        event,
        kind=EventStateChange.Kind.TIME_MOVED,
        version=bump_catalog(event, start=newer_start),
        after={"start_utc": newer_start.isoformat()},
    )

    run(newer)
    run(older)

    assert SavedEvent.objects.using(PERSONAL).get(pk=saved.id).start_utc == newer_start


def test_two_changes_racing_on_one_event_leave_the_newer_effect():
    """The race, not the sequence.

    The sequential case above proves an *older* change arriving after a newer one is refused.
    This proves the other order: the newer one runs first and the older one is refused *by
    the version gate inside the service*, not by any gate this job added.

    The distinction matters because the job deliberately has no gate of its own. If it had
    one, it would be a second place for the version to live — and this test is what shows
    the answer still comes out right with the gate in the service alone.
    """
    event = make_event()
    user_id = make_user()
    saved = save(user_id, event).saved
    older_start = START + timedelta(days=1)
    older = a_change(
        event,
        kind=EventStateChange.Kind.TIME_MOVED,
        version=bump_catalog(event, start=older_start),
        after={"start_utc": older_start.isoformat()},
    )
    newer_start = START + timedelta(days=5)
    newer = a_change(
        event,
        kind=EventStateChange.Kind.TIME_MOVED,
        version=bump_catalog(event, start=newer_start),
        after={"start_utc": newer_start.isoformat()},
    )

    # The newer change is offered twice — a re-offer from the reconciler landing while the
    # first run is still in flight — and the older one lands in the middle of both.
    run(newer)
    run(older)
    run(newer)

    row = SavedEvent.objects.using(PERSONAL).get(pk=saved.id)
    assert row.start_utc == newer_start
    assert row.event_version == newer.event_version


def test_the_catalog_is_read_once_for_the_whole_change(monkeypatch):
    """One read for the change, not one per saver.

    Every saver is notified about the *same* event, so the event's current start is the same
    fact for all of them. `get_public_events` is a batch read precisely so a caller with many
    events pays one round-trip; asking it once per saver would undo that on the one path
    that scales with the saver count.
    """
    calls: list[set] = []
    real = propagation.get_public_events

    def counting(**kwargs):
        calls.append(kwargs["event_ids"])
        return real(**kwargs)

    monkeypatch.setattr(propagation, "get_public_events", counting)

    event = make_event()
    users = [make_user() for _ in range(3)]
    for user_id in users:
        save(user_id, event)
    _, change = _move(event)

    run(change)

    assert len(calls) == 1
    assert calls[0] == {event.id}


def test_every_saver_is_reached():
    event = make_event()
    users = [make_user() for _ in range(3)]
    for user_id in users:
        save(user_id, event)
    new_start, change = _move(event)

    result = run(change)

    assert (result.users, result.applied, result.failed) == (3, 3, 0)
    for user_id in users:
        assert (
            SavedEvent.objects.using(PERSONAL).get(user_id=user_id, event_id=event.id).start_utc
            == new_start
        )


def test_the_savers_are_paged(monkeypatch):
    """The page is a round-trip bound, not a cap: every saver must still be reached."""
    monkeypatch.setattr(propagation, "SAVERS_PAGE", 1)
    event = make_event()
    users = [make_user() for _ in range(3)]
    for user_id in users:
        save(user_id, event)
    _, change = _move(event)

    assert run(change).applied == 3


# --- A failing user ------------------------------------------------------------------------------


def test_one_failing_user_does_not_stop_the_others(monkeypatch):
    event = make_event()
    first, second = make_user(), make_user()
    save(first, event)
    save(second, event)
    _, change = _move(event)

    real = propagation.update_saved_event_snapshot
    failed_for = sorted([first, second])[0]

    def flaky(**kwargs):
        if kwargs["user_id"] == failed_for:
            raise RuntimeError("boom")
        return real(**kwargs)

    monkeypatch.setattr(propagation, "update_saved_event_snapshot", flaky)

    result = run(change)

    assert (result.users, result.applied, result.failed) == (2, 1, 1)


def test_a_failing_user_leaves_the_change_unpropagated(monkeypatch):
    """`propagated_at` may only be set once *every* affected user is done (AD-17).

    Setting it to stop the churn would claim a propagation that never happened, and the
    reconciler would stop offering — leaving that user on the old state forever.
    """
    event = make_event()
    user_id = make_user()
    save(user_id, event)
    _, change = _move(event)
    monkeypatch.setattr(
        propagation,
        "update_saved_event_snapshot",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    result = run(change)

    assert result.marked is False
    change.refresh_from_db(using=CATALOG)
    assert change.propagated_at is None


def test_a_retry_after_a_partial_run_completes(monkeypatch):
    event = make_event()
    first, second = sorted([make_user(), make_user()])
    save(first, event)
    save(second, event)
    new_start, change = _move(event)

    real = propagation.update_saved_event_snapshot
    broken = {"on": True}

    def flaky(**kwargs):
        if broken["on"] and kwargs["user_id"] == second:
            raise RuntimeError("boom")
        return real(**kwargs)

    monkeypatch.setattr(propagation, "update_saved_event_snapshot", flaky)
    assert run(change).failed == 1

    broken["on"] = False
    result = run(change)

    assert (result.failed, result.marked) == (0, True)
    for user_id in (first, second):
        assert (
            SavedEvent.objects.using(PERSONAL).get(user_id=user_id, event_id=event.id).start_utc
            == new_start
        )


# --- A save with no Reminder Plan -----------------------------------------------------------------


def test_a_save_with_no_plan_propagates_without_error():
    """`save_event` attaches no plan, so this is the ordinary shape, not an edge case."""
    event = make_event()
    user_id = make_user()
    saved = save(user_id, event).saved
    assert not ReminderPlan.objects.using(PERSONAL).filter(user_id=user_id).exists()
    new_start, change = _move(event)

    result = run(change)

    assert result.failed == 0
    assert SavedEvent.objects.using(PERSONAL).get(pk=saved.id).start_utc == new_start


# --- The alarm, and why it is an alarm --------------------------------------------------------
#
# `EventStateChange` is append-only — `propagated_at` is its one mutable column — so there is
# no attempts counter to retire a poisoned change with. What is bounded is how long the
# failure stays quiet.


def test_nothing_is_stuck_when_everything_propagates():
    event = make_event()
    version = bump_catalog(event, sold_out=True)
    run(a_change(event, kind=EventStateChange.Kind.SOLD_OUT, version=version))

    assert propagation.count_stuck_propagations(now=NOW) == 0


def test_a_change_unpropagated_past_the_window_is_counted():
    from shared.constants import PROPAGATION_ALARM_AFTER

    event = make_event()
    version = bump_catalog(event, sold_out=True)
    a_change(
        event,
        kind=EventStateChange.Kind.SOLD_OUT,
        version=version,
        occurred_at=NOW - PROPAGATION_ALARM_AFTER - timedelta(minutes=1),
    )

    assert propagation.count_stuck_propagations(now=NOW) == 1


def test_a_change_inside_the_window_is_not_counted_yet():
    """The boundary. A change younger than the window is merely waiting, not stuck."""
    from shared.constants import PROPAGATION_ALARM_AFTER

    event = make_event()
    version = bump_catalog(event, sold_out=True)
    a_change(
        event,
        kind=EventStateChange.Kind.SOLD_OUT,
        version=version,
        occurred_at=NOW - PROPAGATION_ALARM_AFTER + timedelta(minutes=1),
    )

    assert propagation.count_stuck_propagations(now=NOW) == 0


# --- The backlog, and AD-17's accepted residual window -------------------------------------------


def test_the_backlog_drains_through_the_reconciler(sent_jobs):
    """Every state change written before this consumer existed is still unpropagated.

    The placeholder deliberately left `propagated_at` NULL, so the outbox has been
    accumulating. The reconciler must drain it with no manual step — this walks the whole
    path: reconcile enqueues, the consumer applies, the row marks.
    """
    from apps.ingestion.services.outbox import reconcile_outbox
    from shared.constants import OUTBOX_RECONCILE_AFTER

    event = make_event()
    user_id = make_user()
    saved = save(user_id, event).saved
    new_start = START + timedelta(days=1)
    change = a_change(
        event,
        kind=EventStateChange.Kind.TIME_MOVED,
        version=bump_catalog(event, start=new_start),
        after={"start_utc": new_start.isoformat()},
        occurred_at=NOW - OUTBOX_RECONCILE_AFTER - timedelta(minutes=1),
    )
    sent_jobs.clear()

    assert reconcile_outbox(now=NOW) == 1
    [(task_name, args)] = sent_jobs
    propagation.propagate(state_change_id=UUID(args[0]), now=NOW)

    assert task_name == "worker.tasks.propagate_state_change"
    change.refresh_from_db(using=CATALOG)
    assert change.propagated_at == NOW
    assert SavedEvent.objects.using(PERSONAL).get(pk=saved.id).start_utc == new_start


def test_a_send_claimed_before_the_change_commits_can_still_go_out():
    """**AD-17's accepted residual window**, deferred here from `held-for-propagation-status`.

    The Spine names this cost explicitly:

        a change that commits between that version read and the provider call can still send
        one reminder for the old time. The window is seconds wide, and the FR-54 notice from
        propagation corrects it.

    It is pinned rather than fixed. Closing it needs the cross-schema transaction AD-3 rules
    out, so the test's job is to show the window is real, bounded to one send, and that the
    correction the Spine promises actually arrives.

    The window is reproduced in its own order rather than with threads: the guard reads the
    catalog *before* the change lands, so the send is judged sendable and released; the
    change then commits and propagation runs.
    """
    from apps.delivery.services.delivery_sweep import hold_stale_sends

    event = make_event()
    user_id = make_user()
    save(user_id, event)
    with_plan(user_id, event)
    send_ids = list(pending(user_id, event).values_list("id", flat=True))

    # The guard runs against the catalog as it stands — nothing has moved yet.
    sendable, held = hold_stale_sends(send_ids=send_ids, now=NOW)
    assert (sendable, held) == (send_ids, 0)

    # The change commits in the window between that read and the provider call.
    new_start, change = _move(event)

    # The already-released send is not recalled: that is the accepted cost.
    assert set(pending(user_id, event).values_list("id", flat=True)) == set(send_ids)

    # And the correction the Spine promises does arrive.
    run(change)

    assert notices(user_id).get().change_kind == EventStateChange.Kind.TIME_MOVED
    assert (
        SavedEvent.objects.using(PERSONAL).get(user_id=user_id, event_id=event.id).start_utc
        == new_start
    )


def test_a_stalled_cursor_raises_instead_of_looping(monkeypatch):
    """A worker that re-reads page one forever makes no progress and raises nothing.

    The cursor advances today — `list_savers_for_event` filters `id__gt=after` — so this
    guards a programming error rather than a reachable state. It earns its place because
    the failure it prevents is indistinguishable from a slow job: no error, no progress,
    and nothing in the logs to say which.
    """
    event = make_event()
    for _ in range(2):
        save(make_user(), event)
    _, change = _move(event)

    # Captured before the patch: reaching through the module afterwards would call the
    # fake from inside itself.
    real = propagation.list_savers_for_event
    first_page = real(event_id=event.id, after=None, limit=1)
    assert first_page

    class ReadTooManyPages(RuntimeError):
        """The fake's own bound, so this test fails fast instead of hanging."""

    calls = {"n": 0}

    def always_page_one(**kwargs):
        calls["n"] += 1
        if calls["n"] > 5:
            # Without the guard under test, the loop never ends. A test that can only
            # fail by timing out is not a test, so the fake stops it and the assertion
            # below then fails on the *wrong* exception type.
            raise ReadTooManyPages("the saver walk did not terminate")
        return first_page

    monkeypatch.setattr(propagation, "list_savers_for_event", always_page_one)

    with pytest.raises(propagation.PropagationCursorStalled):
        run(change)

    # The guard fired on the second page, long before the fake's own bound.
    assert calls["n"] == 2
