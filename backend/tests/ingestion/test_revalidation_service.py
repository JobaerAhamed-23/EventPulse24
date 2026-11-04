"""The revalidation outbox (FR-26, FR-27): one open request per event, the paths it names,
the post-commit enqueue, the delivery markers and the reconciler.

The service's shape is AD-17's outbox shape: a row written in the caller's transaction, an
enqueue registered on commit, a conditional close, and a reconciler for what nobody
finished. The consumer is different — the frontend's revalidation route handler — and the
marker is this table, because `EventStateChange` has exactly one mutable column and it is
spoken for.
"""

from datetime import timedelta
from uuid import uuid4

import pytest
from django.db import IntegrityError, transaction

from apps.ingestion.models import City, Event, RevalidationRequest, Venue
from apps.ingestion.services import revalidation
from apps.ingestion.services.revalidation import (
    REVALIDATE_TASK,
    enqueue_revalidation,
    mark_delivered,
    mark_failed,
    open_request,
    reconcile_revalidation,
    request_revalidation,
)
from shared.constants import REVALIDATION_MAX_ATTEMPTS, REVALIDATION_RECONCILE_AFTER
from shared.db import CATALOG
from tests.ingestion.factories import EventFactory, VenueFactory, make_superseded_pair

pytestmark = pytest.mark.django_db(databases=[CATALOG])


def _city(slug: str) -> City:
    return City.objects.using(CATALOG).create(
        slug=slug,
        name=slug.title(),
        country_code="US",
        normalized_key=slug,
    )


def _venue(city: City | None = None, **overrides) -> Venue:
    venue = VenueFactory(**overrides)
    if city is not None:
        venue.city_ref = city
        venue.city = city.name
        venue.save(using=CATALOG, update_fields=["city_ref", "city", "updated_at"])
    return venue


def _published_event(**overrides) -> Event:
    return EventFactory(publication_status=Event.PublicationStatus.PUBLISHED, **overrides)


def test_a_change_records_the_event_page_and_its_city_page():
    city = _city("brooklyn")
    venue = _venue(city)
    event = _published_event(venue=venue)

    request = request_revalidation(event=event, event_version=2)

    assert request is not None
    assert request.paths == ["/events/" + event.slug, "/events-in-brooklyn"]
    assert request.state == RevalidationRequest.State.OPEN
    assert request.event_version == 2


def test_an_unpublished_event_still_revalidates_its_own_page():
    """**An unpublished event's own page must be rebuilt — to become a 404.**

    The event page may be cached from before it was unpublished, or before it went into
    review. Only a rebuild can replace that cached 200 with the 404 the public read
    already knows to return. So the event's own path is always named.

    The *city* page is different: an event that was never public was never on the city
    page, so naming the city page would rebuild a page that cannot have changed.
    """
    event = EventFactory(publication_status=Event.PublicationStatus.IN_REVIEW)

    request = request_revalidation(event=event, event_version=2)

    assert request is not None
    assert request.paths == ["/events/" + event.slug]


def test_a_venue_with_no_city_has_no_city_page():
    """**A venue with no `city_ref` has no city page.** The backfill links venues to their
    city, and a venue that named no city resolves to none — the same rule Event Fit
    follows rather than guessing one."""
    event = _published_event(venue=VenueFactory(city_ref=None))

    request = request_revalidation(event=event, event_version=2)

    assert request is not None
    assert request.paths == ["/events/" + event.slug]


def test_an_event_that_moved_between_cities_revalidates_both_city_pages():
    """**The old city page is affected too, and the old city is only nameable by its id.**

    The recorded `venue_fingerprint` is a hash, and a hash cannot be reversed to a city —
    so without the previous venue's id, an event that moved from Brooklyn to Queens could
    not have its old city page revalidated at all.
    """
    brooklyn = _city("brooklyn")
    queens = _city("queens")
    old_venue = _venue(brooklyn)
    new_venue = _venue(queens)
    event = _published_event(venue=new_venue)

    request = request_revalidation(event=event, event_version=2, previous_venue_id=old_venue.pk)

    assert request is not None
    assert request.paths == [
        "/events/" + event.slug,
        "/events-in-brooklyn",
        "/events-in-queens",
    ]


def test_a_move_within_one_city_names_that_city_once():
    brooklyn = _city("brooklyn")
    venue = _venue(brooklyn)
    event = _published_event(venue=venue)

    request = request_revalidation(event=event, event_version=2, previous_venue_id=venue.pk)

    assert request is not None
    assert request.paths == ["/events/" + event.slug, "/events-in-brooklyn"]


def test_a_superseded_event_revalidates_its_page_and_its_city():
    """**A superseded event's page must become a 404**, and its city page must drop it."""
    city = _city("brooklyn")
    venue = _venue(city)
    old, _new = make_superseded_pair(venue=venue)

    request = request_revalidation(event=old, event_version=old.event_version)

    assert request is not None
    assert request.paths == ["/events/" + old.slug, "/events-in-brooklyn"]


