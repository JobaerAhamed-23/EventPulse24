"""The onboarding endpoints (FR-1).

The surface is seven endpoints under `/api/personal/onboarding`. What these tests pin is
the **shape of the contract**, not the service's behaviour (which `test_onboarding_commands.py`
owns):

- every endpoint is **authed** — an anonymous request is refused;
- every endpoint is **scoped to the session user** — another user's rows are invisible, and
  no endpoint accepts a user id as input;
- the chip list comes from **the server's constant** — the frontend holds no second copy;
- the refusals answer in the project's error shape, with calm messages;
- `PUT` replaces and `POST` transitions.

The client is a `CsrfClient`, because these endpoints resolve their user through
`identity`'s resolver and the resolver checks CSRF on every unsafe method (D13).
"""

from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.personalization.models import DigestPreference, Interest, OnboardingProgress
from shared.constants import ONBOARDING_RESUME_WINDOW
from shared.db import PERSONAL
from tests.csrf import CsrfClient

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

User = get_user_model()


def make_user(email="sam@example.test"):
    """A real user with a real pk — the session resolves to this one."""
    return User.objects.create_user(email=email, password="pw")


def signed_in(user=None):
    """A client whose session identifies `user`."""
    client = CsrfClient()
    client.force_login(user or make_user())
    return client


# --- The chip list ----------------------------------------------------------------------------


def test_the_chip_endpoint_returns_the_ten_chips():
    client = signed_in()

    response = client.get("/api/personal/onboarding/interest-chips")

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 10
    assert items[0] == {"key": "tech_meetups", "label": "Tech & meetups"}
    assert items[-1] == {"key": "government_civic", "label": "Government & civic"}


def test_the_chip_endpoint_projects_the_constant():
    """The API is the one source: the list matches `shared.constants` exactly."""
    from shared.constants import INTEREST_CHIPS

    client = signed_in()

    response = client.get("/api/personal/onboarding/interest-chips")

    assert response.json()["items"] == [
        {"key": key, "label": label} for key, label in INTEREST_CHIPS
    ]


def test_the_chip_endpoint_requires_a_session():
    client = Client()

    response = client.get("/api/personal/onboarding/interest-chips")

    assert response.status_code == 401


# --- The state --------------------------------------------------------------------------------


def test_the_state_endpoint_returns_the_whole_state():
    client = signed_in()

    response = client.get("/api/personal/onboarding")

    assert response.status_code == 200
    payload = response.json()
    assert payload["completed"] is False
    assert payload["current_step"] == 1
    assert payload["step_name"] == "calendar"
    assert payload["interests"] == []
    assert payload["digest"] == {"delivery_time": None, "timezone": None}


def test_the_state_endpoint_requires_a_session():
    client = Client()

    response = client.get("/api/personal/onboarding")

    assert response.status_code == 401


def test_the_state_endpoint_shows_the_stored_interests():
    user = make_user()
    client = signed_in(user)

    client.put(
        "/api/personal/onboarding/interests",
        {"chip_keys": ["tech_meetups", "arts_culture"]},
        content_type="application/json",
    )

    response = client.get("/api/personal/onboarding")

    assert sorted(response.json()["interests"]) == ["arts_culture", "tech_meetups"]


# --- The interests -----------------------------------------------------------------------------


