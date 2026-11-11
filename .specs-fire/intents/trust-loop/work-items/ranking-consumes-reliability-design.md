# Design: Paying the ranking debt — source reliability enters the Relevance Pulse

**Work item:** `ranking-consumes-reliability`
**Intent:** `trust-loop`
**Complexity:** high → this document
**Mode:** validate (two checkpoints)
**Date:** 2026-11-11

---

## D1. What this item is for

`domain/ranking.py` publishes a **reduced** Relevance Pulse:

```
relevance_score = 0.45 × interest_overlap
                + 0.25 × recency
                + 0.20 × city_match
                + 0.10 × confidence
```

FR-22 publishes the full one:

```
relevance_score = 0.40 × preference_graph_match
                + 0.25 × source_reliability
                + 0.20 × recency_fit
                + 0.15 × novelty_vs_exploration
```

The reduction was a **deliberate, documented debt**, and the module docstring names
`source_reliability` as the term this item pays:

> `source_reliability` — **FR-16**. Its arithmetic has shipped in `domain/reliability.py`;
> what is still missing is a stored score on `Source` for this formula to read, which
> `reliability-recompute-and-escalation` adds and `ranking-consumes-reliability` wires in.

The predecessor item has shipped. `Source.reliability_score` exists, the weekly
recompute writes it, the escalation fires on it, and the source panel shows it. **The
number exists. The ranking does not read it.** That is this item.

Two things this item must *not* do, both stated as hard constraints before the design
begins:

- **It must not publish a formula that does not match the card.** The module's own
  standard: *"A term pinned to a constant is an **inert weight**: the published formula
  would stay arithmetically checkable and still produce a different number from the one on
  the card, which is a worse trust failure than a reduced formula because it looks
  verifiable."* So the term either moves the number **for real**, from a **real** stored
  value, or it is not in the expression at all.
- **It must not move a user's Confidence Pulse for a reason the user cannot see.** A
  weight change is a re-weighting of every user's digest. AD-10 says the explanation is
  **persisted and never recomputed at render**, so the re-weighting happens only at the
  next composition — but "at the next composition" is exactly where a card's dots can
  jump for no visible reason. D9 handles that.

---

## D2. The weights — and the PRD-amendment question

### D2.1 The proposed weights

| Term | FR-22's published weight | Now | Rationale |
| --- | --- | --- | --- |
| `interest_overlap` | — (`preference_graph_match` = 0.40) | **0.35** | The chips are the Preference Graph's only surviving trace; they lose 0.05 to the term they were standing in for. |
| `source_reliability` | **0.25** | **0.25** | **FR-22's exact published weight.** No change. |
| `recency` | — (`recency_fit` = 0.20) | **0.20** | FR-22's exact published weight for `recency_fit`. |
| `city_match` | — | **0.10** | FR-5's `geographic_distance_factor` is not computable; the city band is the surviving form of it. |
| `confidence` | — | **0.10** | Unchanged. The "certainty about relevance, not just trust in the source" term. |
| **Sum** | 1.00 | **1.00** | |

So the new weights are:

```
relevance_score = 0.35 × interest_overlap
                + 0.25 × source_reliability
                + 0.20 × recency
                + 0.10 × city_match
                + 0.10 × confidence
```

### D2.2 Why this is *toward* FR-22, not away from it

This is the AC's question, and the answer is: **it is a step toward the published weights,
which makes the reduced weights a temporary state the PRD already anticipates.** Three of
the five weights now sit at, or very near, FR-22's published values for the terms they
stand in for:

- `source_reliability` is **0.25**, exactly FR-22's `w2`.
- `recency` is **0.20**, exactly FR-22's `w3` for `recency_fit`. (The reduced formula had
  *raised* it to 0.25 when it was standing in for two things at once; now that it stands
  for one thing again, it goes back to FR-22's number.)
- `city_match` + `confidence` together are 0.20, and FR-22's `w4` (`novelty_vs_exploration`)
  is 0.15. The slack is 0.05, and it goes to `interest_overlap` (0.40 → 0.35) — the term
  standing in for `preference_graph_match`, which FR-25 will replace.

**The reduced formula was never a published formula.** It was an *interim* expression
whose docstring said so ("the reduction is the design", "what is still missing is…"),
and whose own weights block says the weights are "the **reduced** ones". FR-22's
immutability policy is about the **published** weights:

> The weights above are the MVP weights and are locked at launch.
> Any change to the weights is a PRD amendment requiring explicit product leadership sign-off.

The MVP weights are 0.40 / 0.25 / 0.20 / 0.15. The reduced 0.45 / 0.25 / 0.20 / 0.10
were **never** the MVP weights, so changing them does not change the MVP weights. What
changes is the *implementation* of `preference_graph_match` and `recency_fit`'s weight,
and FR-22 explicitly permits that:

> The Architecture spec describes the *implementation* of the formula but does not redefine
> the weights.

### D2.3 The amendment that IS owed

FR-22's own words require the *implementation* to be published and the amendment history
surfaced:

> Amendments are tracked in `docs/adr/` and surfaced in Settings → Privacy → "Ranking
> algorithm version" with the amendment date and a link to the relevant ADR.

And:

> A user reading the PRD can compute the Confidence Pulse for any Event given the inputs.

**A user cannot compute the Confidence Pulse today** — the PRD's formula names four
terms, two of which do not exist in the product, and the product's actual formula names
four *different* terms, none of which the PRD mentions. That is the gap this item closes,
and closing it needs **an amendment**.

**Therefore: an ADR is owed, and it is owed under FR-22's own amendment policy.** The
amendment is not "we changed FR-22's weights" — it is:

> **Amendment A-10 (proposed).** FR-22's published formula is implemented with a documented
> substitution for each term that has no computable input. `source_reliability` is now
> implemented at FR-22's published weight of 0.25. `preference_graph_match` is implemented
> as the interest-chip overlap (a trace of the Preference Graph) at 0.35. `recency_fit` is
> implemented as the start-time band at 0.20. `novelty_vs_exploration` is not implemented
> and its 0.15 is split between the city band (0.10) and extraction confidence (0.10),
> which together are 0.20. The **MVP weights are unchanged**; the formula's *terms* are
> now the terms the product computes, and the PRD's formula is the one a reader can
> evaluate.

`docs/adr/` did not exist in this repository before this item (verified: `ls docs/adr/` → no such
directory). **This item creates it** and writes the ADR at `docs/adr/ADR-0025.md`. Creating the ADR directory and
the ADR is the deliverable that makes the change compliant; the CI pin in
`tests/shared/test_constants.py` (D11) references it, so the two cannot drift.

