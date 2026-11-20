---
run: run-eventpulse24-053
work_item: avatar-on-the-shell
intent: account-profile-expansion
generated: 2026-11-20
mode: confirm
---

# Implementation Walkthrough: The Face, Everywhere the Name Already Is

## Summary

A person can now choose, upload and remove their picture on `/settings/profile`, and the
picture follows them to all three places the shell draws a face — the sidenav's account
row, the bottom bar's More sheet, and the account sheet — **without a reload**, and only
**after the server has accepted the write**. An account with no picture gets the
initials treatment everywhere, and the name beside the face is never blanked. The
initials rule lives in one module and is used by every one of those places, so a second
copy cannot drift away from it.

## Structure Overview

The picture follows **the same path the display name already takes**, rather than
inventing a second one.

The server renders the shell with the picture the account holds. That is the **seed**.
The picture is then *live* in the client: a small module store holds the published URL,
and every place that draws a face reads it through a hook that prefers the published
value over the seed. So when the island on the profile screen publishes a new URL after
the server accepts the write, the rail, the bottom bar and the sheet all re-read it —
without a navigation and without a reload.

The face itself is **one component**, `AvatarDisc`. It draws the picture when there is
one and the initials when there is not, and it is the same component in all three
places, so the three faces cannot disagree. The initials come from **one pure module**,
`lib/avatar.ts`, which imports nothing and is safe to call from a server component.

The upload lives in **one client island** on the profile screen. It owns the file
input, the removal button, the in-flight state and the failure line, and it is the
only thing in the frontend that publishes a picture. It publishes **only after the
server has accepted**, because the server validates the bytes, re-encodes them and may
refuse the file outright — a URL published early would name a picture that does not
exist.

**Nothing is published before the server accepts**, and **two uploads can never race**
— a second choice while a write is in flight is refused in the handler, not merely by
the input's `disabled` attribute.

## Architecture

### Pattern Used

**A module-scoped external store read through `useSyncExternalStore`** — the pattern
`lib/session-name.ts` already established for the display name, applied to a second,
separate channel for the picture.

**Why a second channel rather than a shared one.** The name's store publishes a
*string*; the picture's store publishes a *URL*, and a URL has two properties a name
does not have: **it changes when the picture is replaced** (the `{version}` segment is
the version), and **it becomes `""` when the picture is removed** — the account's state
is *no picture*, not *a picture of nothing*. One store per value, one rule each.

**Why the rule and the store are separate modules.** `lib/avatar.ts` is a pure function
that imports nothing and may be called from a server component; `lib/avatar-store.ts` is
React plumbing only the client has. Mixing them would make the rule un-importable on
the server.

### Layer Structure

```text
┌──────────────────────────────────────────────────────────┐
│  Presentation                                             │
│  components/settings/avatar-upload.tsx   (the island)     │
│  components/shell/avatar-disc.tsx        (the one disc)   │
├──────────────────────────────────────────────────────────┤
│  Application (the live channel)                          │
│  lib/avatar-store.ts   publishAvatar / useLiveAvatar     │
├──────────────────────────────────────────────────────────┤
│  Domain (the one rule)                                   │
│  lib/avatar.ts         initials(name)                    │
├──────────────────────────────────────────────────────────┤
│  Infrastructure                                          │
│  lib/avatar-upload.ts  multipart POST / DELETE           │
│  lib/api/              generated client (AD-19)          │
└──────────────────────────────────────────────────────────┘
```

**The data flow, end to end.**

```text
  person picks a file
          │
          ▼
  AvatarUpload island  ──►  POST /api/auth/profile/avatar
          │                          │
          │                     server validates, re-encodes,
          │                     may refuse
          │                          │
          │              ┌───────────┴───────────┐
          │              │                       │
          │           refused                 accepted
          │              │                       │
          ▼              ▼                       ▼
   API's own      nothing published     publishAvatar(url)
   message,                                  │
   verbatim                                  ▼
   (or the                            useLiveAvatar → the rail,
   offline line)                       the bottom bar, the sheet
```

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `frontend/lib/avatar.ts` | **The one** initials rule — `initials(name)`, server-safe, imports nothing |
| `frontend/lib/avatar-store.ts` | The published-URL store — `publishAvatar`, `useLiveAvatar` |
| `frontend/lib/avatar.test.ts` | The initials rule, pinned (10 tests) |
| `frontend/components/shell/avatar-disc.tsx` | **The one** disc — picture or initials, `alt=""`, `aria-hidden` |
| `frontend/components/shell/avatar-disc.test.tsx` | The disc's fallback and alt-text rules (7 tests) |
| `frontend/components/settings/avatar-upload.tsx` | The upload/remove island on `/settings/profile` |
| `frontend/components/settings/avatar-upload.test.tsx` | Upload, refusal, offline, remove, in-flight, publish-ordering (18 tests) |
| `frontend/tests/avatar-in-the-shell.test.tsx` | The shell follows the picture — all three places, no reload (8 tests) |

