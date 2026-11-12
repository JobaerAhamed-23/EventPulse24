"""The paid path closes — and cancelling closes every gate again.

**What this file is for.** The fourteen items before it each proved their own piece against
its own seam: the subscription row, the adapter, the checkout, four caps, five surfaces. This
file proves the **claim the intent was captured on** — that a Free user can hit a wall, pay,
and find all four Pro capabilities genuinely unlocked, and that a cancellation closes every
one of them again **without deleting anything the user made**.

**Every step is driven through the surface a real actor would touch.**

- The user saves through `POST /api/personal/saved-events/{id}`, signed in, with CSRF — not
  by calling `save_event`.
- Checkout starts through `POST /api/billing/checkout`.
- **Entitlement arrives only through `POST /api/webhooks/billing`**, signed. Nothing else in
  this product can grant Pro, and `TestTheWebhookIsTheOnlyGrant` is the test that says so.
- The four capabilities are exercised through their own endpoints, and FR-51 is asserted at
  the **instant a send is deferred to**, not at a feature flag.
- Cancellation arrives as another webhook.

**No Stripe, no network, no secrets.** `FakeBillingAdapter` and `InMemoryThrottleAdapter`,
so CI runs this unchanged.

**Every instant is relative to `timezone.now()`.** Seventeen tests in this repository fail
today because their fixtures hard-code dates that have since passed — the count grew from 16
to 17 *during* this run, with no code change. Nothing here can join them.

**Nothing in `apps/`, `domain/` or `worker/` is modified by this item.** If a journey finds
a defect, it is a finding and gets a test that asserts the broken behaviour, as
`trust-loop`'s proof did with `TestTheStrandedEventGetsOut`.
"""

import json
from datetime import UTC, datetime, time, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from adapters.billing.fake import FAKE_SIGNATURE
from adapters.throttle.memory import InMemoryThrottleAdapter
from apps.delivery.models import NotificationPreference, QuietHoursOverride, ScheduledSend
from apps.identity.models import DataExport, Subscription, SubscriptionStatus
from apps.personalization.models import (
    CalendarConnection,
    SavedCollection,
    SavedCollectionItem,
    SavedEvent,
)
from apps.personalization.services import save_cap as save_cap_service
from ports.billing import BillingEventKind, ProPlan
from shared.db import CATALOG, PERSONAL
from shared.ids import uuid7
from tests.csrf import CsrfClient
from tests.identity.factories import SubscriptionFactory
from tests.ingestion.factories import EventFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

User = get_user_model()
JSON = "application/json"

WEBHOOK = "/api/webhooks/billing"
CHECKOUT = "/api/billing/checkout"
ACCOUNT = "/api/billing/account"
COLLECTIONS = "/api/personal/collections"
CALENDARS = "/api/personal/calendars"
SETTINGS = "/api/settings/notifications"
EXPORTS = "/api/exports"

#: Four distinct calendar addresses. Each must differ, or the "already connected" refusal
#: would fire before the cap and the test would pass for the wrong reason.
CALENDAR_URLS = (
    "https://example.com/one/basic.ics",
    "https://example.com/two/basic.ics",
    "https://example.com/three/basic.ics",
    "https://example.com/four/basic.ics",
)

#: A fixed instant for the throttle's own clock, so the save window is deterministic
#: without pinning any *calendar* date.
THROTTLE_CLOCK = 1_000_000.0


def far_future(days: int) -> datetime:
    """An instant comfortably ahead of the run, on a known weekday-independent offset.

    Relative, never hard-coded — see the module docstring.
    """
    return (timezone.now() + timedelta(days=days)).replace(
        hour=3, minute=30, second=0, microsecond=0
    )


def make_user() -> User:
    return User.objects.create_user(email=f"user-{uuid7()}@example.test", password="pw")


def signed_in(user) -> CsrfClient:
    client = CsrfClient()
    client.force_login(user)
    return client


def public_event(**overrides):
    """A published, upcoming catalog event — the only kind that is saveable.

    **The end time is always set.** An event with no end is *open-ended*, so two of them
    would overlap and the second save would answer 409 for a scheduling conflict rather
    than for the cap this test is about.
    """
    start = overrides.pop("start_time_utc", far_future(30))
    return EventFactory(start_time_utc=start, end_time_utc=start + timedelta(hours=2), **overrides)


