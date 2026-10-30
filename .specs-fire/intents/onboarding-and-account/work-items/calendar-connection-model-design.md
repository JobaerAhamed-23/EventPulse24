# Design: Calendar Connection Model & Credential Encryption

**Work item**: `calendar-connection-model`
**Intent**: `onboarding-and-account`
**Mode**: validate (Checkpoint 1 of 2 — this document)
**Date**: 2026-10-29

---

## 1. What this item delivers

The `CALENDAR_CONNECTION` entity (AD-18) and the encryption that makes its credential safe to
store, plus the `PersonalEvent.Source` change that lets an imported event reference its
connection.

**In scope**: the model, the migration, the encrypted field, the constants, the app-level key
and its fail-fast startup check, and the tests that prove the credential never reaches a
plaintext column, a log line, a `repr`, or an API response.

**Out of scope** (separate work items): fetching the feed (`ics-calendar-adapter`), polling
and import (`calendar-sync-and-polling`), the HTTP endpoints (`calendar-connect-api`), the
Free-tier cap enforcement at the connect step (`calendar-connect-api`).

---

## 2. The problem, stated precisely

The secret ICS/webcal address **is** the credential. Google classifies it as a secret and
offers a reset for it (PRD FR-50, §11.2). Anything that can read the `personal` schema can
therefore impersonate the user against their calendar provider until the address is reset.

Three things follow, and they drive every decision below:

1. **The stored value must be ciphertext.** A database dump, a backup, a replica, a
   `SELECT` in an ops console, or an error page showing raw SQL — none of them may yield a
   usable calendar address.
2. **The plaintext must exist in as few places as possible.** A plaintext that lives in a
   Python attribute, an exception message, a log record, a `repr`, or an API payload is a
   plaintext that leaks.
3. **The key must be separate from `SECRET_KEY`.** `SECRET_KEY` signs sessions and CSRF
   tokens; it is frequently shared across environments and rotates for reasons that have
   nothing to do with data at rest. Using it as the encryption key would mean one leaked
   `SECRET_KEY` decrypts every credential, and rotating it would orphan every stored
   credential.

---

## 3. Decisions

### D1 — The cipher: AES-256-GCM, not Fernet

**Decision.** Encrypt with **AES-256-GCM** (`cryptography.hazmat.primitives.ciphers.aead.AESGCM`).

**What each option gives you:**

| | Fernet (AES-128-CBC + HMAC-SHA256) | AES-256-GCM (chosen) |
|---|---|---|
| Confidentiality | AES-128-CBC | AES-256 |
| Integrity | HMAC-SHA256, encrypt-then-MAC | GCM's built-in GHASH tag |
| Nonce handling | Random 16-byte IV, prepended | Random 12-byte nonce, prepended |
| Tamper detection | HMAC over IV+ciphertext | AEAD tag over ciphertext |
| Ciphertext format | versioned, base64 | our own (see D2) |
| Key size | 32 bytes (AES-256 key, HMAC-SHA256 key derived from it) | 32 bytes (AES-256) |

**Why GCM:**

- **It is a proper AEAD primitive.** One key does both jobs, and the tag covers the
  ciphertext *and* the associated data. Fernet is encrypt-then-MAC, which is correct, but it
  is two primitives and two key schedules under one hood.
- **256-bit block key, not 128.** Fernet's AES-128-CBC half is 128-bit; GCM gives us 256.
  This is not the deciding factor — 128 bits is plenty against brute force — but there is no
  reason to take the smaller half.
- **Associated data.** GCM lets us bind the ciphertext to *what* it encrypts. We use that in
  D4 to bind a credential to its connection row, so a ciphertext copied from one row into
  another is rejected by the AEAD itself rather than by a convention.

**Why not Fernet:** no disqualifying flaw, but GCM gives a real AEAD with AAD in one
primitive, and the stored format is ours to design either way.

**Rejected: AES-CBC.** No authentication tag of its own; ciphertext malleability would let a
tampered row decrypt to attacker-chosen bytes.

**Rejected: "just hash it".** A hash is not reversible, so the feed could not be fetched.
The credential must be *decryptable* by the server and *only* by the server.

**Dependency.** `cryptography==46.0.3` added to `backend/pyproject.toml`. It is a
compiled wheel with prebuilt binaries for CPython 3.13 on Linux, macOS and Windows, so it
installs without a Rust or C toolchain — no build step in CI.

**Import-contract impact.** `cryptography` is not an LLM, Stripe, HTTP or Redis SDK, so no
existing `import-linter` contract covers it. The chosen placement (§4) keeps it out of
`domain` and out of `ports` anyway.

---

### D2 — The stored format: a self-describing envelope that can rotate

**Decision.** The stored column holds a **versioned, tagged envelope**:

```
EPENC1.<key_id>.<nonce_b64>.<ciphertext_b64>
```

- `EPENC1` — the format version. A future format gets `EPENC2`.
- `<key_id>` — which key encrypted it (see D3).
- `<nonce_b64>` — the 12-byte GCM nonce, base64url, unpadded.
- `<ciphertext_b64>` — the ciphertext **including** the 16-byte GCM tag, base64url, unpadded.

**Why not Fernet's own wire format?** Fernet is fine, but its version byte is a *Fernet*
version, not an *EventPulse24* version. Our own envelope lets us add a second key id, a
"decrypt-then-reencrypt" marker, or an algorithm id later without changing the column type
or the migration.

**Why a key id at all, if rotation is out of scope?** Because the brief says key rotation
"is not designed in this intent" — not "key rotation must be impossible". A format that
*cannot* express a key id forces a schema change at rotation time; a format that can express
one makes rotation a data operation. The key id costs one short token and changes nothing
about the format otherwise.

**Why not `MultiFernet`/`MultiFernet`-style key lists?** Same reason: a list of keys in the
env var is a **secret-management** decision (how many keys, how they're provisioned, who
rotates). The brief explicitly leaves that open. The envelope carries the *capability*; the
list-of-keys policy is a later decision that needs no schema change.

**The column type.** `models.TextField`, never `BinaryField` and never a `CharField` with a
length that could truncate. A truncated envelope fails to parse; a `TextField` cannot
truncate silently. The envelope is ASCII (base64url + dots), so a `TextField` is exact.

