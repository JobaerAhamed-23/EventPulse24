---
id: personal-event-reminder-plan
title: Reminders for a Personal Event — The Picker's Other Half
intent: unwired-surfaces
complexity: medium
mode: confirm
status: completed
depends_on: []
created: 2026-11-13
run_id: run-eventpulse24-031
completed_at: 2026-11-13T07:27:39.768Z
---

# Work Item: Reminders for a Personal Event — The Picker's Other Half

## Description

`GET`/`PUT /api/reminders/{target_kind}/{target_id}` accept `target_kind` of
`personal_event` **or** `saved_event` (`delivery/api.py:81`). The UI only ever sends the
second: `ReminderPicker` is mounted exactly once, at
`app/events/[id]/reminders/page.tsx:93`, with a hard-coded `targetKind="saved_event"`.

So a personal event cannot be given a reminder plan, and FR-20 ("Personal Event Reminder
Defaults") has no reachable surface — while `personal-event-reminders-desktop.html` exists
and was written **specifically** to close FR-20's design gap. Its own header says so:

> FR-20 Personal Event Reminder Defaults. Closes the TRACEABILITY.md open gap ("PARTIAL
> (inferred only)") — FR-20 had no design anywhere: `reminder-picker-desktop.html` is
> self-tagged FR-9 (reminders on *saved public* events)… The requirement was being built
> from FR-9's UI by adjacency.

The matrix then upgraded FR-20 to `FULL` on the strength of that mockup. The mockup is real;
the screen is not.

## Acceptance Criteria

- [ ] A personal event's reminder plan can be read and saved from the UI, through
      `GET`/`PUT /api/reminders/personal_event/{id}`
- [ ] The surface is reachable from where a user manages a personal event — the edit sheet,
      the timeline block, or a route of its own; the choice is stated with its reason
- [ ] `ReminderPicker` is reused, not reimplemented — it already takes `targetKind` as a prop
      (`reminder-picker.tsx:299`)
- [ ] A personal event with **no** stored plan shows the defaults FR-20 specifies, and the
      surface says they are defaults rather than presenting them as a saved choice
- [ ] Saving a plan on a personal event does not touch any saved-event plan, and a test with
      one of each proves it
- [ ] A refused save is reported distinctly from a network failure, matching the picker's
      existing behaviour
- [ ] Tests cover: read, save, the no-plan default state, the two-target isolation, and a
      refused save
- [ ] Every test is verified by a mutation probe that makes it fail

## Technical Notes

- **`/events/[id]` is not the route for this.** That route serves catalog events — a minted
  slug renders the public page, everything else renders the signed-in Detail Screen reading
  `readEventDetail`. A personal event id is not a catalog event id and will not resolve
  there. Either a new route or an in-sheet surface; decide and say why.
- **Check what `read_plan` returns for a personal event with no plan.** `delivery/api.py:86`
  calls `read_plan(…)`; whether that 404s or returns defaults changes the UI's empty state
  entirely. Read the service before designing the screen.
- **FR-20 is about *defaults*.** The mockup is the authority on what those are and how they
  are presented. Do not infer them from FR-9's saved-event picker — inferring from FR-9 is
  precisely the error the mockup was written to correct.
- **The reminders route has a `loading.tsx`** (`app/events/[id]/reminders/loading.tsx`). If
  this becomes a route, it gets one too.

## Dependencies

- (none)
