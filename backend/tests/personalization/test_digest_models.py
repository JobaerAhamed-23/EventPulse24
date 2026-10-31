"""The digest models: `PulseDigest` and `DigestComposition` (AD-10, AD-15, AD-16, FR-5).

The constraints are the point. Every invariant here is a check or a unique constraint in
the database, so a violation is an `IntegrityError` from Postgres rather than a Python
assertion — and the tests pin the *rule*, not Django's rendering of it.

**The immutability test is the one that can pass for the wrong reason.** `AppendOnlyModel`
raises `AppendOnlyViolation` (a `RuntimeError`) in Python *before* the database trigger
would fire, so a test expecting `IntegrityError` would pass against a table with no
trigger at all. The ORM guard and the SQL trigger are therefore asserted separately: the
first as `AppendOnlyViolation`, the second as psycopg's `RestrictViolation` — the
trigger's own ERRCODE — on a raw statement that never goes through the ORM.

Design: .specs-fire/intents/pulse-digest-and-trust/work-items/
digest-composition-models-design.md (decisions D1-D12).
"""

from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal

import psycopg
import pytest
from django.db import IntegrityError, connections, transaction

from apps.personalization.models import DIGEST_SLOT_ORDER, DigestComposition, PulseDigest
from shared.db import PERSONAL
from shared.models import AppendOnlyViolation
from shared.retention import RetentionCategory
from tests.personalization.factories import (
    COMPOSED_AT,
    LOCAL_DATE,
    DigestCompositionFactory,
    PulseDigestFactory,
)

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

COMPOSITION_TABLE = "personal.personalization_digestcomposition"


def execute(sql: str, params=()) -> int:
    with connections[PERSONAL].cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.rowcount


@contextmanager
def restricted(message: str):
    """Expect the block to fail in a trigger with this message (rolled back to a savepoint)."""
    with pytest.raises(IntegrityError) as excinfo, transaction.atomic(using=PERSONAL):
        yield
    assert isinstance(excinfo.value.__cause__, psycopg.errors.RestrictViolation)
    assert message in str(excinfo.value.__cause__)


# --- PulseDigest -----------------------------------------------------------------------------


def test_pulse_digest_rejects_a_second_digest_for_the_same_user_and_day():
    """One digest per user per local calendar day (D8)."""
    first = PulseDigestFactory.create()

    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        PulseDigestFactory.create(user_id=first.user_id, local_date=first.local_date)


def test_pulse_digest_accepts_the_same_day_for_a_different_user():
    """The uniqueness is per *user* and day — two users each have their own digest."""
    first = PulseDigestFactory.create()

    second = PulseDigestFactory.create(local_date=first.local_date)

    assert second.user_id != first.user_id


def test_pulse_digest_accepts_a_different_day_for_the_same_user():
    """The uniqueness includes the day — a user has one digest per day, not one ever."""
    first = PulseDigestFactory.create()

    second = PulseDigestFactory.create(
        user_id=first.user_id,
        local_date=LOCAL_DATE + timedelta(days=1),
    )

    assert second.local_date != first.local_date


def test_pulse_digest_stores_the_empty_state_as_a_flag():
    """FR-8: the empty digest is a real digest with zero compositions (D1).

    `is_empty` is stored rather than derived, so a reader does not have to count children
    to know whether this was a deliberate empty digest.
    """
    empty = PulseDigestFactory.create(is_empty=True)
    composed = PulseDigestFactory.create(is_empty=False)

    assert empty.is_empty is True
    assert composed.is_empty is False


def test_pulse_digest_declares_its_retention_category():
    """AD-15: `manage.py check` fails without one, and this pins the *choice*.

    `ACCOUNT_CONTENT` is the only category under which AD-10's "most recent composition
    for that `(user, event)` pair" promise holds: a `PREFERENCE_SIGNALS` window of 12
    months rolling would delete an event's only explanation while the user is still
    looking at the event (D4).
    """
    assert PulseDigest.retention_category is RetentionCategory.ACCOUNT_CONTENT


