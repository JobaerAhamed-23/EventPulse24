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

import {
  DigestTimeControl,
  DIGEST_TIME_PRESETS,
} from "@/components/onboarding/digest-time-control";
import { ZONE_CHOICES, browserZone } from "@/lib/timezones";

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
    deliveryTime: stored.delivery_time ? stored.delivery_time.slice(0, 5) : DIGEST_TIME_PRESETS[0],
    timezone: stored.timezone ?? browserZone() ?? "UTC",
  };
}

export function DigestStep({ values, onChange, error }: DigestStepProps) {
  const set = (patch: Partial<DigestValues>): void => onChange({ ...values, ...patch });

  return (
    <div className="flex flex-col gap-8">
      {/*
        **The time control is shared with the settings route.** It was extracted out of
        this step so `/settings/quiet-hours` could reuse the same control rather than
        grow a second copy of it — two copies of a time control is how two screens come
        to disagree about what a time means.
      */}
      <DigestTimeControl
        id="digest-time"
        label="Pulse Digest delivery time"
        value={values.deliveryTime}
        onChange={(deliveryTime) => set({ deliveryTime })}
        error={error}
      />

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
