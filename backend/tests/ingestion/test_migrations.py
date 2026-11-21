"""The FR-53 backfill migration: existing rows are brought within their tier's ceiling.

**Why a migration needs its own test.** A `RunPython` backfill runs once, on a database
whose contents nobody controls, and its result is baked into the schema afterwards. A
migration that silently rewrites an operator's data is a migration nobody can audit — and
a migration that clamps *too much* is data loss with a comment saying it was intentional.

So the clamp is exercised directly, on rows built in the test, and three things are
asserted: the rows that break the rule are brought to it, the rows that already satisfy it
are left exactly as they were, and the derivation agrees with the application's.

**The constraint is dropped to build the pre-migration state.** The test database is built
from the migrations, so the ceiling constraint is already in place — which means a row
that breaks the rule cannot even be inserted. That is the constraint working, but it makes
the *pre*-migration state unbuildable, so the constraint is dropped for the duration of
each test and put back afterwards. Without this, the backfill could only ever be tested
on a legal database, where it does nothing.

**The migration's rule is restated, not imported.** `0007_source_cadence_ceiling.py`
re-derives the ceiling from `shared.constants` rather than calling `domain.sources`, so
that the migration keeps its meaning when the application's code moves on. This test
asserts the two agree — because if they drift, the constraint the migration adds and the
rule the application enforces are two different guarantees.
"""

import importlib
from contextlib import contextmanager
from datetime import timedelta

import pytest
from django.apps import apps as django_apps
from django.db import connections

from apps.ingestion.models import Source
from domain.sources import cadence_ceiling
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import SourceFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

#: The migration module's name starts with a digit, so it cannot be imported by name.
#: `importlib` is the way in.
MIGRATION = importlib.import_module("apps.ingestion.migrations.0007_source_cadence_ceiling")

CONSTRAINT = "source_cadence_within_priority_ceiling_ck"
TABLE = "catalog.ingestion_source"


@contextmanager
def constraint_dropped():
    """The database as it was *before* the migration: no ceiling constraint.

    The test database is built from the migrations, so the constraint is already there and
    an over-ceiling row cannot be inserted at all. Dropping it here is what makes the
    pre-migration state buildable — and the constraint is put back afterwards, so the next
    test starts from the same schema the last one left.
    """
    with connections[CATALOG].cursor() as cursor:
        cursor.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT {CONSTRAINT}")
    try:
        yield
    finally:
        # **The pending trigger events are flushed first.** A `PROTECT` foreign key is
        # created `DEFERRABLE INITIALLY DEFERRED`, so the row the test inserted queues a
        # deferred FK check that is only evaluated at commit. PostgreSQL refuses to
        # `ALTER TABLE` a relation with pending trigger events, so the constraint cannot be
        # put back until they are resolved. `SET CONSTRAINTS ALL IMMEDIATE` evaluates them
        # now, inside the test's transaction, without committing it.
        with connections[CATALOG].cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        with connections[CATALOG].cursor() as cursor:
            cursor.execute(
                f"ALTER TABLE {TABLE} ADD CONSTRAINT {CONSTRAINT} CHECK ("
                "(acquisition_method IN ('api', 'partnership') "
                "AND ingestion_cadence <= interval '4 hours') "
                "OR (acquisition_method NOT IN ('api', 'partnership') "
                "AND ingestion_cadence <= interval '24 hours'))"
            )


def _clamp() -> None:
    """Run the backfill against the live test database, as the migration does."""
    MIGRATION.clamp_source_cadences(django_apps, None)


def _cadence(source_id) -> timedelta:
    return Source.objects.using(CATALOG).get(pk=source_id).ingestion_cadence


def test_an_over_ceiling_cadence_is_clamped_down_to_the_ceiling():
    """A 7-day cadence on a high-priority source becomes the 4-hour ceiling."""
    with constraint_dropped():
        source = SourceFactory(acquisition_method="api", ingestion_cadence=timedelta(days=7))

        _clamp()

        assert _cadence(source.pk) == timedelta(hours=4)


def test_a_lower_priority_source_is_clamped_to_the_daily_ceiling():
    with constraint_dropped():
        source = SourceFactory(acquisition_method="rss", ingestion_cadence=timedelta(days=7))

        _clamp()

        assert _cadence(source.pk) == timedelta(hours=24)


def test_a_legal_cadence_is_left_exactly_as_it_was():
    """The clamp only touches rows that break the rule — a legal row keeps its own cadence."""
    with constraint_dropped():
        source = SourceFactory(acquisition_method="rss", ingestion_cadence=timedelta(hours=6))

        _clamp()

        assert _cadence(source.pk) == timedelta(hours=6)


def test_a_cadence_exactly_at_the_ceiling_is_left_alone():
    with constraint_dropped():
        source = SourceFactory(acquisition_method="api", ingestion_cadence=timedelta(hours=4))

        _clamp()

        assert _cadence(source.pk) == timedelta(hours=4)


def test_the_clamp_reports_what_it_changed(capsys):
    """A migration that silently rewrites an operator's data cannot be audited."""
    with constraint_dropped():
        SourceFactory(acquisition_method="api", ingestion_cadence=timedelta(days=7))

        _clamp()

    assert "clamped 1 source cadence" in capsys.readouterr().out


def test_the_clamp_reports_nothing_when_nothing_changed(capsys):
    with constraint_dropped():
        SourceFactory(acquisition_method="api", ingestion_cadence=timedelta(hours=4))

        _clamp()

    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    ("method", "cadence"),
    [
        ("api", timedelta(hours=4, seconds=1)),
        ("partnership", timedelta(days=3)),
        ("rss", timedelta(hours=24, seconds=1)),
        ("ics", timedelta(days=7)),
        ("email_ics", timedelta(days=7)),
    ],
)
def test_the_migration_and_the_application_agree_on_the_ceiling(method, cadence):
    """The migration restates the rule; the application derives it. They must be one rule.

    If they drift, the constraint the migration adds and the refusal the registry issues
    are two different guarantees — and which one a source sees depends on whether it was
    written before or after the migration ran.
    """
    with constraint_dropped():
        source = SourceFactory(acquisition_method=method, ingestion_cadence=cadence)

        _clamp()

        assert _cadence(source.pk) == cadence_ceiling(method)


def test_the_reverse_does_not_try_to_restore_the_clamped_values():
    """The reverse drops the constraint and says so; it does not guess the old cadences."""
    assert MIGRATION.unconstraint_source_cadences(django_apps, None) is None
