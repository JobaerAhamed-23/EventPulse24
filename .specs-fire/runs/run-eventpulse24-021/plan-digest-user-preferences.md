---
run: run-eventpulse24-021
work_item: digest-user-preferences
intent: pulse-digest-and-trust
mode: confirm
---

# Implementation Plan: The user's home city and the personal-events opt-out

## Approach

Two stored preferences in the `personal` schema, written only by `personalization`
(AD-16): the user's **home city** and whether **personal events** appear in the digest.

**The shape decision: both values are columns on `DigestPreference`.** No new model, no
new table, no new unique constraint, no new ownership entry.

The design doc (D1, D7) argues it: the city is a *third coordinate* of the same
question `DigestPreference` already answers — where and when the digest arrives — and
the opt-out says what goes *into this user's digest*. Both are one row per user, read
together by the composition service, written together by one settings command. A new
table would add an owner, a retention category, a backfill and a second lookup for
information that sits in the same row.

`DigestPreference`'s docstring asked for exactly this reconsideration — "the shape is
reconsidered when a second, genuinely separate preference arrives" — and the answer is
that a city is not *genuinely separate*: it is the same delivery, in another
coordinate.

**Three columns:**

| Column | Type | Meaning |
|---|---|---|
| `city` | `CharField(max_length=64, null=True, blank=True)` | the catalog's spelling of the user's home city; `NULL` = "not known" |
| `city_source` | `CharField(max_length=16, null=True, blank=True)` | how it was arrived at: `geo`, `choice`, `fallback`, `backfill` |
| `include_personal_events` | `BooleanField(default=True)` | `[ASSUMPTION-7]`: personal events are included unless the user opts out |

**Why `city` is nullable (D2).** A required field would invalidate every existing row
— every user who set a delivery time before this item — and would force the backfill
to run *before* the migration could apply. `NULL` is a real, reachable state meaning
"we do not know where this user is", and it is the state the opt-out path produces
(D5).

**Why `city_source` exists at all (D14).** The work item requires the fallback to be
"recorded as a fallback rather than a guess". Without a source column, a user whose
city was inferred cannot be distinguished from a user whose city they chose — and the
digest would show "Brooklyn, NY" for both. `city_source` is what makes the fallback
honest rather than invisible, and it costs one column.

**The coverage rule and the NYC fallback are reused, not reimplemented (D3).**
`list_supported_cities()` and `PREVIEW_FALLBACK_CITY` already exist and are already
tested. This item calls the service and stores the constant's value. Two rules for
"which cities may a user be in" would disagree, and the disagreement would surface as a
digest ranking on a city the preview says is not served.

**The import is legal.** The `models-ingestion` contract protects
`apps.ingestion.models`, not the services — and `personalization` already imports
`apps.ingestion.services.catalog_read` in three places.

## Files to Create

| File | Purpose |
|------|---------|
| `backend/apps/personalization/migrations/0009_digestpreference_city_and_more.py` | The three columns and the `city`/`city_source` agreement check. |
| `backend/apps/personalization/services/digest_preferences.py` | The commands: `set_home_city`, `set_include_personal_events`, the coverage check, and the backfill. |
| `backend/config/management/commands/backfill_digest_cities.py` | The idempotent backfill (D9). |
| `backend/tests/personalization/test_digest_preferences.py` | The commands, the coverage check, the fallback, the audit, the backfill. |
| `backend/tests/personalization/test_digest_preference_model.py` | The new columns, the constraint, the retention category, `__str__` leaking no city. |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/apps/personalization/models.py` | `DigestPreference`'s three columns, the `CitySource` enum, the agreement check, and the docstring rewrite. |
| `backend/apps/personalization/schemas.py` | The city, the source and the flag on `DigestPreferenceIn`/`DigestPreferenceOut`. |
| `backend/apps/personalization/api.py` | The change endpoint accepts the new fields; the read returns them. |
| `backend/apps/personalization/services/onboarding.py` | `set_digest_preference` gains the optional city and flag. |
| `backend/apps/identity/schemas.py` | `SignUpIn` gains an optional `city`. |
| `backend/apps/identity/api.py` | The sign-up endpoint passes the city through. |
| `backend/apps/identity/services/sign_up.py` | The service accepts an optional city and calls `personalization`'s published service. |
| `backend/tests/personalization/factories.py` | The `DigestPreferenceFactory` gains the three fields. |
| `backend/tests/personalization/test_model_structure.py` | `DigestPreference` is already in `MODELS`; no change needed beyond verifying. |

## The command shape

Every command follows `onboarding.py`'s exact pattern:

```
with transaction.atomic(using=PERSONAL):
    _lock_user(user_id)              # the advisory lock
    _write_digest(...)                # the upsert
    write_audit(...)                  # inside the transaction
