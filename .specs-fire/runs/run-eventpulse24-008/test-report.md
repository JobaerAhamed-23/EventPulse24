---
run: run-eventpulse24-008
work_item: health-round-trip
intent: project-scaffold
generated: 2026-10-27
status: passed on macOS; Ubuntu verification pending (user)
machine: macOS 26.4.1 (Apple Silicon), Node 24.22.1, Docker Desktop 29.9.2
---

# Test Report: Health Round-Trip & make dev

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Health endpoint (`backend/tests/api/test_health.py`) | 7 | 0 | 0 | n/a |
| Contract drift (`backend/tests/api/test_contract.py`) | 1 | 0 | 0 | n/a |
| Database-alias scan: the new `config/health.py` (existing test) | +1 | 0 | 0 | n/a |
| Backend existing suite | 429 | 0 | 0 | n/a |
| **Backend total** | **438** | 0 | 0 | n/a |
| Health panel (`app/dev/health/health-panel.test.tsx`) | 5 | 0 | 0 | n/a |
| Dev page production gate (`app/dev/health/page.test.tsx`) | 2 | 0 | 0 | n/a |
| Proxy (`proxy.test.ts`) | 4 | 0 | 0 | n/a |
| Lint rules via the ESLint API (`tests/lint-rules.test.ts`) | 7 | 0 | 0 | n/a |
| Frontend existing suite | 33 | 0 | 0 | n/a |
| **Frontend total** | **51** | 0 | 0 | n/a |
| `make lint-backend` (12 contracts), `manage.py check` | clean | | | |
| `make lint-web` (ESLint, typecheck, Prettier) | clean | | | |
| `pnpm build` **without `API_BASE_URL`** | ✓ (`/dev/health` static, Proxy registered) | | | |
| `pnpm typecheck` **without `API_BASE_URL`** | ✓ | | | |
| Mutation checks | 15/15 caught | | | |

## Acceptance Criteria Validation

- ✅ **`GET /api/health` (Ninja, Pydantic response schema) returns per-component status for the catalog DB, personal DB and Redis, using the shared error shape on failure.**
  - 200 `HealthOut`, or 503 `HealthUnavailableOut`: an `ErrorOut` subclass with typed `details.components`. Each alias must land in `SCHEMA_FOR_ALIAS[alias]`.
  - Verified live under the runtime (DML-only) roles. Redis stopped gave a 503; Redis started again gave a 200.
- ✅ **`make openapi` exports the schema to a committed file; `make client` generates the TS client into `frontend/lib/api/`.** That's `openapi.json` + `schema.ts` (`openapi-typescript` 7.13.0). Drift is caught by `test_contract.py`, shown by a planted summary change.
- ✅ **A Next.js page (`/dev/health`) fetches via the generated client and shows each component's status.** `api.GET("/api/health")` through `openapi-fetch`, typed from `schema.ts`. Each component shows a text label and reason, so colour isn't the only signal. Screenshot taken: all three OK. The page is a 404 in production.
- ✅ **CORS / API base URL configured from env for local dev.**
  - `API_BASE_URL` is read **per request** by `proxy.ts`. It's in `.env.example` and defaulted by the Makefile.
  - **No CORS, by the user's decision** (the browser reaches the API through Next.js). A direct cross-origin `fetch` from the page to `:8000` **reached Django**, which logged it, but **the browser refused to let the page read it** (`TypeError: Failed to fetch`).
- ✅ **`make dev` starts API, worker, beat and Next.js together with readable, prefixed output and clean Ctrl-C shutdown** (verified on macOS):
  - `[api]` `[worker]` `[beat]` `[web]` prefixes, and ticks 60 s apart in the worker
  - SIGINT to the process group, as a terminal sends it: every process `exited with code 0`, **no leftover processes**, and **the beat pidfile was removed**
  - With a beat already running: "Celery beat is already running (pid …); not starting another", and only three processes started
- ✅ **Tests: the health endpoint returns ok with services up and a structured error when a component is down.** Covers Redis down, each database down, wrong schema, the typed 503 body, and logs and response free of exception text.
- ⏳ **Verified on both Ubuntu and macOS from a clean clone.** macOS ✅ in this session. **Ubuntu: pending, for the user on that machine.** Needs Node 24 (`nvm install 24`), the new `API_BASE_URL` line in `.env` (`make doctor` reports it), then `make web-install && make dev` → `/dev/health` all green.

## Manual Verification (macOS)

1. `make dev`:
   - `curl :3000/api/health` returns 200 through the proxy, with `X-Request-ID` echoed
   - `/dev/health` returns 200; screenshot shows all OK
2. `docker compose stop redis` → `:3000/api/health` returns 503 `service_unavailable`, with redis down/`unreachable`. `start redis` → 200.
3. Ctrl-C (SIGINT to the group): all four processes exit with code 0, nothing left running (`pgrep` empty), and `beat.pid` is gone. **The first try printed `make[1]: *** [beat] Error 130`, because each process ran inside a nested `make`.** Fixed: the commands are defined once in the Makefile (`API_CMD`, …) and run directly.
4. `make beat`, then `make dev`: the "already running" message, three processes, and the standalone beat untouched.
5. **Production** (`next start`, no `API_BASE_URL`): `/dev/health` returns 404, and `/api/health` returns 503 `{"code":"api_not_configured",…}`, logged once.
6. **Headers Django receives through the proxy** (recorded with a header-echo upstream), for the CSRF hand-off:
   - `host` = the upstream's own address
   - `origin` = the frontend's address
   - `x-forwarded-host` / `-port` / `-proto` / `-for` = the frontend's values
   - the browser's `cookie` is forwarded

## Issues Found During Execution

| Issue | Resolution |
|---|---|
| **Review fix "put the `API_BASE_URL` check in `rewrites()`" wouldn't have worked:** `next typegen` calls `rewrites()` (`route-types-utils.js:280`) with `NODE_ENV=production` | Switched to request-time `proxy.ts`. Probed in a scratch app, then verified: build and typecheck pass without the variable |
| Ninja 1.7 deprecates tuple `(status, body)` returns | `Status(…)`; health tests pass with `-W error::DeprecationWarning` |
| `make dev` shutdown noise from nested `make` | Process commands moved into Makefile variables; `dev.sh` runs them directly |
| Testing Library leaked DOM between tests (Vitest globals off) | `afterEach(cleanup)` in `vitest.setup.ts` |
| `beforeEach(() => GET.mockReset())` returned the mock, which Vitest ran as a teardown, so it hung or threw | Braces; nothing returned |
| No test covered the production gate on `/dev/health` | Added `page.test.tsx` |
| `make doctor` fails on an existing `.env` without `API_BASE_URL` | That's the existing rule (every `.env.example` key is required). Appended the line to this Mac's `.env`; Ubuntu needs the same (setup guide §5) |

## Mutation Checks (each reverted after)

All 15 caught:
- **Backend:**
  - wrong-schema check removed
  - a down component still answering 200
  - exception text in the log field
  - `component` not allowlisted
  - Redis ping skipped
  - an API change without `make client`
- **Frontend:**
  - proxy reading `API_BASE_URL` at import
  - production defaulting to localhost
  - query string dropped
  - `window.fetch` allowed
  - `fetch` global allowed
  - `openapi-fetch` allowed anywhere
  - down shown by colour only
  - 503 details ignored
  - dev page available in production

## Ready for Review

- [x] All tests passing (backend 438, frontend 51)
- [x] Acceptance criteria validated on macOS
- [ ] Ubuntu verification (user, on that machine)
