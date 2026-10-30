---
id: digest-ranking-domain-design
title: The ranking domain — design
intent: pulse-digest-and-trust
work_item: digest-ranking-domain
status: approved
created: 2026-10-30
---

# Design: The ranking domain (slots, Relevance Pulse, buckets, hysteresis)

## The problem this design solves

FR-22 publishes a formula and **locks its weights**:

```
relevance_score = 0.40 × preference_graph_match
                + 0.25 × source_reliability
                + 0.20 × recency_fit
                + 0.15 × novelty_vs_exploration
```

Two of those four components **have no input in this codebase**:

| Component | Weight | State today |
|---|---|---|
| `preference_graph_match` | 0.40 | `PREFERENCE_GRAPH` is unbuilt (FR-25 deferred). `Interest` chips exist and are read by nothing. |
| `source_reliability` | 0.25 | FR-16 unbuilt. `Source` has no score field. |
| `recency_fit` | 0.20 | **Survivable.** The event's start time and the user's local day exist. |
| `novelty_vs_exploration` | 0.15 | Needs the Preference Graph, and needs `Event.category`, which does not exist. |

FR-5's slot formulas have the same problem, and worse: `Slot 2 = source_reliability × geographic_distance_factor × freshness_factor` has **one** of three factors available (`freshness_factor`), because `Venue` has `city` and `country_code` but **no coordinates** — haversine is not computable.

The intent's rule, from the brief, is that the unavailable terms are **omitted from the formula and named** — "never pinned to constants that would leave a published formula with inert weights". This design does that, and it does it in a way that keeps the *published* promise FR-22 actually makes to a user.

## What FR-22 actually promises

FR-22's testable consequence is not "these four weights are used". It is:

> "a user reading the PRD can compute the Confidence Pulse for any Event given the inputs"

and

> "The formula and weights are published in the PRD and immutable post-launch to honor the 'Trust through transparency' principle."

A formula with a `0.25 × source_reliability` term where `source_reliability` is always `0` is a formula whose published weights are **inert** — the user computes 0.40 + 0.20 and gets 0.60, a different number from the one shown. That is a *worse* trust failure than a reduced formula, because it is a formula that is arithmetically checkable and still wrong.

So: the formula is **reduced to the inputs that exist**, the reduction is **documented in the module docstring**, and the surviving weights are **renormalised** so the score still occupies [0, 1] and the published bucket boundaries still mean what they say.

## D1 — The surviving inputs

Four inputs, all of which exist today and all of which a user can read off the card:

| Input | Source | Normalisation |
|---|---|---|
| **interest overlap** | `Interest.chip_key` vs. the event's chip keys | `overlap / max(1, min(len(chips), MAX_INTEREST_PICKS))` → [0, 1] |
| **recency** | `Event.start_time_utc` vs. `now` | band → [0, 1] |
| **confidence** | `Event.extraction_confidence` | already [0, 1] |
| **city match** | `Venue.city` vs. the user's home city | band → [0, 1] |

**The event's chip keys.** `Event` has no category field, and the brief says so: "category tags / Jaccard < 0.3 — `Event` has no category field → **Interest-chip overlap** from the 10 fixed chips, which is what the user actually told us."

But the event must be matched to a chip somehow, or the overlap is always zero. The matching is by **the event's own text against the chip's keyword set**, and it is done at the **candidate-read** layer (ingestion), not in `domain/`. `domain/` receives the already-computed chip keys as plain data.

**D1a — Where the event→chip mapping lives.** The chips are the 10 fixed slugs in `shared.constants.INTEREST_CHIPS`. A chip's keywords are a small fixed noun set (`music` for `arts_culture`, `tech` for `tech_meetups`, …). Matching an event title against them is a **text concern over untrusted source content** (AD-9), and it belongs next to the parsers, not in the pure ranking core. The candidate read returns `chip_keys: tuple[str, ...]` per event; `domain/ranking.py` receives it as plain data and never touches a title.

This is the same discipline as Event Fit: the score is computed from *facts the caller supplies*, and the facts are supplied by a layer that knows where they came from.

**D1b — The city band, not a distance.** `Venue` has no coordinates. The brief is explicit: "**City equality**, as a band, not a distance." The bands:

- same city → `1.0`
- same country, different city → `0.5`
- different country → `0.0`

**D1c — The recency band.** The event's start, relative to `now`, in the **event's own IANA zone** (AD-6, and the rule `domain/event_fit.py` is built around):

- starts within 24 hours → `1.0`
- within 3 days → `0.75`
- within 7 days → `0.5`
- within 14 days → `0.25`
- beyond → `0.0`

The bands are a **day-boundary decision in the event's zone**, exactly like Event Fit's "tonight". A 23:30 Friday event in `America/New_York` is "tonight" on Friday, not Saturday.

