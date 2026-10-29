"""The throttle: per-IP and per-account limits, and the key hygiene that keeps the email
out of the store (AD-13).

The clock is injected, so the window boundary is pinned exactly — no sleeping, no flake.
"""

from apps.identity.services.throttle import LIMITS, account_key, ip_key, is_throttled
from shared.constants import (
    AUTH_THROTTLE_RESET_ACCOUNT,
    AUTH_THROTTLE_RESET_IP,
    AUTH_THROTTLE_SIGN_IN_ACCOUNT,
    AUTH_THROTTLE_SIGN_IN_IP,
    AUTH_THROTTLE_SIGN_UP_ACCOUNT,
    AUTH_THROTTLE_SIGN_UP_IP,
    AUTH_THROTTLE_WINDOW_SECONDS,
)


def test_the_account_key_never_carries_the_email():
    """AD-13: the address must not appear in a key the store holds or logs."""
    key = account_key("sign_in", "maya@example.com")

    assert "maya@example.com" not in key
    assert key.startswith("auth:sign_in:acct:")


def test_two_spellings_of_one_address_share_one_bucket():
    """Otherwise the per-account limit would be bypassed by varying the casing."""
    assert account_key("sign_in", "Maya@Example.com") == account_key("sign_in", "maya@example.com")


def test_the_ip_key_carries_the_address_as_given():
    assert ip_key("sign_in", "1.2.3.4") == "auth:sign_in:ip:1.2.3.4"


def test_the_ip_key_has_a_placeholder_for_a_missing_address():
    assert ip_key("sign_in", None) == "auth:sign_in:ip:unknown"


def test_the_limits_are_the_named_constants():
    assert LIMITS["sign_in"] == (AUTH_THROTTLE_SIGN_IN_IP, AUTH_THROTTLE_SIGN_IN_ACCOUNT)
    assert LIMITS["sign_up"] == (AUTH_THROTTLE_SIGN_UP_IP, AUTH_THROTTLE_SIGN_UP_ACCOUNT)
    assert LIMITS["reset"] == (AUTH_THROTTLE_RESET_IP, AUTH_THROTTLE_RESET_ACCOUNT)


def test_the_window_is_an_hour():
    assert AUTH_THROTTLE_WINDOW_SECONDS == 3600


def test_is_throttled_refuses_once_the_ip_limit_is_spent(throttle_adapter):
    # Distinct addresses, so only the per-IP bucket is being spent.
    for n in range(AUTH_THROTTLE_SIGN_IN_IP):
        assert (
            is_throttled("sign_in", ip_address="1.2.3.4", normalised_email=f"u{n}@example.com")
            is False
        )

    assert (
        is_throttled("sign_in", ip_address="1.2.3.4", normalised_email="another@example.com")
        is True
    )


def test_is_throttled_refuses_once_the_account_limit_is_spent(throttle_adapter):
    for n in range(AUTH_THROTTLE_SIGN_IN_ACCOUNT):
        assert (
            is_throttled("sign_in", ip_address=f"1.2.3.{n}", normalised_email="maya@example.com")
            is False
        )

    assert (
        is_throttled("sign_in", ip_address="9.9.9.9", normalised_email="maya@example.com") is True
    )


def test_the_window_frees_the_bucket_when_it_expires(throttle_adapter):
    """The clock is the fake's, so the boundary is exact."""
    for _ in range(AUTH_THROTTLE_SIGN_IN_ACCOUNT):
        is_throttled("sign_in", ip_address="1.2.3.4", normalised_email="maya@example.com")

    assert (
        is_throttled("sign_in", ip_address="1.2.3.4", normalised_email="maya@example.com") is True
    )

    # Move past the window.
    throttle_adapter.test_clock["now"] += AUTH_THROTTLE_WINDOW_SECONDS + 1

    assert (
        is_throttled("sign_in", ip_address="1.2.3.4", normalised_email="maya@example.com") is False
    )


def test_the_operations_do_not_share_a_bucket(throttle_adapter):
    """A sign-in attempt does not spend the sign-up budget."""
    for _ in range(AUTH_THROTTLE_SIGN_IN_IP):
        is_throttled("sign_in", ip_address="1.2.3.4", normalised_email="a@example.com")

    assert is_throttled("sign_up", ip_address="1.2.3.4", normalised_email="a@example.com") is False