### D2.4 The e2e mutation probe, and what it means for this change

`tests/e2e/mutation_probe_contract_e2e.py:267-278` is a **probe**: it mutates
`RANKING_WEIGHT_INTEREST` from `0.45` to `0.50` and requires the backend suite to fail.

The probe's note says:

> FR-22: the weights are pinned, and the pin is watched to fail.

**The probe still works after this change, but its mutation target is now stale.** The
probe hard-codes the *old* value `0.45`:

```python
(
    'RANKING_WEIGHT_INTEREST = Decimal("0.45")\n',
    'RANKING_WEIGHT_INTEREST = Decimal("0.50")\n',
),
```

After this item, `RANKING_WEIGHT_INTEREST` is `Decimal("0.35")` and the literal
`RANKING_WEIGHT_INTEREST = Decimal("0.45")` **no longer appears in `shared/constants.py`**.
The probe's edit is a **no-op** — it would find nothing to replace, the suite would stay
green, and the probe would pass **while proving nothing**. That is precisely the
**false green** the probe's own comment warns about in probe #7:

> The bug has to parse. An earlier version of this probe wrote
> `transaction.atomic(using=PERSONAL, using=CATALOG)`, which is a `SyntaxError` — and the
> suite "caught" it, because a suite that cannot be collected fails. That is a **false
> green**.

**So the probe's edit string must move with the constant.** It becomes `0.35 → 0.40`.
This is a **required** change, not an optional one: leaving the probe pointing at a
literal that no longer exists silently disables one of the run's contract probes.

### D2.5 The pin, and what "an unreferenced change" means

FR-22's consequence:

> A weight change without a PRD amendment is a CI-level test failure.

`tests/shared/test_constants.py:134` (`test_ranking_weights_are_pinned`) is that test. It
pins the four weights and `RANKING_WEIGHT_SUM == Decimal("1.00")`.

**The pin's own docstring must be rewritten**, because it currently states the *old*
reduction as the reason:

> The published formula (0.40 preference_graph / 0.25 source_reliability / 0.20 recency /
> 0.15 novelty) has two terms with no computable input in this codebase, so the surviving
> four are redistributed to still sum to 1.0. If any weight moves, the PRD must be amended
> in the same commit.

After this item: **five** weights, one of which (`source_reliability`) is at FR-22's
published value, and the reason for the distribution is now the **ADR**, not a
redistribution.

**"The pin test must still fail on an unreferenced change"** — the AC's wording. The
mechanism has to be that the pin names the amendment, and the amendment reference is
itself part of what is pinned. The design for this (D11) is a **second pinned constant**:

```python
# The ADR that authorises the current weights.
RANKING_WEIGHTS_AMENDMENT = "ADR-0025"
```

and the test asserts both the weights **and** the amendment reference. A weight change
then fails the test in two ways: the number changed, **and** the ADR reference did not.
The second is the one the AC asks for — the change is *unreferenced* unless an amendment
names it. To make that meaningful the reference must be checked against something real,
not just re-typed in the test; see D11.

---

## D3. The inert-at-launch problem — **answered**

This is the AC's hardest question, and the module docstring frames it:

> At launch, every source has fewer than 30 observations, so every source sits at or near
> the 0.50 prior, and the new term would be close to a constant until data accrues.

The three options the AC offers:

1. enter the term only for sources past the minimum N;
2. enter it for everyone, with the prior as a neutral value, and say why that is not
   "inert" under the module's own definition;
3. centre it, so 0.50 contributes nothing relative to other sources.

### D3.1 The choice: **option 2, with option 3's centring applied inside it**

The term enters for **every** source, with the prior (`0.50`) as the neutral value, and
the input the ranking consumes is the **centred** reliability:

```
source_reliability_term = source_reliability − 0.50      # ∈ [−0.50, +0.50]
```

**But** — and this is the part that needs care — a *negative* term breaks the module's
clamp and the score's [0, 1] range, and a negative weight is not something
`RANKING_WEIGHT_SUM == 1` can express. So the centring is done the other way: **the
weight is applied to the reliability, and the *neutrality* is expressed by making 0.50
score exactly what a term with no opinion would score.**

### D3.2 The shape that works: a **shifted** reliability, not a centred one

Here is the honest arithmetic. FR-22 says each component is "normalized to [0.0, 1.0]".
A reliability of 0.50 is the *prior mean* — the score of a source about which we know
nothing. So "no opinion" is a legitimate value of the input, and the term should be
`0.25 × 0.50 = 0.125` when we know nothing. That is **not** an inert weight in the
module's sense: it is a **constant contribution of 0.125 to every card**, which is
exactly what every other term contributes when *it* is unknown. `confidence` is `1.00` for
a personal event and `0.10` for a catalog event — also a constant within its population.
`city_match` is `0.00` for a personal event — also constant.

**The module's definition of an inert weight is precise, and it is about *the whole
formula*, not about a term:**

> A term pinned to a constant is an **inert weight**: the published formula would stay
> arithmetically checkable and still produce a different number from the one on the card.

The defect of an inert weight is that it **cannot distinguish two candidates**, so it
cannot affect the *ranking* while appearing in the *published formula*. The defect this
item faces is different: the term **can and does** distinguish candidates — a source
scored 0.20 and a source scored 0.80 produce different scores — it simply does not
distinguish them *yet*, because no source has enough observations to be scored away from
the prior.

**And that is the answer to "why is that not inert".** The term is inert **only** in the
sense that its *value* is currently uniform across the corpus. It is **not** inert in the
sense the module forbids, because:

1. **The value is read from a stored, computed, per-source number** — `Source.reliability_score`,
   written by the weekly recompute, not a literal in the code. A reader can watch it move
   for a specific source.
2. **The term distinguishes candidates the moment the corpus differentiates.** The design
   must not wait for that to be true to publish the term, because the corpus *starts*
   differentiating only if the term is in the formula — no wait, that is not true either:
   the recompute runs independently of the ranking. So this argument alone is weak.
3. **The stronger argument: the term is not pinned to a constant *in the expression*.**
   The expression reads `inputs.source_reliability`, a per-candidate field. It is a
   *variable* whose current distribution happens to be narrow. A constant and a
   currently-uniform variable are different things, and the second one starts working
   the moment the data does.

