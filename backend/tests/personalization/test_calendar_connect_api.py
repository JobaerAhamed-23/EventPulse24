"""The calendar-connect endpoints (FR-50, AD-18, AD-19).

The surface is five endpoints under `/api/personal/calendars`. What these tests pin is
the **shape of the contract**:

- every endpoint is **authed** — an anonymous request is refused;
- every endpoint is **scoped to the session user** — another user's connection reads as
  *not found*, not as forbidden, and no endpoint accepts a user id as input;
- **the address never comes back.** Not in full, not masked, not as a fragment — and
  the check is on the *raw response body*, so it catches a field the schema does not
  declare as well as one it does;
- the **Free cap** is a typed, calm refusal with no modal semantics in the payload;
- an invalid address gets a calm, specific message that **never echoes the address**;
- the first sync is **enqueued, not run inline**;
- a failing request **writes nothing to the log** that carries the address.

The client is a `CsrfClient`, because the endpoints resolve their user through
`identity`'s resolver and the resolver checks CSRF on every unsafe method (D13).
"""

import json
import logging
from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.personalization.models import CalendarConnection, PersonalEvent
from shared.db import PERSONAL
from shared.ids import uuid7
from tests.csrf import CsrfClient
from tests.personalization.factories import (
    FAKE_CALENDAR_URL,
    CalendarConnectionFactory,
    PersonalEventFactory,
)

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

User = get_user_model()

#: A second, distinct calendar. It must be a different address or the "already
#: connected" refusal would fire before the cap.
SECOND_URL = "https://example.com/other/calendar/basic.ics"

#: The path segment providers put the secret in. Every "the address is not in the body"
#: assertion checks for this, because a masked or fragmented address would still leak
#: it.
SECRET_SEGMENT = "ZmFrZXNlY3JldHNlY3JldHNlY3JldHNlY3JldHNlY3JldA"


def make_user(email=None):
    """A real user with a real pk — the session resolves to this one.

    The email is unique per call, because a test may need two users (the caller and
    somebody else), and the email column is unique.
    """
    if email is None:
        email = f"user-{uuid7()}@example.test"
    return User.objects.create_user(email=email, password="pw")


def signed_in(user=None):
    """A client whose session identifies `user`."""
    client = CsrfClient()
    client.force_login(user or make_user())
    return client


def connect_body(address=FAKE_CALENDAR_URL, provider="google", label=""):
    return json.dumps({"provider": provider, "address": address, "display_label": label})


JSON = "application/json"


def post_connect(client, address=FAKE_CALENDAR_URL, provider="google", label=""):
    return client.post(
        "/api/personal/calendars",
        data=connect_body(address, provider, label),
        content_type=JSON,
    )


# --- The list -----------------------------------------------------------------------------------


def test_the_list_is_empty_for_a_user_with_no_connections():
    client = signed_in()

    response = client.get("/api/personal/calendars")

    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_the_list_returns_the_users_connections():
    user = make_user()
    connection = CalendarConnectionFactory(user_id=user.pk, provider="apple")
    client = signed_in(user)

    response = client.get("/api/personal/calendars")

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == str(connection.pk)
    assert items[0]["provider"] == "apple"
    assert items[0]["status"] == "active"


def test_the_list_carries_the_sync_state():
    """Onboarding step 1 shows the import without leaving the flow (FR-3), so the sync
    state has to be on the wire."""
    user = make_user()
    CalendarConnectionFactory(
        user_id=user.pk,
        last_polled_at=datetime(2026, 10, 29, 9, 0, tzinfo=UTC),
        next_poll_at=datetime(2026, 10, 29, 10, 0, tzinfo=UTC),
        # A *fresh* claim: the worker holds it right now.
        sync_claimed_at=datetime.now(UTC),
        last_error_kind="revoked",
    )
    client = signed_in(user)

    response = client.get("/api/personal/calendars")

    item = response.json()["items"][0]
    assert item["last_synced_at"].startswith("2026-10-29T09:00")
    assert item["next_sync_at"].startswith("2026-10-29T10:00")
    assert item["sync_in_progress"] is True
    assert item["last_error_kind"] == "revoked"


