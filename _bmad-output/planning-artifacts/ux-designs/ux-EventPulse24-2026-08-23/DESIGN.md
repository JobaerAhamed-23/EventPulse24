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

[ASSUMPTION: Hex values below are estimated from named descriptions; calibrate against final brand sampling before engineering. Terracotta `#C4502B` was provided; the rest are derived from the warm-neutral palette direction. — see _Assumptions_ at end of document, ASSUM-1.]

### Light mode

- `color.surface.paper` — `#FAF8F4`. Base canvas. Used for the page background, the dominant surface. Near-white, slightly warm (paper, not screen white).
- `color.surface.elevated` — `#FFFFFF`. Cards, sheets, popovers. Sits on top of `color.surface.paper`.
- `color.surface.subtle` — `#F1ECE3`. Page-2 backgrounds, dividers, hover affordance on ghost rows, the "no events" empty state fill.
- `color.surface.inset` — `#EDE7DA`. Inset wells (e.g., the search field resting state, a nested grouping block).
- `color.ink.primary` — `#1A1814`. Headlines, serif display, the highest-contrast text. Slightly warm black, not pure `#000`.
- `color.ink.secondary` — `#3A352D`. Body copy, input text. Softer than primary but still high contrast.
- `color.ink.muted` — `#7A7066`. Metadata, timestamps, helper text, source attribution labels. (Path alias: `color.ink.meta` — same value, both names accepted so EXPERIENCE.md and DESIGN.md can use either without drift.)
- `color.ink.faint` — `#C9C2B5`. The dimmest readable ink. Used only for: empty `Indicator.Confidence` dot placeholders and the dim target of the skeleton pulse animation. Never used for body copy or interactive affordances.
- `color.ink.inverse` — `#FAF8F4`. Text on dark fills (e.g., the terracotta CTA label).
- `color.surface.paper.darker` — `#F4F0E8`. The hover background for `Card.PulseDigest` (one step darker than `color.surface.paper`, no shadow). Used only on hover and on the skeleton pulse animation's resting frame; never as a static surface.
- `color.warm.personal` — `#A8765C`. The warm tone reserved for Personal events on `Card.PulseDigest` and the Detail Screen. Used only as an accent strip or small label, paired with the visible text label "Personal" (PRD §13.1) so color is never the sole carrier of meaning.
- `color.cool.public` — `#5B6B7E`. Path alias of `color.accent.slate`; both names accepted so EXPERIENCE.md and DESIGN.md can use either. Reserved for the public-event tone on `Card.PulseDigest` and Detail Screen; paired with the text label "Public event."
- `color.warn.amber` — `#B8893A`. Muted amber reserved for the conflict indicator (filled circle, PRD FR-58). Distinct from `color.accent.amber`, which is a warm-secondary category stripe. Used only at the moment of state change (conflict active) and as a static indicator mark on a card or detail screen header; never as decoration.
- `color.accent.terracotta` — `#C4502B`. Single warm accent. Used only for: the `Indicator.Today` dot, the `Button.Primary` fill, the `Badge.Source.verified` fill, and the focus ring (the fourth sanctioned use — see §Color usage rules). Nothing else.
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
- `color.ink.muted` — `#8C8478`. Metadata on dark. (Path alias: `color.ink.meta` — same value, both names accepted.)
- `color.ink.faint` — `#3A352D`. Empty `Indicator.Confidence` dot placeholders and the dim target of the skeleton pulse animation on dark surfaces.
- `color.ink.inverse` — `#15140F`. Text on light fills (e.g., terracotta CTA label in dark mode).
- `color.surface.paper.darker` — `#1A1814`. Hover background for `Card.PulseDigest` on dark (one step darker than `color.surface.paper`, no shadow).
- `color.warm.personal` — `#C8967A`. Warm tone for Personal events on dark surfaces. Same usage rules as light mode.
- `color.cool.public` — `#7E91A6`. Path alias of `color.accent.slate` (dark variant); both names accepted.
- `color.warn.amber` — `#D8A86A`. Conflict indicator on dark surfaces. Same usage rules as light mode.
- `color.accent.terracotta` — `#D88A6E`. Terracotta reduced saturation for dark surfaces. Still reserved for the same four uses (today indicator, primary CTA, verified badge, focus ring).
- `color.accent.slate` — `#7E91A6`. Slate brightened for dark contrast on category stripes.
- `color.accent.amber` — `#D8A06A`. Amber warm-secondary, adjusted for dark.
- `color.signal.success` — `#7AAA7A`.
- `color.signal.warn` — `#D8A86A`.
- `color.signal.error` — `#C66A5C`.
- `color.border.subtle` — `rgba(242, 239, 232, 0.10)`.
- `color.border.strong` — `rgba(242, 239, 232, 0.20)`.

