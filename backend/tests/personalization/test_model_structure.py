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
    PersonalEvent,
    PersonalizationAuditEntry,
    SavedEvent,
)

MODELS = [PersonalEvent, SavedEvent, ConflictPair]


@pytest.mark.parametrize("model", MODELS, ids=lambda m: m.__name__)
def test_personal_model_declares_no_relation_field(model):
    # A relation field is the only way to make Postgres create a foreign key constraint, and
    # the only way the ORM could join across the wall.
    relations = [field.name for field in model._meta.get_fields() if field.is_relation]

    assert relations == []


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
