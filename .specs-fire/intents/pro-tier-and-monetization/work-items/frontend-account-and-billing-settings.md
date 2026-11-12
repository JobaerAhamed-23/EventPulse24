---
id: frontend-account-and-billing-settings
title: Account settings — plan, portal, and Download my data
intent: pro-tier-and-monetization
complexity: medium
mode: confirm
status: completed
depends_on:
  - checkout-and-portal-api
  - data-export
created: 2026-11-11
run_id: run-eventpulse24-027
completed_at: 2026-11-12T00:22:17.927Z
---

# Work Item: Account settings — plan, portal, and Download my data

## Description

One settings surface for everything about the account itself: which plan the user is on, how
to manage or cancel it, and FR-52's *"Settings → 'Download my data.'"*

These are one item because they are one screen and one concern. Splitting the export button
from the billing status would mean building the same surface twice.

## Acceptance Criteria

- [ ] The surface shows the **current plan** — Free, or Pro with its billing period and
      renewal date — read from `Subscription`, never inferred from the presence of a feature.
- [ ] A Pro user gets a **Manage subscription** link that opens the portal session from
      `checkout-and-portal-api`. Cancellation happens in Stripe's portal; this app does not
      build its own cancel flow.
- [ ] A Free user gets a quiet link to `/pricing`, in the same calm register as the cap
      prompts.
- [ ] **"Download my data"** requests the export from `data-export`, and tells the user it
      will arrive by email within 24 hours rather than appearing to download immediately.
- [ ] Requesting an export twice in quick succession is handled gracefully in the UI, matching
      the backend's single-job behaviour.
- [ ] **A lapsed or past-due subscription is shown honestly** — the user can see their state
      and reach the portal to fix it. This is the screen where a failed payment becomes
      visible, so it must not render a past-due user as simply "Free".
- [ ] Whether the export control is Pro-gated follows whatever `data-export`'s checkpoint
      decided about FR-52 and Article 20. This item does not settle that question, and does
      not quietly gate it by placing it in a Pro-only section.
- [ ] Works at mobile width; follows existing settings conventions.
- [ ] Tests cover Free, Pro, and past-due states, the portal link, and the export request.

## Technical Notes

Medium complexity. Follow the existing settings surfaces (`app/settings/reminders/`,
`app/settings/quiet-hours/`) for layout, save feedback and test conventions —
`components/settings/save-feedback.tsx` and `settings-states.tsx` already exist.

The past-due state is the detail most likely to be skipped and matters most: it is the only
place a user discovers a payment failed, and showing them as plain "Free" would hide a
recoverable problem. Whether `past_due` exists at all was fixed by
`subscription-model-and-entitlement`'s design doc — follow it.

Cancellation deliberately lives in Stripe's portal. Do not build a local cancel flow; it
would be a second write path into subscription state that the webhook would then have to
reconcile against.

## Dependencies

- checkout-and-portal-api
- data-export
