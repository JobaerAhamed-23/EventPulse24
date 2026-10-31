I have everything. Here is the complete research report.

---

# Pulse Card (`Card.PulseDigest`) — Verbatim Spec Report

**Authoritative files (both confirmed to exist; there is NO separate `ASSUMPTIONS.md` — assumptions are inline in each doc):**
- `/Users/jobaer/Documents/EventPulse24/_bmad-output/planning-artifacts/ux-designs/ux-EventPulse24-2026-08-23/DESIGN.md` (107,641 bytes)
- `/Users/jobaer/Documents/EventPulse24/_bmad-output/planning-artifacts/ux-designs/ux-EventPulse24-2026-08-23/EXPERIENCE.md` (177,389 bytes) — exact filename confirmed

Throughout, `DESIGN.md` = `_bmad-output/planning-artifacts/ux-designs/ux-EventPulse24-2026-08-23/DESIGN.md` and `EXPERIENCE.md` = `.../EXPERIENCE.md`.

---

## 0. Precedence — "the spines win"

The quoted sentence in the work item is **not** in the UX docs themselves; it is the `bmad-ux` skill contract, which is the upstream rule that makes the spines authoritative.

`.agents/skills/bmad-ux/SKILL.md:11` (identical at `.claude/skills/bmad-ux/SKILL.md:11`):

