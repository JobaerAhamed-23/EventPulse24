---
title: "DESIGN.md — EventPulse24"
status: final
created: 2026-08-23
updated: 2026-08-23
project: EventPulse24
source_prd: _bmad-output/planning-artifacts/prds/prd-EventPulse24-2026-08-19/prd.md
source_brief: _bmad-output/planning-artifacts/briefs/brief-EventPulse24-2026-08-19/brief.md
references:
  experience: EXPERIENCE.md
  spec: https://github.com/google-labs-code/design.md
  prd: _bmad-output/planning-artifacts/prds/prd-EventPulse24-2026-08-19/prd.md
  reconcile: _bmad-output/planning-artifacts/prds/prd-EventPulse24-2026-08-19/reconcile-blue-ocean.md
  reference_editorial: .agents/skills/bmad-ux/assets/design-example-editorial.md
  reference_shadcn: .agents/skills/bmad-ux/assets/design-example-shadcn.md
---

## Brand & Style

EventPulse24 is a calm intelligence layer for events. The product sits above every event source and answers one question — *what's actually worth my attention right now* — without asking the user to maintain a system.

The brand posture is **Editorial Calm**. The visual reference is the "Headspace of events": a Headspace-grade feel of restraint and pacing, applied to the discovery and triage of nearby events. It is deliberately **anti-Eventbrite** — anti the bright badges, the social-proof counters, the upsell carousel, the loud category tinting, the streak popup. Where Eventbrite sells tickets, EventPulse24 sells attention.

The aesthetic posture is paper-like: a warm near-white canvas, ink-black type, one warm accent (terracotta) used with intention, no neon, no glassmorphism, no gradient surfaces. Information earns its place on the page. Whitespace is the default; density is the exception. The page reads like an editorial — a short headline, a measured lede, a category stripe, an italic micro-tag, a quiet source attribution.

Anti-patterns that must not appear anywhere in the product:

- No notification badges (red dots, unread counters).
- No streak popups or "you checked in 7 days in a row!" surfaces.
- No social-proof counters ("234 people going").
- No infinite scroll.
- No category-tinted card floods (six different bright card colors stacked).
- No gamification chrome (progress bars, badges, leaderboards).
- No upsell carousels or "you might also like" rails beyond three suggestions.

The visual rule: if it would feel at home on Eventbrite, Meetup, or a gaming app, it does not belong here.

## Colors

The palette is paper-and-ink plus one warm accent. Editorial Calm has a dark mode: paper becomes ink, ink becomes paper, terracotta stays terracotta but loses saturation. Tokens use path-style names so `EXPERIENCE.md` can cross-reference with `{color.accent.terracotta}` syntax.

[ASSUMPTION: Hex values below are estimated from named descriptions; calibrate against final brand sampling before engineering. Terracotta `#C4502B` was provided; the rest are derived from the warm-neutral palette direction.]

### Light mode

- `color.surface.paper` — `#FAF8F4`. Base canvas. Used for the page background, the dominant surface. Near-white, slightly warm (paper, not screen white).
- `color.surface.elevated` — `#FFFFFF`. Cards, sheets, popovers. Sits on top of `color.surface.paper`.
- `color.surface.subtle` — `#F1ECE3`. Page-2 backgrounds, dividers, hover affordance on ghost rows, the "no events" empty state fill.
- `color.surface.inset` — `#EDE7DA`. Inset wells (e.g., the search field resting state, a nested grouping block).
- `color.ink.primary` — `#1A1814`. Headlines, serif display, the highest-contrast text. Slightly warm black, not pure `#000`.
- `color.ink.secondary` — `#3A352D`. Body copy, input text. Softer than primary but still high contrast.
- `color.ink.muted` — `#7A7066`. Metadata, timestamps, helper text, source attribution labels.
- `color.ink.inverse` — `#FAF8F4`. Text on dark fills (e.g., the terracotta CTA label).
- `color.accent.terracotta` — `#C4502B`. Single warm accent. Used only for: the `Indicator.Today` dot, the `Button.Primary` fill, the `Badge.Source.verified` fill. Nothing else.
- `color.accent.slate` — `#5B6B7E`. Cool secondary. Used only for: the public-event category stripe on `Card.PulseDigest`, the surprise / discovery card category stripe. No other use.
- `color.accent.amber` — `#C77A2C`. Warm secondary, distinct from terracotta. Used only for: the must-know card category stripe on `Card.PulseDigest`. Used sparingly; should not appear on more than ~10% of cards in any view.
- `color.signal.success` — `#4A7A4A`. Reminder confirmed, source verified success state. Muted, not vivid.
- `color.signal.warn` — `#B8893A`. Schedule conflict, partial information, soft warning. Muted amber, lower saturation than `color.accent.amber`.
- `color.signal.error` — `#8E2A1F`. Rare; reserved for destructive actions (remove reminder permanently, delete account). Not used inline on cards.
- `color.border.subtle` — `rgba(26, 24, 20, 0.08)`. The 1px border on cards and inputs. Ink at 8% opacity.
- `color.border.strong` — `rgba(26, 24, 20, 0.16)`. Focused-input border, active row in a list.

