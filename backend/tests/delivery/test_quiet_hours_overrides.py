"""Seven quiet-hours windows, one per weekday, and what happens when Pro lapses (FR-51).

The domain's arithmetic lives in `tests/domain/test_weekly_quiet_hours.py`. What this file
pins is the part the domain cannot see:

- that a **Free user's behaviour is byte-for-byte what it was** — the same base window, the
  same effective schedule, the same stored columns;
- that a **Pro user's overrides are applied**, and only a Pro user's;
- that a **lapsed Pro user keeps their rows and loses their effect**, which is the brief's
  never-delete constraint and the acceptance criterion that forbade leaving it implicit;
- and that the commands refuse the things the base window already refuses.
"""

from datetime import UTC, datetime, time

import pytest
from django.db import IntegrityError, transaction

from apps.delivery.models import DeliveryAuditEntry, QuietHoursOverride
from apps.delivery.services.notification_preferences import (
    clear_quiet_hours_override,
    get_preference,
    set_quiet_hours,
    set_quiet_hours_override,
)
from apps.identity.models import SubscriptionStatus
from domain.errors import InvalidQuietHoursWindowError
from domain.quiet_hours import DAYS_IN_WEEK, QuietHours, WeeklyQuietHours
from shared.actor import Actor
from shared.db import PERSONAL
from shared.ids import uuid7
from tests.identity.factories import SubscriptionFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
ACTOR = Actor.system("test")

THURSDAY = 3
SATURDAY = 5

LATE = QuietHours(start=time(23, 30), end=time(10, 0))
BASE = QuietHours(start=time(22, 0), end=time(8, 0))


def a_user():
    return uuid7()


def a_pro_user():
    """A user with a live subscription — Pro by the one published entitlement read."""
    user = uuid7()
    SubscriptionFactory(user_id=user, status=SubscriptionStatus.ACTIVE)
    return user


# --- A Free user is exactly where they were -----------------------------------------------


def test_a_free_users_effective_schedule_is_their_base_window_every_day():
    user = a_user()

    settings = get_preference(user_id=user)

    assert settings.effective_quiet_hours == WeeklyQuietHours.every_day(settings.quiet_hours)


def test_a_free_user_with_quiet_hours_off_is_quiet_on_no_day():
    user = a_user()
    set_quiet_hours(user_id=user, window=None, actor=ACTOR, now=NOW)

    settings = get_preference(user_id=user)

    assert settings.quiet_hours is None
    assert settings.effective_quiet_hours == WeeklyQuietHours.every_day(None)


def test_overrides_are_ignored_for_a_user_who_is_not_pro():
    """The rows exist and say nothing. Entitlement is read where the window is used."""
    user = a_user()
    set_quiet_hours(user_id=user, window=BASE, actor=ACTOR, now=NOW)
    set_quiet_hours_override(user_id=user, weekday=SATURDAY, window=LATE, actor=ACTOR, now=NOW)

    settings = get_preference(user_id=user)

    assert settings.effective_quiet_hours == WeeklyQuietHours.every_day(BASE)
    assert QuietHoursOverride.objects.using(PERSONAL).filter(user_id=user).count() == 1


def test_a_user_with_no_overrides_never_reads_the_subscription_table(
    django_capture_on_commit_callbacks,
):
    """The common case never touches entitlement at all.

    `_effective_week` queries the overrides first and only asks `is_pro` if it finds any, so
    a user who has never been Pro — every Free user, which is the delivery batch's whole
    population — never reads `Subscription`.

    Asserted by the table a query names rather than by a query count: the count includes
    transaction bookkeeping that has nothing to do with this claim, and would make the test
    fail for reasons that are not the thing it is about.
    """
    from django.db import connections
    from django.test.utils import CaptureQueriesContext

    user = a_user()
    get_preference(user_id=user)  # create the row, so the counted read is a plain read

    with CaptureQueriesContext(connections[PERSONAL]) as captured:
        get_preference(user_id=user)

    sql = " ".join(query["sql"] for query in captured.captured_queries)
    assert "quiethoursoverride" in sql.lower()
    assert "identity_subscription" not in sql.lower()


def test_a_user_with_overrides_does_read_the_subscription_table():
    """The other half: the entitlement read is skipped, not absent."""
    from django.db import connections
    from django.test.utils import CaptureQueriesContext

    user = a_user()
    set_quiet_hours_override(user_id=user, weekday=SATURDAY, window=LATE, actor=ACTOR, now=NOW)

    with CaptureQueriesContext(connections[PERSONAL]) as captured:
        get_preference(user_id=user)

    sql = " ".join(query["sql"] for query in captured.captured_queries)
    assert "identity_subscription" in sql.lower()


# --- A Pro user gets seven windows ---------------------------------------------------------


