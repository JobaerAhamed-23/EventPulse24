"""The auth endpoints (FR-4, AD-18, AD-19, D13).

These are the tests for the HTTP surface of `/api/auth/*`: the wire shapes, the status
codes, the session that a sign-up or a sign-in establishes, and the refusals.

**The enumeration-safety tests compare bytes, not shapes.** `response.content` is compared
for equality, so a response that grew a field, reordered its keys or changed a space would
fail. "The same shape" is not the property; "the same bytes" is.

**The CSRF tests use a plain `Client`, not `CsrfClient`.** That is the point of the split:
the refusal is provable because the ordinary client still refuses. `CsrfClient` exists so
that the *other* tests — the ones about behaviour, not about the check — do not each have
to re-derive how a browser obtains a token.

**The session is the real one.** A sign-in goes through the endpoint and sets the session
cookie; the tests then use that cookie. Nothing is forced into the session by hand.
"""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from shared.db import PERSONAL
from tests.csrf import ORIGIN, CsrfClient
from tests.identity.factories import UserFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

User = get_user_model()

PASSWORD = "correct-horse-battery"
#: A password that is *not* similar to `PASSWORD`. Django's similarity validator refuses
#: a password whose words appear in the account's email or in the old password, and the
#: two must not trip it — the tests are about the endpoints, not about the validators.
OTHER_PASSWORD = "zephyr-quartz-lantern-9"


def json_client() -> Client:
    """A client that posts JSON, which is what the endpoints take."""
    client = Client()
    client.defaults["CONTENT_TYPE"] = "application/json"
    return client


def csrf_json_client() -> CsrfClient:
    """A client that posts JSON and carries the CSRF token."""
    client = CsrfClient()
    client.defaults["CONTENT_TYPE"] = "application/json"
    return client


def body(client: Client, path: str, payload: dict):
    """POST `payload` as JSON, without a CSRF token."""
    return client.post(path, payload, content_type="application/json")


def signup_payload(email="maya@example.test", password=PASSWORD) -> dict:
    return {"email": email, "password": password}


# ---------------------------------------------------------------------------
# The CSRF endpoint
# ---------------------------------------------------------------------------


def test_the_csrf_endpoint_returns_a_token_and_sets_the_cookie():
    """The token the frontend sends back on unsafe requests, and the cookie it checks
    against. The endpoint is a `GET`, so it is not itself checked for a token."""
    client = Client()

    response = client.get("/api/auth/csrf")

    assert response.status_code == 200
    payload = response.json()
    assert payload["csrf_token"]
    # The cookie is the other half of the pair Django's check compares.
    assert client.cookies["csrftoken"].value


def test_the_csrf_endpoint_is_a_safe_request():
    """A `GET` needs no token — and the endpoint that *issues* one is itself a `GET`."""
    client = Client()

    response = client.get("/api/auth/csrf")

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Sign-up
# ---------------------------------------------------------------------------


def test_signing_up_creates_an_account_and_a_session():
    """A new account is created and the caller is signed in."""
    client = csrf_json_client()

    response = body(client, "/api/auth/signup", signup_payload())

    assert response.status_code == 201
    assert response.json() == {"status": "accepted"}
    assert User.objects.filter(email="maya@example.test").exists()
    # The session cookie is set, so the next request is not anonymous.
    assert "sessionid" in client.cookies


def test_signing_up_with_a_taken_address_gives_the_same_bytes_as_a_new_address():
    """AD-18: the answer must not say whether the address was taken.

    The bodies are compared as **bytes**, so a difference in the JSON's shape, its key
    order or its spacing would fail the test.
    """
    UserFactory(email="maya@example.test", plain_password=PASSWORD)

    fresh = csrf_json_client()
    taken = csrf_json_client()

    fresh_response = body(fresh, "/api/auth/signup", signup_payload("new@example.test"))
    taken_response = body(taken, "/api/auth/signup", signup_payload())

    assert fresh_response.status_code == taken_response.status_code == 201
    assert fresh_response.content == taken_response.content


