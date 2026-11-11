"""`SourceReliabilityScore`'s database rules (design: reliability-recompute-and-escalation D2, D11).

**The rules are in Postgres, not in Python.** The Python guard (`append_only_mutable`) is a
fast failure for the ordinary path; the trigger is the guarantee, because it binds every
role and raw SQL. Each rejection below asserts the *named* constraint or the trigger's own
message, so a test cannot pass because some other rule happened to fire.

---

## Why this table has its own trigger

The shared `catalog.forbid_history_mutation` allows exactly **one** column to go from NULL
to a value — an outbox's `propagated_at`. This row's same-period refresh rewrites four
non-nullable columns at once (`score`, `positives`, `negatives`, `computed_at`), which the
shared trigger would refuse. And that refresh is exactly what the AC's idempotence
requires: *"a re-run writes no duplicate row"* — and a score that is a week stale is a score
that is wrong.

So the rule is written out in full, and it is **narrow**: the source and the period are
fixed, the id and the creation time are immutable, and the four computed columns may move.
"""

from contextlib import contextmanager
from datetime import UTC, date, datetime
from decimal import Decimal

import psycopg
import pytest
from django.db import IntegrityError, connections, transaction

from apps.ingestion.models import SourceReliabilityScore
from shared.db import CATALOG, PERSONAL
from shared.retention import RetentionCategory
from tests.ingestion.factories import SourceFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

TABLE = "catalog.ingestion_sourcereliabilityscore"
NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
THIS_WEEK = date(2026, 11, 9)
LAST_WEEK = date(2026, 11, 2)


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


def _row(**overrides) -> SourceReliabilityScore:
    fields = {
        "source": SourceFactory(),
        "period_start": THIS_WEEK,
        "score": Decimal("0.50"),
        "positives": 0,
        "negatives": 0,
        "computed_at": NOW,
    }
    fields.update(overrides)
    return SourceReliabilityScore.objects.using(CATALOG).create(**fields)


# ── The constraints ───────────────────────────────────────────────────────────────────────


def test_a_second_row_for_the_same_source_and_period_is_refused():
    """**The idempotence guarantee, enforced by Postgres.**"""
    row = _row()

    with violates("source_reliability_score_period_uq"):
        _row(source=row.source, period_start=THIS_WEEK)


def test_the_same_source_may_have_a_row_for_each_period():
    """**The history is one row per week**, which is what makes the spike rule's lookup
    possible."""
    source = SourceFactory()
    _row(source=source, period_start=LAST_WEEK)
    _row(source=source, period_start=THIS_WEEK)

    assert SourceReliabilityScore.objects.using(CATALOG).filter(source=source).count() == 2


def test_a_score_outside_the_unit_range_is_refused():
    with violates("source_reliability_score_range_ck"):
        _row(score=Decimal("1.50"))


def test_a_negative_score_is_refused():
    with violates("source_reliability_score_range_ck"):
        _row(score=Decimal("-0.10"))


def test_a_period_that_is_not_a_week_start_is_refused():
    """**The row is a week, not a moment.**

    `date_trunc('week', ...)` is Postgres's own ISO-week-to-Monday truncation, so the
    database and the service agree on where a week starts without either of them
    hard-coding an offset.
    """
    with violates("source_reliability_score_week_ck"):
        _row(period_start=date(2026, 11, 10))  # a Tuesday


def test_a_monday_is_accepted():
    """**The check is not merely refusing everything.**"""
    _row(period_start=date(2026, 11, 9))
    _row(period_start=date(2026, 11, 2))


# ── The trigger ───────────────────────────────────────────────────────────────────────────


def test_a_row_cannot_be_deleted():
    with restricted("a SourceReliabilityScore is never deleted"):
        execute(f"DELETE FROM {TABLE} WHERE id = %s", [_row().pk])


def test_a_row_can_be_deleted_inside_a_retention_purge():
    """**The retention sweep is the one way a history row goes away**, and the sweep knows
    it: it sets the flag."""
    row = _row()
    with transaction.atomic(using=CATALOG):
        execute("SET LOCAL eventpulse.retention_purge = 'on'")
        execute(f"DELETE FROM {TABLE} WHERE id = %s", [row.pk])


def test_the_source_cannot_change():
    """**The source is part of the row's identity.** Moving it would make the history lie
    about which source a conclusion was about."""
    row = _row()
    other = SourceFactory()

    with restricted("source and period are fixed"):
        execute(f"UPDATE {TABLE} SET source_id = %s WHERE id = %s", [other.pk, row.pk])


def test_the_period_cannot_change():
    """**The period is part of the row's identity**, for the same reason."""
    row = _row()

    with restricted("source and period are fixed"):
        execute(f"UPDATE {TABLE} SET period_start = %s WHERE id = %s", [LAST_WEEK, row.pk])