So, the **decisive** argument is the third one plus this: **the prior is a value, not a
constant.** `0.50` is `reliability_score(0, 0)` — it is *asked of the domain module*, so
if FR-16's prior is ever re-tuned the term moves with it. And a source that has been
scored **0.20** or **0.80** — which the AC's proof requires, and which the recompute
produces the moment observations accrue — is distinguished **today**, in the formula, by
real numbers.

### D3.3 The counter-argument, and why option 1 and option 3 are rejected

**Option 1 (enter only past the minimum N) is rejected** because it is *worse* than the
alternative, and it is worse in a way the module already knows how to name.

- It makes the formula's **shape depend on a data condition** that the reader cannot see
  from the inputs. A reader given "interest 0.5, recency 0.75, city 0.5, confidence 0.9,
  reliability 0.20" cannot compute the score unless they also know the source's
  observation count — which FR-22 does not put in the formula. **That breaks FR-22's
  promise that "a user reading the PRD can compute the Confidence Pulse for any Event
  given the inputs".** The inputs would no longer be enough.
- It creates **two different formulas**, one of which is the published one. The card would
  show a number computed by a formula that is not the published formula, for some
  candidates and not others — the exact "arithmetically checkable but produces a
  different number" failure the module warns about.
- It has a **cliff**: a source crossing n=30 would change score discontinuously, with no
  event change. That is the AD-10 failure D9 is about, manufactured by the ranking
  itself.

**Option 3 (centre it so 0.50 contributes nothing) is rejected** because it cannot be
expressed as a weight.

FR-22's terms are all "normalized to [0.0, 1.0]" and the weights sum to 1, so every
term contributes between 0 and its weight. A centred term contributes `−0.12 … +0.12`, so
the sum is no longer a convex combination and the score can go **negative** for a bad
source — which the clamp at `[0, 1]` would then silently flatten to 0, destroying the
ordering information the term exists to provide. Centring also breaks
`RANKING_WEIGHT_SUM == 1`, the constant the module pins as "so the score stays in [0, 1]
and the bucket boundaries keep their meaning".

**The compromise that is actually chosen:** enter the term for everyone (option 2), and
make the prior's contribution **explicit and identical to what a term with no opinion
contributes** — which is what "the prior as a neutral value" means. The prior is `0.50`,
it enters as `0.25 × 0.50`, and that is the same for every source until the data says
otherwise.

**But there is one more thing to do, and it is what makes this honest rather than
merely defensible:** the term must **not** be silently constant. If a user reads the
card and asks "why does this source's card score lower?", the answer must exist. So the
**Why-this tag** set gains a way to say it (D8), and the **inputs** carry the reliability
so the explanation can name it.

### D3.4 The module docstring is updated to match

The module docstring currently says:

> The two absent terms have no `Source` score field and no `Event` category field to read
> from, and FR-16 and FR-25 are both unbuilt.

and

> `source_reliability` — **FR-16**. Its arithmetic has shipped in `domain/reliability.py`;
> what is still missing is a stored score on `Source` for this formula to read, which
> `reliability-recompute-and-escalation` adds and `ranking-consumes-reliability` wires in.

**Both sentences become false with this change**, and the docstring must say what is now
true. The new text states:

- `source_reliability` is **present**, at FR-22's published weight of 0.25, read from
  `Source.reliability_score`.
- **Why the term is not inert**, in the module's own terms: it is a per-source *variable*
  read from a stored, computed number — the prior is a value, not a constant in the
  expression — and the module names the condition under which it would have been inert
  and why it is not.
- `novelty_vs_exploration` is **still absent** (FR-25), and its weight is distributed.
- The **published formula** (FR-22's) is now *implemented with documented substitutions*,
  and the ADR records them.

---

## D4. `RankingInputs` gains the source's reliability

```python
@dataclass(frozen=True)
class RankingInputs:
    interest_overlap: Decimal
    recency: Decimal
    city_match: Decimal
    confidence: Decimal
    source_reliability: Decimal      # NEW
```

**Required, not defaulted.** Every other field on this dataclass is required, "so that a
new construction site cannot forget one silently" (the same reasoning
`PublicEventCandidate.is_sold_out` records). A default of `0.50` would let a
construction site forget the term and silently score every card as if the source were at
the prior — an inert weight by construction. **No default.**

**`domain/` stays pure.** `domain/ranking.py` imports the stdlib plus `shared.constants`
and `shared.ids` — AD-8, checked by `tests/architecture/test_stdlib_only.py` and
import-linter's `domain-pure` contract. So the reliability **prior** must be reachable
from `domain/` without importing `apps.ingestion.models`.

**The prior's home.** `RELIABILITY_PRIOR_ALPHA = 5` and `RELIABILITY_PRIOR_BETA = 5` are
already in `shared/constants.py`, and `domain/reliability.py` computes the prior mean
from them. `domain/reliability.py` is itself stdlib-only (it is in `domain/`), so
`domain/ranking.py` **may** import it: `from domain.reliability import reliability_score`
— but that is a *domain → domain* import, which is allowed. Alternatively the prior
constant can live in `shared/constants.py` directly.

**Decision:** the ranking consumes the *already-computed* score from `Source.reliability_score`
and, for a source that has never been scored, the **prior**. The prior is asked of
`domain/reliability.py`'s `reliability_score(0, 0)` — the *same function* the recompute
uses, so the two can never disagree about what "no observations" means. This mirrors
`apps.ingestion.services.reliability.current_score(source)`, which already does exactly
this (returns `reliability_score(0, 0)` when `source.reliability_score is None`).

**But `domain/ranking.py` must not read the database.** So the *value* is computed by
the caller (the composition service, which is allowed to read the catalog) and passed in
as a `Decimal` on `RankingInputs`. The prior logic lives in one place —
`domain/reliability.py` — and the *service* asks it the same question
`current_score` asks.

### D4.1 The read: where the reliability comes from, and the no-N+1 guarantee

**The AC says: "read through the published `ingestion` read the recompute item provides."
There is no such read yet.** The recompute item published
`apps/ingestion/services/reliability.py` with `current_score(source)` — but that takes a
`Source` **model instance**, which `personalization` may not hold (AD-2's
`models-ingestion` contract: only `apps.ingestion` may import `apps.ingestion.models`).
So `personalization` cannot call `current_score` at all — it cannot construct a `Source`.

**The fix is free, and it is the reason this item is cheap.** Look at what the candidate
read already does:

```python
queryset = (
    Event.objects.using(CATALOG)
    ...
    .select_related("venue", "source")
)
```

`select_related("source")` **already joins the `Source` row**. The reliability score is a
column on that row. So `PublicEventCandidate` gains a field:

