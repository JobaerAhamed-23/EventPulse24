"""The test-only loopback allowance cannot escape the tests.

The end-to-end proof connects a calendar to a local fixture ICS server on loopback,
which the SSRF policy rightly denies. The allowance that makes that reachable is
`ports.fetch_policy.allow_loopback_fetch()` — and this file is the proof of the
requirement that it is **impossible to enable outside tests**.

There are three claims to prove, and each is a separate test because each fails for a
different reason:

1. **The permissive policy is reachable inside the block, under the test settings.**
   Without this, the allowance might be unreachable *everywhere* — which would make
   the other two tests pass for the wrong reason.
2. **The block refuses to open outside a test run.** This is the guarantee: the
   mechanism is the settings module's *name* **and** the fact that a test runner is
   executing a test right now. Two independent gates, because one is not enough — see
   the note on the deployment-controlled environment variable below.
3. **The default is the real deny table, everywhere else.** A permissive policy that
   leaked outside the block would silently disable the SSRF policy for the whole
   suite — which is exactly the bug the first (global-flag) design had.

**Why the settings module is resolved by name.** `django.conf.settings` is a lazy
object that does not say which *file* the values came from, and the two settings
modules could define the same name with different values. The identity of the module
is the fact that matters, so that is what is checked.

**Why there is a second gate.** The first version checked the settings module's name
and nothing else, and the code review found that insufficient: `DJANGO_SETTINGS_MODULE`
is a **deployment-controlled environment variable**, and `config.settings_test` is a
fully functional settings module rather than a crippled one. An operator who pointed
it there would have got the permissive policy — which admits *every* address,
including a link-local metadata address. So the name check is now **necessary but not
sufficient**, and a test runner must also be executing a test. The two gates fail for
different reasons, so each gets its own test.

**Why this test changes `DJANGO_SETTINGS_MODULE` itself.** The check is made at
*call* time against the environment, so proving the refusal means pointing the
environment at the production settings module for the duration of one call. The
environment is restored in a `finally`, and `monkeypatch` restores it again even if
the test fails, so no test can inherit the production name.
"""

import os
import threading
from contextvars import copy_context
from ipaddress import ip_address

import pytest

from domain.address_policy import is_denied
from ports.fetch_policy import (
    TEST_SETTINGS_MODULE,
    LoopbackAllowanceUnavailable,
    allow_loopback_fetch,
    fetch_deny_policy,
    loopback_allowed,
    runner_is_active,
    settings_module_name,
)

# Addresses — the ones the SSRF policy denies and the allowance admits. The policy
# takes parsed address objects, not strings, because that is what the adapter's
# resolver produces.
LOOPBACK_V4 = ip_address("127.0.0.1")
LOOPBACK_V6 = ip_address("::1")
PRIVATE_V4 = ip_address("10.0.0.1")
DOCUMENTATION_V4 = ip_address("203.0.113.10")


def test_the_allowance_is_reachable_inside_the_block_under_the_test_settings():
    """Claim 1: inside the block, under `config.settings_test`, the policy is permissive.

    If this failed, the other two claims would be vacuous — a policy that is always
    the deny table refuses everywhere and so "refuses outside tests" would prove
    nothing.
    """
    assert settings_module_name() == TEST_SETTINGS_MODULE, (
        "This test must run under the test settings module; the whole allowance "
        "mechanism is the identity of that module."
    )

    deny = fetch_deny_policy()
    assert deny(LOOPBACK_V4) is True, "the real policy denies loopback"
    assert deny(LOOPBACK_V6) is True, "the real policy denies IPv6 loopback"

    with allow_loopback_fetch():
        permissive = fetch_deny_policy()
        assert permissive(LOOPBACK_V4) is False, (
            "the permissive policy is `lambda address: False` — it denies nothing, "
            "so `False` means 'admitted'."
        )
        assert permissive(LOOPBACK_V6) is False
        assert loopback_allowed() is True

    # And the block ends: the real policy is back.
    assert loopback_allowed() is False
    assert fetch_deny_policy() is is_denied


