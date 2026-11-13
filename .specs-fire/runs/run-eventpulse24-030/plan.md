---
run: run-eventpulse24-030
work_item: personal-events-digest-toggle
intent: digest-personal-events-control
mode: autopilot
checkpoint: none
---

# Implementation Plan: The Toggle — Personal Events In or Out of the Pulse Digest

> **This run covers six work items.** Each item's plan is a section here, appended in
> execution order. The item currently executing is named in each section's heading.

---

# Work Item 1 of 6: `digest-preference-read-helper` (autopilot)

## Approach

Add `frontend/lib/digest-preference-read.ts`, a server-only helper that reads
`GET /api/personal/onboarding` and hands back **only** the three fields this intent's
screen needs: `delivery_time`, `timezone`, and `include_personal_events`.

**The house pattern, copied from `lib/conflict-list-read.ts`** — which is the closest
precedent because it is also a `/api/personal/...` server read:

- A `kind` discriminant with exactly two answers: `"found"` (the server's answer) and
  `"unavailable"` (a failure to answer). No third state — the endpoint is a singleton
  that self-creates, so there is no target that might not exist and none that might
  belong to somebody else.
- The `apiBaseUrl()` guard, because a build machine has no API to ask and that is not a
  reason to crash the page.
- The read carries `sessionHeaders()`, because a server-side read without the visitor's
  cookies is anonymous — and an anonymous read of somebody's digest preference is
  nobody's preference, which would render the toggle in the wrong state.
- The module is server-only by construction: it reaches `next/headers` through
  `sessionHeaders()`.

**One correction to the work item, found against the generated schema.**
`OnboardingStateOut.digest` is **not** nullable in `frontend/lib/api/schema.ts` — it is
a required `DigestPreferenceOut`. The work item anticipated an "absent digest block"
case; the schema says that block is always present on a successful response. The only
real absences are a missing body and an error response, both of which land in
`"unavailable"`. The test suite covers those instead of the case that cannot occur.

**The returned shape is narrower than the API's.** The helper returns a plain object
with the three fields rather than the whole `DigestPreferenceOut`, so a later change to
the onboarding state shape — adding a field, changing the digest block — cannot break
a settings screen that never asked for it.

## Files to Create

| File | Purpose |
|------|---------|
| `frontend/lib/digest-preference-read.ts` | The server-only read helper |
| `frontend/lib/digest-preference-read.test.ts` | Its tests |

## Files to Modify

| File | Changes |
|------|---------|
| (none) | |

## Tests

| Test File | Coverage |
|-----------|----------|
| `frontend/lib/digest-preference-read.test.ts` | found; carries the cookie; unavailable on no-API; unavailable on throw; unavailable on error response; unavailable on empty body; returns only the three fields |

## Technical Details

- **Follow `conflict-list-read.ts` exactly** for the mock pattern: `vi.mock` on
  `@/lib/backend-client`, `@/lib/api-base-url`, and `next/headers`, with `cookies`
  resolving to an object whose `toString()` is the cookie jar.
- **The `include_personal_events` default.** `DigestPreferenceOut.include_personal_events`
  is `boolean` with a default of `true`. The helper returns the server's value as-is —
  it does not second-guess it. A user who has never touched the setting has `true` from
  the server, and the toggle should show "on" because that is what the server said.
- **The `delivery_time` and `timezone` are returned verbatim.** The toggle's save has to
  round-trip them unchanged, and the endpoint refuses to half-apply the pair — so the
  helper must not normalise, reformat, or default them. A `null` timezone in the
  response is a real state (a user who has not finished onboarding) and must survive
  the round-trip unchanged, because normalising it would change the user's schedule.
- **No `city`.** The helper returns the three fields this intent's screen needs. The
  city is not one of them, and returning it would tempt a caller to send it back.

---

# Work Item 2 of 6: `personal-events-digest-toggle` (confirm)

> **This plan covers item 2 only** (`personal-events-digest-toggle`): the control
> itself. The route it lives on is item 3 (`digest-settings-route`). The plan records
> the boundary explicitly so the two do not blur — see "What this item does not do".

## Approach

Build `frontend/components/settings/digest-personal-events.tsx`: a `"use client"`
component that renders a `<button type="button">` with `aria-pressed`, saves inline
with no Save button, and sends exactly three fields.

**The house toggle pattern, copied from `components/state/detail-mute-control.tsx`:**

- A `<button>` with a **stable accessible name** and `aria-pressed` carrying the state.
  **Not** `role="switch"` — the house decision was made and written down in
  `reminders/reminder-picker.tsx:20`, and this item follows it rather than reopening it.
- The **visible text changes** with the state, so a sighted reader sees it in words and
  the state is never carried by colour alone (WCAG 1.4.1).
- **Optimistic local state with rollback on failure**, and a `busy` disable so the
  button cannot be pressed twice.
- **The state after a save is the server's answer**, not the client's guess.

**The save body is exactly three keys:** `include_personal_events`, `delivery_time`,
`timezone`. The first is the point; the other two are the required round-trip (see
below). **No `city`** — the endpoint cannot clear it, and a client that sent it back
would be relying on a field the screen does not own.

**The round-trip is the endpoint's rule, not this component's invention.**
`DigestPreferenceIn.delivery_time` is `time` and `.timezone` is `str` — both
**required and non-nullable** (`backend/apps/personalization/schemas.py:653-654`,
generated `frontend/lib/api/schema.ts:2569,2576`). The endpoint has no patch-one-field
mode. So the toggle sends the schedule it read, unchanged, alongside the flag. The
precedent is `digest-delivery-time.tsx:15-16`, whose docstring says it in its own
words: *"The zone travels with the time… Both or neither."*

**The failure line follows `saveFailureMessage(error, offline)`.** The API's own
refusal is shown verbatim when the API made one; the route's own line — *"Couldn't
save."*, matching `digest-delivery-time.tsx:47` — when the request never arrived.

### The schedule guard — a gap the work item did not anticipate

**The work item says the toggle "must read the stored delivery time and timezone and
send them back unchanged". That is right when there is a schedule, and impossible when
there is not.**

`OnboardingStateOut.digest.delivery_time` is `time | None`
(`backend/apps/personalization/schemas.py:658-666`), and it is `None` whenever the
user has **no `DigestPreference` row** — `onboarding.py:727-728` reads
`state.digest_delivery_time` as `digest.delivery_time if digest is not None else None`.
A user who has not finished onboarding is exactly that user. The model columns are not
nullable (`models.py:649`), but the *row* may not exist.

**So for that user there is no valid body.** `delivery_time` is required and
non-nullable, so sending `null` is a **422**, not a save. The toggle would show a
failure for a user who did nothing wrong, on a control that could never have worked.

**The guard: the toggle renders, but it is disabled with an explanation, when the
stored schedule is absent.** Two things follow from that, and both are the point:

1. **The control never sends a body the endpoint must refuse.** A control that can
   only fail is worse than a control that is honestly unavailable.
2. **The user is told why.** "Set your delivery time first" is a sentence the user can
   act on. A 422 is not.

**And the button stays disabled rather than optimistically flipping.** `aria-pressed`
still reports the **server's** stored value — the opt-out is `true` by default on a
user with no preference row, so the button reads pressed while being unavailable.
That is honest: the server does believe personal events are included.

**This is a client-side guard, not a backend change.** The intent forbids touching
the backend, and none is needed: `set_digest_preference` would happily create the row
via `_write_digest`'s upsert — but it cannot be called without a delivery time and a
zone, which is the very thing we do not have.

### Route placement — the work item's open decision, now decided

The work item left this open, with a recommendation for (b) a new `/settings/digest`
route "on the condition that the item adds a discoverable link". **This item takes
recommendation (b),** for the reasons the work item gives — one route per settings
concern, each a standalone page; room for FR-7's delivery-tolerance work later
without crowding an unrelated page.

**But the route itself is item 3.** So this item builds the **component** and its
**tests**, plus the **link** that makes the route discoverable — the link is a
one-line change to the quiet-hours page's existing "Pulse Digest" section, and without
it the route would be reachable and invisible. The link lands in this item because the
work item makes it a **condition** of choosing (b), not an optional extra.

**The sidenav needs no change.** Its active rule is a prefix match on
`pathname.startsWith("/settings/")` (`sidenav.tsx:141`), so `/settings/digest` marks
Settings active automatically.

### The one status region

`SaveFeedback` renders a `role="status"` region. `detail-mute-control.tsx:215-228`
records that a page must have **one** status region. The new `/settings/digest` route
will carry exactly one — the toggle's `SaveFeedback` — so the rule holds by
construction. Item 3 owns the route and must not add a second.

## Files to Create

| File | Purpose |
|------|---------|
| `frontend/components/settings/digest-personal-events.tsx` | The toggle |
| `frontend/components/settings/digest-personal-events.test.tsx` | Its tests |

## Files to Modify

| File | Changes |
|------|---------|
| `frontend/app/settings/quiet-hours/page.tsx` | One link into `/settings/digest`, in the existing "Pulse Digest" section |

## What this item does not do

- **It does not build the route.** `app/settings/digest/page.tsx` is item 3.
- **It does not touch the backend.** The narrow command
  `set_include_personal_events()` exists but is not wired to any endpoint, and wiring
  it would be a backend change the intent forbids.
- **It does not touch `frontend/lib/api/` or `openapi.json`.** No schema change, so no
  regeneration. `make client` must leave `frontend/lib/api/` clean.
- **It does not decide the onboarding question.** Whether onboarding should own the
  opt-out is item 4.

## Tests

| Test File | Coverage |
|-----------|----------|
| `frontend/components/settings/digest-personal-events.test.tsx` | The body has exactly three keys and no `city`; the schedule is sent back unchanged; success shows "Saved."; the API's refusal is shown verbatim; the offline line is shown when the request throws; the state after a save is the server's answer; the accessible name is stable across both states and `aria-pressed` flips; the visible text changes with the state; a failed save rolls the state back; the control is disabled with an explanation when the schedule is absent |

**Every test must be able to fail.** The body assertions are exact-key-set
assertions, not subset checks, so a widened body fails. The accessible-name assertion
compares the name in both states, so a name that changes with the state fails.

**The mutation standard applies.** Each test is checked against the mutation it is
meant to catch before the item is reported complete.

## Technical Details

- **The write is `PUT /api/personal/onboarding/digest-preference`** — the endpoint
  `put_digest_preference` → `set_digest_preference` (`api.py:626-660`). **Not**
  `/api/settings/notifications`, which is the delivery-time endpoint the quiet-hours
  page uses.
- **`delivery_time` is sent as the wall clock exactly as read.** The stored value is
  `HH:MM:SS`; `_validated_delivery_time` (`onboarding.py:216-226`) refuses a tz-aware
  time, so the value travels as the string it was read as — never re-formatted, never
  re-zoned.
- **`include_personal_events` is the server's value, not the client's guess.** The
  backend defaults it to `true`; a user who never touched it has `true`, and the
  toggle shows what the server believes.
- **No new tokens.** `frontend/styles/tokens.css` resets Tailwind's palette via
  `@theme static { --color-*: initial }`, and `styles/tokens.test.ts` pins every
  colour against `DESIGN.md`. This item adds no colour — so no `DESIGN.md` edit.
- **The button does not use `bg-warm-personal`.** `pulse-card.test.tsx:220-228`
  asserts interactive surfaces never carry stripe colours; the toggle is interactive.
- **`SaveFeedback` is used as-is** — its props are `{ busy, saved, failure }`, fully
  generic and not time-shaped.

---
*Plan approved at checkpoint. Execution follows.*

---

# Work Item 3 of 6: `digest-settings-route` (confirm)

## Approach

Build `frontend/app/settings/digest/page.tsx` — the route that hosts the toggle — plus
its `loading.tsx` sibling and its page test.

**The five-step house pattern, followed without deviation.** All four existing
settings routes do the same five things in the same order, and this one does too:

1. `export const dynamic = "force-dynamic"` — a settings screen is per-user and is
   never cached.
2. `const session = await getSession()`, then `const destination = homeRoute(session)`;
   `redirect(destination)` if it is not `null` — an anonymous visitor goes to
   `/preview`, a half-onboarded one to `/onboarding`. `redirect` throws, so it is
   called outside any try/catch.
3. If `session.kind !== "signed-in"`, render
   `<AppShell name="" email=""><SettingsStates /></AppShell>`.
4. Read the data; if the read is `"unavailable"`, render
   `<AppShell name={displayName(...)} email={...}><SettingsStates /></AppShell>`.
5. Otherwise render the page inside `AppShell`, with a header (`h1` + a one-line lede)
   and the content capped at `max-w-(--layout-container-reading)`.

**The read is the helper from item 1** — `readDigestPreference()` — so the route's
data comes from the one place that knows how to read the digest preference.

**`displayName()` is copied, not extracted.** The work item says to follow the
existing pattern rather than refactor: there are ten copies of this function across
`app/`, four of them in settings routes, and extracting a shared helper is a different
change that is not in this intent's scope.

**The discoverability link is already done — in item 2.** The work item asks for "at
minimum, a link from an existing settings page", and item 2 put it in the quiet-hours
page's existing "Pulse Digest" section, with a test pinning its `href`. **This item
does not add a second link.** The work item is explicit: *"Choose one, and do not add
links to both — a link in two places is two places to keep in sync."*

**The sidenav is not modified.** Its active rule is already a prefix match on
`pathname.startsWith("/settings/")` (`sidenav.tsx:141`), so `/settings/digest` marks
Settings active automatically, and `DESIGN.md`'s rule forbids adding nav rows.

**No `/settings` index and no settings sub-nav.** The convention is stated in two
places and this item respects it.

**The page's own status region is the toggle's.** `SaveFeedback` renders the one
`role="status"`. The route adds no second one.

## Files to Create

| File | Purpose |
|------|---------|
| `frontend/app/settings/digest/page.tsx` | The route |
| `frontend/app/settings/digest/page.test.tsx` | Its tests |
| `frontend/app/settings/digest/loading.tsx` | Its skeleton, as the other four settings routes have |

## Files to Modify

| File | Changes |
|------|---------|
| (none) | |

## What this item does not do

- **It does not add a settings index or sub-nav.**
- **It does not touch the sidenav.**
- **It does not add a second discoverability link** — item 2 already put the one.
- **It does not add a second status region.**

## Tests

| Test File | Coverage |
|-----------|----------|
| `frontend/app/settings/digest/page.test.tsx` | The toggle renders with the stored value; an anonymous request is redirected rather than served; a half-onboarded request is redirected to `/onboarding`; the unavailable state renders and the toggle does not; the page has an `h1` and a lede; the sidenav marks Settings active; there is no page-level Save button |

**Every test must be able to fail.** The redirect tests assert `redirect` was called
with the right path — not merely that the page rendered. The stored-state test asserts
the button's `aria-pressed`, so a page that passed a default instead of the server's
value fails.

## Technical Details

- **The route is `/settings/digest`.** The sidenav's prefix rule covers it, and item
  2's link points at it.
- **The `schedule` prop is built from the read.** `readDigestPreference()` returns
  `delivery_time` and `timezone` as `string | null`, so the route maps them to
  `schedule: { deliveryTime, timezone } | null` — **both or neither**, matching the
  prop's contract in item 2.
- **The header's tone.** The other settings pages' ledes are one line and say what the
  screen is for: *"What we suggest when you save an event."*, *"When we stay quiet."*,
  *"Group your saved events however you like."* This one says what the screen is for
  in the same register.
- **The skeleton is a skeleton, not a spinner.** `styles/motion.test.ts` fails the
  suite on any animation other than `.fade-in`, so the in-flight state is rectangles
  in the shape of the page — one heading, one lede, one control row.
- **No new tokens.** The skeleton uses `bg-surface-subtle`, `rounded-subtle` and
  `rounded-control`, exactly as the other four do.

---
*Plan approved at checkpoint. Execution follows.*

---

# Work Item 4 of 6: `onboarding-opt-out-decision` (confirm)

## The decision

**Onboarding does not own the opt-out. The settings route does, and onboarding's only
job here is to stop pretending it sends the field.**

### Why, in four lines

1. **The PRD's own framing puts configuration after onboarding.** PRD §4.1: *"The flow is
   glass-floor simple: skip most steps, get immediate value, **configure later**."* The
   opt-out is configuration.
2. **FR-1 caps onboarding at three steps and names their contents** — calendar connect,
   interest chips, delivery time + timezone. The opt-out is not one of them, and adding
   a fourth *control* to a step is a step-contract change, not a step-count change.
3. **No design document specifies an onboarding opt-out.** A sweep of the design corpus
   (`EXPERIENCE.md`, `DESIGN.md`, the PRD, the addendum, the reconcile brief) found
   **zero** occurrences of an opt-out control in onboarding. Every opt-out the corpus
   *does* specify is Settings-scoped — geo-IP (Settings→Privacy), training opt-out
   (Settings→Privacy), source mute (Settings→Sources), per-day quiet hours (Settings→
   Quiet Hours), streak counter (Settings→Reminders). **The corpus has a pattern, and
   the opt-out is in it.**
4. **Making onboarding own it would be a new design decision, not an implementation of
   an existing one** — and it would need copy written deliberately, which is a design
   task, not a code task.

**The case for onboarding owning it is real and is recorded, not dismissed.** The
calendar step's lede promises *"We'll surface your personal events alongside public
ones"* (`onboarding-flow.tsx:55`) — and that promise is exactly what the opt-out
governs. **But the answer to a promise made in onboarding is a control that can be
changed later, and there is one:** `/settings/digest`, with a link into it from the
quiet-hours page's "Pulse Digest" section (item 2). **A promise plus a reachable
setting is how the corpus handles every other opt-out.** If the promise itself turns
out to be wrong for a user, the fix is to the step's copy — not to add a third control
to the step's contract.

### What this decision costs, and what it does not

**It does not change the onboarding flow's behaviour.** The three steps, the
resume-from-server-state behaviour, the delivery time and the timezone are untouched.
The PUT body stays exactly `{ delivery_time, timezone }`.

**It does not change the settings toggle.** That is where the control lives, and item 2
built it.

**It does change one thing that is a lie: the test fixture.**

## Approach

Fix the false signal, and pin the truth.

### The fixture's misleading comment and field

`components/onboarding/onboarding-flow.test.tsx:46-53` currently reads:

```typescript
// The three fields the digest preference grew: the home city, how it was arrived
// at, and the personal-events opt-out (which defaults to included).
digest: {
  delivery_time: null,
  timezone: null,
  city: null,
  city_source: null,
  include_personal_events: true,
},
```

**The comment says "the three fields" and then lists five**, and it names the opt-out
as one of them — a reader would conclude the flow reads and sends the opt-out. **It
does neither.** The `digest` block here is the server's *state* (the mock of
`GET /api/personal/onboarding`), not the body's shape — so `include_personal_events` in
it is not itself wrong. **The comment is what is wrong**, because it credits the flow
with a field the flow does not touch.

