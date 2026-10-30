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
