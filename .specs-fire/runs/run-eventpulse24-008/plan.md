---
run: run-eventpulse24-008
work_item: health-round-trip
intent: project-scaffold
mode: confirm
checkpoint: plan
revision: 2 (plan review: 3 points + 2 smaller; typegen finding)
approved_at: 2026-10-27
---

# Implementation Plan: Health Round-Trip & make dev

## Approach

Connect the stack end to end for the first time:

```text
browser ── GET /api/health ──► Next.js (:3000) proxy.ts ── /api/:path* ──► Django Ninja (:8000) /api/health
   ▲  (same origin: no CORS)   API_BASE_URL read per request              ├─ personal alias: SELECT current_schema()
   │                                                                     ├─ catalog alias:  SELECT current_schema()
/dev/health page ◄── typed client (openapi-fetch + generated types) ◄─────┘─ Redis: PING (CELERY_BROKER_URL)
```

**User decision (this session): the browser reaches the API through Next.js.**
- The browser only ever calls `/api/…` on the frontend's own address, and Next.js forwards that to `API_BASE_URL`.
- There's **no CORS**, and login cookies will be first-party on any hosting.
- The work item's "CORS / API base URL from env" criterion is met by `API_BASE_URL`. **CORS isn't configured, and that's deliberate.** Without CORS headers the browser won't let a page on another origin *read* Django's answers. A cross-origin request still *reaches* Django, though: CORS doesn't protect writes, CSRF does *(review 2)*.

