"""`GET /api/personal/browse` — the wire contract for the Browse surface (FR-26, FR-48).

The service's own rules are pinned in `test_browse_read.py`. What is pinned here is what
reaches the client: that the route is authed, that its three empty-ish answers all come back
as 200 and are told apart by fields rather than by status codes, that the quota is reported
without being spent, and that a Pro account is told it has no cap.

**Why all of that is a 200.** The surface has to say "Nothing matched." and "Nothing nearby
tonight." and mean different things. If "no city" were a 4xx the client would have to map a
status code onto a sentence, which is the interpretation an API exists to remove.
"""

from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from freezegun import freeze_time

from apps.personalization.models import DigestPreference
from shared.db import CATALOG, PERSONAL
from tests.csrf import CsrfClient
from tests.ingestion.factories import EventFactory, VenueFactory
from tests.personalization.factories import DigestPreferenceFactory, SavedEventFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

User = get_user_model()

#: The instant every test here measures from. 2026-11-10 12:00 UTC is 04:00 in Los Angeles.
NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)

CITY = "Brooklyn"
ZONE = "America/Los_Angeles"
PATH = "/api/personal/browse"


@pytest.fixture(autouse=True)
def _frozen_clock():
    """Pin the clock at `NOW`, with `tick=True` so UUIDv7 keys stay monotonic."""
    with freeze_time(NOW, tick=True):
        yield


def make_user(email="sam@example.test"):
    return User.objects.create_user(email=email, password="pw")


def signed_in(user=None):
    """A client whose session identifies `user`."""
    client = CsrfClient()
    client.force_login(user or make_user())
    return client


def with_city(user, *, city: str | None = CITY, zone: str = ZONE):
    """Give the user a digest-preference city — the city Browse reads.

    `city_source` travels with the city; the database refuses one without the other.
    """
    DigestPreferenceFactory(
        user_id=user.pk,
        city=city,
        city_source=DigestPreference.CitySource.CHOICE if city else None,
        timezone=zone,
    )


def make_event(*, hours_ahead: float, city: str = CITY, **overrides):
    """A published, fresh, upcoming event. `last_seen_at` is pinned so FR-14 keeps it."""
    venue = VenueFactory(city=city, country_code="US")
    return EventFactory(
        venue=venue,
        start_time_utc=NOW + timedelta(hours=hours_ahead),
        last_seen_at=NOW,
        **overrides,
    )


def test_an_anonymous_request_is_refused():
    """The route is on the authed router, and Browse is a personal surface."""
    response = Client().get(PATH)

    assert response.status_code == 401


def test_a_signed_in_user_gets_their_citys_events():
    user = make_user()
    with_city(user)
    event = make_event(hours_ahead=6)

    response = signed_in(user).get(PATH)

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["city"] == CITY
    assert body["timezone"] == ZONE
    assert [card["event_id"] for card in body["cards"]] == [str(event.id)]
    assert body["total"] == 1
    assert body["has_more"] is False
    assert body["city_missing"] is False


def test_a_card_carries_what_the_surface_renders():
    user = make_user()
    with_city(user)
    make_event(hours_ahead=6)

    body = signed_in(user).get(PATH).json()

    card = body["cards"][0]
    for field in (
        "event_id",
        "slug",
        "title",
        "start_time_utc",
        "start_time_tz",
        "source_badge",
        "tags",
        "confidence",
        "stripe",
        "is_saved",
    ):
        assert field in card, f"the card is missing {field}"
    assert card["stripe"] in ("public", "must_know")
    assert isinstance(card["tags"], list)


def test_a_user_with_no_city_gets_200_and_a_flag_not_an_error():
    """Onboarding can be skipped. The client shows the quiet empty state, not a failure."""
    user = make_user()
    with_city(user, city=None)
    make_event(hours_ahead=6)

    response = signed_in(user).get(PATH)

    assert response.status_code == 200
    body = response.json()
    assert body["city_missing"] is True
    assert body["cards"] == []
    assert body["total"] == 0


def test_a_city_with_nothing_on_is_a_different_answer_from_having_no_city():
    """The two emptinesses must be distinguishable in the payload, not just on screen."""
    user = make_user()
    with_city(user)

    body = signed_in(user).get(PATH).json()

    assert body["cards"] == []
    assert body["total"] == 0
    assert body["city_missing"] is False
    assert body["city"] == CITY


def test_the_tier_boundary_is_on_the_response():
    user = make_user()
    with_city(user)
    for hour in range(1, 7):
        make_event(hours_ahead=hour)

    body = signed_in(user).get(PATH).json()

    assert body["tier_2_starts_at"] == 3


def test_paging_is_bounded_and_says_whether_more_exists():
    user = make_user()
    with_city(user)
    for hour in range(1, 8):
        make_event(hours_ahead=hour)

    first = signed_in(user).get(f"{PATH}?offset=0&limit=5").json()

    assert len(first["cards"]) == 5
    assert first["total"] == 7
    assert first["has_more"] is True


def test_an_already_saved_event_comes_back_saved():
    user = make_user()
    with_city(user)
    event = make_event(hours_ahead=6)
    SavedEventFactory(user_id=user.pk, event_id=event.id)

    body = signed_in(user).get(PATH).json()

    assert body["cards"][0]["is_saved"] is True


def test_a_free_users_quota_is_reported_and_not_spent():
    """Opening Browse must not cost the user their one free save.

    Three requests, and the quota still reads zero. If the endpoint reported the allowance
    by calling the gate — which counts an attempt by contract — the third read would say the
    user had spent three saves without ever pressing Save.
    """
    user = make_user()
    with_city(user)
    make_event(hours_ahead=6)
    client = signed_in(user)

    bodies = [client.get(PATH).json() for _ in range(3)]

    for body in bodies:
        assert body["quota"]["used"] == 0
        assert body["quota"]["cap"] == 1
        assert body["quota"]["is_pro"] is False


def test_a_pro_user_is_told_they_have_no_cap(monkeypatch):
    """FR-48: a Pro account has no save cap at all — `null`, not a very large number."""
    monkeypatch.setattr(
        "apps.personalization.services.save_cap.is_pro",
        lambda *, user_id: True,
    )
    user = make_user()
    with_city(user)
    make_event(hours_ahead=6)

    body = signed_in(user).get(PATH).json()

    assert body["quota"]["is_pro"] is True
    assert body["quota"]["cap"] is None


def test_one_users_browse_never_shows_another_users_save_state():
    user = make_user()
    stranger = make_user(email="other@example.test")
    with_city(user)
    event = make_event(hours_ahead=6)
    SavedEventFactory(user_id=stranger.pk, event_id=event.id)

    body = signed_in(user).get(PATH).json()

    assert body["cards"][0]["is_saved"] is False
