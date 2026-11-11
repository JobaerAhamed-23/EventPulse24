# Design: The small flag — "Report this event" on the Detail screen

**Work item:** `frontend-report-control`
**Mode:** confirm (one checkpoint, before implementation)
**Depends on:** `event-report-api` (completed — the endpoint, the four categories, the throttle)

---

## 1. What this item is

FR-59 gives the signed-in reader a way to say "this is wrong". The API is built: `POST
/api/personal/event-reports` takes `{event_id, category}`, answers 201 with
`{category, reported}`, and refuses the sixth report in a day with a 429. This item builds
the **control**: a small flag in the Detail Screen's secondary action row, a modal with the
four categories, and the toast that says thanks.

**The event's own state never changes.** That is not a UI preference — the API says it, and
`event-report-api` proved it with a test. A report is a private signal to an editor. So
there is no "reported" badge, no greyed card, and no second read of the event after the
report. The report control's entire visible footprint is: the flag, the modal, and the
toast.

---

## 2. The three decisions this design has to make, and what it decided

The work item's acceptance criteria leave three things open. Each is decided here, on the
evidence, and each is pinned by a test.

### 2.1 Signed out: the flag is **hidden** — and it is hidden for free

**The decision.** An anonymous visitor does not see the flag at all. The flag is not
disabled, not greyed, and does not route to sign-in.

**Why this is the right answer, and not a convenience.** The acceptance criterion says the
behaviour must match "what Save does on the same screen". Save is **not shown** to an
anonymous visitor — and it is not shown because the whole action row is inside a
`personal` gate:

```tsx
// frontend/app/events/[id]/page.tsx:477
{personal ? (
  <>
    …
    <DetailActions eventId={event.id} … />
  </>
) : null}
```

`personal` is `read.detail.personal ?? null`, which is `null` for an anonymous reader. So
the **entire row** — Save, Share, and the new flag — is already gated. Placing the flag
inside `DetailActions` means the signed-out behaviour is not *implemented*; it is
**inherited**, and it cannot drift from Save's because it is the same `if`.

**The alternative, and why it loses.** Routing to sign-in would mean a sign-in wall for a
control whose whole point is a one-tap report. FR-59's user is a **reader who has an
account** — the endpoint is session-scoped and answers 401 otherwise. A visitor with no
account cannot report an event, so offering them the flag and then stopping them at a
sign-in form is a control that leads to a dead end. And the surface's own rule — the one
that already governs the reminder picker and the Save button — is *"a control that could not
be persisted is the same failure as a control that does nothing"*. A flag that always ends
at a sign-in wall is a control that does nothing, plus three extra taps.

**The test.** `frontend/app/events/[id]/page.test.tsx` renders the page in the anonymous
state and asserts the flag is absent. It is the same assertion style the file already uses
for the whole `personal` gate.

### 2.2 The rate limit is a **calm inline message inside the modal**, not a toast and not a raw error

**The decision.** The 429 renders as a line of ordinary prose **inside the modal**, under
the options and above the buttons. The modal **stays open**. The message is the API's own
words: *"You have reported enough events for today. Please try again tomorrow."*

**Why the API's words and not ours.** `lib/api-errors.ts` exists so the frontend quotes the
API verbatim: *"The frontend's job is to put those words on the screen, not to write its
own."* The 429 carries a `code` of `rate_limited` and a `message` written for the user by
`domain/errors.py`. We render it as it arrives.

**Why inline and not a toast.** A toast is a *transient* thing that appears and goes. The
rate limit is not transient in the user's frame — it lasts until tomorrow. A message that
disappears on a timer is a message the user will miss, and a missed rate limit is a
confusing dead button. An inline line is still there when the user looks back.

**Why the modal stays open.** The alternative — closing the modal and showing the limit as a
toast — would take the user's selection away from them. The selection is not a cost; it is
the only thing they typed, and losing it because the server said "not today" is the kind of
small rudeness this product is trying not to have. The modal stays open, the selection is
preserved, and the Submit button is left alone — **the server's limit is not the client's
to pre-empt**. (See §5.3 for what the mockup wanted here and why it does not ship.)

**Why not "a raw error".** The criterion says the limit must not render "as a raw error" —
not as a stack trace, not as `rate_limited`, not as a JSON blob. The `code` is for the
client's branching, not for the reader. What the reader sees is the sentence.

### 2.3 A network failure leaves the modal open, the selection preserved, with a retry

**The decision.** The modal stays open. The chosen category is still chosen. A calm line
appears: *"Couldn't reach Pulse. Try again."* — which is `OFFLINE_MESSAGE` from
`lib/api-errors.ts`, the one string the frontend owns, because in this case the API never
spoke. The Submit button is live, and pressing it again re-sends the same category.

**Why the selection survives.** The selection is the user's work. A failure that discards it
makes the user do the thing twice — which is the opposite of FR-59's "one tap submits". So
the category state lives in the component that owns the modal, and a failed submit does not
touch it. The test asserts the radio is still `aria-checked` after the failure.

**Why the toast is not used for this.** Same reason as the rate limit: a failure that the
user has to catch before it vanishes is a failure they will not catch. And the toast is
reserved for its one job — the success message, which is the only thing in this feature the
user is meant to read and then forget.

---

## 3. The layout: what sits where, and why

