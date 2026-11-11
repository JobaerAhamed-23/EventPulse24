"""The FR-57 review queue in Django admin (AD-14): where an editor actually works.

These tests drive the admin through the Django test client, because the AC is about the
*surface*: the list an editor reads, the verdict they give, the refusal they see when the
world moved under them, and who is allowed in at all.

**Nothing here writes through the ORM.** Every mutation the tests observe is a command's
write, seen through the audit row it left.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.urls import reverse

from apps.ingestion.models import Event, IngestionAuditEntry, ReviewItem, Source
from apps.ingestion.services.review_queue import raise_review_item
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import EventFactory, ReviewItemFactory, SourceFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
SYSTEM = Actor.system("event_report")

CHANGELIST = "admin:ingestion_reviewitem_changelist"


# --- the people ----------------------------------------------------------------------------------


def _user(*, staff=True, superuser=False, email="editor@example.test"):
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
    """The `editorial` group, with exactly the two review permissions.

    **The group is a bundle of permissions, and the permissions are the rule.** A member
    gets `change_reviewitem` and `view_reviewitem`; a reviewer granted one directly works
    the queue too, and that is right — Django's permission model is per-permission.
    """
    group, _created = Group.objects.using(PERSONAL).get_or_create(name="editorial")
    permissions = Permission.objects.using(PERSONAL).filter(
        content_type__app_label="ingestion",
        codename__in=("change_reviewitem", "view_reviewitem"),
    )
    group.permissions.set(permissions)
    return group


@pytest.fixture
def editor():
    """A staff member of the editorial group. **Not a superuser** — the AC says one is not
    required, so the case that works is the one that has to work without one."""
    user = _user(email="group-member@example.test")
    user.groups.add(_editorial_group())
    return user


@pytest.fixture
def client(client, editor):
    client.force_login(editor)
    return client


# --- the queue's contents ------------------------------------------------------------------------


def _quarantined():
    event = EventFactory(publication_status=Event.PublicationStatus.IN_REVIEW)
    item = raise_review_item(
        event=event,
        reason=ReviewItem.Reason.IN_REVIEW,
        actor=Actor.system("ingest_pipeline"),
        now=NOW,
    ).item
    return event, item


def _reported(*, due_at=None, category=ReviewItem.ReportCategory.WRONG_VENUE):
    event = EventFactory()
    item = raise_review_item(
        event=event,
        reason=ReviewItem.Reason.USER_REPORTED,
        category=category,
        actor=SYSTEM,
        now=NOW,
    ).item
    if due_at is not None:
        ReviewItem.objects.using(CATALOG).filter(pk=item.pk).update(due_at=due_at)
        item.refresh_from_db(using=CATALOG)
    return event, item


def _source_item():
    source = SourceFactory()
    item = raise_review_item(
        source=source,
        reason=ReviewItem.Reason.SOURCE_RELIABILITY,
        actor=Actor.system("reliability_recompute"),
        now=NOW,
    ).item
    return source, item


def _resolve(item, *, resolution=ReviewItem.Resolution.APPROVED):
    """Mark an item resolved the way the database insists on.

    **The check constraint demands the whole resolution**, not just the status: a resolved
    row carries a resolver (`resolved_by_kind="user"` and an id), a moment, and a
    resolution that fits its target. Setting only `status` would be refused by the
    constraint, which is the point of the constraint.
    """
    ReviewItem.objects.using(CATALOG).filter(pk=item.pk).update(
        status=ReviewItem.Status.RESOLVED,
        resolution=resolution,
        resolved_at=datetime.now(UTC),
        resolved_by_kind="user",
        resolved_by_id=uuid4(),
        resolved_by_label="",
    )
    item.refresh_from_db(using=CATALOG)
    return item


def _audit(**filters) -> list[IngestionAuditEntry]:
    return list(IngestionAuditEntry.objects.using(CATALOG).filter(**filters).order_by("id"))


# --- the changelist ------------------------------------------------------------------------------


def test_changelist_lists_open_items_first(client):
    """Open items come before resolved ones, whatever their priority."""
    event, item = _quarantined()
    resolved = _resolve(ReviewItemFactory())

    response = client.get(reverse(CHANGELIST))

    assert response.status_code == 200
    body = response.content.decode()
    assert body.index(str(item.pk)) < body.index(str(resolved.pk))


def test_changelist_orders_by_priority_then_deadline(client):
    """`user_reported` first, then `source_reliability`, then `in_review`.

    **The order is derived from the reason**, because `ReviewItem` has no priority column:
    `review-intake-and-backfill` D1 declined to add one. `shared.constants.REVIEW_PRIORITY`
    is the mapping, and it is applied in the database as one `Case/When`.
    """
    report_event, report = _reported(due_at=NOW + timedelta(hours=20))
    source, source_item = _source_item()
    quarantined_event, quarantined_item = _quarantined()

    response = client.get(reverse(CHANGELIST))

    body = response.content.decode()
    assert body.index(str(report.pk)) < body.index(str(source_item.pk))
    assert body.index(str(source_item.pk)) < body.index(str(quarantined_item.pk))
    assert report_event.pk and source.pk and quarantined_event.pk


def test_changelist_orders_reports_by_due_at_within_a_priority_band(client):
    """Two reports: the one whose deadline is nearer comes first."""
    _event_a, later = _reported(due_at=NOW + timedelta(hours=20))
    _event_b, nearer = _reported(due_at=NOW + timedelta(hours=2))

    response = client.get(reverse(CHANGELIST))

    body = response.content.decode()
    assert body.index(str(nearer.pk)) < body.index(str(later.pk))


def test_changelist_marks_a_report_past_its_sla(client):
    """A `user_reported` item past its 24h deadline is visibly marked."""
    _event, overdue = _reported(due_at=datetime.now(UTC) - timedelta(hours=1))
    _event2, within = _reported(due_at=datetime.now(UTC) + timedelta(hours=1))

    response = client.get(reverse(CHANGELIST))

    body = response.content.decode()
    assert "Overdue" in body
    # The mark is on the overdue row and not on the one still inside its window.
    overdue_row = body[body.index(str(overdue.pk)) : body.index(str(overdue.pk)) + 2000]
    within_row = body[body.index(str(within.pk)) : body.index(str(within.pk)) + 2000]
    assert "icon-yes.svg" in overdue_row
    assert "icon-no.svg" in within_row


def test_changelist_does_not_mark_a_non_report_item_overdue(client):
    """Only a `user_reported` item has a deadline, so only one can be overdue."""
    _source, source_item = _source_item()

    response = client.get(reverse(CHANGELIST))

    body = response.content.decode()
    row = body[body.index(str(source_item.pk)) : body.index(str(source_item.pk)) + 2000]
    assert "icon-yes.svg" not in row


def test_changelist_is_filterable_by_reason_status_and_source(client):
    """The three filters the AC names."""
    _event, report = _reported()
    source, source_item = _source_item()

    by_reason = client.get(reverse(CHANGELIST), {"reason": "source_reliability"})
    body = by_reason.content.decode()
    assert str(source_item.pk) in body
    assert str(report.pk) not in body

    by_status = client.get(reverse(CHANGELIST), {"status": "open"})
    assert by_status.status_code == 200

    # A related field's filter keys on the target's pk: `source__id__exact`.
    by_source = client.get(reverse(CHANGELIST), {"source__id__exact": str(source.pk)})
    body = by_source.content.decode()
    assert by_source.status_code == 200
    assert str(source_item.pk) in body
    assert str(report.pk) not in body


def test_changelist_shows_the_three_fr57_metrics(client):
    """The summary: queue size, the age of the oldest open item, and the SLA breaches.

    **The numbers are computed by the read service**, so the context carries the
    `QueueSummary` itself rather than three loose values.
    """
    _event, overdue = _reported(due_at=datetime.now(UTC) - timedelta(hours=1))
    _event2, other = _reported(due_at=datetime.now(UTC) + timedelta(hours=1))

    response = client.get(reverse(CHANGELIST))

    summary = response.context["queue_summary"]
    assert summary.queue_size == 2
    assert summary.sla_breaches == 1
    assert summary.oldest_open_age is not None
    # The template lays them out; the numbers themselves come from the service.
    body = response.content.decode()
    assert 'data-field="queue-size"' in body
    assert 'data-field="oldest-open-age"' in body
    assert 'data-field="sla-breaches"' in body


def test_changelist_summary_counts_open_items_only(client):
    """A resolved item is history, and counting it would make the queue look bigger."""
    _event, item = _quarantined()
    _resolve(item)

    response = client.get(reverse(CHANGELIST))

    assert response.context["queue_summary"].queue_size == 0


# --- the change page -----------------------------------------------------------------------------


def test_change_page_shows_the_facts_an_editor_decides_on(client):
    """The event's current facts, the source and its badge, and the report tallies."""
    event, item = _reported()
    ReviewItem.objects.using(CATALOG).filter(pk=item.pk).update(
        reports_wrong_venue=3, reports_duplicate=1
    )

    response = client.get(reverse("admin:ingestion_reviewitem_change", args=[item.pk]))

    assert response.status_code == 200
    body = response.content.decode()
    assert event.title in body
    assert event.source.name in body
    assert "wrong venue: 3" in body
    assert "duplicate: 1" in body