def test_the_list_does_not_list_another_users_connections():
    user = make_user()
    CalendarConnectionFactory(user_id=make_user().pk)
    client = signed_in(user)

    response = client.get("/api/personal/calendars")

    assert response.json() == {"items": []}


def test_the_list_requires_a_session():
    client = Client()

    response = client.get("/api/personal/calendars")

    assert response.status_code == 401


# --- The address never comes back ----------------------------------------------------------------


def test_the_list_never_contains_the_address():
    user = make_user()
    CalendarConnectionFactory(user_id=user.pk, credential=FAKE_CALENDAR_URL)
    client = signed_in(user)

    response = client.get("/api/personal/calendars")

    body = response.content.decode()
    assert FAKE_CALENDAR_URL not in body
    assert SECRET_SEGMENT not in body
    assert "calendar.google.com" not in body


def test_the_connect_response_never_contains_the_address():
    client = signed_in()

    response = post_connect(client)

    assert response.status_code == 201
    body = response.content.decode()
    assert FAKE_CALENDAR_URL not in body
    assert SECRET_SEGMENT not in body
    assert "calendar.google.com" not in body


def test_no_endpoint_in_the_router_returns_the_address():
    """Every endpoint in this router, one after the other, and not one body carries it.

    This is the acceptance criterion stated as a sweep rather than as three examples:
    a new endpoint added later is covered by the same assertion.
    """
    user = make_user()
    client = signed_in(user)

    created = post_connect(client)
    assert created.status_code == 201
    connection_id = created.json()["id"]

    bodies = [
        client.get("/api/personal/calendars").content,
        client.get(f"/api/personal/calendars/{connection_id}").content,
    ]
    # The failing paths too: a refusal must not echo the address either.
    bodies.append(
        client.post(
            "/api/personal/calendars",
            data=connect_body("http://example.com/insecure.ics"),
            content_type=JSON,
        ).content
    )
    bodies.append(
        client.post(
            f"/api/personal/calendars/{connection_id}/reconnect",
            data=json.dumps({"address": FAKE_CALENDAR_URL}),
            content_type=JSON,
        ).content
    )

    for body in bodies:
        text = body.decode()
        assert SECRET_SEGMENT not in text
        assert "calendar.google.com" not in text


def test_the_connect_response_has_no_address_field():
    """The guarantee is structural: the shape cannot carry the address."""
    client = signed_in()

    response = post_connect(client)

    assert "address" not in response.json()
    assert "credential" not in response.json()
    assert "fingerprint" not in response.json()


# --- Connect -----------------------------------------------------------------------------------


def test_connect_stores_the_connection():
    user = make_user()
    client = signed_in(user)

    response = post_connect(client, label="Work")

    assert response.status_code == 201
    body = response.json()
    assert body["provider"] == "google"
    assert body["status"] == "active"
    assert body["display_label"] == "Work"
    assert CalendarConnection.objects.using(PERSONAL).filter(user_id=user.pk).count() == 1


def test_connect_stores_the_address_encrypted():
    """The address is the credential, so the column holds ciphertext."""
    from django.db import connections

    user = make_user()
    client = signed_in(user)

    post_connect(client)

    with connections[PERSONAL].cursor() as cursor:
        cursor.execute(
            "SELECT credential FROM personal.personalization_calendarconnection",
        )
        raw = cursor.fetchone()[0]
    assert raw.startswith("EPENC1.")
    assert FAKE_CALENDAR_URL not in raw


def test_connect_enqueues_the_first_sync_rather_than_running_it():
    """AD-11: no long work in a request. The connection is *due*, not synced."""
    user = make_user()
    client = signed_in(user)

    response = post_connect(client)

    connection = CalendarConnection.objects.using(PERSONAL).get(user_id=user.pk)
    # Due immediately: the dispatcher picks it up within a tick.
    assert connection.next_poll_at is not None
    # …and not yet synced: nothing was fetched.
    assert connection.last_polled_at is None
    assert response.json()["last_synced_at"] is None


