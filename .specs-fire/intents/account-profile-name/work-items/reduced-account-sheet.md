---
id: reduced-account-sheet
title: The Account Sheet, Reduced — One Link and Sign Out
intent: account-profile-name
complexity: low
mode: autopilot
status: completed
depends_on:
  - profile-screen-and-editor
created: 2026-11-13
run_id: run-eventpulse24-032
completed_at: 2026-11-13T12:10:34.881Z
---

# Work Item: The Account Sheet, Reduced — One Link and Sign Out

## Description

**One file.** `frontend/components/shell/account-menu.tsx` (138 lines) opens the sheet
that appears when a person clicks their name in the left rail — or in the bottom bar's
More sheet on mobile.

Today `AccountPanel` renders four things: the avatar, the name, the email, a
**`Settings` link**, a **`Pricing` link**, and `SignOutButton`. After this item it
renders: the avatar, the name, the email, **an "Edit your name" link**, and
`SignOutButton`.

### Remove the `Settings` link

`/settings` **exists** as an index now, and the rail already has a Settings row. The
sheet's own docstring admits the link "is for the mobile overflow sheet, where this
panel renders inline" — but the mobile overflow sheet sits *inside* the bottom bar,
which itself carries a Settings destination. Two ways to the same place, one of them a
dead end from the rail's perspective.

### Remove the `Pricing` link

`/pricing` is a marketing page. The sheet is about the account, not about the upsell —
and the account's plan already has a home, `/settings/account`, which shows the plan,
the payment state and the data export.

### Add the "Edit your name" link

It points at `/settings/profile`, and it is styled like the links it replaces.

### Rewrite the module docstring

**This is not optional polish.** The docstring currently **argues for the two links
this item removes**, and one of its sentences becomes **half false**:

- *"Two links in here, and both are real routes"* — there is one link now.
- *"`/pricing` is where a Free user reads what Pro adds and a Pro user finds the
  portal; it is quiet, because the sheet is about the account, not about the upsell"* —
  the Pricing link is gone, so this sentence has no subject.
- *"Changing an email, changing a password while signed in and closing an account have
  no endpoints yet, so the panel does not offer them: an affordance that cannot work is
  the same lie as a link to a 404."* — **now half false**: the name *does* have an
  endpoint. The docstring must say that the name is the one thing that **can** be
  changed here, and that the email and the password still cannot (the password is
  changed by the reset flow, which ends the account's other sessions).

**The rule this codebase holds its docstrings to:** a docstring that argues for a
position the code has left is the same defect these docstrings exist to prevent. A
docstring is not a record of what the code used to do.

### What does **not** change

`AccountMenu` (the rail's button and the sheet it opens), `Avatar`, the
`AccountProps` type, and `SignOutButton` at the bottom of the panel. **`Sidenav` and
`MoreMenu` do not change** — they render `AccountMenu` / `AccountPanel` with `name` and
`email` props, and they start showing the stored name when the pages pass it (the
`display-name-everywhere` item).

## Acceptance Criteria

- [ ] The account sheet renders the name, the email, **"Edit your name"** and
      **Sign out**
- [ ] There is **no** `Settings` row in the account sheet
- [ ] There is **no** `Pricing` row in the account sheet
- [ ] "Edit your name" links to `/settings/profile` — a route that **exists**
- [ ] "Edit your name" is styled like the links it replaces (ink-secondary, underlined,
      with an offset) — not a button, not a heading
- [ ] `SignOutButton` is still the last thing in the panel
- [ ] The panel still opens as a `Sheet` from the rail's row, and still renders **inline**
      in the bottom bar's More sheet — the two-shapes-one-panel rule is unchanged
- [ ] The module docstring no longer claims two links, no longer defends the Pricing
      link, and now states that the **name is the one thing that can be changed** here
- [ ] The docstring still says the email, the password-while-signed-in and closing the
      account are **not** offered, because they have no endpoints
- [ ] The sheet is reachable and correct at **both** breakpoints — the desktop rail's row
      and the mobile bottom bar's More sheet
- [ ] A test proves the sheet renders "Edit your name" and **not** "Settings" or
      "Pricing", and that the link points at `/settings/profile`

## Technical Notes

- **`AccountPanel` is rendered in two places**: the rail opens it in a `Sheet`
  (`account-menu.tsx:114-118`), and `more-menu.tsx:86` renders it **inline** — because a
  sheet opened from inside a sheet is a second overlay level, and `Sheet` keeps there
  being exactly one. **One change fixes both.** Test both.
- **`MoreMenu` imports `AccountPanel` and the `AccountProps` type** from this module
  (`more-menu.tsx:8`), and `bottom-tab-nav.tsx:7` imports the type. **The `AccountProps`
  type must keep its shape** — `{name, email}` — or those two imports break.
- **`SignOutButton` stays where it is.** Its own docstring says it lives in *"the
  account surface (`AccountPanel`)"*, and it explains why it is not in the topbar: the
  topbar-quiet rule keeps account affordances out of the topbar.
- **The link's copy is "Edit your name", not "Profile".** The section in the settings nav
  is "Profile"; the link says what it does. The rail's Settings row points at the index,
  and the index carries the Profile row — so the two labels are different on purpose.
- **A link to a 404 is the defect this codebase names most often.** The link must point
  at `/settings/profile`, which the `profile-screen-and-editor` item builds.

## Dependencies

- `profile-screen-and-editor` — the link points at `/settings/profile`, and a link to a
  route that does not exist is the exact lie this codebase refuses to tell.