### 3.1 The flag goes in the secondary row, after Share

```tsx
// frontend/components/detail/detail-actions.tsx
<div className="flex flex-wrap items-center gap-3" data-detail-actions>
  {soldOut ? null : <button …>Save to Pulse</button>}
  <ShareControl slug={slug} title={eventName} origin={shareOrigin} />
  <EventReportControl eventId={eventId} eventName={eventName} />
  …
</div>
```

FR-59: *"Detail Screen, secondary action row (alongside Save, Share, Dismiss). Icon: small
flag glyph. Not a primary button."*

**After Share, not before.** The row reads left-to-right by weight: Save is the filled
terracotta primary; Share is the bordered secondary; the flag is the quietest thing on
the row. Putting the flag last is what makes it "not a primary button" — it is the
smallest, quietest mark in a row whose first item shouts. FR-25's Dismiss has no endpoint
and does not ship, so the row is Save · Share · flag.

**The flag is visually subordinate, and the test says so.** It is a text button in muted ink
with an underline — the same treatment `DetailMuteControl` uses (`min-h-[44px]
text-ink-secondary underline underline-offset-4`), which is the surface's existing
expression of "a quiet link-like control". No fill, no border, no terracotta. The
acceptance criterion's "visually subordinate to Save and Share" is asserted by the *absence*
of the tokens Save and Share have: the flag's classes must not contain `bg-accent-terracotta`,
`bg-surface-elevated`, or `border-border-subtle`.

**Why a text label and not an icon-only flag.** FR-59 says "Icon: small flag glyph". The
criterion says the control "has an accessible name ('Report this event') because the icon
alone is not a label". The repo's rule is stated in `share-control.tsx`'s own docstring:
*"A visible label, never an icon-only button (WCAG 1.1.1, as this repo reads it — see the
Source Badge's own docstring). There is no icon library in the product (`DESIGN.md`: 'UI
system: None'), and a share icon with no label would fail the rule that every other control
here passes."*

So the flag is **both**: a `⚑` glyph (`aria-hidden="true"`) followed by the words "Report
this event". The glyph is the affordance FR-59 asked for; the words are the label the
house rule requires. The accessible name is "Report this event" and it **contains** the
visible text, which satisfies WCAG 2.5.3's "label in name" (the same rule `ShareControl`
follows with `aria-label={`Share ${title}`}`).

### 3.2 The toast lives next to the flag, in a bare live region

```tsx
<p aria-live="polite" className="text-ink-muted [font:var(--type-scale-meta-sm)]">
  {message ? MESSAGES[message] : null}
</p>
```

**A bare `aria-live="polite"`, never a second `role="status"`.** The Detail Screen's action
row already owns one `role="status"` — the conflict-failure line at
`detail-actions.tsx:443` — and the page's own test asserts `expect(screen.queryAllByRole("status")).toHaveLength(0)`
in the resting state (`page.test.tsx:1121`). Two status regions on one surface would make
"which one is the page talking?" a question the DOM cannot answer. This is the rule
`share-control.tsx`, `detail-mute-control.tsx`, `add-event-button.tsx` and `notice-strip.tsx`
all already follow, and the comment is copied into the new file.

**Always in the DOM.** A live region added to the page together with its text is not
announced reliably; a region that is already there and then changes is. So the `<p>` is
unconditional and the *change* to it is what gets announced.

**Where it sits.** The toast is inside the control's own wrapper `<div>`, directly under
the flag — exactly where `ShareControl` puts its "Shared." line. It is **not** in the row's
own flex line as a sibling of the buttons, because `ShareControl` already sets the
precedent of a control owning its own confirmation as a stacked child.

### 3.3 The modal is a `Sheet`, and the Sheet is dismissible

```tsx
<Sheet open={open} onClose={close} label="Report this event">
  …
</Sheet>
```

`Sheet` is the shared `<dialog>` base (`components/sheets/sheet.tsx`). It is **not** the
forced-choice mode: `dismissible` is left at its default `true`, so **Esc closes it** and
a backdrop click closes it. That is required — the criterion says "Esc closes it", and
unlike the conflict prompt (FR-58, a forced choice between three actions) a report is
**optional**. A user who opens the report modal and changes their mind must be able to
leave without reporting. `ConflictResolution` uses `dismissible={false}`; this does not,
and the difference is the whole point.

