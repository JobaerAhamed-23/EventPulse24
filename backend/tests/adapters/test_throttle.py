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

from adapters.throttle.memory import InMemoryThrottleAdapter
from adapters.throttle.redis import RedisThrottleAdapter

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
