---
id: browse-surface
title: Browse — the Discovery Surface, and an Honest Test Baseline
status: completed
created: 2026-11-12
completed_at: 2026-11-12T17:08:29.755Z
---

# Intent: Browse — the Discovery Surface, and an Honest Test Baseline

## Goal

Build `/browse`, the one surface this product designed in full and never built, and restore
the backend suite to a state where "green" means something.

Browse is the authed discovery surface: **what is happening in your city tonight and the
next seven days, ranked, with a Save on every card.** It is the counterweight to the
Digest. The Digest is three cards a day and an attention surface; Browse is the fuller list
and a discovery surface. `EXPERIENCE.md` §338 makes the relationship one-way on purpose —
Digest may link to Browse, Browse never links back, because *"saves are the conversion"*.

## Users

- **Any signed-in user who wants more than three cards.** Today there is nowhere to go. The
  Digest caps at three by design (FR-5), the Timeline shows only what is already saved, and
  the public city page at `/events-in/[slug]` is built for crawlers under FR-27 — it carries
  Sign-up CTAs and an SEO footer, and it has no Save affordance at all.
- **Free users at the moment of upgrade.** `save_cap.py` calls the 1-save/day gate *"the
  single thing that turns a Free user into a paying one"*. Browse is where a user meets a
  list worth saving from, so it is where that gate will actually be felt. Right now the gate
  exists and the surface that exercises it does not.
- **Every future run in this repo.** The backend suite has 17 failures on `main`. Until they
  are fixed, no run can say "the tests pass" without a footnote, and a real regression can
  hide in the noise.

## Problem

### 1. Browse is designed, mocked three times over, and unbuilt

This is not an oversight; it is a deliberate deferral that the code documents honestly.
`sidenav.tsx:32` states the rule and applies it:

> **An inert route is a `<span>`, not an `<a>`.** An anchor with `aria-disabled="true"` is
> still focusable and still navigates — the attribute is a hint, not a mechanism — and a
> link to a 404 is a lie about where the label goes.

So three places render a "Coming soon" stub rather than a broken link: `sidenav.tsx:96`,
`more-menu.tsx`, `bottom-tab-nav.tsx:167`. The honesty is the right call. The stub is the
problem.

What exists on the other side of that stub:

| Artifact | State |
|---|---|
| `EXPERIENCE.md` §335–378 `Component.Surface.Browse` | complete — 44 lines of spec, incl. a full anti-pattern lock list |
| `EXPERIENCE.md` §379–386 `Component.Button.Save.Inline` | complete — explicit `idle → saving → saved` state machine |
| `mockups/browse-desktop.html` | complete |
| `mockups/browse-desktop-filtered.html` | complete |
| `mockups/browse-desktop-empty.html` | complete |
| Surface Coverage Map row 14 | `/browse`, binds **FR-26 + FR-48** |
| Route `/browse` | **does not exist** |

### 2. The backend half is closer than it looks, but not close enough

Three reuses were verified against the code at capture, not assumed:

- **Ranking is reusable as-is.** `backend/domain/ranking.py` exposes `relevance_score`,
  `why_this_tags` and `score_bucket` as pure stdlib functions, with no Django and no I/O.
  Browse's two attention tiers ("3 worth your attention today" / "More this week") and the
  cards' why-tag and confidence rows can all call them directly. No new scoring logic.
- **The save gate is reusable as-is.** `apps/personalization/services/save_cap.py` already
  implements FR-48's cap through `ThrottlePort.check` — deliberately *not* a count of
  `SavedEvent` rows, because *"unsaving an event would hand the allowance back"* — and skips
  the gate entirely for Pro.
- **The save endpoint already exists and already fits.** `POST
  /api/personal/saved-events/{catalog_event_id}` returns two 409s told apart by `code`:
  `scheduling_conflict` and `save_cap_reached`. Those map exactly onto the two inline
  failure messages the Save button spec requires. **No new save API is needed.**

What is missing is the read. `GET /api/catalog/events` is the only list endpoint, and its
own description says *"No session is used and none is set."* It cannot serve Browse: no
keyword relevance, no why-tags, no confidence, no saved-state per card, no quota state, and
no notion of whose city it is.

### 3. 17 backend tests fail on `main`, and the count is growing

