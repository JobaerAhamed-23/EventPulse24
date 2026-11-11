"""The editor's four verbs: what each one does, and every way each one refuses."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from apps.ingestion.models import (
    Event,
    EventStateChange,
    IngestionAuditEntry,
    ReviewItem,
    Source,
    SourceObservation,
)
from apps.ingestion.services.editorial_review import (
    approve_review_item,
    dismiss_source_item,
    edit_and_publish,
    reject_review_item,
)
from apps.ingestion.services.review_queue import raise_review_item
from domain.errors import ConflictError, ValidationError
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import EventFactory, SourceFactory, VenueFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
EDITOR = Actor.user(uuid4())
SYSTEM = Actor.system("ingest_pipeline")


def quarantined() -> tuple[Event, ReviewItem]:
    event = EventFactory(publication_status=Event.PublicationStatus.IN_REVIEW)
    item = raise_review_item(
        event=event, reason=ReviewItem.Reason.IN_REVIEW, actor=SYSTEM, now=NOW
    ).item
    return event, item


def reported() -> tuple[Event, ReviewItem]:
    event = EventFactory()
    item = raise_review_item(
        event=event,
        reason=ReviewItem.Reason.USER_REPORTED,
        category=ReviewItem.ReportCategory.WRONG_VENUE,
        actor=Actor.system("event_report"),
        now=NOW,
    ).item
    return event, item


def changes(event):
    return list(
        EventStateChange.objects.using(CATALOG).filter(event_id=event.pk).order_by("event_version")
    )


# ── Approve ──────────────────────────────────────────────────────────────────────────────


def test_approving_publishes_a_quarantined_event():
    event, item = quarantined()

    result = approve_review_item(item_id=item.pk, actor=EDITOR, now=NOW)

    event.refresh_from_db(using=CATALOG)
    assert event.publication_status == Event.PublicationStatus.PUBLISHED
    assert result.item.resolution == ReviewItem.Resolution.APPROVED
    assert result.item.resolved_by_id == EDITOR.id


def test_approving_a_reported_event_leaves_it_published():
    """A report never hid it, so "approve" here means "I looked, it is correct"."""
    event, item = reported()

    approve_review_item(item_id=item.pk, actor=EDITOR, now=NOW)

    event.refresh_from_db(using=CATALOG)
    assert event.publication_status == Event.PublicationStatus.PUBLISHED


def test_approving_notifies_nobody():
    """Publication is not a lifecycle field: the event was never visible to have changed."""
    event, item = quarantined()

    approve_review_item(item_id=item.pk, actor=EDITOR, now=NOW)

    assert changes(event) == []


def test_approving_writes_an_audit_entry():
    _event, item = quarantined()

    approve_review_item(item_id=item.pk, actor=EDITOR, now=NOW)

    entry = IngestionAuditEntry.objects.using(CATALOG).get(action="review_item_approved")
    assert entry.actor_id == EDITOR.id


# ── One verdict closes every open item (D2) ──────────────────────────────────────────────


def test_one_verdict_closes_every_open_item_on_the_event():
    """`review-queue-model` D2 pinned this here: the editor decides once.

    An event can be quarantined *and* reported — two questions, one decision.
    """
    event = EventFactory(publication_status=Event.PublicationStatus.IN_REVIEW)
    raise_review_item(event=event, reason=ReviewItem.Reason.IN_REVIEW, actor=SYSTEM, now=NOW)
    reported_item = raise_review_item(
        event=event,
        reason=ReviewItem.Reason.USER_REPORTED,
        category=ReviewItem.ReportCategory.DUPLICATE,
        actor=Actor.system("event_report"),
        now=NOW,
    ).item
    assert ReviewItem.objects.using(CATALOG).filter(event=event, status="open").count() == 2

    result = approve_review_item(item_id=reported_item.pk, actor=EDITOR, now=NOW)

    assert result.closed == 2
    assert ReviewItem.objects.using(CATALOG).filter(event=event, status="open").count() == 0


# ── Edit ─────────────────────────────────────────────────────────────────────────────────


def test_editing_the_time_bumps_the_version_and_appends_a_state_change():
    """The edit rides ingestion's own path, so AD-17 carries it to saved users."""
    event, item = quarantined()
    moved = event.start_time_utc + timedelta(hours=2)

    edit_and_publish(item_id=item.pk, actor=EDITOR, fields={"start_time_utc": moved}, now=NOW)

    event.refresh_from_db(using=CATALOG)
    assert event.start_time_utc == moved
    assert event.event_version == 2
    assert [c.kind for c in changes(event)] == [EventStateChange.Kind.TIME_MOVED]
    assert changes(event)[0].actor_id == EDITOR.id


