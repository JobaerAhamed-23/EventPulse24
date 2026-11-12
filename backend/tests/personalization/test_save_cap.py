"""The Free-tier save cap (FR-49): one save a day, and the calm prompt after it.

FR-49 is the **upgrade trigger**. "Free tier: 1 Pulse Card saved per 24-hour period", and
the second save in that window shows a calm upgrade prompt. Everything else in the Pro
tier — the pricing page, the upgrade prompts, the tier itself — is decoration around this
gate, so the gate is worth pinning hard.

What these tests pin:

- the **second distinct save in the window is refused**, and the first is not;
- the refusal is a **409 with `save_cap_reached`**, not a 429 — the remedy is to upgrade,
  not to retry;
- the payload is **exactly `{"cap", "upgrade_hint"}`** — no modal-shaped field, so a
  future edit that grows one fails here;
- **a refused save changes nothing** — no `SavedEvent` row, no audit entry, and the
  refusal does not extend the user's wait;
- the cap is declared through **`ThrottlePort.check(key, limit, window_seconds)`**, the
  same call `EventReport` makes — not a hand-rolled counter and not a row count;
- **a Pro user has no cap at all** — ten or more saves in a day, with no soft wall;
- a **repeat save of an already-saved event is not a new save**, so it is not gated;
- a **Pro user who lapses back to Free is refused again** — the gate reads entitlement at
  the moment of the save, not once at signup.

The throttle adapter is **pinned to one instance** on purpose. `ports.registry.get_adapter`
constructs a *new* adapter per call, and the in-memory fake keeps its counter in an
instance dict — so an unpinned fake would reset its counter on every request and the limit
could not be observed at all. In production the adapter is Redis-backed and the state lives
outside the instance, which is why a fresh instance per call is fine there. Here, the
single instance is what makes the port's own window visible.
"""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from adapters.throttle.memory import InMemoryThrottleAdapter
from apps.identity.models import Subscription, SubscriptionStatus
from apps.personalization.models import PersonalizationAuditEntry, SavedEvent
from apps.personalization.services import save_cap as save_cap_service
from shared.constants import (
    FREE_TIER_SAVE_DAILY_LIMIT,
    FREE_TIER_SAVE_WINDOW_SECONDS,
)
from shared.db import CATALOG, PERSONAL
from shared.ids import uuid7
from tests.csrf import CsrfClient
from tests.identity.factories import SubscriptionFactory
from tests.ingestion.factories import EventFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

User = get_user_model()

#: An instant that is always ahead of the run. Only an event that has not started is
#: saveable, and the wall clock is not injectable here — the endpoint reads
#: `timezone.now()` itself.
START = (timezone.now() + timedelta(days=30)).replace(hour=3, minute=30, second=0, microsecond=0)

#: A fixed moment for the throttle's clock, so the window is deterministic.
CLOCK = 1_000_000.0


def make_user(email=None):
    """A real user with a real pk — the session resolves to this one.

    The email is unique per call, because a test may need two users (the caller and
    somebody else), and the email column is unique.
    """
    if email is None:
        email = f"user-{uuid7()}@example.test"
    return User.objects.create_user(email=email, password="pw")


def signed_in(user=None):
    """A client whose session identifies `user`.

    It is a `CsrfClient`, because the endpoint resolves its user through `identity`'s
    resolver and the resolver checks CSRF on every unsafe method (D13).
    """
    client = CsrfClient()
    client.force_login(user or make_user())
    return client


def public_event(**overrides):
    """A published, upcoming catalog event — the only kind that is saveable.

    **The end time is set, and it matters.** An event with no `end_time_utc` is
    *open-ended* — `domain.conflict` reads a missing end as "runs to the end of
    representable time" — so two such events a day apart would still overlap, and the
    second save would answer 409 for the wrong reason. These tests are about the *cap*,
    so their events must not clash.
    """
    start = overrides.pop("start_time_utc", START)
    return EventFactory(start_time_utc=start, end_time_utc=start + timedelta(hours=2), **overrides)


