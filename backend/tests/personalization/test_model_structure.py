"""The structural guarantee: no relation crosses the AD-3 wall (design D2, D12, D17).

These tests read the models' metadata rather than their behaviour, so a future "helpful"
ForeignKey breaks the build instead of quietly making a cross-schema join possible. AD-21
says a saved public event holds its `event_id` **by value**; spine OQ-8 says no model
relates to `User` or `ContentType`; AD-3 says nothing in `personal` may relate to
`catalog`.
"""

import pytest
from django.db import models

from apps.personalization.models import (
    ConflictPair,
    DigestComposition,
    PersonalEvent,
    PersonalizationAuditEntry,
    PulseDigest,
    SavedEvent,
)

MODELS = [PersonalEvent, SavedEvent, ConflictPair, PulseDigest, DigestComposition]


#: The apps whose models live on the other side of the AD-3 wall.
CATALOG_APPS = {"ingestion", "catalog", "editorial"}

#: Relations OQ-8 forbids by name, wherever the model lives.
FORBIDDEN_TARGETS = {"user", "contenttype"}


@pytest.mark.parametrize("model", MODELS, ids=lambda m: m.__name__)
def test_no_personal_model_relates_across_the_wall(model):
    """**A relation is forbidden for what it reaches, not for existing.**

    This test asserted that these models had *zero* relation fields of any kind. That was a
    wider net than any rule it cited, and FR-49's collections are what found the gap: a
    membership table inside `personal`, pointing at `SavedEvent`, crosses nothing — but it
    hangs a reverse accessor on `SavedEvent`, which the old assertion counted as a
    violation. A reverse accessor is not even a column; Postgres puts the constraint on the
    *other* table.

    So the rule is now its three reasons, stated:

    - nothing in `personal` may relate to `catalog` (AD-3);
    - nothing may relate to `User` or `ContentType` (OQ-8);
    - a saved public event holds its `event_id` by value (AD-21), which
      `test_saved_event_event_id_is_a_plain_uuid_field` pins directly.

    **What was given up is worth naming.** The blanket version made any foreign key in
    `personal` a build break, which is a cheaper signal than a judgement about what the key
    points at. The three invariants themselves keep their own dedicated tests — including
    `test_no_foreign_key_crosses_from_personal_to_catalog`, which reads the live database
    rather than the metadata — so the wall is still enforced by something that cannot be
    satisfied by a model declaration.
    """
    for field in model._meta.get_fields():
        if not field.is_relation or field.related_model is None:
            continue
        related = field.related_model._meta

        assert related.app_label not in CATALOG_APPS, (
            f"{model.__name__}.{field.name} relates to {related.label}, across the AD-3 wall"
        )
        assert related.model_name not in FORBIDDEN_TARGETS, (
            f"{model.__name__}.{field.name} relates to {related.model_name} (OQ-8)"
        )


def test_saved_event_event_id_is_a_plain_uuid_field():
    field = SavedEvent._meta.get_field("event_id")

    assert isinstance(field, models.UUIDField)
    assert not isinstance(field, models.ForeignKey)
    assert field.concrete


def test_no_personal_model_relates_to_user_or_content_type():
    # OQ-8: the user is referenced by UUID value, never as a relation. `User` lives in the
    # personal schema, so a FK would pass the cross-alias check and still be forbidden.
    forbidden = {"user", "contenttype"}
    for model in [*MODELS, PersonalizationAuditEntry]:
        related = {
            field.related_model._meta.model_name
            for field in model._meta.get_fields()
            if field.is_relation and field.related_model is not None
        }

        assert not related & forbidden, f"{model.__name__} relates to {related & forbidden}"


def test_saved_event_event_id_is_not_a_foreign_key_to_any_model():
    field = SavedEvent._meta.get_field("event_id")

    # A plain UUIDField has no remote_field at all: there is nothing for a relation to point
    # at. That is the structural proof that no FK to `catalog` exists.
    assert field.remote_field is None
    assert not isinstance(field, models.ForeignKey)


@pytest.mark.parametrize("model", MODELS, ids=lambda m: m.__name__)
def test_personal_model_stores_the_user_id_by_value(model):
    field = model._meta.get_field("user_id")

    assert isinstance(field, models.UUIDField)
    assert not isinstance(field, models.ForeignKey)


def test_audit_entry_stores_its_actor_by_value():
    # The audit table's actor is stored the same way: `actor_id` is a UUID column with no
    # relation to `User`. The audit table has no `user_id` of its own.
    field = PersonalizationAuditEntry._meta.get_field("actor_id")

    assert isinstance(field, models.UUIDField)
    assert not isinstance(field, models.ForeignKey)
    assert "user_id" not in {f.name for f in PersonalizationAuditEntry._meta.get_fields()}


def test_conflict_pair_stores_both_sides_by_value():
    for side in ("left_id", "right_id"):
        field = ConflictPair._meta.get_field(side)

        assert isinstance(field, models.UUIDField), side
        assert not isinstance(field, models.ForeignKey), side


def test_conflict_pair_stores_each_side_kind_alongside_its_id():
    # A UUID alone cannot say which kind of record it refers to, so the kind is stored beside
    # it (design D17).
    for side in ("left", "right"):
        kind = ConflictPair._meta.get_field(f"{side}_kind")
        identifier = ConflictPair._meta.get_field(f"{side}_id")

        assert kind.choices, side
        assert set(kind.choices) >= {
            (ConflictPair.SideKind.PERSONAL_EVENT.value, "Personal Event"),
            (ConflictPair.SideKind.SAVED_EVENT.value, "Saved Event"),
        }
        assert identifier.concrete, side


def test_personal_event_declares_no_reminder_plan_field():
    # AD-16: `delivery` owns REMINDER_PLAN. `personalization` attaches the default by calling
    # `delivery`'s published service, so no plan column lives here.
    field_names = {field.name for field in PersonalEvent._meta.get_fields()}

    assert "reminder_plan" not in field_names
    assert not any("reminder" in name for name in field_names)


def test_digest_composition_holds_its_parent_digest_by_value():
    """D2: `digest_id` is a plain UUID, not a foreign key.

    `PulseDigest` is in the *same* schema, so a foreign key would be legal to write and
    would cascade the digest's deletion into its children — and AD-10 says a composition is
    immutable and must outlive its day. A UUID column has no `remote_field` at all, so
    there is nothing for a cascade to hang from.
    """
    field = DigestComposition._meta.get_field("digest_id")

    assert isinstance(field, models.UUIDField)
    assert not isinstance(field, models.ForeignKey)
    assert field.remote_field is None


def test_digest_composition_holds_its_event_by_value():
    """AD-3: the event's id crosses the wall by value, never as a relation."""
    field = DigestComposition._meta.get_field("event_id")

    assert isinstance(field, models.UUIDField)
    assert not isinstance(field, models.ForeignKey)
    assert field.remote_field is None


def test_pulse_digest_holds_its_user_by_value():
    field = PulseDigest._meta.get_field("user_id")

    assert isinstance(field, models.UUIDField)
    assert not isinstance(field, models.ForeignKey)