```python
    #: FR-16: the source's reliability score, as the catalog computed it.
    #: `None` when the source has never been scored — the prior stands in.
    source_reliability: Decimal
```

and `_to_public_candidate` fills it from `source.reliability_score`.

**This is zero extra queries.** The join is already there; a column on a joined row costs
nothing. **And that is the N+1 guarantee, structurally** — the AC asks for "no N+1
query, and the bound on query count is tested", and the strongest form of that is *the
query count does not change at all*.

### D4.2 The published `ingestion` read

The AC says "read through the published `ingestion` read the recompute item provides."
The honest reading is that the reliability must arrive through an **`ingestion` service
that hands over plain data**, not through a model reference. Two candidates:

**(a) Extend `PublicEventCandidate`** with the score. The read is already published,
already joins the source, already hands over plain data.

**(b) Add a new read** `apps/ingestion/services/reliability_read.py` with a function like
`reliability_for_sources(source_ids) -> dict[UUID, Decimal]`.

**(b) is rejected**: it would be a *second* query for data the first query already
carried, and it would need a source-id list the candidate read does not currently carry
(`PublicEventCandidate` has `source_name`, not `source_id`). **(a) is chosen.**

But **(a) alone is not quite the whole answer**, because there is a second consumer: the
**personal** candidates. `PersonalEventCandidate` has **no source** — a personal event is
the user's own agenda, and there is no `Source` behind it. So:

- **A public candidate's reliability is its source's reliability.** Read from the joined
  `Source` row.
- **A personal candidate's reliability is the prior, `0.50`.** The user's own calendar
  has no source reliability; the facts are the user's own, which is already what
  `confidence=1.00` says in `_inputs_for_personal`. **This is not an inert weight in the
  forbidden sense** — it is the same structure as `city_match=0.00` and `confidence=1.00`
  for personal events, both of which the module already ships, and it is *stated* in the
  code that carries it.

**So the published read is `list_public_candidates`, extended.** And to make the "no
N+1" claim testable, the extension gets its **own named read function in `ingestion`**,
because the AC's phrase "the published `ingestion` read" suggests the score should be
reachable through `ingestion`'s published surface rather than through a field the
composition service has to know the meaning of.

**Decision:** `apps/ingestion/services/catalog_read.py` gains:

```python
@dataclass(frozen=True)
class SourceReliability:
    """One source's FR-16 reliability, as plain data."""
    source_id: UUID
    score: Decimal
    scored_at: datetime | None
    observation_count: int
```

and `PublicEventCandidate` gains `source_reliability: Decimal` (the resolved value, prior
or stored). `list_public_candidates` is the published read; the DTO is the published
shape. The **prior** is resolved by `apps/ingestion/services/reliability.py`'s existing
`current_score`-equivalent, so the two paths cannot disagree.

### D4.3 The query-count bound, and how it is tested

The digest's other reads already pin their bounds (`tests/personalization/test_digest_api.py`
— "Six is the worst case", "the bound is a property of the read, not of the day"). The
bound for the **composition** path is the one this item must add:

> **The composition's catalog query count does not change when this item lands, and does
> not grow with the number of candidates.**

Test shape (in `tests/personalization/test_digest_composition.py` or a new file):

```python
with CaptureQueriesContext(connections[CATALOG]) as catalog_queries:
    compose_digest(user_id=user.pk, now=NOW)
one = len(catalog_queries.captured_queries)
# ... ten candidates ...
assert len(catalog_queries.captured_queries) == one
```

**And the stronger form:** the count is asserted to be **exactly** what it was before the
change — i.e. a named constant `COMPOSITION_CATALOG_QUERY_COUNT` — so a future
"optimisation" that starts querying per-candidate fails loudly.

**The N+1 proof is the mutation:** an implementation that read
`Source.objects.get(pk=candidate.source_id)` per candidate would make the count grow
with the candidate count, and the "does not grow" test would fail. The test *is* the
mutation probe for this AC.

---

## D5. Slots 2 and 3

### D5.1 `score_slot_2` — "nearby"

FR-5 writes slot 2's score as:

```
source_reliability × geographic_distance_factor × freshness_factor
```

Its current docstring says:

> **two of those three terms have no input here**: `source_reliability` is FR-16
> (unbuilt), and `geographic_distance_factor` is a haversine over a city centroid that
> does not exist because `Venue` has no coordinates.

**After this item, one of the three terms has an input.** `geographic_distance_factor`
still does not, and `freshness_factor` is not a separate input either — it is the
recency band.

**Decision: slot 2 is updated to use the term.** It already calls `relevance_score`, and
`relevance_score` now includes the reliability term, so **slot 2 gets the term for free
and correctly** — the docstring is what changes. The new docstring says:

- `source_reliability` **now has an input** and enters at FR-22's published 0.25.
- `geographic_distance_factor` **still has no input** — `Venue` has no coordinates — so
  the multiplicative shape is still not computable, and the city band remains the
  surviving form of it.
- The slot's score is the standard Relevance Pulse, which now carries the source's
  reliability.

**This is a real change to slot 2's numbers**, and D9 handles what it means for cards
already shown.

### D5.2 `score_slot_3` — "serendipity"

FR-5 publishes:

```
score = source_reliability × geographic_distance_factor × freshness_factor
      × (1 − normalized_popularity)
```

Its current docstring says `normalized_popularity` does not exist and the bias is
expressed as an **inverted preference term** — "**this is a deviation from FR-5, and it
is not the same quantity**".

**After this item, `source_reliability` is no longer missing from slot 3 either** — the
inverted-preference construction passes the reliability through unchanged:

```python
inverted = RankingInputs(
    interest_overlap=RANKING_SCORE_MAX - inputs.interest_overlap,
    recency=inputs.recency,
    city_match=inputs.city_match,
    confidence=inputs.confidence,
    source_reliability=inputs.source_reliability,   # NEW — not inverted
)
```

**Is the reliability inverted in slot 3?** **No**, and the reason matters: FR-5's slot-3
formula **multiplies by** `source_reliability` — it is a *quality gate*, not a
*popularity* term. The anti-popularity bias is `(1 − normalized_popularity)`. Inverting
the reliability would invert a quality signal, which is not what FR-5 says and would
mean slot 3 *prefers* unreliable sources. **The reliability passes through un-inverted.**

The docstring's "two terms have no input" sentence becomes "**one** term has no input",
and the deviation note is narrowed: the deviation is now **only** the anti-popularity
factor, not the reliability.

### D5.3 The **proof** the AC demands