def test_a_pro_users_override_replaces_the_base_window_on_that_day_only():
    user = a_pro_user()
    set_quiet_hours(user_id=user, window=BASE, actor=ACTOR, now=NOW)
    set_quiet_hours_override(user_id=user, weekday=SATURDAY, window=LATE, actor=ACTOR, now=NOW)

    weekly = get_preference(user_id=user).effective_quiet_hours

    assert weekly.for_weekday(SATURDAY) == LATE
    for weekday in range(DAYS_IN_WEEK):
        if weekday != SATURDAY:
            assert weekly.for_weekday(weekday) == BASE


def test_a_pro_user_can_hold_seven_distinct_windows():
    user = a_pro_user()
    set_quiet_hours(user_id=user, window=BASE, actor=ACTOR, now=NOW)
    for weekday in range(DAYS_IN_WEEK):
        set_quiet_hours_override(
            user_id=user,
            weekday=weekday,
            window=QuietHours(start=time(20 + weekday % 4, 0), end=time(6 + weekday, 0)),
            actor=ACTOR,
            now=NOW,
        )

    weekly = get_preference(user_id=user).effective_quiet_hours

    assert len({weekly.for_weekday(day) for day in range(DAYS_IN_WEEK)}) == DAYS_IN_WEEK


def test_an_override_on_a_user_with_quiet_hours_off_leaves_the_other_days_open():
    user = a_pro_user()
    set_quiet_hours(user_id=user, window=None, actor=ACTOR, now=NOW)
    set_quiet_hours_override(user_id=user, weekday=THURSDAY, window=LATE, actor=ACTOR, now=NOW)

    weekly = get_preference(user_id=user).effective_quiet_hours

    assert weekly.for_weekday(THURSDAY) == LATE
    assert weekly.for_weekday(SATURDAY) is None


def test_setting_the_same_weekday_twice_replaces_it_rather_than_stacking():
    user = a_pro_user()
    set_quiet_hours_override(user_id=user, weekday=THURSDAY, window=BASE, actor=ACTOR, now=NOW)
    set_quiet_hours_override(user_id=user, weekday=THURSDAY, window=LATE, actor=ACTOR, now=NOW)

    assert QuietHoursOverride.objects.using(PERSONAL).filter(user_id=user).count() == 1
    assert get_preference(user_id=user).effective_quiet_hours.for_weekday(THURSDAY) == LATE


# --- A lapsed Pro user ----------------------------------------------------------------------


def test_a_lapsed_pro_users_windows_are_kept_and_stop_applying():
    """The acceptance criterion that forbade leaving this implicit.

    The rows are the user's own statement and the brief forbids deleting them. What the
    delivery path does with them while the user is Free is: nothing. They fall back to their
    base window, and everything is where they left it if they resubscribe.
    """
    user = a_pro_user()
    set_quiet_hours(user_id=user, window=BASE, actor=ACTOR, now=NOW)
    set_quiet_hours_override(user_id=user, weekday=SATURDAY, window=LATE, actor=ACTOR, now=NOW)
    assert get_preference(user_id=user).effective_quiet_hours.for_weekday(SATURDAY) == LATE

    # The subscription ends. Nothing touches the override rows.
    subscription = SubscriptionFactory._meta.model.objects.using(PERSONAL).get(user_id=user)
    subscription.status = SubscriptionStatus.CANCELED
    subscription.save(using=PERSONAL)

    lapsed = get_preference(user_id=user)
    assert lapsed.effective_quiet_hours == WeeklyQuietHours.every_day(BASE)
    assert QuietHoursOverride.objects.using(PERSONAL).filter(user_id=user).count() == 1


def test_resubscribing_restores_the_windows_without_the_user_re_entering_them():
    user = a_pro_user()
    set_quiet_hours(user_id=user, window=BASE, actor=ACTOR, now=NOW)
    set_quiet_hours_override(user_id=user, weekday=SATURDAY, window=LATE, actor=ACTOR, now=NOW)
    subscription = SubscriptionFactory._meta.model.objects.using(PERSONAL).get(user_id=user)
    subscription.status = SubscriptionStatus.CANCELED
    subscription.save(using=PERSONAL)

    subscription.status = SubscriptionStatus.ACTIVE
    subscription.save(using=PERSONAL)

    assert get_preference(user_id=user).effective_quiet_hours.for_weekday(SATURDAY) == LATE


# --- The commands' refusals ------------------------------------------------------------------


def test_an_override_that_starts_where_it_ends_is_refused():
    """ "No quiet hours" keeps exactly one spelling: a null base pair."""
    with pytest.raises(InvalidQuietHoursWindowError):
        set_quiet_hours_override(
            user_id=a_user(),
            weekday=THURSDAY,
            window=QuietHours(start=time(9, 0), end=time(9, 0)),
            actor=ACTOR,
            now=NOW,
        )


