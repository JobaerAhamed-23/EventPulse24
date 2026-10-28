---
id: run-eventpulse24-009
scope: single
work_items:
  - id: ci-pipeline
    intent: project-scaffold
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
current_item: null
status: completed
started: 2026-10-28T03:50:44.007Z
completed: 2026-10-28T04:32:34.607Z
---

# Run: run-eventpulse24-009

## Scope
single (1 work item)

## Work Items
1. **ci-pipeline** (confirm) — completed


## Current Item
(all completed)

## Files Created
- `.github/workflows/ci.yml`: CI: backend, contract and frontend jobs
- `.github/dependabot.yml`: Weekly updates for SHA-pinned actions

## Files Modified
- `backend/pyproject.toml`: pytest-cov==7.1.0; coverage source and fail_under 80
- `backend/uv.lock`: pytest-cov
- `Makefile`: coverage-backend
- `README.md`: CI runs the same targets
- `docs/setup/macos.md`: make coverage-backend
- `docs/setup/ubuntu.md`: make coverage-backend
- `.specs-fire/standards/testing-standards.md`: Coverage measurement, gates, CI jobs

## Decisions
- **Run ownership**: Continued run 009 started by another session (User choice)
- **Coverage**: Application packages only; 80% overall + 100% domain/; line coverage (testing-standards; 96.95% at introduction)
- **Triggers**: push to any branch + pull_request to main; cancel outdated runs except on main (Throwaway-branch verification; every main merge finishes (plan review))
- **Action pinning**: Full commit SHAs + Dependabot weekly (Supply-chain safety)
- **DB init in CI**: Init script via docker exec into the service container (Same script and psql as local)
- **Verification**: PR green; throwaway branch red (contract + backend), then deleted (User-approved pushes; user read the results (private repo, no gh))


## Summary

- Work items completed: 1
- Files created: 2
- Files modified: 7
- Tests added: 0
- Coverage: 0%
- Completed: 2026-10-28T04:32:34.607Z
