---
id: profile-endpoint-and-contract
title: The Profile Endpoint — and the Contract It Regenerates
intent: account-profile-name
complexity: medium
mode: confirm
status: completed
depends_on:
  - user-name-model-and-command
created: 2026-11-13
run_id: run-eventpulse24-032
completed_at: 2026-11-13T11:34:54.400Z
---

# Work Item: The Profile Endpoint — and the Contract It Regenerates

## Description

**Two endpoints, one router.** The `/api/auth` router (`backend/apps/identity/api.py:96`)
has **no router-level `auth=`** — sign-up and sign-in are how a session is created — so
each handler resolves the user itself, exactly as `me` does at line 260. The new write
follows that same shape.

### `GET /api/auth/me` — extended

`CurrentUserOut` (`backend/apps/identity/schemas.py:84`) gains **`name: str`**.

**Why `me` and not a new read.** `me` is already *"who is making this request"*, and
the frontend needs the name on **every** page — the rail, the bottom bar, every screen's
`AppShell`. `frontend/lib/session.ts` already reads `me` for the session; a second
endpoint for the same user would be a second round-trip for the same row.

**The field is `""` when unset**, matching the model's blank default. It is spelled out
explicitly, which is the point of `CurrentUserOut`'s rule that it carries *"no password
field, no permission field and no catch-all, so nothing internal can ride along"*
(`schemas.py:87-89`) — a catch-all would have let a new column leak by accident; an
explicit field does not.

### `PUT /api/auth/profile` — new

```python
class ProfileIn(Schema):
    name: str

class ProfileOut(Schema):
    id: UUID
    email: str
    name: str
```

Response: `{200: ProfileOut, 403: ErrorOut, 422: ErrorOut}`.

The handler:
1. calls `require_csrf(request)` **first** — the `/api/auth` router has no router-level
   auth, so the CSRF check is explicit, exactly as in `signup` (`api.py:167`), `signin`
   (line 210) and `signout` (line 234);
2. resolves the user (401 for an anonymous caller);
3. calls `set_user_name(user_id=user.pk, name=body.name)` — the named command from
   `user-name-model-and-command`, **not** an ORM write (AD-5);
4. returns the updated profile.

**`PUT`, not `PATCH`.** The frontend has **no `api.PATCH` call site anywhere** — the
only mention of "PATCH" in the frontend is `lib/csrf.ts:37`, a comment — and
`/api/settings/notifications` is already a `PUT` with patch semantics
(`apps/delivery/preferences_api.py:86`). One verb for the product's settings writes.

**`ProfileOut` carries the email and the id** as well as the name, so the client can
update what it knows without a second `me` call after a save.

### The contract

```bash
make client
```

regenerates `frontend/lib/api/openapi.json` and `frontend/lib/api/schema.ts`. **Both are
committed** (AD-19).

This is not optional bookkeeping:
- `backend/tests/api/test_contract.py:16` compares the committed `openapi.json` to the
  live schema and **fails** when they differ;
- `backend/tests/e2e/test_state_change_contract.py:88` asserts `make client` leaves the
  tree unchanged;
- CI's contract job runs `make client` then `git diff --exit-code frontend/lib/api/`.

**The operation ids are generated, not chosen.** They carry the Django app's dotted path
(`apps_identity_api_…`). **Read the exact ids out of the regenerated `openapi.json`** —
do not assume them.

## Acceptance Criteria

- [ ] `CurrentUserOut` carries `name: str`, and `GET /api/auth/me` returns it
- [ ] A user with no name set gets `name: ""` — not `null`, and not a 404
- [ ] `PUT /api/auth/profile` saves the name and returns the updated profile
- [ ] The handler calls `require_csrf(request)` **before** any other work
- [ ] An anonymous caller gets **401**
- [ ] A request with no CSRF token gets **403**
- [ ] A refused name (newline, control character) gets **422** with the project's
      `{code, message, details}` shape
- [ ] The endpoint calls the **named command** and writes no ORM row itself — asserted
      against `tests/architecture/test_no_direct_writes.py`
- [ ] The endpoint is declared `PUT`, and the OpenAPI schema says `put`
- [ ] `make client` has been run, and **both** `frontend/lib/api/openapi.json` and
      `frontend/lib/api/schema.ts` are committed and modified in this change
- [ ] `backend/tests/api/test_contract.py` is green
- [ ] `backend/tests/e2e/test_state_change_contract.py` is green
- [ ] The new schemas live in `apps/identity/schemas.py`, next to the other wire shapes
- [ ] Tests cover: save, read-back through `me`, empty name, an over-long name, an
      anonymous caller, a missing CSRF token, and a refused name — each verified by a
      mutation probe that makes it fail

## Technical Notes

- **`me` is the read to copy, not `billing_api.py`.** `me` (`api.py:248-282`) is a
  `GET` on a router with no `auth=`, so it resolves the user itself with
  `current_user(request)` (which raises the 401) and reads the onboarding state through
  `personalization`'s published service rather than its model.
- **The response statuses are declared, not implied.** `signup` declares
  `{201: ..., 403: ErrorOut, 422: ErrorOut, 429: ErrorOut}` with a comment explaining
  that declaring them *"is what puts `ErrorOut` in the generated client, so the frontend
  can read the message it has to show"* (`api.py:150-153`). Do the same.
- **`ErrorOut` is `shared.errors.ErrorOut`** — the shared shape, not a local one.
- **Do not add a `PATCH`.** A second verb for the same write would put two shapes for one
  operation into the contract, and the frontend has no `PATCH` client support to speak
  of.
- **The name is not in the error `details` for a refusal.** The refusal's details say
  *what was wrong with the input*; they must not echo the input back (AD-13).
- **The onboarding read in `me` is read-only and stays that way.** Its comment says an
  expired onboarding is *reported* as step 1 and *"the row is left for the next command
  to restart"* — because `me` is a `GET`, and a `GET` is never CSRF-checked, so a write
  behind one would be a cross-site write. The name write is behind `PUT /profile`, which
  **is** CSRF-checked. Do not move it onto `me`.

## Dependencies

- `user-name-model-and-command` — the endpoint calls `set_user_name`, and
  `CurrentUserOut.name` reflects the field the model now has.
