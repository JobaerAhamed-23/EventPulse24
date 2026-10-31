# Design: The composition command (slots, determinism, the empty state)

**Work item**: `digest-composition-service`
**Intent**: `pulse-digest-and-trust`
**Mode**: validate
**Date**: 2026-10-30

---

## The shape of the problem

`digest-candidate-reads` produced two candidate pools on two sides of the AD-3 wall.
`digest-ranking-domain` produced the scorer. `digest-composition-models` produced the
rows. This item is the thing that joins them: it reads the candidates, scores them,
assigns A-2's three slots, and writes one `PULSE_DIGEST` with its
`DIGEST_COMPOSITION` rows.

It is the **only** writer of those rows (AD-16), it runs in the **worker** and never in
a request (AD-11), and it takes an explicit `actor` and an explicit `now`.

### The one thing that makes this item different from the last three

Every item so far has been *local*. The ranking domain is pure. The models are rows.
The reads are queries. This item is where the pieces meet, and where three separate
failure modes show up at once:

1. **Determinism.** Two runs over the same candidates must produce identical rows.
   The domain is deterministic; the *ordering* is not, unless this item makes it so.
2. **The empty state.** "No pulse for today" is a real digest with zero cards, and
   its trigger has two independent halves that must not be conflated.
3. **The transaction.** AD-3 forbids a transaction spanning both schemas, so the shape
   is "read the catalog outside, write the personal side atomically inside" — and the
   window between the two is a real window.

---

## D1 — The service is one named command, and it takes the candidate pool as *inputs*

**Decision.** `compose_digest(*, user_id, actor, now) -> DigestCompositionResult` in
`apps/personalization/services/digest_composition.py`.

**Why the signature has no pool parameter.** The command reads the candidates itself.
A `candidates=` parameter would let a caller compose a digest from a pool the command
did not read — which is exactly the "the card and the score can drift apart" failure
AD-10 exists to prevent. The command owns its inputs.

**Why it is not a class.** Every other service in this package is a module of
functions, and the "one named command that owns its validation and its audit-log write"
rule (AD-5) is a function-level rule here.

**Why `actor` is explicit.** AD-11: the composition runs in the worker, so the actor
is a **system** actor — `Actor.system("digest_composition")`. The caller passes it in,
so the composition service itself never decides who it is acting as, and a test can
pass a user actor to check the audit row's shape.

**Why `now` is explicit.** Everything in this codebase takes `now` explicitly; no
module reads the clock. `now` is the reference instant for scoring, for the local
date, and for `composed_at`.

### The result

```python
@dataclass(frozen=True)
class DigestCompositionResult:
    digest_id: UUID
    user_id: UUID
    local_date: date
    timezone: str
    is_empty: bool
    compositions: tuple[DigestCompositionRow, ...]
    created: bool   # False when this was a re-run that returned the existing digest
```

`created` is the difference between "composed" and "returned what was already there",
and it is what the scheduling job's log line says.

---

## D2 — The local date is the user's, in their stored zone, and it is the **day** not the instant

**Decision.** `local_date = now.astimezone(ZoneInfo(preference.timezone)).date()`, and
`timezone = preference.timezone`.

**Where the zone comes from.** `DigestPreference.timezone` — the same row that holds
the delivery time and the city. There is **no timezone on the identity `User`**
(`apps/identity/models.py` has only `email`, `is_staff`, `is_active`, `date_joined`),
and `apps.personalization` may not import `apps.identity.models` (AD-2) anyway. So the
zone is the preference's, and the preference is the natural home: it is the row that
already answers "when and where does this user's digest live".

**What happens when there is no preference at all.** A user who has never been through
onboarding has no `DigestPreference`, so there is no zone and no city. The fallback is
`DEFAULT_DIGEST_TIMEZONE` (`"UTC"`) — the same constant onboarding uses when a user
skips step 3. A user with no preference gets a UTC-local digest, and the digest says
nothing about a city, because there is no city.

**Why the zone is stored on the digest row too.** `PulseDigest.timezone` records the
zone the local date was computed in. If the user moves, their old digests still say
which day they were for — `local_date` alone would be ambiguous across a move.

### The DST case

The local date is computed by **converting an instant into a zone and taking its
date** — never by adding 24 hours, and never by computing a "day number" in UTC. That
is what makes the DST cases fall out correctly:

- **Spring forward.** In `America/New_York`, 2026-03-08 02:00–03:00 does not exist. An
  instant of `2026-03-08T07:30Z` is `2026-03-08 03:30 EDT` — the local date is the
  8th. No arithmetic is involved, so nothing special happens.
- **Fall back.** In `America/New_York`, 2026-11-01 has two 01:00s. An instant of
  `2026-11-01T05:30Z` is `2026-11-01 01:30 EDT` and `2026-11-01T06:30Z` is
  `2026-11-01 01:30 EST` — the same wall clock, two hours apart, **the same local
  date**. So a user in New York gets one digest for the 1st, not two, and the second
  run is the no-op it should be.

**The test.** Two instants on either side of the fall-back transition, one hour apart
in UTC, produce the **same** `local_date` and the same digest id — the second call
returns the existing digest.

