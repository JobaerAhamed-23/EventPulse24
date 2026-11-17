"""The Pulse Ping switch (FR-10): a user can turn the daily digest off, and back on.

**Why "and back on" is the point.** `unsubscribe_pulse_ping` has existed since FR-11,
because the RFC 8058 one-click link needs it — and a one-click unsubscribe is one-way by
definition, so nothing in the product could ever clear the flag. Onboarding has told every
new user *"One calm Pulse Ping per day… You can change this anytime"* the whole time. This
file holds the half that makes that sentence true.

**The scope split is tested here too**, because it is the thing most easily broken by a
settings screen: turning the daily digest off must leave every event reminder alone.
"""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.delivery.models import NotificationPreference, ScheduledSend
from apps.delivery.services.notification_preferences import get_preference
from apps.delivery.services.preferences import SettingsPatch, apply_settings_patch
from apps.delivery.services.preferences_read import read_notification_settings
from apps.delivery.services.unsubscribes import (
    resubscribe_pulse_ping,
    unsubscribe_pulse_ping,
)
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from tests.csrf import CsrfClient
from tests.delivery.factories import ScheduledSendFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

User = get_user_model()

#: The test's clock, **taken from the real one**.
#:
#: A literal here would be a time bomb of exactly the kind `time-bomb-tests` was opened
#: for: the pending digest row below is dated relative to `NOW`, and once the wall clock
#: passed a fixed `NOW` that row would be in the past while the HTTP writes scheduled
#: against the real clock. The two would disagree, and the failure would look like a
#: regression in code nobody had touched.
NOW = timezone.now().replace(microsecond=0)
SETTINGS_URL = "/api/settings/notifications"


def make_user(email="ping@example.test"):
    return User.objects.create_user(email=email, password="pw")


def signed_in(user=None):
    client = CsrfClient()
    client.force_login(user or make_user())
    return client


def put(client, body: dict):
    """A `PUT` of `body` as JSON — the shape `test_preferences_api.py` uses."""
    return client.put(SETTINGS_URL, data=body, content_type="application/json")


def _actor(user) -> Actor:
    return Actor.user(user.pk)


def _flag(user_id) -> bool:
    return (
        NotificationPreference.objects.using(PERSONAL).get(user_id=user_id).pulse_ping_unsubscribed
    )


class TestTheCommandPair:
    def test_turning_it_off_sets_the_opt_out(self):
        user = make_user()
        result = unsubscribe_pulse_ping(user_id=user.pk, actor=_actor(user), now=NOW)

        assert result.changed is True
        assert _flag(user.pk) is True

    def test_turning_it_back_on_clears_the_opt_out(self):
        user = make_user()
        unsubscribe_pulse_ping(user_id=user.pk, actor=_actor(user), now=NOW)

        result = resubscribe_pulse_ping(user_id=user.pk, actor=_actor(user), now=NOW)

        assert result.changed is True
        assert _flag(user.pk) is False

    def test_turning_on_a_ping_that_is_already_on_is_a_no_op(self):
        """Not an error. A switch pressed twice is a user being sure, not a conflict."""
        user = make_user()
        get_preference(user_id=user.pk)

        result = resubscribe_pulse_ping(user_id=user.pk, actor=_actor(user), now=NOW)

        assert result.changed is False
        assert _flag(user.pk) is False

    def test_turning_it_back_on_does_not_resurrect_cancelled_sends(self):
        """A cancelled digest was for a day that has passed. Delivering it now would be a
        digest about yesterday — the next tick mints a fresh one instead."""
        user = make_user()
        ScheduledSendFactory(
            kind=ScheduledSend.Kind.DIGEST,
            user_id=user.pk,
            target_kind="",
            target_id=None,
            slot="",
            event_version=None,
            due_at=NOW + timedelta(hours=1),
        )
        off = unsubscribe_pulse_ping(user_id=user.pk, actor=_actor(user), now=NOW)
        assert off.cancelled == 1

        back_on = resubscribe_pulse_ping(user_id=user.pk, actor=_actor(user), now=NOW)

        assert back_on.cancelled == 0
        assert (
            ScheduledSend.objects.using(PERSONAL)
            .filter(user_id=user.pk, status=ScheduledSend.Status.PENDING)
            .count()
            == 0
        )


