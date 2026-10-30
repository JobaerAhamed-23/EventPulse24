"""In-memory throttle adapter: counts attempts in a dict, with an injectable clock.

This is the fake the tests use. It owns the notion of "now", so a test can pin the window
boundary exactly — no sleeping, no Redis, no timing flake. That is what makes the throttle
limit deterministically testable, which the work item asks for.
"""

import time
from collections.abc import Callable

from ports.throttle import ThrottleDecision, ThrottlePort


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
        cutoff = moment - window_seconds
        attempts = [t for t in self._attempts.get(key, ()) if t > cutoff]
        attempts.append(moment)
        self._attempts[key] = attempts

        if len(attempts) <= limit:
            return ThrottleDecision(allowed=True)
        # The window frees up when the oldest attempt in it falls out.
        retry_after = max(1, int(attempts[0] + window_seconds - moment) + 1)
        return ThrottleDecision(allowed=False, retry_after_seconds=retry_after)
