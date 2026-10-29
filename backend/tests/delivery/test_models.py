"""The `delivery` models: the constraints the database holds (AD-16, FR-9).

Every invariant here is a check constraint or a unique constraint, so a violation is an
`IntegrityError` from Postgres rather than a Python assertion. The tests pin the *rule*, not
Django's rendering of it.
"""

import pytest
from django.db import IntegrityError, transaction

from apps.delivery.models import ReminderPlan
from shared.db import PERSONAL
from shared.ids import uuid7
from tests.delivery.factories import ReminderPlanFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

# FR-9: "up to 4 reminder slots".
FOUR_SLOTS = ["5d", "2d", "1d", "1hr"]
FIVE_SLOTS = ["5d", "2d", "1d", "1hr", "custom:my-slot"]


# --- ReminderPlan ----------------------------------------------------------------------------


def test_reminder_plan_defaults_to_no_slots():
    # A plan with no slots is a valid state (FR-9: "0 slots = no reminders").
    plan = ReminderPlanFactory.create(slots=[])

    assert ReminderPlan.objects.get(pk=plan.pk).slots == []


def test_reminder_plan_accepts_four_slots():
    plan = ReminderPlanFactory.create(slots=FOUR_SLOTS)

    assert ReminderPlan.objects.get(pk=plan.pk).slots == FOUR_SLOTS


def test_reminder_plan_rejects_a_fifth_slot():
    # The bound is enforced by the database, not by the service alone: `jsonb_array_length`.
    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        ReminderPlanFactory.create(slots=FIVE_SLOTS)


def test_reminder_plan_rejects_a_second_plan_for_the_same_event():
    first = ReminderPlanFactory.create()

    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        ReminderPlanFactory.create(
            user_id=first.user_id,
            target_kind=first.target_kind,
            target_id=first.target_id,
        )


def test_reminder_plan_allows_the_same_event_for_two_users():
    first = ReminderPlanFactory.create()

    ReminderPlanFactory.create(
        user_id=uuid7(),
        target_kind=first.target_kind,
        target_id=first.target_id,
    )

    # Two users may each hold a plan for the same event; the unique constraint is per user.
    assert ReminderPlan.objects.filter(target_id=first.target_id).count() == 2


def test_reminder_plan_allows_a_plan_for_a_personal_event_and_a_saved_event():
    # The same id under two kinds is two different plans: a personal event and a saved event
    # are different records, even if their ids happened to collide.
    user_id = uuid7()
    target_id = uuid7()

    ReminderPlanFactory.create(user_id=user_id, target_kind="personal_event", target_id=target_id)
    ReminderPlanFactory.create(user_id=user_id, target_kind="saved_event", target_id=target_id)

    assert ReminderPlan.objects.filter(user_id=user_id, target_id=target_id).count() == 2


def test_reminder_plan_reads_as_its_target_and_slots():
    plan = ReminderPlanFactory.create(slots=["1d", "1hr"])

    assert str(plan) == "personal_event plan [1d, 1hr]"


def test_reminder_plan_reads_as_no_slots_when_empty():
    plan = ReminderPlanFactory.create(slots=[])

    assert str(plan) == "personal_event plan [none]"