## D2 — The formula and the weights

Four surviving inputs, four weights. The published FR-22 weights are **redistributed proportionally** over the surviving terms, and the total is renormalised to 1.0:

| Surviving input | Weight | Rationale |
|---|---|---|
| `interest_overlap` | **0.45** | FR-22's `preference_graph_match` was 0.40 and is the *largest* published term. The chips are what the user actually told us, so they inherit the preference term's rank. |
| `recency` | **0.25** | FR-22's `recency_fit` was 0.20. It is the term that survives most directly. |
| `city_match` | **0.20** | Stands in for FR-5's `geographic_distance_factor`, which was a *multiplier* on the slot scores. Here it is an *additive* term, because a multiplicative band would zero out every event outside the user's city. |
| `confidence` | **0.10** | The event's facts are known to this degree. It is a *trust* input, not a *relevance* input — hence the smallest share. |

`relevance_score = 0.45×interest_overlap + 0.25×recency + 0.20×city_match + 0.10×confidence`

**Why the preference term is 0.45 and not 0.40.** The published `preference_graph_match` weight is 0.40. The chip overlap *is* the preference signal we have — it is the Preference Graph's only surviving trace. Giving it the other surviving terms' slack keeps the relative emphasis the PRD published (preference > recency > reliability) while acknowledging that reliability is gone rather than zeroed.

**Why `city_match` is additive, not multiplicative.** FR-5 multiplies by a distance factor, so an event in another city scores *zero* and never reaches Slot 2. But the brief requires Slot 2 to be "the highest-scoring eligible public event **in the user's city**" — city membership is decided by the *candidate read*, not by the score. Once the read has filtered to the user's city, multiplying by a city factor would be multiplying by a constant, which is exactly the "inert weight" the brief forbids. Making it additive keeps it a real term: a city-matching event outranks an out-of-city one, without either being excluded by arithmetic.

**Why `confidence` is a term at all.** FR-22 says the Confidence Pulse measures "the AI's certainty about relevance (**not just** trust in the source)". Extraction confidence is the one measure of "how well do we know this event's facts" that exists, and it is the same number the eligibility gates use. A card whose facts were scraped at 0.55 confidence is a card more likely to be wrong about its own time and place — and the user is being asked to trust it.

## D3 — The cold-start path, and ADR-0007

FR-5 gates all personalized weighting on "the signal threshold in the deferred ADR-0007", which **does not exist**. The brief says: "This intent ships **the cold-start path only**, and that is a statement about the sources, not a shortcut."

So the formula above **is** the cold-start formula. There is no personalised branch and no threshold check, because there is nothing to check. This is recorded as a named deviation, and the module docstring says so — a reader must be able to tell that the absence is deliberate.

**The interest-overlap normalisation.** FR-1 allows 0–3 chips. A user who skipped onboarding has **zero** chips. Dividing by `len(chips)` would divide by zero, so:

```
interest_overlap = overlap / MAX_INTEREST_PICKS   if the user has chips
                 = 0.0                            if the user has none
```

Dividing by the **maximum** rather than by the user's own count is deliberate: a user who picked one chip has expressed a *narrow* interest, and their single match should not outrank a user with three matches. Dividing by the count would make one-chip users score 1.0 on any match. The chip count is not a confidence measure, and FR-1 caps it at 3 for exactly this reason.

A user with **no** chips scores `0.0` on this term — they are not penalised into invisibility (the other three terms still score), and they are not handed a free `1.0` for having told us nothing.

## D4 — Slots, and the inverted term

**Slot 1 (must-know).** The module **scores**; the **caller** decides the personal-event fallback. `score_slot_1` is the standard score, plus a **personal-event boost** for an event the user created. The boost is a named constant, not a fudge: a personal event inside 48 hours is the one thing on the card that is *definitely* theirs and *definitely* soon.

**Slot 2 (nearby).** The standard score.

**Slot 3 (serendipity).** The standard score **with the preference term inverted**:

```
serendipity_score = 0.45×(1 − interest_overlap) + 0.25×recency + 0.20×city_match + 0.10×confidence
```

This is the **published anti-popularity bias**, expressed over the input that exists. FR-5 writes `(1 − normalized_popularity)`; `normalized_popularity` does not exist (no engagement, save-count or attendance signal anywhere), and FR-16's `source_reliability` is likewise absent. The brief instructs: "Slot 3's anti-popularity bias is expressed as an inverted *preference* term instead."

**This is a deviation from FR-5 and must be legible as one.** The module docstring states, in the slot-3 function itself, that the inverted term stands in for `(1 − normalized_popularity)` and that the two are not the same quantity.

**Slot 3's tag rule.** Slot 3's Why-this Tag is `discovery` or `new-to-you` — **never a category name** (Glossary §3 / FR-25). UJ-1's `novel` is stale and does not govern (the brief's source-conflict list, item 4).

