# Plan: detail-screen-conflict-prompt

**Work item**: `detail-screen-conflict-prompt` · **Mode**: confirm · **Run**: `run-eventpulse24-022`

The Detail Screen answers a clash where it is found. Today a clashing Save says
*"It overlaps "Dentist" on your calendar."* — a stopgap, because nothing could resolve a
saved-vs-personal pair. `saved-public-conflict-resolution` made it resolvable; this work
item makes the user **choose**.

---

## What already exists (read, not assumed)

**The backend already returns 409.** `POST /api/personal/saved-events/{catalog_event_id}`
raises `SchedulingConflictError` with `details.conflicts[0]` — a `ConflictOut` carrying
`pair_id`, `kind`, `actions`, `new_side` (the save) and `other_side` (the personal event).
The save row is written **before** the 409 is raised, so the pair is already `active` when
the client sees it. `actions` for a saved side = `resolutions_for_side(kind, SAVED_EVENT)` =
**`keep_both`, `edit_new`, `skip_public`** — exactly the three the work item asks for.

**So the backend needs one change, not two.** The 409 is done. What is missing is the
*indicator* path: `DetailPersonalOut` has no conflict field, so the Detail Screen cannot
know an event is already in an active pair without a second read.

---

## Decisions

### D1 — The prompt is the existing `ConflictResolution` sheet, not a second one

The work item's Technical Note says so, and it is right: the sheet already owns the
"no dismiss", the focus-to-heading, the `"Schedule conflict. Three choices."` announcement,
and the delete-confirmation step. A second prompt would be a second copy of all of it.

**The sheet needs one change**: its copy is personal-event-shaped. It says *"You've already
saved {other.name}"* — which is right for the personal-events panel (where the *saved* event
is the other side) and **wrong** here, where the thing being saved is the new one and the
personal event is the other side. The sheet will take a `newSideKind` and say the right
sentence for each.

### D2 — The sheet's labels come from `lib/conflict-wording.ts`, in **both** modes

The module built by `frontend-conflicts-page` already holds the two vocabularies:

| | Prompt (relative) | Review (contextual) |
|---|---|---|
| move | "Edit the new one" | "Move Work standup" |
| skip | "Skip the public event" | "Skip Designers coffee chat" |

The work item's AC asks for **"Move {personal event} / Skip {this event} / Keep both"** —
that is the *review* vocabulary, but on a **prompt**, where the pair is not symmetric and
the "new" side is the save.

**The resolution.** The Detail prompt's labels name the event **the action acts on**, which
is the same rule the review screen follows and the same `reviewActionLabel` function. But
the Detail prompt has a **known new side** (the save the user just made), so the sheet can
say "Skip *this event*" about the event on screen, and "Move *Work standup*" about the
personal event. That is exactly `reviewActionLabel(resolution, subject)` with `subject`
being the **target** side's name — and the target side is already computed by
`actionSide()`.

**So the Detail prompt uses `reviewActionLabel`/`reviewActionAria`**, not
`RESOLUTION_LABELS`. The prompt-relative strings stay for the personal-events panel, where
the new side genuinely is "the new one".

### D3 — The request names the side, from `actionSide()`

`PersonalEventsPanel.resolve()` hardcodes `side: { kind: "personal_event", id: pending.id }`.
That is right there and **wrong here** — for `skip_public` the server requires the
**saved** side (`_target_side_kind`), and naming the personal side is refused with
`IllegalResolutionError`.

**The Detail prompt uses `actionSide(resolution, newSide, otherSide)`** — the same rule the
review screen uses, already tested, and already quoted from the backend.

### D4 — The 409 opens the prompt; the pair is already saved

The save succeeded. The 409 says *"saved, but now choose"*. So the Save button reads
**"Saved to your Pulse"** and the prompt opens over it. The stopgap line is gone.

### D5 — The three actions do three different things

