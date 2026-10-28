---
run: run-eventpulse24-009
work_item: ci-pipeline
intent: project-scaffold
generated: 2026-10-28
status: passed
machine: macOS 26.4.1 (local checks) + GitHub Actions (ubuntu-latest)
---

# Test Report: CI Pipeline (GitHub Actions)

## Summary

| Check | Result |
|-------|--------|
| `actionlint` 1.7.12 (Docker, pinned by digest; includes shellcheck) on `ci.yml` | clean |
| Backend gates run locally **with no `.env`**, env vars only, as in CI | lint + 12 contracts kept, `check` clean, no missing migrations, 438 passed |
| `make coverage-backend` | 96.95% overall (floor 80%), `domain/` 100% |
| DB init step command (`docker exec -i <pg> sh -s < init script`) against the local container | ok (idempotent) |
| Contract step locally: clean / planted summary change / restored | no diff / `git diff` exit 1 / no diff |
| Frontend steps locally (`web-install`, `lint-web`, `test-web`, `build`) | clean; 51 passed; build ok |
| **GitHub: PR `setup-specsmd` → `main`** | **all three jobs green** (reported by user) |
| **GitHub: throwaway branch with a stale contract** | **API contract ❌, Backend ❌, Frontend ✅**, exactly as expected (reported by user); branch deleted afterwards |
| Mutation checks | 4/4 caught (see below) |

## Acceptance Criteria Validation

- ✅ **`.github/workflows/ci.yml` triggers on push and pull_request:**
  - push to every branch (not tags) and pull requests to `main`
  - outdated runs cancelled except on `main`
- ✅ **Backend job:**
  - **Services:** `pgvector/pgvector:0.8.6-pg18` (the same image as compose), with the same init script run inside the container, plus Redis 8.
  - **Tooling:** uv with Python 3.13 from `requires-python`.
  - **Checks:** `ruff check`, `ruff format --check`, `lint-imports` (`make lint-backend`); `manage.py check`; `makemigrations --check --dry-run`; `pytest --cov` with `fail_under` 80, plus a 100% gate for `domain/`.
- ✅ **Contract job:** export OpenAPI, regenerate the TS client, fail if `git diff` shows changes. **Proven red on GitHub** with a stale contract.
- ✅ **Frontend job:** pnpm install (store cached), `lint`, `typecheck`, `test`, plus a production build.
- ✅ **Dependency caching:** uv via `setup-uv` (keyed on `backend/uv.lock`); pnpm store via `actions/cache` (keyed on `frontend/pnpm-lock.yaml`, path from `pnpm store path`).
- ✅ **Verified:** green on a PR; a deliberately broken contract makes it red.

## Mutation Checks (each reverted after)

- **Overall floor raised to 99%:** `make coverage-backend` exits non-zero.
- **Untested function planted in `domain/`:** "Coverage failure: total of 91 is less than fail-under=100".
- **Contract drift locally:** `git diff --exit-code -- frontend/lib/api/` exits 1.
- **Contract drift on GitHub:** the contract and backend jobs go red; frontend stays green.

## Issues Found During Execution

| Issue | Resolution |
|---|---|
| `pytest-cov>=7.1.0` (added by the session that started this run) wasn't pinned like the other dev dependencies | `==7.1.0` |
| A bare `on: push` also fires on tag pushes | `branches: ["**"]` |
| The pnpm store path differs between pnpm versions | Taken from `pnpm store path` instead of hard-coded |
| **My slip:** `git commit -a` on the throwaway branch also captured the uncommitted run 009 entry in `state.yaml`, and switching back removed it from the working tree | Restored from that commit with `git checkout c5f9ed9 -- .specs-fire/state.yaml` and unstaged; verified identical. CI never reads that file, and the throwaway branch is deleted. |
| The `gh` CLI isn't installed, and the repo is private | The user opened the PR on github.com and reported the check results; I didn't read credentials from the keychain to query the API |

## Ready for Review

- [x] All acceptance criteria validated, locally and on GitHub
- [x] Throwaway branch deleted (remote and local)
