"""The invariant: an `in_review` Event always has an open ticket, and nothing else does.

Driven through the **real** ingest path wherever possible, because the thing under test is
that the raise happens *inside* the write's transaction — which a direct call to
`sync_review_item` would not prove.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from apps.ingestion.models import Event, IngestionAuditEntry, ReviewItem
from apps.ingestion.services.editorial_state import reject_event
from apps.ingestion.services.event_writes import IncomingEvent, create_event
from apps.ingestion.services.ingest_source import ingest_source
from apps.ingestion.services.review_intake import sync_review_item, withdraw_review_item
from domain.lifecycle import EventStatus
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import EventFactory, SourceFactory, VenueFactory
from tests.ingestion.pipeline_support import ScriptedFetchPort, calendar, ics_source, vevent

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

UID = "quarantined@club.example.test"
START = "20261105T193000"
NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
EDITOR = Actor.user(uuid4())


def items(event, *, status=ReviewItem.Status.OPEN):
    return list(
        ReviewItem.objects.using(CATALOG).filter(
            event_id=event.pk, reason=ReviewItem.Reason.IN_REVIEW, status=status
        )
    )


def _run(source, *events: str):
    return ingest_source(source.id, fetch_port=ScriptedFetchPort().serve(calendar(*events)))


@pytest.fixture
def source():
    return ics_source()


# ── The invariant, through the real ingest paths ────────────────────────────────────────


def test_an_event_ingested_into_review_gets_a_ticket(source, monkeypatch):
    """**The bug this item closes.** Before now the event was stored and never looked at."""
    from apps.ingestion.services import ingest_item as item_module

    # A timezone the resolver is unsure about is what sends a real event to IN_REVIEW.
    monkeypatch.setitem(
        item_module._PUBLICATION,
        item_module.Gate.PUBLISH,
        (Event.PublicationStatus.IN_REVIEW, False),
    )
    _run(source, vevent(UID, START))

    event = Event.objects.using(CATALOG).get(source=source)
    assert event.publication_status == Event.PublicationStatus.IN_REVIEW
    assert len(items(event)) == 1


def test_an_event_ingested_as_published_gets_no_ticket(source):
    _run(source, vevent(UID, START))

    event = Event.objects.using(CATALOG).get(source=source)
    assert items(event) == []


def test_a_flagged_event_gets_no_ticket():
    """**D1, confirmed with the user.** `tz_review_pending` is published and working.

    It is neither stuck nor reported, so it does not belong in a queue whose size and
    oldest-item age are the metrics an editor works from.
    """
    event = EventFactory(tz_review_pending=True)

    sync_review_item(event=event, now=NOW)

    assert items(event) == []


def test_a_re_poll_that_publishes_a_quarantined_event_withdraws_its_ticket(source, monkeypatch):
    """The gates move in both directions, so the sync has to as well."""
    from apps.ingestion.services import ingest_item as item_module

    monkeypatch.setitem(
        item_module._PUBLICATION,
        item_module.Gate.PUBLISH,
        (Event.PublicationStatus.IN_REVIEW, False),
    )
    _run(source, vevent(UID, START))
    event = Event.objects.using(CATALOG).get(source=source)
    assert len(items(event)) == 1

    monkeypatch.undo()
    _run(source, vevent(UID, START, summary="Jazz Night (updated)"))

    event.refresh_from_db(using=CATALOG)
    assert event.publication_status == Event.PublicationStatus.PUBLISHED
    assert items(event) == []
    (closed,) = items(event, status=ReviewItem.Status.RESOLVED)
    assert closed.resolution == ReviewItem.Resolution.WITHDRAWN
    assert closed.resolved_by_kind == "system"
    assert closed.resolved_by_label == "review_intake"


# ── The FR-14 seam ──────────────────────────────────────────────────────────────────────


def test_a_low_extraction_confidence_event_gets_a_ticket():
    """**FR-14's LLM path inherits the queue at no cost**, and this proves it today.

    Structured ingestion always writes `extraction_confidence = 1.00`, so the gate that will
    send LLM-extracted events to review cannot be reached through a real feed yet. The event
    is built directly instead — the point being that `sync_review_item` keys off the
    *resulting publication status*, so it never had to learn about the gate at all.
    """
    source = SourceFactory()
    venue = VenueFactory()
    incoming = IncomingEvent(
        title="Uncertain Event",
        description="",
        canonical_url="https://source.example.test/uncertain",
        venue_id=venue.id,
        venue_fingerprint=venue.venue_fingerprint,
        title_fingerprint="uncertain event",
        start_utc=datetime(2026, 12, 1, 3, 0, tzinfo=UTC),
        end_utc=None,
        start_time_local="2026-12-01T19:00:00",
        start_time_tz="America/Los_Angeles",
        status=EventStatus.SCHEDULED,
        is_sold_out=False,
        series_id=None,
        tz_inference_confidence=Decimal("1.00"),
        extraction_confidence=Decimal("0.60"),  # the FR-14 band: below 0.70, above 0.50
        publication_status=Event.PublicationStatus.IN_REVIEW,
        tz_review_pending=False,
    )
    event = create_event(source=source, source_event_id="uncertain-1", incoming=incoming, now=NOW)

    sync_review_item(event=event, now=NOW)

    assert len(items(event)) == 1


# ── Leaving review by a non-editorial route ─────────────────────────────────────────────


def test_withdrawing_is_idempotent():
    event = EventFactory(publication_status=Event.PublicationStatus.IN_REVIEW)
    sync_review_item(event=event, now=NOW)

    assert withdraw_review_item(event=event, now=NOW) == 1
    assert withdraw_review_item(event=event, now=NOW) == 0


def test_withdrawing_writes_an_audit_entry():
    event = EventFactory(publication_status=Event.PublicationStatus.IN_REVIEW)
    sync_review_item(event=event, now=NOW)

    withdraw_review_item(event=event, now=NOW)

    entry = IngestionAuditEntry.objects.using(CATALOG).get(action="review_item_withdrawn")
    assert entry.actor_kind == "system"
    assert entry.details["event_id"] == str(event.pk)


def test_withdrawing_an_event_with_no_item_is_a_no_op():
    assert withdraw_review_item(event=EventFactory(), now=NOW) == 0


def test_syncing_twice_does_not_stack_tickets():
    """`raise_review_item`'s one-open-item-per-(target, reason) rule, relied on here."""
    event = EventFactory(publication_status=Event.PublicationStatus.IN_REVIEW)

    sync_review_item(event=event, now=NOW)
    sync_review_item(event=event, now=NOW)

    assert len(items(event)) == 1


