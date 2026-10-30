"""Which address policy a fetch actually enforces, and the test-only allowance.

**This module is the seam between the SSRF deny table and the settings in force.**

`domain.address_policy` holds the deny table itself — pure knowledge, stdlib only, as
AD-2 requires. What it deliberately does **not** hold is the question "is this table the
one to apply right now?", because answering it needs to know *whether the caller has
asked for the allowance* — and that is a fact about the caller, not about the policy.

So the table stays in `domain`, and the resolution lives here.

**Why in `ports`, and not `domain`?** Because `domain` may not import Django
(`domain-pure`), and the resolution needs the settings. `shared` is the wrong side of
the layering for the same reason — `shared` sits *below* `domain` and may not import
it. `ports` is the layer that both `apps` and `adapters` can reach, and
`ports/registry.py` already reads Django's settings, so the precedent is here.

## The test-only loopback allowance

The end-to-end proof connects a calendar to a **local fixture ICS server** on
loopback. The SSRF policy rightly denies loopback, so the proof needs an allowance —
and the work item's requirement is explicit: *"the test configuration needs a
deliberate, test-only allowance. Make it impossible to enable outside tests, and add a
test proving that."*

### The first attempt, and why it was wrong

The obvious shape is a settings flag: `ALLOW_LOOPBACK_FETCH = True` in
`config/settings_test.py`, and the policy consults it. **That was tried and it is
wrong**, and the proof found why: the flag is *global*, so it switches the SSRF policy
off for **every test in the suite**, not just the one that asked for it. The thirteen
tests that pin the policy — that a private address is refused, that a redirect to a
private address is refused, that a host resolving to any denied address is refused
without connecting — all stopped refusing. A test-only allowance that weakens the
policy everywhere is not a test-only allowance; it is a hole in the policy with a
convenient name.

### The shape that works: the allowance is **per call**, and it must be asked for

`fetch_deny_policy()` returns the real `is_denied` **unless the caller is inside
`allow_loopback_fetch()`** — a context manager that turns the allowance on for one
block, in one thread, and off again when the block ends.

Three things make it safe, and each is checked by a test:

1. **It is off by default.** Nothing outside `allow_loopback_fetch()` ever gets the
   permissive policy, so the thirteen policy tests keep passing unchanged — and they
   are the proof that the default really is the deny table.
2. **It is scoped to a block.** The flag is a `ContextVar`, so it is per-thread and
   per-task: a test that opens the block does not open it for the test that runs after
   it, and an async task spawned inside it does not inherit it by accident.
3. **It cannot be enabled outside tests.** The context manager **refuses to open at
   all** unless **both** gates are satisfied:
   - the settings module in use is `config.settings_test` — the *name*, so there is
     nothing to set, export or pass; **and**
   - a test runner is genuinely driving this process.

   The second gate exists because the first one alone is **not enough**, and the code
   review is what found it. `DJANGO_SETTINGS_MODULE` is a deployment-controlled
   environment variable: `manage.py`, `config/asgi.py`, `config/wsgi.py` and
   `config/celery.py` all set it with `os.environ.setdefault(...)`, so an operator who
   sets it to `config.settings_test` gets a process running the **test settings module
   in production** — and `config.settings_test` is a fully functional settings module,
   not a crippled one. The name check alone would then open the allowance, and the
   permissive policy admits *every* address, including a link-local metadata address.

   So the name check is treated as **necessary but not sufficient**. The second gate is
   a fact about the *process*, not about its configuration: `pytest` is loaded and has
   an active session. A deployment can set any environment variable it likes and
   cannot make that true, because it does not run the tests.

   `config/settings.py` defines no allowance flag at all, and
   `tests/e2e/test_loopback_allowance.py` proves that opening the block under the
   production settings raises rather than granting the allowance — and that a process
   whose settings module is the test one, but which is not under a test runner, is
   refused as well.

The permissive policy is `lambda address: False` — *admits everything*, which is why it
is reachable only inside an explicitly opened, test-only block. It is deliberately not
"deny loopback but allow the rest": an allowance that names an exception invites the
next exception, and this one is a test fact rather than a policy.
"""

import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from ipaddress import IPv4Address, IPv6Address

from domain.address_policy import is_denied

# The settings module in which the allowance may be opened. **The name is one of the
# two gates**: the allowance is reachable only when this exact module is the one in
# use *and* a test runner is driving the process.
TEST_SETTINGS_MODULE = "config.settings_test"

# The flag the allowance turns on, scoped to the current context.
_loopback_allowed: ContextVar[bool] = ContextVar("ep_loopback_allowed", default=False)