### Modified

| File | Changes |
|------|---------|
| `frontend/lib/avatar-upload.ts` | **Reused, not forked.** It already spoke multipart; `AvatarResult` became the island's contract |
| `frontend/components/shell/account-menu.tsx` | The local `Avatar` component **deleted** — it was a second copy of the initials rule. `AvatarDisc` used instead; the row and the panel both read the live picture |
| `frontend/components/shell/app-shell.tsx` | Gains `avatarUrl` and threads it to both navs |
| `frontend/components/shell/sidenav.tsx` | `AccountMenu` gains `avatarUrl` |
| `frontend/components/shell/bottom-tab-nav.tsx` | `MoreMenu` gains `avatarUrl` |
| `frontend/components/shell/more-menu.tsx` | `AccountPanel` gains `avatarUrl` |
| `frontend/app/settings/profile/page.tsx` | The picture island mounted above the name; `avatarUrl` from `me` into the shell; the header copy names the picture |
| `frontend/app/page.tsx`, `timeline`, `browse`, `conflicts`, `events/[id]`, `events/[id]/reminders`, `personal-events/[id]/reminders`, `settings/*` (15 files) | `avatarUrl={session.user.avatar_url}` into `AppShell` |
| `frontend/next.config.ts` | The docstring records the **measurement** that no `images.remotePatterns` is needed |
| `frontend/tests/architecture.test.ts` | A new rule: the initials rule is written once, in `lib/avatar.ts`, and reached through the shared helper |
| `frontend/tests/settings-routes.test.ts` | The source-text rule that went vacuous when the shell's opening became multi-line — fixed |
| `frontend/components/shell/account-menu.test.tsx`, `nav-routes.test.tsx`, `frontend/tests/live-display-name.test.tsx` | The new required `avatarUrl` prop added to each render call |

## Key Implementation Details

### 1. The picture is published only after the server accepts

The shell is rendered on the server, so the picture it was drawn with is fixed for the
life of that render — and **a save that does not show up is a save that did not happen**.

So the island publishes the new URL to the shell **after** the server's answer and on
no other path. The server validates the bytes, re-encodes them and may refuse the file
outright, so a URL published early would name a picture that does not exist, and the
rail would show a broken face for an upload that was refused.

The same ordering governs the island's own preview: it is written only after the
acceptance, so the screen and the rail can never disagree.

### 2. Two uploads racing would leave two objects

A name is typed a character at a time, and a late response overwrites a newer value —
bad, but recoverable. **Two uploads racing leave two objects in the bucket**, one of
them orphaned, and the account's row points at whichever committed last.

So the control refuses a second choice while a write is in flight — **in the handler,
not only in the `disabled` attribute**, because a disabled attribute is a hint to the
browser rather than a guarantee. The test fires the change event on the disabled input
*on purpose* and asserts no second request went out.

**The consequence, which the plan did not anticipate.** The plan described the in-flight
counter as the thing that stops a late response overwriting a newer picture. With the
guard in place, **two uploads can no longer race through the UI at all**, so that
scenario became unreachable through the screen — and two tests were asserting a state
the UI cannot reach.

**The resolution: the guard is the property, and the counter is the defence in depth
behind it.** The counter costs nothing, and the hazard it defends against is real in
the narrow window where the previous write's `inFlight` has been cleared but its state
update has not committed. **The stronger property replaced the weaker one**, and it is
the one the acceptance criteria actually ask for.

### 3. The failure line is the API's, when the API refused

