---
id: frontend-pulse-card
title: The Pulse Card component
intent: pulse-digest-and-trust
complexity: medium
mode: confirm
status: pending
depends_on: [digest-read-api]
created: 2026-10-30
---

# Work Item: The Pulse Card component

## Description

`Card.PulseDigest` — the signature component of the product, used on `/` now and reused card-for-card by `/browse` and the Pulse Preview later. It is a **projection of a `DIGEST_COMPOSITION` row** (AD-10, PRD §3), never a thing that decides anything: everything it shows was decided by the composition service and persisted.

The spec is unusually complete, and where the mockups disagree with it, **the spines win** — EXPERIENCE.md says so in as many words: "if a mockup diverges from a token in `DESIGN.md` or a behavior in this spine, fix the mockup, not the spine."

## Acceptance Criteria

- [ ] **Anatomy, top to bottom** (DESIGN.md `component.card.pulse.digest`): a **3px left-edge category stripe**; a `type.scale.meta.sm` kicker in `color.ink.muted`; a `type.scale.headline.md` headline (22px, **max 8 words**) in `color.ink.primary`; a `type.scale.microtag` row of inline italic tags; a `type.scale.meta.md` source-and-time row; the confidence indicator row at the bottom.
- [ ] **Container:** `color.surface.elevated` fill, 1px `color.border.subtle`, `radius.card` **12px**, `spacing.6` (24px) padding desktop / `spacing.4` (16px) mobile. Hover is a border or background shift only — **no shadow is ever added**. *(The mockup's 14px radius and 32px padding are drift; the tokens govern.)*
- [ ] **Stripes, and the rule that no stripe stands alone.** Public → `color.accent.slate`; must-know → `color.accent.amber`; personal → `color.warm.personal`; discovery → slate at **0.85 opacity** plus a `discovery` micro-tag. Every stripe is **paired with a visible text label on the card** — "Public event", "Must-know", "Personal" — because color is never the sole carrier of meaning (WCAG 1.4.1). A test asserts the label renders for each variant.
- [ ] **Slate, amber and warm-personal are stripe-only.** They never appear on a button, an icon or any interactive surface. *(The mockup's amber-tinted "Why this?" button and its violet `#B59CE8` save button are both violations — the violet is not in any token table at all. Neither is reproduced.)*
- [ ] **Why-this Tags**: up to 3, `type.scale.microtag` (13px, 400, **italic**, body family), `color.ink.muted`. Italic is reserved for this token alone and bold italic is never used. Screen readers announce them as **comma-separated text**. The visual separator (middle dot vs comma) is unresolved across the sources — pick one, apply it everywhere, and record the choice.
- [ ] **`Indicator.Confidence`**: exactly **five positions, always**, 6px `radius.full` dots, 4px apart, filled in `color.ink.primary` and empty in `color.ink.faint`. **Never a bar, never a partial fill, never terracotta.** Default shows **dots only with no visible numeric**, with `aria-label="N of 5"`. Hover, focus-visible and touch-tap open a tooltip whose contributing-factor lines come from the **persisted tags**, not from a recomputation.
- [ ] **`Badge.Source`**: five variants, each with a **visible inline text label** (not icon-only, WCAG 1.1.1), always inline in the card's top-right trust row, **never behind a tap**. `official_site` renders "Official" in `color.accent.terracotta` — one of the four sanctioned terracotta uses. *(The mockup renders it green with a `✅ Verified` label; that is a direct violation of the terracotta rationing rule and is not reproduced.)* `crawled_html` carries its one-time "Why does this show ⚠?" tooltip, once per user per event.
- [ ] **Conflict indicator**: a **6px** filled `color.warn.amber` circle, top-right, `aria-label="Schedule conflict"`, **never red**, symmetric across the conflict pair. *(DESIGN.md L293's "8px" and the mockup's 10px are both stale; ASSUM-13's 6px is locked.)* It **never collapses below 6×6px at any density**.
- [ ] **Density: the trust signals never hide.** At every mode — default, keyboard-focused, hovered, long-pressed — the Why-this Tags, Confidence Pulse and Source Badge are all present. Hover and focus **add** detail; they never remove a trust signal. This is a locked anti-pattern and is tested, not just honored.
- [ ] **Interaction:** the whole card is the tap target and opens `/events/:id`; the `▸` hover affordance is `aria-hidden` and decorative, **not a click target**; keyboard focus shows a 2px `color.accent.terracotta` ring and the `aria-label` reads the full card content, reachable in a **single Tab cycle**; tap targets are **≥44×44 CSS px**.
- [ ] **Motion** is the one sanctioned 240ms opacity transition (`motion.fadeIn`), no transform, and `prefers-reduced-motion` collapses it to an instant change. No animation library (the stack is "UI system: None").
- [ ] **Tokens come from `styles/tokens`**, never as literal hex. `styles/tokens.test.ts` already fails when CSS and `DESIGN.md` disagree; keep it green.
- [ ] Tests cover each stripe variant rendering its text label, all five source-badge variants, the confidence indicator at 1 and 5 and the absence of a visible numeric, the conflict indicator's size and label, the tag cap at 3, the 8-word headline rule, trust signals surviving every density mode, reduced motion, and the full-card tap target.

## Technical Notes

**This component is reused by three surfaces and built once.** Browse (A-10) "reuses `component.card.pulse.digest` vocabulary card-for-card", and the Pulse Preview already renders a structurally identical card with Event Fit data. Build the props so that the *explanation source* is a parameter: a card fed a Relevance Pulse and a card fed an Event Fit look identical on screen, which is exactly why AD-10 insists they are never substituted — the component must make the caller say which it is, and must label it accordingly.

The existing preview page (`frontend/app/preview/page.tsx` and `frontend/lib/event-fit.ts`) already solved part of this for the anonymous case. Read it before building; the work item for the preview card was explicit that its indicator is "**labelled as Event Fit's meaning**", and the digest card's label must differ.

Amendment A-12 caps Browse at 2 stripe colors and drops discovery **there only** — the digest keeps all three treatments. Don't let a future Browse constraint leak backwards into this component.

## Dependencies

- digest-read-api
