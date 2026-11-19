---
run: run-eventpulse24-052
work_item: avatar-endpoint-and-contract
intent: account-profile-expansion
generated: 2026-11-19
status: passed
---

# Test Report: Uploading It — a Multipart Endpoint on a Router With No Auth

## Summary

| Category | Passed | Failed | Skipped |
|----------|--------|--------|---------|
| Backend (full suite) | **7544** | 0 | 0 |
| `tests/identity/test_avatar_api.py` | 22 | 0 | 0 |
| Frontend | **2698** | 0 | 0 |
| `tsc --noEmit` | 0 errors | | |

`lint-imports`: 21 kept, 0 broken.

## Acceptance Criteria Validation

- ✅ `POST /api/auth/profile/avatar` accepts multipart and returns the updated profile
- ✅ `DELETE` clears it, and clearing nothing is a success
- ✅ `CurrentUserOut.avatar_url` is `""` when unset — not null, not absent
- ✅ `GET /profile/avatar/{version}` **302s** to a freshly presigned URL — tested against the **real store**, skipping when none is listening, as `tests/adapters/test_blob.py` does
- ✅ **`max-age` strictly less than the presign TTL, both read from the same settings** — `AVATAR_REDIRECT_MAX_AGE = BLOB_URL_TTL_SECONDS // 2`, derived so a changed TTL moves it
- ✅ Replacing changes the version, so the old URL is not reused
- ✅ **A stale version is refused, not served** — an old URL must not follow the account forward
- ✅ Another account's URL is refused — the version is checked against the *caller's* key
- ✅ Both write handlers call `require_csrf(request)` first — **and the ordering is now tested**, see below
- ✅ Anonymous → 401; no CSRF token → 403
- ✅ A refused upload is 422 in `{code, message, details}` with **no filename echoed** (AD-13)
- ✅ An over-sized upload is refused **before the body is parsed** — 413 from middleware
- ✅ Every status declared on the handler, so `ErrorOut` reaches the generated client
- ✅ Handlers call the named commands and touch no ORM — `test_no_direct_writes.py` green
- ✅ `make client` run; `openapi.json` and `schema.ts` both regenerated and committed (AD-19)
- ✅ `tests/api/test_contract.py` and `test_state_change_contract.py` green
- ✅ **Operation ids read out of the regenerated schema**, not assumed:
  `apps_identity_api_post_profile_avatar`, `…_delete_profile_avatar`, `…_get_profile_avatar`

## The multipart question the work item said to answer here

**It was all new.** Before this run: `multipart/form-data` appeared **0 times** in
`openapi.json`, `FormData` **0 times** in `frontend/`, `UploadedFile` **0 times** in
`backend/`.

**Django Ninja and the schema generator were fine.** The field emits as
`multipart/form-data` and `openapi-typescript` generates a request body type.

**The client could not express it, and that is solved here rather than in the UI item.**
OpenAPI's `format: binary` has no TypeScript equivalent, so the generated type is
`file: string` — a real `File` would not typecheck. There is no CLI flag to change it (the
generator's `transform` hook is Node-API only, and `make client` is the one sanctioned way
to produce `schema.ts` under AD-19). And `openapi-fetch` serialises bodies as JSON by
default, so a `FormData` body needs a pass-through `bodySerializer` — a hand-written
`Content-Type` would omit the multipart boundary and the server would fail to parse.

`frontend/lib/avatar-upload.ts` holds both, once, with the reasoning: one documented cast
and one serializer. `tsc --noEmit` is clean, so the UI item inherits `uploadAvatar(file)`
rather than an unknown.

## Two defects the probes found

### 1. The redirect answered 400 for every user in a supported mode

`BLOB_ADAPTER=memory` is documented as "run with no object store at all". The in-memory
adapter's `url_for` returns `memory://…`, and Django refuses to redirect to a scheme
outside http/https/ftp — so `HttpResponseRedirect` raised `DisallowedRedirect` and the
endpoint answered **400 Suspicious operation**. A broken feature reported as a security
event.

A store that cannot mint a fetchable address now has its bytes **served inline** instead.
The redirect is an optimisation for stores that can serve, not the contract; the contract
is "the caller's picture". Both paths are tested — the 302 against the real store, the
inline fallback against memory.

### 2. The CSRF ordering was untested on both writes

A mutation probe deleted `require_csrf` from the upload handler and **all 20 tests still
passed**. `current_user` checks the token too, but *after* resolving the caller — so
without the explicit call first, an anonymous tokenless request is answered 401 ("you are
not signed in") instead of 403 ("this could not be shown to come from this site"). Every
signed-in case is refused either way; **only the anonymous one can tell the two orders
apart**, and nothing tested it.

Two tests added, mirroring `test_the_csrf_check_runs_before_the_resolver` which the project
already has for `PUT /profile`. Re-probed: the mutation now fails.

## Mutation probes

| Mutation | Result |
|---|---|
| Stale version served (check removed) | **1 failed** |
| `require_csrf` removed from upload (before the new tests) | 20 passed ← **the gap** |
| `require_csrf` removed (after) | **1 failed** |
| `max-age` set equal to the presign TTL | **1 failed** |

## Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| Redirect → 400 in `BLOB_ADAPTER=memory` | **High** | **Fixed** — inline fallback, both paths tested |
| CSRF ordering untested on both writes | **High** | **Fixed** — two tests, mutation-confirmed |
| Generated client cannot type a file upload | Medium | **Solved here**, as the work item required — one confined cast in `lib/avatar-upload.ts` |
| Nothing caps a multipart file field in Django | Medium | **Fixed** — `UploadSizeLimitMiddleware` refuses on declared length before parsing; the command's `read(cap + 1)` remains the real guard |
| New required field broke 3 backend and 2 frontend fixtures | By design | **Updated** — these are deliberate exact-shape assertions |
| The redirect endpoint has no TypeScript caller | By design | **Declared** in `DECLARED_UNCALLED` with its reason — the consumer is an `<img>` tag |

## Ready for Completion

- [x] All tests passing — 7544 backend, 2698 frontend, 0 skipped, 0 type errors
- [x] Coverage target met — every guard mutation-probed
- [x] All acceptance criteria validated
- [x] No critical issues open

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-052*
