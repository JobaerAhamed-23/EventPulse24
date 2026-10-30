---
id: onboarding-and-account
title: Onboarding, Account & Calendar Connect
status: completed
created: 2026-10-29
completed_at: 2026-10-30T11:16:02.900Z
---

# Intent: Onboarding, Account & Calendar Connect

## Goal

Take a visitor from an anonymous **Pulse Preview**, through sign-up and a skippable 3-step onboarding, to a signed-in home — and make the session that results the real one, replacing the `current_user` seam in `apps/personalization/auth.py`.

It delivers FR-1 (30-second onboarding flow), FR-2 (Pulse Preview), FR-3 and FR-50 (read-only calendar connect via ICS/webcal, Amendment A-9), FR-4 (authenticated user state), and the session-free **Event Fit** half of AD-10 that Pulse Preview needs.

## Users

- **The anonymous visitor**, who lands on the home page and sees three events in their city before being asked for anything (UJ-3, step 1).
- **The new user**, who signs up and is on a signed-in home within three skippable steps (UJ-3, steps 2–6).
- **The returning user**, who stays signed in for 7 days and can connect, reconnect and disconnect Google, Apple or Outlook calendars (UJ-2, FR-50).

## Problem

Three intents are done, but nobody can become a user:

- `apps/identity/models.py` holds only `User`, and `apps/identity/api.py` is an empty router. There is no sign-up, sign-in, sign-out or password reset.
- `apps/personalization/auth.py` is a deliberate one-function seam. Its own docstring says the onboarding intent replaces it. The personal-event and saved-event endpoints built in `personal-events-and-saved-catalog` answer 401 to everyone, because nothing can create a session.
- `adapters/calendar/` has only a fake. There is no `CALENDAR_CONNECTION`, so UJ-2 (an imported calendar feeding conflict detection) cannot happen.
- Catalog events have no categories, no tags and no Event Fit. AD-12 forbids the public home from depending on a session, and AD-10 forbids it from borrowing a personal explanation. As a result, Pulse Preview has nothing it is allowed to show.

## Success Criteria

- **Accounts (FR-4, AD-18):** a user signs up, signs in and signs out with email and password.
  - Password reset uses **single-use, short-lived** tokens.
  - Sign-up, sign-in and reset responses are **enumeration-safe**: the response for an unknown email is indistinguishable from the one for a known email.
  - The session persists for **7 days**, so a user reopening within 7 days is not asked to sign in again.
  - Auth is resolved at the API edge, and services receive an explicit actor, never a `request`.
  - `personalization/auth.py`'s `current_user` is replaced **in one place**. Every existing personal endpoint keeps working with the real session.