The API writes its messages for the person who typed them — *"That file isn't an image
we can read. Try a PNG, JPEG, WebP or GIF."* — and replacing one with a generic
*"Couldn't save."* throws away the only line that says what to change.

So the refusal is shown **verbatim**, and the generic offline line appears **only**
when the request never reached the API, because then the API said nothing to quote.
The test asserts the generic line is **not** shown *alongside* the API's — the API's
verdict replaces it rather than joining it.

### 4. The image is decorative, and that is the whole alt-text decision

The name is beside the disc in text, always. So the picture repeats what the text
already says, and a screen reader that reads both reads the name twice. The image is
therefore `alt=""`, and the disc keeps its `aria-hidden` — the initials fallback is
decorative for the same reason.

**The word "avatar" is never the alt text.** It is a fact about the markup, not about
the person, and an alt of "avatar" next to a name reads as *"avatar, Maya Ahmed"* in the
accessibility tree. A test asserts **no** element anywhere in the document has an alt
containing "avatar".

### 5. A plain `<img>`, not `next/image`

**The URL is same-origin** — `/api/auth/profile/avatar/{version}`, an app-owned path on
the frontend's own origin — so there is no remote host to allowlist, and
`next.config.ts` needs no `images.remotePatterns`.

**And the optimizer could not help anyway.** The URL answers **302** to a freshly-minted
presigned URL, so there is no stable cacheable asset for the optimizer to work on.
**The 302 is the cache-busting strategy, and the `{version}` segment is the version.**
This also answers "the signature expires while the page is open": the URL the shell
carries never carries a signature, so the browser re-mints under it.

The `no-img-element` lint warning is the honest cost of the decision, and it is left
standing rather than suppressed.

## Security Considerations

| Concern | Approach |
|---------|----------|
| File type enforcement | **The server's, not the browser's.** The frontend's `accept` attribute is a convenience for the person choosing a file; the server identifies the format *from the bytes* and may refuse the file outright. A refusal is shown verbatim, so the person is told what to change. |
| Upload authorisation | The write goes through the existing generated client (AD-19) against `POST /api/auth/profile/avatar`, which the backend already authenticates. **No new endpoint was added.** |
| Stored-object scope | The server re-encodes the bytes and stores the object under the account's own key. **The frontend never names a storage path** — it only ever holds the app-owned URL the server hands back. |
| Picture URL exposure | The URL is a same-origin app path with **no signature in it**, so it carries nothing secret. It is not logged, and the avatar store holds it only in memory for the life of the page. |
| The removed picture | A removal deletes the row and the object; the frontend publishes `""`, which is the backend's own "no picture" state — the client never asserts a picture is gone by omission. |

## Performance Considerations

| Requirement | Implementation |
|-------------|----------------|
| The shell must not re-render on every keystroke anywhere | The live picture is read through `useSyncExternalStore` with a **snapshot per subscriber** — a store that returned a new object each read would re-render every subscriber on every store change. |
| One picture, three subscribers | **One module store, three subscribers.** The URL is published once and read by the rail, the bottom bar and the sheet — not copied into three pieces of state that could disagree. |
| The picture must not cause layout shift | The disc's box is fixed by its own size token (`size-8` / `size-[40px]`), and the image fills it with `object-cover`. **The image's dimensions do not depend on the file.** |
| The browser must not serve a stale picture | The URL's `{version}` segment changes when the picture is replaced, so the browser's cache invalidates itself. The server's answer replaces the server's answer — the island never keeps the old URL. |
| The bytes must not sit in the page | The URL carries no signature and the image is fetched once by the browser; there is no base64 payload in the HTML. |

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Where the picture is drawn | **One `AvatarDisc` component**, used by the row, the panel and the preview | Three copies would be three places for the fallback to differ from itself — and the fallback is *what the account looks like* to somebody who has not set a picture. |
| The initials rule | **One pure module**, `lib/avatar.ts`, importing nothing | The acceptance criteria forbid a second copy. The rule must be callable from a server component, so it may not pull in React. |
| The live channel | **A separate store** from the name's | The name publishes a string; the picture publishes a URL that becomes `""` on removal and changes on replacement. One store per value, one rule each. |
| The image element | **A plain `<img>`** | The URL is same-origin and 302s to an expiring signature — the optimizer can neither be configured for it nor help with it. |
| The alt text | **`alt=""`** — decorative | The name is beside the disc in text, always. The picture repeats it. |
| Upload timing | **Save-on-change** — the choice *is* the save | There is no save button, and no second step. |
| The undo | **None, and the screen says so before the choice** | A replaced picture is gone, and the old object is removed when the new one commits. Unlike every other settings island, the copy says what will happen *before* it happens. |
| The in-flight guard | **Enforced in the handler**, not only by `disabled` | A disabled attribute is a hint to the browser, not a guarantee. Two uploads racing leave two orphaned objects. |
| The in-flight counter | **Kept as a ref, as defence in depth** | The guard makes the race unreachable through the UI, but the counter costs nothing and the hazard is real in the window where `inFlight` has cleared but the state update has not committed. |
| `aria-busy` | **On the control *and* on the region** | The control's says the *control* is waiting; the region's says the *section* is. A screen reader user who has activated the picker and moved on needs the second one. |
| The visible control | **A `<label>` for an `sr-only` file input** | A `display: none` input cannot be reached and drops out of the accessibility tree. `sr-only` is out of sight, still focusable, still operable — **the control the person presses is the control a screen reader reaches.** |
| The size of the sheet's disc | **`size-[40px]`**, an exact size | 32px is a step on the spacing scale; **40px is not**, and the scale reset makes off-scale utilities silently absent — which would be a disc with no size rather than an error. |

