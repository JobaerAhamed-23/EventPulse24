---
id: legal-page-routes
title: /terms and /privacy are promised on every auth screen and 404 — build the
  routes
intent: broken-links-and-legal-pages
complexity: medium
mode: confirm
status: in_progress
depends_on: []
created: 2026-11-20
---

# Work Item: The two routes the consent sentence depends on

## Description

Both auth screens print *"By creating an account, you agree to our **Terms** and **Privacy
Policy**."* and link both phrases. **Neither route exists.** Four link sites, two
destinations, 404 on all of them:

| File | Line | Link |
|---|---|---|
| `components/auth/signup-form.tsx` | 253 | `/terms` |
| `components/auth/signup-form.tsx` | 257 | `/privacy` |
| `app/signin/page.tsx` | 65 | `/terms` |
| `app/signin/page.tsx` | 69 | `/privacy` |

This is the only 404 in the product that a user is asked to *agree to* before they can
proceed, which is what separates it from the `/suggest` case.

**This work item builds the vessels, not the words.** Routes, chrome, typography,
navigation and the draft notice. The copy is `legal-copy-draft`, and it is kept separate so
that the plumbing can be reviewed as plumbing and the claims can be reviewed as claims.

## Acceptance Criteria

- [ ] `/terms` and `/privacy` exist as routes and render; all four links resolve
- [ ] Both use the **pre-auth chrome** — `Component.Topbar.PreAuth` and the pre-auth page
      footer, the same family `/signin`, `/signup`, `/pricing` and `/preview` use. These are
      pre-auth surfaces by definition: they are read *before* the account exists
- [ ] Neither route requires a session, and neither redirects to onboarding. Verified
      against `lib/session.ts`, which currently routes unauthenticated users to `/preview`
      or `/onboarding`
- [ ] Both carry a **visible, unmissable notice** that the text is an unreviewed draft
      describing current behaviour, not legal advice, and that it has not been reviewed by
      counsel. Not a footnote — a banner at the top, before the first clause
- [ ] Both carry a **last-updated date** rendered from a single source, not hand-typed in
      two places
- [ ] Long-document typography: readable measure (`layout.container.reading`), real heading
      hierarchy, anchor-linkable section ids so a clause can be cited
- [ ] Both pages are reachable, keyboard-navigable and announce correctly — they are the
      pages a screen-reader user is most likely to need read aloud in full
- [ ] A route-level test asserts both render and that the draft banner is present. **The
      banner assertion must be able to fail** — it is the one element whose removal would
      change what the page claims about itself
- [ ] `app/sitemap.ts` and `robots.ts` are reviewed: legal pages are normally indexable, and
      a deliberate choice is recorded either way

## Technical Notes

- Content shape is the next work item's problem, but the **route must not ship with lorem or
  with an empty body** — if `legal-copy-draft` is not done when this lands, the pages carry
  only the draft banner and a one-line "this document is being written" statement. A page
  that is blank reads as broken; a page that says what it is reads as honest.
- `EXPERIENCE.md` §473 locks the auth footnote's wording. **This work item changes no copy on
  `/signin` or `/signup`** — the words already there simply begin to resolve. If the hrefs
  are correct as written (they are), those two files are not touched at all.
- There is no mockup for either page. No `mockups/*terms*` or `*privacy*` file exists, and
  `/settings/privacy` is a different surface entirely (privacy *settings*, built by
  run-048 for FR-22's ranking transparency). Do not reuse its layout; it is an app-shell
  settings screen, not a pre-auth document.
- Check whether the repo prefers MDX, a content constant or plain JSX for long prose before
  choosing. Match whatever `/pricing` does for its longest copy blocks.

## Dependencies

(none)
