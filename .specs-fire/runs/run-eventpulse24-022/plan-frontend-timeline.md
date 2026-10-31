# Implementation Plan: "The Timeline screen — week on desktop, day on mobile"

**Work item**: `frontend-timeline`
**Intent**: `timeline-and-conflicts`
**Mode**: confirm
**Depends on**: `timeline-week-api`

---

## Approach

`/timeline` is a **server component** that reads `GET /api/personal/timeline?week=…` through
the generated client with the visitor's cookies, and renders the week the server sent.

**The screen draws what it is given.** The server has already decided the week, the days,
the blocks, their order, and the conflict indicator. The page re-buckets nothing,
re-sorts nothing and re-decides no conflict — it renders `days` as they arrived.

**One page, two layouts, one source of truth.** The desktop grid and the mobile day view
are the same seven days, drawn differently. Both read the same `TimelineOut`; the mobile
view selects one day out of it. Neither computes a date that the server already computed.

---

### The four decisions this plan makes

The AC names five states, two layouts and two kinds of block. Four things needed a
decision rather than a lookup.

---

### D1 — The visible week lives in the URL, as `?week=YYYY-MM-DD`

The AC says so: *"The visible week lives in the URL (`?week=`), so reload, back and share
keep it."*

**What the parameter means.** The API's `week` is **any date in the wanted week** — the
server names that week's Monday and Sunday. The client therefore never has to know which
day of the week it asked for, and never computes a Monday.

**What the client sends.** The client sends the **Monday** it was given, when it has one.
That keeps the URL canonical: the same week always has the same URL, so the back button
and a shared link both land on the same address. The **mobile** day view adds `&day=` —
the day *within* the week — so `?week=2026-11-02&day=2026-11-04` is "the Wednesday of
that week".

**What is canonical when the day is missing.** The server's `days` array is the truth, and
it always has seven entries. The mobile view picks the day the URL names; if the URL names
none, it picks **today** if today is in the week, and otherwise the week's first day.

**The malformed week.** A `?week=` that is not a date is a 422 from the API. The page
treats it the way it treats any failed read — the error state. A malformed URL is not a
week, and the page does not guess one.

---

### D2 — The block's local time is rendered **in the user's zone**, with the event's own zone when it differs

The AC says *"name and local time"*, and the Technical Notes say *"Browser-zone vs
event-zone display follows the card rule (`cardTime`): render deterministic text on the
server."*

**The card rule.** `lib/detail-time.ts`'s `cardTime(startTimeUtc, zone)` renders the
instant **in the event's own zone** and appends that zone's short name. It exists so a
card renders the same string on the server and in the browser — a card formatted in the
browser's zone would print a different string on each side of the hydration boundary.

**The Timeline's rule is the same, with one addition.** The week is cut in the **user's**
zone, but a block's *time* belongs to the event's own zone. So:

- the block's time is rendered in **`start_time_tz`** — the event's own zone — by the same
  `cardTime` helper, so the server and the browser agree;
- **when the event's zone differs from the week's zone**, the event's own zone's name is
  what appears, because a time without its zone is a claim the reader cannot check.

**Why not the user's zone.** A public event in Berlin shown to a user in Los Angeles is
on a *different Los Angeles day* than its own clock suggests. Rendering it in the user's
zone would put it on the wrong cell — the day cell is decided by the server in the user's
zone, so the time in the user's zone would contradict the cell it sits in. The event's
own zone is the one that agrees with the event.

**The range.** A block shows `start – end` when it has an end, and the start alone when
it does not (`end_time_utc` is nullable — an open-ended event). The zone's short name is
appended once, at the end.

---

### D3 — The personal block opens the **Edit personal event** sheet; the public block links to `/events/:id`

The AC says: *"a public block links to `/events/:id`; a personal block opens the existing
**Edit personal event** sheet, and a saved edit refreshes the Timeline."*

**The public block is a link.** `next/link` to `/events/{id}` — the id is the **catalog**
event's id, which the API sends for exactly this reason.

**The personal block is a button.** It opens the existing `PersonalEventForm` sheet in
edit mode. That sheet lives inside the `PersonalEventsPanel` client island, and the
island owns the create → conflict → resolve → edit round trip.

**So the panel needs a way in.** `PersonalEventsPanel` currently owns its `editing` state
and has no way to be told *what* to edit. The panel grows an optional
**`editingEvent`** prop: given a personal event, it opens the edit sheet on that event.
The Timeline's own island passes the clicked block through.

