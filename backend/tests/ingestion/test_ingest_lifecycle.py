"""Event lifecycle through re-ingest (AD-4, AD-17; pipeline design D9-D12): version bumps, one
state change per kind, supersede in the D7 order, silent detail updates, the outbox hook.
"""

from datetime import UTC, datetime

import pytest

from apps.ingestion.models import Event, EventStateChange, ExtractedRecord, RevalidationRequest
from apps.ingestion.services import ingest_item as item_module
from apps.ingestion.services import outbox
from apps.ingestion.services.ingest_source import ingest_source
from apps.ingestion.services.outbox import PROPAGATE_TASK
from apps.ingestion.services.revalidation import REVALIDATE_TASK
from shared.db import CATALOG, PERSONAL
from tests.ingestion.pipeline_support import ScriptedFetchPort, calendar, ics_source, vevent

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

UID = "jazz@club.example.test"
# 2026-11-05 19:30 in New York (EST) = 2026-11-06 00:30 UTC.
START = "20261105T193000"
START_UTC = datetime(2026, 11, 6, 0, 30, tzinfo=UTC)


def _run(source, *events: str):
    return ingest_source(source.id, fetch_port=ScriptedFetchPort().serve(calendar(*events)))


def _event(source, **filters) -> Event:
    return Event.objects.using(CATALOG).get(source=source, **filters)


def _changes(event) -> list[EventStateChange]:
    return list(
        EventStateChange.objects.using(CATALOG).filter(event=event).order_by("event_version")
    )


@pytest.fixture
def source():
    return ics_source()


@pytest.fixture
def jazz(source):
    _run(source, vevent(UID, START))
    return _event(source)


def test_cancellation_bumps_version_and_appends_one_state_change(source, jazz):
    report = _run(source, vevent(UID, START, status="CANCELLED"))

    event = _event(source)
    assert report.counts == {"updated": 1}
    assert (event.pk, event.status, event.event_version) == (jazz.pk, "cancelled", 2)
    [change] = _changes(event)
    assert (change.kind, change.event_version, change.propagated_at) == ("cancelled", 2, None)
    assert (change.before, change.after) == ({"status": "scheduled"}, {"status": "cancelled"})
    assert (change.actor_kind, change.actor_label) == ("system", "ingest_pipeline")


def test_move_within_30_days_keeps_the_event(source, jazz):
    _run(source, vevent(UID, "20261112T193000"))  # one week later

    event = _event(source)
    assert (event.pk, event.event_version) == (jazz.pk, 2)
    assert event.start_time_local == "2026-11-12T19:30:00"
    assert event.original_start_utc == START_UTC
    [change] = _changes(event)
    assert change.kind == "time_moved"
    assert change.before["start_utc"] == "2026-11-06T00:30:00Z"
    assert change.after["start_utc"] == "2026-11-13T00:30:00Z"


def test_move_beyond_30_days_supersedes_in_order(source, jazz):
    report = _run(source, vevent(UID, "20261222T193000"))  # 47 days later

    assert report.counts == {"superseded": 1}
    old = Event.objects.using(CATALOG).get(pk=jazz.pk)
    new = _event(source, status="scheduled")
    assert (old.status, old.superseded_by_id, old.event_version) == ("superseded", new.pk, 2)
    assert (new.event_version, new.source_event_id) == (1, UID)
    assert new.original_start_utc == new.start_time_utc == datetime(2026, 12, 23, 0, 30, tzinfo=UTC)
    assert new.slug != old.slug
    record = ExtractedRecord.objects.using(CATALOG).get(source=source)
    assert record.event_id == new.pk
    [change] = _changes(old)
    assert (change.kind, change.event_version) == ("superseded", 2)
    assert change.after["superseded_by"] == str(new.pk)
    assert _changes(new) == []


def test_small_moves_are_measured_from_the_original_start(source, jazz):
    _run(source, vevent(UID, "20261125T193000"))  # +20 days: within the window
    assert _event(source).pk == jazz.pk

    report = _run(source, vevent(UID, "20261215T193000"))  # +20 again: +40 from the original

    assert report.counts == {"superseded": 1}
    assert Event.objects.using(CATALOG).get(pk=jazz.pk).status == "superseded"


def test_uncancel_is_recorded_as_reinstated(source, jazz):
    _run(source, vevent(UID, START, status="CANCELLED"))

    _run(source, vevent(UID, START, status="CONFIRMED"))

    event = _event(source)
    assert (event.status, event.event_version) == ("scheduled", 3)
    assert [c.kind for c in _changes(event)] == ["cancelled", "reinstated"]