**The native `<dialog>` gives the focus trap for free.** `showModal()` puts the dialog in
the top layer and the browser confines Tab to it. That is why the criterion's "the modal
traps focus" needs no JavaScript here — and it is why this item does not add a focus-trap
library (which would also violate `tests/architecture.test.ts`'s ban on UI kits).

**Focus moves to the heading on open**, by the `conflict-resolution.tsx` pattern:

```tsx
const headerRef = useRef<HTMLHeadingElement>(null);
useEffect(() => { if (open) headerRef.current?.focus(); }, [open]);
…
<h2 ref={headerRef} tabIndex={-1} className="… outline-none">Report this event</h2>
```

A screen reader lands on the question rather than on the first radio. `tabIndex={-1}` plus
`outline-none` is the house's way of making a heading focusable without adding a tab stop.

**The accessible name of the dialog is "Report this event"** — the `Sheet`'s `label` prop
becomes `aria-label` on the `<dialog>`. The visible `<h2>` says the same words. The
`aria-label` and the heading agree, so the name is not doubled up.

### 3.4 Focus returns to the flag

**This is new behaviour and it is required.** When the modal closes — by Esc, by the Cancel
button, by a successful submit — focus must go back to the flag that opened it.

**Why.** The browser's default is to move focus to `<body>` when a modal dialog closes. A
keyboard user who opens a modal, reads it, and dismisses it is then dumped at the top of
the document with no focus at all — they have to Tab their way back down the page to find
the control they were using. That is the specific thing WCAG 2.4.3 (Focus Order) is about,
and it is why the browser's default is not good enough.

**How.** A `useRef` on the flag button, and the focus move happens **when the modal
closes**, not when it opens:

```tsx
const flagRef = useRef<HTMLButtonElement>(null);

// **The modal closed — take the focus back.**
useEffect(() => {
  if (wasOpen && !open) flagRef.current?.focus();
}, [open, wasOpen]);
```

**Why it is keyed on the *transition* and not on `open === false`.** An effect that runs
"when `open` is false" also runs on the **first render**, when the modal has never been
open — and that would steal focus to the flag on page load, before the user has done
anything. The `wasOpen` guard makes the move happen only on the transition from open to
closed. (This is the same class of bug as `Sheet`'s own `showModal()` guard: `showModal`
throws if the dialog is already open, so the check is `open && !dialog.open`.)

**Why focus returns on *success* too.** The criterion says so, and it is the right
behaviour: the modal is gone, the toast is on the page, and the user's next action is
probably another one on this row. Landing them back on the flag means the toast's live
region is announced while they are still in the row's context.

### 3.5 The four options are a radio group

```tsx
<div role="radiogroup" aria-label="Report category">
  {CATEGORIES.map((category) => (
    <button
      key={category.value}
      type="button"
      role="radio"
      aria-checked={selected === category.value}
      onClick={() => select(category.value)}
    >
      …
    </button>
  ))}
</div>
```

**A radio group, because it is one.** Four mutually exclusive choices with one answer is
the definition of a radio group, and `role="radiogroup"` + `role="radio"` + `aria-checked`
is the ARIA spelling of it. The mockup uses exactly this (`role="radiogroup" aria-label="Report
category"`, four `role="radio"` buttons) and the criterion requires "the options are a
proper radio group".

**There is no precedent for this in the codebase** — `ConflictResolution` uses a
`role="group"` of buttons, because a conflict's three resolutions are *actions*, not
*states*. A report's category is a **state**: exactly one is true. So this item
establishes the radio-group pattern, and it does so with the roles rather than with native
`<input type="radio">`.

**Why not native radio inputs.** Native radios inside a `<form>` would need a form, a
label element per option, and a submit — and the criterion wants "choosing one and
submitting is a single further action", which is a *button* press after the *radio* press.
Native inputs would also change the visual design: the mockup's option cards are radio
cards (a filled circle on the right), and a native radio input cannot be styled into a
card with a description under it without either hiding the input (`opacity-0`, which then
breaks focus visibility) or rebuilding the card.

**Why buttons and not `role="option"` in a listbox.** A listbox is a *composite* widget
with its own keyboard model (arrow keys, roving tabindex, `aria-activedescendant`). The
buttons-with-radio-roles give the ARIA radio group semantics over ordinary buttons, which
are all in the tab order — a defensible, simpler model, and the one the mockup drew.

**The radio group's accessible name is "Report category"**, from the mockup.

**`aria-checked` is the state.** Clicking an option sets it; clicking a second option
replaces it. Clicking the *already selected* option leaves it selected — a radio group does
not un-select. **There is no way to submit with nothing chosen**, which is what makes the
disabled Submit honest.

### 3.6 The four categories, worded exactly

The four labels are **FR-59's own**, verbatim, and the criterion says "worded exactly as
in FR-59". They are not paraphrased, not shortened, and not given the mockup's
descriptions as their labels.

| The label the user reads | The value sent |
| --- | --- |
| "Wrong date or time" | `wrong_date_time` |
| "Wrong venue or address" | `wrong_venue` |
| "Doesn't exist or is cancelled" | `does_not_exist` |
| "Duplicate of another event" | `duplicate` |

**The values are the generated type's**, not hand-written. The category union is derived
from the contract:

```ts
type ReportCategory = components["schemas"]["EventReportIn"]["category"];
```

which is `"wrong_date_time" | "wrong_venue" | "does_not_exist" | "duplicate"` — the
**generated** union, so a new category in the schema is a type error here rather than a
silent mismatch (AD-19). And the body is typed by the generated client:

```ts
const body: components["schemas"]["EventReportIn"] = { event_id: eventId, category };
```

**The apostrophe is a typographic one.** "Doesn't exist or is cancelled" uses U+2019
(’), matching the mockup and the repo's copy (which writes `doesn&apos;t` / `Couldn&apos;t`).
In JSX, `Doesn't` in text is a syntax error, so the label is written with the HTML
entity `doesn&apos;t` — which renders the same U+2019.

**The descriptions under each option are the mockup's**, and they are `aria-hidden`
decorative text? **No** — they are read by screen readers as part of the option's name,
which would make each radio's accessible name "Wrong date or time The event is on a
different day, at a different time, or the date is missing." That is a mouthful but it is
*accurate*, and it is what the mockup intends.

**But then `getByRole("radio", { name: "Wrong date or time" })` fails.** So the decision is
the opposite: **the option's accessible name is the label alone**, and the description is
`aria-hidden="true"`:

```tsx
<button role="radio" aria-checked={…} aria-label={category.label}>
  <span aria-hidden="true">{category.glyph}</span>
  <span>
    <span className="block …">{category.label}</span>
    <span aria-hidden="true" className="…">{category.description}</span>
  </span>
</button>
```

**Why.** The criterion says the options are "worded exactly as in FR-59" — the *labels* are
the contract. An accessible name that glues a sentence of description onto the label makes
the label un-findable by name, and the four labels are the thing the editorial queue
triage on. The descriptions are helpful to a sighted reader and are **aria-hidden** so the
radio's name is exactly its label. (This also matches the mockup's own choice: the glyphs
are `aria-hidden="true"` there, and the descriptions are ordinary text inside a button
whose *visible* name is the label — the mockup is a visual artefact, not an ARIA
specification, and this item is.)

