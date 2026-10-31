# Code Review Report

**Run**: run-eventpulse24-021
**Intent**: pulse-digest-and-trust
**Work item**: digest-ranking-domain
**Reviewed**: 2026-10-30
**Files Reviewed**: 4

---

## Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Code Quality | 2 | 0 | 0 |
| Security | 0 | 0 | 0 |
| Architecture | 1 | 0 | 0 |
| Testing | 1 | 0 | 0 |
| **Total** | **4** | **0** | **0** |

**Tests Status**: Passing — 3411 passed, 0 failed; `domain/` at 100%

> The four fixes were applied without a checkpoint because each is mechanical and
> reversible: a wrong number in prose, a constant that duplicated another, a dataclass
> nothing referenced, and a test that pins a constant. None of them changes behaviour,
> and the full suite was re-run after each. The one change that *did* touch behaviour —
> adding a test — was additive.

---

## Files Reviewed

- `backend/domain/ranking.py` (created) — the ranking core: score, buckets, hysteresis, three slots, tag derivation
- `backend/shared/constants.py` (modified) — the ranking weights, bands, boundaries, hysteresis delta and tag keys
- `backend/tests/domain/test_ranking.py` (created) — 75 boundary-pinned tests
- `backend/tests/shared/test_constants.py` (modified) — 4 added tests pinning the weights and boundaries

---

## Auto-Fixed Issues

### 1. [Testing] The module's prose stated the wrong chip count

- **File**: `backend/domain/ranking.py:35`
- **Description**: The module docstring said the interest term is computed over "the
  ten interest chips" the user picked at onboarding. `MAX_INTEREST_PICKS` is **3** —
  FR-1 says "up to 3 picks", and a fourth is refused, not silently dropped. The *code*
  divided by the right constant, so no score was wrong; the *explanation* of the score
  was.

  This matters more than a typo. The module's whole promise is that "a reader can
  compute any event's score by hand from these four inputs" (FR-22's actual promise). A
  reader who believes the divisor is 10 computes the interest term wrong by a factor of
  more than three, and has no way to notice — the code says otherwise but the prose is
  what they read first.

- **Diff**:

```diff
 The two absent terms have no `Source` score field and no `Event` category field to read
 from, and FR-16 and FR-25 are both unbuilt. The third is reduced rather than absent:
-what the user actually picked at onboarding is the ten interest chips, and that overlap
-is the computable part of `preference_graph_match`.
+what the user actually picked at onboarding is the interest chips — up to three of them
+(FR-1) — and that overlap is the computable part of `preference_graph_match`.
```

The same wrong numbers appeared in this run's `test-report.md` (the "1 of 10 → 0.10"
table) and were corrected there too: 1 of 3 → 0.33, 2 of 3 → 0.67, 3 of 3 → 1.00.

**Two tests were added** so the number is pinned rather than merely corrected:

- `test_interest_overlap_is_divided_by_the_maximum_picks_constant` — asserts
  `MAX_INTEREST_PICKS == 3` and that the overlap divides by that constant.
- `test_a_one_chip_user_does_not_outrank_a_three_chip_user` — asserts the *reason* the
  divisor is the maximum and not the user's own count: a one-chip user who matches
  their chip scores strictly below a three-chip user who matches all three.

### 2. [Code Quality] A constant that duplicated another and was never referenced

- **File**: `backend/shared/constants.py:471`
- **Description**: `RANKING_TAG_CHIP_PREFIX_SERENDIPITY = "discovery"` was byte-identical
  to `RANKING_TAG_DISCOVERY` and was referenced nowhere in the codebase. Its stated
  purpose — "the chip-match tag for Slot 3 is **not** emitted; Slot 3 shows
  `discovery` instead" — is a rule about *absence*, and a constant named
  `..._PREFIX_SERENDIPITY` that holds a value with no prefix in it reads as though
  there were a second chip-prefix to choose from.

  The rule itself is real and is enforced in `why_this_tags()` (Slot 3 never emits a
  chip tag) and tested (`test_slot_3_shows_discovery_and_never_a_chip_tag`). Only the
  constant was redundant.

