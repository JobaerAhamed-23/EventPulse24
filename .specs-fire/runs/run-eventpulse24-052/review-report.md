---
run: run-eventpulse24-052
work_item: avatar-endpoint-and-contract
intent: account-profile-expansion
generated: 2026-11-19
status: reviewed
---

# Review Report: Uploading It

## Scope

| File | Change |
|---|---|
| `apps/identity/api.py` | three endpoints, `_avatar_url`, `me` and `put_profile` carry the field |
| `apps/identity/schemas.py` | `avatar_url` on `CurrentUserOut` and `ProfileOut` |
| `apps/identity/services/avatar.py` | `version_of` |
| `config/middleware.py` | `UploadSizeLimitMiddleware` |
| `config/settings.py` | `AVATAR_REDIRECT_MAX_AGE`, `AVATAR_MAX_REQUEST_BYTES`, middleware registration |
| `frontend/lib/avatar-upload.ts` | new — the multipart boundary the generated client cannot cross |
| `frontend/lib/api/*` | `make client` |
| 6 test files | the new suite, plus fixtures the new field touched |

## Checks

| Check | Result |
|---|---|
| Backend | 7544 passed, 0 failed, 0 skipped |
| Frontend | 2698 passed; `tsc --noEmit` 0 errors |
| `ruff` / `format` | clean (695 files) |
| `lint-imports` | 21 kept, 0 broken |
| `test_no_direct_writes.py` | green — handlers call commands only |
| Generated client hand-edited | no — `make client` only (AD-19) |
| Operation ids | read from the regenerated schema, not assumed |

## The checkpoint question, answered by a test rather than by me

At the checkpoint I flagged that the redirect is the first endpoint whose response is
consumed by the browser's image loader rather than typed client code, and proposed keeping
it on `/api/auth`.

**The project's own `endpoint-coverage` test then failed on exactly that**, because the
endpoint has no frontend caller. It is now in `DECLARED_UNCALLED` with the reason — which
is a better outcome than my handler comment alone, because the next person adding an
endpoint meets the rule rather than the prose.

## Findings

### 1. The redirect was broken in a supported mode — High, fixed

`BLOB_ADAPTER=memory` answered **400 Suspicious operation** for every user, because the
memory adapter mints `memory://…` and Django refuses to redirect outside http/https/ftp.
Found by a test failing, not by review.

Resolved by serving the bytes inline when the store cannot mint a fetchable URL. **The
redirect is an optimisation, not the contract** — a distinction worth stating, because the
acceptance criterion says "302s to a freshly presigned URL" and the honest reading is "for
a store that has one".

### 2. The CSRF ordering was untested — High, fixed

Deleting `require_csrf` from the upload handler left all twenty tests green. `current_user`
checks the token *after* resolving the caller, so every signed-in case is refused either
way; only an anonymous tokenless request distinguishes 403 from 401. The project already
had this exact test for `PUT /profile` and I did not carry it over.

**This is the second run in a row where a mutation probe found a guard that was not
load-bearing** (run 051: the format allow-list). Both were invisible to reading, because
every path ended in a refusal — just not for the reason the code claimed.

### 3. Nothing in Django caps a multipart file field — Medium, fixed

`DATA_UPLOAD_MAX_MEMORY_SIZE` governs the non-file part; files spool to disk past
`FILE_UPLOAD_MAX_MEMORY_SIZE`. A ten-gigabyte POST would be written to disk before any
project code had an opinion. `UploadSizeLimitMiddleware` refuses on the declared length
**before the body is parsed**, scoped to the one upload path.

**It treats `Content-Length` as a claim, not a fact**, and says so: a request that lies
still meets `read(cap + 1)` in the command. Two cheap checks, and the one that can be
trusted is the one that reads.

### 4. The generated client could not type a file upload — Medium, solved here

As the work item instructed, not deferred to the UI item. OpenAPI's `format: binary`
becomes `file: string`; `openapi-fetch` JSON-serialises by default. Both are absorbed in
`lib/avatar-upload.ts` — one cast, one `bodySerializer`, both explained — so the UI item
inherits `uploadAvatar(file)`.

**The generator was left alone deliberately.** A `transform` hook would mean driving
`openapi-typescript` from a Node script instead of the CLI, changing how `make client`
works project-wide to fix one field's type. The cast is smaller and confined.

## Judgment calls

| Decision | Why |
|---|---|
| `version_of` lives in the service, not `api.py` | A surface file owning a rule about key format is what `test_no_direct_writes.py` discourages. |
| The version is a **digest** of the key, not the key | The bucket is private so publishing the key would probably be harmless — but "probably harmless" is not a reason to put an object's address in every page's HTML. |
| `AVATAR_MAX_REQUEST_BYTES` > `AVATAR_MAX_BYTES` | The request also carries boundaries and headers; equal limits would refuse a legal maximum-size picture for its envelope. |
| Middleware registered last | After session and auth, so a refusal is of a request that was otherwise ready — and still before any view, which is the point. |
| Inline fallback keyed on the URL scheme | Not on the adapter class: the rule is "can a browser fetch this?", and asking the URL is asking the right question. |

## Findings Summary

| # | Finding | Severity | Status |
|---|---|---|---|
| 1 | Redirect → 400 in `BLOB_ADAPTER=memory` | **High** | **Fixed** |
| 2 | CSRF ordering not load-bearing in tests | **High** | **Fixed** |
| 3 | No cap on a multipart file field | Medium | **Fixed** |
| 4 | Generated client cannot type a file upload | Medium | **Solved here** |
| 5 | Redirect has no TypeScript caller | By design | **Declared** with its reason |

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-052*
