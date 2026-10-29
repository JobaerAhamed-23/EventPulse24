---
work_item: account-auth-core
intent: onboarding-and-account
created: 2026-10-29
mode: validate
checkpoint_1: approved
---

# Design: Account & Auth Core (identity services)

## Summary

This item builds the `identity` module's account core: the services that create an account,
sign a user in and out, and reset a forgotten password. These services are the only route by
which a session comes to exist. After this item, `identity` owns `USER` in practice and not
just on paper (AD-16).

The item covers the **services and settings**, not the HTTP surface. `auth-api-and-session-seam`
puts endpoints over them. The split is deliberate: the security properties here — enumeration
safety, token single-use and expiry, session lifetime, throttling — are pinned at the service
layer, where they are tested without HTTP noise. Services receive explicit arguments, never a
`request` (spine: "Auth resolved at the API edge").

Four decisions carry the item:

1. **The email is the login**, unique case-insensitively, enforced by a database constraint.
2. **Reset tokens are stored, hashed, single-use rows** — not Django's stateless generator
   (D1–D3 below).
3. **Throttling lives in a new port** (`ports.throttle`) with an in-memory fake, so a test can
   pin the limit deterministically without Redis (D8).
4. **The session is Django's**, configured for a 7-day lifetime with hardened cookie flags
   (D12).

## Scope

**In Scope:**

- `User` model changes: drop `username`, make `email` the login field, add a case-insensitive
  unique constraint (D4–D6).
- `PasswordResetToken` model: a stored, hashed, single-use, expiring token row (D2–D3).
- `IdentityAuditEntry` model: the `identity`-owned audit table (D14).
- Service layer in `apps/identity/services/`:
  - `sign_up.py` — enumeration-safe account creation.
  - `authenticate.py` — timing-equalised sign-in with a dummy-hash path.
  - `password_reset.py` — reset request, token consumption, session invalidation.
  - `session.py` — sign-out and session lifetime helpers.
  - `throttle.py` — the throttle check used by the three public auth operations.
  - `audit.py` — the `identity` audit writer (AD-5).
- `ports/throttle.py` — a new port (D8).
- `adapters/throttle/memory.py` — the in-memory fake adapter.
- `config/adapters.py` — the `throttle` entry in the fake and real tables.
- `shared/constants.py` — the named constants (reset token lifetime, session lifetime,
  throttle limits, dummy hash) (D7, D8, D12).
- `shared/errors.py` — no change; the existing domain errors cover it.
- Settings: `SESSION_COOKIE_*`, `CSRF_*`, `PASSWORD_HASHERS` unchanged (D12, D13).
- Tests under `backend/tests/identity/`.

**Out of Scope:**

