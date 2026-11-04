"""The revalidation delivery task (FR-26, FR-27): what it does when the frontend answers,
when it does not, and what a repeat delivery does.

**Every failure is an outcome, not an exception.** A frontend that is down is the normal
condition this signal is designed to survive, and there is no Celery retry anywhere in this
codebase — the house pattern is "record it on the row, retry at the next cadence".
"""

import pytest

from adapters.revalidation.fake import FakeRevalidationAdapter
from apps.ingestion.models import Event, RevalidationRequest
from apps.ingestion.services.revalidation import request_revalidation
from ports.revalidation import RevalidationOutcome
from shared.db import CATALOG
from tests.ingestion.factories import EventFactory
from worker import tasks

pytestmark = pytest.mark.django_db(databases=[CATALOG])


@pytest.fixture
def port(monkeypatch):
    """The fake adapter the task reaches through the port registry."""
    adapter = FakeRevalidationAdapter()
    monkeypatch.setattr(tasks, "get_revalidation_port", lambda: adapter)
    return adapter


def _request(**overrides) -> RevalidationRequest:
    event = EventFactory(publication_status=Event.PublicationStatus.PUBLISHED, **overrides)
    request = request_revalidation(event=event, event_version=2)
    assert request is not None
    return request


def _reload(request: RevalidationRequest) -> RevalidationRequest:
    return RevalidationRequest.objects.using(CATALOG).get(pk=request.pk)


def test_a_delivered_signal_closes_the_request(port):
    request = _request()

    tasks.revalidate_public_pages(str(request.pk))

    refreshed = _reload(request)
    assert refreshed.state == RevalidationRequest.State.DELIVERED
    assert refreshed.closed_at is not None
    assert refreshed.attempts == 0


def test_the_signal_carries_the_paths_and_the_version(port):
    request = _request()

    tasks.revalidate_public_pages(str(request.pk))

    assert len(port.requests) == 1
    assert port.requests[0].paths == tuple(request.paths)
    assert port.requests[0].event_version == request.event_version


def test_a_failed_delivery_leaves_the_request_open_for_the_reconciler(port, monkeypatch):
    """**A frontend that is down will very likely be fine in five minutes.** The request
    stays open, so the reconciler offers it again."""
    port.outcome = RevalidationOutcome.UNAVAILABLE
    port.status = 503
    request = _request()

    tasks.revalidate_public_pages(str(request.pk))

    refreshed = _reload(request)
    assert refreshed.state == RevalidationRequest.State.OPEN
    assert refreshed.attempts == 1
    assert refreshed.last_error == "unavailable"
    assert refreshed.closed_at is None


def test_a_timeout_leaves_the_request_open(port):
    port.outcome = RevalidationOutcome.TIMEOUT
    request = _request()

    tasks.revalidate_public_pages(str(request.pk))

    refreshed = _reload(request)
    assert refreshed.state == RevalidationRequest.State.OPEN
    assert refreshed.attempts == 1
    assert refreshed.last_error == "timeout"


def test_a_wrong_secret_is_permanent_and_is_not_retried(port):
    """**A wrong secret is a deployment misconfiguration, not a transient fault.**"""
    port.outcome = RevalidationOutcome.UNAUTHORIZED
    port.status = 401
    request = _request()

    tasks.revalidate_public_pages(str(request.pk))

    refreshed = _reload(request)
    assert refreshed.state == RevalidationRequest.State.FAILED
    assert refreshed.closed_at is not None
    assert refreshed.last_error == "unauthorized"


def test_the_attempt_bound_exhausts_the_request(port):
    """**"This page is stale and we gave up" is a fact an operator needs to see.**"""
    from shared.constants import REVALIDATION_MAX_ATTEMPTS

    port.outcome = RevalidationOutcome.UNAVAILABLE
    request = _request()

    for _ in range(REVALIDATION_MAX_ATTEMPTS):
        tasks.revalidate_public_pages(str(request.pk))

    refreshed = _reload(request)
    assert refreshed.state == RevalidationRequest.State.EXHAUSTED
    assert refreshed.attempts == REVALIDATION_MAX_ATTEMPTS


def test_a_double_delivery_is_harmless(port):
    """**The conditional close is what makes a double delivery harmless.** The second
    attempt finds nothing open and does nothing — it does not even call the frontend."""
    request = _request()

    tasks.revalidate_public_pages(str(request.pk))
    tasks.revalidate_public_pages(str(request.pk))

    assert len(port.requests) == 1  # the second attempt did not deliver at all
    refreshed = _reload(request)
    assert refreshed.state == RevalidationRequest.State.DELIVERED
    assert refreshed.attempts == 0


def test_a_delivery_to_a_closed_request_does_nothing(port):
    request = _request()
    tasks.revalidate_public_pages(str(request.pk))
    port.requests.clear()

    tasks.revalidate_public_pages(str(request.pk))

    assert port.requests == []


def test_the_reconciler_re_offers_what_nobody_delivered(port, monkeypatch):
    """**A broker outage at enqueue time, or a crash between the commit and the enqueue,
    loses the message — never the row.**"""
    from datetime import timedelta

    from apps.ingestion.services import revalidation as service
    from shared.constants import REVALIDATION_RECONCILE_AFTER

    sent: list[str] = []
    monkeypatch.setattr(service, "_send", lambda task, args: sent.append(args[0]))
    request = _request()
    RevalidationRequest.objects.using(CATALOG).filter(pk=request.pk).update(
        requested_at=request.requested_at - REVALIDATION_RECONCILE_AFTER - timedelta(minutes=1)
    )

    count = service.reconcile_revalidation()

    assert count == 1
    assert sent == [str(request.pk)]


def test_the_reconciler_task_enqueues_the_delivery(port, monkeypatch):
    from datetime import timedelta

    from apps.ingestion.services import revalidation as service
    from shared.constants import REVALIDATION_RECONCILE_AFTER

    sent: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(service, "_send", lambda task, args: sent.append((task, args)))
    request = _request()
    RevalidationRequest.objects.using(CATALOG).filter(pk=request.pk).update(
        requested_at=request.requested_at - REVALIDATION_RECONCILE_AFTER - timedelta(minutes=1)
    )

    tasks.reconcile_revalidation()

    assert sent == [(service.REVALIDATE_TASK, [str(request.pk)])]