def test_pulse_digest_reads_as_its_local_date_and_state():
    empty = PulseDigestFactory.create(is_empty=True)
    composed = PulseDigestFactory.create(is_empty=False)

    assert str(empty) == f"digest {empty.local_date} (empty)"
    assert str(composed) == f"digest {composed.local_date} (composed)"


def test_pulse_digest_carries_no_updated_at():
    """A digest is a fact about a day, not a mutable record (D9).

    A row whose `updated_at` can change invites the question of what changed, and the
    answer would be "nothing — it is a fact".
    """
    field_names = {field.name for field in PulseDigest._meta.get_fields()}

    assert "updated_at" not in field_names
    assert "created_at" in field_names


# --- DigestComposition ----------------------------------------------------------------------


def test_digest_composition_rejects_a_duplicate_event_in_one_digest():
    """FR-5: "a Pulse Card in the digest is not a duplicate of another" (D8)."""
    first = DigestCompositionFactory.create()

    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        DigestCompositionFactory.create(digest_id=first.digest_id, event_id=first.event_id)


def test_digest_composition_accepts_the_same_event_in_a_different_digest():
    """The uniqueness is per *digest* — yesterday's digest may show the same event."""
    first = DigestCompositionFactory.create()

    second = DigestCompositionFactory.create(event_id=first.event_id)

    assert second.digest_id != first.digest_id


@pytest.mark.parametrize("bucket", [0, 6, 100], ids=["zero", "six", "a-hundred"])
def test_digest_composition_rejects_a_bucket_outside_one_to_five(bucket):
    """FR-22's bucket is 1 to 5, and there is no sixth value (D5)."""
    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        DigestCompositionFactory.create(bucket=bucket)


@pytest.mark.parametrize("bucket", [1, 3, 5], ids=["one", "three", "five"])
def test_digest_composition_accepts_every_bucket_from_one_to_five(bucket):
    DigestCompositionFactory.create(bucket=bucket)


def test_digest_composition_rejects_a_public_event_without_a_version():
    """A public composition describes a catalog Event, and that Event has a version (D7)."""
    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        DigestCompositionFactory.create(
            event_kind=DigestComposition.EventKind.PUBLIC,
            event_version=None,
            source_badge="official_site",
        )


def test_digest_composition_rejects_a_public_event_without_a_badge():
    """FR-23: "a Pulse Card always shows a Source Badge" (D6, D7)."""
    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        DigestCompositionFactory.create(
            event_kind=DigestComposition.EventKind.PUBLIC,
            event_version=1,
            source_badge=None,
        )


def test_digest_composition_rejects_a_personal_event_carrying_a_version():
    """A personal event is not in `catalog`: it has no version and no source (D7)."""
    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        DigestCompositionFactory.create(
            event_kind=DigestComposition.EventKind.PERSONAL,
            event_version=1,
            source_badge=None,
        )


def test_digest_composition_rejects_a_personal_event_carrying_a_badge():
    """A personal event came from nowhere — there is no source to badge (D7)."""
    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        DigestCompositionFactory.create(
            event_kind=DigestComposition.EventKind.PERSONAL,
            event_version=None,
            source_badge="official_site",
        )


def test_digest_composition_accepts_a_public_event_with_a_version_and_a_badge():
    composition = DigestCompositionFactory.create(
        event_kind=DigestComposition.EventKind.PUBLIC,
        event_version=3,
        source_badge="aggregator",
    )

    assert composition.event_version == 3
    assert composition.source_badge == "aggregator"


def test_digest_composition_accepts_a_personal_event_with_neither():
    composition = DigestCompositionFactory.create(
        event_kind=DigestComposition.EventKind.PERSONAL,
        event_version=None,
        source_badge=None,
    )

    assert composition.event_version is None
    assert composition.source_badge is None


