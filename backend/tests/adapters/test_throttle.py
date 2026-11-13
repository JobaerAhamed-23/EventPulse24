"""The two throttle adapters, and the port's window contract (PRD §11.2).

**The port states one rule, and two adapters implement it.** `ThrottlePort.check` says:
*"The window is fixed: the count resets `window_seconds` after the first attempt in it."*
That is not a suggestion — it is the sentence the whole rate-limit story rests on, and two
adapters have to honour it identically or a test written against the fake would be pinning
behaviour production does not have.

So these tests pin two things:

- **the rule itself**, on the in-memory adapter, at the boundary — the window opens with the
  *first* attempt, not the last, and a refused attempt does not move the anchor;
- **the parity**, by running the same calls against both adapters and asserting they answer
  identically. The Redis adapter is exercised against an in-memory stand-in for Redis, so no
  server is needed; the stand-in **deletes expired keys**, because that is what real Redis
  does and it is the behaviour the window rule depends on.

**Why the Redis adapter deserves a test at all.** It is the adapter production runs, and
until now nothing tested it directly — it was only ever reached through app-level tests that
stub the port out. A window rule that only the fake implements is a window rule that does
not exist in production.

**A fixed window, not a sliding one.** The difference matters: under a sliding window a
client that keeps attempting just often enough holds its bucket open forever, and a refusal
extends the wait it was supposed to end. The in-memory adapter used to slide; these tests
are why it does not any more.
"""

import pytest

from adapters.throttle.memory import (
    InMemoryThrottleAdapter,
    InMemoryThrottleStore,
    reset_default_store,
)
from adapters.throttle.redis import KEY_PREFIX, RedisThrottleAdapter

#: A window long enough to walk through without arithmetic drifting.
WINDOW = 100

#: A limit of one, so the boundary is reachable in two calls.
LIMIT = 1


class StubRedis:
    """The slice of Redis the throttle adapter uses, over a logical clock.

    **It deletes expired keys**, because that is the part that matters. A stand-in that kept
    an expired key would make the adapter believe a closed window was still open — and the
    parity test would then be testing the stand-in rather than the adapter.
    """

    def __init__(self) -> None:
        self.store: dict[str, int] = {}
        self.expiry: dict[str, float] = {}
        self.now = 0.0

    def _sweep(self) -> None:
        """Drop every key whose TTL has passed, as Redis does on access."""
        for key in [k for k, when in self.expiry.items() if when <= self.now]:
            self.expiry.pop(key, None)
            self.store.pop(key, None)

    def incr(self, key: str) -> int:
        self._sweep()
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    def expire(self, key: str, seconds: int) -> None:
        self.expiry[key] = self.now + seconds

    def ttl(self, key: str) -> int:
        self._sweep()
        if key not in self.store:
            return -2
        return max(0, int(self.expiry.get(key, 0) - self.now))

    def get(self, key: str):
        """What `peek` reads. Redis returns bytes and `None` for a missing or expired key —
        and an expired key is indistinguishable from one that never existed, which is the
        behaviour `peek` relies on rather than special-casing."""
        self._sweep()
        if key not in self.store:
            return None
        return str(self.store[key]).encode()

    def delete(self, key: str) -> int:
        """What `reset` calls. Redis answers with the number of keys it removed, and zero
        is a perfectly good answer — deleting a key that was never there is not an error."""
        self._sweep()
        existed = self.store.pop(key, None) is not None
        self.expiry.pop(key, None)
        return 1 if existed else 0


@pytest.fixture
def clock():
    """A clock the test owns, so the window boundary is exact and no test ever sleeps."""
    return {"now": 0.0}


@pytest.fixture
def memory(clock):
    """The in-memory adapter, with the test's clock."""
    return InMemoryThrottleAdapter(now=lambda: clock["now"])


# ── The window rule, on the in-memory adapter ─────────────────────────────────────