**The fix: the comment says what the fixture is.** The block is the server's stored
state; the flow reads `delivery_time` and `timezone` from it and sends those two back.
The opt-out is in the state because the server has it — **not** because the flow
owns it. And the count is right.

**The field stays.** Removing `include_personal_events` from the mocked state would make
the fixture *less* faithful to the server's response — the server really does return it,
and a mock that hides a field the server sends is its own kind of false signal. The
false signal is the **comment**, not the data.

### The exact-body assertion stays, and gains a name

`onboarding-flow.test.tsx:343-347` already asserts the **whole** body:

```typescript
expect(PUT).toHaveBeenCalledWith("/api/personal/onboarding/digest-preference", {
  body: { delivery_time: "07:30", timezone: "America/New_York" },
});
```

**That is the assertion that makes the omission visible** — add a field to the body and
this test fails until someone says so. **It is kept in exactly this form.** What
changes is that the test now *says* what it is protecting, so the next reader does not
have to re-derive it.

### A new test that names the omission

The exact-body assertion proves the body has two keys. **A test that says the body has
*no* opt-out** says it in words, and reads as a deliberate fact rather than an
accident of what the body happened to contain. It is the same shape as the house's
`expect(body).not.toHaveProperty("quiet_hours")` pattern.

### The decision itself is recorded in the code

