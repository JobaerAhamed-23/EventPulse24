---
id: browse-collecting-states
title: The four honest states on Browse and the city page
intent: city-picker-and-auto-collection
complexity: medium
mode: confirm
status: completed
depends_on:
  - city-provisioning-service
created: 2026-11-20
run_id: run-eventpulse24-057
completed_at: 2026-11-21T02:39:00.549Z
---

# Work Item: The four honest states on Browse and the city page

## Description

Make the surface say something different and true for each of the four ways a city can
have nothing on it. Today there is one quiet empty state — "Nothing nearby tonight" —
and it is the right answer to exactly one of the four.

The heading always names the user's own city. It never shows another city's events.

## Acceptance Criteria

- [ ] The Browse payload carries the city's provisioning status alongside the existing `city_missing` flag.
- [ ] **Collecting** renders "Events in {city}" with "We're collecting events for {city} — check back soon."
- [ ] **Live but quiet** renders the existing `BrowseEmpty` ("Nothing nearby tonight") unchanged — a covered city that is simply quiet must not be told its sources failed.
- [ ] **No sources** / **yielded nothing** renders "We couldn't find any event sources for {city}." and carries the coverage-request control.
- [ ] **Paused** renders the same honest line as "no sources" and keeps the city selected.
- [ ] The heading names the user's stored city in every one of these states.
- [ ] `city_missing` keeps its current behaviour: no city set still shows the quiet state with "Change city", and is not confused with a provisioned city that is collecting.
- [ ] The collecting state is `role="status"` / `aria-live="polite"`, because it is a state the reader is waiting on.
- [ ] The FR-27 city page degrades the same way, and its existing "coming soon" copy for `is_published=False` is reconciled with these states rather than left to contradict them.
- [ ] Browse's layout, its two tiers and its search box are unchanged. `BrowseSearchEmpty` is untouched — a query that matched nothing is still a different answer from a city that has nothing.
- [ ] Each state has a test that fails if the states are collapsed into one.

## Technical Notes

`browse-states.tsx`'s own docstring is the specification for this item: *"They are four
different things and must not share a treatment"* and *"telling a user their city is empty
because a request failed is a lie about the world."* That file already distinguishes two;
this item takes it to four.

Watch the heading-level rule it documents: the zero-events state **replaces** the hero and
so carries the `<h1>`, while the no-match state sits under the hero's `<h1>` and is an
`<h2>`. The new states replace the hero, so they are `<h1>`.

The FR-27 city page's `is_published` threshold (`event_count > 5`) is a *different*
question from provisioning status, and a city can be provisioned-and-live with four
events. Decide explicitly which message wins when they disagree; do not let two
independent conditions both render copy.

## Dependencies

- city-provisioning-service
