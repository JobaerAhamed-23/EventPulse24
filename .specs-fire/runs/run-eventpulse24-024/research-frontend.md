# Research: Frontend & Revalidation Signal

**Run:** run-eventpulse24-024 · **Date:** 2026-11-02 · **Scope:** Next.js frontend, Next.js ISR/revalidation state, proxy matcher, frontend↔backend client, frontend config, STANDARDS, ARCHITECTURE-SPINE.md, intent brief, prior art.

**Status:** RESEARCH ONLY. No project file was edited. This file is the only artefact created.

---

## 1. Next.js version & structure

### 1.1 Version and framework

| Fact | Value | Source |
| --- | --- | --- |
| Next.js | **16.3.8** | `frontend/package.json:20` — `"next": "16.3.8"` |
| React | 19.2.9 | `frontend/package.json:22-23` |
| Router | **App Router** | `frontend/app/` directory exists; `next.config.ts` uses `NextConfig` type |
| Package manager | `pnpm@12.15.0` | `frontend/package.json:5` |
| Node engine | `>=24.15` | `frontend/package.json:6-8` |
| TypeScript | 5.9.3 | `frontend/package.json:45` |
| Tailwind | 4.3.3 | `frontend/package.json:43` |

Spine pins a slightly older line — `_bmad-output/planning-artifacts/architecture/architecture-EventPulse24-2026-09-04/ARCHITECTURE-SPINE.md:343-347`:

```
| Next.js | 16.3.4 (Active LTS) |
| React | 19.2.8 |
| Tailwind CSS | 4.x (PRD §16) |
| TypeScript | 5.x |
| Node.js | ≥20.9 |
```

`tech-stack.md:19-20` records the patch bump as deliberate: *"Next.js 16.3.8 (Active LTS). Django and Ninja are patch bumps over the spine's 6.1.1 / 1.7.0, taken at scaffold time (run-eventpulse24-002)"* and *"Next 16 `cacheComponents` and `partialPrefetching` make ISR'd public event pages viable at scale (AD-12)."*

### 1.2 Routes under `frontend/app/` — complete list

All page routes (non-test files):

| Route | File |
| --- | --- |
| `/` | `frontend/app/page.tsx` |
| `/conflicts` | `frontend/app/conflicts/page.tsx` |
| `/dev/health` | `frontend/app/dev/health/page.tsx` (+ `health-panel.tsx`) |
| `/events/[id]` | `frontend/app/events/[id]/page.tsx` (+ `loading.tsx`) |
| `/events/[id]/reminders` | `frontend/app/events/[id]/reminders/page.tsx` (+ `loading.tsx`) |
| `/onboarding` | `frontend/app/onboarding/page.tsx` |
| `/preview` | `frontend/app/preview/page.tsx` |
| `/reset-password` | `frontend/app/reset-password/page.tsx` |
| `/settings/quiet-hours` | `frontend/app/settings/quiet-hours/page.tsx` (+ `loading.tsx`) |
| `/settings/reminders` | `frontend/app/settings/reminders/page.tsx` (+ `loading.tsx`) |
| `/signin` | `frontend/app/signin/page.tsx` |
| `/signup` | `frontend/app/signup/page.tsx` |
| `/timeline` | `frontend/app/timeline/page.tsx` (+ `loading.tsx`) |
| `layout.tsx`, `favicon.ico` | `frontend/app/layout.tsx` |

**Not present:** `app/sitemap.ts`, `app/robots.ts`, `app/events-in-[city]/`, any `route.ts` file, any `opengraph-image.*`, any `api/` directory. The brief confirms: *"`frontend/app/` has `conflicts`, `dev`, `events`, `onboarding`, `preview`, `reset-password`, `settings`, `signin`, `signup`, `timeline` — and no `sitemap.ts`, no `robots.ts`, and no route that renders without a session."* (`brief.md:27`).

### 1.3 Is there a public page yet?

**One — `/preview`, and it is deliberately cacheable.**

