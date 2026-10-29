---
id: calendar-connection-model
title: Calendar Connection Model & Credential Encryption
intent: onboarding-and-account
complexity: high
mode: validate
status: completed
depends_on: []
created: 2026-10-29
run_id: run-eventpulse24-020
completed_at: 2026-10-29T09:04:48.182Z
---

# Work Item: Calendar Connection Model & Credential Encryption

## Description

Adds the `CALENDAR_CONNECTION` entity (AD-18) and the encryption that makes its credential safe to store.

AD-18's rules:

- "Each connected calendar is one `CALENDAR_CONNECTION` row (`personal`, owned by `personalization`) holding the encrypted credential."
- "Every imported `PERSONAL_EVENT` references its connection, so a disconnect purges exactly that connection's events."
- "Every provider credential … is encrypted at rest with the application-level key, never logged, and revocable by the user."

The secret ICS address is the credential. Google itself classifies it as a secret and offers a reset for it. The data model has to treat it as a credential from the first migration.

This item is **models, migrations, the encrypted field and constants**. Fetching is `ics-calendar-adapter`, and sync is `calendar-sync-and-polling`.

## Acceptance Criteria

- [ ] **`CalendarConnection` model** in `personal`:
  - the user by value (no FK to `User`);
  - `provider` (`google` | `apple` | `outlook`);
  - the **encrypted** credential;
  - `status` (`active` | `needs_reconnect` | `disconnected`, or the set the design doc settles on);
  - last-polled and next-due timestamps;
  - last error kind, never the URL;
  - an AD-15 retention category.
- [ ] **The credential is encrypted at rest** with an application-level key that is **separate** from `SECRET_KEY` and read from the environment or secret store. A test reads the raw column with SQL and asserts it contains neither the URL nor any recognisable fragment of it, such as the host or path.
- [ ] A missing key causes the app to **fail fast at startup** with a clear message whenever a component that needs the key is configured. It never falls back to plaintext or to `SECRET_KEY`.
- [ ] **The credential never leaks.** In code, the decrypted value is only ever a `ports.calendar.Credential`, which already redacts `repr` and `str`. Tests assert that the model's `repr`, its admin representation (if registered), any serializer, and the logger output from save and load never contain the URL.
- [ ] **`PersonalEvent.Source` gains a calendar-import value.** The model comment already anticipates this: "AD-18's calendar import will add its own value when FR-50 lands". An imported `PersonalEvent` references its connection, and `(connection, uid)` is unique so re-syncs upsert rather than duplicate. `user_created` events have no connection.
- [ ] A **check constraint** ties source to connection: imported rows always have a connection and user-created rows never do.
- [ ] **AD-3:** no FK crosses the schema wall. The connection-to-personal-event relationship stays inside `personal`.
- [ ] Named constants in `shared/constants.py`: `CALENDAR_POLL_INTERVAL = timedelta(hours=1)` (provisional, OQ-7, with a comment saying so) and `FREE_TIER_CALENDAR_PROVIDER_CAP = 1`.
- [ ] Only `personalization` writes these models, and `make lint-imports` and `manage.py check` pass, including the retention check.
- [ ] Tests that can fail cover: the raw column is ciphertext; round-trip decrypt; a wrong key fails loudly; `repr` and log redaction; the source/connection check constraint; `(connection, uid)` uniqueness; and no cross-schema FK.

## Technical Notes

**Design doc required (validate).** It must settle at least:

- **The cipher and library.** `cryptography`'s Fernet (AES-128-CBC + HMAC) versus AES-GCM. State what each gives you.
- **Key rotation.** It is not built in this intent (brief "Still open"), but choose a format that can rotate later, for example a key-id prefix or `MultiFernet`, so the stored format doesn't have to change.
- **Field implementation.** A custom model field, or explicit encrypt and decrypt in the service layer. Consider which one makes an accidental plaintext read harder.
- **Deduplication.** Whether to store a keyed hash (HMAC) of the normalised URL so the same calendar can't be connected twice without decrypting every row.
- **Status values and transitions,** especially what `disconnected` means if disconnect deletes the row.

The `ports.calendar.Credential` class already exists. Reuse it rather than inventing a second secret wrapper.

The logger adapter's allowlist (AD-13) is the enforcement point for "never logged". Confirm the URL can't reach a sink even through an exception message, because a URL inside an `httpx` exception string is the classic leak.

## Dependencies

(none)
