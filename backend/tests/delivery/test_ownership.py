"""The AD-16 ownership boundary: `delivery` owns `REMINDER_PLAN`, `personalization` calls it.

AD-16's contested rule: "`delivery` owns `REMINDER_PLAN`. `personalization` calls `delivery`'s
published service to attach the default plan when it creates a `PERSONAL_EVENT` (FR-20)."

These tests read the import graph and the module structure rather than exercising behaviour, so
a future "helpful" direct import of `apps.delivery.models` from `personalization` breaks the
build instead of quietly making a cross-module write possible.
"""

import ast
import pathlib

import pytest

from apps.delivery.models import ReminderPlan

BACKEND = pathlib.Path(__file__).resolve().parents[2]
DELIVERY_MODELS = "apps.delivery.models"


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


def test_no_module_outside_delivery_imports_the_delivery_models():
    # The import-linter contract `models-delivery` enforces this at build time; the test
    # states the rule in the place a reader of the delivery app will look for it.
    offenders = {}
    for path in _python_files("apps"):
        if "apps/delivery" in path.as_posix():
            continue
        if DELIVERY_MODELS in _imported_modules(path):
            offenders[path.relative_to(BACKEND).as_posix()] = DELIVERY_MODELS

    assert offenders == {}


def test_the_personalization_app_does_not_import_the_delivery_models():
    for path in _python_files("apps/personalization"):
        assert DELIVERY_MODELS not in _imported_modules(path), path


def test_personalization_reaches_delivery_through_its_service():
    # The published interface is importable by `personalization` without the models.
    from apps.delivery.services import reminder_plans

    assert hasattr(reminder_plans, "attach_default_plan")
    assert hasattr(reminder_plans, "set_plan_slots")
    assert hasattr(reminder_plans, "remove_all_reminders")


def test_the_service_does_not_leak_the_model_to_its_callers():
    # The service hands over plain data: a frozen dataclass, not a model instance. A caller
    # that received a `ReminderPlan` would hold a reference to `apps.delivery.models`.
    from apps.delivery.services.reminder_plans import PlanSlots

    assert not hasattr(PlanSlots, "save")
    assert not hasattr(PlanSlots, "objects")


def test_the_reminder_plan_declares_no_relation_field():
    # OQ-8: the user is referenced by UUID value, and the target is a personal-side row
    # referenced by value. A relation field would be the only way to make Postgres create a
    # foreign key, and the only way the ORM could join across a module boundary.
    relations = [field.name for field in ReminderPlan._meta.get_fields() if field.is_relation]

    assert relations == []


def test_the_reminder_plan_stores_the_user_and_target_by_value():
    from django.db import models

    for name in ("user_id", "target_id"):
        field = ReminderPlan._meta.get_field(name)

        assert isinstance(field, models.UUIDField), name
        assert not isinstance(field, models.ForeignKey), name


def test_the_service_module_is_the_only_way_in():
    # `apps/delivery/services/reminder_plans.py` is the module `personalization` calls.
    assert (BACKEND / "apps/delivery/services/reminder_plans.py").exists()


@pytest.mark.parametrize(
    "module",
    [
        "apps.delivery.services.reminder_plans",
        "apps.delivery.services.audit",
    ],
)
def test_the_service_modules_import_cleanly(module):
    import importlib

    assert importlib.import_module(module) is not None
