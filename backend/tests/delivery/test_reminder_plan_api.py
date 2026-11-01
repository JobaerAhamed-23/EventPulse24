"""The Reminder Plan API: the surface that makes a saved plan actually send (FR-9, AD-7).

**What these tests pin is the shape of the contract**, not the service's behaviour
(which `test_reminder_plans.py` owns):

- the endpoint is **authed** — an anonymous request is refused;
- the endpoint is **scoped to the session user** — another user's target is invisible,
  and no endpoint accepts a user id as an input;
- **a missing target is a 404, not a 403** — a 403 would confirm that the record exists,
  so the endpoint could be used to probe for other users' ids (no existence leak);
- **the delivery time is the server's answer** — each slot carries the post-Quiet-Hours
  instant, the deferred flag, and the window end, so the client never reimplements the
  shift;
- **0 slots is a valid save**, not a delete and not an error;
- **the plan and its sends move together** — a reschedule that fails rolls the plan back;
- **the query count is bounded** and does not grow with the slot count.

The client is a `CsrfClient`, because the endpoints resolve their user through
`identity`'s resolver and the resolver checks CSRF on every unsafe method (D13).
"""

from datetime import UTC, datetime, time, timedelta
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.test.utils import CaptureQueriesContext

from apps.delivery.models import ReminderPlan, ScheduledSend
from apps.delivery.services import scheduled_sends
from apps.delivery.services.reminder_plans import get_plan
from apps.personalization.services.personal_events import create_personal_event
from apps.personalization.services.saved_events import save_event
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from tests.csrf import CsrfClient
from tests.ingestion.factories import EventFactory, VenueFactory
from tests.personalization.factories import (
    DigestPreferenceFactory,
)

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

User = get_user_model()

#: The instant every test measures from. Pinned so a reminder's due time is a fact, not a
#: function of when the suite happened to run.
NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)

ZONE = "America/Los_Angeles"
TIMEZONE_OFFSET = timedelta(hours=-8)

#: An event that starts at 6pm local — outside the default 22:00–08:00 quiet window, so a
#: `1d` slot lands the previous day at 6pm and is **not** deferred.
AFTERNOON_START = datetime(2026, 11, 12, 2, 0, tzinfo=UTC)  # 2026-11-11 18:00 in LA

#: An event that starts at 11:30pm local — inside the quiet window's evening side, so a
#: `1hr` slot lands at 10:30pm and **is** deferred to 8:00am the next morning.
LATE_START = datetime(2026, 11, 14, 7, 30, tzinfo=UTC)  # 2026-11-13 23:30 in LA


def make_user(email="sam@example.test"):
    """A real user with a real pk — the session resolves to this one."""
    return User.objects.create_user(email=email, password="pw")


def signed_in(user=None):
    """A client whose session identifies `user`."""
    client = CsrfClient()
    client.force_login(user or make_user())
    return client


def with_zone(user, zone=ZONE):
    """Give the user a digest preference, so the zone read has something to return."""
    DigestPreferenceFactory(user_id=user.pk, timezone=zone)
    return user


def make_personal_event(user, *, start_utc=AFTERNOON_START, name="Personal Event"):
    """A personal event owned by `user`, with its default plan attached."""
    result = create_personal_event(
        user_id=user.pk,
        name=name,
        start_utc=start_utc,
        end_utc=start_utc + timedelta(hours=2),
        start_time_tz=ZONE,
        actor=Actor.user(user.pk),
        now=NOW,
    )
    return result.event


def make_saved_event(user, *, start_utc=AFTERNOON_START, title="Brooklyn Tech Meetup"):
    """A saved public event owned by `user`.

    The save's `target_id` in the plan's world is the **catalog** event's id — the tree's
    convention — so a real catalog event is saved and its id is what the plan addresses.
    """
    fingerprint = f"venue-{title}|{uuid4()}"
    event = EventFactory(
        title=title,
        venue=VenueFactory(city="New York City", venue_fingerprint=fingerprint),
        start_time_utc=start_utc,
        last_seen_at=NOW,
    )
    result = save_event(user_id=user.pk, event_id=event.id, actor=Actor.user(user.pk), now=NOW)
    return event, result.saved


def path(kind, target_id):
    return f"/api/reminders/{kind}/{target_id}"


def put_plan(client, kind, target_id, slots):
    return client.put(
        path(kind, target_id),
        data={"slots": list(slots)},
        content_type="application/json",
    )


def get_plan_response(client, kind, target_id):
    return client.get(path(kind, target_id))


