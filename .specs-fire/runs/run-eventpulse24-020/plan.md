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

---

# Work Item: ics-calendar-adapter — Implementation Plan

**Design**: `.specs-fire/intents/onboarding-and-account/work-items/ics-calendar-adapter-design.md`
(approved). This plan implements it.

**Mode**: validate — Checkpoint 2 of 2 is this document.

---

## 0. The shape of the change

Twelve files move, and the interesting part is what does **not** move.

```
formats/ics/                  NEW — the one ICS implementation
  __init__.py
  events.py                   the shared intermediate: IcsEvent
  parser.py                   bytes -> list[IcsEvent]  (moved from apps/ingestion)
  text.py                     plain_text + the caps     (moved, format-only)
  times.py                    all_day_span, roll_overnight, at_midnight (moved)
  windows_zones.py            Windows TZID -> IANA      (moved)

ports/calendar.py             the typed outcomes, the validators, CalendarResult
ports/fetch.py                fetch() gains allow_cross_host_redirect
adapters/crawl/http.py        honours allow_cross_host_redirect
adapters/calendar/ics.py      NEW — the adapter
apps/ingestion/parsers/       rewritten to consume formats.ics
config/adapters.py            registers the real calendar adapter
pyproject.toml                the layers amendment + the single-ics-parser contract
```

---

## 1. Step 1 — `formats/ics`: the one ICS implementation

### 1.1 What moves, and what stays behind

| From | To | Why it moves |
|---|---|---|
| `apps/ingestion/parsers/ics.py` | `formats/ics/parser.py` | Both callers need it |
| `apps/ingestion/parsers/times.py` | `formats/ics/times.py` | Pure format concern |
| `apps/ingestion/parsers/windows_zones.py` | `formats/ics/windows_zones.py` | Pure format concern |
| `apps/ingestion/parsers/text.py` → `plain_text` | `formats/ics/text.py` | Pure format concern |

**What stays in `apps/ingestion/parsers/`**: `types.py` (the *catalog* shape),
`feeds.py`, `jsonld.py`, and `text.py`'s catalog helpers (`item_id`, `derived_id`,
`http_url`, `absolute_iri`).

### 1.2 The shared intermediate: `IcsEvent`

**The key decision in the whole item.** The parser produces `IcsEvent`s — a *format*
shape, with no identity policy and no instant.

```python
@dataclass(frozen=True)
class IcsEvent:
    uid: str                       # the UID exactly as written ("" when absent)
    title: str
    start: datetime | None         # as written: naive wall clock, or aware
    end: datetime | None           # as written, in the start's representation
    start_zone: str | None         # IANA name (Windows mapped), or None
    end_zone: str | None
    all_day: bool
    status: str                    # "CANCELLED" or ""
    location: str
    description: str
    url: str
    recurrence_id: datetime | None # the RECURRENCE-ID instant, when this is an override
    has_rrule: bool
    raw: dict[str, str]            # the as-written fields, for the catalog's payload
```

**Why not reuse `ParsedCandidate`.** `ParsedCandidate` is the *catalog* shape: it has
`source_event_id` (an identity decision), `canonical_url` (resolved against a source
base), `venue_name` (a catalog concept), and `status` as a `StatusHint`. The calendar
needs none of those, and needs two things `ParsedCandidate` has no room for: the
`RECURRENCE-ID` and the `has_rrule` flag. So the shared shape is the **intersection**:
what both need, which is what the format actually says.

### 1.3 The parser's contract

```python
def parse_ics(content: bytes) -> IcsParseResult
```

where

```python
@dataclass
class IcsParseResult:
    events: list[IcsEvent] = field(default_factory=list)
    skipped: Counter = field(default_factory=Counter)
    error: str | None = None        # the whole document was unreadable
```

**The differences from the catalog's `parse_ics(content, context)`:**

1. **No `SourceContext`.** The context carries `source_id` and `source_url` — the
   catalog's identity inputs. The calendar has neither. A URL in the ICS is resolved
   against nothing, so `IcsEvent.url` keeps it *as written* and the catalog mapper
   resolves it.
2. **The return is `IcsParseResult`, not `ParseResult`.** `ParseResult` is the catalog's
   type, with `ParsedCandidate`s in it.
3. **`IcsEvent` keeps the `RECURRENCE-ID` and the `has_rrule` flag**, which the catalog's
   candidate does not (the catalog folds both into `source_event_id` and `series_id`).

**The behaviour is unchanged otherwise.** Same handling of: all-day spans, overnight
rolls, Windows zone mapping, malformed VEVENT isolation (one bad event never stops the
rest), the `MAX_ITEMS` cap, and the "never raises" promise.

**One decision: the `MAX_ITEMS` cap.** The catalog's is `MAX_ITEMS = 5_000`. A calendar
feed is a *single user's* calendar — it is small. But the cap protects the parser from a
hostile 500 MB file, and the byte limit already bounds the file. So: **the shared parser
keeps a cap**, at `MAX_EVENTS = 5_000`, the same value. One number, one place.

### 1.4 The two mappers

**The catalog mapper** — `apps/ingestion/parsers/ics.py` becomes a thin translation:

```python
def parse_ics(content: bytes, context: SourceContext) -> ParseResult:
    """The catalog's view of an ICS file: candidates, times as written, identity decided."""
```

It calls `formats.ics.parser.parse_ics`, then for each `IcsEvent` produces the same
`ParsedCandidate` the old code produced — **byte-for-byte the same output**, so the 21
existing tests in `tests/ingestion/parsers/test_ics.py` still pass unchanged.

**The calendar mapper** — in `adapters/calendar/ics.py`:

```python
def to_calendar_entry(event: IcsEvent) -> CalendarEntry | None
```

### 1.5 The identity rule (D10)

Both mappers use `domain.dedup.ics_item_id`, so the same event gets the same identity
string in both paths.

| The event | The catalog's `source_event_id` | The calendar's `uid` |
|---|---|---|
| A plain event | `uid` | `uid` |
| An `RRULE` master | `ics_item_id(uid, dtstart_utc)` | the same |
| A `RECURRENCE-ID` override | `ics_item_id(uid, recurrence_utc)` | the same |

**The catalog's existing behaviour for a plain event with no UID** is
`derived_id(url, title, raw_dtstart)`. The calendar has no `derived_id` — it has no
source URL to derive from and no catalog identity policy. So: **an event with no UID is
skipped by the calendar adapter**, counted as `no_uid`. A `CalendarEntry.uid` must be
non-empty and stable across imports, and a derived id from a title and a date is neither
stable nor meaningful in the personal calendar's namespace.

**The master's `uid` carries its instance suffix** — the same as the catalog. This is
what keeps a master and its override from colliding on the `(connection, uid)` unique
constraint.

---

## 2. Step 2 — `ports/`: the calendar's typed outcomes and validators

### 2.1 `ports/calendar.py`

```python
class CalendarError(DomainError):
    """Base for every calendar failure. Never carries the URL (AD-13)."""

class CalendarRevokedError(CalendarError):
    """The provider says the credential is no longer valid: the user must reconnect."""

class CalendarTransientError(CalendarError):
    """A temporary failure: 5xx, a timeout, a network error, a malformed response."""

class CalendarRefusedError(CalendarError):
    """We refused to fetch: a blocked scheme, a blocked address, an oversized body."""
```

Each carries a **reason slug** in `details`, never a URL, a host, or a path — the
`FetchError` convention exactly.

**`CalendarFeed`** gains `etag` and `last_modified`.
**`CalendarResult`** is new: `entries`, `etag`, `last_modified`, `not_modified`.
**`CalendarPort.fetch_entries`** returns `CalendarResult`.

### 2.2 `ports/fetch.py`

`fetch()` gains one keyword:

```python
allow_cross_host_redirect: bool = False
```

**The default is `False`, so every existing caller and every existing test is
unaffected.** The port's docstring says why it exists.

`FakeFetchAdapter.fetch` accepts and ignores it (it has no redirects). Its signature
must match the port's, or the registry's `issubclass` check is fine but the call would
break — so it takes the parameter and ignores it, with a comment.

---

## 3. Step 3 — `adapters/crawl/http.py`: honouring the cross-host redirect

**One change.** `_check_target` takes the flag:

```python
def _check_target(self, target, origin_host=None, *, allow_cross_host=False):
    ...
    if origin_host is not None and not allow_cross_host and not _same_host(target.host, origin_host):
        raise FetchBlockedError("cross_host_redirect")
```

**What does NOT change**, and this is the security-critical part:

- `GuardedBackend.connect_tcp` still refuses a denied address on **every** hop.
- The port check still runs on every hop.
- The scheme and userinfo checks still run on every hop.
- The deadline, the size budget, and the decompression budget are untouched.

**The relaxation is about the host, never the address.** A cross-host redirect to
`http://169.254.169.254/` is still refused — because the *address* is checked at connect
time, independently of which host the redirect came from.

**The default stays `False`.** `FetchLimits` does **not** grow a setting for it: it is a
property of the *call*, not of the deployment, and a settings key would make the
security-relevant default configurable by accident. The calendar adapter passes `True`
explicitly, in one place, in code a reader can see.

---

## 4. Step 4 — `adapters/calendar/ics.py`: the adapter

### 4.1 The scheme rules (D6)

```python
CALENDAR_SCHEMES = {"https": "https", "webcal": "https", "webcals": "https"}
```

`http://` and everything else → `CalendarRefusedError("scheme")`.

The normalisation happens at **fetch time**. The stored credential keeps the form the
user typed.

### 4.2 The status mapping (D4)

| HTTP status | Outcome |
|---|---|
| 401, 403, 404, 410 | `CalendarRevokedError("revoked")` |
| 429, 5xx, other 4xx, 3xx | `CalendarTransientError("http_status")` |
| 2xx | success |

**Every other failure**, from the fetch port:

| Fetch failure | Calendar outcome |
|---|---|
| `FetchTimeoutError` | transient |
| `FetchNetworkError` | transient |
| `FetchRedirectError` | transient |
| `FetchContentError` | transient |
| `FetchHTTPError(401/403/404/410)` | **revoked** |
| `FetchHTTPError(other)` | transient |
| `FetchBlockedError("address")` | **refused** |
| `FetchBlockedError("scheme"/"port"/"userinfo")` | **refused** |
| `FetchTooLargeError` | **refused** |

**The distinction that matters:** a *revoked* credential is the provider's verdict on the
user's credential; a *refused* fetch is **our** verdict on the request. A refused fetch
must never mark a calendar revoked — the user's calendar may be perfectly fine.

### 4.3 The limits (D7)

Named constants in the adapter, passed into the shared client:

```python
MAX_ICS_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 5
CONNECT_TIMEOUT = 5.0
READ_TIMEOUT = 15.0
WRITE_TIMEOUT = 5.0
TOTAL_TIMEOUT = 30.0
DNS_TIMEOUT = 3.0
```

The adapter builds a `FetchLimits` from them, **not** from `settings.SOURCE_FETCH` — a
calendar is a different shape from an RSS feed, and the limits are a property of the
adapter.

### 4.4 The mapping to `CalendarEntry` (D3)

```python
def to_calendar_entry(event: IcsEvent) -> CalendarEntry | None:
    """Resolve the event's times and shape it. None when it cannot be placed."""
```

1. **Resolve the zone.** `event.start_zone` is the IANA name (Windows already mapped).
   If the start is naive and has no zone, the event is **floating** — it cannot be
   placed → skipped as `floating_time`.
2. **`resolve_tz(start, source_zone=zone)`** → a `TzResolution` or a `TzRejection`.
   A rejection → skipped as `unresolvable_time`.
3. **The end.** The same resolver with `end=event.end`. If the end cannot be resolved,
   the entry's `ends_at` is the start (a zero-length event) — never a crash.
4. **`tz`** is the resolved zone. For an all-day event, the zone is the event's own zone
   (or `UTC` when it has none) — an all-day event's instant is local midnight.

**The all-day case, precisely:** an all-day event is `VALUE=DATE`, a *date*, not a time.
Its instant is the **local midnight of its date in its zone**. `formats.ics.times.
all_day_span` gives the naive midnight and the next midnight; `resolve_tz` then reads
that wall clock in the zone. An all-day event with no zone → `UTC`, because a date with
no zone has exactly one sensible reading: the UTC day.

**The floating case, precisely:** a `DTSTART` with no `TZID` and no `Z` is a wall-clock
time with no zone. `resolve_tz` rejects it. So does the calendar adapter: the event is
**skipped and counted**. It is not an error — a floating event is a normal thing to find
in a feed — but it cannot be placed on a timeline, and placing it wrongly would put the
user's event at the wrong hour.

**`resolve_tz` is `domain.timezones.resolve_tz`** — the same function the catalog
pipeline calls. There is one timezone resolver in the codebase.

### 4.5 The credential never leaks (D5)

- The crawl adapter's log line carries no URL (already true), and the calendar adapter
  adds **its own** log line with counts only: `job`, `status_code`, `entry_count`,
  `skipped_count`, `duration_ms`, `error_code`.
- **Every** exception is converted at the boundary, so no `httpx` exception — whose
  message contains the URL — ever escapes.
- The `httpx` logger stays at WARNING (`settings.LOGGING` already does this).

### 4.6 The port's fetch dependency (D9)

```python
class IcsCalendarAdapter(CalendarPort):
    def __init__(self, fetch: SourceFetchPort | None = None) -> None:
        self._fetch = fetch or get_fetch_port()
```

**Injected, not constructed**, so the adapter is testable with a scripted fetch and no
socket. `get_fetch_port` is in `ports.registry`, which `adapters` may import (the layers
contract puts `adapters` above `ports`).

---

## 5. Step 5 — the contracts and the configuration

### 5.1 The `layers` amendment

```toml
layers = [
    "config | worker",
    "apps | adapters",
    "formats",
    "ports",
    "domain",
    "shared",
]
```

`formats` sits below `apps`/`adapters` and above `ports`. It may import `ports`,
`domain`, `shared` and third-party libraries. It may import **neither `apps` nor
`adapters`** — which the layer ordering enforces.

**`root_packages` gains `"formats"`.**

### 5.2 The new contract

```toml
[[tool.importlinter.contracts]]
id = "single-ics-parser"
name = "AD-9 one ICS parser: only formats.ics imports the icalendar library"
type = "forbidden"
source_modules = ["domain","apps","ports","config","worker","shared","adapters"]
forbidden_modules = ["icalendar"]
allow_indirect_imports = true
```

`formats` is deliberately **absent** from `source_modules` — it is the one module allowed
to read ICS.

**A subtlety worth stating:** `allow_indirect_imports = true` is required, because
`config.api → apps.personalization.api → … → models → fields → credentials` style chains
exist. But for this contract the *direct* import is the violation, and that is what the
planted test asserts: a module in `apps` or `adapters` that imports `icalendar` directly
breaks the contract.

**The `adapters-independent` contract needs `formats` NOT to be an adapter.** `formats` is
a top-level package, not under `adapters`, so `adapters.*` never covers it. Good.

**But wait:** the `adapters-independent` contract lists `modules = ["adapters.*"]`. The
`formats` layer is separate. Fine.

### 5.3 The architecture test

`tests/architecture/checkers.py` gains `ROOT_PACKAGES += ("formats",)` so the AST checks
cover the new package — the `alias_violations` and `direct_write_calls` checks should
apply to it, and a `formats` module that writes to the database would be a bug.

**`formats` must not import Django.** It is a pure format library: no Django, no
database, no network. A test asserts it.

### 5.4 `config/adapters.py`

```python
CALENDAR_ADAPTER = "adapters.calendar.ics.IcsCalendarAdapter"
REAL_ADAPTERS = {
    "fetch": HTTP_FETCH_ADAPTER,
    "throttle": "adapters.throttle.redis.RedisThrottleAdapter",
    "calendar": CALENDAR_ADAPTER,
}
```

**The fake stays the local and CI default** — `FAKE_ADAPTERS["calendar"]` is unchanged.

---

## 6. Step 6 — the tests

### 6.1 `tests/formats/ics/test_parser.py` — the shared parser

The existing 21 tests in `tests/ingestion/parsers/test_ics.py` **move** to
`tests/formats/ics/test_parser.py`, retargeted at the new signature, plus new cases for
the `IcsEvent` fields the catalog never needed (`recurrence_id`, `has_rrule`).

**And the catalog's 21 tests stay where they are**, retargeted at the thin mapper — so
the catalog's output is proven unchanged by the move. That is the anti-fork test: the
same fixture, through two paths, and the catalog's answers are identical to what they
were before the refactor.

### 6.2 `tests/adapters/test_calendar_ics.py` — the adapter

| Group | Cases |
|---|---|
| **Schemes** | `https` used as is; `webcal` → `https`; `webcals` → `https`; `http` refused; `ftp` refused; a URL with userinfo refused |
| **Revocation** | 401, 403, 404, 410 → `CalendarRevokedError` — **one test per status** |
| **Transient** | 429, 500, 502, 503, 504, 400, 301-final → `CalendarTransientError`; a timeout; a network error; a malformed ICS |
| **Refused** | a blocked address; a blocked scheme; a body over the limit → `CalendarRefusedError`, and **never** revoked |
| **SSRF** | loopback, link-local metadata, a private range, an IPv6-embedded IPv4, and a **redirect from a public host to a private one** → all refused |
| **Limits** | an oversized body; a gzip bomb; too many redirects; a timeout — each a named constant's worth |
| **Parsing** | a Google-shaped fixture; an Apple-shaped fixture; an Outlook-shaped fixture; all-day; floating; a Windows `TZID`; an `RRULE` master; a `RECURRENCE-ID` override |
| **Identity** | the master's `uid` differs from its override's; both are stable across two imports |
| **Conditional** | the `ETag` is sent when supplied; a 304 is a success with `not_modified=True` and no entries |
| **No leaks** | each failure path, with log capture, asserts the URL is absent — including with the `httpx` logger at INFO |
| **Registered** | the adapter is in `REAL_ADAPTERS`; the fake is still the fake mode's default |

### 6.3 The SSRF tests, specifically

The work item names five cases. Each is a test:

1. **loopback** — `127.0.0.1` → refused
2. **link-local metadata** — `169.254.169.254` → refused
3. **private ranges** — `10.0.0.5`, `192.168.1.1`, `172.16.0.1` → refused
4. **IPv6-embedded IPv4** — `::ffff:127.0.0.1` → refused
5. **a redirect from a public host to a private one** → refused

**Case 5 is the important one**, because it is the case the cross-host relaxation could
have opened. The test serves a public host that 302s to a private address, and asserts
the fetch is **refused**, not followed. **This test is the proof that D1b's relaxation is
about the host and not the address.**

### 6.4 The scripted network

`tests/adapters/scripted_network.py` is **reused as is** — it already drives the real
`httpx`/`httpcore` stack with no sockets. The calendar tests build an `HttpFetchAdapter`
with the calendar's limits and inject it into `IcsCalendarAdapter`.

**The harness needs one addition**: a way to build the adapter with the *calendar's*
limits. `ScriptedNetwork.adapter(**limits)` already takes keyword overrides, so
`net.adapter(max_bytes=MAX_ICS_BYTES)` is enough — no change needed.