def save(client, catalog_event_id):
    return client.post(f"/api/personal/saved-events/{catalog_event_id}")


@pytest.fixture
def clock():
    """The throttle's notion of now, so a test can walk the window boundary exactly."""
    return {"now": CLOCK}


@pytest.fixture
def throttle(monkeypatch, clock):
    """The in-memory throttle, pinned to one instance, with a clock the test owns."""
    adapter = InMemoryThrottleAdapter(now=lambda: clock["now"])
    monkeypatch.setattr(save_cap_service, "get_throttle_port", lambda: adapter)
    return adapter


def make_pro(user):
    """Give the user a live subscription, so `is_pro` reads true for them."""
    return SubscriptionFactory(user_id=user.pk)


def lapse(user):
    """End the user's subscription, so `is_pro` reads false again.

    **A lapse is a transition on the existing row, not a new row.** `Subscription` allows
    at most one live row per user and keeps the history as terminal rows, so adding a
    `CANCELED` row beside the `ACTIVE` one would leave the user still Pro — the live row
    is what `is_pro` reads.
    """
    Subscription.objects.using(PERSONAL).filter(user_id=user.pk).update(
        status=SubscriptionStatus.CANCELED
    )


# ── The gate ─────────────────────────────────────────────────────────────────────


def test_the_first_save_of_the_day_is_allowed(throttle):
    client = signed_in()
    event = public_event(start_time_utc=START)

    response = save(client, event.id)

    assert response.status_code == 201


def test_the_second_save_in_the_window_is_refused(throttle):
    """FR-49's own consequence: one save a day for Free."""
    client = signed_in()
    first = public_event(start_time_utc=START)
    second = public_event(start_time_utc=START + timedelta(days=1))

    assert save(client, first.id).status_code == 201

    response = save(client, second.id)

    assert response.status_code == 409


def test_the_refusal_is_a_conflict_and_not_a_rate_limit(throttle):
    """**The remedy is to upgrade, not to retry.**

    A 429 would say "come back later", and the user cannot: their window is a day. A 409
    says "your account's state refuses this", which is what is true.
    """
    client = signed_in()
    save(client, public_event(start_time_utc=START).id)

    response = save(client, public_event(start_time_utc=START + timedelta(days=1)).id)

    assert response.status_code == 409
    assert response.json()["code"] == "save_cap_reached"


def test_the_refusal_payload_is_exactly_the_cap_and_one_sentence(throttle):
    """**Exactly two fields, and nothing else.**

    No `modal`, no `title`, no `actions`, no `dismissable`: the refusal is an *inline*
    prompt with a quiet "Upgrade" link, not a modal (EXPERIENCE.md §3, the Free-tier
    save-cap prompt). The key set is pinned exactly, so a future edit that grows a
    modal-shaped field fails here.
    """
    client = signed_in()
    save(client, public_event(start_time_utc=START).id)

    response = save(client, public_event(start_time_utc=START + timedelta(days=1)).id)

    body = response.json()
    assert set(body) == {"code", "message", "details"}
    details = body["details"]
    assert set(details) == {"cap", "upgrade_hint"}
    assert details["cap"] == FREE_TIER_SAVE_DAILY_LIMIT
    assert details["upgrade_hint"] == "You saved one event today. Save more with Pro."
    assert "modal" not in str(details).lower()


def test_the_refusal_message_is_calm(throttle):
    """The UX voice: no exclamation mark, no urgency, no shouting."""
    client = signed_in()
    save(client, public_event(start_time_utc=START).id)

    response = save(client, public_event(start_time_utc=START + timedelta(days=1)).id)

    message = response.json()["message"]
    assert message == "You've used your free save for today."
    assert "!" not in message


# ── A refused save changes nothing ─────────────────────────────────────────────────