**A decision that lives only in a run artifact is a decision that gets re-litigated.**
The onboarding flow's docstring says which fields it sends and why; the digest step's
docstring says what it owns. Both get one sentence each naming the opt-out's home, so
the next person who wonders "why isn't there a toggle here?" finds the answer where
they are looking.

## Files to Create

| File | Purpose |
|------|---------|
| (none) | |

## Files to Modify

| File | Changes |
|------|---------|
| `frontend/components/onboarding/onboarding-flow.test.tsx` | The fixture's comment corrected; the exact-body test renamed and given its rationale; a new test naming the omission |
| `frontend/components/onboarding/onboarding-flow.tsx` | One sentence in the docstring saying which fields the flow sends and where the opt-out lives |
| `frontend/components/onboarding/digest-step.tsx` | One sentence in the docstring saying the step owns the time and the zone, and not the opt-out |

## What this item does not do

- **It does not add a control to the digest step.** That would be onboarding owning the
  opt-out, which this item decides against.
- **It does not change the PUT body.** It stays `{ delivery_time, timezone }`.
- **It does not add a fourth onboarding step.** FR-1 caps it at three, and the step
  count is `ONBOARDING_STEP_COUNT` in `components/onboarding/steps.ts`.
- **It does not change any onboarding copy.** The criterion is "copy is updated *if and
  only if* the copy changes as a result of the decision" — the decision changes no
  copy.
