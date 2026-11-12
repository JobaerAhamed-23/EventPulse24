---
id: run-eventpulse24-029
scope: wide
work_items:
  - id: test-clock-seam
    intent: browse-surface
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: browse-read-api
    intent: browse-surface
    mode: validate
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: frontend-browse-shell-and-grid
    intent: browse-surface
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: frontend-browse-search
    intent: browse-surface
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: frontend-browse-save-button
    intent: browse-surface
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: browse-nav-activation
    intent: browse-surface
    mode: autopilot
    status: completed
    current_phase: review
    checkpoint_state: none
    current_checkpoint: null
  - id: e2e-proof-and-contract-tests
    intent: browse-surface
    mode: confirm
    status: in_progress
    current_phase: plan
    checkpoint_state: none
    current_checkpoint: plan
current_item: e2e-proof-and-contract-tests
status: in_progress
started: 2026-11-12T06:53:06.076Z
completed: null
---

# Run: run-eventpulse24-029

## Scope
wide (7 work items)

## Work Items
1. **test-clock-seam** (confirm) — completed
2. **browse-read-api** (validate) — completed
3. **frontend-browse-shell-and-grid** (confirm) — completed
4. **frontend-browse-search** (confirm) — completed
5. **frontend-browse-save-button** (confirm) — completed
6. **browse-nav-activation** (autopilot) — completed
7. **e2e-proof-and-contract-tests** (confirm) — in_progress


## Current Item
e2e-proof-and-contract-tests (confirm)

## Files Created
(none yet)

## Files Modified
(none yet)

## Decisions

- **The sidenav's and the bottom bar's inert-route branches were KEPT; the More sheet's
  was DELETED.** `browse-nav-activation`'s fifth criterion reads *"The inert-row component
  or branch is deleted if Browse was its only remaining user; if another route still needs
  it, it stays and the run log says which."* Browse **was** the last user of both kept
  branches — so a literal reading says delete. The item's Technical Notes say the opposite
  and are more specific about intent: *"Nothing here should weaken that rule for whatever
  route is deferred next."* The branch is the **implementation of a rule the product still
  states** (an inert route is a `<span>`, never an anchor — *"the attribute is a hint, not a
  mechanism"*), not a Browse thing. Deleting the only implementation of a rule in the same
  edit that removes its last user is how the rule dies quietly. **This is the decision a
  reviewer should check first.** The More sheet's branch went because its only row is
  Browse, and Browse is a route — there was never a reason for that sheet to carry a
  disabled `<span>`. The kept branches are pinned by
  `tests/digest-home-boundary.test.ts`, so they cannot rot into anchors while they wait.
- **The bottom tab's Digest slot was made a link, though the item was written about
  Browse.** The bar has five slots and Browse is the sixth route, behind the More sheet —
  so the bar never had a Browse slot. Its *first* slot was the inert one, and it had had
  no `href` since the digest home shipped (`git log -p --follow` shows only the `+` line,
  never a `-` line). The item's third criterion — *"the visually-hidden 'Coming soon' text
  is removed where it referred to Browse"* — pointed where nothing referred to Browse,
  because the text that remained was attached to **Digest**. The criterion is satisfied by a
  fix the item did not name, and it is the fix that matters: the home route's own tab did
  nothing, while carrying `active={pathname === "/"}`.
- **The bar's Digest slot takes the sidenav's *prefix* active rule** (`/` or `/events/*`),
  not an equality. The Detail Screen is reached by tapping a Digest card, so `/events/*`
  hangs off Digest in the IA. The sidenav already applied this rule; if the bar did not,
  the same screen would show Digest active in the rail and nothing active in the bar.
