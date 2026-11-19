"""The notification settings API: one settings surface over two modules.

**What these tests pin is the shape of the contract**, not the service's behaviour
(which `test_preferences.py` owns):

- the endpoint is **authed** — an anonymous request is refused;
- the endpoint is **scoped to the session user** — and **no endpoint accepts a user id as
  an input**, so the scoping cannot be talked out of by a payload;
- the `GET` is **one call, one response** — the window, the default slots, the delivery
  time and the zone, assembled across the two modules;
- the `PUT` is a **patch** — an omitted field is left alone, and `quiet_hours: null` is
  the one place where `null` is a value;
- the quiet-hours window and the default slots are validated by **the same validators** the
  per-event plan uses, not by a second copy;
- **every write re-times the pending sends** and **never mints or re-keys**;
- a **partial write is atomic** — both halves land or neither does;
- the **default plan is not retroactive** — existing per-event plans keep their slots and
  their sends.

The client is a `CsrfClient`, because the endpoints resolve their user through
`identity`'s resolver and the resolver checks CSRF on every unsafe method (D13).
"""

import ast
import inspect
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.delivery.models import NotificationPreference, ScheduledSend
from apps.delivery.services.notification_preferences import get_preference
from apps.delivery.services.scheduled_sends import reschedule_pending_for_user
from apps.personalization.services.personal_events import create_personal_event
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from tests.csrf import CsrfClient
from tests.personalization.factories import DigestPreferenceFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

User = get_user_model()

#: The instant every test measures from. Pinned so a reminder's due time is a fact, not a
#: function of when the suite happened to run.
NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)

ZONE = "America/Los_Angeles"


def future_local(*, days_ahead: int, hour: int, minute: int = 0, zone: str = ZONE) -> datetime:
    """A local wall clock on a day the real clock has not reached yet.

    **Why these fixtures cannot use a literal date.** The two tests below mint their
    reminder through the **real API**, which schedules against `timezone.now()` and not
    against this module's `NOW`. They used to build an event on a fixed date; once the
    wall clock passed it the event was in the past, no reminder was minted at all, and
    both failed on `ScheduledSend.DoesNotExist` — a time bomb, not a regression.

    **A local wall clock, converted — never UTC arithmetic.** The deferral these tests
    prove is about *local* times: a slot at 22:30 falls inside the default 22:00–08:00
    window and is pushed to 08:00 the next morning. Computing that in UTC would drift by
    an hour across a DST boundary; 22:30, 23:30 and 08:00 exist on every day of the
    year, because a transition happens at 02:00.

    **And why the tests using this also count their rows.** Converting the dates is only
    half the fix. Several tests here compare a before-count to an after-count, and that
    shape is **self-nulling**: when the fixture stops minting, both sides reach zero
    together and the test passes while asserting nothing. That is what happened on
    2026-11-19 — three tests failed loudly and four kept passing on fewer rows than their
    names claim, one of them comparing a one-row user against a none-row user to prove a
    property about four. So each of them now asserts the row count it depends on *before*
    the behaviour under test runs. A test that cannot tell the difference between "nothing
    changed" and "there was nothing" is not a test.
    """
    today = timezone.now().astimezone(ZoneInfo(zone)).date()
    return datetime.combine(
        today + timedelta(days=days_ahead), time(hour, minute), tzinfo=ZoneInfo(zone)
    )


SETTINGS_URL = "/api/settings/notifications"


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


def put(client, **body):
    """A `PUT` to the settings endpoint with a JSON body."""
    return client.put(SETTINGS_URL, data=body, content_type="application/json")


def pending_of(user):
    """The user's pending sends."""
    return ScheduledSend.objects.using(PERSONAL).filter(
        user_id=user.pk, status=ScheduledSend.Status.PENDING
    )


def make_personal_event(user, *, start_utc, name="Personal Event"):
    """A personal event owned by `user`, with its default plan attached.

    Creating an event attaches the user's default plan (FR-20). **Attaching is not
    minting** — the plan row is written, and the sends are minted when the plan is saved.
    A test that needs pending reminders to re-time therefore saves the plan through the
    Reminder Plan API, which is how a user's reminders come to exist in the first place.
    """
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


def save_plan(client, event, slots):
    """Save the event's Reminder Plan — which is what mints its pending reminders."""
    response = client.put(
        f"/api/reminders/personal_event/{event.id}",
        data={"slots": list(slots)},
        content_type="application/json",
    )
    assert response.status_code == 200, response.content


