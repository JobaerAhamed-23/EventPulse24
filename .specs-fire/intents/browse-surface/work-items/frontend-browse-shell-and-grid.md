---
id: frontend-browse-shell-and-grid
title: The /browse Route — Hero, Section Heads and the Three-Column Grid
intent: browse-surface
complexity: medium
mode: confirm
status: completed
depends_on:
  - browse-read-api
created: 2026-11-12
run_id: run-eventpulse24-029
completed_at: 2026-11-12T11:43:45.657Z
---

# Work Item: The /browse Route — Hero, Section Heads and the Three-Column Grid

## Description

The route itself: `/browse` inside the existing A-8 shell, rendering the hero, the two
section heads and the card grid. This is `Component.Surface.Browse` minus the search input
and minus the Save button, both of which are their own items — the grid renders cards with
a Save slot that the later item fills.

Amendment A-12 is the shape of this work: the surface **inherits the pre-auth city page's
visual vocabulary and refuses its conversion scaffolding.** That distinction is the whole
item. Getting the layout right while letting a Sign-up CTA or the SEO footer ride along
would fail it.

## Acceptance Criteria

- [ ] `/browse` renders inside the existing authed shell (sidenav + brand-only topbar +
      sidenav footer); the shell markup is not forked or re-implemented
- [ ] Hero renders: terracotta-dot eyebrow (`Brooklyn · Tonight + 7 days`, uppercase,
      letter-spaced, ink-muted), `Text.Display.xl` h1 with the city in terracotta italic
      `<em>`, lede at max-width 600px, and the city-meta pill
- [ ] The city-meta pill shows city, event count for the week, and a **Change city** link
      routing to `/settings/account`
- [ ] The quota note renders below the pill in `Text.Meta.md` mono — "Free plan: N of 1 save
      used today · resets {time}" — reading the quota state from the API, not a client guess
- [ ] Section head 1 is `Text.Display.sm` "3 worth your attention today" + mono meta
      "{city} · {weekday, date}"; section head 2 is "More this week" + mono meta
      "{n} events · scroll for more"
- [ ] The persona-prefixed "Maya-fit" copy from the city page is **not** carried over
- [ ] Grid is `repeat(3, minmax(0, 1fr))` with 20px gap at ≥1280px, 2-col at 1024–1279px,
      1-col below; `.main` uses `padding: 0 32px` and **not** the city page's full-bleed
      80px frame wrapper
- [ ] Cards use 22px padding and an 18px headline — the denser Browse sizing, not the
      digest's
- [ ] **Stripes are capped at two colours**: slate for public, amber for must-know. No
      discovery stripe exists anywhere in the markup or the stylesheet
- [ ] **No Sign-up row, no How-it-works CTA, no SEO neighbour-cities footer** — absent from
      the markup, not hidden with CSS. A test asserts their absence by query, so a later
      regression that adds one fails
- [ ] Soft cap at 24 cards, with a `Text.Meta` "More events below" anchor loading the next
      chunk in place — no pagination chrome, no page numbers, no "Load more" button
- [ ] Zero-events state renders `component.emptystate.quiet`: "Nothing nearby tonight. Try a
      wider city?" + a "Change city" link to `/settings/account`
- [ ] Loading state renders 12 card-shaped skeletons in the existing digest skeleton
      vocabulary — 1800ms pulse, no spinners
- [ ] Error state renders "Couldn't reach Browse. Try again." with one retry button, and the
      sidenav and bottom-tab stay functional so the user can escape
- [ ] No new colour tokens, CSS variables or spacing tokens are introduced
- [ ] Accessibility: the page has one h1, the section heads are real headings in order, and
      the a11y test suite passes as the other surfaces' do

## Technical Notes

`mockups/browse-desktop.html` is the reference for the default state and
`browse-desktop-empty.html` for the empty-result state. Read their **entire** leading
comment blocks — the Browse mockups carry their locks in the header, and
`browse-desktop.html`'s header names each anti-pattern it is deliberately missing.

The existing `components/city-page/city-page.tsx` is the closest built analogue for the hero
and grid vocabulary, and the closest trap: it is the pre-auth surface, so it carries exactly
the CTA and footer scaffolding A-12 forbids here. Read it for structure; do not extend it.

## Dependencies

- browse-read-api
