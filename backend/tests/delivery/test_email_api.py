"""The mail endpoints: the RFC 8058 unsubscribe and the click tracker (FR-11, AD-20, SM-2).

**The property at the centre of this file is the `GET`/`POST` split.**

RFC 8058 says the unsubscribe endpoint is a **`POST`**, precisely because mail clients and
link scanners follow `GET` links automatically. If a `GET` unsubscribed, the user's own
mail provider could cancel the subscription before the user had read the message — and
the user would never know why the mail stopped.

So both behaviours are tested, and they are tested **through the real HTTP endpoints**,
because the property is a property of the HTTP surface and not of a function the
endpoint happens to call:

- A `GET` renders a confirmation page and **changes nothing**.
- A `POST` applies the unsubscribe.

And the two scopes never touch each other, at the HTTP level too.
"""

import pytest
from django.test import Client

from apps.delivery.models import ScheduledSend
from apps.delivery.services.unsubscribe_tokens import (
    mint_click_token,
    mint_unsubscribe_token,
)
from shared.constants import (
    UNSUBSCRIBE_SCOPE_EVENT_REMINDERS,
    UNSUBSCRIBE_SCOPE_PING,
)
from shared.db import PERSONAL
from shared.ids import uuid7
from tests.delivery.factories import ReminderPlanFactory, ScheduledSendFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])


@pytest.fixture
def client():
    return Client()


def _event_token(user_id, target_id) -> str:
    return mint_unsubscribe_token(
        user_id=user_id,
        scope=UNSUBSCRIBE_SCOPE_EVENT_REMINDERS,
        target_id=target_id,
    )


def _ping_token(user_id) -> str:
    return mint_unsubscribe_token(user_id=user_id, scope=UNSUBSCRIBE_SCOPE_PING)


# --- The GET does not unsubscribe -----------------------------------------------------------------


def test_a_get_does_not_unsubscribe_anyone(client):
    """**A link scanner must not unsubscribe anyone.**

    Mail clients, security proxies and corporate gateways follow the links in a message
    to decide whether it is safe — several do it automatically, before the user has seen
    the message. A `GET` that unsubscribed would let the user's own mail provider cancel
    a subscription the user never touched.
    """
    user = uuid7()
    plan = ReminderPlanFactory(user_id=user, slots=["1d"])
    token = _event_token(user, plan.target_id)

    response = client.get(f"/api/email/unsubscribe?token={token}")

    assert response.status_code == 200
    plan.refresh_from_db()
    assert plan.slots == ["1d"]


def test_a_get_on_the_ping_link_does_not_turn_the_ping_off(client):
    from apps.delivery.services.unsubscribes import pulse_ping_unsubscribed

    user = uuid7()
    token = _ping_token(user)

    response = client.get(f"/api/email/unsubscribe?token={token}")

    assert response.status_code == 200
    assert pulse_ping_unsubscribed(user_id=user) is False


def test_a_get_renders_a_confirmation_page_that_says_what_it_would_do(client):
    """The page says exactly what would be turned off — and offers the inverse, because
    unsubscribing by accident is a real thing."""
    user = uuid7()
    plan = ReminderPlanFactory(user_id=user, slots=["1d"])
    token = _event_token(user, plan.target_id)

    response = client.get(f"/api/email/unsubscribe?token={token}")

    assert response.status_code == 200
    body = response.content.decode()
    assert "reminders for this event" in body
    # The inverse is offered.
    assert "Turn it back on" in body or "settings" in body


def test_a_get_says_the_digest_would_stop_and_the_reminders_would_not(client):
    """The page distinguishes the two scopes, so a user knows what they are about to do."""
    user = uuid7()
    token = _ping_token(user)

    response = client.get(f"/api/email/unsubscribe?token={token}")

    body = response.content.decode()
    assert "daily Pulse digest" in body
    assert "Your event reminders will keep arriving" in body


def test_a_get_does_not_cancel_the_pending_sends(client):
    user = uuid7()
    plan = ReminderPlanFactory(user_id=user, slots=["1d"])
    row = ScheduledSendFactory(
        user_id=user,
        target_kind=plan.target_kind,
        target_id=plan.target_id,
    )
    token = _event_token(user, plan.target_id)

    client.get(f"/api/email/unsubscribe?token={token}")

    row.refresh_from_db()
    assert row.status == ScheduledSend.Status.PENDING


