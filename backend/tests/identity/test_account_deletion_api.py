"""The account-deletion endpoints: `POST /api/auth/profile/deletion` and
`DELETE /api/auth/profile/deletion`.

This is the HTTP edge of the two commands a person uses to ask for — and to call off —
the deletion of their account. What is proved here is the **edge's** behaviour:

- **Anonymous is refused** with 401, and **a request without a CSRF token is refused**
  with 403.
- **The CSRF check comes first**, so a caller with no session and no token is told
  "your token is wrong" rather than "you are not signed in" — the order is a property of
  the edge, not an accident.
- **The contract is what the OpenAPI says**, and the answer carries the date the
  account will be destroyed.
- **Nothing is destroyed by the request**, and cancelling is a success whether or not
  anything was pending.

**The CSRF refusals use a plain `Client`, not `CsrfClient`**, which is the point of the
split: the refusal is provable because the ordinary client still refuses.
"""

import pytest
from django.test import Client

from apps.identity.models import DeletionRequest, User
from shared.db import PERSONAL
from tests.csrf import ORIGIN, CsrfClient
from tests.identity.factories import UserFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

PASSWORD = "correct-horse-battery"
EMAIL = "maya@example.test"


@pytest.fixture(autouse=True)
def _adapters(email_adapter, throttle_adapter):
    return None


def signed_in_client(email: str = EMAIL) -> CsrfClient:
    client = CsrfClient()
    client.defaults["CONTENT_TYPE"] = "application/json"
    user = UserFactory(email=email, plain_password=PASSWORD)
    client.post(
        "/api/auth/signin",
        {"email": email, "password": PASSWORD},
        content_type="application/json",
    )
    client._test_user = user  # noqa: SLF001
    return client


def ask(client):
    return client.post("/api/auth/profile/deletion", {}, content_type="application/json")


def cancel(client):
    return client.delete("/api/auth/profile/deletion")


class TestAskingToBeDeleted:
    def test_it_is_accepted_and_says_when_the_account_will_go(self):
        client = signed_in_client()

        response = ask(client)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "scheduled"
        assert body["requested_at"]
        assert body["scheduled_for"]

    def test_the_scheduled_date_is_thirty_days_after_the_request(self):
        """**The promise, on the wire.** The answer says when — not "soon"."""
        from datetime import datetime

        client = signed_in_client()

        body = ask(client).json()

        requested = datetime.fromisoformat(body["requested_at"])
        scheduled = datetime.fromisoformat(body["scheduled_for"])
        assert (scheduled - requested).days == 30

    def test_nothing_is_destroyed_by_the_request(self):
        """**The request is a schedule, not an execution.**"""
        client = signed_in_client()

        ask(client)

        assert User.objects.filter(pk=client._test_user.pk).exists()  # noqa: SLF001
        assert DeletionRequest.objects.filter(user_id=client._test_user.pk).count() == 1  # noqa: SLF001

    def test_asking_twice_does_not_move_the_deadline(self):
        """**The promise cannot be extended by pressing the button again.**"""
        client = signed_in_client()

        first = ask(client).json()
        second = ask(client).json()

        assert second["scheduled_for"] == first["scheduled_for"]
        assert DeletionRequest.objects.filter(user_id=client._test_user.pk).count() == 1  # noqa: SLF001

    def test_an_anonymous_caller_is_refused(self):
        client = CsrfClient()

        assert ask(client).status_code == 401

    def test_a_request_without_a_csrf_token_is_refused(self):
        client = Client()
        client.post(
            "/api/auth/signin",
            {"email": EMAIL, "password": PASSWORD},
            content_type="application/json",
        )

        response = client.post(
            "/api/auth/profile/deletion",
            {},
            content_type="application/json",
            headers={"origin": ORIGIN},
        )

        assert response.status_code == 403

    def test_the_csrf_check_comes_before_the_session_check(self):
        """**A caller with no session and no token is told the token is wrong.**

        The order is a property of the edge: a 401 would tell an anonymous caller that
        this endpoint needs a session, and a 403 tells them their token is missing. The
        second is the more useful answer, and it is the one this router gives.
        """
        client = Client()

        response = client.post(
            "/api/auth/profile/deletion",
            {},
            content_type="application/json",
            headers={"origin": ORIGIN},
        )

        assert response.status_code == 403


class TestCallingItOff:
    def test_it_succeeds_and_the_pending_request_is_gone(self):
        client = signed_in_client()
        ask(client)

        response = cancel(client)

        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"
        assert DeletionRequest.objects.filter(user_id=client._test_user.pk).count() == 0  # noqa: SLF001

    def test_the_account_survives(self):
        """**Cancelling returns the account whole.**"""
        client = signed_in_client()
        ask(client)

        cancel(client)

        assert User.objects.filter(pk=client._test_user.pk).exists()  # noqa: SLF001

    def test_cancelling_when_nothing_is_pending_is_not_an_error(self):
        """**An idempotent command, at the edge too.**"""
        client = signed_in_client()

        response = cancel(client)

        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    def test_an_anonymous_caller_is_refused(self):
        client = CsrfClient()

        assert cancel(client).status_code == 401

    def test_a_request_without_a_csrf_token_is_refused(self):
        client = Client()
        client.post(
            "/api/auth/signin",
            {"email": EMAIL, "password": PASSWORD},
            content_type="application/json",
        )

        response = client.delete(
            "/api/auth/profile/deletion",
            headers={"origin": ORIGIN},
        )

        assert response.status_code == 403


class TestTheContract:
    def test_the_openapi_declares_the_two_endpoints_and_their_failures(self):
        """**AD-19: the OpenAPI is the contract, and the contract is checked.**

        The status codes are declared, not merely produced — which is what puts
        `ErrorOut` in the generated client and lets the frontend handle a refusal
        without guessing.

        **The served schema is read, not the checked-in file.** The served one is what
        the frontend's client is generated from, so this asserts the two cannot drift.
        """
        schema = Client().get("/api/openapi.json").json()

        paths = schema["paths"]
        request_path = "/api/auth/profile/deletion"

        assert "post" in paths[request_path], "the request endpoint is not in the contract"
        assert "delete" in paths[request_path], "the cancel endpoint is not in the contract"

        for method in ("post", "delete"):
            responses = paths[request_path][method]["responses"]
            assert "401" in responses, f"{method} does not declare the anonymous refusal"
            assert "403" in responses, f"{method} does not declare the CSRF refusal"
