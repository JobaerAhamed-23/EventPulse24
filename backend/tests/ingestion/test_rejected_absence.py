"""A rejected Event is absent from every public read, and present in the database (design D1).

**The whole point of the design is that this file needed no production read to change.** Every
public read already filters `publication_status == published` by equality, so a third value
leaves all of them at once. These tests exist to prove that claim surface by surface rather
than to assert it once, because "they all filter by equality" is exactly the kind of statement
that stays true until one of them is rewritten with an `exclude(in_review)`.

Each test rejects the event through the real command, so the version bump and the state change
are in the path too.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from apps.ingestion.event_fit.reads import list_event_fit_for_city
from apps.ingestion.event_fit.writes import write_event_fit
from apps.ingestion.models import Event
from apps.ingestion.services.catalog_read import (
    EventNotFoundError,
    get_public_event,
    get_public_event_by_slug,
    get_public_events,
    list_public_candidates,
    list_public_events,
)
from apps.ingestion.services.editorial_state import reject_event
from apps.ingestion.services.url_feed_read import list_url_feed
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import EventFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
EDITOR = Actor.user(uuid4())
CITY = "Los Angeles"
FIT_ACTOR = Actor.system("rejected_absence_test")


@pytest.fixture
def event() -> Event:
    return EventFactory(start_time_utc=NOW + timedelta(hours=16))


def reject(event: Event) -> None:
    reject_event(event_id=event.pk, actor=EDITOR)


# --- It is hidden, not gone -----------------------------------------------------------------


def test_a_rejected_event_is_still_in_the_database(event):
    """**Never delete.** The row, its history and its evidence all stay."""
    reject(event)

    stored = Event.objects.using(CATALOG).get(pk=event.pk)
    assert stored.publication_status == Event.PublicationStatus.REJECTED
    assert stored.title == event.title


# --- One test per public read ----------------------------------------------------------------


def test_a_rejected_event_is_absent_from_the_catalog_list(event):
    items, total = list_public_events(now=NOW)
    assert [item.id for item in items] == [event.pk]
    assert total == 1

    reject(event)

    items, total = list_public_events(now=NOW)
    assert items == []
    assert total == 0


def test_a_rejected_event_is_absent_from_the_catalog_detail(event):
    assert get_public_event(event_id=event.pk, now=NOW).id == event.pk

    reject(event)

    with pytest.raises(EventNotFoundError):
        get_public_event(event_id=event.pk, now=NOW)


def test_a_rejected_event_is_absent_from_the_batch_read(event):
    """The read every saved-event surface uses: the Timeline, the conflicts page, the cards.

    This is what makes a saver's card fall back to "event no longer available" with no
    personal write at all (design D6).
    """
    assert set(get_public_events(event_ids={event.pk})) == {event.pk}

    reject(event)

    assert get_public_events(event_ids={event.pk}) == {}


def test_a_rejected_event_is_absent_from_the_public_event_url(event):
    assert get_public_event_by_slug(slug=event.slug).slug == event.slug

    reject(event)

    with pytest.raises(EventNotFoundError):
        get_public_event_by_slug(slug=event.slug)


def test_a_rejected_event_is_absent_from_the_digest_candidates(event):
    assert [c.id for c in list_public_candidates(now=NOW)] == [event.pk]

    reject(event)

    assert list_public_candidates(now=NOW) == []


def test_a_rejected_event_is_absent_from_the_url_feed(event):
    """The sitemap's source (FR-28): a rejected event's URL must stop being advertised."""
    paths = {entry.path for entry in list_url_feed(now=NOW).items}
    assert any(event.slug in path for path in paths)

    reject(event)

    paths = {entry.path for entry in list_url_feed(now=NOW).items}
    assert not any(event.slug in path for path in paths)


def test_a_rejected_event_is_absent_from_the_event_fit_preview(event):
    """Event Fit keeps its row; the read is what drops it.

    The fit row is deliberately *not* deleted by a reject — nothing in this design deletes
    anything — so this proves the read's own filter, which is the thing that protects the
    preview if an editor reinstates the event later.
    """
    write_event_fit(event=event, now=NOW, actor=FIT_ACTOR)
    assert [entry.id for entry in list_event_fit_for_city(city=CITY, now=NOW)] == [event.pk]

    reject(event)

    assert list_event_fit_for_city(city=CITY, now=NOW) == []


# --- And it comes back ------------------------------------------------------------------------


def test_a_reinstated_event_returns_to_the_public_reads(event):
    """Reversible by an editor, and the reads need nothing special to notice."""
    from apps.ingestion.services.editorial_state import reinstate_event

    reject(event)
    reinstate_event(event_id=event.pk, actor=EDITOR)

    items, _ = list_public_events(now=NOW)
    assert [item.id for item in items] == [event.pk]
    assert get_public_event(event_id=event.pk, now=NOW).id == event.pk