def test_a_refused_save_stores_no_row(throttle):
    user = make_user()
    client = signed_in(user)
    save(client, public_event(start_time_utc=START).id)
    second = public_event(start_time_utc=START + timedelta(days=1))

    save(client, second.id)

    rows = SavedEvent.objects.using(PERSONAL).filter(user_id=user.pk).count()
    assert rows == 1


def test_a_refused_save_writes_no_audit_entry(throttle):
    """**A refused save changes nothing** — not even a trace in the audit log.

    The gate refuses inside the transaction, before any write, so there is no command to
    audit. An audit row saying "we refused to save" would be a record of a save that never
    happened.
    """
    user = make_user()
    client = signed_in(user)
    save(client, public_event(start_time_utc=START).id)

    save(client, public_event(start_time_utc=START + timedelta(days=1)).id)

    entries = PersonalizationAuditEntry.objects.using(PERSONAL).filter(actor_id=user.pk)
    assert [entry.action for entry in entries] == ["saved_event.saved"]


def test_a_refusal_does_not_extend_the_wait(throttle, clock):
    """**A refused save costs the user no time.**

    Both throttle adapters count an attempt *before* deciding whether to allow it, and
    the window is anchored at the *first* attempt in it. So a refused save cannot push
    the user's window forward: the allowance frees up when the first save's window
    closes, whether or not the second attempt ever happened.
    """
    client = signed_in()
    save(client, public_event(start_time_utc=START).id)

    # The window is nearly over; the second save is refused.
    clock["now"] = CLOCK + FREE_TIER_SAVE_WINDOW_SECONDS - 10
    refused = save(client, public_event(start_time_utc=START + timedelta(days=1)).id)
    assert refused.status_code == 409

    # And it frees up once the *first* save's window closes — not a window after the
    # refusal.
    clock["now"] = CLOCK + FREE_TIER_SAVE_WINDOW_SECONDS + 1
    allowed = save(client, public_event(start_time_utc=START + timedelta(days=2)).id)
    assert allowed.status_code == 201


# ── The cap is the port's, not a hand-rolled counter ───────────────────────────────


def test_the_cap_is_declared_through_the_throttle_port(monkeypatch):
    """**The count is the throttle port's, not a row count.**

    The gate declares its limit through `ThrottlePort.check(key, limit, window_seconds)`
    — exactly as `EventReport` declares its own — with the limit and the window coming
    from `shared/constants.py`. A row count would make the cap depend on data the user
    can delete: unsaving an event would hand the allowance back.
    """
    calls: list[tuple[str, int, int]] = []

    class RecordingThrottle:
        def check(self, key: str, *, limit: int, window_seconds: int):
            calls.append((key, limit, window_seconds))
            from ports.throttle import ThrottleDecision

            return ThrottleDecision(allowed=True)

    monkeypatch.setattr(save_cap_service, "get_throttle_port", lambda: RecordingThrottle())
    user = make_user()
    client = signed_in(user)

    save(client, public_event(start_time_utc=START).id)

    assert len(calls) == 1
    key, limit, window = calls[0]
    assert key == f"save:{user.pk}"
    assert limit == FREE_TIER_SAVE_DAILY_LIMIT
    assert window == FREE_TIER_SAVE_WINDOW_SECONDS


def test_unsaving_does_not_hand_the_allowance_back(throttle):
    """**The gate counts attempts, not rows.**

    A row count would let a user unsave an event and save another, for ever. The throttle
    port counts the attempt, so the refusal stands even though the row is gone.
    """
    client = signed_in()
    first = public_event(start_time_utc=START)
    save(client, first.id)

    client.delete(f"/api/personal/saved-events/{first.id}")

    response = save(client, public_event(start_time_utc=START + timedelta(days=1)).id)
    assert response.status_code == 409


# ── Pro has no cap ────────────────────────────────────────────────────────────────