def test_digest_composition_kind_values_match_the_constraint():
    """The check constraint compares the kind as a literal string.

    The enum and the model class are both still being defined while the constraint's body
    executes, so neither name is bound there and the literal is used instead. This test
    pins the two together, so renaming the enum's value without changing the constraint
    fails here rather than at the first insert (D7).

    **The assertion is on an exact token, not a substring.** A substring check is
    satisfied by a *stale* literal: if `EventKind.PUBLIC` were renamed to `"pub"`, the
    old literal `"public"` would still be in the rendered constraint, and both the
    substring `"public" in rendered` and the substring `"pub" in rendered` would be
    true — so the pin would hold against a constraint that no longer matched the enum.
    Django renders the comparison as `('event_kind', 'public')`, so the exact-token
    form is `('event_kind', 'pub')`, which does not match `('event_kind', 'public')`.
    """
    constraint = next(
        c
        for c in DigestComposition._meta.constraints
        if c.name == "digest_composition_kind_shape_ck"
    )
    rendered = str(constraint.condition)

    for member in DigestComposition.EventKind:
        assert f"('event_kind', '{member.value}')" in rendered

    # The constraint has exactly two branches, one per kind. A third value added to the
    # enum must not silently widen the constraint to accept it.
    assert len(DigestComposition.EventKind) == 2


def test_digest_composition_slot_values_match_the_constraint():
    """The slot check constraint compares the slots as literal strings, like the kind.

    Same reasoning as the kind: the enum is not bound while the constraint's body
    executes, so the literals stand in for it and are pinned here by exact token.

    Django renders an `__in` lookup as a **list**, `('slot__in', ['must_know', ...])`,
    so each value is matched with its own quotes rather than as a substring.
    """
    constraint = next(
        c for c in DigestComposition._meta.constraints if c.name == "digest_composition_slot_ck"
    )
    rendered = str(constraint.condition)

    for member in DigestComposition.Slot:
        assert f"'{member.value}'" in rendered

    assert len(DigestComposition.Slot) == 3

    # Each slot appears exactly once, and no fourth value is present. A stale literal
    # left over from a removed slot would push the count above three and fail here.
    assert rendered.count("'must_know'") == 1
    assert rendered.count("'nearby'") == 1
    assert rendered.count("'serendipity'") == 1


def test_digest_composition_rejects_a_slot_outside_the_enum():
    """FR-5 has three slots and no fourth — held by the database (D8).

    Django's `choices` are a Python-level convenience and are **not** a database
    constraint, so without this check a row with `slot='bogus_slot'` is perfectly
    writable. That row would then be invisible to the digest read: the read sorts
    against `DIGEST_SLOT_ORDER`, and a slot outside it has nowhere to sort, so the card
    would silently vanish from the digest.
    """
    with pytest.raises(IntegrityError), transaction.atomic(using=PERSONAL):
        DigestCompositionFactory.create(slot="bogus_slot")


@pytest.mark.parametrize("slot", ["must_know", "nearby", "serendipity"])
def test_digest_composition_accepts_every_slot_in_the_enum(slot):
    """The three slots FR-5 names are all writable, and all three are legal."""
    composition = DigestCompositionFactory.create(slot=slot)

    assert composition.slot == slot


def test_digest_composition_stores_the_score_as_an_exact_decimal():
    """FR-22's boundaries are exact, so the stored score is an exact decimal (D5).

    A float would be `0.83000000000000007105...`, and the bucket boundary at 0.85 would
    land in the wrong bucket for the same reason a float does everywhere else in this
    codebase.
    """
    composition = DigestCompositionFactory.create(score=Decimal("0.85"))

    assert composition.score == Decimal("0.85")
    assert isinstance(composition.score, Decimal)
    assert composition.score.as_tuple().exponent == -2


@pytest.mark.parametrize(
    ("written", "read_back"),
    [
        (Decimal("0.00"), Decimal("0.00")),
        (Decimal("0.45"), Decimal("0.45")),
        (Decimal("0.65"), Decimal("0.65")),
        (Decimal("0.85"), Decimal("0.85")),
        (Decimal("1.00"), Decimal("1.00")),
    ],
    ids=["zero", "bucket-3-boundary", "bucket-4-boundary", "bucket-5-boundary", "one"],
)
def test_digest_composition_round_trips_the_score_at_two_places(written, read_back):
    """The score survives the round trip through the database unchanged."""
    composition = DigestCompositionFactory.create(score=written)

    reloaded = DigestComposition.objects.get(id=composition.id)

    assert reloaded.score == read_back
    assert reloaded.score.as_tuple().exponent == -2