def test_editing_only_the_title_notifies_nobody():
    """`domain/notices.py` already decided a typo fix is not an email."""
    event, item = quarantined()

    edit_and_publish(item_id=item.pk, actor=EDITOR, fields={"title": "Corrected Title"}, now=NOW)

    event.refresh_from_db(using=CATALOG)
    assert event.title == "Corrected Title"
    assert event.event_version == 1
    assert changes(event) == []


def test_editing_publishes_the_event_and_closes_the_item():
    event, item = quarantined()

    result = edit_and_publish(item_id=item.pk, actor=EDITOR, fields={"title": "Fixed"}, now=NOW)

    event.refresh_from_db(using=CATALOG)
    assert event.publication_status == Event.PublicationStatus.PUBLISHED
    assert result.item.resolution == ReviewItem.Resolution.EDITED


def test_editing_a_field_that_is_not_editable_is_refused():
    """The slug is a public URL; the source is identity (AD-4). Neither is the editor's."""
    _event, item = quarantined()

    with pytest.raises(ValidationError) as excinfo:
        edit_and_publish(item_id=item.pk, actor=EDITOR, fields={"slug": "new-slug"}, now=NOW)

    assert excinfo.value.details["errors"][0]["loc"] == ["slug"]


def test_editing_nothing_is_refused():
    _event, item = quarantined()

    with pytest.raises(ValidationError, match="Nothing to change"):
        edit_and_publish(item_id=item.pk, actor=EDITOR, fields={}, now=NOW)


def test_editing_the_venue_is_a_lifecycle_change():
    event, item = quarantined()
    venue = VenueFactory(city=event.venue.city, venue_fingerprint=f"v|{uuid4()}")

    edit_and_publish(item_id=item.pk, actor=EDITOR, fields={"venue_id": venue.id}, now=NOW)

    event.refresh_from_db(using=CATALOG)
    assert event.venue_id == venue.id
    assert event.event_version == 2


# ── Reject ───────────────────────────────────────────────────────────────────────────────


def test_rejecting_hides_the_event_and_closes_the_item_as_rejected():
    """**The gap `event-rejection-state` left open, now closed.**

    `reject_event` owns the state transition and says nothing about the queue; this is the
    caller that records the verdict with the editor's name on it.
    """
    event, item = quarantined()

    result = reject_review_item(item_id=item.pk, actor=EDITOR, now=NOW)

    event.refresh_from_db(using=CATALOG)
    assert event.publication_status == Event.PublicationStatus.REJECTED
    assert result.item.resolution == ReviewItem.Resolution.REJECTED
    assert result.item.resolved_by_id == EDITOR.id


def test_rejecting_delists_through_the_outbox():
    event, item = quarantined()

    reject_review_item(item_id=item.pk, actor=EDITOR, now=NOW)

    assert [c.kind for c in changes(event)] == [EventStateChange.Kind.DELISTED]


# ── Dismiss ──────────────────────────────────────────────────────────────────────────────


def source_item() -> tuple[Source, ReviewItem]:
    source = SourceFactory()
    item = raise_review_item(
        source=source, reason=ReviewItem.Reason.SOURCE_RELIABILITY, actor=SYSTEM, now=NOW
    ).item
    return source, item


def test_dismissing_closes_the_item():
    _source, item = source_item()

    result = dismiss_source_item(item_id=item.pk, actor=EDITOR, now=NOW)

    assert result.item.resolution == ReviewItem.Resolution.DISMISSED


def test_dismissing_never_touches_the_source():
    """**FR-16: escalation, never removal.** Asserted, not left to the absence of a line."""
    source, item = source_item()
    before = Source.objects.using(CATALOG).values().get(pk=source.pk)

    dismiss_source_item(item_id=item.pk, actor=EDITOR, now=NOW)

    assert Source.objects.using(CATALOG).values().get(pk=source.pk) == before
    assert source.status == Source.Status.ACTIVE


def test_dismissing_an_event_item_is_refused():
    _event, item = quarantined()

    with pytest.raises(ValidationError, match="about an event"):
        dismiss_source_item(item_id=item.pk, actor=EDITOR, now=NOW)


def test_approving_a_source_item_is_refused():
    _source, item = source_item()

    with pytest.raises(ValidationError, match="about a source"):
        approve_review_item(item_id=item.pk, actor=EDITOR, now=NOW)


# ── Refusals ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("command", [approve_review_item, reject_review_item])
def test_a_system_actor_cannot_record_a_verdict(command):
    """AD-14. `ReviewItem`'s D6 check enforces it at the database too."""
    _event, item = quarantined()

    with pytest.raises(ValidationError, match="user actor"):
        command(item_id=item.pk, actor=SYSTEM, now=NOW)


