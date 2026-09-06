---
title: "DESIGN.md — EventPulse24"
status: final
created: 2026-08-23
updated: 2026-09-03
updated_note: "Added three enforcement-tightening rules to §Color usage rules and §Token Implementation Contract, derived from the 2026-09-03 pulse-preview audit. (1) Glow rule now enumerates the two sanctioned glows and explicitly lists what does NOT glow (eyebrow glyphs, status dots, focus rings, hover targets, decorative dots). (2) Stripe color rule extended from color.warm.personal only to all category stripes, requiring both an inline label on the card AND a legend on the surface that first uses the stripe. (3) New rule scoping font-variant-numeric: tabular-nums to type.scale.numeric and time/duration strings; explicitly forbids body-wide application. Subsequent update 2026-09-03 (v1 onboarding audit): added §Layout `layout.container.form` token, §Shapes chip/input radius clarifications banning pills outside the four sanctioned round elements, §Components three new control patterns (Control.Segmented, Control.Preset, Button.Provider) with the small-control selection tint rule formalized, §Do's-and-Dont's four new rows enforcing topbar-quiet, provider parity, segmented-control ink inversion, and selection-tint pattern."
project: EventPulse24
source_prd: _bmad-output/planning-artifacts/prds/prd-EventPulse24-2026-08-19/prd.md
source_brief: _bmad-output/planning-artifacts/briefs/brief-EventPulse24-2026-08-19/brief.md
references:
  experience: EXPERIENCE.md
  spec: https://github.com/google-labs-code/design.md
  prd: _bmad-output/planning-artifacts/prds/prd-EventPulse24-2026-08-19/prd.md
  reference_editorial: .agents/skills/bmad-ux/assets/design-example-editorial.md
  reference_shadcn: .agents/skills/bmad-ux/assets/design-example-shadcn.md
  mockups: mockups/
---

## Brand & Style

EventPulse24 is a calm intelligence layer for events. The product sits above every event source and answers one question — *what's actually worth my attention right now* — without asking the user to maintain a system.

The brand posture is **OLED Dark**. The visual identity is true-black first: a near-pure-black canvas, cool near-white ink, a single warm accent (terracotta) that glows on the dark surface like a small pilot light. The aesthetic posture is **instrument-grade calm** — the feel of a well-engineered dark-mode app (think Linear, Vercel dashboard, Arc dark) translated to the discovery and triage of nearby events. It is deliberately **anti-Eventbrite** — anti the bright badges, the social-proof counters, the upsell carousel, the loud category tinting, the streak popup. Where Eventbrite sells tickets, EventPulse24 sells attention.

**Theme priority: Dark is the default.** Light mode is provided as an alternative for users who prefer it, but every screen is designed dark-first. Every color, contrast, motion, and component behavior is calibrated for the dark surface; the light surface is a swap-out, not the source.

The aesthetic reads like a precision instrument: dense information earns its keep, type is generous, accent color is rationed, surfaces carry depth through tonal layering (paper → elevated → subtle → inset), and motion is reduced to a single 240ms fade. The terracotta dot on today's date, the terracotta primary CTA, the terracotta focus ring — that's where the warmth lives. Everything else is ink on void.

Anti-patterns that must not appear anywhere in the product:

- No notification badges (red dots, unread counters).
- No streak popups or "you checked in 7 days in a row!" surfaces.
- No social-proof counters ("234 people going").
- No infinite scroll.
- No category-tinted card floods (six different bright card colors stacked).
- No gamification chrome (progress bars, badges, leaderboards).
- No upsell carousels or "you might also like" rails beyond three suggestions.
- No drop shadows used for hover lift on dark surfaces (use border-color transition, not elevation).
- No chromatic accents outside the four sanctioned uses (today dot, primary CTA, verified badge, focus ring).

The visual rule: if it would feel at home on Eventbrite, Meetup, or a gaming app, it does not belong here. If it would feel at home on Linear or Arc dark, it does.

## Colors

The palette is **near-black canvas + cool near-white ink + one warm accent (terracotta) that glows**. The dark surface is the default and primary; a light alternative is provided but not optimized beyond minimum contrast.

[ASSUMPTION: Hex values for light mode are derived from a cool-neutral paper-and-ink direction; the dark hex values are calibrated for true-black OLED with maximum contrast and a single terracotta glow. — see _Assumptions_ at end of document, ASSUM-1.]

### Dark mode (default)