def test_digest_composition_stores_the_tags_in_order():
    """The list order is the Why-this Tag order (D6).

    `EventFit.tags` stores ordered keys the same way, and the two explanation kinds stay
    structurally parallel so a reader can compare them.
    """
    tags = ["nearby", "tonight", "matches_arts_culture"]
    composition = DigestCompositionFactory.create(tags=tags)

    reloaded = DigestComposition.objects.get(id=composition.id)

    assert reloaded.tags == tags


def test_digest_composition_declares_its_retention_category():
    """AD-15 requires a category; `ACCOUNT_CONTENT` is the one that keeps AD-10's promise.

    A composition is an *output* — a record of what this user was shown and why — not a
    preference *signal*, which is an input to the preference graph. The 12-month rolling
    window of `PREFERENCE_SIGNALS` would delete the only explanation an event ever had
    while the user was still looking at the event (D4).
    """
    assert DigestComposition.retention_category is RetentionCategory.ACCOUNT_CONTENT


def test_digest_composition_reads_as_its_slot_and_bucket():
    """AD-13: the `__str__` names the slot and the bucket, and nothing else (D10)."""
    composition = DigestCompositionFactory.create(slot=DigestComposition.Slot.NEARBY, bucket=3)

    assert str(composition) == "nearby digest composition, bucket 3"


def test_digest_composition_str_leaks_no_event_content():
    """The event's title is untrusted source text and must not reach a log line (AD-9, AD-13).

    The `__str__` is what `repr()` shows, and what the admin's list column shows.

    **The slot is pinned to `must_know` on purpose.** The tags include `"nearby"`, which
    is also a *slot* value, and `__str__` legitimately names the slot. If the factory's
    default slot were ever `"nearby"`, the `"nearby" not in rendered` assertion would
    fail because the slot leaked — not because a tag leaked — and the test would be
    asserting something it never set up. Pinning the slot makes the assertion mean what
    it says: the *tag* "nearby" is absent, while the slot "must_know" is present.
    """
    composition = DigestCompositionFactory.create(
        slot=DigestComposition.Slot.MUST_KNOW,
        tags=["nearby", "matches_arts_culture"],
    )

    rendered = f"{composition!r} {composition}"

    assert "arts_culture" not in rendered
    assert "nearby" not in rendered
    # The slot *is* named — the assertion above is about tags, not about the whole row.
    assert "must_know" in rendered


def test_digest_composition_slot_order_is_must_know_then_nearby_then_serendipity():
    """D12: the slot order is fixed, and it is the order FR-5 reads the cards in.

    The must-know card is first, then nearby, then serendipity. The order lives in one
    place — `DIGEST_SLOT_ORDER` — because a `CHAR` index sorts alphabetically and that
    would be a *different* order from the one the reader expects.
    """
    assert DIGEST_SLOT_ORDER == ("must_know", "nearby", "serendipity")


def test_digest_composition_slot_order_matches_the_enum_declaration_order():
    """The order and the enum are the same fact, and they cannot drift apart (D12).

    A `TextChoices` member holds a scalar, so the order cannot live inside the enum
    class; it is a module constant beside it. This test is what keeps the two in step.

    **The enum is walked unfiltered.** A filtered walk — one that kept only the members
    the constant already names — would pass even after a fourth slot was added to the
    enum, because the new member would simply be skipped and the two would still look
    equal. An unadded slot is exactly the drift this test exists to catch: the read
    sorts against `DIGEST_SLOT_ORDER`, and a slot outside it has nowhere to sort.
    """
    declared = tuple(member.value for member in DigestComposition.Slot)

    assert declared == DIGEST_SLOT_ORDER


def test_digest_composition_slot_order_covers_every_slot():
    """Every slot the model accepts appears in the order — no slot is unreachable.

    **List equality, not set equality.** A set comparison would pass against an extra
    slot in the constant *or* a missing one, because a set forgets both order and
    multiplicity. The list pins the count and the order together.
    """
    accepted = [value for value, _ in DigestComposition.Slot.choices]

    assert list(DIGEST_SLOT_ORDER) == accepted


# --- The immutability -----------------------------------------------------------------------