- **Diff**:

```diff
 # The prefix for a chip-match tag: `matches_music`, `matches_tech_meetups`.
 RANKING_TAG_CHIP_PREFIX = "matches_"
 
-# The chip-match tag for Slot 3 is **not** emitted — Slot 3 shows `discovery` instead.
-# The name is a constant so the rule is a fact in the codebase, not a comment.
-RANKING_TAG_CHIP_PREFIX_SERENDIPITY = "discovery"
-
 # At most three Why-this Tags on a card (FR-6).
 RANKING_MAX_TAGS = 3
```

### 3. [Architecture] An exported dataclass nothing used and the design did not specify

- **File**: `backend/domain/ranking.py:161`
- **Description**: `SlotScore` (a `score` + `tags` pair) was defined, exported in
  `__all__`, and referenced nowhere — not by the module, not by the tests, not by any
  other package. The design doc's module surface (D11) lists seven functions and no
  dataclass beyond `RankingInputs`.

  Left in place it would have been a *second* candidate shape competing with whatever
  the composition service defines, in the one layer every other app imports. That is
  the shape of a future integration bug: two dataclasses that mean the same thing, one
  of them imported because it was exported.

- **Diff**:

```diff
-@dataclass(frozen=True)
-class SlotScore:
-    """One scored candidate: its raw score and its Why-this Tag keys.
-
-    `tags` are **keys, not display strings**. The server states facts; the client speaks
-    the user's language. The presentation edge renders them.
-    """
-
-    score: Decimal
-    tags: tuple[str, ...]
-
-
 def _zone(name: str) -> ZoneInfo:
```

and from `__all__`:

```diff
     "SCORE_PRECISION",
     "RankingInputs",
-    "SlotScore",
     "apply_hysteresis",
```

### 4. [Code Quality] Eight over-length lines in the module docstring

- **File**: `backend/domain/ranking.py:26` (and 4 other locations)
- **Description**: Ruff's `E501` (line length 100, per `.specs-fire/standards/coding-standards.md`)
  flagged eight lines in the module docstring and the `score_slot_3` docstring. Two were
  markdown table rows whose cells ran past 100 characters; one was FR-5's published slot-3
  formula on a single line.

  The tables were restructured rather than truncated. The "which FR will supply this
  term" information — the part that makes the reduction legible as a debt instead of a
  choice — was moved out of a cramped third column into a bulleted list below the
  table, so nothing was lost to satisfy the linter.

