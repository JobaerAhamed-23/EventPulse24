"""The email-change endpoints: `POST /api/auth/profile/email` and `.../email/confirm`.

This is the HTTP edge of the two commands that move a login. What is proved here is the
**edge's** behaviour, and the properties it must not lose:

- **The answer is the same for a free address and a taken one** — status *and* body. A
  difference of any kind turns this endpoint into an oracle for *"does an account exist at
  this address?"*, which the whole flow is shaped to avoid.
- **Both messages are sent, to the right mailboxes.** The confirmation to the new address
  proves it; the warning to the old one is the security control.
- **The confirmation endpoint works with no session**, because the link is opened from a
  mailbox, in a browser that may never have signed in — and it is still CSRF-checked,
  exactly as the password-reset confirmation is.

**The CSRF refusals use a plain `Client`, not `CsrfClient`**, which is the point of the
split: the refusal is provable because the ordinary client still refuses.
"""

import pytest
from django.test import Client

from apps.identity.models import PendingEmailChange, User
from shared.db import PERSONAL
from tests.csrf import ORIGIN, CsrfClient
from tests.identity.factories import UserFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

PASSWORD = "correct-horse-battery"
OLD = "maya@example.test"
NEW = "maya.new@example.test"


@pytest.fixture(autouse=True)
def _adapters(email_adapter, throttle_adapter):
    return None


def signed_in_client(email: str = OLD) -> CsrfClient:
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


def ask(client, new_email: str = NEW):
    return client.post(
        "/api/auth/profile/email",
        {"new_email": new_email},
        content_type="application/json",
    )


def confirm(client, token: str):
    return client.post(
        "/api/auth/profile/email/confirm",
        {"token": token},
        content_type="application/json",
    )


class TestAskingForAChange:
    def test_it_is_accepted_and_nothing_has_moved_yet(self):
        client = signed_in_client()

        response = ask(client)

        assert response.status_code == 202
        assert User.objects.using(PERSONAL).get(pk=client._test_user.pk).email == OLD  # noqa: SLF001

    def test_both_messages_are_sent_to_the_right_mailboxes(self, email_adapter):
        """**Swapping them must fail.** The confirmation proves the new address; the
        warning defends the old one."""
        client = signed_in_client()

        ask(client)

        recipients = [sent.message.to for sent in email_adapter.sent]
        assert NEW in recipients
        assert OLD in recipients

    def test_the_warning_carries_no_token(self, email_adapter):
        client = signed_in_client()

        ask(client)

        token = _token_for(email_adapter)
        warning = next(sent for sent in email_adapter.sent if sent.message.to == OLD)
        assert token not in warning.message.text_body
        assert "/confirm-email" not in warning.message.text_body

    def test_a_taken_address_is_answered_identically(self):
        """**Field for field and status for status.** This is the oracle test."""
        UserFactory(email=NEW)
        taken_client = signed_in_client(email="someone@example.test")
        free_client = signed_in_client(email="other@example.test")

        taken = ask(taken_client, NEW)
        free = ask(free_client, "nobody-has-this@example.test")

        assert taken.status_code == free.status_code
        assert taken.json() == free.json()

    def test_nothing_is_sent_for_a_taken_address(self, email_adapter):
        UserFactory(email=NEW)
        client = signed_in_client()

        ask(client, NEW)

        assert email_adapter.sent == []

    def test_an_anonymous_caller_is_refused(self):
        client = CsrfClient()
        client.defaults["CONTENT_TYPE"] = "application/json"

        assert ask(client).status_code == 401

    def test_a_request_without_a_csrf_token_is_refused(self):
        signed_in_client()
        plain = Client()

        response = plain.post(
            "/api/auth/profile/email",
            {"new_email": NEW},
            content_type="application/json",
            HTTP_ORIGIN=ORIGIN,
        )

        assert response.status_code == 403

    def test_your_own_address_is_refused_without_echoing_it(self):
        client = signed_in_client()

        response = ask(client, OLD)

        assert response.status_code == 422
        assert OLD not in response.content.decode()


