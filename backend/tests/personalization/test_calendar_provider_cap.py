"""The calendar-provider cap, chosen by tier (FR-50).

FR-50: *"Free tier: 1 connected provider. Pro tier: up to 3."* The cap is **chosen by
entitlement**, so the two tiers are one rule with two values rather than two rules — and
the choice is made by the one published read (`is_pro`), never by a second mapping of
"who is Pro" that could disagree with it.

What these tests pin:

- a **Free user cannot connect a second** provider, and the refusal is the same calm
  payload the shipped `CalendarProviderCapReached` carries;
- a **Pro user connects a second and a third**, and is refused a fourth;
- the cap in the refusal payload **is the tier's cap** — 1 for Free, 3 for Pro — so the
  frontend can say what the account would get rather than a number that does not change;
- the **reuse path** — a `needs_reconnect` row that is flipped back to `active` — still
  behaves correctly under the raised cap: it reuses the row and does not take a second
  slot;
- a **Pro user who lapses back to Free** is refused a second connection again, while
  **keeping** the connections they already have;
- **the cap is per user**, and a refusal **stores nothing**.

The Free-tier half of this is also covered by `test_calendar_connect_api.py`; this file
is about the *tiering*, and it re-pins the payload so that the Pro value is pinned too.
"""

import json

import pytest
from django.contrib.auth import get_user_model

from apps.identity.models import Subscription, SubscriptionStatus
from apps.personalization.models import CalendarConnection
from shared.constants import (
    FREE_TIER_CALENDAR_PROVIDER_CAP,
    PRO_TIER_CALENDAR_PROVIDER_CAP,
)
from shared.db import PERSONAL
from shared.ids import uuid7
from tests.csrf import CsrfClient
from tests.identity.factories import SubscriptionFactory
from tests.personalization.factories import FAKE_CALENDAR_URL, CalendarConnectionFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

User = get_user_model()

JSON = "application/json"

#: Three distinct addresses. Each must differ from the others, or the "already connected"
#: refusal would fire before the cap.
URLS = (
    FAKE_CALENDAR_URL,
    "https://example.com/other/calendar/basic.ics",
    "https://example.com/third/calendar/basic.ics",
    "https://example.com/fourth/calendar/basic.ics",
)


def make_user(email=None):
    """A real user with a real pk — the session resolves to this one."""
    if email is None:
        email = f"user-{uuid7()}@example.test"
    return User.objects.create_user(email=email, password="pw")


def signed_in(user=None):
    """A client whose session identifies `user`."""
    client = CsrfClient()
    client.force_login(user or make_user())
    return client


def post_connect(client, address=FAKE_CALENDAR_URL, provider="google", label=""):
    return client.post(
        "/api/personal/calendars",
        data=json.dumps({"provider": provider, "address": address, "display_label": label}),
        content_type=JSON,
    )


def make_pro(user):
    """Give the user a live subscription, so `is_pro` reads true for them."""
    return SubscriptionFactory(user_id=user.pk)


def lapse(user):
    """End the user's subscription, so `is_pro` reads false again.

    **A lapse is a transition on the existing row, not a new row.** `Subscription` allows
    at most one live row per user and keeps the history as terminal rows, so adding a
    `CANCELED` row beside the `ACTIVE` one would leave the user still Pro.
    """
    Subscription.objects.using(PERSONAL).filter(user_id=user.pk).update(
        status=SubscriptionStatus.CANCELED
    )


# ── The tiering ───────────────────────────────────────────────────────────────────


def test_a_free_user_cannot_connect_a_second_provider():
    user = make_user()
    client = signed_in(user)
    assert post_connect(client, URLS[0]).status_code == 201

    response = post_connect(client, URLS[1])

    assert response.status_code == 409
    assert response.json()["code"] == "calendar_cap_reached"


def test_a_pro_user_connects_a_second_and_a_third():
    """FR-50: *"Pro tier: up to 3."*"""
    user = make_user()
    make_pro(user)
    client = signed_in(user)

    assert post_connect(client, URLS[0]).status_code == 201
    assert post_connect(client, URLS[1]).status_code == 201
    assert post_connect(client, URLS[2]).status_code == 201

    assert CalendarConnection.objects.using(PERSONAL).filter(user_id=user.pk).count() == 3


def test_a_pro_user_is_refused_a_fourth_provider():
    user = make_user()
    make_pro(user)
    client = signed_in(user)
    for address in URLS[:3]:
        assert post_connect(client, address).status_code == 201

    response = post_connect(client, URLS[3])

    assert response.status_code == 409
    assert response.json()["code"] == "calendar_cap_reached"


def test_the_refusal_names_the_tiers_own_cap():
    """**The cap in the payload is the tier's cap.**

    A Free user is refused with `cap: 1` and a Pro user with `cap: 3`, so the frontend
    can say what the account *would* allow rather than a number that never changes.
    """
    free_user = make_user()
    free_client = signed_in(free_user)
    post_connect(free_client, URLS[0])
    free_refusal = post_connect(free_client, URLS[1]).json()

    pro_user = make_user()
    make_pro(pro_user)
    pro_client = signed_in(pro_user)
    for address in URLS[:3]:
        post_connect(pro_client, address)
    pro_refusal = post_connect(pro_client, URLS[3]).json()

    assert free_refusal["details"]["cap"] == FREE_TIER_CALENDAR_PROVIDER_CAP
    assert pro_refusal["details"]["cap"] == PRO_TIER_CALENDAR_PROVIDER_CAP