# --- Authentication and ownership ----------------------------------------------------------------


def test_an_anonymous_caller_is_refused():
    client = CsrfClient()

    response = get_plan_response(client, "personal_event", uuid4())

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"


def test_an_anonymous_caller_cannot_save_a_plan():
    client = CsrfClient()

    response = put_plan(client, "personal_event", uuid4(), ["1d"])

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"


def test_another_users_personal_event_is_a_404_not_a_403():
    """No existence leak: a 403 would confirm that the record exists."""
    owner = make_user("owner@example.test")
    intruder = make_user("intruder@example.test")
    event = make_personal_event(owner)
    client = signed_in(intruder)

    response = get_plan_response(client, "personal_event", event.id)

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_another_users_saved_event_is_a_404_not_a_403():
    owner = make_user("owner@example.test")
    intruder = make_user("intruder@example.test")
    event, _saved = make_saved_event(owner)
    client = signed_in(intruder)

    response = get_plan_response(client, "saved_event", event.id)

    assert response.status_code == 404


def test_another_users_plan_is_not_written():
    """The refusal is a refusal — the owner's plan is untouched."""
    owner = make_user("owner@example.test")
    intruder = make_user("intruder@example.test")
    event = make_personal_event(owner)
    client = signed_in(intruder)

    response = put_plan(client, "personal_event", event.id, ["5d", "2d"])

    assert response.status_code == 404
    assert get_plan(user_id=owner.pk, target_kind="personal_event", target_id=event.id).slots == (
        "1d",
        "1hr",
    )


def test_a_target_that_does_not_exist_is_a_404():
    user = make_user()
    client = signed_in(user)

    response = get_plan_response(client, "personal_event", uuid4())

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_a_saved_event_the_user_has_unsaved_is_a_404():
    """Un-saved and never-saved are the same fact: the save is the target."""
    from apps.personalization.services.saved_events import unsave_event

    user = make_user()
    event, saved = make_saved_event(user)
    unsave_event(user_id=user.pk, event_id=event.id, actor=Actor.user(user.pk), now=NOW)
    client = signed_in(user)

    response = get_plan_response(client, "saved_event", event.id)

    assert response.status_code == 404


def test_a_target_of_the_other_kind_is_a_404():
    """A personal event's id is not a saved event's id, and vice versa."""
    user = make_user()
    event = make_personal_event(user)
    client = signed_in(user)

    response = get_plan_response(client, "saved_event", event.id)

    assert response.status_code == 404


def test_an_unknown_target_kind_is_a_404():
    user = make_user()
    client = signed_in(user)

    response = get_plan_response(client, "not_a_kind", uuid4())

    assert response.status_code == 404


# --- Both target kinds ----------------------------------------------------------------------------


def test_a_personal_events_plan_is_read():
    user = make_user()
    event = make_personal_event(user)
    client = signed_in(user)

    response = get_plan_response(client, "personal_event", event.id)

    assert response.status_code == 200
    body = response.json()
    assert body["target_kind"] == "personal_event"
    assert str(body["target_id"]) == str(event.id)
    assert body["slots"] == ["1d", "1hr"]


def test_a_saved_events_plan_is_read():
    user = make_user()
    event, _saved = make_saved_event(user)
    client = signed_in(user)

    response = get_plan_response(client, "saved_event", event.id)

    assert response.status_code == 200
    body = response.json()
    assert body["target_kind"] == "saved_event"
    assert str(body["target_id"]) == str(event.id)
    # A saved event has **no** plan until one is saved (FR-20 attaches one to a personal
    # event; `save_event` does not). So the read is the empty state.
    assert body["slots"] == []


def test_a_personal_events_plan_is_saved():
    user = make_user()
    event = make_personal_event(user)
    client = signed_in(user)

    response = put_plan(client, "personal_event", event.id, ["5d", "2d"])

    assert response.status_code == 200
    assert response.json()["slots"] == ["5d", "2d"]
    assert get_plan(user_id=user.pk, target_kind="personal_event", target_id=event.id).slots == (
        "5d",
        "2d",
    )


def test_a_saved_events_plan_is_saved():
    """A saved event has no plan, so the `PUT` attaches one."""
    user = make_user()
    event, _saved = make_saved_event(user)
    client = signed_in(user)

    response = put_plan(client, "saved_event", event.id, ["1d"])

    assert response.status_code == 200
    assert response.json()["slots"] == ["1d"]
    plan = ReminderPlan.objects.get(
        user_id=user.pk, target_kind=ReminderPlan.TargetKind.SAVED_EVENT, target_id=event.id
    )
    assert plan.slots == ["1d"]


