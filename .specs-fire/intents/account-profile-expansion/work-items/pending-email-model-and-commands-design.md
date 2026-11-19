---
work_item: pending-email-model-and-commands
intent: account-profile-expansion
created: 2026-11-19
mode: validate
checkpoint_1: approved
---

# Design: Moving the Login — a Token That Proves the New Address First

## Summary

`User.email` is `USERNAME_FIELD`. Changing it moves the credential a person signs in
with, so the new address is **proven before the login moves**: a `PendingEmailChange` row
holds the request and a token, and only that token coming back from the new address
completes it.

**Almost none of this is new invention, and that is the point.**
`apps/identity/services/password_reset.py` already solves the same problem — issue a
proof to an address, consume it once, safely — and its docstring records *why* each
property is there. This design reuses that shape, its helper, and its error vocabulary,
and spends its own reasoning only on what is genuinely different: a second address, a
uniqueness constraint that can be lost in the race, and a credential that moves while a
session is open.

## Scope

**In Scope:**
- `PendingEmailChange`, shaped from `PasswordResetToken`
- `request_email_change` and `confirm_email_change` in `apps/identity/services/`
- The non-disclosing refusal, the throttle, the audit rows, the session decision
- One forward-only migration

**Out of Scope:**
- The mails (`email-change-mails`), the endpoints (`email-change-endpoints-and-contract`)
  and the screen. This item **emits what the mail item needs** and sends nothing.

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Token storage | **Salted SHA-256 digest, raw token never stored** (AD-18) | `PasswordResetToken`'s rule verbatim: a database dump must yield no usable link. **Reuse `password_reset.hash_token`** rather than write a second digest function — two hashing implementations is two things to get wrong. |
| Token generator | **`secrets.token_urlsafe(32)`, not Django's `PasswordResetTokenGenerator`** | Already probed and rejected in this codebase against the pinned Django: it is replayable between issue and use, cannot be revoked, and cannot be listed. That reasoning applies here unchanged, and re-deciding it would be re-litigating a settled probe. |
| Row identity | **User held by value (`user_id`), no FK** | OQ-8, the same as `PasswordResetToken`. |
| Lifetime | **A named constant**, `AUTH_EMAIL_CHANGE_TOKEN_LIFETIME`, beside `AUTH_RESET_TOKEN_LIFETIME` | The mail quotes the expiry, so one constant must feed both the model and the copy. Reset is 30 minutes; **this should be longer** — a reset is a person locked out and acting now, an email change is a person who may check the new mailbox later. Proposed **24 hours**, and this is the number most worth your opinion. |
| Supersede | **A new request revokes the outstanding one** | Two live tokens for one account is two ways in, and it is `request_password_reset`'s existing behaviour. |
| Address already taken | **Refused, and the refusal is indistinguishable from success** | `request_password_reset` is enumeration-safe and this must be too — otherwise the endpoint is an oracle for "does an account exist at this address". **Nothing is written and no mail is sent to the taken address.** |
| Where the race is lost | **The `user_email_uq` constraint, at confirm time — not a pre-check** | Between request and confirm, another account can claim the address. A pre-check is a TOCTOU window; the unique constraint is the only thing that actually arbitrates. Confirm catches `IntegrityError` and raises the same refusal. |
| Refusal vocabulary | **One error for unknown, used, revoked, expired — and for the lost race** | `InvalidResetTokenError`'s rule: *"one error for all four cases, so the response never says which one it was"*. A distinguishing message is an oracle for token guessing. A **new** `InvalidEmailChangeTokenError(ValidationError)` → 422, so the two flows' errors cannot be confused. |
| Throttle | **A fourth operation, `email_change`, in `services/throttle.py`'s `LIMITS`** | The table is the extension point and already keys per IP *and* per account digest. Without it the endpoint is a mailer pointed at any address an attacker types. |
| Which address is throttled | **The account's own, not the requested one** | The per-account key digests an address; keying on the *requested* address would let an attacker spray many targets from one account at full allowance, and would create a counter bucket per victim address. |
| Sessions | **The login moves; other sessions are NOT ended** | See below — this is the open question the brief named, and the answer is "no", with a reason. |
| Audit | **Two rows: `email_change_requested`, `email_change_confirmed`** | Written inside the command's `transaction.atomic(using=PERSONAL)`, which `write_audit` enforces by raising otherwise. **Neither address appears in `details`** (AD-13); the details carry the method only. |

### The session decision, argued rather than asserted

`reset_password` ends the user's other sessions, and the obvious move is to copy it. **I
recommend not copying it**, for a reason that is specific to Django rather than to taste:

- Django's session auth hash is an HMAC **over the password field**. A password change
  invalidates every session automatically, which is *why* `reset_password` has to pass
  `keep_session_key` and re-stamp — it is rescuing one session from a logout the framework
  already imposed.
- **Changing the email does not touch the password**, so no session is invalidated by the
  framework. Ending them would be a new, deliberate logout.

The threat ending sessions defends against is *an attacker who already has a session*. But
an attacker with a live session can request a change to their own address and confirm it —
ending sessions at confirm time logs out **the victim**, not the attacker. So it does not
defend the case it appears to, and it does sign out every honest user's other devices for
changing their own address.

**What actually defends that case is the notification to the old address**, which is the
next work item's job, plus the throttle here.

**This is the single decision in this item I most want challenged.** If you prefer sessions
to end, it is a two-line change — `end_other_sessions(user, keep_session_key=...)` after
the commit, exactly as `reset_password` does it — and the screen must then warn first.

## Data Models Affected

### Creates

