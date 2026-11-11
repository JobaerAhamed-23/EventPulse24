"""Seven quiet-hours windows over the wire (FR-51).

The storage and the arithmetic are pinned by `test_quiet_hours_overrides.py` and
`tests/domain/test_weekly_quiet_hours.py`. What this file pins is the contract:

- a **Free account's request and response shape is unchanged** — the new fields are
  additive, and an existing client that ignores them keeps working;
- a **Pro account sets seven windows in one request**, and the server never observes a
  partially-updated week;
- a **Free account's attempt is refused** with the same calm `{cap, upgrade_hint}` payload
  the save cap and the calendar cap use, so the inline prompt renders it with no new
  component;
- a **lapsed Pro account can still read its windows**, and `effective_quiet_hours` tells it
  which are actually in force;
- `start == end` is refused on **every** window, not just the first.

The client is a `CsrfClient`, because the endpoints resolve their user through `identity`'s
resolver and the resolver checks CSRF on every unsafe method (D13).
"""

from datetime import UTC, datetime, time

import pytest
from django.contrib.auth import get_user_model

from apps.delivery.models import QuietHoursOverride
from apps.identity.models import SubscriptionStatus
from shared.db import CATALOG, PERSONAL
from tests.csrf import CsrfClient
from tests.identity.factories import SubscriptionFactory
from tests.personalization.factories import DigestPreferenceFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

User = get_user_model()

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
ZONE = "America/Los_Angeles"
SETTINGS_URL = "/api/settings/notifications"

MONDAY, SATURDAY = 0, 5

#: A full week of seven distinct windows, as a client would send it.
SEVEN = [
    {"weekday": weekday, "start": f"{20 + weekday % 4:02d}:00", "end": f"{6 + weekday:02d}:00"}
    for weekday in range(7)
]


def make_user(email="sam@example.test"):
    return User.objects.create_user(email=email, password="pw")


def with_zone(user, zone=ZONE):
    DigestPreferenceFactory(user_id=user.pk, timezone=zone)
    return user


def signed_in(user=None):
    client = CsrfClient()
    client.force_login(user or make_user())
    return client


def make_pro(user, status=SubscriptionStatus.ACTIVE):
    return SubscriptionFactory(user_id=user.pk, status=status)


def put(client, **body):
    return client.put(SETTINGS_URL, data=body, content_type="application/json")


def overrides_of(user):
    return QuietHoursOverride.objects.using(PERSONAL).filter(user_id=user.pk)


# ── A Free account is exactly where it was ────────────────────────────────────────


def test_the_free_shape_is_unchanged():
    """The existing single-window contract, byte for byte.

    The new fields are additive: a client written before FR-51 sends the same body and
    reads the same `quiet_hours`, and never has to know the other two exist.
    """
    user = with_zone(make_user())
    client = signed_in(user)

    response = put(client, quiet_hours={"start": "23:00", "end": "07:00"})

    assert response.status_code == 200
    body = response.json()
    assert body["quiet_hours"] == {"start": "23:00:00", "end": "07:00:00"}
    assert body["quiet_hours_overrides"] == []


def test_a_free_account_reads_seven_effective_days_that_are_all_its_one_window():
    user = with_zone(make_user())
    client = signed_in(user)
    put(client, quiet_hours={"start": "23:00", "end": "07:00"})

    body = client.get(SETTINGS_URL).json()

    assert [day["weekday"] for day in body["effective_quiet_hours"]] == list(range(7))
    for day in body["effective_quiet_hours"]:
        assert day["quiet_hours"] == {"start": "23:00:00", "end": "07:00:00"}


def test_a_free_account_with_quiet_hours_off_is_quiet_on_no_day():
    user = with_zone(make_user())
    client = signed_in(user)

    body = put(client, quiet_hours=None).json()

    assert body["quiet_hours"] is None
    assert all(day["quiet_hours"] is None for day in body["effective_quiet_hours"])


# ── The refusal ───────────────────────────────────────────────────────────────────


