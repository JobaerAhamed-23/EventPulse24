"use client";

/**
 * The frame every onboarding step shares: the progress dots, the step label, the heading
 * and lede, the step's own body, and the footer actions.
 *
 * **The actions are in the footer, never the topbar** (the topbar-quiet rule, ASSUM-11):
 * "← Back", "Skip all", "Skip for now" and "Continue →" all live here, which is where the
 * mockups draw them and where `EXPERIENCE.md` says they belong.
 *
 * **Focus moves to the heading on every step change.** The heading takes `tabIndex={-1}`
 * and is focused when the step number changes, so a keyboard or screen-reader user lands
 * on the new step instead of being left where the old step's button used to be. The
 * step label is a `role="status"`, so the change is announced without stealing focus
 * twice.
 */

import { useEffect, useRef } from "react";

import { ONBOARDING_STEP_COUNT } from "./steps";

export type StepShellProps = {
  /** 1, 2 or 3 — the step being shown, which is not always the server's step. */
  step: number;
  title: string;
  lede: string;
  /** Shown on the right of the step label, e.g. "2 of 3 picked". */
  note?: string;
  /** The label on the primary action: the last step's differs. */
  continueLabel: string;
  busy: boolean;
  onBack: (() => void) | null;
  onSkipStep: () => void;
  onSkipAll: () => void;
  onContinue: () => void;
  children: React.ReactNode;
};

export function StepShell({
  step,
  title,
  lede,
  note,
  continueLabel,
  busy,
  onBack,
  onSkipStep,
  onSkipAll,
  onContinue,
  children,
}: StepShellProps) {
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    heading.current?.focus();
  }, [step]);

  return (
    <div className="fade-in mx-auto w-full max-w-(--layout-container-form) px-6 py-12">
      <StepDots step={step} />

      <div className="mt-6 flex items-baseline justify-between gap-4">
        <p role="status" className="[font:var(--type-scale-meta-sm)] tracking-wide text-ink-muted">
          Step {step} of {ONBOARDING_STEP_COUNT} · Optional
        </p>
        {note ? <p className="[font:var(--type-scale-meta-sm)] text-ink-muted">{note}</p> : null}
      </div>

      <h1
        ref={heading}
        tabIndex={-1}
        className="mt-3 text-ink-primary outline-none [font:var(--type-scale-display-md)]"
      >
        {title}
      </h1>
      <p className="mt-4 [font:var(--type-scale-body-lg)] text-ink-secondary">{lede}</p>

      <div className="mt-10">{children}</div>

      <div className="mt-12 flex flex-wrap items-center justify-between gap-4 border-t border-border-subtle pt-6">
        <div className="flex items-center gap-4">
          {onBack ? (
            <button
              type="button"
              onClick={onBack}
              className="[font:var(--type-scale-body-sm)] text-ink-muted"
            >
              ← Back
            </button>
          ) : null}
          <button
            type="button"
            onClick={onSkipAll}
            disabled={busy}
            className="[font:var(--type-scale-body-sm)] text-ink-muted underline underline-offset-4"
          >
            Skip all
          </button>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onSkipStep}
            disabled={busy}
            className="rounded-control px-4 py-2 [font:var(--type-scale-meta-md)] text-ink-secondary"
          >
            Skip for now
          </button>
          <button
            type="button"
            onClick={onContinue}
            disabled={busy}
            aria-busy={busy}
            className="rounded-control bg-accent-terracotta px-5 py-2.5 [font:var(--type-scale-meta-md)] text-ink-inverse disabled:bg-surface-inset disabled:text-ink-faint"
          >
            {continueLabel}
          </button>
        </div>
      </div>

      <p className="mt-4 [font:var(--type-scale-body-sm)] text-ink-muted">
        All steps are skippable. You can change these later in Settings.
      </p>
    </div>
  );
}

/**
 * The three progress dots.
 *
 * Each dot carries its own state in words, because the state is otherwise carried only by
 * colour (WCAG 1.4.1). The group is labelled, so a screen reader reads it as progress
 * rather than as three stray images.
 */
function StepDots({ step }: { step: number }) {
  return (
    <div role="group" aria-label="Onboarding progress" className="flex items-center gap-2">
      {Array.from({ length: ONBOARDING_STEP_COUNT }, (_, index) => {
        const position = index + 1;
        const state = position < step ? "done" : position === step ? "current" : "pending";
        return (
          <span
            key={position}
            aria-label={`Step ${position} of ${ONBOARDING_STEP_COUNT} — ${state}`}
            className={[
              "h-1.5 flex-1 rounded-full",
              state === "current"
                ? "bg-accent-terracotta"
                : state === "done"
                  ? "bg-ink-muted"
                  : "bg-surface-inset",
            ].join(" ")}
          />
        );
      })}
    </div>
  );
}