**A new `ScriptedFetch` fake** — a `SourceFetchPort` that returns canned results — goes
in `tests/adapters/calendar_fakes.py`, for the tests that do not need the network.

### 6.5 The fixtures

Three provider-shaped ICS files in `tests/fixtures/calendars/`:

- `google.ics` — a `TZID=America/Los_Angeles` event, an `RRULE` master, a
  `RECURRENCE-ID` override, a `VTIMEZONE` block
- `apple.ics` — an all-day event, a floating event, a `TZID=Europe/London` event
- `outlook.ics` — a **Windows** `TZID` (`"W. Europe Standard Time"`), which must map to
  `Europe/London`

**The existing `tests/fixtures/sources/calendar.ics` is already Outlook-shaped** (it has
`Eastern Standard Time` and `PRODID:-//Microsoft Corporation//Outlook 16.0`). The new
fixtures are *additional*, provider-shaped, and are used by the calendar tests.

---

## 7. Step 7 — the order of work

The order matters, because each step's tests depend on the previous step's shape.

1. **`formats/ics`** — move the parser, the times, the zones, the text. Add `IcsEvent`.
   Move the 21 catalog tests to `tests/formats/ics/` and add the new cases.
   *Gate: the 21 moved tests pass, unchanged in their assertions.*
2. **`apps/ingestion/parsers/ics.py`** — rewrite as the thin mapper. The 21 catalog
   tests stay and are retargeted at the mapper.
   *Gate: the catalog's output is byte-for-byte what it was.*
3. **`ports/`** — the calendar's outcomes, `CalendarResult`, the validators; `fetch()`'s
   new keyword.
4. **`adapters/crawl/http.py`** — honour `allow_cross_host_redirect`.
   *Gate: the existing 60+ crawl tests pass unchanged.*
5. **`adapters/calendar/ics.py`** — the adapter.
6. **The contracts** — the `layers` amendment, `single-ics-parser`, `root_packages`.
7. **`config/adapters.py`** — the registration.
8. **The adapter's tests** — the schemes, the statuses, the SSRF, the limits, the
   parsing, the leaks.
9. **The fixtures** — the three provider-shaped files.

---

## 8. Step 8 — the gates

| Gate | Command | Target |
|---|---|---|
| Tests | `pytest -q` | 0 failures; the existing 2363 still pass |
| Coverage | `pytest --cov` | ≥ 98% overall (floor 80%); `domain/` 100% (floor 100%) |
| Coverage, new code | `pytest --cov=formats --cov=adapters.calendar` | 100% |
| Lint | `ruff check .` | clean |
| Format | `ruff format --check .` | clean |
| Architecture | `lint-imports` | 17 kept, 0 broken (16 + `single-ics-parser`) |
| Django | `manage.py check` | no issues |
| Migrations | `manage.py makemigrations --check --dry-run` | no changes detected |

**The coverage target for the new code is 100%,** because this is the code that fetches a
user-supplied URL — the part where an untested branch is an SSRF hole or a leaked
credential.

---

## 9. What is deliberately not done

- **No RRULE expansion** (FR-31). A master produces one entry.
- **No polling, no scheduling, no import write** — `calendar-sync-and-polling`.
- **No HTTP endpoints** — `calendar-connect-api`.
- **No `CalendarConnection.etag` column** — the polling item owns that write. This item
  makes the *adapter* capable of conditional requests; the polling item stores the
  validators.
- **No venue lookup.** A personal calendar has no venue registry, so `CalendarEntry`
  carries no venue.

---

## 10. The risks, and what happens if a step goes wrong

| Risk | If it happens |
|---|---|
| Moving the parser changes the catalog's output | Step 2's gate is exactly this: the 21 catalog tests, retargeted, must pass **unchanged in their assertions**. |
| The `layers` amendment breaks an existing contract | `lint-imports` after step 6; the amendment is additive (a new layer), so the existing contracts' *relative* order is preserved. |
| The cross-host relaxation opens an SSRF hole | Step 4's tests, especially the redirect-to-private case. The address check is at connect time and is not relaxed. |
| The `formats` package becomes a dumping ground | The `single-ics-parser` contract and the "no Django" test. |
| The port's break (`list[CalendarEntry]` → `CalendarResult`) breaks a caller | There is no caller yet but the fake; both are updated in the same change. |


---

## Work Item: calendar-sync-and-polling

**Design doc**: `.specs-fire/intents/onboarding-and-account/work-items/calendar-sync-and-polling-design.md`
(approved 2026-10-29 — decisions D1–D17)

### Approach

The write side of calendar import, as **services** — no HTTP endpoints. Four commands
(`connect`, `sync`, `reconnect`, `disconnect`) plus the polling dispatcher.

The shape of the work is dictated by three facts already in the codebase:

- **A feed is a snapshot, not a delta.** So the sync is a *three-way diff* keyed on
  `(connection, uid)` — the unique constraint `personal_event_connection_uid_uq` already
  carries, created by the connection-model item for exactly this purpose (D1).
- **Every mutation goes through the existing command paths** (the work item's
  requirement), so the sync calls `create_personal_event` / `update_personal_event` /
  `delete_personal_event` rather than writing rows. That means those commands gain
  parameters — and the gain is where D2 and D11 live (D11).
- **A background sync has no user to prompt**, so FR-58's forced three-way prompt cannot
  run at import time. The pair is recorded; the prompt is presented later from
  `/conflicts` (D3).

The polling path **mirrors `ingestion`'s scheduling exactly**: the 60s tick enqueues a
dispatcher, the dispatcher claims due connections with `FOR UPDATE SKIP LOCKED` and a TTL,
and enqueues one sync per claim. `beat_schedule` stays exactly one tick (D8).

### The decisions that shape the code

| # | Decision | Where it lands |
|---|---|---|
| D1 | Three-way diff on `(connection, uid)`; identical → nothing | `calendar_sync.py` |
| D2 | User edit wins over the feed; `user_modified` flag | `PersonalEvent.user_modified` |
| D3 | Pair recorded, prompt deferred; "delete new" not offered for an import | `calendar_sync.py`, `conflict_resolutions.py` |
| D4 | Duplicate rule not applied vs. a user-created event | `detect_conflicts(..., include_duplicates=False)` |
| D5 | FR-20 default on import; attached on **create only** | `calendar_sync.py` |
| D6 | Revoked → `needs_reconnect`, **events kept** | `calendar_sync.py` |
| D7 | Transient → status alone, retry at the next due time | `calendar_sync.py` |
| D8 | Tick → dispatcher → atomic claim with a TTL | `calendar_sync.py`, `worker/tasks.py` |
| D9 | Connect **requests** a sync (`next_poll_at`), never fetches | `calendar_connections.py` |
| D10 | One `calendar.synced` audit row per sync, system actor, counts only | `calendar_sync.py` |
| D11 | The sync calls the existing commands; they gain import parameters | `personal_events.py` |
| D12 | A time change re-judges the pairs; the plan's slots are relative | inherited from the commands |
| D13 | Disconnect purges events + pairs + **plans** (via `delivery`) | `calendar_connections.py`, `reminder_plans.py` |
| D14 | The entry's own zone is the event's zone | `calendar_sync.py` |
| D15 | A failed fetch writes nothing | `calendar_sync.py` |
| D16 | The code layout | below |
| D17 | The log line carries counts only | `calendar_sync.py` |

### Files to create

| File | Purpose |
|---|---|
| `backend/apps/personalization/services/calendar_sync.py` | `sync_calendar`, the reconcile diff, `claim_due_connections`, `release_claim`. |
| `backend/apps/personalization/migrations/0003_…` | `PersonalEvent.user_modified`, `CalendarConnection.sync_claimed_at`. |
| `backend/tests/personalization/test_calendar_sync.py` | The sync: the three branches, idempotence, revoked/transient, the conflicts, the audit. |
| `backend/tests/personalization/test_calendar_polling.py` | The due-claim: atomicity, the TTL, the batch, the ordering. |
| `backend/tests/worker/test_calendar_tasks.py` | The dispatcher and the sync task. |

### Files to modify

| File | Change |
|---|---|
| `backend/apps/personalization/models.py` | `PersonalEvent.user_modified`; `CalendarConnection.sync_claimed_at`. |
| `backend/apps/personalization/services/calendar_connections.py` | `connect_calendar` sets `next_poll_at`; `disconnect_calendar` purges; `reconnect_calendar` added. |
| `backend/apps/personalization/services/personal_events.py` | `create_personal_event` / `update_personal_event` gain the import parameters and `user_modified`. |
| `backend/apps/personalization/services/conflicts.py` | `detect_conflicts(..., include_duplicates=False)`. |
| `backend/apps/personalization/services/conflict_resolutions.py` | "delete the new one" refused for an imported side (D3). |
| `backend/apps/delivery/services/reminder_plans.py` | `remove_plans_for_targets` (D13's step 4). |
| `backend/worker/tasks.py` | `schedule_calendars`, `sync_calendar`. |
| `backend/shared/constants.py` | `CALENDAR_SYNC_BATCH`, `CALENDAR_CLAIM_TTL`. |
| `backend/apps/personalization/admin.py` | The new columns, if listed. |

### Steps

1. **`shared/constants.py`** — `CALENDAR_SYNC_BATCH = 100`, `CALENDAR_CLAIM_TTL = 15 min`.
   *Gate: the constants exist and are used by nothing yet (ruff passes).*
2. **The models + migration** — `PersonalEvent.user_modified` (Boolean, default `False`),
   `CalendarConnection.sync_claimed_at` (nullable DateTime). `makemigrations` generates
   `0003`. *Gate: `manage.py check` and `makemigrations --check` pass; the existing
   personalization tests still pass.*
3. **`personal_events.py`** — the import parameters:
   - `create_personal_event(..., source=…, calendar_connection_id=…, source_uid=…,
     user_modified=False)`. The defaults keep every existing caller byte-for-byte
     unchanged.
   - `update_personal_event(..., user_modified=True)`.
   *Gate: the existing personal-event tests pass unchanged.*
4. **`conflicts.py`** — `detect_conflicts(..., include_duplicates: bool = True)`. The
   default keeps every existing caller unchanged; the import path passes `False`.
   *Gate: the existing conflict tests pass unchanged.*
5. **`reminder_plans.py`** — `remove_plans_for_targets(*, user_id, target_kind,
   target_ids) -> int`. *Gate: `delivery`'s tests pass unchanged.*
6. **`calendar_sync.py`** — the core. `sync_calendar(*, connection, actor, now)`:
   - fetch through `CalendarPort` (the port is injected, resolved from the registry);
   - classify the outcome (D6, D7);
   - diff the entries against the connection's rows (D1);
   - create / update / delete through the commands (D11);
   - write one audit row with the counts (D10);
   - schedule the next poll (D7, D9).
   Plus `claim_due_connections(*, now, limit)` and `release_claim(connection_id)` (D8).
7. **`calendar_connections.py`** — `connect_calendar` sets `next_poll_at = now` (D9);
   `disconnect_calendar` gains the purge (D13); `reconnect_calendar` is added (D9).
8. **`conflict_resolutions.py`** — refuse `delete_new` when the new side is an imported
   event (D3). *Gate: the existing resolution tests pass unchanged.*
9. **`worker/tasks.py`** — `schedule_calendars` and `sync_calendar` (D8). The tick gains
   one `_enqueue(schedule_calendars)` line. *Gate: `tests/worker/test_tick.py` passes
   **unchanged** — the acceptance criterion.*
10. **The tests** — the three new files.
11. **The full suite + lint + contracts.**

### The gates

| Gate | Command | Must hold |
|---|---|---|
| The suite | `pytest tests/ -q` | Everything passes; nothing broken |
| The tick | `pytest tests/worker/test_tick.py -q` | **Unchanged** — one 60s tick |
| Coverage | `pytest --cov` | ≥ the project's floor; the new module at 100% |
| Lint | `ruff check . && ruff format --check .` | Clean |
| Contracts | `lint-imports` | 17 kept, 0 broken |
| Django | `manage.py check` | No errors |
| Migrations | `makemigrations --check` | No drift |

### The risks

| Risk | If it happens |
|---|---|
| The sync writes rows directly and the two paths drift | Step 6 goes through the commands only; a test asserts the conflict pair exists after an import, which only happens via the command path |
| `user_modified` is set by the import's own update, freezing the mirror | The flag is an explicit parameter; the import passes `False` for an untouched row and preserves `True` for an edited one; a test covers both |
| The claim is not atomic and two ticks sync one connection twice | `select_for_update(skip_locked=True)` + the TTL; a test claims from two "ticks" and asserts one row |
| The disconnect leaves reminder plans behind | `remove_plans_for_targets` in `delivery`; a test asserts the plans are gone |
| A revoked fetch deletes the user's events | D6 keeps them; a test asserts the events survive |
| The duplicate rule fires between an import and a user event | `include_duplicates=False` on the import path; a test asserts no pair |
| A title or UID reaches a log line | D17; a test captures the logs over a full sync and asserts no title |

---

### What the implementation actually did (the deltas from the plan above)

The plan's eleven steps were followed in order. Four things came out differently from how
the plan wrote them, and each is recorded here because the plan is the record of what was
decided, not only what was predicted.

1. **Step 3 grew a second parameter.** The plan put `user_modified` on the two commands.
   The *duplicate* rule (D4) also had to be switchable on them, because the import's
   detection must skip it — and the import reaches detection only through the commands.
   So both commands gained `include_duplicate_conflicts: bool = True` alongside
   `user_modified`. The default keeps every existing caller unchanged.

2. **A second migration was needed.** The plan's step 2 named `0003` with the two fields.
   The port's `CalendarFeed` carries `etag` and `last_modified`, and `CalendarResult`
   returns new ones — but `CalendarConnection` had nowhere to keep them, so the 304 path
   could never work and every poll was a full download. `0004` adds `etag` and
   `last_modified` to the connection. A stale validator is cleared rather than kept: a
   stale `ETag` would make the provider answer 304 for a feed it has changed.

3. **`remove_plans_for_targets` writes one audit row per plan, not one for the batch.**
   The plan said "a command that deletes the plans for a set of targets". AD-5 says one row
   per mutation, and an audit row names a target — a single row for a bulk delete would
   have to name no target, and a row that names no target cannot say what changed. So each
   deleted plan gets its own row, carrying its target's id.

4. **The tick's enqueue list changed, in `test_scheduling_tasks.py`.** The acceptance
   criterion names `tests/worker/test_tick.py` — and that file is indeed unchanged. But
   `tests/worker/test_scheduling_tasks.py` pins the tick's enqueued job list, and the tick
   now enqueues `schedule_calendars` as well as `schedule_sources`. That file's
   expectation was updated to include the new dispatcher; the tick's *shape* (one 60s beat
   entry, enqueue-only, never touching the database) is unchanged.

### The module the plan named, and what is in it

`apps/personalization/services/calendar_sync.py` — the service, not the task. The task is
the trigger; the service is the work, and the service is testable without Celery.

| Function | What it does |
|---|---|
| `sync_calendar(*, connection_id, port, now)` | Fetch, classify, reconcile, audit, schedule (D1, D6, D7, D10, D15) |
| `claim_due_connections(*, now, limit)` | The atomic due-claim (D8) |
| `release_claim(connection_id)` | End a claim, however the job ended (D8) |
| `_reconcile(*, connection, result, now)` | The three-way diff (D1) |

**The reconcile is all-or-nothing.** A failed fetch writes no event row, no conflict pair
and no reminder plan — only the connection's own status and error fields, which are not
part of the reconcile (D15). A partial sync would delete half the user's imported events
because the feed happened to be truncated.

**The connection's row is not locked for the whole reconcile.** The claim that stops two
ticks syncing one connection is the dispatcher's (`sync_claimed_at`); holding a row lock
across a network fetch would hold a database connection open for the length of the fetch.

**Each write is its own transaction.** The commands are individually atomic, which is
their own guarantee. One transaction for the whole diff would roll back a correct update
because an unrelated event failed to write.

### The commands the import goes through

The import calls the same three commands the user's own edits use (D11), so an imported
event is indistinguishable from a user-created one except for its `source` and the
connection it names:

| The diff says | The command called | What the command brings |
|---|---|---|
| new uid | `create_personal_event` | the FR-20 default plan, the conflict detection, the audit row |
| changed uid | `update_personal_event` | the pair reconciliation, the version bump, the audit row |
| vanished uid | `delete_personal_event` | the pair closure, the audit row |

The two flags that make the import's calls different from the user's:

- `user_modified=None` — "leave the ownership as it stands". The import is applying the
  **feed's** value, not the user's, so it must not decide who owns the row. (The plan
  above said `False`; the code review found that `False` *resets* the flag, which hands
  the row back to the feed and lets the next poll overwrite the user's edit. A boolean
  cannot say "don't change it", so the parameter now has a third value — see the review's
  delta below.)
- `include_duplicate_conflicts=False` — an import is never a duplicate of a user-created
  event (D4). The time rule still applies.

### What the code review changed (the deltas from the plan above)

The review found five defects in the implementation this plan produced. Each is fixed,
regression-tested, and verified by reverting the fix and watching the test fail.

1. **`update_personal_event`'s `user_modified` gained a third value.** It is now
   `bool | None`: `True` (the user owns the row), `False` (the feed owns it) and `None`
   (leave it as it stands). The import passes `None`. The plan's `False` was a real
   defect — it *reset* the flag, so a user's edit could be overwritten by the next poll.

2. **The reconcile's ownership decision moved under a row lock.** It is now made against
   committed state, in the same transaction as the write, rather than against the
   snapshot the diff started with. A user edit landing mid-reconcile is protected.
   `_apply_updated` now returns whether it applied, so the counts are right too.

3. **The worker records an unexpected failure.** `calendar_sync.record_unexpected_failure`
   writes the next poll time and the error kind on the connection, so a failed calendar
   is retried at the poll cadence rather than the tick cadence. Without it, a failed
   calendar was re-fetched every 60 seconds, forever, each fetch carrying the user's
   secret address.

4. **`connect_calendar` and `reconnect_calendar` clear `sync_claimed_at`.** A claim left
   behind by a dead worker kept a reconnected calendar out of the claim filter, so D9's
   "synced within 60 seconds" was broken for up to the claim TTL.

5. **`purge_connection_events` was removed.** It was a raw `DELETE` that closed no
   conflict pairs, removed no reminder plans and wrote no audit rows, and it was the one
   a caller would reach for by name. `disconnect_calendar` is now the only way a
   connection's events are purged.

Two docstrings were also corrected: they said the reconcile was "all-or-nothing", which
contradicted `_reconcile`'s own docstring. D15's actual requirement — a failed *fetch*
writes nothing — holds and is tested; the reconcile is deliberately not atomic.


---

## Work Item: auth-api-and-session-seam

Mode: **confirm** (1 checkpoint — this plan).

### Approach

`account-auth-core` built the identity *services*. This item puts the HTTP surface over
them, and replaces the `current_user` seam in `apps/personalization/auth.py` with a
resolver that `identity` publishes.

