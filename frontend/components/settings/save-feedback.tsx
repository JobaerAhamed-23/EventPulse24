"use client";

/**
 * The inline-save feedback — **the same three states on every settings control**.
 *
 * **There is no spinner.** `EXPERIENCE.md` §"No spinners, anywhere" (and the
 * architecture test's planted `animate-spin` fixture) forbid one: *"A spinner is a
 * visual urgency badge."* The product has exactly one transition (`.fade-in`), and
 * `styles/motion.test.ts` fails the suite on any other animation.
 *
 * **So the in-flight state is a static dot** — the form the spec itself specifies for
 * reduced motion, and therefore the form that renders instantly under every motion
 * preference without a second implementation. `components/auth/submit-button.tsx` has
 * used this since the auth screens shipped.
 *
 * **Three states, and they are quiet.** While the request is in flight the control is
 * `disabled` and `aria-busy`; on success the region says *"Saved."*; on failure it says
 * the route's own failure line, and **the user's chosen state is kept** — reverting it
 * would throw away their work over a transient failure, and the copy promises a retry.
 */
export type SaveFeedbackProps = {
  /** Whether a save is in flight. */
  busy: boolean;
  /** Whether the last save succeeded. */
  saved: boolean;
  /** The route's failure line, verbatim. */
  failure: string | null;
};

export function SaveFeedback({ busy, saved, failure }: SaveFeedbackProps) {
  return (
    <>
      {/*
        **The success region is a `role="status"`**, so a screen reader announces it
        without the focus moving. It is always present — an empty live region is what
        makes the *arrival* of the text announceable at all.
      */}
      <div role="status" aria-live="polite" className="mt-2">
        {saved ? (
          <p className="text-ink-secondary [font:var(--type-scale-body-sm)]" data-saved>
            Saved.
          </p>
        ) : null}
      </div>

      {failure ? (
        <p
          role="alert"
          className="mt-2 text-warn-amber [font:var(--type-scale-body-sm)]"
          data-save-failed
        >
          {failure}
        </p>
      ) : null}

      {/*
        **The in-flight dot.** It sits beside the control, so the thing being saved is
        the thing that shows the wait. It is `aria-hidden` because the control's own
        `aria-busy` already carries that state to assistive technology.
      */}
      {busy ? (
        <span
          aria-hidden="true"
          className="inline-block h-2 w-2 rounded-full bg-current"
          data-saving-dot
        />
      ) : null}
    </>
  );
}