def test_putting_interests_stores_them():
    client = signed_in()

    response = client.put(
        "/api/personal/onboarding/interests",
        {"chip_keys": ["tech_meetups", "arts_culture"]},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert sorted(response.json()["chip_keys"]) == ["arts_culture", "tech_meetups"]
    assert Interest.objects.using(PERSONAL).count() == 2


def test_putting_interests_replaces_the_set():
    client = signed_in()

    client.put(
        "/api/personal/onboarding/interests",
        {"chip_keys": ["tech_meetups", "arts_culture"]},
        content_type="application/json",
    )

    response = client.put(
        "/api/personal/onboarding/interests",
        {"chip_keys": ["family_kids"]},
        content_type="application/json",
    )

    assert response.json()["chip_keys"] == ["family_kids"]
    assert Interest.objects.using(PERSONAL).count() == 1


def test_putting_more_than_three_interests_is_refused():
    client = signed_in()

    response = client.put(
        "/api/personal/onboarding/interests",
        {
            "chip_keys": [
                "tech_meetups",
                "sports_fitness",
                "arts_culture",
                "family_kids",
            ]
        },
        content_type="application/json",
    )

    assert response.status_code == 422
    assert response.json()["code"] == "too_many_interests"
    assert not Interest.objects.using(PERSONAL).exists()


def test_putting_an_unknown_chip_is_refused():
    client = signed_in()

    response = client.put(
        "/api/personal/onboarding/interests",
        {"chip_keys": ["underwater_basket_weaving"]},
        content_type="application/json",
    )

    assert response.status_code == 422
    assert response.json()["code"] == "unknown_interest"


def test_putting_no_interests_is_valid():
    """Zero picks is how the step is skipped."""
    client = signed_in()

    response = client.put(
        "/api/personal/onboarding/interests",
        {"chip_keys": []},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["chip_keys"] == []


def test_putting_interests_requires_a_session():
    client = Client()

    response = client.put(
        "/api/personal/onboarding/interests",
        {"chip_keys": ["tech_meetups"]},
        content_type="application/json",
    )

    assert response.status_code == 401


# --- The digest preference ---------------------------------------------------------------------


def test_putting_the_digest_preference_stores_it():
    client = signed_in()

    response = client.put(
        "/api/personal/onboarding/digest-preference",
        {"delivery_time": "09:30", "timezone": "America/Los_Angeles"},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["digest"] == {
        "delivery_time": "09:30:00",
        "timezone": "America/Los_Angeles",
    }
    preference = DigestPreference.objects.using(PERSONAL).get()
    assert preference.delivery_time.hour == 9
    assert preference.delivery_time.minute == 30


def test_putting_a_non_iana_timezone_is_refused():
    client = signed_in()

    response = client.put(
        "/api/personal/onboarding/digest-preference",
        {"delivery_time": "09:00", "timezone": "Mars/Olympus_Mons"},
        content_type="application/json",
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_timezone"
    assert not DigestPreference.objects.using(PERSONAL).exists()


def test_putting_the_digest_preference_requires_a_session():
    client = Client()

    response = client.put(
        "/api/personal/onboarding/digest-preference",
        {"delivery_time": "09:00", "timezone": "UTC"},
        content_type="application/json",
    )

    assert response.status_code == 401


# --- The step movers ---------------------------------------------------------------------------


def test_advancing_a_step_moves_to_the_next_one():
    client = signed_in()

    response = client.post("/api/personal/onboarding/step")

    assert response.status_code == 200
    assert response.json()["current_step"] == 2


def test_skipping_a_step_moves_to_the_next_one():
    client = signed_in()

    response = client.post("/api/personal/onboarding/step/skip")

    assert response.status_code == 200
    assert response.json()["current_step"] == 2


def test_skipping_all_completes_the_onboarding():
    client = signed_in()

    response = client.post("/api/personal/onboarding/skip-all")

    assert response.status_code == 200
    assert response.json()["completed"] is True


def test_advancing_a_completed_onboarding_is_refused():
    client = signed_in()
    client.post("/api/personal/onboarding/skip-all")

    response = client.post("/api/personal/onboarding/step")

    assert response.status_code == 409
    assert response.json()["code"] == "onboarding_already_complete"


def test_the_step_movers_require_a_session():
    client = Client()

    for path in (
        "/api/personal/onboarding/step",
        "/api/personal/onboarding/step/skip",
        "/api/personal/onboarding/skip-all",
    ):
        response = client.post(path)
        assert response.status_code == 401, path


def test_the_step_movers_refuse_a_request_without_a_csrf_token():
    """D13: every state-changing request needs the token."""
    client = Client()
    client.force_login(make_user())

    response = client.post("/api/personal/onboarding/step")

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"


# --- The safe methods -------------------------------------------------------------------------


def test_reading_the_state_does_not_write():
    """A GET must be safe.

    Django Ninja exempts every view from Django's CSRF middleware, and the resolver
    only checks CSRF on *unsafe* methods — so a write behind a GET is a **cross-site
    write**: a hostile page could restart a user's onboarding flow with a plain
    `<img src>` and no token at all.

    An expired flow therefore reads as step 1, and the stored row is left alone.
    """
    user = make_user()
    old = datetime.now(UTC) - ONBOARDING_RESUME_WINDOW - timedelta(days=1)
    OnboardingProgress.objects.using(PERSONAL).create(
        user_id=user.pk, current_step=3, last_advanced_at=old
    )
    client = signed_in(user)

    response = client.get("/api/personal/onboarding")

    assert response.status_code == 200
    assert response.json()["current_step"] == 1
    # The row is untouched: the read reported the restart, it did not perform one.
    progress = OnboardingProgress.objects.using(PERSONAL).get()
    assert progress.current_step == 3
    assert progress.last_advanced_at == old


def test_reading_the_state_creates_no_progress_row():
    """A user who only ever reads accumulates no row."""
    user = make_user()
    client = signed_in(user)

    client.get("/api/personal/onboarding")

    assert not OnboardingProgress.objects.using(PERSONAL).exists()


def test_the_me_endpoint_does_not_write():
    """`me` is on the hot path for every authenticated request — it must stay read-only."""
    user = make_user()
    old = datetime.now(UTC) - ONBOARDING_RESUME_WINDOW - timedelta(days=1)
    OnboardingProgress.objects.using(PERSONAL).create(
        user_id=user.pk, current_step=3, last_advanced_at=old
    )
    client = signed_in(user)

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    progress = OnboardingProgress.objects.using(PERSONAL).get()
    assert progress.current_step == 3
    assert progress.last_advanced_at == old


# --- The scoping -------------------------------------------------------------------------------


def test_the_endpoints_are_scoped_to_the_session_user():
    """Another user's rows are invisible, and no endpoint accepts a user id as input."""
    mine = make_user("mine@example.test")
    theirs = make_user("theirs@example.test")
    other_client = signed_in(theirs)

    other_client.put(
        "/api/personal/onboarding/interests",
        {"chip_keys": ["arts_culture"]},
        content_type="application/json",
    )

    client = signed_in(mine)
    response = client.get("/api/personal/onboarding")

    assert response.json()["interests"] == []

    # And the other user's row is untouched by this user's write.
    client.put(
        "/api/personal/onboarding/interests",
        {"chip_keys": ["tech_meetups"]},
        content_type="application/json",
    )

    assert Interest.objects.using(PERSONAL).filter(user_id=theirs.pk).count() == 1
    assert Interest.objects.using(PERSONAL).filter(user_id=mine.pk).count() == 1


def test_a_user_id_in_the_payload_is_ignored():
    """The scoping comes from the session; a user id in the body changes nothing."""
    user = make_user()
    other = make_user("other@example.test")
    client = signed_in(user)

    client.put(
        "/api/personal/onboarding/interests",
        {"chip_keys": ["tech_meetups"], "user_id": str(other.pk)},
        content_type="application/json",
    )

    assert Interest.objects.using(PERSONAL).filter(user_id=user.pk).count() == 1
    assert Interest.objects.using(PERSONAL).filter(user_id=other.pk).count() == 0