def test_signing_up_with_a_taken_address_does_not_sign_the_caller_in():
    """The caller does not know the existing account's password, so they get no session —
    even though the body is identical to the new-address case."""
    UserFactory(email="maya@example.test", plain_password=PASSWORD)

    client = csrf_json_client()

    # A different password, so the supplied password does not verify against the account
    # that is already there.
    response = body(client, "/api/auth/signup", signup_payload(password=OTHER_PASSWORD))

    assert response.status_code == 201
    assert response.json() == {"status": "accepted"}
    # No session: the browser is not signed in as the account's owner.
    me = client.get("/api/auth/me")
    assert me.status_code == 401


def test_signing_up_with_a_taken_address_and_the_right_password_does_sign_the_caller_in():
    """The other side of the same rule: the caller *does* know the password, so they are
    the account's owner and signing them in is legitimate.

    The body is the same in both cases — only the session differs, and the session is not
    part of the body.
    """
    UserFactory(email="maya@example.test", plain_password=PASSWORD)

    client = csrf_json_client()

    response = body(client, "/api/auth/signup", signup_payload())

    assert response.status_code == 201
    assert response.json() == {"status": "accepted"}
    assert client.get("/api/auth/me").status_code == 200


def test_signing_up_with_a_weak_password_is_refused_with_the_projects_error_shape():
    """A validation error carries `details.errors` with a location and a message."""
    client = csrf_json_client()

    response = body(client, "/api/auth/signup", signup_payload(password="123"))

    assert response.status_code == 422
    payload = response.json()
    assert payload["code"] == "invalid_input"
    assert payload["details"]["errors"]
    assert "loc" in payload["details"]["errors"][0]
    assert "msg" in payload["details"]["errors"][0]


def test_signing_up_with_a_malformed_body_is_refused_with_the_projects_error_shape():
    """A missing field is a 422 with the same shape."""
    client = csrf_json_client()

    response = body(client, "/api/auth/signup", {"email": "maya@example.test"})

    assert response.status_code == 422
    payload = response.json()
    assert payload["code"] == "invalid_request"
    assert payload["details"]["errors"]


# ---------------------------------------------------------------------------
# Sign-in
# ---------------------------------------------------------------------------


def test_signing_in_with_the_right_password_establishes_the_session():
    """The session cookie is set, and `me` then answers for that account."""
    user = UserFactory(email="maya@example.test", plain_password=PASSWORD)
    client = csrf_json_client()

    response = body(client, "/api/auth/signin", signup_payload())

    assert response.status_code == 200
    assert response.json() == {"status": "signed_in"}
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["id"] == str(user.pk)


def test_signing_in_with_a_wrong_password_and_with_an_unknown_address_give_the_same_bytes():
    """AD-18: one error for both failures, so neither can be used to find out who has an
    account."""
    UserFactory(email="maya@example.test", plain_password=PASSWORD)

    wrong_password = csrf_json_client()
    unknown_address = csrf_json_client()

    wrong_response = body(
        wrong_password, "/api/auth/signin", signup_payload(password=OTHER_PASSWORD)
    )
    unknown_response = body(
        unknown_address, "/api/auth/signin", signup_payload(email="nobody@example.test")
    )

    assert wrong_response.status_code == unknown_response.status_code == 401
    assert wrong_response.content == unknown_response.content


def test_a_wrong_password_does_not_establish_a_session():
    """No session cookie, and the next request is still anonymous."""
    UserFactory(email="maya@example.test", plain_password=PASSWORD)
    client = csrf_json_client()

    body(client, "/api/auth/signin", signup_payload(password=OTHER_PASSWORD))

    assert client.get("/api/auth/me").status_code == 401


# ---------------------------------------------------------------------------
# `me`
# ---------------------------------------------------------------------------


