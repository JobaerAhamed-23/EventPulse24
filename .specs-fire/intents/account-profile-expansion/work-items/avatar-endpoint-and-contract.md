---
id: avatar-endpoint-and-contract
title: Uploading It — a Multipart Endpoint on a Router With No Auth
intent: account-profile-expansion
complexity: medium
mode: confirm
status: pending
depends_on:
  - avatar-model-and-command
created: 2026-11-19
---

# Work Item: Uploading It — a Multipart Endpoint on a Router With No Auth

## Description

**Two endpoints and one extended read**, on the `/api/auth` router
(`backend/apps/identity/api.py:96`), which has **no router-level `auth=`** — so each
handler resolves the user itself and calls `require_csrf(request)` **first**, exactly as
`signup`, `signin`, `signout` and `PUT /api/auth/profile` already do.

- `POST /api/auth/profile/avatar` — **multipart**, one file field. Calls
  `set_user_avatar`. Returns the updated profile.
- `DELETE /api/auth/profile/avatar` — calls `clear_user_avatar`.
- `GET /api/auth/me` — `CurrentUserOut` gains the **avatar URL**, `""` when none is set,
  matching how `name` was added for exactly this reason: the shell needs it on every
  page, and `frontend/lib/session.ts` already reads `me`. **A second endpoint for the
  same row would be a second round trip on every render.**

**The field on the wire is a URL, not the key.** The key is internal; what the client
can use is an address it can put in an `img`. If the storage item chose signed URLs,
this is where the signing happens and **the expiry becomes part of the contract** — a
URL that expires while a page is open is a broken picture, and the TTL has to outlive a
reasonable page view.

**This is a multipart endpoint, and it is the first one.** Check whether the project's
Ninja setup, the CSRF helper and the generated client already handle `multipart/form-data`
before assuming they do — and if the generated TypeScript client cannot express a file
upload, **say so and solve it here**, not in the UI item.

## Acceptance Criteria

- [ ] `POST /api/auth/profile/avatar` accepts a multipart upload and returns the updated
      profile
- [ ] `DELETE /api/auth/profile/avatar` clears it
- [ ] `CurrentUserOut` carries the avatar URL, and it is `""` when unset — not `null`,
      not absent
- [ ] Both handlers call `require_csrf(request)` **before any other work**
- [ ] An anonymous caller gets **401**; a request with no CSRF token gets **403**
- [ ] A refused upload gets **422** in the project's `{code, message, details}` shape,
      and the details **do not echo the filename back** (AD-13)
- [ ] An over-sized upload is refused without the process buffering it whole
- [ ] Every response status is **declared** on the handler, so `ErrorOut` reaches the
      generated client
- [ ] The handlers call the **named commands** and touch no ORM —
      `tests/architecture/test_no_direct_writes.py` green
- [ ] `make client` run, and **both** `frontend/lib/api/openapi.json` and
      `frontend/lib/api/schema.ts` committed and modified in this change (AD-19)
- [ ] `backend/tests/api/test_contract.py` and
      `backend/tests/e2e/test_state_change_contract.py` green
- [ ] Operation ids are **read out of the regenerated `openapi.json`**, not assumed
- [ ] Tests cover: upload, read-back through `me`, delete, unset, anonymous, missing
      CSRF, non-image, over-size — each verified by a mutation probe

## Technical Notes

- **`me` is the read to copy** (`api.py:248-282`): a `GET` on a router with no `auth=`,
  resolving the user through `current_user(request)` which raises the 401.
- **`CurrentUserOut` has no catch-all on purpose** (`schemas.py:87-89`) — add the field
  explicitly so nothing internal can ride along.
- **`GET` is never CSRF-checked**, so no write may hide behind `me`.
- **`DELETE`, not a `PUT` of an empty string.** The product's settings writes are `PUT`
  with patch semantics, but removing a stored object is a deletion and reads as one.
- **`ErrorOut` is `shared.errors.ErrorOut`**, the shared shape.

## Dependencies

- `avatar-model-and-command` — the endpoint calls the commands and returns the field
  they write.
