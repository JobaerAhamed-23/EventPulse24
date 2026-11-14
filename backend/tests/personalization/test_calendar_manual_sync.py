"""`POST /api/personal/calendars/{id}/sync` — the "Sync now" button (FR-50).

**What a manual sync is, and is not.** It is not a fetch: the endpoint marks the
connection due (`next_poll_at = now`) and the 60-second dispatcher claims it on its next
tick, exactly as `connect_calendar` already queues the first sync. So what these tests
pin is the *queueing*, not an import — an endpoint that fetched inline would be a second
implementation of the hourly sync, and the two would drift.

The properties that matter:

- it is **authed**, and **scoped to the session user** — another user's connection reads
  as not found, not as forbidden, and no payload names a user;
- it **marks the connection due**, and leaves a live claim alone while clearing a stale
  one — clearing a live claim would let two workers fetch one feed at once, which is the
  race `sync_claimed_at` exists to prevent;
- the **cooldown is per connection**, so a Pro account can refresh each of its calendars;
- a **non-active** connection is a 409 that names the remedy, and it does **not** spend
  the cooldown;
- the **address never comes back**, which is the standing rule for every calendar
  endpoint and is asserted on the raw body.

The client is a `CsrfClient`, because the endpoints resolve their user through
`identity`'s resolver and the resolver checks CSRF on every unsafe method (D13).
"""

from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from apps.personalization.models import CalendarConnection
from shared.constants import CALENDAR_CLAIM_TTL, CALENDAR_MANUAL_SYNC_COOLDOWN_SECONDS
from shared.db import PERSONAL
from shared.ids import uuid7
from tests.csrf import CsrfClient
from tests.personalization.factories import CalendarConnectionFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

User = get_user_model()

#: The path segment the fake address hides its secret in. The "no address in the body"
#: assertion looks for this, so a masked or fragmented address would still be caught.
SECRET_SEGMENT = "ZmFrZXNlY3JldHNlY3JldHNlY3JldHNlY3JldHNlY3JldA"


def make_user(email=None):
    if email is None:
        email = f"user-{uuid7()}@example.test"
    return User.objects.create_user(email=email, password="pw")


def signed_in(user=None):
    client = CsrfClient()
    client.force_login(user or make_user())
    return client


def post_sync(client, connection_id):
    return client.post(f"/api/personal/calendars/{connection_id}/sync")


# --- The queueing -------------------------------------------------------------------------------


def test_a_manual_sync_marks_the_connection_due_now():
    """The whole mechanism: due now, so the next tick picks it up."""
    user = make_user()
    connection = CalendarConnectionFactory(
        user_id=user.pk,
        next_poll_at=datetime(2099, 1, 1, tzinfo=UTC),
    )
    client = signed_in(user)

    before = timezone.now()
    response = post_sync(client, connection.pk)

    assert response.status_code == 202
    connection.refresh_from_db()
    assert connection.next_poll_at is not None
    assert before <= connection.next_poll_at <= timezone.now()


def test_it_answers_202_not_200():
    """**The status is the honesty.** The sync has been accepted, not performed: a 200
    would claim the import had happened by the time the response was written."""
    user = make_user()
    connection = CalendarConnectionFactory(user_id=user.pk)

    response = post_sync(signed_in(user), connection.pk)

    assert response.status_code == 202


def test_it_does_not_sync_inline():
    """No fetch happens in the request. The proof is that nothing a *sync* writes has
    moved: `last_polled_at` is what it was, because only the worker sets it."""
    user = make_user()
    connection = CalendarConnectionFactory(
        user_id=user.pk,
        last_polled_at=datetime(2026, 10, 29, 9, 0, tzinfo=UTC),
    )

    post_sync(signed_in(user), connection.pk)

    connection.refresh_from_db()
    assert connection.last_polled_at == datetime(2026, 10, 29, 9, 0, tzinfo=UTC)


def test_it_returns_the_connection_as_it_stands():
    user = make_user()
    connection = CalendarConnectionFactory(user_id=user.pk, provider="apple")

    response = post_sync(signed_in(user), connection.pk)

    body = response.json()
    assert body["id"] == str(connection.pk)
    assert body["provider"] == "apple"
    assert body["status"] == "active"


# --- The claim ----------------------------------------------------------------------------------


def test_a_live_claim_is_left_alone():
    """**The race this must not open.** A worker holding a fresh claim is fetching this
    feed right now; clearing it would let the next tick claim the same connection and
    fetch the same feed a second time, concurrently."""
    user = make_user()
    held = timezone.now()
    connection = CalendarConnectionFactory(user_id=user.pk, sync_claimed_at=held)

    post_sync(signed_in(user), connection.pk)

    connection.refresh_from_db()
    assert connection.sync_claimed_at == held