**The other direction.** A user in `Asia/Tokyo` at `2026-10-30T23:00Z` is at
`2026-11-01 08:00 JST` — the **1st** locally, while a user in `America/Los_Angeles` at
the same instant is at `2026-10-30 16:00 PDT` — still the **30th**. Two users, one
instant, two different digests. That is AD-6's "the user's day, not the server's".

---

## D3 — The tie-break is explicit, and it is `(-score, start_time_utc, event_id)`

**Decision.** Every ordering over candidates is by **the key**:

```python
(-score, start_time_utc, event_id)
```

with the score negated so that the ordering is ascending-by-best.

**Why this key and not another.** Three requirements, in order:

1. **The score must come first.** It is the ranking, and FR-22 says the score is the
   ranking. Any other primary key would be a different ranking.
2. **The start time breaks a score tie, earliest first.** Two events with identical
   scores are not equally good — the sooner one is more actionable, and recency is
   already a term in the score, so a score tie means recency did not separate them.
   "Soonest first" is also the order the digest's cards read in.
3. **The event id breaks a start-time tie.** The id is a UUIDv7, so it is
   **time-ordered and unique**. Two events cannot share an id, so the key is a **total
   order** — there is never a residual tie, and the ordering never depends on the
   order the rows happened to come back from the database.

**Why not the database order.** Postgres does not promise an order without an `ORDER
BY`, and an `ORDER BY` on a `uuid` column in a text collation is not the order the
digest wants. The work item says it: "Determinism is a property of the ordering, not
of the scorer."

**Why the id and not the slug.** The slug is not unique (two events may share a
slug), and it is derived text. The id is unique, stable, and total.

**Why the negation.** The key is stated in the docstring as an *ascending* key, so
"highest score first" needs a negation. The alternative — sorting with a `reverse`
key function on the score and not on the others — is the same thing but harder to
read, because `reverse=True` reverses *every* component.

**The key is applied to the *composed* score, not the raw score.** Slot 1's personal
event carries the boost (`RANKING_PERSONAL_EVENT_BOOST`), so its composed score is
what the ordering uses. Ordering on the raw score and then boosting would put a
personal event below a public event it outscores.

---

## D4 — The three slots, and what "no duplicate `event_id`" means

**Decision.** Slot 1 is filled first, then slot 2, then slot 3, each from the
candidates **not already used**, so the three are distinct by construction.

### Slot 1 — must-know

> *an eligible personal event within 48 hours if one exists and the user has not opted
> out; otherwise the highest-scoring eligible public event*

The implementation:

1. If the user has **not** opted out, take the personal candidates (the read already
   bounded them to the 48-hour window, inclusively at both ends) and pick the best by
   the D3 key, scored with `score_slot_1(inputs=inputs, is_personal_event=True)`.
2. Otherwise — no personal candidate, or the opt-out — take the best public candidate
   by the D3 key, scored with `score_slot_1(inputs=inputs, is_personal_event=False)`.

**The scorers are keyword-only.** `domain/ranking.py` declares `score_slot_1`,
`score_slot_2` and `score_slot_3` with `inputs` as a keyword argument, and they are
called that way. (The implementation first called them positionally, which raised
`TypeError` on every composition — see the review report.)

**The personal event wins Slot 1 even when a public event scores higher.** FR-5 says
"Personal Events eligible (warm-tone)" *first*, and the fallback is conditional on
"if no Personal Event is eligible". So the personal event is not competing with the
public event for Slot 1 — it *is* Slot 1 when there is one. The public event takes
Slot 1 only when there is no eligible personal event.

**This is worth being explicit about, because it is the opposite of what a
"highest-scoring candidate wins" implementation would do.** A personal event in the
48-hour window goes in Slot 1 even if a public event would have outscored it. That is
the point of the slot: "the thing you must know" is the thing on your own calendar.

**What the personal event's score is.** `score_slot_1` with
`is_personal_event=True` — the boost applies. The boost is `0.20`, so a personal
event with an otherwise mediocre score still competes. The score is stored, so the
card can show it.

**What the personal event's tags are.** `why_this_tags` with the personal event's own
zone and start time. A personal event has a `start_time_tz` (the zone the user entered
it in), so the "tonight" tag is computed in that zone.

**A personal event has no source badge and no event version.** The model's check
constraint `digest_composition_kind_shape_ck` says so: `event_kind="personal"` means
`event_version IS NULL` and `source_badge IS NULL`.

### Slot 2 — nearby

The highest-scoring **remaining** public candidate, scored with `score_slot_2`
(which is the plain relevance score).

### Slot 3 — serendipity

The highest scorer under the **inverted** preference term — `score_slot_3` — among the
**remaining** candidates.

**Slot 3's candidates are the same pool as Slot 2's.** FR-5's serendipity slot is "the
highest scorer under the inverted preference term", and the inversion happens
*inside* `score_slot_3`. So the service does not build a separate "unpopular" pool; it
scores the remaining candidates with the inverted function and takes the best.

**Why the remaining set, and not the whole pool.** FR-5: "a Pulse Card in the digest is
not a duplicate of another". The model's `digest_composition_digest_event_uq` is the
backstop, but the service must not rely on an `IntegrityError` to notice — so the
duplicates are removed *before* the write, by construction.