**The visible text is unchanged.** Hiding a description from assistive technology does not
hide it from anyone. A sighted reader sees the label *and* the description; a screen-reader
user hears the label and can move on.

### 3.7 There is no free-text field, and the Submit is disabled until something is chosen

```tsx
<button type="button" disabled={!selected || busy} onClick={submit}>Submit report</button>
```

**No free-text field exists.** Not a hidden one, not a disabled one — there is no
`<textarea>` and no `<input>` in the modal at all. FR-59: *"No free-text field in MVP"* and
*"Out of Scope: Free-text feedback (Phase 2)"*. The API's `EventReportIn` has exactly two
fields, `category` and `event_id`, so there is nowhere for free text to go — a text field
would be a control that cannot be submitted. The API's own docstring says it: *"Four fixed
categories mean there is nothing for a user to type into, so there is nothing to moderate,
nothing to leak into an editor's screen, and nothing that needs its own retention rule."*

**A test asserts the absence**, by querying the modal for textboxes and finding none — not
by a source check, but by the DOM.

**Submit is disabled until an option is chosen.** The criterion says so, and it is what
makes "choosing one and submitting is a single further action" true: the user presses a
radio, then presses Submit. Two presses, and the first one is a choice rather than a
commitment. Before a choice, Submit is disabled — so there is no "submit nothing" state
to handle.

**"A single further action" means one action *after* the choice.** The choice itself is
not the submission. So the modal does **not** submit on selection: pressing a radio must
not fire the request, because the user may want to change their mind, and a report that
fires on the first tap of a mis-tapped radio is a report the user did not mean to make.

### 3.8 The modal's header and footer

Header, from the mockup: the amber ⚑ glyph (`aria-hidden="true"`, `--color-warn-amber` — the
same amber the conflict prompt uses; **never red**), the `<h2>` "Report this event", and a
sub-line that names the event and says "Editorial reviews reports within 24 hours."

The 24-hour SLA is **FR-59's own** (*"The editorial review SLA for user-reported events is
24 hours from submission"*), so the modal can promise it.

Footer: a Cancel button (the ghost treatment) and the Submit button (terracotta, the
primary treatment — the same treatment the conflict sheet's "Delete it" uses for a
committed action). Both are real buttons with visible labels.

**The mockup's footer also has a daily counter — and it does not ship.** See §5.3.

---

## 4. The write, and what happens to the event afterwards

### 4.1 The call

```ts
const response = await api.POST("/api/personal/event-reports", {
  body: { event_id: eventId, category },
});
```

**Through the generated client, and only through it (AD-19).** `api` comes from
`@/lib/backend-client`; there is no `fetch`. The body is typed as the generated
`EventReportIn`, so a category outside the union is a type error and a missing field is a
type error — the criterion's "no hand-written request shapes".

**The path is the contract's path**, `/api/personal/event-reports`, which is what the
generated `paths` type is keyed by. The AD-19 coverage test's sweep ("every endpoint the
frontend calls is in the committed schema") greps for `api.POST("…")` literals and checks
them against the committed OpenAPI, so a typo in the path fails the suite.

**This endpoint is added to `NEW_ENDPOINTS` in `frontend/tests/ad19-endpoint-coverage.test.ts`**,
with its operation id and this module as its caller — so the AD-19 file's "is in the
committed schema / has its operation id / is bound in the generated TypeScript / reaches it
through the generated client / imports the generated client and does not define its own"
checks all cover the report write. The operation id comes from the committed
`openapi.json`.

### 4.2 What a success does

1. The modal closes.
2. The toast reads **"Thanks — we'll review this."** — FR-59's own words, verbatim.
3. Focus returns to the flag (§3.4).
4. **Nothing else changes.** No badge, no card state, no second read.

**The toast is `role`-free.** See §3.2 — the row already owns the page's one `role="status"`.