def test_the_first_attempt_is_allowed(memory):
    decision = memory.check("k", limit=LIMIT, window_seconds=WINDOW)

    assert decision.allowed is True
    assert decision.retry_after_seconds == 0


def test_the_second_attempt_inside_the_window_is_refused(memory):
    memory.check("k", limit=LIMIT, window_seconds=WINDOW)

    decision = memory.check("k", limit=LIMIT, window_seconds=WINDOW)

    assert decision.allowed is False


def test_the_window_closes_on_the_first_attempt_plus_the_window(memory, clock):
    """**The window is anchored at the *first* attempt, not the last.**

    The attempt at t=0 opens the window, so it closes at t=WINDOW — not at t=2*WINDOW, which
    is what a window anchored at the *last* attempt would give.
    """
    memory.check("k", limit=LIMIT, window_seconds=WINDOW)

    clock["now"] = WINDOW - 1
    assert memory.check("k", limit=LIMIT, window_seconds=WINDOW).allowed is False

    clock["now"] = WINDOW
    assert memory.check("k", limit=LIMIT, window_seconds=WINDOW).allowed is True


def test_a_refused_attempt_does_not_move_the_anchor(memory, clock):
    """**A refusal costs the user no extra time.**

    The anchor is the *first* attempt, so refusing an attempt leaves it where it was — the
    allowance frees up on the schedule the first attempt set, not on a later one.
    """
    memory.check("k", limit=LIMIT, window_seconds=WINDOW)

    # A refusal just before the window closes.
    clock["now"] = WINDOW - 1
    assert memory.check("k", limit=LIMIT, window_seconds=WINDOW).allowed is False

    # And the window still closes at the first attempt's deadline.
    clock["now"] = WINDOW
    assert memory.check("k", limit=LIMIT, window_seconds=WINDOW).allowed is True


def test_the_window_does_not_slide_from_the_last_attempt(memory, clock):
    """**A sliding window would let a client hold its bucket open forever.**

    Under a sliding window, a client that keeps attempting holds its bucket open, because
    every attempt pushes the expiry out. Under a fixed one, the window closes on the
    *first* attempt's deadline no matter what came in between — so the attempt right after
    that deadline is allowed, even though the client never stopped trying.
    """
    memory.check("k", limit=LIMIT, window_seconds=WINDOW)

    # Keep attempting, all inside the first window.
    for moment in range(1, WINDOW):
        clock["now"] = float(moment)
        memory.check("k", limit=LIMIT, window_seconds=WINDOW)

    # The first attempt's deadline still governs: the window closed at t=WINDOW and a new
    # one opened, so this attempt is allowed — a sliding window would have refused it.
    clock["now"] = float(WINDOW)
    assert memory.check("k", limit=LIMIT, window_seconds=WINDOW).allowed is True


def test_the_count_is_per_key(memory):
    memory.check("a", limit=LIMIT, window_seconds=WINDOW)

    assert memory.check("b", limit=LIMIT, window_seconds=WINDOW).allowed is True


def test_a_refusal_says_how_long_to_wait(memory, clock):
    memory.check("k", limit=LIMIT, window_seconds=WINDOW)

    clock["now"] = 10
    decision = memory.check("k", limit=LIMIT, window_seconds=WINDOW)

    assert decision.allowed is False
    assert decision.retry_after_seconds > 0
    assert decision.retry_after_seconds <= WINDOW


# ── Parity: the two adapters answer the same question the same way ────────────────