- `color.surface.paper` — `#0A0A0B`. Base canvas. Near-pure-black, slightly warm-tinted at the deep end to avoid the flat-blue cast of pure `#000` on OLED. Used for the page background, the dominant surface.
- `color.surface.elevated` — `#131316`. Cards, sheets, popovers, modal bodies. One step lighter than paper — a faint glow that lifts content off the void without visible shadow.
- `color.surface.subtle` — `#1B1B1F`. Page-2 backgrounds, dividers, hover affordance on ghost rows, the "no events" empty state fill.
- `color.surface.inset` — `#232328`. Inset wells (e.g., the search field resting state, a nested grouping block, the resting frame of the skeleton pulse animation).
- `color.ink.primary` — `#F2F2F4`. Headlines, serif display, the highest-contrast text. Cool near-white, not warm cream — dark-first breaks the editorial-paper metaphor.
- `color.ink.secondary` — `#C9C9CF`. Body copy, input text, button labels on ghost. Softer than primary but still AA-readable.
- `color.ink.muted` — `#8A8A92`. Metadata, timestamps, helper text, source attribution labels. (Path alias: `color.ink.meta` — same value, both names accepted so EXPERIENCE.md and DESIGN.md can use either without drift.)
- `color.ink.faint` — `#3A3A40`. The dimmest readable ink. Used only for: empty `Indicator.Confidence` dot placeholders, the dim target of the skeleton pulse animation, and the handle bar on mobile bottom sheets. Never used for body copy or interactive affordances.
- `color.ink.inverse` — `#0A0A0B`. Text on light fills (e.g., the terracotta CTA label in dark mode).
- `color.surface.paper.darker` — `#050506`. The deeper hover background for `Card.PulseDigest` (one step darker than `color.surface.paper`, no shadow). Used only on hover and on the skeleton pulse animation's resting frame; never as a static surface.
- `color.warm.personal` — `#C8967A`. The warm tone reserved for Personal events on `Card.PulseDigest` and the Detail Screen. Used only as an accent strip or small label, paired with the visible text label "Personal" (PRD §13.1) so color is never the sole carrier of meaning.
- `color.cool.public` — `#6E7E92`. Path alias of `color.accent.slate` (dark variant); both names accepted. Reserved for the public-event tone on `Card.PulseDigest` and Detail Screen; paired with the text label "Public event."
- `color.warn.amber` — `#D8A86A`. Muted amber reserved for the conflict indicator (filled circle, PRD FR-58). Distinct from `color.accent.amber`, which is a warm-secondary category stripe. Used only at the moment of state change (conflict active) and as a static indicator mark on a card or detail screen header; never as decoration. On dark, never red.
- `color.accent.terracotta` — `#FF6A47`. Single warm accent. Glow-lifted from the light-mode `#C4502B` for dark contrast. Used only for: the `Indicator.Today` dot, the `Button.Primary` fill, the `Badge.Source.verified` fill, and the focus ring (the fourth sanctioned use — see §Color usage rules). Nothing else. The glow is created with `box-shadow: 0 0 12px rgba(255,106,71,0.55)` on the dot and the brand mark — the only sanctioned use of glow in the system.
- `color.accent.slate` — `#6E7E92`. Cool secondary. Used only for: the public-event category stripe on `Card.PulseDigest`, the serendipity / discovery card category stripe. No other use.
- `color.accent.amber` — `#E89B4A`. Warm secondary, distinct from terracotta. Used only for: the must-know card category stripe on `Card.PulseDigest`. Used sparingly; should not appear on more than ~10% of cards in any view.
- `color.signal.success` — `#7AAA7A`. Reminder confirmed, source verified success state. Muted, not vivid.
- `color.signal.warn` — `#D8A86A`. Schedule conflict, partial information, soft warning. Muted amber, lower saturation than `color.accent.amber`.
- `color.signal.error` — `#C66A5C`. Rare; reserved for destructive actions (remove reminder permanently, delete account). Not used inline on cards.
- `color.border.subtle` — `rgba(242, 242, 244, 0.08)`. The 1px border on cards and inputs. Ink at 8% opacity.
- `color.border.strong` — `rgba(242, 242, 244, 0.16)`. Focused-input border, active row in a list.

### Light mode (alternative)

Light mode is provided as a swap-out, not the source. Same vocabulary applies.

- `color.surface.paper` — `#FAF8F4`. Base canvas — paper, not screen white.
- `color.surface.elevated` — `#FFFFFF`. Cards and sheets on light.
- `color.surface.subtle` — `#F1ECE3`. Page-2 backgrounds and dividers.
- `color.surface.inset` — `#EDE7DA`. Inset wells.
- `color.ink.primary` — `#1A1814`. Headlines on light.
- `color.ink.secondary` — `#3A352D`. Body copy on light.
- `color.ink.muted` — `#7A7066`. Metadata on light. (Path alias: `color.ink.meta`.)
- `color.ink.faint` — `#C9C2B5`. Empty `Indicator.Confidence` dot placeholders on light.
- `color.ink.inverse` — `#FAF8F4`. Text on dark fills (e.g., terracotta CTA label).
- `color.surface.paper.darker` — `#F4F0E8`. Card hover on light.
- `color.warm.personal` — `#A8765C`. Personal event tone on light.
- `color.cool.public` — `#5B6B7E`. Public event tone on light (alias `color.accent.slate` light variant).
- `color.warn.amber` — `#B8893D`. Conflict indicator on light.
- `color.accent.terracotta` — `#C4502B`. Terracotta on light.
- `color.accent.slate` — `#5B6B7E`.
- `color.accent.amber` — `#C77A2C`.
- `color.signal.success` — `#4A7A4A`.
- `color.signal.warn` — `#B8893A`.
- `color.signal.error` — `#8E2A1F`.
- `color.border.subtle` — `rgba(26, 24, 20, 0.08)`.
- `color.border.strong` — `rgba(26, 24, 20, 0.16)`.

### Color usage rules

- `color.accent.terracotta` is the only chromatic accent. Its **four sanctioned uses** are the today indicator, the primary CTA, the verified source badge, and the focus ring. It does not appear on hover, link underlines, category stripes, or anywhere else.
- **Glow (dark only).** The terracotta `Indicator.Today` dot and the brand mark in the topbar carry a soft glow: `box-shadow: 0 0 12px rgba(255,106,71,0.55)` (dot), `0 0 14px rgba(255,106,71,0.55)` (brand mark). This is the only sanctioned use of glow in the system. It applies only to dark mode; light mode has no glow. **The two elements above are the complete list.** No other element carries a glow — not eyebrow glyphs, not status or notification dots, not focus rings (which use solid stroke, not glow), not hover affordances, not decorative dots.
- **Focus ring (exception, fourth sanctioned use).** The 2px focus ring at 2px offset on focusable interactive elements uses `color.accent.terracotta`. WCAG 2.2 focus-visible is required, and terracotta is the highest-contrast chromatic signal we own; AA contrast (≥3:1 against `color.surface.paper`) is verified for the ring stroke in both modes. There is no other chromatic focus ring in the system.
- `color.accent.slate` and `color.accent.amber` are reserved exclusively for category stripes on `Card.PulseDigest`. They are not used for buttons, icons, or interactive surfaces. `color.accent.slate` and `color.cool.public` are interchangeable path aliases for the same token; either name is accepted.
- `color.warm.personal` is reserved exclusively for the Personal-event tone on `Card.PulseDigest` and Detail Screen (a small accent strip or label). It is always paired with the visible text label "Personal" so color is never the sole carrier of meaning (WCAG 1.4.1).
- **Stripe color is never the sole carrier of meaning.** When any category stripe (`color.accent.slate`, `color.accent.amber`, `color.cool.public`, `color.warm.personal`, `color.warn.amber`) appears on a card or in a card grid, it must be paired with (a) a visible text label on the card itself (e.g., "Public event", "Must-know", "Personal") and (b) a legend on the surface where the stripe first appears to a visitor (e.g., the Pulse Preview header before the card grid). Stripes may not stand alone as the only signal of category. (WCAG 1.4.1.)
- `color.warn.amber` is reserved exclusively for the conflict indicator (filled circle mark on `Card.PulseDigest` and Detail Screen header, per PRD FR-58). It is distinct from `color.accent.amber` (warm-secondary category stripe) — do not substitute one for the other.
- `color.signal.success`, `color.signal.warn`, and `color.signal.error` are signal colors, not brand colors. They appear only at the moment of state change, never as decoration.
- `color.ink.faint` is reserved for empty `Indicator.Confidence` dot placeholders, the skeleton pulse animation's dim target, and the handle bar on mobile bottom sheets. Never used for body copy or interactive affordances.
- `color.surface.paper.darker` is reserved for `Card.PulseDigest` hover background and the skeleton pulse animation's resting frame. Never used as a static surface or as a hover state on non-card elements.