def save(client, event_id):
    return client.post(f"/api/personal/saved-events/{event_id}")


def connect(client, address, provider="google"):
    return client.post(
        CALENDARS,
        data=json.dumps({"provider": provider, "address": address, "display_label": ""}),
        content_type=JSON,
    )


def webhook(client, body: dict, *, signature: str = FAKE_SIGNATURE):
    return client.post(
        WEBHOOK, data=json.dumps(body), content_type=JSON, HTTP_STRIPE_SIGNATURE=signature
    )


def started_event(user_id, *, event_id="evt_start", ref="sub_e2e", at=None, plan=ProPlan.MONTHLY):
    return {
        "kind": BillingEventKind.SUBSCRIPTION_STARTED.value,
        "event_id": event_id,
        "occurred_at": int((at or timezone.now()).timestamp()),
        "customer_ref": "cus_e2e",
        "subscription_ref": ref,
        "user_id": str(user_id),
        "plan": plan.value,
    }


def ended_event(user_id, *, event_id="evt_end", ref="sub_e2e", at=None):
    return {
        "kind": BillingEventKind.SUBSCRIPTION_ENDED.value,
        "event_id": event_id,
        "occurred_at": int((at or timezone.now()).timestamp()),
        "customer_ref": "cus_e2e",
        "subscription_ref": ref,
        "user_id": str(user_id),
    }


@pytest.fixture
def throttle(monkeypatch):
    """The in-memory throttle, pinned to one instance with a clock the test owns.

    The save cap is a throttle, so the window has to be deterministic — but it is the
    *throttle's* clock, not the calendar, so nothing here ages.
    """
    adapter = InMemoryThrottleAdapter(now=lambda: THROTTLE_CLOCK)
    monkeypatch.setattr(save_cap_service, "get_throttle_port", lambda: adapter)
    return adapter