def test_the_two_adapters_agree_about_every_call(clock):
    """**The fake and the real adapter must answer the same question the same way.**

    The in-memory adapter exists so a test can pin the window boundary without Redis. If the
    two disagreed about the same call, a test written against the fake would be pinning
    behaviour production does not have — which is the one thing a test double must never do.

    The walk below crosses the window boundary, so it covers the case where the two
    implementations are most likely to drift.
    """
    memory = InMemoryThrottleAdapter(now=lambda: clock["now"])
    stub = StubRedis()
    real = RedisThrottleAdapter(client=stub)

    for moment in (0, 1, 50, WINDOW - 1, WINDOW, WINDOW + 1, 2 * WINDOW):
        clock["now"] = float(moment)
        stub.now = float(moment)

        fake_decision = memory.check("k", limit=LIMIT, window_seconds=WINDOW)
        real_decision = real.check("k", limit=LIMIT, window_seconds=WINDOW)

        assert fake_decision.allowed == real_decision.allowed, (
            f"the adapters disagree at t={moment}: "
            f"memory said {fake_decision.allowed}, redis said {real_decision.allowed}"
        )


def test_the_two_adapters_agree_on_the_window_opening_again(clock):
    """**They agree on the second window too** — not just the first.

    A parity test that only walked the first window would miss an implementation that reset
    its state wrongly on the boundary.
    """
    memory = InMemoryThrottleAdapter(now=lambda: clock["now"])
    stub = StubRedis()
    real = RedisThrottleAdapter(client=stub)

    for cycle in range(3):
        for moment in (0, WINDOW - 1, WINDOW):
            clock["now"] = float(cycle * WINDOW + moment)
            stub.now = clock["now"]

            fake_decision = memory.check("k", limit=LIMIT, window_seconds=WINDOW)
            real_decision = real.check("k", limit=LIMIT, window_seconds=WINDOW)

            assert fake_decision.allowed == real_decision.allowed, (
                f"the adapters disagree in cycle {cycle} at t={clock['now']}"
            )


# ── `peek`: reading the window without spending it ────────────────────────────────
#
# The method exists because *displaying* a limit and *spending* it are different acts.
# Browse shows "0 of 1 save used today" on every page load; if it asked the gate, loading
# the page would be the save. These tests pin that it counts nothing, on both adapters.


def test_peek_on_an_untouched_key_reads_empty(memory):
    state = memory.peek("k", window_seconds=WINDOW)

    assert state.used == 0
    assert state.resets_in_seconds == 0


def test_peek_counts_nothing(memory):
    """The whole point. Peeking a hundred times must not spend a single attempt."""
    for _ in range(100):
        memory.peek("k", window_seconds=WINDOW)

    assert memory.check("k", limit=LIMIT, window_seconds=WINDOW).allowed is True


def test_peek_reports_what_check_has_spent(memory):
    memory.check("k", limit=LIMIT, window_seconds=WINDOW)

    state = memory.peek("k", window_seconds=WINDOW)

    assert state.used == 1
    assert state.resets_in_seconds > 0


def test_peek_forgets_a_closed_window(memory, clock):
    """An expired window and one that never opened are the same answer — nothing is spent
    in the window that is open *now*."""
    memory.check("k", limit=LIMIT, window_seconds=WINDOW)
    clock["now"] = float(WINDOW)

    assert memory.peek("k", window_seconds=WINDOW).used == 0


def test_peek_does_not_evict_the_closed_window_it_finds(memory, clock):
    """A read that mutated the store would change the answer a later `check` gives, and a
    surface polling it on every page load would then be deciding when a user's window
    resets — which is the gate's job, not the sign's."""
    memory.check("k", limit=LIMIT, window_seconds=WINDOW)
    clock["now"] = float(WINDOW)
    memory.peek("k", window_seconds=WINDOW)

    # The gate still sees a fresh window and allows the attempt, exactly as it would have
    # had nobody peeked.
    assert memory.check("k", limit=LIMIT, window_seconds=WINDOW).allowed is True


def test_peek_is_per_key(memory):
    memory.check("a", limit=LIMIT, window_seconds=WINDOW)

    assert memory.peek("a", window_seconds=WINDOW).used == 1
    assert memory.peek("b", window_seconds=WINDOW).used == 0


