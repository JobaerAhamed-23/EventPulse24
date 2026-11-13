"""Django settings for EventPulse24. Values come only from `config.env`."""

from pathlib import Path

from config.adapters import adapter_paths
from config.databases import build_databases
from config.env import env
from shared.constants import AUTH_SESSION_LIFETIME
from shared.db import CATALOG, PERSONAL

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = env.django_secret_key
DEBUG = env.django_debug
ALLOWED_HOSTS = env.django_allowed_hosts

INSTALLED_APPS = [
    # Django admin is the MVP surface for FR-29 / FR-57 (AD-14). Its tables live in the personal
    # schema (AD-3). Routed at /admin/ (config/urls.py).
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

# Django's W045 warns that a CheckConstraint built on RawSQL() is not validated by
# `Model.full_clean()`. The ReminderPlan's "at most 4 slots" bound needs `jsonb_array_length`,
# because Django's JSONField has no length lookup at all: the generic `__len` lookup would
# render `(slots -> 'len') <= '4'`, which reads a *key* named "len" and yields NULL for every
# array — and a CHECK that evaluates to NULL passes, so the bound would never reject anything.
# The database still enforces the constraint, which is where this project wants it; the
# service validates the slot list too, so nothing relies on full_clean() for this rule.
SILENCED_SYSTEM_CHECKS = ["models.W045"]

# Project models use shared.models.UUIDv7Model; this only applies to Django's own models
# (Group, Permission, LogEntry).
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# AD-12, D12: the session is Django's, with a 7-day lifetime (FR-4). The lifetime is one
# named constant, so "how long does a sign-in last" has one answer.
#
# `SESSION_COOKIE_AGE` is a number of *seconds*, not a timedelta: Django's session backend
# passes it straight to `timedelta(seconds=...)`. The named constant is a timedelta, so it
# is converted here — the conversion happens in exactly one place.
SESSION_COOKIE_AGE = int(AUTH_SESSION_LIFETIME.total_seconds())
# The expiry is set at login, not slid on every request. A sliding session would mean a
# stolen session that is actively used never expires — which is exactly the property "a
# password reset ends the user's other sessions" relies on not being undermined.
SESSION_SAVE_EVERY_REQUEST = False
# The session outlives the browser, or the 7-day guarantee fails on every restart.
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
# JavaScript cannot read the session id.
SESSION_COOKIE_HTTPONLY = True
# Secure outside local. `Lax` allows the top-level GET navigation a user does when
# clicking the link in a reset email, and blocks cross-site POSTs — the CSRF-relevant case.
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = "Lax"

# AD-13, D13: the frontend's origin is trusted explicitly. `USE_X_FORWARDED_HOST` stays
# False: it would make Django trust the `Host` header, which is what an attacker controls.
CSRF_TRUSTED_ORIGINS = env.csrf_trusted_origins

# AD-18: the application-level key the calendar credential is encrypted with. Separate
# from SECRET_KEY on purpose, and validated at settings-load time (i.e. at startup): a
# missing or malformed key aborts the boot rather than failing later, when a user
# connects a calendar.
CALENDAR_CREDENTIAL_KEY = env.calendar_credential_key

# The frontend's base URL. The reset link points at the frontend's own route, because the
# frontend is a different origin from this runtime.
FRONTEND_BASE_URL = env.frontend_base_url

# The revalidation signal's edge (FR-26, FR-27). The backend POSTs a cache instruction to
# the frontend's route handler when an event's public page has gone stale.
#
# **The secret is separate from `CALENDAR_CREDENTIAL_KEY`**: one key per capability, and
# the calendar key is encrypted at rest (AD-18) so it could not be compared in plaintext
# anyway. The URL is server-to-server — the backend dials the frontend, so it needs the
# server's address, not the browser's.
REVALIDATION_SECRET = env.revalidation_secret
FRONTEND_REVALIDATION_URL = env.frontend_revalidation_url
REVALIDATION_TIMEOUT_SECONDS = env.revalidation_timeout_seconds

# FR-48 billing. The API key authorises calls out; the webhook secret verifies calls in.
STRIPE_API_KEY = env.stripe_api_key
STRIPE_WEBHOOK_SECRET = env.stripe_webhook_secret
STRIPE_PRICE_IDS = {"monthly": env.stripe_price_monthly, "yearly": env.stripe_price_yearly}

# FR-48: the paths the checkout and portal URLs point at. **These are the whole reason the
# endpoints cannot be turned into an open redirect.** The success, cancel and portal-return
# URLs handed to the provider are built from `FRONTEND_BASE_URL` plus one of these paths,
# so no part of them can come from a request body.
#
# The client supplies only the *plan*. A client that asks for a checkout with a
# `success_url` of its own gets a session whose URLs point at this host.
BILLING_SUCCESS_PATH = env.billing_success_path
BILLING_CANCEL_PATH = env.billing_cancel_path
BILLING_PORTAL_RETURN_PATH = env.billing_portal_return_path

# Whether the caller's IP may be read from `X-Forwarded-For`. Off by default: the header
# is attacker-controlled unless a trusted edge overwrites it, and trusting it let any
# caller mint a fresh throttle bucket per request. See `env.trust_forwarded_for`.
TRUST_FORWARDED_FOR = env.trust_forwarded_for

# AD-6: UTC is the storage truth; conversion happens at the presentation edge.
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

# Which adapter implements each port (resolved by ports.registry); ADAPTER_MODE=fake by default.
# THROTTLE_ADAPTER names the throttle's counter store on its own, because that port's state
# is shared by every process in the stack and a per-process fake cannot serve it.
ADAPTERS = adapter_paths(env.adapter_mode, env.source_fetch, env.throttle_adapter)

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

# FR-2: the city the **fake** geo adapter reports (adapters.geo.fake). Unset: the fake
# reports no location, which is the geo-miss branch. It has no effect in real mode, where
# the adapter reads the edge's geo header instead.
GEO_FAKE_CITY = env.geo_fake_city

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
