---
run: run-eventpulse24-054
work_item: account-delete-confirmation-surface
intent: account-profile-expansion
mode: confirm
checkpoint: plan
approved_at: 2026-11-20
---

# Implementation Plan: The Modal — the Moment Before the Account Goes

## Approach

**A-16's modal, built against the engine that now exists.**

Both halves of A-16's third paragraph shipped in this run — the mail
(`account-deletion-confirmation-email`) and the cancel surface
(`account-deletion-cancel-surface`) — so the modal can now say the sentence the
mockup says without lying. **That sentence is the whole reason this item exists, and it
is the reason the plan below is shaped the way it is.**

### Decision 1 — The modal is its own component, and the danger zone owns whether it is open

**The work item says the section's two-state logic belongs to `account-danger-zone`, and
this item only hangs the modal off the row.** That holds, and it settles the ownership:

| Thing | Owner | Why |
|---|---|---|
| Whether the modal is open | `danger-zone.tsx` (the container) | The container is already the client component that decides which state shows. It now decides three: request row, pending row, and modal-open. |
| The modal's own state | `account-delete-modal.tsx` (a new island) | The input's value, the disabled gate, the focus trap, the in-flight state. |
| What the container learns | `onRequested(scheduledFor)` | The container turns a successful request into the pending state. |

**The container does not fetch anything.** The modal calls
`POST /api/auth/profile/deletion` and answers with `scheduled_for`; the container is
told. **This keeps the container's state machine in one place** — it already owns
`pending` and `kept`, and `pending` now has a second way to become true.

**Why not `router.refresh()`?** It is the project's pattern for a write that changes
server-rendered state (`conflicts-panel.tsx:119`, `onboarding-flow.tsx:105`). But here
the container already holds the answer: **the endpoint returns `scheduled_for`**, and
the modal already has it in hand. A refresh would be a second round trip for a value
the client is already holding, and it would re-render the whole page to change one
row. **The container is told the date, and it renders the pending state itself.** The
date it renders is the server's date — the same one the next `me` read would carry.

### Decision 2 — The three paragraphs are checked against the engine, and two of them change

The work item requires each paragraph to be "true of the engine as built, and checked
against the code rather than against the mockup." **Two of the mockup's three
paragraphs are not true, and one of them is not even the right shape.**

| ¶ | Mockup | The engine | Verdict |
|---|---|---|---|
| 1 | *"We'll permanently delete your account, personal events, saved events, and preference graph within **30 days**."* | `purgeable_models()` purges `personalization.personalevent`, `personalization.savedevent`, `personalization.interest`, `personalization.digestpreference`, `personalization.eventdetailopen`, `personalization.eventdismissal` and the rest. The account itself is deleted last, by hand. **The picture is removed at destruction, not at request.** | **The nouns are right. The verb is wrong.** "Permanently delete … within 30 days" says two things at once, and neither is the engine's: nothing is deleted *within* the 30 days, and the deletion is not permanent at request time. |
| 2 | *"**Anonymized aggregates** (e.g., '47 events were saved in NYC on Aug 27') survive. We can't reverse deletion."* | `DELETION_SURVIVES` in `deletion.py:446` — *"Anonymised aggregate figures survive — counts like 47 events saved in NYC on Aug 27. They are not linked to your account and cannot be traced back to you."* **The backend already holds the canonical copy**, and the mail renders it. | **The mockup's sentence is half a promise the engine does not keep.** "We can't reverse deletion" contradicts the grace period *in the very next paragraph*. The backend's own wording is true and already ships. |
| 3 | *"You can cancel anytime during the 30-day grace from this page or from the email we send."* | Both halves now exist: `DangerZonePending` cancels from the page; `account_deletion.txt` sends the mail. | **True, and shippable as written.** |

**So the modal's body uses the backend's canonical strings, not the mockup's.** This is
the important decision in the plan, and it goes further than it looks:

**`DELETION_REMOVES` and `DELETION_SURVIVES` are already the copy the mail renders.**
Duplicating them into the frontend would be a second place for the same sentence to
live, and the two could drift — the exact failure this project's test report keeps
naming. **So they are not duplicated.** The plan below puts them on the wire.

### Decision 3 — The canonical copy reaches the modal from the API, not from a TS constant

