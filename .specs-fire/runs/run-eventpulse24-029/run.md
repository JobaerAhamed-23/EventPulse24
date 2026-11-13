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
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
current_item: null
status: completed
started: 2026-11-12T06:53:06.076Z
completed: 2026-11-12T17:08:29.744Z
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
7. **e2e-proof-and-contract-tests** (confirm) — completed


## Current Item
(all completed)

## Files Created
- `frontend/components/browse/browse-quota-provider.tsx`: The live save allowance: a client context that holds the server's last quota and asks the server again after a save. The hero's note and the cards' buttons read the same moving number, and a prop cannot cross the server/client boundary.
- `frontend/components/browse/browse-quota-note.tsx`: The hero's quota line, as a client island. It reads the live allowance from the provider so the line says what the server says now, rather than what it said when the page was rendered.
- `frontend/tests/browse-quota-live.test.tsx`: Seven tests for the live allowance: the note moves after a save, the wall appears on the other cards, the client never counts its own presses, a refused save moves nothing, a failed refresh keeps the last known number, and a Pro account has no wall.

## Files Modified
- `backend/adapters/throttle/memory.py`: Split the counters out of the adapter into InMemoryThrottleStore. An adapter built with a clock owns its own store; one built without a clock shares the process-wide one. The Free save cap was inert under the default ADAPTER_MODE=fake because every registry-built adapter got a fresh counter dict.
- `backend/apps/identity/services/throttle.py`: Added reset_sign_in_throttle, which clears the sign-in windows for a set of accounts and an address. It clears the counters, not the rules: ten sign-ins an hour are still ten.
- `backend/config/adapters.py`: Added THROTTLE_ADAPTERS and a throttle override on adapter_paths, so one port's counter store can be chosen without changing ADAPTER_MODE's meaning for the ports that need credentials.
- `backend/config/env.py`: Added throttle_adapter (memory | redis). The throttle is the one port whose state the whole stack shares, so the local stack uses the real Redis adapter rather than a per-process fake.
- `backend/config/settings.py`: Passed env.throttle_adapter into adapter_paths.
- `backend/config/management/commands/seed_browse_catalog.py`: Four accounts instead of two (the no-city account and a second Free account), a --reset-saves flag that starts a test run from an empty Pulse, and a sign-in allowance reset. The saved rows are cleared through unsave_event, not a model delete.
- `backend/config/browse_seed.json`: Added the free-saver and no-city accounts, with the reasons they exist written into the file.
- `Makefile`: Added seed-browse-for-test, which seeds and clears the accounts' saved events; make test-e2e now depends on it.
- `.env.example`: Documented THROTTLE_ADAPTER and why this one port overrides ADAPTER_MODE.
- `frontend/lib/browse-labels.ts`: quotaNote no longer says 'resets in 0s' when there is no open window. It says 'allowance full'. The 24-hour window starts with the first save, so before that there is no countdown to announce.
- `frontend/components/browse/browse-save.tsx`: Reads the live allowance from the provider, refreshes it after a save, and renders the inline wall line with its Upgrade link when the allowance is already spent -- not only when the server refuses a press.
- `frontend/components/browse/browse-hero.tsx`: The quota line became the BrowseQuotaNote island, because the allowance moves while the reader is on the page.
- `frontend/app/browse/page.tsx`: Wrapped the hero and the search island in the BrowseQuotaProvider, so the note and the buttons read one shared number.
- `frontend/e2e/browse.spec.ts`: The full path -- sign in, navigate from the sidenav, two tiers, keyword filter, tag: literal filter, clear, save, see it saved -- plus the design's locks: no chip rail, no count badges, no upsell carousel, no horizontal scroller, one Save button per card, and no social proof, Sign-up CTA or SEO footer.
- `frontend/e2e/browse-quota.spec.ts`: The Free quota wall (refused inline, with the upgrade copy and no modal) and the Pro account's repeated saves with no cap. Added the allowance-wording assertions: 'allowance full' before the save, a real countdown after it.
- `frontend/e2e/browse-emptiness.spec.ts`: The city's emptiness is now tested against the seeded no-city account rather than asserted as a contract.
- `frontend/e2e/helpers.ts`: Added seedFreeSaverAccount, seedNoCityAccount, navigateToBrowseExpectingEmpty and renderedText -- the last walks the rendered text nodes only, so a forbidden phrase is not found in Next.js's RSC payload or in the shell's closed menus.
- `frontend/lib/site-url.test.ts`: The two 'unset' tests now delete the key instead of stubbing it undefined. Vitest 5.0.5's stubEnv(name, undefined) is not idempotent, so the second unset was silently ignored and the 'unset' case quietly became the 'configured' case.
- `frontend/tests/browse-labels.test.ts`: Two tests: a zero reset claims no countdown, and a real countdown is still counted down once the window is open.
- `frontend/tests/browse-boundary.test.ts`: Five anti-pattern rules that had no enforcement, plus the two new surface files added to the scanned list, and the client-module rule updated from two islands to four.
- `frontend/tests/browse-save.test.tsx`: Assertions for the wall's inline line and its Upgrade link.
- `backend/tests/conftest.py`: An autouse throttle fixture: one in-memory adapter with an injected clock per test, patching both consumers of the port. Isolation has to mean something once the gate actually works.
- `backend/tests/identity/conftest.py`: The package's throttle fixture now covers both consumers of the port.
- `backend/tests/adapters/test_throttle.py`: Five tests for the shared store: two clockless adapters share their counters, the store survives the adapter being rebuilt, a clocked adapter keeps its own, an explicit store is used verbatim, and reset_default_store clears every key.
- `backend/tests/identity/test_throttle.py`: Tests for reset_sign_in_throttle: the allowance comes back, the limits do not change, the address is normalised before it is keyed, and the other operations are left alone.
- `backend/tests/config/test_adapters.py`: Tests for the throttle override: it swaps only the throttle port, and the named implementation satisfies the port.
- `backend/tests/config/test_env.py`: Tests for throttle_adapter: it follows the mode by default, accepts the two stores, and rejects an unknown one.
- `backend/tests/config/test_seed_browse_catalog.py`: The seed file names four accounts; the seed puts the sign-in allowance back without changing the limits; and --reset-saves clears the saved rows.
- `backend/tests/personalization/test_saved_events_api.py`: The listing tests use a Pro account, because the Free cap is one save a day and a test that saves two events as a Free user is testing the cap.

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


## Summary

- Work items completed: 7
- Files created: 3
- Files modified: 29
- Tests added: 97
- Coverage: 98.6%
- Completed: 2026-11-12T17:08:29.744Z