> **The proof:** two otherwise-identical events, one from a source scored 0.2 (past the
> minimum N) and one from a source scored 0.8, rank in that order. A test for each slot
> that uses the term. A mutation (removing the term) fails them.

**This is the acceptance test, and it is the one that proves the item is real.**

- Two events, identical in every input except `source_reliability`: `0.20` and `0.80`.
- Every other input held equal.
- The event from the `0.20` source scores **lower** in **each slot that uses the term**:
  slot 1 (`score_slot_1` → `relevance_score`), slot 2 (`score_slot_2`), slot 3
  (`score_slot_3`).
- **The score difference must be exactly `0.25 × (0.80 − 0.20) = 0.15`** for slots 1 and
  2, and the same for slot 3 (because slot 3 does not invert the reliability).
- **The mutation:** removing `RANKING_WEIGHT_RELIABILITY * inputs.source_reliability` from
  `relevance_score` makes the two scores **equal**, so the test fails. That is the proof
  that the term is load-bearing and not decorative.

**Where the test lives:** `tests/domain/test_ranking.py` (the domain's own test file,
which already has the slot tests at :457/:486/:491).

**A note on "past the minimum N".** The AC says the 0.2 source is "past the minimum N".
A source with 30 observations can score 0.20? **No** — FR-16's floor is 0.32, so a
scored source cannot be at 0.20. **But** the *stored* value can be 0.20 in the test
fixture without the domain caring: the domain reads a `Decimal` and does not check the
observation count. And the floor is a property of the *recompute*, not of the *ranking*.

**Decision:** the domain test uses `0.20` and `0.80` directly, because the ranking's
contract is "given this reliability, this is the score" and the floor is enforced
upstream. The **service-level** test uses a source that has actually been recomputed to
`0.20` — which, under FR-16's floor, is only reachable with the floor disabled or with
the escalation path. **The domain test is the one the AC asks for**; the service test
uses a realistic pair (`0.32` and `0.80`) to prove the wiring.

---

## D6. The weights in `shared/constants.py`

```python
RANKING_WEIGHT_INTEREST = Decimal("0.35")
RANKING_WEIGHT_RECENCY = Decimal("0.20")
RANKING_WEIGHT_CITY = Decimal("0.10")
RANKING_WEIGHT_CONFIDENCE = Decimal("0.10")
RANKING_WEIGHT_RELIABILITY = Decimal("0.25")
```

Sum: 0.35 + 0.20 + 0.10 + 0.10 + 0.25 = **1.00**.

`RANKING_WEIGHT_SUM` is re-defined over five terms and still pinned to `1.00`.

**The comment block above the weights is rewritten** — it currently says "two of the four
components have no input in this codebase" and lists `source_reliability` first among
the missing ones. That is now false, and a comment that lies about the formula is worse
than no comment: it is the thing a reader would trust.

---

## D7. `domain/ranking.py` — the changes, precisely

1. **Module docstring** — rewritten per D3.4.
2. **`RankingInputs`** — gains `source_reliability: Decimal` (required).
3. **`relevance_score`** — gains the term.
4. **`score_slot_3`** — the inverted `RankingInputs` passes `source_reliability` through.
5. **`score_slot_2`** — docstring updated (the code already routes through
   `relevance_score`).
6. **`__all__`** — unchanged (`RankingInputs` is already exported).

**Nothing else in `domain/` changes.** `score_bucket`, `apply_hysteresis`, `why_this_tags`,
`interest_overlap`, `recency_band`, `city_band` are untouched.

---

## D8. The Why-this Tags — the term must be explainable

AD-10's rule: "The tags come from the **same inputs the score used**", because "if a tag
said 'nearby' and the score had not matched the city, the card would be lying."

**A new term in the score with no tag creates a gap.** The score now moves with the
source's reliability, and the card's Why-this tags say nothing about the source. Is that a
lie? **No** — the tags are "category descriptors, not full explanations" (FR-23's
definition of Why-this Tags), and they were never a decomposition of the score. But a
card whose dots dropped because the source's reliability fell, with no tag change, is
exactly the "card's Confidence Pulse jump with no change in the event" the AC is about —
**except that in this case there IS a change in the event's source**, which is the honest
reason.

**Decision:** the tags are **not** extended in this item. Three reasons:

1. **The tag cap is 3** (`RANKING_MAX_TAGS = 3`), and the order is fixed
   (`RANKING_TAG_ORDER`). Adding a "reliability" tag would displace an existing tag for
   every card — including cards whose source is fine. **A tag that appears on some cards
   because their source is bad, and not on others, is worse than no tag**, because the
   absence is unexplained.
2. The Source Badge (FR-23) already tells the user **where** the event came from. The
   source's reliability is a fact about that badge, shown on the source's own panel and
   (per the predecessor item) in the editorial queue.
3. The PRD's own definition of Why-this Tags is "category descriptors, not full
   explanations". The full explanation is the Detail Screen (FR-24) — and the Detail
   Screen reads the **persisted** composition.

**What the Design says instead:** the *inputs* carry the reliability (so the score and any
future explanation can both read it), and the **module docstring** documents the term's
meaning. A future item may add a source-quality tag; this item does not, and says why.

---

## D9. AD-10 — the already-persisted explanations, and `apply_hysteresis`

This is the AC's sharpest requirement:

> **Explanations already persisted are not recomputed (AD-10).** The design states what
> happens to stored `DigestComposition` rows and to hysteresis (`apply_hysteresis`) when the
> weights change, so that no user sees a card's Confidence Pulse jump with no change in the
> event.

### D9.1 What the stored rows are

