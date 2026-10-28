---
id: run-eventpulse24-002
scope: single
work_items:
  - id: backend-skeleton
    intent: project-scaffold
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
current_item: null
status: completed
started: 2026-10-27T09:10:04.371Z
completed: 2026-10-27T09:25:25.272Z
---

# Run: run-eventpulse24-002

## Scope
single (1 work item)

## Work Items
1. **backend-skeleton** (confirm) — completed


## Current Item
(all completed)

## Files Created
- `backend/pyproject.toml`: uv project: Python 3.13, pinned deps, ruff + pytest config
- `backend/uv.lock`: Locked dependency set
- `backend/manage.py`: Django entry point
- `backend/config/env.py`: Typed env config (pydantic-settings); only module reading the environment
- `backend/config/settings.py`: Django settings from config.env; UTC; placeholder DB
- `backend/config/api.py`: NinjaAPI, OpenAPI at /api/openapi.json
- `backend/config/urls.py`: Mounts api/ only (admin deferred)
- `backend/config/asgi.py`: ASGI entry
- `backend/config/wsgi.py`: WSGI entry
- `backend/apps/{ingestion,catalog,personalization,delivery,identity,editorial}/*`: Six MVP Django apps (8 files each, empty models)
- `backend/{domain,ports,shared,worker,adapters/*}/__init__.py`: Layer packages per the spine
- `backend/tests/domain/test_domain_is_django_free.py`: AD-2 guard in a fresh interpreter
- `backend/tests/config/test_env.py`: Typed config tests
- `backend/tests/config/test_project.py`: App registry, UTC, system check, no admin route
- `backend/tests/api/test_openapi.py`: Ninja mounted, schema + docs served

## Files Modified
- `.env.example`: Django keys; $ and # warning
- `scripts/doctor.sh`: Config check: .env must contain every .env.example key
- `Makefile`: api, manage, test-backend, lint-backend, fmt-backend via uv run --directory backend; help column 14
- `README.md`: backend/ in layout; make api in quick start
- `docs/setup/ubuntu.md`: Updating an existing .env section; backend commands
- `docs/setup/macos.md`: Same as ubuntu.md
- `.specs-fire/standards/tech-stack.md`: Django 6.1.2, ninja 1.7.1, psycopg, dj-database-url; no .python-version
- `.specs-fire/intents/project-scaffold/work-items/backend-skeleton.md`: Pinned versions in acceptance criteria

## Decisions
- **Django / django-ninja versions**: 6.1.2 / 1.7.1 (spine: 6.1.1 / 1.7.0) (Latest patch releases; minor lines unchanged; pydantic kept at spine 2.13.5)
- **Python version selection**: requires-python ==3.13.* only, no .python-version file (pyenv also reads .python-version; with uv installed under pyenv 3.12.3 it broke the uv shim inside backend/)
- **Admin**: contrib apps installed, /admin/ not routed (Admin tables need a schema decided by schema-router-spike)
- **Domain purity check**: Fresh-subprocess import guard + negative test (Cannot be masked by Django already loaded in the pytest process)
- **Stale .env detection**: doctor Config check against .env.example keys (Catches missing keys on both machines after every future change)


## Summary

- Work items completed: 1
- Files created: 15
- Files modified: 8
- Tests added: 21
- Coverage: 0%
- Completed: 2026-10-27T09:25:25.272Z
