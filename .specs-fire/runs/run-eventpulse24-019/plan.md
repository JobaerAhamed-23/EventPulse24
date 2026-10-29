---
run: run-eventpulse24-019
work_item: repo-hygiene-cleanup
intent: personal-events-and-saved-catalog
mode: autopilot
checkpoint: none
approved_at: n/a
---

# Implementation Plan: Repository Hygiene Cleanup

## Approach

Inventory every macOS AppleDouble duplicate in the working tree, separate the *files* from the
*directories*, confirm each candidate is untracked by git before removal, then prove the cleanup
is behaviour-neutral by recording the backend and frontend test counts before and after.

The work item's premise was that ~30 duplicate **files** (`Makefile 2.py`, `README 2.md`,
`domain/confidence 2.py`, `apps/personalization/api 2.py`, …) were present. That premise turned
out to be **stale**: by the time this item was executed the duplicate files had already been
removed outside this session. What remained were ~10 **empty duplicate directories** — the
`… 2/` folders that survive their files, and that a `find -name '* 2.*'` file glob does not
match.

The cleanup therefore proceeds in two passes:

1. **Inventory.** Glob for both duplicate *files* (`* 2.py`, `* 2.ts`, `* 2.tsx`, `* 2.md`,
   `* 2.yml`, `* 2.yaml`, `* 2.json`, `* 2.toml`, `* 2.lock`, `* 2.css`, `* 2.mts`, `* 2.mjs`)
   and duplicate *directories* (`* 2*`). For each hit, cross-check `git ls-files` to determine
   tracked vs. untracked.
2. **Removal.** Delete only what is (a) untracked, (b) empty, and (c) not referenced by the
   `Makefile`, `scripts/`, `.github/workflows/` or `frontend/package.json`.
3. **Proof.** Re-run the full backend suite (1691 tests) and the frontend suite (51 tests) against
   the real Postgres and confirm both counts are identical to the pre-cleanup baseline.

### Correctness safeguards

- **Legitimate names are not touched.** A name merely *containing* a `2` — `run-eventpulse24-002`,
  `voyage.py`, `schema.ts` — is not a duplicate. The removal set is built from the explicit
  AppleDouble shape (`<name> 2<ext>` / `<name> 2/`), never from a bare `*2*` glob.
- **Tracked duplicates would be removed with `git rm`.** None were found, so nothing in the
  removal set needed a git-tracked removal.
- **No feature work in this commit.** The cleanup is its own commit, revertible independently.

## Files to Create

| File | Purpose |
|------|---------|
| (none) | |

## Files to Modify

| File | Changes |
|------|---------|
| (none) | |

## Tests

| Test File | Coverage |
|-----------|----------|
| `backend/tests/` (full suite) | Regression proof: 1691 tests, count identical before and after |
| `frontend/tests/` + `frontend/app/` (Vitest) | Regression proof: 51 tests, count identical before and after |

## Technical Details

### Pre-cleanup inventory

**Duplicate files — 0 found.** A glob across the whole tree for every AppleDouble suffix returned
zero hits. The ~30 duplicate files described in the work item description (and confirmed present
during the planning phase) had already been deleted before this item ran. This is recorded rather
than claimed as work done here.

**Duplicate directories — 10 found, all empty and all untracked:**

| Path | Files inside | Tracked? |
|------|--------------|----------|
| `docker/postgres 2` | 0 | untracked |
| `frontend/app/dev 2` | 0 | untracked |
| `frontend/.next/server/middleware 2` | 0 | untracked |
| `frontend/.next/server/app 2` | 0 | untracked |
| `frontend/.next/server/chunks 2` | 0 | untracked |
| `frontend/.next/server/pages 2` | 0 | untracked |
| `frontend/.next/build/chunks 2` | 0 | untracked |
| `frontend/lib/api 2` | 0 | untracked |
| `.specs-fire/intents 2` | 0 | untracked |
| `backend/tests/fixtures/sources 2` | 0 | untracked |
| `.specsmd/fire 2` | 0 | untracked |

Each was confirmed empty (`0 files`) before removal. The removal had to be iterative: the first
`rmdir` exposed nine further nested duplicates, and a second `find -depth -type d -empty -delete`
pass cleared the rest.