def test_connect_accepts_every_known_provider():
    """The provider is a label, not a branch: all three are first-class (FR-3)."""
    for provider, address in (
        ("google", FAKE_CALENDAR_URL),
        ("apple", "https://p01-calendars.icloud.com/published/2/abc/basic.ics"),
        ("outlook", SECOND_URL),
    ):
        # A user each: the Free tier is one calendar, so a second connect for the same
        # user would be the cap rather than the provider.
        client = signed_in(make_user())
        response = post_connect(client, address=address, provider=provider)
        assert response.status_code == 201, provider
        assert response.json()["provider"] == provider


def test_connect_refuses_an_unknown_provider():
    client = signed_in()

    response = post_connect(client, provider="yahoo")

    assert response.status_code == 422


def test_connect_requires_a_session():
    client = Client()

    response = client.post(
        "/api/personal/calendars",
        data=connect_body(),
        content_type=JSON,
    )

    assert response.status_code == 401


def test_connect_refuses_a_request_without_a_csrf_token():
    """D13: the check is explicit, and it applies to the unsafe methods."""
    client = Client()
    client.force_login(make_user())

    response = client.post(
        "/api/personal/calendars",
        data=connect_body(),
        content_type=JSON,
    )

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"


# --- The Free cap -------------------------------------------------------------------------------


def test_the_cap_refuses_a_second_connection():
    user = make_user()
    client = signed_in(user)
    assert post_connect(client).status_code == 201

    response = post_connect(client, address=SECOND_URL)

    assert response.status_code == 409
    assert response.json()["code"] == "calendar_cap_reached"


def test_the_cap_message_is_the_approved_copy():
    """Calm, no urgency, no exclamation mark — the project's voice."""
    client = signed_in()
    post_connect(client)

    response = post_connect(client, address=SECOND_URL)

    message = response.json()["message"]
    assert message == "You've connected the calendars your plan allows."
    assert "!" not in message
    assert "LIMITED" not in message.upper()


def test_the_cap_payload_has_no_modal_semantics():
    """The approved copy is an *inline* prompt with a quiet link, not a modal.

    So the payload carries a code, a message and plain data — and no `modal`, no
    `title`, no `actions`, no `dismissable`, no `cta`. The key set is pinned exactly, so
    a future edit that grows a modal-shaped field fails here.
    """
    client = signed_in()
    post_connect(client)

    response = post_connect(client, address=SECOND_URL)

    body = response.json()
    assert set(body) == {"code", "message", "details"}
    details = body["details"]
    assert set(details) == {"cap", "upgrade_hint"}
    assert details["cap"] == 1
    assert "modal" not in str(details).lower()


def test_the_cap_does_not_store_the_second_connection():
    user = make_user()
    client = signed_in(user)
    post_connect(client)

    post_connect(client, address=SECOND_URL)

    assert CalendarConnection.objects.using(PERSONAL).filter(user_id=user.pk).count() == 1


# --- The invalid addresses ----------------------------------------------------------------------


def test_a_bad_scheme_is_refused():
    client = signed_in()

    response = post_connect(client, address="http://example.com/basic.ics")

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_calendar_credential"


def test_a_cleartext_scheme_is_refused():
    """The secret ICS URL *is* the credential; fetching it in cleartext puts it on the
    wire on every poll, forever."""
    client = signed_in()

    response = post_connect(client, address="http://example.com/basic.ics")

    assert response.status_code == 422


def test_a_webcal_scheme_is_accepted():
    """`webcal://` is the iCloud spelling."""
    client = signed_in()

    response = post_connect(client, address="webcal://p01-calendars.icloud.com/published/2/x")

    assert response.status_code == 201


def test_an_address_with_no_host_is_refused():
    client = signed_in()

    response = post_connect(client, address="https:///basic.ics")

    assert response.status_code == 422


def test_an_address_with_credentials_in_it_is_refused():
    client = signed_in()

    response = post_connect(client, address="https://user:pass@example.com/basic.ics")

    assert response.status_code == 422


def test_a_loopback_address_is_refused_by_the_ssrf_policy():
    """The pre-flight: the user hears about it while they are still typing, rather than
    at the first poll, with a stored connection they cannot use."""
    client = signed_in()

    response = post_connect(client, address="https://127.0.0.1/feed.ics")

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_calendar_credential"


def test_a_link_local_address_is_refused():
    """`169.254.169.254` is the cloud metadata address."""
    client = signed_in()

    response = post_connect(client, address="https://169.254.169.254/latest/meta-data")

    assert response.status_code == 422