@pytest.mark.parametrize("weekday", [-1, 7, 99])
def test_a_weekday_outside_the_week_is_refused(weekday):
    with pytest.raises(ValueError, match="weekday must be"):
        set_quiet_hours_override(
            user_id=a_user(), weekday=weekday, window=LATE, actor=ACTOR, now=NOW
        )
    with pytest.raises(ValueError, match="weekday must be"):
        clear_quiet_hours_override(user_id=a_user(), weekday=weekday, actor=ACTOR, now=NOW)


def test_the_database_refuses_a_weekday_outside_the_week():
    """The command checks it, and so does the table — the guard is not only in Python."""
    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        QuietHoursOverride.objects.using(PERSONAL).create(
            user_id=a_user(), weekday=9, start=time(22, 0), end=time(8, 0)
        )


def test_the_database_refuses_a_zero_length_override():
    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        QuietHoursOverride.objects.using(PERSONAL).create(
            user_id=a_user(), weekday=THURSDAY, start=time(9, 0), end=time(9, 0)
        )


def test_the_database_refuses_two_windows_on_one_weekday():
    user = a_user()
    QuietHoursOverride.objects.using(PERSONAL).create(
        user_id=user, weekday=THURSDAY, start=time(22, 0), end=time(8, 0)
    )

    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        QuietHoursOverride.objects.using(PERSONAL).create(
            user_id=user, weekday=THURSDAY, start=time(23, 0), end=time(9, 0)
        )


# --- Clearing ---------------------------------------------------------------------------------


def test_clearing_an_override_returns_that_day_to_the_base_window():
    user = a_pro_user()
    set_quiet_hours(user_id=user, window=BASE, actor=ACTOR, now=NOW)
    set_quiet_hours_override(user_id=user, weekday=SATURDAY, window=LATE, actor=ACTOR, now=NOW)

    clear_quiet_hours_override(user_id=user, weekday=SATURDAY, actor=ACTOR, now=NOW)

    assert get_preference(user_id=user).effective_quiet_hours == WeeklyQuietHours.every_day(BASE)
    assert QuietHoursOverride.objects.using(PERSONAL).filter(user_id=user).count() == 0


def test_clearing_a_weekday_with_no_override_changes_nothing_and_records_nothing():
    user = a_pro_user()
    before = DeliveryAuditEntry.objects.using(PERSONAL).count()

    clear_quiet_hours_override(user_id=user, weekday=SATURDAY, actor=ACTOR, now=NOW)

    assert DeliveryAuditEntry.objects.using(PERSONAL).count() == before


# --- Audit (AD-5) ------------------------------------------------------------------------------


def test_setting_an_override_writes_an_audit_row():
    user = a_pro_user()

    set_quiet_hours_override(user_id=user, weekday=SATURDAY, window=LATE, actor=ACTOR, now=NOW)

    entry = (
        DeliveryAuditEntry.objects.using(PERSONAL)
        .filter(action="notification_preference.quiet_hours_override_set")
        .get()
    )
    assert entry.details["weekday"] == SATURDAY
    assert entry.details["quiet_hours_start"] == "23:30:00"
    assert entry.details["quiet_hours_end"] == "10:00:00"


def test_clearing_an_override_writes_an_audit_row():
    user = a_pro_user()
    set_quiet_hours_override(user_id=user, weekday=SATURDAY, window=LATE, actor=ACTOR, now=NOW)

    clear_quiet_hours_override(user_id=user, weekday=SATURDAY, actor=ACTOR, now=NOW)

    entry = (
        DeliveryAuditEntry.objects.using(PERSONAL)
        .filter(action="notification_preference.quiet_hours_override_cleared")
        .get()
    )
    assert entry.details["weekday"] == SATURDAY


# --- The migration invents nothing ------------------------------------------------------------


def test_the_migration_has_no_data_step():
    """The acceptance criterion, asserted against the migration rather than its effects.

    *"The migration invents nothing. A user with one window keeps one window. No migration
    fabricates seven copies of an existing window."* The strongest form of that is a
    migration with no data step in it at all — which is what the base-window-plus-overrides
    shape bought, and what this pins. A later edit that added a `RunPython` backfill here
    would be exactly the thing the criterion forbids.
    """
    from importlib import import_module

    from django.db.migrations.operations.models import CreateModel

    migration = import_module("apps.delivery.migrations.0008_quiethoursoverride").Migration

    assert [type(operation) for operation in migration.operations] == [CreateModel]
    assert migration.operations[0].name == "QuietHoursOverride"


def test_the_base_window_columns_are_untouched_by_this_item():
    """`NotificationPreference`'s pair and its check constraint are exactly as they were."""
    from apps.delivery.models import NotificationPreference

    names = {constraint.name for constraint in NotificationPreference._meta.constraints}
    assert "notification_preference_quiet_hours_pair_ck" in names
    columns = {field.name for field in NotificationPreference._meta.get_fields()}
    assert {"quiet_hours_start", "quiet_hours_end"} <= columns