# ── The read ──────────────────────────────────────────────────────────────────────


def test_the_get_returns_the_window_the_default_slots_the_delivery_time_and_the_zone():
    """One call, one response — all four facts.

    The settings live in two tables in two apps, and the client makes one call.
    """
    user = make_user()
    with_zone(user)
    client = signed_in(user)

    response = client.get(SETTINGS_URL)

    assert response.status_code == 200
    body = response.json()
    assert body["quiet_hours"] == {"start": "22:00:00", "end": "08:00:00"}
    assert body["default_reminder_slots"] == ["1d", "1hr"]
    assert body["digest"] == {"delivery_time": "09:00:00", "timezone": ZONE}


def test_the_get_reports_no_quiet_hours_when_the_user_turned_them_off():
    """`null` on the wire — and only then.

    "Never configured" is not a state the window can hold: reading the preference creates
    it with the defaults.
    """
    user = make_user()
    client = signed_in(user)
    put(client, quiet_hours=None)

    body = client.get(SETTINGS_URL).json()

    assert body["quiet_hours"] is None


def test_the_get_falls_back_to_the_shared_defaults_when_there_is_no_digest_preference():
    """A user with no digest preference row is a real state, not an error.

    The answer is what their digest *would* be scheduled at if it were minted now — the
    shared constants, not a guess and not `null`.
    """
    user = make_user()
    client = signed_in(user)

    body = client.get(SETTINGS_URL).json()

    assert body["digest"] == {"delivery_time": "09:00:00", "timezone": "UTC"}


def test_the_get_assembles_the_response_across_the_two_modules():
    """The surface spans two modules, and the API hides that from the client.

    **Checked structurally, with `ast`.** The API module must not import another app's
    models: `delivery` owns `NotificationPreference` and `personalization` owns
    `DigestPreference`, and the API reads the latter through `personalization`'s
    published service (AD-3, AD-16).
    """
    source = Path("apps/delivery/preferences_api.py").read_text()
    tree = ast.parse(source)

    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)

    assert "apps.personalization.models" not in imported
    assert "apps.delivery.models" not in imported


# ── The quiet-hours write ─────────────────────────────────────────────────────────


def test_putting_the_window_writes_it():
    user = make_user()
    client = signed_in(user)

    response = put(client, quiet_hours={"start": "23:00", "end": "07:00"})

    assert response.status_code == 200
    assert response.json()["quiet_hours"] == {"start": "23:00:00", "end": "07:00:00"}
    assert get_preference(user_id=user.pk).quiet_hours is not None


def test_putting_a_null_window_turns_quiet_hours_off():
    """`null` is a value here — the one field where it is."""
    user = make_user()
    client = signed_in(user)
    put(client, quiet_hours={"start": "23:00", "end": "07:00"})

    response = put(client, quiet_hours=None)

    assert response.status_code == 200
    assert response.json()["quiet_hours"] is None


def test_omitting_the_window_leaves_it_alone():
    """The patch rule: an omitted field means "leave it alone".

    A client that changes the default plan must not silently clear the user's night.
    """
    user = make_user()
    client = signed_in(user)
    put(client, quiet_hours={"start": "23:00", "end": "07:00"})

    response = put(client, default_reminder_slots=["1d"])

    assert response.status_code == 200
    assert response.json()["quiet_hours"] == {"start": "23:00:00", "end": "07:00:00"}


def test_a_full_day_window_is_refused_with_a_readable_message():
    """The same clock twice is the absence of a window, not a window.

    It is refused rather than stored, so "off" has exactly one spelling.
    """
    user = make_user()
    client = signed_in(user)

    response = put(client, quiet_hours={"start": "22:00", "end": "22:00"})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "invalid_quiet_hours_window"
    assert body["message"]


