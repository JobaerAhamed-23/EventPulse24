---
id: avatar-on-the-shell
title: The Face, Everywhere the Name Already Is
intent: account-profile-expansion
complexity: medium
mode: confirm
status: completed
depends_on:
  - avatar-endpoint-and-contract
created: 2026-11-19
run_id: run-eventpulse24-053
completed_at: 2026-11-20T05:39:55.101Z
---

# Work Item: The Face, Everywhere the Name Already Is

## Description

**The picture goes exactly where the display name already goes** — the sidenav, the
bottom bar and the account sheet. `AppShell` (`frontend/components/shell/app-shell.tsx`)
passes `name` and `email` to `Sidenav` (line 40) and `BottomTabNav` (line 98); the
avatar follows the same path rather than inventing a second one.

**The fallback must not blank anything.** The name has an email-derived fallback through
the one shared helper in `frontend/lib/display-name.ts` — *the stored name when there is
one, the email-derived name when there is not* — and the picture needs the same shape: a
generated initials treatment when no picture is set. **One helper, one implementation,
no second copy to keep in sync**, which is the rule the previous intent established when
it deleted twelve copies of `displayName()`.

**The upload control itself is not save-on-change, and that is the honest break with the
house pattern.** Every other settings island saves on change because the control the
user pressed *is* the change. A file picker has a moment — the file is chosen — and that
moment is the save. **But there is no undo on a file picker**, so a replaced picture is
gone, and the screen says what will happen before it happens rather than after.

**The shell follows the save, as the name does.** The shell is rendered on the server,
so the picture it was drawn with is fixed for the life of the render — and *a save that
does not show up is a save that did not happen*. `frontend/lib/session-name.ts`'s
`publishName` is the precedent, and the avatar publishes the same way after the server
has accepted the write — **never before**, because the server may refuse the file.

## Acceptance Criteria

- [ ] A picture can be chosen, uploaded and removed from `/settings/profile`
- [ ] It appears in the **sidenav, the bottom bar and the account sheet** without a
      reload, after the server accepts the write
- [ ] An account with no picture gets the initials treatment, and **the name is not
      blanked** in any of the three places
- [ ] The initials rule lives in **one** module and is used everywhere — no second copy
- [ ] The API's own refusal is shown **verbatim** when the API refused; the generic
      offline line is shown only when the request never reached the API (the pattern
      `profile-name.tsx` and `save-failure.ts` already set)
- [ ] An upload in flight is announced — `aria-busy`, and the control is not pressable
      twice into two uploads
- [ ] Nothing is published to the shell before the server accepts
- [ ] A removed picture reverts all three places to the initials treatment
- [ ] The image element carries sensible alt text that is **not** the word "avatar"
      repeated in the accessibility tree next to the name that is already there
- [ ] `axe-core` passes on the screen (constitution, PRD §11.5)
- [ ] Vitest covers: upload, failure with an API message, failure offline, remove,
      unset fallback, and the publish-after-accept ordering — each with a mutation probe
- [ ] Run the frontend under **Node 24**

## Technical Notes

- **Read `profile-name.tsx` first.** Its in-flight counter (`saves`, a ref) exists
  because a late response must not overwrite a newer value. An upload has the same
  hazard and a worse one: two uploads racing leave *two* objects, one orphaned.
- **`publishName` is the precedent**, not a thing to duplicate blindly — decide whether
  the avatar rides the same channel or gets its own, and say why.
- **If the storage item chose signed URLs**, a URL rendered on the server can expire
  while the page is open. Decide what the shell does then; a broken image icon in the
  rail is not an acceptable answer.
- **Next's `Image` needs the remote host allowlisted** in `next.config.ts` — and that
  file already carries a long, measured docstring. Keep its standard: say what was
  measured, not what was assumed.

## Dependencies

- `avatar-endpoint-and-contract` — the UI needs the generated client and the `me` field.