### Reference check

The only `grep` hits for the duplicate names were the search pattern itself and a `2>/dev/null`
redirection inside `scripts/db-check.sh` — neither references a duplicate path. `Makefile`,
`scripts/`, `.github/workflows/` and `frontend/package.json` reference no duplicate.

### `__pycache__` duplicates

Remaining `__pycache__` directories with numeric suffixes are gitignored
(`.gitignore:7: __pycache__/`), regenerate harmlessly, and are not AppleDouble artifacts. Left
alone.

### Environment blocker, resolved

The first full backend run produced `1234 passed, 457 errors` — every error a
`psycopg` `ConnectionTimeout`. Root cause: **Docker Desktop was not running**, so the project's
Postgres 18 + pgvector (host port 5440) and Redis (6380) were unreachable. Only a native
Postgres on 5432 was listening — and the scaffold brief explicitly forbids disturbing the
pre-existing native PG12/PG16/Redis instances.

Resolved the prescribed way rather than by repointing `.env`: started Docker Desktop and ran
`docker compose up -d`. All three services reached `healthy`
(`pgvector/pgvector:0.8.6-pg18` on 5440, `redis:8-alpine` on 6380, `axllent/mailpit:v1.32` on
1025/8025). `.env` was **not** modified — the pre-existing native services on 5432/5434/6379
were left untouched.

### Baseline

| Suite | Before | After |
|-------|--------|-------|
| Backend (pytest, real Postgres, both schemas) | 1691 collected | **1691 passed** |
| Frontend (Vitest) | 51 passing / 9 files | **51 passing / 9 files** |
| `ruff check` | clean | **All checks passed!** |
| `make lint-imports` | 13 kept, 0 broken | **13 kept, 0 broken** |

---
*Autopilot mode — 0 checkpoints. Plan recorded for review; execution follows.*

---

## Work Item: conflict-domain-and-constants

### Approach

Implement `backend/domain/conflict.py`: the single pure overlap function AD-21 mandates, plus the
separate FR-58 duplicate-detection rule. Pure logic — no models, no database, no API.

**The overlap function.** The signature is pinned by the project standards
(`.specs-fire/standards/coding-standards.md` §"Pure domain function" and
`.specs-fire/standards/testing-standards.md` §"Test Structure"):

```python
def conflicts(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
```

Two UTC intervals conflict when their overlap is **strictly more than** `CONFLICT_MIN_OVERLAP`
(15 minutes, already in `shared/constants.py` — used, never re-declared). Exactly 15 minutes is
**not** a conflict; 15 minutes + 1 second **is**.

**The threshold's source of truth.** AD-21 states the rule; the work item and the testing
standards agree. Note that FR-58's prose ("scans for other Personal Events within ±30 minutes of
the new event's start time") describes a **candidate scan window** around the start, not the
overlap threshold — the two are not in conflict: the scan finds candidates, the overlap function
decides. This item implements the overlap function only; the candidate scan belongs to the
service layer (work item ⑤).

**Intervals with no end.** `end_time_utc` is nullable on the catalog's Event, and the personal
event form's end time is optional. So the function must handle `end=None`. The rule is
"two UTC intervals conflict when they overlap", and an event with no end has an **open-ended**
interval `[start, ∞)`. Treating it as unbounded makes it overlap everything after it — which is
the honest reading of "this event has no known end" and is the *safe* direction for a
double-booking guard. A zero-length interval (`end == start`) is a different matter: it occupies
no time at all and can never overlap by more than 15 minutes, so it never conflicts.

**Purity.** `domain/conflict.py` imports only the stdlib plus `shared.constants` — the two
allowlisted by the `domain-pure` import-linter contract. No Django, no clock read, no I/O. The
existing `tests/domain/test_domain_is_django_free.py` walks **every** `domain/` module in a fresh
interpreter, so the new module is covered for Django-freedom with no extra test. The
`tests/domain/test_domain_api.py` scan likewise picks up the new module automatically and
asserts no public API takes an embedding or similarity input — the duplicate rule is structural,
never semantic.

**The duplicate rule.** A separate function, per FR-58: a likely duplicate when another event
has the same name (case-insensitive, ≥80% token overlap) **and** starts within 24 hours.

