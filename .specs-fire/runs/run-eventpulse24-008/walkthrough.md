---
run: run-eventpulse24-008
work_item: health-round-trip
intent: project-scaffold
generated: 2026-10-27
mode: confirm
---

# Implementation Walkthrough: Health Round-Trip & make dev

## Summary

The stack now works end to end. A browser on the Next.js site calls `/api/health`; Next.js forwards the call to Django per request, so there's no CORS. Django checks that each AD-3 database alias lands in its own schema and that Redis answers, and returns either a typed 200 or the shared error shape as a 503. The `/dev/health` page renders the result through a client generated from the committed OpenAPI schema.

`make dev` runs the API, worker, beat and Next.js together with prefixed output, and Ctrl-C stops them cleanly. All of this is verified on the Mac (backend 438 tests, frontend 51, 15/15 mutations caught). The Ubuntu run is left for you on that machine.

## Structure Overview

```text
browser ──GET /api/health──► Next.js :3000  proxy.ts  (matcher /api/:path*, API_BASE_URL read per request)
   ▲                                   │  NextResponse.rewrite → http://127.0.0.1:8000/api/health
   │                                   ▼
/dev/health ◄── api.GET (openapi-fetch,   Django Ninja: config/health.py
 health-panel    typed by lib/api/         personal alias → SELECT current_schema() == "personal"
 .tsx            schema.ts)                catalog  alias → SELECT current_schema() == "catalog"
                                           redis           → PING (1 s timeouts)
                                           → 200 HealthOut | 503 HealthUnavailableOut (ErrorOut + typed details)

backend schema ──make openapi──► frontend/lib/api/openapi.json ──make client──► lib/api/schema.ts
                 (test_contract.py fails on drift)

make dev → scripts/dev.sh → concurrently: [api] $API_CMD · [worker] $WORKER_CMD · [beat] $BEAT_CMD · [web] $WEB_CMD
           (commands defined once in the Makefile; beat skipped if its pidfile names a live process)
```

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `backend/config/health.py` | Router, checks, `HealthOut` / `HealthUnavailableOut` |
| `backend/tests/api/test_health.py`, `test_contract.py` | Endpoint behaviour; contract drift |
| `frontend/proxy.ts`, `proxy.test.ts` | Request-time forwarding of `/api/*` |
| `frontend/lib/api-base-url.ts` | `API_BASE_URL` with a dev default, none in production |
| `frontend/lib/backend-client.ts` | `api`: the typed client, the only backend path |
| `frontend/lib/api/openapi.json`, `schema.ts` | Generated contract and types (committed) |
| `frontend/app/dev/health/{page,health-panel}.tsx` + tests | The developer health page |
| `frontend/tests/lint-rules.test.ts` | AD-19 lint rules proven through the ESLint API |
| `scripts/dev.sh` | `make dev` |

### Modified

| File | Changes |
|------|---------|
| `backend/config/api.py` | Mount `/health` |
| `backend/adapters/logging/redaction.py` | `component` allowlisted (fixed slug) |
| `frontend/eslint.config.mjs` | Ban `fetch`, `window.fetch`, `globalThis.fetch`, `self.fetch` in `app/` and `components/`; `openapi-fetch` only in `lib/backend-client.ts`; ignore `lib/api/` |
| `frontend/vitest.setup.ts` | Testing Library cleanup between tests |
| `frontend/package.json`, lockfile | `openapi-fetch` 0.17.0; dev: `openapi-typescript` 7.13.0, `concurrently` 10.0.6 |
| `Makefile` | `API_CMD`/`WORKER_CMD`/`BEAT_CMD`/`WEB_CMD`; `dev`, `openapi`, `client`; `API_BASE_URL` default |
| `.env.example` | `API_BASE_URL` |
| `README.md`, `docs/setup/{macos,ubuntu}.md`, `frontend/README.md`, `lib/api/README.md` | `make dev`, the health page, `make client`, backend access |
| Standards (coding, system-architecture, tech-stack, testing), `ci-pipeline.md` | Browser → API rule, CSRF hand-off, new dependencies, contract job |

## Key Implementation Details

### 1. Why `proxy.ts`, not `next.config` rewrites

`rewrites()` is evaluated at `next build` and saved in the build output. **`next typegen` (run by `pnpm typecheck`) also calls `rewrites()`, with `NODE_ENV=production`** (`route-types-utils.js:280`, `bin/next`).

`proxy.ts` instead runs per request on the Node runtime:
- changing `API_BASE_URL` needs no rebuild
- build and typecheck never need the variable (verified with it unset)
- production without it answers 503 `api_not_configured` instead of silently using localhost