class TestThePaidPathCloses:
    """Free → the wall → pay → the webhook → all four capabilities, in one test."""

    def test_the_whole_paid_path(self, throttle):
        user = make_user()
        client = signed_in(user)
        first, second = public_event(), public_event(start_time_utc=far_future(40))

        # ── 1. The free tier works, once ────────────────────────────────────────────
        assert save(client, first.id).status_code == 201

        # ── 2. The wall, with the inline prompt ─────────────────────────────────────
        refused = save(client, second.id)
        assert refused.status_code == 409
        body = refused.json()
        assert body["code"] == "save_cap_reached"
        assert body["details"]["upgrade_hint"]
        # The prompt is inline: nothing in the payload can make it an interruption.
        assert set(body["details"]) == {"cap", "upgrade_hint"}

        # ── 3. The account screen agrees they are Free ──────────────────────────────
        assert client.get(ACCOUNT).json()["is_pro"] is False

        # ── 4. Checkout starts, and grants nothing by itself ────────────────────────
        checkout = client.post(
            CHECKOUT, data=json.dumps({"plan": ProPlan.MONTHLY.value}), content_type=JSON
        )
        assert checkout.status_code == 200
        assert checkout.json()["url"]
        assert client.get(ACCOUNT).json()["is_pro"] is False, (
            "starting a checkout granted entitlement; only the webhook may do that"
        )

        # ── 5. The webhook lands. This is the only thing that grants Pro ────────────
        assert webhook(client, started_event(user.pk)).status_code == 200
        assert client.get(ACCOUNT).json()["is_pro"] is True

        # ── 6. The second save now succeeds ─────────────────────────────────────────
        assert save(client, second.id).status_code == 201, "the cap did not lift on upgrade"

        # ── 7. FR-50: a second and a third calendar provider ────────────────────────
        for address in CALENDAR_URLS[:3]:
            assert connect(client, address).status_code == 201
        assert CalendarConnection.objects.using(PERSONAL).filter(user_id=user.pk).count() == 3

        # ── 8. FR-49: a collection, with an event in it ─────────────────────────────
        created = client.post(
            COLLECTIONS, data=json.dumps({"name": "Music this month"}), content_type=JSON
        )
        assert created.status_code == 201, created.content
        collection_id = created.json()["id"]
        saved_row = SavedEvent.objects.using(PERSONAL).filter(user_id=user.pk).first()
        assert saved_row is not None
        assert client.put(f"{COLLECTIONS}/{collection_id}/events/{saved_row.id}").status_code == 204
        assert client.get(COLLECTIONS).json()[0]["item_count"] == 1

        # ── 9. FR-51: seven windows, written in one request ─────────────────────────
        overrides = [{"weekday": day, "start": "23:00:00", "end": "07:00:00"} for day in range(7)]
        settings_response = client.put(
            SETTINGS, data=json.dumps({"quiet_hours_overrides": overrides}), content_type=JSON
        )
        assert settings_response.status_code == 200, settings_response.content
        assert len(settings_response.json()["quiet_hours_overrides"]) == 7
        # The effective week is what the delivery path will actually apply.
        assert len(settings_response.json()["effective_quiet_hours"]) == 7

        # ── 10. FR-52: an export is requested ───────────────────────────────────────
        export = client.post(EXPORTS, data=json.dumps({}), content_type=JSON)
        assert export.status_code == 202, export.content
        assert DataExport.objects.using(PERSONAL).filter(user_id=user.pk).count() == 1

    def test_a_weekday_window_defers_a_send_to_the_windows_end(self):
        """**FR-51 asserted at the instant, not at the feature.**

        A reminder due inside a weekday's quiet window must be deferred to that window's
        end. This drives the real path — `scheduled_sends` applies
        `effective_quiet_hours` through `shift_to_sendable` — rather than asserting that a
        column was written.
        """
        from apps.delivery.services.notification_preferences import (
            set_quiet_hours,
        )
        from apps.personalization.services.personal_events import create_personal_event
        from domain.quiet_hours import QuietHours
        from shared.actor import Actor
        from tests.personalization.factories import DigestPreferenceFactory

        user = make_user()
        actor = Actor.user(user.pk)
        now = timezone.now()
        # **The zone read needs something to return.** A send's `due_at` is a shift of a
        # *local* wall clock, so a user with no digest preference has no zone and no send
        # is minted at all — which is how the first run of this test failed.
        DigestPreferenceFactory(user_id=user.pk, timezone="UTC")

        # Quiet every night 23:00–07:00, and on *one* weekday a much wider window.
        set_quiet_hours(
            user_id=user.pk,
            window=QuietHours(start=time(23, 0), end=time(7, 0)),
            actor=actor,
            now=now,
        )

        # An event far enough ahead that its 1-day reminder is still in the future.
        start = far_future(21)
        created = create_personal_event(
            user_id=user.pk,
            name="Gig",
            start_utc=start,
            end_utc=start + timedelta(hours=2),
            start_time_tz="UTC",
            location="",
            notes="",
            actor=actor,
            now=now,
        )
        # `create_personal_event` answers with a result, not a row: `Created` carries the
        # snapshot, and `ConflictFound` would carry a prompt instead.
        event = created.event

        # **The plan goes through the API, and that is not incidental.**
        # `set_plan_slots` only re-times sends when handed a `send_target`, which only the
        # caller holding the event can supply — `delivery` may not read
        # `apps.personalization.models` (AD-3). Called directly it updates the plan and
        # mints nothing, which is how the first run of this test found an empty table.
        client = signed_in(user)
        plan_url = f"/api/reminders/personal_event/{event.id}"
        assert (
            client.put(plan_url, data=json.dumps({"slots": ["1d"]}), content_type=JSON).status_code
            == 200
        )

        # The reminder a day before lands at 03:30 UTC — inside the base window.

        base_due = (
            ScheduledSend.objects.using(PERSONAL)
            .filter(user_id=user.pk, target_id=event.id, slot="1d")
            .values_list("due_at", flat=True)
            .first()
        )
        assert base_due is not None
        # Deferred out of the night window to its 07:00 end.
        assert base_due.astimezone(UTC).hour == 7, (
            f"the base quiet window did not defer the send; due at {base_due}"
        )

        # ── Now the Pro variant ────────────────────────────────────────────────────
        #
        # **Two things the first run of this test got wrong, both of them real rules.**
        #
        # 1. **Overrides only apply to a Pro account.** `_effective_week` reads entitlement
        #    and falls back to the base window otherwise, so writing them for a Free user
        #    changes no send — the lapse behaviour this intent promises, seen from the
        #    other side.
        # 2. **A day's window begins on that day.** A 23:00–09:00 window set for Friday
        #    owns *Saturday's* small hours, so the window governing a 03:30 send is the
        #    previous night's — not the one whose weekday the instant falls on.
        #
        # All seven days get the wider window, so this asserts that the override takes
        # effect rather than which night owns the instant; that selection is pinned by
        # `test_weekly_quiet_hours.py`'s eighteen domain tests.
        SubscriptionFactory(user_id=user.pk)
        # **Through the settings API, not the command.** `apply_settings_patch` wraps the
        # write and `reschedule_pending_for_user` in one transaction — AD-7's *"a preference
        # change rewrites `due_at` on pending rows"*. Calling `replace_quiet_hours_overrides`
        # directly writes the windows and re-times nothing, so the send kept its old instant
        # and this test read 07:00 for a third time before the real path was used.
        assert (
            client.put(
                SETTINGS,
                data=json.dumps(
                    {
                        "quiet_hours_overrides": [
                            {"weekday": day, "start": "23:00:00", "end": "09:00:00"}
                            for day in range(7)
                        ]
                    }
                ),
                content_type=JSON,
            ).status_code
            == 200
        )

        weekday_due = (
            ScheduledSend.objects.using(PERSONAL)
            .filter(user_id=user.pk, target_id=event.id, slot="1d")
            .values_list("due_at", flat=True)
            .first()
        )
        assert weekday_due is not None
        assert weekday_due.astimezone(UTC).hour == 9, (
            f"the weekday window did not override the base one; due at {weekday_due}"
        )