def test_the_block_refuses_to_open_outside_the_test_settings(monkeypatch):
    """Claim 2: under the production settings module, opening the block raises.

    This is the guarantee the work item asks for. The refusal happens *before* any
    state is set, so a failed attempt leaves nothing behind — there is no partially
    enabled allowance to inherit.

    **The runner is still active here, and that is what makes this test isolate the
    *settings* gate.** Two gates refuse in the same place, so a test that only checked
    "it raised" could not tell which one fired — and would still pass if the settings
    gate were deleted outright, because the runner gate would refuse instead. So the
    refusal is checked for the reason it gives: the message must name the settings
    module. Delete the settings gate and the block opens instead, and the test fails.
    """
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings")
    assert settings_module_name() == "config.settings"

    with pytest.raises(LoopbackAllowanceUnavailable) as excinfo:
        with allow_loopback_fetch():
            pytest.fail("the block must not open under the production settings")

    message = str(excinfo.value)
    assert "settings module" in message, (
        "the refusal must name the settings-module gate, so that this test cannot "
        "pass on the runner gate's refusal alone."
    )
    assert TEST_SETTINGS_MODULE in message
    assert loopback_allowed() is False
    assert fetch_deny_policy() is is_denied, (
        "a refused attempt must leave the real policy in force."
    )


def test_the_allowance_is_refused_when_no_settings_module_is_in_use(monkeypatch):
    """Claim 2, second case: a process with no settings module at all is refused too.

    The check is equality against the test module's name, so "no settings module" is
    simply another name — and it is refused. An allowlist that only refused *other*
    known names would be one missed name away from being open.

    As above, the refusal is checked for the settings-module reason, so that the
    runner gate cannot stand in for it.
    """
    monkeypatch.delenv("DJANGO_SETTINGS_MODULE", raising=False)

    with pytest.raises(LoopbackAllowanceUnavailable) as excinfo:
        with allow_loopback_fetch():
            pytest.fail("the block must not open without a settings module")

    assert "settings module" in str(excinfo.value)
    assert loopback_allowed() is False


def test_the_default_policy_is_the_real_deny_table():
    """Claim 3: with nothing asked for, the policy is exactly `domain`'s `is_denied`.

    This is the claim the thirteen SSRF policy tests in the suite rest on. It is
    stated here as its own test so that a future change to `fetch_deny_policy` cannot
    quietly weaken the default without one of these turning red.
    """
    assert loopback_allowed() is False
    assert fetch_deny_policy() is is_denied

    deny = fetch_deny_policy()
    assert deny(LOOPBACK_V4) is True, "loopback is denied by default"
    assert deny(LOOPBACK_V6) is True, "IPv6 loopback is denied by default"
    assert deny(PRIVATE_V4) is True, "private IPv4 is denied by default"
    assert deny(DOCUMENTATION_V4) is True, "documentation IPv4 is denied by default"


def test_the_allowance_does_not_leak_out_of_the_block():
    """Claim 3, second case: the block's end restores the default, even on an exception.

    `ContextVar.reset` runs in a `finally`, so an exception inside the block cannot
    leave the permissive policy behind. The next test that fetches a private address
    must still be refused — and the thirteen policy tests depend on exactly that.
    """
    with pytest.raises(RuntimeError):
        with allow_loopback_fetch():
            assert loopback_allowed() is True
            raise RuntimeError("boom")

    assert loopback_allowed() is False
    assert fetch_deny_policy() is is_denied


def test_the_allowance_is_scoped_to_the_current_context():
    """Claim 3, third case: the allowance does not leak into another context.

    `ContextVar` is per-thread and per-task. A `copy_context()` taken *inside* the
    block carries the flag; one taken *outside* does not. A background thread started
    inside the block — the shape of a task that outlives its request — sees the
    default, not the allowance.
    """
    with allow_loopback_fetch():
        inner = copy_context()
        assert inner.run(loopback_allowed) is True

    outer = copy_context()
    assert outer.run(loopback_allowed) is False

    seen: list[bool] = []
    with allow_loopback_fetch():
        thread = threading.Thread(target=lambda: seen.append(loopback_allowed()))
        thread.start()
        thread.join()
    assert seen == [False], (
        "a thread started inside the block must not inherit the allowance: "
        "the flag is per-context, and a new thread gets a fresh context."
    )