**The refresh.** The panel already calls `router.refresh()` after a successful write, and
the Timeline is a server component — so a saved edit re-runs the server read and the week
re-renders with the new time. **No extra refresh call is needed**: the panel's existing
one does it.

**Read-only means read-only in the grid.** The block offers no drag, no inline rename and
no chevron. The only affordance is the one the AC names.

---

### D4 — The **empty week** and the **empty day** are different states

The AC names both: *"empty day 'Quiet day.' (`Text.Meta`, muted, centred); empty week
'Your week is quiet. Pulse Digest is the place to discover.' + one `Text.Meta` 'Open
Pulse Digest' link"*.

**A quiet day is a column with nothing in it.** "Quiet day." sits in the cell, centred, in
muted meta ink. It is a **cell state**, not a page state — the week still has six other
days.

**A quiet week is the page's own state.** When *every* day in the week is quiet, the
whole grid is replaced by the week's empty state: the headline, plus one `Text.Meta`
"Open Pulse Digest" link to `/`.

**The empty week hides the grid.** A grid of seven empty columns with seven "Quiet day."
lines is noise; the week's empty state says the one thing that is true. The desktop's
grid and the mobile's day view **both** show it — otherwise a mobile user would see only
"Quiet day." for a week with nothing in it, which says less than the week does.

**The week navigator stays.** The user can still go to another week from the empty week,
and the error state — a grid would be a lie about a week nobody read.

---

## The structure

```
/timeline
├── the header: "This week" + the week's range + the sub-line
├── the navigator: ← / Today / →   (desktop)   ← {date} → + Today pill   (mobile)
├── the grid (desktop, md+): seven columns, Mon–Sun
├── the day stack (mobile, sm): one day
└── the states: empty week, error
```

**The header's copy.** "This week" as the `Text.Headline` title, with the week's range
below it in `Text.Meta` — "Sep 7 – Sep 13" and the zone. The sub-line says it is
read-only, because the AC's read-only rule is a claim the user can check.

**The grid is one continuous grid.** `layout.timeline.grid` is
`grid-template-columns: repeat(7, minmax(0, 1fr))`. The **outer** corners use
`radius.timeline-cell` (10px); the inner shared edges are not rounded, so the seven
columns read as one grid rather than as seven cards. The dividers between columns are 1px
`border-subtle`; there is no horizontal border.

**The today column.** Today's cell gets `surface.subtle` fill and its date number is
terracotta — `Indicator.Today`'s treatment, the sanctioned terracotta use. The cell
carries `aria-current="date"`.

**The mobile view.** One day, with a centred `← {date} →` navigator and a "Today" pill.
The `←` / `→` links move one day and stay in the same week — and the last day of the week
does **not** roll into the next week, because the week is what the URL names. (`→` on
Sunday is inert; `←` on Monday is inert.)

**Both layouts are in the DOM.** The desktop grid is `hidden md:grid` and the mobile stack
is `md:hidden`, so one server render carries both and the CSS picks. **This is the same
approach the shell already uses** for its sidenav and bottom-tab bar, and it keeps the
page a **server component** — no client-side viewport measurement, no hydration mismatch.

---

## The blocks

```
┌──────────────────────────────────┐
│ ● Work standup          Personal │   ← 2px stripe (warm/cool), the label top-right
│   9:00 – 9:30 AM PDT             │   ← name in meta-md, time in meta-sm muted
└──────────────────────────────────┘
```

- **The stripe is 2px on the left edge**, `warm.personal` for a personal block and
  `accent.slate` for a public one (`color.cool.public` reads `--color-accent-slate`).
- **The label is visible text** — "Personal" / "Public event" — in the top-right corner.
  **Colour is never the sole carrier of meaning** (WCAG 1.4.1); the stripe and the label
  always come together.
- **The conflict indicator** is a 6px filled amber circle with
  `aria-label="Schedule conflict"`. It sits at the **top-left**, so it never covers the
  category label at the top-right.
- **Hover swaps the fill to `surface.subtle`** — actually, to `surface.inset`, which is
  what the mockup and DESIGN.md both specify ("Hover: fill swaps to `{color.surface.inset}`").
  **No chevron.**
- **The accessible name** is `name + time + "Personal" / "Public event"`, plus
  "Schedule conflict" when the indicator is on.