def test_a_free_account_setting_weekday_windows_is_refused_with_an_upgrade_hint():
    user = with_zone(make_user())
    client = signed_in(user)

    response = put(client, quiet_hours_overrides=SEVEN)

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "quiet_hours_pro_required"
    assert body["details"]["cap"] == 1
    assert body["details"]["upgrade_hint"] == "Set a different window for each day with Pro."


def test_the_refusal_carries_no_modal_shaped_field():
    """The same posture as the save cap: an inline prompt, never an interruption."""
    user = with_zone(make_user())
    client = signed_in(user)

    details = put(client, quiet_hours_overrides=SEVEN).json()["details"]

    assert set(details) == {"cap", "upgrade_hint"}


def test_a_refused_write_changes_nothing_at_all():
    user = with_zone(make_user())
    client = signed_in(user)
    put(client, quiet_hours={"start": "23:00", "end": "07:00"})

    put(client, quiet_hours={"start": "21:00", "end": "06:00"}, quiet_hours_overrides=SEVEN)

    assert overrides_of(user).count() == 0
    # The base window in the same refused request is not applied either.
    assert client.get(SETTINGS_URL).json()["quiet_hours"] == {
        "start": "23:00:00",
        "end": "07:00:00",
    }


def test_clearing_weekday_windows_is_never_refused():
    """Going back to what the free plan includes cannot need a subscription.

    It is also what a lapsed Pro account needs in order to tidy up.
    """
    user = with_zone(make_user())
    client = signed_in(user)

    response = put(client, quiet_hours_overrides=[])

    assert response.status_code == 200


# ── A Pro account sets its week ────────────────────────────────────────────────────


def test_a_pro_account_sets_seven_windows_in_one_request():
    user = with_zone(make_user())
    make_pro(user)
    client = signed_in(user)

    response = put(client, quiet_hours_overrides=SEVEN)

    assert response.status_code == 200
    body = response.json()
    assert [override["weekday"] for override in body["quiet_hours_overrides"]] == list(range(7))
    assert overrides_of(user).count() == 7


def test_a_pro_accounts_effective_week_shows_the_windows_it_set():
    user = with_zone(make_user())
    make_pro(user)
    client = signed_in(user)
    put(client, quiet_hours={"start": "22:00", "end": "08:00"})

    body = put(
        client,
        quiet_hours_overrides=[{"weekday": SATURDAY, "start": "23:30", "end": "10:00"}],
    ).json()

    effective = {day["weekday"]: day["quiet_hours"] for day in body["effective_quiet_hours"]}
    assert effective[SATURDAY] == {"start": "23:30:00", "end": "10:00:00"}
    assert effective[MONDAY] == {"start": "22:00:00", "end": "08:00:00"}


def test_the_list_replaces_the_week_rather_than_merging_into_it():
    user = with_zone(make_user())
    make_pro(user)
    client = signed_in(user)
    put(client, quiet_hours_overrides=SEVEN)

    put(client, quiet_hours_overrides=[{"weekday": MONDAY, "start": "22:00", "end": "08:00"}])

    assert [override.weekday for override in overrides_of(user)] == [MONDAY]


def test_an_omitted_field_leaves_the_weekdays_alone():
    """The patch rule: `quiet_hours_overrides` behaves like every other field."""
    user = with_zone(make_user())
    make_pro(user)
    client = signed_in(user)
    put(client, quiet_hours_overrides=SEVEN)

    put(client, quiet_hours={"start": "21:00", "end": "05:00"})

    assert overrides_of(user).count() == 7


# ── Atomicity and validation ───────────────────────────────────────────────────────


def test_a_week_whose_last_window_is_empty_writes_none_of_them():
    """The acceptance criterion's hard half: the server never sees a half-applied week."""
    user = with_zone(make_user())
    make_pro(user)
    client = signed_in(user)
    bad = [*SEVEN[:6], {"weekday": 6, "start": "09:00", "end": "09:00"}]

    response = put(client, quiet_hours_overrides=bad)

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_quiet_hours_window"
    assert overrides_of(user).count() == 0