**The event is not re-read.** There is no `GET` after the report. The report does not change
the event, so re-reading would be a request whose answer cannot differ — and a client that
refetches to "check" is a client that might render a different card. The event on screen is
the event that was there before, which is the truth (AD-10's shape, in the client).

### 4.3 What a failure does

| The answer | What happens |
| --- | --- |
| 201 | The modal closes; the toast says thanks; focus returns to the flag. |
| 429 | The modal **stays open**; an inline line shows the API's message; the selection is preserved. |
| 404 | The modal stays open; an inline line shows the API's message. (The event was not publicly visible — but the user is looking at it, so this should not happen.) |
| 422 | The modal stays open; an inline line shows the API's message. |
| Network failure | The modal stays open; the selection is preserved; `OFFLINE_MESSAGE`; Submit is live again. |

**Every non-2xx leaves the modal open.** A modal that closes on a failed submit tells the
user the report went somewhere. It did not.

**The 429 is distinguished by its status code**, and the message comes from the API:

```ts
if (response.response.status === 429) { /* the API's message, inline */ }
```

The `code` (`rate_limited`) is available too, but the *branch* is on the status, because
that is the contract's own statement about what happened.

### 4.4 The event never visibly changes

This is the criterion that is easiest to get wrong by accident — a `reported` flag that
greys the card, a "Reported" chip, a changed border. **None of that exists.**

**Why.** FR-59: *"A single report does not auto-reject an event"* and *"Out of Scope:
Auto-rejection on a single report (rejected — editorial confirmation required)."* A report
is a *signal to an editor*, not a state of the event. If the card changed, one person's
report would change what every other person sees — which is exactly the "pile-on dynamic"
FR-59 rejects for public counters.

**How it is pinned.** The control holds **no** state about the event. It holds the modal's
open flag, the selected category, the busy flag, and the message. There is no
`reported` state, no `isReported` prop, and no prop anywhere that carries "has this been
reported" — the server does not send one, and `EventReportOut` has no such field
(*"No report id, no tally, no queue state"*).

**The test.** After a successful report, the test asserts the event's own furniture is
unchanged: no element on the page says "reported", the card's classes are the same before
and after, and the flag's label is still "Report this event" (it does not become "Reported"
or "Reported ✓"). A second report of the same event is still allowed — the API is
idempotent per (user, event, category), so a repeat is accepted and counted once.

---

## 5. The three things the mockup wants that this item does not build

The mockup (`ux-designs/…/mockups/report-event-modal-desktop.html`) is a **visual
artefact**, and three of its elements cannot be built against this API. Each is recorded
here rather than silently dropped, because a design that quietly drops a mockup's feature
is how a mockup and a product drift apart.

### 5.1 The daily-report counter: **not implemented**

The mockup's footer says *"You've reported 2 events today · 3 left in your daily limit."*

**This needs the user's own daily tally**, and **no endpoint provides one**. The API's
`EventReportOut` is `{category, reported}` and its own docstring says: *"No report id, no
tally, no queue state. A client that could read the tally could count other people's
reports on an event, which is a fact about other users and not about this one."*

**The mockup's counter is about the user's own count**, so it is not the leak the API
refuses — but it still needs an endpoint that does not exist, and inventing one would mean
adding a second read to the report flow for a number the criterion never asks for.

**And the PRD forbids the visible counterpart.** FR-59's Out of Scope: *"User-visible
report counter on public Event URLs (rejected — would create a pile-on dynamic violating the
calm principle)."* The *same* reasoning applies to a counter in the modal: it turns a
one-tap report into a metered interaction, and the calm principle is the reason this
product exists.

**So the counter does not ship, and the design says so rather than leaving the mockup
looking unimplemented.** The rate limit is instead surfaced **when it is actually hit** —
the 429's inline message ("You have reported enough events for today. Please try again
tomorrow."). That is strictly better than a counter: it tells the user what they need to
know at the moment it is true, and it costs nothing when it is not.

### 5.2 The pre-emptively disabled Submit: **not implemented**

FR-59 says: *"The 6th attempt in a 24h window is silently rate-limited (the modal opens
but the submit button is disabled with the message 'You've reported 5 events today — try
again tomorrow.')"*.

**The client cannot know the user is on their sixth report** without reading the tally —
which is §5.1's missing endpoint. A client that disabled Submit "just in case" would
disable it for the first five reports too, which is a control that is wrong most of the
time.

**So the Submit is disabled only until a category is chosen**, and the server's limit is
enforced on the attempt. The observable behaviour the PRD asks for — the modal opens, the
Submit is disabled, and the message says to try again tomorrow — **is** what happens on the
sixth attempt, except that the disablement is the server's answer rather than the client's
guess. The criterion's phrasing ("the sixth-report error renders as a calm inline
message") describes exactly this: the limit is a **server fact**, discovered by attempting.

**The difference is worth one sentence in the code, so a future reader does not "fix" it
by adding a client-side counter.** The rate limit is the server's to enforce; the client's
job is to render the answer calmly.

### 5.3 The repeat-reporter warning: **not implemented, and not implementable here**

FR-59: *"Repeat reporters (users whose reports are rejected by editorial ≥80% of the time
over the prior 30 days) get a soft warning: 'Some recent reports weren't actionable —
thanks for being careful.' Their reports remain in the queue at reduced priority."*

**This needs the user's own editorial rejection history** — a fact about *this user's*
past reports and how editors judged them. No endpoint carries it, and the editorial side
that would compute it is `editorial-review-commands`' territory, not this item's.