def settings_module_name() -> str:
    """The dotted name of the settings module in use, or `""` if there is none.

    **`django.conf.settings` is deliberately not used.** It is a lazy object that does
    not say which *file* the values came from — and that is the whole question here,
    because the allowance is a fact about a file rather than about a value. The test
    settings and the production settings can both define the same name with different
    values; only the module's identity distinguishes them.

    **`os.environ` is read directly, not through `config.env`.** The banned-API rule
    (`TID251`) exists so that *configuration* — the values a deployment chooses — goes
    through pydantic-settings. This is not configuration: `DJANGO_SETTINGS_MODULE` is
    Django's own bootstrap variable, set by `manage.py` before any settings module is
    imported, and it is not a deployment choice about how the app should behave. It is
    the name of the file that *is* the configuration.
    """
    return os.environ.get("DJANGO_SETTINGS_MODULE", "")


def loopback_allowed() -> bool:
    """Whether the test-only loopback allowance is in force **right now**.

    True only inside an open `allow_loopback_fetch()` block.
    """
    return _loopback_allowed.get()


def runner_is_active() -> bool:
    """Whether a test runner is genuinely running a test in this process.

    **The second gate, and the one a deployment cannot satisfy by configuration.**

    The signal is `PYTEST_CURRENT_TEST`, which pytest sets in the environment for the
    duration of every test **call** phase and removes afterwards. It names the test
    that is running — `test_thing.py::test_case (call)`.

    Three things make this the right signal, and each was checked:

    - **It is present in every phase a test might use the allowance.** The allowance is
      opened inside a test, and pytest sets the variable for the whole call phase, so
      it is there whether the test is a plain function, a method of a class, or a
      fixture body.
    - **It is absent outside a test call.** It is unset at collection time and unset
      in any process that is not running a test — a web server, a Celery worker, a
      management command. So "pytest is installed" is not enough; "pytest is
      *executing a test right now*" is the actual requirement, and that is what the
      allowance needs.
    - **It is not an argument.** Unlike `sys.argv`, it is not a string the deployment
      composes to talk the check into passing — it is written by pytest itself, into
      the environment, for the duration of a test.

    A deployment that *did* set `PYTEST_CURRENT_TEST` by hand would be doing something
    deliberate and unusual, and the settings-module gate would still have to pass too.
    Two independent gates is the point: each alone is weaker than the guarantee, and
    together they are much harder to satisfy by accident.

    **The name does not begin with `test_`.** A public function called
    `test_runner_active` would be collected by pytest as a test when a test module
    imported it — a test that asserts nothing, and a warning in the output. The name
    says what it is without looking like a test.
    """
    current = os.environ.get("PYTEST_CURRENT_TEST", "")
    return bool(current)


def _allowance_refusal_reason() -> str | None:
    """Why the allowance cannot open right now, or `None` if it can.

    The two gates, in the order they are checked, each with its own reason — so the
    refusal says *which* gate stopped it. A single combined message would make a
    misconfigured deployment hard to diagnose.

    **Both gates live here, and nowhere else.** The context manager consults this and
    this only, so there is one place that decides whether the permissive policy is
    reachable — which is the property the whole design rests on.
    """
    if settings_module_name() != TEST_SETTINGS_MODULE:
        return (
            "the settings module in use is "
            f"{settings_module_name() or 'none'}, not {TEST_SETTINGS_MODULE}"
        )
    if not runner_is_active():
        return "no test runner is executing a test in this process"
    return None


class LoopbackAllowanceUnavailable(RuntimeError):
    """Raised when the loopback allowance is asked for outside the test settings."""


@contextmanager
def allow_loopback_fetch() -> Iterator[None]:
    """Admit loopback for the duration of the block. **Test settings only.**

    **This is the only way the permissive policy is ever reachable.** The block is
    refused outright unless **both** gates hold: the settings module in use is
    `config.settings_test`, **and** a test runner is driving this process. A
    deployment cannot reach it by setting a variable, passing a flag, or importing
    something — and the settings-module gate alone would not have been enough, because
    that module is itself a deployment-controlled choice.

    The allowance is scoped to the block and to the current context (`ContextVar`), so
    it does not leak into the next test, and it is off everywhere else — which is what
    keeps the SSRF policy's own tests meaningful.
    """
    reason = _allowance_refusal_reason()
    if reason is not None:
        raise LoopbackAllowanceUnavailable(
            "The loopback fetch allowance is available only under the test settings "
            f"module ({TEST_SETTINGS_MODULE}) and only while a test runner is "
            f"executing a test. This process was refused because {reason}."
        )

    token = _loopback_allowed.set(True)
    try:
        yield
    finally:
        _loopback_allowed.reset(token)


def fetch_deny_policy() -> Callable[[IPv4Address | IPv6Address], bool]:
    """The address policy a fetch actually enforces.

    **The real `is_denied`, unless the caller is inside `allow_loopback_fetch()`.**
    Nothing else is ever returned, so the production path is exactly the policy it
    always was.
    """
    if loopback_allowed():
        return lambda address: False
    return is_denied


__all__ = [
    "LoopbackAllowanceUnavailable",
    "TEST_SETTINGS_MODULE",
    "allow_loopback_fetch",
    "fetch_deny_policy",
    "loopback_allowed",
    "runner_is_active",
    "settings_module_name",
]
