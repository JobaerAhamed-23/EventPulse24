"""The architecture invariants the personal-events intent touched, re-verified.

AD-3 (schema separation), AD-16 (write ownership) and AD-21 (snapshot semantics) were
established by earlier intents. This intent added models, services and endpoints on top of
them, so the invariants are **re-verified here** — after the new code landed, not before.

These are structural assertions about the codebase, so they live in `tests/architecture/`
alongside the contract tests from `project-scaffold`. Where an earlier item already wrote a
test for an invariant, this file **extends** it rather than duplicating it: the cross-schema
foreign-key check and the delivery-ownership checks already exist, so what is added here is
the part that is *new* — the personal-events models, the reminder-plan attachment, and the
conflict indicator's symmetry.
"""

import ast
import pathlib
from datetime import UTC, datetime

import pytest
from django.db import connections

from apps.personalization.models import ConflictPair, PersonalEvent, SavedEvent
from shared.db import CATALOG, PERSONAL

BACKEND = pathlib.Path(__file__).resolve().parents[2]

#: The tables this intent's models put in the personal schema.
PERSONALIZATION_TABLES = {
    "personalization_personalevent",
    "personalization_savedevent",
    "personalization_conflictpair",
    "personalization_personalizationauditentry",
}

#: The catalog's tables. A personal table may not reference any of them.
INGESTION_TABLES = {
    "ingestion_source",
    "ingestion_tosreview",
    "ingestion_venue",
    "ingestion_event",
    "ingestion_extractedrecord",
    "ingestion_eventstatechange",
    "ingestion_ingestionauditentry",
}


# --- AD-3: schema separation ----------------------------------------------------------------


def tables_in(schema: str) -> set[str]:
    """The tables that physically live in `schema`."""
    with connections[PERSONAL].cursor() as cursor:
        cursor.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = %s", [schema]
        )
        return {row[0] for row in cursor.fetchall()}


def cross_schema_foreign_keys(source_schema: str) -> list[tuple[str, str]]:
    """Every foreign key in `source_schema` whose target lives in another schema."""
    with connections[PERSONAL].cursor() as cursor:
        cursor.execute(
            """
            SELECT tc.table_name, ccu.table_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.constraint_column_usage ccu
              ON ccu.constraint_name = tc.constraint_name
             AND ccu.constraint_schema = tc.constraint_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = %s
              AND ccu.table_schema <> %s
            """,
            [source_schema, source_schema],
        )
        return cursor.fetchall()


@pytest.mark.django_db(databases=[PERSONAL, CATALOG])
def test_the_personal_tables_live_in_personal_and_the_catalog_tables_in_catalog():
    # AD-3, verified through information_schema rather than assumed from the router.
    assert PERSONALIZATION_TABLES <= tables_in("personal")
    assert not tables_in("catalog") & PERSONALIZATION_TABLES
    assert INGESTION_TABLES <= tables_in("catalog")
    assert not tables_in("personal") & INGESTION_TABLES


@pytest.mark.django_db(databases=[PERSONAL, CATALOG])
def test_no_foreign_key_crosses_from_personal_to_catalog():
    # AD-3: the wall is a database constraint, not a convention. A `SavedEvent` holds the
    # catalog Event's id **by value**, so no constraint may span the two schemas.
    assert cross_schema_foreign_keys("personal") == []


#: The apps on the far side of the AD-3 wall.
CATALOG_APPS = {"ingestion", "catalog", "editorial"}


@pytest.mark.parametrize(
    "model",
    [PersonalEvent, SavedEvent, ConflictPair],
    ids=lambda m: m.__name__,
)
def test_the_new_models_relate_to_nothing_across_the_wall(model):
    """The metadata half of AD-3, narrowed to what AD-3 actually says.

    This asserted zero relation fields, which also forbade a relation entirely inside
    `personal` — something no rule here prohibits. FR-49's collection membership is exactly
    that case: a table in `personal` pointing at `SavedEvent`, whose only mark on
    `SavedEvent` is a reverse accessor.

    `test_no_foreign_key_crosses_from_personal_to_catalog` above remains the stronger of the
    pair: it reads the foreign keys Postgres actually holds, so a model that lied in its
    metadata could not satisfy it.
    """
    for field in model._meta.get_fields():
        if not field.is_relation or field.related_model is None:
            continue

        assert field.related_model._meta.app_label not in CATALOG_APPS, (
            f"{model.__name__}.{field.name} reaches "
            f"{field.related_model._meta.label} across the wall"
        )


def test_the_saved_event_holds_the_catalog_event_id_by_value():
    # AD-21: the save is a snapshot, not a join. A plain `UUIDField` has no `remote_field`
    # at all — there is nothing for a relation to point at.
    field = SavedEvent._meta.get_field("event_id")

    assert field.remote_field is None
    assert not hasattr(field, "related_model") or field.related_model is None


def test_the_conflict_pair_holds_both_sides_by_value():
    # AD-21: the pair names two sides by id and kind. A relation would make the pair's
    # existence depend on the other side's row, and a conflict is a claim about two
    # records that may each go away.
    for name in ("left_id", "right_id"):
        field = ConflictPair._meta.get_field(name)
        assert field.remote_field is None, name
        assert not hasattr(field, "related_model") or field.related_model is None, name