**Storage of the nonce.** GCM nonce reuse under one key is catastrophic (it leaks the XOR of
two plaintexts and breaks authentication). We generate a fresh random 12-byte nonce per
encryption with `os.urandom` — a CSPRNG, never `random`. A random 96-bit nonce has a
collision birthday bound of ~2^32 encryptions under one key, far beyond any realistic
lifetime for a single key; and we never derive the nonce from anything (no counter, no
timestamp), so there is no reuse path.

**A fresh nonce per encryption even for the same plaintext.** Encrypting the same URL twice
yields different ciphertexts. That is correct and expected.

---

### D3 — Key management: one key, one key id, from the environment

**Decision.** The application-level key comes from the environment as
`CALENDAR_CREDENTIAL_KEY`, read by `config/env.py` like every other setting (AD-8: the
environment is read in exactly one place).

**Format.** The environment variable holds a **base64url-encoded 32-byte key**, optionally
prefixed with a key id:

```
CALENDAR_CREDENTIAL_KEY="k1.<base64url-32-bytes>"
```

The prefix is the **key id** that ends up in the envelope. Keeping it in the same variable
means the id and the key cannot drift apart: rotating means writing a new value, and the id
in the envelope tells you which one a row was written with.

**Why not several keys in one variable now?** Because the *policy* — how many keys are kept
alive, what happens to a row whose key has been retired — is exactly the open question the
brief defers. But the *format* has to permit it before the first row is written, and it does:
a comma-separated list of `id.key` pairs is a superset of the single-key form, and the
envelope's `<key_id>` slot is already there. Adding the list later is an env-parsing change
plus a key-id lookup — **no migration, no stored-format change**.

**Why the key id is in the envelope rather than only in the env var:** a row encrypted with
a retired key must be *identifiable* without decrypting it. The envelope answers that in
one read.

**The key is 32 bytes.** AES-256. A shorter key is refused at startup rather than stretched
by the application's own KDF: stretching is a policy decision (PBKDF2 rounds vs HKDF) and
doing it implicitly would make the stored key format ambiguous.

**Never derived from `SECRET_KEY`.** Never a fallback. Never a default. If the variable is
absent or malformed, the app refuses to start (§D5).

---

### D4 — Where the key lives in code: a dedicated module, not the model

**Decision.** The key handling lives in **`apps/personalization/credentials.py`** (see §4 for
why this module), and the model field is a **custom Django field** that encrypts on the way
in and decrypts on the way out.

**Why a custom field rather than explicit encrypt/decrypt in the service layer:**

| | Custom field | Explicit encrypt/decrypt in the service |
|---|---|---|
| A raw `SELECT` returns | ciphertext | ciphertext |
| A forgotten `Model.objects.filter(...)` in some other code path | ciphertext | **plaintext** |
| An accidental `repr(conn)` | ciphertext-ish | ciphertext-ish |
| An admin form field | ciphertext | **plaintext** |
| The number of places that must remember to encrypt | **one** | every write site |

The last row is the whole argument. With a custom field, *every* path — the service, the
admin, a management command, a test factory, a future script — is encrypted by
construction. With explicit encrypt/decrypt, encryption is a convention that a new code
path can forget, and the failure mode is a plaintext credential in a database column.

**The field's Python-level attribute holds the plaintext**, because that is what the service
needs (it has to hand a `Credential` to the port). The *stored* value is ciphertext. The
plaintext attribute is never serialised, never logged, and never returned by an API
serializer (there is no serializer for this model in this item; §7).

**Round-trip safety.** The field's `to_python` decrypts. A row whose ciphertext cannot be
decrypted (wrong key, corrupted column, retired key) raises a typed error
(`CredentialDecryptionError`) rather than returning `None` or an empty string. A silent
`None` would look like "no credential", and the poll would then mark the connection as
revoked — misreporting a key problem as a revoked address.

**Associated data.** The GCM AAD is a fixed, non-secret string identifying the field and
the table: `"eventpulse24.calendar_connection.credential"`. It is **not** the row id —
binding to the row id would make the ciphertext non-portable (you could not copy a row
between databases, and a migration that rewrites ids would break every credential). A fixed
AAD already prevents cross-purpose confusion: a ciphertext produced for another field or
table will not decrypt under this key.

---

### D5 — Failing fast at startup

**Decision.** The key is validated at **import of the credentials module**, which happens
when Django loads the app registry. A missing or malformed key raises
`ImproperlyConfigured` with a message naming the environment variable and the expected
format — and **never** falls back to plaintext, to `SECRET_KEY`, or to a generated
development key.

**Why fail at import and not lazily on first use:** a lazily-failing credential means the
app starts healthy, passes its health checks, accepts traffic, and only fails when a user
connects a calendar. That is a production incident discovered by a user. Failing at startup
means the deploy fails, the deploy is rolled back, and no user ever sees it.

**Why "whenever a component that needs the key is configured":** the `personalization` app
owns the model, so the app is always configured with it. The check is therefore
unconditional for this app. The failure mode being described in the work item — "a component
that needs the key is configured" — is exactly satisfied: this component is always
configured, so it always fails fast.

**Local development and CI.** The key is a **required** environment variable, with a
local-only default in `.env.example` and in the local `.env`. There is deliberately **no
code-level default**: a default in `config/env.py` would be a silent fallback, which is the
thing the acceptance criterion forbids.

**Tests.** The test settings pin a fixed key, so the suite never needs a secret. The
fail-fast test calls the validator directly with a missing/malformed value and asserts the
typed error — it does not need to un-import the module.

**`manage.py check` must pass**, including the retention check (AD-15) and a new system
check that the key is present and well-formed. The system check (`eventpulse.E007`) reports
a missing key as an *error* with a hint naming the variable, so `manage.py check` is a
second, tool-visible gate.

---

### D6 — Deduplication: a keyed hash of the normalised URL

**Decision.** Store `credential_fingerprint`: a **keyed HMAC-SHA256** of the normalised URL,
hex, and a unique constraint on `(user_id, credential_fingerprint)`.

**Normalisation before hashing** (so the same calendar typed two ways is one row):

