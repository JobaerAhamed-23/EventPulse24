"""`POST /api/personal/event-reports`: the FR-59 contract.

The endpoint is thin by design — it resolves the user, checks visibility with the public
read, and calls the service — so these tests are about the *contract*: the statuses, the
body, and the two refusals that must not leak information.
"""

from datetime import timedelta
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from apps.ingestion.models import Event, ReviewItem
from apps.personalization.models import EventReport
from apps.personalization.services import event_reports as service
from shared.constants import EVENT_REPORT_DAILY_LIMIT
from shared.db import CATALOG, PERSONAL
from tests.csrf import CsrfClient
from tests.ingestion.factories import EventFactory, make_superseded_pair

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

User = get_user_model()
URL = "/api/personal/event-reports"


@pytest.fixture(autouse=True)
def throttle(monkeypatch):
    from adapters.throttle.memory import InMemoryThrottleAdapter

    clock = {"now": 1_000_000.0}
    adapter = InMemoryThrottleAdapter(now=lambda: clock["now"])
    monkeypatch.setattr(service, "get_throttle_port", lambda: adapter)
    return adapter


@pytest.fixture
def client():
    c = CsrfClient()
    c.force_login(User.objects.create_user(email="sam@example.test", password="pw"))
    return c


@pytest.fixture
def event():
    return EventFactory(start_time_utc=timezone.now() + timedelta(days=7))


def post(client, event_id, category="wrong_date_time"):
    return client.post(
        URL, data={"event_id": str(event_id), "category": category}, content_type="application/json"
    )


# ── The happy path ───────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "category", ["wrong_date_time", "wrong_venue", "does_not_exist", "duplicate"]
)
def test_each_category_is_accepted(client, event, category):
    response = post(client, event.pk, category)

    assert response.status_code == 201
    assert response.json() == {"reported": True, "category": category}


def test_the_response_carries_nothing_but_the_toast(client, event):
    """**No report id, no tally, no queue state.**

    A client that could read the tally could count other people's reports, which is a fact
    about other users rather than about this one.
    """
    body = post(client, event.pk).json()

    assert set(body) == {"reported", "category"}


def test_a_report_creates_the_row_and_the_item(client, event):
    post(client, event.pk)

    assert EventReport.objects.using(PERSONAL).count() == 1
    assert (
        ReviewItem.objects.using(CATALOG)
        .filter(event_id=event.pk, reason=ReviewItem.Reason.USER_REPORTED)
        .exists()
    )


# ── Refusals ─────────────────────────────────────────────────────────────────────────────


def test_a_signed_out_request_is_refused(event):
    response = post(Client(), event.pk)

    assert response.status_code in (401, 403)
    assert EventReport.objects.using(PERSONAL).count() == 0


def test_an_invalid_category_is_refused(client, event):
    response = post(client, event.pk, "the_vibes_are_off")

    assert response.status_code == 422
    assert EventReport.objects.using(PERSONAL).count() == 0


def test_an_unknown_event_is_not_found(client):
    response = post(client, uuid4())

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_an_in_review_event_is_not_found(client):
    """**The endpoint cannot be used to probe hidden events.**

    A quarantined event answers exactly as an unknown id does — same status, same body — so
    a caller learns nothing about what the catalog is holding back.
    """
    hidden = EventFactory(
        publication_status=Event.PublicationStatus.IN_REVIEW,
        start_time_utc=timezone.now() + timedelta(days=7),
    )
    unknown = post(client, uuid4())

    response = post(client, hidden.pk)

    assert response.status_code == 404
    assert response.json()["code"] == unknown.json()["code"]


def test_a_rejected_event_is_not_found(client):
    rejected = EventFactory(
        publication_status=Event.PublicationStatus.REJECTED,
        start_time_utc=timezone.now() + timedelta(days=7),
    )

    assert post(client, rejected.pk).status_code == 404


def test_a_superseded_event_is_not_found(client):
    old, _new = make_superseded_pair(start_time_utc=timezone.now() + timedelta(days=7))

    assert post(client, old.pk).status_code == 404


# ── The throttle ─────────────────────────────────────────────────────────────────────────


def test_the_sixth_report_answers_429(client):
    events = [
        EventFactory(start_time_utc=timezone.now() + timedelta(days=7))
        for _ in range(EVENT_REPORT_DAILY_LIMIT + 1)
    ]
    for event in events[:EVENT_REPORT_DAILY_LIMIT]:
        assert post(client, event.pk).status_code == 201

    response = post(client, events[-1].pk)

    assert response.status_code == 429
    body = response.json()
    assert body["code"] == "rate_limited"
    assert body["details"]["retry_after_seconds"] > 0


def test_the_throttled_report_is_not_stored(client):
    events = [
        EventFactory(start_time_utc=timezone.now() + timedelta(days=7))
        for _ in range(EVENT_REPORT_DAILY_LIMIT + 1)
    ]
    for event in events[:EVENT_REPORT_DAILY_LIMIT]:
        post(client, event.pk)

    post(client, events[-1].pk)

    assert EventReport.objects.using(PERSONAL).count() == EVENT_REPORT_DAILY_LIMIT