## Token Implementation Contract

The visual identity in this document is the source of truth; this subsection specifies the build substrate so engineering does not reach for a UI library, a tooltip framework, or an animation library to implement it.

- **Token substrate.** Tokens are CSS custom properties declared at `:root` (light mode default) with a dark-mode override under `[data-theme="dark"]`. The DARK block is the canonical default at MVP — engineering should ship `[data-theme="dark"]` as the body attribute on first paint, and let `Settings → Appearance` toggle between Dark / Light / System. Path-style names in `{color.accent.terracotta}` form are the canonical names referenced by `EXPERIENCE.md`; the CSS variable name is the kebab-case form of the path (`--color-accent-terracotta`).
- **Path aliases (canonical mapping).** Path aliases resolve to a single CSS variable. Engineering does not declare separate variables for each alias; it declares one and accepts both names on read.
  - `color.ink.meta` is a path alias for `color.ink.muted` → CSS variable `--color-ink-muted` (declared). `--color-ink-meta` is **not** declared; `color.ink.meta` is read as the same key.
  - `color.cool.public` is a path alias for `color.accent.slate` → CSS variable `--color-accent-slate` (declared). `--color-cool-public` is **not** declared; `color.cool.public` is read as the same key.
  - Dark-mode overrides apply to the primary variable only; both names pick up the override through the same key.
- **Dark-mode trigger.** Dark mode is set by writing `data-theme="dark"` on the `<html>` element. Engineering ships with `data-theme="dark"` as the default attribute (matching the dark-first brand posture); users can switch to `data-theme="light"` from Settings. There is no `prefers-color-scheme: dark` auto-switch at MVP — the user picks theme explicitly. (Phase 2: add a "System" option that follows the OS.)
- **Motion — `motion.fadeIn`.** A 240ms CSS `opacity` transition (no transform, no translate). Implementation is a single class toggled by the framework: `.fade-in { transition: opacity 240ms ease-out; }` plus `opacity: 0` → `opacity: 1`. Under `@media (prefers-reduced-motion: reduce)`, the class becomes `transition: none`. There is no JS animation library. Skeleton pulse animation is a CSS `@keyframes` between `color.surface.elevated` and `color.surface.inset` (dark) or `color.surface.paper` and `color.ink.faint` (light), 1800ms period, also collapsing to a static frame under reduced-motion.
- **Tooltip pattern.** `Tooltip.Source` and `Tooltip.Confidence` use a `<button>` trigger with `aria-describedby="tooltip-{id}"` pointing to a sibling `<span role="tooltip" id="tooltip-{id}">`. Tooltips appear on `:hover` and `:focus-visible`; on touch viewports (`<768px`), tooltips appear on tap and dismiss on outside-tap or `Esc`. No hover-only tooltips on touch. The tooltip container uses `color.surface.elevated` fill, the one allowed shadow (`0 8px 24px rgba(0,0,0,0.40)` in dark, `0 8px 24px rgba(0,0,0,0.08)` in light), and `Text.Meta` content.
- **No UI framework.** "UI system: None" (see `EXPERIENCE.md` §1) is binding: vanilla web components plus the token layer above. No Material, no shadcn, no full kit. The tooltip pattern is hand-rolled per the rule above; the modal pattern is a single overlay level using `<dialog>` native element; the sheet pattern uses `<dialog>` with `bottom` anchoring on mobile only.
- **Tabular numerics are scoped, not body-wide.** `font-variant-numeric: tabular-nums` applies only to elements that render `type.scale.numeric` (confidence counts, durations, ambiguous timestamps) and to time/duration strings where digit alignment aids scanning. It is never applied to the `body` element or to body-copy containers. Tabular figures on body copy make prose feel like a ledger and break the editorial posture.

## Typography

Three type families. Headlines use a serif for editorial weight on the dark surface. Body uses a sans for clarity and screen readability. Mono is reserved for confidence numerics (the 1–5 dot counts) and any timestamp that requires non-ambiguous digit rendering.

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
- `layout.container.form` — 720px. Centered form / onboarding / single-decision column. Same value as `layout.container.reading` because the form column needs the same line-length to feel readable; the two tokens are intentionally aliased (1:1 value) but kept distinct so semantic references don't drift. Used on `/onboarding`, `/settings/*` narrow-column layouts, and single-column auth flows.
- `layout.section.gap` — `{spacing.16}` (64px). Vertical gap between major page sections.
- `layout.section.gap.large` — `{spacing.20}` (80px). Hero-to-first-section gap.
- `layout.grid.columns` — 12. Desktop grid; cards typically span 6 or 12 columns depending on density.
- `layout.timeline.grid` — CSS Grid `grid-template-columns: repeat(7, minmax(0, 1fr))` on desktop `md+`. Mobile `sm` collapses to a single column with horizontal swipe between days (see `Surface.Timeline` in EXPERIENCE.md §4, Amendment A-8).
- `layout.bottom-tab.height` — 56px + `env(safe-area-inset-bottom)`. Fixed bottom navigation on mobile (Amendment A-8).
- `layout.sidenav.app.width.tablet` — 220px. Desktop `md` (768–1023px) sidebar nav width.
- `layout.sidenav.app.width.desktop` — 240px. Desktop `lg+` (≥1024px) sidebar nav width.

