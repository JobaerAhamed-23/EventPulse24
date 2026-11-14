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
    "THROTTLE_ADAPTER",
    "CALENDAR_ADAPTER",
    "SOURCE_FETCH_ALLOWED_PORTS",
    "SOURCE_FETCH_MAX_REDIRECTS",
    "SOURCE_FETCH_MAX_BYTES",
    "CALENDAR_CREDENTIAL_KEY",
    "REVALIDATION_SECRET",
    "VOYAGE_API_KEY",
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
    # The revalidation shared secret (FR-26, FR-27): required, with no default and no
    # fallback — a deployment that boots without it cannot authenticate a signal.
    "REVALIDATION_SECRET": "test-revalidation-secret",
    # FR-48 billing: required, with no default and no fallback. The API key authorises calls
    # out to the provider; the webhook secret verifies calls in. They are separate so one
    # leaking does not confer the other's power, and so they can rotate independently.
    "STRIPE_API_KEY": "sk_test_not-a-real-key",
    "STRIPE_WEBHOOK_SECRET": "whsec_not-a-real-secret",
    # FR-25 embeddings: required, with no default and no fallback. A missing key must
    # abort the boot rather than leave an app that looks healthy and fails the first
    # time an event needs embedding.
    "VOYAGE_API_KEY": "pa_test_not-a-real-key",
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


def test_settings_revalidation_secret_missing_raises(clean_env):
    """**The revalidation secret is required, with no default and no fallback.**

    A deployment that booted without it could not authenticate the signal — and a
    deployment that accepted *every* signal would let anyone invalidate our caches. So
    the missing value aborts the boot rather than degrading into an open endpoint.
    """
    clean_env.delenv("REVALIDATION_SECRET", raising=False)

    with pytest.raises(ValidationError, match="revalidation_secret"):
        Settings(_env_file=None)


def test_settings_revalidation_defaults(clean_env):
    """The revalidation URL and timeout have defaults; the secret does not."""
    settings = Settings(_env_file=None)

    assert settings.frontend_revalidation_url == "http://localhost:3000/revalidate"
    assert settings.revalidation_timeout_seconds == 5.0
    assert settings.revalidation_secret == REQUIRED["REVALIDATION_SECRET"]


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


def test_the_throttle_adapter_defaults_to_following_the_mode(clean_env):
    assert Settings(_env_file=None).throttle_adapter is None  # follow ADAPTER_MODE


@pytest.mark.parametrize("value", ["memory", "redis"])
def test_the_throttle_adapter_accepts_the_two_stores(clean_env, value):
    clean_env.setenv("THROTTLE_ADAPTER", value)

    assert Settings().throttle_adapter == value


def test_the_throttle_adapter_rejects_an_unknown_store(clean_env):
    """A misspelled store must fail at boot, not fall back to a working one.

    Silently falling back to the in-memory store would be the worst outcome: the stack
    would boot, the counters would go back to being per-process, and the seed's reset
    would stop reaching the API — with nothing in the logs to say why.
    """
    clean_env.setenv("THROTTLE_ADAPTER", "redisx")

    with pytest.raises(ValidationError):
        Settings()


# --- CALENDAR_ADAPTER ---------------------------------------------------------------------------


def test_the_calendar_adapter_is_unset_by_default(clean_env):
    """Unset: follow ADAPTER_MODE. The default local stack keeps the fake importer."""
    settings = Settings(_env_file=None)

    assert settings.calendar_adapter is None


def test_the_calendar_adapter_accepts_ics_with_a_real_fetch(clean_env):
    clean_env.setenv("CALENDAR_ADAPTER", "ics")
    clean_env.setenv("SOURCE_FETCH", "http")

    settings = Settings(_env_file=None)

    assert settings.calendar_adapter == "ics"


def test_ics_without_a_real_fetch_is_refused(clean_env):
    """**The configuration that would silently keep faking.**

    The ICS adapter never opens a socket — it fetches through the shared source-fetch
    port, so a fake one answers with fixture data for every calendar address. A stack
    configured this way would say `ics` and behave exactly like the fake, which is the
    confusion this whole override exists to end. So it is refused at boot, with the
    variable to set.
    """
    clean_env.setenv("CALENDAR_ADAPTER", "ics")
    clean_env.delenv("SOURCE_FETCH", raising=False)

    with pytest.raises(ValidationError, match="SOURCE_FETCH=http"):
        Settings(_env_file=None)


def test_ics_with_an_explicitly_fake_fetch_is_refused(clean_env):
    """The same refusal when the fake fetch is named rather than merely defaulted to."""
    clean_env.setenv("CALENDAR_ADAPTER", "ics")
    clean_env.setenv("SOURCE_FETCH", "fake")

    with pytest.raises(ValidationError, match="SOURCE_FETCH=http"):
        Settings(_env_file=None)


def test_the_fake_calendar_adapter_needs_no_real_fetch(clean_env):
    """The guard is about `ics` only: faking the calendar asks nothing of the fetch port."""
    clean_env.setenv("CALENDAR_ADAPTER", "fake")

    settings = Settings(_env_file=None)

    assert settings.calendar_adapter == "fake"


def test_an_unknown_calendar_adapter_is_refused(clean_env):
    clean_env.setenv("CALENDAR_ADAPTER", "google")

    with pytest.raises(ValidationError, match="calendar_adapter"):
        Settings(_env_file=None)