### Dark mode

Editorial Calm has dark mode. Paper inverts to ink, ink inverts to paper, terracotta stays terracotta but loses saturation by ~15%.

- `color.surface.paper` — `#15140F`. Base canvas in dark mode — warm near-black, not pure `#000`.
- `color.surface.elevated` — `#1E1C17`. Cards and sheets on dark.
- `color.surface.subtle` — `#25221B`. Page-2 backgrounds and dividers.
- `color.surface.inset` — `#2C2820`. Inset wells.
- `color.ink.primary` — `#F2EFE8`. Headlines on dark — warm near-white.
- `color.ink.secondary` — `#D6D1C5`. Body copy on dark.
- `color.ink.muted` — `#8C8478`. Metadata on dark.
- `color.ink.inverse` — `#15140F`. Text on light fills (e.g., terracotta CTA label in dark mode).
- `color.accent.terracotta` — `#D88A6E`. Terracotta reduced saturation for dark surfaces. Still reserved for the same three uses (today indicator, primary CTA, verified badge).
- `color.accent.slate` — `#7E91A6`. Slate brightened for dark contrast on category stripes.
- `color.accent.amber` — `#D8A06A`. Amber warm-secondary, adjusted for dark.
- `color.signal.success` — `#7AAA7A`.
- `color.signal.warn` — `#D8A86A`.
- `color.signal.error` — `#C66A5C`.
- `color.border.subtle` — `rgba(242, 239, 232, 0.10)`.
- `color.border.strong` — `rgba(242, 239, 232, 0.20)`.

### Color usage rules

- `color.accent.terracotta` is the only chromatic accent. Its three sanctioned uses are the today indicator, the primary CTA, and the verified source badge. It does not appear on hover, focus rings, or link underlines.
- `color.accent.slate` and `color.accent.amber` are reserved exclusively for category stripes on `Card.PulseDigest`. They are not used for buttons, icons, or interactive surfaces.
- `color.signal.success`, `color.signal.warn`, and `color.signal.error` are signal colors, not brand colors. They appear only at the moment of state change, never as decoration.

## Typography

Three type families. Headlines use a serif for the editorial voice. Body uses a sans for clarity and screen readability. Mono is reserved for confidence numerics (the 1–5 dot counts) and any timestamp that requires non-ambiguous digit rendering.

[ASSUMPTION: The locked chain is `Source Serif 4` with `Fraunces` as fallback. If engineering prefers a different serif, swap the family name only — the scale and roles below are the contract.]

### Type families

- `type.family.display` — `Source Serif 4, Fraunces, Georgia, serif`. Headlines and editorial display moments.
- `type.family.body` — `Inter, -apple-system, system-ui, sans-serif`. Body copy, labels, navigation, buttons.
- `type.family.mono` — `JetBrains Mono, ui-monospace, SFMono-Regular, monospace`. Confidence numerics, ambiguous timestamps.

### Type scale (desktop)

- `type.scale.display.lg` — 48px / 1.10 / 700 / display. Reserved for the page hero (e.g., the Today view opening line).
- `type.scale.display.md` — 36px / 1.15 / 700 / display. Reserved for empty-state hero text and the project introduction.
- `type.scale.headline.lg` — 28px / 1.20 / 600 / display. Section openers within a page.
- `type.scale.headline.md` — 22px / 1.25 / 600 / display. Card headlines on `Card.PulseDigest`.
- `type.scale.headline.sm` — 18px / 1.30 / 600 / display. Inline editorial callouts.
- `type.scale.body.lg` — 18px / 1.55 / 400 / body. Article body, lede copy.
- `type.scale.body.md` — 16px / 1.55 / 400 / body. Default body copy, button text.
- `type.scale.body.sm` — 14px / 1.50 / 400 / body. Dense list rows, secondary copy.
- `type.scale.meta.md` — 14px / 1.45 / 500 / body. Timestamps, source labels.
- `type.scale.meta.sm` — 12px / 1.45 / 500 / body. Caption, legal microcopy, axis labels.
- `type.scale.microtag` — 13px / 1.40 / 400 italic / body. The "nearby · tonight · music" inline italic micro-tags.
- `type.scale.numeric` — 14px / 1.40 / 600 / mono. Confidence dot counts, durations.