def test_a_private_address_is_refused():
    client = signed_in()

    response = post_connect(client, address="https://192.168.1.10/feed.ics")

    assert response.status_code == 422


def test_an_ipv6_loopback_address_is_refused():
    client = signed_in()

    response = post_connect(client, address="https://[::1]/feed.ics")

    assert response.status_code == 422


def test_an_already_connected_address_is_refused():
    user = make_user()
    client = signed_in(user)
    assert post_connect(client).status_code == 201

    response = post_connect(client)

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_calendar_credential"


def test_a_refused_address_is_not_stored():
    user = make_user()
    client = signed_in(user)

    post_connect(client, address="https://127.0.0.1/feed.ics")

    assert not CalendarConnection.objects.using(PERSONAL).filter(user_id=user.pk).exists()


def test_a_refusal_never_echoes_the_address():
    """The message must not carry the secret — not in the message and not in `details`."""
    client = signed_in()

    for address in (
        "http://example.com/basic.ics",
        "https://127.0.0.1/feed.ics",
        "https://user:pass@example.com/basic.ics",
        "https://calendar.google.com/calendar/ical/ZmFrZXNlY3JldA/basic.ics",
    ):
        response = post_connect(client, address=address)
        body = response.content.decode()
        assert address not in body, address
        assert SECRET_SEGMENT not in body, address


# --- The log ------------------------------------------------------------------------------------


def test_a_failing_request_writes_the_address_to_no_log(caplog):
    """AD-13: the address is the credential, so it never reaches a log.

    The check is on a **failing** request, because that is where a log line is most
    likely: an unhandled exception's traceback carries the arguments, and a validation
    error's `input` carries the submitted value.
    """
    address = "https://calendar.google.com/calendar/ical/ZmFrZXNlY3JldHNlY3JldA/basic.ics"
    client = signed_in()

    with caplog.at_level(logging.DEBUG):
        response = post_connect(client, address=address, provider="yahoo")

    assert response.status_code == 422
    logged = "\n".join(
        f"{record.getMessage()} {record.args!r} {record.exc_info!r}" for record in caplog.records
    )
    assert address not in logged
    assert SECRET_SEGMENT not in logged
    assert "calendar.google.com" not in logged


def test_a_successful_request_writes_the_address_to_no_log(caplog):
    address = "https://calendar.google.com/calendar/ical/ZmFrZXNlY3JldHNlY3JldA/basic.ics"
    client = signed_in()

    with caplog.at_level(logging.DEBUG):
        response = post_connect(client, address=address)

    assert response.status_code == 201
    logged = "\n".join(
        f"{record.getMessage()} {record.args!r} {record.exc_info!r}" for record in caplog.records
    )
    assert address not in logged
    assert SECRET_SEGMENT not in logged


# --- One connection ------------------------------------------------------------------------------


def test_get_one_returns_the_connection():
    user = make_user()
    connection = CalendarConnectionFactory(user_id=user.pk)
    client = signed_in(user)

    response = client.get(f"/api/personal/calendars/{connection.pk}")

    assert response.status_code == 200
    assert response.json()["id"] == str(connection.pk)


def test_get_one_of_another_users_connection_is_404_not_403():
    """A 403 would confirm that the record exists, so it could be probed for."""
    other = CalendarConnectionFactory(user_id=make_user().pk)
    client = signed_in()

    response = client.get(f"/api/personal/calendars/{other.pk}")

    assert response.status_code == 404
    assert response.json()["code"] == "calendar_connection_not_found"


def test_get_one_of_an_unknown_connection_is_404():
    client = signed_in()

    response = client.get(f"/api/personal/calendars/{uuid7()}")

    assert response.status_code == 404


def test_get_one_requires_a_session():
    client = Client()

    response = client.get("/api/personal/calendars/00000000-0000-7000-8000-000000000000")

    assert response.status_code == 401


# --- Reconnect ----------------------------------------------------------------------------------