## D5 — Why-this Tags

Tags are **keys, not display strings** — `domain/` has no idea a render exists. The presentation edge renders them (EXPERIENCE.md: "the server states facts, the client speaks the user's language").

Derived from **the same inputs the score used**, because AD-10's whole point is that the explanation and the decision cannot drift apart. If the tag said "nearby" and the score had not matched the city, the card would be lying.

The tag set, in a **fixed order**:

| Key | Fires when | Slot 3? |
|---|---|---|
| `nearby` | city band is "same city" | no — slot 3 shows `discovery` instead |
| `tonight` | event starts later today, in the event's own zone, at or after `17:00` | yes |
| `tomorrow` | event starts on the next local day, in the event's own zone | yes |
| `weekend` | event starts on the coming (or current) weekend, in the event's own zone | yes |
| `saved` | the user saved this event | yes |
| `matches_<chip>` | the event matched one of the user's chips | **no** — slot 3 shows `discovery` |
| `discovery` | — | **slot 3 only**, replaces the chip tag |

**At most 3**, and the cap is applied by **priority**, not by insertion order: the first tag that applies in the fixed order wins the remaining slots. So a card that is nearby, tonight and matches a chip shows `nearby, tonight, matches_music` — never three chip tags.

**Slot 3's `discovery` tag is mandatory.** FR-25 and the Glossary require it; it is not merely one of the tags. So slot 3's tag list always begins with `discovery`.

**The separator is undecided in the sources** (the brief says so: DESIGN.md says middle dots, EXPERIENCE.md §3 says commas). This design decides the **storage** question — the tags are stored as an ordered tuple of keys, and the separator is a **presentation** decision that belongs to the frontend. The accessible reading is settled by EXPERIENCE.md §8 ("announced as comma-separated text"), so the frontend will render commas and the screen reader reads commas. The visual separator is recorded as a frontend decision in the pulse-card work item.

## D6 — Buckets

FR-22's boundaries, **verbatim and exact**:

```
≥ 0.85 → 5
≥ 0.65 → 4
≥ 0.45 → 3
≥ 0.25 → 2
else   → 1
```

**On an exact boundary the lower bucket wins.** `0.850 → 4`, not 5. This is FR-22's and EXPERIENCE.md's rule: "≥0.85 means **strictly greater than** 0.85; 0.85 itself → 4 dots."

This is why the score is a `Decimal` and never a float. `Decimal("0.850")` is exactly 0.850 and compares exactly against the constant; `0.85` as a binary float is `0.85000000000000002220446...`, which compares **greater** than `Decimal("0.85")` under Python's exact decimal comparison and lands the card in the wrong bucket. `domain/confidence.py` already refuses floats for the same reason.

The score is **clamped to [0.0, 1.0]** before mapping.

## D7 — Hysteresis

EXPERIENCE.md §4, exactly:

