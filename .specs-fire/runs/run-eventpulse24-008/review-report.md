# Code Review Report

**Run**: run-eventpulse24-008
**Intent**: project-scaffold
**Reviewed**: 2026-10-27
**Files Reviewed**: 34 (17 created, 17 modified incl. docs and standards; generated `openapi.json` / `schema.ts` and the lockfile spot-checked)

---

## Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Code Quality | 0 | 0 | 1 |
| Security | 0 | 0 | 3 |
| Architecture | 0 | 0 | 0 |
| Testing | 0 | 0 | 0 |
| **Total** | **0** | **0** | **4** |

**Tests Status**: Passing (backend 438, frontend 51; lint, typecheck, format, contracts clean)

Ruff, `lint-imports`, ESLint (strict + the new AD-19 rules), `tsc` and Prettier were clean before review.

Already handled during execution, so not repeated here:
- the missing production-gate test
- the shutdown noise
- the deprecated tuple returns
- the Testing Library cleanup

---

## Files Reviewed

- Backend: `config/health.py`, `config/api.py`, `adapters/logging/redaction.py`, `tests/api/test_health.py`, `tests/api/test_contract.py`
- Frontend: `proxy.ts`, `lib/api-base-url.ts`, `lib/backend-client.ts`, `app/dev/health/{page,health-panel}.tsx` and tests, `proxy.test.ts`, `tests/lint-rules.test.ts`, `eslint.config.mjs`, `vitest.setup.ts`, `package.json`, `.prettierignore`, READMEs, generated `lib/api/*`
- Tooling and docs: `scripts/dev.sh`, `Makefile`, `.env.example`, `README.md`, `docs/setup/{macos,ubuntu}.md`, standards (4), `ci-pipeline.md`

---

## Skipped (recorded for later intents)

- **[Security] `/api/health` is unauthenticated and opens a connection to each database and Redis per call.** It names the components (`personal`, `catalog`, `redis`) and reason slugs, nothing more: no versions, hosts or exception text. That's fine locally. The deployment intent should decide whether production exposes it publicly, rate-limited (spine: limits at the surface edge), or as a dependency-free liveness probe instead.
- **[Security] Known disclosure: `x-middleware-rewrite` names the backend URL** on proxied responses (Next adds it). In production that's the API's public origin, so it isn't secret. Recorded in `proxy.ts` and the standards.
- **[Security] CSRF for the first unsafe request:** not exercised by this GET-only item. The hand-off is in coding-standards and system-architecture, with the headers Django actually receives through the proxy (recorded live).
- **[Code Quality] `django.server` access-log lines have `trace_id: null`.** `runserver`'s handler logs after the request context is gone, and its `request` attribute is a socket, not an `HttpRequest`. This predates this run (shared-foundations) and only affects the dev server's access log; application logs carry the id. Revisit if the production server's access log needs it.

---

## Notes

- **Alias rule:** `config/health.py` uses `connections[alias]` with the `shared.db` constants and `SCHEMA_FOR_ALIAS`, with no literals. The database-alias scan covers the new file (+1 case).
- **Layers:**
  - `config.health` imports `redis` (third party), `config.databases` and `shared.*`, so `config | worker` stays independent.
  - The import contracts still pass (12 kept).
- **Redaction:** `component` joins `ALLOWED_FIELDS` as a fixed slug. The health tests prove exception text (a password and an email) appears neither in the response nor in any log line.
- **The frontend fetch ban covers `app/` and `components/`.** `lib/` and `proxy.ts` aren't covered, because `proxy.ts` forwards rather than fetching, and `lib/backend-client.ts` is the sanctioned path. Widening it to `lib/` would need an exception for the client, which is what `no-restricted-imports` already expresses.