**It is also the wrong place to implement it.** It is a property of the *user*, not of the
*event*, so it belongs on a surface that knows the user's standing — and it must not
appear in a modal the user opens for a specific event.

**Recorded as a gap, not silently dropped.** The warning is a FR-59 consequence that
remains owed. It will need an endpoint and a surface; neither is this item's.

### 5.4 There is no mobile mockup

The UX folder has `report-event-modal-desktop.html` and no mobile counterpart. The sheet
is a native `<dialog>`, which is responsive by construction (it is `w-full
max-w-(--layout-container-form)` and centred by the browser), so no mobile-specific work is
implied. **Noted so the absence is a known state rather than an oversight.**

---

## 6. The one existing test this item breaks, and what happens to it

**`frontend/app/events/[id]/page.test.tsx:1137`** currently asserts:

```tsx
it("renders no reviews, no similar events and no report link", async () => {
  …
  expect(text).not.toMatch(/report this event/i);
  …
});
```

**This test is now wrong, and it was right when it was written.** It was written by
`feat(frontend): the Detail Screen — an explanation, or none at all` (commit `ccfadca`), at
a time when FR-59 had no endpoint and the report control was correctly absent. This item
ships the control, so the assertion about its absence is now false by design.

**The test is updated, not deleted and not worked around.** Its name becomes *"renders no
reviews and no similar events"*, the `/report this event/i` assertion is **removed**, and
the other three assertions stay exactly as they are — reviews, similar events, and
"attended" are still absent, and they are still absent for the same reasons. **The report
assertion is the only thing that changes**, because the report is the only one of those
four that now ships.

**This is the correct change to make, and here is why it is not a case of a test being
bent to fit the code.** The test's *purpose* is "the Detail Screen ships only the sections
that have shipped". The report control is now one of the shipped sections. A test that
asserted a shipped section was absent would be the defect — it would be a test that
actively forbids the feature. The other three assertions are untouched, so the test
continues to do its job.

**A new test replaces the removed assertion**, and it is the *positive* form of the same
claim: in the signed-in state, the page **does** render "Report this event". The pair
(positive in the signed-in state, absent in the anonymous state) is a stronger claim than
the old negative one, because it pins the behaviour in both directions.

---

## 7. The files

### New

| File | What it is |
| --- | --- |
| `frontend/components/detail/event-report-control.tsx` | The flag, the modal, the toast. One island, like `ShareControl` and `DetailMuteControl`. |
| `frontend/components/detail/event-report-control.test.tsx` | The component tests (§8). |

**The file name is kebab-case**, as `tests/architecture.test.ts` requires of every file in
`components/`. `event-report-control.tsx` is the name; `EventReportControl` is the
component.

**Why a separate island rather than more state in `detail-actions.tsx`.** `detail-actions.tsx`
is already 505 lines and already owns the Save button, the conflict prompt and the
`ConflictResolution` wiring. The report control has its own modal, its own toast, its own
focus-return, and its own error states — that is a **self-contained interaction**, and
`ShareControl` is the precedent for exactly this shape (a secondary control with its own
confirmation line, extracted so the Pulse Card and the Detail Screen share it).

### Modified

| File | What changes |
| --- | --- |
| `frontend/components/detail/detail-actions.tsx` | Import and render `<EventReportControl eventId={eventId} eventName={eventName} />` after `<ShareControl />`. Nothing else changes. |
| `frontend/app/events/[id]/page.test.tsx` | The "no report link" assertion is removed and replaced (§6). |
| `frontend/tests/ad19-endpoint-coverage.test.ts` | `POST /api/personal/event-reports` is added to `NEW_ENDPOINTS`, with its operation id and `components/detail/event-report-control.tsx` as its caller. |

### Not touched

- **`frontend/lib/api/schema.ts`** — already regenerated by `event-report-api`; the
  endpoint and both schemas are already there.
- **`frontend/lib/api/openapi.json`** — same.
- **The backend** — `event-report-api` is complete and its contract tests pass. This item
  changes no server behaviour.
- **`frontend/app/events/[id]/page.tsx`** — the flag inherits the `personal` gate, so the
  page does not change at all.

---

## 8. The tests, and how each one is proved to be able to fail

**Every assertion below is verified by mutation, not by inspection.** The house rule from
the earlier items in this run: a test whose assertions cannot fail is a false green, and a
false green is worse than no test because it is a claim.

### 8.1 The component tests — `event-report-control.test.tsx`

