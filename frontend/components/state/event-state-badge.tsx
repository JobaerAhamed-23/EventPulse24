/**
 * `Component.Badge.SoldOut` and its two siblings — the card's **state treatment**.
 *
 * **One badge, three states, and the shape is what tells them apart.**
 *
 * `DESIGN.md` gives `component.badge.soldout` a full anatomy: a `{color.surface.subtle}`
 * fill, a 1px `{color.border.strong}` stroke, a 6px radius, and a leading glyph in
 * `{color.signal.warn}` beside the label "Sold out" in `{type.scale.meta.sm}`
 * `{color.ink.secondary}`, uppercase. `EXPERIENCE.md` §`Component.Badge.SoldOut` adds the
 * two rules that decide everything else:
 *
 * - **"Color is paired with the visible text label … so the chromatic signal is never
 *   the sole carrier of meaning (WCAG 1.4.1)."** So the label is always present, and it
 *   is the label — not the glyph, not the fill — that carries the meaning.
 * - **"No desaturated-grey variant — the warn amber is the canonical signal."** So
 *   there is one colour and one treatment; the states differ in their *words*.
 *
 * **The design system has a sold-out badge and no cancelled or postponed one.** That is
 * a real gap, and this file closes it by extending the sold-out anatomy rather than by
 * inventing a second one: the same pill, the same ink, the same stroke — and a
 * **different glyph** for each state. The glyph is what makes the three legible at a
 * glance, since the colour cannot do it (the conflict indicator's amber and this badge's
 * amber are *the same hex*).
 *
 * **The glyphs are deliberately different from each other and from the conflict
 * indicator's dot.** The conflict indicator is a 6px filled circle with an ink ring —
 * a *mark*, not a badge. These are pills with a leading glyph, which is a different
 * shape in a different place. `DESIGN.md` is explicit that the conflict indicator must
 * be "distinct in shape and position from the Source Badge and Confidence Pulse", and
 * this badge sits in the same card as those and the conflict mark — **in its own row
 * above the title, not in the trust row**, which is at capacity — so it has to be
 * distinct from all of them too.
 *
 * **Nothing here is a control.** The badge is a static fact, not a button: there is
 * nothing to dismiss and nothing to do about a cancelled event. It is a `<span>`, so
 * it is never a focus stop and never in the tab order.
 */

import { STATE_LABELS, type CardState } from "@/lib/event-state";

/**
 * The states the badge can show.
 *
 * **This is `CardState`, and it stays `CardState`.** An alias under a second name
 * would be a second vocabulary for one concept — which is the exact thing the shared
 * table in `lib/event-state.ts` exists to prevent. The badge is a *card* badge: it
 * renders the states a card can carry, and the type says so.
 */
export type EventState = CardState;

/**
 * The glyph for each state.
 *
 * **Three shapes, and none of them is the conflict indicator's dot.** The conflict
 * indicator is a 6px *filled circle* — `●` — so no state may use one. Cancelled is `✕`,
 * a strike: the ordinary mark for "not happening". Postponed is `↦`, a deferral: a
 * movement in time, which is exactly what a postponement is and what a cancellation is
 * not. Sold out is `⊘`, a slashed circle: "no more of this", and not a plain filled
 * circle, so it cannot be mistaken for the conflict mark at a glance.
 *
 * **`⊘` is a departure from `DESIGN.md`, and it is a deliberate one.** The design
 * specifies "a leading `●` glyph in `{color.signal.warn}`" — and a filled circle is
 * *exactly the shape of the conflict indicator*, which sits in the same card, at the
 * same scale, in the same amber. The design's rule for the conflict indicator is that
 * it must be "distinct in shape and position from the Source Badge and Confidence
 * Pulse", and the badge is a third signal in that row. So the sold-out glyph is
 * hollow where the conflict dot is solid: same hue, different figure.
 *
 * **`↦` is the right mark for postponed, and the alternative is wrong.** A clock (`◷`)
 * would say "the time is provisional", but a postponed event has *no* new time yet
 * (the backend's `POSTPONED` means "date to be announced"), so a clock would promise a
 * time that does not exist. `↦` promises only a movement.
 */
const GLYPHS: Record<EventState, string> = {
  sold_out: "⊘",
  cancelled: "✕",
  postponed: "↦",
};

/**
 * The badge, for one state.
 *
 * **The badge is decorative to assistive technology, because the card already says it
 * in words.**
 *
 * `EXPERIENCE.md` originally asked for `aria-label="Sold out"` on the badge, "in card
 * contexts where the badge might be parsed as decoration". But the card's own link
 * carries the state in its `aria-label` — and that link is the tap target, so it is
 * what a link-navigating reader hears. Putting the same word in *two* places in one
 * card means a browse-mode reader reaches the badge, hears "Cancelled", and then
 * reaches the link and hears "Cancelled" again: the same fact, twice, in one card.
 *
 * **So the badge is `aria-hidden`, and the link carries the fact.** The visible label
 * stays — it is what makes the state legible at a glance and it is what satisfies
 * WCAG 1.4.1, where colour must never be the sole carrier of meaning. Hiding the
 * badge from the accessibility tree does not hide it from anyone; it only stops the
 * announcement being made twice.
 *
 * **This is A-22's second amendment, and it is a change of the design, not of the
 * implementation.** The design had it both ways — the badge named *and* the card's
 * `aria-label` naming — and the build had to pick one. It picked the link, because the
 * link is the thing the reader activates.
 */
export function EventStateBadge({ state }: { state: EventState }) {
  return (
    <span
      className={[
        "inline-flex items-center gap-2 rounded-subtle border border-border-strong",
        "bg-surface-subtle px-3 py-1",
        "[font:var(--type-scale-meta-sm)] font-semibold uppercase tracking-[0.06em]",
        "text-ink-secondary",
      ].join(" ")}
      data-event-state={state}
      aria-hidden="true"
    >
      {/*
        **The glyph is decorative and the label carries the meaning.** `aria-hidden` on
        the glyph is what stops a screen reader announcing "black circle, Sold out" —
        and it is the same rule the Source Badge and the conflict indicator already
        follow.
      */}
      <span aria-hidden="true" className="text-signal-warn">
        {GLYPHS[state]}
      </span>
      {STATE_LABELS[state]}
    </span>
  );
}
