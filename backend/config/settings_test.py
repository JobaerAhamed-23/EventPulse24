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

# **There is deliberately no loopback-allowance flag here.** The end-to-end proof
# connects a calendar to a local fixture ICS server on loopback, which the SSRF
# policy rightly denies, so it needs an allowance — but a *global* settings flag
# would switch the policy off for every test in the suite, not just the one that
# asked for it. (It was tried; the thirteen tests that pin the SSRF policy all
# stopped refusing.)
#
# So the allowance is not a setting at all: it is `ports.fetch_policy.
# allow_loopback_fetch()`, a context manager that a test opens by name. It is
# refused outright unless the settings module in use is *this one* — the name is
# the whole mechanism — so there is nothing for an operator to set, export or
# pass. `tests/e2e/test_loopback_allowance.py` proves both halves: the
# permissive policy inside the block, and the refusal under production settings.

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
