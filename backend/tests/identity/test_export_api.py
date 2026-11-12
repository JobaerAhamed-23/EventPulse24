"""The export endpoints (FR-52): ask for it signed in, fetch it with the emailed link.

**Two auth models, and the tests exist to pin the difference.**

`POST /api/exports` is session-authed and takes no user id from the body, like every other
personal surface (AD-12).

`GET /api/exports/{id}/{fmt}` takes **no session at all**, because the link is followed from
a mail client days later and possibly on another device. The token is the credential — so
the tests that matter here are the ones that try to aim a valid token somewhere else.

**And the tier tests.** `POST` succeeds for an account with no subscription, because Article
20 is a right rather than a feature. That is a deliberate departure from the PRD's pricing
bullet, settled at this item's checkpoint, and a test is what stops it being "fixed" back.
"""

import json
from datetime import UTC, datetime

import pytest
from django.test import Client
from django.utils import timezone

from apps.identity.models import DataExport, DataExportStatus, Subscription
from apps.identity.services.data_export import (
    build_export,
    claim_next_export,
    download_token,
    request_export,
)
from shared.actor import Actor
from shared.db import PERSONAL
from tests.csrf import CsrfClient
from tests.identity.factories import UserFactory
from tests.personalization.factories import PersonalEventFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

EXPORTS_URL = "/api/exports"
NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)


def signed_in_client(user=None) -> CsrfClient:
    client = CsrfClient()
    client.force_login(user or UserFactory())
    return client


def ready_export_for(user):
    """A built, downloadable export for `user`."""
    PersonalEventFactory(user_id=user.pk, name="Dentist")
    view = request_export(user_id=user.pk, actor=Actor.user(user.pk), now=timezone.now())
    claim_next_export(now=timezone.now())
    return build_export(export_id=view.id, now=timezone.now())


# ── Requesting ─────────────────────────────────────────────────────────────────────


def test_a_free_account_may_request_an_export():
    """**The checkpoint decision, pinned.** No `Subscription` row exists, and the request
    is accepted — data portability is a right, not a tier feature."""
    user = UserFactory()
    client = signed_in_client(user)

    response = client.post(EXPORTS_URL, {}, content_type="application/json")

    assert response.status_code == 202, response.content
    assert Subscription.objects.using(PERSONAL).filter(user_id=user.pk).count() == 0
    assert DataExport.objects.using(PERSONAL).filter(user_id=user.pk).count() == 1


def test_the_response_says_when_the_user_should_have_it_by():
    """FR-52's 24 hours, stated to the caller rather than left in a constant."""
    client = signed_in_client()

    body = json.loads(client.post(EXPORTS_URL, {}, content_type="application/json").content)

    assert body["status"] == DataExportStatus.PENDING
    assert body["due_by"] > body["requested_at"]


def test_asking_twice_returns_the_same_request():
    client = signed_in_client()

    first = json.loads(client.post(EXPORTS_URL, {}, content_type="application/json").content)
    second = json.loads(client.post(EXPORTS_URL, {}, content_type="application/json").content)

    assert first["id"] == second["id"]


def test_an_anonymous_caller_cannot_request_an_export():
    """There is no user to export, and no payload may name one (AD-12)."""
    response = Client().post(EXPORTS_URL, {}, content_type="application/json")

    assert response.status_code in (401, 403)


def test_the_status_of_another_users_export_is_not_readable():
    owner = UserFactory()
    built = ready_export_for(owner)

    response = signed_in_client().get(f"{EXPORTS_URL}/{built.id}")

    assert response.status_code == 404


# ── Downloading ────────────────────────────────────────────────────────────────────


def download_url(export_id, fmt, token) -> str:
    return f"{EXPORTS_URL}/{export_id}/{fmt}?token={token}"


def test_the_emailed_link_works_with_no_session_at_all():
    """**The property this endpoint exists for.** The link is followed from a mail client,
    which carries no session; requiring one would deny a user data they are owed."""
    user = UserFactory()
    built = ready_export_for(user)
    token = download_token(export_id=built.id, user_id=user.pk, fmt="json")

    response = Client().get(download_url(built.id, "json", token))

    assert response.status_code == 200, response.content
    assert b"Dentist" in response.content


