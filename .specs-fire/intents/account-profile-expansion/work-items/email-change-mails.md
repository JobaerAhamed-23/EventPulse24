---
id: email-change-mails
title: Two Letters — One to Prove It, One to Warn About It
intent: account-profile-expansion
complexity: medium
mode: confirm
status: completed
depends_on:
  - pending-email-model-and-commands
created: 2026-11-19
run_id: run-eventpulse24-043
completed_at: 2026-11-19T10:35:55.524Z
---

# Work Item: Two Letters — One to Prove It, One to Warn About It

## Description

**Two messages, and the second one is the security control.**

1. **To the new address** — the confirmation link that moves the login. It is the only
   thing that proves the address is reachable and the person's.
2. **To the old address** — *"a change to this address was requested."* **A credential
   that moves silently is an account takeover.** Someone who reads this mail and did not
   ask for it is the only person who can stop it, so the mail has to tell them how:
   what to do, and by when.

`backend/apps/identity/services/emails.py` already does this work for password resets
and data exports — `reset_password_link`, `render_reset_password_email`,
`reset_password_stream` — so this is **two renderers, two links and the stream choice**,
not new machinery.

**The token appears in the link and nowhere else.** Not in a log, not in an audit row,
not in the message sent to the old address — that mail warns; it must not carry the
means (AD-13).

## Acceptance Criteria

- [ ] A link builder and a renderer for the confirmation mail, following
      `reset_password_link` / `render_reset_password_email` exactly
- [ ] A renderer for the notification to the **old** address
- [ ] The old-address mail **contains no token and no link that performs the change**
- [ ] Neither mail is logged with its token; the logger allowlist is not widened (AD-13)
- [ ] The stream for each is chosen explicitly, as `reset_password_stream` is
- [ ] Both mails state **when the link expires**, from the same named constant the model
      uses — not a number retyped into copy
- [ ] The confirmation mail goes to the **new** address only; the notification to the
      **old** address only — asserted by a test that would fail if they were swapped
- [ ] Preview environments **never send real email** (constitution) — the existing seam
      is used, not bypassed
- [ ] Tests cover both renderers, the recipients, and the absence of a token in the
      warning mail — each with a mutation probe

## Technical Notes

- **Read `services/emails.py` first**; copy its shape rather than its text.
- **Say what happens if the mail fails to send** after the row was written: the user is
  left with an outstanding request and no link. Whether that is retried, surfaced, or
  left to the resend control in the UI item is a decision — record it.

## Dependencies

- `pending-email-model-and-commands` — the token and the expiry constant come from it.