# --- 0, 1 and 4 slots ----------------------------------------------------------------------------


def test_zero_slots_is_a_valid_save():
    """FR-9: "0 slots = no reminders (still in feed)." Not a delete, not an error."""
    user = make_user()
    event = make_personal_event(user)
    client = signed_in(user)

    response = put_plan(client, "personal_event", event.id, [])

    assert response.status_code == 200
    assert response.json()["slots"] == []
    # The row **survives**, so "the user chose no reminders" stays distinguishable from
    # "the user never configured a plan".
    assert ReminderPlan.objects.filter(
        user_id=user.pk, target_kind=ReminderPlan.TargetKind.PERSONAL_EVENT, target_id=event.id
    ).exists()


def test_one_slot_is_saved():
    user = make_user()
    event = make_personal_event(user)
    client = signed_in(user)

    response = put_plan(client, "personal_event", event.id, ["2d"])

    assert response.status_code == 200
    assert response.json()["slots"] == ["2d"]


def test_four_slots_are_saved():
    user = make_user()
    event = make_personal_event(user)
    client = signed_in(user)

    response = put_plan(client, "personal_event", event.id, ["5d", "2d", "1d", "1hr"])

    assert response.status_code == 200
    assert response.json()["slots"] == ["5d", "2d", "1d", "1hr"]


def test_five_slots_are_refused():
    user = make_user()
    event = make_personal_event(user)
    client = signed_in(user)

    response = put_plan(client, "personal_event", event.id, ["5d", "2d", "1d", "1hr", "custom:90"])

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "invalid_input"
    assert body["message"]


def test_a_duplicate_slot_is_refused():
    user = make_user()
    event = make_personal_event(user)
    client = signed_in(user)

    response = put_plan(client, "personal_event", event.id, ["1d", "1d"])

    assert response.status_code == 422


def test_an_unknown_slot_is_refused():
    user = make_user()
    event = make_personal_event(user)
    client = signed_in(user)

    response = put_plan(client, "personal_event", event.id, ["3d"])

    assert response.status_code == 422


# --- The custom slot ------------------------------------------------------------------------------


def test_a_custom_slot_is_saved():
    """`custom:90` is 90 minutes before the event — the id carries the offset."""
    user = make_user()
    event = make_personal_event(user)
    client = signed_in(user)

    response = put_plan(client, "personal_event", event.id, ["custom:90"])

    assert response.status_code == 200
    assert response.json()["slots"] == ["custom:90"]


def test_a_custom_slots_delivery_time_honours_its_offset():
    user = make_user()
    with_zone(user)
    event = make_personal_event(user, start_utc=AFTERNOON_START)
    client = signed_in(user)

    response = put_plan(client, "personal_event", event.id, ["custom:90"])

    assert response.status_code == 200
    delivery = response.json()["deliveries"][0]
    # 18:00 local minus 90 minutes is 16:30 local on the same day → 00:30Z the next day.
    assert delivery["delivery_at"] == "2026-11-12T00:30:00Z"


def test_a_custom_slot_below_the_minimum_is_refused():
    """EXPERIENCE.md: "Min: 15 minutes before." A reminder *after* the event is not one."""
    user = make_user()
    event = make_personal_event(user)
    client = signed_in(user)

    response = put_plan(client, "personal_event", event.id, ["custom:14"])

    assert response.status_code == 422


def test_a_custom_slot_above_the_maximum_is_refused():
    """EXPERIENCE.md: "max: 30 days before." 43200 minutes is exactly thirty days."""
    user = make_user()
    event = make_personal_event(user)
    client = signed_in(user)

    response = put_plan(client, "personal_event", event.id, ["custom:43201"])

    assert response.status_code == 422


def test_a_custom_slot_at_the_maximum_is_accepted():
    user = make_user()
    event = make_personal_event(user)
    client = signed_in(user)

    response = put_plan(client, "personal_event", event.id, ["custom:43200"])

    assert response.status_code == 200


def test_a_negative_custom_slot_is_refused():
    """A negative offset would be a reminder *after* the event."""
    user = make_user()
    event = make_personal_event(user)
    client = signed_in(user)

    response = put_plan(client, "personal_event", event.id, ["custom:-30"])

    assert response.status_code == 422


def test_two_custom_slots_are_refused():
    user = make_user()
    event = make_personal_event(user)
    client = signed_in(user)

    response = put_plan(client, "personal_event", event.id, ["custom:90", "custom:120"])

    assert response.status_code == 422