It reuses `domain/dedup.py`'s existing public helpers — `tokens()` and `jaccard()` — rather than
declaring a second normaliser. This matters: `dedup.tokens()` folds case, drops Latin/Greek/
Cyrillic accents, keeps CJK dakuten, and splits unspaced scripts into bigrams. A second
normaliser would fold "Café Night" differently in the duplicate prompt than in the dedup path,
which is exactly the drift AD-21 exists to prevent. `jaccard()` takes two *fingerprints*, so the
rule computes `title_fingerprint()` on each name and compares — the same machinery rule (b) uses.

**The threshold constant.** `TITLE_JACCARD_MIN` is already `Fraction(4, 5)` — exactly 80%, and
already used by the dedup path. The work item asks whether the duplicate rule should share it or
declare its own. **Decision: share it.** Both are the same threshold — "≥80% Jaccard overlap on
tokens" — differing only in what they are applied to (catalog identity vs. a user-facing
duplicate prompt). Two constants with the same value that mean the same thing can drift apart
later; one constant named for what it means cannot. It is renamed `TITLE_TOKEN_OVERLAP_MIN` to
describe the measure rather than its current single caller, and the PRD's wording matches: the
PRD says "≥80% Jaccard overlap **on tokens**" for both the identity rule and the duplicate rule.

A float `0.8` would not be exactly 4/5, so the boundary test would be a lie. `Fraction` stays.

**The 24-hour window.** A new constant, `DUPLICATE_START_WINDOW = timedelta(hours=24)`. "Starts
within 24 hours" is read as an **absolute** difference between start instants (not a signed
one-sided window), so a candidate 23 hours *earlier* counts as within the window. The PRD says
"starts within 24 hours", which is symmetric phrasing.

**Error handling.** An interval whose end precedes its start is invalid input. Rather than a bare
`ValueError`, the module raises a domain error from `domain/errors.py` so the HTTP mapping in
`config/errors.py` stays in one place. A new `InvalidIntervalError(ValidationError)` is added
there.

### Files to Create

| File | Purpose |
|------|---------|
| `backend/domain/conflict.py` | The single overlap function and the FR-58 duplicate rule |
| `backend/tests/domain/test_conflict.py` | Golden tests for both rules, Django-free |

### Files to Modify

| File | Changes |
|------|---------|
| `backend/shared/constants.py` | Rename `TITLE_JACCARD_MIN` → `TITLE_TOKEN_OVERLAP_MIN`; add `DUPLICATE_START_WINDOW` |
| `backend/domain/dedup.py` | Import the renamed constant |
| `backend/domain/errors.py` | Add `InvalidIntervalError` |
| `backend/tests/shared/test_constants.py` | Update the renamed import and pin the new constants |

### Tests

| Test File | Coverage |
|-----------|----------|
| `backend/tests/domain/test_conflict.py` | Overlap boundaries (0, 1s, exactly 15m, 15m+1s, containment, midnight span, back-to-back, no end) and duplicate rules (case, 80% boundary, just-below, outside 24h) |

### Technical Details

**Overlap arithmetic.** The standard interval-overlap formula:

```python
overlap = min(a_end, b_end) - max(a_start, b_start)
return overlap > CONFLICT_MIN_OVERLAP
```

This is negative for disjoint intervals and zero for back-to-back ones — both correctly below
the threshold. For an open-ended interval, `min(a_end, b_end)` needs an infinite sentinel, so
`datetime.max` stands in for "no end".

**Golden tests.** `tests/domain/test_dedup.py` pins behaviour with exact expected values rather
than re-deriving it, so a change to normalisation or arithmetic fails loudly instead of silently
re-baselining. `test_conflict.py` follows the same style: exact boundary values, parametrised
with readable `ids=`, and the domain's `test_<unit>_<condition>_<expected>` naming
(`test_conflicts_overlap_exactly_15min_returns_false` is the standard's own worked example).

**What this item must not do.** It touches no model, no migration, no API and no frontend. It
does not implement the candidate scan (±30-minute window), the persistence of a `CONFLICT_PAIR`,
or the resolution actions — those belong to work items ③ and ⑤.

