"""The session seam (AD-5, AD-12).

`apps.personalization.auth` is one function, and these tests pin the two properties it
exists for:

- **The user id comes from the session, never from the request body.** A user-supplied user
  id in a payload is the classic way scoping goes wrong: the client asserts *who it is*, and
  the server believes it. Here there is nowhere for one to come from — no endpoint in this
  app accepts a user id as input.
- **An anonymous request is refused**, with the project's calm voice: "Please sign in to
  continue." The 401 comes from the shared handler in `config/errors.py`, so the message and
  the shape are the project's, not this module's.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import Client, RequestFactory

from apps.personalization.auth import UNAUTHENTICATED_MESSAGE, current_user
from shared.db import PERSONAL

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

User = get_user_model()


def test_a_signed_in_request_resolves_to_that_user():
    user = User.objects.create_user(email="sam@example.test", password="pw")
    request = RequestFactory().get("/api/personal/events")
    request.user = user

    assert current_user(request) == user


def test_an_anonymous_request_is_refused():
    from ninja.errors import HttpError

    request = RequestFactory().get("/api/personal/events")
    request.user = AnonymousUser()

    with pytest.raises(HttpError) as caught:
        current_user(request)

    assert caught.value.status_code == 401
    assert caught.value.message == UNAUTHENTICATED_MESSAGE


def test_a_user_with_no_session_is_still_a_user():
    """Django's `User.is_authenticated` is always True; only `AnonymousUser` is False.

    So the seam checks `is_authenticated`, not whether a session row exists — a request that
    reached the endpoint at all has already been through the session middleware.
    """
    user = User.objects.create_user(email="guest@example.test", password="pw")
    request = RequestFactory().get("/api/personal/events")
    request.user = user

    assert current_user(request) == user


def test_a_request_with_no_user_at_all_is_refused():
    """The middleware may not have run — the seam must not fall back to anyone."""
    from ninja.errors import HttpError

    request = RequestFactory().get("/api/personal/events")

    with pytest.raises(HttpError) as caught:
        current_user(request)

    assert caught.value.status_code == 401


def test_an_anonymous_request_gets_the_shared_401_shape():
    response = Client().get("/api/personal/events")

    assert response.status_code == 401
    assert response.json() == {
        "code": "not_authenticated",
        "message": "Please sign in to continue.",
    }
