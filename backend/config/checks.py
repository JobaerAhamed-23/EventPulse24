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
PROJECT_PACKAGES = frozenset(
    {"apps", "adapters", "config", "domain", "formats", "ports", "shared", "worker"}
)


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


def find_missing_credential_key_errors(keys: Iterable[str]) -> list[Error]:
    """E007: the application-level credential key must be present and well-formed.

    A pure function over an explicit input, like the other checks, so it is testable
    without touching the process environment.

    The key is what the calendar credential is encrypted with (AD-18). A missing or
    malformed key means the app cannot read or write a credential, so it is reported here
    as well as at settings-load time — `manage.py check` is a second, tool-visible gate.
    """
    from shared.credential_key import KEY_ENV_VAR, InvalidCredentialKey, parse_key

    errors = []
    for key in keys:
        try:
            parse_key(key)
        except InvalidCredentialKey as exc:
            errors.append(
                Error(
                    f"The application-level credential key is missing or malformed: {exc}",
                    hint=(
                        f"Set {KEY_ENV_VAR} to '<key_id>.<base64url-encoded 32-byte key>'. "
                        f"It is separate from DJANGO_SECRET_KEY on purpose, and there is no "
                        f"fallback (AD-18)."
                    ),
                    id="eventpulse.E007",
                )
            )
    return errors


@register()
def check_credential_key(app_configs=None, **kwargs):
    return find_missing_credential_key_errors([settings.CALENDAR_CREDENTIAL_KEY])


#: The settings the S3 blob adapter cannot work without, named as an operator sets them.
BLOB_REQUIRED_SETTINGS = ("endpoint", "public_endpoint", "bucket", "access_key", "secret_key")


def find_blob_storage_errors(adapter_path: str, storage: dict) -> list[Error]:
    """E008: the object store must be configured when the S3 adapter is the one selected.

    A pure function over explicit inputs, like the other checks, so it is testable without
    touching the process environment or the settings module.

    **Why this is a check and not only a settings validator.** `config.env` validates the
    case an operator asked for by name (`BLOB_ADAPTER=s3`), but the adapter is usually
    *not* named: it is whatever `ADAPTER_MODE` resolved to, and that resolution happens in
    the settings module, after `env` is built. This check sees the resolved table, so it
    catches the default local stack booting against a bucket nobody configured.

    **It must not fire for the in-memory adapter.** The test suite runs on it and dials no
    store, so demanding credentials there would mean demanding credentials to run tests.
    """
    if not adapter_path.endswith("S3BlobAdapter"):
        return []
    missing = [name for name in BLOB_REQUIRED_SETTINGS if not storage.get(name)]
    if not missing:
        return []
    return [
        Error(
            "The object store is not configured: " + ", ".join(sorted(missing)),
            hint=(
                "Set BLOB_ENDPOINT, BLOB_PUBLIC_ENDPOINT, BLOB_BUCKET, BLOB_ACCESS_KEY "
                "and BLOB_SECRET_KEY in .env (`make env` writes local defaults), and run "
                "`make up` to start MinIO. To run with no object store at all, set "
                "BLOB_ADAPTER=memory — nothing is then kept across a restart. "
                "BLOB_ENDPOINT is the address this process dials; BLOB_PUBLIC_ENDPOINT is "
                "the address a presigned URL is minted for, which the browser dials."
            ),
            id="eventpulse.E008",
        )
    ]


@register()
def check_blob_storage(app_configs=None, **kwargs):
    return find_blob_storage_errors(settings.ADAPTERS.get("blob", ""), settings.BLOB_STORAGE)
