# Testing Standards

## Overview

Tests prove the architecture's invariants, not just behaviour. The algorithmic core (`domain/`) is tested in isolation with no database and no Django. Apps are tested against a real Postgres with both schemas. Structural rules (AD-2, AD-15, AD-19) are enforced by tooling in CI, not by review.

## Testing Framework

**Framework**: pytest + pytest-django (backend) · Vitest + Testing Library (frontend) · Playwright + axe-core (E2E/a11y)
**Runner**: `pytest` · `pnpm vitest` · `pnpm playwright test`

## Test Types

| Type | Tool | Location | When to Use |
|------|------|----------|-------------|
| Domain unit | pytest (no Django) | `backend/tests/domain/` | Every function in `domain/`: dedup identity, conflict, quiet hours, ranking, confidence |
| App / service | pytest-django, real Postgres | `backend/tests/apps/<module>/` | Named commands, ownership, schema routing, idempotency |
| API contract | pytest-django + Ninja TestClient | `backend/tests/api/` | Endpoint shapes, error mapping `{code, message}`, auth at edge |
| Worker | pytest-django | `backend/tests/worker/` | Sweep claim (`SKIP LOCKED`), propagation outbox, retention sweep |
| Architecture | import-linter, `manage.py check` | `.importlinter`, system checks | AD-2 contracts, AD-15 retention declarations |
| Frontend unit | Vitest + Testing Library | `frontend/**/*.test.tsx` | Components, token usage, client logic |
| E2E + a11y | Playwright + `@axe-core/playwright` | `frontend/e2e/` | Critical journeys and PRD §11.5 surfaces (zero serious/critical violations) |

## Coverage Requirements

**Target**: 80% overall; **100% of `backend/domain/`**
**Enforcement**: CI gate via `pytest --cov` with `fail_under`

**Critical paths that MUST have coverage:**
- Event Identity dedup and the three match rules. Embeddings never merge (AD-4).
- ±30-day postponement rule and `superseded_by` (AD-4)
- Conflict detection: >15 min overlap, UTC only (AD-21, AD-6)
- Quiet Hours due-time shifting at compute time (AD-7)
- Send idempotency key minting and no double-send under concurrent sweeps (AD-7)
- Propagation: versioned, idempotent, out-of-order safe, outbox reconciler (AD-17)
- Confidence gates 0.5 / 0.7 for extraction and tz inference (AD-6, AD-8)
- LLM gateway fallback and cost-row write (AD-8)
- Account deletion and export via the retention registry (AD-15, FR-52)
- Email stream separation + RFC 8058 unsubscribe endpoint (AD-20)

## Test Naming

**Pattern**: `test_<unit>_<condition>_<expected>`

**Examples**:
- `test_conflicts_overlap_exactly_15min_returns_false`: boundary of the FR-33 rule
- `test_sweep_two_workers_same_row_sends_once`: SKIP LOCKED claim
- `test_propagate_older_version_after_newer_is_noop`: out-of-order safety

## Test Structure

```python
# backend/tests/domain/test_conflict.py: no Django import anywhere
from datetime import datetime, timedelta, UTC
from domain.conflict import conflicts

def test_conflicts_overlap_exactly_15min_returns_false():
    # Arrange
    a_start = datetime(2026, 11, 1, 18, 0, tzinfo=UTC)
    a_end = a_start + timedelta(hours=1)
    b_start = a_end - timedelta(minutes=15)
    b_end = b_start + timedelta(hours=1)

    # Act
    result = conflicts(a_start, a_end, b_start, b_end)

    # Assert
    assert result is False
```

## Multi-Database Tests (AD-3)

- pytest-django allows only `default` (= personal) unless a test declares more. Any test touching `catalog` must use `@pytest.mark.django_db(databases=[PERSONAL, CATALOG])`, or it fails with "Database queries to 'catalog' are not allowed".
- Tests that need to observe a **commit** (e.g. per-schema transaction behavior) need `transaction=True`. Otherwise pytest-django wraps every alias in an outer atomic and nothing is ever committed.
- Pass `using=PERSONAL` / `using=CATALOG` explicitly, as in production code.
- Both aliases share one test DB built from `eventpulse24_test_template`; `tests/conftest.py` always sets up both aliases and refuses to migrate unless both point at the test DB. Never bypass it.
- Tests run as the owner role (`config.settings_test`). To test runtime-role privileges, open a raw `psycopg` connection with the runtime URL retargeted at the test DB, inside `with`, and roll back.

## Log Assertions (AD-13)

- `caplog.records` are raw `LogRecord`s, before redaction. Use them to assert *that* something was logged (logger, level, `exc_info`).
- To assert *what reaches the sink*, attach a `logging.StreamHandler` with `adapters.logging.formatter.JsonFormatter` to the root logger and parse the JSON lines (see `tests/api/test_trace_id.py`).
- Redaction tests also assert that a known title or email appears nowhere in the serialised line.

## Mock Strategy

**Approach**: fake at the **port** boundary. Never mock Django ORM or the database.

**Guidelines**:
- Use in-memory fakes implementing `ports/` interfaces for LLM, email, calendar, crawl, billing
- Tests never call Anthropic, Voyage, Stripe, or a real email provider
- Use a real Postgres (both `catalog` and `personal` databases) for app and worker tests
- Freeze time explicitly. Never depend on wall-clock or local timezone.
- No `time.sleep` in tests

## Test Data

**Strategy**: factories (factory_boy) per owning app; explicit UTC + IANA tz on every temporal fixture

**Guidelines**:
- Factories create rows via the owning app's commands where invariants matter
- Never use real user data or PII. Use synthetic emails on a reserved domain (`example.test`).
- Include DST-boundary and non-UTC timezone cases for any time logic
- LLM extraction fixtures are captured, sanitized JSON. Never live calls.

## Running Tests

```bash
# Run all tests
cd backend && pytest && cd ../frontend && pnpm test

# Run with coverage
cd backend && pytest --cov=. --cov-report=term-missing

# Run specific test file
cd backend && pytest tests/domain/test_conflict.py

# Run in watch mode
cd frontend && pnpm vitest --watch
```

## CI/CD Integration

**Pipeline**: GitHub Actions
**Trigger**: every push and pull request

**Required gates**:
- `ruff check` + `ruff format --check`; ESLint + Prettier check
- `lint-imports` (import-linter AD-2 contracts)
- `python manage.py check` (AD-15 retention registry)
- `python manage.py makemigrations --check` (no missing migrations)
- `pytest` with coverage `fail_under`
- OpenAPI schema export → regenerate TS client → frontend typecheck (AD-19)
- Vitest + Playwright E2E + axe-core zero serious/critical (PRD §11.5)

---
*Generated by specs.md - fabriqa.ai FIRE Flow*
