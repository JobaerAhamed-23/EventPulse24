"""`ReviewItem`'s database rules (design: review-queue-model D1-D3, D6-D8, D11).

There is no Python guard on this model, so an ORM write reaches Postgres unfiltered; each
rejection asserts the *named* constraint (or the trigger's message and RestrictViolation), so
a test cannot pass because some other rule fired. Trigger tests use raw SQL on the catalog
connection, as tests/ingestion/test_triggers.py does.
"""

import re
from contextlib import contextmanager
from datetime import timedelta

import psycopg
import pytest
from django.db import IntegrityError, connections, transaction
from django.utils import timezone

from apps.ingestion.models import ReviewItem
from shared.db import CATALOG, PERSONAL
from shared.ids import uuid7
from shared.retention import RetentionCategory
from tests.ingestion.factories import EventFactory, ReviewItemFactory, SourceFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

TABLE = "catalog.ingestion_reviewitem"
NOW = timezone.now()
USER = uuid7()


@contextmanager
def violates(constraint: str):
    """Expect the block to fail on exactly this named constraint."""
    with pytest.raises(IntegrityError) as excinfo, transaction.atomic(using=CATALOG):
        yield
    assert excinfo.value.__cause__.diag.constraint_name == constraint


@contextmanager
def restricted(message: str):
    """Expect the block to fail in the guard trigger with this message."""
    with pytest.raises(IntegrityError) as excinfo, transaction.atomic(using=CATALOG):
        yield
    assert isinstance(excinfo.value.__cause__, psycopg.errors.RestrictViolation)
    assert message in str(excinfo.value.__cause__)


def execute(sql: str, params=()) -> int:
    with connections[CATALOG].cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.rowcount


def report(**overrides) -> ReviewItem:
    fields = {
        "reason": ReviewItem.Reason.USER_REPORTED,
        "due_at": NOW + timedelta(hours=24),
        "reports_wrong_venue": 1,
    }
    return ReviewItemFactory(**{**fields, **overrides})


def source_item(**overrides) -> ReviewItem:
    fields = {"reason": ReviewItem.Reason.SOURCE_RELIABILITY, "event": None}
    if "source" not in overrides:
        fields["source"] = SourceFactory()
    return ReviewItemFactory(**{**fields, **overrides})


def resolve(item: ReviewItem, resolution: str, **resolver) -> None:
    item.status = ReviewItem.Status.RESOLVED
    item.resolution = resolution
    item.resolved_at = NOW
    for name, value in resolver.items():
        setattr(item, f"resolved_by_{name}", value)
    item.save(using=CATALOG)


def editor(item: ReviewItem, resolution: str) -> None:
    resolve(item, resolution, kind="user", id=USER)


def job(item: ReviewItem, resolution: str) -> None:
    resolve(item, resolution, kind="system", label="ingest_pipeline")


# --- D1: the reason decides the target ---------------------------------------------------


def test_an_event_item_with_a_source_too_is_refused():
    with violates("review_item_target_ck"):
        ReviewItemFactory(source=SourceFactory())


def test_an_event_item_with_no_target_is_refused():
    with violates("review_item_target_ck"):
        ReviewItemFactory(event=None)


def test_a_source_item_with_an_event_is_refused():
    with violates("review_item_target_ck"):
        source_item(event=EventFactory())


def test_each_reason_accepts_its_own_target():
    assert ReviewItemFactory().event_id is not None
    assert report().event_id is not None
    assert source_item().source_id is not None


# --- D2: one open item per (target, reason) ----------------------------------------------


def test_a_second_open_item_for_the_same_event_and_reason_is_refused():
    first = ReviewItemFactory()

    with violates("review_item_open_event_reason_uq"):
        ReviewItemFactory(event=first.event)


def test_a_second_open_item_for_the_same_source_and_reason_is_refused():
    first = source_item()

    with violates("review_item_open_source_reason_uq"):
        source_item(source=first.source)