### Color usage rules

- `color.accent.terracotta` is the only chromatic accent. Its **four sanctioned uses** are the today indicator, the primary CTA, the verified source badge, and the focus ring (the focus ring being the only exception outside the original three). It does not appear on hover, link underlines, category stripes, or anywhere else.
- **Focus ring (exception, fourth sanctioned use):** The 2px focus ring at 2px offset on focusable interactive elements uses `color.accent.terracotta`. WCAG 2.2 focus-visible is required, and terracotta is the highest-contrast chromatic signal we own; AA contrast (≥3:1 against `color.surface.paper`) is verified for the ring stroke. This is the only sanctioned use of terracotta outside the three originally named above (today indicator, primary CTA, verified source badge), and the only chromatic focus ring in the system — there is no terracotta-on-link or terracotta-on-hover rule.
- `color.accent.slate` and `color.accent.amber` are reserved exclusively for category stripes on `Card.PulseDigest`. They are not used for buttons, icons, or interactive surfaces. `color.accent.slate` and `color.cool.public` are interchangeable path aliases for the same token; either name is accepted.
- `color.warm.personal` is reserved exclusively for the Personal-event tone on `Card.PulseDigest` and Detail Screen (a small accent strip or label). It is always paired with the visible text label "Personal" so color is never the sole carrier of meaning (WCAG 1.4.1).
- `color.warn.amber` is reserved exclusively for the conflict indicator (filled circle mark on `Card.PulseDigest` and Detail Screen header, per PRD FR-58). It is distinct from `color.accent.amber` (warm-secondary category stripe) — do not substitute one for the other.
- `color.signal.success`, `color.signal.warn`, and `color.signal.error` are signal colors, not brand colors. They appear only at the moment of state change, never as decoration.
- `color.ink.faint` is reserved for empty `Indicator.Confidence` dot placeholders and the skeleton pulse animation's dim target. Never used for body copy or interactive affordances.
- `color.surface.paper.darker` is reserved for `Card.PulseDigest` hover background and the skeleton pulse animation's resting frame. Never used as a static surface or as a hover state on non-card elements.

## Token Implementation Contract

The visual identity in this document is the source of truth; this subsection specifies the build substrate so engineering does not reach for a UI library, a tooltip framework, or an animation library to implement it.

- **Token substrate.** Tokens are CSS custom properties declared at `:root` (`--color-accent-terracotta: #C4502B;` etc.) with a dark-mode override under `[data-theme="dark"]`. Tokens are not a JS constants file and not a build-time JSON; they are read by the runtime CSS engine directly. Path-style names in `{color.accent.terracotta}` form are the canonical names referenced by `EXPERIENCE.md`; the CSS variable name is the kebab-case form of the path (`--color-accent-terracotta`).
- **Path aliases (canonical mapping).** Path aliases resolve to a single CSS variable. Engineering does not declare separate variables for each alias; it declares one and accepts both names on read.
  - `color.ink.meta` is a path alias for `color.ink.muted` → CSS variable `--color-ink-muted` (declared). `--color-ink-meta` is **not** declared; `color.ink.meta` is read as the same key.
  - `color.cool.public` is a path alias for `color.accent.slate` → CSS variable `--color-accent-slate` (declared). `--color-cool-public` is **not** declared; `color.cool.public` is read as the same key.
  - Dark-mode overrides apply to the primary variable only; both names pick up the override through the same key.
