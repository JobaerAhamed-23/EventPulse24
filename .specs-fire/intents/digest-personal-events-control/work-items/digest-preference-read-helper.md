---
id: digest-preference-read-helper
title: The Read Helper — One Server-Side Way to Read the Digest Preference
intent: digest-personal-events-control
complexity: low
mode: autopilot
status: completed
depends_on: []
created: 2026-11-13
run_id: run-eventpulse24-030
completed_at: 2026-11-13T01:14:33.781Z
---

# Work Item: The Read Helper — One Server-Side Way to Read the Digest Preference

## Description

The settings screen needs to read the user's stored digest preference — the delivery time,
the timezone, **and** the `include_personal_events` flag — before it can render a toggle
that shows the truth.

There is no read helper for `/api/personal/onboarding`. The three existing settings
routes each have one, but all three read the *notification* settings singleton
(`readNotificationSettings()`, `lib/notification-settings-read.ts`) or the billing
account (`readBillingAccount()`) or collections (`readCollections()`). **No settings page
has ever read a personalization endpoint.**

Onboarding reads the same endpoint, but it does it inline in
`app/onboarding/page.tsx:59-66` as a local `readState()` function, and it reads the whole
`OnboardingStateOut` — which is more than a settings screen wants and less specific about
failure than the house pattern.

This item adds the missing helper and nothing else. It is the foundation the toggle
stands on, and it is deliberately first in the dependency order.

The helper reads `GET /api/personal/onboarding` and returns **only the digest preference**
— the three fields this intent's screen needs — so that a later change to the onboarding
state shape cannot break a settings screen.

## Acceptance Criteria

- [x] A server-only read helper exists, following `lib/notification-settings-read.ts`'s shape exactly: a `kind` discriminant of `"found" | "unavailable"`, and no third state
- [x] It reads `GET /api/personal/onboarding` with the visitor's cookies via `sessionHeaders()`, so the request is authenticated rather than anonymous
- [x] It returns **only** what the settings screen needs — `delivery_time`, `timezone`, `include_personal_events` — and does not expose the whole `OnboardingStateOut` to its callers
- [x] It never throws: a failed request, a missing body, or an absent `digest` block all produce `"unavailable"`
- [x] It is **server-only** — it calls `sessionHeaders()` from `next/headers`, so it is not importable from a `"use client"` component. A test asserts this, so the constraint survives a refactor
- [x] The existing `readNotificationSettings()` helper and every current settings route are **untouched**
- [x] A test covers: found-with-values, unavailable-on-throw, unavailable-on-missing-body, and unavailable-on-absent-digest

## Technical Notes

- **Mirror the house shape, do not invent one.** `lib/notification-settings-read.ts` is the
  pattern: a `type XRead = { kind: "found"; ... } | { kind: "unavailable" }`, an
  `async function readX(): Promise<XRead>`, a `try/catch` that returns `"unavailable"`, and
  a module docstring explaining why the read carries cookies and why there is only one
  kind of nothing.
- **Why only one kind of nothing.** The module docstring of the existing helper says it:
  the endpoint is a singleton that self-creates, so `"missing"` is not a state the user
  can be in. The same is true here.
- **Why not reuse `readNotificationSettings()`.** It reads
  `/api/settings/notifications`, which is the *delivery* surface — quiet hours, reminder
  slots, digest schedule — owned by `apps.delivery`. This preference is owned by
  `apps.personalization` and lives on `DigestPreference`. Two owners, two endpoints, two
  helpers. Reading the wrong one would be reading a different module's row.
- **Why not reuse onboarding's inline `readState()`.** It returns the entire
  `OnboardingStateOut`, it lives in a route file rather than `lib/`, and its error
  behaviour is `null` rather than a discriminated union. A settings screen wants the
  narrow shape and the discriminated union.
- **The `digest` block is optional on the response.** `OnboardingStateOut.digest` is
  nullable in the generated schema, so `state.digest` can be `undefined`. The helper
  treats an absent block as `"unavailable"` — a user with no preference row yet has no
  digest preference to show, and the screen falls back to its own defaults.
- **Test location.** `frontend/lib/` has no test directory convention yet; the
  repo's frontend tests sit next to what they test (`components/settings/*.test.tsx`).
  Put this test beside the helper or under `frontend/lib/` following whatever the
  neighbouring `lib` modules do — check `frontend/lib/` for an existing `*.test.ts` before
  choosing a path.
- **The mock pattern.** `vi.mock("@/lib/backend-client", () => ({ api: { GET: (...) => GET(...) } }))`
  — the same shape as `components/settings/settings-inline-save.test.tsx:24-28`. A server
  helper needs the `sessionHeaders()` seam too; mock `next/headers` the way the existing
  tests do, and check how `lib/notification-settings-read.ts` is covered today, if at all.

## Dependencies

(none)
