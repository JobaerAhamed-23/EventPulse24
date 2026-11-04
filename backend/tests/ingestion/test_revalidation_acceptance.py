"""The revalidation signal's acceptance criteria, end to end through the ingest pipeline
(FR-26, FR-27).

Each test here names one of the work item's acceptance criteria and drives it the way the
product does — a re-ingest with a changed feed — rather than by calling the service
directly. **What is asserted is the signal**: which paths it names, and that it fires at
all. What the frontend does with those paths is the frontend's business, and is tested on
the frontend's side.
"""

import pytest
from django.db import transaction
from django.utils import timezone

from apps.ingestion.models import Event, RevalidationRequest
from apps.ingestion.services.ingest_source import ingest_source
from shared.db import CATALOG, PERSONAL
from tests.ingestion.pipeline_support import ScriptedFetchPort, calendar, ics_source, vevent

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

UID = "jazz@club.example.test"
START = "20261105T193000"


def _run(source, *events: str):
    return ingest_source(source.id, fetch_port=ScriptedFetchPort().serve(calendar(*events)))


def _event(source, **filters) -> Event:
    return Event.objects.using(CATALOG).get(source=source, **filters)


def _request(source, **filters) -> RevalidationRequest:
    return RevalidationRequest.objects.using(CATALOG).get(event=_event(source, **filters))


@pytest.fixture
def source():
    # The source names its city, so a venue's fingerprint can be matched on ingest. The
    # pipeline never creates venues — it matches registered ones.
    return ics_source(city="Brooklyn")


@pytest.fixture
def jazz(source):
    # A LOCATION, so the event has a venue — and so a venue change has somewhere to move
    # from. The venue's city is "Brooklyn" by the parser's default; the venue test
    # replaces the city explicitly.
    _run(source, vevent(UID, START, location="The Old Room"))
    return _event(source)


def test_a_cancellation_revalidates_the_event_page(source, jazz):
    """**AC: a lifecycle change rebuilds that event's page only.**"""
    _run(source, vevent(UID, START, status="CANCELLED"))

    request = _request(source)
    assert request.state == RevalidationRequest.State.OPEN
    assert f"/events/{jazz.slug}" in request.paths


def test_a_sold_out_flip_revalidates_the_event_page(source, jazz):
    """**AC: a sold-out flip rebuilds that event's page only.**

    **The sold-out flag comes from a JSON-LD feed, not from an ICS one**, so this drives
    the write path directly rather than through a feed. What the AC is about is the
    *signal*, and the signal is produced by the same write path either way.
    """
    from apps.ingestion.services.event_writes import apply_lifecycle_change
    from domain.lifecycle import Change, ChangeKind
    from shared.actor import Actor

    incoming = _incoming(jazz, is_sold_out=True)
    change = Change(
        kinds=(ChangeKind.SOLD_OUT,),
        fields=frozenset({"is_sold_out"}),
        is_lifecycle=True,
    )
    assert change.is_lifecycle

    with transaction.atomic(using=CATALOG):
        apply_lifecycle_change(
            event=jazz,
            incoming=incoming,
            change=change,
            actor=Actor.system("test"),
            now=timezone.now(),
        )

    request = _request(source)
    assert request.paths == [f"/events/{jazz.slug}"]
    assert request.state == RevalidationRequest.State.OPEN


def _incoming(event: Event, **overrides):
    """The `IncomingEvent` the write path takes, built from the event as it stands."""
    from decimal import Decimal

    from apps.ingestion.services.event_writes import IncomingEvent
    from domain.lifecycle import EventStatus

    defaults = {
        "title": event.title,
        "description": event.description,
        "canonical_url": event.canonical_url,
        "venue_id": event.venue_id,
        "venue_fingerprint": event.venue_fingerprint,
        "title_fingerprint": event.title_fingerprint,
        "start_utc": event.start_time_utc,
        "end_utc": event.end_time_utc,
        "start_time_local": event.start_time_local,
        "start_time_tz": event.start_time_tz,
        "status": EventStatus(event.status),
        "is_sold_out": event.is_sold_out,
        "series_id": event.series_id,
        "tz_inference_confidence": Decimal("1.00"),
        "extraction_confidence": Decimal("1.00"),
        "publication_status": event.publication_status,
        "tz_review_pending": event.tz_review_pending,
    }
    return IncomingEvent(**(defaults | overrides))


def test_a_time_change_revalidates_the_event_page(source, jazz):
    """**AC: a time change rebuilds that event's page only.**"""
    _run(source, vevent(UID, "20261112T193000"))

    request = _request(source)
    assert f"/events/{jazz.slug}" in request.paths