### Type scale (mobile)

Mobile is slightly tighter. The 48 and 36 display sizes step down; body sizes are preserved.

- `type.scale.display.lg.mobile` — 36px / 1.10 / 700 / display.
- `type.scale.display.md.mobile` — 28px / 1.15 / 700 / display.
- `type.scale.headline.lg.mobile` — 22px / 1.20 / 600 / display.
- `type.scale.headline.md.mobile` — 18px / 1.25 / 600 / display.

All other tokens remain unchanged on mobile.

### Weight pairs

- 400 — body, captions, micro-tags.
- 600 — emphasis inside body, headlines, card titles, buttons.
- 700 — display-only (reserved for `type.scale.display.lg` and `type.scale.display.md`).

### Italic usage

Italic is reserved for the `type.scale.microtag` token. Italic is the language of the "why this?" hint — it is conversational, never emphatic. Bold italic is not used.

## Layout & Spacing

The grid is a **4px base**. All spacing tokens are multiples of 4. Generous whitespace is a brand commitment — mobile is 24px page-padded, desktop is 80px page-padded with a 32px card spacing rhythm.

### Spacing scale

- `spacing.0` — 0.
- `spacing.1` — 4px.
- `spacing.2` — 8px.
- `spacing.3` — 12px.
- `spacing.4` — 16px.
- `spacing.6` — 24px.
- `spacing.8` — 32px.
- `spacing.12` — 48px.
- `spacing.16` — 64px.
- `spacing.20` — 80px.
- `spacing.30` — 120px.

### Layout tokens

- `layout.page.padding.mobile` — `{spacing.6}` (24px). Page edge inset on viewports <768px.
- `layout.page.padding.desktop` — `{spacing.20}` (80px). Page edge inset on viewports ≥1024px.
- `layout.page.padding.tablet` — `{spacing.12}` (48px). Viewports 768–1023px.
- `layout.card.spacing.mobile` — `{spacing.4}` (16px). Vertical gap between cards on mobile.
- `layout.card.spacing.desktop` — `{spacing.8}` (32px). Vertical gap between cards on desktop.
- `layout.container.max` — 1180px. Maximum content width on desktop; content is centered with the 80px gutter eating the rest.
- `layout.container.reading` — 720px. The single-column reading width used inside event detail and explanation surfaces.
- `layout.section.gap` — `{spacing.16}` (64px). Vertical gap between major page sections.
- `layout.section.gap.large` — `{spacing.20}` (80px). Hero-to-first-section gap.
- `layout.grid.columns` — 12. Desktop grid; cards typically span 6 or 12 columns depending on density.

### Breakpoints

- `breakpoint.mobile` — max-width 767px. Single column, 24px padding.
- `breakpoint.tablet` — 768–1023px. Single column, 48px padding.
- `breakpoint.desktop` — 1024px+. Up to 12-column grid, 80px padding, max content 1180px.

## Elevation & Depth

Editorial Calm communicates depth with **tonal layering and one shadow**. No glow. No neon. No glassmorphism.

- Cards and sheets use a 1px border (`color.border.subtle`) instead of shadow to sit above `color.surface.paper`.
- The one allowed shadow is reserved for floating surfaces — modals, popovers, the command-palette overlay: `0 8px 24px rgba(0, 0, 0, 0.08)`. Tinted toward ink, not toward terracotta or slate.
- Hover on a card does not add shadow. Hover is communicated by a 1px transition from `color.border.subtle` to `color.border.strong`. That's the entire hover affordance.
- Focus rings are 2px solid `color.ink.primary` at 100% opacity, with a 2px offset. No glow, no chromatic focus ring.

## Shapes

The shape language is **mostly square with subtle rounding**. Card corners are 8px. Inputs are 4px. Primary CTA corners are 12px — the most generous radius in the system, reserved for the single most important affordance per surface. There are no pill buttons.