`DELETION_REMOVES` and `DELETION_SURVIVES` live in Python. The frontend cannot import
them, and hard-coding them in TS would be the drift the backend avoided.

**So the backend publishes them.** The plan adds them to
`AccountDeletionRequestOut` — the endpoint's own answer — as two fields. **This is a
contract change, so the client is regenerated** and the OpenAPI stays the contract
(AD-19).

**Why on the request endpoint and not a new one?** The modal needs the copy and the
date in the same answer, and it is asking for the date anyway. A separate copy endpoint
would be a second round trip on the one screen where the modal opens.

**Why is the copy not on `me`?** Because `me` is read on every page, and two paragraphs
of prose on every page's payload is a cost the project has already declined twice —
`me` carries two *dates* and no prose.

**And the frontend renders the words it is given.** The modal does not know what is
deleted; it says what the API told it. **That is the same rule the whole frontend
follows** — the API's words are for the user, and a frontend that replaces them with
its own generic sentence throws away the one line that says what to fix
(`lib/api-errors.ts`, and the copy in `deletion.py`).

### Decision 4 — The modal's anatomy is A-16's, and the two places A-16 conflicts with the project's token rules are resolved without new tokens

A-16 says **no new tokens**. Two of its values are not in the project's closed scale:

| A-16 value | The project's scale | Resolution |
|---|---|---|
| `max-width: 480px` | `--layout-container-{max,reading,form}` = 1180 / 720 / 720 | `max-w-[480px]` — an inline value, not a token. The token test (`styles/tokens.test.ts`) only governs `tokens.css`, so the scale stays closed. |
| `padding: 28px` | spacing is 0, 4, 8, 12, 16, 24, 32, 48, 64, 80, 120 — **no 28** | `p-7` does not exist. **`px-6 py-6` (24px)** is the nearest existing step. **The 4px difference is not worth inventing a token for, and the token test would fail if I did.** |
| `backdrop-filter: blur(8px)` | Tailwind's `backdrop-blur` is 8px by default | `backdrop-blur` — Tailwind's own utility, not a project token, and `--blur-*` is not in the reset list. |

**Every colour, radius and type value A-16 names already exists as a token:**
`rounded-modal` (16px), `rounded-control` (12px), `rounded-subtle` (6px),
`bg-surface-elevated`, `bg-surface-inset`, `text-ink-faint`, `border-border-subtle`,
`shadow-floating`, `text-accent-terracotta`, `text-ink-inverse`.

### Decision 5 — A real `role="dialog"`, with a focus trap this repo has never had

**The research corrected two of the work item's assumptions, and both matter:**

1. **There is no type-to-confirm pattern in this repo.** The work item points at
   `components/sheets/personal-event-form.tsx`, but that file has a *two-press inline
   confirm* — `DangerZone` there asks "Delete it?" and shows "Delete it" / "Keep it".
   **There is no confirm input anywhere in the frontend.** So there is nothing to reuse
   and nothing to extract; the pattern is new.
2. **`Button.Primary` and `Button.Secondary` are DESIGN.md vocabulary, not components.**
   There is no `components/ui/`. Buttons are plain `<button>` elements with Tailwind
   classes written inline, and the house treatment is in
   `components/sheets/personal-event-form.tsx:388-402`.

**So the modal follows `components/digest/mute-prompt.tsx`, which is the only component
in the repo with `role="dialog"` + `aria-modal="true"` + `aria-labelledby` +
`aria-describedby` + focus-restore + Escape.** The house `Sheet` cannot be used: it is
a native `<dialog>`, and `mute-prompt.tsx:40-43` records why that matters — *a native
dialog has no `aria-describedby` slot, because its description is the element's own
text content*, and A-16's description is a separate element from the title.

**A focus trap has to be written, because none exists.** `mute-prompt.tsx` has no trap
either; it relies on there being nothing interactive behind it. **A-16's acceptance
criteria require a trap**, and A-16's modal is a *different* shape from a bottom sheet:
it is centred, it blurs the page behind it, and the page behind it is the settings
screen — which is full of interactive controls. **So the trap is load-bearing here in a
way it is not there.**

The trap is a small, self-contained `useEffect` that keeps Tab inside the panel. It is
**not** a new shared primitive: the plan puts it in the modal file, because a
one-caller hook is not an abstraction yet.

