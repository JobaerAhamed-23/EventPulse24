"""Typed environment configuration (config/env.py)."""

import pytest
from pydantic import ValidationError

from config.env import ENV_FILE, REPO_ROOT, Settings

ENV_KEYS = [
    "DJANGO_SECRET_KEY",
    "DJANGO_DEBUG",
    "DJANGO_ALLOWED_HOSTS",
    "DJANGO_DB_ROLE",
    "DATABASE_URL_OWNER",
    "DATABASE_URL_CATALOG",
    "DATABASE_URL_PERSONAL",
    "REDIS_URL",
    "SMTP_HOST",
    "SMTP_PORT",
    "ADAPTER_MODE",
    "SOURCE_FETCH",
    "SOURCE_FETCH_ALLOWED_PORTS",
    "SOURCE_FETCH_MAX_REDIRECTS",
    "SOURCE_FETCH_MAX_BYTES",
    "CALENDAR_CREDENTIAL_KEY",
]

REQUIRED = {
    "DJANGO_SECRET_KEY": "test-secret",
    "DATABASE_URL_OWNER": "postgresql://owner:pw@127.0.0.1:5440/db",
    "DATABASE_URL_CATALOG": "postgresql://catalog:pw@127.0.0.1:5440/db",
    "DATABASE_URL_PERSONAL": "postgresql://personal:pw@127.0.0.1:5440/db",
    "REDIS_URL": "redis://127.0.0.1:6380/0",
    # AD-18: required, with no default and no fallback (a credential key must never be
    # derived from DJANGO_SECRET_KEY). The value is a valid `<key_id>.<base64url-32-bytes>`.
    "CALENDAR_CREDENTIAL_KEY": ("k1.ZXZlbnRwdWxzZTI0LWxvY2FsLWNyZWRrZXktMzJieXQ"),
}


@pytest.fixture
def clean_env(monkeypatch):
    # `make` exports .env into the environment; start every test from a known-empty state.
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    for key, value in REQUIRED.items():
        monkeypatch.setenv(key, value)
    return monkeypatch


def test_settings_required_values_present_loads(clean_env):
    settings = Settings(_env_file=None)

    assert settings.django_secret_key == "test-secret"
    assert settings.redis_url == "redis://127.0.0.1:6380/0"
    assert settings.adapter_mode == "fake"


def test_settings_secret_key_missing_raises(clean_env):
    clean_env.delenv("DJANGO_SECRET_KEY", raising=False)

    with pytest.raises(ValidationError, match="django_secret_key"):
        Settings(_env_file=None)


def test_settings_debug_unset_defaults_false(clean_env):
    assert Settings(_env_file=None).django_debug is False


def test_settings_allowed_hosts_comma_separated_splits_and_strips(clean_env):
    clean_env.setenv("DJANGO_ALLOWED_HOSTS", "a, b,,c ")

    assert Settings(_env_file=None).django_allowed_hosts == ["a", "b", "c"]


def test_settings_allowed_hosts_unset_empty_list(clean_env):
    assert Settings(_env_file=None).django_allowed_hosts == []


def test_settings_adapter_mode_unknown_rejected(clean_env):
    clean_env.setenv("ADAPTER_MODE", "production")

    with pytest.raises(ValidationError, match="adapter_mode"):
        Settings(_env_file=None)


def test_env_file_path_absolute_at_repo_root(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    assert ENV_FILE.is_absolute()
    assert ENV_FILE == REPO_ROOT / ".env"
    assert (REPO_ROOT / "docker-compose.yml").is_file()
    assert Settings.model_config["env_file"] == ENV_FILE


def test_settings_runtime_role_owner_url_optional(clean_env):
    clean_env.delenv("DATABASE_URL_OWNER")

    settings = Settings(_env_file=None)

    assert settings.django_db_role == "runtime"
    assert settings.database_url_owner is None


def test_settings_owner_role_without_owner_url_raises(clean_env):
    clean_env.delenv("DATABASE_URL_OWNER")
    clean_env.setenv("DJANGO_DB_ROLE", "owner")

    with pytest.raises(ValidationError, match="DATABASE_URL_OWNER"):
        Settings(_env_file=None)


def test_settings_owner_role_with_owner_url_accepted(clean_env):
    clean_env.setenv("DJANGO_DB_ROLE", "owner")

    assert Settings(_env_file=None).database_url_owner == REQUIRED["DATABASE_URL_OWNER"]


def test_source_fetch_defaults(clean_env):
    settings = Settings()

    assert settings.source_fetch is None  # follow ADAPTER_MODE
    assert settings.source_fetch_allowed_ports == [80, 443]
    assert settings.source_fetch_max_bytes == 10 * 1024 * 1024
    assert settings.source_fetch_total_timeout == 30.0


def test_source_fetch_allowed_ports_comma_separated(clean_env):
    clean_env.setenv("SOURCE_FETCH_ALLOWED_PORTS", "80, 443,8080")

    assert Settings().source_fetch_allowed_ports == [80, 443, 8080]


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("SOURCE_FETCH_ALLOWED_PORTS", "0"),
        ("SOURCE_FETCH_ALLOWED_PORTS", "70000"),
        ("SOURCE_FETCH_MAX_REDIRECTS", "-1"),
        ("SOURCE_FETCH_MAX_BYTES", "0"),
        ("SOURCE_FETCH", "ftp"),
    ],
)
def test_source_fetch_invalid_values_rejected(clean_env, key, value):
    clean_env.setenv(key, value)

    with pytest.raises(ValidationError):
        Settings()