- `radius.none` — 0.
- `radius.subtle` — 4px. Inputs, chips, meta tags, the resting-state of small controls.
- `radius.card` — 8px. Cards, sheets, list rows that need their own edge.
- `radius.control` — 12px. Reserved exclusively for `Button.Primary`. The contrast in radius between the primary CTA (12px) and the secondary button (8px) is part of the visual hierarchy.
- `radius.modal` — 8px (same as `radius.card`). Modals do not get a distinct radius — they get the shadow instead.
- `radius.full` — 9999px. Reserved for the terracotta `Indicator.Today` dot and the dots in `Indicator.Confidence`. Never used for buttons or chips.

Stroke language:

- `stroke.hairline` — 1px solid `color.border.subtle`. Default card and input border.
- `stroke.strong` — 1px solid `color.border.strong`. Focused inputs, active rows.
- `stroke.focus` — 2px solid `color.ink.primary`, 2px offset. Focus ring, no chromatic variant.

## Components

Components are named in dotted path notation so `EXPERIENCE.md` can cross-reference each one with `{component.surface.canvas}` syntax. Each entry below states its anatomy, color usage, and intent in one paragraph.

### Surfaces

- `component.surface.canvas` — The full-bleed page background. `{color.surface.paper}` fill, no border, no shadow. The single anchoring surface of the product.
- `component.surface.card` — The `Card.PulseDigest` container. `{color.surface.elevated}` fill, 1px `{color.border.subtle}` stroke, `{radius.card}` corner radius. Padding `{spacing.6}` (24px) on desktop, `{spacing.4}` (16px) on mobile. Hover transitions the border to `{color.border.strong}`; no shadow is added.
- `component.surface.sheet` — The bottom sheet used on mobile for filters, the why-this breakdown, and reminder configuration. `{color.surface.elevated}` fill, top corners `{radius.card}`, no border on the sides, 1px `{color.border.subtle}` along the top edge. The one allowed shadow (`0 8px 24px rgba(0,0,0,0.08)`) appears only when the sheet is fully expanded.

### Text roles

- `component.text.display` — `{type.scale.display.lg}` on desktop, `{type.scale.display.lg.mobile}` on mobile, `{type.family.display}`, `{color.ink.primary}`. Used at most once per page.
- `component.text.headline` — `{type.scale.headline.md}`, `{type.family.display}`, `{color.ink.primary}`. Card titles, section openers.
- `component.text.body` — `{type.scale.body.md}`, `{type.family.body}`, `{color.ink.secondary}`. Default body copy.
- `component.text.meta` — `{type.scale.meta.md}`, `{type.family.body}`, `{color.ink.muted}`. Timestamps, source attribution.
- `component.text.microtag` — `{type.scale.microtag}` (italic), `{type.family.body}`, `{color.ink.muted}`. The "nearby · tonight · music" inline editorial tags.

### Buttons

- `component.button.primary` — Filled `{color.accent.terracotta}` background, `{color.ink.inverse}` label, `{type.scale.body.md}` weight 600, padding `{spacing.3}` × `{spacing.6}`, `{radius.control}` (12px). Reserved for the single most important affordance on a surface (e.g., "Set reminder", "View why this?"). One primary per surface.
- `component.button.secondary` — Transparent fill, 1px `{color.border.strong}` border, `{color.ink.primary}` label, padding `{spacing.3}` × `{spacing.6}`, `{radius.card}` (8px). For less-important affordances ("Show fewer like this", "Edit").
- `component.button.ghost` — Transparent fill, no border, `{color.ink.secondary}` label, padding `{spacing.2}` × `{spacing.4}`. For inline tertiary actions ("Dismiss", "Maybe later"). Quietest button in the system.

### Inputs

- `component.input.field` — `{color.surface.elevated}` fill, 1px `{color.border.subtle}` stroke, `{radius.subtle}` (4px), padding `{spacing.3}` × `{spacing.4}`, label in `{type.scale.meta.sm}` above the field. Focus transitions stroke to `{color.border.strong}` and adds the 2px focus ring.
- `component.input.chip` — `{color.surface.subtle}` fill, `{color.ink.secondary}` label, `{type.scale.meta.sm}`, padding `{spacing.1}` × `{spacing.3}`, `{radius.subtle}` (4px). Used for static category labels, source filters, "applied filter" pills. No interactivity chrome — chips become buttons only when they are actually buttons.
- `component.input.reminder.slot` — The 5d / 2d / 1d / 1hr reminder configuration chip. `{color.surface.subtle}` resting fill, `{color.ink.primary}` label, `{type.scale.meta.sm}`, padding `{spacing.2}` × `{spacing.3}`, `{radius.subtle}`. Selected state fills with `{color.ink.primary}` and inverts label to `{color.ink.inverse}`. No terracotta on this chip — selection is communicated by ink inversion, not by accent.

