"""Fixtures for the `identity` tests.

The email adapter is the one thing these tests need to *see*: which messages were sent, on
which stream, with which idempotency key. `ports.registry.get_email_port` builds a fresh
adapter on every call, so a test cannot inspect the adapter it just used.

The services import their adapters by name (`from ports.registry import get_email_port`),
so the name is bound in the *service* module at import time. Patching
`ports.registry.get_email_port` would not reach it; the patch has to land on the name each
service module actually calls.

That patch cannot be written as a dotted path either: `apps.identity.services.sign_up` as
an *attribute* of the package is the `sign_up` **function** (the package's `__init__`
imports it), not the submodule. Only `sys.modules` holds the module object itself, so
`patch_module_attribute` looks it up there.
"""

import importlib
import sys

import pytest

from adapters.email.memory import InMemoryEmailAdapter
from adapters.throttle.memory import InMemoryThrottleAdapter

#: The service modules that resolve the email adapter by name.
_EMAIL_CONSUMERS = (
    "apps.identity.services.sign_up",
    "apps.identity.services.password_reset",
)


def _ensure_imported(module_path: str) -> None:
    """Make sure the module is in `sys.modules` before it is looked up there.

    `patch_module_attribute` resolves through `sys.modules`, and a module is only in
    `sys.modules` once something has imported it. Without this, the fixture would depend
    on which test happened to run first: a test that needs the email adapter and happens
    to be the first in the file would fail with a `KeyError` on the module name, while the
    same test would pass later in the run. Importing here makes the fixture
    order-independent.
    """
    if module_path not in sys.modules:
        importlib.import_module(module_path)


def patch_module_attribute(monkeypatch, module_path: str, attribute: str, value) -> None:
    """Patch `attribute` on the module object named `module_path`.

    The module is resolved through `sys.modules`, not through `monkeypatch.setattr`'s
    dotted path: `apps.identity.services.sign_up` as an *attribute* of the package is the
    `sign_up` **function** (the package's `__init__` imports it), not the submodule. Only
    `sys.modules` holds the module object itself.
    """
    _ensure_imported(module_path)
    module = sys.modules[module_path]
    monkeypatch.setattr(module, attribute, value)


@pytest.fixture
def email_adapter(monkeypatch):
    """One in-memory email adapter, shared by every send in the test."""
    adapter = InMemoryEmailAdapter()
    for module_path in _EMAIL_CONSUMERS:
        patch_module_attribute(monkeypatch, module_path, "get_email_port", lambda: adapter)
    return adapter


@pytest.fixture
def throttle_adapter(monkeypatch):
    """One in-memory throttle adapter, with a clock the test can move.

    The fake keeps its own attempt log, so each test starts from a clean count. The clock
    is injected, so a test pins the window boundary exactly instead of sleeping.
    """
    clock = {"now": 1_000_000.0}
    adapter = InMemoryThrottleAdapter(now=lambda: clock["now"])
    # `throttle.py` is the only module that resolves the throttle port by name, and all
    # three auth services call `is_throttled`, so patching it covers them all.
    patch_module_attribute(
        monkeypatch, "apps.identity.services.throttle", "get_throttle_port", lambda: adapter
    )
    adapter.test_clock = clock  # type: ignore[attr-defined]
    return adapter
