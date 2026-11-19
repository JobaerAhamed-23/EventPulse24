"""The profile endpoint: `PUT /api/auth/profile` (FR-52, AD-5, AD-13, D13).

This is the HTTP edge of the one command that writes the account's name. What is
proved here is the edge's own behaviour, and each rule is pinned by an assertion:

- **The CSRF check is first.** A request without a token is refused with 403 — before
  the resolver, so it is refused as a cross-site write rather than as an
  authentication problem.
- **An anonymous caller gets 401.** The resolver raises it.
- **The write goes through the command.** The endpoint's module is a *surface file* and
  `tests/architecture/test_no_direct_writes.py` scans it for ORM writes; here the
  command's own effects are observed — the row changed, and the audit row is there.
- **The audit row carries no name** (AD-13). The name is PII.
- **A refused name writes nothing.** A line break or a control character is a 422, and
  the old name survives.

**The CSRF refusals use a plain `Client`, not `CsrfClient`.** That is the point of the
split: the refusal is provable because the ordinary client still refuses.
"""

import json

import pytest
from django.test import Client

from apps.identity.models import IdentityAuditEntry, User
from shared.db import PERSONAL
from tests.csrf import ORIGIN, CsrfClient, csrf_token
from tests.identity.factories import UserFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

PASSWORD = "correct-horse-battery"


def signed_in_client() -> CsrfClient:
    """A client with a session, established the way a browser establishes one."""
    client = CsrfClient()
    client.defaults["CONTENT_TYPE"] = "application/json"
    user = UserFactory(email="maya@example.test", plain_password=PASSWORD)
    client.post(
        "/api/auth/signin",
        {"email": "maya@example.test", "password": PASSWORD},
        content_type="application/json",
    )
    client._test_user = user  # noqa: SLF001 — the test's own handle on the account
    return client


def put_profile(client, name: str):
    """`PUT /api/auth/profile` with a name."""
    return client.put(
        "/api/auth/profile",
        {"name": name},
        content_type="application/json",
    )


def stored_name(user) -> str:
    return User.objects.using(PERSONAL).get(pk=user.pk).name


def name_audit_rows():
    """The audit rows the **name** write left.

    Filtering by action rather than counting every row matters: signing in writes a row
    of its own (`sign_in`), so a bare count would be counting the session as well as the
    name — and a test that counts rows it did not create proves less than it looks like
    it does.
    """
    return IdentityAuditEntry.objects.using(PERSONAL).filter(action="user_name_changed")


# ---------------------------------------------------------------------------
# The write
# ---------------------------------------------------------------------------


def test_put_profile_saves_the_name_and_returns_the_updated_profile():
    """The write lands, and the answer is the caller's whole profile."""
    client = signed_in_client()

    response = put_profile(client, "Maya Ahmed")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "id": str(client._test_user.pk),  # noqa: SLF001
        "email": "maya@example.test",
        "name": "Maya Ahmed",
        # The answer is the caller's **whole** profile, so a client can update what it
        # knows without a second `me` call — which is why a new profile field lands here
        # too, and why this dict is exact rather than a subset check.
        "avatar_url": "",
    }
    assert stored_name(client._test_user) == "Maya Ahmed"  # noqa: SLF001


def test_put_profile_reads_back_through_me():
    """The saved name is on `me`, which is the read the frontend already makes."""
    client = signed_in_client()

    put_profile(client, "Maya Ahmed")
    me = client.get("/api/auth/me")

    assert me.status_code == 200
    assert me.json()["name"] == "Maya Ahmed"


def test_put_profile_trims_and_collapses_the_name():
    """The command's rules reach the edge unchanged: trimmed, collapsed."""
    client = signed_in_client()

    response = put_profile(client, "  Maya   Ahmed  ")

    assert response.status_code == 200
    assert response.json()["name"] == "Maya Ahmed"
    assert stored_name(client._test_user) == "Maya Ahmed"  # noqa: SLF001


def test_put_profile_stores_an_empty_name_as_no_name_set():
    """Clearing your name is a thing a person does; it is not a refusal."""
    client = signed_in_client()
    put_profile(client, "Maya Ahmed")

    response = put_profile(client, "")

    assert response.status_code == 200
    assert response.json()["name"] == ""
    assert stored_name(client._test_user) == ""  # noqa: SLF001


