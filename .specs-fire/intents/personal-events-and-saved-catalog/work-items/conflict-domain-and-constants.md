---
id: conflict-domain-and-constants
title: Conflict Detection Domain Logic
intent: personal-events-and-saved-catalog
complexity: medium
mode: confirm
status: in_progress
depends_on:
  - repo-hygiene-cleanup
created: 2026-10-29
---

# Work Item: Conflict Detection Domain Logic

## Description

Implements the **one overlap function** that AD-21 requires: a single pure function in `backend/domain/conflict.py` that decides whether two UTC intervals conflict, plus the separate duplicate-detection rule FR-58 defines for personal events.

AD-21 is explicit that conflict detection is *one* function, not several: "Conflict detection is one pure function in `domain/conflict.py`: two UTC intervals conflict when they overlap by **strictly more than 15 minutes** (FR-33). It runs on save, on Personal Event create, edit or import, and on AD-17 propagation — **never at render**."

The reason for the single-function rule is that the Pulse Card, the Timeline and `/conflicts` each need to answer the same question. If three surfaces each computed overlap their own way, the PRD's symmetric conflict indicator would disagree between them, and a cancelled event would keep its conflict marker. So the function is the contract, and the callers are interchangeable.

The strictness matters: **exactly 15 minutes is not a conflict.** The threshold is `CONFLICT_MIN_OVERLAP`, which already exists in `shared/constants.py`.

This work item is pure logic. It touches no models, no database and no API.

## Acceptance Criteria

- [ ] `backend/domain/conflict.py` exists and contains the single overlap function. Two UTC intervals conflict when the overlap is **strictly more than** `CONFLICT_MIN_OVERLAP` (15 minutes). An overlap of exactly 15 minutes returns "not a conflict"; 15 minutes and 1 second returns "conflict".
- [ ] The function is **pure**: no Django import, no I/O, no clock read, no database access. It takes the intervals as arguments. A test that imports `domain.conflict` in a process with no configured Django settings succeeds.
- [ ] The module honours the `domain-pure` import-linter contract: it may import only the standard library plus `shared.constants` and `shared.ids` (both explicitly allowlisted by `ignore_imports` in the `domain-pure` contract). `make lint-imports` passes.
- [ ] The module has no `from datetime import timezone`-style wall-clock reads. `now` is always an explicit argument, matching the convention in `domain/timezones.py` and `apps/ingestion/services/catalog_read.py`.
- [ ] The duplicate-detection rule is implemented as a **separate** function from the overlap function: a likely duplicate when another event has the same name (case-insensitive, token-overlap ≥ 80%) AND starts within 24 hours. The 80% threshold is a named constant in `shared/constants.py`, not a literal in the module.
- [ ] The token-overlap comparison is **not** semantic. No embeddings, no LLM call, no similarity service (AD-4's discipline extended to personal events).
- [ ] The duplicate rule **reuses** `domain/dedup.py`'s existing `tokens()` and `jaccard()` helpers, which are already public in that module. The two rules must not disagree about what "the same name" means, so a second normaliser is forbidden.
- [ ] `shared/constants.py` gains only the genuinely new constants (the 80% duplicate threshold and the 24-hour window if they are not already present). The 15-minute threshold and the 1d+1hr reminder default are **already there** and are used, never re-declared.
- [ ] Unit tests cover: a zero-overlap pair, a 1-second overlap, exactly 15 minutes, 15 minutes + 1 second, full containment, an event that spans midnight, a back-to-back pair (one ends exactly when the other starts → no overlap), and an event with no end time.
- [ ] Unit tests cover duplicates: identical names differing only in case, names at exactly 80% token overlap, names just below 80%, and duplicate candidates outside the 24-hour window.
- [ ] Tests are pinned as **golden tests** in the style of `backend/tests/domain/test_dedup.py`: if the normalisation or the token-overlap arithmetic ever changes, the test fails loudly rather than silently re-baselining.

## Technical Notes

`shared/constants.py` already defines:

```python
CONFLICT_MIN_OVERLAP = timedelta(minutes=15)
```

Use it. Do not write `timedelta(minutes=15)` again. The 80% threshold should follow the same pattern as the existing `TITLE_JACCARD_MIN = Fraction(4, 5)` — a `Fraction`, not a float, because a float `0.8` is not exactly 4/5 and a boundary test would be a lie.

Note the existing `TITLE_JACCARD_MIN` is `Fraction(4, 5)` = 80%, but it is used by the **dedup** rule for catalog events, where the PRD specifies token-overlap ≥ 80%. The duplicate rule for personal events uses the same 80% figure. Consider whether these should be one shared constant or two separate ones with the same value — if they are semantically the same threshold, one constant named for what it means (e.g. `TITLE_TOKEN_OVERLAP_MIN`) is better than two constants that can drift. If they are semantically different (dedup's is structural identity, duplicate-detection's is a user-facing prompt), keep them separate and document why in a comment.

`domain/dedup.py` already contains the normalisation and Jaccard machinery as **public helpers**: `tokens(text) -> list[str]`, `jaccard(a, b) -> Fraction`, plus `STOP_WORDS` and the Unicode-aware `_fold()`. Import and reuse those. Duplicating a second normaliser is exactly the drift AD-21 exists to prevent — and it would mean a title like "Café Night" folds differently in the dedup path than in the duplicate-prompt path, which is precisely the bug the rule was written to prevent.

`domain/errors.py` holds the domain error types. If conflict detection needs to signal an invalid interval (e.g. end before start), add the error type there rather than raising a bare `ValueError`, so the HTTP mapping in `config/errors.py` stays in one place.

## Dependencies

- repo-hygiene-cleanup
