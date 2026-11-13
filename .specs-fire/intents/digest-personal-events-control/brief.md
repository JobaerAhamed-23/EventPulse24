---
id: digest-personal-events-control
title: The Control That Was Deferred — Personal Events in the Pulse Digest
status: completed
created: 2026-11-13
completed_at: 2026-11-13T02:39:46.368Z
---

# Intent: The Control That Was Deferred — Personal Events in the Pulse Digest

## Goal

Give the user the switch PRD FR-19 has required since day one: **"A user can opt out of
personal events appearing in the Pulse Digest."** The backend half of that switch is built,
tested, and correct. The frontend half — the one screen a person would actually touch —
was deferred on purpose and has never been built.

This intent builds that screen, and nothing else.

## Users

- **A user whose digest mixes their own events with public ones.** Slot 1 is "must-know"
  and it is filled by a personal event within the next 48 hours (FR-5, FR-19). For a user
  with a dinner reservation, a flight, or a birthday, that is correct and wanted. For a
  user who finds their own calendar items crowding out the public discovery they came for,
  it is the opposite — and today there is **no way to turn it off**. The field exists in the
  database and is honoured by the composition service; no interface ever writes it.
- **A user who has already asked us to fix this.** FR-19's opt-out is a *testable
  consequence* in the PRD (`prd.md:605`), and the delivery plan in `prd.md:320` tracks
  `slot_1_save_rate` per slot. A user who opts out removes personal events from Slot 1
  and the metric changes — but the opt-out cannot be exercised because no surface sets it.
- **Every reader of the FR-19 row in the traceability matrix.** The matrix reports FR-19
  as covered by design and shipped by code. Both are true, and between them they leave a
  hole: the requirement is met by machinery and unmet by experience.

## Problem

### 1. The backend is complete; the surface is absent

Verified against the code at capture (2026-11-13), not assumed:

| Artifact | State |
|---|---|
| `DigestPreference.include_personal_events` — `models.py:658` (`BooleanField(default=True)`) | **built** |
| Migration `0009_digestpreference_city_…:34` | **built** |
| `set_include_personal_events()` command — `services/digest_preferences.py:259-285` | **built** |
| `PUT /api/personal/onboarding/digest-preference` accepts it — `api.py:656`, `schemas.py:655` | **built** |
| `OnboardingStateOut.digest.include_personal_events` read — `schemas.py:670`, `:1108` | **built** |
| Composition honours it — `digest_composition.py:628` reads it, `:489` gates Slot 1, `:681` suppresses the count | **built** |
| Backend tests — `test_digest_preferences.py`, `test_onboarding_api.py`, `test_digest_composition.py` | **built** |
| `frontend/` — any read or write of `include_personal_events` outside the generated client | **does not exist** |
| A settings control for it | **does not exist** |
| An onboarding control for it | **does not exist** |

A grep of `frontend/` for `include_personal_events` returns exactly five hits: three inside
the generated `lib/api/schema.ts` (the contract, not a control), one description string
quoted from the API, and one line in an onboarding **test fixture**
(`onboarding-flow.test.tsx:53`) asserting a value the real flow never sends. The real
onboarding PUT at `onboarding-flow.tsx:148-150` sends `delivery_time` and `timezone` only.
The fixture passes because the API defaults the field to `True` and the assertion is about
the response echo — so the test proves the default, not the control.

### 2. This was a deliberate deferral, not an oversight

`digest-user-preferences-design.md` (the design doc for the work item that built the
command) says so in its own words, under "What this item does not decide":

> **The settings surface.** The command exists; the screen that calls it is out of scope
> (the work item says so explicitly).

The deferral was correct at the time — the item was about the *backend contract*, and
building a screen for one boolean in the same pass would have spread the work thin. But
the deferral was never scheduled, and the consequence is a preference the product stores,
audits, and honours but cannot be set. The command even writes an audit entry
(`preferences.personal_events_set`, `digest_preferences.py:282`) — so the system is
already recording a decision no user is able to make.

