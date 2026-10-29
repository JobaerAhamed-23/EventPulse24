"""Test settings: owner role (tests create the test DB and run DDL) plus the AD-3 probe apps."""

from config.databases import build_databases
from config.settings import *  # noqa: F403
from config.settings import DATABASE_ROUTING as BASE_ROUTING
from config.settings import INSTALLED_APPS as BASE_INSTALLED_APPS
from config.settings import env
from shared.db import CATALOG, PERSONAL

DATABASES = build_databases(env, role="owner")

# The test environment runs with `DEBUG` off, whatever the developer's `.env` says. Two
# reasons: it is the state production runs in, and `SESSION_COOKIE_SECURE` is computed from
# `DEBUG` at import time — so a developer's local `DJANGO_DEBUG=true` would otherwise
# silently change the cookie's security flags in the test suite.
DEBUG = False
SESSION_COOKIE_SECURE = not DEBUG

INSTALLED_APPS = [
    *BASE_INSTALLED_APPS,
    "tests.wall.catalog_probe",
    "tests.wall.personal_probe",
]

# New sets, so the imported routing map is never mutated.
DATABASE_ROUTING = {
    CATALOG: {*BASE_ROUTING[CATALOG], "catalog_probe"},
    PERSONAL: {*BASE_ROUTING[PERSONAL], "personal_probe"},
}
