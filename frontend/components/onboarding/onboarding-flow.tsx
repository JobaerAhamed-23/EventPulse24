"use client";

/**
 * The onboarding flow: three optional steps, and the rule that keeps the screen and the
 * server agreeing about which one you are on.
 *
 * **There are two step numbers, and conflating them skips a step.** The step endpoints
 * take no body — `POST /api/personal/onboarding/step` advances *the server's* current
 * step, whatever the screen happens to be showing. The mockups have a Back button, and
 * the server has no "go back": `current_step` records how far someone **got**, which is
 * what the 7-day resume rule restores. So:
 *
 *   - `serverStep` is what the API last told us,
 *   - `viewStep` is what is on screen,
 *   - Back moves `viewStep` only and calls nothing,
 *   - Continue and Skip call the API **only when `viewStep === serverStep`**.
 *
 * Without that last rule, going Back from step 2 and pressing Continue would advance the
 * server from 2 to 3 while the screen went from 1 to 2 — the user would never see step 3,
 * and the flow would finish a step they never answered.
 *
 * Saving is independent of position: the interests and digest `PUT`s address their own
 * resources, so they still work from a revisited step.
 */

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { components } from "@/lib/api/schema";
import { readApiError } from "@/lib/api-errors";
import { api } from "@/lib/backend-client";

import { CalendarStep } from "./calendar-step";
import { DigestStep, type DigestValues, initialDigestValues } from "./digest-step";
import { InterestsStep, pickedNote } from "./interests-step";
import { StepShell } from "./step-shell";
import { CALENDAR_STEP, DIGEST_STEP, INTERESTS_STEP, ONBOARDING_STEP_COUNT } from "./steps";

type OnboardingState = components["schemas"]["OnboardingStateOut"];
type Chip = components["schemas"]["InterestChipOut"];
type Connection = components["schemas"]["CalendarConnectionOut"];

export type OnboardingFlowProps = {
  /** The server's state, read with the first paint — this is what makes resume work. */
  state: OnboardingState;
  /** The ten chips, read alongside it. */
  chips: Chip[];
  /** A calendar the user has already connected, if any. */
  connection: Connection | null;
};

const TITLES: Record<number, { title: string; lede: string; continueLabel: string }> = {
  [CALENDAR_STEP]: {
    title: "Connect a calendar?",
    lede: "We'll surface your personal events alongside public ones — birthdays, dinners, hard-to-get tickets — in the same calm brief. Read-only access. You can disconnect anytime.",
    continueLabel: "Continue →",
  },
  [INTERESTS_STEP]: {
    title: "What kinds of things?",
    lede: "Pick up to three. We'll bias your brief toward them — and your serendipity slot toward something else. Skip and we'll learn from your first week instead.",
    continueLabel: "Continue →",
  },
  [DIGEST_STEP]: {
    title: "When should we ping you?",
    lede: "One calm Pulse Ping per day. It links to your brief. You can change this anytime — and quiet hours come later in Settings.",
    continueLabel: "Open my brief →",
  },
};

