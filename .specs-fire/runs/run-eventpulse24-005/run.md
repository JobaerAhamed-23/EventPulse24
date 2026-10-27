---
id: run-eventpulse24-005
scope: single
work_items:
  - id: architecture-contracts
    intent: project-scaffold
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
current_item: null
status: completed
started: 2026-10-27T12:55:45.292Z
completed: 2026-10-27T13:19:01.689Z
---

# Run: run-eventpulse24-005

## Scope
single (1 work item)

## Work Items
1. **architecture-contracts** (confirm) — completed


## Current Item
(all completed)

## Files Created
- `backend/tests/architecture/checkers.py`: AST checkers: stdlib-only allowlist, database-alias scanner
- `backend/tests/architecture/test_import_contracts.py`: Clean run, 15 planted violations (exact sets), 7 allowed controls, coverage + drift guards
- `backend/tests/architecture/test_stdlib_only.py`: domain + shared/__init__, constants, ids are stdlib-only; planted cases
- `backend/tests/architecture/test_database_alias.py`: Every project file names its alias; forbidden/allowed forms
- `backend/tests/architecture/test_env_access.py`: Ruff TID251 via stdin per path

## Files Modified
- `backend/pyproject.toml, backend/uv.lock`: import-linter 2.15 (dev); 12 [tool.importlinter] contracts; Ruff TID + banned-api os.environ/getenv; per-file ignores config/**, manage.py, tests/**
- `backend/config/checks.py`: eventpulse.E005 UUIDv7 PK on all project-package models; PROJECT_PACKAGES
- `backend/tests/config/test_checks.py`: +5 E005 tests
- `Makefile`: lint-imports target; lint-backend runs it
- `README.md, docs/setup/{ubuntu,macos}.md`: lint-backend / lint-imports
- `.specs-fire/standards/coding-standards.md`: Key Rules rewritten as enforced rules; AD-2 shared.constants/ids departure; ports loosening; scanner limitations; AD-8 cost-row placement
- `.specs-fire/standards/tech-stack.md`: import-linter 2.15
- `.specs-fire/intents/project-scaffold/work-items/{ci-pipeline,ports-fakes-and-worker}.md`: lint-backend covers contracts; Celery app in config/celery.py, tasks by string, no apps.*.api from worker

## Decisions
- **AD-2 departure: domain imports**: stdlib plus shared.constants and shared.ids (both stdlib-only, as is shared/__init__) (Thresholds live once (AD-8/AD-16/AD-21) without passing every constant as a parameter; spine says stdlib only)
- **Layers**: config | worker > apps | adapters > ports > domain > shared (AD-1: API surface and worker never import each other; apps reach adapters via ports)
- **SDK contracts**: Direct imports only (allow_indirect_imports = true) (Wiring config/worker -> adapters.llm -> anthropic is intended; layers already block apps -> adapters)
- **Cross-app models**: protected contract per app (direct importers only, verified in import-linter 2.15 source); chain via services pinned by a test (Service calls must stay legal)
- **Stdlib-only and alias rules**: AST tests, not import-linter/Ruff (import-linter can't express an allowlist; Ruff has no custom rules)
- **os.environ ban**: Ruff TID251; exempt config/**, manage.py, tests/**; Celery app goes in config/celery.py (Single config reader; standard Django layout needs no new exemption)
- **E005 scope**: All our top-level packages, through tables skipped (AD-8 cost-row model will live in adapters/llm)
- **ports may import all of shared**: Deliberate loosening of spine (ports -> domain only) (Acceptable while ports are Protocols over plain types)
- **lint-backend**: Runs ruff, format check and lint-imports (One command (and one CI target) covers all static rules)


## Summary

- Work items completed: 1
- Files created: 5
- Files modified: 8
- Tests added: 172
- Coverage: 0%
- Completed: 2026-10-27T13:19:01.689Z