def test_change_page_shows_no_reporter_identities(client):
    """The AC forbids them, and the `ReviewItem` row cannot carry them: there is no user
    column on it (D4 of `review-queue-model`). The reporter lives in `personal`."""
    _event, item = _reported()

    response = client.get(reverse("admin:ingestion_reviewitem_change", args=[item.pk]))

    body = response.content.decode()
    assert "reporter" not in body.lower()
    assert "reported by" not in body.lower()


def test_change_page_for_a_source_item_shows_its_verdict_history(client):
    """A source item shows the observations the reliability score is computed from."""
    source, item = _source_item()

    response = client.get(reverse("admin:ingestion_reviewitem_change", args=[item.pk]))

    assert response.status_code == 200
    body = response.content.decode()
    assert source.name in body
    assert "The score is computed from these:" in body


def test_change_page_for_a_source_item_shows_the_stored_score(client):
    """**The score is shown, and it is the stored one.**

    FR-16's score is computed and stored by `reliability-recompute-and-escalation`, so the
    admin reads `Source.reliability_score` rather than recomputing it — recomputing here
    would be a second implementation of that work item's job, and two implementations of one
    score are two truths.
    """
    source, item = _source_item()
    Source.objects.using(CATALOG).filter(pk=source.pk).update(
        reliability_score=Decimal("0.42"), reliability_scored_at=NOW
    )

    response = client.get(reverse("admin:ingestion_reviewitem_change", args=[item.pk]))

    body = response.content.decode()
    assert "Reliability score: 0.42" in body


