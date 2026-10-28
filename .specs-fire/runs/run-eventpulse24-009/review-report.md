# Code Review Report

**Run**: run-eventpulse24-009
**Intent**: project-scaffold
**Reviewed**: 2026-10-28
**Files Reviewed**: 10 (`.github/workflows/ci.yml`, `.github/dependabot.yml`, `backend/pyproject.toml`, `backend/uv.lock`, `Makefile`, `README.md`, `docs/setup/{macos,ubuntu}.md`, `testing-standards.md`)

---

## Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Code Quality | 0 | 0 | 0 |
| Security | 0 | 0 | 1 |
| Architecture | 0 | 0 | 0 |
| Testing | 0 | 0 | 1 |
| **Total** | **0** | **0** | **2** |

**Tests Status**: Passing (locally and on GitHub; the red check behaved as designed)

`actionlint` was clean before review. No changes were made after the GitHub verification, so the verified workflow is exactly what's committed.

---

## Skipped (recorded)

- **[Testing] The contract check uses `git diff --exit-code`, which ignores untracked files.** If a future generator wrote an additional *new* file into `frontend/lib/api/`, it wouldn't fail. Today both outputs (`openapi.json`, `schema.ts`) are tracked, so the check is complete. Hardening it means also failing on `git status --porcelain -- frontend/lib/api/`. Recorded rather than changed, so the pipeline stays exactly as verified on GitHub.
- **[Security] Branch protection isn't configured.** It's a GitHub repository setting, outside the code. To enforce the constitution ("all PRs must pass CI", "no self-merging"), require these checks on `main`:
  - `Backend (lint, checks, tests + coverage)`
  - `API contract (AD-19)`
  - `Frontend (lint, typecheck, tests, build)`

  Also require an approving review.

---

## Notes

- **Least privilege:** `permissions: contents: read`; no secrets used; CI-only database and Django values are clearly labelled and grant nothing outside the job.
- **Pinned actions:** each third-party action is pinned to a full commit SHA, with Dependabot updating the pins weekly. `${{ job.services.postgres.id }}` in a `run:` line is runner-provided, not user input, so it can't be injected.
- **Parity:** every job step is a `make` target, or a command the docs also list, and each was run locally before pushing. The `.env`-less backend run showed CI needs nothing from a developer's `.env`.
- **Cost:** three jobs, about 10–15 minutes of runner time per push. A branch with an open PR runs twice (push + PR). That's acceptable within the private repo's 2,000 free minutes; narrowing `push` to `main` later halves it if needed.
