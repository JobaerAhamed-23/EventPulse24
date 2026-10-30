---
run: run-eventpulse24-021
work_item: digest-composition-models
intent: pulse-digest-and-trust
generated: 2026-10-30
status: passing
---

# Test Report: The Ranking Domain (slots, Relevance Pulse, buckets, hysteresis)

> **This report covers two work items.** The first section below is
> `digest-ranking-domain` (complete). The second, further down, is
> `digest-composition-models` — the current item.

The ranking core decides what a user sees on a Pulse card and how many dots it gets.
Those are the two claims the user reads as *about themselves*, so the rules that produce
them are pinned at their boundaries rather than sampled. A ranking score that is
0.8499999 instead of 0.85 is not a rounding detail — it moves a card between the four-dot
and five-dot bucket and the user cannot tell why.

Every test in this report was checked for the ability to fail: the boundary cases sit
*at* the published value, not near it, and the negative cases assert the opposite
outcome.

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Item-scoped | 75 | 0 | 0 | 100% (`domain/ranking.py`) |
| Constants-pinning | 4 | 0 | 0 | — |
| **Total (whole backend)** | **3411** | **0** | **0** | **99.07%** |

The whole backend suite is **3411 passed, 0 failed**, with **100.00% on `domain/`**
(the AD-2 purity gate) and **171 files at 100%**. The item-scoped 75 are a subset.

> The earlier scoped run reported `domain/` at 99%, with `domain/address_policy.py`
> lines 60–64 uncovered. That was an artifact of running `pytest tests/domain/`
> alone: `address_policy.py` is exercised by `tests/adapters/test_crawl_address_policy.py`
> and `tests/e2e/test_loopback_allowance.py`, neither of which is under `tests/domain/`.
> The full-suite run puts `domain/` back at **100%**. No code changed to make that
> number true.