### Breakpoints

- `breakpoint.mobile` — max-width 767px. Single column, 24px padding.
- `breakpoint.tablet` — 768–1023px. Single column, 48px padding.
- `breakpoint.desktop` — 1024px+. Up to 12-column grid, 80px padding, max content 1180px.

## Elevation & Depth

OLED Dark communicates depth with **tonal layering and a single shadow token**. No glow except on the sanctioned terracotta marks. No glassmorphism. No gradient surfaces (except the Pro upsell card, which is the single sanctioned use of a tinted background gradient — see Do's and Don'ts).

- Cards and sheets use a 1px border (`color.border.subtle`) instead of shadow to sit above `color.surface.paper`. On dark, the border is the depth — there is no shadow lift.
- The one allowed shadow is reserved for floating surfaces — modals, popovers, tooltips. Dark: `0 8px 24px rgba(0, 0, 0, 0.40)`. Light: `0 8px 24px rgba(0, 0, 0, 0.08)`. Tinted toward ink (black), not toward terracotta or slate.
- Hover on a card does NOT add shadow. Hover is communicated by a 1px transition from `color.border.subtle` to `color.border.strong`, OR by the `color.surface.paper.darker` background swap (per the surface rules). That's the entire hover affordance. **On dark, never add a shadow lift on hover.**
- Focus rings are 2px solid `color.accent.terracotta` at 100% opacity, with a 2px offset. AA contrast (≥3:1 against `color.surface.paper`) is verified in both modes. The focus ring is the only sanctioned use of terracotta outside the three named in §Color usage rules (today indicator, primary CTA, verified source badge); no other chromatic focus ring exists in the system.
- Glow (dark only, sanctioned): terracotta `Indicator.Today` dot and the brand mark in the topbar. Implemented as `box-shadow: 0 0 12px rgba(255,106,71,0.55)`. This is the only sanctioned glow. No other element glows.

## Shapes

The shape language is **mostly square with subtle rounding**. Card corners are 12px (slightly more generous than the light-mode 8px to soften the harsh dark void). Inputs are 8px. Primary CTA corners are 12px. There are no pill buttons.

- `radius.none` — 0.
- `radius.subtle` — 6px. **The default radius for inputs, chips, meta tags, preset/segmented buttons, time-pickers, timezone fields, and the resting-state of small controls.** Chips (interest chips, time presets) are NOT pill-shaped (`9999px` is reserved for the four sanctioned round elements per `radius.full`). Engineering must not exceed `radius.subtle` for chips in any state.
- `radius.card` — 12px. Cards, sheets, list rows that need their own edge. (Bumped from 8px in the prior light-mode spec — darker surfaces need slightly more rounding to feel intentional rather than abrupt.)
- `radius.control` — 12px. **Reserved exclusively for `Button.Primary` and the calendar provider buttons on `/onboarding` step 1** (per-provider buttons share the radius-control shape language so the user perceives them as decision affordances, not as list rows). Same radius as cards in dark; the distinction comes from the terracotta fill on the active primary, or the elevated surface fill on secondary provider buttons, not from the corner radius.
- `radius.modal` — 16px. Modals get a slightly more generous radius than cards to feel like a separate floating surface.
- `radius.full` — 9999px. Reserved for the terracotta `Indicator.Today` dot, the dots in `Indicator.Confidence`, the avatar, and status dots. **Never used for buttons, chips, preset rows, or segmented controls.**
- `radius.timeline-cell` — 10px. **Used exclusively on `component.timeline.cell` outer corners** (Amendment A-8). Slightly tighter than `radius.card` (12px) so the 7-column week grid reads as one continuous grid rather than as 7 separate cards. Inner dividers are 1px straight strokes, no radius on the shared edges.

Stroke language:

- `stroke.hairline` — 1px solid `color.border.subtle`. Default card and input border.
- `stroke.strong` — 1px solid `color.border.strong`. Focused inputs, active rows.
- `stroke.focus` — 2px solid `color.accent.terracotta`, 2px offset. Focus ring, the only chromatic focus indicator.

## Components

Components are named in dotted path notation so `EXPERIENCE.md` can cross-reference each one with `{component.surface.canvas}` syntax. Each entry below states its anatomy, color usage, and intent in one paragraph.

### Surfaces

- `component.surface.canvas` — The full-bleed page background. `{color.surface.paper}` fill, no border, no shadow. The single anchoring surface of the product.
- `component.surface.card` — The `Card.PulseDigest` container. `{color.surface.elevated}` fill, 1px `{color.border.subtle}` stroke, `{radius.card}` (12px) corner radius. Padding `{spacing.6}` (24px) on desktop, `{spacing.4}` (16px) on mobile. Hover swaps the fill to `{color.surface.subtle}` (desktop) and transitions the border to `{color.border.strong}` (mobile). No shadow is ever added.
- `component.surface.sheet` — The bottom sheet used on mobile for filters, the why-this breakdown, and reminder configuration. `{color.surface.elevated}` fill, top corners `{radius.modal}` (16px), 1px `{color.border.subtle}` along the top edge, the one allowed shadow appears only when the sheet is fully expanded.
- `component.surface.modal` — Centered modal on desktop, anchored to bottom on mobile. `{color.surface.elevated}` fill, `{radius.modal}` (16px), the one allowed shadow. Backdrop is `rgba(10,10,11,0.7)` (dark) or `rgba(26,24,20,0.4)` (light) with `backdrop-filter: blur(8px)`.

### Text roles

