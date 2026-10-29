---
id: run-eventpulse24-019
scope: wide
work_items:
  - id: repo-hygiene-cleanup
    intent: personal-events-and-saved-catalog
    mode: autopilot
    status: completed
    current_phase: review
    checkpoint_state: none
    current_checkpoint: null
  - id: conflict-domain-and-constants
    intent: personal-events-and-saved-catalog
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: personalization-models
    intent: personal-events-and-saved-catalog
    mode: validate
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: delivery-reminder-plan-owner
    intent: personal-events-and-saved-catalog
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: personalization-write-services
    intent: personal-events-and-saved-catalog
    mode: validate
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: personal-events-api
    intent: personal-events-and-saved-catalog
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: saved-events-api
    intent: personal-events-and-saved-catalog
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: frontend-personal-and-conflict-surfaces
    intent: personal-events-and-saved-catalog
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: e2e-proof-and-contract-tests
    intent: personal-events-and-saved-catalog
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
current_item: null
status: completed
started: 2026-10-29T02:04:32.027Z
completed: 2026-10-29T05:31:56.212Z
---

# Run: run-eventpulse24-019

## Scope
wide (9 work items)

## Work Items
1. **repo-hygiene-cleanup** (autopilot) — completed
2. **conflict-domain-and-constants** (confirm) — completed
3. **personalization-models** (validate) — completed
4. **delivery-reminder-plan-owner** (confirm) — completed
5. **personalization-write-services** (validate) — completed
6. **personal-events-api** (confirm) — completed
7. **saved-events-api** (confirm) — completed
8. **frontend-personal-and-conflict-surfaces** (confirm) — completed
9. **e2e-proof-and-contract-tests** (confirm) — completed


## Current Item
(all completed)

## Files Created
- `backend/apps/personalization/models.py`: Four models: PersonalEvent, SavedEvent, ConflictPair, PersonalizationAuditEntry (AD-21 snapshots, the pair that is the indicator).
- `backend/apps/personalization/services/personal_events.py`: The create/edit/delete/list commands for personal events, with conflict detection on write (AD-21, FR-18).
- `backend/apps/personalization/services/saved_events.py`: The save/unsave commands with the AD-21 race protocol: read the version, write the snapshot, commit, re-read, report staleness.
- `backend/apps/personalization/services/conflicts.py`: Which events to compare and what to write when they do: candidates, the domain call, and the normalised sides.
- `backend/apps/personalization/services/conflict_resolutions.py`: The forced-choice machine: RESOLUTIONS_BY_KIND, the resolution recorded before the action it names, and the immutable pair.
- `backend/apps/personalization/api.py`: The session-scoped HTTP surface: create, list, get, edit, delete, resolve, save, unsave.
- `backend/apps/personalization/schemas.py`: The Pydantic wire shapes (AD-19). The conflict action list is a closed set, so a dismiss is inexpressible.
- `backend/apps/personalization/auth.py`: The session seam: one function, so the onboarding intent replaces it in one place.
- `backend/apps/delivery/services/reminder_plans.py`: The published reminder-plan service (AD-16): attach, set, remove, read.
- `backend/domain/conflict.py`: The one overlap function and the duplicate rule, stdlib only (AD-21).
- `frontend/components/sheets/conflict-resolution.tsx`: The forced three-action prompt (FR-58): no dismiss, delete needs confirmation.
- `frontend/components/sheets/personal-event-form.tsx`: The create/edit form: the timezone is a required, first-class field (AD-6).
- `frontend/components/personal-events-panel.tsx`: The client island that owns the list, the create sheet and the conflict flow.
- `frontend/components/personal-events-section.tsx`: The server component that reads the user own events.
- `frontend/components/add-event-button.tsx`: The spine Add affordance: opens the create sheet in place, no route.
- `backend/tests/e2e/test_personal_events_and_saved_catalog.py`: The recorded end-to-end scenario and the pinned boundaries.
- `backend/tests/e2e/test_save_race.py`: The AD-21 save race, forced deterministically, with a control case.
- `backend/tests/architecture/test_personal_events_invariants.py`: AD-3, AD-16 and AD-21 re-verified after this intent landed.

## Files Modified
(none)

## Decisions
- **The browser converts local time to UTC; the backend does not**: The conversion lives once, in frontend/lib/timezones.ts (The backend stores the instant and never reinterprets a wall clock in the zone (AD-6). Copying the rule into a caller would have left it in two places.)
- **The overlap rule is strictly more than 15 minutes**: A pure function in domain/conflict.py, with the threshold in shared/constants.py (One function, so the Pulse Card, the Timeline and the conflicts list cannot disagree about whether a pair overlaps (AD-21).)
- **The duplicate threshold is a rational, not a float**: Fraction(4, 5) (Fraction(4, 5) == 0.8 is False, so a float threshold would make the boundary undecidable.)
- **A resolved pair is immutable and never re-prompted**: The service checks the pair status before writing and skips a closed pair (AD-21 says so, and the database trigger would refuse the write anyway; checking first means the user never sees a raw RestrictViolation.)
- **The save-race is forced, not raced**: Patch the catalog read so the first call returns version N and the second N+1 (A probabilistic race test is a flaky test, and a flaky test in CI is worse than no test.)
- **The same pair is proven by an edit, not a re-create**: Edit the second event back into the first one time (A re-created event has a new id, so it is a new pair and the assertion would prove nothing about immutability.)
- **One Sheet base with a dismissible prop**: A single <dialog> component with two dismissal regimes (A native modal is Escape-dismissable by default, and the dismissal rules are the part most likely to be got wrong.)
- **The page is dynamic, not statically prerendered**: export const dynamic = force-dynamic on the page (The page shows the signed-in user own events, which is per-session state; and the build must not need a live Django.)
- **delivery owns REMINDER_PLAN; personalization calls its service**: A published service in apps/delivery/services/reminder_plans.py (AD-16. The service hands over plain data, so no caller holds a reference to apps.delivery.models.)
- **The conflict actions come from the server**: The sheet renders the actions[] array and maps names to labels (The sheet cannot offer a resolution the pair kind does not allow, because it never decides what the choices are (FR-58).)


## Summary

- Work items completed: 9
- Files created: 18
- Files modified: 0
- Tests added: 2231
- Coverage: 99.29%
- Completed: 2026-10-29T05:31:56.212Z