- **It does not touch the settings toggle.** Item 2 built it; this item does not.

## Tests

| Test File | Coverage |
|-----------|----------|
| `frontend/components/onboarding/onboarding-flow.test.tsx` | The exact-body assertion still holds in its exact-body form (the two fields, nothing else); a new test asserts the body carries no `include_personal_events`; the flow's existing behaviour is unchanged (the whole existing suite still passes) |

**Every test must be able to fail.** The new test asserts the body's exact key set, so
a flow that started sending the opt-out would fail it — which is what makes it a
**false-signal killer** rather than a description of today's behaviour. The existing
exact-body assertion is itself the mutation target: adding the field to the body fails
it, and that is the point of keeping its exact form.

## Technical Details

- **The mocked state keeps all five fields.** The mock is the server's
  `OnboardingStateOut`, and the server sends all five. A mock that hides one is a
  different kind of false signal.
- **`DigestValues` does not grow a field.** It stays `{ deliveryTime, timezone }` —
  the flow has no opt-out value to carry.
- **The docstring paragraphs are short, and they carry the reasoning.** Each names the
  opt-out's home (`/settings/digest`) and the reason (the step owns the *schedule*; the
  opt-out governs the digest's *contents*), and cites the PRD and the design corpus
  rather than restating them — so they will not rot. *(Amended during execution: the
  plan first said "one sentence each"; the shipped text is a short section each, because
  a bare assertion invites the next reader to re-derive it.)*
