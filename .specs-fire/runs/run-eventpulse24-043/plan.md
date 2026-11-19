---
run: run-eventpulse24-043
work_item: email-change-mails
intent: account-profile-expansion
mode: confirm
checkpoint: plan
---

# Plan: Two Letters — One to Prove It, One to Warn About It

## What exists, so what this actually is

`services/emails.py` already renders and streams auth mail: `reset_password_link`,
`render_reset_password_email`, `reset_password_stream`, plus a text template under
`apps/identity/templates/identity/`. **So this item is two links, two renderers, two
templates and a stream choice — not new machinery.**

`request_email_change` already returns everything needed: the raw token, **both**
addresses, the row id for the idempotency key, and `expires_at`.

## The work

### 1. The confirmation mail → the **new** address

- `confirm_email_change_link(token)` — the frontend's own route plus the token, exactly as
  `reset_password_link` does, from `FRONTEND_BASE_URL` because the API is a different
  origin. The route is the one `email-change-on-the-profile-screen` will build.
- `render_confirm_email_change_email(*, to, token, expires_in)` + a text template.
- Addressed to the **new** address, because that is the address being proven.

### 2. The warning mail → the **old** address

- `render_email_change_requested_email(*, to, new_email_hint, expires_in)` + a template.
- **It carries no token and no link that performs the change.** It warns; it must not also
  be the means. Someone who reads it and did not ask for it is the only person who can
  stop this, so it says what to do — and what to do is *change your password*, which is
  the one action that is entirely in their hands and which revokes nothing else they need.

**One open question inside it:** does the warning name the new address? Naming it tells a
victim exactly what is happening. It also mails a stranger's address to the account holder
— but the account holder is the person being attacked here, not a third party, and they
can already see the pending change on their own profile screen. **Recommendation: name it**,
because a warning that will not say what is being changed is hard to act on.

### 3. The stream

`email_change_stream()` returning `Stream.TRANSACTIONAL`, named in one place for the same
reason `reset_password_stream` is: *"a future second auth mail cannot drift onto the wrong
one by accident."* Both of these mails are security notices.

### 4. The expiry, from the constant

Both templates state when the link expires, rendered from
`AUTH_EMAIL_CHANGE_TOKEN_LIFETIME` passed in as context — **not typed into the copy.**

> **Finding, and a decision for you.** `password_reset.txt` *does* type it in: it says
> *"valid for 30 minutes"* as literal text, so changing `AUTH_RESET_TOKEN_LIFETIME` today
> leaves the mail lying to the reader. That is exactly what this item's acceptance
> criterion forbids. It is a two-line fix in a file I am otherwise not touching.
> **I propose fixing it**, rather than shipping new mails that do it right beside an old
> one that does it wrong. Say if you would rather I leave it alone.

## Tests

- Each renderer's recipient — asserted so that **swapping them fails**
- The warning carries **no token** and no confirmation link
- Neither mail is logged with its token; the logger allowlist is untouched
- The expiry text follows the constant: change the constant, the copy changes
- Both go on the transactional stream
- Preview environments never really send — the existing seam is used, not bypassed

Then a mutation probe per test.

## What I will stop and report

- Any need to put the token in the warning mail to make the flow work
- A template change that would require widening the logger allowlist
- The send-failure question below, if it turns out to need product behaviour rather than a
  recorded decision

## The send-failure decision, stated rather than left

`request_email_change` writes the row and returns; the mails are sent **after** the
transaction, as `request_password_reset` does. If a send fails, the user holds an
outstanding request and no link. **Proposal: that is acceptable and not retried here** —
the row expires, and the screen's resend control (a later item) is the remedy. The
alternative, retrying inside the request path, makes a mail provider's outage into a
failed API call for the user.

## Files

| File | Action |
|---|---|
| `backend/apps/identity/services/emails.py` | modify — two links/renderers + stream |
| `backend/apps/identity/templates/identity/email_change_confirm.txt` | create |
| `backend/apps/identity/templates/identity/email_change_requested.txt` | create |
| `backend/apps/identity/templates/identity/password_reset.txt` | modify — *if you approve the finding above* |
| `backend/tests/identity/test_email_change_mails.py` | create |

**Nothing calls these yet.** Wiring the sends into the request path belongs to
`email-change-endpoints-and-contract`, which owns the edge.