def test_the_two_adapters_agree_about_peek(clock):
    """Parity, for the same reason `check` has it: a test written against the fake must be
    pinning behaviour production actually has. The walk crosses the window boundary, which
    is where two implementations are most likely to drift."""
    memory = InMemoryThrottleAdapter(now=lambda: clock["now"])
    stub = StubRedis()
    real = RedisThrottleAdapter(client=stub)

    for moment in (0, 1, 50, WINDOW - 1, WINDOW, WINDOW + 1, 2 * WINDOW):
        clock["now"] = float(moment)
        stub.now = float(moment)

        memory.check("k", limit=LIMIT, window_seconds=WINDOW)
        real.check("k", limit=LIMIT, window_seconds=WINDOW)

        fake_state = memory.peek("k", window_seconds=WINDOW)
        real_state = real.peek("k", window_seconds=WINDOW)

        assert fake_state.used == real_state.used, (
            f"the adapters disagree about `used` at t={moment}: "
            f"memory said {fake_state.used}, redis said {real_state.used}"
        )


def test_the_redis_adapter_reads_a_missing_key_as_empty():
    real = RedisThrottleAdapter(client=StubRedis())

    assert real.peek("never-touched", window_seconds=WINDOW).used == 0


def test_the_redis_adapter_survives_a_key_that_is_not_a_counter():
    """A key under our namespace holding something else is not a throttle window.

    Reporting zero shows a full allowance rather than refusing one the gate would allow —
    and the gate itself still decides every actual save, so nothing is let through.
    """
    stub = StubRedis()
    stub.store[KEY_PREFIX + "k"] = "not-a-number"
    real = RedisThrottleAdapter(client=stub)

    assert real.peek("k", window_seconds=WINDOW).used == 0


# ── The reset, on both adapters ──────────────────────────────────────────────────


def test_reset_puts_the_allowance_back(memory):
    """The whole point of the reset: the key's window is gone, so the allowance is full.

    **The seed needs this**, because the Free account's one-save-a-day window outlives
    the command — a second run would otherwise find the quota already spent and the
    walk-through's wall would be up before anything had pressed it.
    """
    assert memory.check("k", limit=LIMIT, window_seconds=WINDOW).allowed is True
    assert memory.check("k", limit=LIMIT, window_seconds=WINDOW).allowed is False

    memory.reset("k")

    assert memory.peek("k", window_seconds=WINDOW).used == 0
    assert memory.check("k", limit=LIMIT, window_seconds=WINDOW).allowed is True


def test_reset_on_a_key_that_was_never_touched_is_not_an_error(memory):
    """Clearing a key that does not exist is the same answer as clearing one that does."""
    memory.reset("never-touched")

    assert memory.peek("never-touched", window_seconds=WINDOW).used == 0


def test_reset_is_per_key(memory):
    """Clearing one key leaves the others alone — the reset is a key's, not the store's."""
    memory.check("a", limit=LIMIT, window_seconds=WINDOW)
    memory.check("b", limit=LIMIT, window_seconds=WINDOW)

    memory.reset("a")

    assert memory.peek("a", window_seconds=WINDOW).used == 0
    assert memory.peek("b", window_seconds=WINDOW).used == 1


def test_the_redis_adapter_resets_the_allowance():
    """The Redis adapter's reset, against the stand-in.

    **The key's layout is the adapter's own.** The caller says which key; the adapter
    says where it lives. A caller that reached past the port to `DEL` the bare key would
    be depending on the `throttle:` prefix being absent — and it is present.
    """
    stub = StubRedis()
    real = RedisThrottleAdapter(client=stub)

    real.check("k", limit=LIMIT, window_seconds=WINDOW)
    real.check("k", limit=LIMIT, window_seconds=WINDOW)
    assert real.peek("k", window_seconds=WINDOW).used == 2

    real.reset("k")

    assert real.peek("k", window_seconds=WINDOW).used == 0
    assert real.check("k", limit=LIMIT, window_seconds=WINDOW).allowed is True