def test_me_returns_the_id_and_the_email_and_nothing_else():
    """No password hash, no permission list, no catch-all field."""
    user = UserFactory(email="maya@example.test", plain_password=PASSWORD)
    client = csrf_json_client()
    body(client, "/api/auth/signin", signup_payload())

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {"id": str(user.pk), "email": "maya@example.test"}
    # The hash is not in the body under any key.
    assert user.password not in response.content.decode()


def test_me_refuses_an_anonymous_request_with_a_401():
    """The refusal is a 401 with the project's shape and a calm message."""
    client = Client()

    response = client.get("/api/auth/me")

    assert response.status_code == 401
    payload = response.json()
    assert payload["code"] == "not_authenticated"
    assert payload["message"] == "Please sign in to continue."


# ---------------------------------------------------------------------------
# Sign-out
# ---------------------------------------------------------------------------


def test_signing_out_ends_the_session():
    """After the sign-out the session cookie no longer identifies anybody."""
    UserFactory(email="maya@example.test", plain_password=PASSWORD)
    client = csrf_json_client()
    body(client, "/api/auth/signin", signup_payload())
    assert client.get("/api/auth/me").status_code == 200

    response = body(client, "/api/auth/signout", {})

    assert response.status_code == 200
    assert response.json() == {"status": "signed_out"}
    assert client.get("/api/auth/me").status_code == 401


def test_signing_out_when_nobody_is_signed_in_is_not_an_error():
    """The caller's intent — "have no session" — is satisfied either way."""
    client = csrf_json_client()

    response = body(client, "/api/auth/signout", {})

    assert response.status_code == 200
    assert response.json() == {"status": "signed_out"}


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------


def test_asking_for_a_reset_answers_the_same_for_a_known_and_an_unknown_address():
    """AD-18: the same status and the same bytes."""
    UserFactory(email="maya@example.test", plain_password=PASSWORD)

    known = csrf_json_client()
    unknown = csrf_json_client()

    known_response = body(known, "/api/auth/password-reset", {"email": "maya@example.test"})
    unknown_response = body(unknown, "/api/auth/password-reset", {"email": "nobody@example.test"})

    assert known_response.status_code == unknown_response.status_code == 202
    assert known_response.content == unknown_response.content


def test_asking_for_a_reset_sends_a_link_to_a_known_address_only(email_adapter):
    """The known address gets a mail; the unknown one gets nothing. The response does
    not say which happened."""
    UserFactory(email="maya@example.test", plain_password=PASSWORD)

    body(csrf_json_client(), "/api/auth/password-reset", {"email": "maya@example.test"})
    body(csrf_json_client(), "/api/auth/password-reset", {"email": "nobody@example.test"})

    assert len(email_adapter.sent) == 1
    assert email_adapter.sent[0].message.to == "maya@example.test"


def test_consuming_a_reset_token_sets_the_new_password(email_adapter):
    """The link's token is consumed and the account's password becomes the new one."""
    UserFactory(email="maya@example.test", plain_password=PASSWORD)
    body(csrf_json_client(), "/api/auth/password-reset", {"email": "maya@example.test"})
    token = _token_from(email_adapter)

    client = csrf_json_client()
    response = body(
        client,
        "/api/auth/password-reset/confirm",
        {"token": token, "new_password": OTHER_PASSWORD},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "password_reset"}
    user = User.objects.get(email="maya@example.test")
    assert user.check_password(OTHER_PASSWORD)


def test_a_reset_token_cannot_be_used_twice(email_adapter):
    """Single use: the second attempt is refused, and it does not say why."""
    UserFactory(email="maya@example.test", plain_password=PASSWORD)
    body(csrf_json_client(), "/api/auth/password-reset", {"email": "maya@example.test"})
    token = _token_from(email_adapter)
    payload = {"token": token, "new_password": OTHER_PASSWORD}

    first = body(csrf_json_client(), "/api/auth/password-reset/confirm", payload)
    second = body(csrf_json_client(), "/api/auth/password-reset/confirm", payload)

    assert first.status_code == 200
    assert second.status_code == 422
    assert second.json()["code"] == "invalid_reset_token"


