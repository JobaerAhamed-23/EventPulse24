"use client";

/**
 * Step 3 — when the daily Pulse arrives (FR-1, FR-7).
 *
 * **The time is a local wall clock.** `DigestPreferenceIn` is explicit: "09:00" means
 * nine in the morning *where the user is*, not nine UTC — so the zone is sent with it and
 * the pair is meaningless apart.
 *
 * **One time control, not three.** The mockup draws an hour box, a minute box and an
 * AM/PM pair. A native `type="time"` is one value, one control, and it is what a screen
 * reader and a keyboard already know how to drive; three controls for one value is three
 * chances to disagree with each other. The mockup's presets are kept, because they are
 * the quick path they were drawn to be, and they set the same single field.
 *
 * The timezone list and the browser's own zone come from `lib/timezones.ts`, which the
 * personal-event form already uses — one list, one idea of which zones exist.
 */

import { ZONE_CHOICES, browserZone } from "@/lib/timezones";

/** The mockup's presets, as 24-hour values for the time input. */
const PRESETS = ["08:00", "07:00", "09:00", "12:00", "18:00"];

/** The server's default when the step is skipped (`DEFAULT_DIGEST_DELIVERY_TIME`). */
export const DEFAULT_DELIVERY_TIME = "09:00";

export type DigestValues = { deliveryTime: string; timezone: string };

export type DigestStepProps = {
  values: DigestValues;
  onChange: (values: DigestValues) => void;
  error?: string | null;
};

/** The step's starting values: what is stored, else the mockup's 8am in the browser's zone. */
export function initialDigestValues(stored: {
  delivery_time?: string | null;
  timezone?: string | null;
}): DigestValues {
  return {
    // A stored time arrives as `HH:MM:SS`; the input wants `HH:MM`.
    deliveryTime: stored.delivery_time ? stored.delivery_time.slice(0, 5) : PRESETS[0],
    timezone: stored.timezone ?? browserZone() ?? "UTC",
  };
}

export function DigestStep({ values, onChange, error }: DigestStepProps) {
  const set = (patch: Partial<DigestValues>): void => onChange({ ...values, ...patch });

  return (
    <div className="flex flex-col gap-8">
      <div>
        <label
          htmlFor="digest-time"
          className="mb-2 block text-[12px] font-semibold tracking-[0.06em] text-ink-secondary uppercase"
        >
          Pulse Digest delivery time
        </label>
        <input
          id="digest-time"
          name="delivery_time"
          type="time"
          value={values.deliveryTime}
          aria-invalid={Boolean(error)}
          aria-describedby={error ? "digest-time-error" : undefined}
          onChange={(event) => set({ deliveryTime: event.target.value })}
          className={[
            "w-full max-w-[200px] rounded-control border bg-surface-subtle px-3 py-2 [font:var(--type-scale-body-md)]",
            error ? "border-signal-warn" : "border-border-subtle",
          ].join(" ")}
        />
        {error ? (
          <p
            id="digest-time-error"
            role="alert"
            className="mt-2 flex items-start gap-2 [font:var(--type-scale-body-sm)] text-signal-warn"
          >
            <span aria-hidden="true">⚠</span>
            <span>{error}</span>
          </p>
        ) : null}

        <div className="mt-4 flex flex-wrap gap-2">
          {PRESETS.map((preset) => (
            <button
              key={preset}
              type="button"
              aria-pressed={values.deliveryTime === preset}
              onClick={() => set({ deliveryTime: preset })}
              className={[
                "rounded-control border px-3 py-1.5 [font:var(--type-scale-meta-sm)]",
                values.deliveryTime === preset
                  ? "border-accent-terracotta text-ink-primary"
                  : "border-border-subtle text-ink-secondary",
              ].join(" ")}
            >
              {preset}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label
          htmlFor="digest-timezone"
          className="mb-2 block text-[12px] font-semibold tracking-[0.06em] text-ink-secondary uppercase"
        >
          Timezone
        </label>
        <select
          id="digest-timezone"
          name="timezone"
          value={values.timezone}
          aria-describedby="digest-timezone-hint"
          onChange={(event) => set({ timezone: event.target.value })}
          className="w-full rounded-control border border-border-subtle bg-surface-subtle px-3 py-2 [font:var(--type-scale-body-md)]"
        >
          {ZONE_CHOICES.map((choice) => (
            <option key={choice.value} value={choice.value}>
              {choice.value} — {choice.label}
            </option>
          ))}
        </select>
        <p
          id="digest-timezone-hint"
          className="mt-2 [font:var(--type-scale-body-sm)] text-ink-muted"
        >
          If you travel, we&apos;ll switch this for you — confirmed by your device, not silently.
        </p>
      </div>
    </div>
  );
}
