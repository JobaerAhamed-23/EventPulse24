---
id: account-deletion-cancel-surface
title: The Way Back — Cancelling a Deletion From the Page
intent: account-profile-expansion
complexity: medium
mode: confirm
status: completed
depends_on:
  - account-deletion-and-avatar-removal
  - account-danger-zone
created: 2026-11-20
run_id: run-eventpulse24-054
completed_at: 2026-11-20T08:50:03.939Z
---

# Work Item: The Way Back — Cancelling a Deletion From the Page

## Description

**A-16's third paragraph promises a second way out, and it does not exist.**

> You can cancel anytime during the 30-day grace from this page or from the email we
> send.

`account-deletion-and-avatar-removal` built `cancel_account_deletion` and its endpoint
(`DELETE /api/auth/profile/deletion`) — **the capability is complete**. What does not
exist is any surface that lets a person use it.

**There is no user-reachable way to cancel a pending account deletion.** Not on the
profile screen, not on the privacy page, not anywhere. A person who asks to delete their
account and then changes their mind has no way back except waiting out the grace period
and losing the account anyway.

## The API gap this item has to close first

**There is no way for the frontend to know a deletion is pending.**

`CurrentUserOut` (`backend/apps/identity/schemas.py:84`) carries `pending_email` and
`pending_email_expires_at` — and carries nothing about a pending deletion. The frontend
reads the user through `/api/auth/me`, and that payload does not say *"this account is
scheduled for destruction on the 14th"*.

**So a cancel button cannot be built on the current contract.** A UI that renders "you
can cancel" unconditionally would be offering a control that fails for the 99% of users
with no pending deletion — and a UI that renders it only when it knows would have
nothing to render it from. **The read has to exist first.**

**The pattern to copy is right there in the same schema.** `pending_email` is the
address an outstanding change is *to*, and `pending_email_expires_at` is the moment its
link stops working. The deletion equivalents are:

| Field | What it carries | Why |
|---|---|---|
| `deletion_scheduled_for` | The moment the account will be destroyed, ISO-8601, or `""` when none | The server computed it once and it cannot be moved — **the moment, not a duration**, for the same reason the email token's expiry is a moment |
| `deletion_requested_at` | When the request was recorded, ISO-8601, or `""` when none | Lets the surface say *"you asked on the 3rd"* without recomputing anything |

**Both are `""` and never `null`, for the same reason `name` and `pending_email` are** —
"none pending" is one state, not two.

**And the expiry of the *cancellation* is not a field.** The cancellation window closes
at `scheduled_for`, so the surface derives "you have N days left" from the one date it
already has. **A second date field would be two answers to one question.**

## Why the read rides `me` and not a new endpoint

**`me` is the read the frontend already makes on every render.** A separate
`GET /api/auth/profile/deletion` would be a second round trip on every page for a fact
that concerns one screen.

**This is the same reasoning `pending_email` already carries**, and its docstring
explains why it rides `me` rather than living on its own endpoint:

> **The address, not a boolean**, and that was a decision rather than convenience. A
> boolean leaves the screen unable to say *which* address a link went to...

**A boolean would be worse here.** `"deletion_pending": true` cannot tell the surface
when the account dies, and the whole point of the surface is to say when.

**The cost is honest and should be recorded**: `me` is read on every page, and two
extra strings ride it forever, even for users who will never delete anything. The
alternative — a read only when the user opens the danger zone — is a second round trip
on one screen, and it cannot be the *shell's* job either.

**This item's design checkpoint should settle it**, because it is a real trade: two
small fields on every page's payload, versus one extra request on one screen.

## Where the surface lives

**The danger zone at `/settings/privacy` is where the request is made, so it is where
the cancel lives** — the sibling item `account-delete-confirmation-surface` builds the
danger zone and the modal that starts the request.

**A user who has a pending deletion needs to be able to reach the cancel without going
through the request modal again.** Opening a "Delete your account?" modal to find out
you cannot cancel is a terrible path to the thing you came to do.

**So the danger zone carries a second state.** When a deletion is pending, it shows the
pending state — the date, and a "Keep my account" action — instead of the "Delete
account →" row.