This was probed in a scratch app before it was adopted.

### 2. The health check proves routing, not just liveness

Each alias must report `current_schema()` equal to `SCHEMA_FOR_ALIAS[alias]`, so a `search_path` mistake shows as `wrong_schema`.

- **Failures** are reason slugs. Exception text never reaches the response or the logs (the tests plant a password and an email in the error).
- **The 503 body is `HealthUnavailableOut`:** the shared `ErrorOut` with typed details. It's returned via `Status(503, …)` and validated by the schema; no domain error is involved.

### 3. One source per command

The four process commands are Makefile variables. `make api` and the others use them, and `make dev` passes them to `scripts/dev.sh`, which runs them under `concurrently` without nesting `make`. That keeps the Ctrl-C output clean: each process reports `exited with code 0`.

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Browser → API | Through Next.js, same origin, no CORS (you) | First-party cookies on any hosting; one extra short hop |
| Forwarding | `proxy.ts` per request | Build-time rewrites need a rebuild and break typecheck without the variable |
| 503 body | Returned directly, typed (review) | Infrastructure state isn't a domain error |
| Client | `openapi-typescript` + `openapi-fetch` | Light and typed from the committed schema; ESLint enforces the single path |
| `make dev` runner | `concurrently` 10.0.6 | Maintained, prefixed output, clean SIGINT |
| `/dev/health` | 404 in production | A developer page |

## Deviations from Plan

- **Process commands moved into Makefile variables.** The first live Ctrl-C showed nested-`make` error lines.
- **`page.test.tsx` added:** the production gate had no test.
- **`vitest.setup.ts` gained `afterEach(cleanup)`:** the first multi-render tests needed it.
- **This Mac's `.env` gained the `API_BASE_URL` line,** because `make doctor` requires every `.env.example` key.

## Dependencies Added

| Package | Why |
|---------|-----|
| `openapi-fetch` 0.17.0 | Typed fetch over the generated `paths` (runtime) |
| `openapi-typescript` 7.13.0 (dev) | Generates `schema.ts` |
| `concurrently` 10.0.6 (dev) | `make dev` |

## How to Verify

1. **Set up once:**
   ```bash
   make up
   make migrate
   make web-install
   ```
   An existing `.env` needs the `API_BASE_URL` line from `.env.example`; `make doctor` says so.
2. **Start everything:** `make dev`, then open <http://127.0.0.1:3000/dev/health>. Expected: personal database, catalog database and Redis all **OK**.
3. **Break Redis:** `docker compose stop redis`, then reload. Expected: Redis "Down: not reachable" and the summary "Some services aren't responding right now." Then `docker compose start redis`.
4. **Stop:** Ctrl-C in the `make dev` terminal. Expected: every process exits; `ls backend/.celery` shows no `beat.pid`.
5. **Contract guard:** change a summary in `backend/config/health.py`, then run `make test-backend`. Expected: `test_contract.py` fails and says to run `make client`. Revert it.
6. **Gates:** `make test-backend` (438), `make test-web` (51), `make lint-backend`, `make lint-web`.

## Test Coverage

- Tests added: 27 (backend 8, plus 1 automatic alias case; frontend 18)
- Coverage: not measured (comes with `ci-pipeline`)
- Status: all passing

## Developer Notes

- **Headers Django receives through the proxy:** `Host` = its own address; `Origin` and `X-Forwarded-Host`/`-Proto`/`-Port`/`-For` = the frontend's; cookies forwarded. **The first POST (login) needs `CSRF_TRUSTED_ORIGINS`, or a deliberate `USE_X_FORWARDED_HOST`.** It's in coding-standards for the auth intent.
- **A cross-origin `fetch` straight to `:8000` reaches Django;** the browser just won't let the page read it. CORS isn't write protection.
- **`beforeEach(() => mock.mockReset())` returns the mock,** and Vitest runs a returned function as teardown. Use braces.
- **Testing Library doesn't clean up between tests unless Vitest globals are on.** `vitest.setup.ts` registers `afterEach(cleanup)`.
- **Next adds `x-middleware-rewrite`** (the backend URL) to proxied responses.
- **`make dev` prints a hint** if the Postgres or Redis container isn't running. It doesn't start Docker itself (`make up`).

## Ready for Review

- [x] All acceptance criteria met on macOS
- [x] Tests passing (backend 438, frontend 51)
- [x] No critical issues (4 items recorded for the auth and deployment intents)
- [x] Documentation updated
- [ ] **Ubuntu verification:** for you on that machine (Node 24, `API_BASE_URL` in `.env`, `make web-install && make dev`, health page green)

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-008*
