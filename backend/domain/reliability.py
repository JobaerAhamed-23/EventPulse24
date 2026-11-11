"""FR-16's Source Reliability Score: the arithmetic, as pure functions (AD-8, AD-16).

**Stdlib only**, like the rest of `domain` — a Decimal in, a Decimal or a bool out. No
Source, no database, no clock. The recompute job (`reliability-recompute-and-escalation`)
reads the counts and stores the result; the ranking consumer reads the stored score. Neither
of them owns a rule, so neither of them can disagree with this module about one.

---

## The model, and what the prior buys

A beta-binomial posterior with `α = β = 5`:

```
posterior_mean = (α + positives) / (α + β + positives + negatives)
```

**The prior is the whole point of using one.** A raw rate punishes a Source for its first bad
event — one negative and the rate is 0.00. The smoothed posterior gives 0.45. FR-16 says it
out loud: *"a single negative event cannot crater a source."*

A Source with no observations sits at the prior mean, **0.50** — neither trusted nor
distrusted, which is the honest position before any evidence.

---

## The floor, and the contradiction it resolves

FR-16 contains two sentences that cannot both be literally true:

> A source needs at least **30** dismissal observations before its score moves.
> A new source (under 30 observations) cannot have its score drop below **0.32**.

A score that does not move never approaches a floor. **The arithmetic says which was meant.**
The all-negative posterior runs 0.50, 0.45, 0.42, 0.38, 0.36, **0.33** (n=5), **0.31** (n=6)
— so 0.32 is the posterior after five or six straight failures. It is emphatically *not* the
floor at n=29, which is 0.13.

So the floor is a deliberate statement rather than a derived constant: **until there are 30
observations, never judge a Source worse than about five strikes.** The score moves from the
first observation; the clamp holds the bottom until there is enough evidence to mean it.

Escalation requires `n >= 30`, so the clamp can never hide a Source that deserves review.

---

## Spike detection measures bad *events*, not the score

FR-16 asks for "a 3x week-over-week drop in reliability score". **That cannot happen**, and
the reason is worth stating because the rule looks like a safety net:

- Under 30 observations the floor pins the score between 0.50 and 0.32 — a ratio of at most
  **1.56**.
- At or above 30, a score low enough to be a third of its predecessor is already below 0.30,
  so `should_escalate` has fired already.
- A cumulative posterior is **sticky**: a Source at 0.80 needs roughly 100 all-negative events
  in a single week to reach even 2.96x. That is not a spike.

So `is_spike` compares the **rate of negative observations**, week over week — which is what
an early-warning signal is for: it fires while the cumulative score is still respectable.

Each week's rate is smoothed with the **same prior**, which costs nothing and buys three
things: no division by zero when the previous week was clean, automatic small-sample
suppression, and the two-argument signature the rest of the tree expects.

```
W1: 40 events,  2 bad -> 0.14 | W2: 24 bad -> 0.58 | 4.1x  spike
W1:  2 events,  0 bad -> 0.42 | W2:  1 bad -> 0.50 | 1.2x  noise, ignored
W1: 40 events,  0 bad -> 0.10 | W2: 20 bad -> 0.50 | 5.0x  spike
```

---

## The FR-25 seam

MVP inputs are editorial rejects and upheld user reports (negative) and approvals (positive).
**FR-25's dismissal rate is unbuilt, and is not faked here.** Every function takes plain
counts, so when dismissals arrive they are simply more negatives — no signature changes, and
no term is multiplied by a placeholder constant in the meantime. `domain/ranking.py` set that
precedent: an absent input is absent from the expression, never pinned to a stand-in that
makes the formula look verifiable when it is not.
"""

from decimal import ROUND_HALF_UP, Decimal

from shared.constants import (
    RELIABILITY_ESCALATION_SCORE,
    RELIABILITY_MIN_OBSERVATIONS,
    RELIABILITY_NEW_SOURCE_FLOOR,
    RELIABILITY_PRIOR_ALPHA,
    RELIABILITY_PRIOR_BETA,
    RELIABILITY_SPIKE_MULTIPLIER,
)

_HUNDREDTHS = Decimal("0.01")
_ALPHA = Decimal(RELIABILITY_PRIOR_ALPHA)
_BETA = Decimal(RELIABILITY_PRIOR_BETA)


def checked_count(value: int, *, name: str = "count") -> int:
    """Return `value` if it is a non-negative plain `int`; raise otherwise.

    **`bool` is refused, and that is not pedantry.** `True` is an `int` in Python, so
    `posterior_mean(True, False)` would quietly mean `(1, 0)` and return a real-looking
    score for what is almost certainly a caller passing flags by mistake.

    The sibling of `domain.confidence.checked_confidence`, which refuses floats for the same
    class of reason: a wrong type here produces a plausible number rather than an error, and
    a plausible wrong number is the one that ships.
    """
    if type(value) is not int:
        raise TypeError(f"{name} must be an int, not {type(value).__name__}")
    if value < 0:
        raise ValueError(f"{name} must be non-negative, not {value}")
    return value


