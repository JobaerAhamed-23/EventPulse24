"""The session's settings: the 7-day lifetime and the cookie flags (D12).

These are asserted against `django.conf.settings`, so a change to any of them fails the
suite. That is the point: the flags are a security property, and a silent edit to them
should not pass unnoticed.
"""

from datetime import timedelta

from django.conf import settings

from shared.constants import AUTH_SESSION_LIFETIME


def test_the_session_lifetime_is_seven_days():
    """FR-4: "not prompted to re-authenticate within 7 days".

    `SESSION_COOKIE_AGE` is a number of seconds — Django's session backend passes it
    straight to `timedelta(seconds=...)`, so a timedelta there is a `TypeError` at the
    first request that saves a session.
    """
    assert AUTH_SESSION_LIFETIME == timedelta(days=7)
    assert settings.SESSION_COOKIE_AGE == 7 * 24 * 60 * 60


def test_the_session_cookie_is_httponly():
    """JavaScript cannot read the session id."""
    assert settings.SESSION_COOKIE_HTTPONLY is True


def test_the_session_cookie_is_secure_outside_local():
    """The rule: `SESSION_COOKIE_SECURE = not DEBUG`.

    Asserted on `django.conf.settings`, because the test environment runs with `DEBUG` off
    — the state production runs in — so the two must agree there.
    """
    assert bool(settings.SESSION_COOKIE_SECURE) == (not settings.DEBUG)
    assert settings.SESSION_COOKIE_SECURE is True


def test_the_session_cookie_is_samesite_lax():
    """`Lax` allows the top-level GET navigation of a reset link, and blocks cross-site
    POSTs — the CSRF-relevant case."""
    assert settings.SESSION_COOKIE_SAMESITE == "Lax"


def test_the_session_expiry_is_not_slid_on_every_request():
    """A sliding session would mean a stolen session that is actively used never
    expires — which is exactly what "a reset ends the other sessions" relies on."""
    assert settings.SESSION_SAVE_EVERY_REQUEST is False


def test_the_session_outlives_the_browser():
    """Otherwise the 7-day guarantee fails on every browser restart."""
    assert settings.SESSION_EXPIRE_AT_BROWSER_CLOSE is False


def test_forwarded_host_is_not_trusted():
    """D13: `USE_X_FORWARDED_HOST` would make Django trust the `Host` header, which is
    what an attacker controls. `CSRF_TRUSTED_ORIGINS` is the explicit allowlist."""
    assert getattr(settings, "USE_X_FORWARDED_HOST", False) is False