- `component.text.display` — `{type.scale.display.lg}` on desktop, `{type.scale.display.lg.mobile}` on mobile, `{type.family.display}`, `{color.ink.primary}`. Used at most once per page.
- `component.text.headline` — `{type.scale.headline.md}`, `{type.family.display}`, `{color.ink.primary}`. Card titles, section openers.
- `component.text.body` — `{type.scale.body.md}`, `{type.family.body}`, `{color.ink.secondary}`. Default body copy.
- `component.text.meta` — `{type.scale.meta.md}`, `{type.family.body}`, `{color.ink.muted}`. Timestamps, source attribution.
- `component.text.microtag` — `{type.scale.microtag}` (italic), `{type.family.body}`, `{color.ink.muted}`. The "nearby · tonight · music" inline editorial tags.

### Buttons

- `component.button.primary` — Filled `{color.accent.terracotta}` background, `{color.ink.inverse}` label, `{type.scale.body.md}` weight 600, padding `{spacing.3}` × `{spacing.6}`, `{radius.control}` (12px). Reserved for the most important affordance within a **decision moment** (e.g., "Save to Pulse", "Set reminders"). A surface may carry multiple primaries when it has multiple decision moments — e.g. `/events/:id` has Save and (when a conflict is active) Resolve-conflict — each rendered in a distinct visual zone separated by `spacing.12`+ whitespace. Hover lightens to `#FF7E5E`. Focus shows the terracotta ring.
- `component.button.secondary` — `{color.surface.subtle}` fill, 1px `{color.border.subtle}` stroke, `{color.ink.primary}` label, padding `{spacing.3}` × `{spacing.6}`, `{radius.card}` (12px). For less-important affordances ("Edit", "Less like this").
- `component.button.ghost` — Transparent fill, no border, `{color.ink.secondary}` label, padding `{spacing.2}` × `{spacing.4}`. For inline tertiary actions ("Dismiss", "Maybe later"). Quietest button in the system.

### Inputs

- `component.input.field` — `{color.surface.elevated}` fill, 1px `{color.border.subtle}` stroke, `{radius.subtle}` (6px), padding `{spacing.3}` × `{spacing.4}`, label in `{type.scale.meta.sm}` above the field. Focus transitions stroke to `color.accent.terracotta` and adds the 2px focus ring.
- `component.input.chip` — `{color.surface.subtle}` fill, `{color.ink.secondary}` label, `{type.scale.meta.sm}`, padding `{spacing.1}` × `{spacing.3}`, `{radius.subtle}` (6px). Used for static category labels, source filters, "applied filter" pills. No interactivity chrome — chips become buttons only when they are actually buttons.
- `component.input.reminder.slot` — The 5d / 2d / 1d / 1hr reminder configuration chip. `{color.surface.subtle}` resting fill, `{color.ink.primary}` label, `{type.scale.meta.sm}`, padding `{spacing.2}` × `{spacing.3}`, `{radius.subtle}`. Selected state fills with `rgba(255,106,71,0.10)` and shifts the label to `color.accent.terracotta`. No terracotta fill — selection is communicated by tint + label color, not by an accent fill.
- `component.control.segmented` — Segmented two- or three-option toggle (e.g., AM/PM in onboarding step 3 time picker, day-of-week picker in Settings → Quiet Hours). Resting state: `{color.surface.elevated}` fill, `{color.ink.secondary}` label, `{radius.subtle}`. **Selected/active state uses ink inversion** (`{color.ink.primary}` fill + `{color.ink.inverse}` label) — never terracotta fill. Terracotta on a small two-option toggle burns the accent on a control that's used once or twice in the user's life; ink inversion reserves the chromatic budget for sanctioned moments. Container around a segmented group is a single `{color.border.subtle}` stroke at 1px, no inner dividers between segments.
- `component.control.preset` — A horizontal row of preset buttons used for low-stakes single-select choices (e.g., the time-preset row "8:00 AM / 7:00 AM / 9:00 AM / 12:00 PM / 6:00 PM" on onboarding step 3). Resting state: `{color.surface.elevated}` fill, 1px `{color.border.subtle}` stroke, `{color.ink.secondary}` label, `{radius.subtle}`. **Active state uses the small-control selection tint** (`background: rgba(255,106,71,0.10)`, `border-color: rgba(255,106,71,0.30)`, `label: color.accent.terracotta`). The same 10%-terracotta tint pattern used for `component.input.reminder.slot` is the canonical small-control selection treatment across the system.
- `component.button.provider` — Calendar-provider connect button on `/onboarding` step 1 (Google / Apple / Outlook). `{color.surface.elevated}` fill, 1px `{color.border.subtle}` stroke, `{radius.control}` (12px), `{spacing.4}` × `{spacing.5}` padding, full-width per provider. Each provider renders a small monogram tile (36×36, `{color.surface.inset}` fill) and a label group (provider name in `{type.scale.body.md}` `{color.ink.primary}` weight 600; sub-label in `{type.scale.meta.sm}` `{color.ink.muted}`). The provider list is a **vertical stack of equal-weight decision buttons** — no single provider is visually elevated above the others (Google is not the "primary CTA" and Apple/Outlook are not "secondary ghost links"). On hover, the stroke transitions to `{color.border.strong}` and the fill to `{color.surface.subtle}` — same hover affordance as `component.surface.card`. Focus shows the 2px terracotta ring.

### Calendar Connect Provider Parity (v1)

All three providers (Google, Apple, Outlook) ship at MVP per PRD FR-3 / FR-50. The provider list renders with **provider parity** — identical visual weight, identical button affordance, identical affordance copy. The handshake differs (OAuth 2.0 vs. CalDAV app-specific password), but the user should never perceive one provider as "the real one" and the others as "secondary." Engineering must not ship a state where Google is `Button.Primary` and Apple/Outlook are `Button.Ghost` text links — that visual hierarchy would falsely signal preference and contradict the parity contract.

### Cards

