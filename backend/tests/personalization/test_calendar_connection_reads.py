"""The calendar-connection reads (FR-50, AD-18).

The API layer may not import `apps.personalization.models` (the `models-personalization`
import contract), so these reads are the published way in. What they own is the
**projection**: what a connection looks like when it is shown to the user.

The properties pinned here:

- the projection carries **no field for the credential and none for the fingerprint** —
  the guarantee that a response body cannot leak the secret address is structural,
  not careful;
- the user's own connections only — another user's are not in the result set;
- another user's connection reads as **not found**, not as forbidden;
- `sync_in_progress` is true only while the claim is **fresh** — a stale claim is a lost
  job, and a spinner that never stops is a lie the user can see;
- a `disconnected` connection is still the user's own row, so it reads as found.
"""

from datetime import UTC, datetime, timedelta

import pytest

from apps.personalization.models import CalendarConnection
from apps.personalization.services.calendar_connections import (
    get_calendar_connection,
    list_calendar_connections,
)
from domain.errors import CalendarConnectionNotFoundError
from shared.constants import CALENDAR_CLAIM_TTL
from shared.db import PERSONAL
from shared.ids import uuid7
from tests.personalization.factories import (
    FAKE_CALENDAR_URL,
    CalendarConnectionFactory,
)

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)


# --- The list -----------------------------------------------------------------------------------


def test_the_list_is_empty_for_a_user_with_no_connections():
    assert list_calendar_connections(user_id=uuid7(), now=NOW) == []


def test_the_list_returns_the_users_own_connections():
    user_id = uuid7()
    connection = CalendarConnectionFactory(user_id=user_id)

    views = list_calendar_connections(user_id=user_id, now=NOW)

    assert len(views) == 1
    assert views[0].id == connection.pk
    assert views[0].provider == "google"
    assert views[0].status == "active"
    assert views[0].display_label == "Work"


def test_the_list_excludes_another_users_connections():
    user_id = uuid7()
    CalendarConnectionFactory(user_id=uuid7())

    assert list_calendar_connections(user_id=user_id, now=NOW) == []


def test_the_list_is_ordered_oldest_first():
    """The list does not reshuffle under the user as connections are added."""
    user_id = uuid7()
    first = CalendarConnectionFactory(user_id=user_id, display_label="First")
    second = CalendarConnectionFactory(user_id=user_id, display_label="Second")

    views = list_calendar_connections(user_id=user_id, now=NOW)

    assert [view.id for view in views] == [first.pk, second.pk]


def test_the_projection_has_no_field_for_the_credential():
    """The guarantee is structural: the projection cannot carry the address.

    A field that is absent cannot leak. This is the difference between a rule that is
    *careful* and one that is *structural* — and only the second one survives the
    next person who adds a field.
    """
    user_id = uuid7()
    CalendarConnectionFactory(user_id=user_id, credential=FAKE_CALENDAR_URL)

    view = list_calendar_connections(user_id=user_id, now=NOW)[0]

    fields = set(type(view).__dataclass_fields__)
    assert "credential" not in fields
    assert "address" not in fields
    assert "credential_fingerprint" not in fields
    assert "fingerprint" not in fields
    # And nothing that *is* a field carries the secret.
    rendered = repr(view)
    assert FAKE_CALENDAR_URL not in rendered
    assert "calendar.google.com" not in rendered


def test_the_projection_carries_the_sync_state():
    user_id = uuid7()
    CalendarConnectionFactory(
        user_id=user_id,
        last_polled_at=datetime(2026, 10, 29, 9, 0, tzinfo=UTC),
        next_poll_at=datetime(2026, 10, 29, 10, 0, tzinfo=UTC),
        # A claim inside the TTL: the worker holds it right now.
        sync_claimed_at=NOW - timedelta(minutes=5),
        last_error_kind="revoked",
    )

    view = list_calendar_connections(user_id=user_id, now=NOW)[0]

    assert view.last_synced_at == datetime(2026, 10, 29, 9, 0, tzinfo=UTC)
    assert view.next_sync_at == datetime(2026, 10, 29, 10, 0, tzinfo=UTC)
    assert view.sync_in_progress is True
    assert view.last_error_kind == "revoked"