- **The new test asserts over *every* call to the endpoint, not the first.** `find`
  would have taken the first matching call and stopped, so a second `PUT` to the same
  path carrying the opt-out would have left the clean first call satisfying the
  assertion and the offending one invisible. The exact-body assertion has the same
  blind spot — it matches *any* call. **This was found by mutation testing.**
- **No new tokens, no new colours, no copy edits** — so no `DESIGN.md` edit, and
  `make client` must leave `frontend/lib/api/` clean.

---

# Work Item 5 of 6: `digest-composition-proof` (confirm)

## Approach

**A new file: `backend/tests/personalization/test_digest_opt_out_seam.py`** — one test
module that spans the seam, and nothing else changes.

### The gap, stated precisely

The research for this item found the exact shape of the gap, and it is a clean one:

- **The write side** is tested in `test_onboarding_api.py` — it asserts the JSON body
  and the stored row.
- **The read side** is tested in `test_digest_composition.py` — but **every one of its
  four opt-out tests writes the flag with a direct ORM factory write**
  (`DigestPreferenceFactory(include_personal_events=False)`), never through the API.
- **So no test does PUT → compose.** The two sides are tested in two disconnected files
  and never joined.

**A regression in the write path would leave every existing backend test green and the
product broken.** Specifically: a field dropped from the PUT body, a wrong key name, a
field the endpoint silently ignores because it was omitted — none of those is caught by
a test that writes the flag with a factory.

