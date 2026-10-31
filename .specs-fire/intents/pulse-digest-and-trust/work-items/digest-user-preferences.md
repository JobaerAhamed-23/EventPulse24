---
id: digest-user-preferences
title: The user's home city and the personal-events opt-out
intent: pulse-digest-and-trust
complexity: medium
mode: confirm
status: completed
depends_on: []
created: 2026-10-30
---

# Work Item: The user's home city and the personal-events opt-out

## Description

Fills two gaps the composition service cannot run without, both of which are small to build and decision-heavy to get right.

**The home city.** A signed-in user has no persisted city anywhere in this codebase. `adapters/geo/` reads a city from the hosting edge's header for the anonymous preview, and `frontend/lib/preview-choice.ts` persists an anonymous visitor's choice in a cookie — but neither survives sign-up, and no model holds a city for an account. The digest cannot rank "nearby" without one. FR-5 calls it the user's "beachhead"; UJ-1 shows "Brooklyn, NY" in the digest header; FR-8's empty state reads "No qualifying events in **{city}**."

**The personal-events opt-out.** FR-19's third testable consequence is "a user can opt out of personal events appearing in the Pulse Digest." PRD `[ASSUMPTION-7]` makes it **opt-out, not opt-in** — personal events appear by default — and flags it as Open Question #13, still open, owner Product. Built as opt-out, with the assumption recorded.

## Acceptance Criteria

- [ ] **A home city is persisted for a signed-in user**, owned by `personalization`, by value, with an AD-15 retention category. The design decides whether it joins `DigestPreference` (which already holds the delivery time and timezone, and is already the "where and when the digest should arrive" model) or stands alone; `DigestPreference`'s own docstring invites exactly this question, saying the shape "is reconsidered when a second, genuinely separate preference arrives."
- [ ] **The city must be one the catalog covers**, with a **fallback to NYC** — the same rule and the same constant `pulse-preview-api-and-geo` already established for the anonymous preview. A city the catalog does not cover is not stored as if it were valid.
- [ ] **It is set without asking a new question.** Onboarding is capped at 3 steps by FR-1 and every step is skippable; this item adds no fourth step and no new field to an existing one. The city comes from the geo header at sign-up or from the anonymous visitor's persisted preview choice, carried across the sign-up boundary. The design states which, and what happens when neither is available (the NYC fallback, recorded as a fallback rather than a guess).
- [ ] **A user can change it**, through a named command with an audit entry (AD-5), so the FR-7 "user in a new timezone" case and a plain move have a path. The settings *surface* is out of scope; the command is not.
- [ ] **Existing users are backfilled** by an idempotent management command, since accounts created by the onboarding intent have no city at all.
- [ ] **The personal-events opt-out is a stored preference, defaulting to included** (`[ASSUMPTION-7]`). A command sets it, with an audit entry. The composition service reads it; this item only owns the storage and the command.
- [ ] Both values reach the frontend through the **generated contract** (AD-19), never hand-written, if they are exposed at all in this intent.
- [ ] **Neither value is ever logged.** A city is weak location data about a real person and belongs under AD-13's allowlist discipline alongside the email address, not in a log line.
- [ ] Tests cover: the catalog-coverage check accepting a covered city and falling back for an uncovered one; the backfill being idempotent; the opt-out defaulting to included; the change command writing its audit entry; and a user with no geo signal at sign-up landing on the fallback rather than on `None`.

## Technical Notes

**Do not reach for the geo header at composition time.** Composition runs in the worker (AD-11), where there is no request and therefore no headers — `GeoPort.resolve_city` takes "a bag of headers, not a request", by deliberate design. The city must already be stored by the time the job runs. This is the whole reason the item exists separately from composition.

**The anonymous→authenticated carry.** `frontend/lib/preview-choice.ts` already persists the visitor's city choice (including "don't use my location") in a cookie. A visitor who corrected their city on `/preview` and then signed up has told us their city more explicitly than any header will; losing that at the sign-up boundary and re-inferring from a header would be a small but real insult. Check what that cookie holds before designing the carry.

The "don't use my location" choice deserves a decision rather than a default: a user who suppressed geo-IP anonymously has not consented to a stored city. The design should say whether that choice carries, and if it does, what the digest ranks on — the NYC fallback is a legitimate answer, and so is asking once at first digest, but silently storing an inferred city for someone who declined inference is not.

## Dependencies

(none)
