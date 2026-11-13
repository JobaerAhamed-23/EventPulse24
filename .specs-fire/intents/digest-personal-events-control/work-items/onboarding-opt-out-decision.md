---
id: onboarding-opt-out-decision
title: The Onboarding Question — Whether Onboarding Owns This Field, and
  Stopping It From Pretending To
intent: digest-personal-events-control
complexity: medium
mode: confirm
status: completed
depends_on:
  - personal-events-digest-toggle
created: 2026-11-13
run_id: run-eventpulse24-030
completed_at: 2026-11-13T01:41:12.267Z
---

# Work Item: The Onboarding Question — Whether Onboarding Owns This Field, and Stopping It From Pretending To

## Description

The brief left one decision open: **does the onboarding flow own the opt-out?**

**The case for onboarding owning it.** Onboarding is where a new user is told what they
are getting. The calendar step's lede already says the substance —
`onboarding-flow.tsx:55`: *"We'll surface your personal events alongside public ones —
birthdays, dinners, hard-to-get tickets — in the same calm brief."* That promise is
exactly what the opt-out governs. A user who would rather not have their calendar events
in the brief has no chance to say so at the moment the promise is made.

**The case against.** Onboarding is three steps with hardcoded copy (`TITLES`,
`onboarding-flow.tsx:52-68`) and a hardcoded step list (`:246-252`). Adding a fourth
control changes the step's contract, its copy, and its test fixture — a bigger change
than a settings screen, and one the design corpus does not currently specify. The UX
documents give onboarding a delivery time and a timezone; they do not give it an opt-out.

**The problem that must be fixed either way.** The onboarding flow currently **sends
only `delivery_time` and `timezone`** (`onboarding-flow.tsx:148-150`) and **omits**
`include_personal_events`. Under the endpoint's contract, an omitted field means "leave
it alone" — so the current behaviour is *correct*. **But the test fixture makes it look
otherwise**: `onboarding-flow.test.tsx:53` includes `include_personal_events: true` in
the mocked server state, and the comment above it says the digest preference "grew"
three fields including "the personal-events opt-out (which defaults to included)". The
fixture asserts a value the flow never sends and never reads.

So a user reading the test would conclude the opt-out is exercised at onboarding. **It
is not.** The fixture is a false signal about what the product does.

This item resolves the question and, either way, **stops the fixture from implying a
capability that does not exist.**

## Acceptance Criteria

- [x] **A decision is made and recorded** — onboarding owns the opt-out, or it does not — with the reasoning stated in the work item's notes
- [x] **If onboarding does not own it:** the fixture's misleading `include_personal_events: true` and its comment are corrected so they no longer imply the flow sends or reads the field, and the assertion at `onboarding-flow.test.tsx:344-346` still holds its exact-body form
- [x] **If onboarding does own it:** the control is added to the digest step using the same `<button>` + `aria-pressed` pattern as the settings toggle, `DigestValues` carries the flag, `initialDigestValues()` seeds it from the stored value, and the PUT body sends it **alongside** the required `delivery_time` and `timezone`
- [x] **In either case**, the onboarding PUT body is asserted by an exact-body test, and that assertion is **updated** to match reality — including the opt-out field when it is sent
- [x] The onboarding step's copy is updated **if and only if** the copy changes as a result of the decision — no copy is edited to explain a control that does not exist
- [x] No test anywhere asserts that onboarding sends `include_personal_events` when it does not
- [x] The onboarding flow's existing behaviour — the three steps, the resume-from-server-state behaviour, the delivery time and timezone — is **unchanged**

## Technical Notes

- **The exact-body assertion is a feature, not a nuisance.**
  `onboarding-flow.test.tsx:344-346` asserts
  `PUT` was called with `{ body: { delivery_time: "07:30", timezone: "America/New_York" } }`
  — the *whole* body. That assertion is what makes the omission visible: if a field is
  added to the body, the test fails until someone says so. **Keep the exact-body form.**
  The house test style elsewhere asserts the *absence* of other fields
  (`settings-inline-save.test.tsx`: `expect(body).not.toHaveProperty("quiet_hours")`) —
  that is the equivalent pattern here.
- **If onboarding owns it, the required fields come free.** Onboarding already has both
  `delivery_time` and `timezone` in hand — they are the step's own inputs and the PUT
  already sends them. Adding `include_personal_events` to that body needs no
  round-trip and no read helper. **This is the one place where sending the opt-out
  alone is impossible but sending it alongside the others is trivial.**
- **`DigestValues` and `initialDigestValues()`** live in
  `components/onboarding/digest-step.tsx`. The step renders `<DigestTimeControl>` plus a
  timezone `<select>`. A third control joins them there, and `DigestValues` grows a
  third field.
- **Seed from the stored value.** `initialDigestValues(state.digest ?? {})` reads the
  server's stored preference — and `OnboardingStateOut.digest.include_personal_events`
  is already `boolean` with a default of `true` in the generated schema, so the value
  arrives ready to use. A user who opted out and returns to onboarding sees it off.
- **The `DigestTimeControl` extraction is the precedent for not duplicating a control.**
  `digest-delivery-time.tsx:7-10` says it: *"`DigestTimeControl` was extracted out of
  `digest-step.tsx` so this route reuses it rather than growing a second copy of a time
  control — two copies is how two screens come to disagree about what a time means."*
  **If the settings toggle and the onboarding control are the same control, extract it
  once** (`components/settings/` or a shared location) and use it in both places. If
  they are genuinely different — different copy, different context — then they are two
  controls and the shared part is only the press/label mechanics.
- **Do not add a fourth onboarding step.** The step count is `ONBOARDING_STEP_COUNT` in
  `components/onboarding/steps.ts`, and the server tracks `current_step`. Adding a step
  is a backend-and-frontend change to the onboarding flow's shape, and it is not what
  this item is about. If the opt-out belongs at onboarding, it belongs **on the digest
  step**, which is where the delivery time and timezone already live.
- **The design corpus does not specify an onboarding opt-out.** `EXPERIENCE.md` gives
  onboarding a delivery time and a timezone. If the decision is "onboarding owns it",
  that is a **new design decision** and it should be recorded as one — with the copy
  written deliberately, not improvised at the end of a component.

## Dependencies

- personal-events-digest-toggle
