---
run: run-eventpulse24-052
work_item: avatar-endpoint-and-contract
intent: account-profile-expansion
mode: confirm
checkpoint: plan
approved_at: 2026-11-19
---

# Implementation Plan: Uploading It — a Multipart Endpoint on a Router With No Auth

## Approach

Three endpoints on `/api/auth` (the router with **no** router-level `auth=`, so every
handler calls `require_csrf(request)` first and resolves the user itself), plus one field
on `CurrentUserOut`.

## The work item told me to check multipart rather than assume it. I checked.

**Multipart does not exist anywhere in this project yet:**

| Probe | Result |
|---|---|
| `multipart/form-data` in `frontend/lib/api/openapi.json` | **0 occurrences** |
| `FormData` anywhere in `frontend/` | **none** |
| `UploadedFile` / `ninja.File` in `backend/` | **none** |

So this is the first one, and three things have to be established rather than assumed:

1. **Django Ninja** expresses it as `file: UploadedFile = File(...)`, and emits
   `multipart/form-data` into the OpenAPI schema.
2. **`openapi-typescript`** generates the request body type from that media type.
3. **`openapi-fetch`** — the client in `lib/backend-client.ts` — sends JSON by default. A
   `FormData` body needs a per-request `bodySerializer` that returns the `FormData`
   untouched, so the browser sets the multipart boundary itself.

**Point 3 is the one that bites**, and the work item is explicit that if the generated
client cannot express a file upload, it is solved **here, not in the UI item**. The plan
therefore includes proving the upload end-to-end from a TypeScript caller shape, not just
from `pytest`.

## Files to Create

| File | Purpose |
|------|---------|
| `backend/tests/identity/test_avatar_api.py` | Upload, delete, read-back, redirect, auth, CSRF, refusals |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/apps/identity/api.py` | `POST`/`DELETE /profile/avatar`, `GET /profile/avatar/{version}` |
| `backend/apps/identity/schemas.py` | `CurrentUserOut.avatar_url`; the avatar fields on `ProfileOut` |
| `backend/apps/identity/services/avatar.py` | `avatar_url_for` / `version_of` — the version↔key rule, in the service, not the surface |
| `backend/config/settings.py` *(maybe)* | `AVATAR_REDIRECT_MAX_AGE`, derived from `BLOB_URL_TTL_SECONDS` |
| `frontend/lib/api/openapi.json`, `schema.ts` | `make client` — never hand-edited |

## Technical Details

### The stable URL, and why it is a redirect

The bucket is private and run 041 proved a presigned URL **cannot be made stable** without
racing botocore's signing path. So `me` hands out an app-owned URL and the redirect mints
the signature per request:

```
GET /api/auth/profile/avatar/{version}   →  302  →  presigned bucket URL (TTL 300s)
```

`{version}` derives from the stored key, so **replacing a picture changes the URL** and the
browser cache invalidates itself without a cache-busting query string.

### Two rules that must not drift

**`max-age` < presign TTL.** If the browser caches the redirect *target* longer than the
signature lives, the picture breaks for exactly as long as the difference. The acceptance
criterion says a test must read **both from the same settings**, so I will derive the
max-age from `BLOB_URL_TTL_SECONDS` rather than writing a second number:

```python
AVATAR_REDIRECT_MAX_AGE = BLOB_URL_TTL_SECONDS // 2
```

and the test asserts `max_age < BLOB_URL_TTL_SECONDS` by reading both settings — so the
relationship holds even if someone changes the TTL.

**A stale `{version}` must be refused, not served.** Otherwise an old URL — which may have
been shared — leaks the *current* picture. The handler compares the requested version
against the version of the user's stored key and 404s on mismatch.

### Refusing a large upload without buffering it whole

Django's defaults spool a file over `FILE_UPLOAD_MAX_MEMORY_SIZE` (2.5 MB) to **disk**, not
memory, and neither `DATA_UPLOAD_MAX_MEMORY_SIZE` nor anything else caps a *file* field. So
a 10 GB POST would be written to disk before the handler ever ran.

**The handler therefore checks `CONTENT_LENGTH` before touching `request.FILES`**, because
accessing `request.FILES` is what triggers parsing. A declared length over the cap is
refused immediately. The command's own `read(cap + 1)` remains the real guard — the header
is a claim, not a fact — but checking it first means an honest oversized upload costs
nothing and a dishonest one still cannot get past the command.

### Where the version rule lives

In `services/avatar.py`, beside the commands that create the keys — **not** in `api.py`.
The surface file would then own a rule about key format, and `api.py` is scanned by
`test_no_direct_writes.py` precisely because surfaces should not own domain rules.

### `avatar_url` is `""` when unset

Not `null`, not absent — matching how `name` and `pending_email` already work on
`CurrentUserOut`. One "no picture" state on the wire, as there is one in the column.

## Verification

1. `make client`; **operation ids read out of the regenerated `openapi.json`**, not assumed.
2. `tests/api/test_contract.py` and `tests/e2e/test_state_change_contract.py` green.
3. `test_no_direct_writes.py` green — the handlers call the named commands only.
4. A mutation probe per test, as run 051 established.
5. The multipart request body type is **inspected in the generated `schema.ts`** and a
   `bodySerializer` proved against it, so the UI item does not inherit an unknown.

## Open question for the checkpoint

**Whether the redirect endpoint should be on `/api/auth` at all.** It is a `GET` that
returns an image to an `<img>` tag, which means the browser issues it without the fetch
client, with cookies but no CSRF token — which is fine for a `GET`, but it is the first
endpoint in this project whose response is consumed by the browser's image loader rather
than by typed client code. It is still an authenticated read of the caller's own data, so
`/api/auth` is defensible; `/api/personal` would be the alternative. **I propose keeping it
on `/api/auth`** beside the profile it belongs to, and noting the distinction in the
handler docstring.

---
*Plan approved at checkpoint. Execution followed.*
