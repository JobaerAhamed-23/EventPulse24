---
id: run-eventpulse24-032
scope: wide
work_items:
  - id: user-name-model-and-command
    intent: account-profile-name
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: profile-endpoint-and-contract
    intent: account-profile-name
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: profile-screen-and-editor
    intent: account-profile-name
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: reduced-account-sheet
    intent: account-profile-name
    mode: autopilot
    status: completed
    current_phase: review
    checkpoint_state: none
    current_checkpoint: null
  - id: display-name-everywhere
    intent: account-profile-name
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: contract-and-e2e-proof
    intent: account-profile-name
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
current_item: null
status: completed
started: 2026-11-13T09:47:48.275Z
completed: 2026-11-13T13:17:34.101Z
---

# Run: run-eventpulse24-032

## Scope
wide (6 work items)

## Work Items
1. **user-name-model-and-command** (confirm) — completed
2. **profile-endpoint-and-contract** (confirm) — completed
3. **profile-screen-and-editor** (confirm) — completed
4. **reduced-account-sheet** (autopilot) — completed
5. **display-name-everywhere** (confirm) — completed
6. **contract-and-e2e-proof** (confirm) — completed


## Current Item
(all completed)

## Files Created
(none)

## Files Modified
(none)

## Decisions
- **How the shell learns a name that changed after the render**: A module-level store read with useSyncExternalStore (The rail is rendered by AppShell, which every page mounts by hand — a context provider would mean fifteen pages each wrapping their own shell. router.refresh() re-runs every server read on the page for one string.)
- **What the store holds**: The display name, not the stored name (Publishing the stored name would blank the rail for anyone who clears their name.)
- **How the line-break refusal is driven in the browser**: BEL, written as a named escape (The HTML value sanitization algorithm strips \r and \n from a single-line input, so a newline never reaches the API.)


## Summary

- Work items completed: 6
- Files created: 0
- Files modified: 0
- Tests added: 13
- Coverage: 0%
- Completed: 2026-11-13T13:17:34.101Z