- `component.card.pulse.digest` — The signature editorial card. Anatomy, top-to-bottom: a 3px left-edge category stripe (`{color.accent.slate}` for public events, `{color.accent.amber}` for must-know, `{color.warm.personal}` for personal events), a `{type.scale.meta.sm}` kicker label in `{color.ink.muted}`, a `{type.scale.headline.md}` headline in `{color.ink.primary}` (max 8 words), a `{type.scale.microtag}` row of inline italic tags separated by middle dots, a `{type.scale.meta.md}` source-and-time row, and the `component.indicator.confidence` row at the bottom. Sits on `component.surface.card`. The conflict indicator (8px filled amber circle, top-right) renders independently when active.
- `component.card.pulse.digest.category.public` — Variant with `{color.accent.slate}` left stripe.
- `component.card.pulse.digest.category.mustknow` — Variant with `{color.accent.amber}` left stripe. Should appear on fewer than ~10% of cards in any given view.
- `component.card.pulse.digest.category.personal` — Variant with `{color.warm.personal}` left stripe. Always paired with the visible text label "Personal."
- `component.card.pulse.digest.category.discovery` — Variant with `{color.accent.slate}` left stripe at 0.85 opacity plus a `discovery` micro-tag in the micro-tag row.

### Badges and indicators

- `component.badge.source` — Inline source attribution badge. Five variants, distinguished by glyph + label color, not by fill. (Canonical list — also enumerated in `EXPERIENCE.md §4`.)
  - `official_site` — `color.accent.terracotta` label, terracotta-filled checkmark icon. One of the four sanctioned terracotta uses. The only one that appears on a card body besides the `Indicator.Today` dot.
  - `community` — `{color.ink.primary}` label, 1.5px ink-bordered checkmark (no fill). Italic label.
  - `aggregator` — `{color.ink.secondary}` label, ink-bordered link/chain glyph.
  - `user_imported` — `{color.ink.secondary}` label, ink-bordered inbox icon.
  - `crawled_html` — Small `color.warn.amber` warning triangle. One-time "Why does this show ⚠?" tooltip on first view per user per event.
  - Always inline on the card (top-right zone, in the trust-signal row with `Indicator.Confidence`), never behind a tap. Every variant includes a visible inline text label, not icon-only (WCAG 1.1.1).
- `component.indicator.confidence` — A row of 1–5 small dots (`{radius.full}`, 6px diameter) in `{color.ink.faint}` for unfilled positions and `{color.ink.primary}` for filled positions. The numeric count is rendered in `{type.scale.numeric}` next to the dots. Five positions, always; never a bar.
- `component.indicator.today` — A single 6px `{radius.full}` dot in `{color.accent.terracotta}` with the sanctioned glow `box-shadow: 0 0 12px rgba(255,106,71,0.55)`. Placed inline next to today's date label. Not a background fill, not a bar — a single glowing dot.
- `component.indicator.conflict` — An 8–10px filled circle in `{color.warn.amber}` (PRD FR-58). Top-right of the affected Pulse Card, symmetric across the conflict pair. Distinct in shape and position from the Source Badge and Confidence Pulse. `aria-label="Schedule conflict"`. Never red.

### Empty and quiet states

- `component.emptystate.quiet` — Full-section empty state on a Pulse Digest with no qualifying events. Centered `{type.scale.display.md}` headline in `{color.ink.primary}`, `{type.scale.body.md}` lede in `{color.ink.secondary}`, optional `{component.button.primary}` or `{component.button.ghost}` action. Bordered by a 1px dashed `{color.border.strong}` to feel intentional, not failed. Example copy: "No pulse today — your week is quiet." A suggested-sources strip below is permitted.

### Pro upsell

- `component.card.pro.upsell` — The single sanctioned use of a tinted background gradient: `linear-gradient(135deg, rgba(255,106,71,0.10), rgba(110,126,146,0.10))`. 1px border `rgba(255,106,71,0.25)`, `{radius.card}` (12px), 20px padding. Used only on the Pulse Digest sidebar and the Settings → Plan section. No other surface uses a gradient background.

### Timeline (Amendment A-8)

- `component.timeline.cell` — A single day cell in the 7-column week grid at `/timeline`. `{color.surface.elevated}` resting fill; `{color.surface.subtle}` fill on the "today" cell (highlight). 1px `{color.border.subtle}` vertical dividers between adjacent cells; no horizontal border. Outer corners (top-left of the first column, top-right of the last) use `{radius.timeline-cell}` (10px); inner shared corners are not rounded so the grid reads as continuous. Padding `{spacing.3}` (12px) desktop, `{spacing.4}` (16px) mobile. Empty state: centered `{type.scale.meta.md}` "Quiet day." in `{color.ink.muted}`. (Locked in EXPERIENCE.md §4 `Surface.Timeline` and §5 Empty Patterns.)
- `component.timeline.day-header` — The Mon/Tue/Wed… column header in the week grid. `{type.scale.meta.sm}` `{color.ink.muted}` for the day-of-week label; `{type.scale.meta.md}` `{color.ink.primary}` for the date number. **Today:** date number rendered in `{color.accent.terracotta}` with the sanctioned glow (`box-shadow: 0 0 12px rgba(255,106,71,0.55)`) — same treatment as `Indicator.Today` on Pulse Cards. Background `{color.surface.paper}` on all cells; no fill differentiation by default. Sticky on scroll (desktop `md+`).
- `component.timeline.event-block` — A single event rendered inside a day cell. `{color.surface.subtle}` resting fill, 1px `{color.border.subtle}` stroke, 2px left-edge category stripe (`{color.warm.personal}` for personal events, `{color.cool.public}` for public events), `{radius.subtle}` (6px) corners. Padding `{spacing.2}` × `{spacing.3}`. Content: event name in `{type.scale.meta.md}` `{color.ink.primary}` (single line, ellipsis on overflow) + time row in `{type.scale.meta.sm}` `{color.ink.muted}`. The "Personal" / "Public event" text label sits in the top-right corner of the block as `{type.scale.meta.sm}` `{color.ink.muted}` — color is never the sole carrier of meaning (WCAG 1.4.1; mirrors the existing Pulse Card category stripe rule). Hover: fill swaps to `{color.surface.inset}` (subtle elevation in the dark surface); no shadow, no border color shift. Conflict indicator: 6px filled circle in `{color.warn.amber}` at the top-right corner of the block, mirroring `component.indicator.conflict` on Pulse Cards. `aria-label="Schedule conflict"`. Reduced motion: no fade-in on mount.

