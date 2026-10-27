---
run: run-eventpulse24-005
work_item: architecture-contracts
intent: project-scaffold
generated: 2026-10-27
status: passed
---

# Test Report: AD-2 Architecture Contracts

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Import contracts (clean tree, 15 planted violations, 7 allowed controls, 4 coverage/drift guards) | 27 | 0 | 0 | n/a |
| Stdlib-only (real files + planted) | 17 | 0 | 0 | n/a |
| Database alias (one per project file + forbidden/allowed forms) | 104 | 0 | 0 | n/a |
| `os.environ` ban (Ruff via stdin) | 19 | 0 | 0 | n/a |
| E005 (added to `test_checks.py`) | 5 | 0 | 0 | n/a |
| Existing suite (unchanged) | 174 | 0 | 0 | n/a |
| **Total (pytest)** | **346** (was 174) | 0 | 0 | n/a |
| `make lint-imports` | 12 kept, 0 broken | | | |
| Mutation checks | 12/12 | 0 | 0 | n/a |

The full suite runs in about 6 s; the planted-violation tests account for about 4 s of that.

## Acceptance Criteria Validation

- ✅ **Contracts: `domain` stdlib only; `apps.X` may not import `apps.Y.models`; adapters independent; layers point inward.** `[tool.importlinter]` in `backend/pyproject.toml` has 12 contracts: layers (with `config | worker` for AD-1), `worker-not-api`, `domain-pure`, `models-<app>` ×6, `adapters-independent`, `llm-sdk` and `stripe-sdk`. "Stdlib only" is completed by the AST allowlist (`test_stdlib_only.py`). Allowing `domain` to import `shared.constants` / `shared.ids` is a recorded decision.
- ✅ **Provider SDKs forbidden outside their adapter.** `llm-sdk` (`anthropic`, `voyageai`, `openai`, `instructor`) and `stripe-sdk` check direct imports only, so wiring the adapter in is allowed. Detected even when the SDK isn't installed.
- ✅ **Ruff banned-api: `os.environ` / `os.getenv` forbidden outside `config/`.** `TID251` for `os.environ`, `os.environb`, `os.getenv`, `os.getenvb`; exempt: `config/**`, `manage.py`, `tests/**`.
- ✅ **`make lint-imports` runs `lint-imports` and passes on the clean tree.** Also part of `make lint-backend`; pinned by `test_clean_tree_keeps_every_contract`.
- ✅ **A fixture plants a violating module, runs the contract check, and asserts it fails.** 15 planted cases, each asserting the **exact** set of broken contracts, in a copy of the tree under `tmp_path` with `PYTHONPATH` replaced.
- ✅ **A domain-importability test imports every `domain` module with Django not configured.** It already existed (`test_domain_is_django_free.py`, a fresh interpreter without `DJANGO_SETTINGS_MODULE`). It is now complemented by the AST allowlist covering `shared/__init__.py`, `constants.py` and `ids.py`.

Hand-offs delivered:
- E005, the UUIDv7 primary-key rule, scoped to all our packages
- the `manage.py` exemption
- the alias scanner, which also catches `using=` literals and `None`

## Planted Cases

| Planted | Expected (exact) |
|---|---|
| `domain` → `django` | `domain-pure` |
| `domain` → `shared.retention` | `domain-pure` |
| `domain` → `ports` | `layers` |
| `ports` → `apps.catalog` | `layers` |
| `shared` → `config.env` | `layers` |
| `apps.catalog` → `adapters.email` | `layers` |
| `adapters.email` → `apps.identity` | `layers` |
| `config` → `worker` | `layers` |
| `worker` → `config.api` | `layers` |
| `worker` → `apps.catalog.api` | `worker-not-api` |
| `apps.catalog` → `apps.ingestion.models` | `models-ingestion` |
| `adapters.email` → `adapters.llm` | `adapters-independent` |
| `apps.catalog` → `anthropic` | `llm-sdk` |
| `adapters.billing` → `openai` | `llm-sdk` |
| `apps.delivery` → `stripe` | `stripe-sdk` |

**Allowed controls** (exit 0, nothing broken):
- `domain` → `shared.constants`
- an app → its own models
- **`apps.catalog` → `apps.ingestion.services` → `apps.ingestion.models`**
- `adapters.llm` → `anthropic`
- `adapters.billing` → `stripe`
- **`worker` → `adapters.llm` → `anthropic`**
- **`config` → `adapters.llm` → `anthropic`**

**Coverage guards:**
- every backend package is a root package
- every adapter is in the SDK contracts' sources (except its own)
- every app has a `models-<app>` contract
- the three package lists (`root_packages`, `PROJECT_PACKAGES`, `ROOT_PACKAGES`) agree (added at code review)

## Mutation Checks (each reverted after)

| Deliberate break | Result |
|---|---|
| Layers contract dropped | caught |
| `models-ingestion` contract dropped | caught |
| `django` removed from the `domain-pure` list | caught |
| `allow_indirect_imports = false` on `llm-sdk` | caught (the `worker → adapters.llm → anthropic` control fails) |
| `config : worker` (dependent) | caught |
| `os.environ` banned-api entry removed | caught |
| Stdlib allowlist loosened to allow anything | caught |
| Alias scanner ignores `on_commit` | caught |
| Alias scanner ignores `using=` literals | caught |
| E005 disabled | caught |
| E005 scoped to `apps` only | caught (the `adapters.llm.models` case) |
| `worker` dropped from `config.checks.PROJECT_PACKAGES` (code review) | caught by the drift guard |

## Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| None in the product code. The current tree already satisfied every contract (probed before planning, confirmed after). | n/a | n/a |
| One plan error found while writing the expected sets: `domain → ports` breaks only `layers`, not `domain-pure` | Low | Fixed in plan revision 2, before execution |

`import-linter` writes `backend/.import_linter_cache/`, which ignores itself (its own `.gitignore`).

## Ready for Completion

- [x] All tests passing
- [x] Coverage target met (n/a until ci-pipeline)
- [x] All acceptance criteria validated
- [x] No critical issues open

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-005*
