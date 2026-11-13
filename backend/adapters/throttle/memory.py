"""In-memory throttle adapter: counts attempts in a dict, with an injectable clock.

This is the fake the tests use. It owns the notion of "now", so a test can pin the window
boundary exactly — no sleeping, no Redis, no timing flake. That is what makes the throttle
limit deterministically testable, which the work item asks for.

**The window is fixed, and it is anchored at the first attempt in it** — the same rule the
port states and the Redis adapter implements. The fake exists to stand in for the real
adapter, so it must not answer a differently-shaped question: a window that slid from the
last attempt would let the fake and the real adapter disagree about the same call, and a
test written against the fake would then be pinning behaviour production does not have.

**The counters live in a store, not in the adapter — and the default store is shared.**

This is the whole point of the split, and it is not a refactor for its own sake. The Redis
adapter keeps its counters in **Redis**: a server outside the process, shared by every
client that talks to it. The in-memory fake stands in for that server, so its counters
have to be shared the same way — by every adapter instance in the process.

**They were not, and the throttle did nothing.** `ports.registry.get_adapter` builds a
fresh adapter per call, so each call got a brand-new counter dict and the window always
read empty. The consequence was not a display bug but a **missing gate**: the Free
account's one-save-a-day cap was inert under `ADAPTER_MODE=fake` (the default), so a second
save was granted instead of refused, and the quota read `0 of 1` after a save. The real
Redis adapter was always correct — which is why this hid for so long: production behaved
and local did not.

**The rule is one line, and it is about the clock.** An adapter built **with** a clock owns
its own store, because the clock and the counters have to agree — a shared store written
by two adapters with different clocks would mix timestamps from two timelines. An adapter
built **without** a clock uses the **process-wide store**, which is the one the registry
builds, and it is the one that counts across requests the way Redis does.

So a test that injects a clock gets an isolated counter set and the real clock, and the
suite's isolation is unchanged; a run that goes through the registry gets the shared
counters, which is what the product needs.
"""

import time
from collections.abc import Callable

from ports.throttle import ThrottleDecision, ThrottlePort, ThrottleState


class InMemoryThrottleStore:
    """The counters, and the clock that dates them.

    **This is the fake's stand-in for Redis.** It holds the same thing Redis holds — a
    count per key, with a window — and it is deliberately separate from the adapter so the
    adapter can be rebuilt without losing the counts, exactly as a Redis client can be
    rebuilt without losing the keys.

    Args:
        now: Returns the current time as a monotonic float. Tests replace it to control
            the window; by default it is `time.monotonic`.
    """

    def __init__(self, now: Callable[[], float] | None = None) -> None:
        self._now = now or time.monotonic
        # key -> the timestamps of the attempts still inside the window.
        self._attempts: dict[str, list[float]] = {}

    def check(self, key: str, *, limit: int, window_seconds: int) -> ThrottleDecision:
        """Count one attempt against `key` and say whether it is within `limit`.

        **The attempt is counted even when it is refused.** That is the port's contract
        and the Redis adapter's behaviour — `INCR` happens before the limit is read — and
        it is what makes a refusal cost the user no extra time: the window is anchored at
        the first attempt, so a refusal does not move the anchor.
        """
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

    def clear(self) -> None:
        """Forget every key's window.

        **This is the store's own blunt instrument**, for the case where a caller cannot
        enumerate the keys it wants gone — the test suite's isolation, mostly.
        """
        self._attempts.clear()


#: The process-wide store, shared by every adapter built without a clock.
#:
#: **It is module-level rather than class-level** so that a store is one object with one
#: identity — the same way Redis is one server — and so that `reset_default_store` has a
#: single, unambiguous thing to clear.
_DEFAULT_STORE = InMemoryThrottleStore()


def default_store() -> InMemoryThrottleStore:
    """The store every clockless adapter shares.

    **It is the fake's Redis.** Everything the fake counts is counted here, so a counter
    spent by one request is visible to the next one — which is what makes the Free save
    cap a cap rather than a decoration.
    """
    return _DEFAULT_STORE


def reset_default_store() -> None:
    """Clear every key in the shared store.

    **This exists for the test suite's isolation, not for the product.** A test that
    wants a full allowance without reaching for a key of its own can clear the lot
    first, rather than guessing which keys a previous test spent.
    """
    _DEFAULT_STORE.clear()


class InMemoryThrottleAdapter(ThrottlePort):
    """Counts attempts per key in a fixed window.

    **Which store it counts in depends on the clock.** Built **with** a clock, it owns a
    store of its own — the clock and the counters have to agree, so an adapter with a
    pinned clock cannot write into a shared store another adapter reads with a different
    clock. Built **without** a clock, it counts in the **shared store**, which is what
    the registry builds and what the product needs.

    Args:
        now: Returns the current time as a monotonic float. Tests replace it to control
            the window; by default it is `time.monotonic`.
        store: The store to count in. Defaults to a store of its own when `now` is
            given, and to the process-wide store otherwise.
    """

    def __init__(
        self,
        now: Callable[[], float] | None = None,
        store: InMemoryThrottleStore | None = None,
    ) -> None:
        if store is not None:
            self._store = store
        elif now is not None:
            # A pinned clock and a shared store cannot be mixed: the shared store's
            # timestamps were written by whatever clock wrote them last.
            self._store = InMemoryThrottleStore(now=now)
        else:
            self._store = default_store()

    def check(self, key: str, *, limit: int, window_seconds: int) -> ThrottleDecision:
        return self._store.check(key, limit=limit, window_seconds=window_seconds)

    def peek(self, key: str, *, window_seconds: int) -> ThrottleState:
        return self._store.peek(key, window_seconds=window_seconds)

    def reset(self, key: str) -> None:
        self._store.reset(key)


__all__ = [
    "InMemoryThrottleAdapter",
    "InMemoryThrottleStore",
    "default_store",
    "reset_default_store",
]