**How the forwarding works: `proxy.ts`, read per request, not `next.config` rewrites** *(review 1, plus a finding in the installed Next source)*.
- **`next.config` `rewrites()` is baked in at `next build`** (saved in the routes manifest; `next start` doesn't re-read it). Changing the backend address would need a rebuild.
- **The review proposed moving the "missing address" check inside `rewrites()`, on the grounds that `next typegen` doesn't call it. It does:**
  - `node_modules/next/dist/server/lib/router-utils/route-types-utils.js:280` has `if (typeof rewrites === 'function') { const rw = await rewrites(); … }`
  - `next typegen` loads the config as `PHASE_PRODUCTION_BUILD`, and `bin/next` gives every command except `dev` `NODE_ENV=production`
  - So that check would still fail `pnpm typecheck` anywhere without `API_BASE_URL`, CI included.
- **Instead, Next 16's `proxy.ts`** (the request-time step formerly called middleware; Node runtime by default) does `NextResponse.rewrite(new URL(pathname + search, API_BASE_URL))` for the matcher `/api/:path*`. **Probed in a scratch Next 16.3.8 app:**
  - **One build, started twice:** with `API_BASE_URL` set, the request reached the upstream server (200 from it); without it, the proxy answered 503.
  - The address is read **per request**, so changing it needs **no rebuild**, and `next build` / `next typegen` never need the variable.
- **A missing address:**
  - In development the proxy defaults to `http://127.0.0.1:8000`, and the Makefile exports `API_BASE_URL` anyway.
  - In production it answers **503 in the shared error shape** (`code: "api_not_configured"`, a calm message) and logs the misconfiguration once, rather than silently using localhost.
- **Seen in the probe:** Next adds an `x-middleware-rewrite` response header carrying the backend URL. In production that's the API's public address, so it's not secret, but it's recorded as a known disclosure.

### 1. Backend: `GET /api/health`

**`config/health.py`**, a Ninja `Router` mounted in `config/api.py` at `/health`. It lives in `config` because it checks infrastructure, not a feature app's data.

**Checks** (each returns `ok`, or `down` with a reason slug; exception text is never returned or logged, per AD-13):
- **`personal` and `catalog`:** loop over `PERSONAL` / `CATALOG` from `shared.db`; `SELECT current_schema()` on `connections[alias]` must equal `SCHEMA_FOR_ALIAS[alias]` from `config/databases.py`. No string literals, so the database-alias test stays happy *(review)*. That proves the AD-3 routing per alias, not just that something answered.
  - `DatabaseError` → `down` / `unreachable`
  - a different schema → `down` / `wrong_schema`
- **`redis`:** `PING` on `settings.CELERY_BROKER_URL`, with 1 s connect and read timeouts, so a dead Redis can't hang the request. `RedisError` → `down` / `unreachable`.

**Responses** (declared, so they're in the OpenAPI contract):
- **200 `HealthOut`:** `{status: "ok", components: {personal, catalog, redis: {status, reason?}}}`
- **503 `HealthUnavailableOut`:** a subclass of the shared `ErrorOut`, so the same `{code, message, details}` shape, but with **typed** details `{components: {…}}`. The generated client therefore knows the per-component fields.
  - **The view returns it directly:** `return 503, HealthUnavailableOut(code="service_unavailable", message="Some services aren't responding right now.", details=…)` *(review: option 1)*.
  - A service being down is infrastructure, not a business rule, so `domain/errors.py` and `config/errors.py` are **not** changed.
  - Ninja serializes the body through the declared schema, so the wire shape is checked by the schema itself. A test also validates the real 503 body against `HealthUnavailableOut`.

**Logging:** each `down` component logs one WARNING, `"Health component down"`, with `component` and `error_type`.
- `component` is a **new entry in `ALLOWED_FIELDS`**. It's a fixed slug (`personal` / `catalog` / `redis`), so it fits the allowlist rule (ids, counts and slugs only). This is a reviewed change to the redaction allowlist.

### 2. Contract: `make openapi` and `make client` (AD-19)

- **`make openapi`:** Ninja's `export_openapi_schema` writes **`frontend/lib/api/openapi.json`** (committed).
- **`make client`:** runs `make openapi`, then **`openapi-typescript`** generates **`frontend/lib/api/schema.ts`** (committed). Both are generated; nothing in `lib/api/` except its README is edited by hand.
- **New frontend dependencies:**
  - `openapi-typescript` 7.13.0 (dev)
  - `openapi-fetch` 0.17.0: a tiny typed `fetch` wrapper driven by the generated `paths` type, with no code generation of its own
- **`frontend/lib/backend-client.ts`**, about 10 hand-written lines and the **only** place `openapi-fetch` is used: `createClient<paths>({ baseUrl })`.
  - In the browser `baseUrl` is `""`, i.e. same origin through the rewrite.
  - On the Next.js server it's `API_BASE_URL`. Nothing uses that yet; it's there for server components later.
- **Drift guard now, before CI exists:** a backend test checks that the committed `openapi.json` equals the schema the API produces, and tells you to run `make client` if not. The full "regenerate and `git diff`" check is `ci-pipeline`'s job.

### 3. Frontend: `/dev/health`

- **`app/dev/health/page.tsx`:** a server component. It returns **`notFound()` in production builds** (it's a developer page) and otherwise renders `HealthPanel`.
- **`app/dev/health/health-panel.tsx`:** a client component. On mount it calls `api.GET("/api/health")` and shows each component with a status dot and a text label, so color is never the only signal (WCAG 1.4.1).
  - `ok` uses `color.signal.success`; `down` uses `color.signal.warn` plus the reason.
  - `signal.error` is reserved for destructive actions, so it isn't used.
  - Both the 200 and the typed 503 bodies render. "Checking…" shows while the request is in flight, and a calm message shows if the API itself is unreachable.
- **Design tokens only;** status dots use `radius.full`, which DESIGN.md sanctions for "status dots".
- **`frontend/proxy.ts`:** the `/api/:path*` forwarding described above. `next.config.ts` stays empty.

**AD-19 enforcement in ESLint, as planned in frontend-skeleton:**
- `no-restricted-globals` forbids `fetch` in `app/` and `components/`, and **`no-restricted-properties` forbids `window.fetch` and `globalThis.fetch`** (and `self.fetch`) *(review 3)*.
- `no-restricted-imports` allows `openapi-fetch` only in `lib/backend-client.ts`.
- A test lints planted snippets through ESLint's Node API to prove both rules fire.

### 4. `make dev`

- **`scripts/dev.sh`** (POSIX `sh`, so it runs on Linux and macOS), started by `make dev`. It runs **`concurrently`** 10.0.6 (frontend dev dependency) with four named, colour-prefixed processes: `api` (`make api`), `worker` (`make worker`), `beat` (`make beat`) and `web` (`make web`).
- **Exactly one beat** (hand-off): if `backend/.celery/beat.pid` names a live process, `make dev` prints "beat is already running (pid N); not starting another" and runs the other three.
  - A stale pidfile (dead pid) is removed and beat starts normally.
- **Ctrl-C:** `concurrently` passes the interrupt to every process and waits for them, so beat removes its pidfile on the way out. The run is verified by checking that the pidfile is gone and no process is left.
- **No Docker inside `make dev`:** the infrastructure stays `make up`, as in the intent's success criteria. If Postgres or Redis aren't reachable, `make dev` prints a one-line hint ("run `make up`"), and the health page shows what's down.
- **`.env.example`** gains `API_BASE_URL=http://127.0.0.1:8000`. The Makefile defaults it when it's missing, so an existing `.env` keeps working.

### 5. Hand-off: CSRF on the first POST *(review 2)*

Through the proxy, the browser sends `Origin: http://127.0.0.1:3000` (in production, the frontend's domain), while Django sees its own host. On the first unsafe request (login, forms), Django's CSRF origin check can reject it unless:
- the frontend origin is in `CSRF_TRUSTED_ORIGINS` (from env), or
- the original host is passed through (`X-Forwarded-Host` + `USE_X_FORWARDED_HOST`) deliberately.

It isn't needed for this GET-only item, and no auth work item exists yet. So the note goes where the planner of that intent will read it:
- **`coding-standards.md`** ("Browser → API" rule, with this caveat)
- **`system-architecture.md`**
- this run's walkthrough

The live check also records which `Host` / `X-Forwarded-*` headers Django actually receives through the proxy, so the note is concrete.

## Files to Create

| File | Purpose |
|------|---------|
| `backend/config/health.py` | Health router, checks, `HealthOut` / `HealthUnavailableOut` schemas |
| `backend/tests/api/test_health.py` | Health endpoint tests |
| `backend/tests/api/test_contract.py` | Committed `openapi.json` matches the live schema |
| `frontend/lib/api/openapi.json`, `frontend/lib/api/schema.ts` | Generated contract and types (committed) |
| `frontend/lib/backend-client.ts` | The typed client instance |
| `frontend/app/dev/health/page.tsx`, `health-panel.tsx` | The health page |
| `frontend/proxy.ts` | `/api/:path*` → `API_BASE_URL`, read per request |
| `frontend/proxy.test.ts` | Forwarding target incl. query string; dev default; production without `API_BASE_URL` → 503 error shape |
| `frontend/app/dev/health/health-panel.test.tsx` | Renders 200, 503 and unreachable states |
| `frontend/tests/lint-rules.test.ts` | Planted `fetch` / `openapi-fetch` imports are rejected; allowed forms pass |
| `scripts/dev.sh` | `make dev` runner |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/config/api.py` | Mount the health router |
| `backend/adapters/logging/redaction.py` | `component` allowlisted (a slug) |
| `frontend/package.json`, `pnpm-lock.yaml` | `openapi-fetch`, `openapi-typescript`, `concurrently` |
| `frontend/eslint.config.mjs` | `fetch` / `openapi-fetch` restrictions; ignore `lib/api/` |
| `frontend/.prettierignore` | `lib/api/openapi.json` |
| `frontend/lib/api/README.md`, `frontend/README.md` | How to regenerate; the client |
| `Makefile` | `openapi`, `client`, `dev`; `API_BASE_URL` default |
| `.env.example` | `API_BASE_URL` |
| `README.md`, `docs/setup/{macos,ubuntu}.md` | `make dev`, the health page, `make client` |
| `.specs-fire/standards/{coding-standards,tech-stack,testing-standards,system-architecture}.md` | Browser → API via `proxy.ts` (no rebuild for address changes); CSRF hand-off; client usage rule; new dependencies |
| `.specs-fire/intents/project-scaffold/work-items/ci-pipeline.md` | Hand-off: contract job commands; health tests need Redis |

## Tests

| Test File | Coverage |
|-----------|----------|
| `tests/api/test_health.py` | All up → 200 with each component `ok` and the right schema per alias. **The real 503 body validates against `HealthUnavailableOut`** (`model_validate`), and against `ErrorOut`. **Redis down** (broker URL pointed at a closed port) → 503 `service_unavailable` with typed details: `redis` down/`unreachable`, databases ok. **A database down** (the cursor raises `OperationalError`) → 503 naming that alias. **Wrong schema** → `wrong_schema`. A down component logs `component` + `error_type` and never the exception text. The trace id header is present. |
| `tests/api/test_contract.py` | The committed `frontend/lib/api/openapi.json` equals `api.get_openapi_schema()`; on mismatch the message says to run `make client` |
| `frontend/app/dev/health/health-panel.test.tsx` | With `api.GET` mocked: the all-ok state; a 503 with one component down (text label and reason, not just colour); API unreachable → calm message; "Checking…" while pending |
| `frontend/tests/lint-rules.test.ts` | Planted in `app/`, each fails lint: `fetch(…)`, `window.fetch(…)`, `globalThis.fetch(…)`, `self.fetch(…)`, `import createClient from "openapi-fetch"`. `openapi-fetch` is allowed in `lib/backend-client.ts`. |
| Existing suites | Backend 429 and frontend 33 stay green; the new frontend files pass the kebab-case and motion scans |

**Live checks on this Mac:**
1. `make up && make migrate && make dev`. `http://127.0.0.1:3000/dev/health` shows all three green. `curl 127.0.0.1:3000/api/health` comes through the proxy, with an `X-Request-ID` echoed.
2. `docker compose stop redis` → the page shows Redis down, and the API returns 503. `docker compose start redis` → green again.
3. Ctrl-C stops all four processes. No `celery` / `next` / `runserver` is left, and `beat.pid` is gone.
4. With beat already running, `make dev` reports it and starts only three processes.
5. A cross-origin `fetch` from a page on `:3000` straight to `:8000` **reaches Django, but the browser won't let the page read the response** (no `Access-Control-Allow-Origin`). That's the expected CORS behaviour; writes are CSRF's job (§5).
6. A record of the `Host` / `Origin` / `X-Forwarded-*` headers Django receives through the proxy, for the CSRF hand-off.

**Ubuntu:** the work item requires verification on **both** OSes, and it can't be done from this Mac. Like run 001's macOS check, the run records it as **pending for you** on the Ubuntu machine: install Node 24, then follow `docs/setup/ubuntu.md` from a clean clone to a green health page.

## Not in this item

- Production hosting of the proxy (Vercel rewrites to Railway) belongs to the deployment intent. The rewrite works the same there, given `API_BASE_URL`.
- CI's contract job (regenerate and `git diff`) belongs to `ci-pipeline`.
- A health endpoint for orchestrators (liveness without dependencies) can come with deployment.

---
*`approved_at` is set when you approve at the checkpoint; until then this plan is a draft.*
