---
id: free-tier-caps-read-entitlement
title: The caps learn who is Pro — the save gate, and the provider cap that caps everyone
intent: pro-tier-and-monetization
complexity: medium
mode: confirm
status: pending
depends_on: [subscription-model-and-entitlement]
created: 2026-11-11
---

# Work Item: The caps learn who is Pro — the save gate, and the provider cap that caps everyone

## Description

Two caps, one concern: both must ask who is Pro.

**The save gate does not exist.** FR-48 names the 1-save/day cap as "the gate" — the single
trigger that turns a Free user into a paying one. There is no constant, no check and nothing
on the save path. The gate stands open, so the product currently has no upgrade trigger at
all.

**The provider cap exists and caps everyone.** `FREE_TIER_CALENDAR_PROVIDER_CAP = 1` is
enforced at `calendar_connections.py:409`, raising `CalendarProviderCapReached` with the
approved copy *"Save more with Pro."* — a prompt whose destination has never existed. The
constant's comment (`shared/constants.py:469`) names this work: *"The Pro cap of 3 is a later
intent and belongs here when it lands."*

## Acceptance Criteria

**The save gate (FR-49)**

- [ ] A Free user's **second save inside a 24-hour window** is refused with a calm inline
      upgrade prompt.
- [ ] The cap is declared through **`ThrottlePort.check(key, limit, window_seconds)`**, as
      `EventReport` already does with `EVENT_REPORT_DAILY_LIMIT` /
      `EVENT_REPORT_WINDOW_SECONDS`. It is not hand-rolled, and it does not count rows.
- [ ] Both the limit and the window live in `shared/constants.py`, named for what they gate.
- [ ] **A Pro user saves 10+ events in one day with no soft wall**, per FR-49's own testable
      consequence.
- [ ] The refusal payload matches the shipped `CalendarProviderCapReached` shape exactly: an
      `upgrade_hint` sentence and **no modal-shaped field** — no `modal`, no `title`, no
      `actions`, no `dismissable`. `calendar_connections.py:413-418` is the reference, and
      its reasoning (EXPERIENCE.md §3 and §4) applies unchanged.
- [ ] **A refused save changes nothing.** No partial `SavedEvent`, no throttle consumed by a
      save that did not happen.

**The provider cap (FR-50)**

- [ ] The cap becomes entitlement-chosen: **1 for Free, 3 for Pro**. A Pro user connects a
      second and third provider; a Free user still cannot connect a second.
- [ ] The comment at `shared/constants.py:469` is **resolved and removed**, not left stale.
- [ ] The existing reuse path at `calendar_connections.py:403-408`, which decrements the
      occupying count when a row is being reused, still behaves correctly under the raised
      cap.

**Both**

- [ ] Each cap reads entitlement through the **single read** from
      `subscription-model-and-entitlement`, by value across the wall (AD-3). Neither
      reimplements "is Pro".
- [ ] Tests cover, for each cap: a Free user at the limit refused; the same user, once Pro,
      allowed; a Pro user who lapses back to Free refused again; and the exact refusal
      payload shape.

## Technical Notes

Medium complexity. The caps are small; the reason they are one item is that they share the
entitlement read, and splitting them would mean wiring that read twice.

The save gate is on a hot path, so it is the first real consumer of whatever read path item
1's design chose. If that design specified a cache, this is where its latency assumption gets
tested — measure rather than assume.

Note the asymmetry worth preserving: the provider cap is enforced **at the connect step**,
and the save cap at the save step. Neither is enforced at read time. A Pro user who lapses
keeps their existing connections and saves — what happens to over-cap data on downgrade is an
open question in the brief, and this item must not quietly answer it by deleting anything.

## Dependencies

- subscription-model-and-entitlement