`frontend/app/preview/page.tsx:12-25` (the file's own docblock):

```
 * `/preview` — the Pulse Preview, the anonymous gateway (FR-2, AD-12).
 *
 * **This page is static, and that is a requirement rather than an optimisation.** AD-12:
 * "Public event pages render fully without a session", and this item's criterion adds
 * that the page "renders identically for an anonymous and a signed-in visitor". So there
 * is no `dynamic` export, no `cookies()`, no `getSession()` — nothing here can vary by
 * who is asking, which is what makes the page cacheable at the edge.
```

`/preview` has **no** `dynamic` export, **no** `revalidate` export, and reads no session. It is a static shell; the per-visitor data is fetched client-side in `components/preview/preview-section.tsx` (a client island).

**No `/events/{slug}` public event page and no `/events-in-{city}` city page exist yet.** `/events/[id]` is the *signed-in Detail Screen*, not a public page.

**The signed-in home is explicitly NOT cacheable** — `frontend/app/page.tsx:46`:

```tsx
export const dynamic = "force-dynamic";
```

with the rationale at `frontend/app/page.tsx:43-45`: *"The page is rendered **per request**, as it was before: it shows the signed-in user's own digest, and neither can be baked into a build."*

---

## 2. Existing ISR / revalidation

### 2.1 Every hit for `revalidate` / `revalidatePath` / `revalidateTag` / `unstable_cache` / `next: { revalidate`

Search scope: all of `frontend/` for `*.ts`, `*.tsx`, `*.js`, `*.mjs`, `*.json`, `*.md`, excluding `node_modules/` and `.next/`.

**There is exactly ONE hit in the whole frontend:**

`frontend/app/preview/page.test.tsx:43`

```tsx
expect("revalidate" in page).toBe(false);
```

Context (the whole test, `frontend/app/preview/page.test.tsx:36-44`):

```tsx
describe("AD-12: no session, nothing per-visitor on the server", () => {
  it("exports no dynamic rendering flag, so the page can be prerendered", async () => {
    // A `force-dynamic` here would make every visitor's request render the page afresh,
    // which is exactly what a public, cacheable surface must not need.
    const page = await import("@/app/preview/page");

    expect("dynamic" in page).toBe(false);
    expect("revalidate" in page).toBe(false);
  });
```

**Zero hits** for `revalidatePath`, `revalidateTag`, `unstable_cache`, `next: { revalidate`, `generateStaticParams`, `dynamicParams`, `cacheComponents`, `partialPrefetching`.

**Conclusion: there is NO existing ISR or on-demand revalidation machinery in the frontend.** The word "revalidate" appears in the frontend exactly once, and it is a *negative* assertion — a test asserting the `/preview` page does **not** export `revalidate`.

> ⚠️ **Design constraint this creates:** if a future public page exports `export const revalidate = 3600`, the `/preview` test at `frontend/app/preview/page.test.tsx:43` is unaffected (it only imports `@/app/preview/page`). But if someone adds `revalidate` to `/preview` itself, **that test fails**. `/preview` must stay `revalidate`-free.

### 2.2 Route handlers under `app/api/`

**There is NO `app/api/` directory. There are NO route handlers (`route.ts`) anywhere in the frontend.**

Command run: `find app -path "*api*" -type f` → empty. Full `app/` file listing confirms no `route.ts` file exists.

**Why:** `frontend/proxy.ts:5-8` explains that `/api/*` is not a Next route at all — it is *rewritten* to Django at the edge:

```
// The browser only ever calls /api/* on this site; Next forwards it to Django. Same origin, so
// no CORS, and cookies stay first-party. Runs per request, so API_BASE_URL can change without a
// rebuild (next.config rewrites would be fixed at build time).
// Note: Next adds an x-middleware-rewrite response header naming the backend URL.
```

So **any** path under `/api/` on the frontend is already spoken for: it is the Django API's namespace, proxied. This is the mechanical reason the revalidation endpoint cannot live under `/api/` — it would be intercepted by the proxy and rewritten to Django, never reaching a Next route handler.

---

## 3. The proxy

### 3.1 The file

`frontend/proxy.ts` — 29 lines total. Full content:

```ts
import { NextResponse, type NextRequest } from "next/server";

import { apiBaseUrl } from "@/lib/api-base-url";

// The browser only ever calls /api/* on this site; Next forwards it to Django. Same origin, so
// no CORS, and cookies stay first-party. Runs per request, so API_BASE_URL can change without a
// rebuild (next.config rewrites would be fixed at build time).
// Note: Next adds an x-middleware-rewrite response header naming the backend URL.

let reportedMissing = false;

export function proxy(request: NextRequest) {
  const base = apiBaseUrl();
  if (!base) {
    if (!reportedMissing) {
      console.error("API_BASE_URL is not set: /api requests answer 503 until it is.");
      reportedMissing = true;
    }
    return NextResponse.json(
      { code: "api_not_configured", message: "The service isn't available right now." },
      { status: 503 },
    );
  }
  const { pathname, search } = request.nextUrl;
  return NextResponse.rewrite(new URL(`${pathname}${search}`, base));
}

export const config = { matcher: "/api/:path*" };
```

> Note: the file is named `proxy.ts` (not `middleware.ts`), and exports a function named `proxy` (not `middleware`). `frontend/proxy.test.ts:6` imports `{ config, proxy } from "@/proxy"`.

### 3.2 The matcher — VERIFIED

**Your information is correct.** `frontend/proxy.ts:28`:

```ts
export const config = { matcher: "/api/:path*" };
```

The matcher intercepts **exactly** `/api/:path*` and nothing else. It is asserted in the test suite at `frontend/proxy.test.ts:18-20`:

```ts
it("only runs for /api/*", () => {
  expect(config.matcher).toBe("/api/:path*");
});
```

**Therefore: a revalidation endpoint MUST NOT live under `/api/`.** If it did, the proxy would match it and `NextResponse.rewrite(new URL("/api/...", base))` would send the request to Django. The Next route handler would never execute.

The proxy also has a **403-free 503 fallback** (`frontend/proxy.ts:14-23`): with no `API_BASE_URL` in production it answers `503` with body `{ code: "api_not_configured", message: "The service isn't available right now." }` and logs once.

### 3.3 Where a revalidation endpoint CAN live

Any path outside `/api/`. But note `frontend/app/` is **entirely** page routes today — a route handler would be a new file kind in the tree.

**Important naming caveat:** the matcher is `/api/:path*`, which does **not** match `/api` itself (no trailing segment) — but `/api/anything` does. A path like `/revalidate` or `/internal/revalidate` is unaffected.

**Also note:** the proxy is the file whose name is `proxy.ts`, and Next.js 16 renamed `middleware.ts` → `proxy.ts`. The proxy function is exported as `proxy`.

### 3.4 The base URL helper

`frontend/lib/api-base-url.ts` (full, 12 lines):

```ts
/** Where the Django API lives: an origin such as "http://127.0.0.1:8000" (any path is ignored). */
export const DEV_API_BASE_URL = "http://127.0.0.1:8000";

/**
 * API_BASE_URL, read when called (per request in proxy.ts), never baked in at build time.
 * Outside production it falls back to the local API; in production it must be set.
 */
export function apiBaseUrl(): string | undefined {
  const configured = process.env.API_BASE_URL;
  if (configured) return configured;
  return process.env.NODE_ENV === "production" ? undefined : DEV_API_BASE_URL;
}
```

---

## 4. How the frontend calls the backend

### 4.1 The client

**`openapi-fetch`** — not axios, not raw fetch.

`frontend/lib/backend-client.ts` (full, 38 lines):

```ts
import createClient from "openapi-fetch";

import type { paths } from "@/lib/api/schema";
import { apiBaseUrl } from "@/lib/api-base-url";
import { csrfOnRequest } from "@/lib/csrf";

/**
 * The only way frontend code reaches the backend (AD-19): typed from the generated schema.
 * In the browser requests stay on this site (/api/…), which proxy.ts forwards to Django;
 * on the Next.js server they go straight to API_BASE_URL.
 */
export const api = createClient<paths>({
  baseUrl: typeof window === "undefined" ? (apiBaseUrl() ?? "") : "",
});

/**
 * **In the browser, every state-changing request carries the CSRF token** (D13).
 * ...
 * It is not registered on the server. There is no `document` to read the cookie from, and
 * the server only ever reads.
 * ...
 */
if (typeof window !== "undefined") {
  api.use({
    onRequest: csrfOnRequest({
      requestToken: () => api.GET("/api/auth/csrf"),
    }),
  });
}
```

**Key mechanics:**
- `baseUrl` is **empty string in the browser** (`""`), so browser requests hit the frontend's own origin at `/api/…` and the proxy rewrites them to Django. On the server it is `apiBaseUrl() ?? ""` — the Django origin directly.
- `paths` is the generated type from `frontend/lib/api/schema.ts`.

### 4.2 The generated API contract

`frontend/lib/api/README.md` (full, 16 lines):

```
# `lib/api/`: generated API contract

Everything in this folder except this README is **generated** and **never edited by hand** (AD-19):

| File           | Made by                                                 | From           |
| -------------- | ------------------------------------------------------- | -------------- |
| `openapi.json` | `make openapi` (Django Ninja's `export_openapi_schema`) | the live API   |
| `schema.ts`    | `make client` (`openapi-typescript`)                    | `openapi.json` |

After changing an API endpoint, run `make client` and commit both files. The backend suite fails
(`tests/api/test_contract.py`) until `openapi.json` matches the API, and CI regenerates both and
fails on any diff.

Frontend code reaches the backend only through `api` from `@/lib/backend-client`, which is typed
from `schema.ts`. ESLint rejects hand-written `fetch` calls in `app/` and `components/`.
```

Files: `frontend/lib/api/openapi.json` (179,276 bytes, mtime Nov 2 13:42), `frontend/lib/api/schema.ts` (159,699 bytes, mtime Nov 2 13:42).

### 4.3 How a page fetches a backend endpoint

Pattern (from `frontend/app/preview/page.test.tsx:101-111`, asserting the call shape):

```tsx
expect(GET).toHaveBeenCalledWith("/api/public/preview", { params: { query: {} } });
```

and from the server-side read modules, e.g. `frontend/lib/timeline-read.ts`, `frontend/lib/digest-read.ts`, `frontend/lib/event-detail-read.ts` — these are the "read" modules that call `api.GET(...)` on the server.

**So: `const { data, error } = await api.GET("/api/catalog/events/by-slug/{slug}", { params: { path: { slug } } })`.**

### 4.4 ESLint enforcement of AD-19 (critical for a new endpoint)

`frontend/eslint.config.mjs` (full, 43 lines):

```js
// AD-19: frontend code reaches the backend only through the generated client.
const BACKEND_ACCESS = "Reach the backend through `api` from @/lib/backend-client (AD-19).";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // coding-standards: @typescript-eslint/strict on top of Next's TypeScript rules.
  ...tseslint.configs.strict,
  {
    files: ["app/**/*.{ts,tsx}", "components/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-globals": ["error", { name: "fetch", message: BACKEND_ACCESS }],
      "no-restricted-properties": [
        "error",
        { object: "window", property: "fetch", message: BACKEND_ACCESS },
        { object: "globalThis", property: "fetch", message: BACKEND_ACCESS },
        { object: "self", property: "fetch", message: BACKEND_ACCESS },
      ],
    },
  },
  {
    files: ["**/*.{ts,tsx,mts,mjs}"],
    ignores: ["lib/backend-client.ts"],
    rules: {
      "no-restricted-imports": [
        "error",
        { paths: [{ name: "openapi-fetch", message: BACKEND_ACCESS }] },
      ],
    },
  },
  // Last: turn off rules that would fight Prettier's formatting.
  prettier,
  globalIgnores([".next/**", "out/**", "build/**", "coverage/**", "next-env.d.ts", "lib/api/**"]),
]);
```

**Two rules that bear directly on the design:**
1. **`fetch` is banned in `app/` and `components/`** (globals and `window.`/`globalThis.`/`self.` property access). A Next.js **route handler** lives in `app/`, so a route handler **cannot use raw `fetch`** without an ESLint error. This applies to any *outbound* call a route handler might make.
2. **`openapi-fetch` may only be imported in `lib/backend-client.ts`.** The `ignores` is scoped to the `no-restricted-imports` rule block only.

> ⚠️ **Design consequence:** if the revalidation route handler lives at `app/<something>/route.ts`, it is inside the `files: ["app/**/*.{ts,tsx}"]` glob — so `fetch` is banned there. If it needs to make an outbound call, it must go through `api` from `@/lib/backend-client`, or the file must live outside `app/` (which is impossible for a Next route handler). **Note the `no-restricted-imports` block's `files` glob is `["**/*.{ts,tsx,mts,mjs}"]` — broader than `app/`+`components/`.** So `openapi-fetch` is banned everywhere except `lib/backend-client.ts`.

### 4.5 Base URL configuration

| Layer | Mechanism | Source |
| --- | --- | --- |
| Browser → backend | same-origin `/api/*` → `proxy.ts` → `API_BASE_URL` | `frontend/proxy.ts:25` |
| Next server → backend | `API_BASE_URL` read directly | `frontend/lib/backend-client.ts:13` |
| Env var name | **`API_BASE_URL`** (server-only; **not** `NEXT_PUBLIC_`-prefixed) | `frontend/lib/api-base-url.ts:9` |
| Local fallback | `DEV_API_BASE_URL = "http://127.0.0.1:8000"` | `frontend/lib/api-base-url.ts:2` |
| Prod without the var | `undefined` → proxy answers 503 | `frontend/lib/api-base-url.ts:11`, `frontend/proxy.ts:14-23` |

---

## 5. Frontend config

### 5.1 `next.config.ts` — EMPTY

`frontend/next.config.ts` (full, 5 lines):

```ts
import type { NextConfig } from "next";

const nextConfig: NextConfig = {};

export default nextConfig;
```

**There is no `cacheComponents`, no `revalidate`, no `rewrites`, no `headers`, no `images` config.** `next.config.ts` is an empty config object (brief.md:27 confirms: *"`next.config.ts` is an empty config object."*).

### 5.2 `package.json` — `frontend/package.json`

Scripts (`frontend/package.json:9-18`):

| Script | Command |
| --- | --- |
| `dev` | `next dev` |
| `build` | `next build` |
| `start` | `next start` |
| `lint` | `eslint .` |
| `typecheck` | `next typegen && tsc --noEmit` |
| `test` | `vitest run` |
| `format` | `prettier --write .` |
| `format:check` | `prettier --check .` |

Production dependencies (`frontend/package.json:19-24`):

```
"next": "16.3.8",
"openapi-fetch": "0.17.0",
"react": "19.2.9",
"react-dom": "19.2.9"
```

**Notable devDependency:** `"openapi-typescript": "7.13.0"` (`frontend/package.json:41`) — generates `frontend/lib/api/schema.ts` from `openapi.json` via `make client`.

Engines (`frontend/package.json:6-8`):

```json
"engines": {
  "node": ">=24.15"
}
```

### 5.3 `.env*` — VARIABLE NAMES ONLY (no values)

**`frontend/.env*` — NO env files exist in `frontend/`.** (Command: `ls frontend/.env*` → "none".) All env vars are read at the repo root.

**Root `.env` (var names only):**
`EP_PG_PORT`, `EP_REDIS_PORT`, `EP_SMTP_PORT`, `EP_MAILPIT_UI_PORT`, `API_PORT`, `WEB_PORT`, `EP_DB_NAME`, `EP_PG_SUPERUSER_PASSWORD`, `EP_OWNER_PASSWORD`, `EP_CATALOG_PASSWORD`, `EP_PERSONAL_PASSWORD`, `DATABASE_URL_OWNER`, `DATABASE_URL_CATALOG`, `DATABASE_URL_PERSONAL`, `REDIS_URL`, `SMTP_HOST`, `SMTP_PORT`, `ADAPTER_MODE`, `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_DB_ROLE`, `CALENDAR_CREDENTIAL_KEY`, `CSRF_TRUSTED_ORIGINS`

**Root `.env.example` (var names only):** the same set **plus** `API_BASE_URL` (and minus nothing). Full list:
`EP_PG_PORT`, `EP_REDIS_PORT`, `EP_SMTP_PORT`, `EP_MAILPIT_UI_PORT`, `API_PORT`, `WEB_PORT`, **`API_BASE_URL`**, `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `DJANGO_DB_ROLE`, `CALENDAR_CREDENTIAL_KEY`, `EP_DB_NAME`, `EP_PG_SUPERUSER_PASSWORD`, `EP_OWNER_PASSWORD`, `EP_CATALOG_PASSWORD`, `EP_PERSONAL_PASSWORD`, `DATABASE_URL_OWNER`, `DATABASE_URL_CATALOG`, `DATABASE_URL_PERSONAL`, `REDIS_URL`, `SMTP_HOST`, `SMTP_PORT`, `ADAPTER_MODE`

> ⚠️ **There is NO `FRONTEND_URL`, no `NEXT_PUBLIC_*`, no `REVALIDATION_SECRET`, no `REVALIDATE_*` variable anywhere in the repo.** A new shared secret for the revalidation handshake would be a NEW env var.

**Backend-side env vars** (`backend/config/env.py`, pydantic-settings `Settings`, `env_file = REPO_ROOT/.env`): `django_secret_key`, `django_debug`, `django_allowed_hosts`, `csrf_trusted_origins`, **`frontend_base_url`**, `trust_forwarded_for`, `django_db_role`, `database_url_owner`, `database_url_catalog`, `database_url_personal`, `redis_url`, `smtp_host`, `smtp_port`, `calendar_credential_key`, `adapter_mode`, `source_fetch*`, `geo_fake_city`.

**🔑 `frontend_base_url` already exists** — `backend/config/env.py:34-36`:

```python
    # The frontend's base URL. The reset link points at the frontend's route, not at the
    # API, because the frontend is a different origin from this runtime.
    frontend_base_url: str = "http://localhost:3000"
```

This is the natural home for the backend→frontend revalidation URL. **It has no default in `.env.example`** — the default lives in the pydantic field.

### 5.4 Node engine mismatch — CONFIRMED

| Fact | Value | Source |
| --- | --- | --- |
| Required | `>=24.15` | `frontend/package.json:7` |
| Enforcement | `engineStrict: true` | `frontend/pnpm-workspace.yaml:4` |
| `.nvmrc` | `24` | `.nvmrc:1` |
| **Installed & active** | **v20.20.0** | `node --version` → `v20.20.0`; `which node` → `/home/bs1346/.nvm/versions/node/v20.20.0/bin/node` |
| **Installed but not active** | **v24.22.1** | `ls ~/.nvm/versions/node` → `v12.18.4`, `v16.14.2`, `v20.20.0`, `v24.22.1` |
| pnpm | 12.15.0 | `pnpm --version` |

**CONFIRMED MISMATCH:** Node **v20.20.0** is the active version, but `>=24.15` is required. `v24.22.1` **is installed** at `~/.nvm/versions/node/v24.22.1` — it is simply not selected. The fix is `nvm use 24` (or `~/.nvm/versions/node/v24.22.1/bin`), not an install.

`tech-stack.md:25` explains the requirement: *"Python 3.13, **Node.js 24 LTS (≥24.15)**. Node 20 is end of life (April 2026), and Vitest 5 / jsdom 30 need it (user decision, run-eventpulse24-007). Enforced by `engineStrict` in `frontend/pnpm-workspace.yaml`, `make doctor`, and `.nvmrc`."*

> ⚠️ **Practical impact:** with `engineStrict: true` and Node 20 active, `pnpm install` will **fail** the engine check. Any `pnpm build` / `pnpm test` run in this environment needs Node 24 selected first.

> Also note: the **spine** says `Node.js ≥20.9` (`ARCHITECTURE-SPINE.md:347`), while `tech-stack.md:25` and `package.json` say `≥24.15`. The tech-stack and the lockfile are the newer authority.

---

## 6. STANDARDS — rules that bear on this feature

### 6.1 `.specs-fire/standards/constitution.md` (full, 49 lines)

Key rules:

- **Line 8** — *"`_bmad-output/planning-artifacts/architecture/architecture-EventPulse24-2026-09-04/ARCHITECTURE-SPINE.md` binds all code. Its ADs (AD-1..AD-21) are invariants, not suggestions; deviating requires amending the spine first."*
- **Line 44** — *"The API contract is the generated OpenAPI schema (AD-19) — every endpoint appears in it"*
- **Line 30** — *"Main branch deployments are automated (Vercel for frontend; always-on Python host for API/worker)"*
- **Line 35** — *"**No secrets in code** — config is validated once at startup via pydantic-settings; secrets live in the platform secret store only"*
- **Line 40** — *"No credentials, API keys, or tokens in source control"*
- **Line 36** — *"No PII in logs — redaction enforced at the logger adapter's allowlist (AD-13)"*
- **Line 31** — *"Preview environments never send real email and never write to the real Source Registry"*

### 6.2 `.specs-fire/standards/coding-standards.md` — the rules that bite

**Frontend ↔ backend access (AD-19)** — `coding-standards.md:47`:
> "Frontend imports from `frontend/lib/api/` only for backend access. No hand-written fetch to backend routes (AD-19)"

**Browser → API goes through Next.js** — `coding-standards.md:48`:
> "**Browser → API goes through Next.js** (user decision, run-eventpulse24-008). The browser calls `/api/…` on the frontend's own origin; `frontend/proxy.ts` forwards it to `API_BASE_URL`, **read per request** (no rebuild to change it; `next.config` rewrites would be baked in at build). Same origin: **no CORS is configured, deliberately**. Server-side code calls `API_BASE_URL` directly through the same client."

**Backend calls use `api` from `@/lib/backend-client`** — `coding-standards.md:49`:
> "**Backend calls use `api` from `@/lib/backend-client`** (`openapi-fetch` over the generated `paths`). ESLint rejects `fetch`, `window.fetch`, `globalThis.fetch` and `self.fetch` in `app/` and `components/`, and `openapi-fetch` imports outside `lib/backend-client.ts`. After an API change, `make client`; `backend/tests/api/test_contract.py` fails until the committed schema matches."

**Layering / import contracts** — `coding-standards.md:26-30`:
> "**Layers** (import-linter `layers`, AD-1/AD-2): `config | worker` → `apps | adapters` → `ports` → `domain` → `shared`. Higher may import lower, never the reverse."
> "`config` (the API surface and composition root) and `worker` never import each other (AD-1)."
> "`apps` and `adapters` never import each other: apps reach adapters through `ports` and settings."

**`os.environ` ban** — `coding-standards.md:46`:
> "**`os.environ` / `os.environb` / `os.getenv` / `os.getenvb`** (Ruff `TID251` banned-api): only under `backend/config/` (pydantic-settings), plus `manage.py` (bootstrap) and `tests/`."

**Request handlers** — `coding-standards.md:114`:
> "**Request handlers** validate, enqueue and return. Crawl, extraction, embedding and bulk send run in the worker (AD-11)."

**No direct writes from surfaces (AD-5/AD-14)** — `coding-standards.md:43-44`:
> "**No direct writes from surfaces** (`tests/architecture/test_no_direct_writes.py`, AD-5/AD-14): `apps/*/admin.py`, `apps/*/api.py` and `config/api.py` make no `.save()`, `.create()`, `.update()`, `.delete()`, `bulk_*`, `get_or_create()` or `update_or_create()` call. The scan is syntactic, so it flags any receiver (a `dict.update()` too); surface modules avoid those names."

**Always pass `using=`** — `coding-standards.md:110`:
> "**Always pass `using=`**: import `PERSONAL` / `CATALOG` from `shared.db` and pass them to `transaction.atomic(using=…)`, `.using(…)` and raw `connections[…]`. A bare `transaction.atomic()` silently means personal. No transaction spans both schemas; operations touching both are ordered and idempotent."

**Logging rules that constrain a signal emitter** — `coding-standards.md:229-251`:
- Only fields in `adapters/logging/redaction.ALLOWED_FIELDS` are kept; anything else is `[redacted]`. *"Adding a field to the allowlist is a reviewed change: ids, counts, durations and slugs only, **never free text**."*
- *"Project loggers … **never interpolate args**: `logger.info("Saved %s", title)` logs `"Saved %s"` with `args: [redacted]`. Ruff `G` forbids f-strings, `.format`, `%` and `+` in log calls."*
- *"Exception **messages are never logged**, only the type chain and the stack frames (they echo user input)."*
- **Always log:** ids (`event_id`, `source_id`, `user_id` as UUID, `state_change_id`), counts, durations, idempotency keys on send attempts.
- **Never log:** email addresses, names, or any PII; OAuth tokens, secret ICS URLs, API keys; personal event content; raw source HTML or prompt bodies.

**Comments** — `coding-standards.md:253-255`:
> "Cite the AD or FR when code exists to satisfy one (`# AD-7: key minted once, never from due_at`). Explain *why*, never *what*. Mark accepted trade-offs explicitly where the spine names one."

**Backend structure** — `coding-standards.md:108-110`: *"Backend `snake_case.py`, one concept per module; services as verbs (`compose_digest.py`), queries as `get_`/`list_`."*

### 6.3 `.specs-fire/standards/testing-standards.md` — rules that bite

- **Line 5**: *"Tests prove the architecture's invariants, not just behaviour."*
- **Line 22**: E2E + a11y via Playwright + `@axe-core/playwright` in `frontend/e2e/`.
- **Line 26-29**: Coverage target 80% overall, **100% of `backend/domain/`**; measured over `domain`, `apps`, `ports`, `adapters`, `config`, `worker`, `shared`.
- **Line 38**: *"Propagation: versioned, idempotent, out-of-order safe, outbox reconciler (AD-17)"* is on the **critical paths that MUST have coverage** list.
- **Line 76**: *"Any test touching `catalog` must use `@pytest.mark.django_db(databases=[PERSONAL, CATALOG])`, or it fails with 'Database queries to "catalog" are not allowed'."*
- **Line 77**: *"Tests that need to observe a **commit** … need `transaction=True`."*
- **Line 80**: Tests run as the **owner** role (`config.settings_test`); `tests/roles.py` provides `run_as(role_url, *statements)` and `expect_denied(...)`.
- **Line 91-92**: *"**Approach**: fake at the **port** boundary. Never mock Django ORM or the database."* and *"Use in-memory fakes implementing `ports/` interfaces for LLM, email, calendar, crawl, billing"*
- **Line 97-98**: *"Freeze time explicitly. Never depend on wall-clock or local timezone. No `time.sleep` in tests"*
- **Line 144**: CI gate — *"OpenAPI schema export → regenerate TS client → frontend typecheck (AD-19). Locally, `backend/tests/api/test_contract.py` already fails when `frontend/lib/api/openapi.json` doesn't match the live API (`make client` fixes it)"*
- **Line 133**: CI `contract:` job runs `make client`, then `git diff --exit-code frontend/lib/api/`.
- **Line 134**: CI `frontend:` job — *"Node from `.nvmrc`; `make web-install`, `make lint-web`, `make test-web`, `pnpm build`"*

**The port-boundary fake rule (line 91-92) is the key constraint for testing a revalidation outbound call: if it is implemented as a port + adapter, the test uses an in-memory fake implementing the port — the pattern used for LLM, email, calendar, crawl and billing.**

### 6.4 `.specs-fire/standards/tech-stack.md` — rules that bite

- **Line 20**: *"Next 16 `cacheComponents` and `partialPrefetching` make ISR'd public event pages viable at scale (AD-12)."*
- **Line 25**: *"Python 3.13, **Node.js 24 LTS (≥24.15)**. Node 20 is end of life (April 2026), and Vitest 5 / jsdom 30 need it (user decision, run-eventpulse24-007). Enforced by `engineStrict` in `frontend/pnpm-workspace.yaml`, `make doctor`, and `.nvmrc`."*
- **Line 44**: *"**Caching** — **Solution**: Redis (managed) as the Celery broker. It carries **only** the periodic tick and the pipeline jobs, **never** the reminder schedule (AD-7). LLM prompt caching lives in the gateway (AD-8). **Public pages are cached by Vercel ISR.**"
- **Line 54**: *"Django Ninja's OpenAPI schema is the single source of truth. The frontend TS client in `frontend/lib/api/` is generated from it in CI and never hand-edited (AD-19)."*
- **Line 69**: *"**State Management** — **Solution**: Server components + the generated API client. No global client state library is adopted at MVP."*
- **Line 76**: *"Frontend: Vercel. Hobby while building, **Pro mandatory before Stripe checkout is enabled** (hard launch gate)."*
- **Line 128**: `httpx` 0.28.1 — *"HTTP framing and redirects for `adapters.crawl.http` only (import contract `http-client`)"*. **⚠️ The `http-client` import contract means `httpx` may only be imported by `adapters.crawl.http`.** A new outbound HTTP call (backend → frontend) would need a new port + adapter, or the existing `http-client` contract would need widening.
- **Line 152**: *"`openapi-fetch` (0.17.0, runtime): typed `fetch` over the generated `paths`, used only in `lib/backend-client.ts`"*
- **Line 151**: *"`openapi-typescript` (7.13.0): generates `frontend/lib/api/schema.ts` from the committed `openapi.json` (`make client`)"*

### 6.5 `.specs-fire/standards/system-architecture.md` — rules that bite

- **Line 11**: *"A web-first product. Anonymous visitors reach ISR'd public event pages (SEO acquisition)."*
- **Line 16** (context diagram): `browser ──► Vercel (Next.js) ──OpenAPI──► API runtime (Django Ninja) ──► Neon PG18`. **There is no arrow from API/worker back to the frontend.** The revalidation feature introduces the first one.
- **Line 59-62**: **`catalog` component** — *"**Purpose**: public read surface for Events. **Responsibilities**: public event pages and SEO data, schema.org JSON-LD. **Dependencies**: reads `catalog` via `ingestion` read interface"*
- **Line 87**: Component diagram top: *"Next.js frontend (generated client only)"*
- **Line 102**: `browser ──/api/*──► Next.js proxy.ts (same origin) ──API_BASE_URL──► Django Ninja`
- **Line 127**: Frontend stack: *"Next.js 16.3 / React 19.2 / Tailwind 4 — Surfaces + ISR public pages"*
- **Line 144**: *"**Public SEO pages**: 99.9% uptime"*
- **Line 158**: *"Public pages scale via ISR."*
- **Line 183**: `AD-12 Public surface | Session-free, ISR | SEO uptime decoupled from auth`
- **Line 186**: `AD-19 Contract | Generated OpenAPI client | No frontend/backend drift`

**Note:** `system-architecture.md:3` states *"**The spine is authoritative.** Read it for full AD rules, rationale and accepted costs."* — and the spine's Key Decisions table (`system-architecture.md:170-188`) lists **15 of the 21 ADs** (AD-9, AD-14, AD-15 are omitted from the condensed table). The spine itself is the full list.

### 6.6 Consolidated: the rules that directly bear on a "revalidation signal" feature

| # | Rule | Where | Effect on this feature |
|---|---|---|---|
| R1 | **AD-19** — "The OpenAPI schema Django Ninja emits is the **single source of truth** for the boundary… No endpoint exists that is absent from the schema." | `ARCHITECTURE-SPINE.md:226` | If the backend gains an endpoint, `openapi.json` + `schema.ts` must be regenerated (`make client`) and committed, or CI's `contract` job fails. |
| R2 | **AD-12** — "Public event pages render fully without a session and are statically generated or ISR'd. Personalized content on a public page arrives only via a separate client-side request." | `ARCHITECTURE-SPINE.md:166` | The revalidation target is an ISR'd page. The page must not read a session, or revalidating it is pointless/harmful. |
| R3 | **AD-1** — "The **Next.js frontend** is a client — it holds no domain logic and reaches the backend only through the generated API client (AD-19)." | `ARCHITECTURE-SPINE.md:63` | The frontend's revalidation handler is an *edge*, not a domain surface. It must not decide anything about events. |
| R4 | **AD-11** — "No request handler performs crawl, extraction, embedding, or bulk send. Such work is enqueued and executed in the worker runtime. A request handler's job is to validate, enqueue, and return." | `ARCHITECTURE-SPINE.md:160` | The backend side that emits the signal must be a **worker job**, not an inline call inside an ingestion request. |
| R5 | **AD-5** — "No route handler, job, or adapter writes to the database directly. Every mutation is a named application command." | `ARCHITECTURE-SPINE.md:93` | If revalidation state is recorded, it is a named command in the owning app. |
| R6 | **AD-13** — redaction at the logger allowlist; never log secrets or free text | `ARCHITECTURE-SPINE.md:172`, `coding-standards.md:229-251` | The shared secret must never reach a log line; only ids/counts/durations/slugs. |
| R7 | **No secrets in code** — "secrets live in the platform secret store only" | `constitution.md:35` | The revalidation shared secret is a new env var in the platform secret store, not in the repo. |
| R8 | **Ruff `TID251`** — `os.environ` only under `backend/config/` | `coding-standards.md:46` | The secret is read via `config/env.py` pydantic-settings, never `os.environ` in a service. |
| R9 | **Config validated once at startup** — "no `os.environ` reads below `config/`" | `ARCHITECTURE-SPINE.md:307` | Same as R8. |
| R10 | **Import contract `http-client`** — `httpx` only in `adapters.crawl.http` | `tech-stack.md:128` | A backend→frontend HTTP call needs a **new port + adapter** (e.g. `ports/revalidation.py` + `adapters/revalidation/…`), or the contract is widened (a reviewed change). |
| R11 | **Ports are ABCs over frozen dataclasses**; `ports.registry.get_<x>_port()`; new port needs a `PORT_KEYS` entry and an entry in every `config/adapters.py` table | `coding-standards.md:33-36` | A new outbound port needs registry + every adapters table + `ADAPTER_MODE=real` startup check. |
| R12 | **Fake at the port boundary** — "Never mock Django ORM or the database" | `testing-standards.md:91` | The revalidation outbound call is tested with an in-memory fake port. |
| R13 | **ESLint: `fetch` banned in `app/`**; `openapi-fetch` only in `lib/backend-client.ts` | `eslint.config.mjs:16-36` | A Next route handler under `app/` cannot use raw `fetch`. |
| R14 | **No direct writes from surfaces** — syntactic scan over `apps/*/api.py` | `coding-standards.md:43` | A backend endpoint that records revalidation state cannot `.save()`. |
| R15 | **Always pass `using=`** — no bare `transaction.atomic()` | `coding-standards.md:110` | Catalog-side writes use `using=CATALOG`. |
| R16 | **Request handlers validate, enqueue and return** | `coding-standards.md:114` | Same as R4. |
| R17 | **Preview environments never send real email and never write to the real Source Registry** | `constitution.md:31` | A preview deploy must not trigger a production revalidation. |
| R18 | **`frontend_base_url` already exists** in `backend/config/env.py:36` | `backend/config/env.py:34-36` | The backend→frontend URL has a home; it is a pydantic-settings field, not `os.environ`. |
| R19 | **Outbound direction is a NEW one** — "until now the frontend has been a pure client of the API (AD-19)" | `brief.md:89` | OQ-C: *"The call path, its shared secret, and its failure behaviour need deciding; a missed revalidation must degrade to stale-but-correct, never to a wrong page."* |

---

## 7. ARCHITECTURE-SPINE.md — the COMPLETE list of numbered decisions

**Path:** `_bmad-output/planning-artifacts/architecture/architecture-EventPulse24-2026-09-04/ARCHITECTURE-SPINE.md` (493 lines, `status: draft`, `updated: '2026-10-27'`).

**Frontmatter (lines 1-22):**
```yaml
name: 'EventPulse24'
type: architecture-spine
purpose: build-substrate
altitude: initiative
paradigm: 'Django modular monolith, ports-and-adapters, two Python runtimes from one repo + a Next.js client'
scope: 'EventPulse24 MVP — the 45 MVP FRs: onboarding, Pulse Digest, reminders, event ingestion, personal events, Timeline and conflict-aware scheduling, explainability, event state sync, sharing/SEO, AI cost discipline, Pro tier'
status: draft
created: '2026-09-04'
updated: '2026-10-27'
sources_as_of: 'PRD amendments A-1..A-9 (A-8 lifts FR-32/FR-33 to MVP; A-9 aligns FR-3/FR-50 to ICS)'
binds:
  - FR-1..FR-30
  - FR-32..FR-33
  - FR-48..FR-60
sources:
  - _bmad-output/planning-artifacts/prds/prd-EventPulse24-2026-08-19/prd.md
  - _bmad-output/planning-artifacts/prds/prd-EventPulse24-2026-08-19/addendum.md
  - _bmad-output/planning-artifacts/ux-designs/ux-EventPulse24-2026-08-23/EXPERIENCE.md
  - _bmad-output/planning-artifacts/ux-designs/ux-EventPulse24-2026-08-23/DESIGN.md
companions: []
```

**Design Paradigm (lines 28-43):** *"Django modular monolith with ports-and-adapters at every external edge, running as two Python runtimes from one repository, served to a separate Next.js client."* — *"One backend codebase, one database, one set of Python domain packages. Two backend deploys — an **API runtime** (Django Ninja) and a **worker runtime** (long-lived loop) — plus the **Next.js frontend**, which is a *client* of the API and shares no domain code with it."*

**The layer table (lines 34-41):**

| Layer | Location | May import |
| --- | --- | --- |
| Domain — pure logic + value objects, **no Django, no I/O, no entity classes** | `backend/domain/` | stdlib only |
| Django apps — **models (the entities)**, services, API routers | `backend/apps/<module>/` | domain, ports |
| Ports — interfaces the apps require | `backend/ports/` | domain |
| Adapters — DB, LLM, email, calendar, crawl | `backend/adapters/<tech>/` | ports, domain |
| Surfaces — API routers, worker commands | `backend/apps/*/api.py`, `backend/worker/` | apps, ports |
| Client — Next.js | `frontend/` | the generated OpenAPI client only |

**The six MVP modules (line 43):** `ingestion`, `catalog`, `personalization`, `delivery`, `identity`, `editorial`.

---

### The COMPLETE list of numbered decisions — exact text

#### AD-1 — Workload separates runtimes, not features `[ADOPTED]` (line 59)

> - **Binds:** all
> - **Prevents:** a crawl or LLM batch competing with Pulse Digest composition for the same process, blowing the <500ms p95 budget — which PRD §10.5 classifies as a SEV-1 incident.
> - **Rule:** Three deploys. The **API runtime** and the **worker runtime** are both Python, deploy separately from the same repository, and share `domain`, `apps`, `ports`, `adapters`; neither imports the other's surface layer. The **Next.js frontend** is a client — it holds no domain logic and reaches the backend only through the generated API client (AD-19). A module is never duplicated across runtimes.

#### AD-2 — Dependencies point inward, and `domain` is logic, not entities `[ADOPTED]` (line 65)

> - **Binds:** all
> - **Prevents:** the modular monolith degrading into a big ball of mud, where the wall is a convention that compiles fine when violated — *and* the opposite failure, a parallel entity model that drifts from the Django model it mirrors.
> - **Rule:** **Django models are the entities.** There is exactly one representation of an entity, and it is the model — the admin operates on it directly. `domain/` holds **pure logic only**: functions and value objects that take plain data and return plain data. It defines no entity classes, performs no I/O, and imports **stdlib only** — a domain module must be importable with Django uninstalled. Adapters never import other adapters. Cross-module calls go through the target app's published service interface, never its models or internals.
> - **Enforcement:** `import-linter` contracts in CI, not review. Two contracts: `domain` may import stdlib only; `apps.<X>` may not import `apps.<Y>.models`.
> - **What belongs in `domain`:** the algorithmic core that must be testable without a database — dedup identity derivation (AD-4), UTC conflict detection (AD-6), quiet-hours due-time shifting (AD-7), ranking. Pydantic extraction schemas are an *adapter* concern and live with the LLM adapter, not here.

#### AD-3 — Public and personal data are schema-separated `[ADOPTED]` (line 73)

> - **Binds:** FR-3, FR-18–20, FR-50, FR-52; PRD §10.2
> - **Prevents:** a convenience join that makes the isolation requirement, the 30-day deletion guarantee, and the per-category retention windows unenforceable.
> - **Rule:** Public event data lives in schema `catalog`; personal user data in schema `personal`. **No foreign keys and no SQL joins cross that boundary.** Composition happens in the application layer. Account deletion is a `personal`-scoped operation that never touches `catalog`.
> - **Enforcement:** the two schemas are exposed as **two Django `DATABASES` entries** against the same Postgres with different `search_path`, behind a database router. Django cannot create relations or joins across databases, so the ORM itself refuses a cross-schema join — the framework is the enforcement mechanism, and the mistake is impossible to *write*, not merely wrong at runtime. Connection roles additionally `GRANT` on their own schema only.
> - **Accepted cost:** **no transaction spans both schemas.** `transaction.atomic(using=...)` is per-schema. Any operation touching both must be ordered and idempotent rather than all-or-nothing — this is the direct consequence of AD-17's propagation rule, not a workaround for it.
> - **Spike required:** confirm the `search_path`-per-connection pattern behaves correctly under Django 6.1 migrations (`allow_migrate` per database) before this is relied on.

#### AD-4 — Event Identity is the sole dedup authority; embeddings never decide it `[ADOPTED]` (line 82)

> - **Binds:** FR-13–17, FR-53–55, FR-60
> - **Prevents:** two owners of one entity, and the specific divergence of a builder reaching for cosine similarity as an identity test — which silently merges distinct events and is explicitly forbidden by PRD §3.
> - **Rule:** The `ingestion` module is the **sole writer** of `catalog`. Identity is decided **only** by the Glossary's Event Identity tuple `(source_id, source_event_id, venue_fingerprint, start_time_with_tz, title_fingerprint)` and its three match rules. **Embedding cosine similarity is never an identity signal.** Cosine ≥0.95 routes a pair to the editorial review queue as "possible duplicate" and never auto-merges. Recurring events are distinct `event_id`s sharing a `series_id`.
> - **Rule (state):** State changes — postpone, cancel, move, sold-out — update the same `event_id` and **append** to `state_history`; history is never rewritten. Propagation into `personal` is AD-17's, not this module's. A postponement within ±30 days of the original start keeps the `event_id`; beyond ±30 days it creates a new Event. The old Event then receives a terminal `superseded_by` state change pointing at the new one, which AD-17 propagates like a cancellation — users are notified and re-save; plans are never silently migrated.

#### AD-5 — State changes only through named commands `[ADOPTED]` (line 89)

> - **Binds:** all
> - **Prevents:** two builders inventing two mutation paths for the same entity, so invariants live in one path and not the other.
> - **Rule:** No route handler, job, or adapter writes to the database directly. Every mutation is a named application command that owns its validation and its audit-log write. Reads may bypass commands; writes may not.

#### AD-6 — UTC is the storage truth, timezone is explicit `[ADOPTED]` (line 95)

> - **Binds:** FR-58, FR-60; PRD §11.6
> - **Prevents:** the timezone bug class — the same event conflicting for one user and not another because two modules chose different reference frames.
> - **Rule:** All instants stored as `timestamptz` in UTC. Every Event additionally carries an explicit IANA `start_time_tz` and a `tz_inference_confidence`. Conflict detection operates **only** in UTC. Display-time conversion happens at the presentation edge, never in domain logic. An Event with `tz_inference_confidence` <0.7 is not eligible for any Pulse Digest until editorial review completes.

#### AD-7 — Delivery is an idempotent due-index sweep, and Quiet Hours shift due time `[ADOPTED]` (line 101)

> - **Binds:** FR-9–12, FR-5–8, FR-51; PRD §10.4
> - **Prevents:** the per-user-timer pattern — millions of individually scheduled future timers, where reschedule and cancel-on-event-change become O(timers) and a source postponement means hunting down every affected timer. With a broker in the stack this is a live temptation, not a theoretical one.
> - **Rule:** Reminders and Pulse Pings dispatch from a worker sweeping a `(due_at, status)` index at **≤60s intervals**, triggered by Celery Beat. Every send carries a stable idempotency key (Rule (send key) below); delivery is at-least-once with dedupe at the send boundary. **The sweep must not be a platform cron** — Railway's cron floor is 5 minutes, which consumes the entire ±5 min budget before any queue latency, and skips a tick if the prior run is still active.
> - **Rule (quiet hours):** Quiet Hours are applied when `due_at` is **computed or recomputed**, deferring to the window end — never as a skip at send time. A deferred send is silently moved, never dropped and never re-delivered next day.
> - **Rule (send key):** The key is minted **once**, when the `SCHEDULED_SEND` row is created, stored under a unique constraint, and never derived from `due_at`:
>
> | Send kind | Key |
> | --- | --- |
> | Reminder for a saved public Event | `user_id · event_reminder · event_id · slot · event_version` |
> | Reminder for a Personal Event | `user_id · personal_reminder · personal_event_id · slot · personal_event_revision` |
> | State-change notice (FR-54) | `user_id · state_notice · state_change_id` |
> | Pulse Ping | `user_id · pulse_ping · local_date` |
> | Pulse Digest email | `user_id · digest · local_date` |
>
>   `event_version` and `personal_event_revision` are the values **at minting**; propagation may re-stamp a row's working `event_version` column (AD-17) but never its key. `slot` is the Reminder Plan slot (`5d`, `2d`, `1d`, `1hr`, or the custom slot's id). Quiet Hours, timezone, digest-time and tier changes **rewrite `due_at` on `pending` rows only and never touch the key**, so a recompute can never produce a second send. A lifecycle change that moves the event (AD-17) bumps `event_version`, cancels the old `pending` rows and mints new ones — the old key stays spent, so a `1d` reminder already sent for the old date does not block the `1d` reminder for the new one. The key is passed to the email provider as its idempotency key; a `sent` row is never rekeyed.
> - **Rule (single writer):** A send row transitions state under a row-level lock (`SELECT … FOR UPDATE SKIP LOCKED`), so adding worker replicas can never double-send.
> - **Rule (broker):** **Celery + Redis** runs background work. The broker carries the periodic tick and the pipeline jobs — crawl, extract, embed, propagate — and **nothing else**.
> - **Rule (the schedule is never in the broker):** A reminder is **never** enqueued as a per-reminder Celery task at its due time. `SCHEDULED_SEND` rows in Postgres are the sole source of truth for what is due. This is the invariant AD-7 exists for: per-reminder tasks make reschedule and cancel-on-postponement O(timers) again, and would put delivery at the mercy of Redis durability, which is not guaranteed by default. Because the schedule lives in Postgres, **a total Redis loss costs in-flight pipeline jobs, never a user's reminder** — the next tick re-finds the row, and AD-17's outbox re-enqueues any lost propagation.
> - **Rule (scheduler):** Celery's own beat scheduler with a **static `beat_schedule` in code**. `django-celery-beat` is not adopted: its purpose is admin-editable schedules, this schedule is one fixed tick, and its 2.9.0 release declares Django support only through 6.0 — not the 6.1 this project runs.

