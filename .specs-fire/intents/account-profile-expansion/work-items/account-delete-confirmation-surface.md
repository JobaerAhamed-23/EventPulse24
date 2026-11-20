---
id: account-delete-confirmation-surface
title: The Modal — the Moment Before the Account Goes
intent: account-profile-expansion
complexity: medium
mode: confirm
status: completed
depends_on:
  - account-deletion-and-avatar-removal
  - account-danger-zone
  - account-deletion-confirmation-email
  - account-deletion-cancel-surface
created: 2026-11-20
run_id: run-eventpulse24-054
completed_at: 2026-11-20T10:06:22.942Z
---

# Work Item: The Modal — the Moment Before the Account Goes

## Description

**The account deletion engine shipped. Nothing can call it.**

`account-deletion-and-avatar-removal` built the whole machine: the three commands
(`request_account_deletion`, `cancel_account_deletion`, `destroy_account`), the
`DeletionRequest` model, the 30-day grace period, the worker that destroys expired
accounts, the bucket removal of the stored picture, and the two endpoints —
`POST /api/auth/profile/deletion` and `DELETE /api/auth/profile/deletion`
(`backend/apps/identity/api.py:551,588`).

**It also deliberately shipped without a user-facing surface**, and that decision is
recorded in its own scope note:

> A type-to-confirm modal is a promise made in the product's voice, in three paragraphs,
> describing what the user is agreeing to. Two of those paragraphs would be describing
> behaviour that does not exist. **Building it would be worse than not building it.**

**That reasoning was sound when it was written, and it is now the reason this item
exists.** The two missing paragraphs have since been built — see the sibling items
`account-deletion-confirmation-email` and `account-deletion-cancel-surface` — so the
modal can now be built against a product that keeps every promise it makes in the
modal. **This item builds the modal, and it may only be built once the other two have
landed.**

**The engine is not the half that was missing. The half that was missing is the part a
person touches.** Today an account can be deleted by calling an endpoint, and no human
ever will. The endpoint sits in the committed OpenAPI contract and is exempted from
frontend coverage by an explicit note in `frontend/tests/endpoint-coverage.test.ts:71`
— *"A-16's confirmation modal is not built"* — so the gap is documented but tracked
nowhere as work.

## Where it lives, and what is not this item's job

**The danger zone at `/settings/privacy` is a separate item** —
`account-danger-zone` — because the modal and the cancel surface are two
mutually-referencing states of the same section, and one of them has to own the
container.

**This item builds the modal and the row that opens it.** The section, the nav row
and the section's two-state logic belong to `account-danger-zone`.

**A "Delete account" row on `/settings/profile` instead would be worse**, and the reason
is worth stating: the profile screen is the screen that says *who you are and where you
are*. A destructive, irreversible control sitting beside an avatar upload invites the
accidental click next to the button people use every day. The danger zone exists to put
irreversible things away from the reversible ones, and A-16 already decided where that
is.

## What the modal must say, and the constraint that shapes it

**A-16's third paragraph is the reason this item is not trivial:**

> You can cancel anytime during the 30-day grace from this page or from the email we
> send.

**Both halves of that sentence are promises, and this item must not build a modal that
breaks either.** "From this page" needs the cancel surface — `account-deletion-cancel-surface`.
"The email we send" needs the mail — `account-deletion-confirmation-email`. **The modal
may not ship before both, or it will be a modal that lies in the one paragraph where the
user is deciding whether they can change their mind.**

**The modal's anatomy is fixed by A-16 and must not be re-invented:**

| Part | What A-16 specifies |
|---|---|
| Backdrop | `rgba(10,10,11,0.7)` + `backdrop-filter: blur(8px)`, `role="dialog"`, `aria-modal="true"`, `aria-labelledby` + `aria-describedby` |
| Modal | `max-width: 480px`, `border-radius: 16px`, `padding: 28px`, surface-elevated |
| Header | `Text.Headline.md` — "Delete your account?" |
| Body | **Exactly three** `Text.Body.md` paragraphs: what is deleted / what survives as anonymised aggregates / the 30-day grace |
| Confirm | `<input type="text">`, label "Type DELETE to confirm", **case-sensitive exact match**, `autocomplete="off"`, `spellcheck="false"`, hint "Case-sensitive. The button activates once this matches." |
| Footer | `Button.Secondary` "Cancel" + `Button.Primary` "Start 30-day deletion" |
| Primary gating | **The primary stays disabled until the input matches `DELETE` exactly** |
| Tokens | **No new tokens** — every colour, radius and spacing value already exists |