def test_a_pro_user_saves_ten_events_in_a_day(throttle):
    """FR-49's own testable consequence: **a Pro user saves 10+ events in one day with
    no soft wall.**"""
    user = make_user()
    make_pro(user)
    client = signed_in(user)

    for index in range(12):
        event = public_event(start_time_utc=START + timedelta(days=index))
        response = save(client, event.id)
        assert response.status_code == 201, f"save {index} was refused: {response.content}"


def test_a_pro_user_spends_no_throttle_slot(monkeypatch):
    """**The gate is skipped entirely for Pro, not made with a limit of infinity.**

    A Pro user's saves leave no trace in the counter at all, so no throttle slot is spent
    on a save that could never have been refused.
    """
    calls: list[str] = []

    class RecordingThrottle:
        def check(self, key: str, *, limit: int, window_seconds: int):
            calls.append(key)
            from ports.throttle import ThrottleDecision

            return ThrottleDecision(allowed=True)

    monkeypatch.setattr(save_cap_service, "get_throttle_port", lambda: RecordingThrottle())
    user = make_user()
    make_pro(user)
    client = signed_in(user)

    save(client, public_event(start_time_utc=START).id)

    assert calls == []


# ── The same row saved twice is not a new save ─────────────────────────────────────


def test_saving_the_same_event_again_is_not_gated(throttle):
    """**A repeat save is the same row returned again, not a new save.**

    The save is idempotent: the second POST returns the same record with a 200 and
    writes no second row. So it is not gated, and no throttle slot is spent on it — the
    allowance is for *new* saves.
    """
    client = signed_in()
    event = public_event(start_time_utc=START)
    save(client, event.id)

    response = save(client, event.id)

    assert response.status_code == 200
    assert SavedEvent.objects.using(PERSONAL).count() == 1


# ── Entitlement is read at the moment of the save ───────────────────────────────────


def test_a_pro_user_who_lapses_back_to_free_is_refused_again(throttle):
    """**The gate reads entitlement when the save happens, not once at signup.**

    A lapsed Pro user is a Free user, and the cap applies to them from the moment the
    subscription ends.

    **Their allowance is the Free allowance, spent from the moment they lapse.** A Pro
    user's save never reached the gate — no throttle slot is spent on a save that could
    never have been refused — so the lapsed user's first *gated* save is their first, and
    the second is refused.
    """
    user = make_user()
    make_pro(user)
    client = signed_in(user)
    assert save(client, public_event(start_time_utc=START).id).status_code == 201

    lapse(user)

    # The first save after the lapse is the first one the gate sees, so it is allowed.
    allowed = save(client, public_event(start_time_utc=START + timedelta(days=1)).id)
    assert allowed.status_code == 201

    # The second is refused, exactly as it would be for a user who was always Free.
    refused = save(client, public_event(start_time_utc=START + timedelta(days=2)).id)
    assert refused.status_code == 409
    assert refused.json()["code"] == "save_cap_reached"


def test_a_free_user_who_becomes_pro_is_allowed_again(throttle):
    """**The same user, once Pro, is allowed.** The cap follows the tier, not the account.

    The Free user has spent their allowance, and the upgrade is what opens the gate —
    which is the whole point of the gate.
    """
    user = make_user()
    client = signed_in(user)
    first = public_event(start_time_utc=START)
    assert save(client, first.id).status_code == 201
    assert (
        save(client, public_event(start_time_utc=START + timedelta(days=1)).id).status_code == 409
    )

    make_pro(user)

    response = save(client, public_event(start_time_utc=START + timedelta(days=2)).id)
    assert response.status_code == 201


# ── The cap is per user ────────────────────────────────────────────────────────────


def test_another_users_allowance_is_unaffected(throttle):
    """**The cap is per user, not global.**"""
    first_client = signed_in()
    save(first_client, public_event(start_time_utc=START).id)

    second_client = signed_in()
    response = save(second_client, public_event(start_time_utc=START).id)

    assert response.status_code == 201