### Navigation (Amendment A-8)

- `component.bottom-tab` — Mobile bottom navigation. Fixed at bottom of the viewport on viewports `<768px`. Full-width, height `{layout.bottom-tab.height}` (56px + safe-area inset). Background `{color.surface.elevated}`. Top edge: 1px `{color.border.subtle}`. Four equal-width slots (25% each) for the four routes: **Digest / Timeline / Add / Settings**. Each slot: 16×16 stroke-only SVG icon (never filled chromatic) + label in `{type.scale.meta.sm}`. Resting state: icon + label in `{color.ink.muted}`. Active state: **ink-inverted background on the slot only** (`{color.ink.primary}` fill + `{color.ink.inverse}` icon + `{color.ink.inverse}` label), mirroring the `Control.Segmented` pattern. **Never** a full-bar `{color.accent.terracotta}` fill — terracotta on a small-control toggle burns the accent on a control used many times per day. Active indicator: a 2px `{color.accent.terracotta}` underline bar above the active slot (the only chromatic use in the bottom-tab, mirrors the desktop topnav active pattern from `mockups/pulse-digest-desktop.html` L75–76). Z-index above page content, below modals. Tap → route navigation; long-press disabled.
- `component.sidenav.app` — Desktop left-rail navigation on viewports `≥768px`. Sticky `<aside>`. Width `{layout.sidenav.app.width.tablet}` (220px) on `md`, `{layout.sidenav.app.width.desktop}` (240px) on `lg+`. Background `{color.surface.paper}` (same as canvas — the sidenav is a layout container, not a visual element). Inset from page edge: `{spacing.6}` (24px) on top and sides. Items, top-to-bottom: (1) Brand mark — 28×28 logo + "EventPulse24" wordmark in `{type.scale.body.md}` `{color.ink.primary}`. Below: 1px `{color.border.subtle}` divider. (2) Four route items: **Digest / Timeline / Add / Settings** in `{type.scale.body.md}` `{color.ink.secondary}`. Resting state on the page background. Active item: `{color.ink.primary}` label on a `{color.surface.subtle}` pill background with 1px `{color.border.subtle}` stroke — mirrors the `Control.Segmented` ink-inversion pattern in miniature. **Never** terracotta fill on the active route. Keyboard: `Tab` cycles sidenav links after the topbar (topbar first in tab order, per ASSUM-11) and before page content. The topbar still carries only the brand mark + (optionally) the tagline; the sidenav is the nav, the topbar is the identity zone.

## Do's and Don'ts

| Do | Don't |
|---|---|
| Use `color.accent.terracotta` only for the today indicator, the primary CTA, the verified source badge, and the focus ring (the one sanctioned exception — see §Color usage rules). | Use terracotta on hover states, link underlines, category stripes, or anywhere else outside the four sanctioned uses. |
| Use italic micro-tags inline (`nearby · tonight · music`) via `type.scale.microtag`. | Set micro-tags in regular weight or in the display font. |
| Show the source badge inline on the card, never behind a tap. | Hide source attribution behind a "details" disclosure or modal. |
| Keep card headlines to 8 words or fewer. | Wrap a long sentence as a card headline; that is body copy, not a headline. |
| Use `{color.accent.slate}`, `{color.accent.amber}`, and `{color.warm.personal}` exclusively for category stripes on `Card.PulseDigest`. Always pair with the visible text label ("Public event", "Must-know", "Personal"). | Use slate, amber, or warm-personal on buttons, icons, or interactive surfaces. |
| Communicate hover on dark via `color.surface.subtle` fill swap or 1px border transition. | Add a drop-shadow on hover in dark mode. Elevation on dark feels cheap and breaks the void aesthetic. |
| Use `radius.control` (12px) for `Button.Primary`. | Apply 12px radius as a unique differentiator vs. cards in dark mode — both share 12px. Distinction comes from the terracotta fill. |
| Reserve `Indicator.Confidence` for AI-generated recommendations and reminders. | Render a confidence indicator on a manually-entered event or a public event from an official source. |
| Place one `Button.Primary` per **decision moment**, separated by `spacing.12`+ whitespace. A surface may have multiple decision moments (e.g. `/events/:id` has Save and Configure-reminders); each gets its own primary in a distinct visual zone. | Stack multiple terracotta CTAs in the same visual zone, or place two primaries adjacent without whitespace separation. |
| Use `EmptyState.Quiet` for genuinely empty days — present it as a feature, not a failure. | Replace an empty state with "no results" copy, illustration, or a suggested-search rail beyond the permitted suggested-sources strip. |
| Use the sanctioned glow only on `Indicator.Today` and the brand mark. | Glow other elements, buttons, or accents. Glow is rationed. |
| Use the gradient background only on `component.card.pro.upsell`. | Apply gradients to hero sections, cards, or any other surface. |
| Ship dark mode as the default. Make light mode an opt-in swap. | Treat light mode as the source and dark as a swap. The visual identity is dark-first. |
| Keep the topbar for identity only — brand mark + tagline. All action affordances (Skip, Sign in, Sign up, Open menu, etc.) live in the page footer or in surface-level CTAs, never in the topbar. | Place action buttons, benefit claims, or "Skip — take me to X" affordances in the topbar. The topbar carries *who we are*, never *what you should do*. (See `EXPERIENCE.md` §3 Zone roles.) |
| Render all three calendar providers (Google / Apple / Outlook) at identical visual weight on `/onboarding` step 1. | Render Google as `Button.Primary` and Apple/Outlook as ghost links or text-only. The three providers have parity per PRD FR-3 / FR-50. |
| Use `component.control.segmented` (ink-inversion selected state) for AM/PM and small two- or three-option toggles. | Fill a segmented control's selected state with terracotta. Terracotta is rationed; small toggles use ink inversion. |
| Use the `rgba(255,106,71,0.10)` small-control selection tint for preset rows and reminder slots. | Fill the active state of a small chip/preset/segmented control with solid terracotta. Tint is the canonical selection treatment. |
| Use `radius.subtle` (6px) for chips, inputs, presets, segmented controls, and meta tags. | Render any of those as pills (`9999px`). Pills are reserved for the four sanctioned round elements in `radius.full`. |
| Pair every category stripe (`color.warm.personal`, `color.cool.public`, `color.warn.amber`) on `component.timeline.event-block` with a visible text label in the top-right corner ("Personal" / "Public event"). | Use category stripe color as the sole carrier of meaning on Timeline event-blocks. WCAG 1.4.1 — color is never the only signal. |
| Render the mobile bottom-tab active slot with **ink inversion** (slot fill in `color.ink.primary` + label/icon in `color.ink.inverse`) plus a 2px `color.accent.terracotta` underline bar above the active slot. | Fill the entire bottom-tab bar with `color.accent.terracotta` on the active route, or fill the active slot solid terracotta. Both burn the accent on a control used many times per day. |
| Reach `/timeline` and `/conflicts` from the bottom-tab nav on mobile (`sm`) and from the left sidebar nav on desktop (`md+`). | Add Timeline or Conflicts links to the topbar. Topbar carries identity only (EXPERIENCE.md ASSUM-11). |

