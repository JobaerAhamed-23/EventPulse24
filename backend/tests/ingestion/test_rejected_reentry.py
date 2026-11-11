"""A rejected Event cannot come back by ingestion (design D8, D9).

**This is the hole the design exists to close, and it was a live one.**
`IncomingEvent.gating()` "follows every new resolution, silently" (run-015 plan P1), and it
is applied on *every* update. The source that produced a bad listing keeps sending it on
every poll, so without the freeze the very next run after an editor's reject would write
`published` straight back over the verdict — within the hour, and with nothing in the log
that looks unusual.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from apps.ingestion.models import Event, EventStateChange, ExtractedRecord, ReviewItem
from apps.ingestion.services.editorial_state import reject_event
from apps.ingestion.services.ingest_source import ingest_source
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from tests.ingestion.pipeline_support import ScriptedFetchPort, calendar, ics_source, vevent

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

UID = "duplicate@club.example.test"
START = "20261105T193000"
START_UTC = datetime(2026, 11, 6, 0, 30, tzinfo=UTC)
EDITOR = Actor.user(uuid4())


def _run(source, *events: str):
    return ingest_source(source.id, fetch_port=ScriptedFetchPort().serve(calendar(*events)))


def _event(source) -> Event:
    return Event.objects.using(CATALOG).get(source=source)


@pytest.fixture
def source():
    return ics_source()


@pytest.fixture
def rejected(source):
    _run(source, vevent(UID, START))
    event = _event(source)
    reject_event(event_id=event.pk, actor=EDITOR)
    event.refresh_from_db(using=CATALOG)
    return event


def test_a_later_poll_of_the_same_item_does_not_republish_a_rejected_event(source, rejected):
    """The re-entry hole. The source re-sends it; the verdict holds."""
    _run(source, vevent(UID, START, summary="Jazz Night (updated)"))

    event = _event(source)
    assert event.publication_status == Event.PublicationStatus.REJECTED


def test_a_later_poll_still_updates_the_evidence(source, rejected):
    """Only the gate is frozen.

    The title and the extracted record keep following the source, so the evidence an editor
    reviews stays current and a reinstatement shows today's facts rather than the ones that
    got it rejected.
    """
    _run(source, vevent(UID, START, summary="Jazz Night (updated)"))

    event = _event(source)
    assert event.title == "Jazz Night (updated)"
    assert ExtractedRecord.objects.using(CATALOG).filter(source=source).exists()


def test_a_later_poll_of_a_rejected_event_raises_no_review_item(source, rejected):
    """D9: the source's persistence is not news.

    Raising an item per poll would re-queue a decision the editor already made, hourly,
    forever — the queue spam `review-queue-model` D2's one-open-item rule exists to stop.
    """
    before = ReviewItem.objects.using(CATALOG).count()

    _run(source, vevent(UID, START, summary="Jazz Night (updated)"))

    assert ReviewItem.objects.using(CATALOG).count() == before


def test_a_lifecycle_change_from_the_source_still_applies_to_a_rejected_event(source, rejected):
    """A reject freezes visibility, not the facts.

    If the source cancels the event, that is still true and still recorded — the event is
    simply not public while it is rejected. Freezing the whole row would make the catalog
    lie about what the source said.
    """
    _run(source, vevent(UID, START, status="CANCELLED"))

    event = _event(source)
    assert event.status == Event.Status.CANCELLED
    assert event.publication_status == Event.PublicationStatus.REJECTED


def test_an_unrejected_event_still_follows_the_gate(source):
    """The freeze is scoped to `rejected` and nothing else.

    Without this, a freeze written slightly too wide would strand every `in_review` event
    in the state that put it there — the exact bug this intent exists to fix.
    """
    _run(source, vevent(UID, START))
    event = _event(source)
    Event.objects.using(CATALOG).filter(pk=event.pk).update(
        publication_status=Event.PublicationStatus.IN_REVIEW
    )

    _run(source, vevent(UID, START, summary="Jazz Night (updated)"))

    assert _event(source).publication_status == Event.PublicationStatus.PUBLISHED


def test_ingestion_never_writes_a_relisted_change(source, rejected):
    """Reversal is an editor's command alone (D8)."""
    _run(source, vevent(UID, START, summary="Jazz Night (updated)"))

    kinds = set(
        EventStateChange.objects.using(CATALOG)
        .filter(event_id=rejected.pk)
        .values_list("kind", flat=True)
    )
    assert EventStateChange.Kind.RELISTED not in kinds