> **These figures are the post-review ones.** The code review found a wrong chip count
> in the module's prose, a duplicated constant and an unused exported dataclass. See
> [§10](#10-what-the-code-review-changed) and the [review report](review-report.md).

### The item-scoped files, and what each is for

| File | Tests | What it proves |
|------|-------|----------------|
| `backend/tests/domain/test_ranking.py` | 75 | Every bucket boundary, the hysteresis rule, all three slots, the tag derivation |
| `backend/tests/shared/test_constants.py` | 4 (added) | The weights, boundaries, hysteresis delta and tag cap are pinned |

## Test Commands

```bash
# The item's own tests
cd backend
uv run pytest tests/domain/test_ranking.py tests/shared/test_constants.py -v

# The whole backend suite with coverage
uv run pytest --cov --cov-report=term-missing

# The domain purity gate
uv run coverage report --include='domain/*' --fail-under=100

# The structural gates
uv run ruff check .
uv run ruff format --check .
uv run lint-imports
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
```

## Results

```
75 passed  (tests/domain/test_ranking.py)
 4 passed  (the new tests in tests/shared/test_constants.py)
3411 passed, 0 failed  (whole backend)
Coverage: 99.07% overall, 100.00% on domain/
Contracts: 19 kept, 0 broken
System check identified no issues (1 silenced).
No changes detected  (makemigrations --check --dry-run)
```

## 1. The bucket boundaries are exact, and the lower bucket wins

FR-22 publishes four boundaries: 0.85 → 5 dots, 0.65 → 4, 0.45 → 3, 0.25 → 2. It also
publishes the rule that **an exact boundary takes the lower bucket**. Both halves are
pinned, at the boundary and one hundredth either side of it.

| Raw score | Bucket | Why |
| --- | --- | --- |
| `0.8500` | 4 | Exact boundary → lower bucket |
| `0.8501` | 5 | Strictly above 0.85 |
| `0.8400` | 4 | Below 0.85 |
| `0.6500` | 3 | Exact boundary → lower bucket |
| `0.6501` | 4 | Strictly above 0.65 |
| `0.4500` | 2 | Exact boundary → lower bucket |
| `0.4501` | 3 | Strictly above 0.45 |
| `0.2500` | 1 | Exact boundary → lower bucket |
| `0.2501` | 2 | Strictly above 0.25 |

**Why `Decimal` and not `float`.** The test that justifies the whole design decision is
`test_score_bucket_is_never_a_float`, and it documents the failure in *both*
directions:

- `Decimal(0.85)` is `0.85000000000000002220446…`, which is **less than**
  `Decimal("0.85")` — so it lands in bucket 4 where the exact value lands in 5.
- `Decimal(0.65)` and `Decimal(0.45)` are **greater than** their exact counterparts —
  so they land one bucket **too high**.

A float is not a near-miss for a boundary; it is a coin flip, and the coin lands wrong
in whichever direction the binary representation happens to fall. The implementation
compares with `Decimal` throughout, and `relevance_score()` quantizes to two places
before bucketing so a score is the same number the card will display.

## 2. The hysteresis rule holds the bucket, but only within 0.10

EXPERIENCE.md: the bucket holds unless the raw score moves by **at least 0.10**, per
event, per day. The mockup's `±0.02` does not govern — the implementation follows the
0.10 rule and the constant's docstring records the deviation.

| Previous | New | Δ | Result |
| --- | --- | --- | --- |
| 0.83 → bucket 4 | 0.86 | 0.03 | **Holds at 4** |
| 0.83 → bucket 4 | 0.97 | 0.14 | Moves to 5 |
| 0.83 → bucket 4 | 0.78 | 0.05 | **Holds at 4** (falling) |
| 0.83 → bucket 4 | 0.60 | 0.23 | Moves to 3 (falling) |
| — | 0.83 | — | First composition maps directly to 4 |
| — | 0.30 | — | First composition maps directly to 2 |

The worked example from EXPERIENCE.md (0.83 → 4, 0.86 → still 4, 0.97 → 5) is
reproduced exactly. The **falling** direction is tested separately from the rising one,
because a rule that only holds upward is a different rule.

**Across days the rule resets.** The caller passes `previous_bucket=None` and the score
maps directly. The reset is the caller's decision, not a clock read inside the domain —
`domain/` has no clock, so a day boundary cannot silently change a bucket.

## 3. The reduced formula is computable by hand

The published FR-22 formula has two terms with no input in this codebase
(`source_reliability` → FR-16; `novelty_vs_exploration` → FR-25), so the four surviving
inputs are redistributed to still sum to 1.0:

```
relevance_score = 0.45 × interest_overlap
                + 0.25 × recency
                + 0.20 × city_match
                + 0.10 × confidence
```

`test_relevance_score_is_the_weighted_sum` computes this by hand in the test and
compares. The weights are pinned in `tests/shared/test_constants.py`, so a weight that
moves without a PRD amendment fails CI — which is what FR-22 requires.

**Clamping.** A score above 1.0 clamps to 1.0 and below 0.0 clamps to 0.0. The bucket
mapper would survive a bad score (everything above 0.85 is bucket 5 either way), but
the persisted score is displayed to the user, so it has to be a number the formula can
actually produce.

## 4. Interest overlap normalises against the *maximum*, not the user's own count

A user who picked 2 chips and a user who picked 3 chips both get a comparable
"how much of this event matches me" number. Normalising by the user's own count would
make a sparse user look maximally interested in everything they did pick. The divisor is
`MAX_INTEREST_PICKS` — **3**, because FR-1 says "up to 3 picks" and a fourth is refused,
not silently dropped.

- 0 chips → `0.00` (nothing matched)
- 1 of 3 → `0.33`
- 2 of 3 → `0.67`
- 3 of 3 → `1.00`
- Duplicate chips on the event are counted once.

## 5. Recency and city bands, with the boundaries pinned

**Recency** (bands at 1, 3, 7 and 14 days): within a day → `1.00`; within three days →
`0.75`; within a week → `0.50`; within a fortnight → `0.25`; later → `0.00`. Each
band's exact edge is tested, because "within three days" at exactly 72 hours is a
boundary the implementation has to answer.

**City**: same city → `1.00`; same country, different city → `0.50`; other →
`0.00`. Comparison is case-insensitive, and an empty city or country is handled
explicitly rather than raising.

**The city term is additive, not a multiplier.** FR-5's slot formulas multiply by
`geographic_distance_factor`, which would zero out every event outside the user's city —
so a local user would never see anything from elsewhere, and a travelling user would
see a digest of zeros. The design doc records this as D2. The consequence is tested:
an event in another country still scores on its other three terms.

## 6. The three slots

| Slot | Rule | Test |
| --- | --- | --- |
| Slot 1 | The standard score; a personal event inside 48h adds `+0.20`, clamped to 1.00 | Personal event inside the window boosts; one outside it does not; the boost cannot push past 1.00 |
| Slot 2 | The standard score | Slot 2 equals `relevance_score()` exactly |
| Slot 3 | The standard score with the **interest term inverted** (`1 − overlap`) | An event the user's signals would *not* have picked outranks one they would have |

**Slot 3 is a deviation from FR-5, and says so.** FR-5 publishes
`… × (1 − normalized_popularity)` — an anti-popularity factor. There is no popularity
signal in this codebase: no engagement, no attendance count, no save count. The
inverted-interest term is the closest honest analogue, and the module's docstring says
plainly that **this is not the same quantity**. A user who can see the formula should be
able to see the deviation too.

## 7. Tags are keys, capped at three, in a fixed order

`domain/` knows nothing about rendering. A tag is a *key* (`nearby`, `tonight`,
`tomorrow`, `weekend`, `saved`, `discovery`, `matches_<chip>`), and the presentation
edge decides how to draw it. That separation is what lets the domain stay pure.

- The cap is three, and the order is fixed: `discovery`, `nearby`, `tonight`,
  `tomorrow`, `weekend`, `saved`, then chip matches.
- A chip tag is the one that falls off the cap — it never displaces a fixed tag.
- Slot 3's `discovery` tag is mandatory and chip tags never appear on it.
- `saved` appears only for a saved event.

**A real bug this suite caught.** The first implementation ordered the tags by walking
the fixed list and then appending "anything left over" — but the leftover loop
explicitly excluded chip tags, and chip tags were not in the fixed list. The result was
that `why_this_tags()` returned `()` instead of `('matches_arts_culture',)` for an
event that matched a chip. The test
`test_tags_include_a_chip_match` caught it; the loop was rewritten to append chip tags
after the fixed ones, with a comment saying why that ordering.

## 8. "Tonight" is decided in the event's own timezone, on the event's own day

This is the rule most likely to be got wrong, and it is pinned across two DST
transitions.

- **The event's zone, not the server's.** A New York event at 20:00 is "tonight" in
  New York even when the digest is composed in Berlin.
- **The event's day, not the user's.** An event on Berlin's 15th at 23:30, composed on
  Berlin's 14th, is **tomorrow** — it is not tonight. This distinction has its own test
  (`test_an_event_on_the_events_next_day_is_tomorrow_not_tonight`), because the
  near-miss version of it — "tonight" for an event later the same evening — is the one
  that reads as obviously correct and is therefore the one most likely to be wrong.

**DST transitions:**

| Case | Zone | Date | Asserted |
| --- | --- | --- | --- |
| Spring forward | `America/New_York` | 2026-03-08 | The skipped hour does not produce a wrong local day |
| Fall back | `Europe/Berlin` | 2026-10-25 | The repeated hour does not produce a wrong local day |

**Unknown zone falls back to UTC**, mirroring `domain/event_fit.py` rather than
raising in the middle of a digest composition.

## 9. The domain stays pure, and the whole backend still passes

`domain/ranking.py` imports only the standard library plus `shared.constants` and
`shared.ids`. The import-linter contract **AD-2 domain is pure** is **kept**, along
with all 19 contracts (0 broken). `domain/ranking.py` at **100%** (135/135 statements).

The full backend suite is **3405 passed, 0 failed**. The pre-existing suites — identity,
calendar, ingestion, personalization, the architecture contract tests — are unchanged and
still pass.

## What this item does not test

- **The digest composition itself.** The ranking functions are pure and tested alone,
  but nothing here composes a digest, persists one, or checks that a card's persisted
  score matches what the renderer displays. That is `digest-composition-service`.
- **The persisted-vs-recomputed equality AD-10 demands.** The design decision D9 says the
  score and bucket are both persisted and re-composition for the same
  `(user, local_date)` is a no-op. That guarantee is the composition service's to keep,
  and it will need a test of its own there.
- **The candidate read.** Matching an event to the user's chips happens in the
  candidate read (AD-9: text over untrusted content), not in `domain/`. This suite tests
  the overlap *given* the chips, not the extraction of the chips from the event.

## 10. What the code review changed

The code review found three things the tests could not, because a test asserts behaviour
and none of these were behaviour:

1. **The module's prose claimed "ten chips".** `MAX_INTEREST_PICKS` is **3** — FR-1 says
   "up to 3 picks", a fourth is refused. The code divided by the right constant; the
   *explanation* of it was wrong, in the module docstring and in this report. A reader
   would have computed the interest term wrongly by hand, which is the one thing this
   module exists to let them do. Fixed in both places, and two tests were added:
   `test_interest_overlap_is_divided_by_the_maximum_picks_constant` pins the divisor
   against the constant, and `test_a_one_chip_user_does_not_outrank_a_three_chip_user`
   pins the reason the divisor is the maximum and not the user's own count.

2. **`RANKING_TAG_CHIP_PREFIX_SERENDIPITY` was a duplicate constant.** It was
   `"discovery"`, identical to `RANKING_TAG_DISCOVERY`, and nothing referenced it. The
   rule it documented — Slot 3 shows `discovery` and never a chip tag — is enforced in
   `why_this_tags()` and tested. Removed.

3. **`SlotScore` was an exported dataclass nothing used.** It was not in the design
   doc's module surface (D11). The composition service will define its own candidate
   structure; a dataclass here would have been a second, competing shape. Removed.

## Verdict

**Passing.** 75 item-scoped tests and 4 constants-pinning tests, all green, with
`domain/ranking.py` at 100% and every architectural gate intact.

---

# Work Item: `digest-composition-models` — `PULSE_DIGEST` and `DIGEST_COMPOSITION`

Two tables in the `personal` schema, written only by `personalization` (AD-16). The
parent row is one user's digest for one local day; the child row is one event's
persisted explanation within it. AD-10's promise — the card, the detail screen and the
email all read the *same* row, and none of them recomputes an explanation — is only
true if the row exists and cannot change underneath them. So this item's tests are
about **the rules the database holds**, not about the behaviour of a service that
does not exist yet.

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Item-scoped | 79 | 0 | 0 | 99% (`test_digest_models.py`) |
| **Total (whole backend)** | **3471** | **0** | **0** | **98.95%** |

The item-scoped 79 are 46 in `test_digest_models.py`, 20 in `test_model_structure.py`
(the shared structural file, 3 of them new) and 13 in `test_grants.py` (3 of them new).

> **These are the pre-review figures.** The code review for this item has not yet run;
> see [§11](#11-what-the-code-review-changed) below once it has.

### The item-scoped files, and what each is for

| File | Tests | What it proves |
|------|-------|----------------|
| `backend/tests/personalization/test_digest_models.py` | 46 | The fields, the constraints, the immutability, and the indexes |
| `backend/tests/personalization/test_model_structure.py` | 20 (3 new) | No relation crosses the AD-3 wall; every relation is held by value |
| `backend/tests/personalization/test_grants.py` | 13 (3 new) | The runtime role may not rewrite or delete a composition, and the migration's own assertion is not decorative |

## Test Commands

```bash
cd backend
uv run pytest tests/personalization/test_digest_models.py \
               tests/personalization/test_model_structure.py \
               tests/personalization/test_grants.py -v

uv run pytest --cov --cov-report=term
uv run coverage report --include='domain/*' --fail-under=100
uv run ruff check .
uv run ruff format --check .
uv run lint-imports
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
```

## Results

```
79 passed  (the three item-scoped files)
1272 passed  (tests/architecture/ + tests/personalization/)
3471 passed, 0 failed  (whole backend)
Coverage: 98.95% overall, 100.00% on domain/
Contracts: 19 kept, 0 broken
System check identified no issues (1 silenced).
No changes detected  (makemigrations --check --dry-run)
All checks passed!  (ruff check / ruff format --check)
```

## 1. The immutability is enforced twice, at two levels, and the tests know the difference

AD-10: "A `DIGEST_COMPOSITION` row is **immutable**." Two guards enforce it, and they
fire at different layers:

| Guard | Layer | What it raises |
|---|---|---|
| `AppendOnlyModel.save()` / `.delete()` | Python, in the ORM | `AppendOnlyViolation` (a **`RuntimeError`**) |
| `personal.forbid_history_mutation()` trigger | SQL, in the database | `psycopg.errors.RestrictViolation` |

**The trap this suite exists to close.** A test that asserts immutability by expecting
`IntegrityError` would pass **against a table with no trigger at all**, because the
Python guard fires first and swallows the attempt before Postgres is ever consulted.
So the tests assert `AppendOnlyViolation` at the ORM level *and* `RestrictViolation` at
the SQL level — the second one bypasses the ORM entirely, so it is the only thing that
proves the trigger exists.

The trigger test uses `SELECT ... FOR UPDATE` inside a transaction, because a bare
`UPDATE` that the trigger rejects aborts the surrounding transaction and takes the
connection with it.

**The existing trigger function was reused, not redefined.** `personal.forbid_history_mutation()`
was installed by `personalization/migrations/0001_initial.py` and has **no `TG_ARGV[0]`
branch** — which is exactly right for a table where nothing is settable after insert.
The catalog copy takes an argument naming the one column that may go from NULL to a
value; `DigestComposition` has no such column, so no argument is passed. This is the
first non-audit `AppendOnlyModel` in the `personal` schema.

## 2. The retention category is the one that keeps AD-10's promise

D4 records the gap honestly: **no source states a retention window for digest
compositions.** PRD §10.2 covers preference signals (12 months rolling), email events
(90 days) and audit logs (24 months), and says nothing about this table.

| Category | Window | Effect on "the Detail Screen reads the most recent composition" |
|---|---|---|
| `PREFERENCE_SIGNALS` | 12 months rolling | **Breaks it** — the explanation vanishes while the user is still looking at the event |
| `ACCOUNT_CONTENT` | While the account is active | **Keeps it** |

`ACCOUNT_CONTENT` is chosen, and the test pins it
(`test_digest_composition_is_retained_as_account_content`). A digest composition is
*output* — what this user was shown and why — while `Interest`,
`OnboardingProgress` and `DigestPreference` are *inputs* and sit in
`PREFERENCE_SIGNALS`. `PulseDigest` takes the same category, because a digest row
without its compositions is meaningless and the two must be purged together.

**The gap is recorded, not resolved.** The retention sweep that would enforce a window
is not built. The category here is a declaration, and when the sweep is built it must
treat `ACCOUNT_CONTENT` as "while the account is active" — the only reading under which
AD-10's promise holds.

## 3. Every relation is held by value, including the parent

The strongest structural claim in this item is negative: there is **no foreign key
anywhere on either table**. `tests/personalization/test_model_structure.py` gained
`PulseDigest` and `DigestComposition` to its `MODELS` list, and three new tests:

| Test | What it proves |
|---|---|
| `test_digest_composition_holds_its_parent_digest_by_value` | `digest_id` is a `UUIDField` with `remote_field is None` — there is nothing for a cascade to hang from |
| `test_digest_composition_holds_its_event_by_value` | `event_id` is a `UUIDField`, not a relation — the AD-3 wall |
| `test_pulse_digest_holds_its_user_by_value` | `user_id` is a `UUIDField`, the OQ-8 pattern |

`PulseDigest` is in the **same schema** as `DigestComposition`, so a foreign key there
would have been legal to write and would have cascaded the digest's deletion into its
children — and AD-10 says a composition is immutable and must outlive its day. Holding
`digest_id` by value means the retention sweep can purge a digest's compositions in an
order the application chose, rather than an order the database chose.

`user_id` is denormalised onto the child so the Detail Screen's "most recent
composition for this `(user, event)` pair" is **one indexed lookup**, not a join
through the parent.

## 4. The check constraints hold the shapes, at the database

Three constraints, and each is tested with the row that violates it:

| Constraint | Rule | The violating row the test builds |
|---|---|---|
| `digest_composition_bucket_ck` | `1 <= bucket <= 5` | bucket `0` and bucket `6` |
| `digest_composition_kind_shape_ck` | public ⇒ has a version **and** a badge; personal ⇒ has **neither** | a public composition with no badge, and a personal one with a badge |
| `digest_composition_digest_event_uq` | no duplicate event in one digest | the same `(digest_id, event_id)` twice |

The kind-shape constraint is the one worth reading twice, because it encodes AD-10's
two explanation kinds in a single expression: a **public** composition carries the
catalog `event_version` and a `source_badge`; a **personal** one carries neither,
because a personal event did not come from a source at all and has no catalog version.

**`event_kind` is stored, not derived.** A personal event is a row in `personal`, not
in `catalog` — so it has no catalog id, no source and no version. Without the stored
kind, the two would be indistinguishable.

**One note on the check constraint's implementation.** The constraint is written with
**literal strings** (`"public"` / `"personal"`) rather than `EventKind.PUBLIC`. This is
not a stylistic choice: `Meta` is a *sibling* scope of the enum class, so
`DigestComposition.EventKind.PUBLIC` raises `NameError` (the class is not bound while
its own body executes). A test
(`test_digest_composition_kind_values_match_the_constraint`) pins the literals to the
enum, so the two cannot drift apart.

## 5. The runtime role may not rewrite a composition — and the migration says so out loud

AD-16 gives `personalization` total write ownership; the runtime role `ep_personal` is
not the owner. On an append-only table the runtime role gets `INSERT` and `SELECT` and
**not** `UPDATE` or `DELETE`.

The subtlety is that **a `REVOKE` by a non-owner merely warns.** Postgres does not
raise; it prints a notice and the privilege stays. A migration that relied on the
`REVOKE` alone would ship a table the runtime role could still rewrite, and CI would
be green. So the migration carries its own assertion:

```sql
DO $$
BEGIN
  IF has_table_privilege('ep_personal', 'personal.personalization_digestcomposition', 'UPDATE')
     OR has_table_privilege('ep_personal', 'personal.personalization_digestcomposition', 'DELETE') THEN
    RAISE EXCEPTION 'ep_personal privileges on the append-only tables were not applied';
  END IF;
END
$$;
```

**The test proves the block is not decorative.** It grants `UPDATE, DELETE` back to
`ep_personal`, runs the block, and asserts the `RaiseException` — inside
`transaction.atomic(using=PERSONAL)`, so the failed block rolls back and the granted
privilege does not leak into the rest of the suite. The `GRANTS` constant is
module-level in the migration file so the test can import it by name.

**The denials are asserted as `InsufficientPrivilege`, not as a `RestrictViolation`.**
That distinction matters: the trigger's `RestrictViolation` would *hide* a missing
`REVOKE`, because the trigger fires first and the test would pass for the wrong reason.
Asserting the exact error class is what makes the test prove what it claims to.

**`PulseDigest` is deliberately *not* in the revoked list.** It is not append-only — it
is a fact about a day, and the guarantee that matters for it is its own unique
constraint. The runtime role's `UPDATE` on it is what lets a correction land. The
immutability AD-10 demands is of the *composition*, and that is the table guarded.

## 6. The indexes are the ones the Detail Screen and the digest read need

Two indexes, each with a named reader:

| Index | Reader | Test |
|---|---|---|
| `digest_comp_user_event_idx` — `(user_id, event_id, -composed_at)` | The Detail Screen: the most recent composition for a `(user, event)` pair | The `EXPLAIN` plan is walked and asserted to have no `Seq Scan` and to use this index |
| `digest_comp_digest_slot_idx` — `(digest_id, slot)` | The digest read: all of one user's compositions | The index exists and the read path is available |

The `composed_at` is **descending**, so the most recent row is the first one the index
yields — the lookup does not sort a result set to find the newest.

**A note on how the index test was written.** The first version asserted that the
`EXPLAIN` plan's *root* node was an `Index Scan`. It is not: the root is a `Limit`.
The plan is `Limit → Index Scan`, and a test that only looks at the root would fail
against a perfectly good plan. The test now walks the plan tree and asserts that no
`Seq Scan` appears anywhere in it, and that the index name appears in it.

## 7. The slot order lives once, and it is not alphabetical

The digest read returns compositions "in slot order" — must-know, nearby,
serendipity. That is a fixed order of three values, and it is **not** alphabetical
(`must_know < nearby < serendipity` happens to be alphabetical, which is exactly the
kind of coincidence that makes a test wrong for the right reason).

The index `(digest_id, slot)` gives the database its *alphabetical* order of the slugs,
which is not the slot order. So the order is defined **once**, as the declaration order
of the `Slot` `TextChoices` class, and exposed as a module-level constant
(`DIGEST_SLOT_ORDER`) that the read sorts by.

**`DIGEST_SLOT_ORDER` is at module level, not inside the enum class.** A first attempt
put `ORDER = (MUST_KNOW, NEARBY, SERENDIPITY)` inside the `Slot` class; because a
`TextChoices` member holds a *scalar*, that tuple was read as an enum member and the
class failed to construct with `TypeError: decoding str is not supported`. The order is
a tuple of three values, and it lives beside the class that defines them.

The sort is done in Python rather than in SQL: three rows cost nothing to sort, and the
order is then defined by one constant rather than by a collation or a `CASE`
expression. Same reasoning as `apps/ingestion/services/preview_read.py`'s city list —
"a database's `ORDER BY` on text is a locale collation".

## 8. `__str__` names the slot and the bucket, and nothing else

AD-13: no PII in what a log line or an admin list column shows. AD-09: the event's
content is untrusted source text.

```python
def __str__(self) -> str:
    return f"{self.slot} digest composition, bucket {self.bucket}"
```

**No event title, no venue, no tag labels.** The event's content is the thing the
composition *explains*; putting it in `__str__` would put untrusted source text into
every log line that mentions the row. Django's `Model.__repr__` delegates to `__str__`,
so `repr()` is safe for free.

`PulseDigest.__str__` names the local date and whether the digest is empty — a local
date is not PII, and it is already on the row.

Both are tested, including a test that builds a composition whose event has an
untrusted title and asserts the title does **not** appear in `str()` or `repr()`.

## 9. The empty digest is stored, not derived

FR-8's empty digest is "a real digest with zero compositions" — a fact the user is
shown ("nothing near you today"). That is different from "we never composed for this
user today", which is a job that has not run.

A single model with nullable columns cannot tell those apart. A parent row with zero
children can: the `PulseDigest` exists, it has no compositions, and that is the empty
state. No `PulseDigest` at all means the job has not run.

`PulseDigest.is_empty` is a **stored flag**, not a derived one — a reader does not have
to count children to know whether this was a deliberate empty digest or a composition
that happened to fail. The flag is set at composition time and, like the digest row
itself, never changes.

**`PulseDigest` has no `updated_at`.** A digest is a fact about a day, not a mutable
record, and a row whose `updated_at` can change invites the question of what changed.
It carries `created_at` only.

## 10. The write-ownership guard did its job

The AD-16 architecture test (`tests/architecture/test_write_ownership.py`) failed on
the two new tables with:

```
AssertionError: tables with no owner in TABLE_OWNERS:
['personalization_digestcomposition', 'personalization_pulsedigest'].
Every table needs an owner; an unowned table is one nobody is responsible for.
```

That is the guard working exactly as designed — a new table is unowned until someone
names its owner. `personalization` owns both: they are the per-user half of AD-10's two
explanation kinds, while `ingestion` keeps Event Fit.

## 11. What the code review changed

*To be filled in by the code-review step for this item.*

## What this item does not test

- **How a composition is written.** The composition service owns the write: it reads
  both sides of the wall, scores with `domain/ranking.py`, assigns the slots and
  writes the rows. This item ships the tables it writes into and the rules the
  database holds.
- **That the persisted score equals what the renderer shows.** That is the composition
  service's to keep, and it will need a test of its own there.
- **The previous day's bucket, for the hysteresis comparison.** It is the previous
  day's composition row for the same `(user, event)` — which is exactly why these
  rows outlive their day. The lookup is the composition service's; this item makes it
  possible, with the index above and the retention category that keeps the rows around.
- **The digest's card count.** "Exactly 3 cards" is the composition service's rule.

## Verdict

**Passing.** 79 item-scoped tests, all green, with every architectural gate intact and
the whole backend at 3471 passed, 0 failed.
