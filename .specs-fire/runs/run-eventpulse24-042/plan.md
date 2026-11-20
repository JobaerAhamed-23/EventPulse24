---
run: run-eventpulse24-042
work_item: pending-email-model-and-commands
intent: account-profile-expansion
mode: validate
checkpoint: plan
---

# Plan: Moving the Login — a Token That Proves the New Address First

**Design approved at checkpoint 1**, with both open questions resolved as recommended:
**24-hour** token lifetime, and **other sessions are not ended**.

## Order of work, and why this order

The shared scan is extracted **first**, while the password-reset suite is the only thing
depending on it. If it were extracted last, a regression in it would surface mixed in
with new failures from new code, and the one suite that proves it still works would be
the one I had just finished editing around.

### 1. Constants and the error

- `shared/constants.py`: `AUTH_EMAIL_CHANGE_TOKEN_LIFETIME = timedelta(hours=24)`, and
  `AUTH_THROTTLE_EMAIL_CHANGE_IP` / `_ACCOUNT` beside the reset limits.
- `domain/errors.py`: `InvalidEmailChangeTokenError(ValidationError)` → 422 via the
  existing map. **Its own class**, so the two flows' refusals cannot be confused.

### 2. Extract the outstanding-token scan — **no behaviour change**

`password_reset._find_outstanding_token` becomes a shared helper taking the model, the
token and `now`, keeping both properties its docstring explains: `select_for_update()`,
and *an expired row does not stop the scan*.

**Gate: the password-reset suite must pass unedited before anything else is written.**
If a single reset test needs changing to accommodate this, the extraction is wrong and I
stop and say so rather than editing the test.

### 3. The model and the migration

`PendingEmailChange` per the design: user by value, normalised `new_email`, digest +
salt, `expires_at` / `used_at` / `revoked_at` / `created_at`, the used-or-revoked check
constraint, a `user_id` index, `retention_category = ACCOUNT_IDENTITY`, UUIDv7 pk,
`personal` schema. One forward-only migration. **No unique constraint on `new_email`** —
`user_email_uq` arbitrates, and a unique here would let a squatter deny a real owner.

### 4. The throttle

`email_change` into `services/throttle.py`'s `LIMITS`. Keyed on **the account's own**
address digest, not the requested one.

### 5. The commands — `services/email_change.py`

`request_email_change` → throttle, reject same-address, **silent return** when taken,
then atomic: revoke outstanding, create row, audit. Returns the raw token and both
addresses for the mail item; **sends nothing**.

`confirm_email_change` → atomic: locate, conditional `UPDATE used_at WHERE used_at IS
NULL`, move the login, audit. `IntegrityError` on `user_email_uq` → the same refusal.

### 6. Tests, then mutation probes

Happy path; same address; taken address **indistinguishable from success**; supersede;
expired; revoked; replayed; unknown; **race lost at confirm**; throttle trips;
mixed-case normalisation vs `user_email_uq`; old address still signs in after every
refusal; audit details carry no address; `test_no_direct_writes` green.

Then a mutation per test, because a test that cannot fail is not evidence.

## What I will stop and report rather than work around

- A password-reset test needing an edit (step 2's gate)
- The `IntegrityError` path proving untestable without touching product code
- Any need to widen the logger allowlist or put an address in audit details

## Files

| File | Action |
|---|---|
| `backend/shared/constants.py` | modify — lifetime + throttle limits |
| `backend/domain/errors.py` | modify — `InvalidEmailChangeTokenError` |
| `backend/apps/identity/services/password_reset.py` | modify — use the extracted scan |
| `backend/apps/identity/services/tokens.py` | create — the shared scan |
| `backend/apps/identity/models.py` | modify — `PendingEmailChange` |
| `backend/apps/identity/migrations/00XX_…` | create |
| `backend/apps/identity/services/throttle.py` | modify — `email_change` |
| `backend/apps/identity/services/email_change.py` | create — both commands |
| `backend/tests/identity/test_email_change.py` | create |

**No API layer, no mails, no UI** — those are the next three items.