def test_put_profile_stores_a_whitespace_only_name_as_no_name_set():
    client = signed_in_client()

    response = put_profile(client, "   \t  ")

    assert response.status_code == 200
    assert response.json()["name"] == ""
    assert stored_name(client._test_user) == ""  # noqa: SLF001


def test_put_profile_truncates_an_over_long_name():
    """A name of 121 characters is still a name, so it is truncated and not refused."""
    client = signed_in_client()

    response = put_profile(client, "a" * 121)

    assert response.status_code == 200
    assert response.json()["name"] == "a" * 120
    assert stored_name(client._test_user) == "a" * 120  # noqa: SLF001


# ---------------------------------------------------------------------------
# The refusals
# ---------------------------------------------------------------------------


def test_put_profile_refuses_a_name_carrying_a_newline_with_a_422():
    """A line break would break the one-line layout the name is rendered in."""
    client = signed_in_client()

    response = put_profile(client, "Maya\nAhmed")

    assert response.status_code == 422
    payload = response.json()
    assert payload["code"] == "invalid_input"
    assert payload["message"]
    assert payload["details"]["errors"][0]["loc"] == ["name"]


def test_put_profile_refuses_a_name_carrying_a_control_character_with_a_422():
    client = signed_in_client()

    response = put_profile(client, "Maya\x00Ahmed")

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_input"


def test_a_refused_name_writes_nothing():
    """The refusal happens before the write, so the row keeps its old name."""
    client = signed_in_client()
    put_profile(client, "Maya Ahmed")

    response = put_profile(client, "Maya\nAhmed")

    assert response.status_code == 422
    assert stored_name(client._test_user) == "Maya Ahmed"  # noqa: SLF001


def test_a_refused_name_does_not_echo_the_name_back():
    """AD-13: the name is PII. The refusal says what was wrong, not what was sent."""
    client = signed_in_client()

    response = put_profile(client, "Maya\nAhmed")

    assert response.status_code == 422
    assert "Maya" not in response.content.decode()


def test_put_profile_refuses_an_anonymous_caller_with_a_401():
    """The resolver's refusal, and it is the project's shape.

    **The caller sends a valid CSRF token here.** The check comes first, so an anonymous
    caller with *no* token is refused with 403 — as a cross-site write, which is what it
    is. To reach the resolver at all the request has to get past the CSRF check, so the
    token is fetched the way a browser fetches it. Both refusals are correct and both
    are worth proving: the 403 says "this write was not authorised", and the 401 says
    "who are you".
    """
    client = Client()
    client.defaults["CONTENT_TYPE"] = "application/json"
    token = csrf_token(client)

    response = client.put(
        "/api/auth/profile",
        {"name": "Maya Ahmed"},
        content_type="application/json",
        headers={"origin": ORIGIN, "x-csrftoken": token},
    )

    assert response.status_code == 401
    payload = response.json()
    assert payload["code"] == "not_authenticated"
    assert payload["message"] == "Please sign in to continue."


def test_put_profile_refuses_a_request_without_a_csrf_token_with_a_403():
    """The CSRF check is explicit here — this router has no router-level `auth=`."""
    client = Client()
    client.defaults["CONTENT_TYPE"] = "application/json"

    response = client.put(
        "/api/auth/profile",
        {"name": "Maya Ahmed"},
        content_type="application/json",
    )

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"