**The name.** A block whose catalog event has disappeared has **no name** — the API sends
`name: null`. The block still draws (the save is the user's, and its time is real), and
says **"Event no longer available"** in place of the name. That is the same state
`conflict_list` models, and it is the AC's "the client says 'event no longer available'
rather than showing a blank" — the API's own docstring says so.

---

## The states

| State | What it says | What it offers |
|---|---|---|
| Loading | the week-row skeleton | — |
| Empty day | "Quiet day." (`Text.Meta`, muted, centred) | — |
| Empty week | "Your week is quiet. Pulse Digest is the place to discover." | one `Text.Meta` "Open Pulse Digest" link → `/` |
| Error | "Couldn't reach Timeline. Try again." | one retry |

**The skeleton.** `loading.tsx` on the route: seven columns, each a stack of 3–5
`surface.elevated` rectangles 40px tall, with the `skeleton-pulse` animation. **No day
labels in the skeleton frame** — the spec says so.

**The error's retry** is a `Button.Primary` — a terracotta fill, which is a sanctioned
terracotta use (a failure that asks for a decision is a decision moment). It is a **link**
that re-navigates to the same URL, which makes the server render again — the same
"re-run the read on the server" rule the digest's error state follows.

---

## Files to Create

- `frontend/app/timeline/page.tsx` — the server component: the read, the header, the two layouts
- `frontend/app/timeline/loading.tsx` — the week-row skeleton
- `frontend/app/timeline/page.test.tsx` — the page's tests
- `frontend/components/timeline/timeline-grid.tsx` — the desktop 7-column grid and the mobile day stack
- `frontend/components/timeline/timeline-block.tsx` — one event block
- `frontend/components/timeline/timeline-states.tsx` — the empty week, the error, the skeleton
- `frontend/components/timeline/timeline-navigator.tsx` — the week and day navigators
- `frontend/components/timeline/timeline-grid.test.tsx` — the components' tests
- `frontend/components/timeline/timeline-panel.tsx` — the client island that owns the edit sheet
- `frontend/lib/timeline-read.ts` — the server-side read (the `digest-read.ts` pattern)

## Files to Modify

- `frontend/components/shell/sidenav.tsx` — Timeline becomes a real link (`href="/timeline"`)
- `frontend/components/shell/bottom-tab-nav.tsx` — Timeline becomes a real link
- `frontend/components/personal-events-panel.tsx` — the `editingEvent` prop
- `frontend/app/page.test.tsx` — the shell test asserts Timeline is inert; that assertion changes
- `frontend/styles/tokens.css` — `layout.timeline.grid` is named in DESIGN.md but **not emitted**

---

## The token gap

DESIGN.md names `layout.timeline.grid` — `grid-template-columns: repeat(7, minmax(0, 1fr))`
on desktop `md+` — and the token file **does not declare it**. The other tokens the
Timeline needs (`radius.timeline-cell`, `warm-personal`, `accent-slate`, `warn-amber`,
`accent-terracotta`, `surface-subtle`, `surface-inset`, `type-scale-meta-*`) all exist.

The token is added to `styles/tokens.css` rather than written as an arbitrary value in the
markup, because DESIGN.md names it and the token file is the contract. `styles/tokens.test.ts`
checks the **colours** against DESIGN.md, so adding a layout token does not disturb it.

---

## Tests

Every test names the rule it pins, in the house style.

### The read

- the read carries the visitor's cookies (the server-side session)
- a failed read is `unavailable`, not an empty week
- a missing base URL is `unavailable`, not a crash

### The page — desktop

- seven columns, Mon–Sun, in the server's order
- the header names the week's range and the zone
- today's column is marked with `aria-current="date"` and the terracotta date
- the navigator's `←` / `→` move one week and keep the week in the URL

### The page — mobile

- one day is shown, and the navigator is centred
- `←` / `→` move one day within the week
- the last day of the week does not roll into the next week
- the day is in the URL

### The blocks

- a personal block carries the warm stripe **and** the "Personal" label
- a public block carries the cool stripe **and** the "Public event" label
- the conflict indicator appears when the API says so, and not when it does not
- the accessible name is name + time + kind
- a block with no name says "Event no longer available"
- a public block links to `/events/:id`
- a personal block opens the edit sheet

### The states

- an empty day says "Quiet day."
- an empty week says "Your week is quiet." and offers one link to `/`
- the error says "Couldn't reach Timeline. Try again." and offers a retry
- the skeleton draws seven columns and no day labels

### Navigation

- Timeline is a real link in the sidenav and in the bottom-tab
- the active route is marked with `aria-current="page"`

### Accessibility

- axe reports zero serious or critical violations, in every state

---

## Gate Results (to be filled in as the work proceeds)

| Gate | Result |
|------|--------|
| `make lint-web` | |
| `make test-web` | |
| `make client` (no backend change — the schema is already generated) | |

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-022*