class TestCancellationClosesEveryGate:
    """The half that is easier to get wrong: every gate closes, and nothing is deleted."""

    @pytest.fixture
    def pro_with_everything(self, throttle):
        """A user who has accumulated data under all four capabilities, then cancels.

        **This is the first time in the intent that a downgrade happens to a user holding
        data from every capability at once.** Each item proved "never delete" in isolation.
        """
        user = make_user()
        client = signed_in(user)
        webhook(client, started_event(user.pk))

        for address in CALENDAR_URLS[:3]:
            assert connect(client, address).status_code == 201

        created = client.post(COLLECTIONS, data=json.dumps({"name": "Weekend"}), content_type=JSON)
        collection_id = created.json()["id"]
        event = public_event()
        assert save(client, event.id).status_code == 201
        saved_row = SavedEvent.objects.using(PERSONAL).filter(user_id=user.pk).get()
        assert client.put(f"{COLLECTIONS}/{collection_id}/events/{saved_row.id}").status_code == 204

        client.put(
            SETTINGS,
            data=json.dumps(
                {
                    "quiet_hours_overrides": [
                        {"weekday": day, "start": "23:00:00", "end": "07:00:00"} for day in range(7)
                    ]
                }
            ),
            content_type=JSON,
        )

        assert webhook(client, ended_event(user.pk)).status_code == 200
        return user, client, collection_id, saved_row

    def test_entitlement_is_gone(self, pro_with_everything):
        _user, client, _collection_id, _saved = pro_with_everything

        assert client.get(ACCOUNT).json()["is_pro"] is False

    def test_a_fourth_provider_is_refused(self, pro_with_everything):
        _user, client, _collection_id, _saved = pro_with_everything

        response = connect(client, CALENDAR_URLS[3])

        assert response.status_code == 409
        assert response.json()["code"] == "calendar_cap_reached"

    def test_a_new_collection_is_refused(self, pro_with_everything):
        _user, client, _collection_id, _saved = pro_with_everything

        response = client.post(COLLECTIONS, data=json.dumps({"name": "Gigs"}), content_type=JSON)

        assert response.status_code == 409
        assert response.json()["code"] == "collections_pro_required"

    def test_the_save_cap_applies_again_once_the_free_allowance_is_spent(self, pro_with_everything):
        """**The gate closes, but not retroactively — and the first run of this test got
        that wrong.**

        A Pro user *"is never refused and never spends a slot"* (`save_cap.py`), so a user
        who lapses has an untouched Free allowance: their next save succeeds, and the one
        after it is refused. Asserting a refusal on the first save would have been asserting
        that lapsing confiscates a day's allowance the user never used, which is not what
        the cap says and not what it should say.
        """
        _user, client, _collection_id, _saved = pro_with_everything
        allowed = public_event(start_time_utc=far_future(45))
        refused = public_event(start_time_utc=far_future(50))

        assert save(client, allowed.id).status_code == 201, (
            "a lapsed account was refused the Free allowance it had not spent"
        )

        response = save(client, refused.id)

        assert response.status_code == 409
        assert response.json()["code"] == "save_cap_reached"

    def test_setting_weekday_windows_again_is_refused(self, pro_with_everything):
        _user, client, _collection_id, _saved = pro_with_everything

        response = client.put(
            SETTINGS,
            data=json.dumps(
                {"quiet_hours_overrides": [{"weekday": 0, "start": "22:00:00", "end": "06:00:00"}]}
            ),
            content_type=JSON,
        )

        assert response.status_code == 409
        assert response.json()["code"] == "quiet_hours_pro_required"

    # ── …and nothing the user made is gone ──────────────────────────────────────────

    def test_the_calendar_connections_survive(self, pro_with_everything):
        user, _client, _collection_id, _saved = pro_with_everything

        assert CalendarConnection.objects.using(PERSONAL).filter(user_id=user.pk).count() == 3

    def test_the_collection_and_its_membership_survive(self, pro_with_everything):
        user, _client, collection_id, _saved = pro_with_everything

        assert SavedCollection.objects.using(PERSONAL).filter(user_id=user.pk).count() == 1
        assert (
            SavedCollectionItem.objects.using(PERSONAL).filter(collection_id=collection_id).count()
            == 1
        )

    def test_the_saves_survive(self, pro_with_everything):
        user, _client, _collection_id, _saved = pro_with_everything

        assert SavedEvent.objects.using(PERSONAL).filter(user_id=user.pk).count() == 1

    def test_the_seven_windows_survive(self, pro_with_everything):
        """**The brief's constraint, literally.** The rows are the user's; what a lapse
        removes is their effect, which `effective_quiet_hours` reports honestly."""
        user, _client, _collection_id, _saved = pro_with_everything

        assert QuietHoursOverride.objects.using(PERSONAL).filter(user_id=user.pk).count() == 7

    def test_the_lapsed_user_can_still_read_all_of_it(self, pro_with_everything):
        _user, client, collection_id, _saved = pro_with_everything

        assert len(client.get(COLLECTIONS).json()) == 1
        assert len(client.get(f"{COLLECTIONS}/{collection_id}/events").json()) == 1
        assert len(client.get(CALENDARS).json()["items"]) == 3
        settings = client.get(SETTINGS).json()
        assert len(settings["quiet_hours_overrides"]) == 7

    def test_the_lapsed_users_effective_week_is_their_base_window(self, pro_with_everything):
        """Reporting the stored windows alone would show seven windows that are not in
        force; reporting only the effective week would look like the lapse deleted them."""
        _user, client, _collection_id, _saved = pro_with_everything

        settings = client.get(SETTINGS).json()

        assert len(settings["quiet_hours_overrides"]) == 7
        effective = settings["effective_quiet_hours"]
        windows = {json.dumps(entry["quiet_hours"], sort_keys=True) for entry in effective}
        assert len(windows) == 1, "a lapsed account's week is not uniform; overrides still apply"

    def test_the_lapsed_user_can_still_tidy_up(self, pro_with_everything):
        """Unassign, rename and delete stay open — gating them would trap somebody with an
        arrangement they cannot change."""
        _user, client, collection_id, saved = pro_with_everything

        assert client.delete(f"{COLLECTIONS}/{collection_id}/events/{saved.id}").status_code == 204
        assert (
            client.patch(
                f"{COLLECTIONS}/{collection_id}",
                data=json.dumps({"name": "Weekends"}),
                content_type=JSON,
            ).status_code
            == 200
        )
        assert client.delete(f"{COLLECTIONS}/{collection_id}").status_code == 204

    def test_the_subscription_row_is_a_transition_not_a_deletion(self, pro_with_everything):
        """`BILLING_RECORDS` keeps these for seven years; a lapse is a status change."""
        user, _client, _collection_id, _saved = pro_with_everything

        rows = list(Subscription.objects.using(PERSONAL).filter(user_id=user.pk))

        assert len(rows) == 1
        assert rows[0].status == SubscriptionStatus.CANCELED


