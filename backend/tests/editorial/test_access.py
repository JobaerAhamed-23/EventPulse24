"""Who may work the FR-57 queue (AD-14).

The AC asks for four cases and says each one is tested, **including the negative ones**:

| Case | Result |
|---|---|
| A member of the editorial group | allowed |
| A signed-in user who is not staff | refused |
| A staff user without the group | refused |
| A superuser | allowed — **but not required** |

**The rule is the permission, not the group.** Django's model permissions are
per-permission, and a group is only one way to hold one; a reviewer granted
`change_reviewitem` directly works the queue exactly as a group member does.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.urls import reverse

from apps.editorial.services.review_queue import (
    EDITORIAL_GROUP,
    REVIEW_PERMISSIONS,
    editor_name,
    may_review,
    may_view,
    queue_view,
)
from apps.ingestion.models import Event, IngestionAuditEntry, ReviewItem
from apps.ingestion.services.review_queue import raise_review_item
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import EventFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

CHANGELIST = "admin:ingestion_reviewitem_changelist"


def _user(*, staff=True, superuser=False, email="someone@example.test"):
    return (
        get_user_model()
        .objects.db_manager(PERSONAL)
        .create_user(
            email=email,
            password="not-used-in-tests",
            is_staff=staff,
            is_superuser=superuser,
        )
    )


def _editorial_group() -> Group:
    group, _created = Group.objects.using(PERSONAL).get_or_create(name=EDITORIAL_GROUP)
    permissions = Permission.objects.using(PERSONAL).filter(
        content_type__app_label="ingestion",
        codename__in=("change_reviewitem", "view_reviewitem"),
    )
    group.permissions.set(permissions)
    return group


@pytest.fixture
def item():
    event = EventFactory(publication_status=Event.PublicationStatus.IN_REVIEW)
    return raise_review_item(
        event=event,
        reason=ReviewItem.Reason.IN_REVIEW,
        actor=Actor.system("ingest_pipeline"),
    ).item


# --- the rule ------------------------------------------------------------------------------------


def test_a_member_of_the_editorial_group_may_review():
    user = _user(email="member@example.test")
    user.groups.add(_editorial_group())

    assert may_review(user) is True


def test_a_signed_in_user_who_is_not_staff_is_refused():
    """A customer account is not a reviewer, however many permissions it holds."""
    user = _user(staff=False, email="customer@example.test")
    user.groups.add(_editorial_group())

    assert may_review(user) is False


def test_a_staff_user_without_the_review_permission_is_refused():
    """Staff gets them into the admin index; the review permission is what opens the queue."""
    user = _user(staff=True, email="staff@example.test")

    assert may_review(user) is False


def test_a_staff_user_with_an_unrelated_permission_is_refused():
    """Holding *some* ingestion permission is not the same as holding the review one."""
    user = _user(email="sourcekeeper@example.test")
    user.user_permissions.set(
        Permission.objects.using(PERSONAL).filter(
            content_type__app_label="ingestion", codename="view_source"
        )
    )

    assert may_review(user) is False


def test_a_superuser_may_review():
    """A superuser holds every permission, so a superuser passes."""
    user = _user(superuser=True, email="root@example.test")

    assert may_review(user) is True


def test_superuser_is_not_required():
    """The AC's positive case is a group member with no superuser flag at all."""
    user = _user(superuser=False, email="member@example.test")
    user.groups.add(_editorial_group())

    assert user.is_superuser is False
    assert may_review(user) is True


def test_an_anonymous_user_is_refused():
    from django.contrib.auth.models import AnonymousUser

    assert may_review(AnonymousUser()) is False
    assert may_review(None) is False


def test_a_directly_granted_permission_is_enough():
    """The permissions are the rule; the group is one way to hold them."""
    user = _user(email="direct@example.test")
    user.user_permissions.set(
        Permission.objects.using(PERSONAL).filter(
            content_type__app_label="ingestion",
            codename__in=("change_reviewitem", "view_reviewitem"),
        )
    )

    assert may_review(user) is True


def test_the_review_permissions_are_the_two_ingestion_ones():
    assert REVIEW_PERMISSIONS == ("ingestion.change_reviewitem", "ingestion.view_reviewitem")


# --- reading is not working ---------------------------------------------------------------------


def test_may_view_is_true_for_a_view_only_user():
    """Reading the queue is what `view_reviewitem` is for."""
    user = _user(email="reader@example.test")
    user.user_permissions.set(
        Permission.objects.using(PERSONAL).filter(
            content_type__app_label="ingestion", codename="view_reviewitem"
        )
    )

    assert may_view(user) is True
    assert may_review(user) is False


