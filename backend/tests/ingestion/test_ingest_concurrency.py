"""Concurrency (pipeline design D2, D4): committed transactions on separate connections.

`transaction=True`: every thread gets its own connection, and what one commits is visible to
the others, as in production.
"""

import threading

import pytest
from django.db import connections

from apps.ingestion.models import Event
from apps.ingestion.services import ingest_item as item_module
from apps.ingestion.services import ingest_source as source_module
from apps.ingestion.services.ingest_source import ingest_source, source_run_key
from shared.db import CATALOG, PERSONAL
from tests.ingestion.pipeline_support import ScriptedFetchPort, calendar, ics_source, vevent

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG], transaction=True)

SHOW_URL = "https://fillmore.example.test/shows/42"


def _in_thread(target, *args):
    errors, results = [], []

    def run():
        try:
            results.append(target(*args))
        except Exception as exc:  # surfaced in the test thread
            errors.append(exc)
        finally:
            connections.close_all()

    thread = threading.Thread(target=run)
    thread.start()
    return thread, results, errors


def _try_lock(key: int) -> bool:
    with connections[CATALOG].cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [key])
        acquired = cursor.fetchone()[0]
        if acquired:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [key])
        return acquired


def test_two_sources_racing_on_one_happening_create_one_event(monkeypatch):
    """Both items reach the live-set lookup together unless the identity lock serializes them.

    Without the lock, each sees no Event and creates one. With it, the second waits, then
    finds the first's committed Event and binds to it.
    """
    barrier = threading.Barrier(2)
    real = item_module._live_events

    def rendezvous(candidate):
        try:
            barrier.wait(timeout=2)
        except threading.BrokenBarrierError:
            pass  # the other item is held at its identity lock: proceed alone
        return real(candidate)

    monkeypatch.setattr(item_module, "_live_events", rendezvous)
    feeds = [
        ics_source(url="https://fillmore.example.test/cal.ics"),
        ics_source(url="https://tickets.example.test/sf.ics"),
    ]
    body = calendar(vevent("show", "20261105T193000", url=SHOW_URL))

    def run(feed):
        return ingest_source(feed.id, fetch_port=ScriptedFetchPort().serve(body))

    runs = [_in_thread(run, feed) for feed in feeds]
    for thread, _, _ in runs:
        thread.join(timeout=20)

    assert [errors for _, _, errors in runs] == [[], []]
    outcomes = sorted(next(iter(results[0].counts)) for _, results, _ in runs)
    assert outcomes == ["bound_other_source", "new"]
    assert Event.objects.using(CATALOG).count() == 1


def test_second_run_of_a_source_reports_already_running():
    source = ics_source()
    held, release = threading.Event(), threading.Event()

    def hold():
        with connections[CATALOG].cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", [source_run_key(source.id)])
            held.set()
            release.wait(timeout=10)
            cursor.execute("SELECT pg_advisory_unlock(%s)", [source_run_key(source.id)])

    thread, _, errors = _in_thread(hold)
    held.wait(timeout=10)
    port = ScriptedFetchPort().serve(calendar())
    try:
        report = ingest_source(source.id, fetch_port=port)
    finally:
        release.set()
        thread.join(timeout=10)

    assert (report.outcome, report.counts, port.calls, errors) == ("already_running", {}, [], [])


def test_run_lock_is_released_after_an_unexpected_error(monkeypatch):
    source = ics_source()

    def explode(*args, **kwargs):
        raise RuntimeError("parser crashed")

    monkeypatch.setattr(source_module, "parse", explode)
    with pytest.raises(RuntimeError):
        ingest_source(source.id, fetch_port=ScriptedFetchPort().serve(calendar()))

    # Advisory locks are re-entrant within one session, so ask from another connection.
    thread, results, errors = _in_thread(_try_lock, source_run_key(source.id))
    thread.join(timeout=10)
    assert (results, errors) == ([True], [])