**`PendingEmailChange`** — `retention_category = ACCOUNT_IDENTITY` (AD-15), `personal`
schema (AD-3), UUIDv7 pk.

| Field | Why |
|---|---|
| `user_id` (UUID, by value) | OQ-8 |
| `new_email` (EmailField, **normalised on write**) | The address being proven. Normalised with `UserManager.normalise_email` so the confirm compares like with like and cannot smuggle a case variant past `user_email_uq`. |
| `token_hash` (char 64, unique), `token_salt` (char 32) | AD-18; no token at rest |
| `expires_at`, `used_at`, `revoked_at`, `created_at` | `PasswordResetToken`'s lifecycle, field for field |

Constraints and indexes, mirroring the precedent:
- `CheckConstraint(~(used_at IS NOT NULL AND revoked_at IS NOT NULL))` — used means the
  login moved; revoked means it did not.
- `Index(["user_id"])` — revoking a user's outstanding requests, and showing them one.
- **No unique constraint on `new_email`.** Two people may both *request* one address; only
  one can *confirm* it, and `user_email_uq` is what decides. A unique constraint here would
  let the first requester deny the address to its real owner.

### Modifies

**Nothing on `User`.** The email column already exists; this changes what may write to it.

## Technical Approach

```
  request_email_change(user_id, new_email, ip_address)
    │ normalise(new_email)
    │ throttle("email_change", ip, account=user's own email digest)   → ThrottledError
    │ new_email == user's current?                                    → ValidationError
    │ taken by another account?  ──────────────► return None  (silent, nothing written)
    │
    ├─ atomic(PERSONAL):
    │    revoke outstanding rows for user_id
    │    create row (digest + salt, expires_at)
    │    write_audit("email_change_requested", details={"method": "token"})
    │
    └─ returns the raw token + both addresses  →  email-change-mails sends:
                                                   confirmation → new address
                                                   warning      → old address

  confirm_email_change(token, now=None)
    └─ atomic(PERSONAL):
         _find_outstanding(token, now)  [select_for_update]   → None: InvalidEmailChangeTokenError
         conditional UPDATE used_at WHERE used_at IS NULL      → 0 rows: same error
         user.email = row.new_email; save(update_fields=["email"])
             └─ IntegrityError on user_email_uq               → same error (race lost)
         write_audit("email_change_confirmed", details={"method": "token"})
```

**`_find_outstanding` is `password_reset`'s `_find_outstanding_token` with a different
model**, including the two properties its docstring explains: `select_for_update()` so two
concurrent confirms serialise rather than both succeeding, and *an expired row does not
stop the scan*, because two rows can share a raw token under different salts.

**Factor it, do not fork it.** The two functions would differ only in the model, and a
copied scan is a copied bug. Extract a shared helper (model + token + now → row) used by
both, and say so in the docstring.

## Security Considerations

- **Enumeration**: the taken-address path returns exactly what the success path returns.
  The *caller* learns nothing; the real owner learns nothing (no mail to the taken
  address — a mail there would itself be the oracle, and a nuisance vector).
- **Timing**: the taken-address path skips a row write and a digest. Treat as acceptable —
  this is the same exposure `request_password_reset` already accepts — but **say so in the
  docstring** rather than leave it unmentioned.
- **No address in audit details, logs or error details** (AD-13).
- **No token anywhere but the link** — not in audit, not in logs, not in the warning mail.
- **The confirm endpoint will be anonymous** (next item), which is why the throttle and the
  single refusal matter more here than in a session-protected command.

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| **`User.save()` normalises email as a backstop** and the command also normalises | Low, but a test must prove a mixed-case new address lands normalised **and** still trips `user_email_uq` against an existing lowercase account | An explicit test for exactly that pair |
| **The race is only testable deliberately** | High — the `IntegrityError` path is the one most likely to be written and never exercised | A test that claims the address *between* request and confirm, and asserts the refusal plus an unchanged login |
| **`update_fields=["email"]`** may bypass intended side effects | Medium | `save()` normalises regardless; assert the stored value, not the call |
| **A 24-hour token is a 24-hour window** on a mailbox that may itself be compromised later | Medium | The number is the lever; it is called out above for your decision |
| **Factoring `_find_outstanding` touches the password-reset path** | Medium — a regression there is a security regression | The reset suite must stay green **unchanged**; no test of it is edited in this item |
| **`transaction.atomic` + `IntegrityError`** leaves the atomic block unusable after the error | Medium — catching it inside the block and continuing silently corrupts the transaction | Catch at the right boundary and re-raise; a test asserts nothing was written |

## Implementation Checklist

- [ ] `AUTH_EMAIL_CHANGE_TOKEN_LIFETIME` in `shared/constants.py` (and the throttle limits)
- [ ] `InvalidEmailChangeTokenError(ValidationError)` in `domain/errors.py`
- [ ] `PendingEmailChange` + one forward-only migration, retention declared
- [ ] Extract the shared outstanding-token scan; **password-reset tests stay green, unedited**
- [ ] `email_change` in `services/throttle.py`'s `LIMITS`
- [ ] `request_email_change`, `confirm_email_change` in `services/email_change.py`
- [ ] Audit rows, inside the transaction, with no address in details
- [ ] Tests: happy path; same-address; taken-address (indistinguishable); supersede;
      expired; revoked; used twice; unknown token; **race lost at confirm**; throttle trips;
      mixed-case normalisation vs `user_email_uq`; old address still signs in after every
      refusal; audit details carry no address
- [ ] `tests/architecture/test_no_direct_writes.py` green
- [ ] Mutation probe per test

---
*Generated by specs.md - fabriqa.ai FIRE Flow | Checkpoint 1 approved: 2026-11-19*