1. Trim whitespace.
2. Lowercase the **scheme and host** only. The path and query are case-sensitive and are
   left exactly as typed — a secret path segment is case-sensitive, and lowercasing it would
   produce a *different* (wrong) URL.
3. Drop a trailing `/` on the path? — **No.** A trailing slash is part of the address for
   some providers and not for others; normalising it could turn a valid URL into an invalid
   one. The scheme/host lowercasing is the only normalisation.

**Why HMAC and not a plain hash:** a plain SHA-256 of the URL is deterministic and
therefore *guessable*. The secret ICS address embeds a long random token in its path — but
an attacker with the database could confirm a guessed URL by comparing digests, and would
only have to guess the *provider-specific* format. With an HMAC keyed by the application
key, an attacker without the key cannot compute the expected digest for any candidate URL,
so the column leaks nothing about which calendars are connected beyond the count.

**Why a fingerprint at all (the alternative was decrypting every row):** without it,
"has this user already connected this calendar?" requires decrypting every one of the user's
connection rows. With it, it is one indexed equality lookup. The acceptance criterion
"the same calendar can't be connected twice without decrypting every row" is satisfied by a
unique constraint on the fingerprint.

**The HMAC key is the application-level key.** One key. Keyed by the same secret that does
the encryption — so the fingerprint is useless without the application key, and rotating the
key (a later item) changes the fingerprints too, which would require a re-fingerprint
migration. **This is recorded as a known consequence**, not hidden: at rotation time the
fingerprints must be recomputed, or the rows re-encrypted anyway (which is exactly what a
rotation migration does), at which point the fingerprints are recomputed for free.

**The fingerprint is not the credential.** It is one-way, and it never leaves the server.
It is not in the admin list display and not in any API response.

---

### D7 — Status values and transitions

**Decision.** The `status` column takes exactly three values.

| Value | Meaning |
|---|---|
| `active` | The connection works. The next poll is scheduled. |
| `needs_reconnect` | The provider said the address is no longer valid (HTTP 401/403/404/410), or the credential could not be decrypted. The user is prompted to reconnect. |
| `disconnected` | The user disconnected it. The row and its imported events are being purged. |

**`disconnected` deletes the row.** FR-50 says disconnecting removes the imported events
"within 24 hours", and AD-18 says a disconnect "purges exactly that connection's events".
A row that lingers with `status = disconnected` would be a row whose credential is still
encrypted-at-rest but whose events are gone — a state nobody needs, and one that keeps a
credential alive after the user asked for it to be revoked.

**But the disconnect must be a soft-delete first, so the purge is auditable and
crash-safe.** The transition is:

1. `status` → `disconnected`, `credential` → **cleared** (the ciphertext is overwritten with
   an empty string, so the secret is destroyed immediately, not at purge time), within the
   disconnect transaction, together with the audit row (AD-5).
2. The purge of that connection's imported `PersonalEvent` rows runs in the same
   transaction if it can, or as a follow-up job otherwise.

**Why clear the credential at step 1 rather than delete the row outright:** "revocable by
the user" (AD-18) is satisfied the moment the credential is destroyed. If the purge job
dies, the credential is *already* gone — the user's revocation is not contingent on a job
succeeding. That ordering is the safe one: **destroy the secret first, purge the events
second.**

**Why not a hard delete of the row?** Because then there is no record that a disconnect
happened, and the audit row would reference a target id that no longer exists. The row is
purged by the retention sweep after the events are gone (AD-15, `ACCOUNT_IDENTITY`).

**Transition table.** Legal transitions, and nothing else:

| From | To | Trigger |
|---|---|---|
| — | `active` | The connect command succeeds. |
| `active` | `needs_reconnect` | A poll returns 401/403/404/410. |
| `active` | `disconnected` | The user disconnects. |
| `needs_reconnect` | `active` | The user reconnects with a working address (new row, or this row updated — see below). |
| `needs_reconnect` | `disconnected` | The user disconnects. |
| `disconnected` | — | Terminal: the row is purged. |

**Reconnect semantics.** A `needs_reconnect` row is **updated in place** when the user
reconnects: the credential is re-encrypted, the fingerprint is replaced, the status returns
to `active`, and the poll schedule resets. The unique constraint on
`(user_id, credential_fingerprint)` is on the *new* fingerprint, so reconnecting the same
address to the same row is an update, not a duplicate.

**Edge case, decided:** if the user reconnects with an address that is *already connected*
under a different row, the unique constraint refuses it and the command reports "already
connected". That is the right answer — the Free-tier cap counts connections, and silently
merging two rows would lose one connection's event history.

**Why the status is a column and not derived.** A connection's health is a fact about the
last interaction with the provider, not something derivable from the stored credential. It
has to be persisted, and it has to be settable by a poll.

---

### D8 — The model

`CalendarConnection` in `apps/personalization/models.py`, `personal` schema, owned by
`personalization` (AD-16).

| Column | Type | Notes |
|---|---|---|
| `id` | UUID (UUIDv7) | `shared.models.UUIDv7Model` — required by system check E005. |
| `user_id` | UUID | **By value.** No FK to `User` (AD-3, OQ-8). |
| `provider` | Char(16) | `google` \| `apple` \| `outlook`. |
| `credential` | **EncryptedTextField** | The encrypted secret. See D1–D4. |
| `credential_fingerprint` | Char(64) | HMAC-SHA256 hex of the normalised URL. See D6. |
| `status` | Char(24) | `active` \| `needs_reconnect` \| `disconnected`. See D7. |
| `last_polled_at` | DateTime, null | When the last poll finished. Null until the first poll. |
| `next_poll_at` | DateTime, null | When the next poll is due. Null when the connection is not `active`. |
| `last_error_kind` | Char(32), null | A **kind**, never a message. E.g. `revoked`, `transient`, `undecryptable`. |
| `last_error_at` | DateTime, null | When the error happened. |
| `display_label` | Char(120), blank | A user-supplied *name* for the calendar ("Work", "Family"). **Not** the URL. |
| `created_at` | DateTime | |
| `updated_at` | DateTime | |

**`last_error_kind` never holds the URL or an exception message.** The acceptance criterion
says "last error kind, never the URL". An `httpx` exception message contains the full
request URL (that is the classic AD-13 leak the work item warns about), so the column holds
a **closed set of kind slugs** and never a message. The slug set is defined in the service
layer when the error is classified.