def checked_rate(value: Decimal, *, name: str = "rate") -> Decimal:
    """Return `value` if it is a finite two-decimal Decimal in [0, 1]; raise otherwise."""
    if type(value) is not Decimal:
        raise TypeError(f"{name} must be a Decimal, not {type(value).__name__}")
    if not value.is_finite() or value.quantize(_HUNDREDTHS) != value or not 0 <= value <= 1:
        raise ValueError(f"{name} must be a two-decimal value in [0, 1], not {value}")
    return value


def _mean(favourable: int, total: int) -> Decimal:
    """The smoothed posterior mean, to two decimals. The one place the model is written."""
    return ((_ALPHA + favourable) / (_ALPHA + _BETA + total)).quantize(
        _HUNDREDTHS, rounding=ROUND_HALF_UP
    )


def posterior_mean(positives: int, negatives: int) -> Decimal:
    """The beta-binomial posterior mean: `(5 + positives) / (10 + positives + negatives)`.

    **The unclamped number.** `reliability_score` is what callers usually want; this is
    exposed because the recompute job records it and because the floor is only legible beside
    the value it is holding up.

    No observations gives the prior mean, 0.50.
    """
    positives = checked_count(positives, name="positives")
    negatives = checked_count(negatives, name="negatives")
    return _mean(positives, positives + negatives)


def reliability_score(positives: int, negatives: int) -> Decimal:
    """FR-16's score: the posterior, floored at 0.32 until there are 30 observations.

    See the module docstring for why the floor exists and why it is 0.32. In short: the score
    moves from the first observation, but a Source is never judged worse than about five
    strikes until there is enough evidence to mean it.

    **The floor lifts at exactly 30**, so a genuinely bad Source drops to its true posterior
    the moment it is measurable — 0.13 for an all-negative one — and `should_escalate` can see
    it.
    """
    score = posterior_mean(positives, negatives)
    if positives + negatives < RELIABILITY_MIN_OBSERVATIONS:
        return max(score, RELIABILITY_NEW_SOURCE_FLOOR)
    return score


def weekly_negative_rate(negatives: int, observations: int) -> Decimal:
    """One week's rate of bad events, smoothed with the same prior.

    **Smoothed, so that `is_spike` is comparing two numbers that mean something.** A raw rate
    is 0 for a clean week — which makes any ratio against it infinite — and wildly noisy for a
    week of two events. The same `α = β = 5` that stops one bad event cratering a score stops
    one bad event in a quiet week looking like a collapse.

    Raises if `negatives` exceeds `observations`: a week cannot have more rejections than
    events, and a caller that thinks it can has its arguments the wrong way round.
    """
    negatives = checked_count(negatives, name="negatives")
    observations = checked_count(observations, name="observations")
    if negatives > observations:
        raise ValueError(f"negatives ({negatives}) cannot exceed observations ({observations})")
    return _mean(negatives, observations)


def is_spike(previous: Decimal, current: Decimal) -> bool:
    """Whether this week's negative rate is 3x or more last week's (FR-16 spike detection).

    Both arguments come from `weekly_negative_rate`. **They are rates of bad events, not
    scores** — the module docstring explains why a ratio of scores cannot fire.

    A spike raises a `source_reliability` ReviewItem. It never pauses, hides or removes the
    Source: FR-16 is explicit that there is no auto-removal.
    """
    previous = checked_rate(previous, name="previous")
    current = checked_rate(current, name="current")
    return current >= RELIABILITY_SPIKE_MULTIPLIER * previous


def should_escalate(score: Decimal, observations: int) -> bool:
    """FR-16: below 0.30 **and** at least 30 observations raises a review item.

    **Both halves, and the second is the one that matters.** A Source with four bad events has
    a low posterior and no evidence; escalating it would put noise in the editor's queue, which
    is the queue's worst failure mode. The floor in `reliability_score` and this threshold are
    the same judgement applied twice: do not act on a Source until it has shown you 30 things.
    """
    score = checked_rate(score, name="score")
    observations = checked_count(observations, name="observations")
    return score < RELIABILITY_ESCALATION_SCORE and observations >= RELIABILITY_MIN_OBSERVATIONS


__all__ = [
    "checked_count",
    "checked_rate",
    "is_spike",
    "posterior_mean",
    "reliability_score",
    "should_escalate",
    "weekly_negative_rate",
]