class TestTheWebhookIsTheOnlyGrant:
    def test_returning_from_a_successful_checkout_grants_nothing(self, throttle):
        """**The property an open-redirect-shaped bug would break.** The success URL is
        under the client's control; if returning to it granted Pro, anyone could visit it."""
        user = make_user()
        client = signed_in(user)

        checkout = client.post(
            CHECKOUT, data=json.dumps({"plan": ProPlan.MONTHLY.value}), content_type=JSON
        )
        assert checkout.status_code == 200
        # The user follows the success URL. No webhook has been delivered.
        client.get("/")

        assert client.get(ACCOUNT).json()["is_pro"] is False
        assert Subscription.objects.using(PERSONAL).filter(user_id=user.pk).count() == 0

    def test_an_unsigned_webhook_grants_nothing(self):
        user = make_user()
        client = signed_in(user)

        response = webhook(client, started_event(user.pk), signature="not-the-signature")

        assert response.status_code == 400
        assert client.get(ACCOUNT).json()["is_pro"] is False


class TestTheReplayAndTheRace:
    def test_a_replayed_grant_does_not_create_a_second_subscription(self):
        user = make_user()
        client = signed_in(user)
        event = started_event(user.pk)

        assert webhook(client, event).status_code == 200
        assert webhook(client, event).status_code == 200

        assert Subscription.objects.using(PERSONAL).filter(user_id=user.pk).count() == 1
        assert client.get(ACCOUNT).json()["is_pro"] is True

    def test_a_stale_update_after_a_cancellation_does_not_restore_entitlement(self):
        """**The race `Subscription.last_event_at` exists for.** Stripe retries, replays and
        reorders; a naive writer lets an older `updated` overwrite a newer `deleted` and
        silently restores Pro to somebody who cancelled."""
        user = make_user()
        client = signed_in(user)
        early = timezone.now() - timedelta(minutes=10)
        late = timezone.now()

        webhook(client, started_event(user.pk, at=early - timedelta(minutes=5)))
        assert webhook(client, ended_event(user.pk, event_id="evt_end", at=late)).status_code == 200
        assert client.get(ACCOUNT).json()["is_pro"] is False

        # A subscription-updated event that was *generated before* the cancellation now
        # arrives late.
        stale = {
            "kind": BillingEventKind.SUBSCRIPTION_CHANGED.value,
            "event_id": "evt_stale",
            "occurred_at": int(early.timestamp()),
            "customer_ref": "cus_e2e",
            "subscription_ref": "sub_e2e",
            "user_id": str(user.pk),
            "plan": ProPlan.MONTHLY.value,
            "status": SubscriptionStatus.ACTIVE.value,
        }
        webhook(client, stale)

        assert client.get(ACCOUNT).json()["is_pro"] is False, (
            "a stale update restored entitlement to a cancelled account"
        )