The work splits into three movements.

**1. The seam is replaced in one place.**

`identity` publishes the resolver. It goes in `apps/identity/api_auth.py`, a module that
is *not* `apps/identity/models.py`, so the `models-identity` import contract is untouched
and other apps reach `identity` through a published interface. It exposes:

- `current_user(request)` — the signed-in user, or a 401 with "Please sign in to continue."
- `unauthenticated_user(request)` — the signed-in user, or `None`. For `GET /api/auth/me`,
  where anonymous is a normal answer rather than an error.

`apps/personalization/auth.py` then becomes a thin delegation to `identity`'s resolver.
Its own docstring is rewritten: it no longer says it is "the seam", because it is not any
more — it says it delegates, and why that keeps the diff to the existing routers at an
import change.

The shape is preserved exactly: `Router(auth=current_user)` and `request.user.pk` keep
working, so `apps/personalization/api.py` changes by **one import line** and nothing else.
That is the acceptance criterion "the seam is replaced in one place".

**2. The endpoints.**

A new `apps/identity/api.py` router, registered at `/api/auth` in `config/api.py`:

| Endpoint | Method | Behaviour |
|---|---|---|
| `/api/auth/csrf` | GET | Issues the CSRF token and sets the cookie. |
| `/api/auth/signup` | POST | Creates the account. Enumeration-safe. |
| `/api/auth/signin` | POST | Authenticates, establishes the session. Enumeration-safe. |
| `/api/auth/signout` | POST | Ends the session. |
| `/api/auth/me` | GET | The signed-in user, or 401. |
| `/api/auth/password-reset` | POST | Requests a reset. Enumeration-safe. |
| `/api/auth/password-reset/confirm` | POST | Consumes a token, sets the password. |

The router has **no** `auth=` of its own: sign-up and sign-in are how a session is created,
so requiring a session to get one would be circular. The authed endpoints resolve the user
explicitly through `identity`'s resolver.

**3. Enumeration safety, at the HTTP edge.**

The acceptance criterion is byte-identical bodies for a known and an unknown address. The
services are already enumeration-safe; this item makes the *responses* identical too.

- **Sign-up.** The service returns `SignUpOutcome()` either way. The endpoint answers
  `201` with `{"status": "accepted"}` for both. It must **not** establish a session for a
  duplicate address — the existing account holder is told by email, and signing the caller
  in would be the enumeration leak.
- **Sign-in.** A wrong password and an unknown address both raise
  `AuthenticationFailedError` (a 422 in `config/errors.py` today). The endpoint does **not**
  let that escape raw: it catches it and answers `401` with one fixed body, so the wire
  shape says "credentials did not work" and never says which half was wrong. The body is
  byte-identical across both cases *and* across the casing of the address.
- **Reset request.** The service returns `None` either way. The endpoint answers `202` with
  one fixed body for both.

The tests compare `response.content` byte-for-byte, not the parsed shape.

### The CSRF decision (the hard part)

The work item requires: "CSRF is enforced on every state-changing endpoint, and the
frontend has a documented way to obtain and send the token."

**What was probed.** Django Ninja 1.7.1 (the pinned version) was read, not guessed:

- `ninja/operation.py` sets `csrf_exempt = True` on **every** Ninja view wrapper. Django's
  `CsrfViewMiddleware` — which is in `MIDDLEWARE` — therefore **does not protect any Ninja
  endpoint**, including ours.
- `ninja/security/session.py`'s `SessionAuth` extends `APIKeyCookie`, and
  `APIKeyCookie._get_key` *does* call `ninja.utils.check_csrf`. But that check only runs
  for routers that declare `auth=` with a cookie-based handler. Our `current_user` is a
  plain function, not an `AuthBase` subclass, so it never reaches that check.
- The auth router has no `auth=` at all (sign-in cannot require a session), so **no**
  built-in check would run there either.

So: **Django's CSRF machinery is present and configured, but nothing in the stack calls it
for our endpoints.** Left alone, the auth endpoints would be CSRF-unprotected — and so
would the existing personal endpoints, which are state-changing and session-cookie-borne.

**The decision.** CSRF is enforced explicitly, in one place, using Django's own
`CsrfViewMiddleware` (via `ninja.utils.check_csrf`) rather than a hand-rolled token
comparison. Django's implementation is the one that gets the origin check, the referer
fallback, the masked-token comparison and the `CSRF_TRUSTED_ORIGINS` allowlist right.

The enforcement points are:

- `identity`'s resolver (`current_user`) calls the check **before** it resolves the user.
  That covers every authed endpoint in the project at once — the personal ones included —
  because they all go through the one resolver.
- The auth router's state-changing endpoints call it explicitly, because they have no
  `auth=` and so no resolver runs.

The check is applied only to unsafe methods (`POST`, `PUT`, `PATCH`, `DELETE`). `GET
/api/auth/me` and `GET /api/auth/csrf` are safe and are not checked — the latter *issues*
the token.

**The frontend's way to obtain and send the token.** `GET /api/auth/csrf` calls Django's
`get_token(request)`, which both returns the token and sets the `csrftoken` cookie. The
frontend reads the cookie and sends the token back in the `X-CSRFToken` header, which is
Django's own convention and what `CsrfViewMiddleware` reads. The proxy
(`frontend/proxy.ts`) must forward both the `Cookie` and `X-CSRFToken` headers — a
requirement this item records and the frontend item implements.

Because the browser holds the cookie on the **frontend's** origin and the request goes
through the proxy, Django's origin check compares the frontend's `Origin` header against
`CSRF_TRUSTED_ORIGINS`. That is D13's mechanism, already configured
(`config/env.py: csrf_trusted_origins` → `config/settings.py`). `USE_X_FORWARDED_HOST`
stays `False`.

**A hole worth naming.** Django's CSRF check refuses a request whose `Referer` is
cross-origin, and for a same-origin request it accepts the token in the `X-CSRFToken`
header. A request with **no** `Origin` and no `Referer` header (a plain `curl`, or a
non-browser client) is refused by Django too — Django requires one of them for HTTPS. The
tests therefore send an `Origin` header. That is the correct behaviour: a browser always
sends `Origin` on a cross-origin-unsafe request, so requiring it does not weaken the
protection against a browser, and it does refuse a scripted attacker who has no token.

### Files to Create

| Path | Purpose |
|---|---|
| `backend/apps/identity/api_auth.py` | The published resolver: `current_user`, `unauthenticated_user`, `require_csrf`. |
| `backend/apps/identity/api.py` | The `/api/auth` router: six endpoints plus the CSRF endpoint. |
| `backend/apps/identity/schemas.py` | Request and response schemas for the auth endpoints. |
| `backend/tests/identity/test_auth_api.py` | Endpoint tests: success, failure, enumeration, CSRF, 429, sign-out, 7-day expiry. |
| `backend/tests/identity/test_session_seam.py` | The seam: a real session through the real endpoint, then the personal endpoints; and the anonymous 401. |

### Files to Modify

| Path | Change |
|---|---|
| `backend/apps/personalization/auth.py` | Delegate to `identity`'s resolver. The seam is replaced **here, in one place**. |
| `backend/apps/personalization/api.py` | One import line: `current_user` now comes from `identity`. |
| `backend/config/api.py` | Register the `/api/auth` router. |
| `backend/tests/identity/conftest.py` | Fixtures for the API tests (client, CSRF helper, fixed clock). |
| `backend/tests/conftest.py` | Nothing — the existing personal-alias setup is enough. |
| `frontend/lib/api/openapi.json` | Regenerated by `make client` (never hand-edited). |
| `frontend/lib/api/schema.ts` | Regenerated by `make client` (never hand-edited). |

### Tests

- **Endpoint success paths**: sign-up creates the account and answers `201`; sign-in
  establishes the session; `me` returns the id, the email and the onboarding status;
  sign-out ends the session; reset-request and reset-confirm work.
- **Enumeration safety**: for sign-up, sign-in and reset-request, a known address and an
  unknown address produce **byte-identical** bodies and the same status. The comparison is
  on `response.content`, not on a parsed shape.
- **CSRF**: a state-changing request with no token is refused; one with a valid token
  succeeds; one with a wrong token is refused. The refusal is a 403 in the project's error
  shape.
- **429**: a throttled sign-in answers `429` with the project's error shape.
- **Sign-out ends the session**: after sign-out, `me` answers 401.
- **A 7-day-old session is expired**, using a fixed clock — not a sleep.
- **The personal endpoints work with a real session**: sign in through the real endpoint,
  then exercise `/api/personal/*` and the save endpoints. An anonymous request still gets
  401 with "Please sign in to continue."
- **No internals leak**: `me` never returns the password hash.

### Import contracts

`personalization` reaches `identity` through `identity`'s published interface
(`apps.identity.api_auth`), never through `apps.identity.models`. The `models-identity`
contract already forbids the latter, and `lint-imports` proves it.

### Risks

1. **CSRF breaking the existing personal endpoints.** The resolver now enforces CSRF, so
   the personal endpoints need a token they did not need before. That is the point — they
   are state-changing and session-cookie-borne — but the frontend must be updated in the
   same breath. The frontend item (`frontend-auth-surfaces`) carries that. The personal
   endpoint tests in this item are updated to send a token.
2. **`csrf_exempt` on the personal router.** The personal router's `auth=current_user` is a
   plain function, so Ninja's own cookie-CSRF check never runs for it. The resolver's
   explicit check is what closes that.
3. **Sign-in answering 422 instead of 401.** `AuthenticationFailedError` is a
   `ValidationError` subclass, so it maps to 422 in `config/errors.py`. The endpoint
   catches it and answers 401 itself, which is the right status for failed credentials.
   The exception mapping is not changed, because `config/errors.py` is one place for the
   whole project.

### Acceptance criteria mapping

| Criterion | Where it is met |
|---|---|
| Six endpoints exist, registered in `config/api.py` | `apps/identity/api.py`, `config/api.py` |
| Sign-up and sign-in establish a session | `django.contrib.auth.login` at the edge |
| The cookie is first-party | The browser only calls `/api/*` on its own origin through `frontend/proxy.ts` |
| `me` returns id, email, onboarding status; 401 when anonymous | `apps/identity/api.py` |
| `me` never returns the password hash | The schema has no field for it |
| Enumeration safety, byte-identical | The edge normalises every response |
| 429 with the project's error shape | `ThrottledError` → `config/errors.py` |
| CSRF enforced; frontend has a documented way | `require_csrf`, `GET /api/auth/csrf` |
| The seam is replaced in one place | `apps/personalization/auth.py` delegates |
| The personal endpoints work with a real session | `tests/identity/test_session_seam.py` |
| Services receive an explicit actor, never `request` | The services already do (D20) |
| OpenAPI regenerates; the client is regenerated with `make client` | `make client` |
| The import contracts pass | `lint-imports` |
| Tests cover every listed path | `tests/identity/test_auth_api.py` |

---

## Work Item: onboarding-state-and-interests

**Intent**: `onboarding-and-account` · **Mode**: confirm (1 checkpoint — this plan)
**Depends on**: `auth-api-and-session-seam` (complete)

### Approach

FR-1's onboarding flow needs server-side state: which step the user is on, what they picked,
and when the digest should arrive. This item builds that state and the HTTP surface over it.

The work splits into four movements.

**1. The vocabulary (`shared/constants.py`).**

`INTEREST_CHIPS` is one constant holding the ten chips with **stable keys** and display
labels. The keys are the contract: they are what the API accepts, what the database stores,
and what the frontend renders. They are slug-like (`tech_meetups`, `sports_fitness`, …) so a
label can change without invalidating a stored pick — a renamed chip must not orphan a
user's existing rows.

The frontend gets the list **from the API**, not from a second copy. The chips endpoint
projects the constant onto the wire, so the mockup's ten labels live in exactly one place.

**2. The models (`personalization`).**

Three models, all in the `personal` schema, all owned by `personalization` (AD-16), all
holding the user **by value** (OQ-8 — no FK to `User`):

| Model | Holds | Constraint |
|---|---|---|
| `Interest` | the user + one chip key | unique `(user_id, chip_key)` — **the DB constraint**, so a duplicate is impossible even under a race |
| `OnboardingProgress` | the user + current step + the moment they last moved | unique `user_id` |
| `DigestPreference` | the user + delivery time + IANA zone | unique `user_id` |

**The digest preference is a small dedicated model, not a `PREFERENCE_GRAPH`.** The work
item asks for that decision explicitly and says not to create a `PREFERENCE_GRAPH`
speculatively. A graph is a structure for a *set* of preferences with edges between them; a
digest's delivery time and zone are a single value with two parts, read as a unit and
written as a unit. A graph would add a node type, an edge type and a traversal for a value
that is one row. When a second, genuinely separate preference arrives (notification
language, digest frequency, quiet hours), *that* is when the shape is reconsidered — and the
plan records that so the next reader knows the decision was deliberate, not accidental.

**3. The commands (`apps/personalization/services/onboarding.py`).**

One module, four commands and three queries. Every command takes an explicit `Actor` and an
explicit `now`, opens one `transaction.atomic(using=PERSONAL)`, and writes its audit row
inside it (AD-5) — the same shape as `personal_events.py` and `saved_events.py`.

- `set_interests(...)` — **replaces** the user's set.
- `set_digest_preference(...)` — writes the delivery time and the zone.
- `advance_step(...)` / `skip_step(...)` — moves the progress row.
- `skip_onboarding(...)` — completes it in one move.
- `get_onboarding_state(...)` — the read.

**4. The surface (`/api/personal/onboarding`).**

A new router in `apps/personalization/api.py`, mounted under the existing `/api/personal`
prefix, so the endpoints are `/api/personal/onboarding/…`. The router keeps the existing
`auth=current_user`, so every endpoint is authed and scoped to the session user — and no
endpoint accepts a user id as input.

`GET /api/auth/me` gains the onboarding status, read through **`personalization`'s published
interface** (`apps.personalization.services.onboarding`), never through its models. The
`models-personalization` import contract already forbids `apps.identity` reaching
`apps.personalization.models`, and `lint-imports` proves it.

### The decisions that shape the code

| # | Decision | Why |
|---|---|---|
| D1 | Chip **keys** are stable slugs; labels are display-only | A renamed chip must not orphan stored picks |
| D2 | `Interest` is one row per chip, unique `(user_id, chip_key)` | The duplicate is impossible at the DB level, not just in the service |
| D3 | Setting interests **replaces** the set | The API is a *set*, not a delta; "I changed my mind" is one call |
| D4 | **Zero picks is valid** | That is how step 2 is skipped |
| D5 | The digest preference is a **dedicated model**, not a `PREFERENCE_GRAPH` | A single value with two parts is not a graph; the work item forbids the speculative one |
| D6 | The delivery time is a **local wall clock** + an IANA zone | The instant depends on the zone; storing a UTC time would freeze the user's intent |
| D7 | The zone is validated by **`domain.timezones.canonical_zone`** | The same validator personal events use, so "UTC" and "Etc/UTC" mean the same thing everywhere |
| D8 | Progress is **one row per user**, holding the current step | One row, one write, no ordering ambiguity |
| D9 | The resume window is **`ONBOARDING_RESUME_WINDOW`**, 7 days | A named constant, pinned by a test with a fixed clock |
| D10 | After the window, onboarding **restarts at step 1** | The stored step expires with it |
| D11 | **Complete is terminal** | A completed user is never sent back into onboarding |
| D12 | There are exactly **3 steps** | FR-1: "exceeds 3 steps … violates FR-1" |
| D13 | **Every step can be skipped**; no step requires input | FR-1 |
| D14 | Step 1 records that it was *passed*; it does not own the connection | The connection belongs to `calendar-connect-api` |
| D15 | The `me` endpoint reads the status through the published interface | AD-2 / the import contracts |

### The step model — exactly three, and a test that fails if a fourth appears

The steps are a **constant**, not a model's rows:

```python
ONBOARDING_STEPS = ("calendar", "interests", "digest")
ONBOARDING_STEP_COUNT = len(ONBOARDING_STEPS)
```

Step 1 is `calendar` — the optional calendar connect. Step 2 is `interests` — the chips.
Step 3 is `digest` — the delivery time and zone.

**A test fails if a fourth step is added.** The test asserts `ONBOARDING_STEP_COUNT == 3`
*and* that the tuple has exactly the three expected members. A bare `== 3` would pass on a
three-element tuple of the wrong steps; asserting the membership as well pins *which* three.
This is the acceptance criterion's "a test fails if a 4th is added" read literally.

The progress row stores the step as an **integer** (1, 2, 3), because the step's *position*
is what the resume rule is about ("resumed at the same step"). The step's identity is
resolved through the constant, so the two can never drift: the integer indexes
`ONBOARDING_STEPS`.

### The resume rule

> A user who leaves mid-step is resumed at the same step on return within 7 days.

The rule is stated in terms of *returning*, so the implementation is:

- `OnboardingProgress` holds `current_step` (1–3) and `last_advanced_at` (the moment the
  user last advanced, completed or skipped a step).
- On read, if `now - last_advanced_at > ONBOARDING_RESUME_WINDOW`, the stored step has
  expired: the read **restarts at step 1**. The row is rewritten at that point (in its own
  transaction), so the restart is not recomputed on every read.
- Within the window, the stored step is returned as-is.

**The boundary is pinned with a fixed clock.** The test asserts three points: at
`now - last_advanced_at == ONBOARDING_RESUME_WINDOW` the user is **still** resumed at the
stored step (the window is inclusive), one second beyond it they are **not**, and well
inside it they are.

**Complete is terminal.** A progress row with `completed_at` set is never returned as
"in progress", whatever the clock says. A completed user is never sent back into
onboarding — that is the acceptance criterion, and the read is where it is enforced.

### The digest preference's default

> A user who skips step 3 gets a documented default, held as a named constant.

```python
DEFAULT_DIGEST_DELIVERY_TIME = time(9, 0)
DEFAULT_DIGEST_TIMEZONE = "UTC"
```

Both are named constants in `shared/constants.py`, next to the chips. The default is
**written** when step 3 is skipped, not merely assumed at read time — so the preference is
always a real row with a real value, and `delivery` (which will consume the delivery time)
reads one row rather than branching on "was it set?".

The default is **9:00 in UTC**. It is deliberately boring and documented rather than clever:
a default that guessed the user's local zone would need the guess, and the guess would be
wrong for most of the world. The user changes it in one tap, or the Pulse Digest intent
refines it once the user's activity is known.

### The delivery time is a local wall clock

The delivery time is stored as a **`TimeField`** (a local wall clock, no zone) **plus** a
separate IANA zone. The pair is the whole preference.

Storing a UTC instant instead would be wrong in a way that only shows up twice a year: the
user says "9am", and a UTC instant is "9am once, then 8am or 10am after a DST change". A
wall clock + zone is what the user actually meant, and it is what `delivery` will read when
it computes the next send time.

### The interests' shape

`set_interests` takes a list of **chip keys**, not labels. The service:

1. Refuses more than `MAX_INTEREST_PICKS` (3) — with a calm message.
2. Refuses an unknown key — with a calm message, and **naming** the offending key so the
   caller can see which one was wrong.
3. Refuses duplicates within one call? No — a duplicate is **deduplicated**, not refused.
   The DB constraint forbids a duplicate *row*; a caller sending the same key twice has not
   made a mistake worth a refusal, and deduplicating is friendlier. The constraint still
   holds, because the set is written once, atomically.
4. Zero picks is valid: it clears the set. That is how step 2 is skipped.
5. **Replaces**: the old rows are deleted and the new ones written in the same transaction.
   A user who goes from three chips to one has one chip afterwards, not four.

The refusals are `ValidationError` subclasses with their own codes, so the client can tell
"too many" from "unknown key" — but both carry a **calm** message, per the project's voice.

### The surface

| Endpoint | Method | Behaviour |
|---|---|---|
| `/api/personal/onboarding` | GET | The whole state: progress, interests, digest preference, the chip list |
| `/api/personal/onboarding/interest-chips` | GET | The ten chips, from the constant |
| `/api/personal/onboarding/interests` | PUT | **Replace** the user's picks |
| `/api/personal/onboarding/digest-preference` | PUT | Set the delivery time and zone |
| `/api/personal/onboarding/step` | POST | Advance to the next step |
| `/api/personal/onboarding/step/skip` | POST | Skip the current step |
| `/api/personal/onboarding/skip-all` | POST | Skip everything; onboarding is complete |

`PUT` for the two setters, because they **replace** a resource — that is what `PUT` means,
and `POST` would imply a create. `POST` for the three step movers, because they are
transitions, not idempotent replacements of a body.

Every endpoint is scoped to `request.user.pk`. **No endpoint accepts a user id as input**
— the same rule the rest of the personal surface follows, so the scoping cannot be talked
out of by a payload.

### `GET /api/auth/me` gains the onboarding status

The schema gains two fields:

```python
class CurrentUserOut(Schema):
    id: UUID
    email: str
    onboarding: OnboardingStatusOut
```

`OnboardingStatusOut` carries `completed: bool` and `current_step: int | None` — enough for
the frontend to decide "show onboarding, or show home". It carries **no** interests and
**no** digest preference: the `me` endpoint is about who the user is, not about their
settings, and a settings blob there would grow without bound.

`identity` reads the status through `personalization`'s **published interface** — the
service function, never the model. The `models-personalization` import contract forbids
`apps.identity` → `apps.personalization.models`; the published-service call is exactly the
seam the architecture intends.

**A circular import is the risk here, and it is real.** `identity` → `personalization`
(services) → `delivery` (services) → … must not loop back into `identity`. The
`personalization` service module imports nothing from `identity`, so the arrow is one-way.
`lint-imports` proves it.

### Files to Create

| Path | Purpose |
|---|---|
| `backend/apps/personalization/services/onboarding.py` | The commands and queries: interests, digest preference, progress. |
| `backend/apps/personalization/schemas.py` (added to) | The onboarding wire shapes. |
| `backend/tests/personalization/test_onboarding_constants.py` | The chip list, the step count, the defaults. |
| `backend/tests/personalization/test_onboarding_models.py` | The constraints: the chip uniqueness, the retention categories, the step check. |
| `backend/tests/personalization/test_onboarding_commands.py` | The commands: replace, the 3-pick limit, the unknown key, the IANA refusal, the resume window, the terminal state. |
| `backend/tests/personalization/test_onboarding_api.py` | The endpoints: the authed scope, the projections, the refusals. |

## Files to Modify

| Path | Change |
|---|---|
| `backend/shared/constants.py` | `INTEREST_CHIPS`, `ONBOARDING_STEPS`, `ONBOARDING_STEP_COUNT`, `MAX_INTEREST_PICKS`, `ONBOARDING_RESUME_WINDOW`, `DEFAULT_DIGEST_DELIVERY_TIME`, `DEFAULT_DIGEST_TIMEZONE`. |
| `backend/apps/personalization/models.py` | `Interest`, `OnboardingProgress`, `DigestPreference`. |
| `backend/apps/personalization/migrations/0005_*.py` | The three tables. |
| `backend/apps/personalization/api.py` | The `/onboarding` endpoints. |
| `backend/apps/personalization/admin.py` | Read-only registrations, if the file has any. |
| `backend/apps/identity/api.py` | `me` gains the onboarding status. |
| `backend/apps/identity/schemas.py` | `CurrentUserOut` gains `onboarding`. |
| `backend/domain/errors.py` | The typed refusals: too many picks, unknown chip, onboarding already complete. |
| `backend/apps/personalization/services/__init__.py` | Export the new commands. |
| `frontend/lib/api/openapi.json`, `frontend/lib/api/schema.ts` | Regenerated by `make client` (never hand-edited). |

## The models, in detail

```python
class Interest(UUIDv7Model):
    """One interest chip the user picked."""

    retention_category = RetentionCategory.PREFERENCE_SIGNALS

    # The user, by value (OQ-8): no relation to User.
    user_id = models.UUIDField()
    # A stable key from `shared.constants.INTEREST_CHIPS`, e.g. "tech_meetups".
    chip_key = models.CharField(max_length=64)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user_id", "chip_key"], name="interest_user_chip_uq"
            ),
        ]
        indexes = [models.Index(fields=["user_id"])]
```

`PREFERENCE_SIGNALS` is the right retention category: a chip is a signal about the user,
not account content and not an audit log.

```python
class OnboardingProgress(UUIDv7Model):
    """Where the user is in the 3-step onboarding flow."""

    retention_category = RetentionCategory.PREFERENCE_SIGNALS

    user_id = models.UUIDField()
    # 1..3 — the index into `shared.constants.ONBOARDING_STEPS`.
    current_step = models.PositiveSmallIntegerField(default=1)
    # The moment the user last advanced, completed or skipped.
    last_advanced_at = models.DateTimeField()
    # Set when onboarding ends. A completed user is never sent back into it.
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user_id"], name="onboarding_progress_user_uq"
            ),
            models.CheckConstraint(
                condition=models.Q(current_step__gte=1) & models.Q(current_step__lte=3),
                name="onboarding_progress_step_ck",
            ),
        ]
```

**The step check constraint is the database's copy of D12.** The constant is the source of
truth; the constraint is the backstop for a row written by something other than the
service. Both say 3, and the test asserts the constant is 3 — so a fourth step would have to
change the constant, the constraint *and* the migration before the check would stop it.

```python
class DigestPreference(UUIDv7Model):
    """When and where the Pulse Digest should arrive."""

    retention_category = RetentionCategory.PREFERENCE_SIGNALS

    user_id = models.UUIDField()
    # A local wall clock (HH:MM), NOT an instant. Paired with `timezone`.
    delivery_time = models.TimeField()
    # An IANA zone name, e.g. "America/Los_Angeles". Validated by the command.
    timezone = models.CharField(max_length=64)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user_id"], name="digest_preference_user_uq"
            ),
        ]
```

**`timezone` as a column name.** Django's `models.TimeField` is a time; the zone is a
string. The column is called `timezone` because that is what it is — but it shadows nothing,
and it is not `models.TimeField`. `start_time_tz` is the precedent in `PersonalEvent`.

## The commands, in detail

### `set_interests`

```python
def set_interests(
    *, user_id: UUID, chip_keys: Sequence[str], actor: Actor, now: datetime
) -> InterestSetSnapshot
```

1. **Validate the count.** More than `MAX_INTEREST_PICKS` → `TooManyInterestsError`.
2. **Validate the keys.** Each key must be in the constant's key set → `UnknownInterestError`
   naming the key. The check is against the *constant*, not against the database, so an
   unknown key is refused before any write.
3. **Deduplicate**, preserving the caller's order.
4. **Replace**, in one transaction: delete the user's rows, insert the new ones, write the
   audit row.

The replace is one transaction because a half-applied set is worse than a failed one: the
user would see picks they did not choose.

**The audit row** carries the count and the keys — the keys are not sensitive (they are a
fixed public list), and an audit row that says only "3 interests changed" cannot say *what*.

### `set_digest_preference`

```python
def set_digest_preference(
    *, user_id: UUID, delivery_time: time, timezone_name: str, actor: Actor, now: datetime
) -> DigestPreferenceSnapshot
```

1. **Validate the zone** with `domain.timezones.canonical_zone` — the same validator
   personal events use. `None` → `InvalidTimezoneError`. The canonical name is stored, so
   "Etc/UTC" is stored as "UTC".
2. **Validate the time** is a real `time` (the schema already guarantees the type; a
   `time` with a non-zero tzinfo would be a wall clock *with* an offset, which is not what
   this field means — the service refuses one).
3. **Write** in one transaction, with the audit row.

The write is an **upsert**: one row per user, so setting the preference twice updates it.

### The progress commands

```python
def get_onboarding_state(*, user_id: UUID, now: datetime) -> OnboardingStateSnapshot
def advance_step(*, user_id: UUID, actor: Actor, now: datetime) -> OnboardingStateSnapshot
def skip_step(*, user_id: UUID, actor: Actor, now: datetime) -> OnboardingStateSnapshot
def skip_all(*, user_id: UUID, actor: Actor, now: datetime) -> OnboardingStateSnapshot
```

**`get_onboarding_state`** is the read, and it is where the resume rule and the terminal
rule live:

- No progress row → the user is at step 1, in progress. (The row is created lazily on the
  first *write*, so a user who only ever reads does not get a row.)
- A row with `completed_at` set → **complete**, whatever the clock says.
- A row whose `last_advanced_at` is older than the window → **restart at step 1**, and the
  row is rewritten in its own transaction.
- Otherwise → the stored step.

**`advance_step`** moves `current_step` forward by one and sets `last_advanced_at = now`.
Advancing past step 3 **completes** the onboarding: step 3 is the last one, so there is no
step 4. That is D12 at the command level — the flow cannot have a fourth step because
advancing from 3 ends it.

**`skip_step`** moves to the next step the same way, but the difference is *what was
recorded*:

- Skipping step 1 (calendar) writes nothing else — the connection belongs to
  `calendar-connect-api`.
- Skipping step 2 (interests) clears the interest set (D4: zero picks is valid).
- Skipping step 3 (digest) writes the **default** digest preference (the named constants).

So a skipped step 3 leaves a real, default-valued preference row, and `delivery` will read
one row rather than branching on whether it was set.

**`skip_all`** completes the onboarding in one move: it writes the default digest
preference, clears the interests, and sets `completed_at = now`. A user who skips
everything has still finished onboarding — which is FR-1's "a user who skips everything
still finishes onboarding".

**Every command refuses to act on a completed user.** `advance_step`, `skip_step` and
`skip_all` on a completed onboarding raise `OnboardingAlreadyCompleteError`. D11 is
terminal, and the refusal is at the command, not at the edge — so every caller gets it.

### The tests

| Test | What it pins |
|---|---|
| `test_the_chip_list_is_the_ten_from_the_mockup` | The constant's exact labels, in order |
| `test_the_chip_keys_are_stable_slugs` | The keys are slug-shaped and unique — a renamed label must not change a key |
| `test_there_are_exactly_three_onboarding_steps` | The step count **and** the step membership (D12) |
| `test_a_fourth_step_would_break_the_test` | The same assertion, stated as the cap |
| `test_the_resume_window_is_seven_days` | The named constant's value |
| `test_the_default_digest_preference_is_the_documented_one` | The two named defaults |
| `test_the_same_chip_cannot_be_held_twice` | The DB constraint fires on a direct second insert |
| `test_setting_interests_replaces_the_set` | Three chips then one → one chip, and the old rows are gone |
| `test_more_than_three_picks_is_refused` | The limit, with a calm message |
| `test_an_unknown_chip_key_is_refused` | The key is named in the refusal |
| `test_zero_picks_is_valid_and_clears_the_set` | D4 |
| `test_a_duplicate_key_in_one_call_is_deduplicated` | Not refused |
| `test_a_non_iana_timezone_is_refused` | D7 — the same validator as personal events |
| `test_the_zone_is_stored_canonically` | "Etc/UTC" → "UTC" |
| `test_a_user_is_resumed_at_the_same_step_within_the_window` | The resume rule, fixed clock |
| `test_a_user_at_the_window_boundary_is_still_resumed` | The boundary is **inclusive** |
| `test_onboarding_restarts_at_step_one_after_the_window` | D10 |
| `test_skipping_the_digest_step_writes_the_default_preference` | The default is written, not assumed |
| `test_skipping_the_interests_step_clears_the_set` | D4 through the step |
| `test_skip_all_completes_onboarding` | FR-1's "a user who skips everything still finishes" |
| `test_a_completed_user_is_never_sent_back_into_onboarding` | D11 — including after the window expires |
| `test_advancing_past_the_last_step_completes_onboarding` | D12 at the command level |
| `test_every_step_can_be_skipped_with_empty_input` | FR-1: no step requires input |
| `test_the_endpoints_require_a_session` | The auth scope |
| `test_the_endpoints_are_scoped_to_the_session_user` | Another user's rows are invisible |
| `test_the_chip_endpoint_projects_the_constant` | The frontend gets one source |
| `test_me_carries_the_onboarding_status` | The `me` addition |
| `test_me_does_not_carry_the_interests_or_the_digest_preference` | `me` is about who, not what |

## The gates

| Gate | Command | Must hold |
|---|---|---|
| Tests | `pytest tests/ -q` | 0 failures; the existing 2710 still pass |
| Coverage | `pytest --cov` | The project's floor; the new module at 100% |
| Lint | `ruff check . && ruff format --check .` | Clean |
| Contracts | `lint-imports` | 17 kept, 0 broken |
| Django | `manage.py check` | No issues |
| Migrations | `makemigrations --check --dry-run` | No drift |
| Client | `make client` | The committed schema matches the regenerated one |

## The risks

| Risk | If it happens |
|---|---|
| `identity` → `personalization` creates an import cycle | The service module imports nothing from `identity`; `lint-imports` proves it |
| The step constant and the DB check constraint drift | Both say 3, and the migration carries the constraint; a test asserts the constant |
| The replace is not atomic and the user sees a half-applied set | One `transaction.atomic(using=PERSONAL)`; a test asserts the old rows are gone |
| The resume rule is off by one at the boundary | The window is inclusive and pinned by a test at the exact instant |
| A completed user is sent back into onboarding after 7 days | The read checks `completed_at` **before** the window; a test covers it |
| The frontend keeps a second copy of the chips | The API is the only source; the frontend item reads it |
| A 4th step is added later without noticing | The step count test fails; the constraint backstops it |

## Acceptance criteria mapping

| Criterion | Where it is met |
|---|---|
| `INTEREST_CHIPS` is one constant, with stable keys and labels | `shared/constants.py`; `GET /onboarding/interest-chips` |
| The frontend gets the list from the API | The endpoint; the frontend item reads it |
| An `Interest` model holds the user by value and a chip key | `apps/personalization/models.py` |
| One user can't hold the same chip twice (DB constraint) | `interest_user_chip_uq` |
| Setting interests replaces the set | `set_interests` |
| >3 picks or an unknown key is refused, calmly | `TooManyInterestsError`, `UnknownInterestError` |
| Zero picks is valid | `set_interests` with an empty list |
| The digest holds a delivery time and an IANA zone | `DigestPreference` |
| A non-IANA or ambiguous zone is refused, by the same validator | `domain.timezones.canonical_zone` |
| A skipped step 3 gets a documented default, a named constant | `DEFAULT_DIGEST_DELIVERY_TIME`, `DEFAULT_DIGEST_TIMEZONE` |
| Progress records the step and the last advance | `OnboardingProgress` |
| Resume within 7 days; restart after; a named constant | `ONBOARDING_RESUME_WINDOW`; the read |
| Complete or skip-all completes; completed is terminal | `skip_all`; the commands refuse a completed user |
| At most 3 steps; a test fails if a 4th is added | `ONBOARDING_STEPS`; the step-count test |
| Every step can be skipped | `skip_step`; the empty-input test |
| The endpoints under `/api/personal/onboarding`, authed and scoped | `apps/personalization/api.py` |
| `me` gains the onboarding status, through the published interface | `apps/identity/api.py` → the service |
| Every new model declares a retention category | The three models |
| `lint-imports` and `manage.py check` pass | The gates |
| Client regenerated | `make client` |
| The tests cover the listed cases | The test table above |

---
*Plan pending approval at checkpoint.*

---

## Work Item: onboarding-state-and-interests — Post-Review Amendments

The plan above is the plan as approved. The code review found five defects and fixed
them; three of them changed the plan, and the amendments are recorded here so the plan
and the code agree.

### A1 — The read became read-only (plan decision D8 reversed)

**The plan said**: the restart is *written*, not recomputed on every read, "so two reads
a second apart agree about the step".

**The review found**: a write behind a `GET` is a **cross-site write**. Django Ninja
exempts every view from Django's CSRF middleware, and the project's own check runs on
unsafe methods only — so a hostile page could restart a user's onboarding flow with a
plain `<img src="/api/auth/me">` and no token at all. `me` is on the hot path, so it also
put a row lock and an `UPDATE` on every authenticated request.

**The amendment**: `get_onboarding_state` now *reports* step 1 for an expired flow and
leaves the row alone. The restart became a command — it happens in `_require_incomplete`,
under the user's lock, in its own transaction.

**The plan's goal is met more strongly, not less.** The original reason for writing the
restart was that two reads must agree. The new answer is derived from `last_advanced_at`
and the window — facts, not from a row that may or may not have been touched — so two
reads agree *without* depending on a write having happened.

### A2 — A concurrency guarantee was added (new plan decision)

The plan did not mention concurrent requests at all. The review found that two concurrent
commands for the same user both found no row and both inserted, and the loser of that
race got a raw `IntegrityError` from a unique constraint — a **500**.

**The amendment**: every command takes the user's **transaction-scoped advisory lock**
(`pg_advisory_xact_lock`, keyed by `blake2b(user_id)` under a dedicated personalisation)
before it reads or writes. The lock is on a *key*, not a row, because the case that
matters most is the one where no row exists yet — a user's very first command. It is
released when the transaction ends, so a crashed worker cannot wedge a user.

A new test file, `tests/personalization/test_onboarding_concurrency.py` (9 tests), pins
it.

### A3 — The row locks were removed as redundant

The first implementation of A2 used `select_for_update()` row locks plus an
`IntegrityError` retry. A revert that removed the row locks and kept the advisory lock
still passed every test — so the row locks were redundant, and were removed. One
mechanism is easier to reason about than two.

### A4 — One existing test was rewritten

`test_the_restart_is_written_not_recomputed` asserted `last_advanced_at == expired`
after a read. It pinned the defect. It was replaced by `test_a_read_never_writes`,
`test_two_reads_of_an_expired_flow_agree` and `test_a_command_restarts_the_expired_flow`.

### A5 — `DigestPreferenceOut` is nested, not top-level

The plan sketched `DigestPreferenceOut` as a sibling schema. It is nested inside
`OnboardingStateOut` as the `digest` field, so the digest preference's shape lives in
one place — it is always read as part of the state, and is never a response body of its
own.