## Deviations from Plan

**Three**, all recorded because the plan's version was weaker than what shipped.

1. **The in-flight guard was added, and two planned tests were rewritten.** The plan
   described the counter as the mechanism that stops a late response overwriting a
   newer value. Implementation showed the stronger property was available and was what
   the acceptance criteria asked for: **a second choice is refused outright**, not
   queued. The two superseded-write tests now assert *the refusal* (a second choice
   refused, a removal refused mid-upload, and the control working again once the first
   write lands) rather than a race the UI can no longer reach. The counter is retained as
   defence in depth.

2. **`aria-busy` moved onto the file input** as well as the region. The plan said
   *"the region"*. The code review found the codebase's own convention — every other
   settings island puts `aria-busy` on the control — and the control is what a screen
   reader announces as busy. The region kept its marker, with the reasoning written
   down.

3. **The initials rule's module was split from the store, and the store got its own
   file.** The plan's file table listed `frontend/lib/avatar.ts` twice — once for the
   rule, once for the store. Shipping them in one file would have made the pure rule
   import React. They are `lib/avatar.ts` and `lib/avatar-store.ts`.

**A fourth is a test defect rather than a plan deviation, and it is recorded because it
would have shipped a rule with no teeth.** The plan's `tests/settings-routes.test.ts`
rule matched the signed-in `<AppShell>` opening on a single line. Threading `avatarUrl`
made the opening span three lines, so the rule **matched nothing and passed
vacuously**. A mutation probe — deleting `<SettingsNav />` from a branch — left the
test green. The rule now matches the whole opening tag across lines and walks the
source rather than the lines.

## Dependencies Added

| Package | Why Needed |
|---------|------------|
| (none) | **No new dependency.** The island uses the existing generated client (AD-19), the existing `readApiError` helper, and the existing `SaveFeedback` component. `useSyncExternalStore` is React's own. |

## How to Verify

1. **The whole frontend suite, under Node 24**

   ```bash
   cd frontend && export PATH="$HOME/.nvm/versions/node/v24.22.1/bin:$PATH" && pnpm vitest run
   ```

   Expected: **169 test files, 2743 tests, 0 failed.** The suite does **not** run under
   the default Node 20 — it fails with a wall of undici/zstd errors that look like
   broken code and are not.

2. **Just the picture's own tests**

   ```bash
   cd frontend && export PATH="$HOME/.nvm/versions/node/v24.22.1/bin:$PATH" && pnpm vitest run lib/avatar.test.ts components/shell/avatar-disc.test.tsx components/settings/avatar-upload.test.tsx tests/avatar-in-the-shell.test.tsx
   ```

   Expected: **43 passed** — 10 + 7 + 18 + 8.

3. **The types**

   ```bash
   cd frontend && npx tsc --noEmit
   ```

   Expected: clean, no output.