## Acceptance Criteria

- [ ] **`CurrentUserOut` carries the pending-deletion state** — `deletion_scheduled_for`
      and `deletion_requested_at`, both ISO-8601 strings, both `""` when there is no
      pending deletion, both never `null`
- [ ] The read is **not** a boolean — the surface can say *when* the account dies, and
      `scheduled_for` is the value the server already computed
- [ ] **A pending deletion does not change the grace period** — the surface reads the
      date the server set and renders that, and asking again does not move it
- [ ] The **danger zone at `/settings/privacy` shows the pending state** when one
      exists — the date, and a **"Keep my account"** action
- [ ] The danger zone shows **the request row** when there is **no** pending deletion —
      one state or the other, never both
- [ ] The cancel action calls `DELETE /api/auth/profile/deletion`, with the CSRF token
      the project already reads from the cookie
- [ ] **Cancelling is not presented as an error** — the endpoint answers the same way
      whether or not anything was pending (`AccountDeletionCancelOut`), and the surface
      reflects that rather than treating "nothing was pending" as a failure
- [ ] After cancelling, **the surface shows the account is safe** and the pending state
      is gone — the next `me` read carries `""`
- [ ] **The account and the picture are untouched by a cancellation** — the picture was
      never removed at request time, so a cancelled deletion leaves it where it was, and
      a test asserts the bucket key is still there
- [ ] The generated client is **regenerated and committed**, and
      `backend/tests/api/test_contract.py` is green (AD-19)
- [ ] `frontend/tests/endpoint-coverage.test.ts` no longer exempts
      `DELETE /api/auth/profile/deletion` — the exemption is deleted, not rewritten
- [ ] `axe-core` passes on the pending state, and on the danger zone in both states
- [ ] The settings sub-nav stays correct from every settings screen, and
      `tests/settings-routes.test.ts` stays green
- [ ] Run the frontend under **Node 24**

## Technical Notes

- **Read `account-deletion-and-avatar-removal.md` first.** It records why the picture is
  removed at destruction and not at request, and why the grace period is the promise
  that must be kept whole.
- **`cancel_account_deletion` deletes the pending rows and writes an audit entry in the
  same transaction** (`backend/apps/identity/services/deletion.py:464`). The API layer
  calls the command — never writes (AD-5) — and
  `tests/architecture/test_no_direct_writes.py` enforces it.
- **The API layer must not read the `DeletionRequest` model directly.** The read that
  fills the two new fields belongs to the service layer, exposed through the same
  published interface the rest of `identity` uses.
- **The date format is ISO-8601 with a timezone**, matching `requested_at` and
  `scheduled_for` in `AccountDeletionRequestOut`.
- **A pending deletion is not an error state for the rest of the product.** The account
  keeps working in full during the grace period, so nothing else in the app changes —
  the digest still sends, the picture still shows, the session still works.
- **Do not add a "deletion pending" banner to the shell.** The user asked to leave;
  plastering the product with a warning they did not ask for is a decision the design
  doc should make deliberately, and it is not in A-16. The default is the danger zone.

## Dependencies

- `account-deletion-and-avatar-removal` — the `cancel_account_deletion` command, the
  `DeletionRequest` row, and the `DELETE /api/auth/profile/deletion` endpoint
- `account-danger-zone` — **the danger zone is where the pending state lives**, so the
  section has to exist before this one can hang its second state on it

## Sequencing Note: The Read Ships Before Anything Uses It

**This item owns the contract change** — the two new fields on `CurrentUserOut` — and
**it is the seam that the other two surfaces depend on.**

**The order is: this item's read → the danger zone → the modal.** The fields land on
`me` with no surface consuming them yet, and the two other items build against a
contract that is already there. **That is what breaks the cycle** between the danger
zone (which needs to know which state to render) and this item (which needs the danger
zone to render that state into).

**The fields are useless on their own, and that is fine.** A contract field nothing
reads yet is not dead code — it is the seam that lets two surfaces that need each other
be built in sequence rather than in one pass.