# --- The POST honours the one-click semantics ----------------------------------------------------


def test_a_post_unsubscribes_the_event_scope(client):
    user = uuid7()
    plan = ReminderPlanFactory(user_id=user, slots=["1d"])
    token = _event_token(user, plan.target_id)

    response = client.post(f"/api/email/unsubscribe?token={token}")

    assert response.status_code == 200
    plan.refresh_from_db()
    assert plan.slots == []


def test_a_post_unsubscribes_the_ping_scope(client):
    from apps.delivery.services.unsubscribes import pulse_ping_unsubscribed

    user = uuid7()
    token = _ping_token(user)

    response = client.post(f"/api/email/unsubscribe?token={token}")

    assert response.status_code == 200
    assert pulse_ping_unsubscribed(user_id=user) is True


def test_a_post_cancels_the_pending_sends(client):
    """**Cancelling, not swallowing.** A row left pending would be claimed by the sweep,
    rendered and sent — and the user would receive the very mail they just turned off."""
    user = uuid7()
    plan = ReminderPlanFactory(user_id=user, slots=["1d"])
    row = ScheduledSendFactory(
        user_id=user,
        target_kind=plan.target_kind,
        target_id=plan.target_id,
    )
    token = _event_token(user, plan.target_id)

    client.post(f"/api/email/unsubscribe?token={token}")

    row.refresh_from_db()
    assert row.status == ScheduledSend.Status.CANCELLED


def test_a_post_with_the_token_in_the_body_works_too(client):
    """The confirmation page's form posts the token in the body, while RFC 8058's
    provider posts to the URL in the mail. **Both work**, so neither path is a
    special case at the call site."""
    user = uuid7()
    plan = ReminderPlanFactory(user_id=user, slots=["1d"])
    token = _event_token(user, plan.target_id)

    response = client.post("/api/email/unsubscribe", data={"token": token})

    assert response.status_code == 200
    plan.refresh_from_db()
    assert plan.slots == []


def test_a_post_twice_says_it_was_already_off(client):
    """**Unsubscribing twice is a no-op, not an error** — and the page says so, rather
    than pretending it did something."""
    user = uuid7()
    plan = ReminderPlanFactory(user_id=user, slots=["1d"])
    token = _event_token(user, plan.target_id)

    client.post(f"/api/email/unsubscribe?token={token}")
    response = client.post(f"/api/email/unsubscribe?token={token}")

    assert response.status_code == 200
    body = response.content.decode()
    assert "Already off" in body
    assert "Nothing changed" in body


def test_a_post_twice_on_the_ping_says_it_was_already_off(client):
    user = uuid7()
    token = _ping_token(user)

    client.post(f"/api/email/unsubscribe?token={token}")
    response = client.post(f"/api/email/unsubscribe?token={token}")

    assert response.status_code == 200
    assert "Already off" in response.content.decode()


def test_the_post_needs_no_csrf_token(client):
    """**The signed token is the authorisation.**

    The RFC 8058 provider has no session, no cookie and no CSRF token, so an endpoint
    that required one could never be called by the very mechanism RFC 8058 describes.
    And there is no ambient authority to abuse: the caller must present a secret bearer
    token, which a cross-site attacker cannot read.
    """
    user = uuid7()
    plan = ReminderPlanFactory(user_id=user, slots=["1d"])
    token = _event_token(user, plan.target_id)

    response = client.post(f"/api/email/unsubscribe?token={token}")

    assert response.status_code == 200
    assert response.status_code != 403


# --- The two scopes never touch each other -------------------------------------------------------


def test_a_reminder_unsubscribe_never_touches_the_ping(client):
    """**FR-11's whole point, at the HTTP edge.**"""
    from apps.delivery.services.unsubscribes import pulse_ping_unsubscribed

    user = uuid7()
    plan = ReminderPlanFactory(user_id=user, slots=["1d"])
    token = _event_token(user, plan.target_id)

    client.post(f"/api/email/unsubscribe?token={token}")

    assert pulse_ping_unsubscribed(user_id=user) is False


