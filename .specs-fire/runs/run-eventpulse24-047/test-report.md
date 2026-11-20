---
run: run-eventpulse24-047
work_item: fr22-published-formula
intent: traceability-gap-closure
generated: 2026-11-19
status: passed
---

# Test Report: FR-22 publishes a formula the product does not compute

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Backend (full suite) | 7477 | 3 (pre-existing) | 7 | unchanged |
| Tests added by this run | 1 | 0 | 0 | n/a |
| **Total** | **7477** | **3 (pre-existing)** | 7 | unchanged |

7477 passed, against 7476 before this run — the one new test.

## The test that was added

`backend/tests/shared/test_constants.py::test_the_prd_publishes_the_weights_the_product_computes`

The existing `test_the_ranking_weights_have_an_amendment_that_says_so` opens `ADR-0025` and
asserts every weight constant appears in it, so the weights cannot move without the ADR
moving too. **It does not check the PRD** — and FR-22's promise is not that the weights are
*authorised* but that they are **published**:

> The formula and weights are **published in the PRD and immutable post-launch** …
> A user reading the PRD can compute the Confidence Pulse for any Event given the inputs.

The new test locates `#### FR-22` in `prd.md`, slices to `#### FR-23`, and asserts each of
the five `RANKING_WEIGHT_*` constants appears in that section.

**This closes the exact gap the work item exists for.** Between 2026-11-11 and 2026-11-19
the PRD's FR-22 published a locked table reading `w1 = 0.40` two paragraphs above an
amendment implementing `interest_overlap` at 0.35. Nothing executable caught it. Now
something does.

### The test was probed for its ability to fail

A test that cannot fail is decoration, so it was mutated rather than trusted:

| Mutation | Result |
|---|---|
| `0.35` → `0.99` throughout the PRD's FR-22 section (4 occurrences) | **FAILED** — `assert '0.35' in '#### FR-22: …'` |
| PRD restored from backup | 38 passed |

The failure message names the weight and says what to do about it ("Amend FR-22 and record
the amendment"), rather than only reporting a missing substring.

## Acceptance Criteria Validation

- ✅ **A decision on which formula is canonical, taken by a human** — the five-term as-built formula, ratified at Checkpoint 1. The PRD's FR-22 weights table now maps each published component to the term that evaluates it.
- ✅ **If the PRD is amended: a new Amendment ID is minted, and it appears in the PRD, DESIGN.md/EXPERIENCE.md and ADR-0025 — the convention applied properly, rather than A-3 being stretched** — **A-25**, appearing 8× in `prd.md`, 2× in `ADR-0025.md`, 2× in `EXPERIENCE.md`, 7× in `TRACEABILITY.md`. A-3 is superseded, not stretched.
- ✅ **FR-22's bucket boundaries are checked against the new weights** — verified unchanged and still correct. The five weights sum to `RANKING_WEIGHT_SUM == 1.00` and each term is normalised to [0,1], so the score range is still [0,1] and the published boundaries still partition it. `test_ranking_bucket_boundaries_are_pinned` passes untouched. The launch-time ceiling (≈0.865 against a 0.85 boundary for 5 dots, while every source sits at the 0.50 prior) is recorded in the design doc as a note, not acted on.
- ➖ **`/settings/privacy`'s ranking-transparency section shows the formula the product actually runs** — **cannot be met in this run; the route does not exist.** No surface in `frontend/` renders a formula at all, so no user is shown a wrong one. Split to `settings-privacy-ranking-transparency` at Checkpoint 1, with your approval.
- ✅ **Only then: the Amendment Ledger entry for A-3 is resolved — either tagged, or recorded as superseded** — recorded as **superseded by A-25**. The ledger's inconsistent-amendment count drops from 2 to 1.

## Tests Written

### Unit Tests

- `backend/tests/shared/test_constants.py` — `test_the_prd_publishes_the_weights_the_product_computes`: the PRD's FR-22 section must carry all five implemented weights.

### Integration Tests

None. No runtime behaviour changed.

## Test Commands

```bash
# Full backend suite (venv must be on PATH — see run 046's report)
cd backend && PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m pytest -q

# Just the weights pins
cd backend && PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m pytest tests/shared/test_constants.py -q
```

## Verification performed

| Check | Result |
|---|---|
| Full backend suite | **7477 passed**, 3 pre-existing failures, 7 skipped (5:06) |
| New test probed by mutation | ✅ fails on drift, passes when restored |
| `ruff check` on the changed test file | ✅ All checks passed |
| `ruff format --check` | ✅ (reformatted once, then clean) |
| `lint-imports` | ✅ **20 contracts kept, 0 broken** |
| No ranking reference to `Amendment A-10` remains | ✅ — every remaining occurrence is Browse, plus the paragraph in FR-22 that explains the re-mint |
| A-25 propagated | ✅ prd.md 8, TRACEABILITY.md 7, ADR-0025.md 2, EXPERIENCE.md 2 |
| FR-22 section carries all five weights | ✅ 0.35 / 0.25 / 0.20 / 0.10, total 1.00 stated |
| PRD and EXPERIENCE frontmatter parse as YAML | ✅ both |
| `shared/constants.py` untouched | ✅ no weight value moved |
| `frontend/` untouched | ✅ |

## Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| FR-22's heading still read "(revised by Amendment A-3)" after A-3 was superseded | Low | **Fixed** — found incidentally in the mutation probe's output, which printed the heading. Now "(revised by Amendment A-3, superseded by Amendment A-25)". The same class of stale reference as `[ASSUMPTION-11]`, and it would have been missed without the probe. |
| `ruff format` wanted one reformat of the new test | Trivial | **Fixed** — formatted, re-checked, re-run. |
| 3 `tests/delivery/test_preferences_api.py` failures — `ScheduledSend.DoesNotExist` | Pre-existing | **Not caused by this run.** Same failures as run 046 and run 041, which verified them against base commit `b8c6b21`. This run touched one test file in `tests/shared/`. **Still unowned by any work item.** |

## Ready for Completion

- [x] All tests passing (3 failures pre-existing and verified unrelated)
- [x] Coverage target met (n/a — one test added, no production code changed)
- [x] All acceptance criteria validated (4 of 5; the 5th split to its own work item with approval)
- [x] No critical issues open

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-047*