def test_a_custom_slot_is_minted():
    """A custom slot used to be stored, listed, and **never minted**. Now it is a send."""
    user = make_user()
    with_zone(user)
    event = make_personal_event(user, start_utc=AFTERNOON_START)
    client = signed_in(user)

    response = put_plan(client, "personal_event", event.id, ["custom:90"])

    assert response.status_code == 200
    sends = ScheduledSend.objects.filter(
        user_id=user.pk, target_kind=ReminderPlan.TargetKind.PERSONAL_EVENT, target_id=event.id
    )
    assert [send.slot for send in sends] == ["custom:90"]
    assert sends[0].status == ScheduledSend.Status.PENDING


# --- The computed delivery time -------------------------------------------------------------------


def test_a_slot_outside_quiet_hours_is_not_deferred():
    """The 6pm local event's 1-day slot lands at 6pm the previous day — outside 22:00–08:00."""
    user = make_user()
    with_zone(user)
    event = make_personal_event(user, start_utc=AFTERNOON_START)
    client = signed_in(user)

    response = put_plan(client, "personal_event", event.id, ["1d"])

    assert response.status_code == 200
    delivery = response.json()["deliveries"][0]
    assert delivery["deferred"] is False
    assert delivery["deferred_to"] is None
    # 2026-11-11 18:00 local → 2026-11-11 02:00Z... one day earlier: 2026-11-10 18:00
    # local → 2026-11-11 02:00Z.
    assert delivery["delivery_at"] == "2026-11-11T02:00:00Z"


def test_a_slot_inside_quiet_hours_is_deferred_to_the_window_end():
    """The UX spec's worked example, on the server.

    An event at 11:30pm local with a 1-hour slot would deliver at 10:30pm — inside Quiet
    Hours — so the chip dims and the tooltip reads *"Will deliver at 8:00 am Saturday."*
    """
    user = make_user()
    with_zone(user)
    event = make_personal_event(user, start_utc=LATE_START)
    client = signed_in(user)

    response = put_plan(client, "personal_event", event.id, ["1hr"])

    assert response.status_code == 200
    delivery = response.json()["deliveries"][0]
    assert delivery["deferred"] is True
    # The window's end is the delivery instant — one instant, not two.
    assert delivery["deferred_to"] == delivery["delivery_at"]
    # 2026-11-13 23:30 local minus an hour is 22:30 local, which defers to 08:00 local on
    # the 14th — 16:00Z.
    assert delivery["delivery_at"] == "2026-11-14T16:00:00Z"


def test_the_delivery_time_matches_the_minted_send():
    """The time the picker shows is the time the send gets — by construction."""
    user = make_user()
    with_zone(user)
    event = make_personal_event(user, start_utc=LATE_START)
    client = signed_in(user)

    response = put_plan(client, "personal_event", event.id, ["1hr"])

    delivery = response.json()["deliveries"][0]
    send = ScheduledSend.objects.get(
        user_id=user.pk, target_kind=ReminderPlan.TargetKind.PERSONAL_EVENT, target_id=event.id
    )
    # The wire shape is an ISO instant in UTC; the row holds the same instant.
    assert send.due_at == datetime.fromisoformat(delivery["delivery_at"])


def test_a_read_reports_the_same_delivery_time_as_the_save():
    user = make_user()
    with_zone(user)
    event = make_personal_event(user, start_utc=LATE_START)
    client = signed_in(user)
    put_plan(client, "personal_event", event.id, ["1hr"])

    response = get_plan_response(client, "personal_event", event.id)

    assert response.json()["deliveries"][0]["deferred"] is True


def test_a_plan_with_no_slots_reports_no_deliveries():
    user = make_user()
    with_zone(user)
    event = make_personal_event(user)
    client = signed_in(user)
    put_plan(client, "personal_event", event.id, [])

    response = get_plan_response(client, "personal_event", event.id)

    assert response.json()["deliveries"] == []


# --- The transaction ------------------------------------------------------------------------------


