"""eventpulse.E001 / E002 on explicit inputs, plus the registered wrappers (AD-3)."""

import pytest
from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import SystemCheckError
from django.db import models
from django.test.utils import isolate_apps, override_settings

from config.checks import (
    check_apps_are_routed,
    check_retention_declared,
    check_uuid7_primary_keys,
    find_cross_alias_relations,
    find_fake_fetch_fixture_errors,
    find_missing_credential_key_errors,
    find_models_without_retention,
    find_models_without_uuid7_pk,
    find_unmapped_apps,
)
from shared.db import CATALOG, PERSONAL
from shared.models import UUIDv7Model
from shared.retention import RetentionCategory


@isolate_apps("tests.wall.catalog_probe", "tests.wall.personal_probe")
def test_cross_alias_foreign_key_reported_as_e002():
    class CatalogSide(models.Model):
        class Meta:
            app_label = "catalog_probe"

    class PersonalSide(models.Model):
        catalog_side = models.ForeignKey(CatalogSide, on_delete=models.CASCADE)

        class Meta:
            app_label = "personal_probe"

    errors = find_cross_alias_relations([CatalogSide, PersonalSide], settings.DATABASE_ROUTING)

    assert [error.id for error in errors] == ["eventpulse.E002"]
    assert errors[0].obj is PersonalSide._meta.get_field("catalog_side")


@isolate_apps("tests.wall.catalog_probe", "tests.wall.personal_probe")
def test_cross_alias_many_to_many_reported_as_e002():
    class CatalogSide(models.Model):
        class Meta:
            app_label = "catalog_probe"

    class PersonalSide(models.Model):
        catalog_sides = models.ManyToManyField(CatalogSide)

        class Meta:
            app_label = "personal_probe"

    errors = find_cross_alias_relations([PersonalSide], settings.DATABASE_ROUTING)

    assert [error.id for error in errors] == ["eventpulse.E002"]


@isolate_apps("tests.wall.personal_probe")
def test_same_alias_foreign_key_not_reported():
    class Parent(models.Model):
        class Meta:
            app_label = "personal_probe"

    class Child(models.Model):
        parent = models.ForeignKey(Parent, on_delete=models.CASCADE)

        class Meta:
            app_label = "personal_probe"

    assert find_cross_alias_relations([Parent, Child], settings.DATABASE_ROUTING) == []


@isolate_apps("tests.wall.catalog_probe", "tests.wall.personal_probe")
def test_cross_alias_assignment_refused_by_router_in_memory():
    class CatalogSide(models.Model):
        class Meta:
            app_label = "catalog_probe"

    class PersonalSide(models.Model):
        catalog_side = models.ForeignKey(CatalogSide, on_delete=models.CASCADE)

        class Meta:
            app_label = "personal_probe"

    with pytest.raises(ValueError, match="database router prevents this relation"):
        PersonalSide(catalog_side=CatalogSide())


def test_unmapped_app_with_models_reported_as_e001():
    probe = apps.get_app_config("catalog_probe")
    routing = {CATALOG: set(), PERSONAL: set()}

    errors = find_unmapped_apps([probe], routing)

    assert [error.id for error in errors] == ["eventpulse.E001"]


def test_app_without_models_never_reported():
    ninja = apps.get_app_config("ninja")

    assert find_unmapped_apps([ninja], {CATALOG: set(), PERSONAL: set()}) == []


def test_project_routing_maps_every_app_with_models():
    assert find_unmapped_apps(apps.get_app_configs(), settings.DATABASE_ROUTING) == []


def test_registered_check_only_inspects_passed_app_configs():
    identity = apps.get_app_config("identity")

    with override_settings(DATABASE_ROUTING={CATALOG: set(), PERSONAL: set()}):
        errors = check_apps_are_routed(app_configs=[identity])

    assert [error.obj for error in errors] == ["apps.identity"]


@isolate_apps("tests.wall.personal_probe")
def test_model_without_retention_reported_as_e003_until_declared():
    class Undeclared(models.Model):
        class Meta:
            app_label = "personal_probe"

    class Declared(models.Model):
        retention_category = RetentionCategory.ACCOUNT_CONTENT

        class Meta:
            app_label = "personal_probe"

    errors = find_models_without_retention([Undeclared, Declared])

    assert [(error.id, error.obj) for error in errors] == [("eventpulse.E003", Undeclared)]


@isolate_apps("tests.wall.personal_probe")
def test_retention_value_not_a_category_reported_as_e004():
    class Misdeclared(models.Model):
        retention_category = "forever"

        class Meta:
            app_label = "personal_probe"

    errors = find_models_without_retention([Misdeclared])

    assert [error.id for error in errors] == ["eventpulse.E004"]