- Every HTTP endpoint (`auth-api-and-session-seam`) — this item writes no route handler.
- The session seam replacement in `apps/personalization/auth.py` (next item).
- OIDC social sign-in (AD-18 defers it).
- The `SUBSCRIPTION` entity and the Pro tier.
- Calendar credentials and encryption (AD-18's other half, `calendar-connection-model`).

## Key Decisions

### The token mechanism (D1–D3)

The work item requires probing Django's `PasswordResetTokenGenerator` before choosing. The
probe was run against **Django 6.1.2**, the pinned version, and the results are decisive.

**What the probe found:**

| Question | Answer | Evidence |
|----------|--------|----------|
| What is hashed? | `pk + password + last_login + timestamp + email` | `PasswordResetTokenGenerator._make_hash_value` |
| Is the token single-use? | **No.** Two consecutive `check_token` calls with no state change both return `True`. | Probe: `first check: True`, `second check (no state change): True` |
| Does a password change invalidate it? | Yes. | Probe: after changing `user.password`, `check_token` returns `False` |
| Does an email change invalidate it? | Yes (Django 6.1 added the email to the hash). | Probe: after changing `user.email`, `check_token` returns `False` |
| Does it expire? | Yes, via `settings.PASSWORD_RESET_TIMEOUT` (Django's default is `259200` seconds = 3 days). | Probe: a token stamped 5 days ago is refused; 2 days ago is accepted. |

**D1. Django's stateless generator is not single-use.** It becomes single-use *only* because the
password changes — and the work item is explicit that this is not enough: the token is not
single-use if the reset fails before saving, and the token can be replayed any number of times
between issuance and use. The probe confirms this directly: the second `check_token` call
returns `True` without any state change. A stateless token also cannot be revoked
individually, cannot be listed for a user's outstanding resets, and cannot be counted for
throttling.

**D2. A stored, hashed token row is the mechanism.** Each reset request creates one
`PasswordResetToken` row holding the **hash** of a random token, never the token itself. The
row carries `user_id`, `token_hash`, `expires_at`, `used_at` and `created_at`.

The properties this gives, each of which the work item requires:

| Required property | How the stored row delivers it |
|-------------------|-------------------------------|
| Single-use | `used_at IS NULL` is checked and set in the **same transaction** that consumes it. A second attempt finds `used_at` set and refuses. Unlike the stateless generator, this holds even when the reset fails before saving, because the consumption is its own committed step. |
| Short-lived | `expires_at` is computed from a named constant at issue time. The expiry check is a comparison against the supplied clock, so a test pins the boundary exactly. |
| Revocable | A row can be revoked (`revoked_at`) without touching the password. Used when a reset ends the user's other sessions and when a user requests a second reset while one is outstanding. |
| No token at rest | Only the hash is stored. A database dump does not yield a usable reset link. |

**D3. The stored row replaces Django's generator entirely.** We do not use
`PasswordResetTokenGenerator` at all. Mixing the two would give two expiry rules and two
notions of "used". The token is `secrets.token_urlsafe(32)` — 256 bits of entropy from the
OS CSPRNG — stored as a SHA-256 hash with a per-row salt, compared in constant time.

The hash is salted per row (`sha256(salt + token)`), so two users with the same reset token
value would not collide, and a leaked table could not be attacked with precomputed digests of
the token space. The comparison uses `secrets.compare_digest`.

**Why not a JWT or an unsigned token?** A signed token has the same single-use problem: signing
proves authenticity, not uniqueness of use. Storing a row is the only way to answer "has this
token been used?".

### The email field (D4–D6)

`User` currently extends `AbstractUser`, which has `username` as the login field, and
`AUTH_USER_MODEL = "identity.User"` was set **before** the first migration
(run-eventpulse24-002), so the table exists and has rows in principle.

**D4. `username` is dropped; `email` becomes the login field.** The work item requires email to
be the login, unique case-insensitively. The options were: drop `username`, mirror it, or keep
it unused.

- *Mirror* (`username` = the normalised email) keeps `AbstractUser`'s `username` machinery
  working — `UserManager.get_by_natural_key`, `createsuperuser`, the admin's username field —
  but stores the email twice, in two columns that can drift.
- *Keep unused* leaves a `username` column that is unique, required by the admin, and
  meaningless. The admin would ask for a username that the product never uses.
- *Drop* removes the column entirely and points `USERNAME_FIELD` at `email`.

**Drop is chosen.** The product has one identity concept — the email — and the sign-up form
has no username field. `AbstractUser` is not a hard requirement: Django's `AbstractBaseUser`
plus `PermissionsMixin` gives everything the project needs (`is_staff`, `is_superuser`,
`is_active`, `groups`, `user_permissions`), and `USERNAME_FIELD = "email"` with
`REQUIRED_FIELDS = []` makes `createsuperuser` ask for an email and a password.

The migration **removes** `username` and **adds** a non-null `email`. The existing
`0001_initial` migration is already applied, so this is a new `0002` migration — forward-only,
as the constitution requires.

**D5. The email is stored normalised, and uniqueness is case-insensitive at the database level.**
The work item requires: "It is unique **case-insensitively**… A database constraint enforces
this, not just a form check."

Two mechanisms are needed, and they are not alternatives:

- **Storage normalisation** — the stored value is lowercased and trimmed. The original casing
  is not needed (the work item says so), so it is not stored. `email = email.strip().lower()`
  at the command boundary, before the write.
- **A database constraint** — a `UniqueConstraint` on `email`. Because the value is normalised
  on the way in, a plain unique index *is* a case-insensitive unique index: `Maya@Example.com`
  is stored as `maya@example.com`, so it collides with the existing `maya@example.com` row.

The constraint is what makes this a real guarantee rather than a form check: two concurrent
sign-ups for `Maya@Example.com` and `maya@example.com` race, and the database refuses the
second insert. The service layer catches `IntegrityError` and converts it to the
enumeration-safe outcome. This is exactly the pattern the ingestion code uses for source
dedup.

**D6. `UserManager` is replaced with an email-keyed manager.** Django's `UserManager` keys
on `username`. `apps/identity/managers.py` defines `UserManager(BaseUserManager)` overriding
`get_by_natural_key` to look up by `email`, plus `create_user` / `create_superuser` that
require an email and take `email` as the first argument. `User.objects` uses it. The admin
(`admin.py`) registers `User` with `email` as the `USERNAME_FIELD`, which Django's admin
already handles.

### The throttle store (D7–D8)

The work item requires rate limiting on sign-in, sign-up and reset-request, **per IP and per
account identifier**, with named constants, and a 429 that never reveals whether the account
exists.

**D7. Two keys per operation.** The throttle check takes two independent keys:

- **Per IP** — key `auth:{op}:ip:{ip}`. Protects against one host spraying many accounts.
- **Per account identifier** — key `auth:{op}:acct:{normalised_email}`. Protects against one
  account being sprayed from many hosts.

Both are checked. Either tripping is a 429. The per-account key is keyed on the **normalised**
email, so `Maya@Example.com` and `maya@example.com` share one bucket — otherwise the
per-account limit would be trivially bypassed by varying the casing.

**The identifier key is hashed before it becomes a Redis key.** A Redis key containing a raw
email would put the email in Redis, in `KEYS` output, and in any monitoring dashboard — which
AD-13 forbids. The key uses a SHA-256 digest of the normalised email instead. The digest is
one-way for an email (the input space is small, so it is *not* a secret — it is a key-hygiene
measure, not a confidentiality measure). The raw email never becomes a key, a log field or a
redis key.

**D8. A new `ports.throttle` port, with an in-memory fake.** Redis is already in the stack,
but the throttle needs to be testable deterministically, and the work item says so explicitly:
"how a test pins the limit deterministically."

- *Using Redis directly* would make every throttle test depend on Redis, and would make the
  "trip the limit" test a timing exercise. It would also break the project's rule that apps
  reach adapters only through ports.
- *A new port* matches how every other external dependency in this codebase is reached
  (`ports.email`, `ports.calendar`, `ports.fetch`, …). The app calls
  `ports.registry.get_throttle_port()`; the adapter is chosen by `settings.ADAPTERS`.

`ports/throttle.py` defines a `ThrottlePort` ABC over frozen dataclasses
(`ThrottleDecision(allowed: bool, retry_after_seconds: int)`). The port has one operation:
`check(key: str, limit: int, window_seconds: int) -> ThrottleDecision`.

The **in-memory fake** (`adapters/throttle/memory.py`) keeps a dict of key → list of timestamps
and a `now` callable the test controls. A test injects a fixed clock, calls the operation
`limit` times, and asserts the `(limit + 1)`-th call is refused. No sleeping, no Redis, no
timing flake. The fake is the default in `ADAPTER_MODE=fake`; the real adapter
(`adapters/throttle/redis.py`) uses `redis` with `INCR` + `EXPIRE`.

Because the fake owns the clock, the throttle decision is deterministic and the test can pin
the boundary exactly, which is what the work item asks for.

**The limits are named constants** in `shared/constants.py`:

| Constant | Value | Meaning |
|----------|-------|---------|
| `AUTH_THROTTLE_SIGN_IN_IP` | 10 | Sign-in attempts per IP per window |
| `AUTH_THROTTLE_SIGN_IN_ACCOUNT` | 5 | Sign-in attempts per account per window |
| `AUTH_THROTTLE_SIGN_UP_IP` | 5 | Sign-up attempts per IP per window |
| `AUTH_THROTTLE_SIGN_UP_ACCOUNT` | 3 | Sign-up attempts per account per window |
| `AUTH_THROTTLE_RESET_IP` | 5 | Reset requests per IP per window |
| `AUTH_THROTTLE_RESET_ACCOUNT` | 3 | Reset requests per account per window |
| `AUTH_THROTTLE_WINDOW_SECONDS` | 3600 | The window all of the above use (1 hour) |

The per-account sign-up limit is 3 (lower than sign-in's 5): sign-up is the enumeration-prone
one, and an attacker enumerating addresses should hit the wall sooner.

### Session lifetime and cookies (D12)

**D12. The session is Django's, configured for 7 days.** FR-4: "not prompted to re-authenticate
within 7 days". The session lifetime is one named constant.

- `SESSION_COOKIE_AGE = AUTH_SESSION_LIFETIME` (7 days).
- `SESSION_SAVE_EVERY_REQUEST = False` — the session's expiry is set at login, not slid on
  every request. A sliding session would mean a stolen session that is actively used never
  expires, which is exactly the property "a reset ends the user's other sessions" relies on
  not being undermined.
- `SESSION_EXPIRE_AT_BROWSER_CLOSE = False` — the session must outlive the browser, or the
  7-day guarantee fails on every browser restart.
- `SESSION_COOKIE_HTTPONLY = True` — JavaScript cannot read the session id.
- `SESSION_COOKIE_SECURE = not DEBUG` — secure outside local. The work item names this
  explicitly.
- `SESSION_COOKIE_SAMESITE = "Lax"` — the work item names this explicitly. `Lax` allows the
  top-level GET navigation a user does when clicking the link in a reset email, and blocks
  cross-site POSTs, which is the CSRF-relevant case.

The `HttpOnly` / `Secure` / `SameSite` flags are asserted by a test reading
`django.conf.settings`, so a change to any of them fails the suite.

### CSRF (D13)

**D13. CSRF is Django's, and the frontend origin is trusted through `CSRF_TRUSTED_ORIGINS`.**

The coding standards record the exact problem (recorded in run-eventpulse24-008): "the browser
calls `/api/…` on the frontend's own origin; `frontend/proxy.ts` forwards it to
`API_BASE_URL`… Django's CSRF origin check compares `Origin` with its own host, so a POST is
rejected unless the frontend origin is in `CSRF_TRUSTED_ORIGINS` (from env), or
`USE_X_FORWARDED_HOST` is enabled deliberately (only behind the trusted proxy). **Decide this
in the auth intent.**"

The decision:

- **`CSRF_TRUSTED_ORIGINS` is the mechanism.** The frontend's origin(s) are added from
  configuration. `config/env.py` gains `csrf_trusted_origins: Annotated[list[str], NoDecode] = []`,
  parsed as a comma-separated list, and `config/settings.py` sets
  `CSRF_TRUSTED_ORIGINS = env.csrf_trusted_origins`.
- **`USE_X_FORWARDED_HOST` stays `False`.** Enabling it would make Django trust the
  `Host` header, which is exactly what an attacker controls. `CSRF_TRUSTED_ORIGINS` is an
  explicit allowlist of origins, which is the safer mechanism and is the one the standards
  recommend first.
- **The cookie is read by the browser and sent to the frontend origin**, which proxies it. The
  proxy must forward the `Cookie` and `X-CSRFToken` headers. The proxy's configuration is the
  next item's business (`auth-api-and-session-seam`); this item settles the **backend**
  mechanism and records the frontend requirement.

The work item says "The design doc states how the same-origin Next.js proxy and Django's CSRF
interact." That is this section: the browser holds the CSRF cookie on the frontend's own
origin (first-party, so `SameSite=Lax` permits it), the frontend proxy forwards both the
cookie and the `X-CSRFToken` header, and Django validates the token against the cookie and
the `Origin` header — which is why the frontend origin must be in `CSRF_TRUSTED_ORIGINS`.

### Audit (D14)

**D14. `identity` gets its own audit table, and the audit pattern applies.**

The work item says: "Sign-in records an `identity`-side audit entry by actor id, with no email
in it, **if the codebase's audit pattern applies to `identity`**. The design doc decides."

The codebase's pattern is clear and consistent: `ingestion` has `IngestionAuditEntry`,
`personalization` has `PersonalizationAuditEntry`, `delivery` has its own. AD-5 requires "one
concrete table per owning app, so it sits in that app's schema, its owner is the only writer
(AD-16)". `identity` owns the auth flows, so **the pattern applies**. This item adds
`IdentityAuditEntry(AuditEntry)` with `retention_category = RetentionCategory.AUDIT_LOG`, and
`apps/identity/services/audit.py` with the same `write_audit` guard the other two apps use
(`AuditOutsidePersonalTransaction` → `AuditOutsideIdentityTransaction`): the audit row is
written in the same transaction as the mutation, or not at all.

Sign-in is audited with `actor_kind=user`, `actor_id=<the user's uuid>`, `action="sign_in"`,
`target_type="User"`, `target_id=<the user's uuid>`. **No email appears** — the actor is stored
by value as a UUID, exactly as AD-13 requires. `details` carries `{"method": "password"}`, a
count-like value, never free text.

Sign-up, sign-out and password reset are audited too, with the same rule: actor id, no email.

### Enumeration safety (D15–D17)

**D15. Sign-up is enumeration-safe.** Signing up with an email that already exists does not
reveal that it exists.

The mechanism: the sign-up service always returns the same outcome shape — the same result
type, the same fields — whether or not the address was already taken. When the address is
already taken, the service **does not raise** and **does not create** a user. Instead it
enqueues a transactional email to the existing account holder saying "someone tried to create
an account with this address" (a standard "email already in use" notification, which is the
only way the existing holder learns of it).

Because the outcome is identical, there is nothing for the caller to distinguish. The only
observable difference is the email that arrives — which goes to the account holder, not to the
caller. The work item's requirement is met exactly: "The caller gets the same outcome shape
as for a new email, and the existing account holder can be notified by transactional email
instead."

The write path distinguishes the two cases **internally** — a duplicate raises `IntegrityError`
from the unique constraint, which the service catches — but the catch does not change the
return value.

**D16. Authentication is timing-equalised.** A wrong password and an unknown email are
indistinguishable in result, in message, and in response time.

The mechanism is the **dummy hash path**, which the work item names: "the unknown-email path
still performs a password hash check against a dummy hash. A test proves the unknown-email path
calls the hasher."

`authenticate(email, password)`:

1. Normalise the email.
2. Look up the user. If **not found**, take the dummy path: call
   `check_password(password, DUMMY_PASSWORD_HASH)` against a precomputed hash of a random
   password, then return the generic failure.
3. If **found**, call `check_password(password, user.password)`. If it is wrong, return the
   generic failure.
4. If it is right, return the user.

Both paths perform exactly one password hash. The dummy hash is computed once at import time
from a random password, so its cost equals a real check.

**It lives in `apps/identity/services/authenticate.py`, not `shared/constants.py`.**
`shared/constants.py` must stay stdlib-only: `domain` imports it, and the `domain-pure`
import-linter contract forbids `django` in `domain`, so a Django import there would break the
contract transitively. The dummy hash needs `django.contrib.auth.hashers.make_password`, so it
belongs in the app.

The test proves it: the test monkeypatches `django.contrib.auth.hashers.check_password` with
a recorder and asserts it was called on the unknown-email path. That is the assertion the work
item asks for, and it is a real one — it fails if someone "optimises" the unknown path by
returning early.

The generic failure is one message for both cases: `"That email and password don't match."`
The domain error is `AuthenticationFailedError`, a subclass of `domain.errors.ValidationError`,
so it maps to a 401 at the API edge through the existing handler in `config/errors.py`.

**D17. The reset request is enumeration-safe.** A reset request for an unknown email returns
exactly what a known email returns, and sends nothing. For a known email it sends exactly one
reset message on the **transactional** stream through the email port, with an idempotency key.

The service always returns the same result. The difference is internal: for a known email a
`PasswordResetToken` row is created and one email is sent; for an unknown email nothing
happens at all — no row, no send.

The idempotency key is minted with `shared.constants.SEND_KEY_SEPARATOR` (`:`), per AD-7, and
is built from ids only: `auth_reset:{token_id}`. It never contains the email or the token.

### The email content and the reset link (D18)

**D18. The reset link targets the frontend's `/reset-password` route on the site's own origin.**

The email is rendered from a template in `apps/identity/templates/identity/`. The reset link
is `{FRONTEND_BASE_URL}/reset-password?token={token}`. The frontend base URL comes from
configuration (`config/env.py` gains `frontend_base_url`), because the API runtime and the
frontend are different origins.

The **raw token appears in the email body and in the URL**. That is unavoidable — the user has
to follow the link — but it appears nowhere else: not in a log line, not in the audit row, not
in the stored row (only the hash is stored). The reset URL is built inside the email adapter
boundary, and the token is passed to the adapter as part of the message body, which the
adapter's allowlist never logs.

The email carries the **transactional** stream (`Stream.TRANSACTIONAL`) — AD-20: "transactional
mail" — and an `idempotency_key`. The body is plain text with no template engine
dependency beyond Django's own template engine, which is already configured.

### The password policy (D19)

**D19. Django's `AUTH_PASSWORD_VALIDATORS` are used unchanged, and their messages are
calm.** The validators are already configured in `settings.py`:
`UserAttributeSimilarityValidator`, `MinimumLengthValidator`, `CommonPasswordValidator`,
`NumericPasswordValidator`.

The work item asks for "a calm, specific message". Django's `MinimumLengthValidator` message
is "This password is too short. It must contain at least 8 characters." — calm and specific.
`UserAttributeSimilarityValidator`'s message mentions the email attribute ("too similar to your
email address") — which names the email in the message. That message goes to the user who is
signing up (who supplied the email), so it is not a disclosure to a third party. But it *is*
the email address in a message body, and if the message were ever logged, it would leak. The
sign-up service raises a domain `ValidationError` carrying the validator's messages, and the
messages reach the user through the API response — they are never logged.

A weak password is refused **before** the user row is created. The password never reaches a
log line, and never reaches the audit row.

### Services take explicit arguments (D20)

**D20. No service receives a `request`.** This is the spine's "Auth resolved at the API edge":
services receive explicit arguments, never a `request`.

The signatures:

```python
def sign_up(*, email: str, password: str, ip_address: str | None = None) -> SignUpOutcome
def authenticate(*, email: str, password: str, ip_address: str | None = None) -> User
def request_password_reset(*, email: str, ip_address: str | None = None) -> None
def reset_password(*, token: str, new_password: str) -> User
def sign_out(*, user: User) -> None
```

`ip_address` is passed in from the API edge (which reads it from the request) and is used only
for the throttle key. It is never used for anything else, and it is never logged.

## Data Models Affected

### Creates

- **`PasswordResetToken`** — `user_id` (UUID, by value), `token_hash` (char 64, the SHA-256
  hex digest), `token_salt` (char 32, hex — the per-row salt), `expires_at` (timestamptz),
  `used_at` (timestamptz, NULL), `revoked_at` (timestamptz, NULL), `created_at`.
  Unique: `(token_hash)`. Index: `(user_id)`. Retention: `ACCOUNT_IDENTITY`.
  A check constraint keeps `used_at` and `revoked_at` from both being set.

- **`IdentityAuditEntry`** — the concrete audit table; `at`, `action`, `target_type`,
  `target_id`, `details`, `actor_kind`, `actor_id`, `actor_label`.
  Retention: `AUDIT_LOG`.

### Modifies

- **`User`** — `username` removed; `email` becomes NOT NULL, unique and the `USERNAME_FIELD`;
  `USERNAME_FIELD = "email"`, `REQUIRED_FIELDS = []`; `objects = UserManager()`.
  The `email` column's original casing is not stored (normalised on write).
  Retention: `ACCOUNT_IDENTITY` (unchanged).

**Migration `identity/0002_*`** — removes `username`, alters `email`, adds the unique
constraint, creates `passwordresettoken` and `identityauditentry`, and adds the audit
table's append-only trigger and runtime-role grants, exactly as `personalization/0001_initial`
does.

## Technical Approach

### Architecture

```
                        the API edge (auth-api-and-session-seam — NEXT ITEM)
                          │  resolves the request, extracts the IP, calls a service
                          ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │  apps/identity/services/                                              │
   │                                                                        │
   │   sign_up              authenticate          request_password_reset      │
   │     │                     │                        │                   │
   │     │  throttle           │  throttle              │  throttle          │
   │     ▼                     ▼                        ▼                   │
   │   ports.throttle ─────────┴────────────────────────┘                   │
   │     (get_throttle_port())                                            │
   │                                                                        │
   │   reset_password                                                 │
   │     └─► consumes the token row, ends the other sessions              │
   │                                                                        │
   │   sign_out ──► ends the session                                      │
   │                                                                        │
   │   audit.write_audit ──► IdentityAuditEntry (in the same transaction)  │
   └──────────────────────────────────────────────────────────────────────────┘
        │                    │                    │
        ▼                    ▼                    ▼
   User (personal)   PasswordResetToken    ports.email
                       (personal)            └─► Stream.TRANSACTIONAL
                                                 (one reset message,
                                                  idempotency_key)
```

### The reset-token state machine

```
                    request_password_reset(email)
                              │
                              ▼
                  throttle.check(ip, acct)  ──► 429 if tripped
                              │
                              ▼
                  user = find_by_normalised_email(email)
                              │
                  ┌───────────┴───────────┐
                  │                       │
              not found                found
                  │                       │
                  ▼                       ▼
             (nothing)          PasswordResetToken row created
             (returns the       token = secrets.token_urlsafe(32)
              same result)      salt  = secrets.token_hex(16)
                               hash  = sha256(salt + token)
                               expires_at = now + AUTH_RESET_TOKEN_LIFETIME
                              │
                              ▼
                       one email, Stream.TRANSACTIONAL,
                       idempotency_key = "auth_reset:{id}"

                   reset_password(token, new_password)
                              │
                              ▼
                  row = find_by_hash(hash_of(token))
                              │
                  ┌───────────┴───────────┐
                  │                       │
           not found / used /         found and valid
           revoked / expired              │
                  │                       ▼
                  ▼                  consume (set used_at)
             generic failure             │
                                          ▼
                                  validate new password
                                          │
                                          ▼
                                  set the new password
                                          │
                                          ▼
                                  end the user's OTHER sessions
                                          │
                                          ▼
                                  audit write
```

### The throttle key shape

```
auth:{operation}:ip:{ip_address}          # the IP, as given by the edge
auth:{operation}:acct:{sha256(email)}     # the digest, never the raw email
```

`{operation}` is one of `sign_in`, `sign_up`, `reset`.

### The constants (all in `shared/constants.py`)

| Constant | Value | Purpose |
|----------|-------|---------|
| `AUTH_SESSION_LIFETIME` | `timedelta(days=7)` | FR-4's 7 days. One named constant. |
| `AUTH_RESET_TOKEN_LIFETIME` | `timedelta(minutes=30)` | The reset token's short life. |
| `AUTH_THROTTLE_WINDOW_SECONDS` | `3600` | The throttle window. |
| `AUTH_THROTTLE_SIGN_IN_IP` | `10` | Per IP, per window. |
| `AUTH_THROTTLE_SIGN_IN_ACCOUNT` | `5` | Per account, per window. |
| `AUTH_THROTTLE_SIGN_UP_IP` | `5` | Per IP, per window. |
| `AUTH_THROTTLE_SIGN_UP_ACCOUNT` | `3` | Per account, per window. |
| `AUTH_THROTTLE_RESET_IP` | `5` | Per IP, per window. |
| `AUTH_THROTTLE_RESET_ACCOUNT` | `3` | Per account, per window. |
| `DUMMY_PASSWORD_HASH` | a hash of a random password | The equalisation hash. |

The reset token lifetime is 30 minutes. Django's own default is 3 days; a password reset link
is a bearer credential for the account, and a short life shrinks the window in which a token
sits in a mailbox or a proxy log. The work item requires "short-lived" and one named
constant, and says nothing about the value — 30 minutes is a defensible default for an MVP
and is trivially changed in one place.

## Affected Files

| File | Action | Purpose |
|------|--------|---------|
| `backend/apps/identity/models.py` | Modify | `User` changes; `PasswordResetToken`, `IdentityAuditEntry` |
| `backend/apps/identity/managers.py` | Create | `UserManager` keyed on email |
| `backend/apps/identity/services/__init__.py` | Modify | Export the service functions |
| `backend/apps/identity/services/sign_up.py` | Create | Enumeration-safe sign-up |
| `backend/apps/identity/services/authenticate.py` | Create | Timing-equalised sign-in |
| `backend/apps/identity/services/password_reset.py` | Create | Request, consume, expire |
| `backend/apps/identity/services/session.py` | Create | Sign-out, session lifetime |
| `backend/apps/identity/services/throttle.py` | Create | The throttle check |
| `backend/apps/identity/services/audit.py` | Create | The `identity` audit writer |
| `backend/apps/identity/services/emails.py` | Create | Reset-mail rendering |
| `backend/apps/identity/templates/identity/password_reset.txt` | Create | The reset mail body |
| `backend/apps/identity/migrations/0002_*.py` | Create | The schema change |
| `backend/apps/identity/admin.py` | Modify | Register `User` by email |
| `backend/ports/throttle.py` | Create | The throttle port |
| `backend/ports/registry.py` | Modify | `get_throttle_port()` + `PORT_KEYS` |
| `backend/adapters/throttle/memory.py` | Create | The in-memory fake |
| `backend/adapters/throttle/redis.py` | Create | The Redis adapter |
| `backend/adapters/throttle/__init__.py` | Create | Package marker |
| `backend/config/adapters.py` | Modify | The `throttle` entries |
| `backend/config/settings.py` | Modify | Session cookie settings, `CSRF_TRUSTED_ORIGINS` |
| `backend/config/env.py` | Modify | `csrf_trusted_origins`, `frontend_base_url` |
| `backend/shared/constants.py` | Modify | The named constants |
| `backend/tests/identity/test_sign_up.py` | Create | Enumeration safety, case-insensitive uniqueness |
| `backend/tests/identity/test_authenticate.py` | Create | The dummy-hash path, the generic failure |
| `backend/tests/identity/test_password_reset.py` | Create | Single-use, expiry, session invalidation |
| `backend/tests/identity/test_throttle.py` | Create | The throttle trips |
| `backend/tests/identity/test_session_settings.py` | Create | The cookie flags and the 7-day lifetime |
| `backend/tests/identity/test_log_redaction.py` | Create | No email, password or token in a log line |
| `backend/tests/identity/test_audit.py` | Create | The audit row, no email in it |
| `backend/tests/identity/factories.py` | Create | A `User` factory |
| `backend/tests/architecture/test_import_contracts.py` | Modify | The new port/adapter contracts |

## Security Considerations

- **No PII in logs.** The email, the password and the raw token never appear in a log line.
  The log-redaction test captures the serialised output of each flow through the JSON
  formatter and asserts the email, the password and the token are absent. The throttle keys
  carry a digest, not the email. The audit rows carry a UUID, not the email.
- **The token is never stored.** Only `sha256(salt + token)` is stored. A database dump
  yields no usable reset link.
- **The reset token is compared in constant time** (`secrets.compare_digest`), so a timing
  attack cannot recover the token byte by byte.
- **The session cookie is `HttpOnly`, `Secure` outside local, `SameSite=Lax`.** A test asserts
  all three.
- **The reset ends the other sessions.** `reset_password` deletes the user's other session
  rows, so a stolen session does not survive a password change. The current session is
  rotated (a new session key) rather than deleted, so the user stays signed in on the device
  they reset from.
- **The enumeration-safe paths are equal in more than message.** Sign-up returns the same
  outcome shape. Sign-in performs one hash on both paths. Reset sends nothing for an unknown
  address.
- **The throttle never reveals account existence.** A 429 is returned for a tripped limit
  regardless of whether the account exists — the throttle check runs **before** the account
  lookup.

## Integration Points

| System | Type | Purpose |
|--------|------|---------|
| `ports.email` | Call | One reset message on `Stream.TRANSACTIONAL` with an idempotency key (AD-20). |
| `ports.throttle` | Call (new) | The per-IP and per-account limits. |
| `domain.errors` | Raise | `ValidationError` subclasses, mapped once in `config/errors.py`. |
| `shared.actor` | Use | `Actor.user(uuid)` — the actor is stored by value. |
| `shared.constants` | Use | Every named constant lives there (AD-8, AD-16). |
| `apps.personalization.auth` | Replaced next | The seam this item's sessions feed. |
| `django.contrib.auth` | Use | `AbstractBaseUser`, `PermissionsMixin`, `check_password`, `make_password`, the password validators. |

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Removing `username` from `User` breaks `createsuperuser`, the admin, or any code reading `user.username`. | High — the admin is the MVP editorial surface (AD-14). | `UserManager` overrides `create_superuser` to take an email; the admin registers `User` with `USERNAME_FIELD = "email"`. A test creates a superuser with an email and asserts it authenticates. A structural test asserts no code outside `apps.identity` reads `username`. |
| The migration removes `username` from a table that may already have rows. | High — a non-null column cannot be removed from a populated table without a default. | The migration is forward-only and does the removal and the `email` alteration in one step, with `email` backfilled from `username` for any pre-existing row before it is made NOT NULL. A test asserts the migration applies cleanly. In practice the table is empty (no sign-up path existed), but the migration must not assume that. |
| The throttle's per-account key is a digest of the email, and a digest of a small input space is reversible by brute force. | Low — the digest is a key-hygiene measure, not a confidentiality measure. | Documented as such in the code. The digest's purpose is to keep the email out of Redis keys and monitoring output, not to hide it from someone who already has the Redis dump. If Redis itself is compromised, the email is not the secret at risk; the reset tokens and the calendar credentials are, and neither is in a Redis key. |
| The throttle's Redis adapter is not exercised by the test suite, so it could be broken. | Medium — a broken Redis adapter means no rate limiting in production. | The adapter is written against a small, well-defined port interface and the port's contract is fully tested through the fake. The Redis adapter gets its own focused test with a fake Redis client, asserting the `INCR`/`EXPIRE` sequence and the decision. |
| `DUMMY_PASSWORD_HASH` is a fixed value in the source tree. | Low — it is not a secret; it is a hash of a random password used only for timing equalisation. | It never authenticates anything. It is a constant because the alternative (computing it per call) would defeat the purpose. A test asserts the unknown-email path calls the hasher with it. |
| The `email` unique constraint is on the **normalised** value, so a row written outside the service layer with a mixed-case email would bypass it. | Medium — two accounts could exist for one address. | The service is the only writer (AD-5, AD-16). The model normalises in `save()` as a backstop, so even a direct write is normalised before the constraint is evaluated. A test writes a mixed-case email directly and asserts the stored value is normalised and the constraint holds. |
| The throttle check runs before the account lookup, so a tripped throttle reveals nothing — but a *non-tripped* throttle followed by an unknown email returns the generic failure, which is right. | Low | Covered by the enumeration-safety tests. |
| Removing `username` from `AbstractUser` means `django.contrib.auth` views (`LoginView`) need `USERNAME_FIELD` set on the model, which it is. | Low — the Django auth views are not used; the project has its own API. | `USERNAME_FIELD = "email"` on the model satisfies them regardless. |

## Implementation Checklist

1. `shared/constants.py`: `AUTH_SESSION_LIFETIME`, `AUTH_RESET_TOKEN_LIFETIME`,
   `AUTH_THROTTLE_WINDOW_SECONDS`, the six throttle limits, `DUMMY_PASSWORD_HASH`.
2. `ports/throttle.py`: the `ThrottlePort` ABC, `ThrottleDecision`, the `ThrottleKey` helpers.
3. `ports/registry.py`: `ThrottlePort` in `PORT_KEYS`, `get_throttle_port()`.
4. `adapters/throttle/memory.py`: the in-memory fake with an injectable clock.
5. `adapters/throttle/redis.py`: the Redis adapter (`INCR` + `EXPIRE`).
6. `config/adapters.py`: the `throttle` entry in the fake and real tables.
7. `apps/identity/managers.py`: `UserManager` keyed on email.
8. `apps/identity/models.py`: `User` with `email` as `USERNAME_FIELD` and the normalisation;
   `PasswordResetToken`; `IdentityAuditEntry`.
9. `apps/identity/migrations/0002_*.py`: remove `username`, alter `email` (backfill first),
   add the unique constraint, create the two tables, the audit trigger and the grants.
10. `apps/identity/services/audit.py`: `write_audit` with the same-transaction guard.
11. `apps/identity/services/throttle.py`: `check_throttle(operation, ip, email)` → the two keys.
12. `apps/identity/services/emails.py`: `render_password_reset_email(token)` → `EmailMessage`.
13. `apps/identity/services/sign_up.py`: `sign_up(email, password, ip_address=None)`.
14. `apps/identity/services/authenticate.py`: `authenticate(email, password, ip_address=None)`.
15. `apps/identity/services/password_reset.py`: `request_password_reset`, `reset_password`.
16. `apps/identity/services/session.py`: `sign_out`, `end_other_sessions`.
17. `apps/identity/templates/identity/password_reset.txt`: the mail body.
18. `apps/identity/admin.py`: register `User` by email.
19. `config/settings.py`: `SESSION_COOKIE_AGE`, `SESSION_COOKIE_SECURE`, `SESSION_SAVE_EVERY_REQUEST`,
    `SESSION_EXPIRE_AT_BROWSER_CLOSE`, `SESSION_COOKIE_SAMESITE`, `CSRF_TRUSTED_ORIGINS`.
20. `config/env.py`: `csrf_trusted_origins`, `frontend_base_url`.
21. Tests: the eight test files listed above, each with at least one assertion that can fail.
22. Run `manage.py check`, `makemigrations --check`, `make lint-imports`, `ruff check`,
    `ruff format --check`, the full backend suite and the coverage gate.
23. Append the item's section to `test-report.md` and `review-report.md`.

---
*Generated by specs.md - fabriqa.ai FIRE Flow | Checkpoint 1: pending*
