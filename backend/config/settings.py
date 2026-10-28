"""Django settings for EventPulse24. Values come only from `config.env`."""

from pathlib import Path

from config.adapters import adapter_paths
from config.databases import build_databases
from config.env import env
from shared.db import CATALOG, PERSONAL

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = env.django_secret_key
DEBUG = env.django_debug
ALLOWED_HOSTS = env.django_allowed_hosts

INSTALLED_APPS = [
    # Django admin is the MVP surface for FR-29 / FR-57 (AD-14). Its tables live in the personal
    # schema (AD-3); /admin/ gets routed when admin is first needed.
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "ninja",
    "config.apps.ConfigConfig",
    "apps.ingestion",
    "apps.catalog",
    "apps.personalization",
    "apps.delivery",
    "apps.identity",
    "apps.editorial",
]

MIDDLEWARE = [
    # First, so every later middleware and view logs with the trace id (AD-13).
    "config.middleware.TraceIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# AD-3: two aliases on one Postgres. `default` is the personal schema, `catalog` the public one.
# The role (runtime DML-only vs owner for migrations) comes from DJANGO_DB_ROLE.
DATABASES = build_databases(env)
DATABASE_ROUTERS = ["config.db_router.SchemaRouter"]

# Which alias each app lives in. Every app with models must appear here (eventpulse.E001), and
# no relation field may cross the two sets (eventpulse.E002).
DATABASE_ROUTING = {
    CATALOG: {"ingestion", "catalog", "editorial"},
    PERSONAL: {
        "identity",
        "personalization",
        "delivery",
        "auth",
        "contenttypes",
        "sessions",
        "admin",
    },
}

AUTH_USER_MODEL = "identity.User"

# Project models use shared.models.UUIDv7Model; this only applies to Django's own models
# (Group, Permission, LogEntry).
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# AD-6: UTC is the storage truth; conversion happens at the presentation edge.
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

# Which adapter implements each port (resolved by ports.registry); ADAPTER_MODE=fake by default.
ADAPTERS = adapter_paths(env.adapter_mode, env.source_fetch)

# Source fetch limits (adapters.crawl.http.FetchLimits) and the fake adapter's fixtures.
SOURCE_FETCH = {
    "user_agent": env.source_fetch_user_agent,
    "max_bytes": env.source_fetch_max_bytes,
    "dns_timeout": env.source_fetch_dns_timeout,
    "connect_timeout": env.source_fetch_connect_timeout,
    "read_timeout": env.source_fetch_read_timeout,
    "write_timeout": env.source_fetch_write_timeout,
    "total_timeout": env.source_fetch_total_timeout,
    "max_redirects": env.source_fetch_max_redirects,
    "allowed_ports": tuple(env.source_fetch_allowed_ports),
    "fixtures_dir": env.source_fixtures_dir,
}

# Used by the SMTP email adapter; locally this is Mailpit. Django 6.1 MAILERS (EMAIL_HOST and
# EMAIL_PORT are deprecated). Tests swap every mailer for the locmem backend automatically.
MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "OPTIONS": {"host": env.smtp_host, "port": env.smtp_port},
    },
}

# Celery (config/celery.py). AD-7: Redis carries the tick and pipeline jobs only.
CELERY_BROKER_URL = env.redis_url
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TASK_IGNORE_RESULT = True  # no result backend: tasks report through the database
CELERY_TIMEZONE = "UTC"
CELERY_ENABLE_UTC = True
# AD-13: keep settings.LOGGING's redacting handler; Celery must not replace the root logger.
CELERY_WORKER_HIJACK_ROOT_LOGGER = False

# AD-13: one JSON handler on the root; redaction happens in the formatter. Django's default
# handlers are removed, not bypassed: `mail_admins` would email unredacted tracebacks and
# `console` would print an unredacted second copy. SQL logging (with parameter values) stays off.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "adapters.logging.formatter.JsonFormatter"}},
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "json",
        },
    },
    "root": {"handlers": ["stdout"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": [], "level": "INFO", "propagate": True},
        "django.server": {"handlers": [], "level": "INFO", "propagate": True},
        "django.db.backends": {"level": "WARNING"},
        # AD-13: both log full URLs and hosts at INFO/DEBUG; source fetches log their own record.
        "httpx": {"level": "WARNING"},
        "httpcore": {"level": "WARNING"},
    },
}
