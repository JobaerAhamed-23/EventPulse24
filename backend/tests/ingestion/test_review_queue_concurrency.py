"""Concurrent raises (design: review-queue-model D10): committed, on separate connections.

`transaction=True`: each thread gets its own connection and sees what the other commits, as in
production. A barrier releases both raisers at once, so both inserts race for the open slot.
"""

import threading

import pytest
from django.db import connections

from apps.ingestion.models import IngestionAuditEntry, ReviewItem
from apps.ingestion.services.review_queue import raise_review_item
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import EventFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG], transaction=True)

REPORTS = Actor.system("event_report")


def test_two_reports_racing_for_the_same_event_make_one_item_that_counts_both():
    event = EventFactory()
    barrier = threading.Barrier(2)
    errors = []

    def raiser(category):
        try:
            barrier.wait(timeout=10)
            raise_review_item(actor=REPORTS, reason="user_reported", event=event, category=category)
        except Exception as exc:  # surfaced in the test thread
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [
        threading.Thread(target=raiser, args=(category,))
        for category in (ReviewItem.ReportCategory.WRONG_VENUE, ReviewItem.ReportCategory.DUPLICATE)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == []
    item = ReviewItem.objects.using(CATALOG).get(event=event)
    assert (item.reports_wrong_venue, item.reports_duplicate) == (1, 1)
    assert item.report_count == 2
    actions = sorted(
        IngestionAuditEntry.objects.using(CATALOG)
        .filter(target_id=item.id)
        .values_list("action", flat=True)
    )
    assert actions == ["review_item_bumped", "review_item_raised"]