### The seam is joinable, and this is the key

`request.user.pk` is a **UUID** (`apps/identity.models.User` is a `UUIDv7Model`), and
`DigestPreference.user_id` is a **`UUIDField`** — the same id space. So a real user,
signed into a real client, is the same `user_id` the composition reads by. **The two
paths meet at a column, and the test can walk both sides of it.**

### The write goes through the HTTP endpoint, not the service function

**The endpoint, not `set_digest_preference`.** The work item says *"the same write path
the frontend uses — not be set by a direct ORM write in the test"*. The frontend's path
is `PUT /api/personal/onboarding/digest-preference`, so the test calls that, through
Django's test `Client` (the project uses **Django Ninja, not DRF** — there is no
`APIClient`), with the CSRF client and `force_login`, exactly as `test_onboarding_api.py`
does.

**Why the endpoint and not the service function.** The service function is the *second*
half of the write path; the endpoint is the *first*. A test that calls the service
function would still miss a broken schema binding, a wrong field name on the request
model, or a serializer that drops the field. **Calling the endpoint is what makes the
test a proof about the thing the browser actually calls.**

### The body is exactly what the settings screen sends

**The same three keys, with the same values the toggle sends:**
`{ include_personal_events, delivery_time, timezone }`. `delivery_time` and `timezone`
are required by the endpoint, so they are in the body — the same required round-trip
the settings toggle performs.

**No `city`.** The endpoint's city triggers a catalog coverage read, which is a
different code path and a different assertion. The seam under test is the opt-out.

## The three cases

| Case | What it proves |
|------|----------------|
| **Opted out** | The user PUTs `include_personal_events: false`; the composed digest has **no personal event** |
| **Not opted out** | The user PUTs `include_personal_events: true`; the personal event **is** in Slot 1 |
| **Opted back in** | The user PUTs `false`, then `true`; the personal event is **back** |

**The positive case is not optional.** Without it, the opt-out assertion is satisfied by
a digest that never contains personal events at all — a broken candidate read, a broken
Slot 1, a broken fixture. **The positive case is what stops the proof from being
vacuous.**

**The inverted case proves the control is not write-once.** It also exercises the
`_write_digest` **update** path — the second PUT finds the existing row — which is a
different branch from the create path the first PUT took. **Two paths, two assertions.**

## The two assertions that catch the failure the work item is about

### The fallback must have run — "no personal event" is not enough

**Slot 1 falls through to the public fallback when the personal branch is skipped**
(`digest_composition.py:503-519`). **So "the digest contains no personal event" is
satisfied by a digest that fell through for the wrong reason** — a broken candidate
read, an event outside the window, a fixture mistake.

**So the opt-out case asserts the public event took Slot 1.** That is the assertion that
distinguishes *"the opt-out removed the personal event"* from *"there was no eligible
personal event to begin with"*. **It is the assertion the work item asks for** — *"must
therefore also confirm the fallback ran, or a broken fallback will look like a passing
opt-out."*

### The count must be suppressed — the quieter leak

`personal_qualifying_count` is suppressed when the user is opted out
(`digest_composition.py:679-683`). **This is the difference between "the personal event
is not shown" and "the product does not know about it."** A dashboard metric counting
opted-out events would be a second, quieter leak of the same bug — and it would leak
after the visible leak was fixed.

## Time

**`compose_digest` takes `now` as a keyword parameter**, so the composition runs at a
stated instant with no wall-clock involvement — the house pattern in
`test_digest_composition.py` (`NOW` constant, passed explicitly). **No new absolute
datetime is introduced**, and no `freezegun` is needed: the write path's `now` is used
only for the audit row's `"at"`, which no assertion reads.

**The personal event is inside the 48-hour window.** `RANKING_PERSONAL_EVENT_WINDOW` is
48 hours; the candidate read is `start_utc >= now` and `start_utc <= now + 48h`, both
ends inclusive. **The event is placed 3 hours out** — comfortably inside, and not on the
boundary, so the test does not depend on an inclusive edge.

**`last_seen_at` is pinned to `NOW`.** FR-14's staleness bound is measured against the
test's clock, and the column's default is the wall clock — an event built with the
default would be days stale against a `NOW` in the future, and the candidate read would
drop it before the composition ever saw it. **This is the house pattern in
`make_event`'s docstring, and the reason the positive case would otherwise fail for a
reason that has nothing to do with the opt-out.**

## Files to Create

| File | Purpose |
|------|---------|
| `backend/tests/personalization/test_digest_opt_out_seam.py` | The seam's proof — three tests |