**The personal event in Slot 3?** No. Slot 3 is serendipity over public events. A
personal event is the user's own agenda; putting it in a "discovery" slot would be
nonsense — the tag is `discovery` and the user already knows about it. So Slot 3 draws
from the public candidates only, after Slot 1 and Slot 2 have taken theirs.

---

## D5 — The empty state is a real digest with zero rows, and its trigger has two independent halves

**Decision.** The digest is written with `is_empty=True` and **zero**
`DigestComposition` rows when **both** hold:

- there is **no qualifying public event**, **and**
- there is **no eligible personal event**.

**Both halves are tested separately**, because each half alone is not enough. A user
with no public events but three personal events this week gets a digest with a card,
not an empty one. A user with public events but no personal events gets cards, not an
empty digest. Only the conjunction is empty.

**The opt-out interacts with the personal half.** An opted-out user's personal events
are not eligible, so an opted-out user with no public events gets the empty state. That
is the honest answer: they asked not to see their own events, and there is nothing else
to show.

**Why `is_empty` is stored and not derived.** The model already decided this (D1 of the
models design). The reader must be able to tell "a deliberate empty digest" from "a
composition that never ran" without counting children — and it must be able to tell
without a second query.

**Why the empty digest is still a `PulseDigest` row.** FR-8's empty state is a *fact
the user is shown*. "Nothing near you today" and "we never composed for you" are
different states, and a row with zero children is what distinguishes them.

---

## D6 — The fewer-than-3 case: **show what there is**, and say so

**The problem, stated as the work item states it.** FR-5 says "exactly 3 cards on a
standard day. Exception: a 'No pulse for today' empty state". A two-card day is
neither. The design must choose: pad from a relaxed pool, show two cards, or fall to
the empty state.

**Decision: show what there is.** A digest with two cards is composed with two
compositions; a digest with one card, one; a digest with none, the empty state.

**Why not pad.** Padding from a "relaxed pool" means relaxing a gate to manufacture a
third card. Which gate? The staleness bound (FR-14) says a stale event is not surfaced
in a fresh digest; the confidence gates say a low-confidence event is never published
to a digest. Relaxing either to fill a slot would be **publishing a card the rules say
must not be published**, and the user would have no way to know the card was filler.

There is also nowhere to relax *to*. The candidate pool is already every eligible
event; "relaxing" it means going back to ineligible events. The gates are the
definition of eligibility, not a filter applied to a larger pool.

**Why not fall to the empty state.** A user with two excellent events in their city and
a two-card digest would see "No pulse for today" — a **lie about their own city**. The
empty state means "nothing is happening near you". Two events *is* something happening
near you.

**Why this is not "exactly 3 or nothing".** FR-5's "exactly 3" is the description of a
**standard day** — a day with a normal catalog. The exception clause names the empty
state, and the empty state is for a day with *nothing*, not a day with *something but
less*. A two-card day is a day with something.

**What the design owes the reader.** The result carries the composition count, so the
read API can decide what to say about a short digest — and that decision is
`digest-read-api`'s, not this item's. This item's job is to compose honestly and let
the count be visible.

**The trade, stated plainly.** A short digest does not satisfy FR-5's "exactly 3"
literally. The alternative readings each break something else that FR-5 states, and
this one breaks the least: it never publishes a card the rules forbid, and it never
tells a user there is nothing happening when there is.

---

## D7 — The chip-key gap: the interest term is inert until the candidate read supplies chips

**This is the most important finding in this design, and it is a gap, not a choice.**

`domain/ranking.py` scores `0.45 × interest_overlap`. The `interest_overlap` term
needs **two** tuples: the user's chip keys (available — `Interest.chip_key`) and the
**event's** chip keys (**do not exist**). `Event` has no category field; no candidate
read carries `chip_keys`; `shared/constants.py`'s `INTEREST_CHIPS` is a list of
`(key, label)` pairs with **no keyword sets**.

The ranking domain's own docstring says the event's chips are "as computed by the
candidate read", and the ranking design doc says the matching "is done at the
candidate-read layer (ingestion), not in `domain/`". **That matching was never
built.** `digest-candidate-reads` did not build it, because its acceptance criteria
never mentioned chips.

### What this breaks, exactly

With `event_chip_keys = ()`:

- `interest_overlap` is `0.0` for every candidate;
- every score is `0.25 × recency + 0.20 × city + 0.10 × confidence`, whose maximum is
  `0.55` — so **the score can never reach bucket 4 or 5**;
- `score_slot_3` inverts `1.0 − 0.0 = 1.0`, so **Slot 3's score equals Slot 2's** for
  every candidate, and the "inverted preference" does nothing;
- no `matches_<chip>` tag is ever produced.

### The decision: build the matching here, as a pure function in the ingestion layer

**Decision.** The event→chip matching is a **pure text→keys function**, and it lives
in `apps/ingestion/services/chip_matching.py`, called from the **catalog's** candidate
read.

**Why here and not in `domain/`.** AD-9 is explicit that matching text over untrusted
source content is not a render concern and belongs to the layer that owns the content.
The `domain/` package is "stdlib only, pure" and has "no idea a render exists"; giving
it a keyword table over event titles would make the pure domain depend on a content
policy. `domain/event_fit.py` set the precedent: it refused to invent a "Free" tag
rather than guess a category.

