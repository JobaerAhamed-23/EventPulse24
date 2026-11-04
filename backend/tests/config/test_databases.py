"""DATABASES construction: aliases, roles, search_path, per-alias settings (AD-3)."""

import pytest
from django.core.exceptions import ImproperlyConfigured

from config.databases import build_databases
from config.env import Settings
from shared.db import CATALOG, PERSONAL

URLS = {
    "database_url_owner": "postgresql://owner:pw@db.local:5440/eventpulse24",
    "database_url_catalog": "postgresql://catalog_user:pw@db.local:5440/eventpulse24",
    "database_url_personal": "postgresql://personal_user:pw@db.local:5440/eventpulse24",
}


def make_env(**overrides) -> Settings:
    values = {
        "django_secret_key": "test-secret",
        "redis_url": "redis://127.0.0.1:6380/0",
        "django_db_role": "runtime",
        # AD-18: required, with no default and no fallback.
        "calendar_credential_key": "k1.ZXZlbnRwdWxzZTI0LWxvY2FsLWNyZWRrZXktMzJieXQ",
        # The revalidation shared secret (FR-26, FR-27): required, with no default and no
        # fallback — a deployment that boots without it cannot authenticate a signal.
        "revalidation_secret": "test-revalidation-secret",
        **URLS,
        **overrides,
    }
    return Settings(_env_file=None, **values)


def test_build_databases_runtime_each_alias_uses_its_schema_role():
    databases = build_databases(make_env())

    assert databases[PERSONAL]["USER"] == "personal_user"
    assert databases[CATALOG]["USER"] == "catalog_user"


def test_build_databases_owner_both_aliases_use_owner_role():
    databases = build_databases(make_env(), role="owner")

    assert databases[PERSONAL]["USER"] == "owner"
    assert databases[CATALOG]["USER"] == "owner"


def test_build_databases_role_from_env_when_not_given():
    databases = build_databases(make_env(django_db_role="owner"))

    assert databases[CATALOG]["USER"] == "owner"


@pytest.mark.parametrize("role", ["runtime", "owner"])
def test_build_databases_search_path_per_alias(role):
    databases = build_databases(make_env(), role=role)

    assert databases[PERSONAL]["OPTIONS"]["options"] == "-c search_path=personal,public"
    assert databases[CATALOG]["OPTIONS"]["options"] == "-c search_path=catalog,public"


@pytest.mark.parametrize("role", ["runtime", "owner"])
def test_build_databases_url_query_options_kept_alongside_search_path(role):
    ssl_urls = {key: f"{url}?sslmode=require" for key, url in URLS.items()}
    databases = build_databases(make_env(**ssl_urls), role=role)

    for alias, schema in ((PERSONAL, "personal"), (CATALOG, "catalog")):
        assert databases[alias]["OPTIONS"] == {
            "sslmode": "require",
            "options": f"-c search_path={schema},public",
        }


@pytest.mark.parametrize("role", ["runtime", "owner"])
def test_build_databases_atomic_requests_off_on_every_alias(role):
    databases = build_databases(make_env(), role=role)

    assert all(config["ATOMIC_REQUESTS"] is False for config in databases.values())


def test_build_databases_test_settings_identical_so_aliases_share_one_test_db():
    databases = build_databases(make_env())

    assert databases[PERSONAL]["TEST"] == databases[CATALOG]["TEST"]
    assert databases[PERSONAL]["TEST"] == {
        "NAME": "test_eventpulse24",
        "TEMPLATE": "eventpulse24_test_template",
    }


def test_build_databases_owner_without_owner_url_raises():
    env = make_env(database_url_owner=None)

    with pytest.raises(ImproperlyConfigured, match="DATABASE_URL_OWNER"):
        build_databases(env, role="owner")
