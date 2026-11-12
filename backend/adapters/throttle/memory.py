"""In-memory throttle adapter: counts attempts in a dict, with an injectable clock.

This is the fake the tests use. It owns the notion of "now", so a test can pin the window
boundary exactly — no sleeping, no Redis, no timing flake. That is what makes the throttle
limit deterministically testable, which the work item asks for.

**The window is fixed, and it is anchored at the first attempt in it** — the same rule the
port states and the Redis adapter implements. The fake exists to stand in for the real
adapter, so it must not answer a differently-shaped question: a window that slid from the
last attempt would let the fake and the real adapter disagree about the same call, and a
test written against the fake would then be pinning behaviour production does not have.
"""

import time
from collections.abc import Callable

from ports.throttle import ThrottleDecision, ThrottlePort, ThrottleState


class InMemoryThrottleAdapter(ThrottlePort):
    """Counts attempts per key in a fixed window.

    Args:
        now: Returns the current time as a monotonic float. Tests replace it to control
            the window; by default it is `time.monotonic`.
    """

    def __init__(self, now: Callable[[], float] | None = None) -> None:
        self._now = now or time.monotonic
        # key -> the timestamps of the attempts still inside the window.
        self._attempts: dict[str, list[float]] = {}

    def check(self, key: str, *, limit: int, window_seconds: int) -> ThrottleDecision:
        moment = self._now()
        attempts = self._attempts.get(key, ())
        # **The window is fixed, and it is anchored at the first attempt in it.** The port
        # says so — "the count resets `window_seconds` after the first attempt in it" — and
        # the Redis adapter implements exactly that: `EXPIRE` is set only when the count
        # is 1, so the window slides from the *first* attempt and not from the last one.
        #
        # The window therefore closes when `first + window_seconds` passes, and **every**
        # attempt made since the first one counts against the limit — including the ones
        # that were refused. That is what makes a refusal cost the user no extra time: a
        # refused attempt does not move the anchor, so the bucket frees up on the schedule
        # the first attempt set.
        #
        # A window that slid from the *last* attempt instead would let a client keep a
        # bucket alive forever by attempting just often enough, and would make the two
        # adapters disagree about the same call — which is the one thing a test double
        # must never do.
        if attempts and attempts[0] + window_seconds <= moment:
            # The window has closed. The next attempt starts a new one.
            attempts = ()
        attempts = (*attempts, moment)
        self._attempts[key] = attempts

        if len(attempts) <= limit:
            return ThrottleDecision(allowed=True)
        # The window frees up when it closes, which is `window_seconds` after the first
        # attempt in it.
        retry_after = max(1, int(attempts[0] + window_seconds - moment) + 1)
        return ThrottleDecision(allowed=False, retry_after_seconds=retry_after)

    def peek(self, key: str, *, window_seconds: int) -> ThrottleState:
        """What this key's window holds, counting nothing.

        **It does not evict the closed window it finds.** `check` does that, on the next
        attempt, by starting a new one. A read that mutated the store would be a read that
        changes the answer a later `check` gives — and a surface polling this on every page
        load would then be deciding when a user's window resets, which is the gate's job.
        """
        moment = self._now()
        attempts = self._attempts.get(key, ())
        if not attempts or attempts[0] + window_seconds <= moment:
            # No window, or one that has already closed: nothing is spent in the window
            # that is open now. Both are the same answer, as the port says.
            return ThrottleState(used=0)
        resets_in = max(1, int(attempts[0] + window_seconds - moment) + 1)
        return ThrottleState(used=len(attempts), resets_in_seconds=resets_in)

    def reset(self, key: str) -> None:
        """Forget the key's window entirely.

        **The key is removed rather than emptied**, so a later `check` finds no window
        and starts a fresh one — which is what "the allowance is full again" means. A
        key that was never there is not an error.
        """
        self._attempts.pop(key, None)