def test_may_view_is_true_for_a_reviewer():
    """`change_reviewitem` implies the ability to read."""
    user = _user(email="worker@example.test")
    user.user_permissions.set(
        Permission.objects.using(PERSONAL).filter(
            content_type__app_label="ingestion", codename="change_reviewitem"
        )
    )

    assert may_view(user) is True
    assert may_review(user) is True


def test_may_view_is_false_for_a_user_with_no_review_permission():
    user = _user(email="nobody@example.test")

    assert may_view(user) is False
    assert may_review(user) is False


def test_may_view_is_false_for_a_non_staff_user():
    """A customer account is not a reviewer, however many permissions it holds."""
    user = _user(staff=False, email="customer@example.test")
    user.user_permissions.set(
        Permission.objects.using(PERSONAL).filter(
            content_type__app_label="ingestion",
            codename__in=("change_reviewitem", "view_reviewitem"),
        )
    )

    assert may_view(user) is False
    assert may_review(user) is False


def test_may_view_is_false_for_an_anonymous_user():
    from django.contrib.auth.models import AnonymousUser

    assert may_view(AnonymousUser()) is False
    assert may_view(None) is False


# --- the reviewer's view of the whole queue ------------------------------------------------------


def test_queue_view_holds_the_queue_and_its_summary_at_one_instant():
    """**One instant for both.** The rows and the numbers describe the same moment, so a
    reviewer cannot see four rows beside a summary that says five."""
    from datetime import UTC, datetime

    moment = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
    view = queue_view(now=moment)

    assert view.now == moment
    assert view.summary.queue_size == len([row for row in view.items if row.status == "open"])
    assert view.summary.sla_breaches == len([row for row in view.items if row.sla_breached])


# --- the rule, through the admin -----------------------------------------------------------------


def test_a_group_member_reaches_the_queue(client, item):
    user = _user(email="member@example.test")
    user.groups.add(_editorial_group())
    client.force_login(user)

    response = client.get(reverse(CHANGELIST))

    assert response.status_code == 200


def test_a_non_staff_user_is_refused_the_queue(client, item):
    user = _user(staff=False, email="customer@example.test")
    user.groups.add(_editorial_group())
    client.force_login(user)

    response = client.get(reverse(CHANGELIST))

    assert response.status_code == 302
    assert "/admin/login/" in response.url


def test_a_staff_user_without_the_permission_is_refused_the_queue(client, item):
    user = _user(email="staff@example.test")
    client.force_login(user)

    response = client.get(reverse(CHANGELIST))

    assert response.status_code == 403


def test_an_anonymous_visitor_is_refused_the_queue(client, item):
    response = client.get(reverse(CHANGELIST))

    assert response.status_code == 302
    assert "/admin/login/" in response.url


def test_a_refused_user_cannot_act_on_the_queue(client, item):
    """A staff user without the permission cannot approve anything."""
    user = _user(email="staff@example.test")
    client.force_login(user)

    response = client.post(
        reverse(CHANGELIST),
        {"action": "approve_items", "_selected_action": [str(item.pk)]},
    )

    assert response.status_code == 403
    assert ReviewItem.objects.using(CATALOG).get(pk=item.pk).status == ReviewItem.Status.OPEN


def test_a_group_member_can_act_on_the_queue(client, item):
    user = _user(email="member@example.test")
    user.groups.add(_editorial_group())
    client.force_login(user)

    response = client.post(
        reverse(CHANGELIST),
        {"action": "approve_items", "_selected_action": [str(item.pk)]},
    )

    assert response.status_code == 302
    assert ReviewItem.objects.using(CATALOG).get(pk=item.pk).status == ReviewItem.Status.RESOLVED


# --- reading the queue is not writing to it ----------------------------------------------------


def _view_only_user():
    """A staff user holding **only** `view_reviewitem`.

    **This is the case the review found.** `may_review` originally accepted *either* of
    the two review permissions, and the admin used that one function for both the view
    gate and the change gate. So a read-only auditor could approve, reject, dismiss and
    edit-and-publish — publishing quarantined events and rewriting event facts with no
    more authority than they were given to read.
    """
    user = _user(email="auditor@example.test")
    user.user_permissions.set(
        Permission.objects.using(PERSONAL).filter(
            content_type__app_label="ingestion", codename="view_reviewitem"
        )
    )
    return user