def test_an_unclaimed_connection_is_not_syncing():
    user_id = uuid7()
    CalendarConnectionFactory(user_id=user_id)

    view = list_calendar_connections(user_id=user_id, now=NOW)[0]

    assert view.sync_in_progress is False


def test_a_stale_claim_is_not_a_sync_in_progress():
    """A claim older than the TTL is a lost job — a worker died holding it.

    Showing it as "syncing" would be a lie the user can see: the spinner would never
    stop, because nothing will ever release the claim.
    """
    user_id = uuid7()
    CalendarConnectionFactory(
        user_id=user_id,
        sync_claimed_at=NOW - CALENDAR_CLAIM_TTL - timedelta(seconds=1),
    )

    view = list_calendar_connections(user_id=user_id, now=NOW)[0]

    assert view.sync_in_progress is False


def test_a_claim_at_the_ttl_boundary_is_still_in_progress():
    """One second inside the window is still a live claim."""
    user_id = uuid7()
    CalendarConnectionFactory(
        user_id=user_id,
        sync_claimed_at=NOW - CALENDAR_CLAIM_TTL + timedelta(seconds=1),
    )

    view = list_calendar_connections(user_id=user_id, now=NOW)[0]

    assert view.sync_in_progress is True


def test_the_last_error_kind_is_a_slug_not_a_message():
    """An `httpx` exception message contains the full request URL, which *is* the
    credential (AD-13). The column holds a slug, and the projection keeps that."""
    user_id = uuid7()
    CalendarConnectionFactory(user_id=user_id, last_error_kind="revoked")

    view = list_calendar_connections(user_id=user_id, now=NOW)[0]

    assert view.last_error_kind == "revoked"
    assert "http" not in view.last_error_kind
    assert "/" not in view.last_error_kind


# --- One connection -----------------------------------------------------------------------------


def test_get_one_returns_the_users_own_connection():
    user_id = uuid7()
    connection = CalendarConnectionFactory(user_id=user_id)

    view = get_calendar_connection(user_id=user_id, connection_id=connection.pk, now=NOW)

    assert view.id == connection.pk


def test_get_one_of_another_users_connection_is_not_found():
    """Not forbidden. A 403 would confirm that the record exists, so it could be probed
    for."""
    connection = CalendarConnectionFactory(user_id=uuid7())

    with pytest.raises(CalendarConnectionNotFoundError):
        get_calendar_connection(user_id=uuid7(), connection_id=connection.pk, now=NOW)


def test_get_one_of_an_unknown_connection_is_not_found():
    with pytest.raises(CalendarConnectionNotFoundError):
        get_calendar_connection(user_id=uuid7(), connection_id=uuid7(), now=NOW)


def test_a_disconnected_connection_still_reads_as_found():
    """The user gave it up; they did not delete it, and the retention sweep has not run
    yet. It is still their own row."""
    user_id = uuid7()
    connection = CalendarConnectionFactory(
        user_id=user_id,
        status=CalendarConnection.Status.DISCONNECTED,
        credential=None,
    )

    view = get_calendar_connection(user_id=user_id, connection_id=connection.pk, now=NOW)

    assert view.status == "disconnected"


def test_the_reads_never_write():
    """A read that mutates is a write behind a GET — and a GET is never CSRF-checked, so
    a write behind one is a cross-site write."""
    user_id = uuid7()
    connection = CalendarConnectionFactory(user_id=user_id)

    list_calendar_connections(user_id=user_id, now=NOW)
    get_calendar_connection(user_id=user_id, connection_id=connection.pk, now=NOW)

    connection.refresh_from_db()
    assert connection.status == CalendarConnection.Status.ACTIVE
    assert connection.credential is not None
    assert connection.sync_claimed_at is None
    assert connection.next_poll_at is None
    assert connection.last_polled_at is None


def test_the_reads_create_no_rows():
    user_id = uuid7()

    list_calendar_connections(user_id=user_id, now=NOW)

    assert not CalendarConnection.objects.using(PERSONAL).filter(user_id=user_id).exists()
