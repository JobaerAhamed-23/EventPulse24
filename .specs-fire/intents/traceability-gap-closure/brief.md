---
id: traceability-gap-closure
title: Traceability Gap Closure — the Cost Dashboard, the Ping Promise, and the Timeline's Missing Detail
status: active
created: 2026-11-17
---

# Intent: Traceability Gap Closure — the Cost Dashboard, the Ping Promise, and the Timeline's Missing Detail

## Goal

Close every gap the 2026-11-17 `doc-trace` pass found, so that all three traceability
sections read clean at once for the first time: Design, Architecture **and** Implementation.

That pass was the first complete Section C — all 45 MVP FRs scored against running code
rather than 12 scored and 33 left `UNASSESSED`. It found exactly one `MISSING` row, two
documented shortfalls behind otherwise-`FULL` rows, and two Amendment tags that never
propagated. This intent is those five things and nothing else.

## Users

- **Staff and the people paying for the AI budget** — FR-29. Cost rows accrue on every LLM
  call and nobody, staff included, can read them back. PRD §10.3 sets a cost ceiling that
  nothing currently reports against.
- **Every signed-up user** — FR-10. Onboarding promises a control over the daily Pulse Ping
  that the product does not have.
- **Desktop Timeline readers** — FR-32. The week view withholds detail that
  `EXPERIENCE.md` §13 says it should reveal on hover and focus.
- **Everyone who runs or reads `doc-trace`** — the Amendment Ledger re-flags the same two
  tag misses on every regeneration.

## Problem

**The product's own measurement found four things it had been unable to see.**

Sections A and B cannot tell designed from built. FR-29 is the proof: it carries a design
`N/A` (internal admin tool, correctly) and an architecture `FULL` (a Capability row naming
`adapters/llm` and `editorial`, also correctly) — and the admin half of that row was never
written. `adapters/llm/costs.py:63` writes an `AICostRow` on every call, the migration
creates the table, the model is append-only and right, and no `admin.py` exists in that
package. **A complete, tested backend with no reachable surface** is exactly the shape
Section C was added to catch, and it caught it.

The other three are smaller but the same species — a promise the code does not keep:

- Onboarding says *"One calm Pulse Ping per day… You can change this anytime"*
  (`onboarding-flow.tsx:86`). `NotificationSettingsIn` (`apps/delivery/schemas.py:267`)
  carries `quiet_hours`, `quiet_hours_overrides`, `default_reminder_slots` and `digest` —
  and no ping field. The `ping_unsubscribed` column already exists
  (`migrations/0004_notificationpreference_ping_unsubscribed`); the only thing that sets it
  is the RFC 8058 one-click link inside a ping the user has to receive first.
- `EXPERIENCE.md` §13 line 1107 specifies that a desktop Timeline event-block **adds**
  location and one Why-this tag on hover or focus. `timeline-block.tsx` has only a
  `hover:bg-surface-inset` fill swap. **And the data is not there to add** —
  `TimelineBlockOut` carries `id`, `kind`, `name`, `conflict`, `state` and the three time
  fields, with no venue and no tags. This is an API contract change before it is a CSS one.
- Amendments A-2 (FR-5) and A-3 (FR-22) are tagged in the PRD and cited nowhere in
  DESIGN.md or EXPERIENCE.md, though both FRs have substantial UX surfaces.

## Success Criteria

- A staff user can read AI cost rows in Django admin, and the surface answers PRD §10.3's
  ceiling question rather than merely listing rows.
- A signed-in user can turn the daily Pulse Ping off and back on from Settings, the setting
  survives a reload, and the onboarding sentence becomes true as written.
- A desktop Timeline block reveals its location and one Why-this tag on hover **and** on
  keyboard focus, with the server supplying both — the client recomputes neither (AD-10).
- `TimelineBlockOut`'s new fields reach the frontend through the generated client, not a
  hand-edited type (AD-19).
- DESIGN.md and EXPERIENCE.md each cite the Amendment ID for the FR they describe, so the
  Ledger stops re-flagging A-2 and A-3.
- A `doc-trace` regeneration afterwards reports **0 missing and 0 partial in all three
  sections**, with the Amendment Ledger down to the A-11–A-20 convention question alone.

## Constraints

- **AD-10 — the client renders decisions, it does not make them.** The Timeline's new tag
  must be chosen server-side and sent; the block may not pick one from a list at render.
- **AD-19 — the OpenAPI schema is the contract.** Any `TimelineBlockOut` change goes
  through `make client` (export schema, regenerate `schema.ts`); `schema.ts` is never
  hand-edited.
- **EXPERIENCE.md §13's anti-pattern is locked**: hover and focus may **add** detail and
  must never **remove** a trust signal. The idle block keeps everything it has today.
- **No hover-only affordances.** Whatever hover reveals, focus must reveal too — the rule
  the existing `▸` on the Pulse Card already follows.
- **Pro gating is server-side.** Nothing in this intent is Pro-only, but the ping control
  follows the existing pattern: the API refuses, the UI does not merely hide.
- **The ping control must not become a second mute path.** `ping_unsubscribed` is one
  column with one meaning; the Settings row and the email's one-click unsubscribe write the
  same field, and turning the ping off cancels that scope's pending sends exactly as the
  unsubscribe path already does.
- **Admin registrations are read-only.** `AICostRow` is an `AppendOnlyModel`; the admin must
  not offer add, change or delete. Model it on `apps/ingestion/admin.py`'s existing
  `SourceReliabilityScore` and `IngestionAuditEntry` registrations.

## Notes

Decisions taken at capture, rather than assumed:

1. **FR-10 — build the control, keep the copy.** The alternative (rewrite
   `onboarding-flow.tsx:86` to point at the email link) was considered and rejected: it
   removes a capability users reasonably expect, and the unsubscribe link only arrives once
   the first ping has been delivered.
2. **FR-32 — in scope.** It follows the 2026-11-17 block layout fix, so the component is
   already open.
3. **A-2 / A-3 — in scope, as their own docs-only work item.** The separate A-11–A-20
   question (whether UX-originated amendments flow back into the PRD at all) is a
   *convention* decision and is deliberately **not** in this intent; it needs deciding once,
   by a human, rather than being fixed repeatedly.

Scope discovered during capture: FR-32 splits into two work items, because the hover detail
cannot be built until the API sends the data. The contract item must land first.
