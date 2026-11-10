---
run: run-eventpulse24-025
work_item: frontend-pulse-card-state
intent: event-state-sync
generated: 2026-11-10
mode: confirm
---

# Implementation Walkthrough: The Pulse Card has to be able to say what happened to the event

## Summary

FR-53's detection has been in the backend since `digest-card-state-fields`. FR-54's notice
has been composed and sent since `notice-composition-and-email`. **Neither one reaches the
reader.** The Pulse Card reads neither `status` nor `is_sold_out`, so a card whose event
had been cancelled — or sold out, or postponed — renders exactly as a live one does, and
the reader is told nothing.

**This item is the card's state treatment.** One shared table of the words, one badge with
three states, and the card rendering it.

### The four decisions this item actually turns on

**1. The design system has a sold-out badge and no cancelled or postponed one.** That is a
real gap in `DESIGN.md` §`component.badge.soldout` and in the mockup, which covers only
sold out. So the item **extends the sold-out anatomy** rather than inventing a second
pill: the same `{color.surface.subtle}` fill, the same 1px `{color.border.strong}` stroke,
the same `{radius.subtle}`, the same ink label. **The three states differ by their glyph
and their label, and by nothing else** — no new colour token, no new spacing token, no new
CSS variable. A second pill for cancellation would have been a second visual language for
one kind of fact.

**2. The sold-out glyph cannot be the design's `●`.** This is a collision *inside the
design document*, and it is the reason the item needs an amendment at all.
`component.indicator.conflict` is "a 6px **filled circle** in `{color.warn.amber}`", and
`{color.signal.warn}` and `{color.warn.amber}` are **the same hex** in both themes
(`#8a5a1c` light / `#d8a86a` dark) — so a `●` in the badge and the conflict indicator
would be the same shape in the same colour at the same scale, **in the same card**.
`DESIGN.md` already requires the conflict indicator to be "distinct in shape and position
from the Source Badge and Confidence Pulse", and the badge is a third signal on that card.
So the sold-out glyph is **hollow** (`⊘`) where the conflict dot is solid. Cancelled is `✕`
(a strike); postponed is `↦` (a deferral) — deliberately **not** a clock, because a
postponed event has no new time yet (`POSTPONED = "postponed"  # date to be announced`).

**3. The lifecycle state wins over the sold-out flag.** `DigestCardOut`'s own docstring
says "An event can be `scheduled` and sold out at the same time, so the two are not
collapsed into one 'state' enum" — so the frontend keeps **both** fields, and only the
*badge* picks one. It picks the lifecycle state: a badge reading "Sold out" on a
cancelled event would invite a reader to wait for tickets for an event that is not
happening.

**4. The badge is `aria-hidden`, and the card's link carries the fact.** The design had it
both ways — the badge named *and* the card's `aria-label` naming — and the build had to
pick one. It picks the link, because the link is the tap target and the only focusable
thing in the card. The **visible** label stays: it is what makes the state legible at a
glance and what satisfies WCAG 1.4.1.

## Structure Overview

```text
┌──────────────────────────────────────────────────────────────┐
│  lib/event-state.ts                    (the one table)      │
│                                                              │
│  STATUS_LINES          cancelled / postponed — the sentences│
│  statusLineFor()       the sentence, or null                │
│  SOLD_OUT_LINE         "Sold out — tickets no longer …"    │
│  STATE_LABELS          sold out / cancelled / postponed     │
│                                                              │
│  cardStateFor()        the two facts → ONE badge state      │
│                        the lifecycle state wins             │
│                        an unknown status → null             │
└────────────────────────────┬─────────────────────────────────┘
                             │ imported by
                             ▼
┌──────────────────────────────────────────────────────────────┐
│  components/state/event-state-badge.tsx    (the badge)       │
│                                                              │
│  ⊘ Sold out     ✕ Cancelled     ↦ Postponed                  │
│                                                              │
│  one colour, one pill, three figures                         │
│  aria-hidden — the card's link names the state                │
└────────────────────────────┬─────────────────────────────────┘
                             │ rendered by
                             ▼
┌──────────────────────────────────────────────────────────────┐
│  components/digest/pulse-card.tsx         (the card)         │
│                                                              │
│  ┌──────────────────────────────────────────────┐            │
│  │ kicker          conflict · confidence · src  │ trust row  │
│  ├──────────────────────────────────────────────┤            │
│  │                            [ ⊘ Sold out ]     │ its own row│
│  │ Brooklyn Symphony open rehearsal              │ title row  │
│  └──────────────────────────────────────────────┘            │
│                                                              │
│  the link's aria-label ends with the state's name            │
│  the share control is rendered from public_slug, NOT state   │
└──────────────────────────────────────────────────────────────┘
```