def test_the_csrf_check_runs_before_the_resolver():
    """A request with no token is refused as a cross-site write, not as a 401.

    The order matters. If the resolver ran first, an anonymous caller would get a 401
    and a signed-in caller without a token a 403 — and a cross-site write against a
    signed-in caller would be answered only *after* the resolver had already resolved
    that user. The check is first, so **the refusal does not depend on the session at
    all**: an anonymous caller with no token and a signed-in caller with no token are
    refused *identically* — same status, same bytes.

    The comparison is made here, between two real requests, because the claim is about
    the two of them agreeing. A single request cannot prove it: an anonymous caller
    refused with a 403 proves only that *this* caller got a 403.
    """
    signed_in = signed_in_client()

    # A plain client that keeps the session cookie but sends no token.
    signed_in_plain = Client()
    signed_in_plain.cookies = signed_in.cookies
    signed_in_plain.defaults["CONTENT_TYPE"] = "application/json"

    # An anonymous client with no session and no token.
    anonymous = Client()
    anonymous.defaults["CONTENT_TYPE"] = "application/json"

    body = {"name": "Maya Ahmed"}
    signed_in_response = signed_in_plain.put(
        "/api/auth/profile", body, content_type="application/json"
    )
    anonymous_response = anonymous.put("/api/auth/profile", body, content_type="application/json")

    assert signed_in_response.status_code == 403
    assert anonymous_response.status_code == 403
    # **The same bytes**, not merely the same status: a body that named the session
    # state would be the oracle this ordering exists to prevent.
    assert signed_in_response.content == anonymous_response.content
    # And nothing was written, because the check refused before any work.
    assert stored_name(signed_in._test_user) == ""  # noqa: SLF001


def test_the_csrf_check_does_not_run_before_the_body_is_validated():
    """**The one thing that happens before the CSRF check is the body's validation.**

    Ninja parses and validates the request body before the handler is called, so a body
    that is not a `ProfileIn` is refused with a 422 `invalid_request` before the token
    is ever looked at. The endpoint's comment says the check comes first, and this test
    pins the exact boundary of that claim — so the comment cannot quietly grow into a
    stronger one than the code supports.

    **This is not a hole.** The write cannot happen either way. A request with a bad
    token *and* a bad body is answered 422, and the body was never going to be written.
    """
    client = Client()
    client.defaults["CONTENT_TYPE"] = "application/json"

    response = client.put("/api/auth/profile", {}, content_type="application/json")

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"


def test_a_signed_in_caller_without_a_csrf_token_is_refused_with_a_403():
    """The session does not exempt an unsafe request from the check."""
    client = signed_in_client()

    # A plain client that keeps the session cookie but sends no token.
    plain = Client()
    plain.cookies = client.cookies
    plain.defaults["CONTENT_TYPE"] = "application/json"

    response = plain.put(
        "/api/auth/profile",
        {"name": "Maya Ahmed"},
        content_type="application/json",
    )

    assert response.status_code == 403
    assert stored_name(client._test_user) == ""  # noqa: SLF001


def test_a_wrong_csrf_token_is_refused_with_a_403():
    client = signed_in_client()

    response = client.put(
        "/api/auth/profile",
        {"name": "Maya Ahmed"},
        content_type="application/json",
        headers={"origin": ORIGIN, "x-csrftoken": "not-the-token"},
    )

    assert response.status_code == 403
    assert stored_name(client._test_user) == ""  # noqa: SLF001


def test_put_profile_refuses_a_body_with_no_name_with_a_422():
    """The name is the whole of the write, so a body without one is malformed.

    **The code is asserted, not just the status.** There are two 422s here, and they
    mean different things: `invalid_request` is Ninja refusing the *shape* of the
    body before the handler runs, and `invalid_input` is the command refusing the
    *value*. A test that asserted only the status would pass even if the command's
    refusal path were entirely broken — it would be satisfied by the shape refusal
    alone.
    """
    client = signed_in_client()

    response = client.put("/api/auth/profile", {}, content_type="application/json")

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"


def test_a_command_refusal_is_a_different_422_from_a_malformed_body():
    """The two 422s are distinguishable by their code, and the frontend branches on it.

    A malformed body is `invalid_request` — the request never reached the command. A
    refused name is `invalid_input` — the command refused it, and the message is the
    one the person has to read.
    """
    client = signed_in_client()

    malformed = client.put("/api/auth/profile", {}, content_type="application/json")
    refused = put_profile(client, "Maya\nAhmed")

    assert malformed.status_code == 422
    assert malformed.json()["code"] == "invalid_request"
    assert refused.status_code == 422
    assert refused.json()["code"] == "invalid_input"


# ---------------------------------------------------------------------------
# The audit row
# ---------------------------------------------------------------------------


