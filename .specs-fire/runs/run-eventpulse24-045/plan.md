---
run: run-eventpulse24-045
work_item: email-change-on-the-profile-screen
intent: account-profile-expansion
mode: confirm
checkpoint: plan
---

# Plan: Asking to Move Your Address — and the Page the Link Lands On

## The gap, resized

The decomposition owed this item a resend and a cancel and provided neither. **Half of it
was never a gap:** the raw token is not stored, only its digest (AD-18), so a resend
cannot re-send the original link — it must mint a new one — and `request_email_change`
already revokes the outstanding row first. **So resend is `POST /profile/email` called
again with the pending address**, and the per-account throttle limits it for free.

**The real gap is cancel**, and it is added to this item.

## 1. Backend: cancel

- `cancel_email_change(*, user_id)` in `services/email_change.py` — revokes the account's
  outstanding rows inside `transaction.atomic(using=PERSONAL)`, audits
  `email_change_cancelled` with **no address in the details** (AD-13).
- **Idempotent.** Cancelling with nothing pending is not an error: the caller's intent —
  *"have no pending change"* — is satisfied either way. That is `signout`'s existing rule.
- `DELETE /api/auth/profile/email` — `require_csrf` first, 401 anonymous, `{200, 401, 403}`.
- `make client`, both artifacts committed.

## 2. The screen: three states

`EmailChange` island on `/settings/profile`, under the name and above the city.

| State | What it shows |
|---|---|
| **Nothing pending** | The current address, and a control to change it |
| **Pending** | The requested address, when the link expires, **Resend**, **Cancel** |
| **Just confirmed** | Handled by the confirm route, not here |

**This control does not save on change, and the screen says why.** Every other settings
island saves on keystroke; an email change fired on a keystroke would mail `m@`, `ma@`,
`may@`. So it has an explicit action, and copy that says a link will be sent and nothing
changes until it is opened.

**A taken address must look exactly like a free one** — the API returns the same 202, and
the UI must not become the oracle the API refused to be. The success line is the same
sentence either way.

**Failures follow the house rule**: the API's own message verbatim via
`saveFailureMessage`, the generic offline line only when the request never reached the
API.

## 3. The route the link lands on: `/confirm-email`

Modelled on `/reset-password`, which solved this already:

- `metadata.referrer = "no-referrer"` — **the token is a bearer credential in the URL**,
  and without this any cross-origin request from the page leaks it in `Referer`.
- `force-dynamic`, because the token comes from the request.
- **It must work signed out.** `homeRoute(session)` sends anonymous visitors to
  `/preview`, so this route must not sit behind that redirect — a confirmation link that
  gets redirected is a link that does not work. This is the single most likely bug in the
  item, and it gets its own test.
- It POSTs the token (never a GET: a GET that moves a login is performed by every mail
  scanner that touches the message), shows the new address on success, and on failure
  gives one undramatic explanation and a way forward.

## 4. What the screen does *not* say

The design decided other sessions are **not** ended, so there is no warning to show. The
screen should not imply otherwise.

## Tests

Vitest over all three island states, the taken-address sameness, both failure modes,
resend minting a new token, cancel clearing the state; and the confirm route signed out,
on success and on every refusal. Backend tests for the cancel command and endpoint,
including idempotency and that a cancelled link no longer confirms.

Then a mutation probe per test.

## Files

| File | Action |
|---|---|
| `backend/apps/identity/services/email_change.py` | modify — `cancel_email_change` |
| `backend/apps/identity/api.py`, `schemas.py` | modify — `DELETE /profile/email` |
| `backend/tests/identity/test_email_change*.py` | modify — cancel |
| `frontend/components/settings/email-change.tsx` (+ test) | create |
| `frontend/app/settings/profile/page.tsx` (+ test) | modify |
| `frontend/app/confirm-email/page.tsx` (+ test) | create |
| `frontend/lib/api/*` | regenerate |

## What I will stop and report

- `/confirm-email` proving unreachable signed out without changing shared routing
- Any need to make the taken-address case visibly different to build the UI
