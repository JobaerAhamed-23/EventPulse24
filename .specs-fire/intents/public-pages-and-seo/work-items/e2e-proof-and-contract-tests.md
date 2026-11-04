---
id: e2e-proof-and-contract-tests
title: Prove a stranger can get in — and that the proof can fail
intent: public-pages-and-seo
complexity: medium
mode: confirm
status: completed
depends_on:
  - revalidation-signal
  - frontend-public-event-page
  - frontend-city-page
  - sitemap-and-robots
  - share-control
created: 2026-11-01
run_id: run-eventpulse24-024
completed_at: 2026-11-04T11:56:14.537Z
---

# Work Item: Prove a stranger can get in — and that the proof can fail

## Description

The end-to-end proof for the whole intent, walked as the user who matters here: **someone with no account and no cookie**. Every other intent's proof could assume a session; this one must assert the opposite, because a sign-in wall that creeps onto a public page is invisible to every test that logs in first.

As with the delivery intent's proof, a test that cannot fail proves nothing — each assertion must be shown to go red when the behaviour it guards is removed.

## Acceptance Criteria

- [x] **The anonymous crawl path**, with no cookie jar at any step: land on `/events-in-{city}` → open an event → see the full event and the "Save to Pulse" CTA. No redirect, no wall, at any hop.
- [x] **The JSON-LD is in the server-rendered HTML** and parses as a valid Schema.org `Event`, asserted with JavaScript disabled — the crawler's actual conditions.
- [x] **Structured data agrees with the rendered page**: a cancelled event's visible state and its `eventStatus` are asserted together, so the two can never drift (AD-12).
- [x] **The revalidation round trip**: change an event's `status` to cancelled → the public page reflects it **without waiting for a timer**. This is the intent's central freshness promise and gets a dedicated test.
- [x] **A past event still resolves** — the case `catalog.get_event` deliberately refuses — asserted as a real 200 with content.
- [x] **A stale `EventFit` row is absent from the city page**, not rendered wrong (AD-10).
- [x] **`in_review` is invisible from every direction**: not at its slug, not on a city page, not in the sitemap.
- [x] **The sitemap contains no URL that 404s** — every entry is fetched and asserted.
- [x] **`robots.ts` disallows the authed routes** and allows the public ones.
- [x] **The existing authed surfaces are unbroken**: `/events/{uuid}` and `/events/{uuid}/reminders` still work, proving the branching route did not regress the signed-in detail screen.
- [x] Contract tests for the new public endpoints, and the **regenerated client is in sync** (AD-19) — a drifted client fails the build.
- [x] **Each assertion is shown to fail** when its behaviour is removed, recorded in the walkthrough.

## Technical Notes

Follow the pattern established by `delivery-and-reminders/e2e-proof-and-contract-tests` — the run that proved the delivery path and proved the proof could fail.

The anonymous assertions are the ones that rot quietest. Prefer a test harness that makes "no session" structural (a client with no cookie jar at all) over one that merely omits a login step, which a later change can silently restore.

## Dependencies

- revalidation-signal
- frontend-public-event-page
- frontend-city-page
- sitemap-and-robots
- share-control