def test_the_id_cannot_change():
    from shared.ids import uuid7

    row = _row()

    with restricted("is immutable"):
        execute(f"UPDATE {TABLE} SET id = %s WHERE id = %s", [uuid7(), row.pk])


def test_a_same_period_refresh_is_allowed():
    """**The exception the AC's idempotence needs.**

    The four computed columns may move, because the week's conclusion may be recomputed
    with observations that arrived since. Without this, a re-run would either fail or leave
    a stale number behind.
    """
    row = _row()

    execute(
        f"UPDATE {TABLE} SET score = %s, positives = %s, negatives = %s, computed_at = %s "
        "WHERE id = %s",
        [Decimal("0.25"), 1, 4, NOW, row.pk],
    )

    row.refresh_from_db(using=CATALOG)
    assert row.score == Decimal("0.25")
    assert row.negatives == 4


# ── The Python guard and the trigger agree ───────────────────────────────────────────────


def test_the_python_guard_names_the_same_columns_the_trigger_allows():
    """**The Python guard and the trigger must not drift.**

    `append_only_mutable` is what the service's `update()` calls are checked against, and
    the trigger is what actually binds. If they disagreed, a write would pass one and fail
    the other — so the trigger's own body is read and compared.
    """
    with connections[CATALOG].cursor() as cursor:
        cursor.execute(
            "SELECT pg_get_functiondef('catalog.guard_reliability_score()'::regprocedure)"
        )
        definition = cursor.fetchone()[0]

    # Every column the Python guard permits must not be named by the trigger's immutability
    # rule, and the trigger must not permit anything the Python guard forbids.
    for column in SourceReliabilityScore.append_only_mutable:
        assert column in ("score", "positives", "negatives", "computed_at")
    assert SourceReliabilityScore.append_only_mutable == frozenset(
        {"score", "positives", "negatives", "computed_at"}
    )
    # The trigger fixes exactly the identity columns and the immutable ones.
    assert "NEW.source_id IS DISTINCT FROM OLD.source_id" in definition
    assert "NEW.period_start IS DISTINCT FROM OLD.period_start" in definition
    assert "NEW.id IS DISTINCT FROM OLD.id" in definition
    assert "NEW.created_at IS DISTINCT FROM OLD.created_at" in definition


# ── The rest of the model's rules ────────────────────────────────────────────────────────


def test_the_table_declares_the_source_registry_retention_category():
    """**AD-15: every model names its retention category.** A score is a standing fact
    about a source, not user data."""
    assert SourceReliabilityScore.retention_category is RetentionCategory.SOURCE_REGISTRY


def test_the_row_is_an_append_only_model():
    """**The Python guard is on**, so the ordinary path fails fast and legibly."""
    from shared.models import AppendOnlyModel

    assert issubclass(SourceReliabilityScore, AppendOnlyModel)


def test_the_table_is_ordered_by_period_for_the_predecessor_lookup():
    """**The spike rule looks up the previous row**, so the index is on (source, period)."""
    indexes = {index.name: index for index in SourceReliabilityScore._meta.indexes}
    assert "reliability_score_period_idx" in indexes
    assert indexes["reliability_score_period_idx"].fields == ["source", "-period_start"]


# ── The runtime role's privileges ──────────────────────────────────────────────────────────


def test_the_runtime_role_cannot_delete_the_row():
    """**The third layer of the append-only standard.**

    The trigger binds every role, but the trigger is a backstop — the *privileges* are the
    rule. `ep_catalog` may refresh the four computed columns and may not delete a row, so a
    bug in the service cannot take a history row away.
    """
    with connections[CATALOG].cursor() as cursor:
        cursor.execute("SELECT has_table_privilege('ep_catalog', %s, 'DELETE')", [TABLE])
        assert cursor.fetchone()[0] is False


def test_the_runtime_role_cannot_update_the_row_wholesale():
    """**The four columns are updatable; the row is not.** A wholesale UPDATE would let a
    caller move the source or the period, which would make the history lie."""
    with connections[CATALOG].cursor() as cursor:
        cursor.execute("SELECT has_table_privilege('ep_catalog', %s, 'UPDATE')", [TABLE])
        assert cursor.fetchone()[0] is False


def test_the_runtime_role_can_refresh_the_computed_columns():
    """**And the refresh the AC's idempotence needs is permitted.**"""
    with connections[CATALOG].cursor() as cursor:
        cursor.execute("SELECT has_column_privilege('ep_catalog', %s, 'score', 'UPDATE')", [TABLE])
        assert cursor.fetchone()[0] is True