def test_a_failed_reschedule_rolls_the_plan_back(monkeypatch):
    """A plan change that fails to reschedule rolls the plan too.

    The plan and its sends move together or not at all — a plan saved without its sends
    changing is a plan that does nothing, which is the state the product was in.
    """
    user = make_user()
    with_zone(user)
    event = make_personal_event(user, start_utc=AFTERNOON_START)
    client = signed_in(user)

    def boom(**kwargs):
        raise RuntimeError("the reschedule failed")

    monkeypatch.setattr("apps.delivery.services.reminder_plans.resync_plan", boom)

    response = put_plan(client, "personal_event", event.id, ["5d", "2d"])

    assert response.status_code == 500
    # The plan's slots are **unchanged** — the write rolled back with the reschedule.
    assert get_plan(user_id=user.pk, target_kind="personal_event", target_id=event.id).slots == (
        "1d",
        "1hr",
    )


def test_a_saved_plan_and_its_sends_move_together():
    """The sends that the save cancelled or minted are the ones the plan says."""
    user = make_user()
    with_zone(user)
    event = make_personal_event(user, start_utc=AFTERNOON_START)
    client = signed_in(user)
    put_plan(client, "personal_event", event.id, ["5d", "2d", "1d", "1hr"])

    sends = ScheduledSend.objects.filter(
        user_id=user.pk, target_kind=ReminderPlan.TargetKind.PERSONAL_EVENT, target_id=event.id
    )
    assert {send.slot for send in sends} == {"5d", "2d", "1d", "1hr"}

    put_plan(client, "personal_event", event.id, ["1d"])

    sends = ScheduledSend.objects.filter(
        user_id=user.pk,
        target_kind=ReminderPlan.TargetKind.PERSONAL_EVENT,
        target_id=event.id,
        status=ScheduledSend.Status.PENDING,
    )
    assert {send.slot for send in sends} == {"1d"}


# --- The bounded query count ----------------------------------------------------------------------


def test_the_query_count_does_not_grow_with_the_slot_count():
    """Four slots cost the same queries as one.

    The per-slot delivery times are computed **in Python** over four facts, not with a
    query per slot — so an N+1 cannot land silently inside the budget.

    **Both reads are measured in the steady state.** The first read of a user's
    notification preference *creates* the row (`get_preference` reads by writing), so it
    costs one extra INSERT. That is a one-time cost per user, not a per-slot cost.
    """
    user = make_user()
    with_zone(user)
    event = make_personal_event(user, start_utc=AFTERNOON_START)
    client = signed_in(user)
    put_plan(client, "personal_event", event.id, ["1d"])

    # The first read creates the notification preference row; it is not part of the
    # steady-state cost.
    get_plan_response(client, "personal_event", event.id)

    with CaptureQueriesContext(connections[PERSONAL]) as one_slot:
        response = get_plan_response(client, "personal_event", event.id)
    assert response.status_code == 200
    one_count = len(one_slot.captured_queries)

    put_plan(client, "personal_event", event.id, ["5d", "2d", "1d", "1hr"])

    with CaptureQueriesContext(connections[PERSONAL]) as four_slots:
        response = get_plan_response(client, "personal_event", event.id)
    assert response.status_code == 200
    four_count = len(four_slots.captured_queries)

    assert one_count == four_count


# --- The contract ---------------------------------------------------------------------------------


def test_the_endpoints_are_in_the_openapi_schema():
    from config.api import api

    schema = api.get_openapi_schema()

    assert "/api/reminders/{target_kind}/{target_id}" in schema["paths"]
    operations = schema["paths"]["/api/reminders/{target_kind}/{target_id}"]
    assert "get" in operations
    assert "put" in operations


def test_the_delivery_api_does_not_import_the_models():
    """AD-3 and AD-16: the surface reads other apps' models only through their services.

    The check is on the **imports**, not on the prose — the module's docstring names the
    models it deliberately does not import, and a substring search over the whole file
    would find that sentence.

    `apps/delivery/models` is allowed **inside `apps/delivery`** (AD-16 gives the app
    ownership of the table) but not in the surface file: `apps/*/api.py` are surface
    files, and the architecture test `test_no_direct_writes.py` treats them as such.
    """
    import ast
    from pathlib import Path

    def imported_modules(path):
        tree = ast.parse(Path(path).read_text())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module)
        return names

    api_modules = imported_modules("apps/delivery/api.py")
    assert not any(name.endswith("ingestion.models") for name in api_modules)
    assert not any(name.endswith("delivery.models") for name in api_modules)
    assert not any(name.endswith("personalization.models") for name in api_modules)

    # The service layer may read its own app's models — and may **not** read another
    # app's. `personalization`'s models are read through its published service.
    read_modules = imported_modules("apps/delivery/services/reminder_plan_read.py")
    assert not any(name.endswith("ingestion.models") for name in read_modules)
    assert not any(name.endswith("personalization.models") for name in read_modules)


