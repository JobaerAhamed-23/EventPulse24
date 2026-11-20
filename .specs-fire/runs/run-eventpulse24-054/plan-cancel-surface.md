---
run: run-eventpulse24-054
work_item: account-deletion-cancel-surface
intent: account-profile-expansion
mode: confirm
checkpoint: plan
---

# Implementation Plan: The Way Back — Cancelling a Deletion From the Page

## Approach

**This item ships the seam, and then the surface that hangs on it.** A person who asked to
delete their account and then changed their mind has no way back: the capability exists
(`cancel_account_deletion`, `DELETE /api/auth/profile/deletion`), but nothing in the app
calls it. This item builds the read that lets the frontend *know* a deletion is pending,
and the surface that acts on it.

**Four decisions are worth stating before the code.**

### 1. The read rides `me`, and it is two moments and not a boolean

`CurrentUserOut` carries `pending_email` and `pending_email_expires_at`; it carries nothing
about a pending deletion. **Without a read, a cancel button cannot be built at all** — a UI
that renders "you can cancel" unconditionally offers a control that fails for the 99% of
users with nothing pending, and a UI that renders it only when it knows has nothing to
render it from.

**The fields are `deletion_scheduled_for` and `deletion_requested_at`, both `""` when
there is nothing pending and never `null`** — "none pending" is one state, not two, for
the same reason `name` and `pending_email` are one state.

**And they are moments, not durations.** The screen has to say *when* the account dies,
and a duration typed into the frontend is the mistake the mail templates already made: a
number that keeps saying "30 days" after the constant says otherwise. The server computed
`scheduled_for` once, at request time, and it cannot be moved by asking again — so the
server's date is what the surface renders.

**The cost is real and it is recorded, not hidden.** `me` is read on every page, and two
extra strings ride it forever, even for users who will never delete anything. The
alternative is a second round trip on one screen, and it cannot be the shell's job
either. **The trade is two small strings on every payload, and it buys the ability to
say the date.**

### 2. The read lives in the service layer, and it does not leak the token

The work item is explicit: *"The API layer must not read the `DeletionRequest` model
directly."* There is a precedent in `api.py` that reads `PendingEmailChange` from the model
directly — **and this item does not copy it.** `DeletionRequest` now carries
`token_hash` and `token_salt`, and a read that handed the API layer the row would hand it
the cancel-token digest too.

**So the read returns a frozen dataclass carrying exactly two `datetime` fields** — the
`billing_read.py` pattern, which exists for the same reason: *"a caller holding the row
could write it."* The token cannot reach the wire because the read cannot carry it.

### 3. The danger zone keeps its shape — a server container with a client island inside it

`danger-zone.tsx` is a server component today, and it stays one. **The pending state
needs `useState` and a `fetch`, so it cannot live in the container** — but the container
is the thing the modal and the cancel action both hang on, and making it a client
component would drag the whole section across the boundary for one button.

**So the split is:** `danger-zone.tsx` reads two props and decides which of the two states
to render; a client island inside it holds the pending state and the "Keep my account"
button. `SettingRow`'s `control` prop is a `ReactNode`, so a client child can be passed
in from a server parent — **and `SettingRow` has a `footer` prop**, which is where the
inline success/refusal belongs, inside the row so the message and its control cannot be
separated by a layout change.

### 4. Cancelling is not an error, and the surface must not pretend it is

`AccountDeletionCancelOut` answers the same way whether or not anything was pending —
*"the caller wanted no pending deletion and has none either way."* **So the surface
reflects that**: after a cancel, the pending state is gone and the request row is back.
There is no "there was nothing to cancel" error path, and there must not be one.

**A cancel that silently cleared the screen would tell the user the deletion was stopped
when it was not** — so a *failed* cancel keeps the pending state and shows the refusal.

## What the pending state says

**It names the date the server computed**, and it says what cancelling does. The pending
state is *not* terracotta — **the accent is spent on the destructive control, and the
pending state is the way back from it.** The "Keep my account" button is the opposite of a
destructive action, so it wears the ordinary treatment.

**It does not claim the account is safe forever** — it says the account is destroyed *on
the date*, and that cancelling keeps it. The grace period is real and the date is the
server's.

## Files to Create