def test_digest_composition_refuses_an_update():
    """AD-10: a composition is immutable (D3).

    `AppendOnlyModel.save()` raises `AppendOnlyViolation` — a `RuntimeError`, **not** an
    `IntegrityError`. A test that expected `IntegrityError` here would pass against a
    table with no trigger at all, because the Python guard fires first.
    """
    composition = DigestCompositionFactory.create()
    composition.bucket = 5

    with pytest.raises(AppendOnlyViolation):
        composition.save()


def test_digest_composition_refuses_a_delete():
    composition = DigestCompositionFactory.create()

    with pytest.raises(AppendOnlyViolation):
        composition.delete()


def test_digest_composition_refuses_a_queryset_update():
    """The queryset guard, not just `save()` — a bulk path must not slip past."""
    composition = DigestCompositionFactory.create()

    with pytest.raises(AppendOnlyViolation):
        DigestComposition.objects.filter(id=composition.id).update(bucket=5)


def test_digest_composition_refuses_a_queryset_delete():
    composition = DigestCompositionFactory.create()

    with pytest.raises(AppendOnlyViolation):
        DigestComposition.objects.filter(id=composition.id).delete()


def test_digest_composition_has_no_mutable_field():
    """Nothing about a composition becomes known after it is written (D3).

    This is what makes the existing `personal.forbid_history_mutation()` — which has no
    `TG_ARGV[0]` branch — the right trigger for this table.
    """
    assert DigestComposition.append_only_mutable == frozenset()


def test_digest_composition_update_is_rejected_by_the_database_trigger():
    """The trigger, tested below the ORM (D11).

    A raw `UPDATE` on the owner connection never reaches the Python guard, so a pass here
    proves the trigger itself. The rejection is asserted as psycopg's
    `RestrictViolation` — the trigger's ERRCODE — and not as a generic `IntegrityError`,
    so a missing REVOKE cannot be mistaken for a working trigger.
    """
    composition = DigestCompositionFactory.create()

    with restricted("is append-only"):
        execute(f"UPDATE {COMPOSITION_TABLE} SET bucket = 5 WHERE id = %s", [composition.id])


def test_digest_composition_delete_is_rejected_by_the_database_trigger():
    composition = DigestCompositionFactory.create()

    with restricted("is append-only"):
        execute(f"DELETE FROM {COMPOSITION_TABLE} WHERE id = %s", [composition.id])


def test_digest_composition_delete_is_allowed_inside_a_retention_purge():
    """AD-15: the sweep must be able to purge a composition (D3, D11).

    The trigger's `DELETE` branch exists for exactly one caller — the retention sweep,
    which sets `eventpulse.retention_purge = 'on'` for the duration of its transaction.
    Without this test that branch is untested code on a table the sweep has to be able
    to empty: the table would be permanently undeletable, and `ACCOUNT_CONTENT`'s "purged
    ≤30 days after deletion" promise (D4) would be unmeetable.

    This is the pattern `tests/ingestion/test_triggers.py` already uses for the catalog
    history tables.
    """
    composition = DigestCompositionFactory.create()

    with transaction.atomic(using=PERSONAL):
        execute("SET LOCAL eventpulse.retention_purge = 'on'")

        assert execute(f"DELETE FROM {COMPOSITION_TABLE} WHERE id = %s", [composition.id]) == 1


def test_pulse_digest_may_be_updated_because_it_is_not_append_only():
    """`PulseDigest` is a fact about a day, not an append-only history (D11).

    The composition is immutable and the runtime role may not rewrite it; the digest row
    is deliberately *not* fenced off the same way, because the runtime role keeps `UPDATE`
    on it so a correction can land. This test pins that difference, so a future
    "helpful" trigger on the digest cannot be added silently.
    """
    digest = PulseDigestFactory.create(is_empty=False)

    with transaction.atomic(using=PERSONAL):
        execute(
            "UPDATE personal.personalization_pulsedigest SET is_empty = true WHERE id = %s",
            [digest.id],
        )

    digest.refresh_from_db()

    assert digest.is_empty is True


# --- The lookups the readers need -------------------------------------------------------------