### Cards

- `component.card.pulse.digest` — The signature editorial card. Anatomy, top-to-bottom: a 4px category stripe (`{color.accent.slate}` for public events, `{color.accent.amber}` for must-know), a `{type.scale.meta.sm}` kicker label in `{color.ink.muted}`, a `{type.scale.headline.md}` headline in `{color.ink.primary}` (max 8 words), a `{type.scale.microtag}` row of inline italic tags separated by middle dots, a `{type.scale.meta.md}` source-and-time row, and the `component.indicator.confidence` row at the bottom. Sits on `component.surface.card`.
- `component.card.pulse.digest.category.public` — Variant with `{color.accent.slate}` stripe.
- `component.card.pulse.digest.category.mustknow` — Variant with `{color.accent.amber}` stripe. Should appear on fewer than ~10% of cards in any given view.
- `component.card.pulse.digest.category.surprise` — Variant with `{color.accent.slate}` stripe plus a "surprise" micro-tag in the micro-tag row.

### Badges and indicators

- `component.badge.source` — Inline source attribution badge. Three variants, distinguished by border and label, not by fill:
  - `verified` — `{color.accent.terracotta}` 1px border, `{color.accent.terracotta}` label, no fill. The only place terracotta appears on a card besides the today indicator.
  - `official` — `{color.ink.primary}` 1px border, `{color.ink.primary}` label, no fill.
  - `community` — `{color.border.strong}` 1px border, `{color.ink.muted}` label, no fill.
  - Always inline on the card (next to the headline), never behind a tap. This carries the "Inline trust beats click-to-reveal" principle from Design Thinking.
- `component.indicator.confidence` — A row of 1–5 small dots (`{radius.full}`, 6px diameter) in `{color.ink.muted}` for unfilled positions and `{color.ink.primary}` for filled positions. The numeric count is rendered in `{type.scale.numeric}` next to the dots. Five positions, always; never a bar.
- `component.indicator.today` — A single 6px `{radius.full}` dot in `{color.accent.terracotta}`, placed inline next to today's date label. Not a background fill, not a bar — a single dot.

### Empty and quiet states

- `component.emptystate.quiet` — Full-section empty state. Centered `{type.scale.display.md}` headline in `{color.ink.primary}`, `{type.scale.body.md}` lede in `{color.ink.secondary}`, optional `{component.button.ghost}` action. Background `{color.surface.subtle}` if the empty state fills a page section. Example copy: "Nothing on the pulse today. The calendar is yours."

## Do's and Don'ts

| Do | Don't |
|---|---|
| Use `color.accent.terracotta` only for the today indicator, the primary CTA, and the verified source badge. | Use terracotta on hover states, focus rings, link underlines, or category stripes. |
| Use italic micro-tags inline (`nearby · tonight · music`) via `type.scale.microtag`. | Set micro-tags in regular weight or in the display font. |
| Show the source badge inline on the card, never behind a tap. | Hide source attribution behind a "details" disclosure or modal. |
| Keep card headlines to 8 words or fewer. | Wrap a long sentence as a card headline; that is body copy, not a headline. |
| Use `{color.accent.slate}` and `{color.accent.amber}` exclusively for category stripes on `Card.PulseDigest`. | Use slate or amber on buttons, icons, or interactive surfaces. |
| Respect Quiet Hours — no motion between 22:00 and 08:00 by default. Cards arrive without the fade-in translate. | Animate card arrival, badge pulses, or any state change during Quiet Hours. |
| Use the 1px border transition for card hover, not a shadow lift. | Add a shadow on hover or active state. |
| Use `radius.control` (12px) only for `Button.Primary`. | Apply 12px to secondary buttons, inputs, or chips. |
| Reserve `Indicator.Confidence` for AI-generated recommendations and reminders. | Render a confidence indicator on a manually-entered event or a public event from an official source. |
| Place one `Button.Primary` per surface. | Stack multiple terracotta CTAs on the same view. |
| Use `EmptyState.Quiet` for genuinely empty days — present it as a feature, not a failure. | Replace an empty state with "no results" copy, illustration, or a suggested-search rail. |
