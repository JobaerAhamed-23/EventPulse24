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