def test_the_refusal_payload_has_no_modal_semantics():
    """**Exactly two fields, and nothing else.**

    No `modal`, no `title`, no `actions`, no `dismissable`: the refusal is an *inline*
    prompt with a quiet "Upgrade" link, not a modal (EXPERIENCE.md §3, the Free-tier cap
    prompt). The key set is pinned exactly, so a future edit that grows a modal-shaped
    field fails here.
    """
    user = make_user()
    make_pro(user)
    client = signed_in(user)
    for address in URLS[:3]:
        post_connect(client, address)

    body = post_connect(client, URLS[3]).json()

    assert set(body) == {"code", "message", "details"}
    assert set(body["details"]) == {"cap", "upgrade_hint"}
    assert "modal" not in str(body["details"]).lower()


def test_the_refusal_message_is_calm():
    """Calm, no urgency, no exclamation mark — the project's voice."""
    user = make_user()
    client = signed_in(user)
    post_connect(client, URLS[0])

    response = post_connect(client, URLS[1])

    message = response.json()["message"]
    assert message == "You've connected the calendars your plan allows."
    assert "!" not in message


# ── The reuse path ────────────────────────────────────────────────────────────────


def test_the_reuse_path_still_reuses_the_row_under_the_free_cap():
    """**A `needs_reconnect` row that is flipped back to `active` is still one row.**

    The reuse path does not get a free pass: the row is already counted, so it does not
    add a slot — but it does not take a second one either, so a Free user whose calendar
    was revoked can reconnect without hitting the cap.
    """
    user = make_user()
    connection = CalendarConnectionFactory(
        user_id=user.pk,
        status=CalendarConnection.Status.NEEDS_RECONNECT,
        last_error_kind="revoked",
    )
    client = signed_in(user)

    response = post_connect(client, URLS[1])

    assert response.status_code == 201
    assert CalendarConnection.objects.using(PERSONAL).filter(user_id=user.pk).count() == 1
    connection.refresh_from_db()
    assert connection.status == CalendarConnection.Status.ACTIVE


def test_the_reuse_path_still_reuses_the_row_under_the_pro_cap():
    """**The reuse path behaves the same at the raised cap.**

    The cap is 3 for Pro, so the reuse arithmetic is exercised against a different
    number — and the row is still reused rather than duplicated.
    """
    user = make_user()
    make_pro(user)
    connection = CalendarConnectionFactory(
        user_id=user.pk,
        status=CalendarConnection.Status.NEEDS_RECONNECT,
        last_error_kind="revoked",
    )
    client = signed_in(user)

    response = post_connect(client, URLS[1])

    assert response.status_code == 201
    assert CalendarConnection.objects.using(PERSONAL).filter(user_id=user.pk).count() == 1
    connection.refresh_from_db()
    assert connection.status == CalendarConnection.Status.ACTIVE


def test_the_reuse_path_does_not_get_a_free_pass_at_the_cap():
    """**The reuse path is counted, not ignored.**

    A Free user who already holds an active calendar and has a revoked one is at the
    cap: the revoked row occupies a slot, so the connect is refused. Skipping the check
    on this path let a user end up with two active calendars on a one-calendar plan.
    """
    user = make_user()
    CalendarConnectionFactory(user_id=user.pk, status=CalendarConnection.Status.ACTIVE)
    CalendarConnectionFactory(
        user_id=user.pk,
        status=CalendarConnection.Status.NEEDS_RECONNECT,
        last_error_kind="revoked",
        credential_fingerprint="b" * 64,
    )
    client = signed_in(user)

    response = post_connect(client, URLS[2])

    assert response.status_code == 409
    assert response.json()["code"] == "calendar_cap_reached"


# ── A lapse ───────────────────────────────────────────────────────────────────────


def test_a_pro_user_who_lapses_back_to_free_is_refused_a_second_connection():
    """**The cap follows the tier, read at the moment of the connect.**

    A lapsed Pro user is a Free user, so the second connection is refused.
    """
    user = make_user()
    make_pro(user)
    client = signed_in(user)
    assert post_connect(client, URLS[0]).status_code == 201

    lapse(user)

    response = post_connect(client, URLS[1])
    assert response.status_code == 409
    assert response.json()["code"] == "calendar_cap_reached"


def test_a_lapsed_pro_user_keeps_the_connections_they_already_hold():
    """**A lapse closes the door behind the user; it does not take their calendars away.**

    The cap is enforced at the *connect* step, so nothing is deleted on a downgrade. What
    happens to over-cap data is an open question in the brief, and answering it here would
    be answering it quietly.
    """
    user = make_user()
    make_pro(user)
    client = signed_in(user)
    assert post_connect(client, URLS[0]).status_code == 201
    assert post_connect(client, URLS[1]).status_code == 201

    lapse(user)

    assert CalendarConnection.objects.using(PERSONAL).filter(user_id=user.pk).count() == 2


# ── The cap is per user, and a refusal stores nothing ─────────────────────────────


def test_the_cap_is_per_user():
    """**One person's cap is not another's.**"""
    first = make_user()
    first_client = signed_in(first)
    assert post_connect(first_client, URLS[0]).status_code == 201

    second_client = signed_in(make_user())
    response = post_connect(second_client, URLS[0])

    assert response.status_code == 201


def test_a_refused_connection_stores_nothing():
    user = make_user()
    make_pro(user)
    client = signed_in(user)
    for address in URLS[:3]:
        post_connect(client, address)

    post_connect(client, URLS[3])

    assert CalendarConnection.objects.using(PERSONAL).filter(user_id=user.pk).count() == 3