def test_change_page_shows_the_prior_for_a_source_that_has_not_been_scored(client):
    """**A source with no computed row reads as the 0.50 prior**, and the page says so —
    it does not show a score it does not have."""
    source, item = _source_item()

    response = client.get(reverse("admin:ingestion_reviewitem_change", args=[item.pk]))

    body = response.content.decode()
    assert "Reliability score: 0.50" in body
    assert "not yet computed" in body


def test_change_page_has_no_add_page(client):
    """A review item is raised by the commands that own the queue, never typed in."""
    assert client.get(reverse("admin:ingestion_reviewitem_add")).status_code == 403


# --- the verdicts --------------------------------------------------------------------------------


def test_approve_action_runs_the_approve_command(client, editor):
    event, item = _quarantined()

    response = client.post(
        reverse(CHANGELIST),
        {"action": "approve_items", "_selected_action": [str(item.pk)]},
    )

    assert response.status_code == 302
    stored = ReviewItem.objects.using(CATALOG).get(pk=item.pk)
    assert (stored.status, stored.resolution) == (ReviewItem.Status.RESOLVED, "approved")
    event.refresh_from_db(using=CATALOG)
    assert event.publication_status == Event.PublicationStatus.PUBLISHED
    [entry] = _audit(action="review_item_approved")
    assert entry.actor_id == editor.pk