## Files to Modify

| File | Changes |
|------|---------|
| (none) | |

## What this item does not do

- **It does not modify `test_digest_composition.py`.** Its four opt-out tests stay
  exactly as they are and keep passing. **They are not wrong** — they prove the
  composition honours the flag; they just do not prove the *write path* produces it.
- **It does not modify any production code.** The backend already honours the opt-out.
- **It does not add a frontend test.** The frontend's exact-body assertion is item 2's
  and is already there.
- **It does not mock the ORM.** **Fake at the port boundary** — the write goes through
  HTTP, the compose through the command.

## Tests

| Test File | Coverage |
|-----------|----------|
| `backend/tests/personalization/test_digest_opt_out_seam.py` | The opted-out user's digest has no personal event **and** the public fallback took Slot 1 **and** the count is suppressed; the not-opted-out user's personal event is in Slot 1; the opted-back-in user's personal event is back |

**Every assertion can fail.** The opt-out case asserts **which event is in Slot 1**
(`rows["must_know"].event_id == public.id`) — not merely that no personal event is
present. The positive case asserts `rows["must_know"].event_id == personal.id` and
`event_kind == "personal"`. **There are no `or`-fallbacks and no assertions that hold
either way.**

## Technical Details

- **The database marker is `pytestmark = pytest.mark.django_db(databases=[PERSONAL,
  CATALOG])`** — the house default for this package. `PERSONAL` is `"default"` (the
  personal Postgres schema); `CATALOG` is the catalog alias.
- **The user is a real `User`** — `User.objects.create_user(email=..., password="pw")` —
  and `client.force_login(user)`. **`user.pk` is the `user_id` everywhere.** The
  `PersonalEvent` is created with `user_id=user.pk`, **not** a fresh `uuid7()`.
- **The CSRF client** — `tests.csrf.CsrfClient`, which attaches the CSRF token and the
  `origin` header to every unsafe method. Copied from `test_onboarding_api.py`.
- **The `PUT` uses `content_type="application/json"`** — Django Ninja needs it to parse
  the body into `DigestPreferenceIn`.
- **`Actor.system("digest_composition")`** for the compose — the house constant in
  `test_digest_composition.py`. The write's actor is the endpoint's own
  (`_actor(request)` → `Actor.user(request.user.pk)`), which is correct: a user action
  is a user action.
- **The factories are the house ones** — `PersonalEventFactory` (personalization) and
  `EventFactory` + `VenueFactory` (ingestion). **The personal event's `end_utc` is
  derived from `start_utc`**, because the factory's default end is a fixed instant from
  the factory module's own clock and overriding only the start would leave the end
  *before* the start and trip `personal_event_end_after_start_ck`.
- **The public event is in the user's city** and pinned with `last_seen_at=NOW`.
- **`compose_digest` is called directly.** **That is not an AD-11 violation** — the
  architecture check is AST-based over request modules under `apps/`, and `tests/` is
  not scanned. The existing composition tests and `tests/e2e/test_digest_and_detail_proof.py`
  already call it, and the latter says why: *"the scenario calls it directly — the same
  command the worker's task runs."*

### Amendments made during execution

- **The premise was too strong, and the plan now says so.** The work item claimed that
  a write-path regression *"would leave every existing backend test green and the
  product broken."* **Mutation testing showed that `test_onboarding_api.py` catches it**
  — it asserts the response body, and the response body echoes the stored state. The
  plan's *conclusion* stands (the seam still needs proving), but the justification is
  now accurate: **the composition suite's four opt-out tests all write the flag
  directly**, so nothing proved the two halves agree — and only the new file asserts
  the **composed digest**, which is the user-visible consequence rather than a row's
  field.
- **There are two writers of `include_personal_events`, and the endpoint uses the
  onboarding one.** The endpoint's flag write is `onboarding.py:370`, inside
  `set_digest_preference` → `_write_digest`. `digest_preferences.py:336` is a
  **separate** implementation, used by the service path. **The first mutation applied
  to this item was placed at the service path and the new test did not catch it** —
  because that is not the code the endpoint runs. Re-applied at `onboarding.py:370`, it
  was caught immediately. **Neither writer is untested** — `test_digest_preferences.py`
  covers the service path and the new file covers the endpoint path — but a reader who
  assumed one writer would test the wrong code, as the first mutation did.
- **The composition is idempotent per local date, so the opt-back-in test composes
  once.** `_existing_digest` (`digest_composition.py:562`) is consulted at `:699-712`,
  so a second compose returns the persisted first digest unchanged. **Composing while
  opted out and then composing again would read back the first digest and prove nothing
  about the flag.** The test therefore composes **once, after the opt-back-in** — and
  the docstring names the idempotence and the reason, so the next reader does not
  "fix" it back into two composes.