All 17 are one defect class — hardcoded absolute datetimes that have since passed. The
count rose from 16 to 17 *during* run 028, when `test_reminder_plan_api.py`'s
`AFTERNOON_START` (2026-11-12 02:00 UTC) expired between one run's suite and the next.
Run 027 recommended a clock seam or `freezegun`; it was deferred twice. A suite that fails
for reasons unrelated to the change under test is a suite nobody reads carefully, and this
intent is explicitly meant to end with a demonstration that Browse works.

## Success Criteria

- `make test-backend` is **green** — all 17 date-expiry failures fixed, and the fix is
  structural (a clock seam or `freezegun`), not new hardcoded dates with later years
- `/browse` renders ranked cards for the user's city across a tonight + 7-day window, in two
  attention-tier sections, 24-card soft cap with in-place chunk loading past it
- Inline keyword search filters the loaded set: plain words AND-matched against headline,
  venue line and why-tags; `tag:<token>` literals constrained to the why-tag set
- **"Nothing matched." and "Nothing nearby tonight." are distinguishable** — same
  `component.emptystate.quiet` vocabulary, different copy and different recovery action, so
  the user always knows whether their query or the data is the reason
- Save morphs `idle → saving → saved ✓`, un-saves on re-tap with no confirmation, and the
  two 409 codes surface as the two specified inline messages — never a modal, never a toast
- A Free user who has spent their save sees every Save button in the muted "1 of 1 used
  today" state; a Pro user never does
- All three "Coming soon" stubs become real links, and no `aria-disabled` Browse row remains
- The surface is demonstrated working in a real browser against seeded catalog data, with
  anything broken reported rather than smoothed over

## Constraints

- **The anti-pattern list is a lock, not advice.** No filter chip rail (A-11 lock), no
  discovery stripe (A-12 lock), no more than 2 stripe colours per page, no infinite scroll,
  no count badges, no social proof, no gamification, no upsell carousel, and no pre-auth CTA
  leakage — the Sign-up / How-it-works row and SEO footer are **omitted from the markup**,
  not hidden with `display: none`.
- **Reuse only.** `EXPERIENCE.md` §378: no new hex values, no new CSS variables, no new
  spacing tokens. Every token comes from `component.card.pulse.digest`,
  `component.button.save.inline`, `component.input.search.browse` or
  `component.hero.citypage`.
- **`mockups/city-page-desktop.html` is not touched.** It serves crawlers under FR-27. Browse
  inherits its visual structure, not its conversion scaffolding.
- **House style is binding** (`ARCHITECTURE-SPINE.md` Consistency Conventions): no component
  kit, CSS-custom-property tokens, `data-theme="dark"` default, no `prefers-color-scheme`
  auto-switch, one 240ms `motion.fadeIn`, `<dialog>` for modals.
- **Every test must be able to fail.** No placeholder assertions, no `or`-fallbacks.
- Browse is desktop-first. Mobile reaches it through the existing
  `component.bottom-tab.more-menu` overflow sheet, which is already built and working — only
  its inert row changes.

## Notes

Decisions taken at capture (2026-11-12), each chosen by Jobaer over the stated alternative:

- **Keyword search runs client-side** over the loaded chunk, not server-side with a `q=`
  param. Instant, no round-trip, no indexing decision. **Known limitation, to be recorded in
  the work item rather than hidden:** it searches only what is loaded, so a term matching a
  card past the current chunk will not surface until that chunk loads. Server-side search is
  a later intent if the catalog grows enough to need it.
- **Ranking is reused from `domain/ranking.py`**, not replaced by chronological ordering.
  Chronology was rejected because it would make the section head lie: "3 worth your
  attention today" would mean "the next 3", and the why-tag and confidence rows would have
  nothing to show.
- **The city comes from the existing digest preference** (`DigestPreferenceOut.city`, set at
  onboarding), not a Browse-specific override. This keeps one meaning of "your city" across
  both surfaces, and it is why "Change city" routes to `/settings/account` as the design
  says.
- **The 17 failing tests are fixed first, inside this intent**, rather than deferred again or
  split into a follow-up. Every later item here is verified against the result.
- **Verification is automated tests plus a real browser walk-through** driven by me, with
  findings reported as found.

Deferred deliberately, not forgotten:

- **`g b` and the whole keyboard-shortcut layer.** `EXPERIENCE.md` §290 specifies `g d` /
  `g t` / `g a` / `g b` / `g c` / `g s`. **None of them exist** — a search of the frontend
  found no `keydown` handler anywhere. Building the shortcut layer is a sixfold change to
  global navigation, not a Browse detail, and shipping only `g b` would be the one shortcut
  in a set of six. It belongs in its own intent.
- **Server-side search**, per the client-side decision above.