- **Onboarding (FR-1):** at most **3 user-visible steps**, and every one can be skipped:
  1. optional calendar connect;
  2. optional interest chips (up to 3 picks);
  3. digest delivery time and timezone.
  
  A user who skips everything still finishes onboarding. A user who leaves mid-step is resumed at **the same step** on return within 7 days. Onboarding ends on a calm signed-in **placeholder home** at `/` (the Pulse Digest's route) that links to personal and saved events. The Pulse Digest intent replaces that home.
- **Interests:** the 10 chips from `onboarding-step2-desktop.html` are **one fixed constant in `shared/`**: Tech & meetups, Sports & fitness, Arts & culture, Family & kids, Community & volunteering, Outdoors & nature, Classes & workshops, Markets & fairs, Talks & lectures, Government & civic. Picks are stored as `INTEREST` rows owned by `personalization`. Nothing reads them for ranking in this intent.
- **Calendar connect (FR-3, FR-50, AD-18):**
  - **Providers:** Google, Apple and Outlook are presented as equal-weight options, each with inline, provider-specific guidance on where to find its ICS/webcal address.
  - **The credential:** the address input is masked. The secret address is **encrypted at rest with a separate application-level key**, **never logged** (enforced by the logger adapter's allowlist, AD-13), and revocable by disconnecting.
  - **One row per calendar:** each connected calendar is one `CALENDAR_CONNECTION` row (`personal`, owned by `personalization`).
  - **One adapter:** all calendar ingestion sits behind the calendar port, with **one ICS/webcal adapter used uniformly** for all three providers. It reuses the ICS parser built during ingestion.
  - **Imported events:** every imported `PERSONAL_EVENT` references its connection and goes through the existing FR-58 conflict detection.
  - **Polling:** connections are polled on a **provisional 1-hour interval**. The interval is one named constant, and the poll is scheduled from the existing single 60s tick.
  - **Revoked addresses:** an HTTP 401, 403, 404 or 410 on poll marks the connection as needing reconnection, and the user is prompted to reconnect. It is never denied silently.
  - **Disconnect:** disconnecting purges **exactly that connection's** imported events, well within FR-50's 24-hour bound.
  - **Free cap:** every user is Free in this intent. The **1-provider cap** is a named constant enforced at the connect step, with a calm in-app upgrade message and no modal.
- **Event Fit (AD-10):** `ingestion` computes a **deterministic, non-personalized** Event Fit per `(event, city)` when an event is ingested or refreshed, and stores it on the catalog side.
  - It has a 1–5 score built from **inputs that already exist on an Event**: start-time proximity and extraction confidence. Its generic tags are time and place tags such as "Tonight", "This weekend" and "In <city>".
  - Catalog events have **no price field** and FR-16 source reliability is **not built yet**, so "Free" tags and reliability weighting wait for those to exist. They are added to Event Fit's rule set then, not faked now.
  - It uses **no LLM**, is never computed at render time, and is never used to fill a missing Relevance Pulse on an authenticated surface.
- **Pulse Preview (FR-2, AD-12):** `/preview` shows **3 Pulse Cards** in the visitor's inferred city. Following the `EXPERIENCE.md` route map, `/` is the signed-in home, and an anonymous visitor to `/` is sent to `/preview`.
  - **No session:** it renders without a session, never reads `personal`, and is cacheable.
  - **City:** the city comes from the hosting edge's geo header (for example `x-vercel-ip-city`) through a small port with a local and CI fake. The city must be one the catalog covers; otherwise it falls back to **NYC**.
  - **Consent banner:** "Showing events near [city]. Use a different city? [Change] [Use this] [Don't use my location]". The choice persists in a cookie, and "Don't use my location" suppresses geo-IP.
  - **Soft wall:** "Save to Pulse" asks for sign-up at the 3rd card.
- **Proof:** the rules are pinned by tests that **can fail**:
  - enumeration-safe responses;
  - reset-token reuse and expiry;
  - the 7-day session;
  - the personal endpoints working with a real session and refusing an anonymous one;
  - the ≤3-step and resume-at-step rules;
  - the credential being stored encrypted, appearing in no log line, and never being returned by the API;
  - revoked-address detection for each of 401, 403, 404 and 410;
  - disconnect purging only its own events;
  - the Free cap;
  - Event Fit being deterministic and persisted;
  - Pulse Preview working without a session and with the NYC fallback.
  
  CI stays green with the coverage gates and the `import-linter` contracts.

## Constraints

- Builds on the three completed intents:
  - `project-scaffold`: the two-schema router (AD-3), `shared/` foundations, the ports and fakes (including `adapters/calendar/fake.py` and `adapters/email/`), the 60s tick, and the `import-linter` contracts.
  - `event-catalog-ingestion`: `ingestion` is the sole writer of `catalog` (AD-4, AD-16), `apps/ingestion/parsers/ics.py` already exists, and the catalog is read through `apps/ingestion/services/catalog_read.py`.
  - `personal-events-and-saved-catalog`: `PERSONAL_EVENT`, `SAVED_EVENT`, `CONFLICT_PAIR`, the conflict function in `domain/conflict.py`, and the `current_user` seam this intent replaces.
- **Ownership (AD-16):**
  - `identity` owns `USER` and the auth flows.
  - `personalization` owns `INTEREST`, `CALENDAR_CONNECTION`, onboarding progress and imported `PERSONAL_EVENT`s.
  - `ingestion` owns Event Fit, because it lives on the catalog side.
  - Cross-module writes go through the owner's published interface.
- **The wall (AD-3, AD-10, AD-12):** the public preview never reads `personal`, never needs a session, and never substitutes Event Fit for a Relevance Pulse. No `personal` model FKs across the wall.
- **Credentials (AD-13, AD-18):** the secret ICS address is a credential and is never treated as a config string. Email addresses and personal event content never reach a log sink.
- **Email (AD-20):** password-reset mail is **transactional** and carries an explicit stream through the email port.
- **API contract (AD-19):** the new endpoints reach the frontend through the generated contract and are never hand-written.
- **Retention (AD-15):** every new model declares a retention category.
- **`beat_schedule` stays exactly one 60s tick** (`backend/tests/worker/test_tick.py`). Calendar polling is due-time work dispatched from that tick, and no request does long work (AD-11).
- **No LLM call anywhere in this intent.**
- **The UX is implemented, not redesigned.** The binding mockups are `signup-desktop.html`, `signin-desktop.html`, `onboarding-step1-desktop.html`, `onboarding-step2-desktop.html`, `onboarding-step3-desktop.html`, `onboarding-skip-all-state-desktop.html` and `pulse-preview-desktop.html`, along with `EXPERIENCE.md` and `DESIGN.md`. There is no component library ("UI system: None" is binding).
- The frontend calls `/api/*` on its own origin through `frontend/proxy.ts`, so the session cookie stays first-party.
- Binding sources:
  - `_bmad-output/planning-artifacts/architecture/architecture-EventPulse24-2026-09-04/ARCHITECTURE-SPINE.md` (AD-3, AD-5, AD-10, AD-11, AD-12, AD-13, AD-15, AD-16, AD-18, AD-19, AD-20)
  - `_bmad-output/planning-artifacts/prds/prd-EventPulse24-2026-08-19/prd.md` §2.3 UJ-2 and UJ-3, §4.1, §4.11 FR-50, §10.2, §11.2
  - `_bmad-output/planning-artifacts/ux-designs/ux-EventPulse24-2026-08-23/`
  - `.specs-fire/standards/`

## Notes

**Out of scope:**
- **OIDC social sign-in** ("Continue with Google / Apple / Microsoft"). The sign-up and sign-in layouts leave room for these buttons, but nothing is wired to them. A later intent can add them, identity-only, under AD-18.
- **`SUBSCRIPTION` and the Pro tier (FR-48–FR-52).** Everyone is Free, and the cap is a constant.
- **The real Pulse Digest (FR-5–FR-8, FR-19).** The placeholder home stands in for it. FR-1's "first authenticated Pulse Digest within 30 seconds, from a pre-computed cached composition" moves to the Pulse Digest intent.
- **Using interests for ranking**, and **event categories** generally. Event Fit tags are generic and not tied to the interest taxonomy.
- **Recurring-event RRULE expansion** beyond listing simple instances (FR-31, Phase 2). Calendar write-back and two-way sync.
- **Settings → Privacy.** Only the persisted location choice is in scope; the settings surface is a later intent.
- **SEO city pages and public event pages (FR-26–FR-28).** Event Fit is built so they can reuse it, but the pages themselves are out of scope.

**Still open:**
- **OQ-7 (Google ICS cache freshness).** The 1-hour interval is provisional. A live poll test against a real Google secret address is needed before it is fixed, and the brief records that rather than inventing a number.
- **PRD amendment needed (OQ-6):** `CalendarConnection` and `EventFit` must be added to PRD §3 Glossary, alongside the `SavedEvent`, `ConflictPair` and `ExtractedRecord` amendment still pending from earlier intents.
- **Encryption key management.** The separate application-level key comes from the platform secret store. Key rotation is not designed in this intent.
- **The geo header depends on the host.** The port keeps that dependency out of the code (AD-1). Locally and in CI the fake supplies the city.

**Decisions taken during capture (2026-10-29):**

1. **All four parts ship in this intent:** accounts and sessions, onboarding, calendar connect, and Pulse Preview.
2. **Email and password only.** OIDC is deferred.
3. **A calm placeholder home** is where users land after onboarding or sign-in until the Pulse Digest exists.
4. **The Free cap of 1 provider is enforced now**, as a constant. There is no `SUBSCRIPTION` entity yet.
5. **Event Fit uses deterministic rules**, with no LLM and no categories.
6. **Geo-IP comes from the hosting edge's header** through a port, with NYC as the fallback.
7. **Interest picks are stored only.** The Pulse Digest intent is the first to read them.
8. **The ICS poll interval is provisionally 1 hour**, held in one named constant, pending OQ-7.
