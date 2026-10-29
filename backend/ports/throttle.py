"""Throttle port (PRD §11.2): rate limiting, per IP and per account identifier.

The public auth operations — sign-in, sign-up and password-reset request — are limited, so
one host cannot spray many accounts and one account cannot be sprayed from many hosts.

The port is deliberately tiny: one operation, `check(key, limit, window_seconds)`, returning
whether the call is allowed. The *keys* are built by the app that owns the rule
(`apps/identity/services/throttle.py`), because the key shape is a product decision; the port
only stores counters.

Why a port rather than a Redis call from the app: the app must reach an adapter through a
port (the `apps | adapters` import contract), and the limit has to be testable
deterministically. The in-memory adapter owns an injectable clock, so a test can call the
operation N times and assert the N+1-th is refused, with no sleeping and no Redis.

Like every other port here, this is an ABC over frozen dataclasses and imports no Django.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ThrottleDecision:
    """Whether one attempt is allowed, and how long to wait if it isn't."""

    allowed: bool
    # Seconds until the window frees up. Zero when the attempt is allowed.
    retry_after_seconds: int = 0


class ThrottlePort(ABC):
    """A fixed-window counter store. Adapters implement `check`."""

    @abstractmethod
    def check(self, key: str, *, limit: int, window_seconds: int) -> ThrottleDecision:
        """Count one attempt against `key` and say whether it is within `limit`.

        The window is fixed: the count resets `window_seconds` after the first attempt in
        it. Implementations must not sleep or block.
        """
        ...
