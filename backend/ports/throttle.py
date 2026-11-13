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


@dataclass(frozen=True)
class ThrottleState:
    """What a key's window holds right now, without touching it.

    This is what `peek` returns, and it exists because *displaying* a limit and *spending*
    it are different acts. `check` counts — that is its contract and the right one for a
    gate. A surface that wants to say "0 of 1 used today" before the user has done
    anything cannot ask the gate, because asking would be the first attempt.
    """

    #: Attempts counted in the current window. Zero when the window is empty or expired.
    used: int
    #: Seconds until the window frees up. Zero when there is no open window.
    resets_in_seconds: int = 0


class ThrottlePort(ABC):
    """A fixed-window counter store. Adapters implement `check` and `peek`."""

    @abstractmethod
    def check(self, key: str, *, limit: int, window_seconds: int) -> ThrottleDecision:
        """Count one attempt against `key` and say whether it is within `limit`.

        The window is fixed: the count resets `window_seconds` after the first attempt in
        it. Implementations must not sleep or block.
        """
        ...

    @abstractmethod
    def peek(self, key: str, *, window_seconds: int) -> ThrottleState:
        """Read `key`'s window **without counting an attempt against it**.

        For showing a user what their allowance stands at. `check` is for deciding whether
        an action may proceed; this one changes nothing, so calling it on every page load
        cannot spend an allowance the user never used.

        It takes no `limit`: a limit is the caller's rule, and this read reports only what
        the store holds. The caller compares.

        **A key with no window reads as `used=0, resets_in_seconds=0`.** An expired window
        and a window that never opened are the same answer, because they are the same fact:
        nothing has been spent in the window that is open now.

        Implementations must not sleep or block.
        """
        ...

    @abstractmethod
    def reset(self, key: str) -> None:
        """Clear `key`'s window, so the next attempt against it starts from zero.

        **This is a seed-and-test affordance, and it is deliberately not on the port's
        everyday surface.** A product has no reason to clear a user's throttle window —
        the window *is* the rule, and a reader who spent their allowance has spent it. But
        a **repeatable seed** does: the walk-through's Free account has to start each run
        with a full allowance, or the second run would find the quota already spent and
        the test that exercises the wall would fail for the wrong reason.

        **The port owns the key's storage, so the port owns the clearing.** A caller that
        reached into the adapter's Redis client to `DEL` the key would be depending on
        the adapter's key layout — the `throttle:` prefix here — which is exactly the
        detail the port exists to hide.

        **Clearing a key that does not exist is not an error.** It is the same answer as
        clearing one that does.

        Implementations must not sleep or block.
        """
        ...
