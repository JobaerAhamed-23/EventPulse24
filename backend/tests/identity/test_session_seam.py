"""The session seam: one resolver, used everywhere (AD-5, AD-18, D13).

**The seam used to be `apps.personalization/auth.py`, and it is now `identity`'s
published resolver.** These tests are the proof that the replacement happened in exactly
one place and that the one place works:

- The seam is **published by `identity`**, and the personal module delegates to it.
  `apps.personalization.auth.current_user` is `apps.identity.api_auth.current_user` —
  the same object, not a copy.

- **A session established through the real endpoint works on the personal endpoints.**
  Nothing is forced into the session by hand. The test signs in through
  `POST /api/auth/signin`, and the session cookie that comes back is what the personal
  endpoints then see.

- **The personal endpoints refuse an anonymous request with the same 401 and the same
  message** the auth endpoints use. One rule for "who is this request?", not two.

- **No endpoint takes a user id as input.** The scoping cannot be forged from a payload.
"""

import inspect

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.identity import api_auth
from apps.personalization import auth as personalization_auth
from shared.db import PERSONAL
from tests.csrf import CsrfClient

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

User = get_user_model()

PASSWORD = "correct-horse-battery"
EMAIL = "maya@example.test"


def sign_in(client: CsrfClient, *, email: str = EMAIL, password: str = PASSWORD):
    """Sign in through the real endpoint, and return the response."""
    return client.post(
        "/api/auth/signin",
        {"email": email, "password": password},
        content_type="application/json",
    )


def make_user(email: str = EMAIL):
    return User.objects.create_user(email=email, password=PASSWORD)


# ---------------------------------------------------------------------------
# The seam is in one place
# ---------------------------------------------------------------------------


def test_the_seam_is_published_by_identity():
    """`identity` owns the answer to "who is making a request?"."""
    assert callable(api_auth.current_user)
    assert "current_user" in api_auth.__all__


def test_the_personalization_module_delegates_to_the_published_resolver():
    """The old seam is a delegation, not a second implementation.

    The two names are the *same object*. A copy would let the two drift, which is exactly
    what the one-place rule exists to prevent.
    """
    assert personalization_auth.current_user is api_auth.current_user


def test_the_personalization_module_has_no_own_implementation():
    """The delegation is a re-export, not a function of its own."""
    source = inspect.getsource(personalization_auth)
    assert "def current_user" not in source


def test_the_resolver_is_not_in_the_models_module():
    """The resolver is deliberately **not** `apps/identity/models.py`.

    The import contract `models-identity` keeps `apps.identity.models` private to
    `apps.identity`; other apps reach `identity` through a published interface instead.
    """
    from apps.identity import models

    assert not hasattr(models, "current_user")
    assert not hasattr(models, "require_csrf")


# ---------------------------------------------------------------------------
# A session from the real endpoint works on the personal endpoints
# ---------------------------------------------------------------------------


def test_a_session_from_the_signin_endpoint_identifies_the_user_on_the_personal_endpoint():
    """The session cookie that `POST /api/auth/signin` sets is what the personal
    endpoints resolve.

    Nothing is forced into the session by hand — the cookie comes from the response.
    """
    user = make_user()
    client = CsrfClient()

    assert sign_in(client).status_code == 200

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["id"] == str(user.pk)

    # The same session now reaches a personal endpoint.
    listed = client.get("/api/personal/events")
    assert listed.status_code == 200


def test_a_signup_then_a_signin_identifies_the_user_on_the_personal_endpoint():
    """The account is created, and signing in with it identifies the user.

    Sign-up does not establish a session — it only creates the account. That is what
    keeps the sign-up response identical in its headers as well as its body, so no
    response can be used to find out whether an address is taken. `/api/auth/signin` is
    where the session is created, and the seam treats it exactly like any other.
    """
    client = CsrfClient()

    signup = client.post(
        "/api/auth/signup",
        {"email": EMAIL, "password": PASSWORD},
        content_type="application/json",
    )
    assert signup.status_code == 201
    # No session yet: the account exists, but the browser is not signed in.
    assert client.get("/api/personal/events").status_code == 401

    signin = client.post(
        "/api/auth/signin",
        {"email": EMAIL, "password": PASSWORD},
        content_type="application/json",
    )
    assert signin.status_code == 200
    assert client.get("/api/personal/events").status_code == 200


def test_a_session_made_by_hand_also_works():
    """The personal endpoints do not care *how* the session was established.

    This is the case the old tests used, and it still has to work: a session is a session.
    """
    user = make_user()
    client = CsrfClient()
    client.force_login(user)

    assert client.get("/api/personal/events").status_code == 200


# ---------------------------------------------------------------------------
# The one rule for "who is this request?"
# ---------------------------------------------------------------------------


def test_the_personal_endpoints_refuse_an_anonymous_request_with_the_same_401():
    """The message and the code are the project's, not the personal module's."""
    client = Client()

    response = client.get("/api/personal/events")

    assert response.status_code == 401
    payload = response.json()
    assert payload["code"] == "not_authenticated"
    assert payload["message"] == api_auth.UNAUTHENTICATED_MESSAGE


def test_the_auth_me_endpoint_refuses_an_anonymous_request_the_same_way():
    """Two endpoints, one rule. The bodies are the same."""
    auth_response = Client().get("/api/auth/me")
    personal_response = Client().get("/api/personal/events")

    assert auth_response.status_code == personal_response.status_code == 401
    assert auth_response.content == personal_response.content


# ---------------------------------------------------------------------------
# The user id comes from the session, never from the payload
# ---------------------------------------------------------------------------


def test_no_endpoint_takes_a_user_id_as_input():
    """There is nowhere for a forged user id to come from."""
    schema = Client().get("/api/openapi.json").json()

    for path, methods in schema["paths"].items():
        if not path.startswith("/api/personal") and not path.startswith("/api/auth"):
            continue
        for method, operation in methods.items():
            body = operation.get("requestBody") or {}
            content = body.get("content") or {}
            for media in content.values():
                for name in (media.get("schema") or {}).get("properties", {}):
                    assert "user_id" not in name, f"{method.upper()} {path} accepts {name}"
                    assert "user" not in name, f"{method.upper()} {path} accepts {name}"


def test_a_personal_event_is_scoped_to_the_sessions_user():
    """A second account's event is not visible, and not even discoverable."""
    owner = make_user("owner@example.test")
    other = make_user("other@example.test")

    owner_client = CsrfClient()
    owner_client.force_login(owner)
    other_client = CsrfClient()
    other_client.force_login(other)

    created = owner_client.post(
        "/api/personal/events",
        {
            "name": "Coffee with Sam",
            "start_time_utc": "2026-11-06T03:30:00+00:00",
            "end_time_utc": "2026-11-06T05:30:00+00:00",
            "start_time_tz": "America/Los_Angeles",
        },
        content_type="application/json",
    )
    assert created.status_code == 201

    # The other account sees nothing.
    listed = other_client.get("/api/personal/events")
    assert listed.status_code == 200
    assert listed.json()["items"] == []
