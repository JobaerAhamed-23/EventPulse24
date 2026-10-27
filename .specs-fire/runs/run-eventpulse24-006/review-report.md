# Code Review Report

**Run**: run-eventpulse24-006
**Intent**: project-scaffold
**Reviewed**: 2026-10-27
**Files Reviewed**: 31 (21 created, 10 modified; docs and standards included)

---

## Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Code Quality | 0 | 0 | 0 |
| Security | 0 | 1 | 0 |
| Architecture | 1 | 0 | 1 |
| Testing | 1 | 0 | 1 |
| **Total** | **2** | **1** | **2** |

**Tests Status**: Passing (429; lint clean; 12 contracts kept)

---

## Files Reviewed

- `backend/ports/{email,llm,embedding,billing,calendar,registry}.py` (created)
- `backend/adapters/email/{smtp,memory}.py`, `adapters/llm/fake.py`, `adapters/billing/fake.py`, `adapters/calendar/fake.py` (created)
- `backend/config/{adapters,celery}.py`, `config/management/commands/send_test_email.py` (created)
- `backend/worker/tasks.py` (created)
- `backend/config/{__init__,settings}.py`, `backend/adapters/logging/{formatter,redaction}.py` (modified)
- `backend/pyproject.toml`, `backend/uv.lock`, `Makefile`, `.gitignore` (modified)
- Tests: `tests/ports/*`, `tests/worker/*`, `tests/config/test_adapters.py`, `tests/config/test_send_test_email.py`, `tests/adapters/test_email_smtp.py`, `tests/adapters/test_fakes.py` (created), `tests/adapters/test_logging.py` (modified)
- `README.md`, `docs/setup/{macos,ubuntu}.md`, `.specs-fire/standards/{tech-stack,coding-standards}.md`, `health-round-trip.md` (modified)

Ruff (`check` + `format --check`) and `lint-imports` were clean before review.

---

## Auto-Fixed Issues

### 1. [Architecture] `EmailPort.send` could be overridden, skipping the AD-20 checks

- **File**: `backend/ports/email.py`
- **Fix**: `@typing.final` on `send`, with a comment. Annotation only: type checkers and readers see that adapters implement `_deliver`, never `send`. No runtime change.

### 2. [Testing] `send_test_email` had only the manual check

- **File**: `backend/tests/config/test_send_test_email.py` (new, 3 tests)
- **Fix**: transactional and bulk sends through the command reach the outbox on the right stream, and the unsubscribe header appears on bulk only. The defaults are checked too.

Tests re-run after the fixes: 424 passed.

---

## Applied Suggestions (user-approved)

### 1. [Security] Password-only URLs weren't scrubbed (AD-13)

- **File**: `backend/adapters/logging/redaction.py`, a pattern added in run-eventpulse24-004 and surfaced here because Redis URLs now exist.
- **Before**:
  - `redis://:s3cretpass@10.0.0.5:6379/0` was logged unchanged
  - `redis://:s3cretpass@cache.example.com/0` came out as `redis://:[email]…`, which hides the password only by accident
- **Fix**: the user part of the URL-credential pattern may be empty (`[^/\s:@]*:`). Five parametrized cases cover user + password, password only with a domain host, password only with an IP host, no credentials, and an IPv6 host left untouched.
- **Mutation-checked**: putting the old `+` back fails 2 cases.
- **Context**: kombu masks passwords in its own messages (`as_uri()` → `redis://:**@…`), so nothing leaked; the scrubber is the backstop.

Tests re-run: 429 passed.

---

## Skipped (low value, recorded)

- [Architecture] **Eager task runs mint a fresh trace id** instead of inheriting the caller's. `task_always_eager` is off, and `tick.apply()` is used only in tests, so a real worker is unaffected. If eager mode is ever turned on for local runs, `bind_task_trace_id` should fall back to `current_trace_id()` before minting.
- [Testing] **No test pins the `setup_logging` handler.** Under pytest the root logger already has handlers, so Celery wouldn't add its own either way, and a test couldn't tell the difference. The live run (all worker lines JSON) is the evidence; `worker_hijack_root_logger = False` is tested.

---

## Notes

- The review found no hard-coded secrets, raw SQL or other injection risks. Header injection through the subject or unsubscribe URL is blocked by Django's mail (`BadHeaderError`).
- Port modules import only the stdlib plus their own port types. `ports/registry.py` is the single Django-importing module in `ports`, as recorded in coding-standards.
- A `/tmp` backup was used briefly during the mutation check. It was removed straight away, but the session's scratchpad was the right place for it.
