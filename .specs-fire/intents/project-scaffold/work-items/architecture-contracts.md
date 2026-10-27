---
id: architecture-contracts
title: AD-2 Architecture Contracts
intent: project-scaffold
complexity: medium
mode: confirm
status: completed
depends_on:
  - backend-skeleton
created: 2026-10-27
run_id: run-eventpulse24-005
completed_at: 2026-10-27T13:19:01.689Z
---

# Work Item: AD-2 Architecture Contracts

## Description

Make the layering rules machine-checked: import-linter contracts plus lint bans, with tests proving the contracts actually catch violations.

## Acceptance Criteria

- [ ] `.importlinter` (or `[tool.importlinter]`) contracts: `domain` may import stdlib only; `apps.X` may not import `apps.Y.models`; adapters may not import other adapters; layers point inward (`domain` ← `ports` ← `apps`/`adapters` ← `worker`/api surfaces)
- [ ] Provider SDKs (`anthropic`, `voyageai`, `openai`, `stripe`) forbidden outside their adapter package
- [ ] Ruff banned-api rule: `os.environ` / `os.getenv` forbidden outside `config/`
- [ ] `make lint-imports` runs `lint-imports` and passes on the clean tree
- [ ] Test proves enforcement: a fixture plants a violating module (e.g. `domain` importing `django`), runs the contract check, and asserts it fails
- [ ] A domain-importability test imports every `domain` module with Django not configured

## Technical Notes

- AD-2 says enforcement is 'import-linter contracts in CI, not review'.

## Dependencies

- backend-skeleton

## Hand-offs from earlier runs

- **`domain` → `shared.constants` / `shared.ids`** (shared-foundations): domain functions (`conflict.py`, `confidence.py`) will need the thresholds. Both modules are stdlib-only, with a fresh-interpreter test. Recommended: the `domain` contract allows exactly these two modules. The rest of `shared` imports Django/Ninja (`retention`, `errors`, `models`, `db`), so `domain` must not import `shared` as a whole. The alternative is to pass thresholds as parameters.
- **Primary-key rule** (shared-foundations): project models must subclass `shared.models.UUIDv7Model`. A system check or test over `apps.*` models.
- **`os.environ` ban** must exempt `backend/manage.py` (Django bootstrap `setdefault`) (backend-skeleton).
- **Alias-less database calls** (schema-router-spike): consider a rule for `transaction.atomic()` / `.using()` / `connections[...]` without `PERSONAL` / `CATALOG`; `default` silently means personal.