def test_reject_action_runs_the_reject_command(client, editor):
    event, item = _quarantined()

    client.post(
        reverse(CHANGELIST),
        {"action": "reject_items", "_selected_action": [str(item.pk)]},
    )

    stored = ReviewItem.objects.using(CATALOG).get(pk=item.pk)
    assert (stored.status, stored.resolution) == (ReviewItem.Status.RESOLVED, "rejected")
    event.refresh_from_db(using=CATALOG)
    assert event.publication_status == Event.PublicationStatus.REJECTED
    [entry] = _audit(action="review_item_rejected")
    assert entry.actor_id == editor.pk


def test_dismiss_action_runs_the_dismiss_command_and_leaves_the_source_alone(client, editor):
    """FR-16 is escalation, never removal: dismissing an item touches no Source column."""
    source, item = _source_item()

    client.post(
        reverse(CHANGELIST),
        {"action": "dismiss_items", "_selected_action": [str(item.pk)]},
    )

    stored = ReviewItem.objects.using(CATALOG).get(pk=item.pk)
    assert (stored.status, stored.resolution) == (ReviewItem.Status.RESOLVED, "dismissed")
    source.refresh_from_db(using=CATALOG)
    assert source.status == "active"
    [entry] = _audit(action="review_item_dismissed")
    assert entry.actor_id == editor.pk


def test_an_action_on_an_already_resolved_item_reports_a_refusal(client):
    """A refusal is a message on the page, not a 500 and not a silent success."""
    _event, item = _quarantined()
    _resolve(item)

    response = client.post(
        reverse(CHANGELIST),
        {"action": "approve_items", "_selected_action": [str(item.pk)]},
        follow=True,
    )

    assert response.status_code == 200
    assert "already resolved" in response.content.decode()


def test_the_changelist_offers_exactly_the_three_verdicts(client):
    _quarantined()

    response = client.get(reverse(CHANGELIST))

    actions = [name for name, _label in response.context["action_form"].fields["action"].choices]
    assert actions == ["", "approve_items", "reject_items", "dismiss_items"]


# --- the edit form -------------------------------------------------------------------------------


def _edit_form(item, event, **overrides) -> dict:
    data = {
        "title": event.title,
        "start_time_utc": event.start_time_utc.strftime("%Y-%m-%d %H:%M:%S"),
        "end_time_utc": "",
        "start_time_tz": event.start_time_tz,
        "venue": str(event.venue_id) if event.venue_id else "",
        "expected_event_version": str(event.event_version),
    }
    return data | overrides


def test_edit_form_corrects_the_event_and_closes_the_item(client, editor):
    event, item = _quarantined()
    form = _edit_form(item, event, title="The corrected title")

    response = client.post(reverse("admin:ingestion_reviewitem_change", args=[item.pk]), form)

    assert response.status_code == 302
    event.refresh_from_db(using=CATALOG)
    assert event.title == "The corrected title"
    stored = ReviewItem.objects.using(CATALOG).get(pk=item.pk)
    assert (stored.status, stored.resolution) == (ReviewItem.Status.RESOLVED, "edited")
    [entry] = _audit(action="review_item_edited")
    assert entry.actor_id == editor.pk


def test_the_change_page_carries_the_expected_event_version(client):
    """The staleness token is **on the page**, not only in the tests.

    **This test exists because the token was once invisible.** The field was declared on
    the form but named in no fieldset, so Django never rendered it. A real browser
    therefore posted no token at all, the command's `expected_event_version is not None`
    check short-circuited, and the optimistic lock was quietly absent in production while
    every test — which posted the field by hand — passed.

    A test that hand-builds the POST body cannot catch this. Only one that reads the
    rendered page can.
    """
    event, item = _quarantined()

    response = client.get(reverse("admin:ingestion_reviewitem_change", args=[item.pk]))

    body = response.content.decode()
    assert 'name="expected_event_version"' in body
    assert f'value="{event.event_version}"' in body