### Decision 6 — The primary's gate is `=== "DELETE"`, and the disabled state is real

A-16 is explicit: `input.value === "DELETE"`, case-sensitive, so `delete` and `Delete`
do not enable it. **The comparison is exactly that — no trim, no case-fold.** A trimmed
comparison would make the gate a suggestion, which is the thing A-16 is against.

**The disabled treatment has no precedent in the repo** — no existing primary button is
ever disabled. A-16 specifies it: `bg-surface-inset`, `text-ink-faint`,
`cursor: not-allowed`. Both tokens exist.

### Decision 7 — A successful request shows the server's date, and a second request is not an error

The endpoint answers `scheduled_for`, and it answers the *same* date on a second
request. **The modal renders that date** — never a hardcoded "30 days", and never a
countdown it computes itself. This is the same rule the pending state already follows
(`danger-zone-pending.tsx:96-105`), and the same rule the mail follows.

**A second request is idempotent and the UI does not present it as an error.** The
endpoint answers 200 with the same date, so the modal shows the same success state.

## Files to Create

| File | Purpose |
|------|---------|
| `frontend/components/settings/account-delete-modal.tsx` | The modal itself — A-16's anatomy, the type-to-confirm gate, the focus trap, the request. A client island. |
| `frontend/components/settings/account-delete-modal.test.tsx` | The modal's own tests — the anatomy, the gate, the focus behaviour, the request, the failure. |
| `backend/tests/identity/test_deletion_copy.py` | The two canonical strings are published, and they are the strings the mail renders. |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/apps/identity/schemas.py` | `AccountDeletionRequestOut` gains `what_is_deleted` and `what_survives` — the canonical copy, so the frontend never keeps its own copy. |
| `backend/apps/identity/api.py` | The POST endpoint answers with the two strings, from the constants `deletion.py` already holds. |
| `backend/apps/identity/services/deletion.py` | The constants move to a place both the mail and the endpoint can import from, if the import direction requires it. |
| `frontend/components/settings/danger-zone.tsx` | Owns the modal's open state; opens the modal from the delete row; takes the scheduled date on success and renders the pending state. |
| `frontend/components/settings/danger-zone.test.tsx` | The row opens the modal; the pending state appears on a successful request. |
| `frontend/app/settings/privacy/page.tsx` | No change expected — the danger zone is already mounted in both branches. Verified, not assumed. |
| `frontend/tests/endpoint-coverage.test.ts` | The `POST /api/auth/profile/deletion` exemption is **deleted, not rewritten**. |
| `frontend/lib/api/openapi.json`, `frontend/lib/api/schema.ts` | Regenerated by `make client` — the two new fields. |

## Tests

| Test File | Coverage |
|-----------|----------|
| `frontend/components/settings/account-delete-modal.test.tsx` | The anatomy (480px, three paragraphs, the input, the two buttons); the gate is case-sensitive; Escape closes; focus moves in and back; the trap holds; the request is literal; the server's date is rendered; a failed request keeps the modal; no new tokens |
| `frontend/components/settings/danger-zone.test.tsx` | The row opens the modal; a successful request moves the section to the pending state with the server's date |
| `frontend/tests/endpoint-coverage.test.ts` | The `DELETE` exemption is still gone and the `POST` exemption is gone too, with no orphan |
| `backend/tests/identity/test_deletion_copy.py` | The endpoint answers with the canonical strings, and they are the strings the mail renders |
| `backend/tests/identity/test_account_deletion_api.py` | The response shape gains the two fields |

## Technical Details

### The modal's DOM, in A-16's order

```
<div role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={bodyId}>
  <h2 id={titleId}>Delete your account?</h2>
  <div id={bodyId}>
    <p>…what is deleted…</p>          {/* from the API */}
    <p>…what survives…</p>            {/* from the API */}
    <p>You can cancel anytime during the 30-day grace from this page or from the email we send.</p>
  </div>
  <label htmlFor={inputId}>Type DELETE to confirm</label>
  <input id={inputId} type="text" placeholder="Type DELETE to confirm"
         autocomplete="off" spellcheck="false" aria-describedby={hintId} />
  <p id={hintId}>Case-sensitive. The button activates once this matches.</p>
  <button>Cancel</button>
  <button disabled={value !== "DELETE"}>Start 30-day deletion</button>