def test_a_venue_change_revalidates_the_event_page_and_both_city_pages(source):
    """**AC: a city's membership change revalidates the affected city page(s).**

    **An event that moves between cities affects two city pages, not one.** The old city
    page still lists the event and the new city page does not list it yet; both are wrong
    until they are rebuilt. The old city is only nameable by the previous venue's id,
    because the recorded `venue_fingerprint` is a hash and a hash cannot be reversed to a
    city.

    **The pipeline never creates venues**, so both venues are registered first and the
    ingest matches one of them by fingerprint.
    """
    from apps.ingestion.models import City
    from apps.ingestion.services.event_writes import apply_lifecycle_change
    from apps.ingestion.services.venue_registry import register_venue
    from domain.lifecycle import Change, ChangeKind
    from shared.actor import Actor

    brooklyn = City.objects.using(CATALOG).create(
        slug="brooklyn", name="Brooklyn", country_code="US", normalized_key="brooklyn"
    )
    queens = City.objects.using(CATALOG).create(
        slug="queens", name="Queens", country_code="US", normalized_key="queens"
    )
    actor = Actor.system("test")
    old_venue = register_venue(
        actor=actor, name="The Old Room", city="Brooklyn", country_code="US", tz="America/New_York"
    )
    old_venue.city_ref = brooklyn
    old_venue.save(using=CATALOG, update_fields=["city_ref", "updated_at"])
    new_venue = register_venue(
        actor=actor, name="The New Room", city="Queens", country_code="US", tz="America/New_York"
    )
    new_venue.city_ref = queens
    new_venue.save(using=CATALOG, update_fields=["city_ref", "updated_at"])

    _run(source, vevent(UID, START, location="The Old Room"))
    jazz = _event(source)
    assert jazz.venue_id == old_venue.pk

    incoming = _incoming(jazz, venue_id=new_venue.pk, venue_fingerprint=new_venue.venue_fingerprint)
    change = Change(
        kinds=(ChangeKind.DETAIL_CHANGED,),
        fields=frozenset({"venue_fingerprint"}),
        is_lifecycle=True,
    )
    with transaction.atomic(using=CATALOG):
        apply_lifecycle_change(
            event=jazz,
            incoming=incoming,
            change=change,
            actor=actor,
            now=timezone.now(),
        )

    request = _request(source)
    assert f"/events/{jazz.slug}" in request.paths
    assert "/events-in-queens" in request.paths
    assert "/events-in-brooklyn" in request.paths


def test_a_publish_revalidates_the_event_page(source, jazz):
    """**AC: publishing revalidates the event page.**

    **Publication is a gate, not a lifecycle fact**, so it does not bump the version — but
    the page it publishes still has to be built, so it still signals. The version guard
    says the rebuild must not be *older* than the signal, not that the version must have
    *changed*, so a signal at the current version is fine.
    """
    from apps.ingestion.services.event_writes import apply_silent_update

    incoming = _incoming(jazz, publication_status=Event.PublicationStatus.PUBLISHED)
    with transaction.atomic(using=CATALOG):
        apply_silent_update(event=jazz, incoming=incoming, now=timezone.now())

    request = _request(source)
    assert request.paths == [f"/events/{jazz.slug}"]
    assert request.state == RevalidationRequest.State.OPEN


def test_an_unpublish_revalidates_the_event_page_so_it_can_404(source, jazz):
    """**AC: unpublishing removes or 404s its page.**

    **The signal is the same as for any other change** — the frontend's public read
    already refuses an unpublished event, so the rebuild replaces the cached 200 with the
    404. No new concept is needed for "removes or 404s": the read decides, and the signal
    asks for the rebuild.
    """
    from apps.ingestion.services.event_writes import apply_silent_update

    incoming = _incoming(jazz, publication_status=Event.PublicationStatus.IN_REVIEW)
    with transaction.atomic(using=CATALOG):
        apply_silent_update(event=jazz, incoming=incoming, now=timezone.now())

    request = _request(source)
    assert request.paths == [f"/events/{jazz.slug}"]
    assert request.state == RevalidationRequest.State.OPEN


def test_a_supersede_revalidates_the_old_page(source, jazz):
    """**AC: a newly-superseded event removes or 404s its page.**

    The successor has its own slug and its own page, which has never been built and so has
    nothing stale to fix — only the *old* page needs rebuilding, and the city page it
    leaves.
    """
    _run(source, vevent(UID, "20261222T193000"))  # 47 days later: beyond the window

    old = Event.objects.using(CATALOG).get(pk=jazz.pk)
    request = RevalidationRequest.objects.using(CATALOG).get(event=old)
    assert f"/events/{old.slug}" in request.paths