def test_the_same_event_may_have_one_open_item_per_reason():
    quarantined = ReviewItemFactory()

    reported = report(event=quarantined.event)

    assert reported.event_id == quarantined.event_id


def test_a_closed_item_does_not_block_a_new_open_one():
    first = ReviewItemFactory()
    editor(first, ReviewItem.Resolution.APPROVED)

    second = ReviewItemFactory(event=first.event)

    assert second.status == ReviewItem.Status.OPEN


# --- D3 and D8: tallies and the SLA belong to reports ------------------------------------


@pytest.mark.parametrize("column", list(ReviewItem.REPORT_FIELDS.values()))
def test_a_tally_on_a_non_report_item_is_refused(column):
    with violates("review_item_tallies_ck"):
        ReviewItemFactory(**{column: 1})


def test_a_report_without_a_deadline_is_refused():
    with violates("review_item_due_ck"):
        report(due_at=None)


@pytest.mark.parametrize("make", [ReviewItemFactory, source_item], ids=["in_review", "source"])
def test_a_deadline_on_a_non_report_item_is_refused(make):
    with violates("review_item_due_ck"):
        make(due_at=NOW)


def test_every_report_category_has_its_own_tally_column():
    """A fifth category without a column must fail here, not as a KeyError in a bump."""
    columns = {f.name for f in ReviewItem._meta.get_fields() if f.name.startswith("reports_")}

    assert set(ReviewItem.REPORT_FIELDS) == set(ReviewItem.ReportCategory)
    assert set(ReviewItem.REPORT_FIELDS.values()) == columns
    assert len(columns) == len(ReviewItem.ReportCategory)


def test_report_count_is_the_sum_of_the_tallies():
    item = report(reports_wrong_venue=2, reports_duplicate=3)

    assert item.report_count == 5


# --- D6: resolution consistency ----------------------------------------------------------


def test_an_open_item_with_a_resolution_is_refused():
    with violates("review_item_resolution_ck"):
        ReviewItemFactory(resolution=ReviewItem.Resolution.APPROVED)


def test_a_resolved_item_without_a_resolver_is_refused():
    item = ReviewItemFactory()

    with violates("review_item_resolution_ck"):
        resolve(item, ReviewItem.Resolution.APPROVED)


def test_a_resolved_item_without_a_time_is_refused():
    item = ReviewItemFactory()
    item.status, item.resolution = ReviewItem.Status.RESOLVED, ReviewItem.Resolution.APPROVED
    item.resolved_by_kind, item.resolved_by_id = "user", USER

    with violates("review_item_resolution_ck"):
        item.save(using=CATALOG)


@pytest.mark.parametrize("resolution", ["approved", "edited", "rejected"])
def test_an_editor_verdict_on_an_event_is_accepted(resolution):
    item = ReviewItemFactory()

    editor(item, resolution)

    item.refresh_from_db(using=CATALOG)
    assert item.resolution == resolution


@pytest.mark.parametrize("resolution", ["approved", "edited", "rejected"])
def test_a_verdict_recorded_by_a_job_is_refused(resolution):
    item = ReviewItemFactory()

    with violates("review_item_resolution_ck"):
        job(item, resolution)


def test_a_withdrawal_recorded_by_a_user_is_refused():
    item = ReviewItemFactory()

    with violates("review_item_resolution_ck"):
        editor(item, ReviewItem.Resolution.WITHDRAWN)


@pytest.mark.parametrize("make", [ReviewItemFactory, source_item], ids=["event", "source"])
def test_a_withdrawal_by_a_job_is_accepted_on_either_target(make):
    item = make()

    job(item, ReviewItem.Resolution.WITHDRAWN)

    item.refresh_from_db(using=CATALOG)
    assert item.resolved_by_label == "ingest_pipeline"


def test_a_system_resolver_with_an_id_is_refused():
    item = ReviewItemFactory()

    with violates("review_item_resolution_ck"):
        resolve(item, "withdrawn", kind="system", label="ingest_pipeline", id=USER)