def test_resolving_an_already_resolved_item_is_refused():
    _event, item = quarantined()
    approve_review_item(item_id=item.pk, actor=EDITOR, now=NOW)

    with pytest.raises(ConflictError) as excinfo:
        approve_review_item(item_id=item.pk, actor=EDITOR, now=NOW)

    assert "item_already_resolved" in excinfo.value.details["errors"]


def test_a_stale_event_version_is_refused():
    """**An editor never overwrites an ingestion update they did not see.**

    The version is what their page was rendered from; if it has moved, the edit in front of
    them describes facts that no longer hold.
    """
    _event, item = quarantined()

    with pytest.raises(ConflictError) as excinfo:
        approve_review_item(item_id=item.pk, actor=EDITOR, expected_event_version=99, now=NOW)

    assert "event_version_stale" in excinfo.value.details["errors"]
    assert excinfo.value.details["actual"] == 1


def test_the_right_event_version_is_accepted():
    _event, item = quarantined()

    result = approve_review_item(item_id=item.pk, actor=EDITOR, expected_event_version=1, now=NOW)

    assert result.item.resolution == ReviewItem.Resolution.APPROVED


def test_an_unknown_item_is_refused():
    with pytest.raises(ValidationError, match="No such review item"):
        approve_review_item(item_id=uuid4(), actor=EDITOR, now=NOW)


# ── FR-16 observations ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("command", "kind"),
    [
        (approve_review_item, SourceObservation.Kind.APPROVED),
        (reject_review_item, SourceObservation.Kind.REJECTED),
    ],
)
def test_each_verdict_records_an_observation_against_the_source(command, kind):
    event, item = quarantined()

    command(item_id=item.pk, actor=EDITOR, now=NOW)

    observation = SourceObservation.objects.using(CATALOG).get(review_item=item)
    assert observation.kind == kind
    assert observation.source_id == event.source_id
    assert observation.event_id == event.pk
    assert observation.actor_id == EDITOR.id


def test_an_edit_records_its_own_observation_kind():
    """**The sign of an edit is deferred, so it is stored as its own fact.**

    `reliability-recompute-and-escalation` decides what an edit is worth; this item records
    that one happened.
    """
    _event, item = quarantined()

    edit_and_publish(item_id=item.pk, actor=EDITOR, fields={"title": "Fixed"}, now=NOW)

    assert (
        SourceObservation.objects.using(CATALOG).get(review_item=item).kind
        == SourceObservation.Kind.EDITED
    )


def test_a_dismissal_records_an_observation_with_no_event():
    source, item = source_item()

    dismiss_source_item(item_id=item.pk, actor=EDITOR, now=NOW)

    observation = SourceObservation.objects.using(CATALOG).get(review_item=item)
    assert observation.event_id is None
    assert observation.source_id == source.pk


# ── The remaining branches ───────────────────────────────────────────────────────────────


def test_editing_to_an_unknown_venue_is_refused():
    """Caught in the command, so the FK's own error never reaches an editor."""
    _event, item = quarantined()

    with pytest.raises(ValidationError) as excinfo:
        edit_and_publish(item_id=item.pk, actor=EDITOR, fields={"venue_id": uuid4()}, now=NOW)

    assert excinfo.value.details["errors"][0]["loc"] == ["venue_id"]


def test_editing_a_lifecycle_field_to_its_current_value_changes_nothing():
    """`classify_change` finds no difference, so there is no version to bump.

    The edit still publishes and still closes the item: the editor looked and decided, and
    that decision is worth recording even when the facts turn out to be already right.
    """
    event, item = quarantined()

    result = edit_and_publish(
        item_id=item.pk,
        actor=EDITOR,
        fields={"start_time_utc": event.start_time_utc},
        now=NOW,
    )

    event.refresh_from_db(using=CATALOG)
    assert event.event_version == 1
    assert changes(event) == []
    assert event.publication_status == Event.PublicationStatus.PUBLISHED
    assert result.item.resolution == ReviewItem.Resolution.EDITED


def test_closing_an_event_with_no_open_items_is_a_no_op():
    """Reachable when a verdict lands on an event whose items closed under it.

    The command still records its observation and its audit row — what the editor decided
    is a fact about the source whether or not a queue row was there to close.
    """
    from apps.ingestion.services.editorial_review import _close_open_items

    event = EventFactory()

    closed, ids = _close_open_items(
        event=event, resolution=ReviewItem.Resolution.APPROVED, actor=EDITOR, now=NOW
    )

    assert (closed, ids) == (0, [])