**Why it is a pure function and not a stored column.** A stored `chip_keys` column on
`Event` would need a migration, a write-time computation, and a backfill for every
existing event — and it would be *wrong* the moment the keyword table changed. The
matching is a function of the event's text and a table that is small and stable, so
computing it at read time is both simpler and more correct.

**Why it is not part of the composition service.** The composition service is in
`apps.personalization`, and it may not import `apps.ingestion.models` (AD-2). The
keyword matching over event titles is ingestion's business — ingestion owns the text.
So the candidate read computes the chips and hands them over as plain data, and the
composition service never sees a title.

### The keyword table

A **new named constant** in `shared/constants.py`: `INTEREST_CHIP_KEYWORDS`, mapping
each chip key to a tuple of keywords. `shared/constants.py` is where thresholds live
(AD-8), and it is stdlib-only so both `domain/` and the apps may read it.

The table is **deliberately small and hand-written**: four to eight keywords per chip,
chosen to be unambiguous. It is not a classifier and does not pretend to be one. A
keyword that would match too broadly is worse than no keyword, because a false match
inflates the interest term and puts a card in a category the user did not ask about.

**The matching rule.** The event's **title and description** are lowercased and
tokenised, and a chip matches when any of its keywords appears in the text as a
**whole word**. Whole-word matching, not substring: "art" must not match "start", and
"market" must not match "marketing".

**Hyphens and apostrophes are normalised on *both* sides.** A word is tokenised with its
hyphens and apostrophes intact, and each token also contributes its hyphen- and
apostrophe-free parts — so "Story-Time" contributes `story-time`, `story` and
`storytime`, and a keyword of `storytime` matches it. The keyword side is normalised
the same way, so a keyword of "story-time" and a text of "storytime" also match.

**This rule is the one the module's docstring promised and the first implementation
did not deliver** — the tokeniser kept the hyphen *inside* the token, so the two
spellings of the same word did not match each other. It is now pinned by
`test_the_whole_word_boundary_respects_apostrophes_and_hyphens`. See the review report.

**A keyword that contains a space is a phrase**, and is matched as a phrase against the
text: "craft fair" matches "Saturday Craft Fair" and not "Fair of Crafts".

