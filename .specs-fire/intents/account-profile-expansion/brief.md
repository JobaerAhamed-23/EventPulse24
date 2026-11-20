---
id: account-profile-expansion
title: A Profile Worth Having — a Face, an Address You Can Move, and a Place
status: completed
created: 2026-11-19
completed_at: 2026-11-20T06:43:49.742Z
---

# Intent: A Profile Worth Having — a Face, an Address You Can Move, and a Place

## Goal

Grow `/settings/profile` from **one field** into the account's real profile surface:
the name it already has, a **picture**, an **email the user can actually change**, and
**where they are** — the last one surfaced from the city the product already stores,
not stored a second time.

## Users

Every signed-in user. Today the only thing an account can change about itself is its
name, and the account sheet introduced "Edit your name" as the one account action there
is. A person who wants a face on their account, or who has changed address, has nowhere
to go.

## Problem

The profile surface is one field, and that was a deliberate, recorded decision — the
previous intent's docstrings say so in as many words: *"the email is the login and the
key, and it is not changeable from here."* **This intent revisits that decision on
purpose**, and the design has to answer the credential questions that decision was
avoiding rather than pretend they are not there.

What the code actually holds today, probed rather than assumed:

- **The account has no face.** `User` (`backend/apps/identity/models.py:23`) carries
  `email` and `name`, and nothing else a person would call a profile. `ProfileName`
  (`frontend/components/settings/profile-name.tsx`) *is* the profile surface.
- **There is no object storage anywhere.** No `MEDIA_ROOT`, no `STORAGES`, no `boto3`,
  no S3 and no MinIO in `backend/config/` or `docker-compose.yml`. A profile picture is
  **infrastructure before it is a field**, and that is the larger half of the work.
- **The email is a credential, not an attribute.** It is `USERNAME_FIELD`, it is unique
  case-insensitively through the named `user_email_uq` constraint, and `User.save()`
  normalises it as a backstop so even a write that bypasses the command layer cannot
  slip a mixed-case duplicate past that constraint. Moving it moves the login.
- **The place already exists, and must not be stored twice.** `DigestPreference.city`
  and `city_source` (`backend/apps/personalization/models.py`) hold where the user is
  and *how that was arrived at*; `components/settings/home-city.tsx` and
  `digest-timezone.tsx` already edit them. A second "address" field on the profile
  would be a second answer to a question the product has already answered — and the
  `city_source` distinction (chosen vs inferred) is exactly what makes the digest's
  fallback honest. The profile screen **surfaces** this; it does not fork it.

**What makes the email change cheaper than it looks.** `PasswordResetToken`
(`backend/apps/identity/models.py:92`) is already the pattern the pending-email flow
needs, and its docstring records why each property is there: the digest at rest with a
per-row salt, single-use via `used_at`, short-lived via `expires_at`, revocable via
`revoked_at`, and the user held by value (OQ-8) rather than by relation. Django's own
`PasswordResetTokenGenerator` was probed and rejected for this project because it is
replayable and cannot be revoked. **The email-change token follows that row's shape
rather than inventing a second token story** — and the same reasoning rules out
reaching for the framework's generator again.

Transactional mail is likewise already built: `services/emails.py` renders messages and
picks a `Stream`, so the confirmation mail is a new renderer and a new stream, not new
machinery.

## Success Criteria

- A user can upload a profile picture on `/settings/profile`, and it appears in the
  **sidenav, the bottom bar and the account sheet** — the three places the display name
  already appears — and survives a reload
- **MinIO runs in `docker-compose`**, and the backend reaches it through the **same S3
  API** a production bucket will answer, so no storage rewrite is owed later
- A user with no picture set still gets the existing name treatment; **the fallback must
  not blank anything**, exactly as the name's email-derived fallback does not
- An upload that is not an image, or is larger than the declared cap, is **refused with
  a message written for the person who typed it** — and nothing is stored
- Requesting an email change sends a confirmation link **to the new address**, and the
  login address **does not move** until that link is used
- An **expired, revoked, already-used or unknown** email-change token is refused, and
  the **old address still logs in** afterwards
- The **old address is notified** that a change was requested — a credential that moves
  silently is an account takeover
- An email change to an address another account already holds is refused **without
  disclosing that the other account exists**
- The home city and the timezone are **reachable from the profile screen**, with **no
  second city field** and **no new location column** anywhere
- Every write is a **named command** in `backend/apps/identity/services/` (AD-5), audited
  in the same transaction, with **no email, no name and no image key in the audit
  details** (AD-13)
- The audit row for each change exists and its details carry the action and the target
  id only
- `PUT`/`POST` on every new endpoint is refused **403 without a CSRF token** and **401
  for an anonymous caller**
- The generated contract is **regenerated and committed** — `make client` output is in
  the tree and `backend/tests/api/test_contract.py` is green (AD-19)
- Every new model declares a `retention_category` (AD-15), and the picture is included
  in the user's data export and deleted with the account

## Constraints

- **AD-5** — every write is a named command in `apps/identity/services/`, never a write
  in the API layer. `tests/architecture/test_no_direct_writes.py` enforces that the API
  layer touches no ORM.
- **AD-2 / AD-16** — the picture and the pending-email row live on `identity`, the app
  that owns the account. `personalization` is **read, not reached into**: the city stays
  where it is and is surfaced through its existing endpoint.
- **AD-3** — new rows live in the `personal` schema with the rest of `User`, and every
  command writes inside `transaction.atomic(using=PERSONAL)`.
- **AD-13** — the email, the name and the image object key are PII. Audit `details`
  carries the action and the target id; the logger allowlist is not widened.
- **AD-15** — every new model declares its retention category, and the picture is
  covered by account deletion and by the FR-52 export.
- **AD-18** — credentials are encrypted at rest. The email-change token is stored as a
  **digest with a per-row salt**, never in the clear.
- **AD-19** — the OpenAPI schema is the contract; the client is regenerated and
  committed in the same pass.
- **Constitution** — this touches auth and credentials, so it is a **security-sensitive
  change requiring additional review**. Migrations are forward-only, one per PR.
- **Storage choice is settled**: MinIO in `docker-compose`, chosen over a local
  `MEDIA_ROOT` volume specifically so the storage API does not have to be replaced
  before a real deploy.
- **Out of scope, explicitly**: bio, phone, and any other new free-text profile column.
- **Branch**: `feature/account-profile-expansion`, one branch for the whole intent
  (the standing exception to the constitution's `PROD-NNNN-<slug>` rule).
- **Node 24** for the frontend (`.nvmrc`); a login shell may default to Node 20, where
  every Vitest file dies in undici.

## Notes

**Two questions are deliberately left open for the design checkpoint rather than
guessed at here:**

1. **Are avatar URLs public or signed?** A public object key is simple, cacheable by the
   CDN and survives a server round trip — but it is a stable, guessable URL to a
   picture of a real person. A signed, short-lived URL is private but has to be minted
   on every render, in a shell that is server-rendered on every page.
2. **What happens to other live sessions when the login address moves?** The password
   reset flow already ends an account's other sessions, and a changed login is at least
   as significant an event. Whether the email change follows it is a decision with a
   real cost to the user, and it belongs in the design doc with its rationale recorded.

**A third, smaller one:** the name saves on change with no Save button, and the other
settings islands do the same. **A picture upload cannot follow that pattern** — there is
no "changed" moment to save on, and an email change must not fire on a keystroke. The
screen will therefore carry controls that behave differently from its neighbours, and
the design should say so plainly rather than let it look like an oversight.
