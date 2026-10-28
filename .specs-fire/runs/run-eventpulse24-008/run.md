---
id: run-eventpulse24-008
scope: single
work_items:
  - id: health-round-trip
    intent: project-scaffold
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
current_item: null
status: completed
started: 2026-10-27T15:52:52.213Z
completed: 2026-10-27T16:19:54.732Z
---

# Run: run-eventpulse24-008

## Scope
single (1 work item)

## Work Items
1. **health-round-trip** (confirm) — completed


## Current Item
(all completed)

## Files Created
- `backend/config/health.py`: GET /api/health: per-alias schema check, Redis ping, typed 200/503
- `backend/tests/api/test_health.py`: Health endpoint: up, Redis down, DB down, wrong schema, no exception text
- `backend/tests/api/test_contract.py`: Committed openapi.json matches the live API
- `frontend/lib/api/openapi.json`: Exported OpenAPI schema (generated)
- `frontend/lib/api/schema.ts`: openapi-typescript types (generated)
- `frontend/lib/api-base-url.ts`: API_BASE_URL read at call time; dev default, none in production
- `frontend/lib/backend-client.ts`: Typed openapi-fetch client, the only backend access path
- `frontend/proxy.ts`: Request-time /api/* forwarding to API_BASE_URL
- `frontend/proxy.test.ts`: Proxy forwarding, dev default, production 503
- `frontend/app/dev/health/page.tsx`: Dev-only health page (404 in production)
- `frontend/app/dev/health/health-panel.tsx`: Health panel: per-component status with text labels
- `frontend/app/dev/health/health-panel.test.tsx`: Panel states: checking, ok, 503 down, unreachable
- `frontend/app/dev/health/page.test.tsx`: Production gate
- `frontend/tests/lint-rules.test.ts`: AD-19 lint rules via the ESLint API
- `scripts/dev.sh`: make dev: concurrently runner, one-beat guard

## Files Modified
- `backend/config/api.py`: Mount health router
- `backend/adapters/logging/redaction.py`: component allowlisted
- `frontend/eslint.config.mjs`: fetch / window.fetch / globalThis.fetch / self.fetch bans; openapi-fetch import restriction; ignore lib/api
- `frontend/vitest.setup.ts`: Testing Library cleanup
- `frontend/package.json`: openapi-fetch, openapi-typescript, concurrently
- `frontend/pnpm-lock.yaml`: Lockfile
- `frontend/.prettierignore`: Generated openapi.json
- `frontend/README.md`: Backend access, proxy, make client
- `frontend/lib/api/README.md`: Generated contract files
- `Makefile`: API_CMD/WORKER_CMD/BEAT_CMD/WEB_CMD, dev, openapi, client, API_BASE_URL default
- `.env.example`: API_BASE_URL
- `README.md`: make dev quick start, health page, make client
- `docs/setup/macos.md`: make dev section
- `docs/setup/ubuntu.md`: make dev section
- `.specs-fire/standards/coding-standards.md`: Browser to API via proxy, client rule, CSRF hand-off
- `.specs-fire/standards/system-architecture.md`: Browser to API path
- `.specs-fire/standards/tech-stack.md`: openapi-typescript, openapi-fetch, concurrently
- `.specs-fire/standards/testing-standards.md`: Local contract test
- `.specs-fire/intents/project-scaffold/work-items/ci-pipeline.md`: Contract job and test hand-off

## Decisions
- **Browser to API**: Through Next.js, same origin, no CORS (User choice; first-party cookies on any hosting)
- **Forwarding mechanism**: proxy.ts (request time) instead of next.config rewrites (rewrites are baked at build and next typegen calls them with NODE_ENV=production; proxy reads API_BASE_URL per request)
- **503 body**: View returns HealthUnavailableOut via Status; no ServiceUnavailableError (Plan review; infrastructure state is not a domain error)
- **Client**: openapi-typescript types + openapi-fetch, used only in lib/backend-client.ts (Light, typed from the committed schema; ESLint enforces the path)
- **make dev runner**: concurrently, commands defined once in the Makefile (Maintained, prefixed output, clean SIGINT; no nested-make noise)
- **Dev page**: /dev/health is a 404 in production (Developer page)


## Summary

- Work items completed: 1
- Files created: 15
- Files modified: 19
- Tests added: 27
- Coverage: 0%
- Completed: 2026-10-27T16:19:54.732Z