> Produce two peer contracts: **`DESIGN.md`** (visual identity per the [Google Labs spec](https://github.com/google-labs-code/design.md) — owns *how it looks*) and **`EXPERIENCE.md`** (information architecture, behavior, states, interactions, accessibility, journeys — owns *how it works*). EXPERIENCE.md cross-references DESIGN.md tokens by name using `{path.to.token}` syntax. **Both spines win on conflict with any mock, wireframe, or import.**

The work item states the rule in its own words — `.specs-fire/intents/pulse-digest-and-trust/work-items/frontend-pulse-card.md:18`:

> The spec is unusually complete, and where the mockups disagree with it, **the spines win** — EXPERIENCE.md says so in as many words: "if a mockup diverges from a token in `DESIGN.md` or a behavior in this spine, fix the mockup, not the spine."

And `.specs-fire/intents/pulse-digest-and-trust/brief.md:112`:

> - **The UX is implemented, not redesigned**, and **the spines win over the mockups** (EXPERIENCE.md's own precedence rule). Binding: `pulse-digest-desktop.html`, `pulse-digest-empty-state-desktop.html`, `event-detail-desktop.html`, `conflict-indicator-card-state-desktop.html`, plus `DESIGN.md` and `EXPERIENCE.md`. There is no component library.

`DESIGN.md:115`:
> The visual identity in this document is the source of truth; this subsection specifies the build substrate so engineering does not reach for a UI library, a tooltip framework, or an animation library to implement it.

`EXPERIENCE.md:19`:
> The behavioral contract for the product. Visual identity lives in `DESIGN.md`; this spine is the experience.

`EXPERIENCE.md:174`:
> Behavioral specs only. Visual composition lives in `DESIGN.md.Components`.

---

## 1. `component.card.pulse.digest` — the full bullet list

### `DESIGN.md` § Components → Cards — `DESIGN.md:291-297` (verbatim, complete)

```
### Cards

- `component.card.pulse.digest` — The signature editorial card. Anatomy, top-to-bottom: a 3px left-edge category stripe (`{color.accent.slate}` for public events, `{color.accent.amber}` for must-know, `{color.warm.personal}` for personal events), a `{type.scale.meta.sm}` kicker label in `{color.ink.muted}`, a `{type.scale.headline.md}` headline in `{color.ink.primary}` (max 8 words), a `{type.scale.microtag}` row of inline italic tags separated by middle dots, a `{type.scale.meta.md}` source-and-time row, and the `component.indicator.confidence` row at the bottom. Sits on `component.surface.card`. The conflict indicator (8px filled amber circle, top-right) renders independently when active.
- `component.card.pulse.digest.category.public` — Variant with `{color.accent.slate}` left stripe.
- `component.card.pulse.digest.category.mustknow` — Variant with `{color.accent.amber}` left stripe. Should appear on fewer than ~10% of cards in any given view.
- `component.card.pulse.digest.category.personal` — Variant with `{color.warm.personal}` left stripe. Always paired with the visible text label "Personal."
- `component.card.pulse.digest.category.discovery` — Variant with `{color.accent.slate}` left stripe at 0.85 opacity plus a `discovery` micro-tag in the micro-tag row.
```

> ⚠️ **Known stale value:** the "8px filled amber circle" in L293 is contradicted by `DESIGN.md:310` (6px), `EXPERIENCE.md` ASSUM-13 (6px, RESOLVED), and `EXPERIENCE.md:1115` ("never collapses below 6×6 px … the locked size"). The work item calls this out explicitly — `frontend-pulse-card.md:29`: *"DESIGN.md L293's "8px" and the mockup's 10px are both stale; ASSUM-13's 6px is locked."*

### `EXPERIENCE.md` §4 `Card.PulseDigest` — `EXPERIENCE.md:176-187` (verbatim, complete)

```
### `Card.PulseDigest`
A single Pulse Card on the home surface. Always shows: event name, time, location, up to 3 Why-this Tags, 1–5 dot Confidence Pulse, Source Badge (PRD FR-6). Visual spec: `DESIGN.md.Components.PulseDigestCard`.

- **Default state:** Card is `Card.PulseDigest` with body `Text.Body`, headline `Text.Display.sm`, metadata `Text.Meta`. No paper-darker shade. The card is `color.surface.paper` with a 1px hairline border in `color.ink.faint`.
- **Hover (desktop only):** Background shifts to `color.surface.paper.darker` (a 1-step paper-darker variant). A small `▸` affordance appears at the trailing edge, indicating the card is tappable to open Detail. The `▸` is **decorative information about tappability, not a click target of its own** — the entire card remains the tap target. The same `▸` affordance is shown on mobile when the card is in any focused or long-pressed state (keyboard focus, Switch Control focus, Touch & Hold), so the desktop hover cue has a mobile equivalent and §6 "No hover-only affordances on `sm` viewports" is honored. The `▸` is rendered with `aria-hidden="true"` (decorative) and the full tap target is announced via the card's `aria-label`.
- **Tap:** Opens `/events/:id`.
- **Long-press (mobile):** Shows a quick-actions sheet anchored to the card: Save, Dismiss, Less like this. Sheet uses `color.surface.paper` and standard mobile sheet affordances.
- **Swipe-left:** Dismiss (records "less like this"). Card animates off-screen to the left, snaps back if cancelled mid-swipe.
- **Swipe-right:** Save (to user's saved collection or default). Card animates off-screen to the right with a brief save confirmation.
- **Focus state (keyboard):** Visible 2px focus ring in `color.accent.terracotta` at AA contrast against `color.surface.paper`. `aria-label` reads the full card content.
- **Reduced motion:** All swipe animations collapse to instant transition with no fade. (See §7 Interaction Primitives.)
- **Adaptive expansion (engaged user ≥10 saves/30d):** Card count grows from 3 to 5 (top of the responsive matrix) or 7 (max). At 5+, a "Show all 5" inline link replaces the bottom card with the remainder of the stack, in place — no modal, no carousel. (See §10 Adaptive Density.)
```

> ⚠️ **Known drift:** L179's default state says `color.surface.paper` + `color.ink.faint` hairline; `DESIGN.md:253` (`component.surface.card`) says `color.surface.elevated` fill + `color.border.subtle` stroke. The work item resolves this in favour of the token — `frontend-pulse-card.md:23`: *"Container: `color.surface.elevated` fill, 1px `color.border.subtle`, `radius.card` **12px** … (The mockup's 14px radius and 32px padding are drift; the tokens govern.)"*
> Also `DESIGN.md:111` states `color.surface.paper.darker` is *"reserved for `Card.PulseDigest` hover background"*, and `DESIGN.md:60` gives it as `#050506` (darker than paper), while `EXPERIENCE.md:180` calls it *"a 1-step paper-darker variant"* — while `DESIGN.md:253` says hover swaps fill to `{color.surface.subtle}` (desktop). The work item settles it as: *"Hover is a border or background shift only — **no shadow is ever added**."*

---

## 2. `Indicator.Confidence` — the full entry

### `EXPERIENCE.md:206-216` (verbatim, complete)

```
### `Indicator.Confidence`
The 1–5 dot Confidence Pulse on each Pulse Card (PRD FR-22). Five discrete states; no partial fills.

- **Visual:** Five dot placeholders arranged horizontally. Filled dots use `color.ink.primary`; empty dots use `color.ink.faint`. Spacing: 4px between dots. (Confidence Pulse is not on the terracotta-sanctioned list — its filled dots use ink-primary for the same reason the rest of the trust-signal dots do; the today indicator (`color.accent.terracotta`) is the single chromatic dot in the system.)
- **Default:** Dots only. No numeric label visible. `aria-label="4 of 5"` for screen readers (per §8 Accessibility Floor).
- **Hover/focus:** Tooltip "Why this confidence?" appears with 1–3 lines of contributing factors: e.g., "Strong match on your top three interests. Within 2 km. Source reliability 0.92." Tooltip uses `Text.Meta` on `color.surface.paper.darker`.
- **Bucket boundaries (PRD FR-22):** ≥0.85 = 5 dots, ≥0.65 = 4, ≥0.45 = 3, ≥0.25 = 2, else 1. No interpolation.
- **Hysteresis (transition rule):** Hysteresis is **per-event-per-day** — once a bucket is assigned at Pulse composition time for a given event on a given calendar day (in the user's local timezone), the event stays in that bucket for the remainder of the calendar day. The bucket recomputes only if the raw score changes by **≥0.10** within the same day (rare; happens only when the underlying recommendation model re-scores the same event mid-day). Across days, hysteresis resets — a new composition starts fresh bucket assignment. No persistent bucket is stored between days. On an exact bucket boundary (raw score e.g. 0.850), the **lower** bucket is used (≥0.85 means strictly greater than 0.85; 0.85 itself → 4 dots).

  _Worked example:_ Event X first appears on Tuesday with raw score 0.83 → 4 dots. Model re-scores mid-day to 0.86 → below the 0.10 delta threshold (delta = 0.03), so the event stays at 4 dots. If the model re-scored to 0.97 (delta = 0.14 from 0.83), the event moves to 5 dots. Next morning Wednesday, a fresh composition assigns the bucket from the new raw score without inheriting Tuesday's bucket.
- **Tap on a dot:** Same as hover (shows tooltip).
```

### `DESIGN.md:308` (verbatim — the visual token entry)

> - `component.indicator.confidence` — A row of 1–5 small dots (`{radius.full}`, 6px diameter) in `{color.ink.faint}` for unfilled positions and `{color.ink.primary}` for filled positions. The numeric count is rendered in `{type.scale.numeric}` next to the dots. Five positions, always; never a bar.

> ⚠️ **Conflict on the visible numeric:** `DESIGN.md:308` says *"The numeric count is rendered in `{type.scale.numeric}` next to the dots."* `EXPERIENCE.md:210` says *"Dots only. **No numeric label visible.**"* The work item rules for EXPERIENCE — `frontend-pulse-card.md:27`: *"Default shows **dots only with no visible numeric**, with `aria-label="N of 5"`."* and `:34`: *"…the confidence indicator at 1 and 5 and **the absence of a visible numeric**…"*.

### Tooltip behaviour (hover / focus / touch) — `DESIGN.md:124`

> - **Tooltip pattern.** `Tooltip.Source` and `Tooltip.Confidence` use a `<button>` trigger with `aria-describedby="tooltip-{id}"` pointing to a sibling `<span role="tooltip" id="tooltip-{id}">`. Tooltips appear on `:hover` and `:focus-visible`; on touch viewports (`<768px`), tooltips appear on tap and dismiss on outside-tap or `Esc`. No hover-only tooltips on touch. The tooltip container uses `color.surface.elevated` fill, the one allowed shadow (`0 8px 24px rgba(0,0,0,0.40)` in dark, `0 8px 24px rgba(0,0,0,0.08)` in light), and `Text.Meta` content.

> ⚠️ **Tooltip surface conflict:** `EXPERIENCE.md:211` says the confidence tooltip *"uses `Text.Meta` on `color.surface.paper.darker`"*, while `DESIGN.md:124` says the tooltip container uses `color.surface.elevated` fill with the one allowed shadow. `DESIGN.md:124` is the token layer and is more specific about the tooltip pattern; `DESIGN.md:111` also reserves `color.surface.paper.darker` for *"Card.PulseDigest hover background and the skeleton pulse animation's resting frame"* — explicitly **"Never used as a static surface"**, which a tooltip is. This is an unresolved drift in the sources.

### Tooltip content — the locked microcopy

`EXPERIENCE.md:117` (§3 microcopy contract table):
> | Confidence Pulse tooltip ("Why this confidence?") | "4 of 5. Strong match on your top three interests and within 2 km." | "We think you'll love this! Confidence: 4.7/5" |

`EXPERIENCE.md:1063-1067` (Why-this breakdown example, contributing-factor line format):
> ```
> > "Surfaced because:
> > - Comedy is in your top 3 categories.
> > - 2 km from your work.
> > - 12 of your neighbors saved this.
> > - Source reliability 0.92."
> ```

### Accessibility floor — `EXPERIENCE.md:734`

> - **Confidence Pulse:** `aria-label="4 of 5"` (not just "4 dots").

### Dot size / radius — `DESIGN.md:237`

> - `radius.full` — 9999px. Reserved for the terracotta `Indicator.Today` dot, the dots in `Indicator.Confidence`, the avatar, and status dots. **Never used for buttons, chips, preset rows, or segmented controls.**

### Empty-dot colour reservations

`DESIGN.md:58`:
> - `color.ink.faint` — `#3A3A40`. The dimmest readable ink. Used only for: empty `Indicator.Confidence` dot placeholders, the dim target of the skeleton pulse animation, and the handle bar on mobile bottom sheets. Never used for body copy or interactive affordances.

`DESIGN.md:84` (light mode):
> - `color.ink.faint` — `#C9C2B5`. Empty `Indicator.Confidence` dot placeholders on light.

`DESIGN.md:110`:
> - `color.ink.faint` is reserved for empty `Indicator.Confidence` dot placeholders, the skeleton pulse animation's dim target, and the handle bar on mobile bottom sheets. Never used for body copy or interactive affordances.

### The "no confidence on official/manual events" rule — `DESIGN.md:388`

> | Reserve `Indicator.Confidence` for AI-generated recommendations and reminders. | Render a confidence indicator on a manually-entered event or a public event from an official source. |

### The "Confidence Pulse" grep hits (every occurrence across both docs)

| File:line | Verbatim |
|---|---|
| `DESIGN.md:58` | `- `color.ink.faint` — `#3A3A40`. The dimmest readable ink. Used only for: empty `Indicator.Confidence` dot placeholders, the dim target of the skeleton pulse animation, and the handle bar on mobile bottom sheets. Never used for body copy or interactive affordances.` |
| `DESIGN.md:84` | `- `color.ink.faint` — `#C9C2B5`. Empty `Indicator.Confidence` dot placeholders on light.` |
| `DESIGN.md:110` | `- `color.ink.faint` is reserved for empty `Indicator.Confidence` dot placeholders, the skeleton pulse animation's dim target, and the handle bar on mobile bottom sheets. Never used for body copy or interactive affordances.` |
| `DESIGN.md:237` | `- `radius.full` — 9999px. Reserved for the terracotta `Indicator.Today` dot, the dots in `Indicator.Confidence`, the avatar, and status dots. **Never used for buttons, chips, preset rows, or segmented controls.**` |
| `DESIGN.md:308` | `- `component.indicator.confidence` — A row of 1–5 small dots (`{radius.full}`, 6px diameter) in `{color.ink.faint}` for unfilled positions and `{color.ink.primary}` for filled positions. The numeric count is rendered in `{type.scale.numeric}` next to the dots. Five positions, always; never a bar.` |
| `DESIGN.md:388` | `| Reserve `Indicator.Confidence` for AI-generated recommendations and reminders. | Render a confidence indicator on a manually-entered event or a public event from an official source. |` |
| `EXPERIENCE.md:43` | `- Trust through transparency — Source Badges, Confidence Pulse, no hidden ranking.` |
| `EXPERIENCE.md:117` | `| Confidence Pulse tooltip ("Why this confidence?") | "4 of 5. Strong match on your top three interests and within 2 km." | "We think you'll love this! Confidence: 4.7/5" |` |
| `EXPERIENCE.md:177` | `A single Pulse Card on the home surface. Always shows: event name, time, location, up to 3 Why-this Tags, 1–5 dot Confidence Pulse, Source Badge (PRD FR-6). Visual spec: `DESIGN.md.Components.PulseDigestCard`.` |
| `EXPERIENCE.md:207-216` | The full `### `Indicator.Confidence`` entry (quoted above) |
| `EXPERIENCE.md:721` | `- Conflict indicator (PRD FR-58): filled circle in `color.warn.amber` *and* `aria-label="Schedule conflict"`. Shape distinct from Source Badge and Confidence Pulse dots.` |
| `EXPERIENCE.md:734` | `- **Confidence Pulse:** `aria-label="4 of 5"` (not just "4 dots").` |
| `EXPERIENCE.md:771-773` | `   - (a) "Sam's birthday dinner — 7pm tonight" with Why-this Tags `close-friend, tonight, restaurant`. Confidence Pulse 4 of 5. Source Badge: User-imported (calendar).` / `   - (b) "Free tech meetup Thu, 2 blocks from work" with `nearby, thursday, free`. Confidence 3 of 5. Source: Community.` / `   - (c) "Rooftop jazz in your neighborhood Sat" with `nearby, weekend, novel`. Confidence 3 of 5. Source: Official.` |
| `EXPERIENCE.md:794-795` | `1. SEO page renders 3 Pulse Cards for Brooklyn today, plus the headline "Events near Brooklyn today." Each card has Why-this Tags, a Confidence Pulse, and a Source Badge. The cards are crawlable, Schema.org JSON-LD embedded.` |
| `EXPERIENCE.md:955` | `- **Desktop does not add features.** Desktop adds whitespace and (optionally) reveals hover affordances on `Badge.Source` and `Indicator.Confidence`. No new screens, no new actions, no new copy. PRD §13.1: "Whitespace over density."` |
| `EXPERIENCE.md:1030` | `- **Confidence Pulse** (PRD FR-22) — top-right of card, immediately left of Source Badge. 1–5 dots. `aria-label="4 of 5"` for screen readers.` |
| `EXPERIENCE.md:1040` | `2. **Confidence Pulse** (inline, with `Tooltip.Confidence` showing contributing factors on hover).` |
| `EXPERIENCE.md:1092` | `- 1 Confidence Pulse (top-right)` |
| `EXPERIENCE.md:1103` | `| **Hovered (desktop)** | Mouse hover | Background shifts to `color.surface.paper.darker`. `▸` affordance appears. Tooltips available on Source Badge and Confidence Pulse. |` |
| `EXPERIENCE.md:1111` | `Adaptive density must not hide the trust signals (Why-this Tags, Confidence Pulse, Source Badge) at any density mode. The mobile default exposes all three; hover/focus/long-press *add* detail but never *remove* the trust signals. PRD §13.1: "Why-this Tags are first-class."` |
| `EXPERIENCE.md:1150` | `- `Indicator.Confidence` — 5-dot confidence indicator.` |
| `EXPERIENCE.md:1160` | `- `Tooltip.Source` / `Tooltip.Confidence` — hover/focus tooltips.` |

---

## 3. `Badge.Source` — the full entry (both docs)

### `EXPERIENCE.md:218-226` (verbatim, complete)

```
### `Badge.Source`
The Source Badge on each Pulse Card and Detail Screen (PRD FR-23). Five types: `official_site`, `community`, `aggregator`, `user_imported`, `crawled_html`.

- **`official_site`:** `color.accent.terracotta`-filled checkmark icon. Inline label "Official" in `Text.Meta`. Tooltip: "Verified venue or organizer."
- **`community`:** Ink-bordered checkmark (no fill, 1.5px border in `color.ink.primary`). Inline label "Community" in `Text.Meta` italic. Tooltip: "Posted by a community member."
- **`aggregator`:** Ink-bordered link icon (chain glyph). Inline label "Listing site." Tooltip: "Aggregated from a public listing."
- **`user_imported`:** Ink-bordered inbox icon. Inline label "Forwarded." Tooltip: "Added by you or from your calendar."
- **`crawled_html`:** A small `color.warn.amber` warning triangle. One-time "Why does this show ⚠?" tooltip on first view per user per event.
- **Text alternative:** Every variant includes a visible inline text label, not icon-only. (WCAG 1.1.1 per §8.)
```

### `DESIGN.md:301-307` (verbatim, complete)

```
- `component.badge.source` — Inline source attribution badge. Five variants, distinguished by glyph + label color, not by fill. (Canonical list — also enumerated in `EXPERIENCE.md §4`.)
  - `official_site` — `color.accent.terracotta` label, terracotta-filled checkmark icon. One of the four sanctioned terracotta uses. The only one that appears on a card body besides the `Indicator.Today` dot.
  - `community` — `{color.ink.primary}` label, 1.5px ink-bordered checkmark (no fill). Italic label.
  - `aggregator` — `{color.ink.secondary}` label, ink-bordered link/chain glyph.
  - `user_imported` — `{color.ink.secondary}` label, ink-bordered inbox icon.
  - `crawled_html` — Small `color.warn.amber` warning triangle. One-time "Why does this show ⚠?" tooltip on first view per user per event.
  - Always inline on the card (top-right zone, in the trust-signal row with `Indicator.Confidence`), never behind a tap. Every variant includes a visible inline text label, not icon-only (WCAG 1.1.1).
```

### The "never behind a tap" rule (Do/Don't) — `DESIGN.md:383`

> | Show the source badge inline on the card, never behind a tap. | Hide source attribution behind a "details" disclosure or modal. |

### Tooltip microcopy contract — `EXPERIENCE.md:116`

> | Source Badge tooltip (on hover/tap of `Badge.Source`) | "Official site. Verified venue." | "Trusted by EventPulse24! 🌟" |

> ⚠️ **Tooltip copy conflict:** `EXPERIENCE.md:116` gives the `official_site` tooltip as *"Official site. Verified venue."* while `EXPERIENCE.md:221` gives it as *"Verified venue or organizer."* Both are in the same doc. `EXPERIENCE.md:735` (screen-reader announcement) uses the L116 wording: `- **Source Badge:** Full label announced, e.g., "Official site. Verified venue."`

### Source badge placement on the card — `EXPERIENCE.md:1029`

> - **Source Badge** (PRD FR-23) — top-right of card. Visible inline label (`Official`, `Community`, `Listing site`, `Forwarded`, or warning triangle for `crawled_html`).

### Source roster governance — `EXPERIENCE.md:1197` (ASSUM-9)

> - **ASSUM-9.** _Derived from §4 `Badge.Source`._ Tooltip text per source variant (`official_site`, `community`, `aggregator`, `user_imported`, `crawled_html`) is locked in §4 — `Tooltip.Source` is approved microcopy. No additional source types are accepted without a Trust Review pass; if the source roster grows, the variant list in §4 must be updated and reviewed.
>   - Status: OPEN. Owner: design. Decision deadline: before source ingestion pipeline ships.

### Terracotta "Official" label — `DESIGN.md:64`

> - `color.accent.terracotta` — `#FF6A47`. Single warm accent. Glow-lifted from the light-mode `#C4502B` for dark contrast. Used only for: the `Indicator.Today` dot, the `Button.Primary` fill, the `Badge.Source.verified` fill, and the focus ring (the fourth sanctioned use — see §Color usage rules). Nothing else. The CSS-rendered glow on the `Indicator.Today` dot uses `box-shadow: 0 0 12px rgba(255,106,71,0.55)` — the only sanctioned CSS-rendered glow on system elements. The brand-mark PNG carries its own halo as a brand-asset artifact (Amendment A-9 — see §Color usage rules → Glow); that halo is not part of this token.

---

## 4. The terracotta rationing rule — the four sanctioned uses

### `DESIGN.md:99-111` — `### Color usage rules` (verbatim, complete section)

```
### Color usage rules

- `color.accent.terracotta` is the only chromatic accent. Its **four sanctioned uses** are the today indicator, the primary CTA, the verified source badge, and the focus ring. It does not appear on hover, link underlines, category stripes, or anywhere else.
- **Glow (dark only).** The terracotta `Indicator.Today` dot and the CSS-rendered brand-mark dot fallback carry a soft glow: `box-shadow: 0 0 12px rgba(255,106,71,0.55)` (dot), `0 0 14px rgba(255,106,71,0.55)` (brand-mark dot). This is the only sanctioned use of CSS-rendered glow in the system. It applies only to dark mode; light mode has no glow. **The two CSS-rendered elements above are the complete list.** No other element carries a CSS-rendered glow — not eyebrow glyphs, not status or notification dots, not focus rings (which use solid stroke, not glow), not hover affordances, not decorative dots.
- **Brand-asset halo carve-out (Amendment A-9).** The shipped brand-mark asset `mockups/EventPulse24-latest-logo.png` (production source `docs/EventPulse24-latest-logo.png`) contains a near-black halo with a thin red rim that renders inside the PNG itself. This halo is **a brand-asset artifact, not a CSS-rendered glow**: it ships baked into the PNG, has no token, and is exempt from the glow rationing rule above. The two CSS-rendered glows (`Indicator.Today` dot + the legacy CSS dot+wordmark fallback used when the PNG is unavailable) remain the only sanctioned CSS glows. **Engineering must not (a) re-render the halo in CSS to "match" it, (b) attempt to crop, mask, or normalize the PNG halo to the 14px envelope, (c) add a `box-shadow` on `.brand-logo` to "extend" or "boost" the halo, or (d) introduce a halo on any other surface in the product.** When the PNG is rendered at the canonical 36×36 (pre-auth + authed topbar) the halo is small enough to coexist with the void aesthetic; rendering the PNG at sizes above 40×40 in-product is forbidden until halo dominance is re-evaluated. The brand-deck halo is the brand's decision; the in-product CSS token system does not own it. See `EXPERIENCE.md §4 Component.Topbar.PreAuth` for the pre-auth rendering context and the rationale.
- **Focus ring (exception, fourth sanctioned use).** The 2px focus ring at 2px offset on focusable interactive elements uses `color.accent.terracotta`. WCAG 2.2 focus-visible is required, and terracotta is the highest-contrast chromatic signal we own; AA contrast (≥3:1 against `color.surface.paper`) is verified for the ring stroke in both modes. There is no other chromatic focus ring in the system.
- `color.accent.slate` and `color.accent.amber` are reserved exclusively for category stripes on `Card.PulseDigest`. They are not used for buttons, icons, or interactive surfaces. `color.accent.slate` and `color.cool.public` are interchangeable path aliases for the same token; either name is accepted.
- `color.warm.personal` is reserved exclusively for the Personal-event tone on `Card.PulseDigest` and Detail Screen (a small accent strip or label). It is always paired with the visible text label "Personal" so color is never the sole carrier of meaning (WCAG 1.4.1).
- **Stripe color is never the sole carrier of meaning.** When any category stripe (`color.accent.slate`, `color.accent.amber`, `color.cool.public`, `color.warm.personal`, `color.warn.amber`) appears on a card or in a card grid, it must be paired with (a) a visible text label on the card itself (e.g., "Public event", "Must-know", "Personal") and (b) a legend on the surface where the stripe first appears to a visitor (e.g., the Pulse Preview header before the card grid). Stripes may not stand alone as the only signal of category. (WCAG 1.4.1.)
- `color.warn.amber` is reserved exclusively for the conflict indicator (filled circle mark on `Card.PulseDigest` and Detail Screen header, per PRD FR-58). It is distinct from `color.accent.amber` (warm-secondary category stripe) — do not substitute one for the other.
- `color.signal.success`, `color.signal.warn`, and `color.signal.error` are signal colors, not brand colors. They appear only at the moment of state change, never as decoration.
- `color.ink.faint` is reserved for empty `Indicator.Confidence` dot placeholders, the skeleton pulse animation's dim target, and the handle bar on mobile bottom sheets. Never used for body copy or interactive affordances.
- `color.surface.paper.darker` is reserved for `Card.PulseDigest` hover background and the skeleton pulse animation's resting frame. Never used as a static surface or as a hover state on non-card elements.
```

### The four uses — enumerated in `DESIGN.md:381` (Do/Don't table, row 1)

> | Use `color.accent.terracotta` only for the today indicator, the primary CTA, the verified source badge, and the focus ring (the one sanctioned exception — see §Color usage rules). | Use terracotta on hover states, link underlines, category stripes, or anywhere else outside the four sanctioned uses. |

### `DESIGN.md:39` (anti-pattern list)

> - No chromatic accents outside the four sanctioned uses (today dot, primary CTA, verified badge, focus ring).

### `DESIGN.md:27` (brand posture)

> The aesthetic reads like a precision instrument: dense information earns its keep, type is generous, accent color is rationed, surfaces carry depth through tonal layering (paper → elevated → subtle → inset), and motion is reduced to a single 240ms fade. The terracotta dot on today's date, the terracotta primary CTA, the terracotta focus ring — that's where the warmth lives. Everything else is ink on void.

### 👉 Direct answer to your question

**Yes — both the "Official" source badge and the focus ring ARE among the four sanctioned terracotta uses.** The four are:

| # | Sanctioned use | Where specified |
|---|---|---|
| 1 | The **today indicator** (`Indicator.Today` dot) | `DESIGN.md:101`, `DESIGN.md:64`, `DESIGN.md:309` |
| 2 | The **primary CTA** (`Button.Primary` fill) | `DESIGN.md:101`, `DESIGN.md:64`, `DESIGN.md:267` |
| 3 | The **verified source badge** (`Badge.Source.official_site` — "Official") | `DESIGN.md:101`, `DESIGN.md:64`, `DESIGN.md:302` |
| 4 | The **focus ring** (2px, 2px offset) | `DESIGN.md:101`, `DESIGN.md:104`, `DESIGN.md:64` |

`DESIGN.md:302` confirms the source-badge case explicitly:
> - `official_site` — `color.accent.terracotta` label, terracotta-filled checkmark icon. One of the four sanctioned terracotta uses. The only one that appears on a card body besides the `Indicator.Today` dot.

Note: `DESIGN.md:64` names use #3 as the **`Badge.Source.verified` fill**, while `DESIGN.md:302` names the same use as **`official_site`**. The variant is `official_site` in both docs' variant lists (`DESIGN.md:301-306`, `EXPERIENCE.md:219-225`); "verified" is a legacy alias for it.

`EXPERIENCE.md:1135`:
> - `color.accent.terracotta` — primary accent (CTAs, focus ring, filled Source Badge).

---

## 5. The stripe rules

### Stripe anatomy & mapping — `DESIGN.md:293-297` (quoted in §1 above)

- 3px left-edge category stripe.
- public → `{color.accent.slate}`
- must-know → `{color.accent.amber}`
- personal → `{color.warm.personal}`
- discovery → `{color.accent.slate}` at **0.85 opacity** + a `discovery` micro-tag in the micro-tag row

### "Discovery" opacity 0.85 & micro-tag — `DESIGN.md:297`

> - `component.card.pulse.digest.category.discovery` — Variant with `{color.accent.slate}` left stripe at 0.85 opacity plus a `discovery` micro-tag in the micro-tag row.

### The pairing rule (WCAG 1.4.1) — `DESIGN.md:107`

> - **Stripe color is never the sole carrier of meaning.** When any category stripe (`color.accent.slate`, `color.accent.amber`, `color.cool.public`, `color.warm.personal`, `color.warn.amber`) appears on a card or in a card grid, it must be paired with (a) a visible text label on the card itself (e.g., "Public event", "Must-know", "Personal") and (b) a legend on the surface where the stripe first appears to a visitor (e.g., the Pulse Preview header before the card grid). Stripes may not stand alone as the only signal of category. (WCAG 1.4.1.)

### The Do/Don't row naming the exact visible labels — `DESIGN.md:385`

> | Use `{color.accent.slate}`, `{color.accent.amber}`, and `{color.warm.personal}` exclusively for category stripes on `Card.PulseDigest`. Always pair with the visible text label ("Public event", "Must-know", "Personal"). | Use slate, amber, or warm-personal on buttons, icons, or interactive surfaces. |

### Colour reservations for the stripe colours — `DESIGN.md:65-66`, `DESIGN.md:105-106`

> - `color.accent.slate` — `#6E7E92`. Cool secondary. Used only for: the public-event category stripe on `Card.PulseDigest`, the serendipity / discovery card category stripe. No other use.
> - `color.accent.amber` — `#E89B4A`. Warm secondary, distinct from terracotta. Used only for: the must-know card category stripe on `Card.PulseDigest`. Used sparingly; should not appear on more than ~10% of cards in any view.

> - `color.accent.slate` and `color.accent.amber` are reserved exclusively for category stripes on `Card.PulseDigest`. They are not used for buttons, icons, or interactive surfaces. `color.accent.slate` and `color.cool.public` are interchangeable path aliases for the same token; either name is accepted.
> - `color.warm.personal` is reserved exclusively for the Personal-event tone on `Card.PulseDigest` and Detail Screen (a small accent strip or label). It is always paired with the visible text label "Personal" so color is never the sole carrier of meaning (WCAG 1.4.1).

`DESIGN.md:61-62`:
> - `color.warm.personal` — `#C8967A`. The warm tone reserved for Personal events on `Card.PulseDigest` and the Detail Screen. Used only as an accent strip or small label, paired with the visible text label "Personal" (PRD §13.1) so color is never the sole carrier of meaning.
> - `color.cool.public` — `#6E7E92`. Path alias of `color.accent.slate` (dark variant); both names accepted. Reserved for the public-event tone on `Card.PulseDigest` and Detail Screen; paired with the text label "Public event."

### The must-know frequency cap — `DESIGN.md:295`

> - `component.card.pulse.digest.category.mustknow` — Variant with `{color.accent.amber}` left stripe. Should appear on fewer than ~10% of cards in any given view.

### The personal label — `DESIGN.md:296`

> - `component.card.pulse.digest.category.personal` — Variant with `{color.warm.personal}` left stripe. Always paired with the visible text label "Personal."

### Non-color signal rule — `EXPERIENCE.md:723`

> - Pulse Card warm/cool tone (Personal vs Public): accompanied by text label "Personal" / "Public event" in `Text.Meta`.

### Timeline mirror rule — `DESIGN.md:402`

> | Pair every category stripe (`color.warm.personal`, `color.cool.public`, `color.warn.amber`) on `component.timeline.event-block` with a visible text label in the top-right corner ("Personal" / "Public event"). | Use category stripe color as the sole carrier of meaning on Timeline event-blocks. WCAG 1.4.1 — color is never the only signal. |

### Browse surface stripe cap (A-12) — `DESIGN.md:356-359`, `DESIGN.md:364`

> ```
> **Stripes — explicit cap of 2 (Amendment A-12):**
> - `public` → `{color.accent.slate}` (default for all public events)
> - `must-know` → `{color.accent.amber}` (max 1 per page, the existing <10% rule)
> - **`discovery` → dropped.** The discovery vocabulary on `mockups/city-page-desktop.html` is pre-auth SEO framing and does not migrate to the authed Browse surface. Three stripe colors would create a category-color flood that violates the anti-pattern list. Documented carve-out: city-page's `<span class="stripe discovery"></span>` markup does NOT translate to the Browse surface.
> ```

> - **No category-color floods.** No more than 2 stripe colors per page (slate + amber at the existing <10% rule). **No discovery stripe** (Amendment A-12 lock).

`EXPERIENCE.md:355`:
> - **Stripes — explicit cap (Amendment A-12):** Two colors only: `color.accent.slate` for public events, `color.accent.amber` for must-know events (max 1 per page, the existing <10% rule). **Discovery stripe dropped** — the discovery vocabulary on `city-page-desktop.html` is pre-auth SEO framing and does not migrate. Three stripe colors would create a category-color flood that violates the anti-pattern list.

`EXPERIENCE.md:359`:
>   - No category-color floods. **No discovery stripe (Amendment A-12 lock).** No more than 2 stripe colors per page (slate + amber at the existing <10% rule).

**Scope:** the A-12 drop applies to **Browse only**. The digest keeps all treatments — `frontend-pulse-card.md:42`: *"Amendment A-12 caps Browse at 2 stripe colors and drops discovery **there only** — the digest keeps all three treatments. Don't let a future Browse constraint leak backwards into this component."*

---

## 6. The Why-this Tag rules

### Type scale — `DESIGN.md:152`

> - `type.scale.microtag` — 13px / 1.40 / 400 italic / body. The "nearby · tonight · music" inline italic micro-tags.

### Text role — `DESIGN.md:263`

> - `component.text.microtag` — `{type.scale.microtag}` (italic), `{type.family.body}`, `{color.ink.muted}`. The "nearby · tonight · music" inline editorial tags.

### Italic reservation & bold-italic ban — `DESIGN.md:174`

> Italic is reserved for the `type.scale.microtag` token. Italic is the language of the "why this?" hint — it is conversational, never emphatic. Bold italic is not used.

### Do/Don't — `DESIGN.md:382`

> | Use italic micro-tags inline (`nearby · tonight · music`) via `type.scale.microtag`. | Set micro-tags in regular weight or in the display font. |

### Max 3 & the tags-are-first-class rule — `EXPERIENCE.md:177`, `EXPERIENCE.md:1031`, `EXPERIENCE.md:146`

> A single Pulse Card on the home surface. Always shows: event name, time, location, **up to 3 Why-this Tags**, 1–5 dot Confidence Pulse, Source Badge (PRD FR-6).

> - **Why-this Tags** (PRD FR-21) — below the event name. Up to 3 keywords in `Text.Meta` ink color, comma-separated.

> **Why-this Tags are first-class.** A Why-this Tag is the smallest unit of trust. The exact three keywords on a Pulse Card are repeated on the Detail Screen (PRD §4.6 FR-21). The tags use sentence-case nouns and short verb-free phrases (`nearby, tonight, music` not `you might enjoy this because it is nearby and tonight and music`).

`EXPERIENCE.md:106`:
> - Why-this Tags are first-class — they are the voice of the product.

### The separator question — middle dot vs comma

**DESIGN.md:293** says middle dots:
> - `component.card.pulse.digest` — … a `{type.scale.microtag}` row of inline italic tags **separated by middle dots**, …

**EXPERIENCE.md:115** (§3 microcopy table) also shows middle dots in the "Do" cell, but calls them comma-separated in the row label:
> | Why-this Tag (max 3 keywords, comma-separated) | "nearby · tonight · music" | "Within walking distance and a perfect acoustic match for your refined taste!" |

**EXPERIENCE.md:1031** says comma-separated:
> - **Why-this Tags** (PRD FR-21) — below the event name. Up to 3 keywords in `Text.Meta` ink color, comma-separated.

**EXPERIENCE.md:736** (screen reader) says comma-separated:
> - **Why-this Tags:** Announced as comma-separated text: "nearby, tonight, music."

`DESIGN.md:152`, `DESIGN.md:263`, `DESIGN.md:382` all show the middle dot in the sample: `nearby · tonight · music`.

**The conflict is real and unresolved in the sources.** The brief records it explicitly — `.specs-fire/intents/pulse-digest-and-trust/brief.md:114`:
> - **Why-this tag separator is undecided** in the sources — DESIGN.md says middle dots, EXPERIENCE.md §3 says commas, and the two mockups disagree. The screen-reader rule ("announced as comma-separated text") settles the accessible reading; the visual separator is a plan-time decision to be recorded.

The work item's instruction — `frontend-pulse-card.md:26`:
> Screen readers announce them as **comma-separated text**. The visual separator (middle dot vs comma) is unresolved across the sources — pick one, apply it everywhere, and record the choice.

### How screen readers announce them

`EXPERIENCE.md:736`:
> - **Why-this Tags:** Announced as comma-separated text: "nearby, tonight, music."

`EXPERIENCE.md:724`:
> - Why-this Tags: each tag is a visible keyword, not a colored dot.

---

## 7. The Conflict indicator

### `DESIGN.md:310` (verbatim)

> - `component.indicator.conflict` — A 6px filled circle in `{color.warn.amber}` (PRD FR-58). Top-right of the affected Pulse Card, symmetric across the conflict pair. Distinct in shape and position from the Source Badge and Confidence Pulse. `aria-label="Schedule conflict"`. Never red. Size is consistent across Pulse Cards and Timeline event-blocks — see `component.timeline.event-block` below for the Timeline variant.

### `EXPERIENCE.md:1115` (never collapses below 6×6px)

> If a card is in conflict (PRD FR-58), the conflict indicator is always visible — top-right of the card, in the same visual zone as Source Badge and Confidence Pulse. Adaptive density may add detail (e.g., a tooltip on the conflict indicator explaining the conflict), but the indicator itself never collapses below 6×6 px (the locked size for both Pulse Cards and Timeline event-blocks per `DESIGN.md` `component.indicator.conflict`).

### `EXPERIENCE.md:721` (non-color signal)

> - Conflict indicator (PRD FR-58): filled circle in `color.warn.amber` *and* `aria-label="Schedule conflict"`. Shape distinct from Source Badge and Confidence Pulse dots.

### `EXPERIENCE.md:1113` (heading)

> ### Anti-pattern: progressive disclosure that hides the conflict indicator

### Why never red — `DESIGN.md:63`, `DESIGN.md:108`, `EXPERIENCE.md:239`

> - `color.warn.amber` — `#D8A86A`. Muted amber reserved for the conflict indicator (filled circle, PRD FR-58). Distinct from `color.accent.amber`, which is a warm-secondary category stripe. Used only at the moment of state change (conflict active) and as a static indicator mark on a card or detail screen header; never as decoration. **On dark, never red.**

> - `color.warn.amber` is reserved exclusively for the conflict indicator (filled circle mark on `Card.PulseDigest` and Detail Screen header, per PRD FR-58). It is distinct from `color.accent.amber` (warm-secondary category stripe) — do not substitute one for the other.

>   - Mobile: bottom-anchored sheet (`component.surface.sheet`) with the same three-action body. The modal header uses an amber-circle exclamation glyph (`color.warn.amber`) — never red.

The rationale for amber-not-red is in `DESIGN.md:38`:
> - No drop shadows used for hover lift on dark surfaces (use border-color transition, not elevation).

…and `DESIGN.md:23`:
> It is deliberately **anti-Eventbrite** — anti the bright badges, the social-proof counters, the upsell carousel, the loud category tinting, the streak popup.

The "never red" rationale is also anchored by `DESIGN.md:31`:
> - No notification badges (red dots, unread counters).

### `DESIGN.md:325` (Timeline variant)

> Conflict indicator: 6px filled circle in `{color.warn.amber}` at the top-right corner of the block, mirroring `component.indicator.conflict` on Pulse Cards. `aria-label="Schedule conflict"`. Reduced motion: no fade-in on mount.

### `EXPERIENCE.md:244` (persistence)

> - **Persistence:** Once a choice is recorded for a conflict pair, the system never re-prompts. The `ConflictResolution` value object lives with the user-event pair. The `Indicator.Conflict` on each Pulse Card persists permanently after "Keep both" as a calm permanent reminder (per PRD §3 Glossary — *Conflict Indicator* entry).

---

## 8. Motion

### `motion.fadeIn` — `DESIGN.md:123` (verbatim, complete bullet)

> - **Motion — `motion.fadeIn`.** A 240ms CSS `opacity` transition (no transform, no translate). Implementation is a single class toggled by the framework: `.fade-in { transition: opacity 240ms ease-out; }` plus `opacity: 0` → `opacity: 1`. Under `@media (prefers-reduced-motion: reduce)`, the class becomes `transition: none`. There is no JS animation library. Skeleton pulse animation is a CSS `@keyframes` between `color.surface.elevated` and `color.surface.inset` (dark) or `color.surface.paper` and `color.ink.faint` (light), 1800ms period, also collapsing to a static frame under reduced-motion.

### "Only one transition" — `DESIGN.md:27`

> … and motion is reduced to a single 240ms fade.

### No animation library — `DESIGN.md:115`, `DESIGN.md:123`, `DESIGN.md:125`, `EXPERIENCE.md:27`

> The visual identity in this document is the source of truth; this subsection specifies the build substrate so engineering does not reach for a UI library, a tooltip framework, or an animation library to implement it.

> There is no JS animation library. (see above)

> - **No UI framework.** "UI system: None" (see `EXPERIENCE.md` §1) is binding: vanilla web components plus the token layer above. No Material, no shadcn, no full kit. The tooltip pattern is hand-rolled per the rule above; the modal pattern is a single overlay level using `<dialog>` native element; the sheet pattern uses `<dialog>` with `bottom` anchoring on mobile only.

> **UI system:** None — vanilla web components plus a thin token layer defined in `DESIGN.md.{Tokens}`. We do not adopt Material, shadcn, or a full kit; the surface vocabulary is small and bespoke. Headline typography is `Text.Display`; body is `Text.Body`; metadata is `Text.Meta`.

### Reduced motion — `EXPERIENCE.md:680-688` (verbatim, complete)

```
### Reduced Motion

`prefers-reduced-motion: reduce` disables:
- Card-fade entrance animation.
- Card swipe animations.
- Skeleton pulse animation (skeletons render statically).
- Tooltip fade.

Text and layout remain unchanged. The product does not become a wall of static — it just doesn't animate.
```

### `EXPERIENCE.md:740-744` (Motion, §7 Accessibility Floor)

```
### Motion

- `prefers-reduced-motion: reduce` disables non-essential animation (see §6 Reduced Motion).
- No auto-playing video or audio at MVP.
- All transitions ≤500ms; default 240ms.
```

### `EXPERIENCE.md:186` (card-level reduced motion)

> - **Reduced motion:** All swipe animations collapse to instant transition with no fade. (See §7 Interaction Primitives.)

### `EXPERIENCE.md:1069`

> Each factor has a tooltip explaining what it means. The expansion uses `motion.fadeIn` (240ms, disabled under reduced-motion).

### `EXPERIENCE.md:1157`

> - `motion.fadeIn` — 240ms entrance transition (disabled under reduced-motion).

---

## 9. Density / trust signals

### `EXPERIENCE.md:1109-1115` (verbatim, complete)

```
### Anti-pattern: progressive disclosure that hides trust signals

Adaptive density must not hide the trust signals (Why-this Tags, Confidence Pulse, Source Badge) at any density mode. The mobile default exposes all three; hover/focus/long-press *add* detail but never *remove* the trust signals. PRD §13.1: "Why-this Tags are first-class."

### Anti-pattern: progressive disclosure that hides the conflict indicator

If a card is in conflict (PRD FR-58), the conflict indicator is always visible — top-right of the card, in the same visual zone as Source Badge and Confidence Pulse. Adaptive density may add detail (e.g., a tooltip on the conflict indicator explaining the conflict), but the indicator itself never collapses below 6×6 px (the locked size for both Pulse Cards and Timeline event-blocks per `DESIGN.md` `component.indicator.conflict`).
```

### `EXPERIENCE.md:1085-1107` (§13 Adaptive Density — verbatim, complete)

```
## 13. Adaptive Density

The principle: cards reveal more detail on long-press, focus, or desktop hover. Mobile default is intentionally spartan. The default mobile view of `Card.PulseDigest` shows only:

- Event name (`Text.Display.sm`)
- When · Where (`Text.Meta`)
- 3 Why-this Tags (`Text.Meta`)
- 1 Confidence Pulse (top-right)
- 1 Source Badge (top-right)

That's it. No description, no image, no map, no price, no attendee count, no share button. The mobile default is the *decision surface*, not the *browsing surface*.

### Density Modes

| Mode | Trigger | Adds |
|---|---|---|
| **Default (mobile, idle)** | Always | Name, When · Where, 3 Why-this Tags, Confidence, Source |
| **Focused (keyboard)** | Tab focus on the card | Visible focus ring (2px, terracotta). `aria-label` exposes full card content to screen readers. |
| **Hovered (desktop)** | Mouse hover | Background shifts to `color.surface.paper.darker`. `▸` affordance appears. Tooltips available on Source Badge and Confidence Pulse. |
| **Long-pressed (mobile)** | Long-press on card | Quick-actions sheet anchored to card: Save, Dismiss, Less like this. |
| **Adaptive expansion** | ≥10 saves in 30d | Card count grows from 3 to 5 (top of the responsive matrix) or 7 (Phase 3 max). Inline "Show all 5" link below the last card. |
| **Default (Timeline event-block, mobile)** | Always | Event name, time, "Personal" / "Public event" label, conflict indicator if active |
| **Hovered / focused (Timeline event-block, desktop)** | Mouse hover or Tab focus | Adds location (`Text.Meta`) and 1 Why-this Tag (read-only at MVP — full Why-this breakdown expansion is on Detail Screen, never on Timeline). |
```

### `EXPERIENCE.md:1117-1127` (verbatim, complete)

```
### Desktop Hover Discipline

On desktop (`md+`), hover affordances are *additions*, not requirements. A user with a mouse and a user with a touchscreen get the same default; hover only adds detail. Per `DESIGN.md.Do's-and-Dont's` (per the locked brief), the desktop view is "whitespace and hover-revealed detail" — not "more features."

### What Adaptive Density Does Not Do

- Does not change the 3-card discipline (except via the explicit adaptive exception).
- Does not introduce infinite scroll.
- Does not introduce a carousel.
- Does not reorder cards based on engagement signal — card composition is determined by Pulse Digest logic (PRD FR-5), not by per-card density.
- Does not introduce paywalled density tiers ("Upgrade to Pro for full event descriptions").
```

### `EXPERIENCE.md:1021-1033` (§12 Trust Signals as First-Class Surface — verbatim, complete)

```
## 12. Trust Signals as First-Class Surface

The "Why this?" pattern is the heart of the product. PRD §4.6 (FR-21–24) makes trust signals an MVP requirement; this section ratifies the *first-class surface* posture — trust signals are not hidden, not behind a tap on the card alone, but elevated in the design language.

### On the Pulse Card (home surface)

Every `Card.PulseDigest` carries these trust signals inline, without an extra tap:

- **Source Badge** (PRD FR-23) — top-right of card. Visible inline label (`Official`, `Community`, `Listing site`, `Forwarded`, or warning triangle for `crawled_html`).
- **Confidence Pulse** (PRD FR-22) — top-right of card, immediately left of Source Badge. 1–5 dots. `aria-label="4 of 5"` for screen readers.
- **Why-this Tags** (PRD FR-21) — below the event name. Up to 3 keywords in `Text.Meta` ink color, comma-separated.

The trust signals are *visible*, not behind a tap. PRD §13.1: "Why-this Tags are first-class." Design Thinking §Next Steps #7: "Inline trust beats click-to-reveal." The rationale is locked.
```

### `EXPERIENCE.md:955` (desktop adds no features)

> - **Desktop does not add features.** Desktop adds whitespace and (optionally) reveals hover affordances on `Badge.Source` and `Indicator.Confidence`. No new screens, no new actions, no new copy. PRD §13.1: "Whitespace over density."

---

## 10. Interaction

### Whole-card tap target + `▸` — `EXPERIENCE.md:180-181`

> - **Hover (desktop only):** Background shifts to `color.surface.paper.darker` (a 1-step paper-darker variant). A small `▸` affordance appears at the trailing edge, indicating the card is tappable to open Detail. The `▸` is **decorative information about tappability, not a click target of its own** — the entire card remains the tap target. The same `▸` affordance is shown on mobile when the card is in any focused or long-pressed state (keyboard focus, Switch Control focus, Touch & Hold), so the desktop hover cue has a mobile equivalent and §6 "No hover-only affordances on `sm` viewports" is honored. The `▸` is rendered with `aria-hidden="true"` (decorative) and the full tap target is announced via the card's `aria-label`.
> - **Tap:** Opens `/events/:id`.

### Focus ring (2px terracotta) + aria-label — `EXPERIENCE.md:185`

> - **Focus state (keyboard):** Visible 2px focus ring in `color.accent.terracotta` at AA contrast against `color.surface.paper`. `aria-label` reads the full card content.

### Focus spec — `EXPERIENCE.md:710-716` (verbatim, complete)

```
### Focus

- Visible 2px focus ring on every focusable element.
- Ring color: `color.accent.terracotta`.
- Ring offset: 2 px from the element edge.
- Focus order matches reading order on every surface.
- `Esc` closes the topmost modal/popover; `Tab` from inside a closed modal returns focus to the trigger.
```

### `DESIGN.md:104`

> - **Focus ring (exception, fourth sanctioned use).** The 2px focus ring at 2px offset on focusable interactive elements uses `color.accent.terracotta`. WCAG 2.2 focus-visible is required, and terracotta is the highest-contrast chromatic signal we own; AA contrast (≥3:1 against `color.surface.paper`) is verified for the ring stroke in both modes. There is no other chromatic focus ring in the system.

### ≥44×44 tap target — `EXPERIENCE.md:704-708` (verbatim, complete)

```
### Touch & Click Targets

- All interactive elements ≥44×44 px CSS.
- Card-level targets wrap the entire card; subordinate buttons inside cards are themselves ≥44×44.
- Spacing between adjacent targets ≥8 px to prevent mis-tap.
```

### Single Tab cycle / keyboard — `EXPERIENCE.md:648`

> **Cards are focusable.** Arrow keys (and `j`/`k`) move between cards in the digest. Focus is visible at AA contrast (2px ring, `color.accent.terracotta`).

`EXPERIENCE.md:632-633` (keyboard shortcut table):
> | `j` / `k` | Move to next / previous card | `/` (Pulse Digest) |
> | `Enter` | Open Detail on focused card | `/` |

> ⚠️ **Note:** "single Tab cycle" is **not** a literal phrase in either spine. The nearest anchors are `EXPERIENCE.md:185` ("`aria-label` reads the full card content"), `EXPERIENCE.md:1102` ("**Focused (keyboard)** | Tab focus on the card | Visible focus ring (2px, terracotta). `aria-label` exposes full card content to screen readers.") and `EXPERIENCE.md:715` ("Focus order matches reading order on every surface."). The single-Tab-cycle requirement comes from the work item — `frontend-pulse-card.md:31`: *"…reachable in a **single Tab cycle**; tap targets are **≥44×44 CSS px**."*

### Touch / mouse primitives — `EXPERIENCE.md:654-667` (verbatim, complete)

```
### Touch

- **Tap** — primary action.
- **Long-press** — opens quick-actions sheet on a Pulse Card (save, dismiss, less like this). Long-press is reserved for system context menus on iOS (text selection) on text content; on cards it's ours.
- **Swipe-left** — dismiss (records "less like this").
- **Swipe-right** — save.
- **Swipe-down** — refresh on the Pulse Digest only.
- **Pull-to-refresh** is disabled on all surfaces except `/`. PRD: no infinite scroll, no carousel-driven browsing.

### Mouse

- **Click** — primary action.
- **Hover** — reveals secondary affordances (Confidence tooltip, Source Badge tooltip). Hover affordances are duplicated as tap-on-mobile. No hover-only affordances on `sm` viewports.
- **Drag** — supported on Reminder Slot chips only.
```

### Banned primitives — `EXPERIENCE.md:669-678`

> ```
> ### Banned Primitives
>
> These are explicitly out of scope in MVP:
> - Infinite scroll (pagination only).
> - Drag-to-reorder lists (deferred to Phase 2 for Saved Collections).
> - Hover-only affordances on `sm` viewports.
> - Modal stacks > 1 level deep.
> - Full-screen takeover animations.
> - Carousels (Pulse Digest is a stack, not a carousel).
> - Bottom-sheet on a modal (one level of overlay only).
> ```

---

## 11. The headline rule

### `DESIGN.md:293` (the anatomy bullet)

> - `component.card.pulse.digest` — The signature editorial card. Anatomy, top-to-bottom: a 3px left-edge category stripe (`{color.accent.slate}` for public events, `{color.accent.amber}` for must-know, `{color.warm.personal}` for personal events), a `{type.scale.meta.sm}` kicker label in `{color.ink.muted}`, a `{type.scale.headline.md}` headline in `{color.ink.primary}` (**max 8 words**), a `{type.scale.microtag}` row of inline italic tags separated by middle dots, a `{type.scale.meta.md}` source-and-time row, and the `component.indicator.confidence` row at the bottom. Sits on `component.surface.card`. The conflict indicator (8px filled amber circle, top-right) renders independently when active.

### `DESIGN.md:145` — the 22px value

> - `type.scale.headline.md` — 22px / 1.25 / 600 / display. Card headlines on `Card.PulseDigest`.

### `DESIGN.md:260` — the text role

> - `component.text.headline` — `{type.scale.headline.md}`, `{type.family.display}`, `{color.ink.primary}`. Card titles, section openers.

### `DESIGN.md:384` — the Do/Don't

> | Keep card headlines to 8 words or fewer. | Wrap a long sentence as a card headline; that is body copy, not a headline. |

> ⚠️ **Type-role conflict:** `DESIGN.md:293` says the headline uses `type.scale.headline.md`; `EXPERIENCE.md:179` says *"headline `Text.Display.sm`"*. `DESIGN.md` owns visual type scale, so `headline.md` (22px) governs the token; `EXPERIENCE.md`'s `Text.Display.sm` is its own role vocabulary (26px per `DESIGN.md:354`). The work item picks `type.scale.headline.md` — `frontend-pulse-card.md:22`: *"a `type.scale.headline.md` headline (22px, **max 8 words**) in `color.ink.primary`"*.

### Browse variant (different sizing, different surface) — `DESIGN.md:354`

> **Cards:** `component.card.pulse.digest` anatomy + city-page sizing. Same `{color.surface.elevated}` fill, 1px `{color.border.subtle}` stroke, `{radius.card}` (12px) corners, 3px left stripe, headline + why-tags + source-and-time + confidence indicator structure. Sizing tweaks for the denser grid: **22px padding** (down from A-10's 24px), **18px headline** (down from 22px for legibility at narrower grid widths), **gap: 20px** replaces the A-10 `margin-bottom: 12px` vertical rhythm.

---

## 12. The container

### `DESIGN.md:253` (verbatim — the container entry)

> - `component.surface.card` — The `Card.PulseDigest` container. `{color.surface.elevated}` fill, 1px `{color.border.subtle}` stroke, `{radius.card}` (12px) corner radius. Padding `{spacing.6}` (24px) on desktop, `{spacing.4}` (16px) on mobile. Hover swaps the fill to `{color.surface.subtle}` (desktop) and transitions the border to `{color.border.strong}` (mobile). **No shadow is ever added.**

### `DESIGN.md:234` — `radius.card`

> - `radius.card` — 12px. Cards, sheets, list rows that need their own edge. (Bumped from 8px in the prior light-mode spec — darker surfaces need slightly more rounding to feel intentional rather than abrupt.)

### `DESIGN.md:187` — `spacing.6`

> - `spacing.6` — 24px.

### `DESIGN.md:199` — `layout.card.spacing.mobile`

> - `layout.card.spacing.mobile` — `{spacing.4}` (16px). Vertical gap between cards on mobile.

### Hover: border or background shift only, never a shadow — `DESIGN.md:386`

> | Communicate hover on dark via `color.surface.subtle` fill swap or 1px border transition. | Add a drop-shadow on hover in dark mode. Elevation on dark feels cheap and breaks the void aesthetic. |

### `DESIGN.md:38`

> - No drop shadows used for hover lift on dark surfaces (use border-color transition, not elevation).

### `DESIGN.md:251` — the canvas for contrast

> - `component.surface.canvas` — The full-bleed page background. `{color.surface.paper}` fill, no border, no shadow. The single anchoring surface of the product.

### Surface tokens — `DESIGN.md:51-53`

> - `color.surface.paper` — `#0A0A0B`. Base canvas. Near-pure-black, slightly warm-tinted at the deep end to avoid the flat-blue cast of pure `#000` on OLED. Used for the page background, the dominant surface.
> - `color.surface.elevated` — `#131316`. Cards, sheets, popovers, modal bodies. One step lighter than paper — a faint glow that lifts content off the void without visible shadow.
> - `color.surface.subtle` — `#1B1B1F`. Page-2 backgrounds, dividers, hover affordance on ghost rows, the "no events" empty state fill.

Light mode — `DESIGN.md:77-79`, `DESIGN.md:86`:
> - `color.surface.paper` — `#FAF8F4`. Base canvas — paper, not screen white.
> - `color.surface.elevated` — `#FFFFFF`. Cards and sheets on light.
> - `color.surface.subtle` — `#F1ECE3`. Page-2 backgrounds and dividers.
> - `color.surface.paper.darker` — `#F4F0E8`. Card hover on light.

Border tokens — `DESIGN.md:70-71`:
> - `color.border.subtle` — `rgba(242, 242, 244, 0.08)`. The 1px border on cards and inputs. Ink at 8% opacity.
> - `color.border.strong` — `rgba(242, 242, 244, 0.16)`. Focused-input border, active row in a list.

---

## 13. Relevant EXPERIENCE.md passages

Covered in full above: §4 `Card.PulseDigest` (L176-187), §4 `Indicator.Confidence` (L206-216), §4 `Badge.Source` (L218-226), §6 Interaction Primitives (L621-688), §7 Accessibility Floor (L692-754), §12 Trust Signals (L1021-1079), §13 Adaptive Density (L1085-1127), Appendix token reference (L1131-1162), Assumptions (L1166-1213).

### The four trust signals — `EXPERIENCE.md:38-44` (Locked principles)

```
**Locked principles (PRD §5.1, ratified for behavior):**
- Calm > Engagement — fewer, better notifications. Counter to industry spam.
- Explainable AI — every recommendation shows its reasoning.
- Calendar-sync-in, not replace — extend Google/Apple/Outlook; do not fight OS distribution.
- 3 cards max — with the adaptive exception (5–7 for engaged users, §4.2 of this spine).
- Trust through transparency — Source Badges, Confidence Pulse, no hidden ranking.
- No dark patterns — no urgency badges, no FOMO carousels, no "Don't miss out!" copy.
```

### FR-58 conflict indicator in EXPERIENCE — `EXPERIENCE.md:241`, `L244`, `L721`, `L1115`, ASSUM-12 (`L1206`)

`EXPERIENCE.md:241`:
>   - The two affected events render as small stacked cards with the `Indicator.Conflict` amber dot on each. The new event is marked "NEW" in a terracotta pill above its card (one of the four sanctioned terracotta uses — `Badge.State.New` is a derived use of the verified-badge pattern, justified because it is a state marker on a personal event the system is bringing to the user's attention, not a decorative accent).

`EXPERIENCE.md:1206` (ASSUM-12):
> - **ASSUM-12.** _Locked 2026-09-06 (Amendment A-8 lift)._ `/timeline` at MVP is a **read-only** Week view combining Personal + Public events (Amendment A-8). No edit-from-Timeline, no drag-to-reschedule, no inline conflict resolution on Timeline itself. Edits happen on Detail Screen or the Personal Event modal; conflict resolution happens via the FR-33 three-action pattern on the Detail Screen header panel. The `/conflicts` route is a review surface for conflict pairs the system has recorded (active + resolved) — it does not surface user-added notes. The conflict indicator is a 6px filled amber circle on both Pulse Cards and Timeline event-blocks (`aria-label="Schedule conflict"`) — color is paired with the `Indicator.Conflict` shape so color is never the sole carrier of meaning (WCAG 1.4.1). Both routes are reachable from `Component.BottomTab` (mobile, 5 slots; Conflicts is the 4th slot between Add and Settings) and `Component.Sidenav.App` (desktop md+, Conflicts link between Add and Settings); the topbar stays brand-only (topbar-quiet rule, ASSUM-11).
>   - Status: RESOLVED. Owner: design + engineering. Decision deadline: before token implementation begins.

### Tag rendering rule (Detail Screen) — `EXPERIENCE.md:1043`, `L1047`

> 5. **Why-this Tags** (3 keywords — same as on the card).

> 9. **Why-this breakdown** (expandable) — the human-readable reasoning behind the tags. E.g., "Comedy is in your top 3 categories. Within 2 km of your work. 12 of your neighbors saved this." Each factor on its own line.

### `EXPERIENCE.md:1061-1069`

```
### Why-this Breakdown (the heart)

The Why-this breakdown is the human-readable explanation of why the AI surfaced this event. It expands from the 3 keywords on the card. Example:

> "Surfaced because:
> - Comedy is in your top 3 categories.
> - 2 km from your work.
> - 12 of your neighbors saved this.
> - Source reliability 0.92."

Each factor has a tooltip explaining what it means. The expansion uses `motion.fadeIn` (240ms, disabled under reduced-motion).
```

### Anti-emoji / visible helper text — `EXPERIENCE.md:738`

> - **Visible helper text is in the DOM, not in pseudo-elements.** Helper text that a sighted user reads (e.g., the line under a "Save" button explaining what happens next) is rendered as a real text element in the DOM, not injected via CSS `::before` / `::after`. Screen readers do not announce `::after` content by default; visible-to-sighted, invisible-to-screen-reader is an accessibility regression. If the helper is decoration-only, hide it with `aria-hidden="true"`; if it carries information, render it in the DOM and pair it with the trigger via `aria-describedby`.

---

## 14. ASSUMPTIONS.md — does not exist; assumptions are inline

There is **no `ASSUMPTIONS.md`** anywhere under `_bmad-output/planning-artifacts/`. Assumptions live as an inline `## Assumptions` section at the end of each spine:

- `DESIGN.md:419-461` — `## Assumptions`, entries ASSUM-1 … ASSUM-7.
- `EXPERIENCE.md:1166-1213` — `## Assumptions`, entries ASSUM-1 … ASSUM-14.
- `EXPERIENCE.md:1170`: > **Cross-doc note.** `DESIGN.md` uses the same `ASSUM-N` numbering scheme (currently `ASSUM-1` — hex palette calibration). Future additions to either doc should append to the higher number, not reuse IDs.

**There is no ASSUM-13 in DESIGN.md.** ASSUM-13 exists only in EXPERIENCE.md.

### ASSUM-13 (the conflict indicator size) — `EXPERIENCE.md:1209-1210` (verbatim, complete)

> - **ASSUM-13.** _Locked 2026-09-06 (A-8 lift, FR-58 follow-on)._ The conflict indicator dot is locked at **6px diameter** for both Pulse Cards and Timeline event-blocks (`DESIGN.md` `component.indicator.conflict` and `component.timeline.event-block`). The dot sits at the top-right of the block (Pulse Card) or top-left of the event-block (Timeline) so the Personal/Public text label in the top-right remains visible (WCAG 1.4.1). The size was chosen for Timeline density (matches `Indicator.Confidence` 6px dots on Pulse Cards) and is the same value on Pulse Cards to avoid re-coding two sizes. Density: pulsing glow (`box-shadow: 0 0 6px rgba(216,168,106,0.6)`) is permitted on the dot on dark surfaces to lift it from the page — glow does not appear on the dot in light mode.
>   - Status: RESOLVED. Owner: design + engineering. Decision deadline: before conflict indicator implementation.

### The confidence indicator in the assumptions — `EXPERIENCE.md:1209` (cross-reference)

> … (matches `Indicator.Confidence` 6px dots on Pulse Cards) …

### DESIGN.md ASSUM-7 (conflicts surface on Pulse Cards) — `DESIGN.md:458-461`

> - **ASSUM-7.** _Amendment A-8 (2026-09-06)._ Timeline at MVP is **read-only** — no edit-from-Timeline, no drag-to-reschedule, no inline conflict resolution on Timeline itself. Conflicts surface on Pulse Cards and Timeline event-blocks as `component.indicator.conflict` (6px filled amber circle, `aria-label="Schedule conflict"`); tapping routes to Detail Screen for resolution via the FR-33 three-action pattern. The `/conflicts` route is a review surface for system-recorded conflict pairs (active + resolved) — no user-added notes. Navigation to `/timeline` and `/conflicts` happens from `Component.BottomTab` (mobile `sm`, 5 slots; Conflicts is the 4th slot between Add and Settings) and `Component.Sidenav.App` (desktop `md+`, Conflicts link between Add and Settings). The topbar stays brand-only (topbar-quiet rule, EXPERIENCE.md ASSUM-11). Cross-reference: EXPERIENCE.md ASSUM-12.
>   - Status: RESOLVED
>   - Owner: design + engineering
>   - Affects: §Components → Timeline; §Components → Navigation; §Do's and Don'ts → topbar nav rule; EXPERIENCE.md §4 `Surface.Timeline`, §4 `Component.BottomTab`, §4 `Component.Sidenav.App`

**No assumption entry anywhere mentions the confidence indicator's size, colour, or numeric.** The confidence indicator's governing rules are `DESIGN.md:308` + `EXPERIENCE.md:206-216` (quoted in §2 above), with `EXPERIENCE.md:1209` merely noting the 6px match.

---

## 15. Slot → visible stripe/label mapping

### What the spines actually name

The spines do **not** use the backend slot vocabulary (`must_know`, `nearby`, `serendipity`). They name **card categories / variants**:

| Spine category name | `DESIGN.md` variant key | Stripe token | Visible text label | Source line |
|---|---|---|---|---|
| public | `component.card.pulse.digest.category.public` | `{color.accent.slate}` | **"Public event"** | `DESIGN.md:294`, `DESIGN.md:385`, `DESIGN.md:62`, `EXPERIENCE.md:723` |
| must-know | `component.card.pulse.digest.category.mustknow` | `{color.accent.amber}` | **"Must-know"** | `DESIGN.md:295`, `DESIGN.md:385` |
| personal | `component.card.pulse.digest.category.personal` | `{color.warm.personal}` | **"Personal"** | `DESIGN.md:296`, `DESIGN.md:385`, `DESIGN.md:61`, `EXPERIENCE.md:723` |
| discovery | `component.card.pulse.digest.category.discovery` | `{color.accent.slate}` @ **0.85 opacity** | *no text label named* — a **`discovery` micro-tag** in the micro-tag row | `DESIGN.md:297` |

### The key passage — `DESIGN.md:65` (the slate token names "serendipity / discovery")

> - `color.accent.slate` — `#6E7E92`. Cool secondary. Used only for: the public-event category stripe on `Card.PulseDigest`, **the serendipity / discovery card category stripe**. No other use.

### The category stripe Do row — `DESIGN.md:385` (this is the mapping table)

> | Use `{color.accent.slate}`, `{color.accent.amber}`, and `{color.warm.personal}` exclusively for category stripes on `Card.PulseDigest`. Always pair with the visible text label ("Public event", "Must-know", "Personal"). | Use slate, amber, or warm-personal on buttons, icons, or interactive surfaces. |

### The Timeline mirror (2px stripe, same labels) — `DESIGN.md:325`

> - `component.timeline.event-block` — A single event rendered inside a day cell. `{color.surface.subtle}` resting fill, 1px `{color.border.strong}`… 2px left-edge category stripe (`{color.warm.personal}` for personal events, `{color.cool.public}` for public events), … The "Personal" / "Public event" text label sits in the top-right corner of the block as `{type.scale.meta.sm}` `{color.ink.muted}` — color is never the sole carrier of meaning (WCAG 1.4.1; mirrors the existing Pulse Card category stripe rule).

### The discovery tag (from the PRD, which the spines inherit) — `prd.md:203`, `prd.md:794`

> - **Why-this Tags**: Up to 3 keywords on a Pulse Card explaining *why* the event was surfaced (e.g., `nearby, tonight, music`). Why-this Tags are **category descriptors**, not full explanations; the full reasoning is on the Detail Screen (FR-24). **On Slot 3 (serendipity) cards, the tag reads `discovery` or `new-to-you` instead of a category name (per Amendment A-2 / FR-5).** Same tags appear on the Pulse Card and on the Detail Screen.

> - Why-this Tag on Slot 3 cards reads `discovery` or `new-to-you` (not a category name) to signal the slot's intent.

`prd.md:311`:
> - **Slot 3 ("serendipity")** — `score = source_reliability × geographic_distance_factor × freshness_factor × (1 - normalized_popularity)`. Explicit anti-popularity bias. Restricted to a category distinct from the user's most-engaged category (per Preference Graph; default to "least-engaged category in beachhead" during cold start).

`prd.md:204`:
> - **Confidence Pulse**: A 1–5 dot indicator on each Pulse Card showing AI certainty about relevance. 5 = very strong match; 1 = weak. Persisted on the Event record.

### 👉 Answer: the slot → stripe/label mapping

**The spines never map backend slots to stripes.** The mapping is a composition-time decision the frontend must make. The evidence:

1. **The variant list is by *category*, not by *slot*** — `DESIGN.md:294-297` names `public` / `mustknow` / `personal` / `discovery`.
2. **`discovery` is the spine's name for the serendipity slot** — `DESIGN.md:65` says "the **serendipity / discovery** card category stripe"; `prd.md:203`/`794` say the Slot 3 (serendipity) tag reads `discovery`.
3. **The `event_kind` public/personal distinction maps to the public/personal stripes** — `DESIGN.md:62` (`color.cool.public` … "Reserved for the public-event tone") and `DESIGN.md:61` (`color.warm.personal` … "reserved for Personal events"). `EXPERIENCE.md:723` confirms the card's tone label is "Personal" / "Public event".
4. **`must_know` maps to the must-know stripe** — `DESIGN.md:66`: "`color.accent.amber` … Used only for: the **must-know** card category stripe."

The **spec-sanctioned** reading, consistent with every spine line:

| Backend | Visible label | Stripe | Citation |
|---|---|---|---|
| `must_know` | "Must-know" | `{color.accent.amber}`, <10% of cards | `DESIGN.md:295`, `DESIGN.md:385`, `DESIGN.md:66` |
| `nearby` (public event) | "Public event" | `{color.accent.slate}` | `DESIGN.md:294`, `DESIGN.md:385`, `DESIGN.md:62` |
| `serendipity` | *no stripe label of its own* — `discovery` **micro-tag** | `{color.accent.slate}` at **0.85 opacity** | `DESIGN.md:297`, `DESIGN.md:65`, `prd.md:203` |
| `event_kind = personal` | "Personal" | `{color.warm.personal}` | `DESIGN.md:296`, `DESIGN.md:385`, `DESIGN.md:61` |

> ⚠️ **Two caveats you must carry into implementation:**
>
> **(a) `discovery` has no named visible text label in the spine.** `DESIGN.md:107` requires every stripe to be *"paired with (a) a visible text label on the card itself (e.g., "Public event", "Must-know", "Personal")"*, but `DESIGN.md:297` gives discovery only a `discovery` **micro-tag** (in the micro-tag row, not a stripe label). The `discovery` micro-tag is therefore the de facto visible label. Also note `DESIGN.md:385`'s Do-row only lists three labels — slate, amber, warm-personal — and does not mention discovery.
>
> **(b) `nearby` is ambiguous between "public stripe" and "discovery stripe".** The spine has two slate stripe treatments — full-opacity (public) and 0.85-opacity (discovery/serendipity) — and the backend's `nearby` slot could plausibly be either. **The spines do not resolve this.** The frontend needs a decision; the natural reading, supported by `DESIGN.md:65` ("serendipity / discovery") + `prd.md:203` (Slot 3 = serendipity = `discovery` tag), is that **`serendipity` → the 0.85-opacity discovery treatment, and `nearby` → the full-opacity public treatment**. Note this decision must be recorded, as the work item requires for the tag separator (same pattern).

**Also relevant:** the work item warns the component must not conflate the two explanation kinds — `frontend-pulse-card.md:38`:

> **This component is reused by three surfaces and built once.** Browse (A-10) "reuses `component.card.pulse.digest` vocabulary card-for-card", and the Pulse Preview already renders a structurally identical card with Event Fit data. Build the props so that the *explanation source* is a parameter: a card fed a Relevance Pulse and a card fed an Event Fit look identical on screen, which is exactly why AD-10 insists they are never substituted — the component must make the caller say which it is, and must label it accordingly.

`ARCHITECTURE-SPINE.md:146-149` (AD-10):
> | Kind | Computed | Persisted on | Serves | Owner |
> | --- | --- | --- | --- | --- |
> | **Event Fit** `[NEW NOUN]` — non-personalized score + generic tags | per `(event, city)`, on ingest/refresh | `catalog` rollup | SEO pages, Pulse Preview — **anonymous, no session, cacheable** | `ingestion` |
> | **Relevance Pulse** `[NEW NOUN]` — per-user score + per-user Why-this Tags | at digest composition | `DIGEST_COMPOSITION` (`personal`) | card, Detail Screen, email | `personalization` |

---

## 16. Conflicts / drift found in the sources (must be resolved before implementing)

| # | Conflict | Sources | Work item's ruling |
|---|---|---|---|
| 1 | **Conflict indicator size: 8px vs 6px** | `DESIGN.md:293` says 8px; `DESIGN.md:310` says 6px; `EXPERIENCE.md:1209` (ASSUM-13, RESOLVED) says 6px | `frontend-pulse-card.md:29`: *"DESIGN.md L293's "8px" and the mockup's 10px are both stale; ASSUM-13's 6px is locked."* → **6px** |
| 2 | **Visible confidence numeric** | `DESIGN.md:308` renders it in `{type.scale.numeric}`; `EXPERIENCE.md:210` says "Dots only. No numeric label visible." | `frontend-pulse-card.md:27`: *"Default shows **dots only with no visible numeric**"* → **no visible numeric** |
| 3 | **Headline type role** | `DESIGN.md:293` `type.scale.headline.md` (22px) vs `EXPERIENCE.md:179` `Text.Display.sm` | `frontend-pulse-card.md:22` picks `type.scale.headline.md` (22px) → **22px** |
| 4 | **Card default fill/border** | `EXPERIENCE.md:179` `color.surface.paper` + `color.ink.faint` hairline vs `DESIGN.md:253` `color.surface.elevated` + `color.border.subtle` | `frontend-pulse-card.md:23` picks the tokens → **elevated + border.subtle** |
| 5 | **Confidence tooltip surface** | `EXPERIENCE.md:211` `color.surface.paper.darker` vs `DESIGN.md:124` `color.surface.elevated` + shadow | `DESIGN.md:111` forbids `paper.darker` as a static surface → **elevated** (token layer wins) |
| 6 | **Card hover fill** | `DESIGN.md:253` `color.surface.subtle` (desktop) vs `EXPERIENCE.md:180`/`:1103` `color.surface.paper.darker` | Both are "background shift only, no shadow"; `DESIGN.md:111` reserves `paper.darker` for card hover, `DESIGN.md:253` says `surface.subtle` → **unresolved in the spines**; either satisfies the work item's "border or background shift only" |
| 7 | **Tag separator** | `DESIGN.md:293`/`:152`/`:263`/`:382` = middle dot; `EXPERIENCE.md:1031`/`:736` = comma | `brief.md:114` — undecided; work item says "pick one, apply it everywhere, and record the choice" |
| 8 | **`official_site` tooltip copy** | `EXPERIENCE.md:221` "Verified venue or organizer." vs `EXPERIENCE.md:116`/`:735` "Official site. Verified venue." | `EXPERIENCE.md:1197` (ASSUM-9) locks `Tooltip.Source` copy to §4; both strings are in §4 |
| 9 | **Discovery stripe label** | `DESIGN.md:107` requires a visible text label for every stripe; `DESIGN.md:297` gives discovery only a micro-tag | The `discovery` micro-tag is the de facto visible label |
| 10 | **`nearby` slot → which slate?** | Backend has `nearby`; spine has two slate treatments | **Unresolved in the spines** — needs a recorded decision (recommended: `nearby` → full-opacity public; `serendipity` → 0.85 discovery) |

---

## Sources

- `DESIGN.md` — `/Users/jobaer/Documents/EventPulse24/_bmad-output/planning-artifacts/ux-designs/ux-EventPulse24-2026-08-23/DESIGN.md`
- `EXPERIENCE.md` — `/Users/jobaer/Documents/EventPulse24/_bmad-output/planning-artifacts/ux-designs/ux-EventPulse24-2026-08-23/EXPERIENCE.md`
- `ARCHITECTURE-SPINE.md` — `/Users/jobaer/Documents/EventPulse24/_bmad-output/planning-artifacts/architecture/architecture-EventPulse24-2026-09-04/ARCHITECTURE-SPINE.md`
- `prd.md` — `/Users/jobaer/Documents/EventPulse24/_bmad-output/planning-artifacts/prds/prd-EventPulse24-2026-08-19/prd.md`
- `frontend-pulse-card.md` — `/Users/jobaer/Documents/EventPulse24/.specs-fire/intents/pulse-digest-and-trust/work-items/frontend-pulse-card.md`
- `brief.md` — `/Users/jobaer/Documents/EventPulse24/.specs-fire/intents/pulse-digest-and-trust/brief.md`
- `SKILL.md` (bmad-ux) — `/Users/jobaer/Documents/EventPulse24/.agents/skills/bmad-ux/SKILL.md`

No files were written or edited.