# --- The service behind the surface -----------------------------------------------------------


def test_the_slot_offset_is_published_for_the_read():
    """The read and the minting path share one implementation of the shift."""
    assert callable(scheduled_sends.slot_due_at)
    assert callable(scheduled_sends.slot_offset)


def test_a_plan_is_attached_when_it_is_missing():
    """The `PUT` attaches the plan when the row is missing — the saved-event case."""
    user = make_user()
    event, _saved = make_saved_event(user)
    assert not ReminderPlan.objects.filter(
        user_id=user.pk, target_kind=ReminderPlan.TargetKind.SAVED_EVENT, target_id=event.id
    ).exists()

    client = signed_in(user)
    put_plan(client, "saved_event", event.id, ["1d"])

    assert ReminderPlan.objects.filter(
        user_id=user.pk, target_kind=ReminderPlan.TargetKind.SAVED_EVENT, target_id=event.id
    ).exists()


def test_an_existing_plan_is_replaced_not_duplicated():
    user = make_user()
    event = make_personal_event(user)
    client = signed_in(user)

    put_plan(client, "personal_event", event.id, ["5d"])
    put_plan(client, "personal_event", event.id, ["2d"])

    assert (
        ReminderPlan.objects.filter(
            user_id=user.pk, target_kind=ReminderPlan.TargetKind.PERSONAL_EVENT, target_id=event.id
        ).count()
        == 1
    )


def test_the_put_does_not_resolve_the_target_twice(monkeypatch):
    """The write path reuses the target it already resolved.

    The `PUT` resolves the target first — it has to, because the `SendTarget` is what the
    minting service needs — and then reads the saved plan back so the response carries the
    same delivery times the next `GET` would.

    Resolving it a second time would re-read the event, the notification preference and the
    digest preference for facts this request already holds. That is **five extra queries
    on every write**, for nothing.

    The test counts the resolutions rather than the queries, because the queries are a
    symptom and the resolution is the cause: one resolution, one read of each fact.
    """
    from apps.delivery import api as delivery_api

    user = make_user()
    event = make_personal_event(user)
    client = signed_in(user)

    real_resolve = delivery_api.resolve_target
    resolutions = {"count": 0}

    def counting_resolve(*args, **kwargs):
        resolutions["count"] += 1
        return real_resolve(*args, **kwargs)

    monkeypatch.setattr(delivery_api, "resolve_target", counting_resolve)

    response = client.put(
        f"/api/reminders/personal_event/{event.id}",
        data={"slots": ["1d"]},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert resolutions["count"] == 1


def test_the_puts_read_back_matches_the_next_get(monkeypatch):
    """The read-back and the next `GET` answer the same thing.

    The `PUT` reads the saved plan back so its response carries the delivery times the
    next `GET` would. The read-back reuses the target the write already resolved, so the
    two cannot disagree about *what the target is* — and the plan row is read from the
    database either way, so they cannot disagree about *what was saved*.

    The test answers the same request both ways and compares the bodies.
    """
    user = make_user()
    event = make_personal_event(user)
    client = signed_in(user)

    put_response = client.put(
        f"/api/reminders/personal_event/{event.id}",
        data={"slots": ["1d", "1hr"]},
        content_type="application/json",
    )
    get_response = client.get(f"/api/reminders/personal_event/{event.id}")

    assert put_response.status_code == 200
    assert get_response.status_code == 200
    assert put_response.json() == get_response.json()


def test_a_malformed_slot_has_no_delivery_time():
    """The validator refuses such a slot on write, so the read is defensive, not a guess.

    A slot whose id carries no offset has no due instant — and the read says so rather than
    inventing one. `delivery_at` is `null` and `deferred` is `false`.
    """
    from apps.delivery.services.reminder_plan_read import compute_deliveries
    from domain.quiet_hours import QuietHours

    window = QuietHours(start=time(22, 0), end=time(8, 0))

    deliveries = compute_deliveries(
        slots=("custom:soon",),
        start_utc=AFTERNOON_START,
        zone=ZONE,
        window=window,
    )

    assert deliveries[0].delivery_at is None
    assert deliveries[0].deferred is False
    assert deliveries[0].deferred_to is None


def test_slot_offsets_leaves_out_a_slot_with_no_offset():
    """The same defensive rule on the minting path's own helper."""
    from apps.delivery.services.reminder_plans import slot_offsets

    assert slot_offsets(start_utc=AFTERNOON_START, slots=("custom:soon",)) == ()