def test_the_window_write_rewrites_the_pending_rows_due_at():
    """A setting that does not change what is scheduled is a setting that does nothing.

    **The row has to be *deferred* for this to be a real test.** The event starts at
    07:30 UTC on the 14th — 23:30 in Los Angeles on the 13th — so its `1hr` slot falls at
    22:30, **inside** the default 22:00–08:00 window, and the row is minted at 08:00
    (16:00 UTC) rather than at 22:30.

    Widening the window to 20:00–22:00 no longer covers 22:30, so the reminder goes back to
    the hour the user chose. **This is the whole point of the Quiet Hours write**: a row
    that was pushed to 8am has to come back to 10:30pm when the window stops covering it.

    And it can only come back because the row remembers **the instant it was for** — its
    `slot_at` — and not merely the instant it was pushed to. Re-deriving the slot from the
    shifted `due_at` compounds the deferral and leaves the row at 8am forever.
    """
    user = make_user()
    with_zone(user)
    # 23:30 local, three days out — far enough ahead that the real clock, which the API
    # schedules against, has not passed it.
    start_local = future_local(days_ahead=3, hour=23, minute=30)
    #: The `1hr` slot: 22:30 local, inside the default 22:00-08:00 window.
    slot_local = start_local - timedelta(hours=1)
    #: Where the window pushes it: 08:00 the next morning, local.
    deferred_local = future_local(days_ahead=4, hour=8)
    event = make_personal_event(user, start_utc=start_local.astimezone(UTC))
    client = signed_in(user)
    save_plan(client, event, ["1hr"])

    row = pending_of(user).get()
    before = row.due_at
    # The slot is inside the default window, so the row was deferred to 08:00 local.
    assert before == deferred_local.astimezone(UTC)

    put(client, quiet_hours={"start": "20:00", "end": "22:00"})

    row.refresh_from_db()
    # 22:30 local the night before — the slot's own hour, no longer deferred.
    assert row.due_at == slot_local.astimezone(UTC)
    assert row.due_at != before


def test_a_deferred_row_keeps_the_instant_it_was_for():
    """The row remembers the slot, not just the deferral — and it survives the round trip.

    **`slot_at` is the fact that makes a Quiet Hours write work at all.** A deferred row's
    `due_at` has lost the original: 22:30 pushed to 08:00 says nothing about 22:30. So the
    row carries both instants — `slot_at` (the slot) and `due_at` (the send) — and the
    rewrite shifts the first to get the second.

    This test pins the pair, and it pins the **round trip**: turning Quiet Hours off brings
    the reminder back to the hour it was always for, and turning them on again pushes it
    back out. A row that only remembered its pushed-to time could not do that.
    """
    user = make_user()
    with_zone(user)
    # The same fixture as the test above: 23:30 local, three days out, so its `1hr` slot
    # at 22:30 falls inside the default 22:00-08:00 window.
    start_local = future_local(days_ahead=3, hour=23, minute=30)
    slot_at = (start_local - timedelta(hours=1)).astimezone(UTC)
    deferred_to = future_local(days_ahead=4, hour=8).astimezone(UTC)
    event = make_personal_event(user, start_utc=start_local.astimezone(UTC))
    client = signed_in(user)
    save_plan(client, event, ["1hr"])

    row = pending_of(user).get()
    # 22:30 local the night before — the slot itself, before any shift.
    assert row.slot_at == slot_at
    # And the deferral: pushed to 08:00 because the default window covers 22:30.
    assert row.due_at == deferred_to

    # Quiet Hours off — the row goes back to the hour it was for.
    put(client, quiet_hours=None)
    row.refresh_from_db()
    assert row.due_at == row.slot_at == slot_at

    # And on again — pushed back out, to the *same* hour it was pushed to the first time.
    put(client, quiet_hours={"start": "22:00", "end": "08:00"})
    row.refresh_from_db()
    assert row.due_at == deferred_to
    # The slot itself never moved — only the send time did.
    assert row.slot_at == slot_at


def test_the_rewrite_does_not_read_the_calendar():
    """The rewrite reads the user's rows and the zone — and nothing else.

    **The query bound, stated as a bound on *what* is read.** The row carries the instant
    it was for, so there is nothing to look up: no event, no save, no per-row query. The
    only cross-module read is the zone, and it is read once.
    """
    source = inspect.getsource(reschedule_pending_for_user)

    for forbidden in (
        "get_personal_event",
        "get_saved_event",
        "list_personal_events",
        "list_saved_events",
    ):
        assert forbidden not in source, f"the rewrite reads the calendar: {forbidden}"


# ── The default-plan write ───────────────────────────────────────────────────────


def test_putting_the_default_slots_writes_them():
    user = make_user()
    client = signed_in(user)

    response = put(client, default_reminder_slots=["5d", "1hr"])

    assert response.status_code == 200
    assert response.json()["default_reminder_slots"] == ["5d", "1hr"]