> once a bucket is assigned at Pulse composition time for a given event on a given calendar day (in the user's local timezone), the event stays in that bucket for the remainder of the calendar day. The bucket recomputes only if the raw score changes by **≥0.10** within the same day. Across days, hysteresis resets.

The worked example is pinned as a test: `0.83 → 4`; a same-day re-score to `0.86` (Δ0.03) stays `4`; a re-score to `0.97` (Δ0.14) moves to `5`.

**The function is pure:** `(previous_bucket, previous_score, new_score) → bucket`. It does not know what day it is; the **caller** decides whether to pass a previous bucket at all, and it passes `None` across a day boundary. That is what "hysteresis resets across days" means in code, and it keeps the day arithmetic (the part that is easy to get wrong) in the composition service, where the user's timezone lives.

**The threshold is ≥0.10**, not the ±0.02 in `ranking-algorithm-transparency-desktop.html`. That mockup is marked deprecated; EXPERIENCE.md is the canonical source and the spines-win rule governs. **Recorded as a deviation.**

The comparison is on the **absolute** difference. A score that *falls* by ≥0.10 also moves the bucket — the rule is about the raw score moving, not about it rising.

## D8 — Day boundaries

Three different local days, each computed in its own zone, and conflating them is the single easiest way to get this wrong:

| Day | Zone | Used for |
|---|---|---|
| the **user's** local day | the user's digest timezone | hysteresis reset, and the digest's `local_date` |
| the **event's** local day | the event's `start_time_tz` | "tonight", "tomorrow", "weekend" |
| the **user's** local day, in the **event's** zone | for cross-zone comparisons | — (not used; see D8a) |

**D8a — "Tonight" is the event's day, not the user's.** An event at 23:30 local in Berlin is "tonight" in Berlin. The user's timezone is irrelevant to whether an event is tonight — it is a fact about the event and the wall clock where the event happens. Event Fit already made this call ("The local day is the event's day, not the reader's"), and the brief confirms it: "the event's 'tonight'-style proximity comes from the event's own zone."

**D8b — DST.** Both day boundaries move when the zone's offset moves. The tests pin a transition in each zone:

- `America/New_York`, 2026-03-08 (spring forward): an event at 23:30 local on the 7th is "tonight" on the 7th; at 23:30 local on the 8th is "tonight" on the 8th (the day is 23 hours long).
- `Europe/Berlin`, 2026-10-25 (fall back): an event at 23:30 local on the 25th is "tonight" on the 25th; the day is 25 hours long, and the *next* day's events are 25 hours away, not 24.

## D9 — What is persisted, and what is derived

The **score** and the **bucket** are **both persisted** on the composition row (AD-10: explanations are never recomputed at render; EXPERIENCE.md: "no persistent bucket is stored between days" — meaning there is no separate carry-over table, not that the bucket is recomputed).

The bucket is written at composition time from the score, through the hysteresis function, using the **previous day's composition row** for the same `(user, event)` as the "previous" input. The previous row is found by an indexed lookup — which is exactly why these rows must outlive their day.

**A re-composition for the same `(user, local_date)` is not an update.** The composition service treats an existing digest as already done and returns it (FR-30).

## D10 — The tie-break key

Determinism is a property of the **ordering**, not of the scorer. Two events with identical scores must break on a **stated, stable key**.

**The key is `(score DESC, start_time_utc ASC, event_id ASC)`.** The `event_id` tiebreak makes the order total — `event_id` is a UUIDv7, so it is time-ordered and unique, and no two candidates can compare equal on all three. Postgres does not promise row order without an explicit `ORDER BY`, and "whatever the queryset returned" is not a tie-break.

## D11 — Module surface

`backend/domain/ranking.py`:

| Function | Purpose |
|---|---|
| `relevance_score(...)` | The FR-22 reduced formula → `Decimal` in [0, 1]. |
| `score_bucket(score)` | FR-22's exact boundaries → int 1–5. |
| `apply_hysteresis(previous_bucket, previous_score, new_score)` | The pure hysteresis rule. |
| `score_slot_1(...)` / `score_slot_2(...)` / `score_slot_3(...)` | A-2's three slots. |
| `why_this_tags(...)` | The ordered tag keys, ≤ 3. |

Every function that needs the current time takes `now` explicitly. No clock read, no randomness.

**The weights live in `shared/constants.py`**, beside the confidence gates — the same place AD-8 requires thresholds to live, and the same place `domain/event_fit.py`'s bands live. A test reads them from there and pins them, the way `tests/shared/test_constants.py` pins each confidence threshold to its gate band: FR-22 says a weight change without a PRD amendment is a CI-level test failure, and a pinned constant is how a weight change fails CI.

## Decisions summary

| # | Decision | Why |
|---|---|---|
| D1 | Four inputs: interest overlap, recency, confidence, city band | The only ones that exist; each readable by the user |
| D1a | Event→chip matching happens in the candidate read, not in `domain/` | Text over untrusted content (AD-9); `domain/` has no idea a title exists |
| D2 | Weights 0.45 / 0.25 / 0.20 / 0.10, renormalised to 1.0 | Keeps FR-22's relative emphasis without inert terms |
| D2 | `city_match` additive, not multiplicative | FR-5's multiplier would zero out every non-local event |
| D3 | Cold-start only; no ADR-0007 branch | ADR-0007 does not exist; recorded, not silently assumed |
| D3 | Interest normalised by `MAX_INTEREST_PICKS`, 0 chips → 0.0 | No division by zero; a one-chip user does not outrank a three-chip user |
| D4 | Slot 3 inverts the **preference** term | The published anti-popularity bias, over the input that exists; a named deviation |
| D5 | Tags are keys, capped at 3 by fixed-order priority | The explanation is built from the score's own inputs |
| D5 | Slot 3's tag is `discovery`, mandatory | FR-25 / Glossary §3 |
| D6 | Buckets verbatim; exact boundary takes the **lower** bucket | FR-22 and EXPERIENCE.md, verbatim |
| D6 | `Decimal`, never float | A float `0.85` is not `Decimal("0.85")` |
| D7 | Hysteresis threshold ≥0.10; the mockup's ±0.02 does not govern | EXPERIENCE.md is canonical; recorded deviation |
| D7 | The function is pure; the caller passes `None` across a day boundary | Keeps the day arithmetic where the timezone lives |
| D8 | "Tonight" is the **event's** day, in the event's own zone | Event Fit's rule; the brief confirms it |
| D9 | Score **and** bucket both persisted on the composition | AD-10 — never recomputed at render |
| D10 | Tie-break: `(score DESC, start_time_utc ASC, event_id ASC)` | A total order; Postgres does not promise row order |
