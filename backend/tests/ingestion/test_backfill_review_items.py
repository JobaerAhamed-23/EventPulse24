"""The backfill that rescues the events already stranded in `in_review`.

**Why the rescue is needed at all.** `sync_review_item` only fires when ingestion writes an
Event. A quarantined Event whose facts have not changed is never written again, so no future
poll frees it. These rows are reachable only by this command.
"""

from datetime import UTC, datetime
from io import StringIO

import pytest
from django.core.management import call_command

from apps.ingestion.models import Event, ReviewItem
from apps.ingestion.services.review_intake import (
    backfill_in_review_items,
    count_unticketed_in_review,
    sync_review_item,
)
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import EventFactory, make_superseded_pair

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
IN_REVIEW = Event.PublicationStatus.IN_REVIEW


def open_items():
    return ReviewItem.objects.using(CATALOG).filter(
        reason=ReviewItem.Reason.IN_REVIEW, status=ReviewItem.Status.OPEN
    )


def run_command(*args) -> str:
    out = StringIO()
    call_command("backfill_review_items", *args, stdout=out)
    return out.getvalue()


def test_the_backfill_rescues_stranded_events():
    stranded = [EventFactory(publication_status=IN_REVIEW) for _ in range(3)]

    assert backfill_in_review_items(now=NOW) == 3

    assert {item.event_id for item in open_items()} == {event.pk for event in stranded}


def test_the_backfill_is_idempotent():
    """**The AC's requirement, and it holds for two independent reasons.**

    The query skips events that already have an open item, *and* `raise_review_item` refuses
    to stack a second one. The filter is the optimisation; the one-open-item rule is the
    guarantee.
    """
    EventFactory(publication_status=IN_REVIEW)

    assert backfill_in_review_items(now=NOW) == 1
    assert backfill_in_review_items(now=NOW) == 0
    assert open_items().count() == 1


def test_the_backfill_ignores_published_events():
    EventFactory()
    EventFactory(tz_review_pending=True)

    assert backfill_in_review_items(now=NOW) == 0


def test_the_backfill_ignores_rejected_events():
    """A rejected event is not in review; an editor has already decided."""
    EventFactory(publication_status=Event.PublicationStatus.REJECTED)

    assert backfill_in_review_items(now=NOW) == 0


def test_the_backfill_ignores_superseded_events():
    """Terminal (AD-4): no editor can act on it, so a ticket would be work nobody can do."""
    old, _new = make_superseded_pair(publication_status=IN_REVIEW)
    assert old.publication_status == IN_REVIEW

    assert backfill_in_review_items(now=NOW) == 0


def test_the_backfill_skips_events_that_already_have_a_ticket():
    ticketed = EventFactory(publication_status=IN_REVIEW)
    sync_review_item(event=ticketed, now=NOW)
    EventFactory(publication_status=IN_REVIEW)

    assert backfill_in_review_items(now=NOW) == 1
    assert open_items().count() == 2


def test_the_backfill_batches_without_losing_rows():
    """A batch size below the backlog must still reach every row, not just the first page."""
    for _ in range(5):
        EventFactory(publication_status=IN_REVIEW)

    assert backfill_in_review_items(now=NOW, batch_size=2) == 5
    assert open_items().count() == 5


def test_count_unticketed_matches_what_the_backfill_would_raise():
    for _ in range(4):
        EventFactory(publication_status=IN_REVIEW)

    expected = count_unticketed_in_review()

    assert expected == 4
    assert backfill_in_review_items(now=NOW) == expected
    assert count_unticketed_in_review() == 0


# ── The command ─────────────────────────────────────────────────────────────────────────


def test_the_command_raises_and_reports():
    EventFactory(publication_status=IN_REVIEW)

    assert "Raised 1 review item" in run_command()
    assert open_items().count() == 1


def test_the_command_says_so_when_there_is_nothing_to_do():
    assert "Nothing to raise" in run_command()


def test_the_command_dry_run_writes_nothing():
    EventFactory(publication_status=IN_REVIEW)

    output = run_command("--dry-run")

    assert "1 in_review event(s) have no open review item" in output
    assert open_items().count() == 0