| Action | Effect on the Detail Screen |
|---|---|
| **Move {personal}** | Opens the personal event in the **edit sheet** with the conflicting time highlighted — the same driven `highlightStartTime` prop the conflicts page uses. |
| **Skip {this event}** | **Un-saves** the event. The Save button returns to "Save to Pulse". |
| **Keep both** | The event stays saved, the indicator stays, and the prompt closes. |

**"Move" needs the personal event's full record** — the edit sheet edits *personal*
events, and the 409's `other_side` carries only `{kind, id, name, start_time_utc,
end_time_utc}` — no zone, no location, no notes. The edit sheet's form needs
`start_time_tz` for the time picker.

**So the Detail prompt reads the personal event** before opening the sheet:
`GET /api/personal/events/{id}` → `PersonalEventOut`. That is one extra read, only on the
"Move" path, and it is what makes the sheet's time picker correct.

### D6 — The indicator needs one backend contract change

`DetailPersonalOut` gains `conflict: DetailConflictOut | None = None`:

```python
class DetailConflictOut(Schema):
    pair_id: UUID
    kind: ConflictPairKind          # "time" | "duplicate"
    other_side: ConflictSideOut     # the other side, from the caller's point of view
    actions: list[ConflictAction] = []
```

**Why not `ConflictPairOut`?** That carries `left`/`right` — the pair's *stored* order,
sorted by id, which is symmetric and so does not say which side is "the one on screen".
The Detail Screen knows which event it is showing, so it needs the **other** side named
directly. This is `ConflictOut`'s shape (which already has `new_side`/`other_side` and
`actions`), narrowed to what the Detail Screen needs.

**`actions` is `resolutions_for_side(kind, side_kind=SAVED_EVENT)`** — the saved side's
three (`keep_both`, `edit_new`, `skip_public`) — because the Detail Screen acts on the
**saved** side. The union across the pair would offer `delete_new`, and deleting a personal
event is not something the Detail Screen should offer.

**The anonymous path stays clean.** The query sits inside the signed-in branch of
`read_event_detail`; `personal` is `None` for an anonymous caller, so the payload has
nothing for the pair (AD-12). The existing "the personal alias is never queried for an
anonymous caller" test guards this.

### D7 — The indicator is a button, and the prompt is one component

`ConflictIndicator` (in `pulse-card.tsx`) is a non-interactive `<span role="img">`. The
Detail Screen's must **open the prompt**, so it is a `<button>` with an accessible name
that says what it does: *"Schedule conflict. Choose how to handle it."*

**It is extracted** into `components/conflicts/conflict-indicator.tsx` and used by both the
Pulse Card (as the non-interactive span it is today) and the Detail Screen (as a button) —
one indicator, one definition of the 6px amber ring.

### D8 — The prompt's live region and focus are the sheet's, unchanged

The sheet already moves focus to its heading and announces *"Schedule conflict. Three
choices."* The work item's AC asks for exactly this. Nothing to add — but a test must pin
it on the Detail path, not just on the panel's.

### D9 — A failed write leaves the prompt open

If the resolve POST fails, the prompt **stays open** with a calm line, and the pair stays
active. A prompt that closes on a failed write would tell the user the conflict is handled
when it is not.

### D10 — The stopgap line is deleted, and its test with it

`detail-actions.tsx:110–114` goes. So does the assertion in `detail-actions.test.tsx:123`
that expects *"It overlaps "Dentist" on your calendar."*. The boundary test
(`tests/event-detail-boundary.test.ts`) asserts the detail surface has no dismissal
control — the new prompt keeps that true, because the sheet is `dismissible={false}`.

---

## The shape of the change

### Backend

| File | Change |
|---|---|
| `backend/apps/personalization/schemas.py` | `DetailConflictOut` (new); `DetailPersonalOut.conflict: DetailConflictOut \| None = None` |
| `backend/apps/personalization/services/detail_read.py` | `DetailPersonal.conflict`; read the active pair for the user's saved row of this event, inside the signed-in branch only |
| `backend/apps/personalization/detail_api.py` | project `detail.personal.conflict` into the response |
| `backend/tests/personalization/test_event_detail_api.py` | the pair is in the payload; an anonymous caller gets `personal: null`; a pair with no saved side gets nothing |
| `frontend/lib/api/openapi.json`, `frontend/lib/api/schema.ts` | regenerated by `make client` |

### Frontend

| File | Change |
|---|---|
| `frontend/components/conflicts/conflict-indicator.tsx` | **new** — the extracted indicator; a span, and a button variant |
| `frontend/components/sheets/conflict-resolution.tsx` | take `newSideKind`; say the right sentence; take the label/aria source (prompt vs. review); take an `onResolve(resolution, side)` |
| `frontend/components/detail/detail-actions.tsx` | the 409 opens the prompt; the three actions; the stopgap line gone |
| `frontend/components/detail/detail-header.tsx` | the indicator, when the payload names a pair |
| `frontend/app/events/[id]/page.tsx` | pass the event's title/time and the payload's conflict to the client island |
| `frontend/lib/conflict-wording.ts` | maybe a helper for "Skip *this event*" — see below |

**One open question the plan settles.** The Detail prompt's "Skip" is about **the event on
screen**, so the label is *"Skip {this event's name}"* — the review vocabulary again
("Skip Designers coffee chat"). The AC's *"Skip {this event}"* is satisfied: the sheet
knows the event's name and says it. `reviewActionLabel("skip_public", subject)` already
produces exactly this. **No new strings.**

---

## Tests

**Backend**
- the payload names the pair, the other side and the three actions
- an anonymous caller gets `personal: null` and **no pair query**
- an event with no saved row has no pair
- a *resolved* pair is not reported (only an **active** pair is an indicator)

**Frontend**
- the 409 opens the prompt with the three actions
- **Move** posts `edit_new` against the personal side, and opens the edit sheet with the
  time highlighted
- **Skip** posts `skip_public` against the **saved** side, and the Save button returns to
  "Save to Pulse"
- **Keep both** posts `keep_both` against one of the pair's own sides, and the event stays
  saved
- a failed write leaves the prompt open
- the indicator is present when the payload names a pair, absent when it does not, and
  tapping it opens the prompt
- the prompt announces *"Schedule conflict. Three choices."* and moves focus to its heading
- the "It overlaps …" line is **gone** (the old assertion is deleted, and a new one says the
  line is absent)
- the regenerated client (`make client`) has the new shape

**Gates**: `make lint-web`, `npx vitest run`, the backend suite, `make client`, and the
axe-core gate with the prompt open.

---

## Risks

| Risk | Why it is handled |
|---|---|
| The pair names a **SavedEvent row id**, but the Detail endpoint is keyed by the **catalog** id | The read resolves the user's `SavedEvent` row by `(user_id, event_id)` first, then looks up the pair by that row's id — the same row `_is_saved` already finds. |
| The prompt might offer `delete_new` and delete a personal event | The Detail payload's `actions` is the **saved side's** set (`keep_both`, `edit_new`, `skip_public`), never the union. `delete_new` never appears. |
| "Move" opens the sheet with a time that has no zone | The sheet reads the **full** personal event first (D5), so the time picker has the zone. |
| The indicator's meaning leaks to anonymous users | `personal` is `None` for an anonymous caller, so there is no indicator. The pair query is in the signed-in branch. |
| The old test still expects the stopgap | It is deleted, and replaced with an assertion that the line is **absent**. |

---

## Out of scope

- The **digest**'s conflict indicator — it exists already and is unchanged.
- The **Timeline**'s conflict marker — unchanged.
- The personal-events panel's copy of the prompt — it keeps the prompt-relative wording
  (D2), because "the new one" is right there.