def test_a_user_resolver_with_a_label_is_refused():
    item = ReviewItemFactory()

    with violates("review_item_resolution_ck"):
        resolve(item, "approved", kind="user", id=USER, label="ingest_pipeline")


def test_a_dismissal_of_an_event_item_is_refused():
    item = ReviewItemFactory()

    with violates("review_item_resolution_ck"):
        editor(item, ReviewItem.Resolution.DISMISSED)


@pytest.mark.parametrize("resolution", ["approved", "edited", "rejected"])
def test_an_event_verdict_on_a_source_item_is_refused(resolution):
    item = source_item()

    with violates("review_item_resolution_ck"):
        editor(item, resolution)


def test_a_dismissal_of_a_source_item_is_accepted():
    item = source_item()

    editor(item, ReviewItem.Resolution.DISMISSED)

    item.refresh_from_db(using=CATALOG)
    assert item.status == ReviewItem.Status.RESOLVED


# --- D7: the guard trigger ---------------------------------------------------------------


def test_a_resolved_item_cannot_be_reopened():
    item = ReviewItemFactory()
    editor(item, ReviewItem.Resolution.APPROVED)

    with restricted("is immutable"):
        execute(
            f"UPDATE {TABLE} SET status = 'open', resolution = '', resolved_at = NULL, "
            "resolved_by_kind = '', resolved_by_id = NULL WHERE id = %s",
            [item.id],
        )


def test_a_resolved_report_cannot_be_bumped():
    item = report()
    editor(item, ReviewItem.Resolution.REJECTED)

    with restricted("is immutable"):
        execute(
            f"UPDATE {TABLE} SET reports_wrong_venue = reports_wrong_venue + 1 WHERE id = %s",
            [item.id],
        )


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("reason", "'user_reported'"),
        ("event_id", "NULL"),
        ("raised_at", "raised_at - interval '1 day'"),
    ],
)
def test_a_fixed_column_cannot_change_on_an_open_item(column, value):
    item = ReviewItemFactory()

    with restricted("target, reason and raised_at are fixed"):
        execute(f"UPDATE {TABLE} SET {column} = {value} WHERE id = %s", [item.id])


def test_the_source_cannot_change_on_an_open_source_item():
    item = source_item()
    other = SourceFactory()

    with restricted("target, reason and raised_at are fixed"):
        execute(f"UPDATE {TABLE} SET source_id = %s WHERE id = %s", [other.id, item.id])


def test_an_open_item_can_still_be_bumped():
    item = report()

    execute(
        f"UPDATE {TABLE} SET reports_wrong_venue = reports_wrong_venue + 1 WHERE id = %s",
        [item.id],
    )

    item.refresh_from_db(using=CATALOG)
    assert item.reports_wrong_venue == 2


def test_an_item_cannot_be_deleted():
    item = ReviewItemFactory()

    with restricted("a ReviewItem is never deleted"):
        execute(f"DELETE FROM {TABLE} WHERE id = %s", [item.id])


def test_an_item_can_be_deleted_inside_a_retention_purge():
    item = ReviewItemFactory()

    with transaction.atomic(using=CATALOG):
        execute("SET LOCAL eventpulse.retention_purge = 'on'")
        deleted = execute(f"DELETE FROM {TABLE} WHERE id = %s", [item.id])

    assert deleted == 1


def test_the_trigger_fixes_exactly_the_models_fixed_fields():
    with connections[CATALOG].cursor() as cursor:
        cursor.execute("SELECT pg_get_functiondef('catalog.guard_review_item'::regproc)")
        body = cursor.fetchone()[0]

    in_trigger = set(re.findall(r"NEW\.(\w+) IS DISTINCT FROM OLD\.\1", body))
    on_model = {ReviewItem._meta.get_field(name).column for name in ReviewItem.FIXED_FIELDS}
    assert in_trigger == on_model


# --- D11 ---------------------------------------------------------------------------------


def test_the_item_declares_the_source_registry_retention_category():
    assert ReviewItem.retention_category is RetentionCategory.SOURCE_REGISTRY