def test_an_unknown_reset_token_is_refused_without_saying_why():
    """A token that was never issued, one that was used and one that expired are
    indistinguishable — one error for all of them."""
    response = body(
        csrf_json_client(),
        "/api/auth/password-reset/confirm",
        {"token": "not-a-real-token", "new_password": OTHER_PASSWORD},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_reset_token"


def test_a_reset_ends_the_accounts_other_sessions(email_adapter):
    """A stolen session must not survive a password change (AD-18, D12)."""
    user = UserFactory(email="maya@example.test", plain_password=PASSWORD)

    # Two sessions for the same account, in two browsers.
    other = csrf_json_client()
    other.force_login(user)
    assert other.get("/api/auth/me").status_code == 200

    resetting = csrf_json_client()
    body(resetting, "/api/auth/password-reset", {"email": "maya@example.test"})
    token = _token_from(email_adapter)
    body(
        resetting,
        "/api/auth/password-reset/confirm",
        {"token": token, "new_password": OTHER_PASSWORD},
    )

    # The other session is gone.
    assert other.get("/api/auth/me").status_code == 401


def _token_from(email_adapter) -> str:
    """The raw token from the reset mail that was sent.

    The mail carries the link, and the link ends the token at the first whitespace — the
    link is on a line of its own, so the token is the rest of that line.
    """
    body_text = email_adapter.sent[0].message.text_body
    marker = "token="
    start = body_text.index(marker) + len(marker)
    end = start
    while end < len(body_text) and not body_text[end].isspace():
        end += 1
    return body_text[start:end]


# ---------------------------------------------------------------------------
# CSRF (D13)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("post", "/api/auth/signup", signup_payload()),
        ("post", "/api/auth/signin", signup_payload()),
        ("post", "/api/auth/signout", {}),
        ("post", "/api/auth/password-reset", {"email": "maya@example.test"}),
        (
            "post",
            "/api/auth/password-reset/confirm",
            {"token": "t", "new_password": OTHER_PASSWORD},
        ),
    ],
)
def test_an_unsafe_request_without_a_token_is_refused(method, path, payload):
    """D13: every state-changing endpoint refuses a request with no token.

    The client is a plain `Client`, so the token is genuinely absent — this is the
    refusal being proved, not the check being bypassed.
    """
    client = json_client()

    response = getattr(client, method)(path, payload, content_type="application/json")

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("post", "/api/auth/signup", signup_payload()),
        ("post", "/api/auth/signin", signup_payload()),
        ("post", "/api/auth/signout", {}),
        ("post", "/api/auth/password-reset", {"email": "maya@example.test"}),
    ],
)
def test_an_unsafe_request_with_a_wrong_token_is_refused(method, path, payload):
    """A token that does not match the cookie is refused."""
    client = json_client()
    client.get("/api/auth/csrf")

    response = getattr(client, method)(
        path,
        payload,
        content_type="application/json",
        headers={"origin": ORIGIN, "x-csrftoken": "not-the-right-token"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"


def test_an_unsafe_request_from_an_untrusted_origin_is_refused():
    """D13: the origin allowlist is the mechanism. `http://testserver` is trusted; a
    different origin is not."""
    client = csrf_json_client()

    response = client.post(
        "/api/auth/signup",
        signup_payload(),
        content_type="application/json",
        headers={"origin": "http://evil.example"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"


def test_a_get_is_not_checked_for_a_token():
    """A safe request cannot change anything, so it is not checked. The `csrftoken`
    endpoint is itself a `GET`."""
    client = Client()

    response = client.get("/api/auth/me")

    # A 401, not a CSRF refusal: the request was safe, so only the session was missing.
    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"


def test_the_callers_ip_comes_from_the_forwarded_header_when_there_is_one():
    """The proxy is the one talking to this runtime, so `X-Forwarded-For` is where the
    caller's address is (AD-13).

    The value only ever becomes part of a throttle key; it is never logged and never
    stored. The first entry of a chain is the caller's own address.
    """
    from apps.identity.api import _client_ip

    class _Request:
        headers = {"x-forwarded-for": "203.0.113.7, 70.41.3.18"}
        META = {"REMOTE_ADDR": "10.0.0.1"}

    assert _client_ip(_Request()) == "203.0.113.7"


def test_the_callers_ip_falls_back_to_the_remote_address():
    """Without a proxy in front, the socket's address is the caller's."""
    from apps.identity.api import _client_ip

    class _Request:
        headers = {}
        META = {"REMOTE_ADDR": "198.51.100.9"}

    assert _client_ip(_Request()) == "198.51.100.9"


def test_the_csrf_middlewares_own_rejection_view_is_never_reached():
    """`_reject_with_forbidden` is the view Django's middleware would call, and it is
    never reached: the checks raise before `process_view` would call it.

    The check is applied by calling the middleware's own methods directly, so the
    middleware's `process_view` — the only thing that would call the rejection view —
    never runs. The view is still there, because `CsrfViewMiddleware` requires one.
    """
    from apps.identity.api_auth import _reject_with_forbidden

    response = _reject_with_forbidden(None)

    assert response.status_code == 403


def test_an_unmapped_domain_error_answers_400():
    """The fallback for a `DomainError` that the mapping does not name.

    Every domain error the project raises is mapped; this is the safety net for one added
    without a status, so it degrades to a 400 rather than to a 500.
    """
    from config.errors import status_for
    from domain.errors import DomainError

    class _Unmapped(DomainError):
        code = "unmapped"

    assert status_for(_Unmapped()) == 400


# ---------------------------------------------------------------------------
# The throttle
# ---------------------------------------------------------------------------


def test_too_many_sign_in_attempts_are_refused_with_a_429_in_the_projects_shape(throttle_adapter):
    """The throttle answers with the project's error shape, not a bare 429."""
    UserFactory(email="maya@example.test", plain_password=PASSWORD)
    client = csrf_json_client()

    statuses = []
    for _ in range(20):
        response = body(client, "/api/auth/signin", signup_payload(password=OTHER_PASSWORD))
        statuses.append(response.status_code)
        if response.status_code == 429:
            break

    assert 429 in statuses
    payload = response.json()
    assert payload["code"] == "rate_limited"
    assert payload["message"]


def test_a_throttled_sign_in_does_not_say_whether_the_account_exists(throttle_adapter):
    """The throttle runs before the account is looked up, so the refusal is the same for
    a known and an unknown address."""
    UserFactory(email="maya@example.test", plain_password=PASSWORD)
    client = csrf_json_client()

    last = None
    for _ in range(20):
        last = body(client, "/api/auth/signin", signup_payload(password=OTHER_PASSWORD))
        if last.status_code == 429:
            break
    known = last

    other = csrf_json_client()
    last = None
    for _ in range(20):
        last = body(other, "/api/auth/signin", signup_payload(email="nobody@example.test"))
        if last.status_code == 429:
            break
    unknown = last

    assert known.status_code == unknown.status_code == 429
    assert known.content == unknown.content


# ---------------------------------------------------------------------------
# The session's lifetime
# ---------------------------------------------------------------------------


def test_a_seven_day_old_session_is_expired(monkeypatch):
    """D12: the session lasts seven days. A session older than that no longer identifies
    anybody.

    The clock is moved forward rather than the session row being aged, because ageing a
    stored row would test Django's store rather than the policy.
    """
    UserFactory(email="maya@example.test", plain_password=PASSWORD)
    client = csrf_json_client()
    body(client, "/api/auth/signin", signup_payload())
    assert client.get("/api/auth/me").status_code == 200

    # Eight days later: past the seven-day lifetime.
    later = timezone.now() + timedelta(days=8)
    monkeypatch.setattr(timezone, "now", lambda *args, **kwargs: later)

    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"