**`display_label` is not the credential.** It is a free-text name the user gives the
calendar, shown in the UI ("Work calendar"). It is a PII-ish string but it is *not* a
secret; it is a normal user-entered label like an event title, and it is covered by the same
no-free-text-in-logs rule (AD-13): the model never logs it.

**Why no `provider_account_id` or `provider_email`?** The MVP connects by pasting an
address; there is no provider account to identify. The provider is a label on the
connection ("which of the three this is"), and `provider` alone says that. A future OAuth
adapter can add a column.

**Retention.** `RetentionCategory.ACCOUNT_IDENTITY` — the PRD's own words: "Personal email
addresses and calendar credentials: while active; encrypted at rest; purged on disconnect or
account deletion." The `ACCOUNT_IDENTITY` category already exists in `shared/retention.py`
and explicitly names calendar credentials.

**`PersonalEvent` gains `calendar_connection_id` and a new `Source` value.**

| Change | Detail |
|---|---|
| `PersonalEvent.Source.CALENDAR_IMPORT = "calendar_import"` | The new value. |
| `PersonalEvent.calendar_connection_id` | UUID, **nullable**, no FK — the connection is in the same schema (`personal`), but the FK would make the schema wall question moot while adding a cascade-delete coupling the project does not want. Held **by value**, consistent with every other relation in this project (`PersonalEvent.user_id`, `SavedEvent.event_id`). |
| Check constraint `personal_event_source_connection_ck` | `(source = 'calendar_import') = (calendar_connection_id IS NOT NULL)`: imported rows always have a connection; user-created rows never do. |
| Unique constraint `personal_event_connection_uid_uq` | `(calendar_connection_id, source_uid)` — so a re-sync **upserts** rather than duplicating. |

**`source_uid`**: the ICS `UID` of the entry, stored alongside the connection. It is the
provider's identifier for the event, and `(connection, uid)` is what makes a re-sync
idempotent. It is nullable, because a user-created event has no UID. The unique constraint
is on `(calendar_connection_id, source_uid)`; Postgres treats NULLs as distinct in a unique
constraint by default, so the many user-created rows with `source_uid = NULL` do not
collide.

**Why the connection is held by value rather than by FK.** AD-3's wall is about *cross-schema*
relations; `CalendarConnection` and `PersonalEvent` are both in `personal`, so an FK would
not violate the wall. But: (a) the project holds *every* other relation by value, by
convention (OQ-8: no `GenericForeignKey`, no relation to `User`); (b) an FK creates a
`ON DELETE CASCADE` or `SET NULL` decision that couples the purge of a connection to the
purge of its events — and D7 wants the credential destroyed *first* and the events purged
second, which is easier to express as two explicit steps than as a cascade; (c) the
check constraint on source/connection is clearer than a nullable FK's implicit nullability
rules. The connection row is purged by the retention sweep in the same pass as the events.

**"A disconnect purges exactly that connection's events."** With the id held by value, the
purge is `PersonalEvent.objects.filter(calendar_connection_id=conn.id).delete()` — exact by
construction, and it is the same query for one connection or for all of them.

---

### D9 — Named constants

In `shared/constants.py` (AD-8: stdlib only, one home):

```python
# AD-18 / FR-50: how often a connected calendar is polled. PROVISIONAL (OQ-7): the interval
# is ours to choose, since we are the HTTP client, but it is not yet validated against a
# live Google secret address. Change this one line when OQ-7 closes.
CALENDAR_POLL_INTERVAL = timedelta(hours=1)

# FR-50: the Free tier connects one calendar provider. Pro (3) is a later intent; this
# intent is Free-only, so the cap is 1.
FREE_TIER_CALENDAR_PROVIDER_CAP = 1
```

`shared/constants.py` is stdlib-only, so `timedelta` is fine and `domain` may import it.

**Why the poll interval is provisional and says so.** OQ-7 is open in the brief. A constant
with a comment saying it is provisional is the honest artifact: the next reader sees a
number *and* its uncertainty, instead of a number that looks measured.

---

### D10 — The credential never leaks: the enforcement points

The acceptance criterion requires the credential to be absent from the model's `repr`, the
admin representation, any serializer, and the logger output from save and load.

**1. The model's `repr`.** Django's `Model.__repr__` prints `<CalendarConnection: {self}>`
where `self` comes from `__str__`. So `__str__` must not include the credential. It returns
`f"{self.provider} calendar"` — provider and nothing else. The admin's list display uses
`__str__` by default, so this covers the admin too.

**2. The admin.** The `CalendarConnection` admin is registered read-only (`has_add_permission`
/ `has_change_permission` / `has_delete_permission` → `False`), like the other audit-style
admins. The **credential field is excluded from the admin entirely** — it is not in
`fieldsets`, not in `list_display`, not in `readonly_fields`. A `readonly_fields` entry
would still *render* the ciphertext into the page; excluding it means the ciphertext never
reaches the browser at all. The admin shows `provider`, `status`, `last_polled_at`,
`next_poll_at`, `last_error_kind`, `created_at` and `display_label`. The fingerprint is also
excluded: it is a stable identifier of a secret, and it has no business in a browser.

**3. Serializers.** There is **no serializer for `CalendarConnection` in this item.** The
API (`calendar-connect-api`) is a different work item, and when it lands it must never
include the credential or the fingerprint. The design records that requirement here so it
is not forgotten; the acceptance criterion "the credential never leaks" is met *at this
item* by the absence of any serializer that could leak it, plus a test asserting that the
model has no `__str__`/repr path that exposes it.

**4. Logs.** Three mechanisms, in order of strength:

- **The logger adapter's allowlist (AD-13).** `adapters/logging/redaction.py` has an
  `ALLOWED_FIELDS` allowlist; anything not on it becomes `[redacted]`. The credential is
  never on it, and **`credential_fingerprint` is explicitly not on it either** — it is a
  stable identifier of a secret, and an allowlisted field would be logged verbatim.
