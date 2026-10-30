---
id: account-auth-core
title: Account & Auth Core (identity services)
intent: onboarding-and-account
complexity: high
mode: validate
status: completed
depends_on: []
created: 2026-10-29
run_id: run-eventpulse24-020
completed_at: 2026-10-29T07:45:51.037Z
---

# Work Item: Account & Auth Core (identity services)

## Description

Builds the `identity` module's account core: the services that create an account, sign a user in and out, and reset a forgotten password. These services are the only route by which a session comes to exist. After this item, `identity` owns `USER` in practice and not just on paper (AD-16).

This item covers the **services and settings**, not the HTTP surface. Item `auth-api-and-session-seam` puts endpoints over them. The split is deliberate. The security properties in this item are enumeration safety, token single-use and expiry, session lifetime and throttling. They need to be pinned at the service layer, where they can be tested without HTTP noise. Services receive explicit arguments, never a `request` (spine: "Auth resolved at the API edge").

AD-18 fixes the MVP sign-in methods: **email and password**, with "single-use, short-lived reset tokens and enumeration-safe responses at the API edge". OIDC is out of scope for this intent.

## Acceptance Criteria

- [ ] **Email is the login.** It is unique **case-insensitively**, so `Maya@Example.com` and `maya@example.com` are one account. A database constraint enforces this, not just a form check. It is stored normalised, and the original casing is not needed.
- [ ] `sign_up(email, password)` creates a `User`. Passwords go through Django's configured hashers and `AUTH_PASSWORD_VALIDATORS`. A weak password is refused with a calm, specific message.
- [ ] **Sign-up is enumeration-safe.** Signing up with an email that already exists does **not** reveal that it exists. The caller gets the same outcome shape as for a new email, and the existing account holder can be notified by transactional email instead. The design doc fixes the exact behaviour.
- [ ] `authenticate(email, password)` returns the user or a single generic failure. A wrong password and an unknown email are **indistinguishable** in result and message. Response timing is also equalised: the unknown-email path still performs a password hash check against a dummy hash. A test proves the unknown-email path calls the hasher.
- [ ] **Password reset request** with an unknown email returns exactly what a known email returns, and sends nothing. With a known email it sends one reset message on the **transactional stream** (AD-20) through the email port, with an idempotency key.
- [ ] **Reset tokens are single-use.** A token that has been used once is refused on a second use.
- [ ] **Reset tokens are short-lived.** The expiry is one named constant in `shared/constants.py`, and an expired token is refused. A test pins the boundary using a fixed clock.
- [ ] A reset **ends the user's other sessions**, so a stolen session does not survive a password change.
- [ ] **Session lifetime is 7 days** (FR-4: "not prompted to re-authenticate within 7 days"). It is one named constant. The cookie is `HttpOnly`, `Secure` outside local, and `SameSite=Lax`.
- [ ] **CSRF is enforced** on state-changing auth operations. The design doc states how the same-origin Next.js proxy and Django's CSRF interact.
- [ ] **Throttling (PRD §11.2: "Rate limiting on all public endpoints (per-IP and per-user)"):** sign-in, sign-up and reset-request are rate-limited per IP and per account identifier. Limits are named constants. A throttled attempt gets a calm 429 that never reveals whether the account exists.
- [ ] **No PII in logs (AD-13).** Emails, passwords and reset tokens never appear in any log line. A test captures the log output of each flow and asserts that the email, password and token are absent.
- [ ] Sign-in records an `identity`-side audit entry by actor id, with no email in it, if the codebase's audit pattern applies to `identity`. The design doc decides.
- [ ] Every new model declares an AD-15 retention category, and `manage.py check` passes.
- [ ] `apps.identity.models` is imported only by `apps.identity`, and `make lint-imports` passes.
- [ ] Every rule above has a test that **can fail**: duplicate email by case, enumeration-safe sign-up and reset, dummy-hash timing path, token reuse, token expiry boundary, session invalidation on reset, throttle trip, and log redaction.

## Technical Notes

**Design doc required (validate).** It must settle at least the following:

- **Token mechanism.** Django's `PasswordResetTokenGenerator` is stateless. It hashes the user's password hash and `last_login`, so it becomes single-use only *because* the password changes. It is not single-use if the reset fails before saving. Its lifetime is `PASSWORD_RESET_TIMEOUT`. The alternative is a stored, hashed, single-use token row. Probe the stdlib behaviour before choosing, and state which property each option actually gives.
- **Throttling store.** Redis is already in the stack. Decide the key shape (IP, normalised email) and how a test pins the limit deterministically.
- **The email field.** `AbstractUser` has `username`. Decide whether `username` is dropped, mirrored or kept unused, and how `USERNAME_FIELD` changes, given `User` is already migrated (run-eventpulse24-002 set `AUTH_USER_MODEL` before the first migration).
- **Where reset mail is rendered,** and the reset-link URL. The link targets the frontend `/reset-password` route on the site's own origin.

The email port (`ports/email.py`) already requires an explicit `stream` with no default. Use `Stream` for transactional mail. Mailpit (`make up`) receives mail locally.

`User` keeps a by-value relationship to everything in `personal` (OQ-8). Nothing in this item adds an FK from `personal` to `User`.

## Dependencies

(none)
