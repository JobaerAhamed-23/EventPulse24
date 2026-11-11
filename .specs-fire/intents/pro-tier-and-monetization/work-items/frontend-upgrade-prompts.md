---
id: frontend-upgrade-prompts
title: The prompt at the cap — calm, inline, and finally going somewhere
intent: pro-tier-and-monetization
complexity: medium
mode: confirm
status: pending
depends_on: [checkout-and-portal-api, free-tier-caps-read-entitlement]
created: 2026-11-11
---

# Work Item: The prompt at the cap — calm, inline, and finally going somewhere

## Description

The backend has been emitting an upgrade hint with nowhere to go since the
`onboarding-and-account` intent: `calendar_connections.py:418` returns
`"upgrade_hint": "Save more with Pro."`. This item renders that hint, and the new save-cap
hint from `free-tier-caps-read-entitlement`, as the inline prompt the UX approved — and
points both at `/pricing`.

The design is `pro-upgrade-cta-desktop.html`. The constraint is already written into the
backend payload's shape and its comment at `calendar_connections.py:413-418`: the approved
copy is *"an **inline** prompt with a quiet 'Upgrade' link, not a modal"*, which is why the
payload deliberately carries no `modal`, `title`, `actions` or `dismissable` field.

## Acceptance Criteria

- [ ] Hitting the **save cap** shows a calm inline prompt with a quiet Upgrade link to
      `/pricing`. The save that was refused is not silently retried.
- [ ] Hitting the **calendar-provider cap** shows the same prompt from the same component.
      One component serves both; there is no second spelling of this UI.
- [ ] **It is never a modal**, never an interstitial, and never blocks the surface behind it.
      It does not steal focus or interrupt a flow in progress.
- [ ] The prompt renders from the server's `upgrade_hint`, so backend copy changes do not
      require a frontend change. It does not hard-code the sentence.
- [ ] **A Pro user never sees it**, under any state — including immediately after upgrading,
      without a page reload.
- [ ] Dismissing it, if dismissal exists at all, does not persist as a setting — the payload
      carries no `dismissable` field by design, and the frontend must not invent one.
- [ ] Tests cover both cap sources, the Pro user seeing nothing, and the link target.

## Technical Notes

Medium complexity, and the risk is tonal rather than technical. The product's whole posture —
"calm", the rejected always-on push, no streak shaming — points one way, and a paywall prompt
is exactly where that posture is easiest to lose. The backend payload was shaped to make the
wrong thing hard to build; do not route around it.

Reuse the existing error-to-UI path rather than special-casing these two endpoints: the hint
arrives as a field on a refusal, and other refusals already render somewhere. Find that path
first.

## Dependencies

- checkout-and-portal-api
- free-tier-caps-read-entitlement