### 3. There is a design precedent to follow, and it is not the one you'd guess

The product already has the right pattern for this class of control, and it is used for the
digest's *delivery time*: `components/settings/digest-delivery-time.tsx`. It reads the
stored value, saves **inline on change** with no Save button, shows
`SaveFeedback` (`saving → saved ✓`), distinguishes "the API refused it" from "the request
never arrived" via `saveFailureMessage`, and **sends the timezone alongside the time**
because the server refuses to half-apply the pair.

The settings routes today are `account`, `collections`, `quiet-hours`, `reminders`. There
is no `/settings` index — `sidenav.tsx:131` says so explicitly — and the sidenav's
Settings row points at `/settings/reminders` and is active on every `/settings/*` route.
So a new route needs no sidenav change, but it must be reachable from somewhere a user
would look.

### 4. The sibling gap, stated so it is not swallowed by this one

`DigestPreference.share_precise_location` (`models.py:671`) is a second boolean preference
with **no surface anywhere** — its own docstring says it outright: *"a privacy control with
no UI is half a control."* It is a different requirement (export redaction, not digest
composition) and it is **out of scope here**. It is named here so that it stays visible and
can be given its own intent rather than quietly riding along.

## Success Criteria

- **A user can turn personal events out of their Pulse Digest, and back on again, from a
  settings screen** — the toggle reflects the stored value on load, and saving it changes
  what the digest composes
- **The control writes through the existing named command** — no new API surface, no new
  model field, no new migration
- **The save is inline, with no Save button**, and shows the same `SaveFeedback` states the
  other settings controls use (`idle → saving → saved ✓`), with a failure line that
  distinguishes an API refusal from a network failure
- **The server's answer replaces the server's answer** — the toggle shows what the API
  confirmed, not what the user optimistically assumed
- **Opting out actually changes the digest** — a user with `include_personal_events=False`
  gets a digest whose Slot 1 contains no personal event, proven by a test against the
  composition service and not merely by a test against the settings screen
- **The onboarding flow sends the field it owns** — if the onboarding step is to expose the
  control, it writes it; if it does not, its test fixture stops implying that it does
- **No frontend reference to `include_personal_events` remains outside the generated
  client** — every hit is a real control or a real assertion
- **Every test can fail** — no placeholder assertions, no `or`-fallbacks
- **The finished surface is demonstrated working** in a real browser against a running
  stack, with anything broken reported rather than smoothed over

## Constraints

- **Reuse only — no new backend.** The field, the command, the endpoint, the read path and
  the composition behaviour all exist. This intent adds **no model field, no migration, no
  API route, no schema change**. If the work seems to need one, that is a signal the
  intent is being misunderstood.
- **The generated client is the contract** (AD-19). The frontend calls
  `PUT /api/personal/onboarding/digest-preference` through `lib/api/schema.ts`. If the
  backend schema changed, `make client` would have to regenerate and
  `git diff --exit-code frontend/lib/api/` would gate CI. **It does not change.**
- **The omission semantics are load-bearing.** `DigestPreferenceIn` treats an omitted
  field as "leave it alone", and the API's own description says so: *"a client that only
  wants to change the delivery time does not reset the city."* The control must send the
  field it owns and must not send fields it does not.
- **House style is binding** (`ARCHITECTURE-SPINE.md` Consistency Conventions): no component
  kit, no CSS-custom-property tokens, no new hex values, no new spacing tokens, no
  `prefers-color-scheme` auto-switch, one 240ms `motion.fadeIn`. Every visual comes from an
  existing token.
- **No PII in logs** (AD-13). The boolean may appear in audit details — the command
  already does it — but the user's city must not.
- **The digest's own copy is untouched.** FR-8's empty state has three competing variants
  (`prd.md:362`, `EXPERIENCE.md:513`, `DESIGN.md:337`); FR-22's hysteresis rule contradicts
  the PRD (`prd.md:739` ±0.02 vs `EXPERIENCE.md:213` ≥0.10); FR-6's card anatomy omits
  location. **All of these are out of scope.** They are a separate intent with a separate
  decision about which document wins.