#### AD-8 — Every model call goes through one gateway, which owns fallback `[ADOPTED]` (line 123)

> - **Binds:** FR-13–16, FR-29, FR-30; PRD §10.3
> - **Prevents:** the per-MAU cost ceiling becoming unenforceable because cost is measured in six places — and a second module quietly adopting a different provider or a non-batched path.
> - **Rule:** No module imports a provider SDK. All extraction, embedding, and enrichment calls pass through `backend/adapters/llm/`, which owns provider selection, batching, prompt caching, schema enforcement, and a **per-call cost row written in the same transaction as the result**. Cost accounting is not optional and not sampled. Extraction schemas are Pydantic models; structured output is enforced by the provider's constrained decoding, so no validate-and-retry loop is written by hand.
> - **Rule (fallback):** Fallback is **multi-model within one provider, not multi-vendor.** Primary `claude-haiku-4-5`, fallback `claude-sonnet-5` — same SDK, same prompt, same gateway. *(Order flipped and ratified 2026-09-06: the cheaper model owns the happy path, which roughly doubles event-volume headroom inside PRD §10.3's ceiling.)* On primary unavailability or schema-validation failure the gateway retries on the fallback model; after 2 consecutive failures it pauses the source and pages editorial. Callers never implement their own retry or fallback.
> - **Accepted risks of the Haiku-primary order, named:** (1) Haiku's confidence calibration may shift the `extraction_confidence` distribution downward, so the 0.5 / 0.7 gates are **tuning anchors until re-baselined against a labeled sample on the primary model** — a pre-launch task, not a budget; (2) date arithmetic for the AD-4 identity tuple and the ±30-day postponement rule is a known Haiku weakness, so those failures route to editorial review rather than auto-merge; (3) FR-29 dashboard curves are Haiku-shaped, and the runbook says so.
> - **Accepted risk, named:** a **provider-wide** outage delays ingestion; it degrades no user-facing surface. PRD §10.4's 4-hour ingestion SLA already absorbs this, which is why a second text-model vendor is not bought. *(Requires the FR-14 amendment — it is written as multi-provider.)*
> - **Rule (embeddings are a second vendor, unavoidably):** Anthropic publishes no embedding model and directs to **Voyage AI**. Embeddings therefore come from `voyage-4-lite`, behind the same gateway, with the same per-call cost row. Vectors are stored **quantized** — Voyage's `output_dtype` supports `int8` and `binary` (4× and 32× smaller), and Matryoshka dimensions allow truncating to 512 or 256. The embedding vendor is a **cost and storage** dependency, never an availability one: under AD-4 embeddings only route review candidates, so an embedding outage cannot stop ingestion or publishing.
> - **Rule (confidence gate):** `extraction_confidence` <0.5 auto-rejects; <0.7 routes to editorial and is never published to a Pulse Digest. The threshold lives in one shared module.

#### AD-9 — Source content is untrusted input `[ADOPTED]` (line 134)

> - **Binds:** FR-13–17, FR-21–25; PRD §11.2
> - **Prevents:** sandboxing being satisfied for the crawler but not for the LLM path, where prompt injection from a scraped page is the live risk.
> - **Rule:** Ingested content is never executed, never rendered as raw HTML, and never interpolated into a prompt without explicit delimiting. Extraction output is schema-constrained at decode time. Every derived record carries its `source_id` and a confidence score. A source can never cause a write outside `catalog`.

#### AD-10 — Explanations are persisted with the decision, and there are two kinds `[ADOPTED]` (line 140)

> - **Binds:** FR-21–25, FR-59
> - **Prevents:** the explanation drifting from the decision it explains — the trust-collapse failure PRD Risk 11 calls company-ending — and three surfaces computing three different answers to "why this?".
> - **Rule (two kinds, one discipline):** Explanations come in two kinds, and **both are persisted, neither is ever recomputed at render**:
>
> | Kind | Computed | Persisted on | Serves | Owner |
> | --- | --- | --- | --- | --- |
> | **Event Fit** `[NEW NOUN]` — non-personalized score + generic tags | per `(event, city)`, on ingest/refresh | `catalog` rollup | SEO pages, Pulse Preview — **anonymous, no session, cacheable** | `ingestion` |
> | **Relevance Pulse** `[NEW NOUN]` — per-user score + per-user Why-this Tags | at digest composition | `DIGEST_COMPOSITION` (`personal`) | card, Detail Screen, email | `personalization` |
>
> - **Why both exist:** the SEO landing page and Pulse Preview must show tags and a 1–5 indicator to a visitor with **no account** (PRD §UJ, UX `EXPERIENCE.md` UJ-3) — there is no user for a personal explanation to be *about*. AD-12 forbids that surface depending on a session, so a personal explanation cannot serve it. Event Fit is the session-free kind that can.
> - **Rule (never cross them):** an authenticated surface never falls back to Event Fit to fill a missing Relevance Pulse, and a public surface never reads `personal`. Two indicators that look identical must never be silently substituted for one another — that is the trust-collapse failure PRD Risk 11 calls company-ending.
> - **Rule:** Source Badge inputs follow the same discipline. A Pulse Card is a **projection**, not an entity (PRD §3) — the persisted record is the composition, and the card is derived from it.
> - **Rule (durability):** A `DIGEST_COMPOSITION` row is immutable and retained per AD-15. The Detail Screen (FR-24) is reachable for an Event that is not in today's digest; it reads the **most recent composition** for that `(user, event)` pair, and renders no explanation rather than recomputing one if none exists. An explanation is never generated at view time.

#### AD-11 — No long work inside a request `[ADOPTED]` (line 156)

> - **Binds:** all
> - **Prevents:** discovering Vercel's 800s Pro ceiling (300s on Hobby) in production, and protecting the read-path latency budget.
> - **Rule:** No request handler performs crawl, extraction, embedding, or bulk send. Such work is enqueued and executed in the worker runtime. A request handler's job is to validate, enqueue, and return.

#### AD-12 — The public surface never depends on a session `[ADOPTED]` (line 162) ★ **MOST RELEVANT**

> - **Binds:** FR-26–28; PRD §10.4 (99.9% SEO uptime)
> - **Prevents:** the cold-start acquisition path — the mitigation for PRD Risk 4 — being coupled to auth availability, and personalization leaking into cacheable pages.
> - **Rule:** Public event pages render fully without a session and are statically generated or ISR'd. Personalized content on a public page arrives only via a separate client-side request. Schema.org `Event` JSON-LD is emitted from the same data the page renders.

#### AD-13 — No PII in logs, redacted at the logger `[ADOPTED]` (line 168)

> - **Binds:** all; PRD §11.2, §11.4
> - **Prevents:** compliance depending on every future author remembering — the failure mode of a convention.
> - **Rule:** Structured JSON logs only. Redaction is enforced by the logger adapter's allowlist, not by call-site discipline. Email addresses, OAuth tokens, and personal event content never reach a log sink. Trace context propagates across extraction, dedup, personalization, and delivery.

#### AD-14 — Internal actors are authenticated actors, never a privileged surface `[ADOPTED]` (line 174)

> - **Binds:** FR-29, FR-57, FR-59; PRD §10.5
> - **Prevents:** the editorial tool becoming a second writer to `catalog` and bypassing AD-4 — and an unauthorized-access hole in the one surface that can publish or reject events.
> - **Rule:** Editorial reviewers, AI Cost Dashboard viewers, and on-call operators are first-class authenticated actors with explicit role grants, modelled as `django.contrib.auth` groups and permissions. Django admin is the MVP surface for FR-57 and FR-29. The `editorial` app reads `catalog` and writes **through `ingestion` services** like any other client; it gets no privileged write path, no shared credential, and no unauthenticated route. Every editorial action (approve, reject, edit, merge) is attributed to an actor and appended to `state_history`. Admin write access is granted per-model, never as blanket superuser for routine review.

#### AD-15 — Retention is a property of the table, swept by a job `[ADOPTED]` (line 180)

> - **Binds:** PRD §10.2 (all seven retention categories), FR-52
> - **Prevents:** the 12-month preference-signal purge and the 90-day email-event window being implemented only for the tables one builder remembered.
> - **Rule:** Every model holding user-derived data declares its retention category in one registry (a class attribute checked by a Django system check); a scheduled worker job sweeps against that registry. A model without a declared category fails `manage.py check`, so it cannot ship. Deletion and export (FR-52) read the same registry, so a new model is covered by all three paths at once.

#### AD-16 — Write ownership is total, not just for `catalog` `[ADOPTED]` (line 186)

> - **Binds:** all
> - **Prevents:** AD-4's sole-writer discipline protecting only half the database. `REMINDER_PLAN` is the concrete case: `personalization` legitimately writes it for FR-20's default plan and `delivery` legitimately writes it for FR-9's per-event picker — both fully compliant with every other AD, each carrying different invariants, and the second to ship silently breaks the first.
> - **Rule:** Every entity in **either** schema has exactly one owning module, per the table below. Only the owner writes it; every other module reads through the owner's published interface. Adding an entity without an owner fails review.
> - **Rule (the contested one, settled):** `delivery` owns `REMINDER_PLAN`. `personalization` calls `delivery`'s published service to attach the default plan when it creates a `PERSONAL_EVENT` (FR-20). Chosen because PRD **SM-5 targets >80%** of saved cards getting a customized plan — plan edits are the frequent path, personal-event creation the rare one — so the boundary crossing sits on the rare path, and "edit the plan, reschedule its sends" stays inside the module AD-17 already makes the sole rewriter of `SCHEDULED_SEND`.
> - **Rule (the default is a constant, not state):** FR-9 and FR-20 both hardcode the default plan as **1d + 1hr**. It is one named constant in `shared/`, beside the confidence thresholds — never two literals that can drift apart.
>
> | Owner | Owns (writes) |
> | --- | --- |
> | `ingestion` | `SOURCE`, `EXTRACTED_RECORD`, `EVENT`, `EVENT_STATE_CHANGE`, `VENUE`, `REVIEW_ITEM`, `EVENT_FIT` |
> | `identity` | `USER`, `SUBSCRIPTION` |
> | `personalization` | `INTEREST`, `PREFERENCE_GRAPH`, `PERSONAL_EVENT`, `SAVED_EVENT`, `CONFLICT_PAIR`, `CALENDAR_CONNECTION`, `PULSE_DIGEST`, `DIGEST_COMPOSITION`, `EVENT_REPORT` |
> | `delivery` | `REMINDER_PLAN`, `SCHEDULED_SEND` |
> | `editorial` | nothing — acts only through `ingestion` commands (AD-14) |

#### AD-17 — Catalog state changes reach `personal` only by propagation `[ADOPTED]` (line 202) ★ **HIGHLY RELEVANT — the outbox pattern to copy**

> - **Binds:** FR-53–55, FR-9–12, FR-33
> - **Prevents:** the race the AD-3 wall makes invisible — a postponement rewriting an event's start time while the sweep is mid-dispatch on a reminder for the old time, sending a user a reminder for an event that moved. Also prevents `ingestion` reaching across the wall to fix it directly.
> - **Rule:** `ingestion` never writes to `personal`. A lifecycle change (postpone, cancel, move, sold-out, editorial time edit, supersede) appends an `EVENT_STATE_CHANGE` row carrying the Event's new, monotonically increasing `event_version`.
> - **Rule (outbox, so propagation cannot be lost):** The `EVENT_STATE_CHANGE` row is written with `propagated_at = NULL` in the **same `catalog` transaction** as the change. The propagation job is enqueued from `transaction.on_commit`, and a periodic reconciler on the beat tick re-enqueues any row still unpropagated after 5 minutes. A Redis loss or a crash between commit and enqueue therefore **delays** propagation; it never loses it.
> - **Rule (propagation is per-user, versioned, idempotent):** The job calls each owner's published service — **`delivery`** rewrites or cancels `SCHEDULED_SEND` rows, **`personalization`** updates the `SAVED_EVENT` snapshot and re-evaluates `CONFLICT_PAIR`s (AD-21). Each user is applied in one `personal` transaction, keyed `(state_change_id, user_id)`, and **only if** the change's `event_version` is greater than the version already stored on that user's `SAVED_EVENT` — so a retried, partial or out-of-order run can neither double-apply nor let an older postponement overwrite a newer cancellation. `propagated_at` is set through an `ingestion` command once every affected user is done.
> - **Rule (what each change does):** time moved → bump the snapshot, cancel `pending` sends, mint new ones (AD-7 send key), queue an FR-54 notice. Cancelled, rejected, or superseded (AD-4 >±30 days) → cancel `pending` sends, close conflicts, queue a notice. Sold-out or venue detail → re-stamp the version, keep sends, queue a notice.
> - **Rule (the sweep never crosses the wall in a transaction):** AD-3 forbids a transaction spanning `catalog` and `personal`, so the claim transaction is **`personal`-only**. Every event-bound `SCHEDULED_SEND` carries the `event_version` it was scheduled against. After claiming a row, the sweep reads the Event's current `event_version` through `ingestion`'s read interface — a separate, non-transactional read. If the catalog version is newer, the row goes to `held_for_propagation` and is not sent; propagation then releases, rewrites or cancels it.
> - **Accepted cost:** a change that commits between that version read and the provider call can still send one reminder for the old time. The window is seconds wide, and the FR-54 notice from propagation corrects it. Closing it fully would need the cross-schema transaction AD-3 rules out.

#### AD-18 — Calendar access is a port, and every credential is a credential `[ADOPTED]` (line 213)

> - **Binds:** FR-3, FR-50; PRD §11.2
> - **Prevents:** the MVP's ICS import bleeding into `personalization` and `delivery`, so that adding OAuth later becomes a cross-module change — and prevents a secret ICS URL being treated as a config string when Google classifies it as a credential and offers a reset for it.
> - **Rule:** All calendar ingestion sits behind one port. MVP ships a single **ICS/webcal adapter** used uniformly for Google, Apple and Outlook; OAuth and CalDAV adapters may be added behind the same port without touching any caller. Every provider credential — secret ICS URL or OAuth refresh token alike — is encrypted at rest with the application-level key, never logged, and revocable by the user.
> - **Rule (identity is not calendar):** "Continue with Google / Apple / Microsoft" on `/signup` and `/signin` is **sign-in only**: OpenID Connect with `openid email profile` scopes, owned by `identity`. It never requests a calendar scope and never creates a calendar connection — calendar connect is the separate ICS step. Email + password, with single-use, short-lived reset tokens and enumeration-safe responses at the API edge, is the other MVP sign-in method. *(PRD FR-3/FR-50 aligned to this AD by PRD Amendment A-9.)*
> - **Rule (connections are entities):** Each connected calendar is one `CALENDAR_CONNECTION` row (`personal`, owned by `personalization`) holding the encrypted credential. Every imported `PERSONAL_EVENT` references its connection, so a disconnect purges exactly that connection's events (FR-50: within 24 hours).
> - **Rule (freshness):** The poll interval is ours to choose, since we are the HTTP client; imported events carry a `fetched_at` and conflict detection (FR-58) never asserts freshness it cannot evidence.

#### AD-19 — The API contract is generated, never hand-written `[ADOPTED]` (line 222) ★ **THE API-CONTRACT BOUNDARY**

> - **Binds:** all frontend↔backend traffic
> - **Prevents:** the divergence the separate-frontend decision created — two sides of one boundary drifting because each hand-maintains its own view of the payload. This invariant did not exist while the stack was one language with shared types.
> - **Rule:** The OpenAPI schema Django Ninja emits is the **single source of truth** for the boundary. The frontend's TypeScript client is generated from it in CI and is never edited by hand; a schema change that breaks the client fails the build. Request and response shapes are Pydantic schemas in `apps/*/schemas.py` — never ad-hoc dicts. No endpoint exists that is absent from the schema.

> **Note on the phrasing in the prompt:** the prompt attributes "the frontend is a client — it holds no domain logic and reaches the backend only through the generated API client" to AD-19. That sentence is **verbatim in AD-1** (`ARCHITECTURE-SPINE.md:63`), not AD-19. AD-19's rule is the generated-contract sentence quoted above. Both bind this feature.

#### AD-20 — Transactional and bulk mail never share a stream `[ADOPTED]` (line 228)

> - **Binds:** FR-9–12, FR-5–8; PRD §10.1
> - **Prevents:** `delivery` sends both reminders and the Pulse Digest through one adapter. Without a required stream argument, the second sender to ship silently inherits whatever default the first picked — and then one digest spam complaint degrades the deliverability of the reminders users explicitly asked for.
> - **Rule:** Every send through the email port carries an explicit **stream**. Transactional mail (reminders, state-change notices, auth) and bulk mail (the Pulse Digest) use **separate sending streams and separate reputations**. A send with no stream is a type error, not a default.
> - **Rule (RFC 8058):** Bulk sends carry `List-Unsubscribe` and `List-Unsubscribe-Post: List-Unsubscribe=One-Click`, with a POST endpoint that returns 200/202 and stops mail within 48 hours. Both candidate providers support this — Postmark attaches the headers automatically on its Broadcast stream, Resend takes them as custom headers — so it constrains the **port**, not the vendor.

#### AD-21 — Timeline and conflicts read personal-side snapshots, never `catalog` joins `[ADOPTED]` (line 280)

> - **Binds:** FR-32, FR-33, FR-58, FR-53–55; PRD Amendment A-8
> - **Prevents:** the Pulse Card, the Timeline and `/conflicts` each computing "does this overlap?" their own way across the AD-3 wall — so the PRD's symmetric conflict indicator disagrees between surfaces, and a cancelled event keeps its conflict marker.
> - **Rule (saves are personal records):** A user's save of a public Event is a `SAVED_EVENT` row in `personal`, owned by `personalization`. It holds `event_id` by value (no FK) plus a snapshot — `start_utc`, `end_utc`, `event_version` — taken from `catalog` at save time and **thereafter updated only by AD-17 propagation**. A save re-reads the Event's version after commit and requests re-propagation for that user if it moved meanwhile, so a save racing a postponement cannot keep a stale snapshot. The Timeline and conflict detection read the snapshot; they never join `catalog`.
> - **Rule (one overlap function):** Conflict detection is one pure function in `domain/conflict.py`: two UTC intervals conflict when they overlap by **strictly more than 15 minutes** (FR-33). It runs on save, on Personal Event create, edit or import, and on AD-17 propagation — **never at render**. Public-vs-public pairs are out of scope at MVP.
> - **Rule (conflicts are persisted pairs):** Each detected conflict is one `CONFLICT_PAIR` row (`personal`, owned by `personalization`) linking two sides (each a `SAVED_EVENT` or a `PERSONAL_EVENT`), with status `active` or `resolved`. A user's choice is recorded on the pair as the Glossary's `ConflictResolution`. A resolved pair is immutable and never re-prompted. When propagation removes the overlap (a cancel, or a postpone past the partner), the pair closes as `cleared_by_state_change`, which is not a user resolution. The Pulse Card indicator, the Timeline event-block indicator and `/conflicts` all read the same rows, so the indicator is symmetric by construction.
> - **Rule (Timeline is a query):** `/timeline` is a read-only `personalization` query over `SAVED_EVENT` and `PERSONAL_EVENT` for one week in the user's timezone. It performs no writes. Display fields for public Events (title, venue) are fetched from `catalog` through `ingestion`'s read interface and combined in the application layer (AD-3).

### Consistency Conventions (lines 289-313) — the rows that bear on this feature

| Concern | Convention (exact) |
|---|---|
| Naming — entities | "**PRD §3 Glossary terms verbatim**: `Event`, `Source`, `PulseDigest`, `ReminderPlan`, `PersonalEvent`, `PreferenceGraph`, `EventReport`, `ConflictResolution`, `SourceReliabilityScore`. A Pulse Card is a projection, never a table." |
| Naming — files | "Backend `snake_case.py`, one concept per module; services as verbs (`compose_digest.py`), queries as `get_`/`list_`. Frontend `kebab-case.ts`." |
| Naming — new nouns | "`ExtractedRecord` **[NEW NOUN]** …, `ScheduledSend` **[NEW NOUN]** …, `SavedEvent` **[NEW NOUN]** …, `ConflictPair` **[NEW NOUN]** … and `CalendarConnection` **[NEW NOUN]** … must be added to PRD §3 before build." |
| UI system | "**None — binding** (EXPERIENCE.md §1, DESIGN.md Token Implementation Contract). No Material, no shadcn, no component kit. Vanilla components over the CSS-custom-property token layer; `<dialog>` for modals and sheets; hand-rolled tooltip per the DESIGN.md pattern." |
| Ids | "UUIDv7 primary keys (time-sortable). **Public event URLs use a separate slug, never the primary key.**" |
| Dates | "`timestamptz` in UTC at rest; ISO-8601 with offset on the wire; IANA tz names, never fixed offsets." |
| Errors | "Domain errors are explicit exception types defined in `domain/`, never bare `Exception`. HTTP mapping happens once, in a Django Ninja exception handler — never per-endpoint." |
| Error shape | "`{ code, message, details? }` — `code` is a stable machine-readable slug; `message` follows the UX spine's voice: calm, no urgency language, no emoji." |
| State mutation | "Named application commands only (AD-5). Audit-log write in the same transaction as the mutation." |
| Config | "Validated once at startup into a typed settings object (pydantic-settings); **no `os.environ` reads below `config/`**." |
| Auth | "Authentication resolved at the API edge; services receive an explicit actor argument, never a `request`. Internal roles are `django.contrib.auth` groups and permissions (AD-14)." |
| Rate limiting | "Per-IP and per-user at the surface edge (PRD §11.2). `EventReport` is capped at 5/user/day (FR-59); free-tier saves at 1 per 24h (FR-48). Limits are declared, not hand-rolled per route." |
| Feature flags | "Server-evaluated, defaulting to off. Phase 2/3 features ship behind a flag or not at all." |
| Tests | "`domain/` unit-tested with no database and no Django. `import-linter` contracts enforce AD-2 in CI. `manage.py check` enforces AD-15. `axe-core` gates the frontend surfaces named in PRD §11.5 at zero serious/critical violations." |

### Structural Seed — Deployment (lines 355-375), the rows that bear on this feature

| Concern | Seed (exact) |
|---|---|
| Frontend | "Vercel — Next.js 16 `cacheComponents` + `partialPrefetching` is what makes tens of thousands of ISR'd event pages viable. **Hobby while building; Pro is mandatory at launch** (see the launch gate below)" |
| API runtime | "An always-on Python host (~$5/mo, e.g. Railway Hobby). Free Python hosts sleep — Render's free web service idles out at 15 min with a ~1 min cold start, which an API cannot wear" |
| Worker runtime | "Celery worker + beat. Phase 0: run locally — the sweep needs no always-on host before there are users. Phase 1: a second always-on process, no execution limit" |
| Broker | "Managed Redis (~$5–10/mo). Carries the tick and pipeline jobs only — never the reminder schedule (AD-7), so losing it never loses a reminder" |
| Database | "Neon PG18 — ships pgvector 0.8.6, above the 0.8.4 line that fixed HNSW vacuum corruption; the managed alternatives checked (Supabase, RDS) lag at 0.8.2. Free tier carries Phase 0" |
| Environments | "`local` → `preview` (per-PR, Neon branch) → `production`. Preview never sends real email and never writes to the real Source Registry." |
| Secrets | "**Platform secret store only.** Every calendar credential — the secret ICS/webcal address at MVP, OAuth refresh tokens and CalDAV passwords after the fast-follow — encrypted at rest with a separate application-level key (AD-18)." |
| Operations | "Status page updated within 30 min of a SEV-1; `runbook.md` lives in the repo and is the on-call first stop (PRD §10.5)." |
| Launch gate — hard | "The Vercel plan must be on **Pro before the Pro tier's Stripe checkout is enabled**. Hobby is non-commercial only… This belongs on the pre-launch checklist beside the DPIA (§10.1) and the accessibility audit (§11.5)." |
| Not a platform-cron fallback | "Vercel Hobby cron runs once per day at ±59 min precision, and even Pro cron is per-minute — AD-7's tick lives in Celery Beat for this reason, on every plan." |

**⭐ Note:** the structural seed names `cacheComponents` and `partialPrefetching` as the ISR mechanism — **neither is configured** in `frontend/next.config.ts` (which is empty). This is a gap the revalidation feature will likely have to close.

### The spine's own deployment diagram (lines 377-389)

```
graph TD
    U["browser"] --> V["Vercel<br/>Next.js frontend"]
    V -->|OpenAPI| API["Django Ninja<br/>API runtime"]
    API --> N[("Neon PG18<br/>pgvector 0.8.6")]
    WK["worker runtime<br/>sweep · pipeline"] --> N
    WK --> LLM["Anthropic + Voyage<br/>via one gateway"]
    WK --> ESP["email provider<br/>OQ-4"]
    WK --> SRC["event sources<br/>partnership · API · RSS/ICS · crawl"]
    WK --> CAL["ICS / webcal feeds<br/>Google · Apple · Outlook"]
    API --> STR["Stripe"]
    ESP --> U
```

**There is no arrow from the API/worker to the frontend.** The revalidation signal adds the first.

### Open Questions (lines 481-493) — the two that touch this feature

| # | Question |
|---|---|
| OQ-6 | "`ExtractedRecord`, `ScheduledSend`, `SavedEvent`, `ConflictPair`, `CalendarConnection`, **`EventFit`** and **`RelevancePulse`** are new nouns this spine needs. PRD §3 requires new nouns to land in the Glossary in the same pass." |
| OQ-8 | "**Consequence of AD-3 found by the schema-router spike (2026-10-27).** `User` and `ContentType` live in `personal`, and no relation may cross aliases (enforced by system check `eventpulse.E002`). So no `catalog` model can FK to `User` or `ContentType`: no `GenericForeignKey` on catalog models, and AD-5's "audit-log write in the same transaction as the mutation" needs **one audit table per schema**, with the actor stored by id and no FK." |

---

## 8. The intent brief

**Path:** `.specs-fire/intents/public-pages-and-seo/brief.md` (97 lines).

**Frontmatter (lines 1-6):**
```yaml
id: public-pages-and-seo
title: Public Pages, SEO & Share Links
status: in_progress
created: 2026-11-01
```

### 8.1 Goal (lines 10-16) — exact

> "Give EventPulse24 a **front door**. Every six intents so far have served people who were already inside — onboarding assumed someone arrived, the digest assumed an account, delivery assumed an address to write to. Nothing in this repository has ever been reachable by a stranger. `frontend/app/` holds ten routes and every one of them sits behind auth, onboarding, or a dev flag.
>
> This intent builds the surface that brings people in: a crawlable public page for every published Event carrying Schema.org `Event` JSON-LD, an "Events in [city]" landing page for every real city, a sitemap, and a share link a user can hand to a friend. It closes **FR-26** (public event pages with structured data), **FR-27** (SEO city pages) and **FR-28** (share-card public link), and it gives `EventFit` its first consumer.
>
> The PRD names the stake plainly (§4.8): *"Growth comes through SEO and shareability. SEO is the cold-start unlock."*"

### 8.2 Freshness requirements (lines 57-60) — exact ★ **THE CORE REQUIREMENT**

> "### Freshness
>
> - Revalidation is **triggered by the existing `event_version` bump**, not by a timer — the lifecycle guard trigger is the signal, and this intent gives it its first listener.
> - A cancelled or sold-out event's public page reflects that **without waiting for a cache window to lapse**."

### 8.3 The decision already taken (lines 74-83, "Decisions taken at intent capture")

> | Freshness | **On-demand revalidation on `event_version` bump** | `LIFECYCLE_FIELDS` + `guard_event_write` already emit the signal; a timer would leave a cancelled event showing as scheduled for the length of the window. |

### 8.4 The problem statement that names the signal (lines 31) — exact

> "**Nothing can tell the frontend a page went stale.** `Event.LIFECYCLE_FIELDS` and the `catalog.guard_event_write` trigger already bump `event_version` on every change to `status`, `is_sold_out`, `venue` or the times — the signal exists and has no listener. A cached page showing "tickets available" for a cancelled show is a trust failure, and trust is this product's whole proposition."

### 8.5 OQ-C — the exact open question this feature answers (lines 89) ★

> "**OQ-C — How does the backend reach the frontend to revalidate?** This is a new outbound direction — until now the frontend has been a pure client of the API (AD-19). The call path, its shared secret, and its failure behaviour need deciding; **a missed revalidation must degrade to stale-but-correct, never to a wrong page.**"

### 8.6 Other constraints (lines 62-70) — exact

> - "**AD-12 — the public surface never depends on a session.** Pages render fully without one; any personalized content arrives only via a separate client-side request. Binds all three FRs."
> - "**AD-19 — the API contract is generated, never hand-written.** The frontend reaches the backend only through the generated client; `frontend/lib/api/` is never hand-edited."
> - "**AD-10 — Event Fit is served as stored.** Never recomputed at render; a stale row (mismatched `event_version`) is never served."
> - "**AD-16 — module ownership.** The City model gets exactly one owning module, and no second write path."
> - "**ASSUMPTION-9** (PRD §4.7) — public event pages are **not user-generated content**; they reflect the registry's source of truth only. No reviews, no UGC, on either page type."
> - "**PRD §10.4** — 99.9% SEO uptime is the standard these pages are held to."
> - "**Out of scope by PRD:** per-event Open Graph tuned for SEO (Phase 2), UGC reviews on public pages, user-generated content on city pages, paid placements."

### 8.7 Success criteria that constrain the page (lines 35-42, 44-49)

- "A session-free page at **`/events/{slug}`** for every `published` Event, statically generated or ISR'd per **AD-12**, rendering fully with no account and setting no session."
- "Served by a **new public read keyed on `slug`**, separate from `catalog.get_event`'s UUID+not-yet-started rule. **A past event still resolves** — its page stays up and indexed."
- "Valid Schema.org `Event` JSON-LD **emitted from the same data the page renders** (AD-12)…"
- "Because `mint_slug` (`services/slugs.py`) mints once at creation and **never re-mints on retitle**, a public URL is permanent by construction. Nothing in this intent may introduce a path that rewrites a slug."

### 8.8 The route-collision decision (line 80) — affects where the public page lives

> "| Route collision | One `app/events/[id]/` route, branching on UUIDv7-vs-slug | Next.js rejects two different dynamic slug names at one level. Branching keeps `/events/{id}` and `/events/{id}/reminders` and every internal link into the detail screen unchanged. |"

**This matters for revalidation:** `revalidatePath` targets a **path**, and `/events/{slug}` and `/events/{uuid}` share one route segment. A path-based revalidation of `/events/{slug}` must be targeted precisely.

### 8.9 Mockups (lines 92-96)

> - "`public-event-page-desktop.html` — self-tagged `FR-26`, contains real `application/ld+json`"
> - "`city-page-desktop.html` — self-tagged `FR-27`, includes the "coming soon" sparse state"
> - "`share-link-desktop.html` — tagged `UJ-5`, covers the **recipient** landing only (see OQ-B)"

---

## 9. Prior art — the whole repo

Search terms: `webhook`, `notify`, `revalidate`, `isr`, `on-demand`, `FRONTEND_URL`, `NEXT_PUBLIC`.

### 9.1 The backend ALREADY has a public-page read surface (built in run 024)

These are the strongest prior art — the backend half of the public-pages intent is already done.

**`backend/apps/catalog/api.py`** (193 lines) — 4 endpoints, all session-free:

| Endpoint | Line | Function | Response |
| --- | --- | --- | --- |
| `GET /api/catalog/events` | 82-109 | `list_events(request, filters: EventPage)` | `EventListOut` |
| `GET /api/catalog/events/{event_id}` | 112-124 | `get_event(request, event_id: UUID)` | `EventOut` / 404 `ErrorOut` |
| `GET /api/catalog/events/by-slug/{slug}` | 127-155 | `get_event_page(request, response: HttpResponse, slug: str)` | `PublicEventPageOut` / 404 |
| `GET /api/catalog/cities/by-slug/{slug}` | 158-193 | `get_city(request, response: HttpResponse, slug: str, params: CityPageQuery)` | `CityPageOut` / 404 |

**The cacheability helper** — `backend/apps/catalog/api.py:64-79`:

```python
def _cacheable(response: HttpResponse) -> HttpResponse:
    """Mark a response as a public, cacheable, per-URL response.

    **`Vary` carries nothing session-related.** A response that varies on the cookie is
    not cacheable, and — worse — a shared cache that stores one variant under a key that
    ignores the cookie would serve one visitor's response to another. The public page sets
    no cookie and reads no session, so the response is identical for everyone and the
    cache key is the URL.
    ...
    """
    response["Cache-Control"] = PUBLIC_PAGE_CACHE_CONTROL
    response["Vary"] = PUBLIC_PAGE_VARY
    return response
```

**The constants** — `backend/shared/constants.py:807` and `:815`:
```python
PUBLIC_PAGE_CACHE_CONTROL = "public, max-age=3600, s-maxage=3600, stale-while-revalidate=86400"
PUBLIC_PAGE_VARY = "Accept-Encoding"
```

### 9.2 `event_version` — the signal itself, already plumbed to the wire

**`backend/apps/ingestion/models.py:243-251`** — the fields that bump the version:

```python
    # Mirrors the trigger in migration 0001: a change to any of these needs a version bump.
    LIFECYCLE_FIELDS: ClassVar[tuple[str, ...]] = (
        "start_time_utc",
        "end_time_utc",
        "start_time_tz",
        "status",
        "is_sold_out",
        "venue",
        "superseded_by",
    )
```

`backend/apps/ingestion/models.py:286` — `event_version = models.PositiveIntegerField(default=1)`

`backend/apps/ingestion/models.py:228-229` (Event docstring):
> "The `catalog.guard_event_write` trigger makes `superseded` terminal and requires `event_version + 1` with every lifecycle-column change (LIFECYCLE_FIELDS)."

**`backend/apps/catalog/schemas.py:100-101`** — the explicit statement that the payload exists *for this feature*:
> "**`event_version` is here because the revalidation work item needs it** to prove a cached page is current."

**`backend/apps/ingestion/services/catalog_read.py:544-548`** — the DTO docstring:
> "**`event_version` is the Event's own counter**, read from the row and never re-derived. The `catalog.guard_event_write` trigger bumps it on every lifecycle change, and the revalidation work item compares it against a cached copy to decide whether a page is current. A re-derived number would not be the number the trigger wrote."

**`frontend/lib/api/openapi.json:2403`** and **`frontend/lib/api/schema.ts:2285`** carry the same text into the generated client:
> "**`event_version` is here because the revalidation work item needs it** to prove a cached page is current."

### 9.3 The outbox pattern to copy — `backend/apps/ingestion/services/outbox.py` (57 lines, full)

```python
"""The AD-17 outbox: enqueue propagation for committed state changes, and the reconciler that
re-enqueues the ones nobody has propagated.

`ingestion` can't import `worker` or `config` (layers), so jobs are sent by task name through
the Celery app `config/__init__` loads. `_send` is the single seam; tests replace it.
"""

from datetime import datetime
from uuid import UUID

from celery import current_app
from django.utils import timezone

from apps.ingestion.models import EventStateChange
from shared.constants import OUTBOX_RECONCILE_AFTER, OUTBOX_RECONCILE_BATCH
from shared.db import CATALOG

PROPAGATE_TASK = "worker.tasks.propagate_state_change"


def _send(task_name: str, args: list[str]) -> None:
    current_app.send_task(task_name, args=args)


def enqueue_propagation(state_change_id: UUID) -> None:
    """Queue one state change for propagation. Run it from `on_commit(using=CATALOG)` only."""
    _send(PROPAGATE_TASK, [str(state_change_id)])


def mark_propagated(state_change_id: UUID, *, now: datetime | None = None) -> bool:
    """Record that a state change reached `personal` (design D23). False if it already has.

    The conditional form is idempotent under the job's retries and the reconciler.
    """
    updated = (
        EventStateChange.objects.using(CATALOG)
        .filter(pk=state_change_id, propagated_at__isnull=True)
        .update(propagated_at=now or timezone.now())
    )
    return updated == 1


def reconcile_outbox(*, now: datetime | None = None, limit: int = OUTBOX_RECONCILE_BATCH) -> int:
    """Re-enqueue the oldest state changes unpropagated for longer than
    `OUTBOX_RECONCILE_AFTER`, at most `limit` of them. Returns how many were enqueued.
    """
    cutoff = (now or timezone.now()) - OUTBOX_RECONCILE_AFTER
    ids = list(
        EventStateChange.objects.using(CATALOG)
        .filter(propagated_at__isnull=True, occurred_at__lt=cutoff)
        .order_by("occurred_at", "id")
        .values_list("id", flat=True)[:limit]
    )
    for state_change_id in ids:
        enqueue_propagation(state_change_id)
    return len(ids)
```

**This is the template for a revalidation outbox**: `on_commit` → task name → `_send` seam (tests replace it) → idempotent conditional update → reconciler on the beat tick.

### 9.4 The worker tasks — the existing seam

`backend/worker/tasks.py` — all task names (each a `@shared_task(name="worker.tasks.<x>")`):

| Line | Task name |
| --- | --- |
| 44 | `worker.tasks.tick` |
| 86 | `worker.tasks.refresh_event_fits` |
| 110 | `worker.tasks.schedule_sources` |
| 132 | `worker.tasks.ingest_source` |
| **154** | **`worker.tasks.propagate_state_change`** ← the AD-17 consumer slot |
| 165 | `worker.tasks.schedule_calendars` |
| 194 | `worker.tasks.sync_calendar` |
| 231 | `worker.tasks.reconcile_outbox` |
| 238 | `worker.tasks.schedule_digests` |
| 272 | `worker.tasks.compose_digest` |
| 344 | `worker.tasks.sweep_due_sends` |

`backend/worker/tasks.py:154-162` — **the existing consumer is a deliberate placeholder**:

```python
@shared_task(name="worker.tasks.propagate_state_change")
def propagate_state_change(state_change_id: str) -> None:
    """AD-17 placeholder consumer: no propagation into `personal` exists yet (FR-53-55).

    It deliberately leaves `propagated_at` NULL: marking the row would claim a propagation that
    never happened, and the real consumer would then skip it. The reconciler keeps re-offering
    it until that consumer arrives.
    """
    logger.debug("State change not propagated yet", extra={"state_change_id": state_change_id})
```

`backend/worker/tasks.py:147-153` — why:
> "The `delivery` half of AD-17 already exists and is tested: `apps.delivery.services.scheduled_sends.apply_lifecycle_change`. It is deliberately NOT called from here yet — `propagated_at` may only be set once *every* owner has applied a change, and the `personalization` half (SAVED_EVENT snapshot + conflict re-evaluation) is FR-53/54 work. … Decided with the user 2026-10-31; see the delivery-and-reminders brief and `send-minting-and-rescheduling-design.md` D8."

**⚠️ This is the single most important structural finding for the design:** there is **exactly one** existing consumer task for `EVENT_STATE_CHANGE`, and it is reserved for the `personal`-side propagation (AD-17). The revalidation signal is a **different** consumer of the same outbox row — it is not `personal` propagation, so **it must not mark `propagated_at`** and **must not be folded into `propagate_state_change`**. It needs its own task (e.g. `worker.tasks.revalidate_public_page`) and its own idempotency marker, or it reuses the same row with a separate "revalidation done" marker.

### 9.5 The run-024 plan already anticipates this feature

`.specs-fire/runs/run-eventpulse24-024/plan.md:95`:
> "**`event_version` is in the payload** because the revalidation work item needs it to prove a cached page is current. The signal already exists (`Event.LIFECYCLE_FIELDS` + `catalog.guard_event_write`); this is its first reader."

`.specs-fire/runs/run-eventpulse24-024/plan.md:153`:
> "**`event_version` is read from the row, never computed.** It is the Event's own counter, bumped by the `catalog.guard_event_write` trigger on every lifecycle change. The revalidation work item compares it against a cached copy to decide whether a page is current — so it must be the *same* number the trigger wrote, not a re-derived one."

### 9.6 `webhook` / `notify` — no prior art

- `backend/apps/identity/services/sign_up.py:110` — `_notify_existing_holder(normalised)`; `:171` — the function definition. **Unrelated** to revalidation: it is about an email already in use during sign-up.
- No `webhook`, `callback_url`, `hook_url`, `notification_url` anywhere in `backend/` outside `.venv/`.
- `backend/adapters/email/` is the **only** existing outbound-HTTP-ish adapter family, and it goes through `ports/email.py`.

### 9.7 `FRONTEND_URL` / `NEXT_PUBLIC` — no prior art

- **Zero** hits for `FRONTEND_URL` in the entire repo.
- **Zero** hits for `NEXT_PUBLIC` in the entire repo.
- The frontend reads `API_BASE_URL` (server-only, no `NEXT_PUBLIC_` prefix), and the backend has `frontend_base_url` in `backend/config/env.py:36`.

**There is currently NO shared secret between the backend and the frontend.** A revalidation handshake secret would be entirely new.

### 9.8 The outbound-HTTP machinery available for the backend→frontend call

`backend/ports/` — 11 modules: `billing.py`, `calendar.py`, `email.py`, `embedding.py`, `fetch_policy.py`, `fetch.py`, `geo.py`, `__init__.py`, `llm.py`, `registry.py`, `throttle.py`.

`backend/ports/registry.py`:
```python
PORT_KEYS: dict[type, str] = { ... }   # line 23
def get_adapter[P](port: type[P]) -> P: ...   # line 35
def get_llm_port() -> LLMPort: ...      # line 51
def get_embedding_port() -> EmbeddingPort: ...  # line 55
def get_email_port() -> EmailPort: ...  # line 59
def get_billing_port() -> BillingPort: ...  # line 63
def get_calendar_port() -> CalendarPort: ...  # line 67
def get_fetch_port() -> SourceFetchPort: ...  # line 71
def get_geo_port() -> GeoPort: ...  # line 75
def get_throttle_port() -> ThrottlePort: ...  # line 79
```

`backend/adapters/` — 9 families: `billing`, `calendar`, `crawl`, `email`, `geo`, `llm`, `logging`, `throttle`.

**⚠️ Constraint:** `tech-stack.md:128` — *"`httpx` 0.28.1 … HTTP framing and redirects for `adapters.crawl.http` **only** (import contract `http-client`)."* The `http-client` import contract means `httpx` may be imported **only** by `adapters.crawl.http`. A backend→frontend HTTP call needs either:
1. a **new port + adapter** (e.g. `ports/revalidation.py` + `adapters/revalidation/http.py`) with `httpx` — which would require **widening or duplicating the `http-client` import contract**, or
2. reuse of `ports/fetch.py` (`SourceFetchPort`) — but that port is scoped to *source* fetching (its settings are `source_fetch_*`: allowed ports `80, 443`, user agent `EventPulse24-SourceFetcher/0.1`, max bytes, timeouts), and `coding-standards.md:36` requires a new port to get a `PORT_KEYS` key **and an entry in every `config/adapters.py` table** (and `ADAPTER_MODE=real` fails startup until every port has a real adapter).

Per `coding-standards.md:33-36`, a new port is the sanctioned path; per `coding-standards.md:113` a *fake* adapter is used in tests (`ADAPTER_MODE=fake`).

### 9.9 What already exists for "the frontend deploy"

| Thing | Status |
|---|---|
| `frontend_base_url` in `backend/config/env.py:36` | **EXISTS** — default `http://localhost:3000`, used for the password-reset link. |
| `FRONTEND_URL` env var | Does not exist. |
| `NEXT_PUBLIC_*` | None anywhere. |
| Shared secret between deploys | **None.** |
| A Vercel deploy hook / `revalidate` URL | **None.** |
| `cacheComponents` / `partialPrefetching` in `next.config.ts` | **Not configured** (config is `{}`). |
| A Next route handler anywhere | **None.** |

---

## 10. Consolidated findings for the design

### 10.1 Facts that are certain (all with file:line)

1. `frontend/proxy.ts:28` — `export const config = { matcher: "/api/:path*" };` — **the matcher is exactly `/api/:path*`**, asserted at `frontend/proxy.test.ts:19`. **A revalidation endpoint must NOT live under `/api/`.**
2. `frontend/proxy.ts:25` — `NextResponse.rewrite(new URL(`${pathname}${search}`, base))` — anything under `/api/` is rewritten to Django, never reaching a Next handler.
3. **No route handlers exist.** No `app/api/`, no `route.ts` anywhere.
4. **No ISR machinery exists.** "revalidate" appears exactly once in `frontend/` — `frontend/app/preview/page.test.tsx:43`, a *negative* assertion.
5. `frontend/next.config.ts:3` — `const nextConfig: NextConfig = {};` — empty. No `cacheComponents`, no `revalidate`, no `rewrites`.
6. `frontend/package.json:20` — Next.js `16.3.8`. `:7` — `"node": ">=24.15"`. `:21` — `openapi-fetch` `0.17.0`.
7. **Node mismatch CONFIRMED**: active `v20.20.0`; required `>=24.15`; `v24.22.1` IS installed at `~/.nvm/versions/node/v24.22.1` — just not selected. `frontend/pnpm-workspace.yaml:4` — `engineStrict: true`.
8. The client is `openapi-fetch` via `frontend/lib/backend-client.ts:12-14`; `baseUrl` is `""` in the browser, `apiBaseUrl()` on the server.
9. **ESLint bans `fetch` in `app/`** (`frontend/eslint.config.mjs:18`) — so a route handler under `app/` cannot make a raw outbound `fetch`. `openapi-fetch` is importable **only** in `lib/backend-client.ts` (`frontend/eslint.config.mjs:29, 31-34`).
10. `backend/config/env.py:36` — `frontend_base_url: str = "http://localhost:3000"` — **the backend already knows the frontend's base URL.**
11. **No shared secret exists** between the backend and the frontend. No `FRONTEND_URL`, no `NEXT_PUBLIC_*`, no `REVALIDATE_*`.
12. `backend/apps/ingestion/models.py:243-251` — `LIFECYCLE_FIELDS` — the trigger already bumps `event_version` on `start_time_utc`, `end_time_utc`, `start_time_tz`, `status`, `is_sold_out`, `venue`, `superseded_by`.
13. `backend/apps/catalog/schemas.py:100-101` and `backend/apps/ingestion/services/catalog_read.py:544-548` — **`event_version` is already on the public-page wire payload specifically for this work item.**
14. `backend/apps/catalog/api.py:127-155` — `GET /api/catalog/events/by-slug/{slug}` — **the public event page read already exists**, session-free, with `Cache-Control` set.
15. `backend/shared/constants.py:807` — `PUBLIC_PAGE_CACHE_CONTROL = "public, max-age=3600, s-maxage=3600, stale-while-revalidate=86400"` — **a 1-hour cache window** the brief says on-demand revalidation must beat.
16. `backend/apps/ingestion/services/outbox.py` — the AD-17 outbox: `on_commit` → task name → `_send` seam → idempotent conditional update → reconciler. **The template.**
17. `backend/worker/tasks.py:154` — `worker.tasks.propagate_state_change` — **an existing consumer slot reserved for `personal` propagation; it deliberately leaves `propagated_at` NULL.** The revalidation signal must not occupy it.
18. `brief.md:89` — **OQ-C** — the exact open question: *"How does the backend reach the frontend to revalidate? … The call path, its shared secret, and its failure behaviour need deciding; a missed revalidation must degrade to stale-but-correct, never to a wrong page."*
19. `brief.md:81` — the decision is already made: **"On-demand revalidation on `event_version` bump"**, not a timer.
20. `brief.md:80` — the route-collision decision: **one `app/events/[id]/` route branching on UUIDv7-vs-slug.** `revalidatePath` is path-keyed, so the slug must be used precisely.
21. `ARCHITECTURE-SPINE.md:63` (AD-1) — *"The **Next.js frontend** is a client — it holds no domain logic and reaches the backend only through the generated API client (AD-19)."*
22. `ARCHITECTURE-SPINE.md:166` (AD-12) — *"Public event pages render fully without a session and are statically generated or ISR'd."*
23. `ARCHITECTURE-SPINE.md:160` (AD-11) — *"No request handler performs crawl, extraction, embedding, or bulk send. Such work is enqueued and executed in the worker runtime. A request handler's job is to validate, enqueue, and return."*
24. `ARCHITECTURE-SPINE.md:226` (AD-19) — the generated contract is the single source of truth; **"No endpoint exists that is absent from the schema."**
25. `tech-stack.md:128` — `httpx` is confined to `adapters.crawl.http` by the `http-client` import contract — **a new outbound HTTP direction needs a new port + adapter.**

### 10.2 The open design decisions this research surfaces (not yet decided anywhere)

| # | Decision | Where it must be settled |
|---|---|---|
| D1 | **Where the Next route handler lives.** Not under `/api/`. Candidate: `app/revalidate/route.ts` (or `app/internal/revalidate/route.ts`). | Design doc. |
| D2 | **How the backend reaches it.** New port + adapter (given the `http-client` contract), reusing `frontend_base_url`. | Design doc. |
| D3 | **The shared secret.** New env var (backend: pydantic-settings in `config/env.py`; frontend: `process.env.*` read server-side). Never logged (AD-13). | Design doc. |
| D4 | **Which task emits the signal.** `worker.tasks.propagate_state_change` is reserved for AD-17 `personal` propagation. A separate task (e.g. `worker.tasks.revalidate_public_page`) reading the same `EVENT_STATE_CHANGE` outbox row, with its own idempotency marker, is the likely answer. | Design doc. |
| D5 | **Failure behaviour.** `brief.md:89` — "a missed revalidation must degrade to stale-but-correct, never to a wrong page." The AD-17 outbox+reconciler pattern gives exactly this. | Design doc. |
| D6 | **Path vs tag.** `revalidatePath("/events/{slug}")` vs `revalidateTag(...)`. The spine's structural seed names `cacheComponents` + `partialPrefetching` — neither is configured yet. Also: the city page (`/events-in-{city-slug}`) depends on the event's city, so a single event change may need to revalidate two paths. | Design doc. |
| D7 | **Whether `next.config.ts` must gain `cacheComponents`** (spine structural seed) before ISR is usable. | Design doc. |
| D8 | **Whether the signal is version-scoped.** `event_version` is on the payload "to prove a cached page is current" — the handler could compare the incoming version against the cached page's version and skip a no-op revalidation. | Design doc. |
| D9 | **The `ETag`/`If-None-Match` angle** — the backend already sets `Cache-Control` on the public reads; a conditional revalidation call could reuse that. | Design doc (optional). |
| D10 | **Node version.** Must `nvm use 24` before `pnpm install`/`pnpm build`/`pnpm test`, or `engineStrict: true` fails. | Immediate, operational. |

### 10.3 What does NOT need deciding (already settled)

- The public event page read (`GET /api/catalog/events/by-slug/{slug}`) — **done**.
- The city page read (`GET /api/catalog/cities/by-slug/{slug}`) — **done**.
- The `event_version` signal on the wire — **done**.
- The `frontend_base_url` config — **done**.
- The outbox-with-reconciler pattern — **done** (AD-17, `outbox.py`).
- The route shape for the public page (`/events/[id]` branching slug-vs-UUID) — **decided** at `brief.md:80`.

---

*End of research. RESEARCH ONLY — no project file was modified other than this one.*