</div>
```

**The backdrop is a sibling of the panel, not a wrapper** — the same shape as
`mute-prompt.tsx`, so a click on it is a click *outside* the dialog. **It is dimmed and
blurred** (`bg-surface-paper/70 backdrop-blur`), which is what A-16 specifies and what
`mute-prompt.tsx` deliberately does *not* do — a modal over a settings screen is an
interruption, and the settings screen behind it is full of controls.

**The backdrop's blur is `backdrop-blur`** (Tailwind's own 8px), and the dim is
`bg-surface-paper/70` — the same value the house `Sheet` uses
(`components/sheets/sheet.tsx`). **No new token is introduced.**

### The three paragraphs, and where each one comes from

| ¶ | Source | It says |
|---|---|---|
| 1 | `AccountDeletionRequestOut.what_is_deleted` — the API | *"Your personal events, your saved events, and your preference graph — the taste we built up about what you like."* |
| 2 | `AccountDeletionRequestOut.what_survives` — the API | *"Anonymised aggregate figures survive — counts like 47 events saved in NYC on Aug 27. They are not linked to your account and cannot be traced back to you."* |
| 3 | **A literal in the frontend** — it is the promise this screen makes, and only this screen can make it | *"You can cancel anytime during the 30-day grace from this page or from the email we send."* |

**Paragraph 3 is the only one written in the frontend, and that is deliberate.** The
other two describe *what the engine does* — a fact the server owns. Paragraph 3
describes *what this product offers* — a promise about the two surfaces, and the only
way a frontend can be sure it is true is to check that both exist. **They do, and this
item is what makes it true at last.**

**The mockup's paragraph 2 is not used.** It ends *"We can't reverse deletion."*, which
contradicts the grace period in paragraph 3 — and the backend's own `DELETION_SURVIVES`
says the true thing instead. **The backend's wording ships, because the mail already
ships it.**

### The focus trap

`Tab` and `Shift+Tab` cycle through the panel's focusable elements and never leave
it. `Escape` closes the modal and returns focus to the trigger. On open, focus moves
to the **confirm input** — not the primary button.

**Why the input and not the primary?** The primary is disabled until the input
matches, so focusing it would put a keyboard user on a control that does nothing.
**The input is the first thing a person has to do**, so it is where the focus belongs.

### The request

```tsx
const response = await api.POST("/api/auth/profile/deletion");
if (response.error) {
  setFailure(saveFailureMessage(response.error, FAILED));
  return;
}
onRequested(response.data.scheduled_for);
```

**The path is written out literally**, because `tests/endpoint-coverage.test.ts`
matches `\.${method}\s*\(\s*"${route}"` — the method and the path have to be adjacent.

**The failure keeps the modal open.** A request that failed did not start a deletion,
and a modal that closed on failure would tell the person their request landed when it
did not. The API's own refusal is shown verbatim, via `saveFailureMessage`.

### The button labels

| Button | Label | Treatment |
|---|---|---|
| Secondary | "Cancel" | `rounded-control border border-border-subtle … text-ink-secondary` |
| Primary | "Start 30-day deletion" | `rounded-control bg-accent-terracotta … text-ink-inverse`, disabled at `bg-surface-inset text-ink-faint cursor-not-allowed` |

**"Start 30-day deletion", not "Delete account".** The engine *schedules*; it does not
delete on this call, and the label tells the truth about what the button does. **Cancel
is never terracotta** — terracotta is rationed, and A-16 says so explicitly.

### What is deliberately not changed

- **The danger zone's row copy.** The mockup says *"Permanent. Cannot be undone."*, and
  that is **false** — the engine holds a thirty-day grace period. The shipped copy is
  correct and stays.
- **The section's own two-state logic.** `account-danger-zone` owns it. This item adds
  a third state — the modal — but does not restructure the other two.
- **The nav row and the page's subheading.** `account-danger-zone` owns them, and they
  already agree.
- **`/settings/privacy` stays a server component.** The modal is a client island the
  danger zone mounts.

---
*Plan for `account-delete-confirmation-surface`. Awaiting approval.*
