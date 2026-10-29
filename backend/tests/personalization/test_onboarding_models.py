"""The onboarding models (FR-1): `Interest`, `OnboardingProgress` and `DigestPreference`.

These tests pin what the **database** holds, not what the service does with it:

- the same chip cannot be held twice (the constraint, not the service);
- the user is held **by value** — no relation to `User`;
- the step is inside 1..3 (the database's copy of FR-1's cap);
- every model declares a retention category (AD-15).

The service's behaviour is pinned in `test_onboarding_commands.py`. This file is about the
guarantees that hold even when a row is written by something other than the command layer.
"""

from datetime import UTC, datetime, time

import pytest
from django.db import IntegrityError, transaction

from apps.personalization.models import DigestPreference, Interest, OnboardingProgress
from shared.db import PERSONAL
from shared.ids import uuid7
from shared.retention import RetentionCategory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

USER = uuid7()
OTHER = uuid7()
NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)


# --- Interest ----------------------------------------------------------------------------


def test_an_interest_holds_the_user_by_value():
    """OQ-8: no relation to `User`, no `GenericForeignKey`. The user is a UUID."""
    interest = Interest.objects.using(PERSONAL).create(user_id=USER, chip_key="tech_meetups")

    assert interest.user_id == USER
    # The model has no relation to `User` at all.
    assert not Interest._meta.related_objects


def test_the_same_chip_cannot_be_held_twice():
    """The acceptance criterion's "DB constraint" — held by the database, not the service.

    The write is done directly, bypassing the service, so this pins the **constraint**
    rather than the command's replace semantics.
    """
    Interest.objects.using(PERSONAL).create(user_id=USER, chip_key="tech_meetups")

    with pytest.raises(IntegrityError):
        with transaction.atomic(using=PERSONAL):
            Interest.objects.using(PERSONAL).create(user_id=USER, chip_key="tech_meetups")


def test_two_users_may_hold_the_same_chip():
    """The constraint is per user, not global."""
    Interest.objects.using(PERSONAL).create(user_id=USER, chip_key="tech_meetups")
    Interest.objects.using(PERSONAL).create(user_id=OTHER, chip_key="tech_meetups")

    assert Interest.objects.using(PERSONAL).filter(chip_key="tech_meetups").count() == 2


def test_an_interest_declares_its_retention_category():
    """AD-15: every concrete model declares one."""
    assert Interest.retention_category == RetentionCategory.PREFERENCE_SIGNALS


# --- OnboardingProgress -------------------------------------------------------------------


def make_progress(**kwargs):
    args = {"user_id": USER, "current_step": 1, "last_advanced_at": NOW}
    args.update(kwargs)
    return OnboardingProgress.objects.using(PERSONAL).create(**args)


def test_a_progress_row_holds_the_user_by_value():
    progress = make_progress()

    assert progress.user_id == USER
    assert not OnboardingProgress._meta.related_objects


def test_a_user_has_one_progress_row():
    """One row per user — the flow is a position, not a history."""
    make_progress()

    with pytest.raises(IntegrityError):
        with transaction.atomic(using=PERSONAL):
            make_progress()


def test_the_step_must_be_inside_the_three_step_range():
    """FR-1's cap, held by the database as a backstop for a row written elsewhere."""
    with pytest.raises(IntegrityError):
        with transaction.atomic(using=PERSONAL):
            make_progress(current_step=4)

    with pytest.raises(IntegrityError):
        with transaction.atomic(using=PERSONAL):
            make_progress(current_step=0)


def test_the_three_valid_steps_are_all_accepted():
    """The constraint permits exactly the steps the flow has."""
    for step in (1, 2, 3):
        row = OnboardingProgress.objects.using(PERSONAL).create(
            user_id=uuid7(), current_step=step, last_advanced_at=NOW
        )
        assert row.current_step == step


def test_a_progress_row_declares_its_retention_category():
    assert OnboardingProgress.retention_category == RetentionCategory.PREFERENCE_SIGNALS


def test_a_completed_row_is_marked_by_its_timestamp():
    progress = make_progress(completed_at=NOW)

    assert progress.completed_at == NOW


# --- DigestPreference ----------------------------------------------------------------------


def test_a_digest_preference_holds_the_user_by_value():
    preference = DigestPreference.objects.using(PERSONAL).create(
        user_id=USER, delivery_time=time(9, 0), timezone="America/Los_Angeles"
    )

    assert preference.user_id == USER
    assert not DigestPreference._meta.related_objects


def test_a_user_has_one_digest_preference():
    """The write is an upsert, so the row is unique per user."""
    DigestPreference.objects.using(PERSONAL).create(
        user_id=USER, delivery_time=time(9, 0), timezone="UTC"
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic(using=PERSONAL):
            DigestPreference.objects.using(PERSONAL).create(
                user_id=USER, delivery_time=time(10, 0), timezone="UTC"
            )


def test_the_delivery_time_is_a_plain_wall_clock():
    """The stored time carries no UTC offset: it is a wall clock, not an instant."""
    preference = DigestPreference.objects.using(PERSONAL).create(
        user_id=USER, delivery_time=time(9, 0), timezone="UTC"
    )

    assert preference.delivery_time == time(9, 0)
    assert preference.delivery_time.tzinfo is None


def test_a_digest_preference_declares_its_retention_category():
    assert DigestPreference.retention_category == RetentionCategory.PREFERENCE_SIGNALS