class TestConfirming:
    def test_it_moves_the_login(self, email_adapter):
        client = signed_in_client()
        ask(client)
        token = _token_for(email_adapter)

        response = confirm(client, token)

        assert response.status_code == 200
        assert response.json()["email"] == NEW

    def test_it_works_without_a_session(self, email_adapter):
        """**The link is opened from a mailbox**, possibly in a browser that never signed
        in. Requiring a session would make the link work only where it was requested."""
        client = signed_in_client()
        ask(client)
        token = _token_for(email_adapter)

        stranger = CsrfClient()
        stranger.defaults["CONTENT_TYPE"] = "application/json"
        stranger.get("/api/auth/csrf")

        assert confirm(stranger, token).status_code == 200

    def test_it_is_still_csrf_checked(self, email_adapter):
        """Anonymous is not unprotected: `GET /api/auth/csrf` issues the token, exactly
        as the password-reset confirmation requires."""
        client = signed_in_client()
        ask(client)
        token = _token_for(email_adapter)

        plain = Client()
        response = plain.post(
            "/api/auth/profile/email/confirm",
            {"token": token},
            content_type="application/json",
            HTTP_ORIGIN=ORIGIN,
        )

        assert response.status_code == 403

    def test_an_unknown_token_is_refused_without_saying_why(self):
        client = signed_in_client()

        response = confirm(client, "not-a-token-anyone-issued")

        assert response.status_code == 422


class TestCancelling:
    def test_it_clears_the_pending_change(self, email_adapter):
        client = signed_in_client()
        ask(client)

        response = client.delete("/api/auth/profile/email")

        assert response.status_code == 200
        assert client.get("/api/auth/me").json()["pending_email"] == ""

    def test_the_cancelled_link_no_longer_confirms(self, email_adapter):
        client = signed_in_client()
        ask(client)
        token = _token_for(email_adapter)

        client.delete("/api/auth/profile/email")

        assert confirm(client, token).status_code == 422

    def test_cancelling_with_nothing_pending_is_not_an_error(self):
        client = signed_in_client()

        assert client.delete("/api/auth/profile/email").status_code == 200

    def test_an_anonymous_caller_is_refused(self):
        client = CsrfClient()
        client.defaults["CONTENT_TYPE"] = "application/json"

        assert client.delete("/api/auth/profile/email").status_code == 401

    def test_a_request_without_a_csrf_token_is_refused(self):
        signed_in_client()
        plain = Client()

        response = plain.delete("/api/auth/profile/email", HTTP_ORIGIN=ORIGIN)

        assert response.status_code == 403


class TestResendingIsJustAskingAgain:
    def test_it_mints_a_new_link_and_kills_the_old_one(self, email_adapter):
        """**No resend endpoint exists, and none is needed.** The token is never stored,
        so a resend must mint a new link anyway, and the request endpoint already revokes
        the outstanding row."""
        client = signed_in_client()
        ask(client)
        first = _token_for(email_adapter)

        email_adapter.sent.clear()
        ask(client)
        second = _token_for(email_adapter)

        assert second != first
        assert confirm(client, first).status_code == 422
        assert confirm(client, second).status_code == 200


class TestMeReportsThePendingChange:
    def test_it_names_the_address_a_link_was_sent_to(self):
        """A boolean would leave the screen unable to say *which* address, which is what
        someone who mistyped it needs to see."""
        client = signed_in_client()
        ask(client)

        assert client.get("/api/auth/me").json()["pending_email"] == NEW

    def test_it_says_when_the_link_stops_working(self, email_adapter):
        """The screen has to tell someone whether a mail is still worth waiting for, and
        the server is what knows — a duration in the frontend would be a number that keeps
        claiming 24 hours after the constant says otherwise."""
        client = signed_in_client()
        ask(client)

        expires = client.get("/api/auth/me").json()["pending_email_expires_at"]

        assert expires != ""
        row = PendingEmailChange.objects.using(PERSONAL).get()
        assert expires.startswith(row.expires_at.isoformat()[:19])

    def test_it_is_empty_when_nothing_is_pending(self):
        client = signed_in_client()

        body = client.get("/api/auth/me").json()
        assert body["pending_email"] == ""
        assert body["pending_email_expires_at"] == ""

    def test_it_clears_once_the_change_is_confirmed(self, email_adapter):
        client = signed_in_client()
        ask(client)
        confirm(client, _token_for(email_adapter))

        body = client.get("/api/auth/me").json()
        assert body["pending_email"] == ""
        assert body["email"] == NEW


def _token_for(adapter) -> str:
    """The raw token, read out of the mail that carries it.

    **The token is not in the database** — only its digest is — so the message is the
    only place to read it from, which is also the only place a real user ever sees it.
    A test that reached into the row could not get the token at all, and one that
    reconstructed it would be testing its own arithmetic.
    """
    from django.conf import settings

    prefix = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/confirm-email?token="
    for sent in adapter.sent:
        if prefix in sent.message.text_body:
            return sent.message.text_body.split(prefix, 1)[1].split()[0]
    raise AssertionError("no confirmation mail carried a link")