def test_put_profile_writes_an_audit_row():
    """AD-5: the write is audited, in the same transaction as the mutation."""
    client = signed_in_client()

    put_profile(client, "Maya Ahmed")

    row = name_audit_rows().get()
    assert row.action == "user_name_changed"
    assert row.target_type == "User"
    assert row.target_id == client._test_user.pk  # noqa: SLF001


def test_the_audit_row_carries_no_name():
    """AD-13: the name is PII. The action names the account; the row is one lookup away."""
    client = signed_in_client()

    put_profile(client, "Maya Ahmed")

    row = name_audit_rows().get()
    assert "Maya" not in str(row.details)
    assert "Ahmed" not in str(row.details)
    assert row.details == {}


def test_a_refused_name_writes_no_audit_row():
    """A refused write leaves no trace: no mutation, no audit row."""
    client = signed_in_client()

    put_profile(client, "Maya\nAhmed")

    assert name_audit_rows().count() == 0


# ---------------------------------------------------------------------------
# `me` — the name on the read the frontend already makes
# ---------------------------------------------------------------------------


def test_me_returns_an_empty_name_when_none_is_set():
    """`""`, not `null`, and not a 404 — one "no name set" state."""
    user = UserFactory(email="maya@example.test", plain_password=PASSWORD)
    client = CsrfClient()
    client.defaults["CONTENT_TYPE"] = "application/json"
    client.post(
        "/api/auth/signin",
        {"email": "maya@example.test", "password": PASSWORD},
        content_type="application/json",
    )

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["name"] == ""
    assert stored_name(user) == ""


def test_me_returns_the_stored_name():
    UserFactory(email="maya@example.test", plain_password=PASSWORD, name="Maya Ahmed")
    client = CsrfClient()
    client.defaults["CONTENT_TYPE"] = "application/json"
    client.post(
        "/api/auth/signin",
        {"email": "maya@example.test", "password": PASSWORD},
        content_type="application/json",
    )

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["name"] == "Maya Ahmed"


def test_me_still_carries_no_password_field():
    """The rule `CurrentUserOut` has always had: no catch-all, so nothing rides along."""
    user = UserFactory(email="maya@example.test", plain_password=PASSWORD)
    client = CsrfClient()
    client.defaults["CONTENT_TYPE"] = "application/json"
    client.post(
        "/api/auth/signin",
        {"email": "maya@example.test", "password": PASSWORD},
        content_type="application/json",
    )

    response = client.get("/api/auth/me")

    assert user.password not in response.content.decode()
    assert set(response.json()) == {
        "id",
        "email",
        "name",
        "avatar_url",
        "pending_email",
        "pending_email_expires_at",
        "onboarding",
    }


# ---------------------------------------------------------------------------
# The contract
# ---------------------------------------------------------------------------


def test_the_endpoint_is_declared_put_in_the_openapi_schema():
    """The verb is one, and it is in the contract — not just in the code.

    A `PATCH` here would put two shapes for one operation into the generated client,
    and the frontend has no `PATCH` support to speak of.

    **The live schema is read, not the committed file.** The committed `openapi.json` is
    what the frontend client was generated from, and asserting on it proves the two
    agree — which `tests/api/test_contract.py` already proves. What it does **not**
    prove is that the *endpoint* is a `PUT`: a stale committed file would satisfy the
    assertion just as well. Reading the live schema closes that hole, and it is what
    makes this test fail when the route's verb is changed and the client not yet
    regenerated.
    """
    from ninja.responses import NinjaJSONEncoder

    from config.api import api

    live = json.loads(json.dumps(api.get_openapi_schema(), cls=NinjaJSONEncoder))

    assert "put" in live["paths"]["/api/auth/profile"]
    assert "patch" not in live["paths"]["/api/auth/profile"]


def test_the_committed_contract_declares_the_put():
    """The committed contract says `put` too — the two agree, and the frontend is
    generated from the committed one."""
    import json
    from pathlib import Path

    schema = json.loads(
        (Path(__file__).parents[3] / "frontend" / "lib" / "api" / "openapi.json").read_text()
    )

    assert "put" in schema["paths"]["/api/auth/profile"]
    assert "patch" not in schema["paths"]["/api/auth/profile"]
