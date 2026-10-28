---
id: backend-skeleton
title: Backend Skeleton (Django + Ninja, layered tree)
intent: project-scaffold
complexity: medium
mode: confirm
status: completed
depends_on:
  - local-infra-and-setup-docs
created: 2026-10-27
run_id: run-eventpulse24-002
completed_at: 2026-10-27T09:25:25.272Z
---

# Work Item: Backend Skeleton (Django + Ninja, layered tree)

## Description

Create the Python backend project under `backend/` with the Architecture Spine's layered source tree, typed configuration, and the test/lint toolchain. No models, no feature endpoints.

## Acceptance Criteria

- [ ] `backend/pyproject.toml` managed by **uv**, `requires-python = "==3.13.*"`, pins Django 6.1.2, django-ninja 1.7.1 (patch bumps over the spine, recorded in tech-stack.md), pydantic 2.13.5, pydantic-settings, psycopg, dj-database-url; `uv.lock` committed
- [ ] Tree exists per spine: `config/`, `domain/`, `apps/{ingestion,catalog,personalization,delivery,identity,editorial}/`, `ports/`, `adapters/{llm,email,calendar,crawl,billing,logging}/`, `worker/`, `shared/`
- [ ] Each app is a registered Django app with empty `models.py`, `services/`, `api.py`, `schemas.py`, `admin.py`
- [ ] `config/settings.py` loads a pydantic-settings object once from `.env`; no `os.environ` reads below `config/`
- [ ] Ninja `NinjaAPI` mounted at `/api/` with OpenAPI docs at `/api/docs`
- [ ] Ruff configured (format + lint, rules `E,F,I,B,UP,S,DTZ`, line length 100) in `pyproject.toml`
- [ ] pytest + pytest-django configured; `tests/domain/` runs with no Django settings loaded
- [ ] `make api` runs the dev server on :8000; `make test-backend` and `make lint-backend` work
- [ ] Verified: `/api/docs` loads; `pytest` and `ruff check` / `ruff format --check` are green

## Technical Notes

- Python 3.13 is the only version satisfying Django 6.1 (≥3.12) and Celery 5.6.3 (≤3.13); uv can install it on both OSes.
- Database config here is a single placeholder default; the two-database split is schema-router-spike's job.

## Dependencies

- local-infra-and-setup-docs