# --- AD-16: write ownership -----------------------------------------------------------------


def _imported_modules(path: pathlib.Path) -> set[str]:
    """Every module named in an import statement inside `path`."""
    tree = ast.parse(path.read_text(), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def _python_files(directory: str) -> list[pathlib.Path]:
    return sorted((BACKEND / directory).rglob("*.py"))


def test_personalization_writes_its_own_three_tables_and_delivery_writes_the_plan():
    # AD-16: `personalization` writes `PERSONAL_EVENT`, `SAVED_EVENT` and `CONFLICT_PAIR`;
    # `delivery` writes `REMINDER_PLAN`; neither writes the other's.
    #
    # The ownership is proved from the **models**, not from a list: each model's owning app
    # is the one whose `models` module declares it, and the import-linter contracts
    # `models-personalization` and `models-delivery` keep the walls from being quietly
    # opened.
    from django.apps import apps

    owners = {model._meta.db_table: model._meta.app_label for model in apps.get_models()}

    assert owners["personalization_personalevent"] == "personalization"
    assert owners["personalization_savedevent"] == "personalization"
    assert owners["personalization_conflictpair"] == "personalization"
    assert owners["delivery_reminderplan"] == "delivery"


def test_no_module_outside_personalization_imports_the_personalization_models():
    # AD-16/AD-2: the `models-personalization` contract enforces this at build time; the
    # test states the rule in the place a reader of this intent's code will look for it.
    offenders = {}
    for path in _python_files("apps"):
        if "apps/personalization" in path.as_posix():
            continue
        if "apps.personalization.models" in _imported_modules(path):
            offenders[path.relative_to(BACKEND).as_posix()] = "apps.personalization.models"

    assert offenders == {}


def test_personalization_reaches_the_reminder_plan_through_deliverys_service():
    # AD-16: "personalization calls delivery's published service to attach the default plan
    # when it creates a PERSONAL_EVENT (FR-20)." The service is the only way in, and it
    # hands over plain data.
    from apps.delivery.services import reminder_plans

    assert hasattr(reminder_plans, "attach_default_plan")

    source = (BACKEND / "apps/personalization/services/personal_events.py").read_text()
    assert "apps.delivery.services.reminder_plans" in source
    assert "apps.delivery.models" not in source


def test_the_service_does_not_leak_a_model_to_its_callers():
    from apps.delivery.services.reminder_plans import PlanSlots

    assert not hasattr(PlanSlots, "save")
    assert not hasattr(PlanSlots, "objects")


# --- AD-21: snapshot semantics --------------------------------------------------------------


@pytest.mark.django_db(databases=[PERSONAL])
def test_the_conflict_indicator_is_symmetric_by_construction():
    """Both sides of a pair carry the indicator, because the pair *is* the indicator.

    AD-21: "The Pulse Card, the Timeline and the conflicts list read the same
    `CONFLICT_PAIR` rows, so they cannot disagree about whether a pair overlaps." The
    symmetry is structural — the row stores two sides and is queried by *either* side, so
    there is one fact and one reader, not two facts that can drift.

    The proof is behavioural: a real pair is written, and the real
    `pairs_for_side` service — the one every reader would use — finds it from **both**
    sides.
    """
    from uuid import UUID

    from apps.personalization.services.conflicts import (
        PERSONAL_EVENT_SIDE,
        SAVED_EVENT_SIDE,
        pairs_for_side,
    )

    user_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    left_id = UUID("11111111-1111-1111-1111-111111111111")
    right_id = UUID("22222222-2222-2222-2222-222222222222")
    now = datetime(2026, 11, 6, 3, 30, tzinfo=UTC)

    ConflictPair.objects.using(PERSONAL).create(
        user_id=user_id,
        kind=ConflictPair.Kind.TIME,
        left_kind=PERSONAL_EVENT_SIDE,
        left_id=left_id,
        right_kind=SAVED_EVENT_SIDE,
        right_id=right_id,
        status=ConflictPair.Status.ACTIVE,
        detected_at=now,
    )

    # Read from the personal-event side.
    from_left = pairs_for_side(user_id=user_id, kind=PERSONAL_EVENT_SIDE, side_id=left_id)
    # Read from the saved-event side.
    from_right = pairs_for_side(user_id=user_id, kind=SAVED_EVENT_SIDE, side_id=right_id)

    assert from_left.count() == 1
    assert from_right.count() == 1
    assert from_left.first().pk == from_right.first().pk

    # And a side that is not in the pair finds nothing.
    other = pairs_for_side(
        user_id=user_id,
        kind=PERSONAL_EVENT_SIDE,
        side_id=UUID("33333333-3333-3333-3333-333333333333"),
    )
    assert other.count() == 0


def test_the_pair_row_stores_both_sides_so_one_row_serves_both_readers():
    """The pair is one row with two sides — not two rows, one per reader.

    Two rows would let the Pulse Card and the Timeline disagree. One row with two
    positions, normalised so `(A, B)` and `(B, A)` are the same row, cannot.
    """
    fields = {field.name for field in ConflictPair._meta.get_fields()}

    assert {"left_kind", "left_id", "right_kind", "right_id"} <= fields