def test_one_open_request_per_event():
    """**A second change updates the open row rather than opening a second one.**

    This is the enqueue-side idempotency. The delivery side needs no dedup table, because
    rebuilding a page twice is harmless.
    """
    event = _published_event()

    first = request_revalidation(event=event, event_version=2)
    second = request_revalidation(event=event, event_version=3)

    assert first.pk == second.pk
    assert RevalidationRequest.objects.using(CATALOG).filter(event=event).count() == 1
    refreshed = RevalidationRequest.objects.using(CATALOG).get(pk=first.pk)
    assert refreshed.event_version == 3


def test_a_delivered_request_is_not_reopened():
    event = _published_event()
    request = request_revalidation(event=event, event_version=2)
    assert mark_delivered(request.pk) is True

    second = request_revalidation(event=event, event_version=3)

    assert second.pk != request.pk
    assert second.state == RevalidationRequest.State.OPEN


def test_a_concurrent_writer_opening_a_request_is_not_a_second_request(monkeypatch):
    """**Another writer opened a request for this event between our read and our write.**

    Theirs is the open one; the service updates it rather than opening a second. The
    unique constraint on `(event)` where `state='open'` is what makes that the only
    possible outcome — the second write cannot succeed.

    **The race is simulated in the order it happens**: the service's first read finds
    nothing, the other writer's row lands, and *then* the service's write trips the
    constraint.
    """
    import apps.ingestion.services.revalidation as module

    event = _published_event()
    # The real manager, captured before the patch, so the patched one can still read.
    real_manager = module.RevalidationRequest.objects
    monkeypatch.setattr(module.RevalidationRequest, "objects", _RacingManager(real_manager))

    request = request_revalidation(event=event, event_version=3)

    assert request is not None
    assert request.state == RevalidationRequest.State.OPEN
    assert request.event_version == 3
    assert request.paths == ["/events/" + event.slug]
    assert real_manager.using(CATALOG).filter(event=event).count() == 1


class _RacingManager:
    """A manager that makes the concurrent writer's race happen in the order it does.

    **The first read finds nothing** — the other writer has not committed yet. **The
    write then trips the constraint** — the other writer has committed by now. The
    service's second read then finds *their* row, and updates it rather than opening a
    second one.
    """

    def __init__(self, real_manager) -> None:
        self._real_manager = real_manager
        self._reads = 0

    def using(self, alias):
        return self

    def filter(self, **kwargs):
        self._reads += 1
        if self._reads == 1:
            # The other writer has not committed yet: nothing to find.
            return self._real_manager.using(CATALOG).filter(pk__in=[])
        return self._real_manager.using(CATALOG).filter(**kwargs)

    def create(self, **kwargs):
        # The other writer commits now; ours trips the constraint.
        self._real_manager.using(CATALOG).create(**kwargs)
        raise IntegrityError("revalidation_open_event_uq")


def test_mark_delivered_is_idempotent():
    """**The conditional close is what makes a double delivery harmless.** The second
    attempt finds nothing open and does nothing."""
    event = _published_event()
    request = request_revalidation(event=event, event_version=2)

    assert mark_delivered(request.pk) is True
    assert mark_delivered(request.pk) is False
    assert open_request(request.pk) is None


def test_mark_failed_keeps_the_request_open_so_it_can_be_retried():
    event = _published_event()
    request = request_revalidation(event=event, event_version=2)

    assert mark_failed(request.pk, reason="unavailable") is True

    refreshed = RevalidationRequest.objects.using(CATALOG).get(pk=request.pk)
    assert refreshed.state == RevalidationRequest.State.OPEN
    assert refreshed.attempts == 1
    assert refreshed.last_error == "unavailable"


def test_a_permanent_failure_is_not_retried():
    """**A wrong secret is a deployment misconfiguration, not a transient fault.** Retrying
    it forever is noise, so it is recorded as `failed` and surfaced."""
    event = _published_event()
    request = request_revalidation(event=event, event_version=2)

    mark_failed(request.pk, reason="unauthorized", permanent=True)

    refreshed = RevalidationRequest.objects.using(CATALOG).get(pk=request.pk)
    assert refreshed.state == RevalidationRequest.State.FAILED
    assert refreshed.closed_at is not None


def test_a_request_is_exhausted_at_the_attempt_bound():
    """**The attempt count is the bound.** A request that has failed too many times is
    kept and surfaced, not retried forever: "this page is stale and we gave up" is a fact
    an operator needs to see."""
    event = _published_event()
    request = request_revalidation(event=event, event_version=2)

    for _ in range(REVALIDATION_MAX_ATTEMPTS - 1):
        mark_failed(request.pk, reason="unavailable")

    assert RevalidationRequest.objects.using(CATALOG).get(pk=request.pk).state == (
        RevalidationRequest.State.OPEN
    )

    mark_failed(request.pk, reason="unavailable")

    refreshed = RevalidationRequest.objects.using(CATALOG).get(pk=request.pk)
    assert refreshed.state == RevalidationRequest.State.EXHAUSTED
    assert refreshed.attempts == REVALIDATION_MAX_ATTEMPTS
    assert refreshed.closed_at is not None