- **Pattern scrubbing.** `webcal://` and `https://` URLs containing a long secret path are
  already scrubbed: the `webcals?://` pattern catches `webcal(s)://…`, and the
  `[A-Za-z0-9_-]{40,}` pattern catches the long opaque path segment that every provider
  uses. A Google secret address looks like
  `https://calendar.google.com/calendar/ical/<48+ chars>/basic.ics`, so the long-token
  pattern covers it.
- **The exception rule.** `JsonFormatter` never logs `str(exc)` — only the exception's
  type chain and stack frames. So an `httpx` exception carrying the URL in its message
  cannot leak through `exc_info`. The formatter's docstring already states this.

**5. The Python object.** The plaintext lives in the model instance's
`credential` attribute (D4). It is a `str` there, so a careless `logger.info("%s", conn.credential)`
would leak it. The defence is (a) project loggers never interpolate args — the formatter
replaces `args` with `[redacted]` — and (b) the service layer never logs the credential.
We add a test that a `repr` of the model and of the service's return value never contains
the URL.

**6. `Credential` from `ports.calendar`.** The work item says to reuse it rather than
inventing a second secret wrapper. It already redacts `repr` and `str`. **The decrypted
value is only ever a `ports.calendar.Credential`** at the service boundary: the model field
decrypts to a `str` internally (a Django field cannot know about the port), and the service
wraps it into a `Credential` before handing it to the calendar port. `Credential.reveal()`
is the only way to get the plaintext back, and only the fetch path calls it.

**D7's `last_error_kind` is a slug**, so an error message never lands in a column that the
admin renders.

---

### D11 — The encrypted field's implementation

**Decision.** `apps/personalization/fields.py` defines `EncryptedTextField`, a
`models.TextField` subclass.

```python
class EncryptedTextField(models.TextField):
    """A text column whose stored value is ciphertext (AD-18)."""
```

**Behaviour:**

- `get_prep_value(value)` → encrypts (this is the write path).
- `to_python(value)` → decrypts (this is the read path). `None` passes through.
- `from_db_value(value, expression, connection)` → decrypts, so a value loaded by the ORM
  is plaintext in Python.
- `db_type` → `"text"`.
- `value_to_string` (serialization) → **the ciphertext**, never the plaintext. This is the
  belt-and-braces for "no serializer leaks it": Django's serializers use
  `value_to_string`, so even `dumpdata` yields ciphertext.

**Encrypt-on-write, decrypt-on-read asymmetry.** `get_prep_value` is called on every write
path, so there is no way to write plaintext into the column — including a `.update()` that
bypasses `save()`, because `update()` goes through `get_prep_value` too.

**The double-encryption trap.** `get_prep_value` must not double-encrypt a value that was
already encrypted. The field distinguishes them by **type**: the plaintext is always a
`str`, and the stored form is always the **envelope string** — but a plaintext URL is also a
`str`. So the field's contract is:

- `get_prep_value` receives the **plaintext** and encrypts it.
- `from_db_value` receives the **envelope** and decrypts it.
- `to_python` receives either: if it parses as an envelope, decrypt it; otherwise treat it
  as plaintext (this is what a freshly-assigned `conn.credential = url` does when Django
  calls `to_python` on assignment — Django does not call `to_python` on assignment, so
  `to_python` only ever sees envelope strings from the DB, but being liberal here is
  harmless).

To make the "already encrypted" case unambiguous, the **envelope has a distinctive prefix**
(`EPENC1.`). `to_python` checks the prefix: present → decrypt; absent → it is plaintext and
is returned as-is. `get_prep_value` always encrypts, because the caller is handing it
plaintext.

**Wait — that is ambiguous for a plaintext that begins with `EPENC1.`.** A plaintext that
starts with `EPENC1.` is not a valid URL (the connect command validates the scheme before
saving), so the collision is unreachable in practice. But we do not rely on "in practice":
the field's `to_python` on the **read** path is only ever handed a value that came from the
database, and every value in that column is an envelope by construction (the only writer
encrypts). The prefix check on the read path is therefore a **defensive** check, not a
mechanism.

**Clearing the credential.** D7's disconnect clears the ciphertext. The field's
`get_prep_value(None)` → `None` (NULL column) or `""` (empty string)? **The column is
NOT NULL** — a connection without a credential is meaningless — so disconnecting sets it to
the empty string, and `to_python("")` returns `""`. The service layer treats `""` as "no
credential" and refuses to fetch with it.

Hmm — actually, a cleaner alternative: make the column **nullable**, and `NULL` means
"the credential has been destroyed". Then "cleared" is unambiguous, and the service layer
cannot accidentally treat `""` as a credential. **Decision: the column is nullable, and
`NULL` is the cleared state.** A `NULL` credential on an `active` connection is a bug, and a
check constraint can say so:

```
(status = 'disconnected' AND credential IS NULL)
OR (status <> 'disconnected' AND credential IS NOT NULL)
```

That constraint is exactly D7's state machine, enforced by the database. A connection can
be `active`/`needs_reconnect` only with a credential, and `disconnected` only without one.
**Adopted.**

**Rotation of the credential in place.** When the user reconnects, the row's credential is
replaced with a new envelope. `save(update_fields=["credential", ...])` encrypts the new
plaintext. The old ciphertext is overwritten by the UPDATE, so the old secret is gone from
the row (though possibly still in the WAL / a backup — noted, not solvable here).

---

### D12 — Where the code lives

**The layering problem.** `cryptography` is a third-party library. The `import-linter`
contracts say `domain` is pure (stdlib only) and `ports` is a layer above `domain`. The
encryption is application infrastructure, not domain logic: it has no business rules, only
a cipher.

**Decision.** The crypto lives in **`apps/personalization/`**:

| Module | Contents |
|---|---|
| `apps/personalization/credentials.py` | Key loading and validation; `encrypt` / `decrypt`; the envelope format; the HMAC fingerprint; the typed errors. **No Django model imports** — it is pure crypto over a supplied key. |
| `apps/personalization/fields.py` | `EncryptedTextField`, the Django field that uses `credentials`. |