---

# Implementation Plan: Calendar Connect API (FR-50, AD-18, AD-19)

**Work item:** `calendar-connect-api`  **Mode:** confirm  **Checkpoint:** plan
**Depends on:** `auth-api-and-session-seam`, `calendar-sync-and-polling`

## Approach

The HTTP surface over the calendar commands that already exist. The work item is
mostly a **projection problem**: `apps/personalization/services/calendar_connections.py`
already publishes `connect_calendar`, `reconnect_calendar` and `disconnect_calendar`,
and the model already holds every field the wire shape needs. What does **not** exist
yet is the read side and the wire shapes.

### The one thing that has to be built: a read service

The API layer may not import `apps.personalization.models` — the `models-personalization`
import contract forbids it — so a list endpoint cannot query the ORM itself. There is
currently **no** read service for connections: `calendar_connections.py` holds only the
three write commands, and `calendar_sync.py` holds the worker's own lookups. So this
item adds a read service, in `calendar_connections.py`, next to the commands that write
the rows it reads. It is the same shape as `onboarding.get_onboarding_state`: a plain
dataclass of plain data, and no ORM types escape the module.

The read service returns **only** what is safe to show: the id, the provider, the
status, the times and the sync state. It never touches `credential`, and it never
touches `credential_fingerprint` either — the fingerprint is a keyed HMAC, so it is not
a secret, but it is not the user's business either, and a digest in a response body is
one more thing to leak in a screenshot.

### The address is the credential, and it never leaves the service

The secret ICS/webcal address **is** the credential (Google classifies it as one and
offers a reset for it). Three rules follow, and each gets a test:

1. **No response body contains it.** Not in full, not masked, not as a fragment. The
   projection simply has no field for it, so the guarantee is structural rather than
   careful: there is nowhere for the address to go.
2. **No error message echoes it.** The existing `InvalidCalendarCredentialError` already
   never echoes the address (`details={"field": "url"}` only), and
   `CalendarProviderCapReached` carries only `{"cap": 1}`. The new SSRF refusal
   follows the same rule.
3. **No log line carries it.** Django's request logging logs the path and the query
   string, never the body — but the body is not the only risk. The address can appear
   in a `repr` of a validation error, in a pydantic error's `input`, or in an
   unhandled exception's traceback. The API layer will therefore never include the
   address in a raised error's `details`, and the test proves it with log capture on a
   *failing* request.

### The Free cap: a typed refusal with the approved copy

The cap is enforced in the **service**, not the API — `connect_calendar` raises
`CalendarProviderCapReached` when the user already holds a slot. The API's job is to
let that error through as a **calm, typed** refusal.

The copy comes from the approved UX spine, not from fresh writing:

| Source | Copy |
|---|---|
| `EXPERIENCE.md` §3 microcopy, "Free-tier save-cap prompt" | *"You saved one event today. Save more with Pro."* |
| `EXPERIENCE.md` §4, Browse save-quota-exceeded (inline, not modal) | *"You've used your 1 free save today. Upgrade for unlimited."* + a quiet `Text.Meta` "Upgrade" link |
| `domain/errors.py`, `CalendarProviderCapReached.default_message` | *"You've connected the calendars your plan allows."* |

The **shape** the approved copy implies: an inline prompt with a quiet "Upgrade" link,
**not** a modal. So the payload carries a code and a message and a plain data detail —
and **no modal semantics**: no `"modal": true`, no `"title"`, no `"actions"`, no
`"dismissable"`. A test asserts the payload's key set exactly, so a future edit that
adds a modal-shaped field fails.

The status is a **409 Conflict**, not a 400. The request is well-formed — the address
is a valid address — it conflicts with the state of the account. This mirrors the
decision already taken for `OnboardingAlreadyCompleteError` in the previous item: a
conflict with the flow's state is a 409. `CalendarProviderCapReached` currently extends
`DomainError`, which `config/errors.py` maps to **400**; it will be re-based on
`ConflictError`.

### The SSRF policy

The acceptance criteria name "an address the SSRF policy refuses" as one of the invalid
addresses. The SSRF policy lives in `adapters/crawl/address_policy.py` — a **deny
table** of IP ranges — and it is enforced today at *connect time*, inside
`GuardedBackend.connect_tcp`, on every redirect hop. That is the right place for it:
a deny table needs to see the *resolved* address, or DNS rebinding defeats it.

But a connect-time refusal is invisible at connect time. The user pastes an address,
the row is created, and the first poll — up to a minute later, in a worker, with no
user watching — fails. So the API has a **pre-flight** check: the address's host is
resolved *before* the row is created, and a host that resolves to a denied address is
refused with a calm message. This is a **convenience**, not the policy: the connect-time
check in `GuardedBackend` still runs and still refuses, so the pre-flight cannot be
bypassed by a rebind between the check and the fetch.

The pre-flight lives in the **service**, not the API — the same rule as the cap: a
policy that only one caller enforces is a policy another caller walks past. It is
implemented in `calendar_connections.py` as a shape check over the host, reusing
`adapters.crawl.address_policy.is_denied`.

### The provider is a label, not a branch

The work item's technical note is explicit: *"The provider value doesn't change any
server behaviour... Keep provider-specific logic out of the services."* So `provider` is
stored, echoed back and validated against the model's `Provider` choices — and nothing
branches on it. The API layer does not know what Google is.

### The first sync is enqueued, not run inline

`connect_calendar` already sets `next_poll_at = now`, which is the durable expression
of "sync this soon": the dispatcher's tick picks it up within 60 seconds. AD-11 forbids
long work in a request, and a calendar fetch can take 30 seconds and download
megabytes. So the connect endpoint returns immediately with the connection's status and
sync state, and the response says the first sync is **pending** — never "done", and
never "failed".

### The sync state the client needs

Onboarding step 1 has to show imported events "without leaving the onboarding flow"
(FR-3), so the wire shape carries the sync state explicitly:

| Field | Meaning |
|---|---|
| `status` | `active` / `needs_reconnect` / `disconnected` — the connection's health |
| `last_synced_at` | when the last poll finished; null if it never has |
| `sync_in_progress` | a worker holds the claim right now |
| `next_sync_at` | when the next poll is due |
| `last_error_kind` | a **slug** (`revoked`, `transient`, …) — never a message, never a URL |

`last_error_kind` is a slug because an `httpx` exception message contains the full
request URL, which **is** the credential (AD-13). The model already stores only slugs;
the projection keeps that discipline.

`sync_in_progress` is `sync_claimed_at is not null` **and** the claim is fresh — a
claim older than `CALENDAR_CLAIM_TTL` is a lost job (a worker died), and showing it as
"in progress" forever would be a lie. The projection compares the claim against `now`,
so it needs the clock; the read service takes `now` explicitly, like every other
service in this codebase.

## Files to Create

| File | Purpose |
|------|---------|
| `backend/tests/personalization/test_calendar_connect_api.py` | The endpoint contract: list, connect, the cap, each invalid-address refusal, reconnect, disconnect, cross-user 404, and that no response or log carries the address |
| `backend/tests/personalization/test_calendar_connection_reads.py` | The read service: the projection, the sync-in-progress flag, the expired-claim case, and that the address and the fingerprint never appear in what it returns |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/apps/personalization/services/calendar_connections.py` | Add the read service (`list_calendar_connections`, `get_calendar_connection`), the SSRF pre-flight, and the `CalendarConnectionNotFoundError`; add `CalendarConnectionNotFoundError` to `domain/errors.py` |
| `backend/domain/errors.py` | Add `CalendarConnectionNotFoundError(NotFoundError)`; re-base `CalendarProviderCapReached` on `ConflictError` so the cap is a 409 |
| `backend/apps/personalization/schemas.py` | `CalendarConnectionOut`, `CalendarConnectionListOut`, `CalendarConnectIn`, `CalendarReconnectIn` |
| `backend/apps/personalization/api.py` | The five endpoints under `/calendars` |
| `backend/config/api.py` | The router is already mounted under `/personal` — no change needed (verified) |
| `backend/tests/personalization/test_calendar_connection_commands.py` | The cap's status changes 400 → 409, so the existing assertions move with it |

## Tests

| Test File | Coverage |
|-----------|----------|
| `backend/tests/personalization/test_calendar_connect_api.py` | The five endpoints: the list, the connect, the cap's status and code and payload shape, the three invalid-address refusals, the reconnect, the disconnect, the cross-user 404, the CSRF refusal, and the log-capture proof that a failing request never writes the address |
| `backend/tests/personalization/test_calendar_connection_reads.py` | The read service's projection and the sync-state rules |

## Technical Details

### The wire shapes

```python
class CalendarConnectIn(Schema):
    provider: str            # one of the model's Provider choices
    address: str             # the secret ICS/webcal address — never echoed
    display_label: str = ""  # the user's own name for the calendar


class CalendarReconnectIn(Schema):
    address: str
    display_label: str = ""


class CalendarConnectionOut(Schema):
    id: UUID
    provider: str
    status: str
    display_label: str
    last_synced_at: datetime | None
    next_sync_at: datetime | None
    sync_in_progress: bool
    last_error_kind: str | None


class CalendarConnectionListOut(Schema):
    items: list[CalendarConnectionOut]
```

`CalendarConnectionOut` has **no** `address` field and **no** `fingerprint` field. The
guarantee is structural: the shape cannot carry the address, so no endpoint in this
router can leak it by accident.

### The endpoints

| Method | Path | Answers |
|---|---|---|
| `GET` | `/api/personal/calendars` | The user's connections, never the address |
| `POST` | `/api/personal/calendars` | Connect a provider; the first sync is enqueued |
| `GET` | `/api/personal/calendars/{id}` | One connection and its sync state |
| `POST` | `/api/personal/calendars/{id}/reconnect` | A new address for a `needs_reconnect` connection |
| `DELETE` | `/api/personal/calendars/{id}` | Disconnect, and purge that connection's events |

All five share the router's `auth=current_user`, and **none** accepts a user id as
input — the scoping comes from the session and cannot be talked out of by a payload.

**Cross-user is 404, not 403.** Another user's connection id reads as *not found*: a 403
confirms that the record exists, so a 403 would let a caller probe for other users'
connection ids. The read service filters by `user_id` and the endpoint never sees
whether the row exists for somebody else.

### The CSRF rule

`require_csrf` is applied to the three unsafe methods (the connect, the reconnect and
the delete) and not to the two reads — the same rule `apps/identity/api.py` uses, for
the same reason: Django Ninja exempts every view it builds from Django's
`CsrfViewMiddleware`, so the check is explicit.

### The provider check

`provider` is validated against `CalendarConnection.Provider.choices`. An unknown
provider is a 422 with the same shape as any other validation error. The check is a
*set membership* test, not a branch: it does not make Apple behave differently from
Google.

### The status codes

| Situation | Status | Code |
|---|---|---|
| A successful connect | 201 | — |
| A successful reconnect | 200 | — |
| The Free cap | **409** | `calendar_cap_reached` |
| A bad scheme, a bad shape, an SSRF-refused host, an already-connected address | 422 | `invalid_calendar_credential` |
| Another user's connection id, or an unknown id | 404 | `calendar_connection_not_found` |
| Reconnecting a connection that is already `active` | 422 | `invalid_calendar_credential` |

### The upgrade payload

```json
{
  "code": "calendar_cap_reached",
  "message": "You've connected the calendars your plan allows.",
  "details": {"cap": 1, "upgrade_hint": "Save more with Pro."}
}
```

`details` is plain data — `domain` is pure stdlib and cannot import an app's schemas.
There is **no modal semantics**: no `modal`, no `title`, no `actions`, no
`dismissable`, no `cta`. The approved copy is an *inline* prompt with a quiet link, and
the payload's key set is pinned by a test so it cannot grow a modal-shaped field.

### What the plan does not cover

- **OAuth.** All three providers connect by pasting an address (Amendment A-9). The
  provider value is a label.
- **The dispatcher's tick.** The connect endpoint enqueues by setting `next_poll_at`;
  the worker that picks it up is `calendar-sync-and-polling`'s, already built.
- **The frontend.** The onboarding step-1 UI is `frontend-onboarding-flow`'s.
- **The `settings/sources` surface.** The same router serves it later; the item only
  requires the endpoints to exist.


---

# Implementation Plan: Event Fit (session-free score and tags)

**Work Item:** event-fit
**Intent:** onboarding-and-account
**Mode:** confirm
**Complexity:** medium

## The Problem

FR-26's Pulse Preview shows a visitor with **no account** three events for their city,
each with Why-this Tags and a 1–5 indicator. AD-12 forbids that surface from depending on
a session, and AD-10 forbids it from borrowing a personal explanation — there is no user
for a personal explanation to be *about*.

So there are two kinds of explanation (AD-10's table), and this item builds the first:

| Kind | Computed | Persisted on | Serves | Owner |
| --- | --- | --- | --- | --- |
| **Event Fit** ← this item | per `(event, city)`, on ingest/refresh | catalog | SEO pages, Pulse Preview — anonymous, cacheable | `ingestion` |
| Relevance Pulse (later) | at digest composition | personal | card, detail screen, email | `personalization` |

The two indicators **look identical** and must never be silently substituted for one
another — that is the trust-collapse failure AD-10 names. So the separation has to be
structural, not a naming convention.

## The Design

### 1. A pure function in `domain/event_fit.py` (stdlib only)

```python
compute_event_fit(
    *,
    start_time_utc: datetime,
    end_time_utc: datetime | None,
    start_time_tz: str,
    extraction_confidence: Decimal,
    city: str,
    now: datetime,
) -> EventFit
```

Returns a frozen dataclass: `score: int` (1–5) and `tags: tuple[str, ...]` (ordered).
No randomness, no clock read, no database. The same inputs always give the same output,
and `now` is an explicit parameter like everywhere else in this codebase — so every
boundary is testable at the exact second.

**The score is two inputs, both of which already exist on an Event:**

- **Start-time proximity** — how soon it is, relative to `now`. A preview shows what is
  worth attention *now*, so an event tonight outranks one in three weeks.
- **Extraction confidence** — how well we know the event's facts. A confidently
  extracted event is a better fit than a guess.

**The bands** (thresholds as named constants in `shared/constants.py`):

| Score | Proximity | Confidence |
|-------|-----------|------------|
| 5 | starts within 24 hours | ≥ 0.90 |
| 4 | starts within 2 days | ≥ 0.70 |
| 3 | starts within 7 days | ≥ 0.50 |
| 2 | starts within 14 days | any |
| 1 | later, or past | any |

**The proximity band is a *duration*, not a calendar day.** An earlier draft of this
table said "starts today", which is calendar language, and it disagreed with the
implementation at the edges: an event at 00:30 on Saturday, seen at 23:50 on Friday, is
"tomorrow" by the tag rule and "within 24 hours" by the band rule, and it scored 5.

The **duration** is the rule, for two reasons. A duration is the same quantity in
every timezone, so the band does not need a second local-day computation to be correct
— the local day already has to be computed for the tags, and a second calendar rule
beside it would be a second thing to get wrong. And "how soon" is what the preview
answers: "what is worth attention *now*". An event forty minutes away is worth
attention now, whatever day it falls on.

The score and the tags are still consistent where a reader would notice: the "tonight"
tag's evening boundary keeps "today" out of the top band in the ordinary case, and the
one place the two rules speak at different lengths — a small number of hours either
side of midnight — is a case where either answer is defensible and the score is the
one that decides.

**The combination rule.** The score is the **lower** of the two bands, then floored at 1.
Taking the lower is the honest rule: a badly-extracted event happening tonight is not a
good fit, however soon it is. An event with no extraction confidence still scores — it
scores on proximity alone.

**Why not a weighted sum.** A weighted sum would need weights that no one can justify
without labelled data, and a score that came out of an unexplainable blend is exactly
what AD-10 is against. Two bands and a min is a rule a person can state out loud.

### 2. Tags: generic, time- and place-based

Tag **keys** are stable slugs; the frontend maps them to labels. The keys are generic
because they describe the event to a stranger: they never say anything about the user.

| Key | Meaning |
|-----|---------|
| `tonight` | the local day is today, and the local hour is evening |
| `tomorrow` | the local day is the next calendar day |
| `this_weekend` | the local day is in the **one weekend in view** (see below) |
| `in_<city>` | the venue's city — the slugified city, e.g. `in_brooklyn` |

**The day boundaries are computed in the event's own IANA timezone**, never UTC. An event
at 23:30 local on Friday is "Tonight" on Friday, not on Saturday. This is the rule the
work item calls out, and it is the one place the implementation is most likely to be
wrong, so it gets the most tests.

**There is exactly one "this weekend".** A definite article means one weekend, and which
one depends on the day the tag was computed on:

* On a **weekday**, the coming weekend — the next Saturday and the Sunday after it. On a
  Thursday that is Saturday and Sunday; on a Monday it is the Saturday five days out.
* On a **Saturday or Sunday**, the weekend **under way** — today, or yesterday's
  Saturday and today. The weekend after it is not "this weekend".

Each weekend is named after its **Saturday** and the comparison is made between dates,
never between ISO week numbers: the week number wraps at the year boundary (2027-01-01
is ISO week 53 of 2026), and a week-number comparison loses a New Year weekend
entirely.

*A plain "within the next seven days" bound is wrong in both directions*, and both
directions are pinned by tests: from a Thursday it tags the weekend *after* next, and
from a Saturday it tags the Saturday exactly seven days out — which is a different
weekend. Seven days from a Saturday is a Saturday, and that Saturday belongs to the
weekend after this one.

**The tags are ordered** by a fixed precedence — `tonight`, `tomorrow`, `this_weekend`,
`in_<city>` — so two events with the same tags always list them the same way.

**The city slug is ASCII.** "São Paulo" becomes `in_sao_paulo`, not `in_são_paulo`. A tag
key has to survive a JSON round-trip, a URL segment and a CSS selector unchanged, and a
key with a non-ASCII character in it eventually breaks in one of those three places. The
tag is shown to a stranger, so it has to be plain.

**An event that has already started scores 1.** Not "soon" — *already*. The past check
comes before the "under a day" check, because an event that began an hour ago is under a
day away in one sense and in the past in the one that matters. A preview shows what is
coming, and an event in progress is not coming.

**"Tonight" needs an evening boundary.** `tonight` applies when the local hour is at or
after `EVENT_FIT_EVENING_HOUR` (17:00) on the local day of the event, and the event is
still ahead. Before that hour an event today is not "tonight" — it is later today, and
the preview's own headline is what tells the visitor that.

### 3. The staleness problem — and why this design complies with AD-10

AD-10 says explanations are **persisted, never recomputed at render**. But "Tonight" goes
stale as time passes: an event that was "Tonight" at 18:00 is still tagged "Tonight" at
23:00, and at 00:01 it is *yesterday*.

The work item asks me to state the choice and why it complies. Four options were
considered:

**(a) Recompute at render.** Rejected — it is exactly what AD-10 forbids, and it puts
the same computation in three surfaces that would then disagree.

**(b) Store the tags as absolute date anchors, and render them relatively at read time.**
This is the tempting one, and it is the one that **violates** the rule in spirit: the
*decision* ("this is tonight") was made at persist time, and the label shown to the
visitor would then be a render-time computation of a relative phrase. The preview and
the SEO page could disagree, because "tonight" depends on when each page is rendered.
That is AD-10's failure mode exactly.

**(c) Store absolute date anchors and let the *client* render them relatively.** Also
rejected, for the same reason.

**(d) Recompute the Event Fit row on a cadence, from the tick.** **This is the choice.**

The Event Fit row is **refreshed periodically**, not just on ingest. The tick already
exists, already runs on a cadence, and already owns "time has passed" work. The refresh
is a **write** to the Event Fit row — the same row, with a new `computed_at` and a new
tag set — and it happens **in the worker, never at render**.

**Why this complies with AD-10:** AD-10's rule is that the explanation is *persisted
with the decision* and *not recomputed at render*. The refresh is a recomputation, but
it is a **recomputation at write time, by a writer, in the catalog schema** — the same
place and the same discipline as the original computation. The read path serves the
persisted row and does nothing but read it. Nothing is computed where it is displayed.

**The cost, stated honestly:** a tag can be up to one refresh interval out of date. The
refresh interval is therefore short — the same tick cadence the ingest uses. This is a
deliberate trade: a tag that is briefly stale is better than two surfaces disagreeing
about what "tonight" means, and far better than a render-time computation that no
review can audit.

**The stale-row guard is separate from this.** A row whose `event_version` no longer
matches the event's is **never served** — that is a correctness failure, not a staleness
one, and it is handled at read time by refusing the row, not by rendering around it.

### 4. The `EventFit` model — catalog side, written only by `ingestion`

```python
class EventFit(UUIDv7Model):
    event = FK(Event, PROTECT, related_name="fits")
    city = CharField(max_length=100)
    score = PositiveSmallIntegerField()   # 1..5
    tags = JSONField(list)                # ordered tag keys
    event_version = PositiveIntegerField()  # the version this was computed from
    computed_at = DateTimeField()
    retention_category = RetentionCategory.SOURCE_REGISTRY
