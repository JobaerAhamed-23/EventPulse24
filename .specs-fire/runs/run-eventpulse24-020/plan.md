---
run: run-eventpulse24-020
work_item: account-auth-core
intent: onboarding-and-account
mode: validate
checkpoint: plan
approved_at:
---

# Implementation Plan: Account & Auth Core (identity services)

## Approach

Implement the `identity` module's account core as **services only** — no HTTP endpoints.
Every service takes explicit arguments and never a `request` (the spine's "Auth resolved at
the API edge"). The security properties the work item names — enumeration safety, token
single-use and expiry, session lifetime, throttling — are pinned here at the service layer,
where they can be tested without HTTP noise. The next item (`auth-api-and-session-seam`) puts
the endpoints over these services.

The work follows the design doc's four decisions in dependency order, so each step has a
stable base to build on:

1. **Constants and the throttle port** — the vocabulary everything else uses.
2. **The `User` model changes and the `UserManager`** — email becomes the login.
3. **The new models and the migration** — `PasswordResetToken`, `IdentityAuditEntry`.
4. **The services** — sign-up, authenticate, reset, sign-out.
5. **Settings** — session cookies and CSRF.
6. **Tests** — one file per rule, each with an assertion that can fail.

**Why the reset token is a stored row.** Django's `PasswordResetTokenGenerator` was probed
against the pinned Django 6.1.2 before choosing (the work item required this). It is **not
single-use**: two consecutive `check_token` calls with no state change both returned `True`. It
becomes single-use only because the password changes, so it is replayable between issuance and
use, it cannot be revoked, and it cannot be listed for a user's outstanding resets. The
stored, hashed, single-use row gives all three properties the work item requires, and it
stores only a digest — a database dump yields no usable reset link.

**Why the throttle is a port.** Redis is in the stack, but the work item asks how a test pins
the limit *deterministically*. A `ports.throttle` ABC with an in-memory fake that owns an
injectable clock gives exactly that: the test calls it N times and asserts the N+1-th call is
refused — no sleeping, no Redis, no timing flake. The Redis adapter is a separate, small file
written against the same interface.

**Why the email uniqueness is a database constraint.** The email is normalised (lowercased and
trimmed) before it is written, so a plain unique index on the normalised column *is* a
case-insensitive unique index: `Maya@Example.com` is stored as `maya@example.com` and collides
with the existing row. The `IntegrityError` from the constraint is what makes the race
between two concurrent sign-ups safe, and the service catches it to return the
enumeration-safe outcome.

**Brownfield rules.** Every pattern below follows an existing precedent in this codebase:
`personalization`'s audit writer and models are the template for `identity`'s; `ports.email`
is the template for `ports.throttle`; `config/adapters.py`'s two tables are the template for
the `throttle` entries. No existing test is modified except the import-contracts test, which
is additive.

## Files to Create

| File | Purpose |
|------|---------|
| `backend/ports/throttle.py` | The `ThrottlePort` ABC, `ThrottleDecision`, and the key builders |
| `backend/adapters/throttle/__init__.py` | Package marker |
| `backend/adapters/throttle/memory.py` | The in-memory fake with an injectable clock |
| `backend/adapters/throttle/redis.py` | The Redis adapter (`INCR` + `EXPIRE`) |
| `backend/apps/identity/managers.py` | `UserManager` keyed on email |
| `backend/apps/identity/services/audit.py` | The `identity` audit writer with the same-transaction guard |
| `backend/apps/identity/services/throttle.py` | `check_throttle(operation, ip, email)` — the two keys |
| `backend/apps/identity/services/emails.py` | `render_password_reset_email(token)` → `EmailMessage` |
| `backend/apps/identity/services/sign_up.py` | `sign_up(email, password, ip_address=None)` |
| `backend/apps/identity/services/authenticate.py` | `authenticate(email, password, ip_address=None)` |
| `backend/apps/identity/services/password_reset.py` | `request_password_reset`, `reset_password` |
| `backend/apps/identity/services/session.py` | `sign_out`, `end_other_sessions` |
| `backend/apps/identity/templates/identity/password_reset.txt` | The reset mail body |
| `backend/apps/identity/migrations/0002_email_login_reset_token.py` | The schema change |
| `backend/tests/identity/factories.py` | A `User` factory |
| `backend/tests/identity/test_sign_up.py` | Enumeration safety, case-insensitive uniqueness, weak passwords |
| `backend/tests/identity/test_authenticate.py` | The dummy-hash path, the generic failure |
| `backend/tests/identity/test_password_reset.py` | Single-use, expiry boundary, session invalidation |
| `backend/tests/identity/test_throttle.py` | The throttle trips, per IP and per account |
| `backend/tests/identity/test_session_settings.py` | The cookie flags and the 7-day lifetime |
| `backend/tests/identity/test_log_redaction.py` | No email, password or token in a log line |
| `backend/tests/identity/test_audit.py` | The audit row, and no email in it |
| `backend/tests/identity/test_models.py` | The token model's constraints, and the email normalisation |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/shared/constants.py` | Add `AUTH_SESSION_LIFETIME`, `AUTH_RESET_TOKEN_LIFETIME`, `AUTH_THROTTLE_WINDOW_SECONDS`, the six throttle limits (stdlib-only: no Django import — see the note below) |
| `backend/apps/identity/models.py` | `User` loses `username` and gains `email` as `USERNAME_FIELD`; add `PasswordResetToken`, `IdentityAuditEntry` |
| `backend/apps/identity/services/__init__.py` | Export the service functions as the published interface |
| `backend/apps/identity/admin.py` | Register `User` by email (`USERNAME_FIELD`), read-only for the audit table |
| `backend/ports/registry.py` | `ThrottlePort` in `PORT_KEYS`, `get_throttle_port()` |
| `backend/config/adapters.py` | The `throttle` entry in `FAKE_ADAPTERS` and `REAL_ADAPTERS` |
| `backend/config/settings.py` | `SESSION_COOKIE_AGE`, `SESSION_COOKIE_SECURE`, `SESSION_SAVE_EVERY_REQUEST`, `SESSION_EXPIRE_AT_BROWSER_CLOSE`, `SESSION_COOKIE_SAMESITE`, `CSRF_TRUSTED_ORIGINS` |
| `backend/config/env.py` | `csrf_trusted_origins`, `frontend_base_url` |
| `backend/tests/architecture/test_import_contracts.py` | Additive: the `throttle` port and adapter contracts |

## Tests

| Test File | Coverage |
|-----------|----------|
| `backend/tests/identity/test_models.py` | The email is normalised on write; the unique constraint refuses a case-variant duplicate; the token row's `used_at`/`revoked_at` check; the token is stored hashed |
| `backend/tests/identity/test_sign_up.py` | Sign-up creates a user; a duplicate email returns the **same outcome shape**; a mixed-case duplicate is refused by the constraint; a weak password is refused with a calm message; the password is hashed, not stored plain |
| `backend/tests/identity/test_authenticate.py` | A correct password returns the user; a wrong password and an unknown email give the **same message**; the unknown-email path **calls the hasher** (monkeypatched recorder); a throttled attempt is refused |
| `backend/tests/identity/test_password_reset.py` | An unknown email returns the same result and **sends nothing**; a known email sends exactly one transactional message with an idempotency key; a token is refused on **second use**; an **expired** token is refused at the boundary (fixed clock); a reset **ends the other sessions** |
| `backend/tests/identity/test_throttle.py` | The limit trips at exactly N+1; the per-account key is shared across email casings; the throttle **never reveals account existence** |
| `backend/tests/identity/test_session_settings.py` | `HttpOnly`, `Secure` outside local, `SameSite=Lax`, the 7-day `SESSION_COOKIE_AGE`, `CSRF_TRUSTED_ORIGINS` is set |
| `backend/tests/identity/test_log_redaction.py` | The email, the password and the raw token appear in **no** serialised log line, across each flow |
| `backend/tests/identity/test_audit.py` | Sign-in writes an `IdentityAuditEntry` with the actor UUID and **no email**; the audit row is written in the same transaction |

## Technical Details

### The constants (all in `shared/constants.py`)

```python
# FR-4: not prompted to re-authenticate within 7 days.
AUTH_SESSION_LIFETIME = timedelta(days=7)
# A reset link is a bearer credential for the account; its life is deliberately short.
AUTH_RESET_TOKEN_LIFETIME = timedelta(minutes=30)

# Throttling (PRD §11.2). The window all the limits share.
AUTH_THROTTLE_WINDOW_SECONDS = 3600
AUTH_THROTTLE_SIGN_IN_IP = 10
AUTH_THROTTLE_SIGN_IN_ACCOUNT = 5
AUTH_THROTTLE_SIGN_UP_IP = 5
AUTH_THROTTLE_SIGN_UP_ACCOUNT = 3
AUTH_THROTTLE_RESET_IP = 5
AUTH_THROTTLE_RESET_ACCOUNT = 3
```

`DUMMY_PASSWORD_HASH` is **not** in `shared/constants.py`. That module must stay stdlib-only:
`domain` imports it, and the `domain-pure` import-linter contract forbids `django` in
`domain`, so a Django import in `shared/constants.py` would break the contract transitively
(`pyproject.toml`: "Both are stdlib-only themselves"). The dummy hash needs
`django.contrib.auth.hashers.make_password`, so it is computed in
`apps/identity/services/authenticate.py`, where Django is allowed.

It is a hash of a random password (`secrets.token_urlsafe(32)`), computed once at import time.
It is a hash of a value nobody knows, used only to equalise the unknown-email timing path. It
authenticates nothing.

### The throttle keys

```
auth:{operation}:ip:{ip_address}
auth:{operation}:acct:{sha256(normalised_email).hexdigest()}
```

The account key is a **digest**, never the raw email: a Redis key containing an email would
put it in `KEYS` output and in any monitoring dashboard, which AD-13 forbids. The digest is a
key-hygiene measure, not a confidentiality measure — the input space is small. The operation
is one of `sign_in`, `sign_up`, `reset`.

Both keys are checked. Either tripping refuses the attempt, and the check runs **before** the
account lookup, so a 429 never reveals whether the account exists.

### The port

```python
# ports/throttle.py
@dataclass(frozen=True)
class ThrottleDecision:
    allowed: bool
    retry_after_seconds: int

class ThrottlePort(ABC):
    @abstractmethod
    def check(self, key: str, *, limit: int, window_seconds: int) -> ThrottleDecision: ...
```

The fake keeps `key -> list[monotonic timestamps]` and a `now` callable the test controls. The
Redis adapter uses `INCR` + `EXPIRE` and reads the TTL back for `retry_after_seconds`.

### The `User` model

`AbstractUser` is replaced by `AbstractBaseUser` + `PermissionsMixin`, with
`USERNAME_FIELD = "email"`, `REQUIRED_FIELDS = []`, and a `UserManager` that overrides
`get_by_natural_key`, `create_user` and `create_superuser`.

`email` is `models.EmailField(unique=True, max_length=254)`. It is normalised in `save()` as a
backstop, so even a write that bypasses the service cannot store a mixed-case value and slip
past the unique constraint.

The migration **backfills** `email` from `username` for any pre-existing row before making
`email` NOT NULL, then removes `username`. The table is almost certainly empty (no sign-up path
existed), but the migration must not assume it.

### The service signatures

```python
def sign_up(*, email: str, password: str, ip_address: str | None = None) -> SignUpOutcome
def authenticate(*, email: str, password: str, ip_address: str | None = None) -> User
def request_password_reset(*, email: str, ip_address: str | None = None) -> None
def reset_password(*, token: str, new_password: str) -> User
def sign_out(*, user: User) -> None
```

`ip_address` is passed in from the API edge and is used **only** for the throttle key. It is
never logged and never used for anything else.

`SignUpOutcome` is a frozen dataclass with no field that distinguishes "created" from
"already existed" — that is the enumeration-safe shape.

### The enumeration-safe sign-up

1. Throttle (IP + account).
2. Normalise the email.
3. Validate the password with `AUTH_PASSWORD_VALIDATORS` → `ValidationError` with the
   validator's messages, in `details = {"errors": [...]}`.
4. Try to create the user inside `transaction.atomic(using=PERSONAL)`.
5. On `IntegrityError` (the unique constraint fired — either a race or an existing account):
   roll back, and **return the same outcome** as for a new account. The existing holder is
   notified by a transactional email.
6. On success: write the audit row in the same transaction, and return the same outcome shape.

### The timing-equalised authenticate

```python
user = User.objects.filter(email=normalised).first()
if user is None:
    check_password(password, DUMMY_PASSWORD_HASH)   # the equalisation path
    raise AuthenticationFailedError()
if not check_password(password, user.password):
    raise AuthenticationFailedError()
```

The unknown-email path performs exactly one password hash. The test monkeypatches
`django.contrib.auth.hashers.check_password` with a recorder and asserts it was called on the
unknown-email path — so removing the equalisation fails the suite.

`AuthenticationFailedError` is a `domain.errors.ValidationError` subclass with the message
`"That email and password don't match."` — one message for both failure cases.

### The reset-token consumption

```python
row = PasswordResetToken.objects.filter(token_hash=hash_of(token), used_at__isnull=True,
                                         revoked_at__isnull=True).first()
if row is None or row.expires_at <= now:
    raise InvalidResetTokenError()
```

The consumption sets `used_at` in the **same transaction** that changes the password. A second
attempt finds `used_at` set and is refused — which holds even if the reset fails before
saving, because the consumption is its own committed step. This is the property Django's
generator does not have.

The expiry check compares against an injected clock, so the test pins the boundary exactly:
`now == expires_at` is expired, `now == expires_at - 1 second` is not.

### The reset ends the other sessions

`reset_password` deletes the user's other `django_session` rows. The current session is
**rotated** (`request.session.cycle_key()`), not deleted, so the user stays signed in on the
device they reset from while every other session dies.

### The audit

`IdentityAuditEntry(AuditEntry)` with `retention_category = RetentionCategory.AUDIT_LOG`, and
`apps/identity/services/audit.py` with the same guard the other two apps use — a
`write_audit` outside `transaction.atomic(using=PERSONAL)` raises
`AuditOutsideIdentityTransaction` instead of writing an orphaned row.

Sign-in: `actor_kind="user"`, `actor_id=<the user's uuid>`, `action="sign_in"`,
`target_type="User"`, `target_id=<the user's uuid>`, `details={"method": "password"}`. **No
email** — the actor is stored by value as a UUID, exactly as AD-13 requires.

### The settings

```python
SESSION_COOKIE_AGE = AUTH_SESSION_LIFETIME          # 7 days
SESSION_SAVE_EVERY_REQUEST = False                  # the expiry is set at login, not slid
SESSION_EXPIRE_AT_BROWSER_CLOSE = False              # the session must outlive the browser
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG                   # secure outside local
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_TRUSTED_ORIGINS = env.csrf_trusted_origins     # the frontend's own origin
```

`USE_X_FORWARDED_HOST` stays `False`: it would make Django trust the `Host` header, which is
attacker-controlled. `CSRF_TRUSTED_ORIGINS` is the explicit allowlist, and it is the mechanism
the coding standards recommend first.

The frontend requirement, recorded for the next item: the browser holds the CSRF cookie on the
frontend's own origin (first-party, so `SameSite=Lax` permits it), and `frontend/proxy.ts` must
forward both the `Cookie` and the `X-CSRFToken` headers.

### The email

One message on `Stream.TRANSACTIONAL` (AD-20), with an idempotency key minted from ids only:
`auth_reset:{token_id}` — joined with `shared.constants.SEND_KEY_SEPARATOR` (`:`), never `-` or
`_`, so each UUID stays a 36-character run.

The reset link targets the frontend's `/reset-password` route:
`{FRONTEND_BASE_URL}/reset-password?token={token}`. The raw token appears in the email body
and the URL — unavoidable, since the user must follow the link — and nowhere else: not in a log
line, not in the audit row, and not in the stored row, which holds only the digest.

## Based on Design Doc

Reference: `.specs-fire/intents/onboarding-and-account/work-items/account-auth-core-design.md`

Decisions carried from the design doc: D1–D3 (the stored, hashed, single-use reset token),
D4–D6 (email as the login, dropped `username`, the case-insensitive unique constraint),
D7–D8 (the two throttle keys, the new `ports.throttle` port and its fake), D12 (the 7-day
session and the cookie flags), D13 (CSRF via `CSRF_TRUSTED_ORIGINS`), D14 (the `identity`
audit table), D15–D17 (the three enumeration-safe paths), D18 (the reset mail and link),
D19 (Django's password validators), D20 (services take explicit arguments, never a `request`).

---
*Plan pending approval at checkpoint.*
---

## Work Item: calendar-connection-model

**Title**: Calendar Connection Model & Credential Encryption
**Mode**: validate
**Design doc**: `.specs-fire/intents/onboarding-and-account/work-items/calendar-connection-model-design.md` (approved, 2026-10-29)

### Approach

Follow the approved design (D1–D15) precisely. The work is in four layers:

1. **Crypto** — `apps/personalization/credentials.py`: key loading, the `EPENC1` envelope,
   AES-256-GCM encrypt/decrypt, the keyed HMAC fingerprint. Pure functions over an explicit
   key; no Django model imports, no settings reads (so it is testable with any key).
2. **The field** — `apps/personalization/fields.py`: `EncryptedTextField`, a `TextField`
   subclass that encrypts on write (`get_prep_value`) and decrypts on read
   (`from_db_value`/`to_python`), and whose `value_to_string` yields the **ciphertext** so
   `dumpdata` cannot leak the plaintext.
3. **The model** — `CalendarConnection` in `apps/personalization/models.py`, plus
   `PersonalEvent.Source.CALENDAR_IMPORT`, `calendar_connection_id`, `source_uid`, and the
   two constraints (source↔connection, and status↔credential).
4. **The commands** — `apps/personalization/services/calendar_connections.py`: connect,
   disconnect, purge, reveal. The only writer of the table (AD-16). Each mutation writes its
   audit row in the same transaction (AD-5).

The `cryptography` library is added to `backend/pyproject.toml` and pinned. A new
`import-linter` contract (`crypto-library`) keeps every other module out of it.

**Order of work** (each step leaves the tree green):

1. `pyproject.toml` — the dependency + the contract; `uv sync`.
2. `shared/constants.py` — the two constants.
3. `domain/errors.py` — the three typed errors.
4. `config/env.py` + `config/settings.py` — the key.
5. `apps/personalization/credentials.py` + `fields.py`.
6. `apps/personalization/models.py` — the model and the `PersonalEvent` changes.
7. The migration (`makemigrations`, then hand-edit for the grants if needed).
8. `config/checks.py` — `eventpulse.E007`.
9. `apps/personalization/services/calendar_connections.py`.
10. `apps/personalization/admin.py` — the read-only admin.
11. `.env.example` / `.env` — the local key.
12. The tests.
13. The gates: ruff, import-linter, pytest, coverage, `manage.py check`, migration drift.

### Implementation Checklist

#### Step 1 — The dependency and the contract

- `backend/pyproject.toml`: add `cryptography==46.0.3` to `dependencies`.
- `backend/pyproject.toml`: add the `crypto-library` import-linter contract (§D12):
  `source_modules` lists everything except `apps.personalization`;
  `forbidden_modules = ["cryptography"]`; `allow_indirect_imports = false`.
- `backend/tests/architecture/test_import_contracts.py`: plant the violation for the new
  contract — one test that breaks exactly this contract and no other.
- `uv sync` to install the wheel.

#### Step 2 — The constants (D9)

`backend/shared/constants.py`, in the accounts/auth section or a new calendar section:

```python
# AD-18 / FR-50: how often a connected calendar is polled. PROVISIONAL (OQ-7): the interval
# is ours to choose, since we are the HTTP client, but it is not yet validated against a
# live Google secret address. Change this one line when OQ-7 closes.
CALENDAR_POLL_INTERVAL = timedelta(hours=1)

# FR-50: the Free tier connects one calendar provider. Pro (3) is a later intent; this
# intent is Free-only, so the cap is 1.
FREE_TIER_CALENDAR_PROVIDER_CAP = 1
```

Stdlib only — `timedelta` is already imported.

#### Step 3 — The typed errors (D14)

`backend/domain/errors.py`:

- `CredentialDecryptionError(DomainError)` — `code = "credential_unreadable"`.
- `InvalidCalendarCredentialError(ValidationError)` — `code = "invalid_calendar_credential"`.
- `CalendarProviderCapReached(DomainError)` — `code = "calendar_cap_reached"`.

Calm `default_message`s, no emoji (the file's stated voice). `domain/` stays stdlib-only.

#### Step 4 — The key (D3, D5)

`backend/config/env.py`:

- `calendar_credential_key: str` — **required**, no default.
- A `field_validator` that parses `<key_id>.<base64url-32-bytes>` and raises a
  `ValueError` naming `CALENDAR_CREDENTIAL_KEY` and the expected format if it is malformed.

`backend/config/settings.py`:

- `CALENDAR_CREDENTIAL_KEY = env.calendar_credential_key`.

**The key parsing lives in one place**: `apps/personalization/credentials.py` as
`parse_key(raw) -> ParsedKey` (a frozen dataclass: `key_id`, `key`), and `config/env.py`
calls it in its validator. `credentials.py` imports **nothing** from `config`, so there is
no cycle: `config.env` → `apps.personalization.credentials` → stdlib + `cryptography` +
`domain.errors`.

The key is validated when settings load — i.e. **at startup** — and a malformed value aborts
the boot with a clear message.

#### Step 5 — The crypto module (D1–D4, D6)

`backend/apps/personalization/credentials.py`:

| Name | Purpose |
|---|---|
| `ParsedKey` | Frozen dataclass: `key_id: str`, `key: bytes` (32 bytes). |
| `parse_key(raw: str) -> ParsedKey` | Parses `k1.<base64url-32-bytes>`; raises `ImproperlyConfigured` with a message naming `CALENDAR_CREDENTIAL_KEY`. |
| `encrypt(plaintext: str, key: ParsedKey) -> str` | Builds the `EPENC1.<key_id>.<nonce>.<ciphertext>` envelope. |
| `decrypt(envelope: str, key: ParsedKey) -> str` | Parses the envelope and decrypts; raises `CredentialDecryptionError` on any failure. |
| `fingerprint(url: str, key: ParsedKey) -> str` | HMAC-SHA256 hex of the normalised URL. |
| `normalise_for_fingerprint(url: str) -> str` | Trim; lowercase the scheme and host only. |
| `AAD` | The fixed associated data `"eventpulse24.calendar_connection.credential"`. |

**Details that must not be got wrong:**

- **The nonce**: `os.urandom(12)`, per encryption, never derived.
- **base64url, unpadded** (`base64.urlsafe_b64encode(...).rstrip(b"=")`), decoded with the
  padding restored.
- **The envelope split**: `envelope.split(".")`, expecting exactly 4 parts. A wrong count is
  a decryption failure, not an `IndexError`.
- **The key id is validated** to be a short, safe token (`[A-Za-z0-9_-]{1,32}`), because it
  lands in a column that an admin might one day display.
- **The AAD is fixed**, not per-row (D4: binding to the row id would make the ciphertext
  non-portable and would break a migration that rewrites ids).
- **`decrypt` never returns `None` or `""` on failure** — it raises
  `CredentialDecryptionError`.
- **The plaintext is never logged.** The module has no logger at all: it has nothing to say
  that is safe to say.

#### Step 6 — The field (D11)

`backend/apps/personalization/fields.py`:

```python
class EncryptedTextField(models.TextField):
    """A text column whose stored value is ciphertext (AD-18)."""
```

- `get_prep_value(value)` → `encrypt(value)` for a non-empty `str`; `None` → `None`;
  `""` → `None` (the column is nullable, and an empty credential is the cleared state).
- `from_db_value(value, expression, connection)` → `decrypt(value)`.
- `to_python(value)` → `decrypt(value)` when the value carries the `EPENC1.` prefix;
  otherwise pass through (a plaintext assigned in Python).
- `value_to_string(value)` → the **ciphertext** (so `dumpdata` never leaks the plaintext).
- `db_type` → `"text"`.

**The key**: read from `django.conf.settings.CALENDAR_CREDENTIAL_KEY` **lazily, per call**,
cached by the raw string (an `lru_cache` keyed by the raw value), so `override_settings`
with a *different* raw string is a different cache entry and the wrong-key test works.

#### Step 7 — The model (D7, D8)

`backend/apps/personalization/models.py`:

**`CalendarConnection`** — `UUIDv7Model`, `retention_category = RetentionCategory.ACCOUNT_IDENTITY`.

| Field | Definition |
|---|---|
| `user_id` | `models.UUIDField()` |
| `provider` | `models.CharField(max_length=16, choices=Provider.choices)` |
| `credential` | `EncryptedTextField(null=True, blank=True)` |
| `credential_fingerprint` | `models.CharField(max_length=64)` |
| `status` | `models.CharField(max_length=24, choices=Status.choices, default=Status.ACTIVE)` |
| `last_polled_at` | `models.DateTimeField(null=True, blank=True)` |
| `next_poll_at` | `models.DateTimeField(null=True, blank=True)` |
| `last_error_kind` | `models.CharField(max_length=32, null=True, blank=True)` |
| `last_error_at` | `models.DateTimeField(null=True, blank=True)` |
| `display_label` | `models.CharField(max_length=120, blank=True, default="")` |
| `created_at` | `models.DateTimeField(auto_now_add=True)` |
| `updated_at` | `models.DateTimeField(auto_now=True)` |

`class Provider(models.TextChoices)`: `GOOGLE = "google"`, `APPLE = "apple"`,
`OUTLOOK = "outlook"`.

`class Status(models.TextChoices)`: `ACTIVE = "active"`,
`NEEDS_RECONNECT = "needs_reconnect"`, `DISCONNECTED = "disconnected"`.

**Constraints:**

```python
models.UniqueConstraint(
    fields=["user_id", "credential_fingerprint"], name="calendar_connection_user_credential_uq"
),
models.CheckConstraint(
    condition=(models.Q(status="disconnected") & models.Q(credential__isnull=True))
    | (~models.Q(status="disconnected") & models.Q(credential__isnull=False)),
    name="calendar_connection_status_credential_ck",
),
```

**Indexes:** `(user_id, status)` for the poll scan, and a partial index on `next_poll_at`
filtered on `status = "active"` for the due-time query (Django's `models.Index` supports
`condition=Q(...)`, and Postgres supports partial indexes).

**`__str__`**: `f"{self.provider} calendar"` — the provider and nothing else. This is what
`repr()` shows too (Django's `Model.__repr__` uses `__str__`).

**`PersonalEvent` changes:**

- `Source.CALENDAR_IMPORT = "calendar_import"` — the comment on the existing value is
  replaced by the real value (the comment anticipated exactly this).
- `calendar_connection_id = models.UUIDField(null=True, blank=True)` — by value, no FK.
- `source_uid = models.CharField(max_length=255, null=True, blank=True)` — the ICS UID.
- `source`'s `max_length` stays **16**: `"calendar_import"` is 15 characters, so it fits.
- Constraints:
  ```python
  models.CheckConstraint(
      condition=(models.Q(source="calendar_import") & models.Q(calendar_connection_id__isnull=False))
      | (~models.Q(source="calendar_import") & models.Q(calendar_connection_id__isnull=True)),
      name="personal_event_source_connection_ck",
  ),
  models.UniqueConstraint(
      fields=["calendar_connection_id", "source_uid"], name="personal_event_connection_uid_uq"
  ),
  ```

  Postgres treats NULLs as distinct in a unique constraint, so the many user-created rows
  with `source_uid = NULL` do not collide.

#### Step 8 — The migration

`makemigrations personalization` → `0002_calendarconnection_personalevent_and_more.py`.

Then **hand-edit** it if needed:

- The `EncryptedTextField` must serialise into the migration. Django serialises a custom
  field by its import path (`apps.personalization.fields.EncryptedTextField`) — that works
  as long as the class is importable, which it is.
- **No trigger** is needed: `CalendarConnection` is not append-only (its status changes), so
  no `forbid_history_mutation` trigger and no `REVOKE UPDATE, DELETE`.
- The runtime role needs `UPDATE` on the new table (it changes status), which is the
  default privilege — no grant change needed.
- `personalization` is already routed to `personal`, so the table lands in the right schema
  automatically.

**Verify** the migration creates `personal.personalization_calendarconnection` and that the
`PersonalEvent` columns are in `personal.personalization_personalevent`.

#### Step 9 — The system check (D5, D15)

`backend/config/checks.py`:

- `find_missing_credential_key_errors(keys) -> list[Error]` — a **pure function over an
  explicit input**, like the other checks, so it is testable without touching the process
  environment.
- Registered as `eventpulse.E007`: "the application-level credential key is missing or
  malformed". The hint names `CALENDAR_CREDENTIAL_KEY`.
- Registered with `@register()` (not `Tags.models`) — a key check is not a model check, and
  this matches `check_fake_fetch_fixtures`.

#### Step 10 — The commands (D13)

`backend/apps/personalization/services/calendar_connections.py`:

| Function | Contract |
|---|---|
| `connect_calendar(*, user_id, provider, url, display_label="", actor, now=None) -> CalendarConnection` | Validates the URL shape; enforces the Free-tier cap; encrypts; fingerprints; writes the row **and** its audit row in one `transaction.atomic(using=PERSONAL)`. |
| `disconnect_calendar(*, connection, actor) -> None` | Sets `status = "disconnected"`, clears `credential` to `NULL`, writes the audit row, in one transaction. Does **not** delete the row. |
| `purge_connection_events(*, connection) -> int` | Deletes exactly that connection's imported `PersonalEvent` rows. |
| `reveal_credential(*, connection) -> Credential` | Decrypts and wraps in `ports.calendar.Credential`. The only function that returns the plaintext. |

**Details:**

- **The URL shape check** (D13): non-empty after trimming; a scheme in
  `{http, https, webcal, webcals}`; no userinfo component (`https://user:pass@host` is
  refused). Raises `InvalidCalendarCredentialError`.
- **The stored value is the address as entered (trimmed)**; the adapter normalises
  `webcal://` → `https://` at fetch time. The fingerprint uses the *normalised* form
  (scheme+host lowercased) so two spellings of one calendar are one row.
- **The Free-tier cap** counts the user's connections whose status is **not**
  `disconnected` — a `needs_reconnect` connection still occupies a slot (the user has not
  given it up). Raises `CalendarProviderCapReached` when the cap is reached.
- **The audit rows** use `apps.personalization.services.audit.write_audit` with actions
  `calendar_connect`, `calendar_disconnect`, `calendar_reconnect`. The `details` carry the
  provider and a count — **never the URL, never the fingerprint**.
- **A reconnect** (a `needs_reconnect` row given a new address) updates the row in place:
  the credential, the fingerprint, the status and the poll schedule.

#### Step 11 — The admin (D10)

`backend/apps/personalization/admin.py` — the file is currently empty (one line). Add a
`CalendarConnectionAdmin`:

- `list_display = ["provider", "status", "last_polled_at", "next_poll_at", "last_error_kind", "created_at"]`
- `list_filter = ["provider", "status"]`
- `search_fields = ["user_id"]`
- `readonly_fields` — **not** used for the credential. The credential field is **excluded
  entirely**: it is not in `fieldsets`, not in `readonly_fields`, not in `list_display`.
- `has_add_permission` / `has_change_permission` / `has_delete_permission` → `False`.

#### Step 12 — The local key

`.env.example` and `.env`:

```
# The application-level key for calendar credentials (AD-18). Separate from DJANGO_SECRET_KEY.
# 32 bytes, base64url. Production keys come from the platform secret store.
CALENDAR_CREDENTIAL_KEY="k1.<base64url-32-bytes>"
```

The `.env.example` value is a **valid, obviously-local** key (a fixed base64url of 32 bytes
with a comment saying it is local-only and must be replaced in production), so a developer
who runs `make env` passes `manage.py check` on the first try.

#### Step 13 — The tests

`backend/tests/personalization/test_calendar_credentials.py` (new) — the pure unit tests:
the parse, the round trip, the wrong key, the envelope's shape, the fingerprint's stability
and its normalisation, the key id's presence.

`backend/tests/personalization/test_calendar_connection_model.py` (new) — the model tests:
the raw column is ciphertext, the round trip through the ORM, the repr, the admin, the
logs, the constraints, the uniqueness, the schema.

`backend/tests/personalization/test_calendar_connection_commands.py` (new) — the command
tests: connect, the cap, the duplicate, disconnect, the purge, the audit rows, reveal.

**Every test must be able to fail.** The verification is the standard the last two items
held: revert the fix in the working tree, re-run the test, and observe the failure.

### Files to Create

| File | Purpose |
|---|---|
| `backend/apps/personalization/credentials.py` | Key parsing, the envelope, encrypt/decrypt, the HMAC fingerprint. |
| `backend/apps/personalization/fields.py` | `EncryptedTextField`. |
| `backend/apps/personalization/services/calendar_connections.py` | The connect/disconnect/purge/reveal commands. |
| `backend/apps/personalization/migrations/0002_*.py` | The table and the `PersonalEvent` changes. |
| `backend/tests/personalization/test_calendar_credentials.py` | The crypto unit tests. |
| `backend/tests/personalization/test_calendar_connection_model.py` | The model tests. |
| `backend/tests/personalization/test_calendar_connection_commands.py` | The command tests. |

### Files to Modify

| File | Change |
|---|---|
| `backend/pyproject.toml` | `cryptography==46.0.3`; the `crypto-library` import contract. |
| `backend/shared/constants.py` | `CALENDAR_POLL_INTERVAL`, `FREE_TIER_CALENDAR_PROVIDER_CAP`. |
| `backend/domain/errors.py` | Three typed errors. |
| `backend/config/env.py` | `calendar_credential_key` + its validator. |
| `backend/config/settings.py` | `CALENDAR_CREDENTIAL_KEY`. |
| `backend/config/checks.py` | `eventpulse.E007`. |
| `backend/apps/personalization/models.py` | `CalendarConnection`; the `PersonalEvent` changes. |
| `backend/apps/personalization/admin.py` | The read-only admin. |
| `backend/tests/architecture/test_import_contracts.py` | The planted violation for the new contract. |
| `backend/.env.example`, `backend/.env` | `CALENDAR_CREDENTIAL_KEY`. |

### Tests

| File | What it pins |
|---|---|
| `tests/personalization/test_calendar_credentials.py` | The parse (valid, missing, malformed, short); the envelope's shape; the round trip; the wrong key raising `CredentialDecryptionError`; the nonce differing between two encryptions; the fingerprint's stability and its case-normalisation; the fingerprint changing with the key. |
| `tests/personalization/test_calendar_connection_model.py` | The raw column is ciphertext (no URL, no host, no path); the ORM round trip; the wrong key on read; the model's `repr`/`str`; the admin's exclusion; the log output; the audit row; the source↔connection constraint both ways; the `(connection, uid)` uniqueness; the `NULL` uid coexistence; the status↔credential constraint both ways; the schema; the absence of FKs; the retention category. |
| `tests/personalization/test_calendar_connection_commands.py` | Connect writes one row and one audit row; the same calendar twice is refused; the cap refuses the second; a `needs_reconnect` connection still counts; disconnect clears the credential and writes an audit row; the purge removes exactly its own events; reveal returns a redacted `Credential`; revealing a cleared credential is refused. |
| `tests/architecture/test_import_contracts.py` | The `crypto-library` contract: exactly one planted violation breaks it. |

### Based on Design Doc

Reference: `.specs-fire/intents/onboarding-and-account/work-items/calendar-connection-model-design.md`

Decisions carried from the design doc: D1 (AES-256-GCM over Fernet), D2 (the `EPENC1`
versioned envelope with a key id), D3 (the key from the environment, never from
`SECRET_KEY`), D4 (a custom field rather than explicit encrypt/decrypt in services), D5
(fail fast at startup), D6 (the keyed HMAC fingerprint), D7 (the three statuses; disconnect
destroys the credential first), D8 (the model and the `PersonalEvent` changes), D9 (the two
constants), D10 (the six leak paths), D11 (the field's behaviour and the nullable column),
D12 (where the code lives; the `crypto-library` contract), D13 (the commands), D14 (the
typed errors), D15 (the fail-fast test shape).

### Gates

```bash
cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check .
cd backend && .venv/bin/python -m pytest --cov --cov-report=term -q
cd backend && .venv/bin/python -m coverage report --include='domain/*' --fail-under=100
make lint-imports
cd backend && .venv/bin/python manage.py check
cd backend && .venv/bin/python manage.py makemigrations --check --dry-run
```

### Notes for the implementation

1. **The key is read lazily by the field, eagerly by `config/env.py`.** The field reads
   `settings.CALENDAR_CREDENTIAL_KEY` per call (cached by raw string) so `override_settings`
   works; `config/env.py` validates it at settings-load time so a malformed key aborts the
   boot.
2. **`credentials.py` imports nothing from `config`.** That keeps it importable from
   `config/env.py` without a cycle.
3. **The `EncryptedTextField` must serialise into the migration.** Django writes
   `apps.personalization.fields.EncryptedTextField(...)` into the migration file, and that
   import must resolve when the migration runs.
4. **`"calendar_import"` is 15 characters**, so `source`'s existing `max_length=16` still
   fits — do not widen it.
5. **The `credential` column is nullable** and `NULL` is the cleared state. The
   status↔credential check constraint ties the two together.
6. **Do not put the credential in a log line, an audit row, an exception message, or the
   admin.** The `last_error_kind` column holds a slug, never a message.
7. **`reveal_credential` is the only function that returns the plaintext**, and it returns it
   wrapped in `ports.calendar.Credential`.

---
*Plan pending approval at checkpoint.*

---

## Work Item: calendar-connection-model — Implementation Notes

**Status:** implemented, tested, all gates green. 2337 passed; 98.62% coverage; `domain/` 100%.

### What was built

| Area | Files |
|------|-------|
| The key's **format** (stdlib-only) | `shared/credential_key.py` |
| The **cipher** (AES-256-GCM, the envelope, the keyed fingerprint) | `apps/personalization/credentials.py` |
| The **model field** (encrypt on write, decrypt on read, ciphertext on serialise) | `apps/personalization/fields.py` |
| The **model** | `apps/personalization/models.py` — `CalendarConnection`, plus `PersonalEvent.calendar_connection_id` / `source_uid` / `Source.CALENDAR_IMPORT` |
| The **commands** | `apps/personalization/services/calendar_connections.py` — connect / disconnect / purge / reveal |
| The **admin** | `apps/personalization/admin.py` — read-only, and the credential is *excluded*, not readonly |
| The **configuration** | `config/env.py` (required, validated at startup), `config/settings.py`, `config/checks.py` (`eventpulse.E007`) |
| The **errors** | `domain/errors.py` — `CredentialDecryptionError`, `InvalidCalendarCredentialError`, `CalendarProviderCapReached` |
| The **constants** | `shared/constants.py` — `CALENDAR_POLL_INTERVAL`, `FREE_TIER_CALENDAR_PROVIDER_CAP` |
| The **migration** | `apps/personalization/migrations/0002_calendarconnection_and_more.py` |
| The **contracts** | `pyproject.toml` — `crypto-library` and `credential-key` |
| The **tests** | `tests/shared/test_credential_key.py`, `tests/personalization/test_calendar_credentials.py`, `tests/personalization/test_calendar_connection_model.py`, `tests/personalization/test_calendar_connection_commands.py`, plus plants in `tests/architecture/test_import_contracts.py` and `tests/config/test_checks.py` |

### Deviations from the plan, and why

1. **The key's format moved to `shared/credential_key.py`.** The plan had
   `config/env.py` import `apps.personalization.credentials` to validate the key at
   startup. That made `config` reach the cipher and broke the `crypto-library` contract.
   The format is now stdlib-only in `shared`, so `config` can validate a key without being
   able to read a credential with it. **The cipher did not move.**

2. **The `crypto-library` contract allows indirect imports.** The model layer must
   encrypt, and Django's registry makes `config.api → … → models → fields → credentials`
   an unavoidable chain — it is the app's own code doing the encrypting. A **direct**
   import from another module is the violation. A second contract, `credential-key`,
   forbids the *key handling* module the same way, which is the rule that actually
   protects the key.

3. **The connect refusals are ordered by specificity.** The plan did not say in which
   order "already connected" and "plan limit" are checked. The cap is checked last: the
   cap counts *distinct* calendars, so a calendar the user already has is already
   counted, and reporting a plan limit for it sends the user to the wrong screen.

4. **The audit row carries the moment.** The plan's `details={"provider": provider}` left
   the `now` parameter unused, which ruff refused. The audit row now carries
   `{"provider": …, "at": now.isoformat()}`, matching `personal_events.py`.

### Defects the tests found, and their fixes

| Defect | Fix |
|--------|-----|
| The cap was checked before the duplicate, so connecting the same calendar twice reported a plan limit | The refusals are ordered: already-connected → reconnect → cap |
| `config` reached the cipher through the key validator | The format moved to `shared/credential_key` |
| A base64 value with a stray character was silently shortened, so a 32-byte key with one stray character would be accepted as a *different* key | The alphabet is checked before decoding, and the decode is strict |

Each fix is pinned by a test that was **reverted and re-run** to confirm it fails without
it — see `test-report.md`.

### Gates

- `pytest` — **2337 passed**, 0 failed
- `coverage` — **98.62%** overall (gate 80%); `domain/` **100%** (gate 100%)
- `ruff check` — clean; `ruff format --check` — clean
- `lint-imports` — **16 kept, 0 broken**
- `manage.py check` — no issues (1 silenced)
- `makemigrations --check --dry-run` — no changes detected

### Carried to the next items

- `CALENDAR_POLL_INTERVAL` is **provisional** (OQ-7) — the poll item confirms it.
- `next_poll_at` is reset to `NULL` on connect and disconnect; the polling item sets it.
- The `CalendarConnection.Status.NEEDS_RECONNECT` transition is set by the poll item; the
  connect command only consumes it.