def test_the_most_recent_composition_for_a_user_and_event_is_the_newest_row():
    """AD-10: the Detail Screen reads "the most recent composition" for a `(user, event)`.

    Several compositions for the same pair can exist — one per day the event appeared in
    the user's digest — and the newest is the one that explains what the user sees now.
    """
    user_id = DigestCompositionFactory.create().user_id
    event_id = DigestCompositionFactory.create().event_id

    oldest = DigestCompositionFactory.create(
        user_id=user_id,
        event_id=event_id,
        composed_at=COMPOSED_AT - timedelta(days=2),
        bucket=2,
    )
    middle = DigestCompositionFactory.create(
        user_id=user_id,
        event_id=event_id,
        composed_at=COMPOSED_AT - timedelta(days=1),
        bucket=3,
    )
    newest = DigestCompositionFactory.create(
        user_id=user_id,
        event_id=event_id,
        composed_at=COMPOSED_AT,
        bucket=4,
    )

    found = (
        DigestComposition.objects.filter(user_id=user_id, event_id=event_id)
        .order_by("-composed_at")
        .first()
    )

    assert found is not None
    assert found.id == newest.id
    assert found.bucket == newest.bucket
    assert oldest.id != newest.id
    assert middle.id != newest.id


def test_the_most_recent_composition_lookup_uses_the_index():
    """D8: the lookup is an indexed query, not a scan.

    A query plan that reads the whole table for a Detail Screen request would make the
    promise in AD-10 slow enough to be a denial of service.

    The plan's root node is the `Limit`, so the tree is walked to find the node that
    actually touches the table — and that node must be an `Index Scan` over the index
    this design added.

    **The sequential scan is switched off for the duration of the plan.** The question
    this test asks is "is there an index the planner *may* use for this lookup", not
    "does the planner *prefer* it on a table with three rows". On a table this small the
    cost model legitimately prefers a sequential scan, and which way it falls depends on
    the table statistics at that moment — so a plan-shape assertion here is a coin toss
    rather than a rule. With `enable_seqscan = off` the planner has to use an index if
    one applies, and the assertion below still fails when none does, which is the case
    this test exists to catch.
    """
    user_id = DigestCompositionFactory.create().user_id
    event_id = DigestCompositionFactory.create().event_id
    DigestCompositionFactory.create(user_id=user_id, event_id=event_id)

    with connections[PERSONAL].cursor() as cursor:
        cursor.execute("SET LOCAL enable_seqscan = off")
        cursor.execute(
            "EXPLAIN (FORMAT JSON) SELECT id FROM personal.personalization_digestcomposition "
            "WHERE user_id = %s AND event_id = %s ORDER BY composed_at DESC LIMIT 1",
            [user_id, event_id],
        )
        plan = cursor.fetchone()[0][0]["Plan"]

    def nodes(node):
        yield node
        for child in node.get("Plans", []):
            yield from nodes(child)

    all_nodes = list(nodes(plan))
    scans = [n for n in all_nodes if n["Node Type"] in {"Index Scan", "Seq Scan"}]

    assert scans, [n["Node Type"] for n in all_nodes]
    # No sequential scan: the whole point is that the lookup is indexed.
    assert all(n["Node Type"] == "Index Scan" for n in scans)
    assert scans[0]["Index Name"] == "digest_comp_user_event_idx"


def test_a_digest_read_returns_its_compositions():
    """The digest read: every composition of one digest (D8)."""
    digest_id = DigestCompositionFactory.create().digest_id
    DigestCompositionFactory.create(digest_id=digest_id, slot=DigestComposition.Slot.NEARBY)
    DigestCompositionFactory.create(digest_id=digest_id, slot=DigestComposition.Slot.SERENDIPITY)

    compositions = list(DigestComposition.objects.filter(digest_id=digest_id))

    assert len(compositions) == 3


def test_a_digest_with_no_compositions_is_the_empty_state():
    """FR-8: a real digest with zero cards is the empty state, not an absent row (D1)."""
    digest = PulseDigestFactory.create(is_empty=True)

    assert digest.pk is not None
    assert DigestComposition.objects.filter(digest_id=digest.pk).count() == 0