- **Dark-mode trigger.** Dark mode is set by writing `data-theme="dark"` on the `<html>` element. There is no `prefers-color-scheme: dark` auto-switch at MVP — the user picks theme in `Settings` (§2 of `EXPERIENCE.md`). The system UI follows.
- **Motion — `motion.fadeIn`.** A 240ms CSS `opacity` transition (no transform, no translate). Implementation is a single class toggled by the framework: `.fade-in { transition: opacity 240ms ease-out; }` plus `opacity: 0` → `opacity: 1`. Under `@media (prefers-reduced-motion: reduce)`, the class becomes `transition: none`. There is no JS animation library. Skeleton pulse animation is a CSS `@keyframes` between `color.surface.paper` and `color.ink.faint` (or `color.surface.paper.darker` resting frame), 1800ms period, also collapsing to a static frame under reduced-motion.
- **Tooltip pattern.** `Tooltip.Source` and `Tooltip.Confidence` use a `<button>` trigger with `aria-describedby="tooltip-{id}"` pointing to a sibling `<span role="tooltip" id="tooltip-{id}">`. Tooltips appear on `:hover` and `:focus-visible`; on touch viewports (`<768px`), tooltips appear on tap and dismiss on outside-tap or `Esc`. No hover-only tooltips on touch. The tooltip container uses `color.surface.elevated` fill, the one allowed shadow (`0 8px 24px rgba(0,0,0,0.08)`), and `Text.Meta` content.
- **No UI framework.** The "UI system: None" declaration in `EXPERIENCE.md` §1 is binding: vanilla web components plus the token layer above. No Material, no shadcn, no full kit. The tooltip pattern is hand-rolled per the rule above; the modal pattern is a single overlay level using `<dialog>` native element; the sheet pattern uses `<dialog>` with `bottom` anchoring on mobile only.

## Typography

Three type families. Headlines use a serif for the editorial voice. Body uses a sans for clarity and screen readability. Mono is reserved for confidence numerics (the 1–5 dot counts) and any timestamp that requires non-ambiguous digit rendering.

[ASSUMPTION: The locked chain is `Source Serif 4` with `Fraunces` as fallback. If engineering prefers a different serif, swap the family name only — the scale and roles below are the contract. — see _Assumptions_ at end of document, ASSUM-2.]

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
- Focus rings are 2px solid `color.accent.terracotta` at 100% opacity, with a 2px offset. AA contrast (≥3:1 against `color.surface.paper`) is verified. **The focus ring is the only sanctioned use of terracotta outside the three named in §Color usage rules** (today indicator, primary CTA, verified source badge); no other chromatic focus ring exists in the system.

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

