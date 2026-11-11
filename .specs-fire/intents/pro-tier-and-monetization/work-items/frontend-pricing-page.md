---
id: frontend-pricing-page
title: The pricing page — one screen, no upsell
intent: pro-tier-and-monetization
complexity: medium
mode: confirm
status: pending
depends_on: [checkout-and-portal-api]
created: 2026-11-11
---

# Work Item: The pricing page — one screen, no upsell

## Description

FR-48: *"Pricing page is a single screen; no upsell copy beyond 'fewer interruptions, more
control.'"* The design exists as `pricing-page-desktop.html`, self-tagged `FR-48`. There is no
`/pricing` route in `frontend/app/`.

## Acceptance Criteria

- [ ] A `/pricing` route renders the single screen from `pricing-page-desktop.html`, at
      **$4.99/month or $49/year**.
- [ ] **No upsell copy beyond "fewer interruptions, more control."** No countdown, no
      scarcity, no comparison table that editorialises. This is a product constraint, not a
      preference.
- [ ] The page states what Free keeps and what Pro adds, drawn from FR-48: Free retains Pulse
      Digest, Reminders, Personal Events, the 1-save/day cap and 1 connected calendar
      provider; Pro adds unlimited saves and collections, 3 providers, per-weekday quiet
      hours, and data export.
- [ ] Choosing a plan calls `checkout-and-portal-api` and follows the returned session URL.
- [ ] **A signed-out visitor can read the page** and is routed to sign-in on choosing a plan,
      rather than hitting an authentication error.
- [ ] **A user who is already Pro** sees their current plan and a link to the portal, not a
      second buy button.
- [ ] The page works at mobile width, follows the existing design-system tokens, and is
      reachable from navigation.
- [ ] Tests cover the three visitor states — signed out, Free, Pro — and the checkout call.

## Technical Notes

Medium complexity. Follow the conventions of the existing routes under `frontend/app/` and
the components in `frontend/components/`; read `settings/reminders/page.tsx` and its test for
the house pattern before writing.

If the local run uses the fake adapter, choosing a plan lands on `/dev/fake-billing` from
`checkout-and-portal-api`. That is expected and is how the path is walked locally.

Keep the restraint. The mockup is the authority on layout, and the PRD is the authority on
copy — where they disagree, the PRD's one sentence wins.

## Dependencies

- checkout-and-portal-api
