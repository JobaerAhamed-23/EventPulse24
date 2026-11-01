"""The `delivery`-owned notification preference: Quiet Hours and the default plan (FR-12, FR-20).

The behaviour that matters here is mostly about *states that must stay distinguishable*: a user
who has never set anything, a user who turned quiet hours off, and a user who deliberately
chose no default reminders. Collapsing any two of those is the bug this file is built to catch.
"""

from datetime import UTC, datetime, time

import pytest
from django.db import IntegrityError, transaction

from apps.delivery.models import DeliveryAuditEntry, NotificationPreference
from apps.delivery.services.notification_preferences import (
    default_slots_for,
    get_preference,
    set_default_reminder_slots,
    set_quiet_hours,
)
from apps.delivery.services.slots import TooManySlotsError, UnknownSlotError
from domain.errors import InvalidQuietHoursWindowError, ValidationError
from domain.quiet_hours import QuietHours
from shared.actor import Actor
from shared.constants import (
    CUSTOM_SLOT_PREFIX,
    DEFAULT_QUIET_HOURS_END,
    DEFAULT_QUIET_HOURS_START,
    DEFAULT_REMINDER_PLAN,
    ReminderSlot,
)
from shared.db import PERSONAL
from shared.ids import uuid7

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
ACTOR = Actor.system("test")


def a_user():
    return uuid7()


# --- Lazy creation and its defaults -------------------------------------------------------------


def test_get_preference_creates_the_row_on_first_read():
    user = a_user()

    settings = get_preference(user_id=user)

    assert settings.user_id == user
    assert NotificationPreference.objects.using(PERSONAL).filter(user_id=user).count() == 1


def test_a_new_user_gets_the_default_quiet_window():
    """A user who has never opened settings still has a night."""
    settings = get_preference(user_id=a_user())

    assert settings.quiet_hours == QuietHours(
        start=DEFAULT_QUIET_HOURS_START, end=DEFAULT_QUIET_HOURS_END
    )
    assert settings.quiet_hours.start == time(22, 0)
    assert settings.quiet_hours.end == time(8, 0)


def test_a_new_user_gets_the_constant_default_plan():
    settings = get_preference(user_id=a_user())

    assert settings.default_reminder_slots == tuple(s.value for s in DEFAULT_REMINDER_PLAN)


def test_get_preference_is_idempotent():
    user = a_user()

    first = get_preference(user_id=user)
    second = get_preference(user_id=user)

    assert first == second
    assert NotificationPreference.objects.using(PERSONAL).filter(user_id=user).count() == 1


def test_get_preference_returns_plain_data_not_a_model():
    settings = get_preference(user_id=a_user())

    assert not isinstance(settings, NotificationPreference)
    with pytest.raises((AttributeError, TypeError)):
        settings.user_id = uuid7()  # frozen


# --- The unique constraint -----------------------------------------------------------------------


def test_a_second_row_for_one_user_is_refused():
    user = a_user()
    get_preference(user_id=user)

    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        NotificationPreference.objects.using(PERSONAL).create(user_id=user)


# --- Quiet hours ---------------------------------------------------------------------------------


def test_set_quiet_hours_stores_the_window():
    user = a_user()

    settings = set_quiet_hours(
        user_id=user, window=QuietHours(time(23, 0), time(7, 0)), actor=ACTOR, now=NOW
    )

    assert settings.quiet_hours == QuietHours(time(23, 0), time(7, 0))
    assert get_preference(user_id=user).quiet_hours == QuietHours(time(23, 0), time(7, 0))


def test_set_quiet_hours_none_turns_them_off():
    user = a_user()

    settings = set_quiet_hours(user_id=user, window=None, actor=ACTOR, now=NOW)

    assert settings.quiet_hours is None
    assert get_preference(user_id=user).quiet_hours is None


def test_quiet_hours_off_is_distinguishable_from_never_set():
    """Both are real states and they are not the same fact about the user."""
    never_set = get_preference(user_id=a_user())
    turned_off = set_quiet_hours(user_id=a_user(), window=None, actor=ACTOR, now=NOW)

    assert never_set.quiet_hours is not None
    assert turned_off.quiet_hours is None


def test_set_quiet_hours_rejects_a_window_that_starts_where_it_ends():
    """ "No quiet hours" has exactly one spelling: a null pair. See InvalidQuietHoursWindowError."""
    with pytest.raises(InvalidQuietHoursWindowError):
        set_quiet_hours(
            user_id=a_user(), window=QuietHours(time(9, 0), time(9, 0)), actor=ACTOR, now=NOW
        )


def test_a_crossing_window_round_trips():
    user = a_user()
    set_quiet_hours(user_id=user, window=QuietHours(time(22, 0), time(8, 0)), actor=ACTOR, now=NOW)

    assert get_preference(user_id=user).quiet_hours.crosses_midnight is True


def test_half_a_window_is_refused_by_the_database():
    """A start with no end is a window that never ends. The pair travels together."""
    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        NotificationPreference.objects.using(PERSONAL).create(
            user_id=a_user(), quiet_hours_start=time(22, 0), quiet_hours_end=None
        )


# --- The default reminder plan (FR-20) -----------------------------------------------------------


def test_set_default_reminder_slots_stores_them():
    user = a_user()

    settings = set_default_reminder_slots(
        user_id=user, slots=[ReminderSlot.FIVE_DAYS.value], actor=ACTOR, now=NOW
    )

    assert settings.default_reminder_slots == (ReminderSlot.FIVE_DAYS.value,)