def test_a_view_only_user_may_read_the_queue(client, item):
    """Reading the queue is what `view_reviewitem` is for."""
    user = _view_only_user()
    client.force_login(user)

    response = client.get(reverse(CHANGELIST))

    assert response.status_code == 200


def test_a_view_only_user_cannot_approve(client, item):
    """`view` does not grant `change`. The item stays open.

    **The property asserted is that nothing was written**, not the status code. Django
    filters the action out of `get_actions` for a user without the change permission, so
    the POST is a no-op that re-renders the page — a 200, not a 403. That is Django's
    behaviour and it is a safe one; what matters is that the item is untouched and no
    audit row was written.
    """
    user = _view_only_user()
    client.force_login(user)

    response = client.post(
        reverse(CHANGELIST),
        {"action": "approve_items", "_selected_action": [str(item.pk)]},
    )

    assert response.status_code in (200, 403)
    stored = ReviewItem.objects.using(CATALOG).get(pk=item.pk)
    assert stored.status == ReviewItem.Status.OPEN
    assert stored.resolution == ""
    # No *verdict* was recorded. The raise itself is audited, and that is the fixture's
    # own doing — the point is that nothing was recorded on top of it.
    assert (
        not IngestionAuditEntry.objects.using(CATALOG)
        .filter(
            action__in=("review_item_approved", "review_item_rejected", "review_item_dismissed")
        )
        .exists()
    )


def test_a_view_only_user_cannot_reject(client, item):
    user = _view_only_user()
    client.force_login(user)

    response = client.post(
        reverse(CHANGELIST),
        {"action": "reject_items", "_selected_action": [str(item.pk)]},
    )

    assert response.status_code in (200, 403)
    stored = ReviewItem.objects.using(CATALOG).get(pk=item.pk)
    assert stored.status == ReviewItem.Status.OPEN
    assert stored.resolution == ""


def test_a_view_only_user_cannot_dismiss(client, item):
    user = _view_only_user()
    client.force_login(user)

    response = client.post(
        reverse(CHANGELIST),
        {"action": "dismiss_items", "_selected_action": [str(item.pk)]},
    )

    assert response.status_code in (200, 403)
    stored = ReviewItem.objects.using(CATALOG).get(pk=item.pk)
    assert stored.status == ReviewItem.Status.OPEN
    assert stored.resolution == ""


def test_a_view_only_user_is_offered_no_verdict_actions(client, item):
    """The three verdicts are not in the dropdown for a read-only viewer.

    **The dropdown is not the enforcement** — the admin's own `_verdict` guard is, and
    the command layer refuses a non-editor actor. But a reviewer who is shown a button
    they cannot use has been told a lie about what they may do, so the choice list is
    checked as well.

    Django builds no action form at all when no action survives the permission filter,
    so the assertion is that the form is absent and the action names never reach the
    page.
    """
    user = _view_only_user()
    client.force_login(user)

    response = client.get(reverse(CHANGELIST))

    assert response.status_code == 200
    assert response.context["action_form"] is None
    body = response.content.decode()
    assert "approve_items" not in body
    assert "reject_items" not in body
    assert "dismiss_items" not in body


def test_a_view_only_user_cannot_edit_the_event(client, item):
    """The edit form is a write. A read-only user may not post it."""
    user = _view_only_user()
    client.force_login(user)
    event = item.event

    response = client.post(
        reverse("admin:ingestion_reviewitem_change", args=[item.pk]),
        {
            "title": "rewritten by an auditor",
            "start_time_utc": event.start_time_utc.strftime("%Y-%m-%d %H:%M:%S"),
            "end_time_utc": "",
            "start_time_tz": event.start_time_tz,
            "venue": str(event.venue_id) if event.venue_id else "",
            "expected_event_version": str(event.event_version),
        },
    )

    assert response.status_code == 403
    event.refresh_from_db(using=CATALOG)
    assert event.title != "rewritten by an auditor"
    assert ReviewItem.objects.using(CATALOG).get(pk=item.pk).status == ReviewItem.Status.OPEN


# --- the actor's name, for display only ----------------------------------------------------------


def test_editor_name_reads_the_name_from_personal_for_display():
    user = _user(email="named@example.test")

    assert editor_name(user.pk) == "named@example.test"


def test_editor_name_is_none_for_an_unknown_id():
    from uuid import uuid4

    assert editor_name(uuid4()) is None
    assert editor_name(None) is None