| File | Purpose |
|------|---------|
| `backend/apps/identity/services/deletion_read.py` | The pending-deletion read — a frozen dataclass and one function. **Its own module**, because a read that is not a write has no business sharing a file with the commands |
| `frontend/components/settings/danger-zone-pending.tsx` | The client island — the pending state, the date, and the "Keep my account" action |
| `frontend/components/settings/danger-zone-pending.test.tsx` | The island's states, the call, the failure, the axe gate |
| `frontend/tests/privacy-danger-zone-pending.test.tsx` | The page, with a pending deletion — the section shows the pending state in both branches |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/apps/identity/schemas.py` | `CurrentUserOut` gains `deletion_scheduled_for` and `deletion_requested_at`, each with a `#:` rationale |
| `backend/apps/identity/api.py` | The `me` handler calls the new read and fills the two fields; the endpoint's `description` documents them |
| `backend/apps/identity/services/__init__.py` | The read is published |
| `backend/tests/identity/test_auth_api.py` | The exact-dict assertion on `me` gains the two fields — **this is the assertion that keeps `me` from becoming a settings blob, and adding a field is meant to cost this edit** |
| `backend/tests/identity/test_profile_api.py` | The field-set assertion gains the two fields |
| `backend/tests/identity/test_deletion_read.py` | **New** — the read's own tests: the two moments, `""` when none, the token never leaking |
| `frontend/lib/api/openapi.json` | Regenerated by `make client` |
| `frontend/lib/api/schema.ts` | Regenerated by `make client` |
| `frontend/components/settings/danger-zone.tsx` | Takes the two props and renders one state or the other |
| `frontend/components/settings/danger-zone.test.tsx` | The "one state at a time" test becomes two tests — one per state |
| `frontend/app/settings/privacy/page.tsx` | Passes the two fields down in **both** branches |
| `frontend/tests/endpoint-coverage.test.ts` | **The `DELETE` exemption is deleted.** The `POST` one stays — that is the modal's work |
| `frontend/tests/privacy-danger-zone.test.tsx` | The `CurrentUserOut` fixture gains the two fields |
| Four other frontend fixtures | `session.test.ts`, `profile-a11y.test.tsx`, `avatar-in-the-shell.test.tsx`, `avatar-upload.test.tsx`, `profile/page.test.tsx` — the generated type is strict, so each mock needs the two fields |

## Tests

| Test File | Coverage |
|-----------|----------|
| `backend/tests/identity/test_deletion_read.py` | The read returns the two moments; `None` when nothing is pending; **the token digest never appears in what it returns**; the read does not write |
| `backend/tests/identity/test_auth_api.py` | `me` carries the two fields, `""` when nothing is pending, and the real moments when something is |
| `frontend/components/settings/danger-zone-pending.test.tsx` | The pending state names the date; the cancel calls `DELETE /api/auth/profile/deletion`; a failed cancel keeps the pending state; a successful cancel clears it; **cancelling is not shown as an error**; axe-core |
| `frontend/components/settings/danger-zone.test.tsx` | **One state or the other, never both** — now two real states rather than one state and an absence |
| `frontend/tests/privacy-danger-zone-pending.test.tsx` | The page shows the pending state in both branches when one exists |

## Technical Details

### The read is a separate module, not a fourth command

`backend/apps/identity/services/deletion.py` is the file with the *commands*, and its
docstring says so: *"Three commands, and the difference between them is the whole
design."* A read is not a fourth command, and putting it there would blur the file's own
central claim. `deletion_read.py` is its own module, holding a frozen dataclass and one
function — the same shape as `billing_read.py`.

**It returns `None` when there is nothing pending**, which is a real answer rather than an
empty one.

### The date format is ISO-8601, and it is the server's

`.isoformat()`, exactly as `AccountDeletionRequestOut` does it and exactly as
`pending_email_expires_at` does it. **The frontend parses it and formats it**; the
frontend never recomputes a grace period.

### The frontend call site must be literal

`frontend/tests/endpoint-coverage.test.ts` matches `\.${method}\s*\(\s*"${route}"` — **the
method and the path string must be adjacent.** A path held in a variable would not be
detected, and the exemption this item deletes would then be hiding a real call. So the
call is written as `api.DELETE("/api/auth/profile/deletion")`, literally.

### The CSRF token is already handled

`frontend/lib/backend-client.ts` installs `csrfOnRequest`, and `DELETE` is in its
`UNSAFE_METHODS` set — **so `api.DELETE` already carries the token read from the
`csrftoken` cookie.** There is no manual header work, and there must not be any.

### The `POST` exemption stays

`POST /api/auth/profile/deletion` is called by the modal, and the modal is
`account-delete-confirmation-surface`'s work — still pending. **This item deletes the
`DELETE` exemption and leaves the `POST` one alone**, and the reason string on the
remaining exemption still reads true.

### No banner in the shell

The work item is explicit, and this item follows it: **no "deletion pending" banner in
the shell.** The user asked to leave; plastering the product with a warning they did not
ask for is a decision the design doc should make deliberately, and it is not in A-16. The
default is the danger zone.

### The picture is untouched by a cancellation

The picture is removed at *destruction*, not at request. A cancelled deletion leaves the
picture exactly where it was, and the backend already asserts it
(`test_cancelling_brings_the_account_back_whole`). This item does not re-assert it — but
it does not contradict it either, and the surface's copy says the account keeps everything.

---
*Plan for approval at the checkpoint. Execution follows.*