class TestThePatch:
    def test_an_omitted_field_leaves_the_ping_alone(self):
        """The patch rule, for this field as for every other."""
        user = make_user()
        unsubscribe_pulse_ping(user_id=user.pk, actor=_actor(user), now=NOW)

        apply_settings_patch(
            user_id=user.pk,
            patch=SettingsPatch(default_reminder_slots=("1d",)),
            actor=_actor(user),
            now=NOW,
        )

        assert _flag(user.pk) is True

    def test_the_patch_turns_it_off(self):
        user = make_user()

        apply_settings_patch(
            user_id=user.pk,
            patch=SettingsPatch(pulse_ping=False),
            actor=_actor(user),
            now=NOW,
        )

        assert _flag(user.pk) is True

    def test_the_patch_turns_it_on(self):
        user = make_user()
        unsubscribe_pulse_ping(user_id=user.pk, actor=_actor(user), now=NOW)

        apply_settings_patch(
            user_id=user.pk,
            patch=SettingsPatch(pulse_ping=True),
            actor=_actor(user),
            now=NOW,
        )

        assert _flag(user.pk) is False


class TestTheScopesNeverTouch:
    def test_turning_the_ping_off_leaves_the_reminders_alone(self):
        """FR-11's split: the digest's unsubscribe stops the digest. A settings screen
        that quietly cancelled a user's event reminders would be the worst kind of bug —
        silent, and about mail that never arrives."""
        user = make_user()
        reminder = ScheduledSendFactory(
            kind=ScheduledSend.Kind.EVENT_REMINDER,
            user_id=user.pk,
            due_at=NOW + timedelta(hours=2),
        )

        apply_settings_patch(
            user_id=user.pk,
            patch=SettingsPatch(pulse_ping=False),
            actor=_actor(user),
            now=NOW,
        )

        reminder.refresh_from_db(using=PERSONAL)
        assert reminder.status == ScheduledSend.Status.PENDING


class TestTheWire:
    def test_the_read_reports_the_ping_as_on_by_default(self):
        """Stored as an opt-out, reported as "is it on" — the inversion happens once."""
        user = make_user()

        view = read_notification_settings(user_id=user.pk)

        assert view.pulse_ping is True

    def test_the_read_reports_the_ping_as_off_once_turned_off(self):
        user = make_user()
        unsubscribe_pulse_ping(user_id=user.pk, actor=_actor(user), now=NOW)

        assert read_notification_settings(user_id=user.pk).pulse_ping is False

    def test_the_get_carries_the_ping(self):
        user = make_user()
        response = signed_in(user).get(SETTINGS_URL)

        assert response.status_code == 200
        assert response.json()["pulse_ping"] is True

    def test_the_put_turns_it_off_and_the_response_says_so(self):
        user = make_user()
        client = signed_in(user)

        response = put(client, {"pulse_ping": False})

        assert response.status_code == 200
        assert response.json()["pulse_ping"] is False
        assert _flag(user.pk) is True

    def test_the_put_round_trips_back_on(self):
        user = make_user()
        client = signed_in(user)
        put(client, {"pulse_ping": False})

        response = put(client, {"pulse_ping": True})

        assert response.json()["pulse_ping"] is True
        assert _flag(user.pk) is False

    def test_a_put_that_does_not_mention_the_ping_leaves_it_off(self):
        user = make_user()
        client = signed_in(user)
        put(client, {"pulse_ping": False})

        response = put(client, {"default_reminder_slots": ["1d"]})

        assert response.json()["pulse_ping"] is False
