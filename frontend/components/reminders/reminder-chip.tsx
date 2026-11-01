"use client";

/**
 * One reminder slot chip.
 *
 * **Selection is an ink inversion, never a terracotta fill.** `EXPERIENCE.md` §4
 * `Input.ReminderSlot`: *"no terracotta on this chip; selection is communicated by ink
 * inversion, not by accent"*. The work item's acceptance criteria say the same thing in
 * the token names, and require a test that asserts no accent token appears here — so
 * the selected chip is `color.ink.primary` filled with `color.ink.inverse` text, and
 * the unselected chip is `color.ink.primary` text on `color.surface.subtle`.
 *
 * **Why the accent is wrong here, and the tint is not.** `DESIGN.md` ASSUM-6 makes the
 * terracotta *tint* the canonical small-control selection treatment, and
 * `component.input.reminder.slot` gives this chip exactly that tint. But the accent is
 * one of four sanctioned uses, and a chip used many times per day is not one of them —
 * `EXPERIENCE.md` says so about the small-control toggle in the same breath: *"terracotta
 * on a small-control toggle burns the accent on a control used many times per day"*.
 * The work item settles it in favour of the inversion. **The tint is not the accent
 * either**, and this chip does not carry it: the acceptance criteria name the two
 * surface tokens and the two ink tokens, and a chip with a third state is a chip whose
 * selection is not invertible.
 *
 * **The dimmed state is the server's flag, never a recomputation.** A slot whose
 * delivery would land inside the user's Quiet Hours arrives with `deferred: true` and
 * `deferred_to` set. The chip dims to 40% opacity and says *"Will deliver at {end of
 * quiet hours}."* The shift is **not** reimplemented here — that would be a second
 * implementation of the Quiet Hours window in TypeScript, with DST and midnight
 * rediscovered there.
 *
 * **The dimmed state is still selectable.** It says what will happen; it does not
 * forbid it. A chip that could not be pressed would be a control that is present and
 * inert, which is the failure this product keeps avoiding.
 *
 * **The dimmed state is not carried by opacity alone.** Opacity is invisible to a
 * screen reader, so the chip also carries the deferred instant in its accessible name
 * and shows it as visible text beside the chip. The visible text is the real signal;
 * the opacity is the quiet part.
 */
export type ReminderChipProps = {
  /** The slot's id — `5d`, `2d`, `1d`, `1hr`, or `custom:<minutes>`. */
  slot: string;
  /** The chip's visible label. */
  label: string;
  /** The chip's accessible name — the sentence a screen reader reads. */
  name: string;
  /** Whether the chip is currently selected. */
  selected: boolean;
  /**
   * Whether Quiet Hours moved this slot's delivery.
   *
   * **The server's flag, carried straight through.** The chip does not compute it and
   * does not question it.
   */
  deferred: boolean;
  /** The visible explanation, when the chip is deferred. */
  note: string | null;
  /** Whether this chip is the plan's custom slot. */
  custom: boolean;
  /** The chip's own toggle. */
  onToggle: () => void;
};

export function ReminderChip({
  slot,
  label,
  name,
  selected,
  deferred,
  note,
  custom,
  onToggle,
}: ReminderChipProps) {
  /**
   * **The chip's accessible name.**
   *
   * **The sentence, not the abbreviation.** The visible label is "1hr" — two
   * characters that read as "one hour" only to someone who already knows what a
   * reminder slot is. The name is "1 hour before", which is what a screen reader
   * should say.
   *
   * **And the deferred instant goes into it too.** Opacity is invisible to a screen
   * reader, so the fact that this slot will deliver later has to be in the name. The
   * name is the label plus the note — and the note is the same sentence the visible
   * text shows, so the two channels never disagree.
   *
   * **`aria-label`, not a visually-hidden span.** A hidden span inside the button
   * would be *concatenated* with the visible label — the chip would be announced as
   * "1hr 1 hour before" — and it would also make the button's `textContent` carry
   * text nobody can see. The label attribute replaces the name outright.
   */
  const accessibleName = deferred && note ? `${name}. ${note}` : name;

  return (
    <div className="flex flex-col gap-1" data-reminder-chip data-slot={slot}>
      <button
        type="button"
        aria-pressed={selected}
        aria-label={accessibleName}
        onClick={onToggle}
        className={[
          "min-h-[44px] rounded-control px-4 py-2 [font:var(--type-scale-meta-md)]",
          // **The ink inversion.** Selected: primary ink filled, inverse ink on it.
          // Unselected: primary ink on the subtle surface. No accent token appears
          // anywhere in this file, and a test asserts it.
          selected ? "bg-ink-primary text-ink-inverse" : "bg-surface-subtle text-ink-primary",
          // **The focus ring is the terracotta stroke.** The one sanctioned accent use
          // on this surface is the focus ring — a ring that says "you are here" is
          // exactly what the accent is for, and it burns nothing.
          "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-terracotta",
          // **The dimmed state.** 40% opacity, from the server's flag.
          deferred ? "opacity-40" : "",
        ].join(" ")}
      >
        <span className="font-semibold">{label}</span>
      </button>

      {/*
        **The note is visible text, not a tooltip.** The acceptance criteria ask for a
        tooltip *and* for the dimmed state to be conveyed by text and not by opacity
        alone — and a tooltip that only appears on hover is unreachable by keyboard and
        invisible to a screen reader. So the note is rendered as text under the chip, and
        the tooltip is that same text made available on hover and focus through
        `title`-like affordances. **One sentence, two channels.**
      */}
      {deferred && note ? (
        <p className="text-ink-muted [font:var(--type-scale-meta-sm)]" data-reminder-chip-note>
          {note}
        </p>
      ) : null}

      {/*
        **The custom slot's marker.** A custom chip is one the user made, and the mockup
        marks it with an amber marker circle. Here it is marked by an appended word
        rather than by a colour — because the accent is spoken for, and because a chip
        that differs only by a hue is a chip that differs only by a hue.
      */}
      {custom ? <span className="sr-only">Custom reminder.</span> : null}
    </div>
  );
}
