"""The Relevance Pulse: the per-user score, its buckets, and its tags (AD-10, FR-22).

AD-10 names **two** kinds of explanation and says both are persisted, neither is ever
recomputed at render:

| Kind | Computed | Persisted on | Serves | Owner |
| --- | --- | --- | --- | --- |
| **Event Fit** | per `(event, city)` | `catalog` | SEO pages, Pulse Preview | `ingestion` |
| **Relevance Pulse** | at digest composition | `personal` | card, detail, email | `personal` app |

This module is the second kind. `domain/event_fit.py` is the first, and the two look
identical on screen — which is why AD-10 says they must never be substituted for one
another. A visitor with no session can be shown an Event Fit and nothing else.

**The formula is reduced, and the reduction is the design.** FR-22 publishes

```
relevance_score = 0.40 × preference_graph_match
                + 0.25 × source_reliability
                + 0.20 × recency_fit
                + 0.15 × novelty_vs_exploration
```

and locks those weights. **One of the four components has no input in this codebase**:

| Published input | Status |
| --- | --- |
| `source_reliability` | **Present** — FR-16's score, stored on `Source` and read here. |
| `novelty_vs_exploration` | Absent — needs FR-25's graph *and* an event category. |
| `preference_graph_match` | Reduced — the interest-chip overlap survives. |
| `recency_fit` | **Survives** — start time and the user's day both exist. |

The absent term has no `Event` category field to read from, and FR-25 is unbuilt. The
third is reduced rather than absent: what the user actually picked at onboarding is the
interest chips — up to three of them (FR-1) — and that overlap is the computable part of
`preference_graph_match`.

What will supply each absent term, so the reduction is legible as a debt and not as a
choice:

- `novelty_vs_exploration` — **FR-25**, when it ships.
- `preference_graph_match` — FR-25 replaces the interest chips with the real graph.
So the omitted term is **absent from the expression** rather than multiplied by a
constant. A term pinned to a constant is an *inert weight*: the published formula would
stay arithmetically checkable and still produce a different number from the one on the
card, which is a worse trust failure than a reduced formula because it looks verifiable.
`domain/event_fit.py` set this precedent when it refused to invent a "Free" tag — "they
are added to Event Fit's rule set then, not faked now."

What survives, and what each term means:

```
relevance_score = 0.35 × interest_overlap
                + 0.20 × recency
                + 0.10 × city_match
                + 0.10 × confidence
                + 0.25 × source_reliability
```

A reader can compute any event's score by hand from these five inputs, which is FR-22's
actual promise — "a user reading the PRD can compute the Confidence Pulse for any Event
given the inputs" — rather than its incidental one about four particular weights.

**`source_reliability` is at FR-22's published weight, 0.25, and it is not an inert
weight.** This is worth being explicit about, because at launch every source has fewer
than 30 observations and therefore sits at or near the 0.50 prior — so the term's
*current* value is nearly uniform across the corpus.

It is not inert for three reasons, and the third is the decisive one:

1. **It is read from a stored, computed, per-source number** — `Source.reliability_score`,
   written by FR-16's weekly recompute, not a literal in this module.
2. **The prior is a value, not a constant in the expression.** `0.50` is
   `reliability_score(0, 0)` — the posterior mean of the beta-binomial prior — so if
   FR-16's prior is ever re-tuned, this term moves with it. A weight pinned to a literal
   cannot do that.
3. **It is a per-candidate *variable*, not a term pinned to a constant.** An inert weight
   is one that *cannot* distinguish two candidates — it cannot affect the ranking while
   appearing in the published formula. This one distinguishes them the moment the corpus
   differentiates: a source recomputed to `0.20` and one recomputed to `0.80` produce
   scores that differ by exactly `0.25 × 0.60 = 0.15`, and the module's own tests pin
   that. A term whose *distribution* happens to be narrow today is not a term that is
   *pinned* to a constant.

**Why the term is not gated on the minimum observation count.** The alternative — entering
the term only for a source past 30 observations — was considered and rejected, for two
reasons that both come back to FR-22's promise that the inputs are enough:

- The formula's *shape* would depend on a fact the formula does not carry. A reader
  given five inputs could not compute the score without also knowing the source's
  observation count, and there would be two different formulas in the product at once —
  which is the "arithmetically checkable but produces a different number" failure the
  paragraph above names.
- It would put a **cliff** in the ranking: a source crossing 30 observations would change
  score with no change in the event, discontinuously. That is the no-flicker rule's
  failure manufactured by the formula itself.

So the term enters for every source, and the prior's contribution is exactly what a term
with no opinion contributes — the same structure the personal-event path already uses for
`city_match = 0.00` and `confidence = 1.00`.

**FR-22's own words govern the relationship between the published formula and this one:**
"The Architecture spec describes the *implementation* of the formula but does not redefine
the weights." The weights above are that implementation, and the substitution of each
published term for the term the product can compute is recorded in the ADR named by
`RANKING_WEIGHTS_AMENDMENT`.

**Cold-start only.** FR-5 gates all personalised weighting on "the signal threshold in the
deferred ADR-0007", and **ADR-0007 does not exist**. This module therefore ships the
cold-start path only, and there is no threshold to check. That is a statement about the
sources, not a shortcut, and it is why the formula above is the whole formula.

**The score is a `Decimal`, never a float.** FR-22's bucket boundaries are exact, and on
an exact boundary the **lower** bucket wins: 0.850 → 4 dots, not 5. A float `0.85` is not
`Decimal("0.85")` — it is `0.85000000000000002220446...` — and it lands the card in the
wrong bucket. `domain/confidence.py` already refuses floats for exactly this reason.

**The tags come from the same inputs the score used.** AD-10's whole point is that the
explanation and the decision cannot drift apart. If a tag said "nearby" and the score had
not matched the city, the card would be lying. So the tags are derived here, from the
score's own inputs — never from raw source text (AD-9).

**`now` is an explicit parameter.** There is no clock read in this module and no
randomness anywhere in it: the same inputs always give the same output, and every
boundary is testable at the exact second. Nothing here is computed at render time —
`domain` has no idea a render exists.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from shared.constants import (
    MAX_INTEREST_PICKS,
    RANKING_BUCKET_2,
    RANKING_BUCKET_3,
    RANKING_BUCKET_4,
    RANKING_BUCKET_5,
    RANKING_BUCKET_MAX,
    RANKING_BUCKET_MIN,
    RANKING_CITY_OTHER,
    RANKING_CITY_SAME,
    RANKING_CITY_SAME_COUNTRY,
    RANKING_EVENING_HOUR,
    RANKING_HYSTERESIS_DELTA,
    RANKING_MAX_TAGS,
    RANKING_PERSONAL_EVENT_BOOST,
    RANKING_RECENCY_LATER,
    RANKING_RECENCY_WITHIN_DAY,
    RANKING_RECENCY_WITHIN_FORTNIGHT,
    RANKING_RECENCY_WITHIN_THREE_DAYS,
    RANKING_RECENCY_WITHIN_WEEK,
    RANKING_SCORE_MAX,
    RANKING_SCORE_MIN,
    RANKING_TAG_CHIP_PREFIX,
    RANKING_TAG_DISCOVERY,
    RANKING_TAG_NEARBY,
    RANKING_TAG_ORDER,
    RANKING_TAG_SAVED,
    RANKING_TAG_TOMORROW,
    RANKING_TAG_TONIGHT,
    RANKING_TAG_WEEKEND,
    RANKING_WEIGHT_CITY,
    RANKING_WEIGHT_CONFIDENCE,
    RANKING_WEIGHT_INTEREST,
    RANKING_WEIGHT_RECENCY,
    RANKING_WEIGHT_RELIABILITY,
)

UTC_ZONE = "UTC"

# The score's precision. Two decimals, like the confidence values it is built from.
SCORE_PRECISION = Decimal("0.01")


@dataclass(frozen=True)
class RankingInputs:
    """The five inputs the Relevance Pulse is built from, as plain data.

    Frozen, because an input that could be mutated after it was scored is an input whose
    meaning has drifted from the score that used it.

    `chip_keys` are the event's own interest-chip keys — the chips the event matched, as
    computed by the candidate read. This module never sees a title: matching text over
    untrusted source content (AD-9) belongs to the layer that owns the content, and
    `domain/` has no idea a render exists.

    `user_chip_keys` are the chips the user picked at onboarding. An empty tuple is the
    skip-everything path, and it scores **0.0** on the interest term — a user who told us
    nothing is neither rewarded nor erased.

    `city_match` is the band the venue's city falls in: the same city, the same country
    but a different city, or elsewhere. `Venue` has no coordinates, so haversine is not
    computable and "nearby" is a band rather than a distance.

    `confidence` is the event's extraction confidence, already in [0, 1].

    `source_reliability` is FR-16's per-source score, already in [0, 1]. **Required, not
    defaulted** — every other field here is required too, "so that a new construction site
    cannot forget one silently". A default of the 0.50 prior would let a construction
    site forget the term and score every card as if its source were unscored, which is an
    inert weight by construction. The caller resolves the prior (a source that has never
    been recomputed) and passes the value in; this module never reads a database.
    """

    interest_overlap: Decimal
    recency: Decimal
    city_match: Decimal
    confidence: Decimal
    source_reliability: Decimal


def _zone(name: str) -> ZoneInfo:
    """The event's own zone.

    An unknown zone falls back to UTC rather than raising, exactly as `domain/event_fit.py`
    does: a score is an *indicator*, and an event whose zone we cannot read should still
    get one. The zone on an `Event` is validated at write time by the ingestion commands,
    so an unknown name here means the data is older or hand-edited — not that the event is
    invalid.
    """
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(UTC_ZONE)


def _clamp(score: Decimal) -> Decimal:
    """The score into [0, 1]. FR-22 clamps before bucket mapping."""
    return max(RANKING_SCORE_MIN, min(RANKING_SCORE_MAX, score))


def interest_overlap(
    *,
    event_chip_keys: tuple[str, ...],
    user_chip_keys: tuple[str, ...],
) -> Decimal:
    """How well the event matches the interests the user actually told us about.

    Normalised by **`MAX_INTEREST_PICKS`**, not by the user's own chip count.

    Dividing by the user's count would make a one-chip user score `1.0` on any match, so a
    narrow interest would beat a broad one — the chip count is not a measure of how well
    anything is known. Dividing by the maximum is what keeps a one-chip match below a
    three-chip match, and it cannot divide by zero.

    A user with **no** chips scores `0.0`. They are not penalised into invisibility — the
    other three terms still score — and they are not handed a free `1.0` for having told
    us nothing.

    The overlap is counted over **distinct** event chips, so an event listing the same
    chip twice cannot claim twice.
    """
    if not user_chip_keys:
        return RANKING_SCORE_MIN

    event_keys = set(event_chip_keys)
    if not event_keys:
        return RANKING_SCORE_MIN

    user_keys = set(user_chip_keys)
    matched = len(event_keys & user_keys)
    if not matched:
        return RANKING_SCORE_MIN

    return _clamp(Decimal(matched) / Decimal(MAX_INTEREST_PICKS))


def recency_band(*, start_time_utc: datetime, now: datetime) -> Decimal:
    """How soon the event starts, as a band.

    The comparison is between two **instants** — the start and `now` — so the band is the
    same whoever reads it. The *day* boundaries that matter for the tags ("tonight") are
    decided in the event's own zone, in `why_this_tags`.

    An event that has already started scores `0.0`: it is not "soon", it is "already".
    """
    until_start = start_time_utc - now
    if until_start <= timedelta(0):
        return RANKING_RECENCY_LATER
    if until_start <= timedelta(days=1):
        return RANKING_RECENCY_WITHIN_DAY
    if until_start <= timedelta(days=3):
        return RANKING_RECENCY_WITHIN_THREE_DAYS
    if until_start <= timedelta(days=7):
        return RANKING_RECENCY_WITHIN_WEEK
    if until_start <= timedelta(days=14):
        return RANKING_RECENCY_WITHIN_FORTNIGHT
    return RANKING_RECENCY_LATER


def city_band(*, event_city: str, event_country: str, user_city: str, user_country: str) -> Decimal:
    """The city band: the same city, the same country, or elsewhere.

    **`Venue` has no coordinates**, so haversine is not computable and FR-5's distance
    curve cannot be evaluated. The brief records this as a named deviation: city equality
    as a band, not a distance.

    The comparison is case-insensitive and whitespace-tolerant, because a venue's city and
    a user's city are typed by two different people and will not agree on capitalisation.
    """
    event_city_key = event_city.strip().casefold()
    user_city_key = user_city.strip().casefold()
    if event_city_key and event_city_key == user_city_key:
        return RANKING_CITY_SAME

    event_country_key = event_country.strip().casefold()
    user_country_key = user_country.strip().casefold()
    if event_country_key and event_country_key == user_country_key:
        return RANKING_CITY_SAME_COUNTRY

    return RANKING_CITY_OTHER


def relevance_score(inputs: RankingInputs) -> Decimal:
    """The Relevance Pulse: the FR-22 formula, as a `Decimal` in [0, 1].

    The five terms and their weights are named constants in `shared/constants.py`, beside
    the confidence gates — the same place AD-8 requires thresholds to live. A test pins
    them there, so a weight change without a PRD amendment fails CI, which is what FR-22
    requires ("the formula and weights are published in the PRD and immutable post-launch").

    **The reliability term is the fifth one** (FR-16's per-source score, at FR-22's
    published weight of 0.25). The module docstring says why it is not an inert weight,
    and why it is not gated on the source's observation count.

    The result is clamped to [0, 1] before it is returned, so a caller never has to clamp
    before mapping it to a bucket.
    """
    score = (
        RANKING_WEIGHT_INTEREST * inputs.interest_overlap
        + RANKING_WEIGHT_RECENCY * inputs.recency
        + RANKING_WEIGHT_CITY * inputs.city_match
        + RANKING_WEIGHT_CONFIDENCE * inputs.confidence
        + RANKING_WEIGHT_RELIABILITY * inputs.source_reliability
    )
    return _clamp(score.quantize(SCORE_PRECISION))


def score_bucket(score: Decimal) -> int:
    """The Confidence Pulse: FR-22's bucket, as an integer 1–5.

    The boundaries are FR-22's, verbatim: ≥0.85 → 5, ≥0.65 → 4, ≥0.45 → 3, ≥0.25 → 2,
    else 1. **No interpolation, never a bar.**

    **On an exact boundary the lower bucket wins** — `0.850` → 4, not 5. That is FR-22's
    and EXPERIENCE.md's rule, and it is why the score is a `Decimal`: a float `0.85` is
    `0.85000000000000002220446...`, which is strictly greater than `Decimal("0.85")` and
    would land the card in the wrong bucket.

    The score is clamped first, so a score above 1.0 is still a 5 and a score below 0.0 is
    still a 1.
    """
    clamped = _clamp(score)
    if clamped > RANKING_BUCKET_5:
        return RANKING_BUCKET_MAX
    if clamped > RANKING_BUCKET_4:
        return 4
    if clamped > RANKING_BUCKET_3:
        return 3
    if clamped > RANKING_BUCKET_2:
        return 2
    return RANKING_BUCKET_MIN


def apply_hysteresis(
    *,
    previous_bucket: int | None,
    previous_score: Decimal | None,
    new_score: Decimal,
) -> int:
    """The bucket, with the no-flicker rule applied (EXPERIENCE.md §4).

    Once a bucket is assigned for an event on a user's local calendar day, it holds for
    the rest of that day unless the raw score moves by **≥0.10**. The comparison is on the
    **absolute** difference: a score that *falls* by enough moves the bucket too, because
    the rule is about the score moving, not about it rising.

    **The function is pure and knows nothing about days.** The caller decides whether a
    previous bucket exists at all: it passes `None` across a day boundary, and that is
    what "across days, hysteresis resets" means in code. Keeping the day arithmetic here
    would put it in a module that has no idea which timezone the user is in.

    `previous_bucket=None` (a fresh composition) maps the new score directly.

    **The threshold is ≥0.10, not ±0.02.** The deprecated
    `ranking-algorithm-transparency-desktop.html` mockup says ±0.02; EXPERIENCE.md §4 says
    ≥0.10 and is the canonical source. The spines-win rule governs, and the deviation is
    recorded in the design doc.
    """
    new_bucket = score_bucket(new_score)

    if previous_bucket is None or previous_score is None:
        return new_bucket

    if abs(_clamp(new_score) - _clamp(previous_score)) < RANKING_HYSTERESIS_DELTA:
        return previous_bucket

    return new_bucket


def _time_tags(*, start_time_utc: datetime, start_time_tz: str, now: datetime) -> list[str]:
    """The time-relative tags, in the **event's own** zone.

    Every comparison here is between two local wall clocks in the event's own zone: the
    event's local start and `now` in that same zone. The local day is the **event's** day,
    not the reader's — which is the whole point of the rule. An event at 23:30 in Berlin
    is "tonight" in Berlin, whatever timezone the reader is in.

    "Tonight" needs the evening, not just the day. An event at 09:00 today is later
    today, and calling it "tonight" would be a lie about the next few hours.

    The weekend is the event's local Saturday or Sunday, and it must be **the one weekend
    in view** — the weekend a reader means by "this weekend". A Saturday three weeks out
    is not it, and a tag that meant "some weekend" would be useless on a card. The rule
    is the same one `domain/event_fit.py` uses, and it compares **dates** rather than ISO
    week numbers, because the week number wraps at the year boundary and a week-number
    comparison would lose a New Year weekend entirely.
    """
    zone = _zone(start_time_tz)
    start_local = start_time_utc.astimezone(zone)
    now_local = now.astimezone(zone)

    tags: list[str] = []
    is_future = start_time_utc > now
    day_delta = (start_local.date() - now_local.date()).days

    if is_future and day_delta == 0 and start_local.hour >= RANKING_EVENING_HOUR:
        tags.append(RANKING_TAG_TONIGHT)
    elif is_future and day_delta == 1:
        tags.append(RANKING_TAG_TOMORROW)

    if is_future and start_local.weekday() >= 5:
        today = now_local.date()
        if today.weekday() == 5:  # Saturday — the weekend under way is today
            weekend_saturday = today
        elif today.weekday() == 6:  # Sunday — the weekend under way started yesterday
            weekend_saturday = today - timedelta(days=1)
        else:  # a weekday — the coming weekend
            weekend_saturday = today + timedelta(days=(5 - today.weekday()) % 7)

        event_date = start_local.date()
        event_saturday = event_date - timedelta(days=(event_date.weekday() - 5) % 7)
        if event_saturday == weekend_saturday:
            tags.append(RANKING_TAG_WEEKEND)

    return tags


def why_this_tags(
    *,
    inputs: RankingInputs,
    event_chip_keys: tuple[str, ...],
    user_chip_keys: tuple[str, ...],
    start_time_utc: datetime,
    start_time_tz: str,
    now: datetime,
    is_saved: bool = False,
    serendipity: bool = False,
) -> tuple[str, ...]:
    """The Why-this Tag keys: at most three, in a fixed order.

    The tags come from **the same inputs the score used**, because AD-10's whole point is
    that the explanation and the decision cannot drift apart. A card tagged "nearby" whose
    score did not match the city would be lying.

    **Slot 3 (`serendipity=True`) shows `discovery`,** and never a chip tag. FR-25 and the
    PRD §3 Glossary require it there: Slot 3's tag is `discovery` or `new-to-you`, never a
    category name. UJ-1's `novel` is stale and does not govern.

    The order is also the **priority**: when more than three tags apply, the first three in
    `RANKING_TAG_ORDER` win. A card that is nearby, tonight and matches a chip shows
    `nearby, tonight, matches_music` — never three chip tags.

    A chip-match tag is `matches_<chip_key>`, e.g. `matches_music` for `arts_culture`. The
    chip key is a slug from `shared.constants.INTEREST_CHIPS`, and it is stable forever
    even if the label changes.
    """
    tags: list[str] = []

    if serendipity:
        tags.append(RANKING_TAG_DISCOVERY)

    if inputs.city_match >= RANKING_CITY_SAME:
        tags.append(RANKING_TAG_NEARBY)

    tags.extend(_time_tags(start_time_utc=start_time_utc, start_time_tz=start_time_tz, now=now))

    if is_saved:
        tags.append(RANKING_TAG_SAVED)

    if not serendipity:
        user_keys = set(user_chip_keys)
        matched = sorted(set(event_chip_keys) & user_keys)
        for chip_key in matched:
            tags.append(f"{RANKING_TAG_CHIP_PREFIX}{chip_key}")

    # The order is fixed, and it is the priority order: the tags are sorted by it and then
    # capped. A tag that appears twice keeps its first position.
    #
    # The chip tags are **not** in `RANKING_TAG_ORDER` — there is one per chip and they are
    # unbounded in number — so they are appended after the fixed tags, in the sorted order
    # of their chip keys. A chip tag therefore never displaces a fixed tag: with three
    # fixed tags and one chip match, the chip tag is the one that falls off the end.
    ordered: list[str] = []
    for tag in RANKING_TAG_ORDER:
        if tag in tags and tag not in ordered:
            ordered.append(tag)
    for tag in tags:
        if tag.startswith(RANKING_TAG_CHIP_PREFIX) and tag not in ordered:
            ordered.append(tag)

    return tuple(ordered[:RANKING_MAX_TAGS])


def score_slot_1(
    *,
    inputs: RankingInputs,
    is_personal_event: bool = False,
) -> Decimal:
    """Slot 1, "must-know" (FR-5, Amendment A-2).

    FR-5: "Personal Events eligible (warm-tone; see FR-19). If no Personal Event is
    eligible within the next 48 hours, falls back to the highest-scoring eligible public
    event in the user's beachhead."

    **This module only scores.** Whether a personal event is *eligible* — whether it
    starts within the next 48 hours, whether the user has opted out of personal events —
    is the composition service's decision, because those are facts about the user's
    calendar and their preferences rather than about the event's score. The service calls
    this function with `is_personal_event=True` only for an event it has already decided
    is eligible.

    The boost is a named constant, so a reader can see exactly what the slot-1 personal
    preference is worth. It is a boost and not a replacement: a personal event that
    matches nothing still has to earn its place on the other three terms.
    """
    score = relevance_score(inputs)
    if is_personal_event:
        score = _clamp(score + RANKING_PERSONAL_EVENT_BOOST)
    return score.quantize(SCORE_PRECISION)


def score_slot_2(*, inputs: RankingInputs) -> Decimal:
    """Slot 2, "nearby" (FR-5, Amendment A-2): the standard score.

    FR-5 writes the slot-2 score as
    `source_reliability × geographic_distance_factor × freshness_factor`.

    **Two of those three terms now have an input, and one does not:**

    - `source_reliability` — FR-16's score, stored on the `Source` and read by the
      candidate read. It enters at FR-22's published weight of 0.25, so the slot's score
      falls when the source's reliability falls.
    - `freshness_factor` — the recency band, which is one of the additive terms the
      standard score now has.
    - `geographic_distance_factor` — **still has no input.** It is a haversine over a city
      centroid that does not exist, because `Venue` has no coordinates. The city *band*
      stands in for it, additively.

    City membership itself is decided by the candidate read, which filters to the user's
    city, so the band here is a genuine term rather than a constant.
    """
    return relevance_score(inputs)


def score_slot_3(*, inputs: RankingInputs) -> Decimal:
    """Slot 3, "serendipity" (FR-5, Amendment A-2): the score with the preference term
    **inverted**.

    FR-5 publishes

    ```
    score = source_reliability × geographic_distance_factor × freshness_factor
          × (1 − normalized_popularity)
    ```

    — an explicit anti-popularity bias, so that Slot 3 is structurally the card the
    user's own signals would not have picked.

    **`normalized_popularity` does not exist here.** There is no engagement, attendance or
    save-count signal anywhere in this codebase, so the published anti-popularity factor
    cannot be evaluated. The intent's decision is that the bias is expressed as an
    **inverted preference term** over the input that does exist, and this docstring says
    so plainly: **this is a deviation from FR-5, and it is not the same quantity.**

    Inverting the interest term is the closest honest analogue. A high interest overlap
    means "your own signals would have picked this", so `1 − overlap` is high for the
    events those signals would *not* have picked. The recency, city and confidence terms
    are left alone: the anti-popularity bias is about *popularity*, and recency is not
    popularity.

    **The reliability term is not inverted, and that is deliberate.** FR-5 *multiplies by*
    `source_reliability`: it is a quality gate, not a popularity term. The only thing
    FR-5 inverts is `(1 − normalized_popularity)`. Inverting the reliability would invert
    a quality signal — it would make Slot 3 structurally prefer the *least* reliable
    sources — which is not what FR-5 says. So the reliability passes through unchanged,
    and Slot 3 still ranks a better source above a worse one.
    """
    inverted = RankingInputs(
        interest_overlap=RANKING_SCORE_MAX - inputs.interest_overlap,
        recency=inputs.recency,
        city_match=inputs.city_match,
        confidence=inputs.confidence,
        source_reliability=inputs.source_reliability,
    )
    return relevance_score(inverted)


__all__ = [
    "SCORE_PRECISION",
    "RankingInputs",
    "apply_hysteresis",
    "city_band",
    "interest_overlap",
    "recency_band",
    "relevance_score",
    "score_bucket",
    "score_slot_1",
    "score_slot_2",
    "score_slot_3",
    "why_this_tags",
]
