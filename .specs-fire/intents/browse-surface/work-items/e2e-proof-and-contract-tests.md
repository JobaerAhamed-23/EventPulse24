---
id: e2e-proof-and-contract-tests
title: End-to-End Proof — Seeded Data, a Real Browser, and an Honest Report
intent: browse-surface
complexity: medium
mode: confirm
status: in_progress
depends_on:
  - frontend-browse-search
  - frontend-browse-save-button
  - browse-nav-activation
created: 2026-11-12
---

# Work Item: End-to-End Proof — Seeded Data, a Real Browser, and an Honest Report

## Description

The closing item, and the one Jobaer asked for by name: *check each item works properly or
not.* Automated coverage of the whole path, then a walk through the running app against
seeded catalog data, reporting what is actually there — including anything broken.

The distinction that matters: a green suite says the code does what the tests say. This item
is about whether the surface does what the **design** says, which is a different question and
the one that has gone unasked on every surface built so far.

## Acceptance Criteria

- [ ] An e2e test covers the full path: sign in → navigate to Browse from the sidenav → see
      ranked cards in two tiers → filter with a keyword → filter with a `tag:` literal →
      clear → save a card → see it saved
- [ ] An e2e test covers the Free quota wall: save once, then confirm the second Save is
      refused inline with the upgrade copy and **no modal appears**
- [ ] An e2e test covers a Pro user saving repeatedly with no cap
- [ ] An e2e test covers the two emptinesses separately: a query matching nothing, and a city
      window holding nothing
- [ ] A contract test asserts the OpenAPI schema and the generated TypeScript client agree,
      with no manual edits to `schema.ts`
- [ ] `make test-backend`, `make test-web`, `make lint-backend`, `make lint-web` and
      `make lint-imports` all pass
- [ ] `make coverage-backend` meets its gates: ≥80% overall, 100% for `domain/`
- [ ] **Catalog data is seeded** by a repeatable command, not hand-inserted rows, so the
      walk-through is reproducible and the next person can see what I saw
- [ ] **The browser walk-through is performed and written up** against the design's own
      locks: no chip rail, no discovery stripe, ≤2 stripe colours, ≤1 must-know card, no
      count badges, no social proof, no Sign-up CTA, no SEO footer, no upsell carousel
- [ ] The write-up states what was checked, what passed, and **what did not** — findings are
      reported as found rather than fixed silently or smoothed over in the summary
- [ ] Anything broken is either fixed in this item or recorded as a named follow-up with the
      reason it was not fixed; nothing is left implied

## Technical Notes

Seeding needs real-shaped data to exercise ranking: enough events in one city across the
full 7-day window to overflow the 24-card soft cap and prove the chunk loader, with varied
why-tags so `tag:` filtering has something to constrain.

Start the stack per the project's own route — `make up`, then `make dev`. The frontend needs
**Node 24** (`.nvmrc`); a login shell defaulting to Node 20 makes every Vitest file die with
`Cannot read properties of undefined (reading 'bind')` from undici.

Run `make up` before `make dev`: `scripts/dev.sh` only warns about missing infrastructure, it
does not start it.

**This item's honesty is the deliverable.** A walk-through that reports everything fine is
worth nothing if it did not look hard. The anti-pattern list is the checklist precisely
because those are the things most likely to creep in unnoticed.

## Dependencies

- frontend-browse-search
- frontend-browse-save-button
- browse-nav-activation