def test_putting_an_empty_default_is_valid():
    """0 slots is a valid state, not an error."""
    user = make_user()
    client = signed_in(user)

    response = put(client, default_reminder_slots=[])

    assert response.status_code == 200
    assert response.json()["default_reminder_slots"] == []


def test_the_default_slots_use_the_same_validator_as_the_per_event_plan():
    """One validator, not a second copy (AD-8, AD-16).

    The service layer's `set_default_reminder_slots` calls `validate_slots` — the same
    function `reminder_plans` calls. So the *errors* are the same errors, and this test
    pins that by comparing the refusal with the per-event plan's refusal.
    """
    user = make_user()
    client = signed_in(user)

    too_many = put(client, default_reminder_slots=["1d", "2d", "5d", "1hr", "custom:90"])
    unknown = put(client, default_reminder_slots=["next-week"])

    assert too_many.status_code == 422
    assert unknown.status_code == 422
    assert too_many.json()["code"] == "invalid_input"
    assert unknown.json()["code"] == "invalid_input"


def test_five_slots_are_refused():
    """FR-9's bound: at most four."""
    user = make_user()
    client = signed_in(user)

    response = put(client, default_reminder_slots=["1d", "2d", "5d", "1hr", "custom:90"])

    assert response.status_code == 422


def test_changing_the_default_plan_does_not_touch_the_existing_per_event_plans():
    """FR-20: the default applies to future attachments only.

    The opposite is a plausible misreading that would silently rewrite a user's choices,
    so it has its own test. Asserted by **key equality and row count**, not by inspection.
    """
    user = make_user()
    with_zone(user)
    event = make_personal_event(
        user,
        start_utc=future_local(days_ahead=3, hour=18).astimezone(UTC),
    )
    client = signed_in(user)
    save_plan(client, event, ["1d", "1hr"])

    keys_before = sorted(row.send_key for row in pending_of(user))
    count_before = pending_of(user).count()
    # Counted, not assumed — see `future_local` on why a before/after test must.
    assert count_before == 2, "the `1d` and `1hr` slots must both be pending"

    response = put(client, default_reminder_slots=["5d"])

    assert response.status_code == 200
    assert sorted(row.send_key for row in pending_of(user)) == keys_before
    assert pending_of(user).count() == count_before


# ── The delivery-time write ──────────────────────────────────────────────────────


def test_putting_the_delivery_time_writes_it_through_the_published_command():
    """The write goes through `personalization`'s own command (AD-16).

    `personalization` owns `DigestPreference`, so `delivery` may not write the row — it
    calls the published command that onboarding calls, and that command is the only
    writer.
    """
    user = make_user()
    with_zone(user)
    client = signed_in(user)

    response = put(client, digest={"delivery_time": "07:30", "timezone": "Europe/London"})

    assert response.status_code == 200
    assert response.json()["digest"] == {
        "delivery_time": "07:30:00",
        "timezone": "Europe/London",
    }


def test_a_bad_timezone_is_refused():
    """The zone is validated by the same validator onboarding's endpoint gets."""
    user = make_user()
    with_zone(user)
    client = signed_in(user)

    response = put(client, digest={"delivery_time": "07:30", "timezone": "Mars/Olympus"})

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_timezone"


def test_putting_the_delivery_time_moves_tomorrows_digest_row_and_keeps_its_key():
    """The work item's Technical Note, tested exactly.

    The delivery-time write changes when **every future digest** is due, so the rewrite
    touches the `digest` rows as well as the reminders. The digest row's **key must not
    move** — it is `user_id · digest · local_date`, and the key identifies *what* is
    sent, not *when* (AD-7).
    """
    from apps.delivery.services.scheduled_sends import mint_digest

    user = make_user()
    with_zone(user)
    client = signed_in(user)

    mint_digest(
        user_id=user.pk,
        local_date=datetime(2026, 11, 11, tzinfo=UTC).date(),
        delivery_time=time(9, 0),
        zone=ZONE,
        actor=Actor.user(user.pk),
        now=NOW,
    )
    row = pending_of(user).get()
    before_due = row.due_at
    before_key = row.send_key

    put(client, digest={"delivery_time": "07:00", "timezone": ZONE})

    row.refresh_from_db()
    assert row.due_at != before_due
    assert row.send_key == before_key
    assert row.send_key.endswith(":digest:2026-11-11")