def test_the_edit_form_refuses_a_post_without_the_staleness_token(client):
    """A post that carries no token is refused, not silently accepted.

    **The check fails closed.** If the token is missing, the safest reading is that the
    editor's page is stale or was tampered with — either way the answer is a refusal,
    not a write that skips the lock.
    """
    event, item = _quarantined()
    form = _edit_form(item, event, title="The corrected title")
    del form["expected_event_version"]

    response = client.post(reverse("admin:ingestion_reviewitem_change", args=[item.pk]), form)

    assert response.status_code == 200
    event.refresh_from_db(using=CATALOG)
    assert event.title != "The corrected title"
    assert ReviewItem.objects.using(CATALOG).get(pk=item.pk).status == ReviewItem.Status.OPEN


def test_edit_form_shows_a_stale_version_refusal_on_the_form(client):
    """The event moved while the editor was looking at it: the form says so, and nothing
    is written."""
    event, item = _quarantined()
    form = _edit_form(item, event, title="The corrected title", expected_event_version="999")

    response = client.post(reverse("admin:ingestion_reviewitem_change", args=[item.pk]), form)

    assert response.status_code == 200
    assert "changed while you were looking at it" in response.content.decode()
    event.refresh_from_db(using=CATALOG)
    assert event.title != "The corrected title"
    assert ReviewItem.objects.using(CATALOG).get(pk=item.pk).status == ReviewItem.Status.OPEN


def test_edit_form_shows_an_already_resolved_refusal_on_the_form(client):
    """Someone else got there first: a message on the form, not a 500."""
    event, item = _quarantined()
    _resolve(item)
    form = _edit_form(item, event, title="The corrected title")

    response = client.post(reverse("admin:ingestion_reviewitem_change", args=[item.pk]), form)

    assert response.status_code == 200
    assert "already resolved" in response.content.decode()
    event.refresh_from_db(using=CATALOG)
    assert event.title != "The corrected title"


def test_edit_form_with_nothing_changed_shows_a_refusal(client):
    """An edit that changes nothing is refused, and the item stays open."""
    event, item = _quarantined()
    form = _edit_form(item, event)

    response = client.post(reverse("admin:ingestion_reviewitem_change", args=[item.pk]), form)

    assert response.status_code == 200
    assert "Nothing to change" in response.content.decode()
    assert ReviewItem.objects.using(CATALOG).get(pk=item.pk).status == ReviewItem.Status.OPEN


def test_edit_form_offers_only_the_editable_fields(client):
    """The slug, the source, the confidences and the publication status are not editable."""
    event, item = _quarantined()

    response = client.get(reverse("admin:ingestion_reviewitem_change", args=[item.pk]))

    body = response.content.decode()
    assert b'name="title"' in response.content
    assert b'name="start_time_utc"' in response.content
    assert b'name="slug"' not in response.content
    assert b'name="publication_status"' not in response.content
    assert b'name="extraction_confidence"' not in response.content
    assert body  # the page rendered


# --- delete is off -------------------------------------------------------------------------------


def test_delete_returns_403(client):
    """Delete is disabled on every editorial view: a resolved item is history."""
    _event, item = _quarantined()

    response = client.post(
        reverse("admin:ingestion_reviewitem_delete", args=[item.pk]), {"post": "yes"}
    )

    assert response.status_code == 403
    assert ReviewItem.objects.using(CATALOG).filter(pk=item.pk).exists()


def test_no_action_bypasses_a_command(client, editor):
    """Every verdict leaves an audit row, and only the commands write one.

    **The raise is audited too**, so the rows are the raise and then the verdict — and
    nothing else. An admin that wrote the row itself would leave no second row.
    """
    event, item = _quarantined()

    client.post(
        reverse(CHANGELIST),
        {"action": "approve_items", "_selected_action": [str(item.pk)]},
    )

    actions = [entry.action for entry in _audit(target_id=item.pk)]
    assert actions == ["review_item_raised", "review_item_approved"]