def test_the_json_download_is_an_attachment_and_is_never_cached():
    """The URL carries a credential: a shared cache holding the response, or a `Referer`
    carrying the token onward, would both leak it."""
    user = UserFactory()
    built = ready_export_for(user)
    token = download_token(export_id=built.id, user_id=user.pk, fmt="json")

    response = Client().get(download_url(built.id, "json", token))

    assert response["Content-Type"] == "application/json"
    assert "attachment" in response["Content-Disposition"]
    assert "no-store" in response["Cache-Control"]
    assert response["Referrer-Policy"] == "no-referrer"


def test_the_ics_download_is_served_as_a_calendar():
    user = UserFactory()
    built = ready_export_for(user)
    token = download_token(export_id=built.id, user_id=user.pk, fmt="ics")

    response = Client().get(download_url(built.id, "ics", token))

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/calendar")
    assert response.content.startswith(b"BEGIN:VCALENDAR")


def test_a_link_with_no_token_is_refused():
    user = UserFactory()
    built = ready_export_for(user)

    response = Client().get(f"{EXPORTS_URL}/{built.id}/json")

    assert response.status_code == 404


def test_another_users_token_does_not_open_this_export():
    """**The acceptance criterion's cross-user case, over HTTP.**"""
    owner = UserFactory()
    intruder = UserFactory()
    built = ready_export_for(owner)
    forged = download_token(export_id=built.id, user_id=intruder.pk, fmt="json")

    response = Client().get(download_url(built.id, "json", forged))

    assert response.status_code == 404


def test_being_signed_in_as_someone_else_does_not_help():
    """The session is not the credential here, so holding one for another account changes
    nothing — it neither grants nor is required."""
    owner = UserFactory()
    built = ready_export_for(owner)
    forged = download_token(export_id=built.id, user_id=UserFactory().pk, fmt="json")

    response = signed_in_client().get(download_url(built.id, "json", forged))

    assert response.status_code == 404


def test_the_format_in_the_url_cannot_disagree_with_the_token():
    user = UserFactory()
    built = ready_export_for(user)
    json_token = download_token(export_id=built.id, user_id=user.pk, fmt="json")

    response = Client().get(download_url(built.id, "ics", json_token))

    assert response.status_code == 404


def test_an_unknown_format_is_refused():
    user = UserFactory()
    built = ready_export_for(user)
    token = download_token(export_id=built.id, user_id=user.pk, fmt="json")

    response = Client().get(download_url(built.id, "csv", token))

    assert response.status_code == 404


def test_an_export_that_is_not_ready_cannot_be_downloaded():
    """A pending row has no payload, and a link minted early must not serve an empty file
    as though it were the user's data."""
    user = UserFactory()
    view = request_export(user_id=user.pk, actor=Actor.user(user.pk), now=timezone.now())
    token = download_token(export_id=view.id, user_id=user.pk, fmt="json")

    response = Client().get(download_url(view.id, "json", token))

    assert response.status_code == 404


def test_an_expired_export_stops_serving():
    user = UserFactory()
    built = ready_export_for(user)
    token = download_token(export_id=built.id, user_id=user.pk, fmt="json")
    DataExport.objects.using(PERSONAL).filter(id=built.id).update(
        status=DataExportStatus.EXPIRED, json_body="", ics_body=""
    )

    response = Client().get(download_url(built.id, "json", token))

    assert response.status_code == 404


def test_the_status_endpoint_carries_no_download_link():
    """The links live in the email. A session-authed response carrying one would be a
    second way to reach a file that is supposed to require the token."""
    user = UserFactory()
    built = ready_export_for(user)

    body = json.loads(signed_in_client(user).get(f"{EXPORTS_URL}/{built.id}").content)

    assert "token" not in json.dumps(body)
    assert set(body) == {
        "id",
        "status",
        "requested_at",
        "completed_at",
        "expires_at",
        "due_by",
    }
