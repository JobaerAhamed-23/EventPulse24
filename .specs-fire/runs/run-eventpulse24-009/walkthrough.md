---
run: run-eventpulse24-009
work_item: ci-pipeline
intent: project-scaffold
generated: 2026-10-28
mode: confirm
---

# Implementation Walkthrough: CI Pipeline (GitHub Actions)

## Summary

Every quality gate now runs on GitHub for each branch push and each pull request to `main`. There are three parallel jobs (backend, API contract, frontend), each calling the same `make` targets developers use locally. Backend coverage is gated: at least 80% of the application code overall, and 100% of `domain/`.

Verified on GitHub:
- the PR `setup-specsmd → main` is green on all three jobs
- a throwaway branch with a deliberately stale contract turned the **contract and backend jobs red** while the frontend stayed green; the branch was then deleted

This run was started by another session and continued here at your request.

## Structure Overview

```text
push (any branch) / pull_request (→ main)      permissions: contents: read
          │                                     concurrency: cancel outdated runs, except on main
          ├── backend   ─ services: pgvector 0.8.6-pg18, redis 8-alpine
          │               init script (docker exec into the PG service)
          │               make lint-backend → manage.py check → makemigrations --check
          │               → make coverage-backend (≥80% overall, 100% domain/)
          ├── contract  ─ uv + Node 24 + pnpm → make client → git diff --exit-code frontend/lib/api/
          └── frontend  ─ Node from .nvmrc, corepack pnpm, store cache
                          make web-install → make lint-web → make test-web → pnpm build
Actions pinned by commit SHA; .github/dependabot.yml updates them weekly.
```

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `.github/workflows/ci.yml` | The pipeline |
| `.github/dependabot.yml` | Weekly updates of the pinned actions |

### Modified

| File | Changes |
|------|---------|
| `backend/pyproject.toml`, `uv.lock` | `pytest-cov==7.1.0`; `[tool.coverage.run]` sources = the 7 application packages; `[tool.coverage.report]` `fail_under = 80` |
| `Makefile` | `coverage-backend` (both gates) |
| `README.md`, `docs/setup/{macos,ubuntu}.md` | `make coverage-backend`; "CI runs these same targets" |
| `.specs-fire/standards/testing-standards.md` | How coverage is measured, the two gates, the jobs, triggers and pinning. The constitution is untouched (plan review). |

## Key Implementation Details

1. **Parity:** each CI step is a `make` target. The backend job was run locally **with `.env` moved away**, using only environment variables, to prove CI needs nothing from a developer's machine.
2. **Database setup:** Actions can't mount the init folder, so the same `01-schemas-and-roles.sh` runs inside the Postgres service container. That's the same `psql` as local; the runner's own client isn't used.
3. **Two coverage gates:** coverage has no per-folder threshold, so the `domain/` 100% check is a second `coverage report --include` step.
4. **`main` is never cancelled:** `cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}`. Two quick merges both get a result.

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Continue run 009 | Yes (you) | It was started by another session |
| Coverage scope | Application packages, line coverage | Test files would inflate the number |
| Triggers | Every branch push + PRs to `main` | The throwaway-branch check needs branch pushes |
| Pinning | Commit SHAs + Dependabot | Supply-chain safety without stale pins |
| Frontend build in CI | Yes | Catches production-only errors (frontend-skeleton hand-off) |
| Constitution | Not edited | It's the governing document; testing-standards carries the detail |

## Deviations from Plan

- `push` limited to `branches: ["**"]`, so tag pushes don't trigger CI.
- The pnpm store path comes from `pnpm store path` rather than being hard-coded.
- **My slip:** during the throwaway-branch check, `git commit -a` captured the uncommitted run 009 entry in `state.yaml`. It was restored immediately and verified identical; the branch is deleted.

## Dependencies Added

| Package | Why |
|---------|-----|
| `pytest-cov` 7.1.0 (dev) | Coverage gate |
| GitHub Actions: `actions/checkout` v7.0.1, `actions/setup-node` v7.1.0, `actions/cache` v6.1.0, `astral-sh/setup-uv` v10.3.2 | CI (SHA-pinned) |

## How to Verify

1. **Locally:** `make coverage-backend && make lint-backend && make test-web && make lint-web` gives the same result CI will.
2. **On GitHub:** the PR's **Checks** tab shows `Backend (lint, checks, tests + coverage)`, `API contract (AD-19)` and `Frontend (lint, typecheck, tests, build)`.
3. **Recommended next (your GitHub settings):** Settings → Branches → add a rule for `main`.
   - Require those three checks.
   - Require a pull request with 1 approval.
   - Block force pushes.

   That turns the constitution's "all PRs must pass CI" into something GitHub enforces.

## Test Coverage

- Tests added: 0 (the workflow is the test). Coverage gates introduced: 96.95% overall, `domain/` 100%.
- Status: green on the PR; red, as intended, on the broken-contract branch.

## Developer Notes

- **A contract failure** prints "frontend/lib/api/ is out of date with the API. Run 'make client' and commit it." The fix is exactly that.
- **The contract check uses `git diff`,** so a *new untracked* file in `lib/api/` wouldn't be caught. Both generated files are tracked today (review note).
- **A branch with an open PR runs CI twice** (push + PR event).
- **The repo is private,** and `gh` isn't installed on the Mac. Reading check results from the terminal needs `brew install gh && gh auth login`.

## Ready for Review

- [x] All acceptance criteria met, verified locally and on GitHub
- [x] Throwaway branch deleted
- [ ] Branch protection on `main`: your GitHub setting
- [ ] Ubuntu verification of `health-round-trip`: still pending, and the last open item of the intent
