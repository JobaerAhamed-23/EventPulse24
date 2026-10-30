---
run: run-eventpulse24-021
work_item: digest-composition-models
intent: pulse-digest-and-trust
mode: validate
checkpoint: plan
approved_at: 2026-10-30T13:20:00Z
---

# Implementation Plan: `PulseDigest` and `DigestComposition`

## Approach

Two models in `apps/personalization/models.py`, in the `personal` schema, written only by
`personalization` (AD-16).

This is the first item that puts the ranking core's output somewhere durable. The
ranking module computes a score; this item decides where that score is *kept*, and AD-10
says it is kept in exactly one place and read by three surfaces:

> A **Pulse Card is a projection of it**, never a stored entity.

So the model is not a cache of a decision — it **is** the decision, and the card is a
view of it. That is why the model is append-only: a row that could be rewritten would
let the card and the detail screen disagree about why an event was shown.

The design work is in three places:

1. **What the retention category is** (D4). AD-15 requires one, no source states a
   window, and the choice is not cosmetic: `PREFERENCE_SIGNALS`'s 12-month window would
   delete an event's only explanation while the user is still looking at the event,
   breaking AD-10's "most recent composition" promise. `ACCOUNT_CONTENT` is the only
   category under which that promise holds.
2. **Whether `digest_id` is a foreign key** (D2). It is not — every relation in this
   codebase is held by value (OQ-8), and a FK would cascade a digest's deletion into
   its children, which is exactly what "immutable and retained per AD-15" forbids.
3. **Where the slot order lives** (D12). Not in the index — a `CHAR` index sorts
   alphabetically, not in slot order — and not in a `CASE` expression. It lives once, as
   the declaration order of the `Slot` enum.

Everything else follows the house patterns the research turned up: `TextChoices` nested
in the model, `retention_category` declared before the fields, `user_id = UUIDField()`
by value, `Meta` with `constraints` then `indexes`, and for the append-only table
`Meta.base_manager_name = "objects"`.

**Design doc**: `.specs-fire/intents/pulse-digest-and-trust/work-items/digest-composition-models-design.md`
(decisions D1–D12).

## Files to Create

| File | Purpose |
|------|---------|
| `backend/apps/personalization/migrations/0007_pulsedigest_digestcomposition.py` | The two tables, the append-only trigger, and the runtime grants. |
| `backend/tests/personalization/test_digest_models.py` | The constraints, the immutability, the retention declaration, the decimal round-trip and the most-recent lookup. |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/apps/personalization/models.py` | The two models, their enums, their constraints and their indexes. |
| `backend/tests/personalization/factories.py` | A factory per model, on the `PersonalFactory` base (`database = PERSONAL`, `skip_postgeneration_save = True`). |
| `backend/tests/personalization/test_model_structure.py` | Both models join the "no relation field" guarantee — they pass it *because* every relation is by value. |

## Tests

| Test File | Coverage |
|-----------|----------|
| `backend/tests/personalization/test_digest_models.py` | Both unique constraints by `IntegrityError`; the bucket check; the `event_kind`/`event_version`/`source_badge` agreement check; immutability at the ORM level (`AppendOnlyViolation`, a `RuntimeError` — **not** an `IntegrityError`) and at the SQL level (`RestrictViolation`, the trigger's ERRCODE); the retention category being declared; `Decimal` round-tripping at two places; the most-recent-composition lookup returning the newest row; `__str__` leaking no event content; the slot order. |
| `backend/tests/personalization/test_model_structure.py` | Both models declare no relation field. |

**The immutability test is the one that can pass for the wrong reason.** `AppendOnlyModel`'s
Python guard fires before the database trigger, so a test that expects `IntegrityError`
would pass against a table with no trigger at all. The test asserts the ORM guard's
`AppendOnlyViolation` *and* the trigger's `RestrictViolation` separately, in the style
of `tests/personalization/test_triggers.py`.

## Technical Details

**No clock read, no Django-in-`domain/` problem.** These are ordinary Django models in
an ordinary app; the purity rule applies to `backend/domain/`, which this item does not
touch.

**The score is `numeric(3,2)`.** `max_digits=3, decimal_places=2` gives exactly `0.00`–
`1.00`, which is the range `domain/ranking.py` produces. The bucket boundaries in FR-22
are exact, so the stored value is an exact decimal and never a float.

**`append_only_mutable = frozenset()`** — the inherited default, because nothing about a
composition becomes known later. This differs from `EventStateChange`, whose
`propagated_at` goes NULL→value once.

**The `personal` schema's `forbid_history_mutation()` is reused as-is.** It was installed
by `personalization/migrations/0001_initial.py` and has no `TG_ARGV[0]` branch, which is
exactly right for a fully immutable table. The new migration adds the trigger and
nothing else; the function is not redefined.

**The grants are asserted, not assumed.** A `REVOKE` by a non-owner merely *warns*, so
the migration carries the `DO $$ … has_table_privilege … RAISE EXCEPTION` block — and
the `GRANTS` constant is module-level and named, so a test can import it and assert the
block fails when the REVOKE is missing. That is the pattern
`tests/personalization/test_grants.py` already uses for the audit table.

**The `__str__` names the slot and the bucket and nothing else.** The event's title is
untrusted source text; putting it in `__str__` would put it in every log line and every
admin list column (AD-9, AD-13).

---

## Work Item: digest-ranking-domain (completed)

*Retained from the previous item of this run.*

### Approach

Build `backend/domain/ranking.py` — a pure, stdlib-only module holding the Relevance Pulse
score, FR-22's bucket mapping, the hysteresis rule, A-2's three slot scores and the Why-this
Tag derivation.

The module is the honesty of the intent, so the design work is in the **formula reduction**:
FR-22 publishes four terms, two of which have no input in this codebase. The design doc
(`digest-ranking-domain-design.md`) reduces the formula to the four inputs that do exist
(interest-chip overlap, recency, extraction confidence, city band), redistributes the weights
so they still sum to 1.0, and names every omitted term and the FR that will supply it.

Everything is `Decimal`, never float — FR-22's exact-boundary rule (0.850 → 4 dots) cannot be
honoured with binary floats.

The weights live in `shared/constants.py` beside the confidence gates, and a test pins them
there, so a weight change without a PRD amendment fails CI the way FR-22 requires.

### Files Created

| File | Purpose |
|------|---------|
| `backend/domain/ranking.py` | The pure ranking core: score, buckets, hysteresis, three slots, tag derivation. |
| `backend/tests/domain/test_ranking.py` | Boundary-pinned tests for every rule in the module (75 tests). |

### Files Modified

| File | Changes |
|------|---------|
| `backend/shared/constants.py` | The ranking weights, the recency/city bands, the hysteresis threshold, the tag keys and order. |
| `backend/tests/shared/test_constants.py` | Pins the ranking weights, so a weight change without a PRD amendment fails CI. |

### Result

75 item-scoped tests + 4 constants-pinning tests, all green. `domain/` at 100%. The code
review fixed a wrong chip count in the prose, a duplicated constant and an unused exported
dataclass. See `test-report.md` and `review-report.md`.

---

*Plan approved at checkpoint. Execution follows.*