## Architecture

### The server states the fact (AD-10)

**The card never computes a state.** It reads `card.status` and `card.is_sold_out` — two
separate fields, exactly as `DigestCardOut` sends them — and picks which one the *badge*
shows. The frontend does not infer "cancelled" from a missing event, nor "sold out" from
a missing ticket, and it does not treat a `null` status as a state.

### The one table

**The sentences used to be triplicated.** `public-event-page.tsx` held a local
`STATUS_LINES` table; the city card and the Detail screen each carried a literal copy of
the sold-out sentence. Every one of them now reads `lib/event-state.ts`, and
`tests/event-state.test.ts` fails if a literal copy reappears — of a sentence *or* of a
label.

**The Detail screen was the odd one out, and it is fixed here.** It read only
`SOLD_OUT_LINE` and rendered **nothing** for a cancelled event, while the public page said
"Cancelled — this event is not happening." Two screens, two vocabularies, one fact. The
Detail screen now reads the same table, and its lifecycle line takes precedence over the
sold-out line for the same reason the badge's does.

### The vocabulary guard

`tests/event-state.test.ts` parses `Event.Status` out of
`backend/apps/ingestion/models.py` and compares it with the frontend's table. **There are
two `class Status` choices classes in that file** — `Source.Status` (`active` / `paused`)
and `Event.Status` (the event's lifecycle) — and the parser scopes to `class Event` first,
because a regex that took the first match would have read the registry's vocabulary and
compared the wrong thing.

`scheduled` and `superseded` are **silent by design**: a card that has not been cancelled
does not need to say so.

## Key Implementation Details

### The three glyphs

| state | glyph | why |
|---|---|---|
| sold out | `⊘` | a slashed circle — "no more of this"; **hollow**, because the conflict dot is solid |
| cancelled | `✕` | a strike — the ordinary mark for "not happening" |
| postponed | `↦` | a deferral — a movement in time, which is exactly what a postponement is |

**`↦` is right and the alternatives are wrong.** A clock (`◷`) would say "the time is
provisional", but a postponed event has *no* new time yet, so a clock would promise a time
that does not exist. `↦` promises only a movement.

### Why the badge is not in the trust row

The trust row already holds the conflict indicator, the five-dot confidence pulse and the
source badge, and it is a `flex items-center gap-2` that **does not wrap**. A fourth
element with a visible label would overflow a 360px viewport. So the badge gets **its own
row, immediately above the title row**, right-aligned — the right-side zone `DESIGN.md`
names, and a *different place* from the conflict mark as well as a different shape.

### Why the badge is `aria-hidden`

A browse-mode screen-reader user reaches the badge and hears "Cancelled"; then reaches the
link and hears "Cancelled" again. **The same fact, twice, in one card.** The badge is
hidden from the accessibility tree and the link carries the fact, because the link is what
the reader activates. The visible label stays — hiding a badge from a screen reader hides
it from nobody, and it only stops the announcement happening twice.

### Why the share control survives a cancellation

**This one was wrong in the first draft, and the review caught it.** The card's comment
said a cancelled event has no public page, so its share control is gone. **The backend does
the opposite**: the catalog's public read excludes **only** `SUPERSEDED`, so a cancelled
event is still published, still has a public page, and the server sends its `public_slug`.

So the share stays — a reader who wants to tell a friend that an event was cancelled needs
a link to the page that says so — and the comment now says what the server actually does.
**The control is rendered from `public_slug` and never from the state**, so if the catalog
ever stops publishing cancelled events, the server sends `null` and the control disappears
on its own, with no frontend change.

## Security Considerations

**Nothing new.** The card reads two fields the server already sends, and it renders no new
control. The badge is a `<span>`: there is nothing to dismiss and nothing to do about a
cancelled event, so it is never a focus stop and never in the tab order.

The one thing that *changed* for assistive technology is that the badge is now
`aria-hidden` — which **removes** an announcement rather than adding one, and leaves the
card's accessible name carrying the state in a place the reader activates.

## Performance Considerations

**Nothing measurable.** The badge is one extra element in a card that is already a dozen
elements deep, and it renders only when the server said there is a state to show — a card
with no state renders **no** badge element at all.

The shared table replaced three literal copies of a sentence, so the bundle is very
slightly smaller.

## Decisions Made

| Decision | Why |
|---|---|
| Extend the sold-out anatomy; do not invent a second pill | One kind of fact, one visual language. A second pill for cancellation would have been a second language for the same sentence |
| Three states, three **glyphs**, one colour | The conflict indicator's amber and the badge's amber are the same hex, so colour cannot tell them apart — and a badge whose states differ only by colour would be unreadable beside the conflict mark |
| `⊘` rather than the design's `●` | `●` is the conflict indicator's shape, in the conflict indicator's colour, at the same scale, in the same card |
| `↦` rather than a clock | A postponed event has no new time yet; a clock would promise one that does not exist |
| The lifecycle state wins over the sold-out flag | A badge reading "Sold out" on a cancelled event invites a reader to wait for tickets for an event that is not happening |
| The badge is `aria-hidden`; the link carries the state | The link is the tap target and the only focusable thing. Two namings of one fact is an announcement twice |
| The badge is in its own row, not the trust row | The trust row does not wrap; a fourth visible label overflows a 360px viewport |
| The share control is rendered from `public_slug`, never from the state | The card never guesses the server's publishing policy (AD-10) |
| An unknown status shows nothing | The vocabulary is the backend's; rendering one as "unknown" would invent a claim (ASSUMPTION-9) |

## Deviations from Plan

**1. The badge is `aria-hidden`, where the design asked for an `aria-label`.** `DESIGN.md`
and `EXPERIENCE.md` both asked for `aria-label="Sold out"` on the badge, *and* for the
Pulse Card's own `aria-label` to name the state — two namings of one fact. The design was
amended (A-22) rather than the build contradicting it silently.

**2. The badge sits in its own row, not "top-right of the title row".** The trust row is
at capacity, and the design's own text says the badge is not in the trust row. The design's
wording was amended to match the build.

**3. The typography follows `DESIGN.md`, not the mockup.** `DESIGN.md` says weight 600 and
`0.06em`; the mockup says 600 and `0.08em` in a mono family; the build had weight 500 and
`0.08em` in the body family. It is now weight 600, `0.06em`, and the mockup's mono family
is explicitly not adopted. Recorded in A-22.

**4. `DESIGN.md`'s Do's-and-Dont's row said `event.status = sold_out`, which the backend
cannot send.** `sold_out` is the boolean field `event.is_sold_out`; `Event.Status` is
`scheduled | postponed | cancelled | superseded`. The row was amended.

**5. The Detail screen gained the cancelled and postponed lines.** Not in the plan — it was
found by the review, and it was a two-surface vocabulary that should not have survived the
item that was specifically about unifying the vocabulary.

## Dependencies Added

**None.** No new package, no new dependency, no new token, no new CSS variable.

## How to Verify

**Static checks**

```bash
cd frontend
npx tsc --noEmit      # clean
npx eslint .          # clean
```

**The new and changed tests**

```bash
npx vitest run components/digest/pulse-card-state.test.tsx \
  tests/event-state.test.ts tests/event-state-badge-boundary.test.ts \
  app/events/[id]/page.test.tsx tests/digest-home-a11y.test.tsx
```

**The whole frontend suite** — `npx vitest run`: **102 files / 1663 tests, 0 failed**. The
baseline at `HEAD` is **99 files / 1577 tests** — **86 net new tests, zero new failures**.

**Node 24 is required.** `package.json`'s `engines` says `>=24.15`; under Node 20 every
component test file is *silently skipped* and the suite reports a false pass of "398
passed". Check `node -v` before trusting a green run.

**The backend** — untouched by this item. The full suite stands at **5637 passed, 16
failed**, the same sixteen date-expired fixture failures as the established baseline.

### The end-to-end path (manual, against a running server)

Sign in → the digest home shows a Pulse Card → the card's event has been cancelled in the
catalog → the card shows a `✕ Cancelled` badge → the badge sits above the title, right
aligned → the card's link announces "…Cancelled" → the card still offers its Share
control, because the server still sends a `public_slug` → the Detail screen for that event
shows "Cancelled — this event is not happening."

## Test Coverage

| File | Tests | What it holds |
|---|---|---|
| `components/digest/pulse-card-state.test.tsx` | **31** | Per state: the label, the accessible name, the affordances, the coexistence with the conflict indicator, the unknown-status case, the two-facts-at-once precedence, the glyph shapes, and that the badge is not a control |
| `tests/event-state.test.ts` | **31** | The backend's `Event.Status` against the frontend's vocabulary; `cardStateFor`'s precedence; the five consuming surfaces hold no literal copy of a sentence *or* a label |
| `tests/event-state-badge-boundary.test.ts` | **18** | The rules a rendering test cannot see: no literal hex, no raw `rgb()`/`hsl()`, every colour from a token, no motion class, the label in ink, the design's weight and tracking, three different glyphs, and none of them the conflict indicator's filled circle |
| `app/events/[id]/page.test.tsx` | **+4** | The Detail screen's lifecycle line, the unknown-status case, and the precedence over the sold-out line |
| `tests/digest-home-a11y.test.tsx` | **+2** | axe-core, over the three states together and over sold-out-and-conflicted |

### The mutations

**9 of 9 caught.** Each was applied to the source, the suite run, and the source restored.

| # | Mutation | Caught by |
|---|---|---|
| 1 | The lifecycle precedence is inverted | 4 tests |
| 2 | An unknown status falls back to "cancelled" | 1 test |
| 3 | All three glyphs become the same character | 5 tests |
| 4 | The sold-out glyph becomes `●` — the conflict mark | 4 tests |
| 5 | The label is put in the signal colour instead of ink | 2 tests |
| 6 | The badge loses its `aria-hidden` | 1 test |
| 7 | The state is dropped from the card's accessible name | 4 tests |
| 8 | The badge is not rendered at all | 17 tests |
| 9 | The Detail screen drops the lifecycle line | 3 tests |

**Mutation 1 survived the first draft, and that is the most useful thing in this run.** The
item's own reasoning says the lifecycle state must win over the sold-out flag, and **no
test covered it** — the card was never rendered with both facts at once. The rule was
documentation and nothing else. The fix added a `describe` block for a card that is *both*
sold out and cancelled, plus four direct `cardStateFor` cases: **the rule is now pinned by
six tests instead of asserted in a comment.**

## Ready for Review

### What this item does not do

- **The Detail Screen's "Save & Reminder" actions are not removed for a cancelled event.**
  `EXPERIENCE.md` says the sold-out state replaces them with a calm line, and the Detail
  screen already does that for a sold-out event. For a **cancelled** event it does not.
  That is the Detail screen's own state treatment, and it belongs to
  `frontend-digest-strip-and-detail-banner` — the next item.
- **The digest strip and the Detail banner are not built.** They are
  `frontend-digest-strip-and-detail-banner`, and they need the API this run already has.
- **The backend is unchanged.** Nothing here needed a schema change; the two facts were
  already on `DigestCardOut` and on `EventDetailFactsOut`.