def test_a_failed_week_does_not_strand_an_earlier_week():
    user = with_zone(make_user())
    make_pro(user)
    client = signed_in(user)
    put(client, quiet_hours_overrides=SEVEN)

    put(client, quiet_hours_overrides=[{"weekday": 6, "start": "09:00", "end": "09:00"}])

    assert overrides_of(user).count() == 7


def test_two_windows_for_one_weekday_are_refused():
    user = with_zone(make_user())
    make_pro(user)
    client = signed_in(user)

    response = put(
        client,
        quiet_hours_overrides=[
            {"weekday": MONDAY, "start": "22:00", "end": "08:00"},
            {"weekday": MONDAY, "start": "23:00", "end": "09:00"},
        ],
    )

    assert response.status_code == 422
    assert overrides_of(user).count() == 0


@pytest.mark.parametrize("weekday", [-1, 7])
def test_a_weekday_outside_the_week_is_refused(weekday):
    user = with_zone(make_user())
    make_pro(user)
    client = signed_in(user)

    response = put(
        client, quiet_hours_overrides=[{"weekday": weekday, "start": "22:00", "end": "08:00"}]
    )

    assert response.status_code == 422


# ── The lapse ──────────────────────────────────────────────────────────────────────


def test_a_lapsed_account_still_reads_its_seven_windows():
    """The acceptance criterion. The rows are the user's data and are never deleted."""
    user = with_zone(make_user())
    subscription = make_pro(user)
    client = signed_in(user)
    put(client, quiet_hours_overrides=SEVEN)

    subscription.status = SubscriptionStatus.CANCELED
    subscription.save(using=PERSONAL)

    body = client.get(SETTINGS_URL).json()
    assert len(body["quiet_hours_overrides"]) == 7


def test_a_lapsed_accounts_effective_week_is_its_base_window_not_its_stored_windows():
    """What stops a lapsed user being shown seven windows that are not in force.

    This is the carried risk from `per-day-quiet-hours-domain-and-model`'s review: a lapse
    silently returns a user to their base window. The response reports both, so the screen
    can show what was stored *and* what applies.
    """
    user = with_zone(make_user())
    subscription = make_pro(user)
    client = signed_in(user)
    put(client, quiet_hours={"start": "22:00", "end": "08:00"})
    put(client, quiet_hours_overrides=SEVEN)

    subscription.status = SubscriptionStatus.CANCELED
    subscription.save(using=PERSONAL)

    body = client.get(SETTINGS_URL).json()
    assert len(body["quiet_hours_overrides"]) == 7
    for day in body["effective_quiet_hours"]:
        assert day["quiet_hours"] == {"start": "22:00:00", "end": "08:00:00"}


def test_a_lapsed_account_cannot_write_its_windows():
    user = with_zone(make_user())
    subscription = make_pro(user)
    client = signed_in(user)
    put(client, quiet_hours_overrides=SEVEN)
    subscription.status = SubscriptionStatus.CANCELED
    subscription.save(using=PERSONAL)

    response = put(
        client, quiet_hours_overrides=[{"weekday": MONDAY, "start": "01:00", "end": "02:00"}]
    )

    assert response.status_code == 409
    assert response.json()["code"] == "quiet_hours_pro_required"
    # And the stored week is untouched by the refusal.
    assert overrides_of(user).count() == 7


# ── Auth and scoping ────────────────────────────────────────────────────────────────


def test_an_anonymous_caller_cannot_set_weekday_windows():
    response = CsrfClient().put(
        SETTINGS_URL,
        data={"quiet_hours_overrides": SEVEN},
        content_type="application/json",
    )

    assert response.status_code in (401, 403)


def test_one_users_windows_are_not_another_users():
    owner = with_zone(make_user("owner@example.test"))
    make_pro(owner)
    put(signed_in(owner), quiet_hours_overrides=SEVEN)

    intruder = with_zone(make_user("intruder@example.test"))

    body = signed_in(intruder).get(SETTINGS_URL).json()
    assert body["quiet_hours_overrides"] == []