def test_several_kinds_get_one_state_change_each_in_precedence_order(source, jazz):
    _run(source, vevent(UID, "20261112T193000", location="Blue Note"))

    event = _event(source)
    assert event.event_version == 3
    changes = _changes(event)
    assert [(c.kind, c.event_version) for c in changes] == [
        ("time_moved", 2),
        ("detail_changed", 3),
    ]
    assert set(changes[0].after) == {"start_utc"}
    assert set(changes[1].after) == {"venue_fingerprint"}


def test_title_only_change_is_a_silent_update(source, jazz):
    report = _run(source, vevent(UID, START, summary="Jazz Night (Trio)"))

    event = _event(source)
    assert report.counts == {"silent_updated": 1}
    assert (event.title, event.event_version, event.slug) == ("Jazz Night (Trio)", 1, jazz.slug)
    assert event.title_fingerprint != jazz.title_fingerprint
    assert _changes(event) == []


def test_state_changes_enqueue_propagation_after_commit(
    source, jazz, sent_jobs, django_capture_on_commit_callbacks
):
    """**Both** outboxes fire on commit: AD-17's propagation and the revalidation signal.

    The revalidation callback is registered on the same site as the propagation one, and
    for the same reason: a rebuild fired from inside an uncommitted write would read the
    old row back and re-cache exactly the stale page it was meant to fix.

    **The two interleave — but not one pair per state change.** Django runs `on_commit`
    callbacks in registration order. The **propagation** callback is registered per state
    change, because a state change is the unit AD-17 propagates. The **revalidation**
    callback is registered once per *logical* change, because a change of two kinds is two
    statements and two state changes but **one** change to the public page — the page ends
    up in one state, and the page that must be rebuilt is the same page either way.

    **The two jobs carry different ids.** The propagation job names the state change; the
    revalidation job names the *request* — its own outbox row, with its own id. That is
    the point of the second outbox: `EventStateChange` has exactly one mutable column and
    it is spoken for, so the revalidation marker is its own table.

    **There is one request for the event, not one per change.** Two changes in quick
    succession update the open request rather than opening a second one — the enqueue-side
    idempotency. So both revalidation jobs name the same request, and the second carries
    the newer version.
    """
    with django_capture_on_commit_callbacks(using=CATALOG, execute=True) as callbacks:
        _run(source, vevent(UID, "20261112T193000", location="Blue Note"))

    change_ids = [str(c.pk) for c in _changes(_event(source))]
    [request] = list(RevalidationRequest.objects.using(CATALOG).all())
    request_id = str(request.pk)
    # Two state changes (a time move and a detail change), so two propagation callbacks —
    # and **one** revalidation, because it is one logical change.
    assert len(callbacks) == 3
    assert request.event_version == 3  # the open request carries the newest version
    assert sent_jobs == [
        (PROPAGATE_TASK, [change_ids[0]]),
        (PROPAGATE_TASK, [change_ids[1]]),
        (REVALIDATE_TASK, [request_id]),
    ], "one propagation per state change, and one revalidation per logical change"


@pytest.mark.django_db(databases=[PERSONAL, CATALOG], transaction=True)
def test_error_after_the_event_write_rolls_back_the_state_change(monkeypatch, sent_jobs):
    source = ics_source()
    _run(source, vevent(UID, START))

    def fail(*args, **kwargs):
        raise RuntimeError("after the Event write")

    monkeypatch.setattr(item_module, "_save_record", fail)  # runs after apply_lifecycle_change
    report = _run(source, vevent(UID, START, status="CANCELLED"))

    assert report.counts == {"failed:RuntimeError": 1}
    event = _event(source)
    assert (event.status, event.event_version) == ("scheduled", 1)
    assert not EventStateChange.objects.using(CATALOG).exists()
    assert sent_jobs == []  # on_commit never fired


@pytest.mark.django_db(databases=[PERSONAL, CATALOG], transaction=True)
def test_broker_failure_after_commit_neither_fails_the_item_nor_skips_other_enqueues(
    monkeypatch, sent_jobs
):
    source = ics_source()
    _run(source, vevent(UID, START))
    attempts = []

    def flaky_broker(name, args):
        attempts.append(args[0])
        if len(attempts) == 1:
            raise ConnectionError("broker down")

    monkeypatch.setattr(outbox, "_send", flaky_broker)
    report = _run(source, vevent(UID, "20261112T193000", location="Blue Note"))

    assert report.counts == {"updated": 1}
    changes = _changes(_event(source))
    assert [c.event_version for c in changes] == [2, 3]  # committed despite the failure
    assert attempts == [str(c.pk) for c in changes]  # the second enqueue still ran