```

- **Keyed by `(event, city)`** — a unique constraint on `(event, city)`. The spine's ERD
  says `EVENT ||--o{ EVENT_FIT : per_city`.
- **AD-15 retention:** `SOURCE_REGISTRY` — it holds no user-derived data, and it is
  catalog content, so it lives and dies with the source registry.
- **The score has a check constraint** (`1 <= score <= 5`) and the tags have a shape
  check — a row with a score of 0 or 6 is refused by the database, not just by the code.
- **Written only by `ingestion`** — the `models-ingestion` contract already forbids
  anyone else importing the model, and an architecture test asserts it.

### 5. Recompute on ingest, inside the existing transaction

The recompute happens in `ingest_item.py`, in the **same `transaction.atomic(using=CATALOG)`**
that wrote the event, so an Event Fit row is never visible for an event that was rolled
back. Three hooks:

| The ingest did | The fit does |
|----------------|--------------|
| `create_event` | compute and insert |
| `apply_lifecycle_change` (version bumped) | recompute and update |
| `supersede_event` | compute for the **new** event; the superseded one's row is left, and the read skips superseded events anyway |

The write is skipped when nothing changed — a `silent_update` does not bump the version
and does not change the fit, so no recompute happens. That keeps the common path
(an unchanged re-ingest) free.

### 6. The backfill command

`manage.py backfill_event_fit` — walks the published, non-superseded events that have a
venue city, computes each one's fit, and writes it. **Idempotent**: re-running it
produces the same rows, and a row that already matches is not rewritten (the
`computed_at` does not move, so a test can assert that).

**Batched**, as the work item asks — the same discipline as `schedule_sources`. The
command takes `--batch-size` and loops, so a large catalog does not load in one query.

### 7. The published read — `list_event_fit_for_city`

In **`apps/ingestion/event_fit/reads.py`** — the Event Fit's own package, not
`catalog_read`:

```python
list_event_fit_for_city(*, city: str, now: datetime, limit: int = 3) -> list[EventFitPreviewEntry]
```

Returns the **top N (default 3)** upcoming public events for a city, **ordered by fit
score then start time**, each with its persisted score and tags.

**Why its own module, and later its own package.** `personalization` legitimately reads
`catalog_read` — saving an event to your calendar needs the event's public facts — so
the Event Fit cannot live there without a name-level wall. A name-level wall is opened
by adding a name: the first version of this plan put the read in `event_fit_read.py`
and forbade two module names, and a third module that re-exported the read gave
`personalization` the Event Fit with the contract **green**. The Event Fit is therefore
a **package**, `apps.ingestion.event_fit`, and the wall names the package — one name
that covers everything inside it.

**It never reads `personal`** — it is on the catalog schema, and the `personal` schema
is not even reachable from `apps.ingestion` (AD-3).

**A stale row is never served.** The read joins the fit to the event and requires
`fit.event_version == event.event_version`; a row that does not match is skipped, not
served. The skip happens **before** the limit is applied, so stale rows cannot starve
the result.

### 8. The separation from Relevance Pulse — an architecture test

AD-10: "an authenticated surface never falls back to Event Fit to fill a missing
Relevance Pulse, and a public surface never reads `personal`."

The architecture test asserts that **`apps.personalization` does not import the Event
Fit read**. The `personalization` app has no `EventFit` import path at all — it cannot
use Event Fit as a Relevance Pulse substitute, because it cannot reach it. The digest
intent will need Event Fit to hold that line, so the test is written now, before
anything tries to cross it.

**The check is on the package PREFIX, not on a list of names.** `personalization` may
import `catalog_read`; it may not import anything whose name starts with
`apps.ingestion.event_fit`. A prefix catches a direct import, an alias, and a
re-export alike — and a re-export module *outside* the package
(`apps.ingestion.event_fit_preview`) carries the prefix too, which is how the bypass
that broke the first wall is caught.

**Two guards, each honest about its scope.** The import contract catches every
**direct** import of the package or anything inside it; it cannot catch a module
outside the package that re-exports what is inside, because a `forbidden` contract
matches on import names and has no data-flow analysis. The AST test is what catches
that one, and the bypass is **planted** in `test_the_wall_catches_a_re_export` so the
claim is checked rather than asserted.

**The contract's shape is pinned too.** `test_the_event_fit_wall_is_a_package_and_not_a_list_of_names`
asserts the contract's `forbidden_modules` exactly, the way `single-ics-parser` and
`redis-sdk` are already pinned. Without that pin, narrowing the wall back to two
module names would leave the whole suite green — the wall would be load-bearing and
the suite would not be able to tell.

A second architecture test asserts that `apps.ingestion` never imports
`apps.personalization` — the reverse direction, so the public read cannot start reading
the personal schema.

## The Files

### Created

| File | Purpose |
|------|---------|
| `backend/domain/event_fit.py` | The pure function. Stdlib only (AD-2) |
| `backend/apps/ingestion/event_fit/__init__.py` | The package: the wall is this name |
| `backend/apps/ingestion/event_fit/writes.py` | The command: compute and persist. The only writer |
| `backend/apps/ingestion/event_fit/reads.py` | The published read: the top N for a city |
| `backend/apps/ingestion/migrations/0004_eventfit.py` | The table and its constraints |
| `backend/config/management/commands/backfill_event_fit.py` | The idempotent backfill |
| `backend/revert_event_fit_check.sh` | The revert harness: twenty-one rules, each watched to fail |
| `backend/tests/domain/test_event_fit.py` | The pure function's rules — every tag boundary, every band, DST, the date line |
| `backend/tests/ingestion/test_event_fit.py` | The writer, the recompute hook, the read, the backfill, the refresh |
| `backend/tests/ingestion/test_event_fit_command.py` | The backfill command: idempotence, batching, the skipped-event report |
| `backend/tests/architecture/test_event_fit_separation.py` | The AD-10 separation, both directions |

### Modified

| File | Change |
|------|--------|
| `backend/shared/constants.py` | The thresholds and weights |
| `backend/apps/ingestion/models.py` | The `EventFit` model |
| `backend/apps/ingestion/services/ingest_item.py` | The recompute hook |
| `backend/apps/ingestion/services/catalog_read.py` | The published read |
| `backend/worker/` | The periodic refresh from the tick |

## The Tests

| Rule | Test |
|------|------|
| Each tag rule at its boundaries | the boundary is **exactly** the constant, and one second either side |
| The score bands | each band's lower edge is in the band and one unit below is not |
| Local-day computation across DST | an event on the DST transition day, in the event's own zone |
| The date line | an event on the far side of the date line from the reader |
| Determinism | the same inputs twice give the same output, and the function reads no clock |
| Recompute on version change | a lifecycle change bumps the version, and the fit is recomputed in the same transaction |
| No stale row served | a fit whose `event_version` is behind is **skipped**, not served |
| The backfill is idempotent | running it twice leaves `computed_at` unmoved on the second run |
| The top-N ordering | ordered by score, then start time; the default is 3 |
| No city, no fit | an event without a venue city gets no row and does not appear |
| The AD-10 separation | `personalization` does not import the Event Fit read |

## The Revert Verification

Every rule is verified by **reverting it and watching the test fail**, in the harness
style the previous items established. A regression test that passes against the broken
code is not a regression test.

## The Decisions, and Why

| Decision | Choice | Rationale |
|----------|--------|-----------|
| The score's combination rule | The **lower** of the two bands, floored at 1 | A badly-extracted event tonight is not a good fit. A min is a rule a person can state; a weighted sum is not |
| The score's bands | 5 bands over proximity (24h / 2d / 7d / 14d / later), by **duration** | The preview answers "what's worth attention now", so proximity dominates. Five bands matches the 1–5 indicator. A duration rather than a calendar day: one rule for the score, and the local day is already computed for the tags |
| The evening boundary | 17:00 local, a named constant | "Tonight" at 09:00 is wrong. The hour is a constant so it can be tuned without touching the logic |
| The staleness handling | A **periodic refresh** from the tick, writing the row | The only option that keeps the read path pure. AD-10 forbids a render-time computation, and a render-time *rendering* of a stale relative phrase is the same failure in a different costume |
| The tag keys | Stable slugs, labels on the client | The server states facts; the client speaks the user's language |
| The city's tag | `in_<city>`, slugified | Place-based and generic |
| The tag order | A fixed precedence | Two events with the same tags must list them the same way |
| The fit's schema | `catalog`, owned by `ingestion` | AD-16 lists `EVENT_FIT` under `ingestion`; the spine puts it in the `catalog` schema |
| The fit's retention | `SOURCE_REGISTRY` | It holds no user-derived data, and it is catalog content |
| The read's location | `apps.ingestion.event_fit.reads` | The published read interface over the catalog. `catalog` calls it and never imports the model |
| The wall's shape | A **package** (`apps.ingestion.event_fit`), forbidden by name | A wall made of module names is opened by adding a name — a third module that re-exported the read walked through the first version of this plan with the contract **green**. A package is one name that covers everything inside it |
| The default N | 3 | The Pulse Preview shows three cards |
| The refresh's cost | Batched, on the existing tick | "Mind the refresh cost" — the work item's own note |

## What This Item Does Not Cover

- **The Pulse Preview endpoint** — `pulse-preview-api-and-geo` owns it. This item
  builds the read it will call.
- **The Relevance Pulse** — a later intent. This item's job is to make sure it never
  gets confused with this one.
- **The frontend rendering** — the tag labels, the dot indicator and the "3 of 5"
  aria-label are the frontend's work. This item ships the keys and the number.
- **Source reliability and price** — the work item says so explicitly: "There is no
  price field and FR-16 source reliability isn't built, so 'Free' tags and reliability
  weighting wait until those exist." So there is no `free` tag and no source weighting
  in the score.


---

# Implementation Plan: Pulse Preview API & Geo Port

**Work Item:** pulse-preview-api-and-geo
**Intent:** onboarding-and-account
**Mode:** confirm
**Complexity:** medium

## The Problem

FR-2 is the first value a visitor gets, before they have an account: three Pulse Cards
for their city, with Why-this Tags, a 1–5 Confidence Pulse and a Source Badge. Three
things have to be true for it to work, and they pull in opposite directions.

**It is anonymous.** AD-12: "Public event pages render fully without a session." The
preview is a *public* surface, so it must not read `request.user`, must not touch
`personal`, and must not set a cookie — otherwise it is not cacheable and the response
depends on who asked.

**It is local.** "Three events in the user's inferred city" means the server has to
know which city the visitor is in. The only source of that is the **edge's geo header**
(Vercel sets `x-vercel-ip-city`; the header name is the edge's business, not ours). That
header is attacker-controlled — a caller can send any value it likes — so it is untrusted
input, and it is *privacy-relevant*: PRD §10.2 and FR-2's consent banner make "Don't use
my location" a first-class choice.

**It is honest.** The preview must not show Brooklyn's events under the heading "Events
in Queens". If a city has nothing, it gets an empty preview **with the city's name**,
not another city's events.

## The Design

### 1. The geo port — `ports/geo.py`

A port, like every other thing that reaches outside the app (`ports/throttle.py`,
`ports/fetch.py`):

```python
@dataclass(frozen=True)
class GeoResult:
    """Where the caller is, as far as the edge told us."""
    city: str | None

class GeoPort(ABC):
    @abstractmethod
    def resolve_city(self, headers: Mapping[str, str]) -> str | None:
        """The city the edge says this request came from, or None."""
        ...
```

**The port takes headers, not a request.** That is the whole design in one sentence: the
port's input is a bag of headers, so the adapter reads a header and does nothing else —
no database lookup, no vendor call, no `request` object. AD-1 says the code doesn't
depend on the host, and a port whose input is a header mapping cannot depend on a host.

**The port is stdlib-only and imports no Django**, like every other port here.

### 2. The real adapter — `adapters/geo/header.py`

It reads **one** header — `x-vercel-ip-city` — and does three things to it:

1. **Length-bounded.** A header is up to 8 KB and it is attacker-controlled, so the
   value is truncated/rejected past a bound (named constant, `GEO_CITY_MAX_LENGTH = 64`).
   A city name longer than 64 characters is not a city; it is an attempt to get the
   value somewhere it shouldn't go.
2. **URL-decoded exactly once.** The edge URL-encodes the city (`Brooklyn%2CNY`),
   because a raw header value cannot contain some characters. `unquote` **once** — not
   twice, because decoding twice is how `%252e%252e%252f` becomes `../`. The result is
   decoded once and then *not* decoded again.
3. **Normalized and validated.** Stripped, collapsed, and reduced to a safe city shape.
   The result is used only as a *lookup key* against the supported-cities set, never
   interpolated into SQL or into a path, but it is still untrusted.

**The real adapter does no lookup and calls no vendor.** It returns the city name the
edge gave, or `None`. Deciding whether that city is *supported* is the application
layer's job, not the adapter's — the adapter does not know what the catalog covers.

**The header name is a named constant** (`GEO_HEADER_NAME = "x-vercel-ip-city"`), so
changing the edge means changing one line. The *port* does not know the header name.

### 3. The fake adapter — `adapters/geo/fake.py`, and it is the default

`FAKE_ADAPTERS["geo"]` points at it, so local and CI get it. It returns **a chosen
city**, configured from `config/env.py`:

```
GEO_FAKE_CITY=<city>       # unset or empty → the adapter reports no location
```

The work item says "a fake adapter is the local and CI default, **configurable to
return a chosen city**", and that is exactly what this is. The fake reads its city from
the settings object, so:

- CI can set `GEO_FAKE_CITY=Brooklyn` and every request resolves to Brooklyn.
- A test can set it to `None` to exercise the geo miss.
- A test can set it to a **supported** city or an **unsupported** one, which is what
  makes the two fallback branches testable without touching a header.

`config/env.py` is the only module allowed to read the environment (ruff bans
`os.environ` everywhere else), so this is the only place the value comes from.

**The fake also honours the header when asked to.** No — it does not. The fake returns
its configured city and ignores the headers entirely. That is what makes it a fake: a
test that wants to exercise the *real* adapter's header handling reaches for the real
adapter, and a test that wants a deterministic city sets the config.

### 4. Where the endpoint lives, and the one architectural problem

The endpoint is a **public, session-free surface**. `apps/catalog` is where the other
public surface lives (`/api/catalog/events`), it is already registered under a router,
and it never touches `personal`. So the preview endpoint belongs in **`apps/catalog`**,
on a **new router** mounted at `/api/public`.

**The problem:** the work item says "the endpoint reads `catalog` only through
`ingestion`'s published read interface". `apps.catalog` **cannot** import
`apps.ingestion.event_fit.reads` directly — that module imports `apps.ingestion.models`,
and the `models-ingestion` contract protects that module to `apps.ingestion` alone. The
contract is right and the previous item proved it: `personalization` cannot reach the
Event Fit that way either.

**The resolution is a wrapper published through `ingestion`'s service interface.** A new
module, `apps/ingestion/services/preview_read.py`, which:

- calls `apps.ingestion.event_fit.reads.list_event_fit_for_city` (it lives *inside*
  `apps.ingestion`, so the contract is satisfied),
- adds the **Source Badge inputs** the fit read does not carry (the source's type and
  name — the badge is a function of the *source*, and the fit read deliberately does not
  join the source),
- exposes the **supported-cities list** — the distinct cities that have at least one
  upcoming published event **with an Event Fit**.

`apps/catalog` then imports `apps.ingestion.services.preview_read` and nothing else
from ingestion. The catalog schema is reached only through ingestion's published
interface. The contract holds, and the endpoint's data comes from the catalog side.

**The wrapper is a query, not a write.** It lives under `services/` because that is where
ingestion's published reads live (`catalog_read.py` is there), not because it writes
anything.

### 5. The supported cities, and the NYC fallback

**Supported cities** = the distinct cities that have at least one upcoming published,
non-superseded event **with a current Event Fit**. The "with Event Fit" half matters: a
city with events but no fits is a city the preview cannot serve, and listing it in the
picker would offer a city that answers with an empty preview. The supported set is
exactly the set of cities for which the preview has something to show.

The set is **derived from the catalog**, not configured. A hard-coded city list is a
list that goes stale the moment a source in a new city is ingested, and the picker would
offer a city the preview cannot fill.

**NYC is a named constant** in `shared/constants.py`:

```python
# FR-2: "falls back to the most-popular city (NYC at MVP)". The fallback when geo
# resolves to a city the catalog does not cover, or when geo resolves to nothing.
PREVIEW_FALLBACK_CITY = "New York City"
```

The fallback is the **fallback**, so it is used in exactly two places:

- **A geo city that is not supported** → the preview resolves to the fallback city.
- **No geo city at all** → the preview resolves to the fallback city.

**An explicit `city` is never silently replaced.** If the visitor picked a city from the
picker and it is not supported, the answer is an **empty preview carrying that city's
name** — not the fallback's events under the wrong name. This is the work item's rule
and it is the honest one: the frontend shows "No preview available in {city} yet.", and
if we answered with NYC's events the heading would be a lie.

### 6. The endpoint's shape

```
GET /api/public/preview?city=<city>&use_geo=<bool>
GET /api/public/preview/cities
```

**Resolution order**, in one place, so there is one rule and not three:

| Situation | Resolved city | `source` | Cards |
|---|---|---|---|
| `use_geo=false` (the opt-out) | the fallback city | `fallback` | the fallback city's |
| `city` given, supported | that city | `query` | that city's |
| `city` given, **not** supported | that city (unchanged) | `query` | **none** — empty preview |
| no `city`, geo resolves to a supported city | that city | `geo` | that city's |
| no `city`, geo resolves to an unsupported city | the fallback city | `fallback` | the fallback city's |
| no `city`, geo resolves to nothing | the fallback city | `fallback` | the fallback city's |

**The `source` field says how the city was resolved** — `geo`, `query` or `fallback` —
which is what the frontend needs to show "Showing events near Brooklyn" versus
"No preview available in Queens yet."

**The opt-out is explicit and it is a parameter, not a cookie.** The frontend sends
`use_geo=false` when the visitor picks "Don't use my location". The endpoint then
**never consults the geo port** — and a test proves it by planting a geo port that
raises if it is called. "Never consulted" is a stronger claim than "consulted and
ignored", and the stronger claim is the one that can be checked.

**The response carries the resolved city and the source**, so the frontend never has to
guess what it got.

### 7. The card's fields

Each card carries:

| Field | From |
|---|---|
| `id`, `slug` | the fit read |
| `title` | the fit read |
| `venue_name` | the fit read |
| `start_time_utc`, `start_time_tz` | the fit read — **UTC plus an explicit IANA zone** (AD-6) |
| `score` | the fit read — the persisted 1–5 Event Fit |
| `tags` | the fit read — the persisted tag keys, in order |
| `source_name` | the preview read wrapper |
| `source_badge` | the preview read wrapper — one of the five badge types |

**The Source Badge inputs, "if the read interface provides them".** The catalog's
`PublicEvent` already carries `source_name`, and `Source` carries `source_type` — so the
inputs **are** available, and this item provides them. The badge *type* is derived from
the source's type and acquisition method:

| Source | Badge type |
|---|---|
| `source_type=venue`, `source_type=promoter` | `official_site` |
| `source_type=community`, `source_type=government` | `community` |
| `source_type=ticketing`, `source_type=media` | `aggregator` |
| `source_type=other` + `acquisition_method=crawl` | `crawled_html` |

There is no `user_imported` badge here: a user-imported event is a *personal* event, and
personal events are not in the public preview (FR-2's out-of-scope line: "Personal event
surfacing in Pulse Preview"). The five-badge list is the UX spec's list; this surface
can only ever produce four of them, and saying so in the code is better than a mapping
that pretends otherwise.

The badge is a **type**, not a label and not an icon: the UX spec owns the label
("Official", "Community", "Listing site", "Forwarded") and the glyph. The server states
the fact; the client speaks the user's language — the same rule the Event Fit tags
follow.

**The score and the badge are different things and are named differently.** `score` is
the Event Fit (AD-10); `source_badge` is the Source Badge (FR-23). They are never
substituted for one another.

### 8. The response

```python
class PreviewOut(Schema):
    city: str                    # the resolved city, always present
    city_source: str             # "geo" | "query" | "fallback"
    items: list[PreviewCardOut]
```

`city` is always present — even for an unsupported explicit city, where it is the city
the visitor asked for. The empty case is `items: []` with the city's name, not an
omitted field.

`GET /api/public/preview/cities` returns `{"cities": ["Brooklyn", "New York City"]}` —
the supported cities, **alphabetically**, for the one-tap picker. Alphabetical, because
a picker whose order changes between requests is a picker nobody can find anything in.

### 9. Cacheable

The preview is a **public, per-city** response, so it is cacheable and it says so:

- `Cache-Control: public, max-age=60, s-maxage=300, stale-while-revalidate=600`
- `Vary: Accept-Encoding` — and **nothing session-related**.

**`Vary` must not include `Cookie`.** A response that varies on the cookie is not
cacheable, and — worse — a shared cache that stores one variant under a key that ignores
the cookie would serve one visitor's response to another. The endpoint sets no cookie
and reads no session, so the response is identical for everyone and the cache key is
just the URL.

**The cacheability is a testable property**: the response headers carry no `Cookie` in
`Vary`, and the body is byte-identical for a signed-in caller and an anonymous one.

**Why 60 seconds of browser cache and 300 of shared cache.** The preview's content
moves when the Event Fit refresh runs (every 15 minutes) and when events start. A
minute of browser cache keeps a reload from re-querying; five minutes of shared cache
keeps a popular city's preview from hammering the database; and
`stale-while-revalidate` means a visitor is never waiting on the origin for a card they
could have had a moment ago. The numbers are named constants.

### 10. Rate-limited per IP

PRD §11.2: "Rate limiting on all public endpoints (per-IP and per-user)". The preview is
a public endpoint, so it is limited per IP. It has **no per-user limit**, because it has
no user — that is the point of AD-12, and a per-user limit on an anonymous endpoint
would mean reading the session, which would mean the endpoint is not anonymous.

**The limit is generous**, because the endpoint is cheap and cacheable and a visitor
legitimately reloads a preview while deciding: 60 requests per IP per minute. Named
constants in `shared/constants.py`.

**The throttle key is the IP and nothing else.** The IP comes from the same
`_client_ip` rule the auth endpoints use — `X-Forwarded-For` only when
`settings.TRUST_FORWARDED_FOR` is on (off by default), otherwise `REMOTE_ADDR` — and it
is **never logged and never stored** (AD-13). It only ever becomes part of a throttle key,
which is why the rule includes "the value must parse as an IP address": a caller cannot
pad the key with arbitrary text.

**The throttle is checked before the work.** The port's `check` is a counter; the
endpoint calls it first and answers 429 with `Retry-After` when the limit is tripped. A
429 on a public cacheable endpoint is a *cacheable* answer too — it must not be cached
as if it were content.

### 11. The privacy rules, which are rules and not preferences

Two of them, from the work item's own note ("Never store the resolved city server-side
for an anonymous visitor, and never log it with the IP"):

- **The resolved city is never stored.** It is a response field and nothing else. There
  is no table, no cache entry, no session key. The endpoint computes it, returns it, and
  forgets it.
- **The city is never logged with the IP.** In fact **neither is ever logged** — the
  resolved city is not logged at all, because a log line that pairs "Brooklyn" with a
  request is a geo-log, and the point of not storing it is that it is not stored. The
  only thing that touches a log on this path is an error, and the error handler does not
  include the city.

**The opt-out is honoured server-side.** "Don't use my location" is a real choice, and a
choice the server ignores is not a choice. `use_geo=false` means the geo port is **not
called** — proven by a planted port that raises on call.

### 12. Where the geo header is read — and what we do *not* depend on

The work item asks: "Check whether the platform's geo header survives that rewrite."

**Checked, by reading the framework source.** `frontend/proxy.ts` rewrites `/api/*` to
Django with `NextResponse.rewrite(url)`. In Next 16.3.8, `resolve-routes.js` restores
the `x-middleware-request-*` headers onto the rewritten request **under their original
names**, so `x-vercel-ip-city` survives the rewrite.

**But the design does not depend on it.** The port's input is a header mapping; the
adapter reads a named header; the endpoint passes the request's headers. If a future
proxy drops the header, the symptom is "geo resolves to nothing" and the visitor gets
the fallback city — a degraded but correct answer. **No code branches on whether the
proxy forwarded it.** That is AD-1: the code does not depend on the host.

### 13. The router

`config/api.py` mounts a new router:

```python
api.add_router("/public", public_router)
```

So the URLs are `/api/public/preview` and `/api/public/preview/cities`.

**Why a new router and not the catalog one.** The catalog router is mounted at
`/api/catalog` and is about *events*. The preview is about a *resolved city* and it has
its own auth-free semantics, its own cache headers and its own rate limit. A separate
router makes those properties obvious at the mount point, and it keeps the `/api/public`
prefix the work item names.

**The router has no `auth=`.** django-ninja's `auth=` on a router is the session
dependency. The preview router has none, and the endpoints never call
`request.user` — and an architecture test asserts the *source* of the preview modules
mentions neither `request.user` nor `personal`.

### 14. AD-19 — the client is regenerated

The OpenAPI schema is the contract, and the frontend client is generated from it
(AD-19). Adding two endpoints changes the schema, so the generated client is
regenerated: `pnpm generate:client` (or whatever the frontend's script is called), and
the regenerated file is committed.

## The Files

### Created

| File | Purpose |
|------|---------|
| `backend/ports/geo.py` | The port: a header mapping in, a city or nothing out |
| `backend/adapters/geo/__init__.py` | The package |
| `backend/adapters/geo/header.py` | The real adapter: reads one header, bounds it, decodes it once |
| `backend/adapters/geo/fake.py` | The fake: returns the configured city |
| `backend/apps/ingestion/services/preview_read.py` | The published read: the preview cards and the supported cities |
| `backend/apps/catalog/preview_api.py` | The preview router and its two endpoints |
| `backend/apps/catalog/preview_schemas.py` | The wire shapes (AD-19) |
| `backend/tests/ports/test_geo.py` | The port and both adapters: bounding, one decode, normalization |
| `backend/tests/catalog/test_preview_api.py` | The endpoints: every branch of the resolution table |
| `backend/tests/ingestion/test_preview_read.py` | The published read: the supported cities and the source badge |
| `backend/tests/architecture/test_preview_anonymity.py` | No session, no `personal`, no `request.user` |
| `backend/revert_preview_check.sh` | The revert harness |

### Modified

| File | Change |
|------|--------|
| `backend/ports/registry.py` | `GeoPort` → `PORT_KEYS` + `get_geo_port()` |
| `backend/config/adapters.py` | `FAKE_ADAPTERS["geo"]` → the fake |
| `backend/config/env.py` | `GEO_FAKE_CITY` |
| `backend/config/api.py` | Mount `/public` |
| `backend/shared/constants.py` | NYC, the limits, the header name, the length bound, the cache TTLs |
| `backend/apps/ingestion/services/__init__.py` | Nothing — the package docstring already says it |
| `frontend/src/lib/api/generated/schema.ts` | Regenerated from the OpenAPI schema (AD-19) |
| `frontend/src/lib/api/generated/client.ts` | Regenerated |

## The Tests

| Rule | Test |
|------|------|
| The geo hit | the fake's configured city resolves, and `city_source` is `geo` |
| The geo miss | no configured city → the fallback city, and `city_source` is `fallback` |
| A geo city outside the supported set | the fallback city, and the fallback's cards |
| An explicit override | `?city=Brooklyn` wins over geo, and `city_source` is `query` |
| An unsupported explicit city | an **empty** preview carrying that city's name — and **not** the fallback's events |
| The opt-out | `?use_geo=false` → the fallback, and a planted geo port that raises is **not** called |
| Identical with and without a session | the same request signed in and unsigned returns byte-identical bodies and identical headers |
| The per-IP limit | the N+1-th request from one IP is a 429 with `Retry-After`; a different IP is unaffected |
| Fewer than 3 events | a city with one fit returns one card, not three and not an error |
| Cacheable | `Cache-Control` is public; `Vary` has no `Cookie` |
| The supported cities | only cities with an upcoming fit; alphabetical |
| The header is bounded | a 10 KB city value is refused |
| The header is decoded once | `%2520` decodes to `%20`, not to a space |
| The real adapter does no lookup | the adapter returns the header's city without touching the catalog |
| No `personal` | the preview modules never mention `personal` |
| No `request.user` | the preview modules never mention `request.user` |
| The supported-city read is published | `apps.catalog` reaches the Event Fit only through `ingestion`'s service |

## The Revert Verification

Every rule is verified by **reverting it and watching the test fail**, in the harness
style the earlier items established. A regression test that passes against the broken
code is not a regression test — and the run's standing rule is that **a revert case that
does not fail is not a revert case; it is a hole in the suite wearing a harness's
clothes.** The harness backs each file up **uniquely per case** and **verifies the
restore byte for byte**, because a restore that silently fails makes every later result
a claim about a tree that does not exist.

## The Decisions, and Why

| Decision | Choice | Rationale |
|----------|--------|-----------|
| The geo port's input | A **header mapping**, not a request | The adapter can then do nothing but read a header — no database, no vendor, no host dependency (AD-1) |
| The header name | `x-vercel-ip-city`, a **named constant** | The edge owns the name; changing edges changes one line, not the port |
| The fake's city | From `config/env.py` (`GEO_FAKE_CITY`) | `config.env` is the only module allowed to read the environment. The work item asks for a fake configurable to a chosen city; this is it |
| The endpoint's home | `apps/catalog`, on a **new `/api/public` router** | The catalog is the public surface; a separate router makes the auth-free, cacheable, rate-limited semantics obvious at the mount |
| How `catalog` reaches the Event Fit | Through a **wrapper in `ingestion`'s services** | `apps.catalog` cannot import `apps.ingestion.event_fit.reads` (the `models-ingestion` contract protects the model to `apps.ingestion`). The wrapper is inside `apps.ingestion`, so the contract holds and the endpoint still reads the catalog only through ingestion's published interface |
| The supported cities | **Derived from the catalog**, not configured | A configured list goes stale when a source in a new city is ingested, and would offer cities the preview cannot fill |
| NYC | `PREVIEW_FALLBACK_CITY` in `shared/constants.py` | "NYC is a named constant" is the work item's own wording. One copy, so the frontend and the backend cannot disagree about the fallback's spelling |
| An unsupported explicit city | An **empty preview carrying that city's name** | The alternative — the fallback's events under the requested city's name — is a heading that lies |
| The opt-out | `use_geo=false`, and the geo port is **not called** | "Never consulted" is checkable; "consulted and ignored" is not |
| The cache headers | `public`, `s-maxage`, `stale-while-revalidate`; **`Vary` without `Cookie`** | A response that varies on the cookie is not cacheable, and a shared cache ignoring the cookie would serve one visitor's response to another |
| The rate limit | Per IP only, 60/min, **no per-user limit** | The endpoint has no user. A per-user limit would mean reading the session, which would mean the endpoint is not anonymous (AD-12) |
| The IP source | `REMOTE_ADDR`, and `X-Forwarded-For` only when `TRUST_FORWARDED_FOR` is on | The header is attacker-controlled; trusting it unconditionally defeated the auth throttle entirely. The same rule the auth endpoints use |
| The resolved city | **Never stored, never logged** | PRD §10.2 and the work item's own note. A log line pairing a city with a request is a geo-log, which is what "never store it" is about |
| The Source Badge | A **type**, derived from the source's type and acquisition method | The UX spec owns the label and the glyph. The server states the fact; the client speaks the user's language |
| `user_imported` | **Not producible here** | A user-imported event is a personal event, and FR-2 puts personal events out of scope for the preview. Four badges are reachable; the fifth is not |
| The score and the badge | Separate fields, `score` and `source_badge` | AD-10: two indicators that look identical must never be silently substituted for one another. Different names are the least that can be done |

## What This Item Does Not Cover

- **The Pulse Preview page** — `frontend-pulse-preview` owns it. This item ships the
  endpoint it will call, and the generated client.
- **The consent banner and the cookie** — FR-2 says the choice "persists in a cookie for
  the session". The cookie is the frontend's; this item ships the **server half**, which
  is the part that has to be right: the opt-out is honoured and the geo port is not
  consulted.
- **The Source Badge's label and glyph** — `EXPERIENCE.md §4` owns them. This item ships
  the type.
- **The SEO city page** — the same Event Fit serves it, but that page is a later item.
- **A real geo vendor** — the real adapter reads a header, which is what the edge gives
  us. There is no geo-IP *lookup* service in the stack, and the work item explicitly
  rules one out: "The real adapter only reads a header. It does no database lookup and
  calls no vendor."


---

# Implementation Plan: Frontend Auth Surfaces & Signed-in Home

**Work Item:** frontend-auth-surfaces
**Intent:** onboarding-and-account
**Mode:** confirm
**Complexity:** medium

## The Problem

The backend can now create a session; the frontend cannot. There is no `/signup`, no
`/signin`, no `/reset-password`, and `/` does not know who is looking at it. Four things
were **probed live** before planning (Django + `next dev` + the proxy, 2026-10-30), and
three of them change the shape of this item:

1. **Every state-changing call through the proxy is refused today.** `GET /api/auth/csrf`
   through `127.0.0.1:3000` sets the `csrftoken` cookie (the `Set-Cookie` passes through
   the rewrite), but a `POST /api/auth/signin` with that token and the browser's
   `Origin: http://127.0.0.1:3000` answers **`403 csrf_failed`**. The same request sent
   straight to Django with Django's own origin gets past CSRF (a `401
   invalid_credentials`). The cause: `CSRF_TRUSTED_ORIGINS` defaults to `[]`
   (`backend/config/env.py:32`), and neither `.env.example` nor `.env` sets it, so
   Django compares the frontend's `Origin` with its own host (`127.0.0.1:8000`) and
   refuses. With `CSRF_TRUSTED_ORIGINS=http://127.0.0.1:3000,http://localhost:3000` the
   whole flow works through the proxy: signup `201`, signin `200` + `sessionid`, `me`
   `200`, a personal `POST` `201`, signout `200`, `me` `401`.
2. **The CSRF token rotates on sign-in.** Django's `login()` rotates it; the sign-in
   response sets a new `csrftoken`. A personal `POST` carrying the **pre-sign-in** token
   was refused with `403 csrf_failed`. So the client must read the cookie **on every
   unsafe request** and never hold the token in memory.
3. **`/` shows a signed-in user an empty list.** With a valid session that owns an event,
   `GET /api/personal/events` through the proxy lists it, but the rendered `/` says
   "You haven't added any personal events yet." `PersonalEventsSection` calls
   `API_BASE_URL` from the Next server **without the visitor's cookie**, so every
   server-side read is anonymous, gets a 401, and quietly returns `[]`. The placeholder
   home reuses that component, so this item has to fix it.
4. The error shapes the UI renders were confirmed on the wire: `invalid_credentials`
   401 "That email and password don't match."; `invalid_input` 422 with
   `details.errors[{loc:["password"], msg:"This password is too common."}]`;
   `invalid_reset_token` 422 "That reset link isn't valid anymore. Ask for a new one.";
   `csrf_failed` 403 "Your session needs refreshing. Reload the page and try again.";
   `rate_limited` 429 "That's a lot of requests. Try again in a little while."

(The local database was also four `personalization` migrations behind; `make migrate`
fixed it. That is the environment, not the code.)

A fifth problem was found by reading the code: the current `/` renders
`<AddEventButton />` **and** `<PersonalEventsSection />`, and `AddEventButton` mounts its
own full `PersonalEventsPanel` (with `events=[]`), so the page carries **two** "Your
personal events" lists, one of them always empty. A render test will pin it before the fix.

## The Design

### 1. CSRF: one middleware on the one client

`lib/backend-client.ts` registers an openapi-fetch middleware (`api.use(...)`, 0.17 API,
checked in `dist/index.d.ts`) **in the browser only**:

- On `POST`/`PUT`/`PATCH`/`DELETE`, it reads `csrftoken` from `document.cookie` **at
  request time** and sets `X-CSRFToken`. No module-level cache (finding 2).
- If the cookie is absent (first visit), it first calls `GET /api/auth/csrf` through the
  same client — a `GET`, so no recursion — and then reads the cookie it set.
- `GET`s are untouched, and the middleware is not registered on the server (there is no
  `document`, and server-side calls are reads).

Every existing write (`personal-events-panel.tsx`'s create, edit, resolve) becomes
CSRF-correct with **no call-site change**. The logic lives in `lib/csrf.ts` so it is
testable with a stub `fetch`.

No automatic retry on `csrf_failed`: with the cookie read fresh per request, the
remaining causes (a cleared cookie mid-form, an origin misconfiguration) are not fixed
by retrying, and the API's own message already tells the user what to do. It is shown
verbatim.

**Config:** `.env.example` gains `CSRF_TRUSTED_ORIGINS=http://127.0.0.1:3000,http://localhost:3000`
with a comment saying why (finding 1), and the setup docs say production must set it to
the site's origin. I will add the same line to your local `.env`, which is not
tracked; without it nothing in this item works locally.

### 2. The session, read on the server with the visitor's cookie

`lib/session.ts` (server-only by use; `server-only` is not a dependency and I won't add one):

- `sessionHeaders()` → `{ cookie: (await cookies()).toString() }`: the visitor's
  cookies, forwarded on server-side reads. Fixes finding 3 in
  `PersonalEventsSection` and serves the new reads.
- `getSession()` → `GET /api/auth/me` with those headers, folded into three cases:
  `{ kind: "signed-in", user }` (200), `{ kind: "anonymous" }` (401), `{ kind:
  "unavailable" }` (anything else, a thrown fetch, or no `API_BASE_URL`).
- `homeRoute(session)` → a **pure** function: anonymous → `"/preview"`; signed in and
  `onboarding.completed === false` → `"/onboarding"`; signed in and completed → `null`
  (render the home); unavailable → `null` (render the calm error, not a misroute).

**Where the `/` decision lives: in the page, not in `proxy.ts`.** The proxy stays a pure
`/api/*` forwarder with one job, and a decision in a server component is a plain
function call that Vitest can drive. The cost is the same one `me` round trip either way.
`/preview` gets no session dependency from this (AD-12): it is not touched here.

### 3. The routes

| Route | Server component does | Client island |
|---|---|---|
| `/` | `getSession()` → `redirect(homeRoute)` or render the placeholder home; keeps `dynamic = "force-dynamic"` | `SignOutButton`, the existing personal-events panel |
| `/signin` | signed in → `redirect("/")` (the silent redirect, `EXPERIENCE.md` `Component.Auth.SignIn`); otherwise the form | `SigninForm` |
| `/signup` | signed in → `redirect("/")` (same rule; the spec is silent, so I'm mirroring `/signin`) | `SignupForm` |
| `/reset-password` | reads `searchParams.token`; a token → the set-new form, none → the request form. `metadata.referrer = "no-referrer"` | `ResetRequestForm`, `ResetConfirmForm` |

`/onboarding` and `/preview` are built by `frontend-onboarding-flow` and
`frontend-pulse-preview` (the next two items in this run). Until then the redirects
land on a 404. The redirect targets are correct now and aren't stubbed.

### 4. The pre-auth shell

`components/pre-auth/`: `PreAuthTopbar` (brand-wrap only: logo, wordmark, tagline,
anchor to `/preview`; nothing else, topbar-quiet rule) and `PreAuthFooter` (the drawn
footer row, with `aria-current="page"` on the current route's link). `frontend-pulse-preview`
reuses both. The logo is copied from the mockups to
`frontend/public/brand/eventpulse24-logo.png` and rendered with `next/image` at 36×36.

### 5. The forms

Shared pieces in `components/auth/`:

- `AuthField`: `<label htmlFor>`, the input, an optional hint (`Text.Meta`, ink-faint),
  and the error row (⚠ glyph + text, **`color.signal.warn`** per the copy bank, not
  `signal.error`), `role="alert"`, `aria-invalid`, `aria-describedby`. The same shape as
  `personal-event-form.tsx`'s `Field`.
- `PasswordInput`: the reveal toggle, `aria-pressed`, with `aria-label` naming the
  *destination* state ("Show password" / "Hide password").
- `SubmitButton`: terracotta primary. While in flight it is `disabled`, `aria-busy`, and
  shows a **static dot** + "Signing in…" / "Creating account…" / "Sending…" / "Saving…",
  and the fields go read-only.
- `lib/api-errors.ts`: `readApiError(error)` → `{ message, fieldErrors }` from the
  generated `ErrorOut` (`details.errors[].loc/msg`, narrowed at runtime), plus the network
  case → "Couldn't reach Pulse. Try again." (the `EXPERIENCE.md` error-voice line).

**Sign-in** (`signin-desktop.html`): Email, Password + reveal, "Forgot password?" →
`/reset-password`, "Sign in"; footer cross-link + privacy line as drawn. Client check:
the email format on blur ("That doesn't look like a valid email address."). A 401
renders the API's message **verbatim on the Password field**. The Email field is never
marked invalid, which is the copy bank's account-enumeration rule. 429 and network
errors render as a form-level alert. Success → `router.replace("/")` + `router.refresh()`.

**Sign-up** (`signup-desktop.html`): Email, Password ("8 characters minimum" hint),
Confirm. Client checks use the locked copy-bank strings: "That doesn't look like a valid
email address.", "Use at least 8 characters.", and "Passwords don't match." on Confirm
(on Confirm blur and on submit; Password is not cleared). Server 422 `details` render
verbatim on their fields. **On 201 the form signs in** (the auth seam's deviation 1:
sign-up establishes no session). It then shows "Account created. Taking you to
onboarding…", holds 1.5 s (0 ms under `prefers-reduced-motion`), and goes to
`/onboarding`.

**Reset** (no mockup; it's built from the sign-in vocabulary, as `EXPERIENCE.md` directs):

- *Request*: Email + "Send reset link" → 202 → "We've sent a reset link to {email}."
  (locked copy) in the `.form-footer` success pattern.
- *Set new*: the token comes from the URL. On mount, the component strips it from the
  address bar (`history.replaceState`), and `no-referrer` keeps it out of `Referer`.
  New password + Confirm use the same client checks as sign-up. Success → "Your password
  is changed. Sign in with your new password." + a link to `/signin` (**new copy**; see D5).
- *Expired or used*: there is no token-check endpoint, and a `GET` pre-check would be a
  token oracle, so this state appears **on submit**. A 422 `invalid_reset_token` shows
  the API's message verbatim with "Ask for a new one" → the request form.

### 6. The placeholder home

A calm page. It has no fake digest cards and no invented numbers:

- The brand topbar (the same brand-wrap; the anchor goes to `/`).
- **"Your Pulse is being prepared."** (the work item's phrase) and one sentence: "The
  Pulse Digest isn't ready yet. Until it is, your personal events and the events you've
  saved are here." (**new copy**; see D5).
- `PersonalEventsSection`, which now gets the visitor's cookie. Its own panel carries
  "Add event". The duplicate `AddEventButton` comes off the page (finding 5). The
  component stays for the future sidenav.
- `SavedEventsSection` (**new**, a server read of `GET /api/personal/saved-events` with the
  cookie): a read-only list of title, local date and time, and venue city, labelled
  "Saved". Empty: "You haven't saved any events yet." The work item says the home "links
  to personal and saved events", and neither has a route in the route map, so both are
  **shown on the home** rather than linked to a 404.
- A footer: "Signed in as {email}" and `SignOutButton` (`POST /api/auth/signout` →
  `router.replace("/signin")` + `refresh`). It lives in the footer because the
  topbar-quiet rule keeps account actions out of the topbar, and the sidenav that will
  hold "Account" does not exist yet.
- *Unavailable* (`me` failed for a reason other than 401): "Couldn't reach Pulse. Try
  again." with a link back to `/`. This is not a redirect to `/preview`, because
  sending a signed-in user to the anonymous page on an API blip would be a lie.

## Open Decisions: the spec conflicts with the ACs

These are your calls. Each has a recommendation, which I'll build unless you say otherwise.

**D1. Sign-up State C ("An account with that email already exists. Sign in →") and the
copy-bank lines "Account not found" / "Email already exists".** `EXPERIENCE.md` allows
the signup leak. The intent (AD-18), the API (201 either way) and this item's AC
("the UI never adds wording that reveals whether an account exists") forbid it.
*Recommendation:* drop State C and never render either string. The API can't produce
them anyway.

**D2. Sign-in's wrong-credentials text.** The copy bank locks "That password doesn't
match. Try again or reset it."; the AC says "the API's calm messages verbatim", and the
API says "That email and password don't match." The copy-bank line also implies the
email was right. *Recommendation:* the API's message verbatim, on the Password field,
with no inline "reset it" link. "Forgot password?" sits directly below it.

**D3. Sign-up when the follow-up sign-in fails** (the address was taken and the password
differs). The 201 hides it, but the follow-up sign-in's 401 can't. The *flow* differs
whatever the copy says; that is inherent to "sign-up creates no session", which the auth
seam's review accepted. *Recommendation:* show the API's own 401 message verbatim as a
form-level alert, with the existing "Already have an account? Sign in →" and "Forgot
password?" paths. No added wording about accounts existing.

**D4. The OIDC provider stack.** It's drawn as three live buttons; the AC forbids dead
buttons. *Recommendation:* hold the position **in code only**. A marked slot comment
sits above the form in `SignupForm` where the stack and the "or" separator go, and
nothing renders, so the card starts at the email form. The alternatives were visible,
non-interactive tiles saying "Coming soon" (they claim "Auto-connects your calendar",
which isn't true yet) and `disabled` buttons (dead buttons by another name).

**D5. New copy** with no locked source: the home's sentence, the reset-success line, the
saved-events empty state, "Signed in as {email}". The wording is above; approve it or
change it.

**D6. Footer links to routes that don't exist** (How it works `/how`, About `#`, Privacy
`/privacy`, Contact `#`, Terms `/terms`). The AC says "as drawn". *Recommendation:*
render them as drawn, including the `#`s. The footer is shared with the preview page,
and dropping links now would make the next item put them back. Note that the privacy
line's Terms and Privacy links will 404 until those pages exist.

## Deviations From the Mockups (recorded, not asked)

- **No spinner.** `EXPERIENCE.md` says "No spinners, anywhere", and
  `styles/motion.test.ts` fails on any animation other than `.fade-in`. The in-flight
  state uses the spec's own reduced-motion form: a **static dot** + the label.
- **The primary button stays enabled** (the mockups' State A); validation runs on blur
  and submit. A button disabled until the form is valid gives no reason why.
- **Card width 480/520 px** (the mockups and `EXPERIENCE.md`), not `layout.container.form`
  (720 px, DESIGN.md). The binding mockups and the token disagree, and the mockups are
  more specific. It is the one non-token value, and the code says why.
- **Success after sign-up goes to `/onboarding`** (the post-signup routing lock), even
  for an existing account whose password matched. `/onboarding` sends a finished user
  home; that is the next item's routing.

## The Files

### Created

| File | Purpose |
|------|---------|
| `frontend/lib/csrf.ts` | Read the cookie, fetch the token if it's missing, set `X-CSRFToken` on unsafe methods |
| `frontend/lib/session.ts` | `sessionHeaders`, `getSession`, `homeRoute` |
| `frontend/lib/api-errors.ts` | `readApiError`: the API's message and field errors, verbatim |
| `frontend/app/signin/page.tsx` | `/signin`, with the silent redirect |
| `frontend/app/signup/page.tsx` | `/signup` |
| `frontend/app/reset-password/page.tsx` | `/reset-password`: request or set-new by token; `no-referrer` |
| `frontend/components/pre-auth/pre-auth-topbar.tsx` | The brand-only topbar |
| `frontend/components/pre-auth/pre-auth-footer.tsx` | The drawn pre-auth footer |
| `frontend/components/auth/auth-field.tsx` | Label, input, hint, error row; the password reveal toggle |
| `frontend/components/auth/submit-button.tsx` | The primary with the static-dot in-flight state |
| `frontend/components/auth/signin-form.tsx` | Sign-in |
| `frontend/components/auth/signup-form.tsx` | Sign-up, then sign-in, then the hold, then `/onboarding` |
| `frontend/components/auth/reset-request-form.tsx` | The reset request and the "sent" state |
| `frontend/components/auth/reset-confirm-form.tsx` | Set-new, success, and expired/used |
| `frontend/components/auth/sign-out-button.tsx` | Sign out |
| `frontend/components/saved-events-section.tsx` | The saved-events read for the home |
| `frontend/public/brand/eventpulse24-logo.png` | Copied from the mockups |
| a `*.test.ts(x)` beside each of the above | See The Tests |

### Modified

| File | Change |
|------|--------|
| `frontend/lib/backend-client.ts` | Register the CSRF middleware in the browser |
| `frontend/app/page.tsx` + test | Routing + the placeholder home; drop the duplicate `AddEventButton`; still `force-dynamic` |
| `frontend/components/personal-events-section.tsx` + test | Forward the visitor's cookie (finding 3) |
| `.env.example` | `CSRF_TRUSTED_ORIGINS` for the local frontend origins |
| the setup doc that lists `.env` keys (to be found; `README.md` or `docs/`) | Say production must set `CSRF_TRUSTED_ORIGINS` |
| `.env` (local, untracked) | The same line, so the stack works |

No backend change, and no schema regeneration: every endpoint already exists in
`lib/api/schema.ts`.

## The Tests

Vitest. `next/navigation` (`redirect`, `useRouter`) and `next/headers` (`cookies`) are
mocked; API calls are stubbed per test.

| Rule | Test |
|------|------|
| CSRF on writes | a client with the middleware and a stub `fetch`: `POST`/`PATCH`/`DELETE` carry `X-CSRFToken` equal to the cookie; `GET` carries none |
| The token is read fresh | change `document.cookie` between two `POST`s → the second carries the **new** value (finding 2) |
| A missing cookie is fetched | no cookie → `GET /api/auth/csrf` happens first, then the `POST` carries the token |
| The real client is wired | `api` from `@/lib/backend-client` sends the header (catches "middleware written, never registered") |
| The session fold | `me` 200 → signed-in; 401 → anonymous; 500, throw, no base URL → unavailable; the `cookie` header is forwarded |
| Each routing branch of `/` | anonymous → `redirect("/preview")`; not onboarded → `redirect("/onboarding")`; onboarded → the home renders, `redirect` not called; unavailable → the calm error, `redirect` not called |
| The silent redirect | signed-in `/signin` → `redirect("/")`; anonymous → the form. Same for `/signup` |
| The placeholder home | the heading; the personal and saved sections; sign-out; **no digest card, score or Pulse Card markup**; **one** personal-events list (finding 5); still `force-dynamic` |
| The server reads carry the session | `PersonalEventsSection` and `SavedEventsSection` send the visitor's `cookie` (finding 3) |
| Sign-in success / errors | success → `/`; 401 → the API's text exactly, on Password, `aria-invalid` on Password only, `role="alert"`; 429 and network → form-level; in-flight → `aria-busy`, disabled, "Signing in…" |
| Enumeration-neutral copy | across every sign-in and sign-up error path, the page text never contains "already exists", "don't see an account", "no account" or "registered" |
| Sign-up | mismatch on Confirm (blur and submit), Password kept; too short; bad email; 422 `details` verbatim on the field; 201 → sign-in → the notice → `/onboarding` after 1500 ms (fake timers) and after 0 ms under reduced motion; the follow-up sign-in 401 → the API message (D3) |
| No dead OIDC buttons | sign-up renders no button named "Continue with …" (D4) |
| Reset | request → "We've sent a reset link to {email}."; set-new success; `invalid_reset_token` → the expired state with the API's message and the way back; weak password `details` verbatim; the token is stripped from the URL |
| Sign-out | posts sign-out → `/signin`; an error → the API message |
| Pre-auth shell | the topbar contains only the brand anchor (no other link or button); the footer's links are as drawn; `aria-current` on the current route |
| WCAG | every input has a label by `htmlFor`; errors are linked by `aria-describedby`; the reveal toggle's `aria-pressed` flips and its label names the destination state |

**Revert verification.** Each rule above is reverted by hand and its test watched to
fail: the middleware unregistered, the cookie cached at module load, the `cookie` header
dropped from a server read, `homeRoute` branches swapped, an enumeration string planted,
the error moved to the Email field, the 1.5 s hold made unconditional. The results go in
the test report. A rule whose revert doesn't fail its test gets a better test.

**Gates:** `make lint-web` (ESLint, `tsc` via `next typegen`, Prettier) and
`make test-web`; the existing architecture tests (kebab-case, no motion classes, no
hand-written `fetch`) keep passing. **A live run-through** follows on the real stack:
sign up → land on `/onboarding` (a 404 until the next item; the URL is what's checked),
sign out, sign in → `/` routes, a personal event appears on the home, reset request →
the Mailpit link → set new → sign in with it.

## The Decisions, and Why

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Where CSRF is added | One openapi-fetch middleware on the one client | Every write, current and future, is covered with no call-site change; a per-call header would be forgotten once |
| How the token is held | Read from the cookie per request | It rotates on sign-in (probed). A cached token is refused |
| Retry on `csrf_failed` | No | Fresh reads remove the common cause. The rest isn't fixed by retrying, and the API's message says what to do |
| Where `/` routes | In the page's server component | The proxy stays a pure API forwarder; the decision is a pure, testable function |
| An unavailable API on `/` | A calm error, not a redirect | A signed-in user isn't anonymous because the API blinked |
| Server reads | Forward the visitor's `Cookie` | Without it every server read is anonymous (probed) |
| The reset token | Stripped from the address bar on load; `no-referrer` | It's a 30-minute bearer credential for the account; it shouldn't sit in history or leave in a `Referer` |
| Saved events on the home | Shown inline | Neither has a route yet. Linking to a 404 isn't "links to" |
| `CSRF_TRUSTED_ORIGINS` | `.env.example` + docs | Without it no local write works; production must set its own origin |

## What This Item Does Not Cover

- **OIDC** — the slot only (D4). A later intent wires it, identity-only, under AD-18.
- **`/onboarding` and `/preview`** — the next two items. This item redirects to them.
- **The authed shell (sidenav, `Account` affordance)** — later. Sign-out lives in the
  home's footer until then.
- **"Last-visited authed route" after sign-in** — `EXPERIENCE.md` says "or last-visited
  authed route if available". Nothing records it yet; `/` is the default the spec gives.
- **Mobile layouts for the auth routes** — `EXPERIENCE.md` defers them ("desktop-first at
  MVP"). The forms are a single column and must not break at a narrow width, but there's
  no mobile mockup to match.
- **The end-to-end proof** — `e2e-proof-and-contract-tests` owns the browser-level flow.