| # | The test | What it pins | The mutation that must fail it |
| --- | --- | --- | --- |
| 1 | renders a control named "Report this event" | The accessible name | Renaming the label |
| 2 | the flag is visually subordinate | No terracotta, no fill, no border on the flag | Putting `bg-accent-terracotta` on it |
| 3 | opens the modal on press | The modal opens | Not rendering the modal |
| 4 | offers exactly four options | Four, and no fifth | Adding a fifth category |
| 5 | words the four options exactly | FR-59's four strings, verbatim | "Wrong date" instead of "Wrong date or time" |
| 6 | has no free-text field | No textbox in the modal | Adding a `<textarea>` |
| 7 | the Submit is disabled until a choice | Disabled, then enabled | Enabling it always |
| 8 | choosing an option does not submit | No request on selection | Submitting on radio press |
| 9 | submits `{event_id, category}` | The body's two fields | Sending a third field, or the wrong category value |
| 10 | calls the endpoint through the generated client | `api.POST("/api/personal/event-reports", …)` | A hand-written `fetch` |
| 11 | on success shows "Thanks — we'll review this." | The toast's words | Changing the wording |
| 12 | on success closes the modal | The modal is gone | Not closing it |
| 13 | on success returns focus to the flag | `document.activeElement` is the flag | Removing the focus move |
| 14 | **the event never visibly changes** | Nothing on the page says "reported"; the flag still reads "Report this event" | Adding a badge or changing the label |
| 15 | the rate limit shows the API's message, inline | The 429's message, in the modal, not a toast | Swallowing the 429 |
| 16 | the rate limit leaves the modal open | Still open after a 429 | Closing on a 429 |
| 17 | a network failure leaves the modal open with the selection preserved | The radio is still `aria-checked` | Clearing the selection on failure |
| 18 | a network failure offers a retry | Submit is live again | Leaving it disabled |
| 19 | the toast is not a second status region | `queryAllByRole("status")` is empty | Adding `role="status"` to the toast |
| 20 | the toast's live region is always in the DOM | The `<p>` exists before the message | Rendering the `<p>` only when there is a message |
| 21 | Esc closes the modal | The modal is gone | `dismissible={false}` |
| 22 | the options are a radio group | `getByRole("radiogroup")` and four `getByRole("radio")` | Using `role="group"` and buttons |
| 23 | exactly one option is checked at a time | `aria-checked` | Selecting two |
| 24 | the dialog's accessible name is "Report this event" | `getByRole("dialog", {name})` | Renaming the `Sheet`'s label |

**The mocks follow `detail-actions.test.tsx`'s shape exactly** — `vi.mock("@/lib/backend-client", …)`
with `POST`/`GET` fakes, `POST.mockResolvedValue({ data: {}, response: { status: 200 } })` in
`beforeEach`. **No `user-event`** — it is not a dependency of this repo, so the tests use
`fireEvent`/`click()` and `waitFor`, as the existing tests do.

**The generated types are used, not re-declared.** The test's body is typed
`components["schemas"]["EventReportIn"]`, so a category the contract does not have is a
**type error** — which is a stronger guarantee than a runtime assertion, and it is the
criterion's "using the generated API types with no hand-written request shapes (AD-19)".

### 8.2 The page-level tests — `page.test.tsx`

| # | The test | What it pins |
| --- | --- | --- |
| 25 | **signed out: the flag is absent** | The anonymous page has no "Report this event" |
| 26 | **signed in: the flag is present** | The positive form of the same claim |

**#25 is the criterion's "signed out" pin.** It renders the page in the `anonymous` state
(`personal: null`) — the same fixture the file already has — and asserts the flag is not
there. **#26** renders it in the `found` state with a `personal` and asserts it is. Together
they say "the flag appears exactly when the account is there", which is what "matching what
Save does" means.

### 8.3 The axe gate — `event-detail-a11y.test.tsx`

**The criterion says "the existing Playwright and axe gates cover it".** Playwright is
**not in this repository** — there is no `playwright.config.ts`, no `@playwright/test`
dependency, and no Playwright suite (the frontend has 14 Vitest suites and no e2e runner).
So **the axe half of the criterion is honoured in the house's own way**: a Vitest + axe-core
case, in the file that already is the Detail Screen's axe gate.

**The new case** renders the Detail Screen in the signed-in state, opens the report modal,
and audits it:

```tsx
it("has zero serious or critical violations with the report modal open", async () => {
  …
  screen.getByRole("button", { name: "Report this event" }).click();
  await waitFor(() => expect(screen.getByRole("dialog", { name: "Report this event" })).toBeInTheDocument());
  const violations = await audit();
  expect(violations.map((v) => `${v.id}: …`)).toEqual([]);
});
```

**It is the same shape as the existing "with the prompt open" case**, and it audits the
whole `document.body`, because a modal is the surface where an accessibility failure would
hurt most.

**`color-contrast` is disabled explicitly**, as it is in every other axe case in the repo:
jsdom computes no layout, so axe has no boxes to compare and the rule reports false
positives rather than findings. Contrast belongs to a real browser.

**The Playwright half of the criterion is reported as a gap, honestly.** The criterion
names a gate that does not exist in this repository. Rather than write it as if it were
satisfied, this design says: the axe gate is implemented and is the repo's real
accessibility gate; the Playwright gate is **not** part of this repository's tooling, and
if it is added later, the report modal will be covered by the same fixture.

### 8.4 The AD-19 coverage — `ad19-endpoint-coverage.test.ts`

`POST /api/personal/event-reports` is added to `NEW_ENDPOINTS` with its operation id —
**`apps_personalization_api_report_event_endpoint`**, read from the committed
`frontend/lib/api/openapi.json:4824` and already bound in the generated TypeScript
(`frontend/lib/api/schema.ts:581` and `:4208`) — and
`components/detail/event-report-control.tsx` as its caller. That file's five per-endpoint checks then cover the report write: in the
committed schema, has its operation id, bound in the generated TypeScript, reached through
the generated client, and importing the generated client without defining its own.

**And the sweep catches a hand-written `fetch`**, because the sweep reads every
`api.POST("…")` call site and checks the path against the committed schema.