def test_a_stale_claim_is_cleared():
    """A claim older than the TTL is a worker that died. Left in place, the user's
    explicit request would wait out the rest of the TTL for a job that is never coming."""
    user = make_user()
    connection = CalendarConnectionFactory(
        user_id=user.pk,
        sync_claimed_at=timezone.now() - CALENDAR_CLAIM_TTL - timedelta(minutes=1),
    )

    post_sync(signed_in(user), connection.pk)

    connection.refresh_from_db()
    assert connection.sync_claimed_at is None


# --- The cooldown -------------------------------------------------------------------------------


def test_a_second_sync_inside_the_window_is_refused():
    user = make_user()
    connection = CalendarConnectionFactory(user_id=user.pk)
    client = signed_in(user)

    assert post_sync(client, connection.pk).status_code == 202
    second = post_sync(client, connection.pk)

    assert second.status_code == 429
    assert second.json()["details"]["retry_after_seconds"] > 0


def test_the_refusal_names_no_address():
    user = make_user()
    connection = CalendarConnectionFactory(user_id=user.pk)
    client = signed_in(user)
    post_sync(client, connection.pk)

    second = post_sync(client, connection.pk)

    assert SECRET_SEGMENT not in second.content.decode()


def test_the_window_frees_up(throttle_adapter):
    """The cooldown is a window, not a lock: when it passes, the button works again."""
    user = make_user()
    connection = CalendarConnectionFactory(user_id=user.pk)
    client = signed_in(user)
    post_sync(client, connection.pk)

    throttle_adapter.test_clock["now"] += CALENDAR_MANUAL_SYNC_COOLDOWN_SECONDS + 1

    assert post_sync(client, connection.pk).status_code == 202


def test_the_cooldown_is_per_connection_not_per_user():
    """**A Pro account holds three calendars.** A window keyed on the user would let the
    first calendar's refresh eat the second's, and the user would be told to wait for a
    calendar they had not touched."""
    user = make_user()
    first = CalendarConnectionFactory(user_id=user.pk, provider="google")
    second = CalendarConnectionFactory(user_id=user.pk, provider="apple")
    client = signed_in(user)

    assert post_sync(client, first.pk).status_code == 202
    assert post_sync(client, second.pk).status_code == 202


# --- The state ----------------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["needs_reconnect", "disconnected"])
def test_a_connection_that_is_not_active_is_refused(status):
    """A revoked credential cannot be fetched with, and a disconnected row holds none at
    all. Asking again fixes neither; reconnecting does."""
    user = make_user()
    connection = CalendarConnectionFactory(
        user_id=user.pk,
        status=status,
        credential=None if status == "disconnected" else "https://example.com/c.ics",
    )

    response = post_sync(signed_in(user), connection.pk)

    assert response.status_code == 409
    assert response.json()["code"] == "calendar_not_syncable"


def test_a_refused_state_does_not_spend_the_cooldown():
    """**The order of the two checks.** A user told to reconnect, who then reconnects and
    presses Sync now, must not be told to wait for a window they never knowingly opened."""
    user = make_user()
    connection = CalendarConnectionFactory(user_id=user.pk, status="needs_reconnect")
    client = signed_in(user)

    assert post_sync(client, connection.pk).status_code == 409

    CalendarConnection.objects.using(PERSONAL).filter(pk=connection.pk).update(status="active")
    assert post_sync(client, connection.pk).status_code == 202


# --- The scoping --------------------------------------------------------------------------------


def test_an_anonymous_request_is_refused():
    connection = CalendarConnectionFactory()

    response = Client().post(f"/api/personal/calendars/{connection.pk}/sync")

    assert response.status_code in (401, 403)


def test_another_users_connection_reads_as_not_found():
    """**Not found, not forbidden.** A 403 would confirm the id exists, so a caller could
    probe for other users' connection ids by watching which status comes back."""
    somebody_else = CalendarConnectionFactory(user_id=uuid7())

    response = post_sync(signed_in(), somebody_else.pk)

    assert response.status_code == 404


def test_another_users_connection_is_not_marked_due():
    """The refusal is not just a status — nothing was written on the way to it."""
    due = datetime(2099, 1, 1, tzinfo=UTC)
    somebody_else = CalendarConnectionFactory(user_id=uuid7(), next_poll_at=due)

    post_sync(signed_in(), somebody_else.pk)

    somebody_else.refresh_from_db()
    assert somebody_else.next_poll_at == due


def test_a_connection_that_does_not_exist_reads_as_not_found():
    response = post_sync(signed_in(), uuid7())

    assert response.status_code == 404