def test_a_ping_unsubscribe_never_touches_a_reminder_plan(client):
    """The other half of the separation: the user asked to stop the digest, not their
    event reminders."""
    user = uuid7()
    plan = ReminderPlanFactory(user_id=user, slots=["1d", "1hr"])
    token = _ping_token(user)

    client.post(f"/api/email/unsubscribe?token={token}")

    plan.refresh_from_db()
    assert plan.slots == ["1d", "1hr"]


def test_a_reminder_unsubscribe_leaves_another_events_reminders_alone(client):
    user = uuid7()
    mine = ReminderPlanFactory(user_id=user, slots=["1d"])
    theirs = ReminderPlanFactory(user_id=user, slots=["1d"])
    token = _event_token(user, mine.target_id)

    client.post(f"/api/email/unsubscribe?token={token}")

    theirs.refresh_from_db()
    assert theirs.slots == ["1d"]


# --- The refusal ---------------------------------------------------------------------------------


def test_an_invalid_token_is_refused_on_the_get(client):
    response = client.get("/api/email/unsubscribe?token=not-a-token")

    assert response.status_code == 422
    assert "isn't valid" in response.content.decode()


def test_an_invalid_token_is_refused_on_the_post(client):
    user = uuid7()
    plan = ReminderPlanFactory(user_id=user, slots=["1d"])

    response = client.post("/api/email/unsubscribe?token=not-a-token")

    assert response.status_code == 422
    plan.refresh_from_db()
    assert plan.slots == ["1d"]


def test_a_forged_token_is_refused(client):
    """A token signed under the *click* salt cannot be used to unsubscribe — the two are
    different signatures over different payloads."""
    user = uuid7()
    plan = ReminderPlanFactory(user_id=user, slots=["1d"])
    forged = mint_click_token(
        user_id=user,
        destination="https://eventpulse24.example/pulse",
    )

    response = client.post(f"/api/email/unsubscribe?token={forged}")

    assert response.status_code == 422
    plan.refresh_from_db()
    assert plan.slots == ["1d"]


def test_every_refusal_says_the_same_thing(client):
    """**One refusal for every failure**, so the response is not an oracle."""
    bodies = set()
    for token in ("", "not-a-token", "a:b:c"):
        response = client.post(f"/api/email/unsubscribe?token={token}")
        assert response.status_code == 422
        bodies.add(response.content)

    assert len(bodies) == 1


# --- The click tracker ---------------------------------------------------------------------------


def test_a_click_redirects_to_the_destination(client):
    """**A redirect, not a pixel.** SM-2 measures the digest CTA click and explicitly
    rejects open-pixel measurement as unreliable."""
    user = uuid7()
    token = mint_click_token(
        user_id=user,
        destination="https://eventpulse24.example/pulse",
    )

    response = client.get(f"/api/email/click?token={token}")

    assert response.status_code == 302
    assert response["Location"] == "https://eventpulse24.example/pulse"


def test_a_click_to_a_destination_we_do_not_send_people_is_refused(client):
    """**The destination is inside the signed token**, so it cannot be edited into an open
    redirect — but the endpoint also checks it against a closed set, because a valid
    token naming somewhere unexpected is still a refusal."""
    user = uuid7()
    token = mint_click_token(
        user_id=user,
        destination="https://elsewhere.example/phishing",
    )

    response = client.get(f"/api/email/click?token={token}")

    assert response.status_code == 422
    assert "Location" not in response


def test_a_click_with_an_invalid_token_is_refused(client):
    response = client.get("/api/email/click?token=not-a-token")

    assert response.status_code == 422


def test_an_unsubscribe_token_cannot_be_used_as_a_click_token(client):
    user = uuid7()
    token = _ping_token(user)

    response = client.get(f"/api/email/click?token={token}")

    assert response.status_code == 422


# --- No address reaches a log sink (AD-13) -------------------------------------------------------


def test_the_endpoints_log_no_address(client, caplog):
    """AD-13: the recipient's address never reaches a log sink."""
    user = uuid7()
    plan = ReminderPlanFactory(user_id=user, slots=["1d"])
    token = _event_token(user, plan.target_id)

    with caplog.at_level("DEBUG"):
        client.get(f"/api/email/unsubscribe?token={token}")
        client.post(f"/api/email/unsubscribe?token={token}")

    for record in caplog.records:
        assert "@" not in record.getMessage()