```

**The upsert** follows `_write_digest`: look the row up, update it if it exists, insert
it if not — under the lock, so two concurrent writers cannot both find no row and both
insert.

**The audit row carries no city (D8, D10).** AD-13's discipline: a city is weak
location data about a real person. The audit row says *that* the city changed; the
value stays out of the log. The `include_personal_events` boolean **is** in the
details — it is not location data, and "did they opt in or out" is exactly what an
audit row should answer.

**The `target_id` is the `DigestPreference`'s id**, matching the existing
`onboarding.digest_preference_set` audit — so the audit table does not become a
per-user index of where people live.

## The backfill (D9)

`config/management/commands/backfill_digest_cities.py`, modelled on
`backfill_event_fit.py`:

- idempotent — it writes the fallback to rows that have no city, and **never
  overwrites a city that is already set**;
- `--dry-run` reports the count and writes nothing;
- it holds **no model query of its own** — `apps.personalization.models` is importable
  only from `apps.personalization` (AD-2), so the query lives in the service and the
  command calls it;
- it runs on the `PERSONAL` alias.

It writes the **fallback**, because it has no better information: there is no geo
header in a management command, and the accounts it fills predate this item.

## Tests

| Test File | Coverage |
|-----------|----------|
| `test_digest_preferences.py` | A covered city is stored with the catalog's spelling; an uncovered city stores the fallback; the opt-out defaults to included; each command writes its audit entry; **the audit details carry no city**; the backfill is idempotent and never overwrites; the sign-up path stores the carried city; an opted-out visitor gets no city. |
| `test_digest_preference_model.py` | The three columns exist; the `city`/`city_source` agreement check; the retention category is unchanged; **`__str__` leaks no city**; the model's `include_personal_events` default is `True`. |

**The two tests that can pass for the wrong reason, and how they are written.**

1. **"The audit details carry no city."** A test that asserts `"city" not in
   str(audit.details)` would pass if the details were *empty* — which would mean the
   audit row says nothing at all. So the test asserts **both**: that the details carry
   the flag, **and** that the city is absent. An empty details dict fails the first
   assertion, so it cannot pass for the wrong reason.

2. **"The fallback is recorded as a fallback."** A test that asserts
   `preference.city == PREVIEW_FALLBACK_CITY` would pass if *every* city were the
   fallback — including a covered one the user actually chose. So the test asserts
   **both**: that an uncovered city stores the fallback **and** that `city_source` is
   `fallback`, **and** that a covered city stores *itself* with `city_source` `choice`.

## Technical Details

**The city is not encrypted (D10).** This is a deliberate departure from
`ACCOUNT_IDENTITY`, and the reason is worth stating: the email address is encrypted
because it is a **credential** — it authenticates. A city is not a credential and it
authenticates nothing. Encrypting it would make it unqueryable and unindexable for no
gain. It is in the `personal` schema, readable only by `ep_personal`, and purged with
the account.

**The retention category stays `PREFERENCE_SIGNALS` (D11).** A city is an *input* and
may be refreshed — the contrast with `DigestComposition`, which is an *output* and must
outlive its day, and whose 12-month window would have broken AD-10's "most recent
composition" promise.

**The API change is additive and backward-compatible (D12).** The city, the source and
the flag are optional in the request body: an existing client that sends only
`delivery_time` and `timezone` keeps working, and a command that omits them **does not
clear** the stored values.

**This endpoint cannot clear the city — a shape limitation, argued in D12.** A `null`
city and an omitted city are the same value in Pydantic, so "leave it alone" and
"clear it" cannot be told apart. A shape that cannot say which one it means must not
guess: guessing "clear" would wipe the city of every client that sends `null`. So
`null` means **leave it alone**, and clearing is reached through the service
(`set_home_city(city=None)`), not through this body.

**The sign-up path is `identity` → `personalization` (D13).** Sign-up lives in
`apps/identity`, and `identity` already imports `personalization`'s published service
(`apps/identity/api.py:93` imports `get_onboarding_state`). The direction is legal and
established, so `sign_up` calls the new `personalization` service to store the carried
city. `personalization` never imports `identity`'s models.

**The transaction boundaries (D15).** The digest-preference endpoint writes the
delivery time and the city in **one** transaction — a half-applied decision is worse
than a failed one. The sign-up path writes the city **outside** the account's
transaction — an account that exists without a city is a state the digest handles; one
that exists without its audit row is a hole. The duplicate sign-up returns before the
city is written, so a duplicate can never change the real holder's city.

**The frontend half is out of scope (D4).** The preview choice lives in a **session
cookie** read in the browser only — deliberately, because a server-side choice would
make `/preview` vary per visitor and break AD-12's cacheability. So the carry is a
**request field**: the frontend reads the cookie at sign-up and sends the city in the
sign-up body. This item owns the backend half and states the contract the frontend
must satisfy.

**No clock read in the command.** The commands take `now` as an argument, matching
`set_digest_preference`.

---

*Plan follows the approved design doc
(`.specs-fire/intents/pulse-digest-and-trust/work-items/digest-user-preferences-design.md`,
D1–D14).*
