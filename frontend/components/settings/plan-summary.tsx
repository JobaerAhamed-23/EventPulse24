"use client";

/**
 * The plan block on `/settings/account` — which plan, and the one way to change it.
 *
 * **Four states, and the third is why this component is not a boolean.** `is_pro` is true
 * for a `past_due` account as well as an `active` one, because a failed payment leaves
 * someone entitled while they fix it. A screen that read only that bool would show a person
 * with a recoverable problem exactly what it shows a person with none — and this is the
 * only place in the product where a failed payment becomes visible at all.
 *
 * **Cancellation is Stripe's, deliberately.** There is no local cancel control and there
 * will not be one: it would be a second write path into subscription state, which the
 * webhook would then have to reconcile against. The portal is the one door.
 *
 * **The date is never called a renewal.** This product does not model
 * `cancel_at_period_end`, so a subscription cancelled in the portal still reads `active`
 * until its term runs out and nothing here can tell the two apart. "Your plan runs until 3
 * March" is true either way; "renews on 3 March" would be a reassuring lie told to exactly
 * the person most likely to be reading this screen — somebody who just cancelled and came
 * to check it worked.
 */
import { useState } from "react";

import { saveFailureMessage } from "@/components/settings/save-failure";
import { api } from "@/lib/backend-client";

export type PlanSummaryProps = {
  /** `active`, `past_due`, `canceled`, `expired`, or `null` for a never-subscribed account. */
  status: string | null;
  /** Whether Pro is available right now. True for `past_due`. */
  isPro: boolean;
  /** Whether a payment failed and the portal is where to fix it. */
  needsPayment: boolean;
  /** Whether this account ever had Pro. */
  hadPro: boolean;
  /** When the current term ends, ISO. **Not a renewal date.** */
  periodEnd: string | null;
};

/** The failure line when the portal cannot be opened. Calm, and it says what to do. */
const PORTAL_FAILED = "Couldn't open your plan. Try again in a moment.";

/**
 * A stored instant as a date a person reads.
 *
 * `undefined` locale, so the browser's own formatting is used rather than a locale this
 * component invents on the user's behalf.
 */
function readableDate(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toLocaleDateString(undefined, {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export function PlanSummary({ status, isPro, needsPayment, hadPro, periodEnd }: PlanSummaryProps) {
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  /**
   * Opening the provider's portal.
   *
   * **A button, not a link**, because the portal URL does not exist until it is minted:
   * `POST /api/billing/portal` creates a session and returns where to go. An anchor would
   * be a link to a page that is not there yet. Same shape as the pricing page's.
   */
  const openPortal = async (): Promise<void> => {
    setBusy(true);
    setFailure(null);
    try {
      const response = await api.POST("/api/billing/portal");
      if (response.data) {
        window.location.assign(response.data.url);
        return;
      }
      // **`|| fallback` because a refusal with no sentence must not render as no
      // refusal at all.** `saveFailureMessage` returns the API's own message
      // whenever the body is the project's error shape — including when that
      // message is empty, which would leave the user staring at an unchanged
      // screen after a failed action.
      setFailure(saveFailureMessage(response.error, PORTAL_FAILED) || PORTAL_FAILED);
    } catch {
      // The request never reached the API, so there is nothing to quote.
      setFailure(PORTAL_FAILED);
    }
    setBusy(false);
  };

  const term = periodEnd ? readableDate(periodEnd) : "";

  return (
    <section aria-label="Your plan" data-plan-summary>
      {isPro ? (
        <>
          <p className="text-ink-primary [font:var(--type-scale-body-md)]" data-plan-state>
            You’re on Pro.
          </p>

          {needsPayment ? (
            // **The one sentence this screen exists for.** It states the fact and points
            // at the fix — no alarm colour, no interruption, nothing the user cannot act
            // on from here.
            <p
              className="mt-2 text-ink-secondary [font:var(--type-scale-body-md)]"
              data-payment-problem
            >
              We couldn’t take your last payment. Update your card to keep Pro.
            </p>
          ) : term ? (
            <p className="mt-2 text-ink-secondary [font:var(--type-scale-body-md)]" data-plan-term>
              Your plan runs until {term}.
            </p>
          ) : null}

          <button
            type="button"
            onClick={openPortal}
            disabled={busy}
            aria-busy={busy}
            data-portal-button
            className="mt-6 min-h-[44px] rounded-control border border-border-strong px-4 py-3 text-ink-primary [font:var(--type-scale-meta-md)] disabled:cursor-default"
          >
            {busy ? "Opening…" : needsPayment ? "Update payment" : "Manage subscription"}
          </button>

          {failure ? (
            <p
              role="alert"
              className="mt-2 text-warn-amber [font:var(--type-scale-body-sm)]"
              data-portal-failed
            >
              {failure}
            </p>
          ) : null}
        </>
      ) : (
        <>
          <p className="text-ink-primary [font:var(--type-scale-body-md)]" data-plan-state>
            You’re on the free plan.
          </p>

          {/*
            **A lapsed subscriber is not a new account.** Showing them the blank copy a
            brand-new user sees would quietly erase a relationship they paid for, so when
            we know Pro ended, the screen says so.
          */}
          {hadPro ? (
            <p className="mt-2 text-ink-secondary [font:var(--type-scale-body-md)]" data-plan-ended>
              {term ? `Your Pro plan ended on ${term}.` : "Your Pro plan has ended."}
            </p>
          ) : null}

          {/*
            **A quiet link, in the register the cap prompts use.** Not a button, not a
            banner: the free plan is a legitimate place to be.
          */}
          <a
            href="/pricing"
            data-pricing-link
            className="mt-4 inline-block [font:var(--type-scale-body-sm)] text-accent-terracotta underline underline-offset-4"
          >
            See what Pro adds
          </a>
        </>
      )}

      {/*
        The status is in the markup for tests and for anyone reading the DOM, never as
        user-facing copy — "past_due" is a word from a payment processor, not from a person.
      */}
      <span hidden data-plan-status={status ?? "none"} />
    </section>
  );
}
