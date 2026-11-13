---
id: less-like-this-adjustment
title: FR-25 "Less like this" — Unbuilt on Both Sides
intent: unwired-surfaces
complexity: high
mode: validate
status: in_progress
depends_on: []
created: 2026-11-13
---

# Work Item: FR-25 "Less like this" — Unbuilt on Both Sides

## Description

FR-25 is MVP scope and exists nowhere in the codebase. Not a missing caller — a missing
feature, end to end: **no endpoint, no model, no UI, no swipe.**

`detail-actions.tsx:7` is the clearest statement of it in the repo, and it is a correct
decision, not an excuse:

> **Two buttons, not three.** The locked order says "Save to Pulse · Share · Dismiss", and
> the mockup has a "Less like this" third. But FR-25's dismissal is a **swipe on the Pulse
> Card**, and there is **no dismissal endpoint** in this codebase — a "Dismiss" button here
> would be a control that silently does nothing, which is the failure this screen is
> supposed to avoid.

The swipe it defers to does not exist either: `components/digest/` has `pulse-card.tsx`,
the empty, error, preparing and skeleton states, and no dismissal of any kind.

`less-like-this-mute-prompt-desktop.html` specifies the full behaviour:

> FR-25. Triggered after 3 clustered dismissals (embedding cosine ≥0.7). Calm copy.
> Reversible from settings. No dark-pattern nag.

That is three separate pieces of machinery: a **dismissal** record, a **clustering rule**
over embeddings, and a **mute** that is reversible from a settings screen — and the settings
screen in question is the one `settings-sources-surface` is about.

**This is the largest item in the intent and may not belong in it.** The brief says so
explicitly. The design checkpoint is the place to decide: if this is bigger than the other
seven items combined, it should be split into its own intent rather than forced through.

## Acceptance Criteria

- [ ] **The design checkpoint decides scope before any code**, and states plainly whether
      this belongs in this intent or in its own
- [ ] A user can dismiss a Pulse Card, and the dismissal is recorded
- [ ] Three dismissals clustered at cosine ≥0.7 trigger the mute prompt, once — not on every
      subsequent dismissal
- [ ] The prompt is **reversible from settings**, and the reversal surface is named and built
      or explicitly sequenced behind `settings-sources-surface`
- [ ] The copy is calm and the prompt does not nag — the mockup's own constraint
- [ ] Dismissing affects what the user is shown; a test proves composition changes, not just
      that a row was written
- [ ] The endpoint is reached through the generated client (AD-19), and `make client` output
      is committed
- [ ] Every test is verified by a mutation probe that makes it fail

## Technical Notes

- **Check whether embeddings exist before designing the clustering.** The repo uses pgvector
  (`pgvector/pgvector:0.8.6-pg18` in `docker-compose.yml`) and the catalog has ranking code
  (`domain/ranking.py`). Whether per-event embeddings are stored, and at what dimension, is
  the first thing the design must establish — the cosine ≥0.7 rule is unimplementable
  without them, and discovering that late would be expensive.
- **"Reversible from settings" couples this to `settings-sources-surface`.** If that item's
  3-state mute control (Mute / Show less / Default) is the reversal surface, say so and
  sequence them; if it is a separate control, say why.
- **A dismissal is user content under the never-delete constraint.** Decide early whether a
  dismissal is reversible per event, and what "undo" means.
- **The PRD and the mockup may disagree.** The brief's precedent is that the design doc wins
  on contradictions (Jobaer's call, recorded in `digest-personal-events-control`), but check
  for one and name it rather than assuming.

## Dependencies

- (none)
