---
id: repo-hygiene-cleanup
title: Repository Hygiene Cleanup
intent: personal-events-and-saved-catalog
complexity: low
mode: autopilot
status: pending
depends_on: []
created: 2026-10-29
---

# Work Item: Repository Hygiene Cleanup

## Description

The repository root and the `backend/` and `frontend/` trees carry roughly 30 Finder duplicate files — `Makefile 2.py`, `README 2.md`, `docker-compose 2.yml`, `apps/personalization/api 2.py`, `domain/confidence 2.py`, and similar. These are AppleDouble artifacts produced when a file is copied or renamed in Finder, and they are near-copies of real source files.

They are a real hazard, not just clutter. `pytest` collects `test_*.py`, `ruff` and `mypy` scan `.py` files, and ESLint and TypeScript scan `.ts`/`.tsx` files — so a duplicate `backend/domain/confidence 2.py` is a second module with the same contents, and a duplicate `frontend/app/page 2.tsx` is a second copy of a React page. Depending on the collector's glob and the file's extension, these can be imported, linted, type-checked or collected as tests. At best they slow the suite down; at worst they produce misleading failures, duplicate test IDs, or a linter report that points at code nobody edits.

This work item removes them before any new implementation lands, so every subsequent run's test counts and lint results are trustworthy.

## Acceptance Criteria

- [ ] Every duplicate `* 2.*` / `* 2` artifact is identified by an explicit inventory, and each is confirmed **untracked by git** (`git ls-files --error-unmatch` fails) before deletion. If any duplicate is tracked, it is removed with `git rm` in this same work item, not left behind.
- [ ] No legitimate file is deleted. A file whose name merely *contains* a digit `2` (for example `run-eventpulse24-002`, `adapters/llm/voyage.py`, or a genuine `v2.py`) is not a duplicate and stays. The inventory is reviewed against the `git ls-files` list before anything is removed.
- [ ] The duplicate count in the working tree after cleanup is zero, verified by a glob for the known duplicate suffixes (`* 2.py`, `* 2.ts`, `* 2.tsx`, `* 2.md`, `* 2.yml`, `* 2.yaml`, `* 2.json`, `* 2.toml`, `* 2.lock`, `* 2.tsx`, `* 2.css`, `* 2.mts`, `* 2.mjs`, `* 2.css`).
- [ ] The backend test count is **identical** before and after the cleanup. Both numbers are recorded in the test report. A difference proves a duplicate was being collected, and that fact is reported rather than silently absorbed.
- [ ] The frontend test count is identical before and after the cleanup, recorded the same way.
- [ ] `make lint-imports` still passes and `ruff check` reports no new violations.
- [ ] `git status` shows only the intended deletions, with no unrelated modifications.
- [ ] The cleanup is a **separate commit** from any feature work, so it can be reverted independently.

## Technical Notes

This is a hygiene commit, not a refactor. Resist the temptation to reorganise anything else while the tree is open.

AppleDouble naming on macOS is `<name> 2.<ext>` — the literal string ` 2` before the extension. The inventory should be produced with a glob over the whole repo, then filtered to `git ls-files` for the tracked/untracked decision.

Note that `backend/apps/personalization/api 2.py` and several others sit next to their originals inside package directories. Python's import machinery will not normally pick up a module whose filename contains a space, so the practical risk is concentrated in the **linting and type-checking** layers and in any `* 2.py` that pytest's `python_files` pattern might match — but the cleanup removes the ambiguity entirely rather than reasoning about which collector is affected.

Do not delete `Makefile 2.py`-style artifacts that are actually **referenced** by a script or the Makefile. Check `Makefile`, `scripts/`, `.github/workflows/` and `frontend/package.json` for references to the duplicate names before removing them.

## Dependencies

(none)
