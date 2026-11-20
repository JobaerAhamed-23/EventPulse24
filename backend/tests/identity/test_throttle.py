"""The throttle: per-IP and per-account limits, and the key hygiene that keeps the email
out of the store (AD-13).

The clock is injected, so the window boundary is pinned exactly — no sleeping, no flake.
"""

from apps.identity.services.throttle import (
    LIMITS,
    account_key,
    ip_key,
    is_throttled,
    reset_email_change_throttle,
    reset_sign_in_throttle,
)
from shared.constants import (
    AUTH_THROTTLE_EMAIL_CHANGE_ACCOUNT,
    AUTH_THROTTLE_EMAIL_CHANGE_IP,
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


# --- the seed's reset ----------------------------------------------------------------------


def test_the_reset_gives_the_ip_allowance_back(throttle_adapter):
    """The per-IP bucket is the one a single-machine suite trips first.

    Six sign-ins from one address is inside the limit; six more from the next run is not.
    So the reset has to clear the per-IP counter, or the second run of a suite fails at
    the sign-in with a 429 and nothing to do with the code under test.
    """
    for _ in range(AUTH_THROTTLE_SIGN_IN_IP):
        is_throttled("sign_in", ip_address="1.2.3.4", normalised_email="a@example.com")
    assert is_throttled("sign_in", ip_address="1.2.3.4", normalised_email="b@example.com") is True

    reset_sign_in_throttle(ip_address="1.2.3.4", emails=[])

    assert is_throttled("sign_in", ip_address="1.2.3.4", normalised_email="b@example.com") is False


def test_the_reset_gives_the_account_allowance_back(throttle_adapter):
    """The per-account bucket is the one an account the suite signs in as twice trips."""
    for n in range(AUTH_THROTTLE_SIGN_IN_ACCOUNT):
        is_throttled("sign_in", ip_address=f"1.2.3.{n}", normalised_email="maya@example.com")
    assert (
        is_throttled("sign_in", ip_address="9.9.9.9", normalised_email="maya@example.com") is True
    )

    reset_sign_in_throttle(ip_address="9.9.9.9", emails=["maya@example.com"])

    assert (
        is_throttled("sign_in", ip_address="9.9.9.9", normalised_email="maya@example.com") is False
    )


def test_the_reset_leaves_the_limits_alone(throttle_adapter):
    """The reset clears the counters, not the rules.

    A reader who signs in ten times in an hour must still be refused the eleventh after
    the seed has run. If the reset had changed a limit, the rate limit would be a
    suggestion — and the seed would be the thing that broke it.
    """
    reset_sign_in_throttle(ip_address="1.2.3.4", emails=["maya@example.com"])

    for _ in range(AUTH_THROTTLE_SIGN_IN_IP):
        is_throttled("sign_in", ip_address="1.2.3.4", normalised_email="a@example.com")

    assert is_throttled("sign_in", ip_address="1.2.3.4", normalised_email="b@example.com") is True


def test_the_reset_normalises_the_address_before_keying_it(throttle_adapter):
    """The sign-in endpoint keys the account on the *normalised* address.

    `account_key` lowercases and strips, so a reset that passed `Maya@Example.com`
    without normalising would clear a key the sign-in never writes — and the account's
    allowance would still be spent.
    """
    for n in range(AUTH_THROTTLE_SIGN_IN_ACCOUNT):
        is_throttled("sign_in", ip_address=f"1.2.3.{n}", normalised_email="maya@example.com")
    assert (
        is_throttled("sign_in", ip_address="9.9.9.9", normalised_email="maya@example.com") is True
    )

    reset_sign_in_throttle(ip_address="9.9.9.9", emails=["  Maya@Example.com  "])

    assert (
        is_throttled("sign_in", ip_address="9.9.9.9", normalised_email="maya@example.com") is False
    )


def test_the_reset_leaves_the_other_operations_alone(throttle_adapter):
    """A seeded run signs in; it does not sign up or request a password reset.

    Clearing those windows too would give away an allowance the run never spent, and a
    sign-up window that a seed had emptied would be a window an attacker could spend
    before the limit noticed.
    """
    for _ in range(AUTH_THROTTLE_SIGN_UP_IP):
        is_throttled("sign_up", ip_address="1.2.3.4", normalised_email="a@example.com")
    assert is_throttled("sign_up", ip_address="1.2.3.4", normalised_email="b@example.com") is True

    reset_sign_in_throttle(ip_address="1.2.3.4", emails=["a@example.com"])

    assert is_throttled("sign_up", ip_address="1.2.3.4", normalised_email="b@example.com") is True


def test_the_reset_clears_only_the_addresses_it_is_given(throttle_adapter):
    """Another account's spent allowance is another account's business."""
    for n in range(AUTH_THROTTLE_SIGN_IN_ACCOUNT):
        is_throttled("sign_in", ip_address=f"1.2.3.{n}", normalised_email="other@example.com")
    assert (
        is_throttled("sign_in", ip_address="9.9.9.9", normalised_email="other@example.com") is True
    )

    reset_sign_in_throttle(ip_address="9.9.9.9", emails=["maya@example.com"])

    assert (
        is_throttled("sign_in", ip_address="9.9.9.9", normalised_email="other@example.com") is True
    )


# --- the email-change reset ----------------------------------------------------------------


def test_the_email_change_limits_are_the_named_constants():
    """The email-change window is tighter than the sign-in's, and it is named."""
    assert LIMITS["email_change"] == (
        AUTH_THROTTLE_EMAIL_CHANGE_IP,
        AUTH_THROTTLE_EMAIL_CHANGE_ACCOUNT,
    )


def test_the_email_change_reset_gives_the_ip_allowance_back(throttle_adapter):
    """The per-IP bucket is the one a single-machine suite trips first.

    The email-change window is five an hour per IP and three per account — tighter than
    the sign-in's — so a suite that asks for an address change more than once inside the
    hour finds the window already up and the request is refused with a 429.
    """
    for _ in range(AUTH_THROTTLE_EMAIL_CHANGE_IP):
        is_throttled("email_change", ip_address="1.2.3.4", normalised_email="a@example.com")
    assert (
        is_throttled("email_change", ip_address="1.2.3.4", normalised_email="b@example.com") is True
    )

    reset_email_change_throttle(ip_address="1.2.3.4", emails=[])

    assert (
        is_throttled("email_change", ip_address="1.2.3.4", normalised_email="b@example.com")
        is False
    )


def test_the_email_change_reset_gives_the_account_allowance_back(throttle_adapter):
    """The per-account bucket is the one an account the suite asks for a change trips."""
    for n in range(AUTH_THROTTLE_EMAIL_CHANGE_ACCOUNT):
        is_throttled("email_change", ip_address=f"1.2.3.{n}", normalised_email="maya@example.com")
    assert (
        is_throttled("email_change", ip_address="9.9.9.9", normalised_email="maya@example.com")
        is True
    )

    reset_email_change_throttle(ip_address="9.9.9.9", emails=["maya@example.com"])

    assert (
        is_throttled("email_change", ip_address="9.9.9.9", normalised_email="maya@example.com")
        is False
    )


def test_the_email_change_reset_leaves_the_limits_alone(throttle_adapter):
    """The reset clears the counters, not the rules.

    An email-change request sends real mail to an address the requester typed, so this
    is the operation where a tight limit matters most. A reader who asks six times in an
    hour must still be refused the sixth after the seed has run.
    """
    reset_email_change_throttle(ip_address="1.2.3.4", emails=["maya@example.com"])

    for _ in range(AUTH_THROTTLE_EMAIL_CHANGE_IP):
        is_throttled("email_change", ip_address="1.2.3.4", normalised_email="a@example.com")

    assert (
        is_throttled("email_change", ip_address="1.2.3.4", normalised_email="b@example.com") is True
    )


def test_the_email_change_reset_normalises_the_address_before_keying_it(throttle_adapter):
    """The endpoint keys the account on the *normalised* address.

    `account_key` lowercases and strips, so a reset that passed `Maya@Example.com`
    without normalising would clear a key the endpoint never writes — and the account's
    allowance would still be spent.
    """
    for n in range(AUTH_THROTTLE_EMAIL_CHANGE_ACCOUNT):
        is_throttled("email_change", ip_address=f"1.2.3.{n}", normalised_email="maya@example.com")
    assert (
        is_throttled("email_change", ip_address="9.9.9.9", normalised_email="maya@example.com")
        is True
    )

    reset_email_change_throttle(ip_address="9.9.9.9", emails=["  Maya@Example.com  "])

    assert (
        is_throttled("email_change", ip_address="9.9.9.9", normalised_email="maya@example.com")
        is False
    )


def test_the_email_change_reset_leaves_the_sign_in_window_alone(throttle_adapter):
    """The two resets clear their own operation's window, and only that one.

    Giving the sign-in window back as a side effect of an email-change reset would hand
    away an allowance the run never spent — and a window a seed had emptied would be a
    window an attacker could spend before the limit noticed.
    """
    for _ in range(AUTH_THROTTLE_SIGN_IN_IP):
        is_throttled("sign_in", ip_address="1.2.3.4", normalised_email="a@example.com")
    assert is_throttled("sign_in", ip_address="1.2.3.4", normalised_email="b@example.com") is True

    reset_email_change_throttle(ip_address="1.2.3.4", emails=["a@example.com"])

    assert is_throttled("sign_in", ip_address="1.2.3.4", normalised_email="b@example.com") is True


def test_the_email_change_reset_clears_only_the_addresses_it_is_given(throttle_adapter):
    """Another account's spent allowance is another account's business."""
    for n in range(AUTH_THROTTLE_EMAIL_CHANGE_ACCOUNT):
        is_throttled("email_change", ip_address=f"1.2.3.{n}", normalised_email="other@example.com")
    assert (
        is_throttled("email_change", ip_address="9.9.9.9", normalised_email="other@example.com")
        is True
    )

    reset_email_change_throttle(ip_address="9.9.9.9", emails=["maya@example.com"])

    assert (
        is_throttled("email_change", ip_address="9.9.9.9", normalised_email="other@example.com")
        is True
    )