def test_reconnect_brings_a_revoked_connection_back():
    user = make_user()
    connection = CalendarConnectionFactory(
        user_id=user.pk,
        status=CalendarConnection.Status.NEEDS_RECONNECT,
        last_error_kind="revoked",
    )
    client = signed_in(user)

    response = client.post(
        f"/api/personal/calendars/{connection.pk}/reconnect",
        data=json.dumps({"address": SECOND_URL}),
        content_type=JSON,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "active"
    assert response.json()["last_error_kind"] is None
    connection.refresh_from_db()
    assert connection.status == CalendarConnection.Status.ACTIVE


def test_reconnect_keeps_the_imported_events():
    """The provider revoked the *address*, not the events (D6)."""
    user = make_user()
    connection = CalendarConnectionFactory(
        user_id=user.pk,
        status=CalendarConnection.Status.NEEDS_RECONNECT,
    )
    event = PersonalEventFactory(
        user_id=user.pk,
        source=PersonalEvent.Source.CALENDAR_IMPORT,
        calendar_connection_id=connection.pk,
        source_uid="uid-1",
    )
    client = signed_in(user)

    client.post(
        f"/api/personal/calendars/{connection.pk}/reconnect",
        data=json.dumps({"address": SECOND_URL}),
        content_type=JSON,
    )

    assert PersonalEvent.objects.using(PERSONAL).filter(pk=event.pk).exists()


def test_reconnect_of_another_users_connection_is_404():
    other = CalendarConnectionFactory(
        user_id=make_user().pk,
        status=CalendarConnection.Status.NEEDS_RECONNECT,
    )
    client = signed_in()

    response = client.post(
        f"/api/personal/calendars/{other.pk}/reconnect",
        data=json.dumps({"address": SECOND_URL}),
        content_type=JSON,
    )

    assert response.status_code == 404


def test_reconnect_of_an_active_connection_is_refused():
    """There is nothing to reconnect, and silently replacing a working credential would
    change which calendar the user is looking at without them asking."""
    user = make_user()
    connection = CalendarConnectionFactory(user_id=user.pk)
    client = signed_in(user)

    response = client.post(
        f"/api/personal/calendars/{connection.pk}/reconnect",
        data=json.dumps({"address": SECOND_URL}),
        content_type=JSON,
    )

    assert response.status_code == 422


def test_reconnect_requires_a_session():
    client = Client()

    response = client.post(
        "/api/personal/calendars/00000000-0000-7000-8000-000000000000/reconnect",
        data=json.dumps({"address": SECOND_URL}),
        content_type=JSON,
    )

    assert response.status_code == 401


def test_reconnect_refuses_a_request_without_a_csrf_token():
    user = make_user()
    connection = CalendarConnectionFactory(
        user_id=user.pk,
        status=CalendarConnection.Status.NEEDS_RECONNECT,
    )
    client = Client()
    client.force_login(user)

    response = client.post(
        f"/api/personal/calendars/{connection.pk}/reconnect",
        data=json.dumps({"address": SECOND_URL}),
        content_type=JSON,
    )

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"


def test_reconnect_does_not_store_the_new_address_in_plaintext():
    from django.db import connections

    user = make_user()
    connection = CalendarConnectionFactory(
        user_id=user.pk,
        status=CalendarConnection.Status.NEEDS_RECONNECT,
    )
    client = signed_in(user)

    client.post(
        f"/api/personal/calendars/{connection.pk}/reconnect",
        data=json.dumps({"address": SECOND_URL}),
        content_type=JSON,
    )

    with connections[PERSONAL].cursor() as cursor:
        cursor.execute(
            "SELECT credential FROM personal.personalization_calendarconnection WHERE id = %s",
            [connection.pk],
        )
        raw = cursor.fetchone()[0]
    assert raw.startswith("EPENC1.")
    assert SECOND_URL not in raw


# --- Disconnect ---------------------------------------------------------------------------------


def test_disconnect_destroys_the_credential():
    user = make_user()
    connection = CalendarConnectionFactory(user_id=user.pk)
    client = signed_in(user)

    response = client.delete(f"/api/personal/calendars/{connection.pk}")

    assert response.status_code == 204
    connection.refresh_from_db()
    assert connection.status == CalendarConnection.Status.DISCONNECTED
    assert connection.credential is None


def test_disconnect_purges_that_connections_events():
    user = make_user()
    connection = CalendarConnectionFactory(user_id=user.pk)
    PersonalEventFactory(
        user_id=user.pk,
        source=PersonalEvent.Source.CALENDAR_IMPORT,
        calendar_connection_id=connection.pk,
        source_uid="uid-1",
    )
    client = signed_in(user)

    client.delete(f"/api/personal/calendars/{connection.pk}")

    assert (
        not PersonalEvent.objects.using(PERSONAL)
        .filter(calendar_connection_id=connection.pk)
        .exists()
    )


def test_disconnect_leaves_the_users_own_events_alone():
    user = make_user()
    connection = CalendarConnectionFactory(user_id=user.pk)
    own = PersonalEventFactory(user_id=user.pk)
    client = signed_in(user)

    client.delete(f"/api/personal/calendars/{connection.pk}")

    assert PersonalEvent.objects.using(PERSONAL).filter(pk=own.pk).exists()


def test_disconnect_leaves_another_connections_events_alone():
    """The purge is scoped by `calendar_connection_id`, so it is exact by construction."""
    user = make_user()
    first = CalendarConnectionFactory(user_id=user.pk)
    second = CalendarConnectionFactory(user_id=user.pk)
    imported = PersonalEventFactory(
        user_id=user.pk,
        source=PersonalEvent.Source.CALENDAR_IMPORT,
        calendar_connection_id=second.pk,
        source_uid="uid-2",
    )
    client = signed_in(user)

    client.delete(f"/api/personal/calendars/{first.pk}")

    assert PersonalEvent.objects.using(PERSONAL).filter(pk=imported.pk).exists()


def test_disconnect_of_another_users_connection_is_404():
    other = CalendarConnectionFactory(user_id=make_user().pk)
    client = signed_in()

    response = client.delete(f"/api/personal/calendars/{other.pk}")

    assert response.status_code == 404


def test_disconnect_requires_a_session():
    client = Client()

    response = client.delete("/api/personal/calendars/00000000-0000-7000-8000-000000000000")

    assert response.status_code == 401


def test_disconnect_refuses_a_request_without_a_csrf_token():
    user = make_user()
    connection = CalendarConnectionFactory(user_id=user.pk)
    client = Client()
    client.force_login(user)

    response = client.delete(f"/api/personal/calendars/{connection.pk}")

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"


def test_a_disconnected_connection_still_reads_as_found():
    """The user gave it up; they did not delete it, and the sweep has not run yet."""
    user = make_user()
    connection = CalendarConnectionFactory(
        user_id=user.pk,
        status=CalendarConnection.Status.DISCONNECTED,
        credential=None,
    )
    client = signed_in(user)

    response = client.get(f"/api/personal/calendars/{connection.pk}")

    assert response.status_code == 200
    assert response.json()["status"] == "disconnected"


# --- The safe-methods guarantee -------------------------------------------------------------------


def test_the_reads_never_write():
    """A read that mutates is a write behind a GET — and a GET is never CSRF-checked."""
    user = make_user()
    connection = CalendarConnectionFactory(user_id=user.pk)
    client = signed_in(user)

    client.get("/api/personal/calendars")
    client.get(f"/api/personal/calendars/{connection.pk}")

    connection.refresh_from_db()
    assert connection.status == CalendarConnection.Status.ACTIVE
    assert connection.credential is not None
    assert connection.sync_claimed_at is None
    assert connection.next_poll_at is None


def test_the_reads_create_no_rows():
    user = make_user()
    client = signed_in(user)

    client.get("/api/personal/calendars")

    assert not CalendarConnection.objects.using(PERSONAL).filter(user_id=user.pk).exists()


# --- The claim -----------------------------------------------------------------------------------


def test_a_stale_claim_is_not_a_sync_in_progress():
    """A claim older than the TTL is a lost job — a worker died holding it. Showing it
    as "syncing" would be a lie the user can see: the spinner would never stop."""
    user = make_user()
    CalendarConnectionFactory(
        user_id=user.pk,
        sync_claimed_at=datetime.now(UTC) - timedelta(hours=1),
    )
    client = signed_in(user)

    response = client.get("/api/personal/calendars")

    assert response.json()["items"][0]["sync_in_progress"] is False
