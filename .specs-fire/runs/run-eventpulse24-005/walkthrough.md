---
run: run-eventpulse24-005
work_item: architecture-contracts
intent: project-scaffold
generated: 2026-10-27
mode: confirm
---

# Implementation Walkthrough: AD-2 Architecture Contracts

## Summary

The architecture's import and configuration rules are now checked by tools, not by review:
- 12 import-linter contracts
- a Ruff ban on reading the environment outside `config/`
- two AST tests: `domain` is stdlib-only, and database calls name their alias
- system check `eventpulse.E005` (UUIDv7 primary keys)

Each rule is proven by planting a violation in a copy of the tree and asserting that **exactly** the expected rule breaks, while the intended paths (wiring adapters in, calling another app's services) stay legal. The suite grew from 174 to 346 tests, and 12/12 mutations were caught.

## Structure Overview

- **Configuration:** the contracts live in `backend/pyproject.toml` beside Ruff's config.
- **Commands:** `make lint-backend` runs Ruff, the format check and `lint-imports`, so one command covers every static rule. `make lint-imports` runs only the contracts.
- **AST rules:** the rules no off-the-shelf tool can express are AST tests in `tests/architecture/`, using shared checker functions.
- **Primary keys:** the PK rule is a system check beside E001–E004.
- **Proof that each rule fires:** `tests/architecture/test_import_contracts.py` copies the packages to `tmp_path`, plants modules and runs `lint-imports` there.

## Architecture

### Layer Structure (as enforced)

```text
   config  |  worker          ← independent (AD-1): API surface and worker runtime never import each other
       │         │              worker also never imports apps.*.api
   apps    |  adapters        ← independent: apps reach adapters through ports + settings
       │         │              apps.X.models imported only by apps.X; adapters never import each other
          ports
            │
          domain              ← stdlib + shared.constants + shared.ids only (AST allowlist)
            │
          shared              ← bottom utility layer (may use Django; imports nothing of ours above)

SDKs: anthropic/voyageai/openai/instructor only in adapters.llm; stripe only in adapters.billing (direct)
Env:  os.environ/getenv only in config/** (+ manage.py, tests)
DB:   every atomic()/on_commit() passes using=PERSONAL|CATALOG; no literal aliases; no django.db.connection
PKs:  every model in our packages subclasses UUIDv7Model (E005)
```

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `backend/tests/architecture/checkers.py` | AST checkers: stdlib allowlist, alias scanner |
| `backend/tests/architecture/test_import_contracts.py` | Clean run, 15 planted violations, 7 allowed controls, coverage and drift guards |
| `backend/tests/architecture/test_stdlib_only.py` | Stdlib-only for `domain` and the `shared` modules it may import |
| `backend/tests/architecture/test_database_alias.py` | Alias rule on every project file, plus forbidden and allowed forms |
| `backend/tests/architecture/test_env_access.py` | Ruff `TID251` per path |

### Modified

| File | Changes |
|------|---------|
| `backend/pyproject.toml`, `uv.lock` | `import-linter==2.15`; 12 contracts; Ruff `TID` + banned-api + exemptions |
| `backend/config/checks.py`, `tests/config/test_checks.py` | E005 + 5 tests |
| `Makefile` | `lint-imports`; `lint-backend` runs it |
| `README.md`, `docs/setup/*.md` | Lint commands |
| `.specs-fire/standards/{coding-standards,tech-stack}.md` | Rules as enforced; recorded departures; AD-8 cost-row placement; scanner limits |
| Work items `ci-pipeline`, `ports-fakes-and-worker` | CI target; Celery app location and string references |

## Key Implementation Details

### 1. The intended paths stay legal

- **Wiring in an SDK:** the SDK bans check **direct** imports only (`allow_indirect_imports = true`). So `config → adapters.llm → anthropic` (wiring the adapter in) passes, while `apps.catalog → anthropic` fails.
- **Cross-app calls:** the per-app `protected` contracts check direct importers only, which I confirmed in import-linter 2.15's source. So `apps.catalog → apps.ingestion.services → apps.ingestion.models` passes. Both are pinned by allowed-control tests, so a tool upgrade that changed either behaviour fails loudly.

### 2. Exact-set assertions

Each planted case asserts that the set of broken contracts *equals* the expected set. A plant that broke two contracts, or a mutation that passed only because some other contract broke, would fail the test. Writing these sets caught one error in the plan itself (`domain → ports` breaks only `layers`).

### 3. Two AST rules

- **Stdlib-only:** every import in `domain/**`, `shared/__init__.py`, `shared/constants.py` and `shared/ids.py` must resolve to `sys.stdlib_module_names`, `domain` itself, or `shared.constants` / `shared.ids`. Relative imports are resolved against the file's package.
- **Database alias:**
  - `atomic()` and `on_commit()` must pass `using=`
  - no bare `@atomic`
  - no string literal or `None` as an alias in `using=`, `.using()` or `connections[...]`
  - no singular `django.db.connection`

### 4. Coverage cannot rot silently

Guards assert that:
- every backend package is a `root_package`
- every adapter is in the SDK contracts' sources
- every app has its `models-<app>` contract
- the three copies of the package list agree (import-linter config, E005 scope, scanner scope)

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **AD-2 departure** | `domain` may import `shared.constants` and `shared.ids` (both stdlib-only, as is `shared/__init__`) | Thresholds live once (AD-8/16/21); the spine says "stdlib only" |
| Layers | `config \| worker` > `apps \| adapters` > `ports` > `domain` > `shared` | AD-1 and AD-2 |
| SDK contracts | Direct imports only | Wiring adapters in is intended |
| Cross-app models | `protected` per app (direct only) | Service calls stay legal |
| Stdlib and alias rules | AST tests | import-linter can't express an allowlist; Ruff has no custom rules |
| `os.environ` | Ruff `TID251`; exempt `config/**`, `manage.py`, `tests/**` | A single config reader |
| E005 scope | All our packages; through tables skipped | AD-8's cost-row model will live in `adapters/llm` |
| `ports` → all of `shared` | Deliberate loosening | Fine while ports are Protocols over plain types |
| `lint-backend` | Includes `lint-imports` | One command and one CI target |

## Deviations from Plan

- **`test_package_lists_agree`** was added at code review: the package list lives in three places.
- **One more planted case:** `adapters.billing → openai` (another adapter importing an LLM SDK).
- **One more allowed control:** `adapters.billing → stripe`.

## Dependencies Added

| Package | Why Needed |
|---------|------------|
| `import-linter==2.15` (dev; brings `grimp` 3.18, `click`, `rich`) | Import-graph contracts (AD-1/AD-2/AD-8) |

## How to Verify

1. **All static rules**
   ```bash
   make lint-backend
   ```
   Expected: `All checks passed!`, `… already formatted`, `Contracts: 12 kept, 0 broken.`

2. **Tests, including the planted violations**
   ```bash
   make test-backend
   ```
   Expected: `346 passed`

3. **See a contract break**
   Add `import anthropic` to `backend/apps/catalog/services/__init__.py`, then run `make lint-imports`.
   Expected: `AD-8 only adapters.llm imports an LLM provider SDK BROKEN`. Remove the line afterwards.

4. **See the environment ban**
   Add `import os; X = os.getenv("X")` to any file under `backend/apps/`, then run `make lint-backend`.
   Expected: `TID251`. Remove the line afterwards.

## Test Coverage

- Tests added: 172 (174 → 346; most are per-file alias and planted cases), plus 12/12 mutation checks
- Coverage: not measured yet (added by `ci-pipeline`)
- Status: passing

## Ready for Review

- [x] All acceptance criteria met
- [x] Tests passing
- [x] No critical issues
- [x] Documentation updated
- [x] Developer notes captured

## Developer Notes

- **Adding a top-level package, an adapter or an app:** update `[tool.importlinter]` (`root_packages`, the SDK contracts' `source_modules`, a new `models-<app>` contract), `config.checks.PROJECT_PACKAGES` and `tests/architecture/checkers.ROOT_PACKAGES`. The guards fail until all of them agree.
- **Needing the user type in another app:** use `get_user_model()`, or `settings.AUTH_USER_MODEL` in an FK. Importing `apps.identity.models` breaks `models-identity`.
- **The Celery app** goes in `config/celery.py`. Reference tasks and beat entries by dotted string; `config` and `worker` may not import each other.
- **The AD-8 cost row:** `adapters/llm/models.py`, routed to `catalog`, `NOT_USER_DATA`, `UUIDv7Model`. The dashboard reads it through a port (coding-standards).
- **The alias scanner is syntactic:** it misses `import django.db` then `django.db.connection`, re-bound names, and dynamic calls. Review covers those.
- **On the Mac:** `uv sync` happens automatically on the next `make` command, which picks up `import-linter`. No database change.
- **Nothing is committed yet**; everything is on `setup-specsmd`.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-005*
