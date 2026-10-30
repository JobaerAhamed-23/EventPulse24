"""The `backfill_event_fit` command (AD-10, FR-26): idempotent, batched, and quiet when
there is nothing to do.

The command holds no model query of its own — `apps.ingestion.models` is importable only
from `apps.ingestion` (AD-2) — so the query lives in the service and the command calls it.
This file tests the command's own behaviour: what it reports, what it writes, and that
running it twice does not double the rows.
"""

from datetime import UTC, datetime, timedelta
from io import StringIO

import pytest
from django.core.management import call_command

from apps.ingestion.models import EventFit
from shared.db import CATALOG
from tests.ingestion.factories import EventFactory

pytestmark = pytest.mark.django_db(databases=[CATALOG])

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


def _event(**overrides):
    return EventFactory(**overrides)


def _fits() -> list[EventFit]:
    return list(EventFit.objects.using(CATALOG).order_by("pk"))


def _run(*args: str) -> str:
    out = StringIO()
    call_command("backfill_event_fit", *args, stdout=out)
    return out.getvalue()


def test_the_command_writes_a_row_for_every_published_event():
    _event(start_time_utc=NOW + timedelta(hours=2))
    _event(start_time_utc=NOW + timedelta(hours=3))

    output = _run()

    assert "Fitted 2 events" in output
    assert len(_fits()) == 2


def test_the_command_is_idempotent():
    """Running it twice writes the same rows, not twice as many.

    This is the whole point of the upsert: a backfill can be re-run after a deploy or a
    failure without a second thought.
    """
    _event(start_time_utc=NOW + timedelta(hours=2))
    _event(start_time_utc=NOW + timedelta(hours=3))

    _run()
    _run()

    assert len(_fits()) == 2


def test_the_dry_run_writes_nothing():
    _event(start_time_utc=NOW + timedelta(hours=2))

    output = _run("--dry-run")

    assert "Would fit 1 published events" in output
    assert _fits() == []


def test_the_command_reports_the_events_it_skipped():
    """A venue with no city has no row to write, and the count says so.

    Hiding the difference would make the output look like a bug — "fitted 0 of 1" with no
    explanation is a worse report than one that says why.

    The event has a **venue** whose city is blank. An event with no venue at all is not
    even a candidate — the query never sees it — so it is not in the count either.
    """
    from tests.ingestion.factories import VenueFactory

    _event(venue=VenueFactory(city="   "))

    output = _run()

    assert "Fitted 0 events across 1 published events" in output
    assert "no venue city" in output


def test_an_event_with_no_venue_at_all_is_not_a_candidate():
    """It has no row to write, and it is not in the count either.

    The count is "the published events the backfill considered", and an event with no
    venue is not considered — there is nothing to consider. Counting it would make the
    report say "skipped 1" for an event the backfill never looked at.
    """
    _event(venue=None, venue_fingerprint="venue-x|unknown")

    output = _run()

    assert "Fitted 0 events across 0 published events" in output
    assert "no venue city" not in output


def test_the_command_batches():
    """The batching is the bound on the refresh cost."""
    for n in range(5):
        _event(start_time_utc=NOW + timedelta(hours=n))

    output = _run("--batch-size", "2")

    assert "Fitted 5 events" in output
    assert len(_fits()) == 5


def test_the_command_says_so_when_there_is_nothing_to_do():
    output = _run()

    assert "Fitted 0 events" in output
    assert _fits() == []