## Assumptions

All open `[ASSUMPTION:…]` markers in this document, consolidated. Each entry has a stable ID (`ASSUM-N`) for cross-reference from the body and from `EXPERIENCE.md`. Status: OPEN = needs a decision before engineering ships; RESOLVED = owner has answered; DEFERRED = explicitly parked to a later phase.

- **ASSUM-1.** Hex values for the dark palette are calibrated for true-black OLED with a single terracotta glow. Light-mode hex values are derived from a cool-neutral paper-and-ink direction. Brand provided terracotta (`#C4502B` light, lifted to `#FF6A47` for dark contrast); all other hex values are derived.
  - Status: OPEN
  - Owner: TBD (brand / design owner)
  - Affects: §Colors, §Token Implementation Contract
  - Decision deadline: before engineering token implementation begins
  - Action: sample the dark palette from the OLED-instrument-grade reference set (Linear, Vercel, Arc dark); replace the estimated hex values with sampled values; re-verify AA contrast for `color.ink.*`, `color.warn.amber`, and the terracotta focus ring against `color.surface.paper` in dark and light modes.

- **ASSUM-2.** The locked display-serif chain is `Source Serif 4` with `Fraunces` as fallback. Engineering may swap the family name (e.g. for `IBM Plex Serif`, `Tiempos`) but the scale (`type.scale.display.*`, `type.scale.headline.*`) and the role (display family for headlines and editorial display moments only) are the contract and may not change.
  - Status: OPEN
  - Owner: design (final family pick) + engineering (font hosting / loading)
  - Affects: §Typography → Type families; all `component.text.display` and `component.text.headline` render paths
  - Decision deadline: before first production typography integration
  - Action: confirm the family pick; verify the chosen family has the weight set (400 / 600 / 700) and italic availability used in `type.scale.microtag`; license the chosen family or confirm open-source status.

- **ASSUM-3.** Dark mode is the default theme at first paint. Engineering ships `data-theme="dark"` on the `<html>` element by default. Light mode is opt-in via Settings. No `prefers-color-scheme: dark` auto-switch at MVP (Phase 2 candidate).
  - Status: RESOLVED
  - Owner: design + engineering
  - Affects: §Token Implementation Contract → Dark-mode trigger
  - Rationale: dark-first brand posture, OLED-friendly default, instrument-grade aesthetic.

- **ASSUM-4.** Card corner radius bumped from 8px (light) to 12px (dark). Inputs bumped from 4px to 6px. Reasoning: darker surfaces need slightly more rounding to feel intentional vs. abrupt against the void.
  - Status: RESOLVED
  - Owner: design
  - Affects: §Shapes

- **ASSUM-5.** `layout.container.form` is a 720px-centered narrow column aliased to `layout.container.reading` (same value, distinct token for semantic clarity). Used on `/onboarding` (all three steps), `/settings/*` narrow forms, and single-decision auth flows. The token exists so semantic references don't drift across docs (e.g., the onboarding mockup saying "max-width: 720px" doesn't accidentally borrow `reading` semantics).
  - Status: RESOLVED
  - Owner: design
  - Affects: §Layout & Spacing → Layout tokens; all `/onboarding` and `/settings/*` mockups

- **ASSUM-6.** The `rgba(255,106,71,0.10)` + `rgba(255,106,71,0.30)` border + `color.accent.terracotta` label pattern is the canonical "small-control selected state" treatment across the system. Originally introduced for `component.input.reminder.slot`, now generalized to time-preset rows, interest-chip selected state, and any future small-toggle selection. **Do not** substitute a solid terracotta fill for the tint; tint is the contract.
  - Status: RESOLVED
  - Owner: design
  - Affects: §Components → Inputs (`Input.ReminderSlot`); §Components → Control (`Control.Preset`); §Color usage rules → selection treatment

- **ASSUM-7.** _Amendment A-8 (2026-09-06)._ Timeline at MVP is **read-only** — no edit-from-Timeline, no drag-to-reschedule, no inline conflict resolution on Timeline itself. Conflicts surface on Pulse Cards and Timeline event-blocks as `component.indicator.conflict` (8–10 px filled amber circle, `aria-label="Schedule conflict"`); tapping routes to Detail Screen for resolution via the FR-33 three-action pattern. The `/conflicts` route is a review surface for system-recorded conflict pairs (active + resolved) — no user-added notes. Navigation to `/timeline` and `/conflicts` happens exclusively from `Component.BottomTab` (mobile `sm`) and `Component.Sidenav.App` (desktop `md+`). The topbar stays brand-only (topbar-quiet rule, EXPERIENCE.md ASSUM-11). Cross-reference: EXPERIENCE.md ASSUM-12.
  - Status: RESOLVED
  - Owner: design + engineering
  - Affects: §Components → Timeline; §Components → Navigation; §Do's and Don'ts → topbar nav rule; EXPERIENCE.md §4 `Surface.Timeline`, §4 `Component.BottomTab`, §4 `Component.Sidenav.App`
