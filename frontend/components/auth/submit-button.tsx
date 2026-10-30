"use client";

/**
 * The auth forms' primary action, and its in-flight state.
 *
 * **There is no spinner.** The mockups draw one, and `EXPERIENCE.md` overrules them in
 * the same breath: "No spinners, anywhere. PRD §13.1 and §13.2: a spinner is a visual
 * urgency badge." The product has exactly one transition (`.fade-in`), and
 * `styles/motion.test.ts` fails the suite on any other animation. So the in-flight state
 * is the form the spec itself specifies for reduced motion: a **static dot** beside the
 * label.
 *
 * While the request is in flight the button is `disabled` and `aria-busy`, which is what
 * stops a double submit, and the label says what is happening ("Signing in…").
 */

export type SubmitButtonProps = {
  /** The resting label ("Sign in"). */
  label: string;
  /** The in-flight label ("Signing in…"). */
  busyLabel: string;
  busy: boolean;
};

export function SubmitButton({ label, busyLabel, busy }: SubmitButtonProps) {
  return (
    <button
      type="submit"
      disabled={busy}
      aria-busy={busy}
      className="inline-flex items-center gap-2 rounded-control bg-accent-terracotta px-5 py-2.5 [font:var(--type-scale-meta-md)] text-ink-inverse disabled:bg-surface-inset disabled:text-ink-faint"
    >
      {busy ? <span aria-hidden="true" className="h-2 w-2 rounded-full bg-current" /> : null}
      {busy ? busyLabel : label}
    </button>
  );
}

/**
 * A form-level message: the API's own words when the failure is not about one field.
 *
 * A 429, a `csrf_failed`, an unreachable API — none of them belong on the Email or the
 * Password field, and putting them there would say the field was wrong when it was not.
 */
export function FormAlert({ message }: { message: string | null }) {
  if (message === null) return null;
  return (
    <p
      role="alert"
      className="flex items-start gap-2 rounded-card border border-signal-warn/40 bg-surface-subtle px-4 py-3 [font:var(--type-scale-body-sm)] text-signal-warn"
    >
      <span aria-hidden="true">⚠</span>
      <span>{message}</span>
    </p>
  );
}
