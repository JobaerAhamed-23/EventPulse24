---
id: fr-49-saved-collections
title: FR-49 — design saved collections, and correct the coverage claim that hid them
intent: traceability-reconciliation
complexity: medium
mode: confirm
status: completed
depends_on: []
created: 2026-11-12
run_id: run-eventpulse24-028
completed_at: 2026-11-12T05:44:53.704Z
---

# Work Item: FR-49 — design saved collections, and correct the coverage claim that hid them

## Description

FR-49 is the only one of the four rated **MISSING** rather than PARTIAL, and the reason is
instructive: a coverage table claimed it was designed when it was not.
`EXPERIENCE.md:1236` lists `settings-desktop.html` as covering *"FR-7 / FR-12 / FR-48 /
FR-49 / FR-51 / FR-52"*. That file carries **no `FR-` tag in its header at all** and contains
no collection content. "Named collections" appears only as a marketing bullet on the
`FR-48`-tagged pricing pages — the thing being sold, with no screen showing it being used.

The software is real and thorough. `collections_api.py:1` opens: *"The collections endpoints
(FR-49): create, rename, reorder, delete, assign, unassign"*, backed by migration
`0014_savedcollection_savedcollectionitem`, `components/collections/collection-manager.tsx`
and `app/settings/collections/page.tsx`.

So this item has a second job beyond the other three: **the false coverage claim gets
corrected**, not just supplemented. A table that over-claims is what let this FR ship
undesigned in the first place.

## Acceptance Criteria

- [ ] A mockup exists, self-tagged `FR-49`, showing a collection being **created, renamed,
      reordered and deleted**, plus a collection's contents and the assign/unassign action.
      All four PRD verbs are visible, not just the two that are easy to draw.
- [ ] A named DESIGN.md or EXPERIENCE.md section cites `FR-49` and names the component per the
      UX spine convention.
- [ ] **`EXPERIENCE.md:1236` is corrected** — `settings-desktop.html` no longer claims FR-49
      coverage it does not have. Check the row's other claims (FR-7, FR-12, FR-48, FR-51,
      FR-52) against that file's actual content while there; one wrong cell in a table is
      rarely alone.
- [ ] A test asserts a Pro user can save 10+ events in one day with no soft-wall CTA.
- [ ] A test asserts **reorder** persists. `collections_api.py:112–120` documents a real trap:
      `/order` must stay registered **before** `/{collection_id}`, or django-ninja matches the
      rename route first and `"order"` fails to parse as a UUID. That comment is a bug report
      from the past — add the regression test that keeps it fixed.
- [ ] A test asserts a free user at the 1-save/day cap gets a **calm in-app prompt with no
      modal interruption**. Assert the absence of the modal, not merely the presence of the
      prompt — "no modal" is the testable half of that consequence, and the `trust-loop` and
      `pro-tier` intents already established the inline-upgrade-hint pattern to match.
- [ ] Rename, delete and unassign are confirmed open on every tier, per `collections_api.py:10`
      — the Pro gate is on *creating* and on the save cap, not on managing what exists.
- [ ] Shared collections stay out (Phase 2 — Pulse the Group), as do collection-level
      reminders.
- [ ] Tests name `FR-49`.

## Technical Notes

`collections_api.py:63` returns `position` on the collection view and `:108` documents
*"This user's collections, in their order"* — so ordering is server-owned, not a client
convenience. The design should show where the user grabs a collection to reorder it and what
the drag affordance is under the no-component-kit, no-animation-library constraint. One 240ms
`motion.fadeIn` and no transform is the whole motion budget; a drag interaction that needs
more than that is a design decision to surface at the checkpoint, not to invent silently.

`test_saved_collections.py` and `test_collections_api.py` already exist. Read them first —
some consequences may already be covered, and the work is then naming them against FR-49
rather than writing them twice.