export function OnboardingFlow({ state, chips, connection }: OnboardingFlowProps) {
  const router = useRouter();
  const startingStep = state.current_step ?? CALENDAR_STEP;
  const [serverStep, setServerStep] = useState(startingStep);
  const [viewStep, setViewStep] = useState(startingStep);
  const [interests, setInterests] = useState<string[]>(state.interests ?? []);
  const [digest, setDigest] = useState<DigestValues>(initialDigestValues(state.digest ?? {}));
  const [digestError, setDigestError] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  /** The onboarding is over: the home decides what comes next. */
  const finish = (): void => {
    router.replace("/");
    router.refresh();
  };

  /**
   * Move the server on by one, and follow its answer.
   *
   * A 409 means the onboarding was finished somewhere else — another tab, another device.
   * There is nothing left to do here, so the user goes home rather than being told off.
   */
  const advance = async (
    path: "/api/personal/onboarding/step" | "/api/personal/onboarding/step/skip",
  ): Promise<void> => {
    let response;
    try {
      response = await api.POST(path);
    } catch (thrown) {
      // The request never left the browser (openapi-fetch rethrows a failed `fetch`).
      // The server's step is untouched, so pressing the button again is all it takes —
      // but only if the button comes back, which is what `setBusy(false)` is for.
      setFailure(readApiError(thrown).message);
      setBusy(false);
      return;
    }
    if (response.error) {
      const error = readApiError(response.error);
      if (error.code === "onboarding_already_complete") {
        finish();
        return;
      }
      setFailure(error.message);
      setBusy(false);
      return;
    }
    const next = response.data;
    // No step left to be on means the flow is over — `completed` and a missing
    // `current_step` are the same news.
    const step = next.current_step ?? null;
    if (next.completed || step === null) {
      finish();
      return;
    }
    setServerStep(step);
    setViewStep(step);
    setBusy(false);
  };

  /** Save whatever the live step holds, before it is left behind. */
  const saveCurrentStep = async (): Promise<boolean> => {
    if (viewStep === INTERESTS_STEP) {
      try {
        const response = await api.PUT("/api/personal/onboarding/interests", {
          body: { chip_keys: interests },
        });
        if (response.error) {
          setFailure(readApiError(response.error).message);
          return false;
        }
      } catch (thrown) {
        setFailure(readApiError(thrown).message);
        return false;
      }
    }
    if (viewStep === DIGEST_STEP) {
      try {
        const response = await api.PUT("/api/personal/onboarding/digest-preference", {
          body: { delivery_time: digest.deliveryTime, timezone: digest.timezone },
        });
        if (response.error) {
          const error = readApiError(response.error);
          setDigestError(error.fieldErrors.delivery_time ?? error.message);
          return false;
        }
      } catch (thrown) {
        // Nothing was stored, so the step stays where it is with the values intact.
        setFailure(readApiError(thrown).message);
        return false;
      }
    }
    return true;
  };

  const onContinue = async (): Promise<void> => {
    setFailure(null);
    setDigestError(null);

    // Revisiting a step the server has already passed: the screen moves, the server does
    // not. Advancing here would push the server past a step the user has not seen.
    if (viewStep < serverStep) {
      setViewStep(viewStep + 1);
      return;
    }

    setBusy(true);
    if (!(await saveCurrentStep())) {
      setBusy(false);
      return;
    }
    await advance("/api/personal/onboarding/step");
  };

  const onSkipStep = async (): Promise<void> => {
    setFailure(null);
    if (viewStep < serverStep) {
      // Skipping a step that is already behind the server would skip the *live* one.
      setViewStep(viewStep + 1);
      return;
    }
    setBusy(true);
    await advance("/api/personal/onboarding/step/skip");
  };

  const onSkipAll = async (): Promise<void> => {
    setFailure(null);
    setBusy(true);
    let response;
    try {
      response = await api.POST("/api/personal/onboarding/skip-all");
    } catch (thrown) {
      setFailure(readApiError(thrown).message);
      setBusy(false);
      return;
    }
    if (response.error) {
      const error = readApiError(response.error);
      if (error.code === "onboarding_already_complete") {
        finish();
        return;
      }
      setFailure(error.message);
      setBusy(false);
      return;
    }
    finish();
  };

  const onBack = viewStep > CALENDAR_STEP ? () => setViewStep(viewStep - 1) : null;

  const copy = TITLES[viewStep] ?? TITLES[CALENDAR_STEP];

  return (
    <StepShell
      step={viewStep}
      title={copy.title}
      lede={copy.lede}
      note={viewStep === INTERESTS_STEP ? pickedNote(interests.length) : undefined}
      continueLabel={viewStep === ONBOARDING_STEP_COUNT ? copy.continueLabel : "Continue →"}
      busy={busy}
      onBack={onBack}
      onSkipStep={onSkipStep}
      onSkipAll={onSkipAll}
      onContinue={onContinue}
    >
      {failure ? (
        <p
          role="alert"
          className="mb-6 flex items-start gap-2 rounded-card border border-signal-warn/40 bg-surface-subtle px-4 py-3 [font:var(--type-scale-body-sm)] text-signal-warn"
        >
          <span aria-hidden="true">⚠</span>
          <span>{failure}</span>
        </p>
      ) : null}

      {viewStep === CALENDAR_STEP ? <CalendarStep existing={connection} /> : null}
      {viewStep === INTERESTS_STEP ? (
        <InterestsStep chips={chips} picked={interests} onChange={setInterests} />
      ) : null}
      {viewStep === DIGEST_STEP ? (
        <DigestStep values={digest} onChange={setDigest} error={digestError} />
      ) : null}
    </StepShell>
  );
}
