"""Project system checks: the AD-3 wall (E001/E002), AD-15 retention (E003/E004), ids (E005),
and the fake source-fetch fixtures (E006).

The logic lives in pure functions over explicit inputs so tests can pass isolated models;
the registered checks are thin wrappers over the app registry. They are tagged `models`, not
`database`: Django skips `database`-tagged checks on a plain `manage.py check`.
"""

from collections.abc import Iterable

from django.apps import AppConfig, apps
from django.conf import settings
from django.core.checks import Error, Tags, register
from django.core.exceptions import ImproperlyConfigured

from shared.models import UUIDv7Model
from shared.retention import FRAMEWORK_RETENTION, RetentionCategory, retention_category_of

# Our top-level packages; models elsewhere (Django, third-party, test probes) aren't ours.
PROJECT_PACKAGES = frozenset({"apps", "adapters", "config", "domain", "ports", "shared", "worker"})


def _alias_for(app_label: str, routing: dict[str, set[str]]) -> str | None:
    for alias, app_labels in routing.items():
        if app_label in app_labels:
            return alias
    return None


def find_unmapped_apps(
    app_configs: Iterable[AppConfig], routing: dict[str, set[str]]
) -> list[Error]:
    errors = []
    for app_config in app_configs:
        has_models = next(iter(app_config.get_models()), None) is not None
        if has_models and _alias_for(app_config.label, routing) is None:
            errors.append(
                Error(
                    f"App '{app_config.label}' has models but is not in DATABASE_ROUTING.",
                    hint="Add it to the catalog or personal set in settings.DATABASE_ROUTING.",
                    obj=app_config.name,
                    id="eventpulse.E001",
                )
            )
    return errors


def find_cross_alias_relations(models: Iterable, routing: dict[str, set[str]]) -> list[Error]:
    errors = []
    for model in models:
        source = _alias_for(model._meta.app_label, routing)
        for field in model._meta.get_fields():
            # Forward relations only: FK/O2O are concrete, M2M has no column. Reverse accessors
            # are auto-created and get reported on the model that declares the field.
            forward = field.is_relation and not field.auto_created
            if not (forward and (field.concrete or field.many_to_many)):
                continue
            target_model = field.related_model
            if target_model is None or isinstance(target_model, str):
                continue
            target = _alias_for(target_model._meta.app_label, routing)
            if source is None or target is None:
                continue  # Unmapped apps are reported by eventpulse.E001.
            if source != target:
                errors.append(
                    Error(
                        f"{model._meta.label}.{field.name} relates to "
                        f"{target_model._meta.label} across database aliases "
                        f"({source} -> {target}).",
                        hint="Store the id by value without a relation field (AD-3).",
                        obj=field,
                        id="eventpulse.E002",
                    )
                )
    return errors


def find_models_without_retention(models: Iterable, framework=FRAMEWORK_RETENTION) -> list[Error]:
    errors = []
    for model in models:
        if model._meta.auto_created:
            continue  # M2M through tables follow their owner.
        category = retention_category_of(model, framework)
        if category is None:
            errors.append(
                Error(
                    f"{model._meta.label} declares no retention category.",
                    hint="Set retention_category = RetentionCategory.<X> on the model "
                    "(NOT_USER_DATA if it holds no user-derived data) (AD-15).",
                    obj=model,
                    id="eventpulse.E003",
                )
            )
        elif not isinstance(category, RetentionCategory):
            errors.append(
                Error(
                    f"{model._meta.label}.retention_category is {category!r}, "
                    "not a RetentionCategory.",
                    hint="Use a member of shared.retention.RetentionCategory.",
                    obj=model,
                    id="eventpulse.E004",
                )
            )
    return errors


def find_models_without_uuid7_pk(models: Iterable) -> list[Error]:
    errors = []
    for model in models:
        if model._meta.auto_created:
            continue  # M2M through tables (e.g. User.groups) keep Django's integer ids.
        if model.__module__.split(".")[0] not in PROJECT_PACKAGES:
            continue
        if not issubclass(model, UUIDv7Model):
            errors.append(
                Error(
                    f"{model._meta.label} does not use a UUIDv7 primary key.",
                    hint="Subclass shared.models.UUIDv7Model.",
                    obj=model,
                    id="eventpulse.E005",
                )
            )
    return errors


def _selected(app_configs):
    return apps.get_app_configs() if app_configs is None else app_configs


@register(Tags.models)
def check_apps_are_routed(app_configs=None, **kwargs):
    return find_unmapped_apps(_selected(app_configs), settings.DATABASE_ROUTING)


@register(Tags.models)
def check_no_cross_alias_relations(app_configs=None, **kwargs):
    models = [model for config in _selected(app_configs) for model in config.get_models()]
    return find_cross_alias_relations(models, settings.DATABASE_ROUTING)


@register(Tags.models)
def check_retention_declared(app_configs=None, **kwargs):
    models = [model for config in _selected(app_configs) for model in config.get_models()]
    return find_models_without_retention(models)


@register(Tags.models)
def check_uuid7_primary_keys(app_configs=None, **kwargs):
    models = [model for config in _selected(app_configs) for model in config.get_models()]
    return find_models_without_uuid7_pk(models)


def find_fake_fetch_fixture_errors(adapters: dict[str, str], fixtures_dir) -> list[Error]:
    """E006: the fake fetch adapter's index must load before the first fetch, not during it."""
    from adapters.crawl.fake import load_index
    from config.adapters import FAKE_ADAPTERS

    if adapters.get("fetch") != FAKE_ADAPTERS["fetch"]:
        return []
    try:
        load_index(fixtures_dir)
    except ImproperlyConfigured as exc:
        return [
            Error(
                f"The fake source-fetch fixtures are invalid: {exc}",
                hint="Fix SOURCE_FIXTURES_DIR/index.json, or set SOURCE_FETCH=http.",
                id="eventpulse.E006",
            )
        ]
    return []


@register()
def check_fake_fetch_fixtures(app_configs=None, **kwargs):
    return find_fake_fetch_fixture_errors(settings.ADAPTERS, settings.SOURCE_FETCH["fixtures_dir"])
