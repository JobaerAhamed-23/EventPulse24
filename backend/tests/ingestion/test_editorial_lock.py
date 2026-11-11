"""D1: an editor's correction is not undone by the next poll — and what *does* undo it.

**The rule needs no code, and that is the finding.** `ingest_item` hashes the *source's*
payload and venue and returns `unchanged` **before** touching the Event when that hash
matches what it stored last time. So a source repeating the same bad data cannot overwrite a
correction, however many times it repeats it.

A source publishing something genuinely new does win. That is the decision (2026-11-10): it
has said something it did not say before, and the remedy for a source that is repeatedly
wrong is FR-16's reliability score rather than a permanent per-event veto — which would also
block a real cancellation from ever reaching the people who saved the event.

Both halves are pinned here, because a rule enforced by an absence is exactly the kind that
gets deleted by someone tidying up.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from apps.ingestion.models import Event, ReviewItem
from apps.ingestion.services.editorial_review import edit_and_publish
from apps.ingestion.services.ingest_source import ingest_source
from apps.ingestion.services.review_queue import raise_review_item
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from tests.ingestion.pipeline_support import ScriptedFetchPort, calendar, ics_source, vevent

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

UID = "locked@club.example.test"
START = "20261105T193000"
MOVED = "20261105T210000"
NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
EDITOR = Actor.user(uuid4())
SYSTEM = Actor.system("ingest_pipeline")
CORRECTED = "Jazz Night (corrected by an editor)"


def _run(source, *events: str):
    return ingest_source(source.id, fetch_port=ScriptedFetchPort().serve(calendar(*events)))


def _event(source) -> Event:
    return Event.objects.using(CATALOG).get(source=source)


@pytest.fixture
def source():
    return ics_source()


@pytest.fixture
def edited(source):
    """An event the source published, that an editor then corrected the title of."""
    _run(source, vevent(UID, START, summary="Jazz Nite"))
    event = _event(source)
    item = raise_review_item(
        event=event, reason=ReviewItem.Reason.IN_REVIEW, actor=SYSTEM, now=NOW
    ).item
    edit_and_publish(item_id=item.pk, actor=EDITOR, fields={"title": CORRECTED}, now=NOW)
    return _event(source)


def test_a_poll_repeating_the_same_data_leaves_the_edit_standing(source, edited):
    """**The half that matters most**, because it is the ordinary case.

    The source keeps publishing what it always published. The content hash is unchanged, so
    ingestion never reaches the Event at all.
    """
    report = _run(source, vevent(UID, START, summary="Jazz Nite"))

    assert report.counts == {"unchanged": 1}
    assert _event(source).title == CORRECTED


def test_many_repeated_polls_still_leave_the_edit_standing(source, edited):
    """A correction is not worn down by repetition."""
    for _ in range(5):
        _run(source, vevent(UID, START, summary="Jazz Nite"))

    assert _event(source).title == CORRECTED


def test_a_poll_with_genuinely_new_data_overrides_the_edit(source, edited):
    """The other half of the decision, asserted so it is a choice rather than an accident."""
    _run(source, vevent(UID, START, summary="Jazz Night Deluxe"))

    assert _event(source).title == "Jazz Night Deluxe"


def test_a_real_lifecycle_change_still_reaches_saved_users_after_an_edit(source, edited):
    """**Why a permanent per-field lock was refused.**

    An event an editor touched must still be able to be cancelled or moved by its source.
    Locking the fields would have left saved users never told.
    """
    _run(source, vevent(UID, MOVED, summary="Jazz Nite"))

    event = _event(source)
    assert event.event_version > edited.event_version
    assert event.start_time_utc.hour != edited.start_time_utc.hour
