"use client";

/**
 * The delivery-time control — **one native time input and the mockup's presets**.
 *
 * **This control was extracted from `digest-step.tsx`, not written a second time.**
 * The work item for the settings routes says the delivery time must *"reuse the
 * onboarding time-preset control rather than a new one"*, and a second copy of a time
 * control is how two screens come to disagree about what a time means — one of them
 * would get the `HH:MM:SS` slicing wrong, or grow a different preset list, or drop the
 * `aria-invalid` wiring, and the user would meet both.
 *
 * **One time control, not three.** The mockup draws an hour box, a minute box and an
 * AM/PM pair. A native `type="time"` is one value, one control, and it is what a
 * screen reader and a keyboard already know how to drive; three controls for one value
 * is three chances to disagree with each other. The mockup's presets are kept, because
 * they are the quick path they were drawn to be, and they set the same single field.
 *
 * **The `id` and the label are props, because two screens label the same control
 * differently.** The onboarding step says *"Pulse Digest delivery time"*; the settings
 * route says *"Delivery time"*. The control itself is the same control.
 *
 * **The timezone select is deliberately not here.** It is a separate concern — the
 * digest's zone — and it lives with the onboarding step that sets it. The settings
 * route sends the zone it read back unchanged.
 */

/** The mockup's presets, as 24-hour values for the time input. */
export const DIGEST_TIME_PRESETS = ["08:00", "07:00", "09:00", "12:00", "18:00"];

export type DigestTimeControlProps = {
  /** The control's id — the `htmlFor` and the `aria-describedby` hang off it. */
  id: string;
  /** The control's visible label. */
  label: string;
  /** The time, as `HH:MM`. */
  value: string;
  /** The new time, when the user changes it. */
  onChange: (value: string) => void;
  /** The field's error, when it has one. */
  error?: string | null;
  /** The id of the hint the control is described by, when it has one. */
  describedBy?: string;
};

export function DigestTimeControl({
  id,
  label,
  value,
  onChange,
  error,
  describedBy,
}: DigestTimeControlProps) {
  /**
   * **The error's own id, derived from the control's.** The control's id is a prop
   * because two screens use this control, so the error id cannot be a constant — and a
   * hardcoded one would collide the moment the second screen rendered it.
   */
  const errorId = `${id}-error`;

  return (
    <div>
      <label
        htmlFor={id}
        className="mb-2 block text-[12px] font-semibold tracking-[0.06em] text-ink-secondary uppercase"
      >
        {label}
      </label>
      <input
        id={id}
        name="delivery_time"
        type="time"
        value={value}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? errorId : describedBy}
        onChange={(event) => onChange(event.target.value)}
        className={[
          "w-full max-w-[200px] rounded-control border bg-surface-subtle px-3 py-2 [font:var(--type-scale-body-md)]",
          error ? "border-signal-warn" : "border-border-subtle",
        ].join(" ")}
      />
      {error ? (
        <p
          id={errorId}
          role="alert"
          className="mt-2 flex items-start gap-2 [font:var(--type-scale-body-sm)] text-signal-warn"
        >
          <span aria-hidden="true">⚠</span>
          <span>{error}</span>
        </p>
      ) : null}

      <div className="mt-4 flex flex-wrap gap-2">
        {DIGEST_TIME_PRESETS.map((preset) => (
          <button
            key={preset}
            type="button"
            aria-pressed={value === preset}
            onClick={() => onChange(preset)}
            className={[
              "rounded-control border px-3 py-2 [font:var(--type-scale-meta-sm)]",
              value === preset
                ? "border-accent-terracotta text-ink-primary"
                : "border-border-subtle text-ink-secondary",
            ].join(" ")}
          >
            {preset}
          </button>
        ))}
      </div>
    </div>
  );
}