`DigestComposition` (in `personal`) stores, per card: `score` (the raw `Decimal`),
`bucket` (the 1–5 int), `tags`, `slot`, `composed_at`, `event_version`. These are the
**persisted Relevance Pulse** (AD-10's second kind).

### D9.2 What happens to them: **nothing**

**The stored rows are not recomputed, not rewritten, and not invalidated.**

Why this is not merely "AD-10 says so" but *the only correct answer*:

- **The digest is a dated artifact.** `PulseDigest` is keyed by user and local date
  (`pulse_digest_user_date_uq`). A digest composed yesterday is **yesterday's** card
  set, with yesterday's score. Rewriting it would make a user's archive change under
  them — and the events it points at may no longer even exist.
- **Recomputing would require the old formula.** To recompute a stored row under the
  *old* weights you need the old inputs, which were **not persisted** (only the resulting
  score was). So "recompute under the new weights" would silently rewrite history with
  today's inputs, and "keep it" is the only option that preserves what the user saw.
- **AD-10's whole point** is that an explanation is persisted so that the screen and the
  card cannot disagree. A stored row that is rewritten after the fact is a score computed
  at render time by another name.

**So: stored rows are immutable history.** A card composed under the old weights keeps its
old score and its old dots, and says so by being dated.

### D9.3 What happens to `apply_hysteresis`

**This is the important part, and the answer is: hysteresis is a no-op here, because the
composition always passes `previous_bucket=None`.**

Look at the composition service:

```python
bucket = apply_hysteresis(
    previous_bucket=None,
    previous_score=None,
    new_score=score,
)
```

The docstring says why:

> **The bucket comes from `apply_hysteresis` with no previous value.** The rule lives in
> the domain, and the domain's function *is* `score_bucket* when there is nothing to
> compare against. Passing `None` is not a shortcut — it is what EXPERIENCE.md §4 means by
> "across days, hysteresis resets... No persistent bucket is stored between days".

**So the digest never compares against a previously persisted bucket.** Each composition
is independent, and the stored `bucket` column is the *output* of that composition, not an
input to the next one. **A weight change therefore cannot trip the hysteresis band
between two compositions** — there is no "previous score" carried across the change.

**The consequence the AC is really asking about** — "no user sees a card's Confidence Pulse
jump with no change in the event" — is therefore governed by **when** the composition runs
and **what** it compares against. The honest statement is:

1. **A card already shown keeps its dots** until the next composition (the stored row is
   history).
2. **At the next composition, the dots may change** — because the formula changed. **This
   is a real change, and it is not "with no change in the event": the formula changed.**
   The alternative — freezing the old weights for stored rows and using the new ones for
   new rows — would mean **two formulas in production at once**, with no way for a reader
   to tell which produced which card. That is *worse* than the jump, and it is the thing
   the module's "inert weight" standard is about.
3. **Within a single composition, the weights are consistent** — every card in one digest
   is scored by the same formula. **That is the invariant that must be tested**: a digest
   composed after the change must not mix old and new formulas.

### D9.4 The invariant that is tested

> **Every card in one digest is scored by the same formula, and a digest's three cards
> can be compared against each other.**

The test: compose a digest, assert that the three cards' scores are each reproducible
from the *current* weights via `domain.ranking` (i.e. the persisted score equals what
today's formula gives for today's inputs), and assert that no stored row predating the
change was modified.

### D9.5 The transition, and the disclosure

A weight change is a change users can observe. FR-22's amendment policy is the
disclosure mechanism:

> Amendments are tracked in `docs/adr/` and surfaced in Settings → Privacy → "Ranking
> algorithm version" with the amendment date and a link to the relevant ADR.

**So the ADR is the disclosure.** It records the date from which the new weights apply,
the old and new weight tables, and the substitution map. FR-52's settings surface shows
the current weights and the last-amendment date — and that surface is built by a
different intent (`delivery-and-reminders` deferred `/settings/privacy` to the intent
that owns its backend, per its brief).

**This item's share of the debt:** the ADR and the constants. The settings surface
reading them is the other intent's.

**Is there anything the ranking must do to avoid a confusing transition?** Yes, one thing:
**the ADR's effective date must be the deployment date, and the ADR must say the old
weights applied before it.** A user comparing yesterday's card to today's sees a
difference; the amendment history explains it. That is the whole, and it is exactly what
FR-22 prescribes.

### D9.6 The alternative that was rejected

**Rejected: keeping a "formula version" column on `DigestComposition` and computing
under the version that wrote it.**

That would preserve the old numbers under the old formula — but it needs the old
*inputs* to do it (they were not persisted), it means two formulas ship forever, and it
makes the card's score depend on a hidden version column rather than on the published
formula. **FR-22's promise is that a reader can compute the pulse from the inputs.** A
version column makes the inputs insufficient.

---

## D10. The files that change

| File | Change |
| --- | --- |
| `backend/shared/constants.py` | Five weights; `RANKING_WEIGHT_SUM` over five; `RANKING_WEIGHTS_AMENDMENT`; the comment block rewritten. |
| `backend/domain/ranking.py` | Module docstring; `RankingInputs.source_reliability`; `relevance_score`; `score_slot_2` docstring; `score_slot_3`'s inverted inputs. |
| `backend/apps/ingestion/services/catalog_read.py` | `PublicEventCandidate.source_reliability`; `_to_public_candidate` fills it from the joined `Source`. |
| `backend/apps/personalization/services/digest_composition.py` | `_inputs_for_public` passes the candidate's reliability; `_inputs_for_personal` passes the prior. |
| `backend/tests/shared/test_constants.py` | The weight pin rewritten; the amendment reference pinned. |
| `backend/tests/domain/test_ranking.py` | The proof tests (D5.3); the slot tests; the new field's required-ness. |
| `backend/tests/e2e/mutation_probe_contract_e2e.py` | The probe's mutation string moves to `0.35` (D2.4). |
| `docs/adr/ADR-00XX-ranking-weights.md` | **Created** — the amendment record. |
| `backend/tests/personalization/test_digest_composition*.py` | The query-count bound (D4.3); the wiring test. |

**No migration.** `Source.reliability_score` exists; `DigestComposition` is unchanged;
no column is added anywhere.

---

## D11. The pin test, and "an unreferenced change"

The AC:

> The weight constants are re-pinned in `tests/shared/test_constants.py` with the
> amendment reference. The pin test must still fail on an unreferenced change.

**"Unreferenced" is the operative word.** A test that pins `0.35` fails on a change to
`0.36` — but that failure is not about *reference*, it is about *value*. The AC wants
the failure to be about the **missing amendment reference**.

**The mechanism: the reference is a constant, and it is checked against a real file.**

```python
# shared/constants.py
# The ADR that authorises the current ranking weights. **A weight change without a
# reference here is a CI failure** (FR-22's amendment policy).
RANKING_WEIGHTS_AMENDMENT = "ADR-0025"
```

```python
# tests/shared/test_constants.py
def test_ranking_weights_are_pinned():
    """FR-22: a weight change is a PRD amendment, and the amendment is a file.

    The pin is on the *numbers* and on the *reference*, and the reference is checked
    against the ADR it names — so a weight change without a matching ADR file fails
    even if someone updates the constant in the same commit.
    """
    assert RANKING_WEIGHT_INTEREST == Decimal("0.35")
    assert RANKING_WEIGHT_RECENCY == Decimal("0.20")
    assert RANKING_WEIGHT_CITY == Decimal("0.10")
    assert RANKING_WEIGHT_CONFIDENCE == Decimal("0.10")
    assert RANKING_WEIGHT_RELIABILITY == Decimal("0.25")
    assert RANKING_WEIGHT_SUM == Decimal("1.00")
    assert RANKING_WEIGHTS_AMENDMENT == "ADR-0025"


def test_the_ranking_weights_have_an_amendment_that_says_so():
    """The reference is not a string in a test. It points at a file that exists.

    A constant that names an ADR is only an amendment if the ADR is there. This test
    reads the ADR and checks that it names the weights it claims to authorise — so
    "bump the weight and update the string" is not a way past the pin: the ADR's own
    table has to move too, and the ADR is a document a human reads.
    """
    adr = REPO_ROOT / "docs" / "adr" / f"{RANKING_WEIGHTS_AMENDMENT}.md"
    assert adr.exists(), f"{RANKING_WEIGHTS_AMENDMENT} is named but there is no ADR at {adr}."
    text = adr.read_text()
    for weight in (
        RANKING_WEIGHT_INTEREST,
        RANKING_WEIGHT_RECENCY,
        RANKING_WEIGHT_CITY,
        RANKING_WEIGHT_CONFIDENCE,
        RANKING_WEIGHT_RELIABILITY,
    ):
        assert f"{weight:.2f}" in text, (
            f"{RANKING_WEIGHTS_AMENDMENT} does not mention the weight {weight}. A weight "
            "that moved without the amendment saying so is exactly the failure FR-22 "
            "makes a CI-level failure."
        )
```

**This is the "unreferenced change" guarantee.** Two ways to move a weight, and both
fail:

- **Move the weight, leave the reference.** The number assertion fails.
- **Move the weight, update the reference string.** The ADR-file assertion fails,
  because the new weight is not in the ADR's table — the ADR has to be *edited*, which
  is a human act on a document that is surfaced in Settings (FR-22).

**And the e2e mutation probe** (D2.4) is the third leg: it proves the pin is *real* by
moving a weight and requiring the suite to go red.

### D11.1 The ADR's number

`ADR-0025`. The directory did not exist before this item. **The number was verified against
the corpus**: ADR-0023 and ADR-0024 are already referenced (ADR-0024 is EXPERIENCE.md's
"forthcoming" ADR for the *reliability* formula, a different subject), so 0025 is the
next free one.

---

## D12. The checklist against the AC

| AC | Where | Done |
| --- | --- | --- |
| New weights proposed and justified against FR-22 | D2.1, D2.2 | ☐ |
| States whether it needs a PRD amendment or is a step toward the published weights | D2.2, D2.3 | ☐ |
| The inert-at-launch problem answered explicitly | D3 | ☐ |
| The module docstring updated to match | D3.4, D7 | ☐ |
| `RankingInputs` gains the source's reliability, read through the published `ingestion` read | D4, D4.2 | ☐ |
| No N+1 query; the bound on query count is tested | D4.1, D4.3 | ☐ |
| Slots 2 and 3 updated, or explicitly left reduced with a reason | D5 | ☐ |
| Their docstrings no longer name FR-16 as the missing input | D5.1, D5.2 | ☐ |
| What happens to stored `DigestComposition` rows and to `apply_hysteresis` | D9 | ☐ |
| The weight constants re-pinned with the amendment reference | D2.5, D6, D11 | ☐ |
| The pin test still fails on an unreferenced change | D11 | ☐ |
| The proof: two events from a 0.2 source and a 0.8 source rank in that order | D5.3 | ☐ |
| A test for each slot that uses the term | D5.3 | ☐ |
| A mutation (removing the term) fails them | D5.3 | ☐ |

---

## D13. Open questions carried into the implementation

1. **The ADR number.** `docs/adr/` does not exist. The implementation creates it and
   pins `ADR-0025`.
2. **`reliability_score` vs. the domain's prior.** The stored column is
   `DecimalField(max_digits=4, decimal_places=2)`, so it carries two decimals; the
   domain's `reliability_score(0, 0)` is the prior. Both must land on the *same* `Decimal`
   scale before multiplication, or the product's precision changes. The implementation
   quantises the reliability to the domain's `SCORE_PRECISION` **before** it goes onto
   `RankingInputs`.
3. **The e2e probe's literal.** The probe file's edit string must be updated to `0.35`
   (D2.4) or it silently stops proving anything.

---

## D14. As built — what the implementation changed

The design above was written before the code. Four things changed, and each is recorded
here because each one is a *fact about the implementation* that the design got wrong or
left open.

### D14.1 The ADR number is `ADR-0025`, not `ADR-0023`

The design said "the next free number", assuming `docs/adr/` would have an index. It
does not — the directory did not exist before this item — so the number was verified
against the **corpus** instead: `ADR-0023` and `ADR-0024` are already referenced
elsewhere, and ADR-0024 is EXPERIENCE.md's *"forthcoming"* ADR for the **reliability
formula**, a different subject from the ranking weights. `ADR-0025` is the next free
number, and the ADR is at `docs/adr/ADR-0025.md`.

**The filename is `ADR-0025.md`, not `ADR-0025-ranking-weights.md`.** The pin test
resolves the path as `docs/adr/{RANKING_WEIGHTS_AMENDMENT}.md`, so the file's name is
the reference — and a name with a suffix would have made the test fail on a path that
does not exist. The subject is in the ADR's title, where a reader looks for it.

### D14.2 The observable difference is 0.16, not 0.15

The design said the two scores differ by "exactly `0.25 × (0.80 − 0.20) = 0.15`". That
is the difference in the **raw sum**, and it is right. But the score is quantised to two
decimals *after* the sum, so the two *scores* differ by **0.16** — each is rounded from
its own raw value.

Both numbers are now pinned, because both are true and a reader checking either must
find it: `EXPECTED_RELIABILITY_DELTA = 0.15` is the raw arithmetic, and
`EXPECTED_OBSERVED_DELTA = 0.16` is the observable gap between the two cards. A single
assertion on 0.15 would have been wrong; a single assertion on 0.16 would have looked
like the weight was 0.26.

The prior-only case has the same shape: `0.25 × 0.50 = 0.125`, quantised with
`Decimal`'s default **ROUND_HALF_EVEN**, gives `0.12`, not `0.13`. The test says so.

### D14.3 The service-level proof uses two users, not two compositions

The design's service proof said "compose, change the source's score, compose again, and
compare". That does not work, for two reasons the composition service makes plain:

- **The re-run is a no-op.** A digest already exists for that `(user, local_date)`, so
  the second call writes nothing.
- **The candidate read drops a started event.** Composing at `NOW + 1 day` puts the
  event's start in the past, so the event is not a candidate and the digest is empty.

So the proof composes for **two users at the same `NOW`, against the same event**. Every
input is then identical except the source's reliability, which is exactly the
comparison the domain proof makes — and the difference is that one of them went through
the **database**.

### D14.4 The AD-10 guarantee needed two new architecture guards

The design argued that stored rows are not recomputed and that hysteresis is a no-op
across compositions. **Both arguments were true but neither was enforced**, and an
argument that is not a test is a comment. Two guards now make them real:

- `test_the_composition_never_rewrites_a_stored_explanation` — the composition may
  `bulk_create` its rows and may not `update`, `save`, `update_or_create` or
  `get_or_create` an existing one. A stored Relevance Pulse is history: its inputs
  were never persisted, so it cannot be recomputed under the formula that wrote it.
- `test_the_hysteresis_rule_is_not_a_cross_composition_carrier` — every
  `apply_hysteresis` call in the composition must pass `previous_bucket=None` and
  `previous_score=None` **literally**. If a previously persisted bucket were carried
  forward, a weight change could be absorbed by the no-flicker band, and a card's dots
  would depend on which formula wrote the previous row — two formulas in production at
  once, with no way for a reader to tell which produced which card.

**Both guards were verified against a mutation**, not merely written:
- Inserting an `update()` on the compositions failed the first guard.
- Replacing the `apply_hysteresis` arguments with a carried-forward value fails the
  second.

### D14.5 The N+1 guard was verified against a mutation too

The query-count test compares one candidate's catalog query count with ten candidates'.
A mutation that looked the source's score up per candidate — `Source.objects.get(...)`
inside `_to_public_candidate` instead of reading the joined row — produced **12 queries
for ten candidates against 2 for one**, and the test failed with exactly that message.
The test is the mutation probe for this AC, and it catches the N+1 it was written for.

### D14.6 The PRD carries the amendment, not just the ADR

The code review found that the ADR's header said *"via PRD Amendment A-10"*, and that
**A-10 did not exist in the PRD** — the PRD's highest is A-9, and A-10 is already spoken
for in the UX lineage as the Browse-surface amendment. The reference was a number
invented to fill a slot.

The fix was to make the reference *true* rather than to soften it, and it took two
edits:

- **The PRD's FR-22 section now carries an `Amendment A-10 (2026-11-11)` block**, in
  the same shape as A-9's. It records that **the MVP weights are unchanged** and what
  changes is which term the implementation evaluates for each published component. So
  FR-22's own consequence — *"a weight change without a PRD amendment is a CI-level test
  failure"* — is now backed by an actual PRD amendment rather than by an ADR alone.
- **The ADR's header now says where the amendment lives** — "recorded in the PRD's FR-22
  section, which carries the matching `Amendment A-10 (2026-11-11)` block" — rather
  than implying the PRD already had it.

**Why this matters beyond tidiness.** FR-22's amendment policy has two halves: the
weights are locked, *and* the amendment is tracked where a user can find it. An ADR
that cites a PRD amendment number the PRD has never heard of satisfies neither half —
the lock is real (the pin test) but the disclosure is a dangling pointer.

### D14.7 The candidate DTO's default was a literal where it should have been the prior

`PublicEventCandidate.source_reliability` defaulted to `Decimal("0.50")` — a **second
copy of the prior's value**, in a module whose own docstring says the prior is *"asked
of the domain module, not written here"*, and whose neighbouring helper `_source_reliability`
asks `domain.reliability` for exactly that value.

Two copies of a number is the drift the codebase's own comments rail against (*"two
copies would drift"*). If FR-16's α/β were re-tuned, the helper would follow the
domain module and the default would not, and the disagreement would be invisible until
a card's dots were wrong.

The default is now `reliability_score(0, 0)` — the same domain call the helper makes.
**The asymmetry with `RankingInputs` is deliberate and stays**: `RankingInputs.source_reliability`
has **no** default at all, because a default there would let a construction site forget
the term and score every card as if its source were unscored. The DTO's default is
reachable only when a candidate is built *without* a source's score, and the prior is
the right value for that case.

### D14.8 `test_an_unscored_source_is_at_the_prior` was a false green

The test's name claimed "a source the recompute has not reached contributes the prior,
not a zero", and its assertions were `score > Decimal("0.00")` and
`reliability_score(0, 0) == Decimal("0.50")`. **The first is true of any reliability
value, including zero**, because four other terms contribute; the second asserts a
*domain constant*, not the composition's behaviour.

**It was verified, not assumed.** Replacing the prior with `Decimal("0.00")` in
`_source_reliability` left all 63 tests in the file green — the mutation passed. So the
test proved nothing about the thing it was named for.

The rewrite makes the assertion **relative**, which is the only shape that can fail: the
same event is composed for three users, with its source's score at *nothing*, at *0.00*
and at *0.80* in turn, and the unscored card must fall **strictly between** the other
two. Only a value that really is the prior sits there — a zero would tie the first and
a 1.00 would tie the second. The same mutation now fails with a message that says
which comparison broke.

**The first attempt at the rewrite was itself wrong**, and the failure is worth
recording. It built *three separate events*, one per source score — and the
composition's three slots hold three *different* events, so `compositions[0]` was not
the event under test. The "worst" card came back scoring exactly the prior. The fix was
the shape the sibling test already used: **one event, three users**, changing only the
source's score between compositions.

### D14.9 The composition's `source_reliability` is read, never written

The ranking is a **consumer** of FR-16's score, and a consumer that could also write it
would make the score's value depend on whether a digest had been composed — and would
race the recompute that owns the column.

**The first version of the guard was a name match, and it failed on correct code.**
The composition writes `source_reliability=reliability_score(0, 0)`: a *keyword
argument* whose value happens to be a function named `reliability_score`. A substring
check on the name read that as a write of the column. This is the name-based-wall
failure the work item's own Technical Notes warn about, arriving from the other
direction — a wall that fails on the code it was written to permit.

So the guard is **AST-based** and looks for exactly two shapes: an **attribute
assignment** (`source.reliability_score = ...`) and a **write call naming the column**
(`update(reliability_score=...)`, `setattr(source, "reliability_score", ...)`). It
lives in `tests/architecture/test_ad10_explanation_persistence.py`, beside the other
AD-10 guards, and it was verified against a mutation: a planted assignment failed it
with the offending line and column named.