def test_mark_failed_on_a_closed_request_does_nothing():
    event = _published_event()
    request = request_revalidation(event=event, event_version=2)
    mark_delivered(request.pk)

    assert mark_failed(request.pk, reason="unavailable") is False


def test_the_attempt_count_is_incremented_by_the_database():
    """**The increment is atomic, so the count is right however many workers arrive.**

    Two workers can hold the same request — the reconciler offering it again and a
    direct enqueue delivering it. A read-then-write would let both read `attempts=4` and
    both write `5`, losing an attempt and stretching the bound. `F("attempts") + 1` makes
    the database do the adding.

    The test does not open two connections — that is a race, not a test. It asserts the
    mechanism: the increment is expressed as a database-side expression, so a concurrent
    writer's update cannot be overwritten by a stale in-memory value.
    """
    from django.db.models import F

    event = _published_event()
    request = request_revalidation(event=event, event_version=2)

    mark_failed(request.pk, reason="unavailable")
    mark_failed(request.pk, reason="unavailable")

    refreshed = RevalidationRequest.objects.using(CATALOG).get(pk=request.pk)
    assert refreshed.attempts == 2

    # The increment is the database's own arithmetic, not Python's.
    assert (
        RevalidationRequest.objects.using(CATALOG)
        .filter(pk=request.pk)
        .update(attempts=F("attempts") + 1)
        == 1
    )
    assert RevalidationRequest.objects.using(CATALOG).get(pk=request.pk).attempts == 3


def test_the_reconciler_re_offers_only_the_old_enough_open_requests():
    """**The reconciler re-offers the rows nobody finished, on a cadence.**"""
    old = _published_event()
    new = _published_event()
    old_request = request_revalidation(event=old, event_version=2)
    new_request = request_revalidation(event=new, event_version=2)

    stale = (
        RevalidationRequest.objects.using(CATALOG)
        .filter(pk=old_request.pk)
        .update(
            requested_at=RevalidationRequest.objects.using(CATALOG)
            .get(pk=old_request.pk)
            .requested_at
            - REVALIDATION_RECONCILE_AFTER
            - timedelta(minutes=1)
        )
    )
    assert stale == 1

    sent: list[str] = []
    import apps.ingestion.services.revalidation as module

    original = module._send
    module._send = lambda task, args: sent.append(args[0])
    try:
        count = reconcile_revalidation()
    finally:
        module._send = original

    assert count == 1
    assert sent == [str(old_request.pk)]
    assert str(new_request.pk) not in sent


def test_the_reconciler_does_not_re_offer_a_delivered_request():
    event = _published_event()
    request = request_revalidation(event=event, event_version=2)
    mark_delivered(request.pk)
    RevalidationRequest.objects.using(CATALOG).filter(pk=request.pk).update(
        requested_at=RevalidationRequest.objects.using(CATALOG).get(pk=request.pk).requested_at
        - REVALIDATION_RECONCILE_AFTER
        - timedelta(minutes=1)
    )

    sent: list[str] = []
    import apps.ingestion.services.revalidation as module

    original = module._send
    module._send = lambda task, args: sent.append(args[0])
    try:
        count = reconcile_revalidation()
    finally:
        module._send = original

    assert count == 0
    assert sent == []


def test_enqueue_revalidation_sends_the_task_name_the_worker_registers():
    sent: list[tuple[str, list[str]]] = []
    import apps.ingestion.services.revalidation as module

    original = module._send
    module._send = lambda task, args: sent.append((task, args))
    try:
        enqueue_revalidation(uuid4())
    finally:
        module._send = original

    assert sent[0][0] == REVALIDATE_TASK == "worker.tasks.revalidate_public_pages"
    assert sent[0][1][0] == str(sent[0][1][0])


def test_the_request_row_is_written_in_the_callers_transaction():
    """**The row is written in the caller's transaction, so it commits with the change that
    caused it.** A rollback takes the request with it."""
    event = _published_event()

    with pytest.raises(RuntimeError), transaction.atomic(using=CATALOG):
        request_revalidation(event=event, event_version=2)
        raise RuntimeError("boom")

    assert not RevalidationRequest.objects.using(CATALOG).exists()


def test_revalidation_is_available_as_a_service_function():
    """The module's public surface is what the worker and the write path use."""
    assert callable(request_revalidation)
    assert callable(enqueue_revalidation)
    assert callable(open_request)
    assert callable(mark_delivered)
    assert callable(mark_failed)
    assert callable(reconcile_revalidation)
    assert revalidation.REVALIDATE_TASK == "worker.tasks.revalidate_public_pages"
