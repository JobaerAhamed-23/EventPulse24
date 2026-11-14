"""The dismissal endpoint (FR-25): record the swipe, say whether to ask.

**What these tests hold.**

1. **The state comes from the session, never from the payload** (AD-12). The endpoint
   takes no user id, so a request cannot talk the scoping out of.
2. **The slot is read, not sent.** The body carries only the event id, so a client cannot
   claim a dismissal came from a slot it did not come from — and cannot put a
   serendipity card into the cluster by asserting it did.
3. **`prompt_due` is the whole answer**, and it is false for a single dismissal. The
   cluster needs three similar events in a window.
4. **The prompt's copy is the server's own.** The title names the category the cluster
   agreed on, and the label comes from `INTEREST_CHIPS` — never from the event's title,
   which is untrusted scraped text (AD-9).
"""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from freezegun import freeze_time

from apps.identity.models import User
from apps.personalization.models import EventDismissal
from shared.db import CATALOG, PERSONAL
from tests.csrf import CsrfClient
from tests.ingestion.factories import EventFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

DISMISSALS = "/api/personal/dismissals"


def make_user(email=None):
    """A fresh user. The email is unique per call, so a test can make two."""
    return User.objects.create_user(
        email=email or f"sam-{uuid4().hex[:8]}@example.test", password="pw"
    )


def signed_in(user=None):
    """A client whose session identifies a user, and that user's id."""
    account = user or make_user()
    client = CsrfClient()
    client.force_login(account)
    client.user_id = account.pk
    return client


def body_of(response):
    return json.loads(response.content)


def dismiss(client, event_id):
    return client.post(
        DISMISSALS,
        {"event_id": str(event_id)},
        content_type="application/json",
    )


def _embed(event_id, values):
    """A known direction for the event's vector.

    **The vector is written directly**, not through the embedding adapter: the rule
    under test is the cosine, and the fake adapter's hash-based vectors would make the
    similarity between two events a function of their titles rather than of the rule.
    """
    from apps.ingestion.models import Event
    from shared.constants import FR25_EMBEDDING_DIMENSIONS

    padded = list(values) + [0.0] * (FR25_EMBEDDING_DIMENSIONS - len(values))
    norm = sum(value**2 for value in padded) ** 0.5
    Event.objects.using(CATALOG).filter(pk=event_id).update(
        embedding=[value / norm for value in padded]
    )


# ── Recording ────────────────────────────────────────────────────────────────────


def test_a_dismissal_is_recorded():
    event = EventFactory()
    client = signed_in()

    response = dismiss(client, event.id)

    assert response.status_code == 200, response.content
    payload = body_of(response)
    assert payload["event_id"] == str(event.id)
    assert payload["cluster_advanced"] is True
    assert payload["prompt_due"] is False
    assert payload["prompt"] is None
    assert EventDismissal.objects.filter(user_id=client.user_id, event_id=event.id).count() == 1


def test_one_users_dismissal_does_not_touch_anothers():
    """The dismissal is the user's, and scoping is by the session."""
    event = EventFactory()
    mine = signed_in()
    theirs = signed_in()

    dismiss(theirs, event.id)

    assert EventDismissal.objects.filter(user_id=mine.user_id).count() == 0


def test_the_same_event_dismissed_twice_is_one_dismissal():
    """The pair is unique, so a second swipe of the same card does not add evidence."""
    event = EventFactory()
    client = signed_in()

    dismiss(client, event.id)
    dismiss(client, event.id)

    assert EventDismissal.objects.filter(user_id=client.user_id, event_id=event.id).count() == 1


def test_an_anonymous_caller_is_refused():
    event = EventFactory()

    response = dismiss(CsrfClient(), event.id)

    assert response.status_code == 401


def test_a_dismissal_of_an_unknown_event_is_recorded_anyway():
    """**The endpoint may not read `catalog` in a write transaction** (AD-3), so it
    cannot check that the event exists — and it does not need to. A dismissal of an event
    that has since been removed excludes nothing and is purged with the user's data.

    The test is here because the *contract* matters more than the behaviour: a declared
    404 that never arrives teaches the client to expect a failure that never comes.
    """
    client = signed_in()
    unknown = uuid4()

    response = dismiss(client, unknown)

    assert response.status_code == 200, response.content
    assert EventDismissal.objects.filter(user_id=client.user_id, event_id=unknown).count() == 1


# ── The prompt ───────────────────────────────────────────────────────────────────


def test_the_prompt_fires_after_three_similar_dismissals():
    """The cluster needs three distinct events inside a digest window, and the prompt
    arrives with the server's own copy.

    **All three go through the endpoint, spaced past the rage-dismiss guard.** The
    endpoint stamps the dismissal with the server's clock, so a dismissal recorded
    through the service at a fixed instant and one recorded through the endpoint would
    be eight days apart — outside the window. And three dismissals inside five seconds
    are a flick, not a considered pattern: the guard stops the third from counting, so
    the test would be measuring the guard instead of the cluster.

    `freeze_time(..., tick=True)` advances the clock with real time, so each block is
    a real minute later and the three dismissals are a considered sequence.
    """
    events = [
        EventFactory(title="Gallery night", description="An art exhibition") for _ in range(3)
    ]
    for event in events:
        _embed(event.id, [1.0, 0.0, 0.0])

    client = signed_in()
    started = datetime(2026, 11, 6, 18, 0, tzinfo=UTC)
    responses = []
    with freeze_time(started, tick=True):
        for index, event in enumerate(events):
            with freeze_time(started + timedelta(minutes=index), tick=True):
                responses.append(dismiss(client, event.id))

    for response in responses[:-1]:
        assert response.status_code == 200, response.content
        assert body_of(response)["prompt_due"] is False

    payload = body_of(responses[-1])
    assert payload["prompt_due"] is True
    assert payload["prompt"] is not None
    # **The copy is the server's own.** The label comes from `INTEREST_CHIPS`.
    assert payload["prompt"]["category_key"] == "arts_culture"
    assert "Arts & culture" in payload["prompt"]["title"]
    assert "Settings → Taste" in payload["prompt"]["description"]


def test_the_prompt_does_not_fire_again_for_the_same_cluster():
    """**The counter resets when the prompt fires**, so the same cluster cannot nag."""
    events = [
        EventFactory(title=f"Gallery night {index}", description="An art exhibition")
        for index in range(4)
    ]
    for event in events:
        _embed(event.id, [1.0, 0.0, 0.0])

    client = signed_in()
    started = datetime(2026, 11, 6, 18, 0, tzinfo=UTC)
    responses = []
    with freeze_time(started, tick=True):
        for index, event in enumerate(events):
            with freeze_time(started + timedelta(minutes=index), tick=True):
                responses.append(dismiss(client, event.id))

    assert body_of(responses[-1])["prompt_due"] is False