**Why not `shared/`?** `shared/` is imported by `domain` (only `shared.constants` and
`shared.ids`, per the contract's `ignore_imports`). A crypto module in `shared/` that
imports `cryptography` would be *importable* by `domain` — and `domain` must stay pure.
`shared/` currently holds genuinely universal things (`actor`, `constants`, `db`, `errors`,
`ids`, `models`, `retention`). Credential encryption is owned by `personalization`
(AD-16: `personalization` owns `CALENDAR_CONNECTION`), so it belongs in `personalization`.

**Why not `adapters/`?** AD-9's rule is that *SDKs* live in adapters. `cryptography` is not
an SDK for an external service; it is a cipher library, like `hashlib` or `hmac` (both
stdlib, used freely). A `ports.encryption` + `adapters.encryption` pair would be the
"correct" ports-and-adapters shape for an *external service* (Stripe, LLM, email). A cipher
is not that. **No new import-linter contract is needed**, and none is added: adding a
contract that says "only `apps.personalization` imports `cryptography`" would be over-fitting
— but see the note below.

**Actually — one contract IS worth adding**, because the risk is real: a future module
importing `cryptography` and rolling its own key handling would be exactly the kind of
drift the architecture spine exists to prevent. The contract to add:

```
[[tool.importlinter.contracts]]
id = "crypto-library"
name = "AD-18 only apps.personalization imports the cryptography library"
type = "forbidden"
source_modules = ["domain", "apps.ingestion", "apps.identity", "apps.delivery", "apps.catalog", "apps.editorial", "ports", "config", "worker", "shared", "adapters"]
forbidden_modules = ["cryptography"]
allow_indirect_imports = false
```

`apps.personalization` is deliberately **not** in the source list. `allow_indirect_imports`
is `false` so that a module cannot reach `cryptography` *through* `apps.personalization`
either.

**Where does the key come from at runtime?** `config/env.py` reads the environment (§D3) and
`config/settings.py` exposes it as `settings.CALENDAR_CREDENTIAL_KEY`. The app layer reads
`settings` — that is the existing pattern (`config/settings.py` holds the values; `apps`
read them). `apps/personalization/credentials.py` takes the key as an **argument** and
never reads `settings` itself, so it stays testable with an explicit key; the **model field**
is the one place that needs the key, and it reads `settings.CALENDAR_CREDENTIAL_KEY` lazily
(per call, not at import) so that a test can override it with `override_settings`.

Hmm — but D5 says the app must fail fast **at startup**. Those two are compatible: the
**startup** check is a Django system check (`eventpulse.E007`) plus an import-time
validation in `config/settings.py` — if the key is missing, `config/settings.py` raises
`ImproperlyConfigured` while Django is loading settings, which *is* startup. The field's
lazy per-call read is only about testability.

**Decision: `config/env.py` validates the key format at import** (so a malformed key fails
when settings load — startup), and the system check `E007` reports it again as a
`manage.py check` error. `apps/personalization/credentials.py` is a pure function of the
key.

---

### D13 — The service layer

**`apps/personalization/services/calendar_connections.py`** — the only writer of
`CalendarConnection` (AD-16). This item provides the **model-level** operations the later
items need, without the HTTP surface:

- `connect_calendar(*, user_id, provider, url, display_label="", now=None) -> CalendarConnection`
  — validates the URL shape (scheme `https`, a host, no credentials in the URL), encrypts,
  fingerprints, writes the row and its audit row in one transaction (AD-5).
- `disconnect_calendar(*, connection, actor) -> None`
  — sets `status = disconnected`, clears the credential to `NULL`, and writes the audit row
  in one transaction. **Does not delete the row** (D7).
- `purge_connection_events(*, connection) -> int`
  — deletes exactly that connection's imported `PersonalEvent` rows. Called by the
  disconnect flow (or the retention sweep) — D7's step 2.
- `reveal_credential(*, connection) -> ports.calendar.Credential`
  — decrypts and wraps in `Credential`. **The only** function in the codebase that returns
  the plaintext, and it returns it wrapped.

**Why the connect command validates the URL here and not in the API layer:** the API layer
is a different work item (`calendar-connect-api`). If validation lived there, a second
caller (the worker, a management command) would bypass it. The command is the boundary.

**URL validation rules** (the shape, not the SSRF policy):
- The scheme must be `https` after `webcal://`/`webcals://` → `https://` normalisation.
  **The normalisation itself belongs to `ics-calendar-adapter`** (it is the adapter's
  job), so this item validates the *stored* form: the address is stored **as the user
  gave it, normalised only for the fingerprint**. The adapter normalises at fetch time.
  Hmm — that means the stored value and the fetched value can differ, which is fine (the
  adapter normalises before fetching), but it means the *stored* form is what the user
  typed, which is what they will recognise in the UI. **Decision: store the address as
  entered (trimmed); the adapter normalises at fetch time.** The connect command still
  rejects an obviously unusable value (empty, no scheme, a scheme that is not
  `http`/`https`/`webcal`/`webcals`) — that is a shape check, not a normalisation.
- **A URL with embedded credentials (`https://user:pass@host/…`) is refused.** A secret in
  the userinfo component is a second secret in a URL we are about to encrypt and store,
  and the redaction patterns are tuned for the path/query form. Refusing it is simpler and
  safer than trying to redact it everywhere.

**The audit row.** Connecting, disconnecting and reconnecting are security events, and AD-5
requires one audit row per mutation. `write_audit` from
`apps/personalization/services/audit.py` is used, with `action` values
`calendar_connect`, `calendar_disconnect`, `calendar_reconnect`. The `details` carry the
provider and a count — **never the URL, never the fingerprint**.

**The Free-tier cap** (`FREE_TIER_CALENDAR_PROVIDER_CAP = 1`) is enforced **at the connect
step** per FR-50. The enforcement lives in the command, not in the API. The brief says the
cap is enforced at the connect step with "a calm in-app upgrade prompt"; the *prompt* is
the API/frontend's job, the *cap* is the command's. **This item enforces the cap** (it is
a property of the connection set, and the constant is required here by the acceptance
criteria); the prompt is `calendar-connect-api`'s.

Hmm — careful. Is enforcing the cap in scope? The work item's acceptance criteria list the
constant `FREE_TIER_CALENDAR_PROVIDER_CAP = 1` as required, and the brief says "the 1-provider
cap is a named constant enforced at the connect step". The connect command is this item.
**Yes: enforce it here**, and raise a typed `CalendarProviderCapReached` error, which the
API later maps to the calm upgrade message.

---

### D14 — Errors

New typed errors in `shared/errors.py` (the project's error home) or `domain/errors.py`?

`domain/errors.py` is the pure layer; `shared/errors.py` also exists. The calendar errors
are app-level (`apps/personalization`). Let me check where `domain/errors.py` lives and
whether app-specific errors go there. The identity app raised `ValidationError`,
`AuthenticationFailedError`, `InvalidResetTokenError` from `domain.errors`. So the project's
convention is: **domain-level error types live in `domain/errors.py`**, and the apps raise
them. `domain/errors.py` must stay stdlib-only (the `domain-pure` contract), which a
typed error is.

**Decision.** The new errors go in `domain/errors.py`, following the existing convention: each
subclasses `DomainError`, carries a stable `code` slug and a calm `default_message` (no
exclamation marks, no emoji — the file's own docstring states the voice), and the HTTP
mapping happens once in `config/errors.py`.

```python
class CredentialDecryptionError(DomainError):
    """The stored ciphertext could not be decrypted (wrong key, corrupted column, retired key).

    Distinct from "there is no credential": a cleared credential is a deliberate state
    (D7), and a decryption failure is a fault. Collapsing them would make a key problem
    look like a revoked address.
    """
    code = "credential_unreadable"
    default_message = "We couldn't read that calendar connection."


class InvalidCalendarCredentialError(ValidationError):
    """The address failed the shape check (empty, no scheme, an unsupported scheme, or
    embedded credentials in the userinfo component)."""
    code = "invalid_calendar_credential"
    default_message = "That calendar address doesn't look right."


class CalendarProviderCapReached(DomainError):
    """The account already has as many connected calendars as its tier allows."""
    code = "calendar_cap_reached"
    default_message = "You've connected the calendars your plan allows."
```

`InvalidCalendarCredentialError` subclasses `ValidationError` (not `DomainError` directly),
so it inherits the `details` convention the API uses for field errors.

**No `CalendarConnectionNotFoundError`.** A missing row is a `DoesNotExist`; adding a type
for it would be noise.

**The credential key error is not a `DomainError`.** A missing or malformed
`CALENDAR_CREDENTIAL_KEY` is an **operator** fault, not a user fault: it is never mapped to
HTTP, and it must not carry a user-facing message. It raises
`ImproperlyConfigured` (Django's own configuration error, which `manage.py` and the
deploy pipeline already know how to report) — see D5.

---

### D15 — What "fail fast" looks like in a test

**The fail-fast test** must not depend on the environment. It calls
`credentials.load_key("")` / `load_key("not-base64")` / `load_key(base64_of_16_bytes)`
directly and asserts `ImproperlyConfigured` (or a project-typed `CredentialKeyError`) with a
message naming `CALENDAR_CREDENTIAL_KEY`.

The **system check** (`eventpulse.E007`) is tested by calling
`checks.find_missing_credential_key_errors(keys)` with explicit inputs — the same
pure-function-over-explicit-inputs pattern the other checks use, so the check is testable
without touching the process environment.

---

## 4. Files

### Created

| File | Purpose |
|---|---|
| `backend/apps/personalization/credentials.py` | Key loading, the envelope, encrypt/decrypt, the HMAC fingerprint, the typed errors. |
| `backend/apps/personalization/fields.py` | `EncryptedTextField`. |
| `backend/apps/personalization/services/calendar_connections.py` | The connect/disconnect/purge/reveal commands (the only writer). |
| `backend/apps/personalization/migrations/0002_calendarconnection_and_more.py` | The table, the constraints, the `PersonalEvent` changes. |
| `backend/tests/personalization/test_calendar_connection_model.py` | The model tests (ciphertext column, round trip, wrong key, repr, logs, constraints, uniqueness, no cross-schema FK). |
| `backend/tests/personalization/test_calendar_credentials.py` | The key/fail-fast/fingerprint unit tests. |

### Modified

| File | Change |
|---|---|
| `backend/apps/personalization/models.py` | `CalendarConnection`; `PersonalEvent.Source.CALENDAR_IMPORT`; `calendar_connection_id`; `source_uid`; the two constraints. |
| `backend/apps/personalization/admin.py` | The read-only `CalendarConnection` admin, with the credential excluded. |
| `backend/config/env.py` | `calendar_credential_key`. |
| `backend/config/settings.py` | `CALENDAR_CREDENTIAL_KEY`. |
| `backend/config/checks.py` | `eventpulse.E007`: the key check. |
| `backend/domain/errors.py` | The new typed errors. |
| `backend/shared/constants.py` | `CALENDAR_POLL_INTERVAL`, `FREE_TIER_CALENDAR_PROVIDER_CAP`. |
| `backend/pyproject.toml` | `cryptography==46.0.3`; the `crypto-library` import contract. |
| `backend/.env.example`, `backend/.env` | The local key. |
| `backend/tests/architecture/test_import_contracts.py` | The new contract's planted violation. |

---

## 5. Test plan

Every test below must be able to **fail** — the fix reverted in the working tree, the test
re-run, and the failure observed. That is the standard the last two work items held.

### Encryption

| Test | Pins |
|---|---|
| `test_the_raw_column_is_ciphertext` | Reads the column with raw SQL and asserts the URL, the host and the path segment are all absent. |
| `test_the_credential_round_trips` | Save then reload; the value equals the original. |
| `test_a_wrong_key_fails_loudly` | Decrypting with another key raises `CredentialDecryptionError`, not `None` and not a `ValueError`. |
| `test_a_missing_key_is_refused` | `load_key("")` raises, naming the variable. |
| `test_a_short_key_is_refused` | A 16-byte key raises. |
| `test_the_key_is_never_derived_from_secret_key` | Changing `SECRET_KEY` does not change the ciphertext. |
| `test_encrypting_twice_gives_different_ciphertexts` | A fresh nonce each time. |
| `test_the_envelope_carries_the_key_id` | The id in the env var appears in the stored envelope. |

### No leakage

| Test | Pins |
|---|---|
| `test_the_model_repr_holds_no_credential` | `repr(conn)` and `str(conn)`. |
| `test_the_admin_excludes_the_credential` | The admin's `fieldsets`/`list_display`/`readonly_fields` never name it; the rendered change page holds neither the ciphertext nor the URL. |
| `test_the_credential_appears_in_no_log_line` | Save and load with log capture; the serialised output has no URL and no fingerprint. |
| `test_the_credential_is_not_in_the_audit_row` | The audit row's `details` hold no URL and no fingerprint. |
| `test_the_fingerprint_is_not_allowlisted` | The fingerprint is not in `ALLOWED_FIELDS`. |
| `test_dumped_data_holds_no_credential` | `serializers.serialize` yields the ciphertext, not the plaintext. |

### The model

| Test | Pins |
|---|---|
| `test_the_connection_is_in_the_personal_schema` | The table's schema is `personal`. |
| `test_the_connection_holds_no_foreign_key` | `CalendarConnection` has no relation fields at all. |
| `test_the_user_is_held_by_value` | `user_id` is a plain UUID column. |
| `test_the_connection_has_no_cross_schema_relation` | The AD-3 wall check (`eventpulse.E002`) still passes, and the model has no FK. |
| `test_an_imported_event_needs_a_connection` | The check constraint refuses `calendar_import` with no connection. |
| `test_a_user_created_event_needs_no_connection` | The check constraint refuses `user_created` **with** a connection. |
| `test_the_same_uid_cannot_be_imported_twice` | `(connection, uid)` uniqueness. |
| `test_a_user_created_event_may_repeat_a_null_uid` | Many `NULL` `source_uid` rows coexist. |
| `test_a_disconnected_connection_has_no_credential` | The status/credential check constraint. |
| `test_an_active_connection_must_have_a_credential` | The same constraint, the other way. |
| `test_the_retention_category_is_account_identity` | AD-15's category. |

### The commands

| Test | Pins |
|---|---|
| `test_connecting_writes_one_connection` | |
| `test_connecting_the_same_calendar_twice_is_refused` | The fingerprint's uniqueness. |
| `test_connecting_two_calendars_is_refused_by_the_free_cap` | The cap of 1. |
| `test_the_cap_counts_only_active_connections` | A `needs_reconnect` connection still counts. |
| `test_disconnecting_clears_the_credential` | The ciphertext is gone from the row. |
| `test_disconnecting_writes_an_audit_row` | AD-5. |
| `test_disconnecting_purges_exactly_its_own_events` | One connection's events go; another's stay. |
| `test_revealing_returns_a_redacted_credential` | `repr` of the returned `Credential` has no URL. |
| `test_revealing_a_cleared_credential_is_refused` | |

---

## 6. Acceptance criteria → where each is met

| Acceptance criterion | Where |
|---|---|
| The `CalendarConnection` model in `personal` | §D8; `apps/personalization/models.py` |
| The user by value, no FK to `User` | §D8; the wall check |
| `provider` ∈ {google, apple, outlook} | §D8 |
| The **encrypted** credential | §D1–D4, §D11 |
| `status` ∈ {active, needs_reconnect, disconnected} | §D7 |
| Last-polled and next-due timestamps | §D8 |
| Last error kind, never the URL | §D8, §D10.7 |
| An AD-15 retention category | §D8: `ACCOUNT_IDENTITY` |
| Encrypted with an application-level key, separate from `SECRET_KEY` | §D3, §D5 |
| A test reads the raw column and asserts no URL/host/path | §5 |
| A missing key fails fast at startup, never falls back | §D5, §D15 |
| The credential never leaks (repr, admin, serializer, logs) | §D10 |
| `PersonalEvent.Source` gains a calendar-import value | §D8 |
| An imported event references its connection; `(connection, uid)` is unique | §D8 |
| `user_created` events have no connection | §D8 (the check constraint) |
| A check constraint ties source to connection | §D8 |
| AD-3: no FK crosses the wall | §D8; the wall check |
| `CALENDAR_POLL_INTERVAL` and `FREE_TIER_CALENDAR_PROVIDER_CAP` | §D9 |
| Only `personalization` writes these models; `lint-imports` and `check` pass | §D12; the `crypto-library` contract |
| Tests that can fail | §5 |

---

## 7. Open questions carried forward

1. **Key rotation policy.** The *format* supports it (D2, D3). The *policy* — how many keys
   stay alive, what happens to a row whose key is retired — is still open, as the brief says.
   When it is designed, the change is: an env-var list, a key-id lookup, and a background
   re-encryption job. No migration, no stored-format change.
2. **The fingerprint's dependence on the key.** D6's fingerprint is keyed by the application
   key, so a key rotation changes every fingerprint. A rotation migration re-encrypts the
   rows anyway, so the fingerprints are recomputed for free — but the rotation migration
   must remember to do it. Recorded here so the rotation design does not miss it.
3. **Provider account identity.** Not modelled; the MVP connects by pasting an address.
   A future OAuth adapter may need `provider_account_id`. Not now.
4. **`display_label`.** Included because a user connecting two calendars needs to tell them
   apart. It is not in the work item's acceptance criteria; it is additive and small. If the
   reviewer prefers the minimum, it can be dropped without affecting anything else.

---

## 8. Standards referenced

- `docs/ARCHITECTURE-SPINE.md` — AD-3 (the wall), AD-5 (the audit), AD-8 (one home for
  constants), AD-9 (SDKs in adapters), AD-13 (no PII in logs), AD-15 (retention), AD-16
  (write ownership), AD-18 (calendar is a port; credentials are credentials), AD-19 (the
  generated contract).
- `PRD §4.11 FR-50`, `PRD §11.2` — the read-only ICS/webcal connect, the encrypted
  credential, the Free-tier cap, revocation detection.
- `.specs-fire/intents/onboarding-and-account/brief.md` — the intent's constraints,
  OQ-7 (the provisional poll interval), the open "encryption key management" note.
- `account-auth-core-design.md` (D1–D20) — the conventions this item follows: the user
  held by value, the audit row inside the mutation's transaction, the typed errors in
  `domain.errors`, the "no PII in a log line" assertions written against the *serialised*
  output.
- `personalization-models-design.md` (D1–D28) — the model's conventions: `UUIDv7Model`,
  the named constraints, the two-layer append-only enforcement, the trigger/grant pattern
  in the migration.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-020*
