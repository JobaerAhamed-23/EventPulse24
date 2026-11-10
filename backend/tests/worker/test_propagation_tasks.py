"""The two worker tasks around AD-17's propagation: the consumer and its alarm.

The orchestration itself is `test_propagation.py`'s. What is pinned here is the thin layer:
the task reads its argument, reports what happened, and never repairs anything on a timer.
"""

import logging
from datetime import UTC, datetime, timedelta

import pytest

from shared.constants import LIFECYCLE_PERSONAL_BEHAVIOUR, LIFECYCLE_SEND_BEHAVIOUR
from shared.db import CATALOG, PERSONAL
from shared.ids import uuid7
from worker import propagation, tasks

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

NOW = datetime(2026, 11, 10, 20, 0, tzinfo=UTC)


def test_the_task_reports_what_it_applied(monkeypatch, caplog):
    change_id = uuid7()
    monkeypatch.setattr(
        propagation,
        "propagate",
        lambda **kwargs: propagation.PropagationResult(
            state_change_id=change_id, users=3, applied=3, marked=True
        ),
    )

    with caplog.at_level(logging.INFO, logger="worker.tasks"):
        assert tasks.propagate_state_change(str(change_id)) is None

    [record] = [r for r in caplog.records if r.name == "worker.tasks"]
    assert (record.getMessage(), record.users) == ("State change propagated", 3)


def test_a_partial_run_is_a_warning_not_a_success(monkeypatch, caplog):
    """A change that reached some users is not a change that propagated."""
    change_id = uuid7()
    monkeypatch.setattr(
        propagation,
        "propagate",
        lambda **kwargs: propagation.PropagationResult(
            state_change_id=change_id, users=5, applied=4, failed=1, marked=False
        ),
    )

    with caplog.at_level(logging.INFO, logger="worker.tasks"):
        tasks.propagate_state_change(str(change_id))

    [record] = [r for r in caplog.records if r.name == "worker.tasks"]
    assert record.levelno == logging.WARNING
    assert (record.applied, record.failed) == (4, 1)


def test_a_missing_change_logs_nothing_at_info(monkeypatch, caplog):
    change_id = uuid7()
    monkeypatch.setattr(
        propagation,
        "propagate",
        lambda **kwargs: propagation.PropagationResult(state_change_id=change_id, missing=True),
    )

    with caplog.at_level(logging.INFO, logger="worker.tasks"):
        tasks.propagate_state_change(str(change_id))

    assert [r for r in caplog.records if r.name == "worker.tasks"] == []


# --- The alarm ------------------------------------------------------------------------------------


def test_the_alarm_warns_when_changes_are_stuck(monkeypatch, caplog):
    monkeypatch.setattr(propagation, "count_stuck_propagations", lambda **kwargs: 4)

    with caplog.at_level(logging.INFO, logger="worker.tasks"):
        assert tasks.report_stuck_propagation() is None

    [record] = [r for r in caplog.records if r.name == "worker.tasks"]
    assert record.levelno == logging.WARNING
    assert record.stuck == 4


def test_the_alarm_is_quiet_when_nothing_is_stuck(monkeypatch, caplog):
    monkeypatch.setattr(propagation, "count_stuck_propagations", lambda **kwargs: 0)

    with caplog.at_level(logging.INFO, logger="worker.tasks"):
        tasks.report_stuck_propagation()

    [record] = [r for r in caplog.records if r.name == "worker.tasks"]
    assert record.levelno == logging.INFO


def test_the_alarm_never_marks_anything_propagated(monkeypatch):
    """It reports and never repairs.

    `EventStateChange` is append-only, so there is no counter to retire a poisoned change
    with — and setting `propagated_at` to stop the churn would claim a propagation that
    never happened, stopping the reconciler and stranding that user on the old state.
    """
    from apps.ingestion.services import outbox

    marked = []
    monkeypatch.setattr(propagation, "count_stuck_propagations", lambda **kwargs: 9)
    monkeypatch.setattr(outbox, "mark_propagated", lambda *a, **k: marked.append(a) or True)

    tasks.report_stuck_propagation()

    assert marked == []


# --- The two behaviour maps stay total -------------------------------------------------------


def test_every_lifecycle_kind_has_a_personal_behaviour():
    """A new kind in `ingestion` must fail here rather than silently doing nothing.

    The mirror of `test_every_lifecycle_kind_is_mapped` for `delivery`. Without it, a kind
    added later would fall through `LIFECYCLE_PERSONAL_BEHAVIOUR` with a `KeyError` at
    propagation time — for every user of one event, in a worker, at once.
    """
    from apps.ingestion.models import EventStateChange

    assert set(LIFECYCLE_PERSONAL_BEHAVIOUR) == {k.value for k in EventStateChange.Kind}


def test_the_two_behaviour_maps_cover_the_same_kinds():
    """They say different things about the same seven kinds, and must not drift apart."""
    assert set(LIFECYCLE_PERSONAL_BEHAVIOUR) == set(LIFECYCLE_SEND_BEHAVIOUR)


def test_only_sold_out_and_detail_changed_skip_the_personal_side():
    """The decision made executable.

    `SAVED_EVENT` stores a start, an end and a version; these two kinds move none of them,
    and `event_writes._kind_facts` does not even record a time for them. Any other kind
    skipping the personal side would be a user's calendar left stale.
    """
    from shared.constants import LifecyclePersonalBehaviour

    skipped = {
        kind
        for kind, behaviour in LIFECYCLE_PERSONAL_BEHAVIOUR.items()
        if behaviour is LifecyclePersonalBehaviour.NONE
    }
    assert skipped == {"sold_out", "detail_changed"}


def test_the_kinds_that_skip_the_personal_side_still_keep_their_sends():
    """And the pairing is the point: `KEEP` is what releases a held row.

    If one of these ever mapped to CANCEL or REMINT on the delivery side while skipping
    personalization, the snapshot and the sends would disagree about an event that moved.
    """
    from shared.constants import LifecyclePersonalBehaviour, LifecycleSendBehaviour

    for kind, behaviour in LIFECYCLE_PERSONAL_BEHAVIOUR.items():
        if behaviour is LifecyclePersonalBehaviour.NONE:
            assert LIFECYCLE_SEND_BEHAVIOUR[kind] is LifecycleSendBehaviour.KEEP


def test_the_alarm_window_outlives_the_reconcilers():
    """A change outliving 30 minutes is failing, not merely waiting.

    `OUTBOX_RECONCILE_AFTER` re-offers at 5 minutes, so an alarm at or below that would
    fire on every change the reconciler is about to pick up anyway.
    """
    from shared.constants import OUTBOX_RECONCILE_AFTER, PROPAGATION_ALARM_AFTER

    assert PROPAGATION_ALARM_AFTER > OUTBOX_RECONCILE_AFTER
    assert PROPAGATION_ALARM_AFTER >= timedelta(minutes=30)
