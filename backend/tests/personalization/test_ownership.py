"""The write services' ownership boundaries (AD-2, AD-3, AD-16).

The import-linter contracts (`models-delivery`, `models-ingestion`, `models-personalization`)
already forbid `apps.personalization.services` from importing another app's **models**. These
tests state the same rule from the other direction — they read the service modules' own source
— so the boundary is proved even if the contracts are not run, and so the reason is recorded
next to the code it protects.

Two boundaries matter here:

- **AD-16**: `delivery` owns `REMINDER_PLAN`. `personalization` attaches the default plan by
  calling `delivery`'s published *service*, never by writing the table.
- **AD-3**: `catalog` and `personal` are separate schemas. `personalization` reads the catalog
  through `ingestion`'s published read interface, which hands over plain data.
"""

import ast
from pathlib import Path

import pytest

SERVICES = Path(__file__).resolve().parents[2] / "apps" / "personalization" / "services"
SERVICE_MODULES = sorted(SERVICES.glob("*.py"))

FORBIDDEN_IMPORTS = {
    "apps.delivery.models",
    "apps.ingestion.models",
    "apps.catalog.models",
    "apps.identity.models",
    "apps.editorial.models",
}


def _imported_modules(path: Path) -> set[str]:
    """Every module name the file imports, absolute or relative-resolved."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # a relative import: `from .models import ...`
                package = ".".join(path.parent.parts[-3:])
                prefix = package + "." * node.level
                base = prefix + (node.module or "")
                names.add(base)
                names.update(f"{base}.{alias.name}" for alias in node.names)
            elif node.module:
                names.add(node.module)
    return names


def test_the_services_package_has_modules_to_check():
    # A vacuous structural test would pass if the package were empty.
    assert SERVICE_MODULES, "no service modules found to check"


@pytest.mark.parametrize("path", SERVICE_MODULES, ids=lambda p: p.name)
def test_a_service_never_imports_another_apps_models(path):
    imported = _imported_modules(path)

    assert not (imported & FORBIDDEN_IMPORTS), (
        f"{path.name} imports another app's models: {sorted(imported & FORBIDDEN_IMPORTS)}"
    )


@pytest.mark.parametrize("path", SERVICE_MODULES, ids=lambda p: p.name)
def test_a_service_never_imports_a_django_model_class_directly(path):
    # `from apps.personalization.models import PersonalEvent` is fine — that is this app's
    # own models. What is forbidden is reaching into another app's models *module*.
    imported = _imported_modules(path)

    for name in imported:
        assert not name.startswith("apps.delivery.models")
        assert not name.startswith("apps.ingestion.models")


def test_the_personal_event_service_calls_deliverys_service_not_its_table():
    source = (SERVICES / "personal_events.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    delivery_imports = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module
        and node.module.startswith("apps.delivery")
    ]
    called = {alias.name for node in delivery_imports for alias in node.names}

    # AD-16: the seam is `delivery`'s published service. Writing `REMINDER_PLAN` from here
    # would be two owners for one table.
    assert called == {"attach_default_plan"}
    assert "ReminderPlan" not in source


def test_the_saved_event_service_reads_the_catalog_through_ingestions_interface():
    source = (SERVICES / "saved_events.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    ingestion_imports = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module
        and node.module.startswith("apps.ingestion")
    ]
    called = {alias.name for node in ingestion_imports for alias in node.names}

    # AD-3 / AD-21: the catalog is read through `ingestion`'s published read interface, which
    # hands over plain data (`PublicEvent`). `personalization` never imports the catalog's
    # models, so the wall holds without either side knowing the other's models.
    assert called == {"get_public_event"}
    assert "apps.ingestion.models" not in _imported_modules(SERVICES / "saved_events.py")
