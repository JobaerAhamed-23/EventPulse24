---
id: run-eventpulse24-022
scope: wide
work_items:
  - id: conflict-list-api
    intent: timeline-and-conflicts
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: saved-public-conflict-resolution
    intent: timeline-and-conflicts
    mode: validate
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: timeline-week-api
    intent: timeline-and-conflicts
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: frontend-timeline
    intent: timeline-and-conflicts
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: frontend-conflicts-page
    intent: timeline-and-conflicts
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: detail-screen-conflict-prompt
    intent: timeline-and-conflicts
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: home-back-to-digest
    intent: timeline-and-conflicts
    mode: autopilot
    status: completed
    current_phase: review
    checkpoint_state: none
    current_checkpoint: null
  - id: e2e-proof-and-contract-tests
    intent: timeline-and-conflicts
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
current_item: null
status: completed
started: 2026-10-31T06:33:07.500Z
completed: 2026-10-31T10:28:08.146Z
---

# Run: run-eventpulse24-022

## Scope
wide (8 work items)

## Work Items
1. **conflict-list-api** (confirm) — completed
2. **saved-public-conflict-resolution** (validate) — completed
3. **timeline-week-api** (confirm) — completed
4. **frontend-timeline** (confirm) — completed
5. **frontend-conflicts-page** (confirm) — completed
6. **detail-screen-conflict-prompt** (confirm) — completed
7. **home-back-to-digest** (autopilot) — completed
8. **e2e-proof-and-contract-tests** (confirm) — completed


## Current Item
(all completed)

## Files Created
- `backend/apps/personalization/api.py`: The personalization API: the week read, the conflict list, the resolve endpoint, and the detail prompt.
- `backend/apps/personalization/services/timeline.py`: The Timeline week read, with the conflict indicator that fires on the day-cell holding the overlap.
- `backend/apps/personalization/services/conflict_list.py`: The conflict list read, scoped to the caller and offering the union of the pair's actions.
- `backend/apps/personalization/services/conflict_resolutions.py`: The resolution service: the allowed set per side, and the one check that makes a closed pair immutable.
- `backend/apps/personalization/services/detail_conflict.py`: The Detail Screen's active pair for one saved event, and only while it is active.
- `frontend/lib/timeline-read.ts`: The frontend's Timeline read, through the generated client.
- `frontend/lib/conflict-list-read.ts`: The frontend's conflict list read, through the generated client.
- `frontend/components/timeline/*`: The Timeline screen: the week grid, the day-cells, and the conflict indicator.
- `frontend/components/conflicts/*`: The Conflict Review screen and its panel.
- `backend/tests/e2e/test_timeline_and_conflict_proof.py`: The backend scenario: twelve tests driving the real HTTP stack through the whole intent.
- `backend/tests/e2e/mutation_probe_timeline_conflicts.py`: The mutation-probe harness: eight probes, each required to fail when its bug is planted.

## Files Modified
- `frontend/tests/ad19-endpoint-coverage.test.ts`: The contract sweep now goes both ways — schema to client, and call-site to schema.
- `backend/apps/personalization/services/detail_conflict.py`: Formatting only, from ruff format. No behaviour change.
- `backend/apps/personalization/services/detail_read.py`: Formatting only, from ruff format. No behaviour change.
- `backend/tests/personalization/test_detail_conflict.py`: Removed an unused import; formatting only otherwise.

## Decisions
- **The scenario drives the HTTP stack**: Real requests, real 409s, real resolutions (The 409 is the seam, and the pair id first appears there.)
- **The contract is proved in both directions**: Schema to client, and call-site to schema (The old sweep could not see a call site naming a path the schema does not describe.)
- **The Timeline indicator fires on the overlap, not the span**: The flag rides the day-cell (A flag carried on the block would light every day an event spans.)
- **Keep both keeps the flag permanently**: The projection carries resolved keep-both pairs alongside active ones (FR-58 promises a permanent reminder; a projection of active pairs only would clear it.)
- **The conflict list offers the union; the Detail Screen offers the saved side only**: Four actions on the list, three on the detail prompt (The Detail Screen acts on the save, and deleting the user's personal event is not a choice that surface should present.)
- **The unreachable guard stays**: The explicit side-kind comparison is left in the code (It is a correct statement of the rule. The allowed set is what carries the property; removing the guard would change reviewed code for no gain.)


## Summary

- Work items completed: 8
- Files created: 11
- Files modified: 4
- Tests added: 4062
- Coverage: 99.15%
- Completed: 2026-10-31T10:28:08.146Z