def test_the_signal_fires_only_after_the_transaction_commits(
    source, jazz, django_capture_on_commit_callbacks
):
    """**AC: revalidation is triggered after the transaction commits.**

    **A rebuild fired from inside an uncommitted write would read the old row back and
    re-cache exactly the stale page it was meant to fix.** So the enqueue is registered
    with `transaction.on_commit`, and the request row is written in the same transaction
    as the change that caused it.

    **The callbacks are captured, not run.** With the callbacks captured, the enqueue has
    not happened yet — so the job is not sent while the write is still open. Running them
    then sends it, and by then the row is committed.
    """
    from apps.ingestion.services import revalidation as service

    sent: list[str] = []
    original = service._send
    service._send = lambda task, args: sent.append(args[0])
    try:
        with django_capture_on_commit_callbacks(using=CATALOG, execute=False) as callbacks:
            _run(source, vevent(UID, START, status="CANCELLED"))
        # Nothing has been sent: the callbacks are still queued.
        assert sent == []
        assert callbacks

        # The row is committed already — it was written in the same transaction.
        [request] = RevalidationRequest.objects.using(CATALOG).all()
        assert request.state == RevalidationRequest.State.OPEN
    finally:
        service._send = original


def test_a_rollback_takes_the_request_with_it(source, jazz):
    """**The row is written in the caller's transaction, so it commits with the change that
    caused it.** A failure after the write rolls both back."""
    from apps.ingestion.services import ingest_item as item_module

    def fail(*args, **kwargs):
        raise RuntimeError("after the write")

    original = item_module._save_record
    item_module._save_record = fail
    try:
        report = _run(source, vevent(UID, START, status="CANCELLED"))
    finally:
        item_module._save_record = original

    assert report.counts == {"failed:RuntimeError": 1}
    assert not RevalidationRequest.objects.using(CATALOG).exists()


def test_a_change_of_several_kinds_still_signals_once(source, jazz):
    """**One logical change is one signal, however many kinds it has.**

    A cancellation that also flips the sold-out flag is two kinds — two statements, two
    state changes — but it is **one** change to the public page: the page ends up in one
    state, and the page that must be rebuilt is the same page either way. Registering the
    enqueue per kind would send the same request to the broker twice for one change.

    **The version recorded is the change's final version**, not an intermediate one, so the
    version guard compares the rebuild against the newest state the change produced.
    """
    from apps.ingestion.services.event_writes import apply_lifecycle_change
    from domain.lifecycle import Change, ChangeKind
    from shared.actor import Actor

    incoming = _incoming(jazz, status=Event.Status.CANCELLED, is_sold_out=True)
    change = Change(
        kinds=(ChangeKind.CANCELLED, ChangeKind.SOLD_OUT),
        fields=frozenset({"status", "is_sold_out"}),
        is_lifecycle=True,
    )

    sent: list[tuple[str, list[str]]] = []
    from apps.ingestion.services import revalidation as service

    original = service._send
    service._send = lambda task, args: sent.append((task, args))
    try:
        with transaction.atomic(using=CATALOG):
            changes = apply_lifecycle_change(
                event=jazz,
                incoming=incoming,
                change=change,
                actor=Actor.system("test"),
                now=timezone.now(),
            )
    finally:
        service._send = original

    assert len(changes) == 2  # two kinds, two state changes
    request = _request(source)
    assert request.paths == [f"/events/{jazz.slug}"]
    # The final version, not the first kind's.
    assert request.event_version == jazz.event_version + 2


def test_the_signal_carries_no_event_data(source, jazz):
    """**The signal carries paths and a version, and no event data.**

    AD-19's direction of data flow is unchanged: the frontend still holds no domain logic
    and still gets every fact through the generated API client. The backend is telling the
    frontend *which cached pages are wrong*, never *what is true*.
    """
    _run(source, vevent(UID, START, status="CANCELLED"))

    request = _request(source)
    assert request.paths
    for path in request.paths:
        assert path.startswith("/")
        assert "?" not in path
    assert request.event_version >= 1


def test_the_start_time_of_the_event_is_not_in_the_signal(source, jazz):
    """**No event data, concretely.**

    **The slug is a name, not data** — the backend mints it, and the frontend already has
    it in the URL it was asked to rebuild. What must not be in the signal is the *fact*:
    the instant, the status, the venue, the title. The signal's paths name pages; they do
    not say what those pages should say.
    """
    _run(source, vevent(UID, START, status="CANCELLED"))

    request = _request(source)
    rendered = " ".join(request.paths)
    assert "T19:30" not in rendered
    assert "2026-11-06T00:30:00" not in rendered
    assert "cancelled" not in rendered.lower()
    assert jazz.title.lower() not in rendered.lower()
    if jazz.venue_fingerprint:
        assert jazz.venue_fingerprint not in rendered
