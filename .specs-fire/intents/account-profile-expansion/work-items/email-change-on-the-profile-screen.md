---
id: email-change-on-the-profile-screen
title: Asking to Move Your Address — and the Page the Link Lands On
intent: account-profile-expansion
complexity: medium
mode: confirm
status: completed
depends_on:
  - email-change-endpoints-and-contract
created: 2026-11-19
run_id: run-eventpulse24-045
completed_at: 2026-11-19T11:56:00.199Z
---

# Work Item: Asking to Move Your Address — and the Page the Link Lands On

## Description

**This control does not save on change, and that is the point.** Every other settings
island in the product saves on keystroke — the quiet window, the delivery time, the
name. **An email change fired on a keystroke would mail `m@`, `ma@`, `may@`.** So this
one has an explicit action, and the screen says what that action will do: *a link goes
to the new address, and nothing changes until you use it.*

Three states the screen must render honestly:

1. **No change in flight** — the current address, and a way to ask for a new one.
2. **A change pending** — what was requested, when the link expires, a **resend**, and a
   **cancel**. A pending change the user cannot cancel is a pending change they are
   stuck with until it expires.
3. **Just confirmed** — the login has moved, and if the session consequence chosen in
   `pending-email-model-and-commands` ends other sessions, **the screen says so before
   the user finds out by being signed out.**

**And the page the link lands on.** The confirm endpoint is a `POST`, because a `GET`
that moves a login is performed by every mail scanner that touches the message. So the
link opens a **frontend route** that posts the token — and that route must work for a
visitor with **no session**, in a browser that never saw the request.

## Scope amendment — 2026-11-19

**The decomposition had a gap: this item's pending state needs a resend and a cancel, and
neither endpoint was in any work item.** `email-change-endpoints-and-contract` shipped
request and confirm only. The gap was mine, not the intent's.

**Half of it turned out not to be a gap.** The raw token is never stored — only its digest
is (AD-18) — so a resend *cannot* re-send the original link; it has to mint a new one. And
`request_email_change` already revokes any outstanding row before creating the next. **So
a resend is `POST /api/auth/profile/email` called again with the pending address**, no new
endpoint, and the existing per-account throttle limits it for free.

**The real gap is one endpoint: cancel.** `DELETE /api/auth/profile/email` and a
`cancel_email_change` command, added to this item's scope.

**Cancel matters more than it looks.** It is the user-facing half of the remedy the
warning mail promises: an account holder who sees a change they did not ask for should be
able to stop it from the screen, not only by resetting their password.

## Acceptance Criteria

- [ ] The profile screen shows the current address and an explicit control to change it
- [ ] The control **does not fire on change**; the copy says what will happen before it
      happens
- [ ] A pending change shows the requested address, the expiry, a resend and a cancel
- [ ] **`DELETE /api/auth/profile/email`** and a `cancel_email_change` command (AD-5),
      audited, with no address in the details
- [ ] Cancelling is **idempotent**: cancelling when nothing is pending is not an error
- [ ] A cancelled link no longer confirms — asserted, not assumed
- [ ] **Resend mints a new token**; the old link stops working
- [ ] Cancelling clears the pending state, and the old address keeps working
- [ ] A refusal from the API is shown **verbatim**; the generic offline line only when
      the request never reached the API (`save-failure.ts`'s existing rule)
- [ ] A taken address produces **the same** screen state as a free one — the UI must
      not become the oracle the API refused to be
- [ ] The confirmation route works **signed out**, in a browser with no prior session
- [ ] A bad, expired or reused token on that route gives one clear, undramatic
      explanation and a way forward
- [ ] If the session consequence ends other sessions, the screen says so **before** the
      user acts
- [ ] `axe-core` passes; every state is announced, not only rendered
- [ ] Vitest covers all three states plus the confirmation route's success and failure —
      each with a mutation probe
- [ ] Run the frontend under **Node 24**

## Technical Notes

- **Do not model this on `profile-name.tsx`'s save-on-change**; model the *failure
  handling* on it and nothing else.
- **The confirmation route is a new public route.** Check how `/preview`, the reset-
  password route and `homeRoute(session)` treat an anonymous visitor before adding it —
  `homeRoute` redirects anonymous visitors to `/preview`, and a confirmation route that
  gets redirected is a confirmation link that does not work.
- **The e2e coverage of all this belongs to the last item**, not here.

## Dependencies

- `email-change-endpoints-and-contract` — the generated client and the `me` field.
