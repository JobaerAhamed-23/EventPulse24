---
id: profile-screen-and-e2e
title: One Screen That Holds All of It — and an e2e That Clicks Through
intent: account-profile-expansion
complexity: medium
mode: confirm
status: completed
depends_on:
  - avatar-on-the-shell
  - email-change-on-the-profile-screen
  - place-on-the-profile-screen
created: 2026-11-19
run_id: run-eventpulse24-053
completed_at: 2026-11-20T06:43:49.702Z
---

# Work Item: One Screen That Holds All of It — and an e2e That Clicks Through

## Description

**The screen's own documentation is now wrong, and that is this item's first job.**
`app/settings/profile/page.tsx` opens with *"the one thing about your account you can
change"* and explains at length why it reads nothing, why it has no `SettingsStates`
shell, and why the email is not changeable. **Three of those statements stop being true
in this intent.** A docstring that argues for a design the code no longer has is worse
than no docstring: the next person believes it.

So this item:

1. **Rewrites the screen's rationale** to the design it now has, including the parts
   that are now *more* complicated — the controls that do not save on change, and why.
2. **Composes the screen**: name, picture, email, place, in an order that reads as a
   profile and not as a changelog of this intent.
3. **Revisits the read.** The screen was built on the fact that it reads nothing — the
   session already carried the name. With an avatar URL and a pending-change state also
   on `me`, **check whether that still holds** before keeping or discarding the
   `SettingsStates` argument. If the screen now has a read that can fail, it needs the
   failure shell it was explicitly denied.
4. **Extends the e2e spec.** `frontend/e2e/profile-name.spec.ts` exists; the settings
   spec was required to reach `/settings/profile` **by clicking**, and that rule holds
   for everything added here.

## Acceptance Criteria

- [ ] The page and component docstrings describe the design the code **now** has; no
      surviving claim that the email cannot be changed or that the screen is one field
- [ ] The screen renders name, picture, email and place as one coherent profile
- [ ] The read question is **answered explicitly**: either the screen still reads
      nothing beyond the session, or it gains the failure shell it needs
- [ ] A signed-out visitor still gets the existing treatment; `homeRoute` ordering
      unchanged and `redirect` still called outside any try/catch
- [ ] The e2e spec reaches `/settings/profile` **by clicking**, and covers: setting a
      name, uploading and removing a picture, requesting an email change, and reaching
      the place controls
- [ ] The e2e asserts the picture and the name appear in the **rail** after a save,
      without a reload
- [ ] The settings sub-nav links to the profile screen from **every** settings screen
- [ ] `axe-core` passes on the finished screen (PRD §11.5)
- [ ] The full frontend and backend suites are green, and the contract test is green
- [ ] Run the frontend under **Node 24**

## Technical Notes

- **Read the existing docstrings before rewriting them.** They record *why* each
  decision was made, and several of those reasons survive even where the conclusion does
  not — the fallback rule, the publish-after-accept rule, the verbatim-API-message rule.
  Keep the reasoning; change the conclusions that changed.
- **This is the integration item.** If it finds that two of the earlier items disagree
  about the screen's shape, that disagreement is a finding to report, not a thing to
  paper over in the layout.

## Dependencies

- `avatar-on-the-shell`
- `email-change-on-the-profile-screen`
- `place-on-the-profile-screen`