class TestTheRefusalsShareOneShape:
    """Four gates, one inline prompt. A new shape would mean a new component."""

    def test_every_cap_refusal_carries_the_same_payload(self, throttle):
        user = make_user()
        client = signed_in(user)
        first, second = public_event(), public_event(start_time_utc=far_future(40))
        save(client, first.id)

        payloads = []

        payloads.append(save(client, second.id).json())
        connect(client, CALENDAR_URLS[0])
        payloads.append(connect(client, CALENDAR_URLS[1]).json())
        payloads.append(
            client.post(COLLECTIONS, data=json.dumps({"name": "X"}), content_type=JSON).json()
        )
        payloads.append(
            client.put(
                SETTINGS,
                data=json.dumps(
                    {
                        "quiet_hours_overrides": [
                            {"weekday": 0, "start": "22:00:00", "end": "06:00:00"}
                        ]
                    }
                ),
                content_type=JSON,
            ).json()
        )

        assert len(payloads) == 4
        for payload in payloads:
            assert set(payload["details"]) == {"cap", "upgrade_hint"}, payload
            assert payload["details"]["upgrade_hint"], payload
            for modal_shaped in ("modal", "title", "actions", "dismissable"):
                assert modal_shaped not in payload["details"]


def test_a_user_with_no_preference_row_still_has_one_after_reading_settings():
    """A guard on the fixture above rather than on the product: `get_preference` creates
    the row on first read, so the seven-window assertions are about writes and not about
    a row springing into existence."""
    user = make_user()
    client = signed_in(user)

    client.get(SETTINGS)

    assert NotificationPreference.objects.using(PERSONAL).filter(user_id=user.pk).exists()
