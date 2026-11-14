"use client";

/**
 * `Component.Control.Switch` — the sliding on/off control from `settings-desktop.html`.
 *
 * ## It looks like a switch and is a button, and that is on purpose
 *
 * The mockup draws `<div class="switch" role="switch" aria-checked>`. **This component
 * renders the mockup's pixels and refuses its markup**, because the codebase has already
 * decided this question in the other direction: `digest-personal-events.tsx` says *"Not a
 * switch, not a checkbox"*, and `reminders/reminder-picker.tsx` records that the Detail
 * Screen was moved **off** `role="switch"` onto `<button aria-pressed>`. A mockup is a
 * picture of a screen, not a ruling about its semantics, and reversing a decision
 * somebody wrote down is not something a visual refresh should do quietly.
 *
 * So: a `<button>` carrying `aria-pressed`, drawn as a track and a knob.
 *
 * ## The accessible name never changes, and the state never hides in it
 *
 * The name is fixed and the state rides on `aria-pressed`. A control renamed by its own
 * state ("Turn on" → "Turn off") is announced as a *different control* each time it is
 * pressed, which is what `ACCESSIBLE_NAME` in `digest-personal-events.tsx` exists to
 * avoid. The same rule holds here, so `label` is what the control *is*, never what
 * pressing it would do.
 *
 * ## The knob is not the only thing that changes
 *
 * Colour alone cannot carry state (WCAG 1.4.1), and neither can position alone for
 * somebody who has never seen the other position. So the component ships a visible
 * `stateLabel` beside the track — "On"/"Off" by default — which is a real element rather
 * than a pseudo-element, so a screen reader and a sighted reader get the same words.
 *
 * ## Terracotta is spent here deliberately
 *
 * The house rule is that *"terracotta on a small-control toggle burns the accent on a
 * control used many times per day"* (`settings-nav.tsx`) — which is why the settings
 * sub-nav uses an ink pill instead. **A settings switch is the exception the mockup
 * draws**, and the reason holds: this is a control touched a handful of times ever, not
 * many times a day, and "on" is exactly the state worth spending the accent on.
 */
import type { ReactNode } from "react";

export type SwitchControlProps = {
  /** Whether the setting is on. */
  checked: boolean;
  /** Called when the user presses the control. */
  onToggle: () => void;
  /**
   * What the control *is* — never what pressing it would do.
   *
   * It is the accessible name, and it does not change with the state.
   */
  label: string;
  /** Visibly disables the control. */
  disabled?: boolean;
  /** The words beside the track. Defaults to "On" / "Off". */
  stateLabel?: { on: string; off: string };
  /** A `data-` hook for tests, set on the button. */
  testAttribute?: string;
};

const DEFAULT_STATE_LABEL = { on: "On", off: "Off" } as const;

export function SwitchControl({
  checked,
  onToggle,
  label,
  disabled = false,
  stateLabel = DEFAULT_STATE_LABEL,
  testAttribute,
}: SwitchControlProps): ReactNode {
  return (
    <span className="flex items-center gap-3">
      {/*
        **The state in words, before the track in the reading order.** It is the part a
        reader who cannot see the knob's position depends on, and putting it first means
        it is not something they have to go looking for.
      */}
      <span
        aria-hidden="true"
        className={[
          "[font:var(--type-scale-meta-sm)]",
          checked ? "text-ink-primary" : "text-ink-muted",
        ].join(" ")}
      >
        {checked ? stateLabel.on : stateLabel.off}
      </span>

      <button
        type="button"
        onClick={onToggle}
        disabled={disabled}
        // `aria-pressed`, not `aria-checked`: see the module docstring.
        aria-pressed={checked}
        aria-label={label}
        {...(testAttribute ? { [testAttribute]: "" } : {})}
        data-switch-control
        data-state={checked ? "on" : "off"}
        className={[
          // **44px of hit area, 22px of paint.** The track is the size the mockup draws;
          // the button around it is the size a thumb needs (A-16's target rule). The
          // padding is what reconciles the two — shrinking the target to match the
          // drawing would be a control that looks right and misses.
          "inline-flex min-h-[44px] items-center px-1",
          "disabled:cursor-default disabled:opacity-60",
        ].join(" ")}
      >
        <span
          aria-hidden="true"
          className={[
            "relative block h-[22px] w-[38px] rounded-full transition-colors duration-150",
            checked ? "bg-accent-terracotta" : "bg-surface-inset",
          ].join(" ")}
        >
          <span
            className={[
              "absolute top-[3px] left-[3px] block size-[16px] rounded-full transition-transform duration-150",
              checked ? "translate-x-[16px] bg-ink-inverse" : "bg-ink-secondary",
            ].join(" ")}
          />
        </span>
      </button>
    </span>
  );
}