### 8.5 The mutation probes

**Each of the 24 component/page assertions is proved by mutation.** The mutations are
listed per-test above. **The probes are run and their output recorded in the run's
`test-report.md`** — the same discipline as work items 8 and 9 in this run, where a probe
whose edit found nothing to replace would have been a false green itself.

**One probe is a probe of the probe.** The axe case and the focus-return case are the two
that could pass vacuously, so each gets a *planted defect*: an axe case that audits a modal
that was never opened (which would pass vacuously) and a focus case that asserts the focus
is on the flag when the flag was never focused.

---

## 9. The accessibility rules this item has to satisfy, and how

| Rule | How it is met | Where it is tested |
| --- | --- | --- |
| The control has an accessible name | `aria-label="Report this event"`, and the visible text is the same words (WCAG 2.5.3 "label in name") | #1 |
| The modal is named | `Sheet`'s `label` → `aria-label` on the `<dialog>` | #24 |
| Focus moves into the modal | `<h2 tabIndex={-1}>` focused on open, by the `conflict-resolution.tsx` pattern | #13's neighbour; the heading-focus assertion |
| Focus is trapped | The native `<dialog>` in the top layer traps Tab — no JS, no library | the axe case + the browser's own behaviour |
| Focus returns on close | The `wasOpen && !open` effect moves focus to the flag | #13 |
| Esc closes it | `Sheet`'s default `dismissible` | #21 |
| The options are a radio group | `role="radiogroup"` + `role="radio"` + `aria-checked` | #22, #23 |
| The toast is announced | A bare `aria-live="polite"`, always in the DOM | #19, #20 |
| No second status region | The row's `role="status"` stays the only one | #19 |
| The option descriptions do not pollute the name | `aria-hidden="true"` on the description | the name assertions in #5 |
| The glyph is not read out | `aria-hidden="true"` on the ⚑ | #5 |
| Colour is not the sole carrier | The flag's state is its words; the option's state is `aria-checked` | #23 |
| A tap target is big enough | `min-h-[44px]`, the house's floor (the card's Source Badge button uses it) | — |

---

## 10. What this item does **not** do

- **It does not change the event's state.** §4.4.
- **It does not add an endpoint.** The API is `event-report-api`'s, and it is complete.
- **It does not show a daily counter.** §5.1 — no endpoint carries the tally, and FR-59
  rejects the visible counterpart.
- **It does not pre-emptively disable Submit for the sixth report.** §5.2 — the client
  cannot know, and the server's answer is rendered when it comes.
- **It does not implement the repeat-reporter warning.** §5.3 — it needs the user's
  editorial history, which no endpoint carries. **Recorded as a remaining FR-59
  consequence.**
- **It does not change the schema.** The endpoint is already in the generated client.
- **It does not add a Playwright suite.** §8.3 — Playwright is not this repository's
  tooling; the axe gate is Vitest + axe-core.
- **It does not add a sign-in route for the flag.** §2.1 — the flag is hidden when signed
  out, matching Save.

---

## 11. The checkpoint

This is a **confirm**-mode item: one checkpoint, before implementation. The decisions a
reviewer may want to change, in the order they matter:

1. **§6 — the existing test that this item breaks.** `page.test.tsx` asserts the Detail
   Screen renders no "report this event" text. The design removes that one assertion and
   replaces it with a positive one, leaving the other three untouched. **This is the
   decision most worth a reviewer's attention**, because it is the one place where this
   item changes a test that was written to forbid exactly this feature.
2. **§2.1 — signed out is "hidden", not "route to sign-in".** Free, because the whole row
   is already gated on `personal`. The criterion asks the plan to state it and a test to
   pin it; both are here.
3. **§3.6 — the option's accessible name is the label alone**, with the mockup's
   description `aria-hidden`. The alternative (the description inside the name) would make
   `getByRole("radio", { name: "Wrong date or time" })` fail.
4. **§5 — the three mockup features that do not ship**, and §5.2's reasoning that the
   server's limit is discovered by attempting rather than guessed at by the client.
5. **§8.3 — the Playwright half of the criterion is not satisfiable in this repository**,
   and the axe gate is implemented instead, in the file that already is the Detail
   Screen's axe gate.

---

## 12. The acceptance criteria, mapped

| The criterion | Where it is met | Where it is tested |
| --- | --- | --- |
| A flag in the secondary row, visually subordinate, named "Report this event" | §3.1 | #1, #2 |
| Exactly four options, FR-59's wording, no free text, Submit disabled until chosen, one further action to submit | §3.6, §3.7 | #4, #5, #6, #7, #8 |
| On success: the toast, the close, the focus return | §4.2, §3.2, §3.4 | #11, #12, #13 |
| The rate limit as a calm inline message; a network failure leaves the modal open with the selection and a retry | §2.2, §2.3 | #15, #16, #17, #18 |
| Signed out: stated and pinned, matching Save | §2.1 | #25, #26 |
| The event never visibly changes | §4.4 | #14 |
| Focus trap, Esc, a radio group, axe clean | §3.3, §3.5, §8.3 | #21, #22, #23, the axe case |
| Vitest tests for rendering, selection, submission, success, the rate limit, network failure and the signed-out state, using the generated types | §8 | #1–#24, #25, #26 |