def test_an_empty_default_is_a_valid_deliberate_state():
    """ "No reminders by default" is a choice, not an unset value."""
    user = a_user()

    set_default_reminder_slots(user_id=user, slots=[], actor=ACTOR, now=NOW)

    assert get_preference(user_id=user).default_reminder_slots == ()
    # And it is honoured rather than falling back to the constant.
    assert default_slots_for(user_id=user) == ()


def test_default_slots_for_falls_back_to_the_constant_when_unset():
    """AD-16: the constant stays the fallback and is never duplicated into delivery."""
    assert default_slots_for(user_id=a_user()) == tuple(s.value for s in DEFAULT_REMINDER_PLAN)


def test_default_slots_for_does_not_create_a_row():
    """The fallback path is a read. Minting a plan must not write a preference row."""
    user = a_user()

    default_slots_for(user_id=user)

    assert not NotificationPreference.objects.using(PERSONAL).filter(user_id=user).exists()


def test_a_custom_slot_is_accepted_as_a_default():
    user = a_user()
    # The custom slot's id is its offset (`custom:90` is 90 minutes before the event), so
    # the id has to be a well-formed one to be accepted at all.
    custom = f"{CUSTOM_SLOT_PREFIX}90"

    settings = set_default_reminder_slots(user_id=user, slots=[custom], actor=ACTOR, now=NOW)

    assert settings.default_reminder_slots == (custom,)


def test_four_default_slots_are_allowed():
    settings = set_default_reminder_slots(
        user_id=a_user(), slots=[s.value for s in ReminderSlot], actor=ACTOR, now=NOW
    )

    assert len(settings.default_reminder_slots) == 4


def test_five_default_slots_are_refused():
    with pytest.raises(TooManySlotsError):
        set_default_reminder_slots(
            user_id=a_user(),
            slots=[*[s.value for s in ReminderSlot], f"{CUSTOM_SLOT_PREFIX}{uuid7()}"],
            actor=ACTOR,
            now=NOW,
        )


def test_an_unknown_default_slot_is_refused():
    with pytest.raises(UnknownSlotError):
        set_default_reminder_slots(user_id=a_user(), slots=["3d"], actor=ACTOR, now=NOW)


def test_a_repeated_default_slot_is_refused():
    with pytest.raises(ValidationError):
        set_default_reminder_slots(
            user_id=a_user(),
            slots=[ReminderSlot.ONE_DAY.value, ReminderSlot.ONE_DAY.value],
            actor=ACTOR,
            now=NOW,
        )


def test_the_slot_bound_is_enforced_by_the_database_too():
    """The CHECK must actually constrain. A `__len` lookup would silently not.

    Django's `__len` transform on a JSON array renders `(col -> 'len') <= '4'`, which yields
    NULL for every array — and a CHECK that evaluates to NULL passes. This test is what tells
    us `jsonb_array_length` is really in the constraint.
    """
    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        NotificationPreference.objects.using(PERSONAL).create(
            user_id=a_user(), default_reminder_slots=["5d", "2d", "1d", "1hr", "extra"]
        )


# --- Audit (AD-5) ---------------------------------------------------------------------------


def test_setting_quiet_hours_writes_an_audit_row():
    user = a_user()

    set_quiet_hours(user_id=user, window=QuietHours(time(23, 0), time(7, 0)), actor=ACTOR, now=NOW)

    entry = (
        DeliveryAuditEntry.objects.using(PERSONAL)
        .filter(action="notification_preference.quiet_hours_set")
        .last()
    )
    assert entry is not None
    assert entry.details["quiet_hours_start"] == "23:00:00"


def test_setting_the_default_plan_writes_an_audit_row():
    set_default_reminder_slots(
        user_id=a_user(), slots=[ReminderSlot.ONE_DAY.value], actor=ACTOR, now=NOW
    )

    entry = (
        DeliveryAuditEntry.objects.using(PERSONAL)
        .filter(action="notification_preference.default_slots_set")
        .last()
    )
    assert entry is not None
    assert entry.details["slots"] == [ReminderSlot.ONE_DAY.value]


# --- Writing one field leaves the other alone ---------------------------------------------------


def test_setting_quiet_hours_does_not_disturb_the_default_plan():
    user = a_user()
    set_default_reminder_slots(
        user_id=user, slots=[ReminderSlot.FIVE_DAYS.value], actor=ACTOR, now=NOW
    )

    set_quiet_hours(user_id=user, window=None, actor=ACTOR, now=NOW)

    assert get_preference(user_id=user).default_reminder_slots == (ReminderSlot.FIVE_DAYS.value,)


def test_setting_the_default_plan_does_not_disturb_quiet_hours():
    user = a_user()
    set_quiet_hours(user_id=user, window=None, actor=ACTOR, now=NOW)

    set_default_reminder_slots(user_id=user, slots=[], actor=ACTOR, now=NOW)

    assert get_preference(user_id=user).quiet_hours is None


def test_a_write_advances_updated_at():
    """`updated_at` is auto_now; Django only writes it when update_fields names it.

    Omitting it leaves a timestamp that silently never moves — invisible until someone tries
    to use it to answer "when did this user last change their settings?".
    """
    user = a_user()
    get_preference(user_id=user)
    row = NotificationPreference.objects.using(PERSONAL).get(user_id=user)
    before = row.updated_at

    set_quiet_hours(user_id=user, window=None, actor=ACTOR, now=NOW)

    row.refresh_from_db()
    assert row.updated_at > before


def test_setting_the_default_plan_advances_updated_at():
    user = a_user()
    get_preference(user_id=user)
    row = NotificationPreference.objects.using(PERSONAL).get(user_id=user)
    before = row.updated_at

    set_default_reminder_slots(user_id=user, slots=[], actor=ACTOR, now=NOW)

    row.refresh_from_db()
    assert row.updated_at > before