@isolate_apps("tests.wall.personal_probe")
def test_retention_auto_created_through_table_ignored():
    class Tag(models.Model):
        retention_category = RetentionCategory.NOT_USER_DATA

        class Meta:
            app_label = "personal_probe"

    class Tagged(models.Model):
        retention_category = RetentionCategory.ACCOUNT_CONTENT
        tags = models.ManyToManyField(Tag)

        class Meta:
            app_label = "personal_probe"

    through = Tagged._meta.get_field("tags").remote_field.through

    assert find_models_without_retention([Tag, Tagged, through]) == []


@isolate_apps("tests.wall.personal_probe")
def test_retention_framework_map_covers_models_we_do_not_own():
    class Foreign(models.Model):
        class Meta:
            app_label = "personal_probe"

    framework = {"personal_probe.foreign": RetentionCategory.AUDIT_LOG}

    assert find_models_without_retention([Foreign], framework) == []


def test_project_models_all_declare_retention():
    assert check_retention_declared() == []
    assert check_retention_declared(app_configs=[apps.get_app_config("identity")]) == []


def test_plain_manage_py_check_passes():
    call_command("check")


def test_plain_manage_py_check_runs_the_routing_check():
    """Regression: these checks were tagged `database`, which plain `check` skips."""
    routing = {alias: set(labels) for alias, labels in settings.DATABASE_ROUTING.items()}
    routing[PERSONAL].discard("identity")

    with override_settings(DATABASE_ROUTING=routing), pytest.raises(SystemCheckError) as error:
        call_command("check")

    assert "eventpulse.E001" in str(error.value)


@pytest.mark.parametrize("module", ["apps.catalog.models", "adapters.llm.models"])
@isolate_apps("tests.wall.catalog_probe")
def test_project_model_without_uuid7_pk_reported_as_e005(module):
    Plain = type(
        "Plain",
        (models.Model,),
        {"__module__": module, "Meta": type("Meta", (), {"app_label": "catalog_probe"})},
    )

    errors = find_models_without_uuid7_pk([Plain])

    assert [(error.id, error.obj) for error in errors] == [("eventpulse.E005", Plain)]


@isolate_apps("tests.wall.catalog_probe")
def test_project_model_on_uuid7_base_not_reported():
    Based = type(
        "Based",
        (UUIDv7Model,),
        {
            "__module__": "apps.catalog.models",
            "Meta": type("Meta", (), {"app_label": "catalog_probe"}),
        },
    )

    assert find_models_without_uuid7_pk([Based]) == []


def test_uuid7_check_skips_through_tables_and_models_that_are_not_ours():
    user = apps.get_model("identity", "User")
    through = user._meta.get_field("groups").remote_field.through
    probe = apps.get_model("catalog_probe", "Thing")
    group = apps.get_model("auth", "Group")

    assert find_models_without_uuid7_pk([through, probe, group]) == []


def test_project_models_all_use_uuid7():
    assert check_uuid7_primary_keys() == []


FAKE = {"fetch": "adapters.crawl.fake.FakeFetchAdapter"}
HTTP = {"fetch": "adapters.crawl.http.HttpFetchAdapter"}


def test_fake_fetch_fixtures_valid_in_this_repo():
    assert find_fake_fetch_fixture_errors(FAKE, settings.SOURCE_FETCH["fixtures_dir"]) == []


def test_broken_fake_fetch_fixtures_reported_as_e006(tmp_path):
    (tmp_path / "index.json").write_text("{not json")

    [error] = find_fake_fetch_fixture_errors(FAKE, tmp_path)

    assert error.id == "eventpulse.E006"


def test_fixtures_not_checked_when_fetching_over_http(tmp_path):
    assert find_fake_fetch_fixture_errors(HTTP, tmp_path) == []


# ─── E007: the credential key ─────────────────────────────────────────────────


VALID_KEY = "k1.ZXZlbnRwdWxzZTI0LWxvY2FsLWNyZWRrZXktMzJieXQ"


def test_a_valid_credential_key_reports_nothing():
    assert find_missing_credential_key_errors([VALID_KEY]) == []


def test_a_missing_credential_key_is_reported_as_e007():
    [error] = find_missing_credential_key_errors([""])

    assert error.id == "eventpulse.E007"


def test_a_malformed_credential_key_is_reported_as_e007():
    [error] = find_missing_credential_key_errors(["not-a-key"])

    assert error.id == "eventpulse.E007"


def test_the_e007_hint_names_the_variable():
    [error] = find_missing_credential_key_errors([""])

    assert "CALENDAR_CREDENTIAL_KEY" in error.hint


def test_the_e007_hint_says_there_is_no_fallback():
    """The credential key is separate from `SECRET_KEY` on purpose (AD-18)."""
    [error] = find_missing_credential_key_errors([""])

    assert "DJANGO_SECRET_KEY" in error.hint
    assert "no fallback" in error.hint


def test_the_e007_error_never_repeats_the_key():
    """The error is visible to an operator, and a malformed value may still be secret."""
    [error] = find_missing_credential_key_errors(["k1.not-valid-base64!!LEAKEDVALUE"])

    assert "LEAKEDVALUE" not in str(error)
    assert "LEAKEDVALUE" not in error.hint