**Why the title and the description.** The title is the event's own name ("Brooklyn
Tech Meetup") and the description is the body. Both are the event's own text, both are
already parser-stripped plain text on the model (`Event.description` — "parser-stripped
plain text, never HTML"), and neither is raw HTML.

**Why not the venue name.** "Brooklyn Brewery" would match a food chip on the word
"Brooklyn" if the keywords were loose, and a venue named "The Tech Bar" would make
every event there a tech event. The venue is where the event happens; the title and
description are what the event *is*.

**Where it is applied.** `PublicEventCandidate` gains a `chip_keys: tuple[str, ...]`
field, computed in `catalog_read.list_public_candidates` from the event's title and
description.

### What it costs and what it buys

It buys: the interest term works, the score can reach buckets 4 and 5, Slot 3's
inversion is real, and the `matches_<chip>` tags appear.

It costs: a keyword table that is a judgment call, and a match rate that is a
heuristic. Both are stated in the module docstring, and the table is one constant
away from being edited when the labels change.

**The alternative, rejected.** Passing `event_chip_keys=()` and accepting an inert
weight would violate the ranking domain's own stated principle: "A term pinned to a
constant is an *inert weight*: the published formula would stay arithmetically
checkable and still produce a different number from the one on the card, which is a
worse trust failure than a reduced formula because it looks verifiable." The interest
term is the **largest** weight in the formula; leaving it inert is the worst version of
that failure.

### The scope note

This is **an addition to the item's stated scope**, and it is a deliberate one. The
work item's acceptance criteria require "Slot 3 — the highest scorer under the
**inverted** preference term" and "a user with **no interest chips at all**" — and
without event-side chips, the inverted term is provably identical to the plain term,
so the acceptance criteria cannot be met without this. The change is confined to the
ingestion candidate read and one new leaf module; the composition service's own logic
is unchanged by it.

---

## D8 — The candidate pool: personal events, saves, and public events, and what each is for

**Decision.** The command reads three pools.

| Pool | Source | What it is for |
|---|---|---|
| Public candidates | `catalog_read.list_public_candidates(now, city=...)` | Slots 1–3 |
| Personal candidates | `digest_candidates.list_personal_candidates(user_id, now)` | Slot 1 |
| Saved candidates | `digest_candidates.list_saved_candidates(user_id, now)` | the `saved` Why-this tag |

### The city filter

The public pool is read with `city=<the user's stored city>`. When the user has **no**
city (`NULL`, meaning "we do not know where this user is"), the read is **not**
filtered by city — every eligible event is a candidate.

**Why.** The city filter is what makes "nearby" mean something. A user with no city
has no "nearby", and filtering them to a city they did not choose would rank them on a
place we invented for them. The `city_band` term then scores every candidate `0.00` on
city — the band is honest rather than assumed.

**Why not the fallback city.** `PREVIEW_FALLBACK_CITY` ("New York City") is what the
*preview* uses when the catalog does not cover a city. It is not the user's city, and
ranking a user who declined location inference on New York events would be the
failure the `city_source` column exists to prevent.

**The user's country.** `city_band` takes a country on both sides. The user's country
is not stored — the `DigestPreference` has a city and a zone, and no country. So the
user's country is `""`, and the country band is `0.00` for every candidate.

**Is that right?** A user in "Brooklyn" with an event in "Boston" is not "nearby", and
the country band would have said `0.50` — "same country, different city". Losing that
band means the score is `0.20` lower for a same-country event than it could have been.

**The alternative — deriving the country from the city.** The catalog's venues carry a
`country_code`, and the city is stored in the catalog's own spelling, so the country
*could* be looked up. But that is a lookup the composition service would have to make,
against the catalog, for one extra term, and it is a lookup that would have to be
repeated for the *user's* city — and the user's city may not be in the catalog at all
(`city_source='fallback'` means the catalog does not cover it).

**Decision: the user's country is empty, and the country band is `0.00`.** The
user's stored city is enough to say "nearby" — the city band is the band that
matters, and it is a full `1.00` when the cities match. The country band is a
half-credit consolation for "different city, same country", and giving it up costs
`0.10` of a score, not the difference between relevant and irrelevant.

**Why this is not the `city_band` being wrong.** `city_band` is a general function; the
composition service is a caller that happens to have only the city. The function's
contract — "same city → 1.00, same country → 0.50, else 0.00" — is honoured for the
call it is given.

### The saves

The saved candidates are read for exactly one reason: **a saved public event gets the
`saved` Why-this tag** — `why_this_tags(is_saved=True)` — because the user saved it,
and the card should say so.

**The saves are not a separate pool of candidates.** A saved event is a *public*
catalog event, and the public candidate read already returns it — if the city filter
found it. The save is what marks it.

**Why a saved event outside the user's city is not a candidate.** The digest's slots
are "must-know", "nearby" and "serendipity" — all three are about what is happening
*near the user*. A user who saved a concert in another city made a save, not a
statement that the concert is nearby, and putting it in "nearby" would be a lie about
the card. The save's *real* effect is on the user's own Timeline, which is where the
event belongs — and that surface already reads the saved pool directly.

**So the save's effect is the tag, and the tag is a tiebreak-neutral marker.** It does
not change the score, and it does not change the ordering.

**A save whose event the catalog no longer holds.** `public is None`. It cannot be
composed: the model's `digest_composition_kind_shape_ck` requires a public
composition to have a non-null `source_badge` and a non-null `event_version`, and a
save the catalog dropped has no badge — the badge is a fact about a *source*, and the
catalog no longer has one for that event. The saved candidate is therefore **not** a
slot candidate at all, and the reason is the constraint: there is no badge to store.

**That is not a loss.** A user whose save points at an event the catalog dropped gets
no card for it in the digest — which is correct, because there is no catalog event to
show a card for. The save is still on their Timeline.

### The saved pool and the 48-hour window

The saved read has **no upper bound** (D8b of the candidate-reads design) — a save
three weeks out is still a save. That bound is a property of the *saved read*, not of
the digest: the digest's slots hold events the user could still go to, and a
three-weeks-out save is not one of them unless there is nothing else. The recency band
already scores a far-off event `0.00`, so the ordering key puts it last, and it fills
a slot only when the pool is *only* distant saves. That is the honest outcome: the
user saved something, and it is all there is.

---

## D9 — Hysteresis: **within** a day only, and nothing is inherited across days

**The source, verbatim.** EXPERIENCE.md §4, `Indicator.Confidence`:

> "**Hysteresis (transition rule):** Hysteresis is **per-event-per-day** — once a bucket
> is assigned at Pulse composition time for a given event on a given calendar day (in
> the user's local timezone), the event stays in that bucket for the remainder of the
> calendar day. The bucket recomputes only if the raw score changes by **≥0.10** within
> the same day (rare; happens only when the underlying recommendation model re-scores
> the same event mid-day). **Across days, hysteresis resets** — a new composition starts
> fresh bucket assignment. **No persistent bucket is stored between days.**"

And the worked example: *"Next morning Wednesday, a fresh composition assigns the
bucket from the new raw score **without inheriting Tuesday's bucket**."*

**This settles a conflict in the work item, and the item's phrasing was misleading.**
The acceptance criteria say "Hysteresis is applied across days by reading the previous
day's composition … and passing its bucket and score into the hysteresis function", and
then say "across days it resets" — two clauses that cannot both hold. EXPERIENCE.md §4
is the canonical source (the ranking domain says so: "EXPERIENCE.md §4 says ≥0.10 and
is the canonical source"), and the **spines-win rule** governs. So:

- **Within** a local calendar day: the bucket holds unless the score moves by `≥0.10`.
- **Across** days: the bucket resets, and **no bucket is inherited**.

**Decision.** The composition service passes `previous_bucket=None` and
`previous_score=None` to `apply_hysteresis`, so a composition maps its scores directly
to buckets. **It does not read yesterday's digest to inherit a bucket**, and it does
not read any other day's digest either.

**Why not read the previous day's compositions.** EXPERIENCE.md is explicit — "No
persistent bucket is stored between days" — and a service that inherited yesterday's
bucket would put on today's card a bucket the user saw yesterday, without the `≥0.10`
score move the rule requires. That is precisely the flicker the no-flicker rule exists
to prevent, arriving by a different road.

**Why the domain's function is still called, with `None`.** The rule lives in one place
and the service does not reimplement it. `apply_hysteresis` is called with the same
shape a caller with a previous value would use — `previous_bucket=None,
previous_score=None` — so the service is already correct if a mid-day recomposition
becomes possible later. It is also why the service calls `apply_hysteresis` rather
than `score_bucket` directly: `apply_hysteresis` *is* `score_bucket` when there is no
previous value, and choosing the narrower function would be the kind of shortcut that
becomes a bug when the caller changes.

**The within-day case, and why it is unreachable here.** EXPERIENCE.md's within-day
hold applies when "the underlying recommendation model re-scores the same event
mid-day". **This system has no such re-score**: the ranking is computed once per event
per day, and the composed rows are **append-only** (D3 of the models design) — a
recomposition could not update a row, and writing a second row for the same
`(digest_id, event_id)` is forbidden by `digest_composition_digest_event_uq`. So the
within-day case cannot arise in the composition service.

**The consequence, stated plainly.** The no-flicker guarantee is preserved, but by a
different mechanism than the UX spec describes: a card's bucket does not change under
the user because **the number under it does not change either**. The digest is an
immutable fact about a day.

**The test.** Two compositions on two different local dates for the same user and the
same event produce **independent** buckets — a score of `0.83` on both days gives
bucket 4 on both days, and `0.83` then `0.95` gives 4 then 5. **Nothing is inherited
across the day boundary.** And a composition with a score of `0.83` produces bucket 4,
not bucket 5, which is the domain's own exact-boundary rule (`0.850` → 4).

---

## D10 — Determinism: the re-run is a no-op, and it is guarded by an advisory lock

**Decision.** The command is **idempotent per `(user_id, local_date)`**:

- if a digest already exists for that pair, the command returns it with `created=False`
  and writes **nothing** — no new compositions, no update to the existing rows (the
  compositions are append-only), and **no second audit row**;
- otherwise it composes and writes.

**Why "not an update to an immutable row".** `DigestComposition` is append-only
(`append_only_mutable = frozenset()`), so an update would raise `AppendOnlyViolation`
at the ORM level and `RestrictViolation` at the SQL level. The re-run must not attempt
it.

**The lock.** The command takes `pg_advisory_xact_lock` on a **per-user** key before
checking for an existing digest, using the same pattern as `digest_preferences.py`:
`blake2b(user_id, digest_size=8, person=...)` → a signed int.

**Why a lock and not just a `get_or_create`.** The unique constraint
`pulse_digest_user_date_uq` would catch a race — but as an `IntegrityError` that
reaches the caller as a 500. The lock serialises the two workers so the second one
*waits*, sees the row, and returns it. The advisory lock is **transaction-scoped**, so
a crashed worker cannot leave a user's digest wedged.

**Why per-user and not per-(user, date).** Per-user is simpler and it is the unit the
other commands in this package use. The cost is that two compositions for the *same*
user but *different* dates would serialise — which cannot happen, because the
scheduling job composes one date per user per run.

**The audit row on a re-run.** A re-run writes **no** audit row. The audit records
*decisions*, and a re-run decides nothing. A second audit row saying "composed" for a
digest that was composed yesterday would make the audit log claim two compositions
where there is one.

## D11 — The transaction: the catalog reads happen first, outside it

**Decision.** The shape is:

```
1. read the personal side (preference, interests, personal candidates, saves)
2. read the catalog side (public candidates)          ← outside the transaction
3. score, assign the slots, decide the empty state     ← pure
4. with transaction.atomic(using=PERSONAL):
       lock the user
       re-check for an existing digest
       write PulseDigest
       write the DigestComposition rows (one bulk_create)
       write the audit row
```

**Why the reads are outside.** AD-3: no transaction may span both schemas. The catalog
read is a query against the `catalog` alias; if it happened inside a `personal`
transaction, the transaction would be reading across the wall — even though the write
is only to `personal`. The rule is "no transaction spans both schemas", and the
cleanest way to keep it is to do all the catalog reading before the transaction opens.

**Why the writes are atomic.** The digest and its three compositions are one fact. A
digest with two of its three rows is a digest the reader would show as two cards with
a "must-know" slot missing — and `is_empty` would be false, so it would not read as
the empty state either. One transaction.

**Why `bulk_create` for the compositions.** Three rows, one statement. And
`AppendOnlyQuerySet.bulk_create` only refuses `update_conflicts=True`, so a plain
`bulk_create` is allowed.

**Why the lock is *inside* the transaction.** `pg_advisory_xact_lock` is
transaction-scoped: it must be taken inside the transaction that does the work, or it
would be released immediately.

**The window between the read and the write.** The catalog facts are read at
`now - ε` and the digest is written at `now`. An event that is deleted from the
catalog in that window is still composed. This is the accepted cost of AD-3's wall:
the alternative — holding a transaction across both schemas — is exactly what AD-3
forbids. The window is one user's composition, microseconds wide.

**Why the digest is written even when it is empty.** Same reason as D5.

## D12 — The audit row: the fact that a digest was composed, and nothing else

**Decision.**

```python
write_audit(
    actor=actor,
    action="digest.composed",
    target_type="PulseDigest",
    target_id=digest.id,
    details={
        "local_date": local_date.isoformat(),
        "is_empty": is_empty,
        "composition_count": len(compositions),
        "at": now.isoformat(),
    },
)
```

**What is in it.** The local date (not PII — it is the user's own day and it is
already on the row), whether the digest is empty, how many cards it has, and the
instant.

**What is not in it.** No event ids, no titles, no cities, no tag lists, no scores.
AD-13 is explicit, and `digest_preferences.py` set the precedent: the city never
appears in an audit row's details — only `"has_city": bool`.

**Why not the event ids.** The `target_id` already identifies the digest, and the
digest's rows are one indexed read away. An audit row that duplicated the digest's
contents would be a second copy of the digest that could disagree with it.

**The action name.** `"digest.composed"` follows the `<module>.<verb>` convention.
The `target_type` is `"PulseDigest"` — capitalised, matching `digest_preferences.py`'s
`"DigestPreference"`.

**No audit row on a re-run.** See D10.

## D13 — The tags come from the same inputs as the score, and the personal event's tags are its own

**Decision.** `why_this_tags` is called with the **same `RankingInputs`** the score
used. That is AD-10's whole point: "the explanation and the decision cannot drift
apart."

**The personal event's chip keys.** A personal event is the user's own agenda; it has
no chips and no title in the catalog. Its `interest_overlap` is `0.0` — the user's
own event is not "matched to" their interests, it *is* theirs.

**The personal event's `is_saved`.** False. It is on the user's calendar; the `saved`
tag means "you saved this public event".

**The personal event's city band.** The personal event has a `location` string, which
is free text and not a city. So its city band is `0.00` — it is not in a city we
know about. The `nearby` tag therefore does not appear on a personal event, which is
right: "nearby" is about a venue's city, and the user's own event is not nearby, it is
*theirs*.

Hmm — that loses the "nearby" signal for a personal event that happens to be in the
user's city. But the personal event's `location` is free text, and matching free text
against a city name is exactly the kind of guess the codebase refuses elsewhere
("give such events no row rather than a guessed one"). So `0.00` is right, and the
decision is recorded.

**The serendipity tag.** Slot 3's composition carries `discovery` and **no chip tag** —
`why_this_tags(serendipity=True)` suppresses chip tags itself.

**The saved tag.** A candidate that is in the saved pool gets `is_saved=True`.

## D14 — The cost shape: bounded, and batched by the scheduling job

**Decision.** This item owns the *per-user* cost; `digest-scheduling` owns the
*batching*. The two statements together are the cost story.

**Per composition, the queries are:**

| Query | Bound |
|---|---|
| the preference | 1 row |
| the interests | ≤ `MAX_INTEREST_PICKS` rows |
| the personal candidates | the 48-hour window |
| the saved candidates | ≤ `MAX_SAVED_CANDIDATES` (60) |
| the conflict pairs | the user's open pairs |
| the public candidates | ≤ `CANDIDATE_POOL_SIZE` (60), one query to `catalog` |
| the writes | 1 + ≤3 + 1 rows |

**Every read is bounded.** The candidate pools are bounded by constants that already
exist (`CANDIDATE_POOL_SIZE`, `MAX_SAVED_CANDIDATES`), the window is bounded, and the
conflict read is bounded by the user's own pairs. There is no query in this path that
scales with the size of the catalog or the size of the user table.

**Why this is per-user work and not per-catalog work.** The composition is a function
of one user's preferences, interests and candidate pool. It cannot be shared between
users — two users in the same city with the same chips still have different digests
because their saved events and personal events differ.

**The batching story, for `digest-scheduling`.** The job claims a bounded batch of
users (the `schedule_sources` pattern), and each claim runs the composition for its
users. At 100K MAU that is 100K compositions a day, each costing roughly a dozen
bounded queries — about 1.2M queries a day, which is a few minutes of a single
worker's time spread across the day. The per-composition cost is the thing that has to
stay bounded, and it is.

**Why the composition must not compete with a crawl for the same process.** AD-1
exists precisely so this cannot happen: the composition is a separate worker from the
crawl, and the crawl's schedule is not delayed by a digest run.

## D15 — AD-10's durability promise is made here

**The promise.** "The Detail Screen can only show an explanation for an event this
service once composed." So the set of events a user can ever ask "why this?" about is
**exactly** the set this service wrote rows for.

**What follows from it.**

- A user who saved an event and never received it in a digest has **no** persisted
  explanation for it, and the Detail Screen must say so rather than recompute one.
  Recomputing would violate AD-10's "persisted, never recomputed at render" and would
  produce a different answer from the card, because the inputs would have moved.
- An event that was in yesterday's digest and is not in today's has a row, and the
  Detail Screen reads **the most recent composition for that `(user, event)` pair** —
  which is what `digest_comp_user_event_idx` is for.
- The read API **must not recompose**. `digest-read-api` reads these rows.

**Why it is worth stating.** A reader who finds an event with no explanation will be
tempted to compute one. This is the constraint that says: there is none, by design.

---

## The decision table

| # | Decision | The alternative | Why this one |
|---|---|---|---|
| D1 | One named command, reads its own pool | A `candidates=` parameter | The command owns its inputs; a caller-supplied pool lets the card and the score drift (AD-10) |
| D2 | The local date is the user's, converted, in the preference's zone | UTC's date; `now + 24h` | AD-6; conversion handles DST for free |
| D3 | The tie-break is `(-score, start_time_utc, event_id)` | Database order; the slug | A total order, so two runs cannot disagree |
| D4 | Slots filled in order, each from the unused candidates | Let the DB's unique constraint catch duplicates | The service must not rely on an `IntegrityError` to notice |
| D5 | The empty state needs **both** halves | Either half alone | FR-5 widens FR-8; two events is not "nothing" |
| D6 | Show what there is | Pad from a relaxed pool; fall to the empty state | Padding publishes cards the rules forbid; the empty state lies when there is something |
| D7 | The chip matching is built, in ingestion, as a pure function | Pass `()` and accept an inert weight | The largest weight cannot be inert; the domain says an inert weight is the worse trust failure |
| D8 | The public pool is filtered by the city, unless the user has none; the user's country is empty | Always filter to the fallback city; derive the country from the city | A fallback city is not the user's city, and the city band already carries "nearby" |
| D8b | The saves mark a card with the `saved` tag; they are not a separate candidate pool | Merge the saved pool into the candidates | The slots are "nearby"; a saved event in another city is not nearby |
| D9 | Hysteresis is called with `previous_bucket=None`; **nothing is inherited across days** | Read yesterday's digest and inherit its buckets | EXPERIENCE.md §4: "No persistent bucket is stored between days" |
| D10 | The re-run is a no-op, guarded by a per-user advisory lock | `get_or_create`; rely on the unique constraint | A race would reach the caller as a 500 |
| D11 | The catalog reads happen outside the transaction | Read inside | AD-3: no transaction spans both schemas |
| D12 | The audit row carries the count, the date and the emptiness | The event ids; the titles | AD-13; `digest_preferences.py`'s precedent |
| D13 | The personal event's city band is `0.00` | Match its free-text location against the city | A guess; the codebase refuses guesses of this kind |
| D14 | The per-composition cost is bounded; the batching is the scheduler's | Batch here | The item owns per-user cost; the scheduler owns throughput |
| D15 | The explanation exists only for composed events | Recompute at read time | AD-10: persisted, never recomputed |

---

## What the code review changed

*(filled in after the review — see the review report.)*

Thirteen findings were applied. **Five were correctness defects that stopped the
command from working at all**, and the tests found every one of them:

| # | What was wrong | What changed |
|---|---|---|
| 1 | The advisory lock's `person` was `b"eventpulse-digest"` — 17 bytes, and `blake2b` caps it at 16. Every composition raised `ValueError`. | `b"ep-digest-c"` — 10 bytes, and distinct from every other lock namespace in the codebase. The comment now says why the digest lock is **not** shared with `digest_preferences.py`'s: the two commands lock different rows. |
| 2 | The slot scorers were called positionally; `domain/ranking.py` declares them keyword-only. Every composition raised `TypeError`. | `slot_scorer(inputs=inputs)` / `score_slot_1(inputs=inputs, ...)`. **D4 above was corrected to match.** |
| 3 | `chip_matching.py`'s hyphen rule did not hold: "story-time" and "storytime" did not match each other, though the docstring promised they would. | Both sides are normalised through the same rule. **D7 above now states the mechanism.** |
| 4 | The token-set path compared the *raw* keyword against the *normalised* text. | `_keyword_tokens(keyword) & words` — symmetric normalisation. |
| 5 | The tests' events were five days stale against the test clock (`last_seen_at` defaults to the wall clock), so the candidate read dropped them all and every composition was empty. | `make_event` pins `last_seen_at=NOW`. |

Two of the five were in the **implementation** and three were in the **tests** — and the
test-side ones are the ones worth noting: a stale-event default and a factory whose
`end_utc` preceded its `start_utc` both produced failures that looked like composition
bugs and were not. The helpers now carry the reason in their docstrings, so the next
reader does not rediscover it.

The other eight were code-quality, architecture and testing findings: a design
document that showed a call the domain forbids (D4, corrected above); a lock comment
that claimed a namespace the code did not use; a keyword-table docstring that made a
claim the table contradicted ("sports must not match sport", in a table that lists
both); the absence of any test for the module that decides the largest term in the
formula; and an uncovered fallback branch for a hand-edited timezone.

**The design's own statements that the review changed** are D4's scorer call, D7's
matching rule, and D7's "two to four keywords per chip" — the shipped table has four
to eight, and the design now says so rather than claiming a number a reader could
check and find false.

**What the review deliberately did not change** is D8's empty country band, D9's
hysteresis resolution, and D5's two-half empty state — each was re-examined against the
canonical source and each survived. The country band remains a **known, stated gap**: if
the `DigestPreference` ever gains a country, D8 has to be revisited.

---

## What this item does not build

- **The scheduling.** `digest-scheduling` owns the tick, the batch claim and the
  per-user dispatch.
- **The read API.** `digest-read-api` reads these rows and **must not recompose**.
- **The frontend.** `frontend-pulse-card` and `frontend-digest-home`.
- **The email.** The digest's email delivery is not in this intent's item list.
- **The keyword table's refinement.** The table in `shared/constants.py` is a
  hand-written starting point; improving it is an editorial task, not a code task.