- **`last_seen_at` is pinned to `NOW`, and `end_utc` is derived from `start_utc`.**
  Both are load-bearing, not incidental: an event left at the column default (the wall
  clock) is days stale against a `NOW` in the future and the candidate read would drop
  it, and an end left at the factory's fixed instant would trip
  `end_after_start_ck`. Both are documented in the docstrings.

---

# Work Item 6 of 6: `browser-walkthrough-and-trace` (confirm)

## What this item is

**The intent's closing accounting.** The work item asks for two things: **a real browser
walkthrough** — sign in, find the control, toggle it, see the digest change — and **the
trace** that proves the intent closed what it set out to close.

**The walkthrough is executable.** `frontend/e2e/digest-opt-out.spec.ts` drives the real
stack — a real browser, the real Next.js app, the real Django API, the real database —
and each of the five things the acceptance criteria name is a test that can fail.

**The trace is a document.** `walkthrough.md` records what actually happened, including
the eight findings, and closes FR-19's row in the traceability matrix.

## The three tests, and what each one is for

### 1. `the control is findable, saves, and changes what the digest holds`

**The "findable" part is the one a unit test cannot do.** There is no settings index and
no settings sub-nav, so `/settings/digest` is reachable and otherwise invisible. **The
walkthrough starts at `/settings/quiet-hours` and follows the link** — a test that went
straight to the URL would pass whether the link existed at all.

**Then it reads the control from both sides** — the DOM for what it *shows*, the API for
what the server *holds* — because the seam this intent closed is precisely the gap
between them.

### 2. `the digest the user receives changes: the personal event leaves Slot 1`

**The user-visible consequence.** A control that saves a flag is not a product that
honours the flag, and the *only* test that can say which one this is composes a digest
and looks at it.

**The "before" and the "after" are composed for two different local dates**, each cleared
first, because the composition is idempotent per local date — a digest left by an earlier
run is returned verbatim.

### 3. `a user with no schedule is told what to do, not given a control that fails`

**The honest unavailable state.** `advance_step` past the last step completes onboarding
without writing a `DigestPreference`, so a user with no delivery time is reachable. **The
control is disabled and says *"Set your delivery time first."*** — a sentence the user can
act on where a 422 is not.

## The plan's premise, and what the walkthrough found

**The work item assumed a working harness and a working control.** The control was
working. **The harness was not.**

**Finding 1 — the Playwright web server bound to `localhost`, not `127.0.0.1`.** The
browser and the server ended up on different addresses, the HMR WebSocket could not be
made, and **React never hydrated**. **An unhydrated form has no `onSubmit` handler**, so
the browser falls back to a native GET submit — the URL becomes
`/signin?email=…&password=…`, **no session is established**, and the password is in the
query string. **The pre-existing browse specs failed the same way**, so the e2e suite had
been unable to sign in at all.

**The fix is one line** — the same `--hostname 127.0.0.1` `make web` already uses — and
it is called out in the review report because it changes the behaviour of every e2e test
in the repository.

**Finding 3 — the sign-in throttle made the walkthrough unrepeatable.** Ten sign-ins an
hour per IP; three tests sign in. **The walkthrough now gives the allowance back**
through the product's own `reset_sign_in_throttle` — **not by weakening the throttle.**

**Finding 4 — the composition's idempotence returned a stale digest.** The walkthrough
clears the days it composes for.

**Finding 5 — the accessible name is "the Pulse Digest", not "your".** The walkthrough's
own locator was wrong; the name is now spelled out in the spec.

## What is deliberately not fixed here

**The corpus corrections — the A-5 and A-7 mis-flags, the A-10 ID collision, and FR-16's
remediation pointing at the wrong row — are named, not fixed.** The A-10 collision in
particular is a **corpus defect**: two different amendments share one ID, which makes the
whole amendment ID space unreliable for any tool that reads it. **Fixing it means
renumbering and propagating across the PRD, DESIGN.md, EXPERIENCE.md and the mockups** —
putting a corpus-wide renumbering inside a feature change is exactly the kind of scope
bleed that makes a traceability matrix stop being trustworthy.

**Two product findings are also named rather than fixed**: the two writers of
`include_personal_events` (carried over from item 5), and `advance_step`'s completion
without a preference row — a product question about whether advancing past the digest
step should write a default.

## The trace

**FR-19 moves from *satisfied by machinery, unmet by experience* to met.** The matrix's
row and the trace both point at a place a user can reach: `/settings/digest`, linked from
the quiet-hours page, saving inline, round-tripping a reload.

**The corrections are recorded as follow-up work in a separate intent.**

## Verification

- `cd frontend && npx playwright test e2e/digest-opt-out.spec.ts` → **3 passed**
- `cd frontend && npx playwright test` → **9 passed** (the whole e2e suite)
- `make test-backend` → **6870 passed**
- `make test-web` → **2336 passed**
- `make client` → **no diff** in `frontend/lib/api/` — the AD-19 contract gate
- **Seven mutations**, all caught, all reverted, working tree verified clean