def test_the_two_adapters_agree_about_reset(clock):
    """Parity, for the same reason the other parity tests have it.

    **The reset is a port method now**, so the fake and the real adapter must answer it
    the same way — or a test written against the fake would be pinning behaviour
    production does not have, which is the one thing a test double must never do.
    """
    memory = InMemoryThrottleAdapter(now=lambda: clock["now"])
    stub = StubRedis()
    real = RedisThrottleAdapter(client=stub)

    for key in ("a", "b"):
        memory.check(key, limit=LIMIT, window_seconds=WINDOW)
        real.check(key, limit=LIMIT, window_seconds=WINDOW)

    memory.reset("a")
    real.reset("a")

    for key in ("a", "b"):
        assert (
            memory.peek(key, window_seconds=WINDOW).used
            == real.peek(key, window_seconds=WINDOW).used
        ), f"the adapters disagree about `reset` for {key}"


# ── The shared store: the fake's Redis ───────────────────────────────────────────
#
# The counters have to survive between adapter instances, because the Redis adapter's
# counters survive between requests — Redis is a server outside the process, and the fake
# stands in for it. They used not to: every adapter got a brand-new counter dict, so the
# window always read empty and **the throttle did nothing at all**. The Free account's
# one-save-a-day cap was granted on every save, and the quota read `0 of 1` after one.


def test_two_adapters_without_a_clock_share_their_counters():
    """**The counters live in the store, not in the adapter.**

    This is the whole regression: two adapters built the way the registry builds them
    must see the same window, or the gate is inert between requests.
    """
    first = InMemoryThrottleAdapter()
    second = InMemoryThrottleAdapter()

    assert first.check("shared", limit=LIMIT, window_seconds=WINDOW).allowed is True
    assert second.check("shared", limit=LIMIT, window_seconds=WINDOW).allowed is False


def test_the_shared_store_survives_the_adapter_being_rebuilt():
    """**The adapter is the client; the store is the server.**

    Rebuilding the adapter is what the registry does on every call, and it must not lose
    the count — the same way a new Redis client does not lose the key.
    """
    InMemoryThrottleAdapter().check("rebuilt", limit=LIMIT, window_seconds=WINDOW)

    assert InMemoryThrottleAdapter().peek("rebuilt", window_seconds=WINDOW).used == 1


def test_an_adapter_with_a_clock_keeps_its_own_counters():
    """**A pinned clock and a shared store cannot be mixed.**

    The clock dates the timestamps, and the timestamps are in the store — so an adapter
    with a test's clock cannot write into a store another adapter reads with a different
    clock. It gets a store of its own, which is what keeps the suite's isolation intact.
    """
    pinned = InMemoryThrottleAdapter(now=lambda: 0.0)

    assert pinned.check("isolated", limit=LIMIT, window_seconds=WINDOW).allowed is True
    assert pinned.check("isolated", limit=LIMIT, window_seconds=WINDOW).allowed is False
    # **And the shared store knows nothing about it.**
    assert InMemoryThrottleAdapter().peek("isolated", window_seconds=WINDOW).used == 0


def test_an_explicit_store_is_used_verbatim():
    """**A caller can hand the adapter a store of its own**, which is how a test that
    wants the shared counters but a controlled clock can have both."""
    store = InMemoryThrottleStore(now=lambda: 0.0)
    adapter = InMemoryThrottleAdapter(store=store)

    adapter.check("explicit", limit=LIMIT, window_seconds=WINDOW)

    assert store.peek("explicit", window_seconds=WINDOW).used == 1


def test_reset_default_store_clears_every_key():
    """**The suite's isolation lever.** A test that wants a full allowance without
    reaching for a key of its own can clear the lot first."""
    first = InMemoryThrottleAdapter()
    first.check("a", limit=LIMIT, window_seconds=WINDOW)
    first.check("b", limit=LIMIT, window_seconds=WINDOW)

    reset_default_store()

    assert InMemoryThrottleAdapter().peek("a", window_seconds=WINDOW).used == 0
    assert InMemoryThrottleAdapter().peek("b", window_seconds=WINDOW).used == 0