def test_rejecting_an_in_review_event_now_closes_its_item():
    """**The gap `review-intake-and-backfill` pinned, now closed by `editorial-review-commands`.**

    That item's version of this test asserted the item stayed *open*, and said in its
    docstring that it should be changed once the editorial commands landed. This is that
    change.

    The verdict is recorded by `reject_review_item`, which calls `editorial_state.reject_event`
    for the state transition and then closes the queue item itself. Rejection is still
    deliberately **not** routed through `sync_review_item`: a system `withdrawn` would lose
    the editor's name, which is the one thing AD-14 requires a verdict to carry.
    """
    from apps.ingestion.services.editorial_review import reject_review_item
    from apps.ingestion.services.review_queue import raise_review_item

    event = EventFactory(publication_status=Event.PublicationStatus.IN_REVIEW)
    item = raise_review_item(
        event=event,
        reason=ReviewItem.Reason.IN_REVIEW,
        actor=Actor.system("ingest_pipeline"),
        now=NOW,
    ).item

    reject_review_item(item_id=item.pk, actor=EDITOR, now=NOW)

    item.refresh_from_db(using=CATALOG)
    assert item.status == ReviewItem.Status.RESOLVED
    assert item.resolution == ReviewItem.Resolution.REJECTED
    assert item.resolved_by_id == EDITOR.id
    assert item.resolved_by_kind == "user"


def test_rejecting_an_event_directly_still_leaves_the_queue_alone():
    """`editorial_state.reject_event` owns the state transition and nothing else.

    Called on its own it hides the event and cancels reminders, but records no verdict —
    which is why `reject_review_item` exists above it rather than beside it.
    """
    event = EventFactory(publication_status=Event.PublicationStatus.IN_REVIEW)
    sync_review_item(event=event, now=NOW)

    reject_event(event_id=event.pk, actor=EDITOR, now=NOW)

    assert len(items(event)) == 1


# ── The in-transaction invariant (AC) ───────────────────────────────────────────────────


def test_an_event_is_not_written_at_all_if_its_ticket_cannot_be_raised(source, monkeypatch):
    """**"In the same catalog transaction" made falsifiable.**

    The AC's invariant is that an `in_review` Event without an open item cannot exist. A
    rollback test alone would not prove it: a raise deferred to `on_commit` would also
    produce no item on a rollback, and would still be a bug — because on a *successful*
    write it would commit the Event first and the item afterwards, leaving a window, and
    would lose the item entirely if the raise then failed.

    So the test runs the failure the other way round: if the raise fails, **the Event must
    not exist either**. That is only true when the two share a transaction, and it is
    exactly what the probe in `mutation_probe_trust_loop.py` breaks.
    """
    from apps.ingestion.services import ingest_item as item_module
    from apps.ingestion.services import review_intake

    monkeypatch.setitem(
        item_module._PUBLICATION,
        item_module.Gate.PUBLISH,
        (Event.PublicationStatus.IN_REVIEW, False),
    )

    def boom(**kwargs):
        raise RuntimeError("the queue is down")

    monkeypatch.setattr(review_intake, "raise_review_item", boom)

    # `ingest_source` isolates one item's failure from the run, so the error does not
    # propagate here. What matters is the rollback it leaves behind.
    report = _run(source, vevent(UID, START))

    assert any(key.startswith("failed") for key in report.counts)
    assert not Event.objects.using(CATALOG).filter(source=source).exists()
    assert ReviewItem.objects.using(CATALOG).count() == 0
