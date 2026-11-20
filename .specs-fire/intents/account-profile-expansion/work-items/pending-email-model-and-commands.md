---
id: pending-email-model-and-commands
title: Moving the Login — a Token That Proves the New Address First
intent: account-profile-expansion
complexity: high
mode: validate
status: completed
depends_on: []
created: 2026-11-19
run_id: run-eventpulse24-042
completed_at: 2026-11-19T09:52:31.876Z
---

# Work Item: Moving the Login — a Token That Proves the New Address First

## Description

**This moves a credential, and that is the whole difficulty.** `User.email` is
`USERNAME_FIELD`; it is unique case-insensitively through the named `user_email_uq`
constraint; and `User.save()` normalises it as a backstop *specifically so a write that
bypasses the command layer cannot slip a mixed-case duplicate past that constraint*
(`models.py:23-88`). The previous intent recorded that the email "is not changeable from
here". **This item changes that deliberately, and pays the price in full.**

**The new address is proven before the login moves.** A `PendingEmailChange` row holds
the requested address and a token; the login moves **only** when that token comes back
from the new address.

**The row's shape is already decided, by `PasswordResetToken` (`models.py:92`).** That
docstring records that Django's `PasswordResetTokenGenerator` was *probed* against the
pinned Django and rejected: two consecutive `check_token` calls both succeed, so it is
replayable, cannot be revoked and cannot be listed. **The same reasoning rules it out
here**, and the pending-email row takes the same properties: a `sha256(salt + token)`
digest with a per-row salt and **no token at rest** (AD-18), `expires_at` from a named
constant, `used_at` set in the same transaction that consumes it, `revoked_at` for
invalidation without use, the user held **by value** (OQ-8), and the used/revoked
mutual-exclusion check constraint.

**Commands, in `apps/identity/services/`** (AD-5):

- `request_email_change(*, user_id, new_email, ip_address=None)` — normalises the
  address the same way `UserManager.normalise_email` does, refuses a change to the
  address already held, **revokes any outstanding request** for that user, issues the
  token, and returns what the mail item needs to send.
- `confirm_email_change(*, token)` — consumes the token and moves the login, inside one
  transaction.

**Three refusals that are security decisions, not validation:**

1. **An address another account holds is refused without disclosing that account
   exists.** `request_password_reset` already answers identically whether or not an
   address is known; this follows it. **The disclosure can also leak through timing and
   through the mail that is or is not sent** — decide and record how.
2. **The window between request and confirmation is a window.** If the other account
   claims the address first, the confirmation must fail cleanly at consumption time, and
   the unique constraint — not a pre-check — is what guarantees it.
3. **Requests are rate limited.** Otherwise the endpoint is a mailer pointed at any
   address an attacker types.

**The open question the brief names is settled here**: whether moving the login ends
the account's other sessions. The password reset flow already does. Decide, record the
rationale, and implement it.

## Acceptance Criteria

- [ ] A `PendingEmailChange` model storing a **digest with a per-row salt and no token
      at rest** (AD-18), with `expires_at`, `used_at`, `revoked_at`, the user **by
      value**, and a used-or-revoked check constraint
- [ ] `retention_category` declared (AD-15); one forward-only migration
- [ ] `request_email_change` normalises the address exactly as `UserManager` does
- [ ] A request for the address the account already holds is refused
- [ ] A request for an address **another account holds** is refused **without revealing
      it exists**, and the chosen anti-disclosure approach is recorded in the docstring
- [ ] A new request **revokes** the user's outstanding one — two live tokens for one
      account is two ways in
- [ ] `confirm_email_change` moves the login **inside one transaction** (AD-3) and marks
      the token used in that same transaction
- [ ] A token that is **expired**, **revoked**, **already used** or **unknown** is
      refused, and **the old address still logs in afterwards** — asserted, not assumed
- [ ] Confirming when the address was claimed in the meantime fails cleanly on the
      **unique constraint**, with nothing half-written
- [ ] Rate limiting on requests, with a named constant and a test that trips it
- [ ] The session consequence is **implemented and recorded with its rationale**
- [ ] Audit rows for request and confirmation, written in the same transaction, with
      **no address in the details** (AD-13)
- [ ] `tests/architecture/test_no_direct_writes.py` green
- [ ] Every test can fail — mutation probe per test

## Technical Notes

- **Read `services/password_reset.py` end to end before writing anything.** It holds
  `hash_token`, `_find_outstanding_token` and the issue/consume split this item mirrors.
  Reuse the hashing helper rather than writing a second one.
- **The login is encrypted/normalised on `save()`** — a command that writes the email
  must not fight that backstop, and a test should prove a mixed-case new address lands
  normalised and still satisfies `user_email_uq`.
- **The notification to the old address is this item's output, not its job** — it emits
  what is needed; `email-change-mails` renders and sends.
- **Do not reach into `personalization`** (AD-2/AD-16): the digest preference keys off
  the user, not the address.

## Dependencies

(none) — it shares no code with the avatar half, and can run in parallel with it.