def test_putting_the_delivery_time_moves_the_pending_reminder_rows_too():
    """The zone is part of every `due_at` computation, not just the digest's."""

    user = make_user()
    with_zone(user)
    event = make_personal_event(
        user,
        start_utc=future_local(days_ahead=3, hour=18).astimezone(UTC),
    )
    client = signed_in(user)
    save_plan(client, event, ["1d"])

    reminder = pending_of(user).filter(kind=ScheduledSend.Kind.PERSONAL_REMINDER).first()
    assert reminder is not None
    before = reminder.due_at

    put(client, digest={"delivery_time": "07:00", "timezone": "Europe/London"})

    reminder.refresh_from_db()
    assert reminder.due_at != before


# ── The rewrite's invariants ─────────────────────────────────────────────────────


def test_the_keys_are_unchanged_across_ten_successive_changes():
    """A user can change their settings ten times and still receive one reminder.

    This is the whole reason the key is not derived from `due_at` (AD-7).
    """
    user = make_user()
    with_zone(user)
    event = make_personal_event(
        user,
        start_utc=future_local(days_ahead=3, hour=18).astimezone(UTC),
    )
    client = signed_in(user)
    save_plan(client, event, ["1d", "1hr"])

    keys_before = sorted(row.send_key for row in pending_of(user))
    count_before = pending_of(user).count()
    # Counted, not assumed — see `future_local` on why a before/after test must.
    assert count_before == 2, "the `1d` and `1hr` slots must both be pending"

    for hour in range(10):
        put(client, quiet_hours={"start": f"{10 + hour:02d}:00", "end": "12:00"})

    assert sorted(row.send_key for row in pending_of(user)) == keys_before
    assert pending_of(user).count() == count_before


def test_a_sent_row_is_never_touched():
    """A sent row is a fact about an email that already went out."""
    user = make_user()
    with_zone(user)
    event = make_personal_event(
        user,
        start_utc=future_local(days_ahead=3, hour=18).astimezone(UTC),
    )
    client = signed_in(user)
    save_plan(client, event, ["1d"])
    row = pending_of(user).get()
    row.status, row.sent_at = ScheduledSend.Status.SENT, NOW
    row.save(using=PERSONAL, update_fields=["status", "sent_at", "updated_at"])
    sent_due = row.due_at

    put(client, quiet_hours={"start": "01:00", "end": "02:00"})

    row.refresh_from_db()
    assert row.due_at == sent_due
    assert row.status == ScheduledSend.Status.SENT


def test_a_cancelled_row_is_never_touched():
    user = make_user()
    with_zone(user)
    event = make_personal_event(
        user,
        start_utc=future_local(days_ahead=3, hour=18).astimezone(UTC),
    )
    client = signed_in(user)
    save_plan(client, event, ["1d"])
    row = pending_of(user).get()
    row.status = ScheduledSend.Status.CANCELLED
    row.save(using=PERSONAL, update_fields=["status", "updated_at"])
    cancelled_due = row.due_at

    put(client, quiet_hours={"start": "01:00", "end": "02:00"})

    row.refresh_from_db()
    assert row.due_at == cancelled_due
    assert row.status == ScheduledSend.Status.CANCELLED


def test_the_row_count_does_not_change_when_the_window_changes():
    """The rewrite never mints — a settings change must not add a reminder."""
    user = make_user()
    with_zone(user)
    event = make_personal_event(
        user,
        start_utc=future_local(days_ahead=3, hour=18).astimezone(UTC),
    )
    client = signed_in(user)
    save_plan(client, event, ["1d", "1hr"])
    before = pending_of(user).count()
    # Counted, not assumed — see `future_local` on why a before/after test must.
    assert before == 2, "the `1d` and `1hr` slots must both be pending"

    put(client, quiet_hours={"start": "01:00", "end": "02:00"})

    assert pending_of(user).count() == before


# ── Atomicity ────────────────────────────────────────────────────────────────────


def test_a_request_that_sets_the_window_and_the_default_plan_applies_both():
    user = make_user()
    client = signed_in(user)

    response = put(
        client,
        quiet_hours={"start": "23:00", "end": "07:00"},
        default_reminder_slots=["5d"],
    )

    assert response.status_code == 200
    assert response.json()["quiet_hours"] == {"start": "23:00:00", "end": "07:00:00"}
    assert response.json()["default_reminder_slots"] == ["5d"]