- `component.button.primary` — Filled `{color.accent.terracotta}` background, `{color.ink.inverse}` label, `{type.scale.body.md}` weight 600, padding `{spacing.3}` × `{spacing.6}`, `{radius.control}` (12px). Reserved for the most important affordance within a **decision moment** (e.g., "Set reminder", "View why this?"). A surface may carry multiple primaries when it has multiple decision moments — e.g. `/events/:id` has Save, Configure-reminders, and (when a conflict is active) Resolve-conflict — each rendered in a distinct visual zone separated by `spacing.12`+ whitespace. See Do's and Don'ts.
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
  - `verified` — `{color.accent.terracotta}` 1px border, `{color.accent.terracotta}` label, no fill. One of the four sanctioned terracotta uses; the only one that appears on a card body besides the `Indicator.Today` dot.
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
| Use `color.accent.terracotta` only for the today indicator, the primary CTA, the verified source badge, **and the focus ring** (the one sanctioned exception — see §Color usage rules). | Use terracotta on hover states, link underlines, category stripes, or anywhere else outside the four sanctioned uses. |
| Use italic micro-tags inline (`nearby · tonight · music`) via `type.scale.microtag`. | Set micro-tags in regular weight or in the display font. |
| Show the source badge inline on the card, never behind a tap. | Hide source attribution behind a "details" disclosure or modal. |
| Keep card headlines to 8 words or fewer. | Wrap a long sentence as a card headline; that is body copy, not a headline. |
| Use `{color.accent.slate}` and `{color.accent.amber}` exclusively for category stripes on `Card.PulseDigest`. | Use slate or amber on buttons, icons, or interactive surfaces. |
| Respect Quiet Hours — no motion between 22:00 and 08:00 by default. Cards arrive without the fade-in translate. | Animate card arrival, badge pulses, or any state change during Quiet Hours. |
| Use the 1px border transition for card hover, not a shadow lift. | Add a shadow on hover or active state. |
| Use `radius.control` (12px) only for `Button.Primary`. | Apply 12px to secondary buttons, inputs, or chips. |
| Reserve `Indicator.Confidence` for AI-generated recommendations and reminders. | Render a confidence indicator on a manually-entered event or a public event from an official source. |
| Place one `Button.Primary` per **decision moment**, separated by `spacing.12`+ whitespace. A surface may have multiple decision moments (e.g. `/events/:id` has Save, Configure-reminders, Resolve-conflict); each gets its own primary in a distinct visual zone. | Stack multiple terracotta CTAs in the same visual zone, or place two primaries adjacent without whitespace separation. |
| Use `EmptyState.Quiet` for genuinely empty days — present it as a feature, not a failure. | Replace an empty state with "no results" copy, illustration, or a suggested-search rail. |

## Assumptions

All open `[ASSUMPTION:…]` markers in this document, consolidated. Each entry has a stable ID (`ASSUM-N`) for cross-reference from the body and from `EXPERIENCE.md`. Status: OPEN = needs a decision before engineering ships; RESOLVED = owner has answered; DEFERRED = explicitly parked to a later phase.

- **ASSUM-1.** Hex values for the palette are estimated from named descriptions and from the warm-neutral palette direction. Only `color.accent.terracotta #C4502B` was provided by brand; the rest (paper, ink, slate, amber, signal colors, and the cross-doc tokens `color.ink.faint`, `color.ink.meta`, `color.surface.paper.darker`, `color.warm.personal`, `color.cool.public`, `color.warn.amber`) are derived.
  - Status: OPEN
  - Owner: TBD (brand / design owner)
  - Affects: §Colors, §Token Implementation Contract
  - Decision deadline: before engineering token implementation begins
  - Action: sample the warm-neutral palette from brand collateral; replace the estimated hex values with sampled values; re-verify AA contrast for `color.ink.*`, `color.warn.amber`, and the terracotta focus ring against `color.surface.paper` in light and dark modes.

- **ASSUM-2.** The locked display-serif chain is `Source Serif 4` with `Fraunces` as fallback. Engineering may swap the family name (e.g. for `IBM Plex Serif`, `Tiempos`) but the scale (`type.scale.display.*`, `type.scale.headline.*`) and the role (display family for headlines and editorial display moments only) are the contract and may not change.
  - Status: OPEN
  - Owner: design (final family pick) + engineering (font hosting / loading)
  - Affects: §Typography → Type families; all `component.text.display` and `component.text.headline` render paths
  - Decision deadline: before first production typography integration
  - Action: confirm the family pick; verify the chosen family has the weight set (400 / 600 / 700) and italic availability used in `type.scale.microtag`; license the chosen family or confirm open-source status.
