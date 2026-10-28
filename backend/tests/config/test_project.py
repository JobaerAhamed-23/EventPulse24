"""Django project wiring: installed apps, timezone, system checks, URL surface."""

import pytest
from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.urls import Resolver404, resolve

MVP_MODULES = ["ingestion", "catalog", "personalization", "delivery", "identity", "editorial"]


@pytest.mark.parametrize("label", MVP_MODULES)
def test_mvp_module_installed_with_label(label):
    assert apps.get_app_config(label).name == f"apps.{label}"


def test_ninja_and_project_config_installed():
    assert "ninja" in settings.INSTALLED_APPS
    assert apps.get_app_config("config").name == "config"


def test_custom_user_model_set():
    assert settings.AUTH_USER_MODEL == "identity.User"


def test_time_zone_utc_and_aware_datetimes():
    assert settings.TIME_ZONE == "UTC"
    assert settings.USE_TZ is True


def test_system_check_passes():
    call_command("check", fail_level="WARNING")


def test_admin_not_routed_yet():
    with pytest.raises(Resolver404):
        resolve("/admin/")