**The primary button's label is "Start 30-day deletion", not "Delete account"** — and
that is not a wording detail. The engine does not delete on this call; it *schedules*.
The label tells the truth about what the button does.

## Acceptance Criteria

- [ ] The **"Delete account →"** row opens the modal — the row itself is
      `account-danger-zone`'s, this item is what it opens
- [ ] The modal matches A-16's anatomy: 480px, three body paragraphs, the type-to-
      confirm input, the two footer buttons, and **no new design tokens**
- [ ] **The primary is disabled until the input matches `DELETE` exactly** — case-
      sensitive, so `delete` and `Delete` do not enable it
- [ ] The modal is a real dialog: `role="dialog"`, `aria-modal="true"`, labelled by its
      heading and described by its body, focus moves into it on open, `Escape` closes it,
      focus returns to the trigger on close, and a focus trap holds it
- [ ] **The copy matches what the engine actually does** — "Start 30-day deletion", and
      the body says the account keeps working during the grace
- [ ] The body's three paragraphs are **true of the engine as built**, and each claim is
      checked against the code rather than against the mockup:
      - personal events, saved events and the preference graph are deleted — verified
        against `purgeable_models()` in `backend/apps/identity/services/deletion.py`
      - **anonymised aggregates survive** — verified against the analytics pipeline, and
        the wording names the *aggregate*, not the account
      - **the 30-day grace** — verified against `DELETION_GRACE_PERIOD`
        (`backend/shared/constants.py:1065`)
- [ ] **The "cancel from this page" sentence is only in the copy if the cancel surface
      has shipped** — and the "email we send" sentence only if the mail has shipped
- [ ] `POST /api/auth/profile/deletion` is called **only** from this surface, with the
      CSRF token the project already reads from the cookie
- [ ] **A successful request shows the scheduled date**, taken from the endpoint's
      `scheduled_for` — not a hardcoded "30 days" — because the server is what set it
- [ ] A second request is idempotent and the UI does not present it as an error
- [ ] `axe-core` passes on the modal, and the danger zone with it open and closed
- [ ] `frontend/tests/endpoint-coverage.test.ts` no longer exempts
      `POST /api/auth/profile/deletion` — **the exemption is deleted, not rewritten**,
      because it exists to record an unbuilt caller and there is now a built one
- [ ] Run the frontend under **Node 24**

## Technical Notes

- **Read `account-deletion-and-avatar-removal.md` first.** It records why the object is
  removed at destruction rather than at request, and why the grace period is the thing
  the modal must not misstate.
- **The modal is a client component** — it holds the input's value, the disabled state
  and the focus trap. `/settings/privacy` is a server component and stays one.
- **Do not invent a new modal primitive.** Check `frontend/components/` for an existing
  dialog, sheet or overlay first; `frontend/components/sheets/personal-event-form.tsx`
  has a type-to-confirm pattern already, and a second implementation of it is a second
  place to keep in sync. Reuse it if it can carry this copy, and say so if it cannot.
- **The `DELETE` match is `=== "DELETE"`, not a trimmed or case-folded comparison** —
  A-16 says case-sensitive, and "case-insensitive" would make the gate a suggestion.
- **The endpoint answers `scheduled_for`**, and that date is computed once, when the
  request is first made. A later request returns the same date. The UI must render the
  server's date.
- **`/settings/privacy` has no danger zone today** and the settings nav row for Privacy
  describes what is behind it. Both change together — a nav row promising "your data"
  over a page that explains ranking is the exact failure that page's docstring records.
  **The section and the nav row are `account-danger-zone`'s**; this item only hangs the
  modal off the row.
- **`tests/settings-routes.test.ts` forbids hand-written links between settings
  screens.** The danger zone is reached by the nav, not by a link from `/settings/account`.

## Dependencies

- `account-deletion-and-avatar-removal` — the engine, the endpoints and the grace
  period
- `account-danger-zone` — **the section and the row the modal is opened from**
- `account-deletion-confirmation-email` — **the modal's third paragraph names the
  email**, so the copy cannot ship before it
- `account-deletion-cancel-surface` — **the modal's third paragraph names cancelling
  from the page**, so the copy cannot ship before it