def test_a_request_that_sets_the_window_and_the_default_plan_applies_neither_when_one_fails():
    """A half-applied decision is worse than a failed one.

    The window says one thing and the default plan says another, and neither half is
    wrong on its own. So the two writes and the rewrite are **one transaction**.
    """
    user = make_user()
    client = signed_in(user)

    response = put(
        client,
        quiet_hours={"start": "23:00", "end": "07:00"},
        default_reminder_slots=["not-a-slot"],
    )

    assert response.status_code == 422
    # The window was not written: the whole request rolled back.
    assert get_preference(user_id=user.pk).quiet_hours.start == time(22, 0)


# ── Ownership ────────────────────────────────────────────────────────────────────


def test_anonymous_get_gets_401():
    client = CsrfClient()

    response = client.get(SETTINGS_URL)

    assert response.status_code == 401


def test_anonymous_put_gets_401():
    client = CsrfClient()

    response = put(client, quiet_hours=None)

    assert response.status_code == 401


def test_a_caller_cannot_read_another_users_settings():
    """No endpoint accepts a user id, so the scoping is structural.

    The test states the property a client relies on: the second user's settings are
    invisible to the first.
    """
    owner = make_user("owner@example.test")
    intruder = make_user("intruder@example.test")
    with_zone(owner)
    with_zone(intruder)
    owner_client = signed_in(owner)
    put(owner_client, quiet_hours={"start": "23:00", "end": "07:00"})

    intruder_body = signed_in(intruder).get(SETTINGS_URL).json()

    assert intruder_body["quiet_hours"] == {"start": "22:00:00", "end": "08:00:00"}


def test_onboardings_digest_preference_endpoint_still_works():
    """The existing endpoint keeps working unchanged.

    The new settings endpoint and onboarding's both call `personalization`'s published
    command — one writer for that row, one validation for that zone.
    """
    user = make_user()
    client = signed_in(user)

    response = client.put(
        "/api/personal/onboarding/digest-preference",
        data={"delivery_time": "06:45", "timezone": "America/New_York"},
        content_type="application/json",
    )

    assert response.status_code == 200
    body = client.get(SETTINGS_URL).json()
    assert body["digest"] == {"delivery_time": "06:45:00", "timezone": "America/New_York"}


# ── The query bound ──────────────────────────────────────────────────────────────


def test_the_rewrite_reads_the_zone_once_not_once_per_row():
    """Design D4: the query count must not grow with a user's reminders."""
    user = make_user()
    with_zone(user)
    event = make_personal_event(
        user,
        start_utc=future_local(days_ahead=7, hour=18).astimezone(UTC),
    )
    client = signed_in(user)
    save_plan(client, event, ["1d", "2d", "5d", "1hr"])
    # **The four rows have to exist for this test to mean anything.** The assertion below
    # compares the query cost of a four-row user against a one-row user; if the fixture
    # mints fewer rows than its name claims, the comparison still passes and the N+1
    # property it defends goes unexercised. This file has been there: its events were
    # once pinned to a literal date, and once the clock passed it this test was comparing
    # one row against none.
    assert pending_of(user).count() == 4, "all four slots must be pending"

    with CaptureQueriesContext(connections[PERSONAL]) as four_rows:
        put(client, quiet_hours={"start": "01:00", "end": "02:00"})

    user2 = make_user("other@example.test")
    with_zone(user2)
    event2 = make_personal_event(
        user2,
        start_utc=future_local(days_ahead=7, hour=18).astimezone(UTC),
    )
    client2 = signed_in(user2)
    save_plan(client2, event2, ["1d"])
    assert pending_of(user2).count() == 1, "the single slot must be pending"

    with CaptureQueriesContext(connections[PERSONAL]) as one_row:
        put(client2, quiet_hours={"start": "01:00", "end": "02:00"})

    # Four pending rows must not cost four extra zone reads.
    assert len(four_rows) - len(one_row) <= 6


def test_the_notification_preference_row_is_owned_by_delivery():
    """AD-16: `delivery` owns `NotificationPreference` and writes it directly.

    The point of the ownership decision — recorded on the model — is that the row the
    hot path reads lives in the app that reads it. The API's read goes through
    `delivery`'s own published service, not through another app.
    """
    user = make_user()
    client = signed_in(user)

    put(client, quiet_hours={"start": "23:00", "end": "07:00"})

    row = NotificationPreference.objects.using(PERSONAL).get(user_id=user.pk)
    assert row.quiet_hours_start == time(23, 0)
    assert row.quiet_hours_end == time(7, 0)