- **Diff** (the AD-10 table's long row):

```diff
-| **Relevance Pulse** | at digest composition | `personal` | card, detail, email | `personalization` |
+| **Relevance Pulse** | at digest composition | `personal` | card, detail, email | `personal` app |
```

**Diff** (the omitted-terms table, restructured into two columns plus a list):

```diff
-| Published input | Why it is absent | What will supply it |
-| --- | --- | --- |
-| `source_reliability` | FR-16 is unbuilt. `Source` has no score field, and the number is not computable from anything that exists. | FR-16, when it ships. |
-| `novelty_vs_exploration` | Needs the `PREFERENCE_GRAPH` (FR-25, deferred) *and* an event category; `Event` has no category field. | FR-25, when it ships. |
-| `preference_graph_match` | The `PREFERENCE_GRAPH` itself is unbuilt. What survives is the **interest-chip overlap** — the ten chips the user actually picked at onboarding. | FR-25 replaces the chips with the graph. |
-| `recency_fit` | **Survives.** The event's start time and the user's day both exist. | — |
+| Published input | Status |
+| --- | --- |
+| `source_reliability` | Absent — FR-16 is unbuilt; `Source` has no score field. |
+| `novelty_vs_exploration` | Absent — needs FR-25's graph *and* an event category. |
+| `preference_graph_match` | Reduced — the interest-chip overlap survives. |
+| `recency_fit` | **Survives** — start time and the user's day both exist. |
+
+What will supply each absent term, so the reduction is legible as a debt and not as a
+choice:
+
+- `source_reliability` — **FR-16**, when it ships.
+- `novelty_vs_exploration` — **FR-25**, when it ships.
+- `preference_graph_match` — FR-25 replaces the interest chips with the real graph.
```

**Diff** (FR-5's slot-3 formula, moved to a fenced block):

```diff
-    FR-5 publishes
-    `score = source_reliability × geographic_distance_factor × freshness_factor × (1 − normalized_popularity)`
-    — an explicit anti-popularity bias, so that Slot 3 is structurally the card the
-    user's own signals would not have picked.
+    FR-5 publishes
+
+    ```
+    score = source_reliability × geographic_distance_factor × freshness_factor
+          × (1 − normalized_popularity)
+    ```
+
+    — an explicit anti-popularity bias, so that Slot 3 is structurally the card the
+    user's own signals would not have picked.
```

---

## Applied Suggestions

No suggestions were applied — every finding was auto-fixable.

---

## Skipped Suggestions

No suggestions were skipped.

---

## What the review checked and found clean

These were reviewed and required no change. They are recorded so the next reviewer does
not re-derive them.

| Check | Result |
| --- | --- |
| **Bucket boundaries** | FR-22's four boundaries are exact, and an exact boundary takes the **lower** bucket. Verified empirically: `0.85 → 4`, `0.65 → 3`, `0.45 → 2`, `0.25 → 1`. |
| **Hysteresis threshold direction** | The rule is "moves by **at least** 0.10". Verified an exact 0.10 delta (`0.60 → 0.70`) **does** move the bucket (3 → 4), so the `<` comparison is the right way round. |
| **The `nearby` tag threshold** | `city_match >= RANKING_CITY_SAME` (1.00) means only a same-city event gets `nearby`; a same-country/different-city event scores 0.50 and does not. Correct. |
| **`discovery` under the 3-cap** | Slot 3 with `discovery` + `nearby` + `tonight` + `saved` returns `('discovery', 'nearby', 'saved')` — `discovery` is first in `RANKING_TAG_ORDER`, so it cannot be capped away. The mandatory-Slot-3-tag rule holds under the cap. |
| **The weekend rule** | Byte-identical to `domain/event_fit.py`'s, including the Saturday-anchored date comparison rather than an ISO week comparison (which would lose a New Year weekend). |
| **The `_zone` fallback** | An unknown zone falls back to UTC rather than raising, mirroring `domain/event_fit.py`. A score is an *indicator*; an event whose zone cannot be read should still get one. |
| **`interest_overlap` clamping** | 3 of 3 → `1.00`; 11 of 11 also → `1.00` (the `_clamp` catches the over-count). |
| **AD-2 purity** | `domain/ranking.py` imports only the stdlib plus `shared.constants`. The `domain-pure` contract is KEPT. |
| **Security** | No secrets, no I/O, no shell, no network, no user input. The module is pure arithmetic over frozen dataclasses. Nothing to review. |
| **Database alias** | No database access at all in this module, so AD-3's `using=` rule does not apply here. |
| **PII in logs** | No logging in this module. |

---

## Project Tooling Used

- **ruff**: `backend/pyproject.toml` (line length 100, `E,F,I,B,UP,S,DTZ,G,LOG`) — `ruff check .` and `ruff format --check .`, both clean
- **import-linter**: `backend/pyproject.toml` `[tool.importlinter]` — `lint-imports`, 19 contracts kept, 0 broken
- **pytest + pytest-django**: `backend/pyproject.toml` — 3411 passed, 0 failed
- **coverage**: `backend/pyproject.toml` — 99.07% overall, **100% on `domain/`** (the `--fail-under=100` gate)
- **Django system checks**: `manage.py check` — no issues; `manage.py makemigrations --check --dry-run` — no changes

---

## Standards Referenced

- `.specs-fire/standards/coding-standards.md`
- `.specs-fire/standards/testing-standards.md`
- `.specs-fire/standards/constitution.md`
- `.specs-fire/intents/pulse-digest-and-trust/work-items/digest-ranking-domain-design.md` (D1–D11)

---

## Verdict

**Approved.** The four fixes are applied, the full suite is green (3411 passed), `domain/`
is at 100%, and all 19 architectural contracts hold. No suggestions require a decision.

---

# Work Item: `digest-composition-models` — `PULSE_DIGEST` and `DIGEST_COMPOSITION`

**Run**: run-eventpulse24-021
**Intent**: pulse-digest-and-trust
**Reviewed**: 2026-10-30
**Files Reviewed**: 6

---

## Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Code Quality | 1 | 0 | 0 |
| Security | 0 | 0 | 0 |
| Architecture | 2 | 0 | 0 |
| Testing | 3 | 0 | 0 |
| **Total** | **6** | **0** | **0** |

**Tests Status**: Passing — 3480 passed, 0 failed; coverage 99.08% overall, `domain/` at 100%

> The six fixes are applied without a checkpoint because each is mechanical and
> reversible: one missing database constraint, two false claims in the design doc, and
> three tests that could not fail for the reason they claimed to check. The one change
> that *did* alter the schema is additive — a `CHECK` constraint that only rejects rows
> the model already rejected in Python — and the full suite was re-run after it.

---

## Files Reviewed

- `backend/apps/personalization/models.py` (modified) — `PulseDigest`, `DigestComposition`, `DIGEST_SLOT_ORDER`
- `backend/apps/personalization/migrations/0007_digestcomposition_pulsedigest.py` (created) — the two tables, the append-only trigger, the runtime grants
- `backend/apps/personalization/migrations/0008_digestcomposition_digest_composition_slot_ck.py` (created) — the slot check constraint added by this review
- `backend/tests/personalization/test_digest_models.py` (created) — 53 tests
- `backend/tests/personalization/factories.py` (modified) — the two factories
- `backend/tests/personalization/test_model_structure.py`, `test_grants.py` (modified) — the structural and grant guards

---

## Auto-Fixed Issues

### 1. [Architecture] `slot` was writable with any value — the enum was Python-only

- **File**: `backend/apps/personalization/models.py:761` (before the fix)
- **Description**: `slot = models.CharField(max_length=16, choices=Slot.choices)` declares
  the three slots, but **Django's `choices` are not a database constraint**. The model
  had check constraints on `bucket` and on the `event_kind`/`event_version`/
  `source_badge` shape — but none on `slot`.

  Verified empirically against the live database, before the fix:

  ```
  INSERT ... slot='bogus_slot' ...  ->  WROTE bogus_slot -> ('bogus_slot',)
  ```

  A row with a fourth slot was accepted. That row would then be **invisible to the
  digest read**: the read sorts against `DIGEST_SLOT_ORDER` (D12), and a slot outside
  that tuple has nowhere to sort, so the card would silently vanish from the digest
  rather than fail loudly.

  This is the same argument D5 makes for the bucket — "a check constraint is what
  makes a sixth one impossible at the database" — applied to a field that had been
  left unenforced. The design doc's own standard is "the constraints are the point",
  and FR-5's "exactly 3 cards, one per slot" depends on `slot` being one of three
  values.

- **Diff** (`models.py`):

  ```diff
               # FR-22's bucket is 1 to 5.
               models.CheckConstraint(
                   condition=models.Q(bucket__gte=1) & models.Q(bucket__lte=5),
                   name="digest_composition_bucket_ck",
               ),
  +            # FR-5's three slots, and no fourth — the same argument D5 makes for the
  +            # bucket.
  +            #
  +            # `choices` is a Python-level convenience only: Django does not turn it into
  +            # a database constraint, so without this a row with `slot='bogus_slot'` is
  +            # perfectly writable and the digest read would silently drop it (the read
  +            # sorts against `DIGEST_SLOT_ORDER`, and a slot outside it has nowhere to
  +            # sort). The check constraint is what makes the fourth slot impossible at
  +            # the database, exactly as the bucket's makes a sixth bucket impossible.
  +            #
  +            # The literals are the enum's values, pinned to the enum by
  +            # `test_digest_composition_slot_values_match_the_constraint`.
  +            models.CheckConstraint(
  +                condition=models.Q(slot__in=["must_know", "nearby", "serendipity"]),
  +                name="digest_composition_slot_ck",
  +            ),
  ```

  and a new migration, `0008_digestcomposition_digest_composition_slot_ck.py`:

  ```python
  migrations.AddConstraint(
      model_name="digestcomposition",
      constraint=models.CheckConstraint(
          condition=models.Q(("slot__in", ["must_know", "nearby", "serendipity"])),
          name="digest_composition_slot_ck",
      ),
  )
  ```

  **Three tests were added** with it: one that a `bogus_slot` is rejected by
  `IntegrityError`, one that each of the three real slots is accepted, and one that
  pins the constraint's literals to the enum.

  The probe row written during the review was deleted afterwards, inside the
  retention-purge escape hatch (`SET LOCAL eventpulse.retention_purge = 'on'`) — the
  append-only trigger correctly refused a plain `DELETE`, which is itself a second
  confirmation that the trigger works.

### 2. [Architecture] D12 named an attribute that does not exist: `Slot.ORDER`

- **File**: `.specs-fire/intents/pulse-digest-and-trust/work-items/digest-composition-models-design.md:319`
- **Description**: D12's "Consequence" said:

  > "`DigestComposition.slot` is a `CharField` with `choices=Slot.choices`, and the
  > *order* comes from `Slot.ORDER`."

  There is no `Slot.ORDER`. Verified: `hasattr(DigestComposition.Slot, 'ORDER')` is
  `False`, and `Slot.ORDER` is referenced nowhere in the codebase. The real source of
  truth is the module-level `DIGEST_SLOT_ORDER` — which the **code** and the rest of
  the design get right — but the design's own summary of it was wrong.

  This matters because a downstream implementer following D12 literally would look for
  `Slot.ORDER`, not find it, and re-derive the order from a string comparison — the
  exact thing D12 exists to forbid ("a second place the slot order lives").

  The design doc now says why the constant is *outside* the enum class: a
  `TextChoices` member holds a scalar, so a tuple attribute inside the class would be
  read as an enum member and fail at import.

### 3. [Architecture] D3's justification for `base_manager_name` was false for this model

- **File**: `digest-composition-models-design.md:100`
- **Description**: D3 said this model was "the first table in the app that needs
  `Meta.base_manager_name = 'objects'` **so that related-object paths use the guarded
  queryset too**."

  There are no related-object paths. Verified: `DigestComposition._meta.related_objects`
  is `()` and `get_fields()` reports zero relations — precisely *because* D2 holds every
  relation by value. `base_manager_name` affects only `_base_manager`, which is used
  for related-object traversal; with no relations it changes nothing about this model.

  The **code** is right — the attribute is correct and consistent with
  `EventStateChange`, `IngestionAuditEntry` and `PersonalizationAuditEntry`. Only the
  stated *reason* was wrong, and a wrong reason is worse than no reason: it invites
  the next author to "simplify" the attribute away for a justification that does not
  hold. The design now says what is actually true — the attribute is declared for
  consistency with the other append-only tables, and there is no related-object path
  today because every relation is held by value.

### 4. [Testing] The slot-order test could not detect an added slot

- **File**: `backend/tests/personalization/test_digest_models.py:336`
- **Description**: The test that D12 leans on walked the enum **filtered** by
  membership in the constant:

  ```python
  declared = tuple(
      member.value for member in DigestComposition.Slot if member.value in DIGEST_SLOT_ORDER
  )
  ```

  A slot added to the enum but not to `DIGEST_SLOT_ORDER` is simply *skipped* by that
  filter, so `declared` still equals the constant and the test still passes. Verified
  by mutation — a fourth member `NEW_SLOT = "new_slot"` was added to `Slot`:

  ```
  OLD filtered assertion passes? True -> ('must_know', 'nearby', 'serendipity')
    (a fourth slot was silently skipped)
  NEW unfiltered assertion passes? False
  ```

  The companion test asserted **set** equality (`set(DIGEST_SLOT_ORDER) == accepted`),
  which forgets both order and multiplicity — so it could not catch it either.

  This is the drift D12 exists to prevent: "the order and the enum are the same fact,
  and they cannot drift apart". A fourth slot would have shipped with no reader able to
  order it, and the digest read would silently drop the card.

  Both tests were rewritten to compare the **unfiltered** enum, and the coverage test
  to assert **list** equality rather than set equality. After the fix, all three
  slot-related tests fail against the mutated enum (verified).

### 5. [Testing] The enum-pinning test asserted a substring, and a substring is not a pin

- **File**: `backend/tests/personalization/test_digest_models.py:227`
- **Description**: `test_digest_composition_kind_values_match_the_constraint` asserted
  that the enum's values appeared *as substrings* of the rendered constraint:

  ```python
  assert DigestComposition.EventKind.PUBLIC.value in rendered
  assert DigestComposition.EventKind.PERSONAL.value in rendered
  ```

  The model's own comment says the test exists so that renaming the enum's value
  "fails here rather than at the first insert". It did not do that. Simulating the
  exact drift — the enum's value renamed to `"pub"` while the constraint kept the stale
  literal `"public"` — both assertions still hold:

  ```
  OLD assertion:
    "public" in rendered -> True  <- PASSES (wrong!)
    "pub" in rendered    -> True  <- PASSES (wrong!)
    => OLD TEST PASSES AGAINST A BROKEN CONSTRAINT
  ```

  The substring `"pub"` is inside `"public"`. The pin was decorative.

  The assertion is now on an **exact token** — Django renders the comparison as
  `('event_kind', 'public')`, so the pin is `('event_kind', 'pub')`, which does not
  match `('event_kind', 'public')`. Verified: with the constraint's literal changed to
  `"pub"`, the test fails.

  The same exact-token treatment was applied to the new slot constraint's pin, with a
  per-value count assertion so a stale literal left behind by a removed slot fails
  too.

### 6. [Testing] The `__str__` leak test conflated the slot with the tag

- **File**: `backend/tests/personalization/test_digest_models.py:313`
- **Description**: The test built a composition whose tags included `"nearby"` — which
  is *also* a slot value — and then asserted `"nearby" not in rendered`. The assertion
  was only meaningful because the factory's default slot happened to be `"must_know"`.
  Had the factory's default slot ever become `"nearby"`, the test would have failed
  because **the slot** leaked, not because a **tag** leaked, and it would have been
  asserting something it never set up.

  The test could fail correctly (verified: a `__str__` that appends `self.tags` is
  caught), so it was not a tautology — but it was testing two things at once and
  naming only one of them.

  The slot is now pinned explicitly to `must_know`, and the test asserts both
  directions: the tag `"nearby"` is **absent** while the slot `"must_know"` is
  **present**. The second assertion is what makes the first meaningful.

---

## Reviewed and found clean

| Check | Result |
| --- | --- |
| **The kind-shape constraint's logic** | Correct in all four valid combinations, and the SQL precedence is right (`AND` binds tighter than `OR`). Verified exhaustively. |
| **`score = numeric(3,2)`** | Verified in `information_schema.columns`: `numeric, precision 3, scale 2`. D5's claim is true. |
| **The `timezone` shadowing** | **Not a bug.** `PulseDigest.timezone` shadows the module only inside `PulseDigest`'s own class body; `DigestComposition` is a separate scope, so `timezone.now` on `DigestComposition.composed_at` resolves to the module. Verified at runtime: `DigestComposition._meta.get_field('composed_at').default is django.utils.timezone.now` → `True`. |
| **`append_only_mutable = frozenset()`** | Necessary and harmless — it restates the inherited default explicitly. Verified that `update()`, `update(bucket=1)`, `bulk_update`, `bulk_create(update_conflicts=True)`, `save(force_update=True)`, `save(update_fields=['bucket'])` and `delete()` are all blocked. |
| **`Meta.base_manager_name = "objects"`** | Correct and consistent with every other append-only model in the codebase. |
| **The migration** | `makemigrations --check` → "No changes detected". Column types match the design: `numeric(3,2)`, `varchar(16)`, `smallint`, `jsonb`, `timestamptz`. The trigger is installed and **reuses** `personal.forbid_history_mutation()` — verified the `personal` copy has **no `TG_ARGV[0]` branch**, unlike `catalog`'s, so D3/D11's claim is true. |
| **The grants** | Verified live: `ep_personal` has `INSERT=True, SELECT=True, UPDATE=False, DELETE=False` on the composition table, and `UPDATE=True, DELETE=True` on `pulse_digest` — exactly D1/D11's intent. The `DO $$ … has_table_privilege … RAISE EXCEPTION` block is present and is exercised by `test_grants.py`. |
| **The index test** | It **can** fail, and fails for the right reason. Verified the planner returns an `Index Scan` over `digest_comp_user_event_idx` with an `Index Cond` on `(user_id, event_id)`, both on an empty table and with rows present. A dropped index becomes a `Seq Scan`, which the test rejects. |
| **`tags = models.JSONField(default=list)`** | Not a mutable-default bug — Django calls the callable per instance. Verified `a.tags is b.tags` → `False`. |
| **AD-3 / AD-9 / AD-13 / AD-15 / AD-16** | All hold. Both models declare `retention_category = ACCOUNT_CONTENT`; both hold every relation by value; neither `__str__` leaks event content, a tag label, or a user identifier. |
| **The write-ownership guard** | The AD-16 architecture test caught the two new tables as unowned during development — the guard working exactly as designed. `personalization` now owns both. |

---

## A cross-item observation (not a defect in this item)

`digest-composition-service.md` requires that re-composing the same
`(user, local_date)` be "a no-op that returns the existing digest, not a second
composition". With only the unique constraint on `(digest_id, event_id)`, a
re-composition attempt raises `IntegrityError` rather than being detected as a
duplicate. **The service must check for the existing digest before writing** — which
that work item's own acceptance criteria already demand ("the service must not rely
on an `IntegrityError` to notice"). Flagged here so it is not discovered at
implementation time.

---

## Project Tooling Used

- **ruff**: `backend/pyproject.toml` — `ruff check .` and `ruff format --check .`, both clean
- **import-linter**: `backend/pyproject.toml` `[tool.importlinter]` — `lint-imports`, 19 contracts kept, 0 broken
- **pytest + pytest-django**: `backend/pyproject.toml` — **3480 passed, 0 failed**
- **coverage**: `backend/pyproject.toml` — 99.08% overall, **100% on `domain/`**
- **Django system checks**: `manage.py check` — no issues; `manage.py makemigrations --check --dry-run` — no changes
- **Mutation checks**: the three test fixes were each verified by mutating the code
  they cover (adding a fourth slot, changing a constraint's literal, leaking the tags
  into `__str__`) and confirming the test fails

---

## Standards Referenced

- `.specs-fire/standards/coding-standards.md`
- `.specs-fire/standards/testing-standards.md`
- `.specs-fire/standards/constitution.md`
- `.specs-fire/intents/pulse-digest-and-trust/work-items/digest-composition-models-design.md` (D1–D12)

---

## Verdict

**Approved.** Six fixes applied — one missing database constraint, two false claims in
the design doc, and three tests that could not fail for the reason they claimed to
check. The full suite is green (**3480 passed**, up from 3473), coverage is 99.08%
overall with `domain/` at 100%, and all 19 architectural contracts hold. No suggestions
require a decision.

