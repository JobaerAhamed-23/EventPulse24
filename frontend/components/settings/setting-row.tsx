/**
 * `Component.Settings.Row` — the mockup's settings row: what it is on the left, the
 * control on the right.
 *
 * `settings-desktop.html` draws every setting the same way — `<div class="row">` holding
 * a `<strong>` name, a muted one-line description, and a control pushed to the far edge,
 * with a hairline between rows and none above the first. That shape is what makes a long
 * preferences page scannable: the eye runs down the names on the left, and the controls
 * line up in a single column on the right.
 *
 * **The settings screens had no such shape.** Each had arrived as its own route with one
 * control, so a control's label was the page's `<h1>` and nothing needed aligning. Merged
 * onto one page, that leaves headings and controls at whatever indent each component
 * happened to use.
 *
 * ## The description is where the state is allowed to speak
 *
 * A toggle's state must be readable as *words*, not only as a knob's position or a
 * colour (WCAG 1.4.1). `SwitchControl` carries a short "On"/"Off", and a control whose
 * state deserves a full sentence — *"Personal events are in your Pulse Digest"* — puts
 * that sentence here, in `description`, where it is a real element that a screen reader
 * and a sighted reader both get.
 *
 * ## It is a plain layout component
 *
 * No state, no `"use client"`, no knowledge of what the control does. It takes a label, a
 * description and a `control`, and it is the *caller* that stays a client component when
 * its control needs to be.
 */
import type { ReactNode } from "react";

export type SettingRowProps = {
  /** What the setting is. Never what toggling it would do. */
  label: string;
  /**
   * One line about the setting — and, for a toggle, the place its state is said in
   * words. Omitted when the label says everything.
   */
  description?: ReactNode;
  /** The control, pushed to the trailing edge. */
  control: ReactNode;
  /**
   * Rendered under the row, full width: a save status, a hint, a refusal.
   *
   * It sits inside the row rather than after it so that the message and the control it
   * belongs to cannot be separated by a later layout change.
   */
  footer?: ReactNode;
  /** A `data-` hook for tests. */
  testAttribute?: string;
};

export function SettingRow({
  label,
  description,
  control,
  footer,
  testAttribute,
}: SettingRowProps): ReactNode {
  return (
    <div
      {...(testAttribute ? { [testAttribute]: "" } : {})}
      data-setting-row
      // **The hairline is a top border, and the first row's is removed by the parent.**
      // `border-t` plus `first:border-t-0` keeps the rule with the row rather than asking
      // every caller to remember which of its children is first.
      className="flex flex-col gap-3 border-t border-border-subtle py-4 first:border-t-0 first:pt-0"
    >
      <div className="flex flex-wrap items-center justify-between gap-4">
        <span className="flex min-w-0 flex-col gap-1">
          <span className="text-ink-primary [font:var(--type-scale-meta-md)]">{label}</span>
          {description ? (
            <span className="text-ink-muted [font:var(--type-scale-body-sm)]">{description}</span>
          ) : null}
        </span>

        {/* `shrink-0`: the control keeps its size and the label wraps instead. */}
        <span className="shrink-0">{control}</span>
      </div>

      {footer ? <div>{footer}</div> : null}
    </div>
  );
}
