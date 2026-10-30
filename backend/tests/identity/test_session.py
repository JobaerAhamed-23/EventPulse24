"""Sign-out: the session ends, and the sign-out is audited (D14).

`sign_out(*, user, request)` takes the user explicitly rather than reading
`request.user`: the services take explicit arguments (D20), and the actor of the audit
row must not be whatever happens to be on the request.
"""

import pytest
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session

from apps.identity.models import IdentityAuditEntry
from apps.identity.services import sign_out
from shared.db import PERSONAL
from tests.identity.factories import UserFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])


class _FakeRequest:
    """The smallest thing `sign_out` needs: a request carrying a session."""

    def __init__(self, session):
        self.session = session


def _request_for(user) -> tuple[_FakeRequest, str]:
    """A request carrying a live session for `user`, and that session's key.

    The store mints its own key and owns its row, so the test and the service address
    the same session — no separate row is created for the test to assert about.
    """
    store = SessionStore()
    store["_auth_user_id"] = str(user.pk)
    store.save()
    return _FakeRequest(store), store.session_key


def test_sign_out_ends_the_session():
    """The session row is gone, so the cookie identifies nobody."""
    user = UserFactory(email="maya@example.com")
    request, session_key = _request_for(user)

    sign_out(user=user, request=request)

    assert not Session.objects.using(PERSONAL).filter(pk=session_key).exists()


def test_sign_out_writes_an_audit_row():
    """D14: sign-out is audited, with the actor id and no address."""
    user = UserFactory(email="maya@example.com")
    request, _session_key = _request_for(user)

    sign_out(user=user, request=request)

    entry = IdentityAuditEntry.objects.using(PERSONAL).get()
    assert entry.action == "sign_out"
    assert entry.target_type == "User"
    assert entry.target_id == user.pk
    assert entry.actor_id == user.pk


def test_the_sign_out_audit_row_holds_no_email():
    """AD-13: the actor is a UUID, so no address reaches the row."""
    user = UserFactory(email="maya@example.com")
    request, _session_key = _request_for(user)

    sign_out(user=user, request=request)

    entry = IdentityAuditEntry.objects.using(PERSONAL).get()
    assert "maya@example.com" not in str(entry.actor_label)
    assert "maya@example.com" not in str(entry.details)


def test_sign_out_on_a_request_with_no_session_is_a_no_op():
    """Not every request carries a session; signing out anyway must not raise."""

    class _Bare:
        pass

    user = UserFactory(email="maya@example.com")

    sign_out(user=user, request=_Bare())

    assert IdentityAuditEntry.objects.using(PERSONAL).count() == 0
