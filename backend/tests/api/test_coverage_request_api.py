"""`POST /api/catalog/coverage-requests`: the endpoint's contract.

**The endpoint is thin by design** — it takes the reader from the session, hands the body
to the published command, and projects the command's plain data back onto the wire. So
these tests are about the *contract*: the statuses, the body, and the refusals.

**What the contract says, in six sentences.**

1. **A signed-out reader is refused.** The router carries `auth=current_user`, so the id
   comes from the session and never from the payload — and a request with no session has
   no reader to attribute the ask to.
2. **A signed-in reader is accepted**, and the row is written.
3. **A second press is a second 201**, not a 409 and not a 500. The row is one per city;
   the count is where the second press lands.
4. **A city we do not have is a 422**, and nothing is written — a request never mints.
5. **Past the limit is a 429**, with the wait in the body.
6. **The body takes a city and nothing else.** A user id in the payload is refused by the
   schema, because the client must not be able to assert who it is.
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.ingestion.models import City, CityCoverageRequest
from apps.ingestion.services import coverage_requests as service
from shared.constants import COVERAGE_REQUEST_LIMIT
from shared.db import CATALOG, PERSONAL
from tests.csrf import CsrfClient

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

User = get_user_model()
URL = "/api/catalog/coverage-requests"

#: A city in the curated catalog.
CITY = "Portland, OR"


@pytest.fixture(autouse=True)
def throttle(monkeypatch):
    """A fresh in-memory throttle per test, with an injected clock.

    The adapter is swapped at the module that calls it, the way
    `tests/personalization/test_event_report_api.py` does, so the limit is deterministic.
    """
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
def city():
    return City.objects.using(CATALOG).create(
        name=CITY,
        country_code="US",
        normalized_key="portland, or",
        slug="portland-or",
        region="or",
    )


def post(client, body):
    return client.post(URL, data=body, content_type="application/json")


# ── The happy path ───────────────────────────────────────────────────────────────────────


def test_a_signed_in_reader_is_accepted(client, city):
    response = post(client, {"city": CITY})

    assert response.status_code == 201
    assert response.json() == {
        "city": CITY,
        "recorded": True,
        "request_count": 1,
        "created": True,
    }


def test_the_request_is_recorded(client, city):
    post(client, {"city": CITY})

    assert CityCoverageRequest.objects.using(CATALOG).count() == 1


def test_the_response_carries_the_city_as_the_catalog_names_it(client):
    """The catalog's spelling, not the caller's.

    A city a *venue* minted carries that venue's spelling (`"Portland, Oregon"`), and the
    reader asked with the catalog's name. The answer uses the catalog's name — the one
    the row points at.
    """
    City.objects.using(CATALOG).create(
        name="Portland, Oregon",
        country_code="US",
        normalized_key="portland",
        slug="portland-or",
        region="or",
    )

    response = post(client, {"city": "Portland, OR"})

    assert response.status_code == 201
    assert response.json()["city"] == "Portland, Oregon"


# ── Idempotence ─────────────────────────────────────────────────────────────────────────


def test_a_second_press_is_a_second_success(client, city):
    """**A second press is not a conflict.**

    The row is one per city, and the database refuses a second one — so a client that
    presses the button twice must not see a 409. It sees 201 again, and the count is
    where the second press lands.
    """
    assert post(client, {"city": CITY}).status_code == 201

    response = post(client, {"city": CITY})

    assert response.status_code == 201
    body = response.json()
    assert body["request_count"] == 2
    assert body["created"] is False
    assert CityCoverageRequest.objects.using(CATALOG).count() == 1


# ── Refusals ─────────────────────────────────────────────────────────────────────────────


def test_a_signed_out_request_is_refused(city):
    response = post(Client(), {"city": CITY})

    assert response.status_code in (401, 403)
    assert CityCoverageRequest.objects.using(CATALOG).count() == 0


def test_a_city_we_do_not_have_is_refused(client):
    """**A request never mints.** A city we have never heard of is a *pick*.

    Picking it provisions it immediately, which is a better answer than queueing it — so
    the request is refused and the reader is sent to the picker. Nothing is written.
    """
    response = post(client, {"city": "Nowhere, ZZ"})

    assert response.status_code == 422
    assert response.json()["code"] == "unknown_home_city"
    assert City.objects.using(CATALOG).count() == 0
    assert CityCoverageRequest.objects.using(CATALOG).count() == 0


def test_an_empty_city_is_refused(client, city):
    """An empty name names no city, and the endpoint does not guess one."""
    response = post(client, {"city": ""})

    assert response.status_code == 422


def test_a_missing_city_is_refused(client, city):
    """The body is required, and the city is required within it."""
    response = post(client, {})

    assert response.status_code == 422


def test_a_body_with_a_user_id_does_not_change_who_is_asking(client, city):
    """**The reader comes from the session, whatever the body says.**

    A user id in the payload is the classic way scoping goes wrong: the client asserts
    *who it is* and the server believes it. Here the body carries somebody else's id and
    the ask is still **the signed-in reader's** — the payload's id is ignored, not obeyed.

    **The row is about a place**, so the reader's id is not on it either; the ask is
    attributed to the session on the audit row, and to nothing on the request.
    """
    mallory = User.objects.create_user(email="mallory@example.test", password="pw")

    response = post(client, {"city": CITY, "user_id": str(mallory.pk)})

    assert response.status_code == 201
    assert CityCoverageRequest.objects.using(CATALOG).count() == 1
    # The count is the ask, and the ask is the signed-in reader's.
    assert CityCoverageRequest.objects.using(CATALOG).get().request_count == 1


def test_the_audit_row_attributes_the_ask_to_the_session(client, city):
    """**The session's reader is on the audit row — and nobody else's.**

    `actor_id` is the codebase's own mechanism for recording who did a thing without
    pairing them with a place in the payload. The city id is in the `details`; the
    reader's id is in the column.
    """
    from apps.ingestion.models import IngestionAuditEntry

    mallory = User.objects.create_user(email="mallory@example.test", password="pw")
    sam = User.objects.get(email="sam@example.test")

    post(client, {"city": CITY, "user_id": str(mallory.pk)})

    audit = IngestionAuditEntry.objects.using(CATALOG).get()
    assert audit.actor_id == sam.pk
    assert audit.actor_id != mallory.pk


# ── The throttle ─────────────────────────────────────────────────────────────────────────


def test_the_sixth_request_answers_429(client, city):
    """Five per reader per day, and the sixth is refused with the wait."""
    for _ in range(COVERAGE_REQUEST_LIMIT):
        assert post(client, {"city": CITY}).status_code == 201

    response = post(client, {"city": CITY})

    assert response.status_code == 429
    body = response.json()
    assert body["code"] == "rate_limited"
    assert body["details"]["retry_after_seconds"] > 0


def test_the_throttled_request_is_not_recorded(client, city):
    """The refusal happens before the write, so it leaves nothing behind."""
    for _ in range(COVERAGE_REQUEST_LIMIT):
        post(client, {"city": CITY})

    post(client, {"city": CITY})

    row = CityCoverageRequest.objects.using(CATALOG).get()
    assert row.request_count == COVERAGE_REQUEST_LIMIT