def test_the_production_settings_module_defines_no_allowance_flag():
    """Claim 2, third case: there is no setting an operator could set.

    The refusal is by settings-module *name*, but a reader deserves the positive
    proof too: the production settings module does not define any allowance flag, so
    there is nothing to set, export or pass. (A test that planted the flag on the
    production settings and asserted it was still refused would be the belt to this
    pair of braces; `test_the_block_refuses_to_open_outside_the_test_settings` is
    that belt, and this is the braces.)
    """
    import config.settings as production_settings

    names = [name for name in dir(production_settings) if "LOOPBACK" in name.upper()]
    assert names == [], (
        f"the production settings module defines allowance-like names: {names}. "
        "The allowance is not a setting; it is a context manager gated on the "
        "settings module's name."
    )


def test_the_allowance_is_refused_under_the_test_settings_without_a_test_runner(monkeypatch):
    """Claim 2, fourth case: the settings module alone is **not** enough.

    **This is the second gate, and the code review is what found it.** The first
    version of this mechanism checked the settings module's *name* and nothing else.
    That is not sufficient, because `DJANGO_SETTINGS_MODULE` is a
    deployment-controlled environment variable: `manage.py`, `config/asgi.py`,
    `config/wsgi.py` and `config/celery.py` all set it with
    `os.environ.setdefault(...)`, so an operator who sets it to `config.settings_test`
    runs the **test settings module in production** — and that module is fully
    functional, not a crippled one.

    Under that configuration the name check would pass, the permissive policy would be
    reachable, and it admits *every* address — including a link-local metadata address.

    So the name check is now treated as **necessary but not sufficient**: a test
    runner must also be executing a test. Here the settings module is deliberately
    left as the test one, and the test runner signal is removed — which is exactly
    what a deployment would look like if it pointed `DJANGO_SETTINGS_MODULE` at the
    test module without running the tests.
    """
    assert settings_module_name() == TEST_SETTINGS_MODULE, (
        "this test is about the *other* gate: the settings module is the test one "
        "here, and the refusal must come from the test-runner gate."
    )

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    with pytest.raises(LoopbackAllowanceUnavailable) as excinfo:
        with allow_loopback_fetch():
            pytest.fail("the block must not open without a test runner")

    assert "test runner" in str(excinfo.value)
    assert loopback_allowed() is False
    assert fetch_deny_policy() is is_denied, (
        "a refused attempt must leave the real policy in force."
    )


def test_the_test_runner_signal_is_present_during_a_test():
    """Claim 2, fifth case: the gate the refusal depends on is real.

    A gate that is *always* false would make the refusal unconditional and the
    allowance unreachable everywhere — which would make every other claim pass for the
    wrong reason. So the signal's presence inside a running test is asserted here,
    directly.

    This is the positive counterpart of the refusal above: inside a test the signal
    is present and the block opens; outside one it is absent and the block refuses.
    """
    assert runner_is_active() is True, (
        "a test runner must be executing this test, or the allowance could never "
        "open and the other claims would be vacuous."
    )
    assert os.environ.get("PYTEST_CURRENT_TEST"), (
        "pytest names the running test in the environment; that name is the signal "
        "the second gate reads."
    )

    with allow_loopback_fetch():
        assert loopback_allowed() is True


def test_the_settings_module_name_is_read_from_the_environment(monkeypatch):
    """The mechanism is the environment's settings-module name — so it is observable.

    A small direct test of `settings_module_name`, so that a later refactor cannot
    change *where* the name comes from without one of the claims above failing in a
    confusing way.
    """
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings")
    assert settings_module_name() == "config.settings"

    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings_test")
    assert settings_module_name() == "config.settings_test"

    monkeypatch.delenv("DJANGO_SETTINGS_MODULE", raising=False)
    assert settings_module_name() == ""

    # The value in the environment at the time of this call is the one that counts.
    assert os.environ.get("DJANGO_SETTINGS_MODULE", "") == ""