- **No new mockups.** The existing design corpus already specifies the warm-tone treatment
  and the settings-surface pattern this work follows. The proof is the working screen and
  its tests.
- **The `share_precise_location` preference is not touched.** Out of scope, named above so
  it is not lost.

## Notes

Decisions taken at capture (2026-11-13), each chosen by Jobaer over the stated alternative:

- **Scope is the FR-19 opt-out only.** The audit that opened this intent found seven gaps
  across the digest surface (FR-19 opt-out, FR-7 delivery tolerance, FR-10 suppression,
  FR-22 hysteresis, FR-8 copy, FR-45 opt-in/opt-out, FR-16 citation). FR-45 is Phase 3 and
  was dropped as out of MVP. The rest are genuine but are **not** digest-composition
  defects and would each expand the intent past a single coherent change. The earlier
  reading — that FR-19 needed a full-stack build — was wrong: the backend was already
  there. Correcting that changed the shape of the work from "build a feature" to "build
  the surface for a finished feature", which is why the scope narrowed rather than grew.
- **The design doc wins over the PRD on contradictions** (Jobaer's call), but this intent
  contains no contradiction it must arbitrate — the contradictions sit in FR-22, FR-8 and
  FR-45, all out of scope. The rule is recorded because a later work item in this repo
  will hit one.
- **Verification is automated tests plus a real browser walk-through**, driven by me, with
  findings reported as found. **No mockups are produced** — the design corpus already
  covers this surface's language, and a new mockup would be a second source of truth for
  a control that has one real implementation.
- **The onboarding step is a decision to make during decomposition**, not a decision taken
  here. Onboarding is where a new user is told what they are getting, and the opt-out is
  arguably the right thing to surface there. But onboarding currently sends two fields and
  adding a third changes its contract, its step copy, and its test fixture — a bigger
  change than the settings screen, and one the design corpus does not currently specify.
  The brief states the requirement ("the onboarding flow sends the field it owns") and
  leaves the placement to decomposition.

Deferred deliberately, not forgotten:

- **`share_precise_location`** — a privacy control with no UI, its own docstring says so.
  Its own intent.
- **FR-7's ±15-minute tolerance and timezone-migration rule** — a delivery-time concern
  with no design artifact for the tolerance window.
- **FR-10's suppression rule** — "0 events → no Pulse Ping; 1+ personal → personal cards
  only" has no design and no personal-only composition state.
- **The traceability-matrix corrections** — the matrix mis-flags A-5 and A-7 as uncited
  (both are cited), misses the A-10 ID collision (PRD `prd.md:751` defines A-10 as FR-22's
  formula amendment; `DESIGN.md:349` and `EXPERIENCE.md:294` define it as the Browse
  route), and points FR-16's fix at the wrong row. A matrix that is wrong in this way
  should be repaired by an intent that treats the repair as the work, not folded into a
  feature intent as a side effect.

Recorded by the walkthrough (2026-11-13, `run-eventpulse24-030`), as follow-ups of their
own — **named, not fixed**:

- **Two writers of `include_personal_events`** — the onboarding endpoint writes it
  (`onboarding.py:370`) and `digest_preferences.py:336` writes it too. Two writers of one
  flag is a defect waiting to happen: they can disagree about what "leave it alone" means.
  The seam test found this during its mutation work — a mutation applied to the *second*
  writer was not caught, and had to be re-applied at the first to be caught at all.
- **Advancing past the digest step leaves a user with no schedule** — `advance_step`
  completes onboarding past the last step without writing a `DigestPreference`
  (`onboarding.py:451`), so a user who walks all three onboarding steps and never touches
  the digest step ends up with no delivery time and no timezone, and gets no digest. The
  control handles it honestly (disabled, *"Set your delivery time first."*), so the product
  is correct — but whether advancing past the digest step should write a default is a
  **product question**, not a test question.