4. **The formatting and the lint**

   ```bash
   cd frontend && npx prettier --check "lib/avatar*.ts" "components/shell/avatar-disc*" "components/settings/avatar-upload*" "tests/avatar-in-the-shell.test.tsx" "tests/settings-routes.test.ts" "tests/architecture.test.ts"
   ```

   Expected: all files matched, no output. `pnpm lint-web` reports **3 pre-existing
   errors** (in `components/settings/email-change.tsx` and
   `e2e/digest-opt-out.spec.ts` — both untouched by this item) and **one deliberate
   warning**, `no-img-element` on `components/shell/avatar-disc.tsx`.

5. **By hand, in the browser**

   Sign in, go to `/settings/profile`, and:

   - **Choose a picture.** The rail's face, the bottom bar's More sheet and the account
     sheet all change **without a reload**, and the control shows a static dot (never a
     spinner) while the upload runs.
   - **Choose a file that is not an image.** The API's own sentence appears —
     *"That file isn't an image we can read. Try a PNG, JPEG, WebP or GIF."* — and
     **not** *"Couldn't save."*
   - **Go offline, then choose a picture.** *"Couldn't save."* appears, because the
     request never reached the API. **The picture you had is still there.**
   - **Remove the picture.** All three places fall back to the initials, and **the name
     beside the face is still there** — never blanked.
   - **Look at the screen with the picture hidden.** The disc is decorative and the
     name is read once. You do not hear the word "avatar".

## Test Coverage

- **Tests added:** 43 across four files (10 + 7 + 18 + 8)
- **Mutation probes:** 14, each confirmed to fail the right test
- **Full frontend suite:** 2743 passed, 0 failed, 0 skipped, 0 type errors
- **Status:** passing

**The probes are the coverage standard here**, because a test that cannot fail proves
nothing. One of them — deleting `<SettingsNav />` from a settings branch — **found a
real hole in the test suite** (a rule that had gone vacuous), which was fixed and
re-probed.

## Ready for Review

- [x] All acceptance criteria met
- [x] Tests passing
- [x] No critical issues
- [x] Documentation updated (if applicable)
- [x] Developer notes captured

## Developer Notes

**The `aria-busy` placement was the one thing this codebase already had an answer to,
and it was not where I first put it.** Every settings island puts `aria-busy` on the
*control* — the name's input, the email's button. A wrapper that holds only a feedback
line says "this region is busy" about a region with nothing in flight. Compare against
the neighbours before inventing a pattern.

**The plan's file table listed `lib/avatar.ts` twice** — once for the rule and once for
the store. A pure function that a server component may call cannot live in the same
file as React plumbing, so they were split. **The rule and the store are two things.**

**`""` is the backend's "no picture" state — not `null`, not absent.** The backend's
`_avatar_url` returns `""` and the schema says `avatar_url: str = ""`. A client that
checked for `null` would show the initials for an account that *has* a picture.

**A `/g` regex and `.test()` do not mix.** The global pattern carries its `lastIndex`
between calls, so the *second* call starts where the first stopped — a rule that passes
on the first branch and silently skips the rest. The counting pattern is now used only
with `matchAll`.

**A source-text rule is a real rule, and it can go vacuous silently.** The
`settings-routes` rule matched a single line; a multi-line tag matches nothing; the
test passed. **A mutation probe is the only thing that finds this** — delete the thing
the rule protects and see if the test notices. The same applies to the *new* rule in
`architecture.test.ts`: it is exempt from its own scan, and it has a planted-mutation
probe of its own.

**Off-scale Tailwind utilities generate no CSS at all.** `size-10` is not on the
spacing scale, so it renders nothing — a disc with no size, rather than an error. The
repo's own convention (stated in the scale test's docstring) is to write the exact size
in brackets: `size-[40px]`. **And watch your own docstrings**: the scale test reads
source text, so a docstring that *mentions* `size-10` fails the test. This one cost a
debugging cycle.

**The `<img>` lint warning is deliberately left standing.** The repo has no precedent
for eslint-disable comments, and the reasoning is written into both the component's
docstring and `next.config.ts`. **A suppressed warning is a warning nobody reads again;
a standing one carries its explanation with it.**

---

*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-053*
